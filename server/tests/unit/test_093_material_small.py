# SPDX-License-Identifier: GPL-3.0-or-later
"""Small things in the material management (LOG-020, MAT-074, MAT-058, MAT-079, MAT-070).

1. The requirement: "Fuhrpark" and the button to take a model into the fleet appear only for fitting categories, not
   for a model of the category Kabel – only a model of a vehicle category (the category or one above it
   presets the product kind "vehicle", as FZ "Fuhrpark") comes into the fleet: the page, its dialog and the API.
2. The requirement: the tab Produkte of the material management has no import button – the import stays under Einstellungen →
   Import und Export.
3. The requirement: the tab Produkte also gets the "Kauf einpflegen" button that models and items already have.
4. The requirement: on models the table in the box "Ertrag" is collapsed by default.
5. The requirement: the audit form has a compact "Stammdatenübersicht" to check whether details such as length,
   purchase date, ... are documented correctly.
6. The requirement: the sub-tabs of "Offene Punkte" show the number of reports in their headings; the sum is shown
   at "Offene Punkte" itself as well.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from unittest import mock
from urllib.parse import urlencode

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.customfields import services as custom_fields
from rentalars.customfields.models import CustomField, Fieldset, FieldsetEntry, FieldType
from rentalars.masterdata.models import Category, CategoryField, StorageLocation, Supplier
from rentalars.material import audits, fleet
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.products.models import Product
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, at, category, make_item, make_model, make_product, make_stock
from tests.ui.base import UiTestCase, form_data

REFUSED = "Nur Modelle einer Fahrzeug-Kategorie (Produktart „Fahrzeug“) kommen in den Fuhrpark."


def trailer_category() -> Category:
    """A subcategory of FZ "Fuhrpark"; like every new category it presets "rental product" itself."""
    sub = Category(name="Anhänger", parent=category("FZ"))
    sub.full_clean()
    sub.save()
    return sub


# --- 1. The fleet only for vehicle categories ------------------------------------------------------------------


class FleetCategoryCase(UiTestCase):
    """A cable of category K "Kabel", a van of FZ "Fuhrpark" and a trailer of the subcategory FZ > Anhänger.

    All three planned as rental products so far.
    """

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_model("XLR-Kabel 10 m", make_product("K-500", "XLR-Kabel 10 m"))
        self.van = make_model("Ford Transit", make_product("FZ-400", "Transporter (Miete)", price="90.00"))
        sub = trailer_category()
        self.trailer = make_model("Planenanhänger", make_product("FZ-410", "Anhänger (Miete)", category=sub))


class FleetCategoryTests(FleetCategoryCase):
    """LOG-020: the rule in the service, on the model's page and in the dialog."""

    def test_only_vehicle_categories(self) -> None:
        self.assertEqual(fleet.transition_problem(self.cable), REFUSED)
        self.assertEqual(fleet.transition_problem(self.van), "")
        self.assertEqual(fleet.transition_problem(self.trailer), "")  # the parent FZ counts
        self.assertFalse(fleet.is_vehicle_category(category("K")))
        self.assertTrue(fleet.is_vehicle_category(self.trailer.category))
        # A model without product of a vehicle category, too.
        self.assertEqual(fleet.transition_problem(make_model("Neuer Bus", category_code="FZ")), "")
        self.assertEqual(fleet.transition_problem(make_model("Neues Kabel", category_code="K")), REFUSED)

    def test_the_service_refuses_a_cable(self) -> None:
        with self.assertRaisesMessage(Exception, REFUSED):
            fleet.move_model_to_fleet(self.cable, ALL_RIGHTS, vehicle_type="car", price_per_km=Decimal("1"))
        self.assertFalse(Product.objects.filter(kind="vehicle").exists())
        transition = fleet.move_model_to_fleet(self.trailer, ALL_RIGHTS, vehicle_type="trailer", price=None)
        self.assertEqual(transition.product.category, self.trailer.category)

    def test_the_row_fleet_only_on_models_of_vehicle_categories(self) -> None:
        cable = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.cable.pk])))
        self.assertNotIn("In den Fuhrpark übernehmen", cable)
        self.assertNotIn(reverse("material:model_to_fleet", args=[self.cable.pk]), cable)
        self.assertNotIn("<dt>Fuhrpark</dt>", cable)
        for model in (self.van, self.trailer):
            with self.subTest(model=model.name):
                page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk])))
                self.assertIn("<dt>Fuhrpark</dt>", page)
                self.assertIn("In den Fuhrpark übernehmen", page)

    def test_the_dialog_refuses_a_cable(self) -> None:
        url = reverse("material:model_to_fleet", args=[self.cable.pk])
        detail = reverse("material:model_detail", args=[self.cable.pk])
        response = self.client.get(url)
        self.assertRedirects(response, detail)
        self.assertEqual(self.messages_of(self.client.get(url, follow=True)), [REFUSED])
        response = self.client.post(url, {"vehicle_type": "car", "price_per_km": "0,75", "trailer_billing": "day"})
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        self.assertFalse(Product.objects.filter(kind="vehicle").exists())
        self.assertEqual(MaterialModel.objects.get(pk=self.cable.pk).default_product.article_number, "K-500")
        # The van opens the dialog.
        self.assert_ok(self.htmx("get", reverse("material:model_to_fleet", args=[self.van.pk])))


