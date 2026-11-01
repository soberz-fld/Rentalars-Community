# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "surcharges": the list of rules and own holidays (PER-040).

* Einstellungen → Zuschläge: add a rule with the button, choose "an Wochentagen" – the fields of the kind show –,
  move it up with the keyboard-reachable buttons, save; add an own holiday.
* "Nach § 3b EStG einstellen" asks first, then sets the rules of the law.
* On a phone without horizontal scrolling and checked with axe-core (NFA-025), with a new row added.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import SkipTest

from rentalars.core.models import OwnHoliday, TimeSurchargeRule
from rentalars.core.surcharges import load_rule_set
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path

URL = "/administration/surcharges/"


class RulesInBrowserTests(BrowserTestCase):
    """PER-040: the list of rules grows, changes its order and shows the fields of each kind."""

    def setUp(self) -> None:
        super().setUp()
        load_rule_set()

    def test_add_a_rule_move_it_and_save(self) -> None:
        self.open(URL)
        rules = self.page.locator("[data-formset=rules]")
        self.assertEqual(rules.locator("[data-formset-row]").count(), 10)  # nine and the empty one
        rules.get_by_role("button", name="Regel hinzufügen").click()
        row = rules.locator("[data-formset-row]", has=self.page.locator("input[name=rules-10-name]"))
        self.assertEqual(self.page.locator("input[name=rules-TOTAL_FORMS]").input_value(), "11")
        self.assertTrue(
            row.locator("input[name=rules-10-name]").evaluate("element => element === document.activeElement")
        )
        row.locator("input[name=rules-10-name]").fill("Samstag")
        self.assertTrue(row.locator("input[name=rules-10-time_until]").is_visible())
        row.locator("select[name=rules-10-kind]").select_option("weekday")
        self.assertFalse(row.locator("input[name=rules-10-time_until]").is_visible())
        row.get_by_label("Sa", exact=True).check()
        row.locator("input[name=rules-10-time_from]").fill("13:00")
        row.locator("input[name=rules-10-price_percent]").fill("25")
        # Up past the empty row of the page and the last rule of the law.
        row.get_by_role("button", name="Regel nach oben").click()
        row.get_by_role("button", name="Regel nach oben").click()
        self.assertIn("Stelle 9", self.page.locator("[data-formset=rules] [aria-live]").inner_text())
        with self.page.expect_navigation():
            self.page.get_by_role("button", name="Einstellungen speichern").click()
        self.assertIn("Einstellungen gespeichert.", self.page.inner_text("main"))
        saturday = TimeSurchargeRule.objects.get(name="Samstag")
        self.assertEqual((saturday.weekdays, saturday.price_percent), ("6", Decimal("25")))
        order = list(TimeSurchargeRule.objects.order_by("position", "id").values_list("name", flat=True))
        self.assertEqual(order.index("Samstag"), 8)

    def test_an_own_holiday(self) -> None:
        self.open(URL)
        holidays = self.page.locator("[data-formset=holidays]")
        row = holidays.locator("[data-formset-row]").first
        row.locator("input[name=holidays-0-name]").fill("Ostermontag")
        row.locator("select[name=holidays-0-kind]").select_option("easter")
        self.assertFalse(row.locator("input[name=holidays-0-day]").is_visible())
        row.locator("input[name=holidays-0-easter_offset]").fill("1")
        with self.page.expect_navigation():
            self.page.get_by_role("button", name="Einstellungen speichern").click()
        self.assertEqual(OwnHoliday.objects.get().easter_offset, 1)
        self.assertIn("Ostermontag eigener", self.text_of("#holidays"))

    def test_the_button_of_section_3b_asks_first(self) -> None:
        for rule in TimeSurchargeRule.objects.all():
            rule.delete()
        self.open(URL)
        self.page.get_by_role("button", name="Nach § 3b EStG einstellen").click()
        with self.page.expect_navigation():
            self.confirm()
        self.assertIn("Die Regeln nach § 3b EStG sind eingestellt.", self.page.inner_text("main"))
        self.assertEqual(TimeSurchargeRule.objects.count(), 9)


class RulesOnAPhoneTests(BrowserTestCase):
    """PER-040: the page on a phone, with axe-core – also with a row added by the button."""

    bypass_csp = True

    def test_settings_page(self) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        load_rule_set()
        for width in (375, 1280, 1920):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.open(URL)
                self.page.wait_for_load_state("networkidle")
                self.page.get_by_role("button", name="Regel hinzufügen").click()
                self.page.get_by_role("button", name="Feiertag hinzufügen").click()
                scroll = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(scroll, width)
                self.page.add_script_tag(path=str(axe))
                findings = self.page.evaluate(
                    "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
                    ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' '))"
                    ".join(' | '))",
                    WCAG_AA,
                )
                self.assertEqual(findings, [], "\n".join(findings))
