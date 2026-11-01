# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "ui", in a real browser: grouped tables (UIX-040) and one picker symbol per field (UIX-042).

* UIX-040: "Gruppieren nach" applies at once; the grouped tables pass axe-core on a desk and on a phone, without
  horizontal scrolling of the page.
* UIX-042: in date, date-and-time and time fields only Rentalars' picker button shows – the browser's own
  calendar or clock symbol is hidden; typing a date or a time into the field still works. Checked in Chromium,
  the browser of these tests. Firefox draws its symbol in a way no page can hide; there Rentalars' button lies
  over it (static/css/app.css, block UIX-042) – not checked here, as the tests have no Firefox.
"""

from __future__ import annotations

import io
from unittest import SkipTest

from PIL import Image

from rentalars.projects import service_cases
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


def difference(first: bytes, second: bytes) -> float:
    """The share of the pixels of two pictures of the same size that differ visibly."""
    one, other = (Image.open(io.BytesIO(picture)).convert("RGB") for picture in (first, second))
    if one.size != other.size:
        return 1.0
    changed = sum(
        1
        for a, b in zip(one.getdata(), other.getdata(), strict=True)
        if max(abs(x - y) for x, y in zip(a, b, strict=True)) > 40
    )
    return changed / (one.size[0] * one.size[1])


class UiInBrowserCase(BrowserTestCase):
    bypass_csp = True  # for axe-core

    def axe(self) -> None:
        """No finding of axe-core on the page as it is now (NFA-025)."""
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))


class GroupedTablesTests(UiInBrowserCase):
    """UIX-040."""

    def test_group_by_applies_at_once_and_passes_axe(self) -> None:
        self.open("/projects/")
        self.page.select_option("#group-projects", "status")
        self.page.wait_for_url("**/projects/?group=status")
        headings = self.page.locator("tr.table-group th")
        self.assertGreater(headings.count(), 1)
        self.assertRegex(headings.first.inner_text(), r"\d+ Eintr(ag|äge)$")
        self.axe()

    def test_on_a_phone_the_groups_are_headings_of_the_cards(self) -> None:
        service_cases.create_case(name="Beamer defekt")
        service_cases.create_case(name="Kabel fehlt", case_contact="Herr Meier")
        self.page.set_viewport_size({"width": 375, "height": 800})
        for path in (
            "/projects/?group=status",
            "/projects/service-cases/?group=status",
            "/administration/automations/",
        ):
            with self.subTest(page=path):
                self.open(path)
                self.page.wait_for_load_state("networkidle")
                width = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(width, 375)
                self.axe()

    def test_the_lists_brought_to_tables_pass_axe(self) -> None:
        """Every list that became a table of core.tables, grouped where it can be."""
        service_cases.create_case(name="Beamer defekt")
        for path in (
            "/projects/service-cases/?group=status",
            "/projects/open-items/",
            "/projects/templates/",
            "/shortages/?subrentals_group=supplier",
            "/material/inspections/",
            "/times/report/expenses/?since=2027-01-01&group=person",
            "/times/expenses/",
            "/notifications/?group=kind",
            "/administration/automations/",
            "/administration/roles/",
            "/administration/security-log/?group=event",
            "/administration/webhooks/",
            "/jobs/",
            "/times/approval/?sort=-hours",
            "/times/report/?entries_group=person",
            "/administration/scales/",
            "/administration/masterdata/masterdata/category/?group=is_active",
        ):
            with self.subTest(page=path):
                self.open(path)
                self.page.wait_for_load_state("networkidle")
                self.axe()

    def test_sorting_by_a_heading_keeps_the_groups(self) -> None:
        self.open("/projects/?group=status")
        self.page.locator("thead th a", has_text="Projekt").first.click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("group=status", self.page.url)
        self.assertIn("sort=", self.page.url)
        self.assertGreater(self.page.locator("tr.table-group").count(), 0)


class OnePickerSymbolTests(UiInBrowserCase):
    """UIX-042: only Rentalars' button, no second calendar symbol of the browser; typing still works."""

    #: A page and a field of each kind: date (filter of the change log), date and time (a new project), time
    #: (the own availability).
    FIELDS = (
        ("/administration/audit-log/", "#f-since", "date", "[data-filter-toggle]"),
        ("/projects/new/", "input[name=start]", "datetime-local", ""),
        ("/me/availability/", "input[name=start_time]", "time", "input[name=with_times]"),
    )

    def shot_of(self, selector: str) -> bytes:
        """A picture of the field alone, without Rentalars' button over it – once nothing moves any more."""
        self.page.evaluate(
            "(s) => { const f = document.querySelector(s); f.blur(); f.nextElementSibling.style.visibility = 'hidden'; }",
            selector,
        )
        shot = self.page.locator(selector).screenshot(animations="disabled")
        for _attempt in range(10):
            self.page.wait_for_timeout(100)
            again = self.page.locator(selector).screenshot(animations="disabled")
            if again == shot:
                return shot
            shot = again
        return shot

    def test_the_rules_of_0_8_1_are_in_the_styles(self) -> None:
        """The stronger rule (Chromium) and the cover (Firefox) of static/css/app.css, block UIX-042, are loaded."""
        self.open("/projects/new/")
        found = self.page.evaluate(
            """() => {
              const result = {important: false, cover: false};
              const walk = (rules, inSupports) => {
                for (const rule of rules) {
                  if (rule.cssRules && rule.conditionText !== undefined) {
                    walk(rule.cssRules, rule.conditionText.includes('-moz-appearance'));
                  } else if (rule.selectorText) {
                    if (rule.selectorText.includes('input.dt-input::-webkit-calendar-picker-indicator')
                        && rule.style.getPropertyValue('display') === 'none'
                        && rule.style.getPropertyPriority('display') === 'important') { result.important = true; }
                    if (inSupports && rule.selectorText.includes('.dt-wrap > .dt-btn')
                        && rule.style.getPropertyValue('background').includes('--field')) { result.cover = true; }
                  }
                }
              };
              for (const sheet of document.styleSheets) { walk(sheet.cssRules, false); }
              return result;
            }"""
        )
        self.assertEqual(found, {"important": True, "cover": True})

    def test_a_later_rule_cannot_bring_the_symbol_back(self) -> None:
        """A block of styles after Rentalars' own that shows the indicator again (as in the screenshot of point 3)."""
        selector = "input[name=start]"
        self.open("/projects/new/")
        self.page.wait_for_load_state("networkidle")
        hidden = self.shot_of(selector)
        self.page.add_style_tag(content=".dt-wrap input[type]::-webkit-calendar-picker-indicator { display: block; }")
        self.assertLess(difference(self.shot_of(selector), hidden), 0.002, "the browser's symbol came back")

    def test_the_browser_symbol_is_hidden_in_every_kind_of_field(self) -> None:
        for path, selector, kind, unfold in self.FIELDS:
            with self.subTest(field=kind):
                self.open(path)
                self.page.wait_for_load_state("networkidle")
                if unfold:  # the filters are folded; the times of a mark show with "with times"
                    self.page.locator(unfold).first.click()
                field = self.page.locator(selector)
                self.assertEqual(field.get_attribute("type"), kind)
                self.assertIn("dt-input", field.get_attribute("class") or "")
                # Exactly one button of Rentalars next to the field, with a name for screen readers.
                button = self.page.locator(f"{selector} + .dt-btn")
                self.assertEqual(button.count(), 1)
                self.assertTrue(button.get_attribute("aria-label"))
                hidden = self.shot_of(selector)
                # The same field with the browser's symbol: the picture must differ – the symbol is gone above.
                self.page.evaluate("(s) => document.querySelector(s).classList.remove('dt-input')", selector)
                shown = self.shot_of(selector)
                self.assertGreater(
                    difference(hidden, shown), 0.004, f"the browser's own symbol shows in a {kind} field"
                )
                self.page.evaluate("(s) => document.querySelector(s).classList.add('dt-input')", selector)
                self.assertLess(difference(self.shot_of(selector), hidden), 0.002)
                self.axe()

    def type_into(self, selector: str, orders: tuple[str, ...], until: str = "2027-03-15") -> None:
        """Type a date into a field: in the order of the browser's language (US or German).

        A space in ``orders`` moves on to the next part of the field (after the year, which takes six digits).
        """
        field = self.page.locator(selector)
        for keys in orders:
            field.evaluate("(f) => { f.value = ''; }")
            field.focus()
            for number, chunk in enumerate(keys.split(" ")):
                if number:
                    self.page.keyboard.press("ArrowRight")
                self.page.keyboard.type(chunk)
            if field.input_value().startswith(until):
                return

    def test_typing_into_the_fields_still_works(self) -> None:
        self.open("/administration/audit-log/")
        self.page.locator("[data-filter-toggle]").first.click()
        self.type_into("#f-since", ("03152027", "15032027"))
        self.assertEqual(self.page.locator("#f-since").input_value(), "2027-03-15")
        self.open("/projects/new/")
        field = self.page.locator("input[name=start]")
        self.type_into("input[name=start]", ("03102027 0830A", "10032027 0830"), until="2027-03-10T08:30")
        self.assertTrue(field.input_value().startswith("2027-03-10T08:30"), field.input_value())
        self.assertFalse(self.page.locator("dialog.dt-picker[open]").count())  # typing opens no picker