class FleetCategoryApiTests(ApiTestCase):
    """LOG-020: ``POST /material-models/{id}/to-fleet`` follows the same rule."""

    def test_a_cable_is_refused_a_trailer_of_a_subcategory_taken(self) -> None:
        cable = make_model("XLR-Kabel 10 m", make_product("K-500"))
        response = self.admin.post(f"{API}/material-models/{cable.pk}/to-fleet", {"vehicle_type": "car"}, format="json")
        self.assert_error(response, 400, "validation_error")
        self.assertIn(REFUSED, response.content.decode())
        trailer = make_model("Planenanhänger", make_product("FZ-410", category=trailer_category()))
        response = self.admin.post(
            f"{API}/material-models/{trailer.pk}/to-fleet", {"vehicle_type": "trailer"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["product"]["article_number"], "FZ-411")


# --- 2. and 3. The buttons of the tab "Produkte" ---------------------------------------------------------------


class ProductsTabTests(UiTestCase):
    """MAT-074: no import button on the tab "Produkte"; "Kauf einpflegen" as on "Modelle" and "Exemplare"."""

    PURCHASE = f'<a class="btn secondary" href="{reverse("material:purchase")}">'

    def head_of(self, text: str) -> str:
        return text[text.index('<div class="page-head">') : text.index('<nav class="tabs"')]

    def test_no_import_but_enter_a_purchase(self) -> None:
        products = self.head_of(self.assert_ok(self.client.get(reverse("products:list"))))
        self.assertNotIn(reverse("core:import", args=["products"]), products)
        self.assertNotIn(">Import<", products)
        self.assertIn("Neues Produkt", products)
        self.assertIn(self.PURCHASE, products)
        self.assertIn("Kauf einpflegen</a>", products)
        # The same button – look and place: after the main button – as on the tabs "Modelle" and "Exemplare".
        button = products[products.index(self.PURCHASE) : products.index("</a>", products.index(self.PURCHASE)) + 4]
        for name in ("material:model_list", "material:item_list"):
            with self.subTest(page=name):
                head = self.head_of(self.assert_ok(self.client.get(reverse(name))))
                self.assertIn(button, head)
                self.assertLess(head.index("Neues Materialmodell"), head.index(button))
        self.assertLess(products.index("Neues Produkt"), products.index(self.PURCHASE))
        # The import of products stays under Einstellungen → Import und Export.
        settings = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(reverse("core:import", args=["products"]), settings)
        self.assert_ok(self.client.get(reverse("core:import", args=["products"])))

    def test_the_button_only_for_who_may_change_the_material(self) -> None:
        Role.objects.create(name="Vertrieb", module_levels={"products": 2, "material": 1})
        sales = self.assert_ok(self.browser_for("vera", "Vertrieb").get(reverse("products:list")))
        self.assertNotIn(reverse("material:purchase"), sales)
        self.assertIn("Neues Produkt", sales)
        warehouse = self.assert_ok(self.browser_for("luka", "Lager").get(reverse("products:list")))
        self.assertIn(self.PURCHASE, warehouse)  # products read only: no "Neues Produkt", but the purchase
        self.assertNotIn("Neues Produkt", warehouse)


# --- 4. The table of the box "Ertrag" folded --------------------------------------------------------------------


class RevenueFoldedTests(UiTestCase):
    """MAT-058: the sums stay in sight; the table item by item is a <details> that is closed."""

    def test_folded_by_default(self) -> None:
        product = make_stock("S-100", 3)
        model = MaterialModel.objects.get(default_product=product)
        page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk])))
        self.assertIn(f'hx-get="{reverse("projects:model_revenue", args=[model.pk])}" hx-trigger="load"', page)
        box = self.assert_ok(self.htmx("get", reverse("projects:model_revenue", args=[model.pk])))
        self.assertIn("Kalkuliert mit den Exemplaren dieses Modells eingenommen", box)  # "kalkuliert"
        self.assertIn(
            '<details class="revenue-items">\n  <summary>Ertrag je Exemplar (3 Exemplare)</summary>\n  <table', box
        )
        self.assertNotIn('<details class="revenue-items" open', box)
        table = box[box.index('<details class="revenue-items">') : box.index("</details>")]
        self.assertIn("<caption", table)
        self.assertEqual(table.count('<a class="tape"'), 3)
        # The sums come before the folded table.
        self.assertLess(box.index("Kalkuliert mit den Exemplaren dieses Modells"), box.index("<details"))


