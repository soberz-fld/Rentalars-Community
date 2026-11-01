# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: book value and the used sale from stock ("Mit Restbuchwert"; MAT-086).

The card "Anlagevermögen" of an item, the preview and the sale ("Gebrauchtverkauf aus Bestand"), the page of the sale with
its reversal, the Anlagenspiegel and the list of sales. All pages are checked with axe-core (NFA-025); without axe the
checks are skipped. Page, service and API tests are in ``tests/unit/test_100_depreciation.py``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from rentalars.material.models import AssetKind, ItemStatus, MaterialItem
from rentalars.material.sale_models import SaleFromStock
from tests.browser.base import BrowserTestCase
from tests.browser.test_100_products_planning_in_browser import AxeMixin
from tests.helpers import make_item, make_model, make_product


class DepreciationInBrowserTests(AxeMixin, BrowserTestCase):
    """The way from the card of an item to the sale and back."""

    bypass_csp = True  # axe-core is put into the page

    def setUp(self) -> None:
        super().setUp()
        model = make_model("Mischpult Midas M32", make_product("T-9100", "Mischpult"), category_code="T")
        self.mixer = make_item(
            model,
            9100,
            purchase_date=datetime.date(2026, 3, 17),
            purchase_price=Decimal("1000.00"),
            asset_kind=AssetKind.FIXED_ASSET,
            useful_life_months=36,
            ancillary_cost_net=Decimal("50.00"),
            acquisition_cost_net=Decimal("1050.00"),
        )

    def fill_day(self, value: datetime.date) -> None:
        """Type the day into the field of the form – the way its type wants it."""
        field = self.page.locator("#id_sold_on")
        field.fill(value.isoformat() if field.get_attribute("type") == "date" else value.strftime("%d.%m.%Y"))

    def test_from_the_card_to_the_sale_and_back(self) -> None:
        self.open(f"/material/items/{self.mixer.pk}/")
        card = self.page.locator("#asset")
        card.wait_for()
        self.assertIn("670,83", card.inner_text())  # the book value of 1 March 2027
        self.assertEqual(self.axe_findings("main"), [])

        # The preview shows the book value and the gain, and changes nothing.
        self.page.get_by_role("link", name="Gebrauchtverkauf aus Bestand").first.click()
        self.page.wait_for_url(f"**/material/items/{self.mixer.pk}/sell/")
        self.fill_day(datetime.date(2027, 3, 1))
        self.page.fill("#id_buyer_name", "Hans Meier")
        self.page.fill("#id_net_price", "700,00")
        self.page.get_by_role("button", name="Vorschau zeigen").click()
        preview = self.page.locator("#preview")
        preview.wait_for()
        text = preview.inner_text()
        self.assertIn("670,83", text)
        self.assertIn("29,17", text)
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.AVAILABLE)
        self.assertEqual(self.axe_findings("main"), [])

        # The sale asks first, then does it.
        self.page.get_by_role("button", name="Verkaufen", exact=True).click()
        self.confirm()
        self.page.wait_for_url("**/accounting/assets/sales/*/")
        sale = SaleFromStock.objects.get()
        self.assertEqual(sale.gain_loss, Decimal("29.17"))
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.SOLD)
        self.assertIn("Hans Meier", self.page.locator("main").inner_text())
        self.assertEqual(self.axe_findings("main"), [])

        # The reversal needs a reason and puts the item back.
        self.page.fill("#cancel-reason", "Käufer ist abgesprungen")
        self.page.get_by_role("button", name="Verkauf stornieren").click()
        self.confirm()
        self.page.get_by_text("Käufer ist abgesprungen").first.wait_for()
        self.assertTrue(SaleFromStock.objects.get().is_cancelled)
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.AVAILABLE)
        self.assertEqual(self.axe_findings("main"), [])

    def test_the_register_and_the_sales_list(self) -> None:
        self.open("/accounting/assets/")
        self.page.get_by_text("9100").first.wait_for()
        self.assertIn("670,83", self.page.locator("main").inner_text())
        self.assertEqual(self.axe_findings("main"), [])
        self.open("/accounting/assets/?year=2026")
        self.assertIn("758,33", self.page.locator("main").inner_text())
        self.open("/accounting/assets/sales/")
        self.page.locator("main").wait_for()
        self.assertEqual(self.axe_findings("main"), [])
