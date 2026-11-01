# SPDX-License-Identifier: GPL-3.0-or-later
"""Material items and models – gross purchase prices (MAT-059), a new supplier in a dialog (MAT-060), the ID
field (MAT-063), duplicates (MAT-064).

The requirements: for new items the gross price can be entered instead of the net price; choosing "neuer Händler"
for a new item opens a dialog for the supplier's master data; the material management has a text field in the head
of every tab, next to "Import" and "Neues Produkt", to type an ID and load the item directly; products, models and
items have a "Duplizieren" button that creates a new object from an existing one.

* The purchase price of new items – and of an item being edited – is entered net or gross; a gross price names the
  tax rate it includes (the default tax rate unless chosen) and is stored net, rounded to cents, as the import does
  (IMP-014). The choice needs the right to see purchase prices and is remembered per user in the session.
* "neuer Händler" among the suggestions of the supplier field opens the supplier's master data in a dialog; saved,
  the answer "supplierCreated" names it, and the item form finds it by its name. Without the script: as before.
* The field "Exemplar-ID" in the head of every tab opens an item: 0427, 427 or #0427; an unknown ID leads to the
  list, filtered.
* "Duplizieren" on a model opens the form of a new model with its values, on an item the form of new items with its
  purchase data.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.masterdata.models import StorageLocation, Supplier, TaxRate
from rentalars.material import services
from rentalars.material.forms import PRICE_ENTRY_SESSION_KEY
from rentalars.material.models import InspectionType, ItemStatus, MaterialItem, MaterialModel
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, category, make_item, make_model, make_product
from tests.ui.base import UiTestCase, form_data

D = Decimal


def workshop_role() -> None:
    """Material write access without the right to see purchase prices."""
    Role.objects.get_or_create(name="Werkstatt", defaults={"module_levels": {"material": 2}})


class GrossPriceTests(RentalarsTestCase):
    """Gross → net, rounded to cents (MAT-059; IMP-014); the tax rate is an active one, by default the default rate."""

    def test_gross_prices_are_stored_net_rounded_to_cents(self) -> None:
        self.assertEqual(services.net_from_gross(D("119.00"), 19), D("100.00"))
        self.assertEqual(services.net_from_gross(D("10.00"), "19"), D("8.40"))  # 8.403…
        self.assertEqual(services.net_from_gross(D("9.99"), D("7")), D("9.34"))  # 9.336…
        self.assertEqual(services.net_from_gross(D("0.01"), 19), D("0.01"))  # 0.0084…
        self.assertEqual(services.net_from_gross(D("50.00"), 0), D("50.00"))

    def test_net_gross_net_keeps_the_cents(self) -> None:
        for cents in range(1, 3000, 7):
            net = D(cents) / 100
            for rate in ("19", "7"):
                self.assertEqual(services.net_from_gross(services.gross_from_net(net, rate), rate), net)

    def test_the_rate(self) -> None:
        self.assertEqual(services.gross_tax_rate(), TaxRate.get_default().rate)
        self.assertEqual(services.gross_tax_rate("19"), D("19"))
        self.assertEqual(services.entered_purchase_price(D("119"), "gross"), D("100.00"))
        self.assertEqual(services.entered_purchase_price(D("119"), "net"), D("119"))
        self.assertIsNone(services.entered_purchase_price(None, "gross"))
        with self.assertRaises(ValidationError) as caught:
            services.gross_tax_rate("16")
        self.assertIn("price_tax_rate", caught.exception.message_dict)


class GrossPricePageTests(UiTestCase):
    """The forms for new items and for an item: net or gross, remembered per user (MAT-059)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Cordial CPM 5 FM", make_product("K-005", "XLR-Kabel 5 m"), category_code="K")
        self.url = reverse("material:item_create", args=[self.model.pk])

    def test_new_items_with_a_gross_price(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Der Preis ist", page)
        self.assertIn("Der Bruttopreis enthält", page)
        self.assertIn('data-show-if="prices=gross"', page)
        data = form_data(self.client.get(self.url), count=2, purchase_price="119,00", prices="gross")
        self.assertEqual(data["price_tax_rate"], "19")  # the default tax rate

        response = self.client.post(self.url, data)

        self.assertRedirects(response, reverse("material:model_detail", args=[self.model.pk]))
        prices = list(MaterialItem.objects.filter(material_model=self.model).values_list("purchase_price", flat=True))
        self.assertEqual(prices, [D("100.00"), D("100.00")])
        # Remembered: the next form starts with "gross".
        self.assertEqual(self.client.session[PRICE_ENTRY_SESSION_KEY], {"prices": "gross", "price_tax_rate": "19"})
        self.assertEqual(form_data(self.client.get(self.url))["prices"], "gross")

    def test_another_tax_rate_and_net_as_before(self) -> None:
        TaxRate.objects.create(name="7 %", rate=D("7.00"), valid_from="2007-01-01")
        data = form_data(self.client.get(self.url), purchase_price="10,70", prices="gross", price_tax_rate="7")
        self.client.post(self.url, data)
        self.assertEqual(MaterialItem.objects.get().purchase_price, D("10.00"))
        data = form_data(self.client.get(self.url), purchase_price="10,70", prices="net")
        self.client.post(self.url, data)
        self.assertEqual(MaterialItem.objects.order_by("-pk").first().purchase_price, D("10.70"))
        refused = self.client.post(self.url, {**data, "prices": "gross", "price_tax_rate": "16"})
        self.assertEqual(refused.status_code, 200)
        self.assertEqual(MaterialItem.objects.count(), 2)

    def test_the_item_form_shows_and_takes_gross_prices(self) -> None:
        item = make_item(self.model, 427, purchase_price=D("100.00"))
        url = reverse("material:item_edit", args=[item.pk])
        self.assertEqual(form_data(self.client.get(url))["prices"], "net")
        session = self.client.session
        session[PRICE_ENTRY_SESSION_KEY] = {"prices": "gross", "price_tax_rate": "19"}
        session.save()
        data = form_data(self.client.get(url))
        self.assertEqual((data["prices"], data["purchase_price"]), ("gross", "119,00"))
        self.client.post(url, data)  # saved unchanged: still 100.00 net
        item.refresh_from_db()
        self.assertEqual(item.purchase_price, D("100.00"))
        self.client.post(url, {**data, "purchase_price": "59,50"})
        item.refresh_from_db()
        self.assertEqual(item.purchase_price, D("50.00"))

    def test_only_with_the_right_to_see_purchase_prices(self) -> None:
        workshop_role()
        workshop = self.browser_for("willi", "Werkstatt")
        page = self.assert_ok(workshop.get(self.url))
        self.assertNotIn("Der Preis ist", page)
        self.assertNotIn("Bruttopreis", page)
        data = form_data(workshop.get(self.url))
        self.assertNotIn("prices", data)
        workshop.post(self.url, {**data, "purchase_price": "119,00", "prices": "gross"})
        self.assertIsNone(MaterialItem.objects.get().purchase_price)
        self.assertNotIn(PRICE_ENTRY_SESSION_KEY, workshop.session)
        item = MaterialItem.objects.get()
        edit = self.assert_ok(workshop.get(reverse("material:item_edit", args=[item.pk])))
        self.assertNotIn("Der Preis ist", edit)


class SupplierDialogTests(UiTestCase):
    """„neuer Händler“ opens the supplier's master data in a dialog; the item form then finds the supplier (MAT-060)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Rack 6 HE", category_code="R")
        self.dialog = reverse("material:supplier_create")

    def test_new_supplier_is_offered_with_the_dialog(self) -> None:
        Supplier.objects.create(name="Musikhaus Nord")
        results = self.client.get(reverse("material:supplier_suggest"), {"q": "Neuhaus"}).json()
        self.assertEqual(results[-1]["hint"], "neuer Händler")
        self.assertEqual(results[-1]["create_url"], f"{self.dialog}?name=Neuhaus")
        known = self.client.get(reverse("material:supplier_suggest"), {"q": "musikhaus nord"}).json()
        self.assertFalse([result for result in known if "create_url" in result])
        # The forms for items ask these suggestions (the page script opens the dialog).
        for url in (
            reverse("material:item_create", args=[self.model.pk]),
            reverse("material:item_edit", args=[make_item(self.model, 500).pk]),
        ):
            self.assertIn(f'data-url="{reverse("material:supplier_suggest")}"', self.assert_ok(self.client.get(url)))

    def test_the_dialog_creates_the_supplier_and_names_it(self) -> None:
        form = self.assert_ok(self.htmx("get", f"{self.dialog}?name=Neuhaus+Licht&field=supplier"))
        self.assertIn("Neuer Händler", form)
        self.assertIn("Straße und Hausnummer", form)
        self.assertIn('value="Neuhaus Licht"', form)
        data = {
            "name": "Neuhaus Licht",
            "contact": "Frau Berg",
            "email": "info@neuhaus.example",
            "phone": "0711 123",
            "customer_number": "K-77",
            "street": "Hafenstraße 4",
            "postal_code": "70173",
            "city": "Stuttgart",
            "country": "Deutschland",
            "note": "Lieferung dienstags",
        }

        response = self.htmx("post", f"{self.dialog}?name=Neuhaus+Licht&field=supplier", data)

        self.assertEqual(response.status_code, 204)
        supplier = Supplier.objects.get(name="Neuhaus Licht")
        self.assertEqual(
            (supplier.contact, supplier.email, supplier.city, supplier.customer_number, supplier.is_active),
            ("Frau Berg", "info@neuhaus.example", "Stuttgart", "K-77", True),
        )
        answer = json.loads(response["HX-Trigger"])
        self.assertEqual(
            answer["supplierCreated"],
            {"id": supplier.pk, "name": "Neuhaus Licht", "label": "Neuhaus Licht", "field": "supplier"},
        )
        self.assertEqual(answer["objectCreated"], {"field": "supplier", "id": supplier.pk, "label": "Neuhaus Licht"})
        self.assertTrue(answer["closeDialog"])
        self.assertEqual(list(answer), ["supplierCreated", "objectCreated", "closeDialog"])  # closing comes last

        # The name lands in the item form, which finds the supplier by it – no second one.
        url = reverse("material:item_create", args=[self.model.pk])
        self.client.post(url, form_data(self.client.get(url), supplier_name="Neuhaus Licht"))
        self.assertEqual(MaterialItem.objects.get().supplier, supplier)
        self.assertEqual(Supplier.objects.filter(name__iexact="Neuhaus Licht").count(), 1)

    def test_a_name_twice_and_an_odd_field(self) -> None:
        Supplier.objects.create(name="Musikhaus Nord")
        refused = self.htmx("post", self.dialog, {"name": "musikhaus nord"})
        self.assertEqual(refused.status_code, 200)
        self.assertIn("Einen Händler mit diesem Namen gibt es schon.", refused.content.decode())
        created = self.htmx("post", f"{self.dialog}?field=a%22%5D", {"name": "Süd"})
        self.assertEqual(json.loads(created["HX-Trigger"])["supplierCreated"]["field"], "")
        self.assertNotIn("objectCreated", json.loads(created["HX-Trigger"]))

    def test_rights(self) -> None:
        """Material write access – as /suppliers of the API; reading material is not enough."""
        reader = self.browser_for("nina", "Nur-Lesen")
        self.assertEqual(self.htmx("get", self.dialog, client=reader).status_code, 403)
        self.assertEqual(self.htmx("post", self.dialog, {"name": "X"}, client=reader).status_code, 403)
        self.assertFalse(Supplier.objects.filter(name="X").exists())
        self.assertFalse(reader.get(reverse("material:supplier_suggest"), {"q": "X"}).json())
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(self.htmx("post", self.dialog, {"name": "Lager-Händler"}, client=warehouse).status_code, 204)
        offered = warehouse.get(reverse("material:supplier_suggest"), {"q": "Neu"}).json()
        self.assertIn("create_url", offered[-1])

    def test_without_the_script_a_new_name_creates_the_supplier_as_before(self) -> None:
        url = reverse("material:item_create", args=[self.model.pk])
        self.client.post(url, form_data(self.client.get(url), supplier_name="Bühnentechnik Süd"))
        supplier = Supplier.objects.get(name="Bühnentechnik Süd")
        self.assertEqual((supplier.city, MaterialItem.objects.get().supplier), ("", supplier))


class ItemJumpTests(UiTestCase):
    """The field "Exemplar-ID" in the head of every tab of the material management (MAT-063)."""

    def setUp(self) -> None:
        super().setUp()
        self.item = make_item(make_model("Rack 6 HE", category_code="R"), 427)
        self.jump = reverse("material:item_jump")

    def test_the_id_as_typed_or_copied(self) -> None:
        detail = reverse("material:item_detail", args=[self.item.pk])
        for typed in ("0427", "427", "#0427", " # 0427 "):
            self.assertRedirects(self.client.get(self.jump, {"id": typed}), detail, msg_prefix=typed)
        self.item.status = ItemStatus.RETIRED
        self.item.save()
        self.assertRedirects(self.client.get(self.jump, {"id": "0427"}), detail)  # archived items too

    def test_an_unknown_id_leads_to_the_list_filtered(self) -> None:
        response = self.client.get(self.jump, {"id": "#999"})
        self.assertRedirects(response, f"{reverse('material:item_list')}?q=0999")
        page = self.client.get(self.jump, {"id": "#999"}, follow=True)
        self.assertEqual(self.messages_of(page), ["Es gibt kein Exemplar mit der ID 0999."])
        self.assertIn('value="0999"', page.content.decode())
        text = self.client.get(self.jump, {"id": "Rack"}, follow=True)
        self.assertEqual(text.redirect_chain[0][0], f"{reverse('material:item_list')}?q=Rack")
        self.assertEqual(self.messages_of(text), ["„Rack“ ist keine gültige ID."])
        self.assertRedirects(self.client.get(self.jump, {"id": " "}), reverse("material:item_list"))

    def test_in_the_head_of_every_tab(self) -> None:
        pages = [
            reverse("products:list"),
            reverse("material:model_list"),
            reverse("material:item_list"),
            # MAT-068, MAT-070: the tab "Ohne Produkt" became "Offene Punkte" with three sub-tabs; the audit mode.
            reverse("material:open_without_product"),
            reverse("material:open_todos"),
            reverse("material:open_audits"),
            reverse("material:audit"),
            reverse("material:inspections"),
            reverse("material:fleet"),
            reverse("material:fleet_utilization"),
            reverse("material:import"),
            reverse("core:import", args=["products"]),
        ]
        for url in pages:
            page = self.assert_ok(self.client.get(url))
            head = page[page.index('class="page-head"') : page.index('class="tabs"')]
            self.assertIn(f'action="{self.jump}"', head, url)
            self.assertIn('<label class="visually-hidden" for="item-jump-id">ID eines Exemplars</label>', head, url)
            self.assertIn('aria-label="Exemplar über seine ID öffnen"', head, url)

    def test_only_for_who_may_read_the_material(self) -> None:
        Role.objects.create(name="Produkte lesen", module_levels={"products": 1})
        seller = self.browser_for("vera", "Produkte lesen")
        self.assertNotIn(f'action="{self.jump}"', self.assert_ok(seller.get(reverse("products:list"))))
        self.assertEqual(seller.get(self.jump, {"id": "0427"}).status_code, 403)
        reader = self.browser_for("nina", "Nur-Lesen")
        self.assertRedirects(
            reader.get(self.jump, {"id": "0427"}), reverse("material:item_detail", args=[self.item.pk])
        )


class ModelDuplicateTests(UiTestCase):
    """„Duplizieren“ on a model: the form of a new model with its values – not its items, not its files (MAT-064)."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_product("K-005", "XLR-Kabel 5 m")
        self.original = make_model("Cordial CPM 5 FM", self.product, category_code="K", manufacturer="Cordial")
        self.original.short_name = "CPM5"
        self.original.specification = "XLR m/f, schwarz"
        self.original.weight_kg = D("0.40")
        self.original.set_category_specific_value("5")
        self.original.save()
        make_item(self.original, 500)
        self.dguv = InspectionType.objects.create(name="DGUV V3")
        self.dguv.material_models.add(self.original)
        self.url = f"{reverse('material:model_create')}?copy={self.original.pk}"

    def test_the_button_and_the_copy(self) -> None:
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.original.pk])))
        self.assertIn(f'href="{self.url}"', detail)
        self.assertIn("Duplizieren", detail)
        page = self.client.get(self.url)
        self.assertIn("Eine Kopie von „Cordial CPM 5 FM“", self.assert_ok(page))
        data = form_data(page)
        self.assertEqual(
            (data["name"], data["short_name"], data["category"], data["manufacturer_name"], data["category_specific"]),
            ("Cordial CPM 5 FM (Kopie)", "CPM5", str(category("K").pk), "Cordial", "5"),
        )
        self.assertEqual((data["default_product"], data["copy_inspection_types"]), (str(self.product.pk), "on"))

        response = self.client.post(self.url, data)

        copy = MaterialModel.objects.get(name="Cordial CPM 5 FM (Kopie)")
        self.assertRedirects(response, reverse("material:model_detail", args=[copy.pk]))
        self.assertEqual(
            (copy.specification, copy.weight_kg, copy.category_specific_display, copy.default_product),
            ("XLR m/f, schwarz", D("0.40"), "5 m", self.product),
        )
        self.assertEqual((copy.items.count(), copy.files.count()), (0, 0))
        self.assertEqual(list(self.dguv.material_models.order_by("pk")), [self.original, copy])
        self.assertEqual(self.original.items.count(), 1)
        # A second copy gets the next free name; its inspection types only when ticked.
        second = form_data(self.client.get(self.url), copy_inspection_types=None)
        self.assertEqual(second["name"], "Cordial CPM 5 FM (Kopie 2)")
        self.client.post(self.url, second)
        self.assertFalse(self.dguv.material_models.filter(name="Cordial CPM 5 FM (Kopie 2)").exists())

    def test_rights_as_creating(self) -> None:
        reader = self.browser_for("nina", "Nur-Lesen")
        detail = self.assert_ok(reader.get(reverse("material:model_detail", args=[self.original.pk])))
        self.assertNotIn("Duplizieren", detail)
        self.assertEqual(reader.get(self.url).status_code, 403)
        warehouse = self.browser_for("luka", "Lager")
        self.assertIn(
            "Duplizieren", self.assert_ok(warehouse.get(reverse("material:model_detail", args=[self.original.pk])))
        )
        warehouse.post(self.url, form_data(warehouse.get(self.url)))
        self.assertTrue(MaterialModel.objects.filter(name="Cordial CPM 5 FM (Kopie)").exists())