# --- 5. The master data in the audit mode ----------------------------------------------------------------------


def make_field(name: str, field_type: str = FieldType.TEXT, **values: object) -> CustomField:
    """A custom field, checked as the form checks it."""
    field = CustomField(name=name, field_type=field_type, **values)
    field.full_clean()
    field.save()
    return field


class AuditMasterDataTests(UiTestCase):
    """MAT-079: a cable 0427 with its length, bought from a dealer, in the fieldset "Kabel" with a firmware and an
    insurance."""

    def setUp(self) -> None:
        super().setUp()
        self.length = CategoryField.objects.get(category=category("K"), label="Länge")
        self.model = make_model("XLR-Kabel 10 m", make_product("K-500"), category_code="K")
        self.model.set_field_value(self.length, "10")
        self.model.save()
        self.hall = StorageLocation.objects.create(name="Halle 2")
        shelf = StorageLocation.objects.create(name="Regal B", parent=self.hall)
        self.item = make_item(
            self.model,
            427,
            serial_numbers=["SN-0427"],
            purchase_date=datetime.date(2027, 2, 1),
            purchase_price=Decimal("12.50"),
            supplier=Supplier.objects.create(name="Musikhaus Muster"),
            storage_location=shelf,
        )
        self.colour = make_field("Farbe")
        self.insurance = make_field("Versicherungswert", FieldType.NUMBER, unit="€", is_sensitive=True)
        self.label_date = make_field("Etikett geklebt")
        fieldset = Fieldset.objects.create(name="Kabel")
        for position, field in enumerate((self.colour, self.insurance, self.label_date), start=1):
            FieldsetEntry.objects.create(
                fieldset=fieldset, field=field, position=position, is_required=field == self.label_date
            )
        custom_fields.assign_fieldset(self.model, fieldset)
        custom_fields.store_values(self.item, {self.colour: "schwarz", self.insurance: "20"})
        self.url = reverse("material:audit")

    def overview_of(self, text: str) -> str:
        return text[text.index('<section class="audit-master"') : text.index("</section>", text.index("audit-master"))]

    def test_every_field_and_the_gaps(self) -> None:
        overview = self.overview_of(self.assert_ok(self.client.get(self.url, {"id": "0427"})))
        self.assertIn('<h3 id="audit-master-title">Stammdaten</h3>', overview)
        gap = '<span class="audit-gap" aria-hidden="true">–</span><span class="visually-hidden">nicht erfasst</span>'
        for label, value in (
            ("ID", "0427"),
            ("Modell", "XLR-Kabel 10 m"),
            ("Hersteller", gap),
            ("Kategorie", "Kabel"),
            ("Seriennummer", "SN-0427"),
            ("Rechnungsdatum", "01.02.2027"),
            ("Gekauft bei", "Musikhaus Muster"),
            ("Kaufpreis (netto)", "12,50 €"),
            ("Lagerort", "Halle 2 &gt; Regal B"),
            ("Status", "verfügbar"),
            ("Länge", "10 m"),
            ("Farbe", "schwarz"),
            ("Versicherungswert (€)", "20"),
        ):
            with self.subTest(label=label):
                self.assertIn(f"<dt>{label}</dt><dd>{value}", overview)
        # A required custom field without value is a gap and says so.
        self.assertIn(f'<dt>Etikett geklebt</dt><dd>{gap} <span class="badge red">Pflichtangabe fehlt</span>', overview)
        # The item's own value of a category field is marked.
        self.item.set_field_override(self.length, "5")
        self.item.save()
        overview = self.overview_of(self.assert_ok(self.client.get(self.url, {"id": "0427"})))
        self.assertIn('<dt>Länge</dt><dd>5 m <span class="muted small">(eigen)</span>', overview)
        # Installed in a case: the place of the case, and which case.
        case = make_item(make_model("Case"), 500, storage_location=self.hall)
        MaterialItem.objects.filter(pk=self.item.pk).update(installed_in=case)
        overview = self.overview_of(self.assert_ok(self.client.get(self.url, {"id": "0427"})))
        self.assertIn('<dt>Lagerort</dt><dd>Halle 2 <span class="muted small">(in 0500)</span>', overview)

    def test_purchase_price_and_sensitive_values_need_the_right(self) -> None:
        Role.objects.create(name="Lager ohne Preise", module_levels={"material": 2})
        page = self.assert_ok(self.browser_for("lea", "Lager ohne Preise").get(self.url, {"id": "0427"}))
        overview = self.overview_of(page)
        self.assertNotIn("Kaufpreis", overview)
        self.assertNotIn("12,50", overview)
        self.assertNotIn("Versicherungswert", overview)
        self.assertIn("<dt>Farbe</dt><dd>schwarz", overview)
        rows = audits.master_data(audits.audit_item(427), ALL_RIGHTS)
        self.assertIn("Kaufpreis (netto)", [row.label for row in rows])

    def test_a_set_names_the_item_with_the_price(self) -> None:
        head = make_item(self.model, 426, purchase_price=Decimal("25.00"))
        MaterialItem.objects.filter(pk=self.item.pk).update(purchase_price=None, purchase_price_in=head)
        overview = self.overview_of(self.assert_ok(self.client.get(self.url, {"id": "0427"})))
        self.assertIn("<dt>Kaufpreis (netto)</dt><dd>im Preis von 0426 enthalten", overview)

    def test_the_protection_class(self) -> None:
        """MAT-077: the protection class of the model, or the item's own one – a gap while none is known."""
        overview = self.overview_of(self.assert_ok(self.client.get(self.url, {"id": "0427"})))
        self.assertIn('<dt>Schutzklasse</dt><dd><span class="audit-gap"', overview)
        MaterialModel.objects.filter(pk=self.model.pk).update(protection_class="I")
        overview = self.overview_of(self.assert_ok(self.client.get(self.url, {"id": "0427"})))
        self.assertIn("<dt>Schutzklasse</dt><dd>I (Schutzleiter)</dd>", overview)
        MaterialItem.objects.filter(pk=self.item.pk).update(protection_class_override="II")
        overview = self.overview_of(self.assert_ok(self.client.get(self.url, {"id": "0427"})))
        self.assertIn(
            '<dt>Schutzklasse</dt><dd>II (Schutzisolierung) <span class="muted small">(eigen)</span>', overview
        )

    def test_edit_the_item_and_come_back_to_the_audit(self) -> None:
        page = self.assert_ok(self.client.get(self.url, {"id": "0427"}))
        back = f"{self.url}?{urlencode({'id': '0427'})}"
        edit = f"{reverse('material:item_edit', args=[self.item.pk])}?{urlencode({'next': back})}"
        self.assertIn(f'href="{edit.replace("&", "&amp;")}"', self.overview_of(page))
        self.assertIn("Exemplar bearbeiten</a>", self.overview_of(page))
        form = self.client.get(edit)
        self.assertIn(f'<a class="btn secondary" href="{back}">Abbrechen</a>', self.assert_ok(form))
        required = {f"cf-f{self.label_date.pk}": "ja"}  # the gap the audit showed, filled
        response = self.client.post(
            edit, form_data(form, containing="serial_number", serial_number="SN-NEU", **required)
        )
        self.assertRedirects(response, back)
        self.assertEqual(MaterialItem.objects.get(pk=self.item.pk).serial_number, "SN-NEU")
        # The round of the audit is kept: what was audited before is still listed.
        self.client.post(self.url, {"item": self.item.pk, "action": "ok"})
        self.client.post(edit, form_data(self.client.get(edit), containing="serial_number"))
        self.assertIn(">0427</a>", self.assert_ok(self.client.get(self.url)).split('id="audit-round-title"')[1])
        # Another server is no place to go back to; without "next" the item's page as before.
        outside = f"{reverse('material:item_edit', args=[self.item.pk])}?next=https://example.com/"
        response = self.client.post(outside, form_data(self.client.get(outside), containing="serial_number"))
        self.assertRedirects(response, reverse("material:item_detail", args=[self.item.pk]))
        plain = reverse("material:item_edit", args=[self.item.pk])
        self.assertIn(
            f'href="{reverse("material:item_detail", args=[self.item.pk])}">Abbrechen',
            self.client.get(plain).content.decode(),
        )

    def test_a_fixed_number_of_queries(self) -> None:
        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assert_ok(self.client.get(self.url, {"id": "0427"}))
            return len(captured)

        queries()  # caches of the first request (settings, company)
        few = queries()
        # Two more category fields and three more custom fields, all with values.
        for position, label in enumerate(("Querschnitt", "Steckertyp"), start=2):
            field = CategoryField.objects.create(category=category("K"), label=label, position=position)
            self.model.set_field_value(field, "XLR")
        self.model.save()
        fieldset = Fieldset.objects.get(name="Kabel")
        values = {}
        for position, name in enumerate(("Charge", "Prüfer", "Hersteller-Nr."), start=4):
            field = make_field(name)
            FieldsetEntry.objects.create(fieldset=fieldset, field=field, position=position)
            values[field] = "x"
        custom_fields.store_values(self.item, values)
        custom_fields.forget_values(self.item)
        page = self.assert_ok(self.client.get(self.url, {"id": "0427"}))
        self.assertIn("<dt>Steckertyp</dt><dd>XLR", page)
        self.assertIn("<dt>Hersteller-Nr.</dt><dd>x", page)
        self.assertEqual(queries(), few)


