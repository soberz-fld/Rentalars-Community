# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "services": service products 1:1 with job functions (PRD-044), incidental costs (PRD-045),
hour tiers per day (PER-035), crew lines by effort (PER-036), the start data of job functions (PER-037)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.masterdata.models import Category
from rentalars.personnel import services as personnel
from rentalars.personnel.defaults import JOB_FUNCTIONS
from rentalars.personnel.models import JobFunction
from rentalars.products.models import BillingMode, KitComponent, Product, ProductKind
from rentalars.products.services import presets_for_category, save_product
from rentalars.projects import crew, hour_tiers, lines
from rentalars.projects.list_sums import attach_sums
from rentalars.projects.models import CrewBilling, CrewLine
from rentalars.projects.mvr import NOT_EQUIPMENT
from rentalars.projects.services import add_line as plan_material
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    add_line_before_071,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    record_time,
)

D = Decimal


def service(article_number: str, name: str, price: str | None = "45.00", **fields: object) -> Product:
    """A service product saved the way the product form saves it – with its job function (PRD-044)."""
    product = Product(
        article_number=article_number,
        name=name,
        category=Category.objects.get(parent__isnull=True, code="D"),
        unit=presets_for_category(Category.objects.get(parent__isnull=True, code="D"))["unit"],
        tax_rate=presets_for_category(Category.objects.get(parent__isnull=True, code="D"))["tax_rate"],
        kind=ProductKind.SERVICE,
        billing_mode=fields.pop("billing_mode", BillingMode.HOURLY),
        price=D(price) if price is not None else None,
        **fields,
    )
    return save_product(product, ALL_RIGHTS)


class StartDataTests(RentalarsTestCase):
    """PER-037: the job functions of a new installation, each with its service product."""

    def test_the_eight_functions_with_their_service_products(self) -> None:
        functions = list(JobFunction.objects.select_related("service_product__category", "service_product__unit"))
        self.assertEqual(sorted(function.name for function in functions), sorted(JOB_FUNCTIONS))
        for function in functions:
            product = function.service_product
            self.assertEqual((product.name, product.kind), (function.name, ProductKind.SERVICE))
            self.assertEqual((product.category.code, product.unit.name), ("D", "Stunde"))
            self.assertEqual((product.price, product.billing_mode), (None, BillingMode.HOURLY))
        self.assertEqual(
            sorted(product.article_number for product in Product.objects.filter(kind=ProductKind.SERVICE)),
            [f"D-00{number}" for number in range(1, 9)],
        )

    def test_the_main_category_of_incidental_costs(self) -> None:
        """PRD-045: N "Nebenkosten" presets the kind and "Pauschal"."""
        category = Category.objects.get(parent__isnull=True, code="N")
        presets = presets_for_category(category)
        self.assertEqual((category.name, category.has_own_stock), ("Nebenkosten", False))
        self.assertEqual(
            (presets["kind"], presets["unit"].name, presets["billing_mode"]), ("incidental", "Pauschal", "flat")
        )


