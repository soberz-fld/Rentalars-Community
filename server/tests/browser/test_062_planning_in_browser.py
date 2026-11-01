# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: suggestions on the utilization page (VFG-025), 1 to 10 days (VFG-024), phases as long as they last.

The page tests read the HTML; only a browser shows that the suggestions
open as a combobox a screen reader can follow, that choosing one shows the
product, and that a bar is drawn as wide as its period.
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.projects.models import ProjectPhase
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import at, make_project


class UtilizationSuggestionsInBrowserTests(BrowserTestCase):
    """VFG-025: typing shows suggestions; choosing one shows that product."""

    def test_choose_a_suggestion_with_the_keyboard(self) -> None:
        self.open("/schedule/products/?from=2027-03-01")
        field = self.page.locator("#f-q")
        self.assertEqual(field.get_attribute("role"), "combobox")
        self.assertEqual(field.get_attribute("aria-expanded"), "false")
        field.click()
        field.press_sequentially("Moving", delay=20)
        options = self.page.locator(".typeahead [role=option]")
        options.first.wait_for()
        self.assertEqual(field.get_attribute("aria-expanded"), "true")
        listbox = field.get_attribute("aria-controls")
        self.assertEqual(self.page.locator(f"#{listbox}").get_attribute("role"), "listbox")
        self.assertEqual(field.get_attribute("aria-activedescendant"), options.first.get_attribute("id"))
        self.assertIn("Moving Head", options.first.inner_text())
        field.press("Enter")
        self.page.wait_for_url("**/schedule/products/?*product=*")
        self.assertIn("Moving Head Spot", self.text_of(".panel.timeline"))
        self.assertEqual(self.page.locator(".panel.timeline .tl-label").count(), 2)  # the head and one product
        self.assertIn("L-020 Moving Head Spot", self.page.input_value("#f-q"))

    def test_choosing_a_category_afterwards_shows_the_category(self) -> None:
        self.open("/schedule/products/?from=2027-03-01")
        field = self.page.locator("#f-q")
        field.click()
        field.press_sequentially("Moving", delay=20)
        self.page.locator(".typeahead [role=option]").first.click()
        self.page.wait_for_url("**/schedule/products/?*product=*")
        self.page.select_option("#f-category", label="Kabel")
        self.page.wait_for_url("**/schedule/products/?*category=*")
        self.assertNotIn("product=", self.page.url)
        self.assertIn("XLR-Kabel", self.text_of(".panel.timeline"))


class DaysInBrowserTests(BrowserTestCase):
    """VFG-024 and the bug: up to ten days, bars as long as their periods."""

    def test_choose_ten_days(self) -> None:
        self.open("/schedule/timeline/?days=3&from=2027-03-01")
        self.page.select_option("#f-days", "10")
        self.page.wait_for_url("**/schedule/timeline/?*days=10*")
        panel = self.page.locator("[data-tl-zoom]")
        self.assertEqual(panel.get_attribute("data-columns"), "200")  # VFG-033: two spans before and after
        self.assertGreater(self.page.evaluate("document.querySelector('[data-tl-zoom]').scrollLeft"), 0)
        self.assertIn("Mo 01.03.2027 – Mi 10.03.2027", self.text_of("[data-tl-range]"))

    def test_a_phase_is_as_wide_as_its_hours(self) -> None:
        project = make_project("Messe", start=at(10, 8), end=at(12, 22))
        ProjectPhase.objects.create(project=project, kind="setup", start=at(10, 12), end=at(10, 18))
        self.open("/schedule/timeline/?from=2027-03-08&weeks=1")
        day = self.page.locator(".tl-head .tl-day").nth(2).bounding_box()
        # The sample project has phases in this week as well (PRJ-092): the bar in the row of the fair.
        row = self.page.locator(".tl-row", has=self.page.locator(".tl-bar", has_text="Messe"))
        phase = row.locator(".tl-bar.phase").bounding_box()
        assert day is not None and phase is not None
        # 12:00 to 18:00: from the middle of Wednesday, a quarter of the day wide (the bar keeps 1 px at each end).
        self.assertAlmostEqual(phase["x"], day["x"] + day["width"] / 2 + 1, delta=2)
        self.assertAlmostEqual(phase["width"], day["width"] / 4 - 2, delta=2)

    def test_ten_days_fit_the_width_of_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 360, "height": 740})
        for path in ("/schedule/timeline/?days=10", "/schedule/personnel/?days=10", "/schedule/products/"):
            with self.subTest(page=path):
                self.open(path)
                width = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(width, 360, f"{path} is {width} pixels wide")


class AccessibilityOfThePlanningWishesTests(BrowserTestCase):
    """NFA-025 with axe-core: the days control, ten days, the utilization with open suggestions."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def run_axe(self) -> list[str]:
        self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def test_no_findings(self) -> None:
        make_project("Messe", start=at(1, 8), end=at(4, 18))
        findings: list[str] = []
        for path in ("/schedule/timeline/?days=10&from=2027-03-01", "/schedule/personnel/?days=7&from=2027-03-01"):
            self.open(path)
            self.page.wait_for_load_state("networkidle")
            findings += [f"{path}: {finding}" for finding in self.run_axe()]
        self.open("/schedule/products/?from=2027-03-01")
        field = self.page.locator("#f-q")
        field.click()
        field.press_sequentially("Moving", delay=20)
        self.page.locator(".typeahead [role=option]").first.wait_for()
        findings += [f"utilization with suggestions: {finding}" for finding in self.run_axe()]
        self.assertEqual(findings, [], "\n".join(findings))
