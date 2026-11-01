# SPDX-License-Identifier: GPL-3.0-or-later
"""Depreciation and book value of assets, the Anlagenspiegel, the used sale from stock (Mit Restbuchwert). (MAT-086)

The requirement: transport costs of purchase invoices are spread as ancillary acquisition costs (per position
merchandise, GWG or fixed asset with a useful life), and the same for the used sale from stock. Scope: "Mit
Restbuchwert": linear
depreciation and the book value per item, the used sale of an item with gain or loss against the book value, and no DATEV
export for it.

* The pure functions (``material.depreciation``): month principle, leap years, partial year, a life of one month, a date
  known to the year only, a date in the future, huge amounts, cents that always add up exactly.
* The services: recording an item as asset, the Anlagenspiegel with its filters and sums, the sale from stock with its
  checks, its reversal, the history without amounts.
* The pages (card on the item, Anlagenspiegel, sale, sales list, reversal, draft of an invoice) and the API – every
  operation (API-014) – with the rights: nothing without the right to see purchase prices.
"""

from __future__ import annotations

import datetime
import random
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module
from rentalars.core.models import AuditLogEntry
from rentalars.masterdata.models import TaxRate
from rentalars.material import book_values, depreciation, partial_dates, sales
from rentalars.material.asset_models import AssetSettings
from rentalars.material.asset_tables import ASSET_TABLE, SALES_TABLE
from rentalars.material.history import item_history
from rentalars.material.installed_models import InstalledQuantity
from rentalars.material.models import AssetKind, ItemBlock, ItemStatus, MaterialItem
from rentalars.material.sale_models import SaleFromStock
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    PlainTestCase,
    RentalarsTestCase,
    at,
    make_customer,
    make_item,
    make_model,
    make_product,
    make_project,
    make_user,
)
from tests.ui.base import UiTestCase, form_data

D = Decimal
FIXED, LOW, MERCH = depreciation.KIND_FIXED_ASSET, depreciation.KIND_LOW_VALUE, depreciation.KIND_MERCHANDISE


def day(year: int, month: int, number: int = 1) -> datetime.date:
    """A date."""
    return datetime.date(year, month, number)


# --- The pure functions ------------------------------------------------------------------------------------------------


class MonthPrincipleTests(PlainTestCase):
    """The month of acquisition and the month of the day asked for count in full."""

    def value(self, acquired: datetime.date, as_of: datetime.date, *, cost: str = "1200", life: int = 12):
        return depreciation.valuation(FIXED, D(cost), acquired, life, as_of)

    def test_a_purchase_on_the_last_day_of_the_month_counts_the_month_in_full(self) -> None:
        january = self.value(day(2027, 1, 31), day(2027, 1, 31))
        self.assertEqual((january.accumulated, january.book_value, january.months_done), (D("100.00"), D("1100.00"), 1))
        february = self.value(day(2027, 1, 31), day(2027, 2, 1))
        self.assertEqual((february.accumulated, february.months_done), (D("200.00"), 2))

    def test_the_day_before_the_purchase_is_not_yet_acquired(self) -> None:
        before = self.value(day(2027, 1, 15), day(2027, 1, 14))
        self.assertEqual((before.state, before.book_value, before.accumulated), (depreciation.NOT_YET, None, D("0.00")))
        same_day = self.value(day(2027, 1, 15), day(2027, 1, 15))
        self.assertEqual(same_day.state, depreciation.RUNNING)

    def test_leap_year_february(self) -> None:
        bought = day(2028, 2, 29)
        self.assertEqual(self.value(bought, day(2028, 2, 29)).months_done, 1)
        self.assertEqual(self.value(bought, day(2028, 3, 1)).months_done, 2)
        self.assertEqual(self.value(day(2027, 2, 28), day(2027, 3, 1)).months_done, 2)
        # a 12-month life bought in a leap February is over after the following January
        self.assertEqual(self.value(bought, day(2029, 1, 31)).state, depreciation.WRITTEN_OFF)
        self.assertEqual(self.value(bought, day(2028, 12, 31)).state, depreciation.RUNNING)

    def test_the_whole_life_and_then_nothing_more(self) -> None:
        end = self.value(day(2027, 1, 10), day(2027, 12, 31))
        self.assertEqual(
            (end.state, end.book_value, end.accumulated, end.months_left), ("written_off", D("0.00"), D("1200.00"), 0)
        )
        later = self.value(day(2027, 1, 10), day(2040, 6, 1))
        self.assertEqual((later.book_value, later.accumulated, later.months_done), (D("0.00"), D("1200.00"), 12))

    def test_a_life_of_one_month(self) -> None:
        bought = self.value(day(2027, 5, 20), day(2027, 5, 20), cost="500", life=1)
        self.assertEqual((bought.book_value, bought.state), (D("0.00"), depreciation.WRITTEN_OFF))
        rows = depreciation.schedule(FIXED, D("500"), day(2027, 5, 1), 1)
        self.assertEqual([(row.year, row.months, row.depreciation) for row in rows], [(2027, 1, D("500.00"))])

    def test_partial_first_year(self) -> None:
        rows = depreciation.schedule(FIXED, D("1000"), day(2026, 3, 17), 36)
        self.assertEqual(
            [(row.year, row.months, row.depreciation) for row in rows],
            [(2026, 10, D("277.78")), (2027, 12, D("333.33")), (2028, 12, D("333.33")), (2029, 2, D("55.56"))],
        )
        self.assertEqual(rows[-1].book_value, D("0.00"))
        self.assertEqual(sum(row.depreciation for row in rows), D("1000.00"))
        self.assertEqual(sum(row.months for row in rows), 36)

    def test_depreciation_of_the_year_and_the_value_at_its_start(self) -> None:
        valued = depreciation.valuation(FIXED, D("1000"), day(2026, 3, 17), 36, day(2027, 3, 1))
        self.assertEqual(valued.accumulated, D("361.11"))
        self.assertEqual(valued.opening_value, D("722.22"))  # 31 December 2026
        self.assertEqual(valued.this_year, D("83.33"))  # January to March 2027
        self.assertEqual(valued.book_value, D("638.89"))
        self.assertEqual((valued.months_done, valued.months_left, valued.last_month), (13, 23, day(2029, 2, 1)))


class RoundingTests(PlainTestCase):
    """Cents: every instalment is a whole cent, the sum is exact, the last month balances."""

    def test_one_third_and_a_cent_over(self) -> None:
        base = D("100.00")
        parts = [depreciation.instalment(base, 7, month) for month in range(1, 8)]
        self.assertEqual(sum(parts), base)
        self.assertEqual(parts, [D("14.29"), D("14.28"), D("14.29"), D("14.28"), D("14.29"), D("14.28"), D("14.29")])
        self.assertTrue(all(part.as_tuple().exponent == -2 for part in parts))

    def test_less_than_a_cent_a_month(self) -> None:
        rows = depreciation.schedule(FIXED, D("0.05"), day(2026, 1, 1), 60)
        self.assertEqual(sum(row.depreciation for row in rows), D("0.05"))
        self.assertTrue(all(row.depreciation >= 0 for row in rows))

    def test_many_costs_and_lives_always_add_up(self) -> None:
        generator = random.Random(20271)
        for _round in range(300):
            cost = D(generator.randint(0, 99_999_999_99)) / 100
            life = generator.choice([1, 2, 3, 7, 11, 12, 13, 36, 60, 84, 120, 599, 600])
            memory = generator.random() < 0.3
            base = depreciation.depreciable_base(cost, memory=memory)
            exact = base / life
            previous = D(0)
            total = D(0)
            for month in range(1, life + 1) if life <= 120 else range(1, 121):
                accumulated = depreciation.written_off_after(base, life, month)
                part = accumulated - previous
                self.assertGreaterEqual(part, 0)
                self.assertLessEqual(abs(part - exact), D("0.01"), (cost, life, month))
                previous = accumulated
                total += part
            self.assertEqual(depreciation.written_off_after(base, life, life), base)
            rows = depreciation.schedule(FIXED, cost, day(2026, generator.randint(1, 12), 1), life, memory=memory)
            self.assertEqual(sum(row.depreciation for row in rows), base, (cost, life, memory))
            self.assertEqual(rows[-1].book_value, depreciation.money(cost) - base)
            self.assertEqual(sum(row.months for row in rows), life)
            self.assertTrue(all(row.book_value >= 0 for row in rows))

    def test_the_book_value_never_falls_below_zero(self) -> None:
        for as_of in (day(2026, 12, 31), day(2030, 1, 1), day(2999, 12, 31)):
            valued = depreciation.valuation(FIXED, D("99.99"), day(2026, 1, 1), 24, as_of)
            self.assertGreaterEqual(valued.book_value, 0)

    def test_huge_values(self) -> None:
        big = D("99999999.99")
        rows = depreciation.schedule(FIXED, big, day(2000, 1, 1), 600)
        self.assertEqual(sum(row.depreciation for row in rows), big)
        valued = depreciation.valuation(FIXED, D("123456789012345.67"), day(2000, 1, 1), 600, day(2025, 6, 1))
        self.assertEqual(valued.accumulated + valued.book_value, D("123456789012345.67"))
        self.assertEqual(depreciation.scale(D("99999999.99"), 1, 3), D("33333333.33"))
        self.assertEqual(depreciation.scale(D("100.00"), 3, 3), D("100.00"))
        # a life that is not a realistic one is still arithmetic, not a list of months
        self.assertEqual(depreciation.written_off_after(D("1000"), 1_000_000, 500_000), D("500.00"))

    def test_a_cost_of_nothing(self) -> None:
        valued = depreciation.valuation(FIXED, D("0"), day(2026, 1, 1), 12, day(2026, 6, 1))
        self.assertEqual((valued.book_value, valued.accumulated), (D("0.00"), D("0.00")))

    def test_what_cannot_be_calculated_is_refused_loudly(self) -> None:
        with self.assertRaises(ValueError):
            depreciation.valuation(FIXED, D("-1"), day(2026, 1, 1), 12, day(2026, 6, 1))
        with self.assertRaises(ValueError):
            depreciation.written_off_after(D("10"), 0, 1)
        with self.assertRaises(ValueError):
            depreciation.schedule(FIXED, D("10"), day(2026, 1, 1), None)
        with self.assertRaises(ValueError):
            depreciation.scale(D("10"), 4, 3)


