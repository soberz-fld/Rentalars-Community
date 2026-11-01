# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: "neuer Händler" opens the supplier's master data in a dialog over the form for new items
(MAT-060), the tax rate of a gross purchase price shows only for "brutto" (MAT-059), and the field "Exemplar-ID"
opens an item (MAT-063).

The page tests (tests/unit/test_091_items.py) read the HTML; only a browser runs the script that opens the dialog
and puts the new supplier into the field the dialog came from.
"""

from __future__ import annotations

from decimal import Decimal

from rentalars.masterdata.models import Supplier
from rentalars.material.models import MaterialItem
from tests.browser.base import BrowserTestCase
from tests.helpers import make_item, make_model


class ItemsInBrowserTests(BrowserTestCase):
    """The parts of the wishes around items that need the page script (MAT-059, MAT-060, MAT-063)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Funkstrecke 091", category_code="T")
        self.item = make_item(self.model, 7427)

    def choose_new_supplier(self, typed: str) -> None:
        """Type a name nobody has into "Gekauft bei" and choose "neuer Händler"."""
        field = self.page.locator("#id_supplier_name")
        field.click()
        field.press_sequentially(typed, delay=20)
        self.page.locator('[role=option]:has-text("neuer Händler")').click()

    def test_a_new_supplier_with_its_master_data(self) -> None:
        self.open(f"/material/models/{self.model.pk}/items/new/")
        self.page.fill("#id_invoice_number", "RE-091")
        self.choose_new_supplier("Neuhaus")
        dialog = self.page.locator("#dialog[open]")
        dialog.wait_for()
        self.assertEqual(dialog.locator("h2").inner_text(), "Neuer Händler")
        self.assertEqual(dialog.locator("#supplier_name").input_value(), "Neuhaus")
        self.assertEqual(self.page.evaluate("() => document.activeElement.id"), "supplier_name")
        # Escape: no supplier, the typed name stays in the field.
        self.page.keyboard.press("Escape")
        dialog.wait_for(state="detached")
        self.assertEqual(self.page.locator("#id_supplier_name").input_value(), "Neuhaus")
        self.assertFalse(Supplier.objects.filter(name__startswith="Neuhaus").exists())

        self.choose_new_supplier(" Licht")
        dialog.wait_for()
        dialog.locator("#supplier_city").fill("Stuttgart")
        dialog.locator("#supplier_email").fill("info@neuhaus.example")
        dialog.locator("button[type=submit]").click()
        dialog.wait_for(state="detached")
        supplier = Supplier.objects.get(name="Neuhaus Licht")
        self.assertEqual(supplier.city, "Stuttgart")
        # The supplier is in the field; what was typed before stays.
        self.assertEqual(self.page.locator("#id_supplier_name").input_value(), "Neuhaus Licht")
        self.assertEqual(self.page.locator("#id_invoice_number").input_value(), "RE-091")
        self.assertEqual(self.page.evaluate("() => document.activeElement.id"), "id_supplier_name")
        self.page.locator("form.form button[type=submit]").click()
        self.page.wait_for_url(f"**/material/models/{self.model.pk}/")
        created = MaterialItem.objects.filter(material_model=self.model).order_by("-pk").first()
        self.assertEqual((created.supplier, created.invoice_number), (supplier, "RE-091"))
        self.assertEqual(Supplier.objects.filter(name__istartswith="Neuhaus").count(), 1)

    def test_the_tax_rate_shows_for_gross_prices(self) -> None:
        self.open(f"/material/models/{self.model.pk}/items/new/")
        rate = self.page.locator("#id_price_tax_rate")
        self.assertFalse(rate.is_visible())
        self.page.select_option("#id_prices", "gross")
        self.assertTrue(rate.is_visible())
        self.page.fill("#id_purchase_price", "119,00")
        self.page.locator("form.form button[type=submit]").click()
        self.page.wait_for_url(f"**/material/models/{self.model.pk}/")
        created = MaterialItem.objects.filter(material_model=self.model).order_by("-pk").first()
        self.assertEqual(created.purchase_price, Decimal("100.00"))

    def test_the_id_field_opens_the_item(self) -> None:
        self.open("/material/")
        field = self.page.get_by_label("ID eines Exemplars")
        field.fill("#7427")
        field.press("Enter")
        self.page.wait_for_url(f"**/material/items/{self.item.pk}/")
        self.open("/products/")
        field = self.page.get_by_label("ID eines Exemplars")
        field.fill("99999")
        field.press("Enter")
        self.page.wait_for_url("**/material/?q=99999")
        self.assertIn("Es gibt kein Exemplar mit der ID 99999.", self.page.inner_text(".messages"))
