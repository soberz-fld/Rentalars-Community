# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the mass inspection – choosing in the list, the form, and both pages checked with axe-core (MAT-082).

The page tests (tests/unit/test_094_inspections.py) send the forms as a browser without scripts would; only a browser
shows that the bar appears with the first tick, that the electrical columns appear for an electrical type alone and
that one tick in the heading ticks the visual inspection of all items.
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.material.models import Inspection, InspectionType, ProtectionClass
from tests.browser import test_accessibility_in_browser as accessibility  # a module: its tests do not run here
from tests.browser.base import BrowserTestCase
from tests.helpers import make_item, make_model
from tests.unit.test_093_dguv import length_field


class BatchInspectionInBrowserTests(BrowserTestCase):
    """Two extension leads (9442, 9443): an electrical and a visual inspection for both."""

    bypass_csp = True
    findings = accessibility.AccessibilityInBrowserTests.findings

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        super().setUpClass()

    def setUp(self) -> None:
        super().setUp()
        length_field()
        model = make_model("Verlängerung 094", category_code="K")
        model.set_category_specific_value("10")
        model.protection_class = ProtectionClass.I
        model.save()
        self.electric = InspectionType.objects.create(name="E-Check 094", interval_months=12, is_electrical=True)
        self.electric.material_models.add(model)
        self.visual = InspectionType.objects.create(name="Sichtkontrolle 094", interval_months=6)
        self.visual.material_models.add(model)
        self.first = make_item(model, 9442)
        self.second = make_item(model, 9443)

    def axe_findings(self, what: str) -> list[str]:
        if self.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.add_script_tag(path=str(self.axe))
        result = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            accessibility.WCAG_AA,
        )
        return [f"{what}: {finding}" for finding in result]

    def test_choose_in_the_list_and_record(self) -> None:
        self.open(f"/material/inspections/?type={self.electric.pk}")
        self.page.wait_for_load_state("networkidle")
        bar = self.page.locator("#bulk-form")
        self.assertFalse(bar.is_visible())
        self.page.locator("input[name=items][form=bulk-form]").first.check()
        bar.wait_for()
        self.assertEqual(self.page.locator("[data-chosen-count=items]").inner_text(), "1")
        self.page.locator("thead input[data-check-all=items]").check()
        self.assertEqual(self.page.locator("[data-chosen-count=items]").inner_text(), "2")
        findings = self.axe_findings("list")
        bar.get_by_role("button", name="Gewählte Exemplare prüfen").click()
        self.page.wait_for_url("**/material/inspections/batch/")
        # The type of the filter is chosen, day and inspector are filled in, the electrical part shows.
        self.assertEqual(self.page.locator("#id_inspection_type").input_value(), str(self.electric.pk))
        self.assertEqual(self.page.locator("#id_date").input_value(), "2027-03-01")
        self.assertNotEqual(self.page.locator("#id_inspector").input_value(), "")
        self.assertTrue(self.page.locator("#id_test_device").is_visible())
        self.assertTrue(self.page.locator("input[name=visual]").first.is_visible())
        findings += self.axe_findings("batch page")
        self.page.select_option("#id_inspection_type", str(self.visual.pk))
        self.page.locator("#id_test_device").wait_for(state="hidden")
        self.assertFalse(self.page.locator("input[name=visual]").first.is_visible())
        self.page.select_option("#id_inspection_type", str(self.electric.pk))
        self.page.locator("#id_test_device").wait_for()
        self.assertEqual(findings, [], "\n".join(findings))
        # One tick in the heading ticks the visual inspection of all items; the values come from the table.
        self.page.locator("thead input[data-check-all=visual]").check()
        self.assertEqual(self.page.locator("input[name=visual]:checked").count(), 2)
        self.page.fill("#id_test_device", "Benning ST 760")
        for item in (self.first, self.second):
            self.page.fill(f"#id_i{item.pk}-pe_resistance_ohm", "0,12")
            self.page.fill(f"#id_i{item.pk}-insulation_resistance_mohm", "250")
            self.page.select_option(f"#id_i{item.pk}-function_test_passed", "yes")
        self.page.get_by_role("button", name="Prüfungen erfassen").click()
        self.page.wait_for_url("**/material/inspections/**")
        done = list(Inspection.objects.order_by("item_id"))
        self.assertEqual([(i.result, i.test_device) for i in done], [("passed", "Benning ST 760")] * 2)