class KindsTests(PlainTestCase):
    """Low-value assets, merchandise, memory value, dates known to the year, missing data."""

    def test_a_low_value_asset_is_written_off_at_the_end_of_the_year_of_purchase(self) -> None:
        bought = day(2026, 3, 17)
        during = depreciation.valuation(LOW, D("500"), bought, None, day(2026, 12, 30))
        self.assertEqual(
            (during.state, during.book_value, during.accumulated), (depreciation.LOW_VALUE_OPEN, D("500.00"), D("0.00"))
        )
        year_end = depreciation.valuation(LOW, D("500"), bought, None, day(2026, 12, 31))
        self.assertEqual(
            (year_end.state, year_end.book_value, year_end.accumulated),
            (depreciation.WRITTEN_OFF, D("0.00"), D("500.00")),
        )
        next_year = depreciation.valuation(LOW, D("500"), bought, None, day(2027, 6, 1))
        self.assertEqual(
            (next_year.book_value, next_year.this_year, next_year.opening_value), (D("0.00"), D("0.00"), D("0.00"))
        )
        self.assertEqual(year_end.this_year, D("500.00"))
        self.assertEqual(
            depreciation.schedule(LOW, D("500"), bought),
            [depreciation.YearRow(2026, 0, D("500.00"), D("500.00"), D("0.00"))],
        )

    def test_merchandise_is_not_depreciated(self) -> None:
        valued = depreciation.valuation(MERCH, D("80"), day(2020, 1, 1), None, day(2027, 3, 1))
        self.assertEqual(
            (valued.state, valued.book_value, valued.accumulated, valued.rows),
            ("merchandise", D("80.00"), D("0.00"), []),
        )

    def test_the_memory_value_stays(self) -> None:
        end = depreciation.valuation(FIXED, D("1000"), day(2020, 1, 1), 12, day(2027, 3, 1), memory=True)
        self.assertEqual(
            (end.book_value, end.accumulated, end.state), (D("1.00"), D("999.00"), depreciation.WRITTEN_OFF)
        )
        cheap = depreciation.valuation(FIXED, D("0.80"), day(2020, 1, 1), 12, day(2027, 3, 1), memory=True)
        self.assertEqual((cheap.book_value, cheap.accumulated), (D("0.80"), D("0.00")))
        rows = depreciation.schedule(FIXED, D("1000"), day(2020, 1, 1), 12, memory=True)
        self.assertEqual((sum(row.depreciation for row in rows), rows[-1].book_value), (D("999.00"), D("1.00")))

    def test_a_date_known_to_the_year_only_starts_in_january(self) -> None:
        bought = partial_dates.parse("2015")
        self.assertEqual(bought.date, day(2015, 1, 1))
        valued = depreciation.valuation(FIXED, D("1200"), bought.date, 24, day(2015, 6, 30))
        self.assertEqual((valued.start, valued.months_done, valued.accumulated), (day(2015, 1, 1), 6, D("300.00")))
        self.assertEqual(
            depreciation.valuation(FIXED, D("1200"), bought.date, 24, day(2016, 12, 31)).state, "written_off"
        )
        by_month = partial_dates.parse("00.05.2015")
        self.assertEqual(depreciation.valuation(FIXED, D("1200"), by_month.date, 24, day(2015, 5, 31)).months_done, 1)

    def test_a_purchase_in_the_future_is_not_yet_acquired(self) -> None:
        valued = depreciation.valuation(FIXED, D("1000"), day(2028, 1, 1), 12, day(2027, 3, 1))
        self.assertEqual(
            (valued.state, valued.book_value, valued.accumulated, valued.this_year),
            ("not_yet", None, D("0.00"), D("0.00")),
        )
        self.assertEqual(len(valued.rows), 1)  # the schedule can still be shown
        low = depreciation.valuation(LOW, D("100"), day(2027, 12, 1), None, day(2027, 3, 1))
        self.assertEqual(low.state, depreciation.NOT_YET)

    def test_what_is_missing_says_so(self) -> None:
        self.assertEqual(
            depreciation.valuation("", D("10"), day(2020, 1, 1), None, day(2027, 3, 1)).state, "unclassified"
        )
        self.assertEqual(depreciation.valuation(FIXED, None, day(2020, 1, 1), 12, day(2027, 3, 1)).state, "no_cost")
        self.assertEqual(depreciation.valuation(FIXED, D("10"), None, 12, day(2027, 3, 1)).state, "no_date")
        self.assertEqual(
            depreciation.valuation(FIXED, D("10"), day(2020, 1, 1), None, day(2027, 3, 1)).state, "no_life"
        )
        self.assertEqual(depreciation.valuation(LOW, D("10"), None, None, day(2027, 3, 1)).state, "no_date")
        for state in ("unclassified", "no_cost", "no_date", "no_life"):
            self.assertNotIn(state, depreciation.VALUED_STATES)


# --- Items -----------------------------------------------------------------------------------------------------------------


class Stock:
    """Items with asset data: a mixer (fixed asset, 36 months), a cable (GWG), a microphone (merchandise), an old one."""

    def prepare(self) -> None:
        self.model = make_model("Mischpult Midas M32", make_product("T-100", "Mischpult"), category_code="T")
        self.mixer = make_item(
            self.model, 100, purchase_date=day(2026, 3, 17), purchase_price=D("1000.00"),
            asset_kind=AssetKind.FIXED_ASSET, useful_life_months=36, ancillary_cost_net=D("50.00"),
            acquisition_cost_net=D("1050.00"),
        )  # fmt: skip
        self.cable_model = make_model("XLR-Kabel 10 m", category_code="K")
        self.cable = make_item(
            self.cable_model, 101, purchase_date=day(2026, 5, 2), purchase_price=D("20.00"),
            asset_kind=AssetKind.LOW_VALUE, acquisition_cost_net=D("22.00"),
        )  # fmt: skip
        self.mic = make_item(
            make_model("Shure SM58", category_code="T"), 102, purchase_date=day(2026, 6, 1),
            purchase_price=D("90.00"), asset_kind=AssetKind.MERCHANDISE, acquisition_cost_net=D("90.00"),
        )  # fmt: skip
        self.old = make_item(make_model("Alter Lautsprecher", category_code="T"), 103, purchase_price=D("300.00"))