class ItemDuplicateTests(UiTestCase):
    """„Duplizieren“ on an item: the form of new items with its model, purchase data and storage location (MAT-064)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Funkempfänger EW-D", make_product("T-050"), category_code="T")
        self.hall = StorageLocation.objects.create(name="Halle 2")
        self.supplier = Supplier.objects.create(name="Musikhaus Nord")
        self.original = make_item(
            self.model,
            427,
            serial_number="SN-1",
            status=ItemStatus.DEFECTIVE,
            status_reason="Antenne ab",
            supplier=self.supplier,
            supplier_article_number="EWD-1",
            invoice_number="RE-4711",
            purchase_date="2026-03-01",
            purchase_price=D("499.00"),
            purchase_note="Messeangebot",
            storage_location=self.hall,
        )
        self.url = f"{reverse('material:item_create', args=[self.model.pk])}?copy={self.original.pk}"

    def test_the_button_and_the_copy(self) -> None:
        detail = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.original.pk])))
        self.assertIn(f'href="{self.url}"', detail)
        page = self.client.get(self.url)
        self.assertIn("Eine Kopie von 0427", self.assert_ok(page))
        data = form_data(page)
        self.assertEqual(
            (data["supplier_name"], data["supplier_article_number"], data["invoice_number"], data["purchase_date"]),
            ("Musikhaus Nord", "EWD-1", "RE-4711", "01.03.2026"),  # A text field, the date as written,
        )
        self.assertEqual(
            (data["purchase_price"], data["purchase_note"], data["storage_location"], data["status"]),
            ("499,00", "Messeangebot", str(self.hall.pk), "available"),
        )
        self.assertEqual((data["serial_numbers"], data["inventory_number"]), ("", ""))

        self.client.post(self.url, {**data, "count": "2", "serial_numbers": "SN-2\nSN-3"})

        copies = list(MaterialItem.objects.exclude(pk=self.original.pk).order_by("inventory_number"))
        self.assertEqual([item.serial_number for item in copies], ["SN-2", "SN-3"])
        for item in copies:
            self.assertEqual(
                (item.supplier, item.invoice_number, item.purchase_price, item.storage_location, item.status),
                (self.supplier, "RE-4711", D("499.00"), self.hall, ItemStatus.AVAILABLE),
            )
            self.assertNotEqual(item.inventory_number, 427)

    def test_prices_with_their_right_and_gross_when_chosen(self) -> None:
        workshop_role()
        workshop = self.browser_for("willi", "Werkstatt")
        data = form_data(workshop.get(self.url))
        self.assertNotIn("purchase_price", data)
        self.assertEqual(data["invoice_number"], "RE-4711")
        self.assertNotIn("499", workshop.get(self.url).content.decode())
        session = self.client.session
        session[PRICE_ENTRY_SESSION_KEY] = {"prices": "gross", "price_tax_rate": "19"}
        session.save()
        self.assertEqual(form_data(self.client.get(self.url))["purchase_price"], "593,81")  # 499.00 × 1.19
        # An item bought in a set has its price at another item: the copy starts without one (MAT-054).
        member = make_item(self.model, 428)
        member.purchase_price_in = self.original
        member.save()
        url = f"{reverse('material:item_create', args=[self.model.pk])}?copy={member.pk}"
        self.assertEqual(form_data(self.client.get(url))["purchase_price"], "")

    def test_rights_and_an_item_of_another_model(self) -> None:
        reader = self.browser_for("nina", "Nur-Lesen")
        detail = self.assert_ok(reader.get(reverse("material:item_detail", args=[self.original.pk])))
        self.assertNotIn("Duplizieren", detail)
        self.assertEqual(reader.get(self.url).status_code, 403)
        other = make_model("Rack 6 HE", category_code="R")
        url = f"{reverse('material:item_create', args=[other.pk])}?copy={self.original.pk}"
        self.assertEqual(form_data(self.client.get(url))["invoice_number"], "")


class ApiTests(ApiTestCase):
    """The API: gross prices on the existing operations (MAT-059); the dialog, the ID field and duplicates need none."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Rack 6 HE", category_code="R")

    def test_new_items_with_a_gross_price(self) -> None:
        response = self.admin.post(
            f"{API}/material-models/{self.model.pk}/items",
            {"count": 2, "purchase_price": "119.00", "prices": "gross"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([row["purchase_price"] for row in response.data], ["100.00", "100.00"])
        net = self.admin.post(
            f"{API}/material-models/{self.model.pk}/items", {"purchase_price": "119.00"}, format="json"
        )
        self.assertEqual(net.data[0]["purchase_price"], "119.00")
        single = self.admin.post(
            f"{API}/material-items",
            {"material_model": self.model.pk, "purchase_price": "11.90", "prices": "gross"},
            format="json",
        )
        self.assertEqual(single.status_code, 201, single.data)
        self.assertEqual(single.data["purchase_price"], "10.00")

    def test_changing_an_item_with_a_gross_price_and_another_rate(self) -> None:
        TaxRate.objects.create(name="7 %", rate=D("7.00"), valid_from="2007-01-01")
        item = make_item(self.model, 427)
        url = f"{API}/material-items/{item.pk}"
        changed = self.admin.patch(
            url, {"purchase_price": "10.70", "prices": "gross", "price_tax_rate": "7"}, format="json"
        )
        self.assertEqual(changed.data["purchase_price"], "10.00")
        refused = self.admin.patch(
            url, {"purchase_price": "10.70", "prices": "gross", "price_tax_rate": "16"}, format="json"
        )
        self.assert_error(refused, 400, "validation_error", "price_tax_rate")
        item.refresh_from_db()
        self.assertEqual(item.purchase_price, D("10.00"))

    def test_the_choice_needs_the_right_to_see_purchase_prices(self) -> None:
        workshop_role()
        workshop = self.client_for("willi", "Werkstatt")
        refused = workshop.post(f"{API}/material-models/{self.model.pk}/items", {"prices": "gross"}, format="json")
        self.assert_error(refused, 400, "validation_error", "prices")
        self.assertFalse(MaterialItem.objects.exists())

    def test_the_other_wishes_with_the_operations_there_are(self) -> None:
        """A supplier with its master data (/suppliers), an item by its ID (lookup), a model copied."""
        warehouse = self.client_for("luka", "Lager")
        created = warehouse.post(
            f"{API}/suppliers", {"name": "Neuhaus Licht", "city": "Stuttgart", "email": "a@neuhaus.example"}
        )
        self.assertEqual(created.status_code, 201, created.data)
        item = make_item(self.model, 427)
        found = warehouse.get(f"{API}/material-items/lookup", {"code": "#0427"})
        self.assertEqual(found.data["id"], item.pk)
        dguv = InspectionType.objects.create(name="DGUV V3")
        dguv.material_models.add(self.model)
        original = warehouse.get(f"{API}/material-models/{self.model.pk}").data
        values = {name: original[name] for name in ("short_name", "category", "manufacturer", "tracking_mode")}
        copy = warehouse.post(f"{API}/material-models", {**values, "name": "Rack 6 HE (Kopie)"}, format="json")
        self.assertEqual(copy.status_code, 201, copy.data)
        types = warehouse.patch(
            f"{API}/inspection-types/{dguv.pk}", {"material_models": [self.model.pk, copy.data["id"]]}, format="json"
        )
        self.assertEqual(types.status_code, 200, types.data)
        self.assertEqual(dguv.material_models.count(), 2)
