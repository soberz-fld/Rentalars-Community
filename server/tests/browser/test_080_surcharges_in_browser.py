# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "surcharges": surcharges for night, Sunday and holidays (PER-009).

* Einstellungen → Zuschläge: switch on, choose a state, change a percentage, save – the page shows the holidays
  of the state.
* The planning: a crew line from Saturday evening into Sunday shows the surcharges; switching them off in its
  dialog updates the planning without a page of its own.
* On a phone without horizontal scrolling and checked with axe-core (NFA-025): the settings page, the planning
  with surcharges and the dialog of the crew line.
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.core.models import TimeSurchargeRule, TimeSurchargeSettings
from rentalars.projects.models import CrewBilling, CrewLine
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import at, job_function, make_person, plan


def surcharge_line(project: object) -> CrewLine:
    """Switch the surcharges on and plan Saturday 18:00 to Sunday 02:00 at 45.00 an hour."""
    settings = TimeSurchargeSettings.load()
    settings.on_price = settings.on_costs = True
    settings.save()
    function = job_function("Tontechnik Nacht", price="45.00", guide="30.00")
    anna = make_person("Nora Nacht", rates={"Tontechnik Nacht": "30.00"})
    return plan(project, function, anna, start=at(13, 18), end=at(14, 2), billing=CrewBilling.PLAN)


class SurchargesInBrowserTests(BrowserTestCase):
    """PER-009: the settings page and the switches of a crew line."""

    def test_the_settings_page(self) -> None:
        self.open("/administration/surcharges/")
        form = self.page.locator("form#time-surcharges")
        form.locator("input[name=on_price]").check()
        form.locator("select[name=state]").select_option("BW")
        form.locator("input[name=rules-0-price_percent]").fill("30")  # PER-040: the night is a rule
        with self.page.expect_navigation():
            form.get_by_role("button", name="Einstellungen speichern").click()
        self.assertIn("Einstellungen gespeichert.", self.page.inner_text("main"))
        self.assertIn("Fronleichnam", self.text_of("#holidays"))
        settings = TimeSurchargeSettings.load()
        night = TimeSurchargeRule.objects.get(code="night")
        self.assertEqual((settings.on_price, settings.state, str(night.price_percent)), (True, "BW", "30.00"))
        self.assertEqual(self.page.locator("input[name=rules-0-price_percent]").input_value(), "30")

    def test_switching_off_a_line(self) -> None:
        line = surcharge_line(self.project)
        self.open_planning()
        row = self.page.locator(f"tr[data-crew-line='{line.pk}']")
        self.assertIn("inkl. Zuschläge 126,00 €", " ".join(row.inner_text().split()))
        row.get_by_role("button", name="Personalposition bearbeiten").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        checkbox = dialog.locator("input[name=time_surcharges_on_price]")
        self.assertTrue(checkbox.is_checked())
        checkbox.uncheck()
        dialog.get_by_role("button", name="Personalposition speichern").click()
        self.page.locator("dialog#dialog[open]").wait_for(state="detached")
        self.settle()
        row = self.page.locator(f"tr[data-crew-line='{line.pk}']")
        text = " ".join(row.inner_text().split())
        self.assertNotIn("inkl. Zuschläge 126,00 €", text)
        self.assertIn("inkl. Zuschläge 84,00 €", text)  # the costs keep theirs
        self.assertFalse(CrewLine.objects.get(pk=line.pk).time_surcharges_on_price)


class SurchargesOnAPhoneTests(BrowserTestCase):
    """PER-009: the new page and parts on a phone, with axe-core."""

    bypass_csp = True

    def check(self, path: str, *, then: str = "") -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        if then:
            self.page.locator(then).first.click()
            self.page.locator("dialog#dialog[open]").wait_for()
            self.settle()
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375, path)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def test_settings_page(self) -> None:
        self.check("/administration/surcharges/")

    def test_planning_with_surcharges(self) -> None:
        surcharge_line(self.project)
        self.check(f"/projects/{self.project.pk}/")

    def test_dialog_of_the_crew_line(self) -> None:
        line = surcharge_line(self.project)
        self.check(f"/projects/{self.project.pk}/", then=f"tr[data-crew-line='{line.pk}'] .icon-btn")

    def test_price_overview(self) -> None:
        surcharge_line(self.project)
        self.check(f"/projects/{self.project.pk}/prices/")
