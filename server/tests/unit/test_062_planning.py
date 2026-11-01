# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning wishes: days 1 to 10, exact bars, start data, maximum discount per product.

* VFG-024 – the timeline and the personnel plan show 1 to 10 days in hour
  columns; the hour step keeps the headings readable.
* Bug – phases were drawn longer than they last: a bar filled every
  column it touched. Bars now carry the parts of their columns before and
  after the period.
* ADM-011 – the start data of a new installation, and the migration that
  adds what is missing to an installation that exists.
* PRD-041 – the maximum discount of a product limits every discount of its
  lines, as the maximum of a job function does (PER-026).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.test import RequestFactory

from rentalars.accounts.rights import Rights
from rentalars.masterdata import defaults
from rentalars.masterdata.models import Category, RentalScale, Unit
from rentalars.products.models import BillingMode, Product, ProductKind
from rentalars.products.tables import PRODUCT_TABLE
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.services import update_group, update_line
from rentalars.projects.summary import PIECE_UNITS
from rentalars.schedule import services
from rentalars.schedule.services import Bar, Scale
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    add_line_before_071,
    at,
    job_function,
    make_customer,
    make_product,
    make_project,
)
from tests.unit.test_stage5_imports import run

D = Decimal
NO_PRICES = Rights(module_levels={"products": 3}, special_rights=frozenset())


def scale_of(**query: str) -> tuple[Scale, dict]:
    return services.scale_from_request(RequestFactory().get("/schedule/timeline/", query))


# --- VFG-024: 1 to 10 days ---------------------------------------------------------------------