class OneToOneTests(RentalarsTestCase):
    """PRD-044: one service product per job function, one job function per service product."""

    def test_a_new_function_brings_its_service_product(self) -> None:
        function = personnel.save_job_function(JobFunction(name="Pyrotechnik"), price=D("60.00"))
        product = function.service_product
        self.assertEqual((product.name, product.price, product.kind), ("Pyrotechnik", D("60.00"), "service"))
        self.assertEqual(product.article_number, "D-009")
        # Saved without the service layer too – e.g. by an import or a script.
        bare = JobFunction.objects.create(name="Rigger")
        self.assertEqual((bare.service_product.name, bare.service_product.price), ("Rigger", None))

    def test_renaming_the_function_renames_a_product_of_the_same_name(self) -> None:
        function = JobFunction.objects.get(name="Lager")
        function.name = "Lager und Logistik"
        personnel.save_job_function(function)
        product = Product.objects.get(pk=function.service_product_id)
        self.assertEqual(product.name, "Lager und Logistik")
        # Named apart ("Lagerarbeit, Stunde"): each keeps its own name.
        Product.objects.filter(pk=product.pk).update(name="Lagerarbeit, Stunde")
        function = JobFunction.objects.get(pk=function.pk)
        function.name = "Logistik"
        personnel.save_job_function(function)
        self.assertEqual(Product.objects.get(pk=product.pk).name, "Lagerarbeit, Stunde")
        product = Product.objects.get(pk=product.pk)
        product.name = "Logistik, Stunde"
        save_product(product, ALL_RIGHTS)
        self.assertEqual(JobFunction.objects.get(pk=function.pk).name, "Logistik")

    def test_a_new_service_product_brings_its_function(self) -> None:
        product = service("D-020", "Bühnenmeister")
        function = JobFunction.objects.get(name="Bühnenmeister")
        self.assertEqual(function.service_product, product)
        product.name = "Bühnenmeisterei"
        save_product(product, ALL_RIGHTS)
        self.assertEqual(JobFunction.objects.get(pk=function.pk).name, "Bühnenmeisterei")

    def test_a_service_named_like_another_function_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            service("D-020", "tontechniker")
        self.assertIn("name", raised.exception.message_dict)
        self.assertFalse(Product.objects.filter(article_number="D-020").exists())
        with self.assertRaises(ValidationError) as raised:
            service("D-021", "X" * 81)
        self.assertIn("name", raised.exception.message_dict)

    def test_a_product_becomes_a_service_with_its_function(self) -> None:
        product = make_product("N-001", "Fahrerdienst", kind="incidental", billing_mode="flat")
        product.kind, product.billing_mode = ProductKind.SERVICE, BillingMode.HOURLY
        save_product(product, ALL_RIGHTS)
        self.assertEqual(JobFunction.objects.get(name="Fahrerdienst").service_product, product)

    def test_the_product_of_a_function_stays_a_service(self) -> None:
        product = JobFunction.objects.get(name="Stagehand").service_product
        product.kind, product.price = ProductKind.INCIDENTAL, D("10.00")
        with self.assertRaises(ValidationError) as raised:
            product.full_clean()
        self.assertIn("kind", raised.exception.message_dict)

    def test_two_functions_cannot_share_a_product(self) -> None:
        stagehand = JobFunction.objects.get(name="Stagehand")
        other = JobFunction.objects.get(name="Lager")
        other.service_product = stagehand.service_product
        with self.assertRaises(ValidationError) as raised:
            other.full_clean()
        self.assertIn("service_product", raised.exception.message_dict)

    def test_deleting_the_function_deletes_its_product_unless_in_use(self) -> None:
        function = personnel.save_job_function(JobFunction(name="Pyrotechnik"))
        product_id = function.service_product_id
        personnel.delete_job_function(function)
        self.assertFalse(Product.objects.filter(pk=product_id).exists())
        used = personnel.save_job_function(JobFunction(name="Feuerwache"))
        plan(make_project(), used)
        with self.assertRaises(ValidationError):
            personnel.delete_job_function(JobFunction.objects.get(pk=used.pk))
        self.assertTrue(Product.objects.filter(pk=used.service_product_id).exists())

    def test_a_crew_line_takes_product_price_unit_tax_and_tiers(self) -> None:
        function = job_function("Tontechnik", price="45.00")
        product = function.service_product
        product.hours_limit, product.price_above_limit = D("10"), D("55.00")
        product.save()
        line = plan(make_project(), JobFunction.objects.get(pk=function.pk))
        self.assertEqual(line.service_product, product)
        self.assertEqual(
            (line.title, line.unit_price, line.tax_rate), ("Tontechnik, Stunde", D("45.00"), product.tax_rate)
        )
        self.assertEqual((line.hours_limit, line.unit_price_above_limit), (D("10"), D("55.00")))

    def test_a_function_whose_product_has_no_price_yet_plans_at_zero(self) -> None:
        line = plan(make_project(), JobFunction.objects.get(name="Techniker"))
        self.assertEqual((line.unit_price, line.list_price, line.billing), (D("0"), None, CrewBilling.EFFORT))


