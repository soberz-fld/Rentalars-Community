# SPDX-License-Identifier: GPL-3.0-or-later
"""LOG-001 ff.: the block "Logistik" – vehicles and trailers booked for a project, on its trips.

The requirement: as with the personnel, logistics (vehicles, trailers) does not stand among the material lines of a
project but separately, below the personnel. A motor vehicle is billed per kilometre; a trailer by the day or per
kilometre. A motor vehicle that pulls a trailer on a route is billed with more per kilometre than the product says,
and this should be recognised automatically as far as possible. Decided: kilometres per trip are planned, driven or
a flat rate, at choice; the trailer surcharge on the towing vehicle; a trailer's day rent counts the rental days as
material does, switchable on the booking to the days with trips.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Rights
from rentalars.documents import content as content_builder
from rentalars.documents import services as documents
from rentalars.documents.models import DocumentKind
from rentalars.masterdata.models import RentalScale, ScaleTable, Supplier
from rentalars.material.models import InspectionType, Vehicle
from rentalars.personnel.models import Qualification, QualificationType
from rentalars.products.models import ProductKind, TrailerBilling, VehicleType
from rentalars.projects import course, logistics
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.list_sums import _prices_of
from rentalars.projects.models import PhaseKind, ProjectStatus, TripAdjustment, TripBilling, VehicleBilling
from rentalars.projects.planning import build_planning
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.project_templates import apply_template, save_as_template
from rentalars.projects.services import update_project
from rentalars.projects.split import split_into_subprojects
from rentalars.schedule import moves
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_item,
    make_model,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    ready_for_invoices,
)
from tests.ui.base import UiTestCase, form_data

PRICES_ONLY = Rights(module_levels={"projects": 3}, special_rights=frozenset({"prices"}))
WITHOUT_PRICES = Rights(module_levels={"projects": 3})


def make_fleet() -> dict:
    """A Sprinter (0.80 €/km, +0.20 €/km with a trailer) and a trailer (40 € a day or 0.30 €/km)."""
    car = make_product(
        "S-500",
        "Sprinter",
        price=None,
        kind=ProductKind.VEHICLE,
        vehicle_type=VehicleType.CAR,
        price_per_km=Decimal("0.80"),
        trailer_surcharge_per_km=Decimal("0.20"),
        cost_per_km=Decimal("0.25"),
    )
    trailer = make_product(
        "S-510",
        "Kofferanhänger",
        price="40.00",
        kind=ProductKind.VEHICLE,
        vehicle_type=VehicleType.TRAILER,
        price_per_km=Decimal("0.30"),
        trailer_billing=TrailerBilling.DAY,
        cost_per_day=Decimal("5.00"),
    )
    van = make_item(make_model("Mercedes Sprinter", car), 900)
    box = make_item(make_model("Humbaur Koffer", trailer), 910)
    Vehicle.objects.create(
        item=van, licence_plate="B-RL 100", seats_min=2, seats_max=3, licence_class="B", towing_capacity_kg=2000
    )
    Vehicle.objects.create(item=box, licence_plate="B-RL 900", licence_class="BE", gross_weight_kg=1500)
    return {"car": car, "trailer": trailer, "van": van, "box": box}


class LogisticsCase(RentalarsTestCase):
    """The Stadtfest, 10 to 12 March, with a setup on the 10th at the Marktplatz: two trips."""

    def setUp(self) -> None:
        super().setUp()
        self.fleet = make_fleet()
        self.project = make_project("Stadtfest")
        self.setup_phase = course.add_phase(
            self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16), location="Marktplatz 1, Musterstadt"
        )
        self.there = f"to_venue-{self.setup_phase.pk}"
        self.back = f"from_venue-{self.setup_phase.pk}"
        self.car = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["car"], item=self.fleet["van"]
        )
        self.trailer = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["trailer"], item=self.fleet["box"]
        )

    def drive(self, key: str, *, trailer: bool = False, **values) -> object:
        return logistics.add_trip_vehicle(
            self.project,
            rights=ALL_RIGHTS,
            trip_key=key,
            vehicle_line=self.car,
            trailer_line=self.trailer if trailer else None,
            **values,
        )

    def prices(self):
        return compute_project_prices(self.project)

    def price_of(self, line):
        return next(price for price in self.prices().logistics if price.line.pk == line.pk)


class BookingTests(LogisticsCase):
    def test_rates_are_copied_from_the_product(self) -> None:
        self.assertEqual((self.car.price_per_km, self.car.trailer_surcharge_per_km), (Decimal("0.80"), Decimal("0.20")))
        self.assertEqual(self.car.billing, VehicleBilling.KM)
        self.assertEqual((self.trailer.price_per_day, self.trailer.price_per_km), (Decimal("40.00"), Decimal("0.30")))
        self.assertEqual(self.trailer.billing, VehicleBilling.DAY)
        self.assertEqual((self.car.start, self.car.end), (self.project.start, self.project.end))
        self.assertEqual(self.car.label, "Sprinter (B-RL 100)")

    def test_only_vehicles_of_the_product(self) -> None:
        with self.assertRaises(ValidationError):
            logistics.add_vehicle_line(
                self.project, rights=ALL_RIGHTS, product=self.fleet["car"], item=self.fleet["box"]
            )
        cable = make_product("S-100", "Kabel")
        with self.assertRaises(ValidationError):
            logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=cable)

    def test_prices_need_the_price_right(self) -> None:
        with self.assertRaises(ValidationError):
            logistics.add_vehicle_line(
                self.project, rights=WITHOUT_PRICES, product=self.fleet["car"], price_per_km=Decimal("1")
            )
        with self.assertRaises(ValidationError):  # LOG-010: the costs need the purchase price right
            logistics.update_vehicle_line(self.car, rights=PRICES_ONLY, cost_per_km=Decimal("1"))
        line = logistics.add_vehicle_line(self.project, rights=WITHOUT_PRICES, product=self.fleet["car"])
        self.assertTrue(line.is_open)

    def test_a_vehicle_is_no_material_line(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Logistik"):
            add_line(self.project, self.fleet["car"])

    def test_a_motor_vehicle_is_billed_per_km(self) -> None:
        with self.assertRaises(ValidationError):
            self.car.billing = VehicleBilling.DAY
            self.car.full_clean()

    def test_bookings_follow_the_project_and_the_phase(self) -> None:
        update_project(self.project, start=at(11), end=at(13))
        self.car.refresh_from_db()
        self.assertEqual((self.car.start, self.car.end), (at(11), at(13)))
        on_phase = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["car"], phase=self.setup_phase
        )
        self.assertEqual((on_phase.start, on_phase.end), (at(10, 8), at(10, 16)))
        change = course.update_phase(self.setup_phase, move_crew=True, start=at(10, 10), end=at(10, 18))
        on_phase.refresh_from_db()
        self.assertEqual((on_phase.start, on_phase.end), (at(10, 10), at(10, 18)))
        self.assertEqual(change.moved_vehicle_lines, [on_phase])


class FollowTheProjectTests(LogisticsCase):
    """LOG-019: the logistics follows the project – timeline, copy, template, subprojects."""

    def test_moving_the_whole_project_takes_the_bookings_along(self) -> None:
        own = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["car"], start=at(10, 6), end=at(10, 20)
        )
        week = datetime.timedelta(days=7)
        move = moves.MoveRequest(
            project=self.project, what=moves.PERIOD, start=self.project.start + week, end=self.project.end + week
        )
        moves.perform_move(move, rights=ALL_RIGHTS)
        self.project.refresh_from_db()
        self.car.refresh_from_db()
        own.refresh_from_db()
        self.assertEqual((self.car.start, self.car.end), (self.project.start, self.project.end))
        self.assertEqual((own.start, own.end), (at(17, 6), at(17, 20)))

    def test_a_copy_with_the_logistics_but_without_driven_kilometres(self) -> None:
        self.drive(self.there, trailer=True, planned_km=Decimal("40"))
        use = self.project.trip_vehicles.get()
        logistics.update_trip_vehicle(use, rights=ALL_RIGHTS, driven_km=Decimal("42"))
        without = duplicate_project(
            self.project, name="", start=at(10, month=4), end=at(12, month=4), rights=ALL_RIGHTS, user=None
        )
        self.assertFalse(without.vehicle_lines.exists())
        copy = duplicate_project(
            self.project,
            name="",
            start=at(10, month=4),
            end=at(12, month=4),
            with_logistics=True,
            rights=ALL_RIGHTS,
            user=None,
        )
        self.assertEqual(copy.vehicle_lines.count(), 2)
        copied = copy.trip_vehicles.get()
        phase = copy.phases.get()
        self.assertEqual(copied.trip_key, f"to_venue-{phase.pk}")
        self.assertEqual((copied.planned_km, copied.driven_km), (Decimal("40"), None))
        self.assertEqual(copied.vehicle_line.item, self.fleet["van"])
        self.assertEqual(copied.trailer_line.item, self.fleet["box"])

    def test_a_template_keeps_open_bookings(self) -> None:
        template = save_as_template(self.project, name="Stadtfest", rights=ALL_RIGHTS)
        target = make_project("Weinfest", start=at(10, month=5), end=at(12, month=5))
        apply_template(template, target, rights=ALL_RIGHTS)
        lines = list(target.vehicle_lines.order_by("position"))
        self.assertEqual([line.product for line in lines], [self.fleet["car"], self.fleet["trailer"]])
        self.assertTrue(all(line.item is None for line in lines))

    def test_subprojects_leave_the_logistics_with_the_whole_project(self) -> None:
        stage = add_group(self.project, "Bühne")
        add_line(self.project, make_product("S-100", "Kabel"), 2, group=stage)
        driver = plan(self.project, "Fahrer", make_person("Ben Kraus"))
        driver.vehicle_line, driver.is_driver = self.car, True
        driver.save()
        (part,) = split_into_subprojects(self.project, [stage.pk], {driver.pk: stage.pk}).parts
        self.assertEqual(self.project.vehicle_lines.count(), 2)
        self.assertFalse(part.vehicle_lines.exists())
        driver.refresh_from_db()
        self.assertEqual((driver.project, driver.vehicle_line, driver.is_driver), (part, None, False))


class TripTests(LogisticsCase):
    def test_a_trip_of_the_project(self) -> None:
        with self.assertRaises(ValidationError):
            self.drive("to_venue-999999")
        self.drive(self.there)
        with self.assertRaises(ValidationError):  # once per trip
            self.drive(self.there)

    def test_a_trailer_pulled_by_one_vehicle_on_a_trip(self) -> None:
        with self.assertRaises(ValidationError):  # a trailer drives nothing itself
            logistics.add_trip_vehicle(self.project, rights=ALL_RIGHTS, trip_key=self.there, vehicle_line=self.trailer)
        self.drive(self.there, trailer=True)
        second = logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=self.fleet["car"])
        with self.assertRaises(ValidationError):  # LOG-006: a combination has one trailer, a trailer one vehicle
            logistics.add_trip_vehicle(
                self.project, rights=ALL_RIGHTS, trip_key=self.there, vehicle_line=second, trailer_line=self.trailer
            )

    def test_billing_and_flat_rate_need_the_price_right(self) -> None:
        with self.assertRaises(ValidationError):
            logistics.add_trip_vehicle(
                self.project, rights=WITHOUT_PRICES, trip_key=self.there, vehicle_line=self.car, billing="planned"
            )
        use = logistics.add_trip_vehicle(
            self.project, rights=WITHOUT_PRICES, trip_key=self.there, vehicle_line=self.car, planned_km=Decimal("12")
        )
        logistics.update_trip_vehicle(use, rights=WITHOUT_PRICES, driven_km=Decimal("14"))
        use.refresh_from_db()
        self.assertEqual(use.driven_km, Decimal("14"))
        with self.assertRaises(ValidationError):
            logistics.update_trip_vehicle(use, rights=ALL_RIGHTS, billing=TripBilling.FLAT)  # without its price


class PriceTests(LogisticsCase):
    """LOG-005, LOG-006, LOG-007, LOG-009, LOG-010."""

    def test_kilometres_surcharge_and_estimate(self) -> None:
        # There with the trailer, 100 km planned – the driven ones are not known yet; back alone, 110 km driven.
        self.drive(self.there, trailer=True, planned_km=Decimal("100"))
        self.drive(self.back, planned_km=Decimal("100"), driven_km=Decimal("110"))
        car = self.price_of(self.car)
        self.assertEqual(car.base_amount, Decimal("188.00"))  # 100 × (0.80 + 0.20) + 110 × 0.80
        self.assertEqual(car.surcharge_total, Decimal("20.00"))
        self.assertTrue(car.is_estimate)
        self.assertEqual(car.km_total, Decimal("210"))
        self.assertEqual(car.cost, Decimal("52.50"))  # 210 km × 0.25
        self.assertTrue(self.prices().has_estimates)

    def test_planned_kilometres_or_a_flat_rate(self) -> None:
        self.drive(self.there, planned_km=Decimal("100"), driven_km=Decimal("130"), billing=TripBilling.PLANNED)
        self.drive(self.back, trailer=True, planned_km=Decimal("100"), billing=TripBilling.FLAT, flat_price="150")
        self.trailer.billing = VehicleBilling.KM
        self.trailer.save()
        prices = self.prices()
        car = next(price for price in prices.logistics if price.line.pk == self.car.pk)
        trailer = next(price for price in prices.logistics if price.line.pk == self.trailer.pk)
        self.assertEqual(car.base_amount, Decimal("230.00"))  # 100 × 0.80 + 150 flat
        self.assertFalse(car.is_estimate)
        self.assertEqual(trailer.base_amount, Decimal("0"))  # its trip is in the flat rate
        self.assertTrue(trailer.charges[0].in_flat_rate)
        self.assertEqual(trailer.cost, Decimal("0.00"))  # no cost per km at the product

    def test_trailer_per_km(self) -> None:
        logistics.update_vehicle_line(self.trailer, rights=ALL_RIGHTS, billing=VehicleBilling.KM)
        self.drive(self.there, trailer=True, planned_km=Decimal("100"))
        self.assertEqual(self.price_of(self.trailer).base_amount, Decimal("30.00"))  # 100 × 0.30

    def test_trailer_per_day_as_material(self) -> None:
        scale = RentalScale.get_default()
        logistics.update_vehicle_line(self.trailer, rights=ALL_RIGHTS, rental_days=3)
        price = self.price_of(self.trailer)
        self.assertEqual(price.days, 3)
        if scale is not None and self.trailer.scale_version_id:
            version = self.trailer.scale_version
            table = ScaleTable(
                rows=list(version.rows.values_list("days", "factor")), extra_day_increment=version.extra_day_increment
            )
            self.assertEqual(price.base_amount, (Decimal("40.00") * table.factor_for(3)).quantize(Decimal("0.01")))
        else:
            self.assertEqual(price.base_amount, Decimal("120.00"))
        self.assertEqual(price.cost, Decimal("15.00"))  # 3 days × 5.00, no scale

    def test_trailer_only_on_the_days_with_trips(self) -> None:
        logistics.update_vehicle_line(self.trailer, rights=ALL_RIGHTS, only_trip_days=True)
        self.assertEqual(self.price_of(self.trailer).days, 0)
        self.assertEqual(self.price_of(self.trailer).amount, Decimal("0"))
        # Both trips on the 10th: one day.
        self.drive(self.there, trailer=True, planned_km=Decimal("10"))
        self.drive(self.back, trailer=True, planned_km=Decimal("10"))
        price = self.price_of(self.trailer)
        self.assertEqual((price.days, price.days_source), (1, logistics.DaysSource.TRIPS))
        self.assertEqual(price.base_amount, Decimal("40.00") * (price.scale_factor or 1))

    def test_discount_up_to_the_maximum_of_the_product(self) -> None:
        self.drive(self.back, driven_km=Decimal("100"))
        logistics.update_vehicle_line(self.car, rights=ALL_RIGHTS, discount_percent=Decimal("10"))
        self.assertEqual(self.price_of(self.car).amount, Decimal("72.00"))
        self.fleet["car"].max_discount_percent = Decimal("5")
        self.fleet["car"].save()
        price = self.price_of(self.car)
        self.assertEqual((price.amount, price.discount_is_capped), (Decimal("76.00"), True))
        self.assertEqual(self.prices().capped_discount_lines, 1)

    def test_a_vehicle_from_a_supplier_costs_what_the_supplier_charges(self) -> None:
        supplier = Supplier.objects.create(name="Autovermietung Nord")
        rented = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["car"], supplier=supplier, subrental_cost=Decimal("300")
        )
        logistics.add_trip_vehicle(
            self.project, rights=ALL_RIGHTS, trip_key=self.there, vehicle_line=rented, driven_km=Decimal("50")
        )
        price = self.price_of(rented)
        self.assertEqual((price.amount, price.cost), (Decimal("40.00"), Decimal("300.00")))
        self.assertTrue(rented.is_subrental)

    def test_totals_taxes_and_margin(self) -> None:
        self.drive(self.back, driven_km=Decimal("100"))  # 80.00
        logistics.update_vehicle_line(self.trailer, rights=ALL_RIGHTS, billing=VehicleBilling.KM)  # no trip: 0
        material = make_product("S-100", "Kabel", price="10.00")
        add_line(self.project, material, 2)
        prices = self.prices()
        self.assertEqual(prices.logistics_total, Decimal("80.00"))
        self.assertEqual(prices.net_total, prices.groups_total + prices.ungrouped_total + Decimal("80.00"))
        self.assertEqual(sum(tax.net for tax in prices.tax_lines), prices.net_total)
        self.assertEqual(prices.logistics_cost, Decimal("25.00"))
        self.assertEqual(prices.margin_before_expenses, prices.net_total - prices.logistics_cost)

    def test_project_list_and_profitability(self) -> None:
        self.drive(self.back, driven_km=Decimal("100"))
        logistics.update_vehicle_line(self.trailer, rights=ALL_RIGHTS, billing=VehicleBilling.KM)  # no trip: 0
        prices = _prices_of([self.project])[self.project.pk][0]
        self.assertEqual(prices.logistics_total, Decimal("80.00"))
        from rentalars.projects import profitability

        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        figures = profitability.figures_of([self.project])[self.project.pk]
        self.assertEqual(figures.logistics_revenue, Decimal("80.00"))
        self.assertEqual(figures.logistics_cost, Decimal("25.00"))
        self.assertEqual(figures.material_revenue, prices.net_total - Decimal("80.00"))


class WarningTests(LogisticsCase):
    """LOG-004, LOG-008, LOG-012, LOG-013, LOG-014."""

    def warnings(self, line) -> list[str]:
        planning = build_planning(self.project)
        return next(item.warnings for item in planning.logistics if item.line.pk == line.pk)

    def test_booked_elsewhere_at_the_same_time(self) -> None:
        other = make_project("Hafenfest", start=at(11), end=at(14))
        logistics.add_vehicle_line(other, rights=ALL_RIGHTS, product=self.fleet["car"], item=self.fleet["van"])
        # The number only – the reader may not be allowed to open the other project.
        texts = self.warnings(self.car)
        self.assertTrue(any(other.number in text for text in texts))
        self.assertFalse(any("Hafenfest" in text for text in texts))
        other.status = ProjectStatus.CANCELLED
        other.save()
        self.assertFalse(any(other.number in text for text in self.warnings(self.car)))

    def test_seats_drivers_and_towing(self) -> None:
        for name in ("Anna", "Ben", "Cem", "Dora"):
            plan(self.project, "Stagehand", make_person(name), vehicle_line=self.car)
        self.assertTrue(any("4" in text and "3" in text for text in self.warnings(self.car)))
        licence = QualificationType(name="Führerschein B", licence_classes="b ;")
        licence.full_clean()
        licence.save()
        self.assertEqual(licence.licence_classes, "B")
        driver = make_person("Erik")
        Qualification.objects.create(person=driver, qualification_type=licence)
        line = plan(self.project, "Fahrer", driver, vehicle_line=self.car, is_driver=True)
        self.drive(self.there, trailer=True)
        # The combination needs BE, the trailer says so; Erik has B.
        self.assertTrue(any("BE" in text for text in self.warnings(self.car)))
        Vehicle.objects.filter(item=self.fleet["van"]).update(towing_capacity_kg=1000)
        self.assertTrue(any("1500" in text for text in self.warnings(self.car)))
        line.delete()

    def test_status_and_inspections(self) -> None:
        inspection = InspectionType.objects.create(name="Hauptuntersuchung", interval_months=24)
        inspection.material_models.add(self.fleet["van"].material_model)
        self.assertTrue(any("Hauptuntersuchung" in text for text in self.warnings(self.car)))

    def test_a_trip_that_is_gone(self) -> None:
        self.drive(self.there)
        course.delete_phase(self.setup_phase)
        self.assertTrue(any("gone" in text or "nicht mehr" in text for text in self.warnings(self.car)))
        planning = build_planning(self.project)
        self.assertEqual([row.trip for row in planning.trip_rows], [None])

    def test_a_trip_that_is_gone_is_not_charged(self) -> None:
        """Review finding 1: neither the kilometres nor the trailer surcharge of a trip that is not there."""
        self.trailer.only_trip_days = True
        self.trailer.save()
        self.drive(self.there, trailer=True, planned_km=Decimal("100"))
        self.drive(self.back, planned_km=Decimal("50"))
        self.assertEqual(self.price_of(self.car).amount, Decimal("140.00"))  # 100 × 1.00 + 50 × 0.80
        TripAdjustment.objects.create(project=self.project, trip_key=self.there, is_removed=True)
        car, trailer = self.price_of(self.car), self.price_of(self.trailer)
        self.assertEqual((car.amount, car.km_total), (Decimal("40.00"), Decimal("50")))
        self.assertEqual((trailer.days, trailer.amount), (0, Decimal("0.00")))
        # Every way to the figures agrees: the list's sums load the trips of many projects at once.
        self.assertEqual(_prices_of([self.project])[self.project.pk][0].logistics_total, self.prices().logistics_total)
        content = content_builder.build_priced(
            self.project, DocumentKind.OFFER, title="Angebot", number="AN-1", issued_on=datetime.date(2027, 3, 1)
        )
        car_position = next(section for section in content.sections if section.title == "Logistik").positions[0]
        self.assertEqual((car_position.quantity, car_position.amount), (Decimal("50"), Decimal("40.00")))
        self.assertNotIn("100 km", car_position.details)
        planning = build_planning(self.project)
        gone = next(row for row in planning.trip_rows if row.key == self.there)
        self.assertEqual(gone.uses[0].amount, Decimal("0"))


class VehicleRevenueTests(LogisticsCase):
    """Review: what a vehicle earned – item, model and the tab "Material" of the reports (MAT-053, MAT-058)."""

    def test_bookings_earn_for_the_vehicle(self) -> None:
        from rentalars.projects.profitability import item_revenue, model_revenue, product_report

        self.drive(self.there, trailer=True, planned_km=Decimal("100"))
        self.assertEqual(item_revenue(self.fleet["van"]).total, Decimal("0.00"))  # not out yet
        projects = type(self.project).objects
        projects.filter(pk=self.project.pk).update(status=ProjectStatus.RETURNED)
        car, trailer = self.price_of(self.car).amount, self.price_of(self.trailer).amount
        revenue = item_revenue(self.fleet["van"])
        self.assertEqual((revenue.direct, revenue.projects), (car, 1))
        self.assertEqual(model_revenue(self.fleet["box"].material_model).total, trailer)
        # An open booking of the product is shared over its vehicles, as pieces of material without an item.
        other = make_project("Hafenfest", start=at(20), end=at(21), status=ProjectStatus.RETURNED)
        open_booking = logistics.add_vehicle_line(other, rights=ALL_RIGHTS, product=self.fleet["trailer"])
        projects.filter(pk=other.pk).update(status=ProjectStatus.RETURNED)
        shared = next(price for price in compute_project_prices(other).logistics if price.line.pk == open_booking.pk)
        self.assertEqual(item_revenue(self.fleet["box"]).estimated, shared.amount)
        rows = {row.product.pk: row.revenue for row in product_report()}
        self.assertEqual(rows.get(self.fleet["car"].pk), car)
        self.assertEqual(rows.get(self.fleet["trailer"].pk), trailer + shared.amount)


class TripKeysTests(LogisticsCase):
    """``trips.trip_keys_of`` names the trips as ``trips_of`` does – for the prices of many projects at once."""

    def test_the_same_keys(self) -> None:
        from rentalars.projects.trips import trip_keys_of, trips_of

        other = make_project("Weinfest")
        course.add_phase(other, kind=PhaseKind.TEARDOWN, start=at(12, 10), end=at(12, 18))
        course.add_phase(other, kind=PhaseKind.LOADING, start=at(10, 6), end=at(10, 8))
        TripAdjustment.objects.create(project=self.project, trip_key=self.back, is_removed=True)
        TripAdjustment.objects.create(project=self.project, trip_key="", title="Nachlieferung", start=at(11, 9))
        keys = trip_keys_of([self.project.pk, other.pk])
        for project in (self.project, other):
            self.assertEqual(keys[project.pk], {trip.key for trip in trips_of(project)})


class PlanningPageTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fleet = make_fleet()
        self.project = make_project("Stadtfest")
        self.phase = course.add_phase(
            self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16), location="Marktplatz 1, Musterstadt"
        )

    def test_book_edit_and_put_on_a_trip(self) -> None:
        detail = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("planning-logistics", detail)
        self.assertIn("Noch kein Fahrzeug gebucht", detail)
        response = self.htmx(
            "post",
            reverse("projects:vehicle_add", args=[self.project.pk]),
            {"vehicle": f"item-{self.fleet['van'].pk}", "start": "", "end": ""},
        )
        self.assertEqual(response.status_code, 200)
        line = self.project.vehicle_lines.get()
        self.assertEqual(line.item, self.fleet["van"])
        self.assertIn("planning-logistics", response.content.decode())
        # The dialog of the booking.
        url = reverse("projects:vehicle_edit", args=[self.project.pk, line.pk])
        dialog = self.htmx("get", url)
        self.assertIn("Anhängerzuschlag", self.assert_ok(dialog))
        response = self.htmx("post", url, form_data(dialog, title="Sprinter weiß", price_per_km="0,90"))
        self.assertEqual(response.status_code, 200, response.content.decode()[:500])
        self.assertNotIn("errorlist", response.content.decode())
        line.refresh_from_db()
        self.assertEqual((line.title, line.price_per_km), ("Sprinter weiß", Decimal("0.90")))
        # A vehicle on the trip to the setup.
        key = f"to_venue-{self.phase.pk}"
        add_url = reverse("projects:trip_vehicle_add", args=[self.project.pk]) + f"?trip={key}"
        dialog = self.htmx("get", add_url)
        self.assertIn("Geplante km", self.assert_ok(dialog))
        response = self.htmx("post", add_url, form_data(dialog, planned_km="42"))
        self.assertEqual(response.status_code, 200, response.content.decode()[:500])
        use = self.project.trip_vehicles.get()
        self.assertEqual((use.trip_key, use.planned_km), (key, Decimal("42")))
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Zwischensumme Logistik", page)
        self.assertIn("37,80", page)  # 42 km × 0.90, an estimate
        # Take it off and remove the booking.
        self.htmx("post", reverse("projects:trip_vehicle_delete", args=[self.project.pk, use.pk]))
        self.assertFalse(self.project.trip_vehicles.exists())
        self.htmx("post", reverse("projects:vehicle_delete", args=[self.project.pk, line.pk]))
        self.assertFalse(self.project.vehicle_lines.exists())

    def test_crew_with_a_vehicle(self) -> None:
        line = logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=self.fleet["car"])
        crew_line = plan(self.project, "Stagehand", make_person("Anna"))
        url = reverse("projects:crew_edit", args=[self.project.pk, crew_line.pk])
        self.assertIn("Fährt das Fahrzeug", self.assert_ok(self.htmx("get", url)))
        crew_line.vehicle_line = line
        crew_line.is_driver = True
        crew_line.save()
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Fahrer", page)

    def test_only_who_may_plan(self) -> None:
        Role.objects.create(name="Nur lesen", module_levels={"projects": 1})
        browser = self.browser_for("lea", "Nur lesen")
        response = browser.post(
            reverse("projects:vehicle_add", args=[self.project.pk]),
            {"vehicle": f"item-{self.fleet['van'].pk}"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 403)
        page = self.assert_ok(browser.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertNotIn(reverse("projects:vehicle_add", args=[self.project.pk]), page)

    def test_without_fleet_a_hint(self) -> None:
        other = make_project("Hafenfest")
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[other.pk])))
        self.assertIn("planning-logistics", page)


class LogisticsApiTests(ApiTestCase):
    """LOG-015: the logistics of a project over the API – every operation (API-014)."""

    def setUp(self) -> None:
        super().setUp()
        self.fleet = make_fleet()
        self.project = make_project("Stadtfest")
        phase = course.add_phase(
            self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16), location="Marktplatz 1, Musterstadt"
        )
        self.key = f"to_venue-{phase.pk}"
        self.base = f"{API}/projects/{self.project.pk}"

    def test_bookings(self) -> None:
        response = self.admin.post(
            f"{self.base}/logistics", {"item": self.fleet["van"].pk, "note": "Weiß"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.json())
        booking = response.json()
        self.assertEqual((booking["vehicle_type"], booking["label"]), ("car", "Sprinter (B-RL 100)"))
        self.assertEqual(booking["price_per_km"], "0.80")
        self.assertIn("cost_per_km", booking)
        url = f"{self.base}/logistics/{booking['id']}"
        self.assertEqual(self.admin.get(url).json()["note"], "Weiß")
        response = self.admin.patch(url, {"price_per_km": "0.95"}, format="json")
        self.assertEqual(response.json()["price_per_km"], "0.95")
        response = self.admin.put(url, {"title": "Sprinter weiß"}, format="json")
        self.assertEqual(response.json()["title"], "Sprinter weiß")
        listed = self.admin.get(f"{self.base}/logistics").json()
        self.assertEqual([item["id"] for item in listed], [booking["id"]])
        # An open trailer of the product, without a vehicle.
        response = self.admin.post(f"{self.base}/logistics", {"product": self.fleet["trailer"].pk}, format="json")
        self.assertEqual((response.status_code, response.json()["is_open"]), (201, True))
        self.assertEqual(self.admin.delete(url).status_code, 204)
        self.assertFalse(self.project.vehicle_lines.filter(pk=booking["id"]).exists())

    def test_vehicles_on_trips(self) -> None:
        car = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["car"], item=self.fleet["van"]
        )
        trailer = logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=self.fleet["trailer"])
        response = self.admin.post(
            f"{self.base}/trips/{self.key}/vehicles",
            {"vehicle_line": car.pk, "trailer_line": trailer.pk, "planned_km": "100"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())
        use = response.json()
        self.assertEqual((use["charged_km"], use["km_is_estimate"], use["billing"]), ("100.0", True, "driven"))
        self.assertEqual(len(self.admin.get(f"{self.base}/trips/{self.key}/vehicles").json()), 1)
        url = f"{self.base}/trip-vehicles/{use['id']}"
        self.assertEqual(self.admin.get(url).json()["trailer_line"], trailer.pk)
        self.assertEqual(self.admin.patch(url, {"driven_km": "120"}, format="json").json()["charged_km"], "120.0")
        response = self.admin.put(url, {"billing": "flat", "flat_price": "150"}, format="json")
        self.assertEqual(response.json()["flat_price"], "150.00")
        booking = self.admin.get(f"{self.base}/logistics/{car.pk}").json()
        self.assertEqual(booking["amount"], "150.00")
        self.assertEqual(booking["trips"][0]["km_source"], "flat")
        planning = self.admin.get(f"{API}/projects/{self.project.pk}/planning").json()
        self.assertEqual(len(planning["logistics"]), 2)
        amounts = sum(Decimal(item["amount"]) for item in planning["logistics"])
        self.assertEqual(Decimal(planning["totals"]["logistics_total"]), amounts)
        self.assertEqual(self.admin.delete(url).status_code, 204)

    def test_own_deployments_name_the_vehicle(self) -> None:
        """LOG-008: the app's "My deployments" says which vehicle a person travels with – without its supplier."""
        line = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["car"], item=self.fleet["van"]
        )
        user = make_user("bob", roles=("Crew",))
        plan(self.project, "Fahrer", make_person("Bob Baumann", user=user), vehicle_line=line, is_driver=True)
        (row,) = self.client_of(user).get(f"{API}/people/me/deployments").json()
        self.assertEqual((row["vehicle"], row["is_driver"]), ("Sprinter (B-RL 100)", True))

    def test_a_packing_list_loaded_into_a_vehicle(self) -> None:
        """Review finding 3: a new packing list may name its vehicle – one of this project only."""
        line = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=self.fleet["car"], item=self.fleet["van"]
        )
        response = self.admin.post(
            f"{self.base}/packlists", {"title": "Sprinter", "vehicle_line": line.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.project.packlists.get(title="Sprinter").vehicle_line, line)
        elsewhere = logistics.add_vehicle_line(make_project("Hafenfest"), rights=ALL_RIGHTS, product=self.fleet["car"])
        response = self.admin.post(
            f"{self.base}/packlists", {"title": "LKW", "vehicle_line": elsewhere.pk}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_route_without_a_service(self) -> None:
        response = self.admin.get(f"{self.base}/trips/{self.key}/route")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.admin.get(f"{self.base}/trips/nowhere/route").status_code, 404)

    def test_rights(self) -> None:
        line = logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=self.fleet["car"])
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.client_for("pia", "Planung ohne Preise")
        booking = planner.get(f"{self.base}/logistics/{line.pk}").json()
        self.assertNotIn("price_per_km", booking)
        self.assertNotIn("cost_per_km", booking)
        response = planner.patch(f"{self.base}/logistics/{line.pk}", {"price_per_km": "2"}, format="json")
        self.assertEqual(response.status_code, 400)
        Role.objects.create(name="Lesen", module_levels={"projects": 1})
        reader = self.client_for("lea", "Lesen")
        self.assertEqual(reader.get(f"{self.base}/logistics").status_code, 200)
        self.assertEqual(reader.delete(f"{self.base}/logistics/{line.pk}").status_code, 403)
        # Review finding 6: the route suggestion only for who may plan, as in the browser.
        self.assertEqual(reader.get(f"{self.base}/trips/{self.key}/route").status_code, 403)