class DaysTests(RentalarsTestCase):
    """VFG-024: one to ten days in hour columns; at most 40 columns in view."""

    def test_the_hour_step_grows_with_the_days(self) -> None:
        steps = {days: services.hours_per_column(days) for days in range(1, 11)}
        self.assertEqual(steps, {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 6, 7: 6, 8: 6, 9: 6, 10: 6})
        for days, hours in steps.items():
            self.assertLessEqual(days * 24 // hours, services.MAX_VISIBLE_COLUMNS)
            self.assertEqual(24 % hours, 0)

    def test_ten_days_in_six_hour_columns_with_a_span_before_and_after(self) -> None:
        # VFG-033: two spans before and two after the chosen one.
        scale, navigation = scale_of(days="10", **{"from": "2027-03-10"})
        self.assertEqual((scale.hours, len(scale.days), scale.columns), (6, 50, 200))
        self.assertEqual((scale.focus, scale.visible, scale.per_day), (80, 40, 4))
        self.assertEqual(scale.days[0], datetime.date(2027, 2, 18))
        self.assertEqual(
            (navigation["first"], navigation["last"], navigation["zoom"], navigation["day_count"]),
            (datetime.date(2027, 3, 10), datetime.date(2027, 3, 19), 10, 10),
        )
        self.assertEqual((navigation["earlier"], navigation["later"]), (at(28, month=2).date(), at(20).date()))
        self.assertEqual(navigation["day_choices"], list(range(1, 11)))
        heads = scale.hour_heads
        self.assertEqual([head.label for head in heads[:5]], ["00", "06", "12", "18", "00"])
        self.assertEqual(heads[1].title, "Do 18.02., 06:00–12:00")
        bar = scale.bar(at(10, 8), at(10, 18), label="x")
        self.assertEqual((bar.first, bar.last), (82, 83))  # 06–12 and 12–18 of the 10th
        # 08:00 lies two hours into the column 06–12; 18:00 ends the column 12–18: no margin there.
        self.assertEqual(bar.style, "grid-column: 82 / 84; margin-left: calc(16.667% + 1px); --fill: 0.833")

    def test_four_and_seven_days(self) -> None:
        four, navigation = scale_of(days="4", **{"from": "2027-03-10"})
        self.assertEqual((four.hours, four.columns, four.focus, navigation["later"]), (3, 160, 64, at(14).date()))
        seven, _navigation = scale_of(days="7", **{"from": "2027-03-10"})
        self.assertEqual((seven.hours, seven.columns, seven.focus), (6, 140, 56))  # VFG-033: 5 spans

    def test_other_values_mean_weeks(self) -> None:
        for wrong in ("0", "11", "84", "-1", "drei"):
            with self.subTest(days=wrong):
                scale, navigation = scale_of(days=wrong, weeks="2", **{"from": "2027-03-08"})
                self.assertEqual((scale.hours, len(scale.days), navigation["zoom"]), (24, 14, 0))
                self.assertEqual(navigation["day_count"], services.DEFAULT_DAYS)


# --- Bug: bars as long as their periods ---------------------------------------------------


class ExactBarTests(RentalarsTestCase):
    """A bar covers the columns its period touches, cut to the exact start and end within them."""

    week = Scale(days=services.day_range(datetime.date(2027, 3, 8), 7))

    def test_a_phase_of_some_hours_in_a_day_column(self) -> None:
        bar = self.week.bar(at(10, 14), at(10, 20), label="Aufbau")
        self.assertEqual((bar.first, bar.last), (3, 3))
        self.assertAlmostEqual(bar.lead, 14 / 24)
        self.assertAlmostEqual(bar.trail, 4 / 24)

    def test_whole_days_keep_their_plain_columns(self) -> None:
        bar = self.week.bar(at(10), at(12), label="Messe")
        self.assertEqual((bar.first, bar.last, bar.lead, bar.trail), (3, 4, 0.0, 0.0))
        self.assertEqual(bar.style, "grid-column: 3 / 5")

    def test_what_lies_outside_the_days_is_cut_without_a_margin(self) -> None:
        bar = self.week.bar(at(5, 8), at(9, 12), label="Vorher")
        self.assertEqual((bar.first, bar.last, bar.lead), (1, 2, 0.0))
        self.assertAlmostEqual(bar.trail, 12 / 48)
        later = self.week.bar(at(14, 20), at(20, 8), label="Später")
        self.assertEqual((later.first, later.last, later.trail), (7, 7, 0.0))
        self.assertAlmostEqual(later.lead, 20 / 24)
        self.assertIsNone(self.week.bar(at(1), at(8), label="Vorbei"))  # ends where the days begin

    def test_the_day_the_clocks_change_follows_the_wall_clock(self) -> None:
        week = Scale(days=services.day_range(datetime.date(2027, 3, 22), 7))
        bar = week.bar(at(28, 1), at(28, 4), label="Nacht")  # 28 March 2027: 02:00 does not exist
        self.assertEqual((bar.first, bar.last), (7, 7))
        self.assertAlmostEqual(bar.lead, 1 / 24)
        self.assertAlmostEqual(bar.trail, 20 / 24)

    def test_the_style_names_columns_margins_and_fill(self) -> None:
        bar = Bar(first=3, last=3, label="x", lead=0.5, trail=0.25)
        self.assertEqual(
            bar.style,
            "grid-column: 3 / 4; margin-left: calc(50.000% + 1px); margin-right: calc(25.000% + 1px); --fill: 0.250",
        )

    def test_project_timeline_and_personnel_plan_use_the_exact_bars(self) -> None:
        from rentalars.projects.models import Project, ProjectPhase

        project = make_project("Stadtfest", start=at(10, 8), end=at(12, 22))
        ProjectPhase.objects.create(project=project, kind="setup", start=at(10, 8), end=at(10, 14))
        ((_shown, bars),) = services.project_timeline(Project.objects.all(), self.week)
        self.assertEqual([(bar.first, bar.last) for bar in bars], [(3, 5), (3, 3)])
        self.assertAlmostEqual(bars[0].trail, 2 / 72)
        self.assertAlmostEqual(bars[1].trail, 10 / 24)


# --- ADM-011: start data -----------------------------------------------------------------------


class StartDataTests(RentalarsTestCase):
    """ADM-011: what a new installation starts with."""

    def test_units(self) -> None:
        units = dict(Unit.objects.values_list("name", "abbreviation"))
        self.assertEqual(
            units,
            {
                "Stück (Verkauf)": "Stk.",
                "Stück (Miete)": "Stk.",
                "Set (Verkauf)": "Set",
                "Set (Miete)": "Set",
                "Stunde": "Std.",
                "Tag": "Tag",
                "Kilometer": "km",
                "Pauschal": "psch.",
                "Angefangener Liter": "l",
                "Angefangener Meter": "m",
                "Angefangenes Kilogramm": "kg",
            },
        )
        # The price summary counts both kinds of pieces in "8 ×".
        self.assertTrue({"Stück (Miete)", "Stück (Verkauf)"} <= PIECE_UNITS)

    def test_the_standard_scale(self) -> None:
        scale = RentalScale.objects.get(is_default=True)
        self.assertEqual(scale.name, "Standardstaffel")
        table = scale.current_version.as_table()
        factors = [table.factor_for(days) for days in range(1, 11)]
        self.assertEqual(
            factors, [D(text) for text in ("1", "1.5", "1.75", "2", "2.4", "2.75", "3.5", "3.8", "4.1", "4.4")]
        )
        self.assertEqual(table.extra_day_increment, D("0.300"))

    def test_main_categories_with_their_presets(self) -> None:
        main = {category.code: category for category in Category.objects.filter(parent__isnull=True)}
        self.assertEqual(
            {code: category.name for code, category in main.items()},
            {
                "T": "Ton",
                "L": "Licht",
                "M": "Video/Medien",
                "R": "Rigging/Traverse",
                "K": "Kabel",
                "V": "Verkauf",
                "E": "Extern zugemietetes Material",
                "D": "Veranstaltungstechnik-Dienstleistung",
                # PRD-043: the material customers keep here.
                "C": "Fremdmaterial",
                # PRD-045: transport, travel costs, fees.
                "N": "Nebenkosten",
                # LOG-002: vehicles and trailers of the fleet.
                "FZ": "Fuhrpark",
            },
        )
        presets = {
            code: (category.has_own_stock, category.default_product_kind, category.default_unit.name)
            for code, category in main.items()
        }
        self.assertEqual(presets["M"], (True, "rental", "Stück (Miete)"))
        self.assertEqual(presets["V"], (True, "sale", "Stück (Verkauf)"))
        # E and D keep their meaning: subrentals and services, without own stock.
        self.assertEqual(presets["E"], (False, "subrental", "Stück (Miete)"))
        self.assertEqual(presets["D"], (False, "service", "Stunde"))
        self.assertEqual(presets["N"], (False, "incidental", "Pauschal"))
        self.assertEqual(presets["FZ"], (True, "vehicle", "Stück (Miete)"))  # LOG-002
        self.assertEqual([field.label for field in main["K"].fields.all()], ["Länge"])

    def test_the_general_subrental_product_stays_in_e(self) -> None:
        """PRD-040: E-001 "Zumietung" behind the subrental suggestions."""
        product = Product.objects.get(kind=ProductKind.SUBRENTAL)
        self.assertEqual(
            (product.article_number, product.category.code, product.unit.name), ("E-001", "E", "Stück (Miete)")
        )

    def test_install_again_adds_nothing(self) -> None:
        counts = (Unit.objects.count(), Category.objects.count(), RentalScale.objects.count())
        defaults.install()
        self.assertEqual((Unit.objects.count(), Category.objects.count(), RentalScale.objects.count()), counts)


class ImportUnitTests(RentalarsTestCase):
    """ADM-011: a file that says "Stück" or "Stk." gets the piece the category presets."""

    def test_pieces_for_renting_and_for_selling(self) -> None:
        rows = [
            ["Art.-Nr.", "Name", "Einheit", "Preis", "Verkaufspreis"],
            ["T-010", "Aktivbox", "Stück", "35", ""],
            ["V-001", "Gaffa-Tape", "Stk.", "", "8,90"],
            ["K-005", "XLR-Kabel 5 m", "m", "1,50", ""],
            ["L-010", "PAR 64", "Stück (Verkauf)", "12", ""],
        ]
        report = run("products", rows)
        self.assertTrue(report.ok, report.errors)
        units = dict(
            Product.objects.filter(article_number__in=["T-010", "V-001", "K-005", "L-010"]).values_list(
                "article_number", "unit__name"
            )
        )
        self.assertEqual(
            units,
            {
                "T-010": "Stück (Miete)",
                "V-001": "Stück (Verkauf)",
                "K-005": "Angefangener Meter",
                "L-010": "Stück (Verkauf)",  # named in full: as written
            },
        )


# --- PRD-041: maximum discount per product ------------------------------------------------------


def flat(article_number: str, price: str, **fields: object) -> Product:
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT, **fields)


