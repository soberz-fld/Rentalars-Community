# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the material wishes: the model form with typed manufacturer and product, weight, dimensions
and power (MAT-048, MAT-049), "Neue Exemplare" (MAT-050), "Als Produkt anlegen" (MAT-051), the default storage
location (MAT-052), and the product form with the kind first and existing models to assign (PRD-046)."""

from __future__ import annotations

import json
import re
from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.masterdata.models import CategoryField, FieldType, Manufacturer, StorageLocation, Supplier
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.products.models import Product, ProductKind
from tests.helpers import category, make_customer, make_item, make_items, make_model, make_product
from tests.ui.base import UiTestCase, form_data

D = Decimal


class ModelFormTests(UiTestCase):
    """MAT-048, MAT-049."""

    def test_the_form_offers_typed_fields_weight_dimensions_and_power(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:model_create")))
        self.assertIn(f'data-url="{reverse("material:manufacturer_suggest")}"', page)
        self.assertIn(f'data-url="{reverse("material:product_suggest")}"', page)
        self.assertNotIn("Oder ein neuer Hersteller", page)
        for label in ("Gewicht (kg)", "Länge (cm)", "Breite (cm)", "Höhe (cm)", "Leistung (W)", "Beschreibung"):
            self.assertIn(label, page)
        self.assertNotIn("Spezifikation", page)

    def test_a_new_manufacturer_and_a_product_are_saved_with_the_model(self) -> None:
        product = make_product("L-020", "Moving Head Spot")
        page = self.client.get(reverse("material:model_create"))
        data = form_data(
            page,
            name="Robe Pointe",
            category=category("L").pk,
            manufacturer_name="Robe",
            default_product=product.pk,
            weight_kg="15,5",
            power_w="470",
            length_cm="40",
            width_cm="30",
            height_cm="60",
        )
        response = self.client.post(reverse("material:model_create"), data)
        model = MaterialModel.objects.get(name="Robe Pointe")
        self.assertRedirects(response, reverse("material:model_detail", args=[model.pk]))
        self.assertEqual((model.manufacturer.name, model.default_product), ("Robe", product))
        self.assertEqual((model.weight_kg, model.power_w, model.volume_litres), (D("15.50"), D("470.00"), D("72.0")))
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk])))
        self.assertIn("470 W", detail)
        self.assertIn("Leistung", detail)

    def test_saving_the_edit_page_keeps_every_value(self) -> None:
        """Emptied weight, dimensions and further category fields: the page did not show them."""
        cable = category("K")
        colour = CategoryField.objects.create(category=cable, label="Farbe", field_type=FieldType.TEXT, position=2)
        model = make_model("Cordial CPM 5 FM", make_product("K-005"), category_code="K", manufacturer="Cordial")
        model.weight_kg, model.length_cm, model.power_w = D("0.40"), D("20.0"), D("0")
        model.field_values = {str(colour.pk): "schwarz"}
        model.save()
        edit = reverse("material:model_edit", args=[model.pk])
        page = self.client.get(edit)
        self.assertIn('value="Cordial"', self.assert_ok(page))
        self.assertIn("K-005 Produkt K-005", page.content.decode())
        self.client.post(edit, form_data(page, short_name="CPM5"))
        model.refresh_from_db()
        self.assertEqual(model.short_name, "CPM5")
        self.assertEqual((model.weight_kg, model.length_cm, model.power_w), (D("0.40"), D("20.0"), D("0.00")))
        self.assertEqual(model.field_values, {str(colour.pk): "schwarz"})
        self.assertEqual(model.manufacturer.name, "Cordial")
        self.assertEqual(Manufacturer.objects.count(), 1)


class SuggestionTests(UiTestCase):
    """MAT-048, MAT-050, PRD-046: the suggestions of the typed fields."""

    def suggest(self, name: str, text: str, client=None) -> list[dict]:
        response = (client or self.client).get(reverse(f"material:{name}"), {"q": text})
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def test_manufacturers_by_name_and_a_new_one_last(self) -> None:
        Manufacturer.objects.create(name="Cordial")
        Manufacturer.objects.create(name="Cameo")
        Manufacturer.objects.create(name="Corda", is_active=False)
        self.assertEqual([row["label"] for row in self.suggest("manufacturer_suggest", "co")][:1], ["Cordial"])
        new = self.suggest("manufacturer_suggest", "Cordal")
        self.assertEqual(new, [{"id": "Cordal", "label": "Cordal", "hint": "neuer Hersteller", "create": True}])
        self.assertEqual(self.suggest("manufacturer_suggest", "cordial"), [{"id": "Cordial", "label": "Cordial"}])

    def test_suppliers_and_who_may_create_them(self) -> None:
        Supplier.objects.create(name="Musikhaus Nord")
        self.assertEqual(self.suggest("supplier_suggest", "nord")[0]["label"], "Musikhaus Nord")
        Role.objects.create(name="Lesen", module_levels={"material": 1})
        reader = self.browser_for("rita", "Lesen")
        self.assertEqual(self.suggest("supplier_suggest", "Thomann", reader), [])
        Role.objects.create(name="Keine", module_levels={"projects": 1})
        self.assertEqual(self.browser_for("kai", "Keine").get(reverse("material:supplier_suggest")).status_code, 403)

    def test_products_with_stock_only(self) -> None:
        make_product("K-005", "XLR-Kabel 5 m")
        make_product("A-001", "Expresszuschlag", kind=ProductKind.SURCHARGE)
        make_product("C-001", "Pult der Band", price=None, owner=make_customer("Die Band"))
        labels = {row["label"]: row["hint"] for row in self.suggest("product_suggest", "-00")}
        self.assertIn("K-005 XLR-Kabel 5 m", labels)
        self.assertNotIn("A-001 Expresszuschlag", labels)
        self.assertEqual(labels["C-001 Pult der Band"], "Fremdmaterial von Die Band")

    def test_models_without_product_only(self) -> None:
        free = make_model("Leiter 3-teilig", category_code="R")
        make_model("Leiter mit Produkt", make_product("R-010"))
        # Model search: a model that belongs to a product is named, too, as a row that cannot be chosen.
        rows = self.suggest("model_suggest", "leiter")
        self.assertEqual([row["id"] for row in rows if not row.get("disabled")], [free.pk])


class NewItemsTests(UiTestCase):
    """MAT-050, MAT-052: "Neue Exemplare"."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Shure SM58", make_product("T-010"), category_code="T")
        self.url = reverse("material:item_create", args=[self.model.pk])

    def test_the_form_asks_for_start_id_serial_numbers_and_the_invoice(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        for text in ("Start-ID", "Seriennummern", "Rechnungsnummer", "Rechnungsdatum", "Gekauft bei"):
            self.assertIn(text, page)
        self.assertNotIn("Tag des Kaufs", page)
        self.assertNotIn("Eine bestimmte ID geht nur bei einem einzelnen Exemplar", page)
        self.assertIn("data-serial-numbers", page)
        self.assertIn(f'data-url="{reverse("material:supplier_suggest")}"', page)
        main_store = StorageLocation.get_default()
        self.assertIn(f'<option value="{main_store.pk}" selected>Hauptlager</option>', page)

    def test_creating_items_with_serial_numbers_from_a_start_id(self) -> None:
        make_item(self.model, 43)
        data = form_data(
            self.client.get(self.url),
            count="3",
            inventory_number="0042",
            serial_numbers="SN-1\r\n\r\nSN-3",
            supplier_name="Thomann",
            invoice_number="RE-2026-118",
            purchase_date="2026-10-01",
        )
        response = self.client.post(self.url, data, follow=True)
        self.assertRedirects(response, reverse("material:model_detail", args=[self.model.pk]))
        created = list(MaterialItem.objects.filter(supplier__name="Thomann").order_by("inventory_number"))
        self.assertEqual([item.inventory_number for item in created], [42, 44, 45])
        self.assertEqual([item.serial_number for item in created], ["SN-1", "", "SN-3"])
        self.assertEqual({item.invoice_number for item in created}, {"RE-2026-118"})
        self.assertEqual({item.storage_location.name for item in created}, {"Hauptlager"})
        detail = self.assert_ok(self.client.get(reverse("material:item_detail", args=[created[0].pk])))
        self.assertIn("RE-2026-118", detail)
        self.assertIn("Rechnungsdatum", detail)

    def test_too_many_serial_numbers_are_explained(self) -> None:
        data = form_data(self.client.get(self.url), count="1", serial_numbers="A\nB")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("2 Seriennummern für 1 Exemplare", response.content.decode())
        self.assertFalse(MaterialItem.objects.filter(material_model=self.model).exists())

    def test_a_known_serial_number_is_a_warning(self) -> None:
        # Duplicate serial numbers: the warning comes before saving, with the choice "Trotzdem anlegen"
        # (it was a message after saving); more cases in tests/unit/test_095_small_things.py.
        make_items(self.model, 1, serial_numbers=["X-9"])
        data = form_data(self.client.get(self.url), count="1", serial_numbers="x-9")
        response = self.client.post(self.url, data)
        page = response.content.decode()
        self.assertIn("gibt es schon beim selben Modell", page)
        self.assertIn("Trotzdem anlegen", page)
        self.assertEqual(MaterialItem.objects.filter(material_model=self.model).count(), 1)
        token = re.search(r'name="confirm_serials" id="id_confirm_serials" value="([0-9a-f]+)"', page).group(1)
        self.client.post(self.url, {**data, "confirm_serials": token})
        self.assertEqual(MaterialItem.objects.filter(material_model=self.model).count(), 2)


class ItemEditTests(UiTestCase):
    """MAT-050 on the item's own form; and the own values of MAT-013 survive saving."""

    def test_supplier_typed_and_own_values_kept(self) -> None:
        cable = category("K")
        colour = CategoryField.objects.create(category=cable, label="Farbe", field_type=FieldType.TEXT, position=2)
        item = make_items(make_model("Cordial CPM 5 FM", make_product("K-005"), category_code="K"))[0]
        item.specification_override = "Stecker getauscht"
        item.field_value_overrides = {str(colour.pk): "rot"}
        item.save()
        edit = reverse("material:item_edit", args=[item.pk])
        page = self.client.get(edit)
        self.assertIn("Abweichend vom Modell", self.assert_ok(page))
        self.client.post(edit, form_data(page, supplier_name="Musikhaus Nord", invoice_number="4711"))
        item.refresh_from_db()
        self.assertEqual((item.supplier.name, item.invoice_number), ("Musikhaus Nord", "4711"))
        self.assertEqual(item.specification_override, "Stecker getauscht")
        self.assertEqual(item.field_value_overrides, {str(colour.pk): "rot"})


class ProductFromModelPageTests(UiTestCase):
    """MAT-051."""

    def test_the_button_creates_the_product_and_opens_its_form(self) -> None:
        model = make_model("Robe Pointe", category_code="L")
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk])))
        self.assertIn("Als Produkt anlegen", detail)
        response = self.client.post(reverse("material:model_create_product", args=[model.pk]))
        product = Product.objects.get(name="Robe Pointe")
        self.assertRedirects(response, reverse("products:edit", args=[product.pk]))
        model.refresh_from_db()
        self.assertEqual(model.default_product, product)
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk])))
        self.assertNotIn("Als Produkt anlegen", detail)

    def test_without_the_price_right_the_product_page_opens(self) -> None:
        Role.objects.create(name="Lager ohne Preise", module_levels={"material": 2, "products": 2})
        storekeeper = self.browser_for("luka", "Lager ohne Preise")
        model = make_model("Leiter 3-teilig", category_code="R")
        response = storekeeper.post(reverse("material:model_create_product", args=[model.pk]))
        product = Product.objects.get(name="Leiter 3-teilig")
        self.assertRedirects(response, reverse("products:detail", args=[product.pk]), fetch_redirect_response=False)

    def test_without_products_rights_there_is_no_button(self) -> None:
        Role.objects.create(name="Werkstatt", module_levels={"material": 2})
        workshop = self.browser_for("willi", "Werkstatt")
        model = make_model("Leiter 3-teilig", category_code="R")
        self.assertNotIn(
            "Als Produkt anlegen", self.assert_ok(workshop.get(reverse("material:model_detail", args=[model.pk])))
        )
        self.assertEqual(workshop.post(reverse("material:model_create_product", args=[model.pk])).status_code, 403)

    def test_customer_material_goes_to_the_product_form(self) -> None:
        model = make_model("Pult der Band", category_code="C")
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk])))
        self.assertNotIn("Als Produkt anlegen", detail)
        self.assertIn(f"{reverse('products:create')}?category={category('C').pk}", detail)