# --- 6. The sum of the open points on the tab "Offene Punkte" -------------------------------------------------


class OpenPointsCountTests(UiTestCase):
    """MAT-070: a rack without product, two open to-dos of a microphone, a cable due for its audit."""

    TAB = re.compile(
        r'<a href="/material/open-points/"(?: aria-current="page")?>Offene Punkte(?: <span class="badge accent">(\d+)</span>)?</a>'
    )
    SUB = re.compile(r'<nav class="tabs sub".*?</nav>', re.S)

    def setUp(self) -> None:
        super().setUp()
        self.rack = make_item(make_model("Rack 19 Zoll"), 500)
        self.microphone = make_item(make_model("Shure SM58", make_product("T-010")), 427)
        audits.add_todo(self.microphone, "Label fehlt")
        audits.add_todo(self.microphone, "Klett fehlt")
        self.cable = make_item(make_model("XLR-Kabel 10 m", make_product("K-010")), 428)
        MaterialItem.objects.filter(pk=self.cable.pk).update(created_at=at(1) - datetime.timedelta(days=800))

    def total_on(self, url: str, client: object = None) -> int | None:
        text = self.assert_ok((client or self.client).get(url))
        found = self.TAB.search(text)
        self.assertIsNotNone(found, url)
        return int(found.group(1)) if found.group(1) else None

    def test_the_sum_of_the_sub_tabs_on_every_tab(self) -> None:
        counts = audits.open_point_counts()
        self.assertEqual(counts, {"without_product": 1, "todos": 2, "audits": 1})
        for url in (
            reverse("products:list"),
            reverse("material:model_list"),
            reverse("material:item_list"),
            reverse("material:open_without_product"),
            reverse("material:open_todos"),
            reverse("material:open_audits"),
            reverse("material:inspections"),
            reverse("material:audit"),
            reverse("material:fleet"),
            reverse("material:fleet_utilization"),
            reverse("material:import"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.total_on(url), 4)
        # The sum equals the three numbers of the sub-tabs.
        page = self.assert_ok(self.client.get(reverse("material:open_todos")))
        numbers = [int(number) for number in re.findall(r'badge accent">(\d+)<', self.SUB.search(page).group(0))]
        self.assertEqual(numbers, [1, 2, 1])
        self.assertEqual(sum(numbers), self.total_on(reverse("material:open_todos")))
        # The number is part of the text of the link.
        self.assertIn(
            '<a href="/material/open-points/" aria-current="page">Offene Punkte <span class="badge accent">4</span></a>',
            page,
        )
        # Done and fixed: the number goes down, and without open points there is none.
        audits.complete_todos(self.microphone.todos.all())
        self.assertEqual(self.total_on(reverse("material:model_list")), 2)
        rack = self.rack.material_model
        rack.default_product = make_product("R-001", "Rack 19 Zoll")
        rack.save()
        audits.record_audit(self.cable)
        self.assertIsNone(self.total_on(reverse("material:model_list")))

    def test_archived_items_do_not_count(self) -> None:
        MaterialItem.objects.filter(pk__in=[self.rack.pk, self.microphone.pk, self.cable.pk]).update(status="retired")
        self.assertIsNone(self.total_on(reverse("material:item_list")))

    def test_readers_see_it_others_do_not(self) -> None:
        Role.objects.create(name="Material lesen", module_levels={"material": 1})
        self.assertEqual(self.total_on(reverse("material:model_list"), self.browser_for("rita", "Material lesen")), 4)
        Role.objects.create(name="Nur Produkte", module_levels={"products": 1})
        products_only = self.browser_for("paul", "Nur Produkte")
        with CaptureQueriesContext(connection) as captured:
            text = self.assert_ok(products_only.get(reverse("products:list")))
        self.assertNotIn("Offene Punkte", text)
        self.assertFalse(
            any("material_itemtodo" in query["sql"] for query in captured), "no counting without the right"
        )

    def test_a_few_queries_however_many_open_points(self) -> None:
        url = reverse("products:list")

        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assert_ok(self.client.get(url))
            return len(captured)

        queries()
        few = queries()
        rack = MaterialModel.objects.get(name="Rack 19 Zoll")
        for number in range(600, 620):
            audits.add_todo(make_item(rack, number), "Label fehlt")
        self.assertEqual(self.total_on(url), 4 + 20 + 20)
        self.assertEqual(queries(), few)
        # The pages of "Offene Punkte" count once: the tab takes the numbers of the sub-tabs.
        with mock.patch.object(audits, "open_point_counts", wraps=audits.open_point_counts) as counted:
            self.assert_ok(self.client.get(reverse("material:open_todos")))
            self.assertEqual(counted.call_count, 1)
            self.assert_ok(self.client.get(reverse("material:model_list")))
            self.assertEqual(counted.call_count, 2)
