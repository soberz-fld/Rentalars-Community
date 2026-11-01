# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: small things in the material management (tests/unit/test_093_material_small.py).

Only a browser shows that the table of the box "Ertrag" is folded and opens with a click after the box was loaded in
the background, that the master data of the audit mode stay compact on a phone (label and value side by side, no
sideways scrolling), and – with axe-core (RENTALARS_AXE, see tests/browser/test_accessibility_in_browser.py) – that
the pages meet WCAG 2.1 AA with the new parts.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest import SkipTest

from rentalars.masterdata.models import CategoryField, Supplier
from rentalars.material import audits
from rentalars.material.models import MaterialModel
from tests.browser import test_accessibility_in_browser as accessibility  # a module: its tests do not run here
from tests.browser.base import BrowserTestCase
from tests.helpers import category, make_item, make_model, make_product, make_stock


class SmallThingsCase(BrowserTestCase):
    """A cable 7427 with its length and an open to-do, a model of three items for the box "Ertrag"."""

    def setUp(self) -> None:
        super().setUp()
        length = CategoryField.objects.get(category=category("K"), label="Länge")
        model = make_model("XLR-Kabel 093", make_product("K-093"), category_code="K")
        model.set_field_value(length, "10")
        model.save()
        self.cable = make_item(
            model,
            7427,
            serial_numbers=["SN-7427"],
            purchase_date=datetime.date(2027, 2, 1),
            purchase_price=Decimal("12.50"),
            supplier=Supplier.objects.create(name="Musikhaus Muster 093"),
        )
        audits.add_todo(self.cable, "Label fehlt")
        self.stock = MaterialModel.objects.get(default_product=make_stock("S-093", 3, "Stagebox 093"))


class FoldedEarningsTests(SmallThingsCase):
    """MAT-058: the table item by item is closed; a click on its summary opens it."""

    def test_open_with_a_click(self) -> None:
        self.open(f"/material/models/{self.stock.pk}/")
        summary = self.page.locator(".revenue-items > summary")
        summary.wait_for()  # the box comes in the background (htmx)
        self.assertEqual(summary.inner_text(), "Ertrag je Exemplar (3 Exemplare)")
        table = self.page.locator(".revenue-items table")
        self.assertFalse(table.is_visible())
        self.assertTrue(self.page.locator("#model-revenue dl.facts").is_visible())  # the sums stay in sight
        summary.click()
        self.assertTrue(table.is_visible())
        self.assertEqual(table.locator("tbody tr").count(), 3)
        summary.press("Enter")  # and with the keyboard
        self.assertFalse(table.is_visible())


class CompactMasterDataTests(SmallThingsCase):
    """MAT-079: the master data of the audit mode – label and value side by side on a phone, no sideways scrolling."""

    viewport = {"width": 390, "height": 844}

    def test_on_a_phone(self) -> None:
        self.open("/material/audit/?id=7427")
        overview = self.page.locator(".audit-master dl")
        overview.wait_for()
        labels, values = overview.locator("dt"), overview.locator("dd")
        self.assertGreaterEqual(labels.count(), 10)
        for index in range(labels.count()):
            label, value = labels.nth(index).bounding_box(), values.nth(index).bounding_box()
            self.assertLess(abs(label["y"] - value["y"]), 2, labels.nth(index).inner_text())
            self.assertGreater(value["x"], label["x"])
        self.assertTrue(self.page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"))
        gap = overview.locator("dt", has_text="Hersteller").locator("xpath=following-sibling::dd[1]")
        self.assertEqual(gap.inner_text().strip().splitlines()[0].strip(), "–")


class SmallThingsAccessibilityTests(SmallThingsCase):
    """The pages with the new parts without a finding of axe-core (NFA-025)."""

    bypass_csp = True
    findings = accessibility.AccessibilityInBrowserTests.findings

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def test_pages(self) -> None:
        findings: list[str] = []
        for path in ("/products/", "/material/open-points/", "/material/audit/?id=7427"):
            findings += self.findings(path)
        findings += self.findings(f"/material/models/{self.stock.pk}/")
        self.page.locator(".revenue-items > summary").click()
        self.page.add_script_tag(path=str(self.axe))
        findings += self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => 'opened earnings: ' + v.id + ': ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            accessibility.WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))