class BookValueTests(Stock, RentalarsTestCase):
    """The valuation of items, recording an item as asset, the Anlagenspiegel."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_the_valuation_follows_the_item(self) -> None:
        valued = book_values.value_of(self.mixer, day(2027, 3, 1))
        self.assertEqual((valued.cost, valued.accumulated, valued.book_value), (D("1050.00"), D("379.17"), D("670.83")))
        self.assertEqual(valued.state, depreciation.RUNNING)
        self.assertEqual(book_values.value_of(self.old).state, depreciation.UNCLASSIFIED)
        self.assertEqual(book_values.value_of(self.mic, day(2030, 1, 1)).book_value, D("90.00"))
        # today is the clock of the tests: 1 March 2027
        self.assertEqual(book_values.value_of(self.mixer).as_of, day(2027, 3, 1))

    def test_the_cost_is_the_recorded_one_else_the_purchase_price(self) -> None:
        self.assertEqual(book_values.cost_of(self.old), D("300.00"))
        MaterialItem.objects.filter(pk=self.old.pk).update(ancillary_cost_net=D("20.00"))
        self.old.refresh_from_db()
        self.assertEqual(book_values.cost_of(self.old), D("320.00"))
        self.assertEqual(book_values.cost_of(self.mixer), D("1050.00"))

    def test_the_memory_value_is_a_setting(self) -> None:
        self.assertFalse(book_values.memory_value_on())
        self.assertEqual(book_values.value_of(self.mixer, day(2040, 1, 1)).book_value, D("0.00"))
        settings = AssetSettings.load()
        settings.keep_memory_value = True
        settings.save()
        self.assertEqual(book_values.value_of(self.mixer, day(2040, 1, 1)).book_value, D("1.00"))

    def test_an_old_item_is_recorded_as_a_fixed_asset(self) -> None:
        book_values.set_asset_data(self.old, kind="fixed_asset")
        self.old.refresh_from_db()
        # no useful life named: the standard one; no cost named: the purchase price
        self.assertEqual(
            (self.old.asset_kind, self.old.useful_life_months, self.old.acquisition_cost_net),
            ("fixed_asset", 60, D("300.00")),
        )
        book_values.set_asset_data(self.old, kind="fixed_asset", useful_life_months=24, ancillary_cost_net=D("15.00"))
        self.old.refresh_from_db()
        self.assertEqual(
            (self.old.useful_life_months, self.old.acquisition_cost_net, self.old.ancillary_cost_net),
            (24, D("315.00"), D("15.00")),
        )
        book_values.set_asset_data(self.old, kind="low_value")
        self.old.refresh_from_db()
        self.assertEqual((self.old.asset_kind, self.old.useful_life_months), ("low_value", None))
        entry = AuditLogEntry.for_object(self.old, include_children=False).first()
        self.assertIn("asset_kind", entry.changes)

    def test_recording_is_checked(self) -> None:
        for values, field in (
            ({"kind": "toy"}, "asset_kind"),
            ({"kind": "fixed_asset", "useful_life_months": 601}, "useful_life_months"),
            ({"kind": "fixed_asset", "acquisition_cost_net": D("-1")}, "acquisition_cost_net"),
            ({"kind": "fixed_asset", "acquisition_cost_net": D("100000000")}, "acquisition_cost_net"),
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError) as caught:
                book_values.set_asset_data(self.old, **values)
            self.assertIn(field, caught.exception.message_dict)
        nothing = make_item(make_model("Ohne Preis", category_code="T"), 104)
        with self.assertRaises(ValidationError) as caught:
            book_values.set_asset_data(nothing, kind="fixed_asset")
        self.assertIn("acquisition_cost_net", caught.exception.message_dict)
        book_values.set_asset_data(nothing, kind="fixed_asset", acquisition_cost_net=D("10"))

    def test_taking_an_item_out_of_the_books(self) -> None:
        book_values.set_asset_data(self.mixer, kind="")
        self.mixer.refresh_from_db()
        self.assertEqual((self.mixer.asset_kind, self.mixer.useful_life_months), ("", None))
        self.assertEqual(self.mixer.acquisition_cost_net, D("1050.00"))  # the costs stay

    def test_the_register_sums_what_counts(self) -> None:
        rows, summary = book_values.register(book_values.parse({}))
        self.assertEqual([row.item.inventory_number for row in rows], [100, 101])  # fixed and low-value assets
        self.assertEqual(summary.total.count, 2)
        self.assertEqual(summary.total.cost, D("1072.00"))
        self.assertEqual(summary.total.book_value, D("670.83"))  # the GWG was written off on 31 December 2026
        self.assertEqual(summary.by_kind["fixed_asset"].accumulated, D("379.17"))

    def test_the_register_on_a_balance_sheet_date(self) -> None:
        rows, summary = book_values.register(book_values.parse({"year": "2026"}))
        self.assertEqual(rows[0].valued.as_of, day(2026, 12, 31))
        self.assertEqual(summary.by_kind["fixed_asset"].book_value, D("758.33"))  # 1050 − 10/36
        self.assertEqual(summary.by_kind["fixed_asset"].this_year, D("291.67"))
        self.assertEqual(summary.by_kind["fixed_asset"].opening_value, D("1050.00"))
        self.assertEqual(summary.by_kind["low_value"].book_value, D("0.00"))
        # on a day in 2026 before the mixer was bought
        rows, summary = book_values.register(book_values.parse({"as_of": "2026-03-01"}))
        self.assertEqual([row.item.inventory_number for row in rows], [])
        self.assertEqual(summary.not_yet, 2)

    def test_filters(self) -> None:
        def numbers(**params: str) -> list[int]:
            return [row.item.inventory_number for row in book_values.register(book_values.parse(params))[0]]

        self.assertEqual(numbers(kind="fixed_asset"), [100])
        self.assertEqual(numbers(kind="low_value"), [101])
        self.assertEqual(numbers(kind="merchandise"), [102])
        self.assertEqual(numbers(kind="unclassified"), [103])
        self.assertEqual(numbers(kind="all"), [100, 101, 102, 103])
        self.assertEqual(numbers(model=str(self.mixer.material_model_id)), [100])
        self.assertEqual(numbers(q="XLR"), [101])
        self.assertEqual(numbers(q="101"), [101])
        location = make_location("Halle 1")
        MaterialItem.objects.filter(pk=self.mixer.pk).update(storage_location=location)
        self.assertEqual(numbers(location=str(location.pk)), [100])
        self.assertEqual(numbers(kind="all", location="999999"), [])

    def test_a_bad_filter_is_reported(self) -> None:
        found = book_values.parse({"kind": "toy", "location": "x", "as_of": "31.12.2026", "year": "20"})
        self.assertEqual(set(found.errors), {"kind", "location", "as_of", "year"})

    def test_unvalued_items_are_counted_apart(self) -> None:
        MaterialItem.objects.filter(pk=self.cable.pk).update(purchase_date=None)
        rows, summary = book_values.register(book_values.parse({}))
        self.assertEqual((summary.total.count, summary.unvalued), (1, 1))
        self.assertEqual(len(rows), 2)
        self.assertEqual(next(row for row in rows if row.item.pk == self.cable.pk).valued.state, depreciation.NO_DATE)

    def test_items_that_left_the_stock(self) -> None:
        MaterialItem.objects.filter(pk=self.mixer.pk).update(status=ItemStatus.RETIRED)
        rows, summary = book_values.register(book_values.parse({}))
        self.assertEqual([row.item.inventory_number for row in rows], [101])
        rows, summary = book_values.register(book_values.parse({"left": "1"}))
        self.assertEqual([row.item.inventory_number for row in rows], [100, 101])
        self.assertEqual((summary.left, summary.total.count), (1, 1))
        self.assertFalse(rows[0].counts)

    def test_a_bulk_row_is_valued_as_a_whole(self) -> None:
        ties = make_item(make_model("Kabelbinder", category_code="K", bulk=True), 110, quantity=200)
        book_values.set_asset_data(ties, kind="merchandise", acquisition_cost_net=D("40.00"))
        self.assertEqual(book_values.value_of(ties).book_value, D("40.00"))


def make_location(name: str):
    """A storage location."""
    from rentalars.masterdata.models import StorageLocation

    return StorageLocation.objects.create(name=name)


# --- The sale from stock ---------------------------------------------------------------------------------------------------


class SaleServiceTests(Stock, RentalarsTestCase):
    """Selling out of the stock: the figures, the checks, the reversal."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        self.user = make_user("luka", roles=("Lager",))

    def sell(self, item: MaterialItem, price: str = "700.00", **extra: object) -> SaleFromStock:
        values = {"sold_on": day(2027, 3, 1), "net_price": D(price), "buyer_name": "Hans Meier"}
        values.update(extra)
        return sales.sell(item, user=self.user, **values)

    def test_the_sale_of_a_fixed_asset(self) -> None:
        sale = self.sell(self.mixer)
        self.mixer.refresh_from_db()
        self.assertEqual(self.mixer.status, ItemStatus.SOLD)
        # (R1-16) changed: the reason is read by everyone who reads the material, so it names no buyer.
        self.assertEqual(self.mixer.status_reason, "Verkauft am 01.03.2027")
        # 1050 € over 36 months from March 2026: 12 months are over on 1 March 2027
        self.assertEqual(
            (sale.cost, sale.accumulated_depreciation, sale.book_value), (D("1050.00"), D("379.17"), D("670.83"))
        )
        self.assertEqual(sale.gain_loss, D("29.17"))
        self.assertEqual((sale.book_value_basis, sale.asset_kind, sale.item_left), ("calculated", "fixed_asset", True))
        self.assertEqual((sale.previous_status, sale.sold_by), (ItemStatus.AVAILABLE, self.user))
        self.assertEqual(sale.tax_amount + sale.net_price, sale.gross_price)

    def test_a_loss(self) -> None:
        sale = self.sell(self.mixer, "500.00")
        self.assertEqual(sale.gain_loss, D("-170.83"))

    def test_the_day_of_the_sale_decides_the_book_value(self) -> None:
        sale = self.sell(self.mixer, sold_on=day(2026, 12, 31))
        self.assertEqual(sale.book_value, D("758.33"))

    def test_a_gwg_sold_in_its_year_leaves_at_cost(self) -> None:
        sale = self.sell(self.cable, "10.00", sold_on=day(2026, 8, 1))
        self.assertEqual((sale.book_value, sale.gain_loss), (D("22.00"), D("-12.00")))
        other = make_item(
            self.cable_model, 105, purchase_date=day(2026, 5, 2), asset_kind=AssetKind.LOW_VALUE,
            acquisition_cost_net=D("22.00"),
        )  # fmt: skip
        later = self.sell(other, "10.00", sold_on=day(2027, 1, 5))
        self.assertEqual((later.book_value, later.gain_loss), (D("0.00"), D("10.00")))

    def test_merchandise_is_sold_against_its_cost(self) -> None:
        sale = self.sell(self.mic, "120.00")
        self.assertEqual((sale.book_value, sale.gain_loss), (D("90.00"), D("30.00")))

    def test_an_item_that_is_no_asset_is_sold_with_a_book_value_of_nothing(self) -> None:
        plan = sales.preview(self.old, sold_on=day(2027, 3, 1), net_price=D("100"))
        self.assertTrue(plan.ok)
        self.assertEqual((plan.basis, plan.book_value, plan.gain_loss), ("unknown", D("0.00"), D("100.00")))
        self.assertEqual(len(plan.notes), 1)
        sale = self.sell(self.old, "100.00")
        self.assertEqual(sale.book_value_basis, "unknown")

    def test_the_preview_changes_nothing(self) -> None:
        plan = sales.preview(self.mixer, sold_on=day(2027, 3, 1), net_price=D("700"))
        self.assertEqual(
            (plan.book_value, plan.gain_loss, plan.ok, plan.complete), (D("670.83"), D("29.17"), True, True)
        )
        self.assertEqual(plan.gross_price, D("700.00") + sales.percentage_of(D("700.00"), plan.tax_percent))
        self.mixer.refresh_from_db()
        self.assertEqual(self.mixer.status, ItemStatus.AVAILABLE)
        self.assertFalse(SaleFromStock.objects.exists())

    def test_the_tax_rate_is_kept_as_it_was(self) -> None:
        from rentalars.masterdata.models import TaxRate

        seven = TaxRate.objects.create(name="Ermäßigt 7 %", rate=D("7.00"))
        sale = self.sell(self.mic, "100.00", tax_rate=seven)
        self.assertEqual((sale.tax_percent, sale.tax_amount, sale.gross_price), (D("7.00"), D("7.00"), D("107.00")))

    def test_the_history_tells_the_sale_without_amounts(self) -> None:
        self.sell(self.mixer)
        rows = item_history(MaterialItem.objects.get(pk=self.mixer.pk), ALL_RIGHTS)
        texts = [row.summary for row in rows]
        # (R1-16) changed: the history names the day but no longer the buyer.
        self.assertTrue(any("2027-03-01" in text for text in texts), texts)
        for text in texts:
            self.assertNotIn("Hans Meier", text)
            self.assertNotIn("700", text)
            self.assertNotIn("670", text)

    def test_what_stops_a_sale(self) -> None:
        def problems(item: MaterialItem, **extra: object) -> list[str]:
            return sales.preview(item, **{"sold_on": day(2027, 3, 1), "net_price": D("1"), **extra}).problems

        self.assertEqual(problems(self.mixer), [])
        self.assertTrue(problems(self.mixer, net_price=None))
        self.assertTrue(problems(self.mixer, net_price=D("-1")))
        self.assertTrue(problems(self.mixer, sold_on=day(2027, 3, 2)))  # tomorrow
        self.assertTrue(problems(self.mixer, sold_on=day(2026, 3, 16)))  # before the purchase
        self.assertTrue(problems(self.mixer, quantity=2))
        MaterialItem.objects.filter(pk=self.mixer.pk).update(status=ItemStatus.IN_USE)
        self.assertTrue(problems(MaterialItem.objects.get(pk=self.mixer.pk)))
        for status in (ItemStatus.SOLD, ItemStatus.LOST):
            MaterialItem.objects.filter(pk=self.mic.pk).update(status=status)
            self.assertIn("Bestand schon verlassen", " ".join(problems(MaterialItem.objects.get(pk=self.mic.pk))))
        MaterialItem.objects.filter(pk=self.mic.pk).update(status=ItemStatus.RETIRED)
        self.assertEqual(problems(MaterialItem.objects.get(pk=self.mic.pk)), [])  # a retired item can still be sold
        MaterialItem.objects.filter(pk=self.cable.pk).update(status=ItemStatus.DEFECTIVE, status_reason="Wackler")
        self.assertEqual(problems(MaterialItem.objects.get(pk=self.cable.pk)), [])

    def test_an_item_in_a_case_must_come_out_first(self) -> None:
        case = make_item(make_model("Rack-Case", category_code="S"), 120)
        MaterialItem.objects.filter(pk=self.mixer.pk).update(installed_in=case)
        mixer = MaterialItem.objects.get(pk=self.mixer.pk)
        self.assertIn("Baue es zuerst aus", " ".join(sales.problems_of(mixer, 1, None)))
        self.assertIn("Baue sie zuerst aus", " ".join(sales.problems_of(case, 1, None)))
        with self.assertRaises(ValidationError):
            self.sell(mixer)

    def test_an_item_chosen_for_a_project_is_not_sold(self) -> None:
        _packing, row = packed_for_a_project(self.mixer)
        problems = sales.problems_of(MaterialItem.objects.get(pk=self.mixer.pk), 1, None)
        self.assertEqual(len(problems), 1)
        self.assertIn("ausgewählt oder gepackt", problems[0])
        with self.assertRaises(ValidationError):
            self.sell(self.mixer)
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.AVAILABLE)
        # issued: out with the project
        from django.utils import timezone

        type(row).objects.filter(pk=row.pk).update(issued_at=timezone.now())
        problems = sales.problems_of(MaterialItem.objects.get(pk=self.mixer.pk), 1, None)
        self.assertIn("unterwegs", problems[0])
        # back: free again
        type(row).objects.filter(pk=row.pk).update(returned_at=timezone.now())
        self.assertEqual(sales.problems_of(MaterialItem.objects.get(pk=self.mixer.pk), 1, None), [])

    def test_a_wish_of_the_planning_asks_for_a_confirmation(self) -> None:
        project = make_project("Stadtfest")
        line = wished_by(project, self.mixer)
        self.assertEqual(len(sales.warnings_of(self.mixer)), 1)
        self.assertIn("Stadtfest", sales.warnings_of(self.mixer)[0])
        with self.assertRaises(ValidationError) as caught:
            self.sell(self.mixer)
        self.assertEqual({error.code for error in caught.exception.error_list}, {"needs_confirmation"})
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.AVAILABLE)
        sale = self.sell(self.mixer, accept_warnings=True)
        self.assertTrue(sale.pk)
        # a finished project does not matter
        from rentalars.projects.models import Project, ProjectStatus

        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CLOSED)
        self.assertEqual(sales.warnings_of(self.mixer), [])
        self.assertTrue(line)

    def test_a_coming_block_asks_for_a_confirmation(self) -> None:
        ItemBlock.objects.create(item=self.cable, start=at(10), end=at(12), reason="Verleih intern")
        self.assertEqual(len(sales.warnings_of(self.cable)), 1)

    def test_the_buyer(self) -> None:
        customer = make_customer("Stadtwerke Musterstadt")
        sale = self.sell(self.mixer, buyer_name="", customer=customer)
        self.assertEqual((sale.buyer_name, sale.customer), ("Stadtwerke Musterstadt", customer))
        with self.assertRaises(ValidationError) as caught:
            self.sell(self.cable, buyer_name="  ")
        self.assertIn("buyer_name", caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            self.sell(self.cable, buyer_name="x" * 201)
        other = make_customer("Andere GmbH")
        from rentalars.customers.models import Contact

        contact = Contact.objects.create(customer=other, name="Berta Berg")
        with self.assertRaises(ValidationError) as caught:
            self.sell(self.cable, customer=customer, contact=contact)
        self.assertIn("contact", caught.exception.message_dict)
        sale = self.sell(self.cable, buyer_name="", contact=contact)
        self.assertEqual((sale.customer, sale.buyer_name), (other, "Berta Berg (Andere GmbH)"))

    def test_an_anonymised_customer_cannot_buy_and_his_sales_lose_his_name(self) -> None:
        from rentalars.customers.services import anonymise_customer

        customer = make_customer("Stadtwerke Musterstadt")
        sale = self.sell(self.mixer, buyer_name="", customer=customer)
        anonymise_customer(customer)
        sale.refresh_from_db()
        customer.refresh_from_db()
        self.assertEqual(sale.buyer_name, customer.name)
        self.assertNotIn("Stadtwerke", sales.buyer_label(sale))
        for entry in AuditLogEntry.for_object(sale):
            self.assertNotIn("Stadtwerke", str(entry.changes) + entry.object_repr)
        # nor does the history of the item tell the name any more
        for entry in AuditLogEntry.for_object(self.mixer, include_children=False):
            self.assertNotIn("Stadtwerke", str(entry.changes))
        self.assertTrue(AuditLogEntry.objects.filter(event="item.sold_from_stock").exists())
        self.assertNotIn("Stadtwerke", MaterialItem.objects.get(pk=self.mixer.pk).status_reason)
        with self.assertRaises(ValidationError):
            self.sell(self.cable, buyer_name="", customer=customer)

    def test_a_part_of_bulk_material(self) -> None:
        row = make_item(
            make_model("Kabelbinder", category_code="K", bulk=True), 130, quantity=100, purchase_date=day(2026, 1, 1),
            purchase_price=D("40.00"), ancillary_cost_net=D("10.00"), asset_kind=AssetKind.MERCHANDISE,
            acquisition_cost_net=D("50.00"),
        )  # fmt: skip
        plan = sales.preview(row, quantity=30, sold_on=day(2027, 3, 1), net_price=D("20.00"))
        self.assertEqual(
            (plan.pieces, plan.complete, plan.book_value, plan.gain_loss), (100, False, D("15.00"), D("5.00"))
        )
        sale = self.sell(row, "20.00", quantity=30)
        row.refresh_from_db()
        self.assertEqual((row.quantity, row.status), (70, ItemStatus.AVAILABLE))
        self.assertEqual(
            (row.purchase_price, row.ancillary_cost_net, row.acquisition_cost_net), (D("28.00"), D("7.00"), D("35.00"))
        )
        self.assertEqual(
            (sale.item_left, sale.quantity, sale.cost, sale.book_value), (False, 30, D("15.00"), D("15.00"))
        )
        # the rest: 70 of 70 pieces now
        rest = self.sell(row, "35.00", quantity=70)
        row.refresh_from_db()
        self.assertEqual((row.status, rest.item_left, rest.gain_loss), (ItemStatus.SOLD, True, D("0.00")))

    def test_more_than_the_free_quantity_is_refused(self) -> None:
        row = make_item(make_model("Schrauben", category_code="K", bulk=True), 131, quantity=10)
        row2 = make_item(make_model("Dübel", category_code="K", bulk=True), 132, quantity=10)
        InstalledQuantity.objects.create(container=self.mixer, material=row2, quantity=4)
        MaterialItem.objects.filter(pk=row2.pk).update(quantity=6)
        row2.refresh_from_db()
        self.assertTrue(sales.preview(row, quantity=11, sold_on=day(2027, 3, 1), net_price=D("1")).problems)
        plan = sales.preview(row2, quantity=6, sold_on=day(2027, 3, 1), net_price=D("1"))
        self.assertTrue(plan.ok)
        self.assertEqual((plan.pieces, plan.complete), (10, False))  # 4 more are built in: the row stays

    def test_the_reversal_of_a_sale(self) -> None:
        sale = self.sell(self.mixer)
        sales.cancel(sale, reason="Käufer ist abgesprungen", user=self.user)
        sale.refresh_from_db()
        mixer = MaterialItem.objects.get(pk=self.mixer.pk)
        self.assertEqual((mixer.status, mixer.status_reason), (ItemStatus.AVAILABLE, ""))
        self.assertTrue(sale.is_cancelled)
        self.assertEqual((sale.cancel_reason, sale.cancelled_by), ("Käufer ist abgesprungen", self.user))
        with self.assertRaises(ValidationError):
            sales.cancel(sale, reason="nochmal")
        # the item can be sold again, the book value follows the new day
        again = self.sell(self.mixer, sold_on=day(2027, 3, 1))
        self.assertNotEqual(again.pk, sale.pk)
        self.assertEqual(SaleFromStock.objects.filter(cancelled_at__isnull=True).count(), 1)
        history = [row.summary for row in item_history(MaterialItem.objects.get(pk=self.mixer.pk), ALL_RIGHTS)]
        self.assertTrue(any("storniert" in text for text in history), history)

    def test_a_reversal_needs_a_reason_and_the_item_as_sold(self) -> None:
        sale = self.sell(self.mixer)
        with self.assertRaises(ValidationError) as caught:
            sales.cancel(sale, reason="  ")
        self.assertIn("reason", caught.exception.message_dict)
        MaterialItem.objects.filter(pk=self.mixer.pk).update(status=ItemStatus.AVAILABLE)
        with self.assertRaises(ValidationError):
            sales.cancel(sale, reason="Irrtum")
        self.assertFalse(SaleFromStock.objects.get(pk=sale.pk).is_cancelled)

    def test_a_defective_item_comes_back_defective(self) -> None:
        from rentalars.material import services

        services.set_status(self.mixer, ItemStatus.DEFECTIVE, reason="Fader hängt")
        sale = self.sell(MaterialItem.objects.get(pk=self.mixer.pk), "100.00")
        sales.cancel(sale, reason="Irrtum")
        mixer = MaterialItem.objects.get(pk=self.mixer.pk)
        self.assertEqual((mixer.status, mixer.status_reason), (ItemStatus.DEFECTIVE, "Fader hängt"))

    def test_the_reversal_of_a_part_puts_it_back_exactly(self) -> None:
        row = make_item(
            make_model("Kabelbinder", category_code="K", bulk=True), 133, quantity=7, purchase_price=D("10.00"),
            ancillary_cost_net=D("1.00"), asset_kind=AssetKind.MERCHANDISE, acquisition_cost_net=D("11.00"),
            purchase_date=day(2026, 1, 1),
        )  # fmt: skip
        sale = self.sell(row, "5.00", quantity=3)
        sales.cancel(sale, reason="Irrtum")
        row.refresh_from_db()
        self.assertEqual(
            (row.quantity, row.purchase_price, row.ancillary_cost_net, row.acquisition_cost_net),
            (7, D("10.00"), D("1.00"), D("11.00")),
        )

    def test_the_sums_per_year(self) -> None:
        self.sell(self.mixer, "700.00")  # +29.17
        self.sell(self.cable, "10.00", sold_on=day(2026, 8, 1))  # −12.00
        reversed_sale = self.sell(self.mic, "500.00")
        sales.cancel(reversed_sale, reason="Irrtum")
        years = sales.sums_by_year(sales.sales())
        self.assertEqual([sums.year for sums in years], [2027, 2026])
        self.assertEqual(
            (years[0].count, years[0].net, years[0].gain, years[0].loss, years[0].result),
            (1, D("700.00"), D("29.17"), D("0"), D("29.17")),
        )
        self.assertEqual((years[1].gain, years[1].loss, years[1].result), (D("0"), D("-12.00"), D("-12.00")))
        self.assertEqual(sales.years_with_sales(), [2027, 2026])

    def test_filters_of_the_sales(self) -> None:
        self.sell(self.mixer, "700.00")
        self.sell(self.cable, "10.00", sold_on=day(2026, 8, 1), buyer_name="Petra Schulz")
        self.assertEqual(sales.parse_filters({"year": "2026"}).apply(sales.sales()).count(), 1)
        self.assertEqual(sales.parse_filters({"q": "Petra"}).apply(sales.sales()).count(), 1)
        self.assertEqual(sales.parse_filters({"q": "100"}).apply(sales.sales()).count(), 1)  # the ID
        self.assertEqual(sales.parse_filters({"since": "2027-01-01"}).apply(sales.sales()).count(), 1)
        self.assertEqual(sales.parse_filters({"until": "2026-12-31"}).apply(sales.sales()).count(), 1)
        self.assertEqual(set(sales.parse_filters({"year": "x", "since": "1.1.2026"}).errors), {"year", "since"})


def packed_for_a_project(item: MaterialItem):
    """The item is chosen on the packing list of a project (an open allocation); returns the packing service and it."""
    from decimal import Decimal as Dec

    from rentalars.packing import services as packing
    from rentalars.packing.models import Allocation
    from tests.helpers import add_line

    project = make_project("Messebau", start=at(10), end=at(12))
    product = item.product
    line = add_line(project, product, 1).line
    packlist = packing.get_packlist(project)
    entry_row = packing.find_row(packing.build_overview(packlist), line.pk, product.pk)
    entry = packing._entry_for(packlist, entry_row)
    allocation = Allocation.objects.create(entry=entry, item=item, issued_at=None)  # chosen, not yet packed
    assert Dec(1)
    return packing, allocation


def wished_by(project, item: MaterialItem):
    """A line of the project wishes for this item."""
    from tests.helpers import add_line

    line = add_line(project, item.product, 1).line
    line.preferred_item = item
    line.save()
    return line


# --- The pages -------------------------------------------------------------------------------------------------------------


def material_writer() -> Role:
    """A role that keeps the material but may not see purchase prices."""
    return Role.objects.create(name="Materialpflege", module_levels={Module.MATERIAL: int(Level.WRITE)})


class AssetPagesTests(Stock, UiTestCase):
    """The card on the item, the Anlagenspiegel, the sale, the sales, the reversal, the draft of an invoice."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        material_writer()

    def item_page(self, item: MaterialItem, client=None) -> str:
        return self.assert_ok((client or self.client).get(reverse("material:item_detail", args=[item.pk])))

    def sell_data(self, **changes: object) -> dict[str, object]:
        data = {
            "sold_on": "2027-03-01", "buyer_name": "Hans Meier", "net_price": "700,00", "note": "", "step": "sell",
            "tax_rate": str(TaxRate.get_default().pk),
        }  # fmt: skip
        data.update(changes)
        return {key: value for key, value in data.items() if value is not None}

    def test_the_card_shows_the_book_value(self) -> None:
        text = self.item_page(self.mixer)
        self.assertIn('id="asset"', text)
        self.assertIn("Anlagevermögen", text)
        self.assertIn("670,83", text)  # the book value today
        self.assertIn("379,17", text)
        self.assertIn(reverse("material:item_sell", args=[self.mixer.pk]), text)
        self.assertIn(reverse("material:item_asset", args=[self.mixer.pk]), text)

    def test_the_card_is_not_there_without_the_purchase_prices_right(self) -> None:
        client = self.browser_for("pflege", "Materialpflege")
        text = self.item_page(self.mixer, client)
        self.assertNotIn('id="asset"', text)
        self.assertNotIn("670,83", text)
        self.assertNotIn(reverse("material:item_sell", args=[self.mixer.pk]), text)

    def test_a_reader_sees_the_card_without_the_buttons(self) -> None:
        client = self.browser_for("leser", "Nur-Lesen")
        text = self.item_page(self.mixer, client)
        self.assertIn("670,83", text)
        self.assertNotIn(reverse("material:item_sell", args=[self.mixer.pk]), text)
        self.assertNotIn(reverse("material:item_asset", args=[self.mixer.pk]), text)

    def test_the_card_of_an_item_that_is_no_asset_offers_to_record_it(self) -> None:
        text = self.item_page(self.old)
        self.assertIn(reverse("material:item_asset", args=[self.old.pk]), text)

    def test_an_item_is_recorded_as_asset_on_the_page(self) -> None:
        url = reverse("material:item_asset", args=[self.old.pk])
        response = self.client.post(url, {"asset_kind": "fixed_asset", "useful_life_months": "48"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Die Anlagedaten von 0103 wurden gespeichert.", self.messages_of(response))
        self.old.refresh_from_db()
        self.assertEqual(
            (self.old.asset_kind, self.old.useful_life_months, self.old.acquisition_cost_net),
            ("fixed_asset", 48, D("300.00")),
        )
        # nonsense is told, nothing is saved
        response = self.client.post(url, {"asset_kind": "fixed_asset", "useful_life_months": "9999"}, follow=True)
        self.assertTrue(self.messages_of(response))
        self.old.refresh_from_db()
        self.assertEqual(self.old.useful_life_months, 48)
        # a get is not allowed
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_recording_needs_the_rights(self) -> None:
        url = reverse("material:item_asset", args=[self.old.pk])
        for username, role in (("pflege", "Materialpflege"), ("leser", "Nur-Lesen")):
            response = self.browser_for(username, role).post(url, {"asset_kind": "low_value"})
            self.assertEqual(response.status_code, 403, username)
        self.old.refresh_from_db()
        self.assertEqual(self.old.asset_kind, "")

    def test_the_register_page(self) -> None:
        text = self.assert_ok(self.client.get(reverse("material:asset_register")))
        self.assertIn("0100", text)
        self.assertIn("0101", text)
        self.assertNotIn("0102", text)  # merchandise is not in the default selection
        self.assertIn("670,83", text)
        self.assertIn(reverse("material:sales"), text)  # the tab
        text = self.assert_ok(self.client.get(reverse("material:asset_register"), {"kind": "all"}))
        self.assertIn("0102", text)
        self.assertIn("0103", text)

    def test_the_register_page_on_a_balance_sheet_date(self) -> None:
        text = self.assert_ok(self.client.get(reverse("material:asset_register"), {"year": "2026"}))
        self.assertIn("758,33", text)
        self.assertIn("31.12.2026", text)

    def test_a_bad_filter_of_the_register_is_told(self) -> None:
        text = self.assert_ok(self.client.get(reverse("material:asset_register"), {"as_of": "gestern", "kind": "toy"}))
        self.assertIn("0100", text)  # the page still works

    def test_the_register_as_csv(self) -> None:
        response = self.client.get(reverse("material:asset_register"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        text = response.content.decode("utf-8-sig")
        self.assertIn("0100", text)
        self.assertIn("670,83", text)
        self.assertNotIn("DATEV", text)

    def test_the_register_is_for_who_sees_purchase_prices(self) -> None:
        writer = self.browser_for("pflege", "Materialpflege")
        reader = self.browser_for("leser", "Nur-Lesen")
        for url in (reverse("material:asset_register"), reverse("material:sales")):
            self.assertEqual(writer.get(url).status_code, 403, url)
            self.assertEqual(reader.get(url).status_code, 200, url)
        self.assertEqual(writer.get(reverse("material:asset_register"), {"format": "csv"}).status_code, 403)

    def test_every_column_of_the_tables_sorts_and_groups(self) -> None:
        self.client.post(reverse("material:item_sell", args=[self.mixer.pk]), self.sell_data())
        self.assertEqual(SaleFromStock.objects.count(), 1)
        for table, url in (
            (ASSET_TABLE, reverse("material:asset_register")),
            (SALES_TABLE, reverse("material:sales")),
        ):
            common = {"cols": "all", "kind": "all", "left": "1", "reversed": "1"}
            for column in table.columns:
                for params in ({"sort": column.key}, {"sort": f"-{column.key}"}, {"group": column.key}):
                    with self.subTest(table=table.key, **params):
                        text = self.assert_ok(self.client.get(url, {**common, **params}))
                        self.assertIn('<table class="table', text)
                with self.subTest(table=table.key, csv=column.key):
                    response = self.client.get(url, {**common, "format": "csv", "sort": column.key})
                    self.assertEqual(response.status_code, 200)

    def test_the_sell_page(self) -> None:
        url = reverse("material:item_sell", args=[self.mixer.pk])
        text = self.assert_ok(self.client.get(url))
        self.assertIn('name="sold_on"', text)
        self.assertIn('name="net_price"', text)
        self.assertNotIn('name="quantity"', text)  # a single item

    def test_the_preview_shows_the_figures_and_changes_nothing(self) -> None:
        url = reverse("material:item_sell", args=[self.mixer.pk])
        text = self.assert_ok(self.client.post(url, self.sell_data(step="preview")))
        self.assertIn("670,83", text)
        self.assertIn("29,17", text)
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.AVAILABLE)
        self.assertFalse(SaleFromStock.objects.exists())

    def test_selling_on_the_page(self) -> None:
        url = reverse("material:item_sell", args=[self.mixer.pk])
        response = self.client.post(url, self.sell_data())
        sale = SaleFromStock.objects.get()
        self.assertRedirects(response, reverse("material:sale_detail", args=[sale.pk]))
        self.assertEqual((sale.gain_loss, sale.buyer_name), (D("29.17"), "Hans Meier"))
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.SOLD)
        # the item page lists the sale and no longer offers to sell
        text = self.item_page(self.mixer)
        self.assertIn(reverse("material:sale_detail", args=[sale.pk]), text)
        self.assertNotIn(url, text)

    def test_the_sell_page_names_what_stops_the_sale(self) -> None:
        packed_for_a_project(self.mixer)
        url = reverse("material:item_sell", args=[self.mixer.pk])
        self.assertIn("ausgewählt oder gepackt", self.assert_ok(self.client.get(url)))
        text = self.assert_ok(self.client.post(url, self.sell_data()))
        self.assertIn("ausgewählt oder gepackt", text)
        self.assertFalse(SaleFromStock.objects.exists())

    def test_the_sell_page_asks_before_it_sells_a_wished_item(self) -> None:
        wished_by(make_project("Stadtfest"), self.mixer)
        url = reverse("material:item_sell", args=[self.mixer.pk])
        text = self.assert_ok(self.client.post(url, self.sell_data()))
        self.assertIn("in der Planung gewünscht", text)
        self.assertFalse(SaleFromStock.objects.exists())
        self.client.post(url, self.sell_data(accept_warnings="on"))
        self.assertEqual(SaleFromStock.objects.count(), 1)

    def test_a_bad_form_is_sent_back(self) -> None:
        url = reverse("material:item_sell", args=[self.mixer.pk])
        for changes in ({"sold_on": "2027-03-02"}, {"net_price": "x"}, {"buyer_name": ""}, {"net_price": None}):
            with self.subTest(changes=changes):
                self.assert_ok(self.client.post(url, self.sell_data(**changes)))
                self.assertFalse(SaleFromStock.objects.exists())

    def test_the_sell_page_for_bulk_material_asks_for_the_quantity(self) -> None:
        ties = make_item(
            make_model("Kabelbinder", category_code="K", bulk=True), 140, quantity=100, purchase_price=D("40")
        )
        url = reverse("material:item_sell", args=[ties.pk])
        self.assertIn('name="quantity"', self.assert_ok(self.client.get(url)))
        self.client.post(url, self.sell_data(quantity="30", net_price="10,00"))
        ties.refresh_from_db()
        self.assertEqual(ties.quantity, 70)

    def test_selling_needs_the_rights(self) -> None:
        url = reverse("material:item_sell", args=[self.mixer.pk])
        for username, role in (("pflege", "Materialpflege"), ("leser", "Nur-Lesen")):
            browser = self.browser_for(username, role)
            self.assertEqual(browser.get(url).status_code, 403, username)
            self.assertEqual(browser.post(url, self.sell_data()).status_code, 403, username)
        self.assertFalse(SaleFromStock.objects.exists())

    def test_a_buyer_from_the_customers(self) -> None:
        customer = make_customer("Stadtwerke Musterstadt")
        url = reverse("material:item_sell", args=[self.mixer.pk])
        self.assertIn('name="customer"', self.assert_ok(self.client.get(url)))
        self.client.post(url, self.sell_data(customer=str(customer.pk), buyer_name=""))
        self.assertEqual(SaleFromStock.objects.get().customer, customer)
        # a user who may not read the customers does not get the field – and cannot name one
        lager = self.browser_for("lager", "Lager")
        self.assertNotIn(
            'name="customer"', self.assert_ok(lager.get(reverse("material:item_sell", args=[self.cable.pk])))
        )

    def test_the_sales_page(self) -> None:
        self.client.post(reverse("material:item_sell", args=[self.mixer.pk]), self.sell_data())
        self.client.post(
            reverse("material:item_sell", args=[self.cable.pk]), self.sell_data(sold_on="2026-08-01", net_price="10,00")
        )
        text = self.assert_ok(self.client.get(reverse("material:sales")))
        self.assertIn("Hans Meier", text)
        self.assertIn("29,17", text)
        self.assertIn("12,00", text)  # the loss
        self.assertIn("2026", text)
        text = self.assert_ok(self.client.get(reverse("material:sales"), {"year": "2026"}))
        self.assertNotIn("29,17", text)
        csv = self.client.get(reverse("material:sales"), {"format": "csv"})
        self.assertIn("text/csv", csv["Content-Type"])
        self.assertIn("Hans Meier", csv.content.decode("utf-8-sig"))
        self.assert_ok(self.client.get(reverse("material:sales"), {"year": "x"}))

    def test_the_sale_page_and_its_reversal(self) -> None:
        self.client.post(reverse("material:item_sell", args=[self.mixer.pk]), self.sell_data())
        sale = SaleFromStock.objects.get()
        url = reverse("material:sale_detail", args=[sale.pk])
        text = self.assert_ok(self.client.get(url))
        self.assertIn("670,83", text)
        self.assertIn(reverse("material:sale_cancel", args=[sale.pk]), text)
        self.assertEqual(self.client.get(reverse("material:sale_cancel", args=[sale.pk])).status_code, 405)
        # without a reason nothing happens
        response = self.client.post(reverse("material:sale_cancel", args=[sale.pk]), {"reason": " "}, follow=True)
        self.assertTrue(self.messages_of(response))
        self.assertFalse(SaleFromStock.objects.get().is_cancelled)
        response = self.client.post(reverse("material:sale_cancel", args=[sale.pk]), {"reason": "Irrtum"}, follow=True)
        self.assertTrue(SaleFromStock.objects.get().is_cancelled)
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.AVAILABLE)
        text = self.assert_ok(response)
        self.assertIn("Irrtum", text)
        self.assertNotIn(reverse("material:sale_cancel", args=[sale.pk]), text)  # reversed once
        self.assertEqual(self.client.get(reverse("material:sale_detail", args=[99999])).status_code, 404)

    def test_the_sale_page_is_read_only_for_a_reader(self) -> None:
        self.client.post(reverse("material:item_sell", args=[self.mixer.pk]), self.sell_data())
        sale = SaleFromStock.objects.get()
        reader = self.browser_for("leser", "Nur-Lesen")
        text = self.assert_ok(reader.get(reverse("material:sale_detail", args=[sale.pk])))
        self.assertNotIn(reverse("material:sale_cancel", args=[sale.pk]), text)
        self.assertEqual(reader.post(reverse("material:sale_cancel", args=[sale.pk]), {"reason": "x"}).status_code, 403)
        self.assertEqual(reader.post(reverse("material:sale_invoice", args=[sale.pk])).status_code, 403)
        self.assertEqual(
            self.browser_for("pflege", "Materialpflege")
            .get(reverse("material:sale_detail", args=[sale.pk]))
            .status_code,
            403,
        )
        self.assertFalse(SaleFromStock.objects.get().is_cancelled)

    def test_an_invoice_for_the_sale(self) -> None:
        from rentalars.documents.models import DocumentDraft

        customer = make_customer("Stadtwerke Musterstadt")
        self.client.post(
            reverse("material:item_sell", args=[self.mixer.pk]),
            self.sell_data(customer=str(customer.pk), buyer_name=""),
        )
        sale = SaleFromStock.objects.get()
        text = self.assert_ok(self.client.get(reverse("material:sale_detail", args=[sale.pk])))
        self.assertIn(reverse("material:sale_invoice", args=[sale.pk]), text)
        response = self.client.post(reverse("material:sale_invoice", args=[sale.pk]))
        draft = DocumentDraft.objects.get()
        self.assertRedirects(response, reverse("documents:free_edit", args=[draft.pk]))
        self.assertEqual(draft.customer, customer)
        line = draft.lines.get()
        self.assertEqual(line.unit_price, D("700.00"))
        self.assertIn("Midas M32", line.title)
        self.assert_ok(self.client.get(reverse("documents:free_edit", args=[draft.pk])))

    def test_one_invoice_for_a_sale_and_no_reversal_with_an_invoice(self) -> None:
        """The sale and its invoice are linked; asking twice makes no second invoice; a standing invoice stops
        the reversal of the sale."""
        from rentalars.documents import free, services
        from rentalars.documents.models import DocumentDraft
        from tests.helpers import ready_for_invoices

        customer = ready_for_invoices(make_customer("Stadtwerke Musterstadt"))
        self.client.post(
            reverse("material:item_sell", args=[self.mixer.pk]),
            self.sell_data(customer=str(customer.pk), buyer_name=""),
        )
        sale = SaleFromStock.objects.get()
        self.client.post(reverse("material:sale_invoice", args=[sale.pk]))
        self.client.post(reverse("material:sale_invoice", args=[sale.pk]))
        draft = DocumentDraft.objects.get()  # still one
        sale.refresh_from_db()
        self.assertEqual(sale.invoice_draft_id, draft.pk)

        document = free.issue(draft)
        sale.refresh_from_db()
        self.assertEqual((sale.document, sale.invoice_draft_id), (document, None))
        again = self.client.post(reverse("material:sale_invoice", args=[sale.pk]), follow=True)
        self.assertIn(document.number, " ".join(self.messages_of(again)))
        self.assertFalse(DocumentDraft.objects.exists())

        refused = self.client.post(reverse("material:sale_cancel", args=[sale.pk]), {"reason": "Irrtum"}, follow=True)
        self.assertIn(document.number, " ".join(self.messages_of(refused)))
        self.assertFalse(SaleFromStock.objects.get().is_cancelled)

        services.cancel_invoice(document)  # the invoice is cancelled: now the sale may be reversed
        self.client.post(reverse("material:sale_cancel", args=[sale.pk]), {"reason": "Irrtum"})
        self.assertTrue(SaleFromStock.objects.get().is_cancelled)

    def test_reversing_a_sale_throws_its_draft_away(self) -> None:
        from rentalars.documents.models import DocumentDraft

        customer = make_customer("Stadtwerke Musterstadt")
        self.client.post(
            reverse("material:item_sell", args=[self.mixer.pk]),
            self.sell_data(customer=str(customer.pk), buyer_name=""),
        )
        sale = SaleFromStock.objects.get()
        self.client.post(reverse("material:sale_invoice", args=[sale.pk]))
        self.assertEqual(DocumentDraft.objects.count(), 1)
        self.client.post(reverse("material:sale_cancel", args=[sale.pk]), {"reason": "Irrtum"})
        self.assertFalse(DocumentDraft.objects.exists())
        self.assertTrue(SaleFromStock.objects.get().is_cancelled)

    def test_no_invoice_for_a_buyer_without_customer_or_a_reversed_sale(self) -> None:
        from rentalars.documents.models import DocumentDraft

        self.client.post(reverse("material:item_sell", args=[self.mixer.pk]), self.sell_data())
        sale = SaleFromStock.objects.get()
        text = self.assert_ok(self.client.get(reverse("material:sale_detail", args=[sale.pk])))
        self.assertNotIn(reverse("material:sale_invoice", args=[sale.pk]), text)
        response = self.client.post(reverse("material:sale_invoice", args=[sale.pk]), follow=True)
        self.assertTrue(self.messages_of(response))
        self.assertFalse(DocumentDraft.objects.exists())

    def test_the_tabs_of_the_accounting_lead_here(self) -> None:
        text = self.assert_ok(self.client.get(reverse("material:asset_register")))
        self.assertIn(reverse("material:sales"), text)
        self.assertIn(reverse("material:asset_register"), text)
        # a user without the right does not see the tabs on the pages of Buchhaltung
        reader = self.browser_for("pflege", "Materialpflege")
        self.assertNotIn(reverse("material:asset_register"), self.assert_ok(reader.get(reverse("material:item_list"))))

    def test_the_navigation_entry(self) -> None:
        from rentalars.accounts.rights import rights_of
        from rentalars.core.navigation import entries_for

        def starts(user) -> list[str]:
            return [start for link in entries_for(rights_of(user)) for _prefix, start in link.starts]

        self.assertIn(reverse("material:asset_register"), starts(self.admin_user))
        self.assertIn(reverse("material:asset_register"), starts(make_user("leser", roles=("Nur-Lesen",))))
        self.assertNotIn(reverse("material:asset_register"), starts(make_user("pflege", roles=("Materialpflege",))))

    def test_the_memory_value_in_the_settings(self) -> None:
        url = reverse("incoming:settings")
        text = self.assert_ok(self.client.get(url))
        self.assertIn("keep_memory_value", text)
        data = form_data(self.client.get(url), containing="default_useful_life_months", keep_memory_value="on")
        self.client.post(url, data)
        self.assertTrue(AssetSettings.load().keep_memory_value)
        self.assertEqual(book_values.value_of(self.mixer, day(2040, 1, 1)).book_value, D("1.00"))


# --- The API ---------------------------------------------------------------------------------------------------------------


class AssetApiTests(Stock, ApiTestCase):
    """Every operation (API-014): reached, with its rights, with its errors."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        material_writer()
        self.sale_body = {"sold_on": "2027-03-01", "net_price": "700.00", "buyer_name": "Hans Meier"}

    def sell(self, item: MaterialItem | None = None, **extra: object) -> dict:
        response = self.admin.post(
            f"{API}/material-items/{(item or self.mixer).pk}/sell", {**self.sale_body, **extra}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_the_asset_data_of_an_item(self) -> None:
        response = self.admin.get(f"{API}/material-items/{self.mixer.pk}/asset")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            (body["asset_kind"], body["book_value"], body["accumulated_depreciation"]),
            ("fixed_asset", "670.83", "379.17"),
        )
        self.assertEqual((body["state"], body["months_done"], body["months_left"]), ("running", 13, 23))
        self.assertEqual(
            body["schedule"][0],
            {"year": 2026, "months": 10, "depreciation": "291.67", "accumulated": "291.67", "book_value": "758.33"},
        )
        later = self.admin.get(f"{API}/material-items/{self.mixer.pk}/asset", {"as_of": "2030-01-01"}).json()
        self.assertEqual((later["book_value"], later["state"]), ("0.00", "written_off"))
        self.assert_error(
            self.admin.get(f"{API}/material-items/{self.mixer.pk}/asset", {"as_of": "1.1.2030"}),
            400,
            "validation_error",
            "as_of",
        )
        self.assertEqual(self.admin.get(f"{API}/material-items/999999/asset").status_code, 404)

    def test_recording_an_item_as_asset(self) -> None:
        url = f"{API}/material-items/{self.old.pk}/asset"
        response = self.admin.patch(
            url, {"asset_kind": "fixed_asset", "useful_life_months": 24, "ancillary_cost_net": "15.00"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            (body["asset_kind"], body["useful_life_months"], body["acquisition_cost_net"]),
            ("fixed_asset", 24, "315.00"),
        )
        self.assertEqual(
            self.admin.patch(url, {"asset_kind": "low_value"}, format="json").json()["asset_kind"], "low_value"
        )
        self.assert_error(
            self.admin.patch(url, {"asset_kind": "toy"}, format="json"), 400, "validation_error", "asset_kind"
        )
        self.assert_error(
            self.admin.patch(url, {"useful_life_months": 0}, format="json"),
            400,
            "validation_error",
            "useful_life_months",
        )
        nothing = make_item(make_model("Ohne Preis", category_code="T"), 150)
        self.assert_error(
            self.admin.patch(f"{API}/material-items/{nothing.pk}/asset", {"asset_kind": "fixed_asset"}, format="json"),
            400,
            "validation_error",
        )

    def test_the_rights_of_the_asset_data(self) -> None:
        url = f"{API}/material-items/{self.mixer.pk}/asset"
        writer = self.client_for("pflege", "Materialpflege")
        reader = self.client_for("leser", "Nur-Lesen")
        self.assert_error(writer.get(url), 403, "permission_denied")
        self.assertEqual(reader.get(url).status_code, 200)
        self.assert_error(reader.patch(url, {"asset_kind": "low_value"}, format="json"), 403, "permission_denied")
        self.assert_error(writer.patch(url, {"asset_kind": "low_value"}, format="json"), 403, "permission_denied")
        self.assertEqual(
            self.client_for("lager", "Lager").patch(url, {"asset_kind": "fixed_asset"}, format="json").status_code, 200
        )

    def test_the_register(self) -> None:
        response = self.admin.get(f"{API}/asset-register")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([row["display_id"] for row in body["results"]], ["0100", "0101"])
        first = body["results"][0]
        self.assertEqual((first["book_value"], first["asset_kind"], first["counts"]), ("670.83", "fixed_asset", True))
        self.assertEqual(
            next(
                row["item"]
                for row in self.admin.get(f"{API}/asset-register", {"kind": "all", "sort": "-id"}).json()["results"]
            ),
            self.old.pk,
        )
        for sort in ("model", "kind", "acquired", "cost", "book_value", "-book_value"):
            self.assertEqual(
                self.admin.get(f"{API}/asset-register", {"sort": sort, "kind": "all"}).status_code, 200, sort
            )
        self.assert_error(self.admin.get(f"{API}/asset-register", {"sort": "color"}), 400, "validation_error", "sort")
        self.assert_error(self.admin.get(f"{API}/asset-register", {"as_of": "x"}), 400, "validation_error", "as_of")
        self.assertEqual(len(self.admin.get(f"{API}/asset-register", {"year": "2026"}).json()["results"]), 2)

    def test_the_totals_of_the_register(self) -> None:
        body = self.admin.get(f"{API}/asset-register/totals").json()
        self.assertEqual((body["count"], body["acquisition_cost_net"], body["book_value"]), (2, "1072.00", "670.83"))
        self.assertEqual(body["by_kind"]["fixed_asset"]["accumulated_depreciation"], "379.17")
        self.assertEqual(
            self.admin.get(f"{API}/asset-register/totals", {"year": "2026"}).json()["by_kind"]["fixed_asset"][
                "book_value"
            ],
            "758.33",
        )
        self.assert_error(
            self.admin.get(f"{API}/asset-register/totals", {"kind": "toy"}), 400, "validation_error", "kind"
        )

    def test_the_csv_of_the_register(self) -> None:
        response = self.admin.get(f"{API}/asset-register/csv", {"kind": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        text = response.content.decode("utf-8-sig")
        self.assertEqual(len(text.strip().splitlines()), 5)  # header and four items
        self.assertIn("670,83", text)
        self.assert_error(self.admin.get(f"{API}/asset-register/csv", {"as_of": "x"}), 400, "validation_error", "as_of")

    def test_the_register_is_for_who_sees_purchase_prices(self) -> None:
        writer = self.client_for("pflege", "Materialpflege")
        reader = self.client_for("leser", "Nur-Lesen")
        for path in (
            "asset-register",
            "asset-register/totals",
            "asset-register/csv",
            "stock-sales",
            "stock-sales/summary",
            "stock-sales/csv",
        ):
            self.assert_error(writer.get(f"{API}/{path}"), 403, "permission_denied")
            self.assertEqual(reader.get(f"{API}/{path}").status_code, 200, path)

    def test_the_preview(self) -> None:
        url = f"{API}/material-items/{self.mixer.pk}/sale-preview"
        response = self.admin.post(url, self.sale_body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            (body["ok"], body["book_value"], body["gain_loss"], body["book_value_basis"]),
            (True, "670.83", "29.17", "calculated"),
        )
        self.assertEqual(
            (body["tax_amount"], body["gross_price"], body["item_leaves_the_stock"]), ("133.00", "833.00", True)
        )
        self.assertFalse(SaleFromStock.objects.exists())
        bad = self.admin.post(url, {**self.sale_body, "sold_on": "2027-03-02"}, format="json").json()
        self.assertFalse(bad["ok"])
        self.assertTrue(bad["problems"])
        self.assert_error(
            self.admin.post(url, {"sold_on": "2027-03-01"}, format="json"), 400, "validation_error", "net_price"
        )
        self.assert_error(
            self.client_for("leser", "Nur-Lesen").post(url, self.sale_body, format="json"), 403, "permission_denied"
        )

    def test_selling(self) -> None:
        body = self.sell()
        self.assertEqual(
            (body["gain_loss"], body["book_value"], body["cancelled"], body["item_left_the_stock"]),
            ("29.17", "670.83", False, True),
        )
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.SOLD)
        again = self.admin.post(f"{API}/material-items/{self.mixer.pk}/sell", self.sale_body, format="json")
        self.assert_error(again, 400, "validation_error")

    def test_selling_with_a_customer(self) -> None:
        customer = make_customer("Stadtwerke Musterstadt")
        body = self.sell(self.cable, buyer_name="", customer=customer.pk)
        self.assertEqual((body["customer"], body["buyer"]), (customer.pk, "Stadtwerke Musterstadt"))
        self.assert_error(
            self.admin.post(
                f"{API}/material-items/{self.mic.pk}/sell", {**self.sale_body, "buyer_name": ""}, format="json"
            ),
            400,
            "validation_error",
        )

    def test_a_warning_needs_a_confirmation(self) -> None:
        wished_by(make_project("Stadtfest"), self.mixer)
        url = f"{API}/material-items/{self.mixer.pk}/sell"
        self.assert_error(self.admin.post(url, self.sale_body, format="json"), 400, "validation_error")
        self.assertEqual(
            self.admin.post(url, {**self.sale_body, "accept_warnings": True}, format="json").status_code, 201
        )

    def test_selling_needs_write_access_and_purchase_prices(self) -> None:
        url = f"{API}/material-items/{self.mixer.pk}/sell"
        for username, role in (("pflege", "Materialpflege"), ("leser", "Nur-Lesen")):
            self.assert_error(
                self.client_for(username, role).post(url, self.sale_body, format="json"), 403, "permission_denied"
            )
        lager = self.client_for("lager", "Lager")
        customer = make_customer("Stadtwerke Musterstadt")
        # the names of customers are not for a user who may not read them
        self.assert_error(
            lager.post(url, {**self.sale_body, "customer": customer.pk}, format="json"), 403, "permission_denied"
        )
        self.assertEqual(lager.post(url, self.sale_body, format="json").status_code, 201)

    def test_the_sales(self) -> None:
        self.sell()
        self.sell(self.cable, sold_on="2026-08-01", net_price="10.00")
        body = self.admin.get(f"{API}/stock-sales").json()
        self.assertEqual([row["item_display_id"] for row in body["results"]], ["0100", "0101"])
        self.assertEqual(len(self.admin.get(f"{API}/stock-sales", {"year": "2026"}).json()["results"]), 1)
        self.assertEqual(len(self.admin.get(f"{API}/stock-sales", {"q": "Midas"}).json()["results"]), 1)
        for sort in ("sold_on", "-sold_on", "net_price", "gain_loss", "book_value", "item"):
            self.assertEqual(self.admin.get(f"{API}/stock-sales", {"sort": sort}).status_code, 200, sort)
        self.assert_error(self.admin.get(f"{API}/stock-sales", {"sort": "color"}), 400, "validation_error", "sort")
        self.assert_error(self.admin.get(f"{API}/stock-sales", {"year": "x"}), 400, "validation_error", "year")

    def test_the_summary_per_year(self) -> None:
        self.sell()
        self.sell(self.cable, sold_on="2026-08-01", net_price="10.00")
        reversed_sale = self.sell(self.mic, net_price="500.00")
        self.assertEqual(
            self.admin.post(
                f"{API}/stock-sales/{reversed_sale['id']}/cancel", {"reason": "Irrtum"}, format="json"
            ).status_code,
            200,
        )
        years = self.admin.get(f"{API}/stock-sales/summary").json()["years"]
        self.assertEqual([year["year"] for year in years], [2027, 2026])
        self.assertEqual(
            (years[0]["count"], years[0]["gains"], years[0]["losses"], years[0]["gain_loss"]),
            (1, "29.17", "0.00", "29.17"),
        )
        self.assertEqual((years[1]["losses"], years[1]["gain_loss"]), ("-12.00", "-12.00"))

    def test_the_csv_of_the_sales(self) -> None:
        self.sell()
        response = self.admin.get(f"{API}/stock-sales/csv")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8-sig")
        self.assertIn("Hans Meier", text)
        self.assertIn("29,17", text)

    def test_one_sale(self) -> None:
        made = self.sell()
        body = self.admin.get(f"{API}/stock-sales/{made['id']}").json()
        self.assertEqual((body["id"], body["buyer"], body["gain_loss"]), (made["id"], "Hans Meier", "29.17"))
        self.assertEqual(self.admin.get(f"{API}/stock-sales/999999").status_code, 404)
        self.assert_error(
            self.client_for("pflege", "Materialpflege").get(f"{API}/stock-sales/{made['id']}"), 403, "permission_denied"
        )

    def test_the_reversal(self) -> None:
        made = self.sell()
        url = f"{API}/stock-sales/{made['id']}/cancel"
        self.assert_error(self.admin.post(url, {}, format="json"), 400, "validation_error")
        self.assert_error(
            self.client_for("leser", "Nur-Lesen").post(url, {"reason": "x"}, format="json"), 403, "permission_denied"
        )
        body = self.admin.post(url, {"reason": "Irrtum"}, format="json").json()
        self.assertEqual((body["cancelled"], body["cancel_reason"]), (True, "Irrtum"))
        self.assertEqual(MaterialItem.objects.get(pk=self.mixer.pk).status, ItemStatus.AVAILABLE)
        self.assert_error(self.admin.post(url, {"reason": "nochmal"}, format="json"), 400, "validation_error")
        self.assertEqual(self.admin.get(f"{API}/stock-sales", {"reversed": "1"}).json()["count"], 1)
        self.assertEqual(self.admin.get(f"{API}/stock-sales").json()["count"], 0)

    def test_the_invoice(self) -> None:
        from rentalars.documents.models import DocumentDraft

        customer = make_customer("Stadtwerke Musterstadt")
        made = self.sell(buyer_name="", customer=customer.pk)
        url = f"{API}/stock-sales/{made['id']}/invoice"
        response = self.admin.post(url)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["draft"], DocumentDraft.objects.get().pk)
        self.assert_error(self.client_for("leser", "Nur-Lesen").post(url), 403, "permission_denied")
        without = self.sell(self.cable)
        self.assert_error(self.admin.post(f"{API}/stock-sales/{without['id']}/invoice"), 400, "validation_error")
        self.assertEqual(DocumentDraft.objects.count(), 1)

    def test_the_settings_carry_the_memory_value(self) -> None:
        self.assertFalse(self.admin.get(f"{API}/incoming-settings").json()["keep_memory_value"])
        response = self.admin.patch(f"{API}/incoming-settings", {"keep_memory_value": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(AssetSettings.load().keep_memory_value)
