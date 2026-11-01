# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the live check of an electrical inspection, and its pages checked with axe-core (MAT-078).

The page tests (tests/unit/test_093_dguv.py) send the form as a browser without scripts would; only a browser shows
that the fields appear for an electrical inspection type alone and that the limits, the marks and the suggested result
follow what is typed (htmx, ``material:inspection_check``). axe-core judges the pages against WCAG 2.1 AA (NFA-025; it
runs with RENTALARS_AXE, see tests/browser/test_accessibility_in_browser.py).
"""

from __future__ import annotations

import datetime
from unittest import SkipTest

from rentalars.material import services
from rentalars.material.models import InspectionType, ProtectionClass
from tests.browser import test_accessibility_in_browser as accessibility  # a module: its tests do not run here
from tests.browser.base import BrowserTestCase
from tests.helpers import make_item, make_model
from tests.unit.test_093_dguv import good_values, length_field


class DguvCase(BrowserTestCase):
    """A 10 m extension lead of protection class I (9342) with an electrical inspection and a visual one."""

    def setUp(self) -> None:
        super().setUp()
        length_field()
        model = make_model("Verlängerung 093", category_code="K")
        model.set_category_specific_value("10")
        model.protection_class = ProtectionClass.I
        model.save()
        self.model = model
        self.electric = InspectionType.objects.create(name="E-Check 093", interval_months=12, is_electrical=True)
        self.electric.material_models.add(model)
        self.cable = make_item(model, 9342, serial_number="SN-093")


class LiveCheckInBrowserTests(DguvCase):
    """MAT-078: the fields show for the electrical type only; limits, marks and the suggestion follow the values."""

    def test_typing_judges_the_values(self) -> None:
        visual = InspectionType.objects.create(name="Sichtkontrolle 093", interval_months=6)
        visual.material_models.add(self.model)
        self.open(f"/material/items/{self.cable.pk}/inspections/")
        fieldset = self.page.locator("fieldset[data-show-if]")
        self.assertFalse(fieldset.is_visible())  # no type chosen yet
        self.page.select_option("#id_inspection_type", str(self.electric.pk))
        fieldset.wait_for()
        suggestion = self.page.locator("#dguv-suggestion")
        self.page.check("#id_visual_check_passed")
        self.page.fill("#id_pe_resistance_ohm", "0,45")
        suggestion.locator(".badge.red", has_text="fehlgeschlagen").wait_for()
        self.page.locator("#dguv-pe_resistance_ohm .badge.red", has_text="außerhalb des Grenzwerts").wait_for()
        self.assertIn("RPE 0,45 Ω liegt außerhalb des Grenzwerts ≤ 0,4 Ω.", suggestion.inner_text())
        # A longer cord allows more: the limit and the suggestion change with it. ("bestanden" needs
        # the insulation check as well, dguv.REQUIRED – so R_ISO is typed, too, and its answer awaited.)
        self.assertIn("Isolationsprüfung fehlt", suggestion.inner_text())
        self.page.fill("#id_insulation_resistance_mohm", "250")
        suggestion.locator("li", has_text="Isolationsprüfung fehlt").wait_for(state="detached")
        self.page.fill("#id_cord_length_m", "15")
        self.page.locator("#dguv-pe_resistance_ohm", has_text="≤ 0,5 Ω").wait_for()
        suggestion.locator(".badge.green", has_text="bestanden").wait_for()
        self.page.select_option("#id_inspection_type", str(visual.pk))
        fieldset.wait_for(state="hidden")


class DguvPagesAccessibilityTests(DguvCase):
    """MAT-077, MAT-078: the form with its fields, the measured values in the list, the protection class – without a finding of axe-core."""

    bypass_csp = True
    findings = accessibility.AccessibilityInBrowserTests.findings

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def opened_findings(self, path: str) -> list[str]:
        """The findings with every ``<details>`` of the page open – the measured values in the list of inspections."""
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        self.page.evaluate("() => document.querySelectorAll('details').forEach(d => { d.open = true; })")
        self.page.add_script_tag(path=str(self.axe))
        result = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            accessibility.WCAG_AA,
        )
        return [f"{path} (details open): {finding}" for finding in result]

    def test_pages(self) -> None:
        services.record_inspection(
            self.cable,
            self.electric,
            date=datetime.date(2027, 2, 26),
            inspector="E. Fachkraft",
            result="failed",
            electrical=good_values(pe_resistance_ohm="0.52"),
        )
        findings: list[str] = []
        inspections = f"/material/items/{self.cable.pk}/inspections/"
        for path in [
            inspections,  # one type only: the fields of the electrical inspection are shown at once
            f"/material/items/{self.cable.pk}/",
            f"/material/items/{self.cable.pk}/edit/",
            f"/material/models/{self.model.pk}/",
            f"/material/models/{self.model.pk}/edit/",
        ]:
            findings += self.findings(path)
        findings += self.opened_findings(inspections)
        self.assertEqual(findings, [], "\n".join(findings))
