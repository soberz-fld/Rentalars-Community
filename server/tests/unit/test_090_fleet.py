# SPDX-License-Identifier: GPL-3.0-or-later
"""The fleet in the material administration, and vehicle products (LOG-002 to LOG-004, LOG-013 to LOG-016, LOG-018).

Requirement: as with the personnel, logistics (vehicles, trailers) does not stand among the material lines of a project but
separately (below the personnel). The fleet is managed in the area "Materialverwaltung". A motor vehicle is billed per kilometre, a
trailer by the day or per kilometre; a vehicle that pulls a trailer on a route is billed with more per kilometre.

* A vehicle product: a motor vehicle needs its price per kilometre, a trailer the price it is billed by; the rates
  need the price right, the internal costs the right to see purchase prices – in the form, on the page, in the API
  and in the import.
* The vehicles are the items of material models of vehicle products: their data (licence plate, seats, class,
  towing capacity, weight) on the item page, the tab "Fuhrpark" lists them, the utilization shows their bookings
  over the projects with overlaps in red.
* A model planned as material so far becomes vehicles with a new vehicle product; the old product and every
  project line stay as they are.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Rights
from rentalars.core.history import describe
from rentalars.core.models import AuditLogEntry
from rentalars.core.tabular import read_table, suggest_mapping
from rentalars.material import fleet
from rentalars.material.history import item_history
from rentalars.material.models import InspectionType, ItemStatus, MaterialItem, MaterialModel, Vehicle
from rentalars.material.services import assign_model_to_product
from rentalars.products.models import BillingMode, Product, ProductKind, TrailerBilling, VehicleType
from rentalars.projects.logistics import add_vehicle_line
from rentalars.projects.models import ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_line, at, make_item, make_model, make_product, make_project
from tests.ui.base import UiTestCase, form_data


def car_product(number: str = "S-900", name: str = "Sprinter", **fields: Any) -> Product:
    """A motor vehicle billed per kilometre, with a surcharge for trips with a trailer."""
    values = {
        "kind": ProductKind.VEHICLE,
        "vehicle_type": VehicleType.CAR,
        "price_per_km": Decimal("0.80"),
        "trailer_surcharge_per_km": Decimal("0.20"),
        "cost_per_km": Decimal("0.35"),
        **fields,
    }
    return make_product(number, name, price=None, **values)


def trailer_product(number: str = "S-901", name: str = "Planenanhänger", **fields: Any) -> Product:
    """A trailer billed per day."""
    values = {"kind": ProductKind.VEHICLE, "vehicle_type": VehicleType.TRAILER, "cost_per_day": Decimal("8.00")}
    values.update(fields)
    return make_product(number, name, price=fields.pop("price", "25.00"), **values)


def book(project: Any, item: MaterialItem, start: Any = None, end: Any = None) -> Any:
    """Book a vehicle for a project with all rights (LOG-001)."""
    return add_vehicle_line(project, rights=ALL_RIGHTS, product=item.product, item=item, start=start, end=end)


class FleetCase(RentalarsTestCase):
    """A van with two items and a trailer with one."""

    def setUp(self) -> None:
        super().setUp()
        self.car = car_product()
        self.car_model = make_model("Mercedes Sprinter", self.car)
        self.van = make_item(self.car_model, 801)
        self.van2 = make_item(self.car_model, 802)
        self.trailer = trailer_product()
        self.trailer_model = make_model("Humbaur Planenanhänger", self.trailer)
        self.hanger = make_item(self.trailer_model, 811)


# --- Vehicle products (LOG-005, LOG-006, LOG-010) ---------------------------------------------------------------


class ProductFormTests(UiTestCase):
    """The product form asks for the rates of a vehicle, and only for them."""

    def setUp(self) -> None:
        super().setUp()
        self.sample = make_product("S-001")

    def new_form(self, **changes: Any) -> dict[str, Any]:
        page = self.client.get(reverse("products:create"), {"kind": "vehicle"})
        values = {
            "category": self.sample.category_id,
            "article_number": "S-950",
            "name": "Crafter",
            "kind": "vehicle",
            "unit": self.sample.unit_id,
            "tax_rate": self.sample.tax_rate_id,
            **changes,
        }
        return form_data(page, containing="vehicle_type", **values)

    def test_the_form_shows_the_fields_of_a_vehicle(self) -> None:
        page = self.assert_ok(self.client.get(reverse("products:create"), {"kind": "vehicle"}))
        self.assertIn("Fahrzeugart", page)
        self.assertIn("Preis je Kilometer (netto)", page)
        self.assertIn("Anhängerzuschlag je Kilometer (netto)", page)
        self.assertIn("Interne Kosten je Kilometer", page)
        # Shown only for a vehicle and its type; the price (per day) only for a trailer, never for a motor vehicle.
        self.assertIn('data-show-if="kind=vehicle&amp;vehicle_type=car"', page)
        self.assertIn('data-require-if="kind=vehicle&amp;vehicle_type=car;', page)
        self.assertIn("kind=vehicle&amp;vehicle_type=trailer&amp;trailer_billing=day", page)
        self.assertIn("unter Materialverwaltung → Fuhrpark", page)

    def test_a_car_needs_its_price_per_kilometre(self) -> None:
        url = reverse("products:create")
        response = self.client.post(url, self.new_form(vehicle_type="car", price="12,00"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("price_per_km", response.context["form"].errors)
        response = self.client.post(url, self.new_form(vehicle_type="car", price="12,00", price_per_km="0,90"))
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        product = Product.objects.get(article_number="S-950")
        # The hidden day price of a motor vehicle is not kept; a vehicle is billed as its kind presets.
        self.assertEqual((product.price, product.price_per_km), (None, Decimal("0.90")))
        self.assertEqual(product.billing_mode, BillingMode.DAILY_PER_PIECE)

    def test_a_trailer_needs_the_price_it_is_billed_by(self) -> None:
        url = reverse("products:create")
        data = self.new_form(vehicle_type="trailer", trailer_billing="day", price="", trailer_surcharge_per_km="1,00")
        response = self.client.post(url, data)
        self.assertIn("price", response.context["form"].errors)
        response = self.client.post(url, {**data, "trailer_billing": "km"})
        self.assertIn("price_per_km", response.context["form"].errors)
        response = self.client.post(url, {**data, "price": "30,00", "cost_per_day": "5,00"})
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        product = Product.objects.get(article_number="S-950")
        self.assertTrue(product.is_trailer)
        # The surcharge belongs to motor vehicles only: dropped for a trailer.
        self.assertEqual((product.price, product.trailer_surcharge_per_km), (Decimal("30.00"), None))
        self.assertEqual(product.cost_per_day, Decimal("5.00"))

    def test_other_kinds_drop_the_values_of_a_vehicle(self) -> None:
        response = self.client.post(
            reverse("products:create"),
            self.new_form(kind="rental", vehicle_type="car", price="12,00", price_per_km="0,90", cost_per_km="0,10"),
        )
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        product = Product.objects.get(article_number="S-950")
        self.assertEqual((product.kind, product.vehicle_type, product.price_per_km), ("rental", "", None))
        self.assertIsNone(product.cost_per_km)

    def test_rates_only_with_the_price_right_costs_only_with_the_purchase_right(self) -> None:
        Role.objects.create(name="Produkte ohne Preise", module_levels={"products": 2})
        Role.objects.create(name="Produkte mit Preisen", module_levels={"products": 2}, special_rights=["prices"])
        bare = self.assert_ok(
            self.browser_for("pia", "Produkte ohne Preise").get(reverse("products:create"), {"kind": "vehicle"})
        )
        self.assertIn('name="vehicle_type"', bare)
        self.assertNotIn('name="price_per_km"', bare)
        self.assertNotIn('name="cost_per_km"', bare)
        priced = self.assert_ok(
            self.browser_for("paul", "Produkte mit Preisen").get(reverse("products:create"), {"kind": "vehicle"})
        )
        self.assertIn('name="price_per_km"', priced)
        self.assertNotIn('name="cost_per_km"', priced)

    def test_the_product_page_shows_the_rates(self) -> None:
        car = car_product()
        trailer = trailer_product()
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[car.pk])))
        self.assertIn("Preis je Kilometer (netto)", page)
        self.assertIn("0,80 €", page)
        self.assertIn("0,20 €", page)
        self.assertIn("Interne Kosten je Kilometer", page)
        self.assertNotIn("Abrechnungsart", page)
        trailer_page = self.assert_ok(self.client.get(reverse("products:detail", args=[trailer.pk])))
        self.assertIn("Preis je Tag (netto)", trailer_page)
        self.assertIn("25,00 €", trailer_page)
        self.assertIn("Interne Kosten je Tag", trailer_page)
        Role.objects.create(name="Produkte lesen", module_levels={"products": 1})
        reader = self.assert_ok(
            self.browser_for("rita", "Produkte lesen").get(reverse("products:detail", args=[car.pk]))
        )
        self.assertIn("Fahrzeugart", reader)
        self.assertNotIn("0,80 €", reader)
        self.assertNotIn("Interne Kosten", reader)

    def test_a_kit_offers_no_vehicle_as_component(self) -> None:
        kit = make_product("S-300", "Set", kind=ProductKind.KIT, price="40.00")
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[kit.pk])))
        self.assertIn("exclude_kind=surcharge,subrental,service,vehicle", page)


class ProductApiTests(ApiTestCase):
    """The product API with the rates of a vehicle and the rights for them."""

    def body(self, **fields: Any) -> dict[str, Any]:
        sample = Product.objects.filter(article_number="S-001").first() or make_product("S-001")
        return {
            "article_number": "S-950",
            "category": sample.category_id,
            "name": "Crafter",
            "unit": sample.unit_id,
            "tax_rate": sample.tax_rate_id,
            "kind": "vehicle",
            "vehicle_type": "car",
            **fields,
        }

    def test_a_car_through_the_api(self) -> None:
        response = self.admin.post(f"{API}/products", self.body(), format="json")
        self.assert_error(response, 400, "validation_error", "price_per_km")
        response = self.admin.post(f"{API}/products", self.body(price_per_km="0.90", cost_per_km="0.30"), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        data = response.json()
        self.assertEqual((data["vehicle_type"], data["price_per_km"], data["cost_per_km"]), ("car", "0.90", "0.30"))
        self.assertEqual(data["trailer_billing"], TrailerBilling.DAY)

    def test_rates_and_costs_need_their_rights(self) -> None:
        car = car_product()
        Role.objects.create(name="Produkte mit Preisen", module_levels={"products": 2}, special_rights=["prices"])
        client = self.client_for("paul", "Produkte mit Preisen")
        data = client.get(f"{API}/products/{car.pk}").json()
        self.assertEqual(data["price_per_km"], "0.80")
        self.assertNotIn("cost_per_km", data)
        response = client.patch(f"{API}/products/{car.pk}", {"cost_per_km": "0.10"}, format="json")
        self.assert_error(response, 400, "validation_error", "cost_per_km")
        Role.objects.create(name="Produkte ohne Preise", module_levels={"products": 2})
        bare = self.client_for("pia", "Produkte ohne Preise")
        self.assertNotIn("price_per_km", bare.get(f"{API}/products/{car.pk}").json())


class ProductImportTests(RentalarsTestCase):
    """LOG-002, LOG-005: vehicles in the product import, by the headings of the exported list."""

    def test_a_trailer_from_a_file(self) -> None:
        from rentalars.products.importer import IMPORT_FIELDS, import_products

        make_product("S-001")
        text = (
            "Art.-Nr.;Name;Art;Fahrzeugart;Anhänger abrechnen;Preis;Preis je km;Interne Kosten je Tag\n"
            "S-960;Kofferanhänger;Fahrzeug;Anhänger;je Tag;28,00;0,40;6,00\n"
        )
        table = read_table(io.BytesIO(text.encode("utf-8")), "fuhrpark.csv")
        mapping = suggest_mapping(table.headers, IMPORT_FIELDS)
        report = import_products(table, mapping, dry_run=False, rights=ALL_RIGHTS)
        self.assertTrue(report.ok, [issue.message for issue in report.errors])
        product = Product.objects.get(article_number="S-960")
        self.assertEqual((product.kind, product.vehicle_type, product.trailer_billing), ("vehicle", "trailer", "day"))
        self.assertEqual(
            (product.price, product.price_per_km, product.cost_per_day),
            (Decimal("28.00"), Decimal("0.40"), Decimal("6.00")),
        )

    def test_costs_need_the_right_to_see_purchase_prices(self) -> None:
        from rentalars.products.importer import IMPORT_FIELDS, import_products

        text = "Art.-Nr.;Name;Interne Kosten je km\nS-960;Kofferanhänger;0,30\n"
        table = read_table(io.BytesIO(text.encode("utf-8")), "f.csv")
        rights = Rights(module_levels={"products": 2}, special_rights=frozenset({"prices"}))
        report = import_products(table, suggest_mapping(table.headers, IMPORT_FIELDS), dry_run=True, rights=rights)
        self.assertIn("Einkaufspreise", report.errors[0].message)


# --- Material of vehicle products (LOG-002) ----------------------------------------------------------------------


class MaterialOfVehiclesTests(RentalarsTestCase):
    """Models and items can belong to vehicle products; the availability of material leaves them out."""

    def test_a_model_is_assigned_to_a_vehicle_product(self) -> None:
        from rentalars.material.forms import stock_products

        car = car_product()
        model = make_model("VW Crafter", category_code="S")
        assign_model_to_product(model, car)
        self.assertEqual(MaterialModel.objects.get(pk=model.pk).default_product, car)
        self.assertIn(car, stock_products())
        service = make_product("S-500", kind=ProductKind.KIT)
        with self.assertRaisesMessage(ValidationError, "Fahrzeuge"):
            assign_model_to_product(make_model("Anderes", category_code="S"), service)

    def test_the_availability_of_material_ignores_vehicles(self) -> None:
        from rentalars.availability.engine import AvailabilityEngine

        car = car_product()
        make_item(make_model("VW Crafter", car), 900)
        answer = AvailabilityEngine().availability([car.pk], at(10), at(12))[car.pk]
        self.assertFalse(answer.checked)

    def test_planned_material_does_not_become_a_vehicle(self) -> None:
        """Review finding 4: its lines would drop out of availability and packing – the model moves instead."""
        from rentalars.products.services import save_product

        van = make_product("S-200", "Transporter", price="90.00")
        add_line(make_project(), van)
        van.kind, van.vehicle_type, van.price_per_km = ProductKind.VEHICLE, VehicleType.CAR, Decimal("0.80")
        with self.assertRaisesMessage(ValidationError, "In den Fuhrpark übernehmen"):
            save_product(van, ALL_RIGHTS)


# --- Vehicle data (LOG-002, LOG-003, LOG-013) -------------------------------------------------------------------


class VehicleDataTests(FleetCase):
    """The rules of the vehicle data, checked wherever they are set."""

    def test_a_car_has_its_seats_min_at_most_max(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            fleet.save_vehicle(self.van, licence_plate="b-rl 123")
        self.assertIn("seats_min", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            fleet.save_vehicle(self.van, licence_plate="B-RL 123", seats_min=9, seats_max=3)
        self.assertIn("seats_min", caught.exception.message_dict)
        vehicle = fleet.save_vehicle(self.van, licence_plate="b-rl  123", seats_min=3, seats_max=9, licence_class="b")
        self.assertEqual((vehicle.licence_plate, vehicle.licence_class, vehicle.seats_text), ("B-RL 123", "B", "3–9"))
        # A second save changes the same row; what is not given stays.
        fleet.save_vehicle(self.van, towing_capacity_kg=2000)
        self.assertEqual(Vehicle.objects.get(item=self.van).seats_max, 9)
        self.assertEqual(Vehicle.objects.count(), 1)

    def test_a_licence_plate_belongs_to_one_vehicle(self) -> None:
        fleet.save_vehicle(self.van, licence_plate="B-RL 123", seats_min=3, seats_max=3)
        with self.assertRaises(ValidationError) as caught:
            fleet.save_vehicle(self.van2, licence_plate="b-rl 123", seats_min=3, seats_max=3)
        self.assertIn("Kennzeichen", " ".join(caught.exception.messages))
        # Empty plates do not collide.
        fleet.save_vehicle(self.van2, seats_min=2, seats_max=2)

    def test_a_trailer_has_no_seats_and_tows_nothing(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            fleet.save_vehicle(self.hanger, seats_min=2, seats_max=2)
        self.assertIn("seats_min", caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            fleet.save_vehicle(self.hanger, towing_capacity_kg=500)
        vehicle = fleet.save_vehicle(self.hanger, licence_plate="B-AH 1", gross_weight_kg=750, licence_class="BE")
        self.assertEqual(vehicle.gross_weight_kg, 750)

    def test_only_items_of_vehicle_products(self) -> None:
        cable = make_item(make_model("Kabel", make_product("S-100")), 100)
        with self.assertRaisesMessage(ValidationError, "Fahrzeug-Produkts"):
            fleet.save_vehicle(cable, licence_plate="X")
        with self.assertRaises(ValidationError):
            fleet.save_vehicle(self.van, colour="rot")

    def test_changes_stand_in_the_history_of_the_item(self) -> None:
        fleet.save_vehicle(self.van, licence_plate="B-RL 123", seats_min=3, seats_max=3)
        fleet.save_vehicle(self.van, licence_plate="B-RL 124")
        changes = [change for row in item_history(self.van, ALL_RIGHTS) for change in row.changes]
        self.assertIn(("Kennzeichen", "B-RL 123", "B-RL 124"), [(c.label, c.old, c.new) for c in changes])


# --- The item page (LOG-002, LOG-004) ---------------------------------------------------------------------------


class ItemPageTests(UiTestCase, FleetCase):
    """The panel "Fahrzeugdaten" with its dialog, and the bookings of the vehicle."""

    def setUp(self) -> None:
        super().setUp()
        self.fest = make_project("Stadtfest", start=at(10), end=at(12))
        self.messe = make_project("Messe", start=at(11), end=at(13))

    def test_a_booked_vehicle_is_retired_not_deleted(self) -> None:
        """Review finding 5: the right reason, in the browser and over the API."""
        book(self.fest, self.van)
        response = self.client.post(reverse("material:item_delete", args=[self.van.pk]), follow=True)
        self.assertIn("Dieses Fahrzeug ist in Projekten gebucht", response.content.decode())
        self.assertTrue(MaterialItem.objects.filter(pk=self.van.pk).exists())

    def test_the_panel_with_seats_missing_and_bookings(self) -> None:
        book(self.fest, self.van)
        book(self.messe, self.van)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.van.pk])))
        self.assertIn("Fahrzeugdaten", page)
        self.assertIn("Sitzplätze fehlen", page)
        # a booking links to the project's Überblick – adapted.
        self.assertIn(f'href="{reverse("projects:overview", args=[self.fest])}"', page)
        self.assertIn(f"{self.messe.number} Messe", page)
        self.assertEqual(page.count("überschneidet sich mit einer anderen Buchung"), 2)
        self.assertIn(reverse("material:vehicle_edit", args=[self.van.pk]), page)
        # An item of another product has no such panel.
        cable = make_item(make_model("Kabel", make_product("S-100")), 100)
        self.assertNotIn(
            "Fahrzeugdaten", self.assert_ok(self.client.get(reverse("material:item_detail", args=[cable.pk])))
        )

    def test_the_dialog_saves_the_data(self) -> None:
        url = reverse("material:vehicle_edit", args=[self.van.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("Sitzplätze min.", dialog)
        self.assertNotIn("<html", dialog)
        response = self.htmx("post", url, {"licence_plate": "B-RL 123", "seats_min": "9", "seats_max": "3"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("seats_min", response.context["form"].errors)
        response = self.htmx("post", url, {"licence_plate": "B-RL 123", "seats_min": "3", "seats_max": "9"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("material:item_detail", args=[self.van.pk]) + "#vehicle")
        self.assertEqual(Vehicle.objects.get(item=self.van).seats_text, "3–9")
        # Without the page script: a page of its own, and back to the item.
        page = self.assert_ok(self.client.get(url))
        self.assertIn("<html", page)
        response = self.client.post(url, {"licence_plate": "B-RL 124", "seats_min": "3", "seats_max": "3"})
        self.assertRedirects(response, reverse("material:item_detail", args=[self.van.pk]) + "#vehicle")
        # Audited: the change stands in the history of the item.
        history = self.assert_ok(self.client.get(reverse("material:item_history", args=[self.van.pk])))
        self.assertIn("B-RL 124", history)

    def test_a_trailer_is_asked_neither_seats_nor_towing(self) -> None:
        url = reverse("material:vehicle_edit", args=[self.hanger.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertNotIn('name="seats_min"', dialog)
        self.assertNotIn('name="towing_capacity_kg"', dialog)
        response = self.htmx("post", url, {"licence_plate": "B-AH 1", "gross_weight_kg": "750", "licence_class": "be"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Vehicle.objects.get(item=self.hanger).licence_class, "BE")

    def test_rights(self) -> None:
        book(self.fest, self.van)
        Role.objects.create(name="Fuhrpark lesen", module_levels={"material": 1})
        reader = self.browser_for("lea", "Fuhrpark lesen")
        page = self.assert_ok(reader.get(reverse("material:item_detail", args=[self.van.pk])))
        self.assertNotIn(reverse("material:vehicle_edit", args=[self.van.pk]), page)
        # A project the reader may not open: "Projekt" with its number, no name, no link.
        self.assertIn(f"Projekt {self.fest.number}", page)
        self.assertNotIn("Stadtfest", page)
        self.assertEqual(reader.get(reverse("material:vehicle_edit", args=[self.van.pk])).status_code, 403)
        url = reverse("material:vehicle_edit", args=[self.hanger.pk])
        self.assertEqual(reader.post(url, {"licence_plate": "X"}).status_code, 403)
        self.assertFalse(Vehicle.objects.exists())


# --- Materialverwaltung → Fuhrpark (LOG-002, LOG-014) -------------------------------------------------------------


class FleetListTests(UiTestCase, FleetCase):
    """The tab "Fuhrpark": every vehicle and trailer with its data, inspection and booking."""

    def setUp(self) -> None:
        super().setUp()
        fleet.save_vehicle(self.van2, licence_plate="B-RL 222", seats_min=2, seats_max=6, licence_class="B")
        fleet.save_vehicle(self.hanger, licence_plate="B-AH 1")
        inspection = InspectionType.objects.create(name="Hauptuntersuchung", interval_months=24)
        inspection.material_models.add(self.car_model)
        self.url = reverse("material:fleet")

    def test_the_list(self) -> None:
        project = make_project("Stadtfest", start=at(10), end=at(12))
        book(project, self.van2)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('aria-current="page">Fuhrpark</a>', page)
        for text in ("B-RL 222", "B-AH 1", "KFZ", "Anhänger", "2–6", "Mercedes Sprinter", "S-900 Sprinter"):
            self.assertIn(text, page)
        # A car without seats says so; the inspection never done is overdue, in red.
        self.assertIn("Sitzplätze fehlen", page)
        self.assertIn('<span class="badge red">Hauptuntersuchung: nie geprüft</span>', page)
        self.assertIn(f"{project.number} Stadtfest", page)
        self.assertIn(reverse("material:fleet_utilization"), page)
        trailers = self.assert_ok(self.client.get(self.url, {"type": "trailer"}))
        self.assertIn("B-AH 1", trailers)
        self.assertNotIn("B-RL 222", trailers)

    def test_archived_vehicles_only_when_asked(self) -> None:
        MaterialItem.objects.filter(pk=self.van.pk).update(status=ItemStatus.RETIRED)
        self.assertNotIn(self.van.display_id, self.assert_ok(self.client.get(self.url)))
        self.assertIn(self.van.display_id, self.assert_ok(self.client.get(self.url, {"status": "retired"})))

    def test_csv_and_sorting(self) -> None:
        response = self.client.get(self.url, {"format": "csv", "cols": "all"})
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8-sig")
        self.assertIn("Kennzeichen", text.splitlines()[0])
        self.assertIn("B-RL 222", text)
        for key in ("plate", "type", "seats", "due", "booking", "licence_class", "status"):
            with self.subTest(sort=key):
                self.assert_ok(self.client.get(self.url, {"sort": f"-{key}", "cols": "all", "group": key}))

    def test_material_read_is_needed(self) -> None:
        Role.objects.create(name="Nur Projekte", module_levels={"projects": 1})
        self.assertEqual(self.browser_for("otto", "Nur Projekte").get(self.url).status_code, 403)


# --- Utilization of the fleet (LOG-004, LOG-018) ----------------------------------------------------------------


class UtilizationTests(UiTestCase, FleetCase):
    """A timeline of the vehicles over the projects; overlapping bookings in red."""

    def setUp(self) -> None:
        super().setUp()
        fleet.save_vehicle(self.van, licence_plate="B-RL 123", seats_min=3, seats_max=3)
        self.fest = make_project("Stadtfest", start=at(10, 8), end=at(12, 18))
        self.messe = make_project("Messe", start=at(11, 8), end=at(13, 18))
        self.kongress = make_project("Kongress", start=at(15, 8), end=at(16, 18))
        self.url = reverse("material:fleet_utilization")

    def test_overlapping_bookings_are_red(self) -> None:
        book(self.fest, self.van)
        book(self.messe, self.van)
        book(self.kongress, self.van2)
        page = self.assert_ok(self.client.get(self.url, {"from": "2027-03-08", "weeks": "2"}))
        self.assertIn("B-RL 123", page)
        self.assertIn("Buchungen überschneiden sich", page)
        self.assertEqual(page.count("is-conflict"), 2 + 1)  # both bookings, and the sample of the legend
        self.assertIn(f"{self.kongress.number} Kongress", page)
        # In hours as well (VFG-024).
        hourly = self.assert_ok(self.client.get(self.url, {"from": "2027-03-11", "days": "2"}))
        self.assertIn("is-conflict", hourly)
        self.assertIn("data-tl-zoom", hourly)

    def test_rows_and_overlaps_from_the_service(self) -> None:
        from rentalars.schedule.services import Scale, day_range

        book(self.fest, self.van)
        book(self.messe, self.van)
        book(self.kongress, self.van2)
        scale = Scale(days=day_range(at(8).date(), 14))
        rows = fleet.utilization_rows([self.van, self.van2, self.hanger], scale, set())
        self.assertEqual([row.conflict for row in rows], [True, False, False])
        self.assertEqual(rows[0].name, "B-RL 123")
        self.assertEqual([bar.label for bar in rows[1].bars], [f"Projekt {self.kongress.number}"])
        self.assertEqual(rows[1].bars[0].url, "")

    def test_a_cancelled_project_does_not_count(self) -> None:
        book(self.fest, self.van)
        book(self.messe, self.van)
        self.messe.status = ProjectStatus.CANCELLED
        self.messe.save()
        page = self.assert_ok(self.client.get(self.url, {"from": "2027-03-08", "weeks": "2"}))
        self.assertNotIn("Buchungen überschneiden sich", page)

    def test_project_names_only_for_who_may_open_them(self) -> None:
        book(self.fest, self.van)
        Role.objects.create(name="Fuhrpark lesen", module_levels={"material": 1})
        page = self.assert_ok(
            self.browser_for("lea", "Fuhrpark lesen").get(self.url, {"from": "2027-03-08", "weeks": "2"})
        )
        self.assertIn(f"Projekt {self.fest.number}", page)
        self.assertNotIn("Stadtfest", page)


# --- From material to the fleet (LOG-016) -----------------------------------------------------------------------


class TransitionTests(UiTestCase):
    """A model planned as material so far becomes vehicles; nothing in the projects changes."""

    def setUp(self) -> None:
        super().setUp()
        # LOG-020 (tests/unit/test_093_material_small.py): only a model of a vehicle
        # category comes into the fleet – the van is a rental product of FZ "Fuhrpark" now, no longer of S.
        self.old = make_product("FZ-400", "Transporter (Miete)", price="90.00")
        self.model = make_model("Ford Transit", self.old)
        self.items = [make_item(self.model, 700), make_item(self.model, 701)]
        self.project = make_project("Stadtfest")
        self.line = add_line(self.project, self.old, 1).line
        self.closed = make_project("Altes Fest", status=ProjectStatus.CLOSED)

    def test_the_service(self) -> None:
        transition = fleet.move_model_to_fleet(
            self.model, ALL_RIGHTS, vehicle_type="car", price_per_km=Decimal("0.75"), cost_per_km=Decimal("0.30")
        )
        product = transition.product
        self.assertEqual((product.kind, product.vehicle_type, product.name), ("vehicle", "car", "Transporter (Miete)"))
        self.assertEqual(product.article_number, "FZ-401")
        self.assertEqual(
            (product.price_per_km, product.cost_per_km, product.price), (Decimal("0.75"), Decimal("0.30"), None)
        )
        self.assertEqual((product.unit, product.tax_rate), (self.old.unit, self.old.tax_rate))
        self.assertEqual(MaterialModel.objects.get(pk=self.model.pk).default_product, product)
        self.assertTrue(all(item.product == product for item in MaterialItem.objects.filter(material_model=self.model)))
        # The old product and the line stay as they are.
        self.old.refresh_from_db()
        self.assertEqual((self.old.kind, self.old.price), ("rental", Decimal("90.00")))
        line = type(self.line).objects.get(pk=self.line.pk)
        self.assertEqual((line.product, line.unit_price), (self.old, Decimal("90.00")))
        self.assertEqual(transition.open_projects, [self.project])
        message = fleet.open_projects_message(transition, {self.project.pk})
        self.assertIn(f"{self.project.number} Stadtfest", message)
        self.assertIn("„Logistik“", message)
        self.assertIn("1 weitere", fleet.open_projects_message(transition, set()))

    def test_items_that_named_the_old_product_follow(self) -> None:
        item = self.items[0]
        item.product_override = self.old
        item.save()
        transition = fleet.move_model_to_fleet(self.model, ALL_RIGHTS, vehicle_type="trailer", price=None)
        self.assertEqual(transition.items_moved, 1)
        self.assertEqual(MaterialItem.objects.get(pk=item.pk).product, transition.product)
        # A trailer per day takes the price of the old product as its day price.
        self.assertEqual((transition.product.price, transition.product.trailer_billing), (Decimal("90.00"), "day"))

    def test_refused(self) -> None:
        sale = make_model(
            "Verbrauch", make_product("FZ-410", kind=ProductKind.SALE, price=None, sale_price=Decimal("1"))
        )
        with self.assertRaisesMessage(ValidationError, "Mietprodukt"):
            fleet.move_model_to_fleet(sale, ALL_RIGHTS, vehicle_type="car", price_per_km=Decimal("1"))
        bulk = make_model("Schüttgut", make_product("FZ-420"), bulk=True)
        with self.assertRaisesMessage(ValidationError, "Mengenmaterial"):
            fleet.move_model_to_fleet(bulk, ALL_RIGHTS, vehicle_type="car", price_per_km=Decimal("1"))
        fleet.move_model_to_fleet(self.model, ALL_RIGHTS, vehicle_type="car", price_per_km=Decimal("1"))
        with self.assertRaisesMessage(ValidationError, "gehört schon zum Fuhrpark"):
            fleet.move_model_to_fleet(self.model, ALL_RIGHTS, vehicle_type="car", price_per_km=Decimal("1"))

    def test_customer_material_is_refused(self) -> None:
        from rentalars.masterdata.models import Category
        from tests.helpers import make_customer

        category = Category.objects.filter(parent__isnull=True, is_customer_material=True).first()
        product = make_product(
            f"{category.code}-001",
            "Kundenbus",
            category=category,
            owner=make_customer(),
            price=None,
            billing_mode=BillingMode.FLAT,
        )
        model = make_model("Kundenbus", product)
        self.assertIn("Kundenmaterial", fleet.transition_problem(model))

    def test_rates_need_their_rights(self) -> None:
        rights = Rights(module_levels={"material": 2, "products": 2})
        with self.assertRaisesMessage(ValidationError, "Preise"):
            fleet.move_model_to_fleet(self.model, rights, vehicle_type="car", price_per_km=Decimal("1"))
        transition = fleet.move_model_to_fleet(self.model, rights, vehicle_type="car")
        # Without the price right the price per kilometre starts at 0, as a product made from a model (MAT-051).
        self.assertEqual(transition.product.price_per_km, Decimal("0"))

    def test_the_page(self) -> None:
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        url = reverse("material:model_to_fleet", args=[self.model.pk])
        self.assertIn(url, detail)
        self.assertIn("In den Fuhrpark übernehmen", detail)
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn('value="90,00"', dialog)  # the day price of a trailer, preset
        response = self.htmx("post", url, {"vehicle_type": "car", "price_per_km": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("price_per_km", response.context["form"].errors)
        response = self.client.post(url, {"vehicle_type": "car", "price_per_km": "0,75", "trailer_billing": "day"})
        self.assertRedirects(response, reverse("material:model_detail", args=[self.model.pk]))
        messages = [str(message) for message in response.wsgi_request._messages]
        self.assertTrue(any("ist jetzt im Fuhrpark" in message for message in messages), messages)
        self.assertTrue(any(f"{self.project.number} Stadtfest" in message for message in messages), messages)
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assertNotIn(url, detail)
        # The move stands in the history of the model, in words.
        entries = describe(list(AuditLogEntry.for_object(self.model)), ALL_RIGHTS)
        self.assertTrue(
            any("In den Fuhrpark übernommen: Produkt FZ-401 statt FZ-400" in row.summary for row in entries)
        )

    def test_who_may_not_change_products_gets_no_action(self) -> None:
        Role.objects.create(name="Lager ohne Produkte", module_levels={"material": 2, "products": 1})
        browser = self.browser_for("luka", "Lager ohne Produkte")
        url = reverse("material:model_to_fleet", args=[self.model.pk])
        self.assertNotIn(url, self.assert_ok(browser.get(reverse("material:model_detail", args=[self.model.pk]))))
        self.assertEqual(browser.post(url, {"vehicle_type": "car"}).status_code, 403)


# --- API (LOG-015) -----------------------------------------------------------------------------------------------


class VehicleApiTests(ApiTestCase, FleetCase):
    """Every operation of the fleet through the API, with its rights (API-014)."""

    def test_a_booked_vehicle_is_not_deleted(self) -> None:
        book(make_project("Stadtfest"), self.van)
        response = self.admin.delete(f"{API}/material-items/{self.van.pk}")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(MaterialItem.objects.filter(pk=self.van.pk).exists())

    def test_list_and_filters(self) -> None:
        fleet.save_vehicle(self.van, licence_plate="B-RL 123", seats_min=3, seats_max=9)
        response = self.admin.get(f"{API}/vehicles")
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.json()["results"]
        self.assertEqual([row["display_id"] for row in rows], [self.van.display_id, self.van2.display_id, "0811"])
        first = rows[0]
        self.assertEqual(
            (first["licence_plate"], first["type"], first["seats_min"], first["seats_max"]), ("B-RL 123", "car", 3, 9)
        )
        self.assertEqual(first["product"]["article_number"], "S-900")
        self.assertEqual(first["material_model"]["name"], "Mercedes Sprinter")
        self.assertTrue(rows[1]["seats_missing"])
        trailers = self.admin.get(f"{API}/vehicles", {"type": "trailer"}).json()["results"]
        self.assertEqual([row["id"] for row in trailers], [self.hanger.pk])
        MaterialItem.objects.filter(pk=self.van2.pk).update(status=ItemStatus.DEFECTIVE)
        defective = self.admin.get(f"{API}/vehicles", {"status": "defective"}).json()["results"]
        self.assertEqual([row["id"] for row in defective], [self.van2.pk])
        self.assert_error(self.admin.get(f"{API}/vehicles", {"type": "bus"}), 400, "validation_error", "type")

    def test_read_and_change_one(self) -> None:
        url = f"{API}/vehicles/{self.van.pk}"
        inspection = InspectionType.objects.create(name="UVV", interval_months=12)
        inspection.material_models.add(self.car_model)
        data = self.admin.get(url).json()
        self.assertEqual((data["licence_plate"], data["next_inspection"]["state"]), ("", "overdue"))
        response = self.admin.patch(url, {"licence_plate": "b-rl 1", "seats_min": 2, "seats_max": 5}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.json()["licence_plate"], "B-RL 1")
        response = self.admin.patch(url, {"licence_class": "C1"}, format="json")
        self.assertEqual((response.json()["licence_class"], response.json()["seats_max"]), ("C1", 5))
        response = self.admin.put(url, {"seats_min": 3, "seats_max": 3}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.json()["licence_plate"], response.json()["licence_class"]), ("", ""))
        self.assert_error(self.admin.patch(url, {"seats_min": 9}, format="json"), 400, "validation_error", "seats_min")
        trailer = f"{API}/vehicles/{self.hanger.pk}"
        self.assert_error(self.admin.patch(trailer, {"seats_min": 1}, format="json"), 400, "validation_error")
        cable = make_item(make_model("Kabel", make_product("S-100")), 100)
        self.assertEqual(self.admin.get(f"{API}/vehicles/{cable.pk}").status_code, 404)

    def test_availability(self) -> None:
        fest = make_project("Stadtfest", start=at(10), end=at(12))
        messe = make_project("Messe", start=at(11), end=at(13))
        book(fest, self.van)
        book(messe, self.van)
        url = f"{API}/vehicles/{self.van.pk}/availability"
        response = self.admin.get(url, {"start": "2027-03-09T00:00:00+01:00", "end": "2027-03-14T00:00:00+01:00"})
        self.assertEqual(response.status_code, 200, response.data)
        data = response.json()
        self.assertFalse(data["free"])
        self.assertEqual([booking["project_name"] for booking in data["bookings"]], ["Stadtfest", "Messe"])
        self.assertEqual([booking["overlaps"] for booking in data["bookings"]], [True, True])
        free = self.admin.get(url, {"start": "2027-03-20T00:00:00+01:00", "end": "2027-03-21T00:00:00+01:00"}).json()
        self.assertTrue(free["free"])
        self.assertEqual(free["bookings"], [])
        self.assert_error(self.admin.get(url, {"start": "2027-03-20T00:00:00"}), 400, "validation_error")
        # Without the projects: the bookings without project, number and name (AUT-016).
        Role.objects.create(name="Fuhrpark lesen", module_levels={"material": 1})
        reader = self.client_for("lea", "Fuhrpark lesen")
        hidden = reader.get(url, {"start": "2027-03-09T00:00:00+01:00", "end": "2027-03-14T00:00:00+01:00"}).json()
        self.assertEqual(
            [
                (booking["project"], booking["project_number"], booking["project_name"])
                for booking in hidden["bookings"]
            ],
            [(None, None, None)] * 2,
        )

    def test_to_fleet(self) -> None:
        # LOG-020: a model of the vehicle category FZ (tests/unit/test_093_material_small.py), no longer of S.
        old = make_product("FZ-400", "Transporter (Miete)", price="90.00")
        model = make_model("Ford Transit", old)
        make_item(model, 700)
        project = make_project("Stadtfest")
        add_line(project, old, 1)
        response = self.admin.post(
            f"{API}/material-models/{model.pk}/to-fleet",
            {"vehicle_type": "trailer", "trailer_billing": "km", "price_per_km": "0.50"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        data = response.json()
        self.assertEqual((data["old_product"]["article_number"], data["items_moved"]), ("FZ-400", 0))
        self.assertEqual(data["open_projects"], [{"id": project.pk, "number": project.number, "name": "Stadtfest"}])
        product = Product.objects.get(pk=data["product"]["id"])
        self.assertEqual(
            (product.vehicle_type, product.trailer_billing, product.price), ("trailer", "km", Decimal("90.00"))
        )
        again = self.admin.post(f"{API}/material-models/{model.pk}/to-fleet", {"vehicle_type": "car"}, format="json")
        self.assert_error(again, 400, "validation_error")

    def test_rights(self) -> None:
        Role.objects.create(name="Fuhrpark lesen", module_levels={"material": 1})
        reader = self.client_for("lea", "Fuhrpark lesen")
        self.assertEqual(reader.get(f"{API}/vehicles").status_code, 200)
        self.assertEqual(
            reader.patch(f"{API}/vehicles/{self.van.pk}", {"licence_plate": "X"}, format="json").status_code, 403
        )
        self.assertEqual(
            reader.put(f"{API}/vehicles/{self.van.pk}", {"licence_plate": "X"}, format="json").status_code, 403
        )
        Role.objects.create(name="Lager ohne Produkte", module_levels={"material": 2, "products": 1})
        keeper = self.client_for("luka", "Lager ohne Produkte")
        model = make_model("Ford Transit", make_product("S-400"))
        response = keeper.post(f"{API}/material-models/{model.pk}/to-fleet", {"vehicle_type": "car"}, format="json")
        self.assertEqual(response.status_code, 403)
        Role.objects.create(name="Nur Projekte", module_levels={"projects": 1})
        self.assertEqual(self.client_for("otto", "Nur Projekte").get(f"{API}/vehicles").status_code, 403)
