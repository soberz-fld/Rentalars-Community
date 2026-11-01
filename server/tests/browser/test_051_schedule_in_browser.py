# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: the week grid, the hour timelines and the planning pages on a phone (VFG-020 to VFG-023).

The page tests read the HTML; only a browser shows that blocks stand side
by side, that the grid opens at the working hours, and that scrolling an hour
timeline to its end loads the next day (static/js/app.js).
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.personnel.models import AvailabilityMark, Person
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import at, make_project, plan


class WeekGridInBrowserTests(BrowserTestCase):
    """VFG-021: the tests run on Monday, 1 March 2027, 08:00."""

    def setUp(self) -> None:
        super().setUp()
        self.talk = make_project("Vortrag", start=at(2, 10), end=at(2, 12))
        self.party = make_project("Kinderfest", start=at(2, 11), end=at(2, 17))

    def block(self, project: object) -> dict[str, float]:
        # a block opens the project's Überblick – adapted.
        box = self.page.locator(f'.wk-event[href="/projects/{project.number}/overview/"]').bounding_box()
        assert box is not None
        return box

    def test_opens_at_six_with_blocks_side_by_side(self) -> None:
        self.open("/schedule/?view=week&week=2027-03-01")
        hour = self.page.locator(".wk-hour").first.bounding_box()["height"]
        scrolled, room = self.page.evaluate(
            "(() => { const s = document.querySelector('.wk-scroll'); return [s.scrollTop, s.scrollHeight - s.clientHeight]; })()"
        )
        # At 06:00 – or as far as it goes when the window shows the rest of the day anyway.
        self.assertAlmostEqual(scrolled, min(6 * hour, room), delta=2)
        self.assertGreater(scrolled, 0)
        talk, party = self.block(self.talk), self.block(self.party)
        self.assertLessEqual(talk["x"] + talk["width"], party["x"] + 1, "the blocks overlap instead of standing apart")
        self.assertAlmostEqual(party["y"] - talk["y"], hour, delta=2)
        self.assertAlmostEqual(party["height"] / talk["height"], 3, delta=0.25)
        self.assertEqual(self.page.locator(".wk-col.today [data-now]").count(), 1)

    def test_a_click_opens_the_project(self) -> None:
        self.open("/schedule/?view=week&week=2027-03-01")
        # the click opens the project's Überblick – adapted.
        self.page.locator(f'.wk-event[href="/projects/{self.talk.number}/overview/"]').click()
        # The Überblick is the first tab, the page at ".../deployment/" – the address redirects there.
        self.page.wait_for_url(f"**/projects/{self.talk.number}/deployment/")

    def test_all_day_entries_open_and_close(self) -> None:
        for number in range(5):
            make_project(f"Messe {number}", start=at(2), end=at(4))
        self.open("/schedule/?view=week&week=2027-03-01")
        extra = self.page.locator(".wk-bar.is-extra")
        self.assertGreater(extra.count(), 0)
        self.assertFalse(extra.first.is_visible())
        self.page.locator(".wk-more").first.click()
        self.assertTrue(extra.first.is_visible())
        self.assertEqual(self.page.evaluate("document.activeElement.className"), "wk-less")
        self.page.keyboard.press("Enter")
        self.assertFalse(extra.first.is_visible())


class HourTimelineInBrowserTests(BrowserTestCase):
    """VFG-022: the hour timeline opens at the chosen day and moves on while scrolling."""

    def test_scrolling_to_the_end_loads_the_next_day(self) -> None:
        make_project("Vortrag", start=at(1, 10), end=at(1, 12))
        self.open("/schedule/timeline/?days=1&from=2027-03-01")
        panel = "document.querySelector('[data-tl-zoom]')"
        start = self.page.evaluate(f"{panel}.scrollLeft")
        self.assertGreater(start, 0, "the timeline does not open at the chosen day")
        self.page.evaluate(f"(() => {{ const p = {panel}; p.scrollLeft = p.scrollWidth; }})()")
        self.page.wait_for_function("() => location.search.includes('from=2027-03-02')")
        self.settle()
        self.assertIn("Di 02.03.2027", self.text_of("[data-tl-range]"))
        self.assertIn("Di 02.03.2027", self.text_of("[data-tl-announce]"))
        # The view stayed where it was: no longer at the end, so the next scroll can move on again.
        left, width, client = self.page.evaluate(f"[{panel}.scrollLeft, {panel}.scrollWidth, {panel}.clientWidth]")
        self.assertLess(left + client, width - 2)
        self.assertGreater(left, 0)

    def test_personnel_plan_in_hours_with_a_warning(self) -> None:
        anna = Person.objects.get(first_name="Anna")
        plan(make_project("Vortrag", start=at(1, 8), end=at(1, 18)), "Tontechnik", anna, start=at(1, 9), end=at(1, 12))
        AvailabilityMark.objects.create(person=anna, start=at(1), end=at(2), state="unavailable")
        self.open("/schedule/personnel/?days=1&from=2027-03-01")
        badge = self.page.locator(".tl-label.person.has-warning .plan-warning").first
        self.assertTrue(badge.is_visible())
        self.assertIn("nicht verfügbar", badge.get_attribute("title") or "")
        self.assertTrue(self.page.locator(".tl-avail .availability.is-unavailable").first.is_visible())


class PlanningOnAPhoneTests(BrowserTestCase):
    """NFA-022: the planning pages fit 360 pixels; wide grids scroll inside themselves."""

    viewport = {"width": 360, "height": 740}

    def test_planning_pages_fit_the_width_of_a_phone(self) -> None:
        make_project("Vortrag", start=at(2, 10), end=at(2, 12))
        pages = ["/schedule/?view=month", "/schedule/?view=week", "/schedule/timeline/?days=1"]
        pages += ["/schedule/timeline/?days=3", "/schedule/personnel/?days=2", "/schedule/personnel/"]
        for path in pages:
            with self.subTest(page=path):
                self.open(path)
                width = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(width, 360, f"{path} is {width} pixels wide")
        self.open("/schedule/?view=week&week=2027-03-01")
        today = self.page.locator(".wk-col.today").bounding_box()
        self.assertLess(today["x"], 360)


class AccessibilityOfTheNewViewsTests(BrowserTestCase):
    """NFA-025 with axe-core, for the views the main page list does not open (zoom levels, filled week)."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def test_no_findings(self) -> None:
        make_project("Vortrag", start=at(2, 10), end=at(2, 12))
        make_project("Messe", start=at(1, 8), end=at(4, 18))
        anna = Person.objects.get(first_name="Anna")
        AvailabilityMark.objects.create(person=anna, start=at(1), end=at(3), state="limited")
        findings: list[str] = []
        for path in (
            "/schedule/?view=week&week=2027-03-01",
            "/schedule/?view=month&month=2027-03",
            "/schedule/timeline/?days=1&from=2027-03-02",
            "/schedule/timeline/?days=3&from=2027-03-11",
            "/schedule/personnel/?days=2&from=2027-03-01",
            "/schedule/personnel/?weeks=4&from=2027-03-08",
        ):
            self.open(path)
            self.page.wait_for_load_state("networkidle")
            self.page.add_script_tag(path=str(self.axe))
            result = self.page.evaluate(
                "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
                ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
                WCAG_AA,
            )
            findings += [f"{path}: {finding}" for finding in result]
        self.assertEqual(findings, [], "\n".join(findings))