class DocumentTests(LogisticsCase):
    """LOG-011: offer, order confirmation and invoice show the logistics as a section of their own."""

    def setUp(self) -> None:
        super().setUp()
        ready_for_invoices(self.project.customer)
        self.drive(self.there, trailer=True, planned_km=Decimal("100"), driven_km=Decimal("100"))
        self.drive(self.back, planned_km=Decimal("100"), driven_km=Decimal("110"))
        logistics.update_vehicle_line(self.car, rights=ALL_RIGHTS, discount_percent=Decimal("10"))

    def test_the_section_with_kilometres_and_rates(self) -> None:
        content = content_builder.build_priced(
            self.project, DocumentKind.OFFER, title="Angebot", number="AN-1", issued_on=datetime.date(2027, 3, 1)
        )
        section = next(section for section in content.sections if section.title == "Logistik")
        car, trailer = section.positions
        self.assertEqual((car.quantity, car.unit, car.unit_code), (Decimal("210"), "km", "KMT"))
        self.assertEqual(
            (car.base_amount, car.discount_amount, car.amount), (Decimal("188.00"), Decimal("18.80"), Decimal("169.20"))
        )
        self.assertIn("100 km à 1,00 €", car.details)
        self.assertIn("Anhängerzuschlag 0,20 €", car.details)
        # Review finding 8: two rates – no unit price that would not multiply out (188 / 210 km).
        self.assertIsNone(car.unit_price)
        self.assertEqual(trailer.unit_code, "DAY")
        self.assertEqual(section.subtotal, compute_project_prices(self.project).logistics_total)

    def test_invoice_and_xrechnung_add_up(self) -> None:
        import xml.etree.ElementTree as ET

        from rentalars.documents.xrechnung import NAMESPACES

        invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        prices = compute_project_prices(self.project)
        self.assertEqual(invoice.net_total, prices.net_total)
        root = ET.fromstring(invoice.xml_file.read())
        cac, cbc = "{" + NAMESPACES["cac"] + "}", "{" + NAMESPACES["cbc"] + "}"
        lines = [Decimal(element.find(f"{cbc}LineExtensionAmount").text) for element in root.iter(f"{cac}InvoiceLine")]
        self.assertEqual(sum(lines), prices.net_total)
        self.assertIn('unitCode="KMT"', ET.tostring(root, encoding="unicode"))

    def test_crew_sheet_names_the_vehicle(self) -> None:
        driver = make_person("Erik")
        plan(self.project, "Fahrer", driver, vehicle_line=self.car, is_driver=True)
        content = content_builder.build_crew_sheet(
            self.project, title="Crew", number="CD-1", issued_on=datetime.date(2027, 3, 1)
        )
        self.assertEqual(content.crew_rows[0].vehicle, "Sprinter (B-RL 100), Fahrer")

    def test_the_crew_does_not_see_the_supplier(self) -> None:
        """Review: a rented van is named by its title for the crew; the supplier stays with the planners."""
        rented = logistics.add_vehicle_line(
            self.project,
            rights=ALL_RIGHTS,
            product=self.fleet["car"],
            supplier=Supplier.objects.create(name="Vanmiete"),
        )
        self.assertEqual((rented.label, rented.crew_label), ("Sprinter (Vanmiete)", "Sprinter"))
        plan(self.project, "Fahrer", make_person("Erik"), vehicle_line=rented)
        content = content_builder.build_crew_sheet(
            self.project, title="Crew", number="CD-1", issued_on=datetime.date(2027, 3, 1)
        )
        self.assertEqual(content.crew_rows[0].vehicle, "Sprinter")


