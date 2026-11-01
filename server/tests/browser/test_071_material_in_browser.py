# SPDX-License-Identifier: GPL-3.0-or-later
"""The material wishes in the browser: a serial number field per new item (MAT-050), manufacturer and
product typed with suggestions (MAT-048), the product form with the kind first (PRD-046), an existing model
assigned from the product's page (PRD-046), a product made from a model (MAT-051) – and axe-core on these pages."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.masterdata.models import Category, Manufacturer
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.products.models import Product
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class MaterialInBrowserTests(BrowserTestCase):
    """MAT-048, MAT-050, MAT-051, PRD-046 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def axe_findings(self) -> list[str]:
        """What axe-core finds on the page."""
        self.page.wait_for_load_state("networkidle")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def serial_inputs(self) -> list[str]:
        return self.page.locator(".serial-fields input").evaluate_all("inputs => inputs.map(input => input.value)")

    def test_a_serial_number_field_per_item(self) -> None:
        """MAT-050: as many fields as items; Enter goes on to the next; pasted lines fill the following ones."""
        model = MaterialModel.objects.get(name="Robe Pointe")
        self.open(f"/material/models/{model.pk}/items/new/")
        self.assertFalse(self.page.locator("textarea[name=serial_numbers]").is_visible())
        self.assertEqual(self.page.locator(".serial-fields legend").inner_text(), "Seriennummern")
        self.assertEqual(self.serial_inputs(), [""])
        self.assertEqual(self.page.locator(".serial-fields label").first.inner_text(), "Exemplar 1")
        self.page.fill("input[name=count]", "3")
        self.assertEqual(self.serial_inputs(), ["", "", ""])
        first = self.page.locator(".serial-fields input").first
        first.fill("RP-1")
        first.press("Enter")  # a scanner ends every code with Enter: on to the next field, no sending
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "id_serial_numbers_2")
        self.page.keyboard.type("RP-2")
        self.assertEqual(self.page.locator("textarea[name=serial_numbers]").input_value(), "RP-1\nRP-2")
        # Fewer items: the last field goes, and its value is not sent.
        self.page.locator(".serial-fields input").nth(2).fill("RP-3")
        self.page.fill("input[name=count]", "2")
        self.assertEqual(self.serial_inputs(), ["RP-1", "RP-2"])
        self.assertEqual(self.page.locator("textarea[name=serial_numbers]").input_value(), "RP-1\nRP-2")
        # Three lines pasted into the second field fill it and the following ones – one more item.
        self.page.locator(".serial-fields input").nth(1).focus()
        self.page.evaluate(
            "() => { const data = new DataTransfer(); data.setData('text', 'RP-2\\nRP-3\\nRP-4\\n');"
            " document.activeElement.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true,"
            " cancelable: true})); }"
        )
        self.assertEqual(self.page.locator("input[name=count]").input_value(), "4")
        self.assertEqual(self.serial_inputs(), ["RP-1", "RP-2", "RP-3", "RP-4"])
        self.assertEqual(self.axe_findings(), [])
        before = MaterialItem.objects.filter(material_model=model).count()
        self.page.locator("form.form button[type=submit]").click()
        self.page.wait_for_url(f"**/material/models/{model.pk}/")
        serials = list(
            MaterialItem.objects.filter(material_model=model)
            .order_by("-inventory_number")
            .values_list("serial_number", flat=True)[:4]
        )
        self.assertEqual(sorted(serials), ["RP-1", "RP-2", "RP-3", "RP-4"])
        self.assertEqual(MaterialItem.objects.filter(material_model=model).count(), before + 4)

    def test_manufacturer_and_product_typed_with_suggestions(self) -> None:
        """MAT-048: a known manufacturer is suggested, a new one is offered as new; the product is chosen by typing."""
        self.open("/material/models/new/")
        self.page.fill("input[name=name]", "Cordial CPM 15 FM")
        self.page.select_option("select[name=category]", label="Kabel")
        manufacturer = self.page.locator("input[name=manufacturer_name]")
        manufacturer.press_sequentially("Cord", delay=20)
        options = self.page.locator(".typeahead:has(input[name=manufacturer_name]) [role=option]")
        options.first.wait_for()
        self.assertEqual(options.first.inner_text().split("\n")[0], "Cordial")
        manufacturer.fill("")
        manufacturer.press_sequentially("Kabelwerk Nord", delay=10)
        new = self.page.locator(".typeahead:has(input[name=manufacturer_name]) [role=option].create")
        new.filter(has_text="Kabelwerk Nord").wait_for()
        self.assertEqual(options.count(), 1)
        self.assertIn("neuer Hersteller", options.first.inner_text())
        manufacturer.press("Enter")
        self.assertEqual(manufacturer.input_value(), "Kabelwerk Nord")
        product = self.page.locator("#id_default_product_text")
        product.press_sequentially("K-010", delay=20)
        self.page.locator(".typeahead:has(#id_default_product_text) [role=option]").first.wait_for()
        product.press("Enter")
        self.assertEqual(
            self.page.locator("input[name=default_product]").input_value(),
            str(Product.objects.get(article_number="K-010").pk),
        )
        self.page.fill("input[name=power_w]", "0")
        self.page.fill("input[name=weight_kg]", "1,2")
        self.assertEqual(self.axe_findings(), [])
        self.page.locator("form.form button[type=submit]").click()
        self.page.wait_for_url("**/material/models/*/")
        model = MaterialModel.objects.get(name="Cordial CPM 15 FM")
        self.assertEqual(model.manufacturer, Manufacturer.objects.get(name="Kabelwerk Nord"))
        self.assertEqual(model.default_product.article_number, "K-010")

    def test_the_product_form_asks_the_kind_first(self) -> None:
        """PRD-046: choosing the kind reloads the form; the categories of that kind come first; the kind stays."""
        self.open("/products/new/")
        self.page.select_option("select[name=kind]", "sale")
        self.page.wait_for_url("**/products/new/?kind=sale")
        first_group = self.page.locator("select[name=category] optgroup").first
        self.assertEqual(first_group.get_attribute("label"), "Kategorien für „Verkaufs- oder Verbrauchsprodukt“")
        self.assertIn("Verkauf", first_group.inner_text())
        self.page.select_option("select[name=category]", label="Kabel")
        self.page.wait_for_url("**/products/new/?kind=sale&category=*")
        self.assertEqual(self.page.locator("select[name=kind]").input_value(), "sale")
        self.assertTrue(self.page.locator("input[name=article_number]").input_value().startswith("K-"))
        self.assertEqual(self.axe_findings(), [])

    def test_an_existing_model_is_assigned_and_a_model_becomes_a_product(self) -> None:
        """PRD-046 on the product's page; MAT-051 on the model's page."""
        product = Product.objects.get(article_number="K-020")
        ladder = MaterialModel.objects.get(name="Leiter 3-teilig")
        self.open(f"/products/{product.article_number}/")
        field = self.page.locator("input[placeholder='Modell ohne Produkt suchen']")
        field.press_sequentially("Leiter", delay=20)
        self.page.locator(".typeahead:has(input[name=material_model]) [role=option]").first.wait_for()
        field.press("Enter")
        self.assertEqual(self.axe_findings(), [])
        self.page.locator("button", has_text="Vorhandenes Modell zuordnen").click()
        self.page.wait_for_load_state("networkidle")
        ladder.refresh_from_db()
        self.assertEqual(ladder.default_product, product)
        self.assertIn("Leiter 3-teilig gehört jetzt zu K-020.", self.page.inner_text("body"))

        free = MaterialModel.objects.create(name="Nebelmaschine Look Unique", category=Category.objects.get(code="L"))
        self.open(f"/material/models/{free.pk}/")
        self.assertEqual(self.axe_findings(), [])
        self.page.locator("button", has_text="Als Produkt anlegen").click()
        self.page.wait_for_url("**/products/*/edit/")
        free.refresh_from_db()
        self.assertEqual(free.default_product.name, "Nebelmaschine Look Unique")
        self.assertIn("Trag jetzt seinen Preis ein.", self.page.inner_text("body"))