class ProductMaximumDiscountTests(RentalarsTestCase):
    """PRD-041: what PER-026 does for the lines of a job function, for the lines of any product."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.desk = add_line(self.project, flat("L-030", "400.00"), 1, group=self.group).line
        self.hazer = flat("L-050", "100.00", max_discount_percent=D("5"))
        self.hazer_line = add_line(self.project, self.hazer, 1, group=self.group).line

    def prices(self) -> object:
        return compute_project_prices(self.project)

    def test_own_discount_is_cut(self) -> None:
        update_line(self.hazer_line, rights=ALL_RIGHTS, discount_percent=D("10"))
        price = self.prices().by_line_id[self.hazer_line.pk]  # type: ignore[attr-defined]
        self.assertEqual(
            (price.discount_percent, price.amount, price.max_discount_percent), (D("5"), D("95.00"), D("5"))
        )
        self.assertTrue(price.discount_is_capped)
        self.assertEqual(self.prices().capped_discount_lines, 1)  # type: ignore[attr-defined]

    def test_customers_standard_discount_is_cut(self) -> None:
        customer = make_customer("Rabattkunde")
        customer.default_discount_percent = D("10")
        customer.save()
        project = make_project("Mit Rabatt", customer=customer)
        line = add_line(project, self.hazer, 1).line
        self.assertEqual(line.discount_percent, D("10"))  # stored as it came; a higher maximum brings it back
        self.assertEqual(compute_project_prices(project).by_line_id[line.pk].amount, D("95.00"))

    def test_share_of_the_group_discount_is_cut(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=D("10"))
        prices = self.prices()
        group = prices.groups[0]  # type: ignore[attr-defined]
        self.assertEqual((group.discount, group.cap_excess, group.subtotal), (D("45.00"), D("5.00"), D("455.00")))
        self.assertEqual(prices.by_line_id[self.hazer_line.pk].group_share, D("95.00"))  # type: ignore[attr-defined]

    def test_zero_means_never_and_empty_means_no_limit(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=D("10"))
        Product.objects.filter(pk=self.hazer.pk).update(max_discount_percent=D("0"))
        self.assertEqual(self.prices().groups[0].subtotal, D("460.00"))  # type: ignore[attr-defined]
        Product.objects.filter(pk=self.hazer.pk).update(max_discount_percent=None)
        self.assertEqual(self.prices().groups[0].subtotal, D("450.00"))  # type: ignore[attr-defined]

    def test_the_stricter_of_product_and_job_function_counts(self) -> None:
        sound = job_function("Tontechnik")
        engineer = sound.service_product  # PRD-044: every job function has its own
        engineer.price, engineer.billing_mode, engineer.max_discount_percent = D("100.00"), BillingMode.FLAT, D("8")
        engineer.save()
        sound.max_discount_percent = D("3")
        sound.save()
        line = add_line_before_071(self.project, engineer, 1, discount_percent=D("10")).line
        self.assertEqual(self.prices().by_line_id[line.pk].amount, D("97.00"))  # type: ignore[attr-defined]
        sound.max_discount_percent = D("9")
        sound.save()
        self.assertEqual(self.prices().by_line_id[line.pk].amount, D("92.00"))  # type: ignore[attr-defined]

    def test_no_query_more(self) -> None:
        update_line(self.hazer_line, rights=ALL_RIGHTS, discount_percent=D("10"))
        with self.assertNumQueries(len(self.queries_of_prices())):
            self.prices()

    def queries_of_prices(self) -> list[object]:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        Product.objects.filter(pk=self.hazer.pk).update(max_discount_percent=None)
        with CaptureQueriesContext(connection) as context:
            self.prices()
        Product.objects.filter(pk=self.hazer.pk).update(max_discount_percent=D("5"))
        return list(context.captured_queries)

    def test_the_value_is_checked_and_kept_from_people_without_the_price_right(self) -> None:
        from django.core.exceptions import ValidationError

        product = Product.objects.get(pk=self.hazer.pk)
        product.max_discount_percent = D("120")
        with self.assertRaises(ValidationError):
            product.full_clean()
        self.assertIn("max_discount_percent", Product.audit_sensitive)


class ProductMaximumDiscountListTests(RentalarsTestCase):
    """PRD-041: the column of the product list, its export and the import."""

    def test_column_and_csv(self) -> None:
        flat("L-050", "100.00", max_discount_percent=D("5"))
        flat("L-060", "100.00", max_discount_percent=D("0"))
        flat("L-070", "100.00")
        column = next(column for column in PRODUCT_TABLE.columns if column.key == "max_discount")
        self.assertFalse(column.default)
        products = {
            product.article_number: product for product in Product.objects.filter(article_number__startswith="L-")
        }
        self.assertEqual([column.cell(products[number]) for number in ("L-050", "L-060", "L-070")], ["5 %", "0 %", "–"])
        self.assertEqual(str(column.label), "Höchstrabatt")

    def test_import_of_the_exported_column(self) -> None:
        flat("L-050", "100.00", max_discount_percent=D("5"))
        rows = [
            ["Art.-Nr.", "Name", "Preis", "Höchstrabatt"],
            ["L-050", "Nebelmaschine", "100", ""],
            ["L-051", "Hazer", "40", "7,5"],
            ["L-052", "Fluter", "10", "0"],
        ]
        report = run("products", rows)
        self.assertTrue(report.ok, report.errors)
        values = dict(
            Product.objects.filter(article_number__in=["L-050", "L-051", "L-052"]).values_list(
                "article_number", "max_discount_percent"
            )
        )
        self.assertEqual(values, {"L-050": None, "L-051": D("7.50"), "L-052": D("0.00")})

    def test_import_checks_the_value_and_the_price_right(self) -> None:
        rows = [
            ["Art.-Nr.", "Name", "Preis", "Höchstrabatt"],
            ["L-051", "Hazer", "40", "120"],
            ["L-052", "Fluter", "10", "-3"],
        ]
        report = run("products", rows)
        self.assertEqual([issue.row for issue in report.errors], [2, 3])
        refused = run("products", [["Art.-Nr.", "Name", "Höchstrabatt"], ["L-051", "Hazer", "5"]], rights=NO_PRICES)
        self.assertFalse(refused.ok)
        self.assertFalse(Product.objects.filter(article_number="L-051").exists())
