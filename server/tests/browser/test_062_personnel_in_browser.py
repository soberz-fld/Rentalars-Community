# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the week of the availability calendar (PER-030), on the desk and on the phone.

``RENTALARS_SHOTS=/some/folder`` keeps screenshots of the week for looking at it.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import SkipTest

from rentalars.accounts.models import User
from rentalars.personnel import marks as availability_marks
from rentalars.personnel import services
from rentalars.personnel.models import AvailabilityMark, AvailabilitySource, AvailabilityState
from tests.browser.base import BrowserTestCase
from tests.helpers import at, job_function, make_project, plan

RED, YELLOW = AvailabilityState.UNAVAILABLE, AvailabilityState.LIMITED


def _shot(page: object, name: str) -> None:
    folder = os.environ.get("RENTALARS_SHOTS", "")
    if folder:
        page.screenshot(path=str(Path(folder) / f"{name}.png"), full_page=True)  # type: ignore[attr-defined]


class _WeekData:
    """Anna's week of 8 to 14 March 2027: an evening not available, busy times, two deployments."""

    def week_data(self) -> None:
        anna = User.objects.get(username="anna").person
        services.set_rate(anna, job_function("Tontechnik"))
        availability_marks.mark_period(anna, at(8), at(9), AvailabilityState.AVAILABLE)
        availability_marks.mark_period(anna, at(10, 18), at(10, 23), RED, "Probe mit der Band")
        AvailabilityMark.objects.create(
            person=anna, start=at(11, 9), end=at(11, 12), state=RED, source=AvailabilitySource.FEED
        )
        plan(make_project("Stadtfest Süd", start=at(10, 8), end=at(10, 20)), "Tontechnik", anna)
        plan(make_project("Messe Nord", start=at(12, 7), end=at(12, 15)), "Tontechnik", anna)
        self.anna = anna


class WeekViewInBrowserTests(_WeekData, BrowserTestCase):
    def test_switch_to_the_week_tap_two_days_and_colour_them(self) -> None:
        self.week_data()
        self.open("/me/availability/?month=2027-03")
        self.page.locator(".avail-views a", has_text="Woche").click()
        self.page.wait_for_load_state("networkidle")
        self.open("/me/availability/?view=week&week=2027-03-10")
        grid = self.page.locator("[data-week-grid]")
        self.assertTrue(grid.is_visible())
        self.assertEqual(self.page.locator(".avail-dayhead").count(), 7)
        # The grid opens at 06:00: the hours before are scrolled away.
        self.assertGreater(self.page.locator(".wk-scroll").evaluate("element => element.scrollTop"), 0)
        band = self.page.locator(".wk-col[data-day='2027-03-10'] .wk-band.unavailable")
        self.assertIn("Probe mit der Band", band.inner_text())
        deployment = self.page.locator(".wk-col[data-day='2027-03-10'] .wk-event.avail-deploy")
        self.assertIn("clash", deployment.get_attribute("class") or "")
        # The band stays visible at the left of the deployment.
        band_box, deployment_box = band.bounding_box(), deployment.bounding_box()
        self.assertLess(band_box["x"] + 10, deployment_box["x"])  # type: ignore[index]
        _shot(self.page, "062-week-desk")
        self.page.locator('.avail-dayhead[data-avail-day="2027-03-13"]').click()
        self.page.locator('.avail-dayhead[data-avail-day="2027-03-14"]').click()
        self.assertEqual(self.page.input_value("input[name=start_day]"), "2027-03-13")
        self.assertEqual(self.page.input_value("input[name=end_day]"), "2027-03-14")
        self.assertEqual(
            self.page.locator('.avail-dayhead[data-avail-day="2027-03-13"]').get_attribute("aria-pressed"), "true"
        )
        self.page.click("button[name=state][value=limited]")
        self.page.wait_for_load_state("networkidle")
        self.assertIn("/me/availability/?view=week&week=2027-03-08", self.page.url)
        self.assertIn("Verfügbarkeit gespeichert.", self.page.locator(".messages").inner_text())
        self.assertEqual(self.page.locator(".avail-dayhead.limited").count(), 2)
        self.assertTrue(AvailabilityMark.objects.filter(person=self.anna, state=YELLOW).exists())
        # Next week and back to the month.
        self.page.locator(".avail-nav a", has_text="nächste Woche").click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("KW 11", self.page.locator(".avail-nav h3").inner_text())
        self.page.locator(".avail-views a", has_text="Monat").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(self.page.locator(".avail-grid").count(), 1)


class WeekViewOnThePhoneTests(_WeekData, BrowserTestCase):
    viewport = {"width": 360, "height": 740}

    def test_the_week_scrolls_inside_its_frame(self) -> None:
        self.week_data()
        self.open("/me/availability/?view=week&week=2027-03-10")
        self.page.wait_for_load_state("networkidle")
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        scroller = self.page.locator(".avail-week .wk-scroll")
        self.assertGreater(scroller.evaluate("element => element.scrollWidth - element.clientWidth"), 0)
        _shot(self.page, "062-week-phone")
        # The heads stay tappable on the phone.
        self.page.locator('.avail-dayhead[data-avail-day="2027-03-09"]').click()
        self.assertEqual(self.page.input_value("input[name=start_day]"), "2027-03-09")


class WeekViewAccessibilityTests(_WeekData, BrowserTestCase):
    """NFA-025 for the week: no finding of axe-core (needs ``RENTALARS_AXE``)."""

    bypass_csp = True

    def test_no_findings(self) -> None:
        from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path

        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.week_data()
        findings: list[str] = []
        for path in (
            "/me/availability/?view=week&week=2027-03-10",
            f"/personnel/people/{self.anna.pk}/availability/?view=week&week=2027-03-10",
            f"/personnel/people/{self.anna.pk}/timeline/?from=2027-03-08",
        ):
            self.open(path)
            self.page.wait_for_load_state("networkidle")
            self.page.add_script_tag(path=str(axe))
            result = self.page.evaluate(
                "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
                ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' '))"
                ".join(' | '))",
                WCAG_AA,
            )
            findings += [f"{path}: {finding}" for finding in result]
        self.assertEqual(findings, [], "\n".join(findings))