class ProductFormTests(UiTestCase):
    """PRD-046: kind before category; existing models assigned from the product's page."""

    def test_the_kind_comes_first(self) -> None:
        page = self.assert_ok(self.client.get(reverse("products:create")))
        self.assertLess(page.index('name="kind"'), page.index('name="category"'))
        self.assertIn('data-reload-fields="kind owner"', page)
        self.assertIn('data-reload-fields="kind category owner"', page)

    def test_categories_of_the_kind_come_first(self) -> None:
        page = self.assert_ok(self.client.get(reverse("products:create"), {"kind": "sale"}))
        group = page.index('<optgroup label="Kategorien für „Verkaufs- oder Verbrauchsprodukt“">')
        others = page.index('<optgroup label="Weitere Kategorien">')
        self.assertLess(group, page.index(">Verkauf</option>"), "Verkauf among the matching ones")
        self.assertLess(page.index(">Verkauf</option>"), others)
        self.assertLess(others, page.index(">Kabel</option>"))

    def test_the_chosen_kind_stays_with_the_category(self) -> None:
        data = form_data(self.client.get(reverse("products:create"), {"kind": "sale", "category": category("K").pk}))
        self.assertEqual((data["kind"], data["billing_mode"], data["article_number"]), ("sale", "flat", "K-001"))
        rental = form_data(
            self.client.get(reverse("products:create"), {"kind": "rental", "category": category("K").pk})
        )
        self.assertEqual((rental["kind"], rental["billing_mode"]), ("rental", "daily_piece"))

    def test_an_existing_model_is_assigned_from_the_product(self) -> None:
        product = make_product("K-005", "XLR-Kabel 5 m")
        model = make_model("Cordial CPM 5 FM", category_code="K")
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[product.pk])))
        self.assertIn("Vorhandenes Modell zuordnen", page)
        self.assertIn(f'data-url="{reverse("material:model_suggest")}"', page)
        response = self.client.post(
            reverse("material:model_assign"), {"product": product.pk, "material_model": model.pk}, follow=True
        )
        self.assertRedirects(response, reverse("products:detail", args=[product.pk]))
        model.refresh_from_db()
        self.assertEqual(model.default_product, product)
        again = self.client.post(
            reverse("material:model_assign"),
            {"product": make_product("K-006").pk, "material_model": model.pk},
            follow=True,
        )
        self.assertTrue(any("gehört schon" in message for message in self.messages_of(again)))
        model.refresh_from_db()
        self.assertEqual(model.default_product, product)

    def test_nothing_chosen_is_explained(self) -> None:
        product = make_product("K-005")
        response = self.client.post(reverse("material:model_assign"), {"product": product.pk}, follow=True)
        self.assertIn("Wähle ein Modell aus den Vorschlägen.", self.messages_of(response))


class DefaultLocationPageTests(UiTestCase):
    """MAT-052: Einstellungen name the default; the storage locations show and set it."""

    def test_the_settings_name_the_default(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn("Neue Exemplare kommen nach: Hauptlager", page)
        listing = self.assert_ok(self.client.get(reverse("admin:masterdata_storagelocation_changelist")))
        self.assertIn("Standard für neue Exemplare", listing)

    def test_choosing_another_default_in_the_settings(self) -> None:
        hall = StorageLocation.objects.create(name="Halle 2")
        change = reverse("admin:masterdata_storagelocation_change", args=[hall.pk])
        page = self.client.get(change)
        data = form_data(page, containing="parent", is_default="on")
        data.pop("_addanother", None)
        data.pop("_continue", None)
        self.client.post(change, data)
        self.assertEqual(StorageLocation.get_default(), hall)
        self.assertEqual(StorageLocation.objects.filter(is_default=True).count(), 1)