class PriceOverviewTests(UiTestCase):
    """LOG-009: the logistics as a block of its own in the price overview, its PDF and CSV."""

    def setUp(self) -> None:
        super().setUp()
        fleet = make_fleet()
        self.project = make_project("Stadtfest")
        phase = course.add_phase(
            self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16), location="Marktplatz 1, Musterstadt"
        )
        car = logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=fleet["car"], item=fleet["van"])
        logistics.add_trip_vehicle(
            self.project, rights=ALL_RIGHTS, trip_key=f"to_venue-{phase.pk}", vehicle_line=car, driven_km=Decimal("50")
        )

    def test_page_pdf_and_csv(self) -> None:
        page = self.assert_ok(
            self.client.get(reverse("projects:price_overview", args=[self.project.pk]) + "?detail=lines")
        )
        self.assertIn("data-price-logistics", page)
        self.assertIn("Sprinter (B-RL 100)", page)
        self.assertIn("40,00", page)  # 50 km × 0.80
        groups = self.assert_ok(
            self.client.get(reverse("projects:price_overview", args=[self.project.pk]) + "?detail=groups")
        )
        self.assertIn("Logistik", groups)
        csv = self.client.get(reverse("projects:price_overview_csv", args=[self.project.pk]) + "?detail=lines")
        self.assertIn("Logistik", csv.content.decode("utf-8-sig"))
        pdf = self.client.get(reverse("projects:price_overview_pdf", args=[self.project.pk]) + "?detail=lines")
        self.assertEqual(pdf.status_code, 200)