class NotAsMaterialTests(RentalarsTestCase):
    """PRD-044: a service is planned only in the crew planning; old material lines of services stay."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.engineer = job_function("Tontechnik", price="45.00").service_product

    def test_adding_a_service_as_material_is_refused_with_its_function(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            add_line(self.project, self.engineer, 2)
        message = " ".join(raised.exception.message_dict["product"])
        self.assertIn("Tontechnik", message)
        self.assertIn("Personal", message)
        self.assertFalse(self.project.material_lines.exists())

    def test_an_old_material_line_of_a_service_stays_and_is_priced(self) -> None:
        line = add_line_before_071(self.project, self.engineer, 2).line
        line.refresh_from_db()
        from rentalars.projects.pricing import compute_project_prices

        self.assertEqual(compute_project_prices(self.project).by_line_id[line.pk].amount, D("90.00"))
        # It can be changed, but not multiplied.
        from rentalars.projects.services import update_line

        update_line(line, rights=ALL_RIGHTS, quantity=D("3"))
        with self.assertRaises(ValidationError):
            lines.duplicate_line(line, rights=ALL_RIGHTS)

    def test_copies_and_templates_leave_old_service_lines_out(self) -> None:
        from rentalars.projects.duplicate import duplicate_project
        from rentalars.projects.project_templates import apply_template, save_as_template

        add_line_before_071(self.project, self.engineer, 2)
        transport = make_product("N-001", "Transport", price="95.00", kind="incidental", billing_mode="flat")
        add_line(self.project, transport, 1)
        copy = duplicate_project(
            self.project, rights=ALL_RIGHTS, user=None, name="Kopie", start=at(20, 8), end=at(22, 18)
        )
        self.assertEqual([line.product for line in copy.material_lines.all()], [transport])
        template = save_as_template(self.project, rights=ALL_RIGHTS, name="Vorlage")
        target = make_project("Neu", start=at(20), end=at(21))
        result = apply_template(template, target, rights=ALL_RIGHTS)
        self.assertEqual([line.product for line in target.material_lines.all()], [transport])
        self.assertTrue(any("Personal" in text for text in result.left_out), result.left_out)

    def test_a_kit_takes_no_service(self) -> None:
        kit = make_product("T-100", "Set", kind="kit", billing_mode="daily_kit")
        component = KitComponent(kit=kit, component=self.engineer, quantity=1)
        with self.assertRaises(ValidationError):
            component.full_clean()

    def test_the_lighting_plot_offers_no_service_and_no_incidental_costs(self) -> None:
        self.assertIn(ProductKind.SERVICE, NOT_EQUIPMENT)
        self.assertIn(ProductKind.INCIDENTAL, NOT_EQUIPMENT)


class IncidentalCostsTests(RentalarsTestCase):
    """PRD-045: incidental costs – no stock, not packed, planned like material, billed flat."""

    def test_planned_like_material_without_stock_and_not_packed(self) -> None:
        from rentalars.packing.services import PACKABLE_KINDS

        transport = make_product("N-001", "Transport Sprinter", price="95.00", kind="incidental", billing_mode="flat")
        self.assertFalse(transport.tracks_stock)
        self.assertNotIn(ProductKind.INCIDENTAL, PACKABLE_KINDS)
        result = plan_material(make_project(), rights=ALL_RIGHTS, product=transport, quantity=D("2"))
        self.assertEqual(result.availability.status, "unchecked")
        self.assertEqual((result.line.billing_mode, result.line.unit_price), ("flat", D("95.00")))

    def test_the_product_search_leaves_services_out_of_the_planning(self) -> None:
        from django.test import Client

        job_function("Tontechnik", price="45.00")
        make_product("N-001", "Transport Sprinter", price="95.00", kind="incidental", billing_mode="flat")
        client = Client()
        client.force_login(make_user("paula", superuser=True))
        found = client.get("/products/suggest/", {"q": "t", "exclude_kind": "service"}).json()
        labels = [row["label"] for row in found]
        self.assertIn("N-001 Transport Sprinter", labels)
        self.assertFalse([label for label in labels if label.startswith("D-")], labels)


class HourTierArithmeticTests(RentalarsTestCase):
    """PER-035: the hours of a day, split at the limit."""

    def test_the_planned_hours_per_calendar_day(self) -> None:
        # The suggested hours: as they fall on each day – Monday 08:00 to Tuesday 20:00 is 16 and 20.
        self.assertEqual(hour_tiers.planned_hours_per_day(at(8, 8), at(9, 20), D("36"), D("36")), [D("16"), D("20")])
        # Typed in by hand: spread evenly over the days the period touches.
        self.assertEqual(hour_tiers.planned_hours_per_day(at(8, 8), at(9, 20), D("20"), D("36")), [D("10"), D("10")])
        self.assertEqual(hour_tiers.planned_hours_per_day(at(8, 8), at(8, 20), D("12"), D("12")), [D("12")])

    def test_the_split_at_the_limit(self) -> None:
        split = hour_tiers.split_at_limit([D("12"), D("8"), D("11")], D("10"))
        self.assertEqual((split.normal, split.above, split.total), (D("28"), D("3"), D("31")))
        self.assertEqual(hour_tiers.split_at_limit([D("12")], None).above, D("0"))

    def test_approved_times_cost_the_rate_from_the_limit_beyond_it(self) -> None:
        day = at(10).date()
        entries = [(day, D("6"), D("30.00")), (day, D("6"), D("30.00")), (at(11).date(), D("4"), D("30.00"))]
        self.assertEqual(hour_tiers.actual_cost_with_limit(entries, D("10"), D("40.00")), D("500.00"))
        self.assertEqual(hour_tiers.actual_cost_with_limit(entries, D("10"), None), D("480.00"))


class HourTierPriceTests(RentalarsTestCase):
    """PER-035: from the limit of a day on, an hour costs the higher price and the higher rate."""

    def setUp(self) -> None:
        super().setUp()
        self.function = job_function("Tontechnik", price="45.00", guide="30.00")
        product = self.function.service_product
        product.hours_limit, product.price_above_limit = D("10"), D("55.00")
        product.save()
        self.function.guide_cost_rate_above_limit = D("36.00")
        self.function.save()
        self.project = make_project()

    def test_by_plan_twelve_hours_on_one_day(self) -> None:
        anna = make_person("Anna Becker")
        personnel.set_rate(anna, self.function, D("35.00"), at(1).date(), hourly_rate_above_limit=D("42.00"))
        line = plan(self.project, self.function, anna, start=at(10, 8), end=at(10, 20), billing=CrewBilling.PLAN)
        price = crew.price_crew_line(line)
        self.assertEqual((price.charged_hours, price.hours_above_limit, price.normal_hours), (D("12"), D("2"), D("10")))
        self.assertEqual(price.amount, D("560.00"))  # 10 × 45 + 2 × 55
        self.assertEqual(
            (price.cost, price.cost_hours_above_limit, price.cost_rate_above_limit), (D("434.00"), D("2"), D("42.00"))
        )
        self.assertFalse(price.is_estimate)

    def test_an_open_place_costs_the_guide_value_from_the_limit(self) -> None:
        line = plan(self.project, self.function, start=at(10, 8), end=at(10, 20))
        price = crew.price_crew_line(line)
        self.assertEqual((price.cost, price.cost_is_guide), (D("372.00"), True))  # 10 × 30 + 2 × 36

    def test_a_person_without_own_rate_from_the_limit_costs_the_own_hourly_rate(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        line = plan(self.project, self.function, anna, start=at(10, 8), end=at(10, 20))
        self.assertEqual(crew.price_crew_line(line).cost, D("420.00"))

    def test_two_days_of_the_period_count_each(self) -> None:
        line = plan(self.project, self.function, start=at(10, 8), end=at(11, 20))  # 16 h and 20 h
        price = crew.price_crew_line(line)
        self.assertEqual((price.hours_above_limit, price.amount), (D("16"), D("1780.00")))  # 20 × 45 + 16 × 55

    def test_by_effort_the_approved_times_per_day(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        line = plan(self.project, self.function, anna, start=at(10, 8), end=at(11, 20))
        self.assertEqual(line.billing, CrewBilling.EFFORT)
        record_time(anna, self.project, self.function, at(10, 8), at(10, 19), approve=True)  # 11 h
        record_time(anna, self.project, self.function, at(11, 8), at(11, 16), approve=True)  # 8 h
        price = crew.price_crew_lines(self.project)[0]
        self.assertEqual((price.charged_hours, price.hours_above_limit), (D("19"), D("1")))
        self.assertEqual(price.amount, D("865.00"))  # 18 × 45 + 1 × 55
        self.assertEqual(price.actual_cost, D("665.00"))  # 19 × 35 – no own rate from the limit
        self.assertFalse(price.is_estimate)

    def test_flat_and_per_day_know_no_limit(self) -> None:
        line = plan(
            self.project, self.function, start=at(10, 8), end=at(10, 22), billing=CrewBilling.FLAT, unit_price=D("300")
        )
        self.assertEqual(
            (crew.price_crew_line(line).amount, crew.price_crew_line(line).hours_above_limit), (D("300.00"), D("0"))
        )
        line = plan(
            self.project, self.function, start=at(10, 8), end=at(10, 22), billing=CrewBilling.DAY, unit_price=D("400")
        )
        self.assertEqual(crew.price_crew_line(line).amount, D("400.00"))

    def test_the_list_sums_split_too(self) -> None:
        plan(self.project, self.function, start=at(10, 8), end=at(10, 20), billing=CrewBilling.PLAN)
        user = make_user("paula", superuser=True)
        attach_sums([self.project], rights=ALL_RIGHTS, user=user)
        self.assertEqual(self.project.list_sums.personnel_revenue, D("560.00"))

    def test_a_limit_needs_its_price(self) -> None:
        line = plan(self.project, self.function)
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=ALL_RIGHTS, unit_price_above_limit=None)
        product = self.function.service_product
        product.price_above_limit = None
        with self.assertRaises(ValidationError):
            product.full_clean()
        transport = make_product("N-001", "Transport", price="95.00", kind="incidental", billing_mode="flat")
        transport.hours_limit, transport.price_above_limit = D("10"), D("1")
        with self.assertRaises(ValidationError):
            transport.full_clean()


class ByEffortTests(RentalarsTestCase):
    """PER-036: new crew lines of a service by the hour are billed by effort; flat and per day stay."""

    def test_the_billing_of_a_new_line(self) -> None:
        function = job_function("Tontechnik", price="45.00")
        project = make_project()
        self.assertEqual(plan(project, function).billing, CrewBilling.EFFORT)
        product = function.service_product
        for mode, expected in ((BillingMode.FLAT, CrewBilling.FLAT), (BillingMode.DAILY_PER_PIECE, CrewBilling.DAY)):
            product.billing_mode = mode
            product.save()
            self.assertEqual(plan(project, JobFunction.objects.get(pk=function.pk)).billing, expected)

    def test_a_line_keeps_its_billing(self) -> None:
        line = plan(make_project(), job_function("Tontechnik", price="45.00"), billing=CrewBilling.PLAN)
        crew.update_crew_line(line, rights=ALL_RIGHTS, planned_hours=D("5"))
        self.assertEqual(CrewLine.objects.get(pk=line.pk).billing, CrewBilling.PLAN)
