# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "surcharges": surcharges for night, Sunday and holidays on crew lines (PER-009).

March 2027: the 12th is a Friday, the 13th a Saturday, the 14th a Sunday; summer time begins on Sunday, 28 March
(Easter Sunday), and ends on Sunday, 31 October 2027. Price 45.00 an hour, cost 30.00 an hour unless said.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from rentalars.accounts.rights import Rights
from rentalars.core.holidays import (
    STATE_CHOICES,
    easter_sunday,
    holiday_list,
    holidays_of,
    is_holiday,
    repentance_day,
)
from rentalars.core.models import TimeSurchargeRule, TimeSurchargeSettings
from rentalars.documents.content import _crew_position
from rentalars.personnel import services as personnel
from rentalars.projects import crew
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.list_sums import attach_sums
from rentalars.projects.models import CrewBilling, CrewLine
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.time_surcharges import (
    HIGH_HOLIDAY,
    HOLIDAY,
    NIGHT,
    NIGHT_AFTER_MIDNIGHT,
    PRICE,
    SUNDAY,
    SurchargeRules,
    WorkPiece,
    applying,
    entry_pieces,
    planned_pieces,
    surcharge_parts,
    time_pieces,
    total_of,
)
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
)

D = Decimal
BERLIN = ZoneInfo("Europe/Berlin")
RULES = SurchargeRules()


def moment(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime.datetime:
    """A moment in Berlin time."""
    return datetime.datetime(year, month, day, hour, minute, tzinfo=BERLIN)


def march(day: int, hour: int = 0, minute: int = 0) -> datetime.datetime:
    """A moment in March 2027."""
    return moment(2027, 3, day, hour, minute)


def summary(pieces: list) -> dict[frozenset[str], Decimal]:
    """Hours by set of kinds."""
    hours: dict[frozenset[str], Decimal] = {}
    for piece in pieces:
        hours[piece.kinds] = hours.get(piece.kinds, D("0")) + piece.hours
    return {kinds: value.quantize(D("0.01")) for kinds, value in hours.items()}


def switch_on(*, price: bool = True, costs: bool = True, **values: object) -> TimeSurchargeSettings:
    """Switch the surcharges on for new crew lines, with further settings.

    PER-040: ``price_<kind>``/``cost_<kind>`` change the percentage of the rules of that kind.
    """
    settings = TimeSurchargeSettings.load()
    settings.on_price, settings.on_costs = price, costs
    for name, value in values.items():
        side, _sep, code = name.partition("_")
        if side in ("price", "cost") and code:
            TimeSurchargeRule.objects.filter(code=code).update(**{f"{side}_percent": D(str(value))})
        else:
            setattr(settings, name, value)
    settings.full_clean()
    settings.save()
    return settings


def rules_of(*kinds: str, rules: SurchargeRules = RULES) -> tuple:
    """PER-040: the first rule of § 3b EStG of each kind."""
    return tuple(next(rule for rule in rules.rules if rule.key == kind) for kind in kinds)


def applying_kinds(kinds: set[str], percents: dict[str, Decimal]) -> list[tuple[str, Decimal]]:
    """PER-040: ``applying`` – the kinds that count, with the price percentages by kind."""
    rules = SurchargeRules.section_3b(price=percents)
    return [(rule.key, percent) for rule, percent in applying(rules_of(*kinds, rules=rules), PRICE)]


class HolidayTests(SimpleTestCase):
    """PER-009: the statutory holidays per federal state, computed (``core.holidays``)."""

    def test_easter_sunday(self) -> None:
        known = {
            2000: (4, 23),
            2008: (3, 23),
            2011: (4, 24),
            2019: (4, 21),
            2024: (3, 31),
            2025: (4, 20),
            2026: (4, 5),
            2027: (3, 28),
            2038: (4, 25),  # the latest possible
            2285: (3, 22),  # the earliest possible
        }
        for year, (month, day) in known.items():
            with self.subTest(year=year):
                self.assertEqual(easter_sunday(year), datetime.date(year, month, day))

    def test_repentance_day_is_the_wednesday_before_23_november(self) -> None:
        for year, day in {2023: 22, 2024: 20, 2025: 19, 2026: 18, 2027: 17, 2028: 22}.items():
            with self.subTest(year=year):
                self.assertEqual(repentance_day(year), datetime.date(year, 11, day))
                self.assertEqual(repentance_day(year).weekday(), 2)

    def test_the_holidays_of_the_whole_country(self) -> None:
        days = holidays_of(2026)
        self.assertEqual(len(days), 9)
        for month, day in [(1, 1), (4, 3), (4, 6), (5, 1), (5, 14), (5, 25), (10, 3), (12, 25), (12, 26)]:
            self.assertIn(datetime.date(2026, month, day), days)
        self.assertNotIn(datetime.date(2026, 4, 5), days)  # Easter Sunday is a Sunday, no holiday
        self.assertEqual(holidays_of(2026, "XX"), days)  # an unknown state: the whole country

    def test_the_states(self) -> None:
        cases = {
            "BW": (12, [(1, 6), (6, 4), (11, 1)], [(8, 15)]),
            "BY": (13, [(1, 6), (6, 4), (8, 15), (11, 1)], [(8, 8)]),
            "BYE": (12, [(1, 6), (6, 4), (11, 1)], [(8, 15)]),
            "BYA": (14, [(8, 8), (8, 15)], []),
            "BE": (10, [(3, 8)], [(5, 8)]),
            "BB": (12, [(4, 5), (5, 24), (10, 31)], []),
            "HB": (10, [(10, 31)], []),
            "HH": (10, [(10, 31)], []),
            "HE": (10, [(6, 4)], [(10, 31)]),
            "MV": (11, [(3, 8), (10, 31)], []),
            "NI": (10, [(10, 31)], []),
            "NW": (11, [(6, 4), (11, 1)], []),
            "RP": (11, [(6, 4), (11, 1)], []),
            "SL": (12, [(6, 4), (8, 15), (11, 1)], []),
            "SN": (11, [(10, 31), (11, 18)], [(6, 4)]),
            "SNF": (12, [(6, 4), (10, 31), (11, 18)], []),
            "ST": (11, [(1, 6), (10, 31)], []),
            "SH": (10, [(10, 31)], []),
            "TH": (11, [(9, 20), (10, 31)], [(6, 4)]),
            "THF": (12, [(6, 4), (9, 20), (10, 31)], []),
        }
        self.assertEqual({code for code, _label in STATE_CHOICES} - {""}, set(cases))
        for state, (count, present, absent) in cases.items():
            with self.subTest(state=state):
                days = holidays_of(2026, state)
                self.assertEqual(len(days), count)
                for month, day in present:
                    self.assertIn(datetime.date(2026, month, day), days)
                for month, day in absent:
                    self.assertNotIn(datetime.date(2026, month, day), days)

    def test_changes_of_the_laws(self) -> None:
        self.assertTrue(is_holiday(datetime.date(2017, 10, 31)))  # 500 years of Reformation, everywhere
        self.assertFalse(is_holiday(datetime.date(2018, 10, 31)))
        self.assertFalse(is_holiday(datetime.date(2016, 10, 31), "HH"))
        self.assertTrue(is_holiday(datetime.date(2018, 10, 31), "HH"))
        self.assertFalse(is_holiday(datetime.date(2018, 3, 8), "BE"))
        self.assertTrue(is_holiday(datetime.date(2019, 3, 8), "BE"))
        self.assertFalse(is_holiday(datetime.date(2022, 3, 8), "MV"))
        self.assertTrue(is_holiday(datetime.date(2023, 3, 8), "MV"))
        self.assertTrue(is_holiday(datetime.date(2020, 5, 8), "BE"))
        self.assertTrue(is_holiday(datetime.date(2025, 5, 8), "BE"))
        self.assertFalse(is_holiday(datetime.date(2026, 5, 8), "BE"))
        self.assertFalse(is_holiday(datetime.date(2018, 9, 20), "TH"))
        self.assertTrue(is_holiday(datetime.date(2019, 9, 20), "TH"))
        self.assertTrue(is_holiday(datetime.date(1994, 11, 16)))  # Repentance Day, everywhere until 1994
        self.assertFalse(is_holiday(datetime.date(1995, 11, 22)))
        self.assertTrue(is_holiday(datetime.date(1995, 11, 22), "SN"))
        self.assertFalse(is_holiday(datetime.date(1989, 10, 3)))
        self.assertTrue(is_holiday(datetime.date(1990, 10, 3)))

    def test_the_list_for_the_settings_page(self) -> None:
        with translation.override("de"):
            listed = holiday_list([2026, 2027], "BY")
        self.assertEqual(len(listed), 26)
        self.assertEqual(listed[0], (datetime.date(2026, 1, 1), "Neujahr"))
        self.assertEqual([day for day, _name in listed], sorted(day for day, _name in listed))


class TimePieceTests(SimpleTestCase):
    """PER-009: a period cut into pieces with the same surcharges (``time_surcharges.time_pieces``)."""

    def test_a_day_shift_has_none(self) -> None:
        pieces = time_pieces(march(10, 8), march(10, 16), RULES)
        self.assertEqual(summary(pieces), {frozenset(): D("8.00")})

    def test_saturday_evening_into_sunday(self) -> None:
        pieces = time_pieces(march(13, 18), march(14, 3), RULES)
        self.assertEqual(
            summary(pieces),
            {
                frozenset(): D("2.00"),
                frozenset({NIGHT}): D("4.00"),
                frozenset({SUNDAY, NIGHT_AFTER_MIDNIGHT}): D("3.00"),
            },
        )
        self.assertEqual([piece.day for piece in pieces], [march(13).date()] * 2 + [march(14).date()])

    def test_work_begun_at_midnight_is_no_work_begun_before_it(self) -> None:
        pieces = time_pieces(march(14, 0), march(14, 3), RULES)
        self.assertEqual(summary(pieces), {frozenset({SUNDAY, NIGHT}): D("3.00")})
        # Begun the evening before, the same hours are "0 to 4" (§ 3b (3) EStG).
        pieces = time_pieces(march(14, 0), march(14, 3), RULES, began=march(13, 22))
        self.assertEqual(summary(pieces), {frozenset({SUNDAY, NIGHT_AFTER_MIDNIGHT}): D("3.00")})

    def test_after_four_the_night_rate_again(self) -> None:
        pieces = time_pieces(march(10, 22), march(11, 6), RULES)
        self.assertEqual(
            summary(pieces),
            {frozenset({NIGHT}): D("4.00"), frozenset({NIGHT_AFTER_MIDNIGHT}): D("4.00")},
        )

    def test_a_sunday_reaches_into_monday_morning(self) -> None:
        pieces = time_pieces(march(14, 22), march(15, 5), RULES)
        self.assertEqual(
            summary(pieces),
            {
                frozenset({SUNDAY, NIGHT}): D("2.00"),
                frozenset({SUNDAY, NIGHT_AFTER_MIDNIGHT}): D("4.00"),
                frozenset({NIGHT}): D("1.00"),
            },
        )

    def test_without_the_rule_for_work_begun_before_midnight(self) -> None:
        rules = SurchargeRules.section_3b(started_before_midnight=False)
        pieces = time_pieces(march(14, 22), march(15, 3), rules)
        self.assertEqual(summary(pieces), {frozenset({SUNDAY, NIGHT}): D("2.00"), frozenset({NIGHT}): D("3.00")})

    def test_into_summer_time_the_night_is_an_hour_shorter(self) -> None:
        pieces = time_pieces(march(27, 20), march(28, 6), RULES)
        self.assertEqual(sum(piece.hours for piece in pieces), D("9"))
        self.assertEqual(
            summary(pieces),
            {
                frozenset({NIGHT}): D("4.00"),
                frozenset({SUNDAY, NIGHT_AFTER_MIDNIGHT}): D("3.00"),  # 0:00 to 4:00 summer time
                frozenset({SUNDAY, NIGHT}): D("2.00"),
            },
        )

    def test_out_of_summer_time_the_night_is_an_hour_longer(self) -> None:
        pieces = time_pieces(moment(2027, 10, 30, 22), moment(2027, 10, 31, 6), RULES)
        self.assertEqual(sum(piece.hours for piece in pieces), D("9"))
        self.assertEqual(
            summary(pieces),
            {
                frozenset({NIGHT}): D("2.00"),
                frozenset({SUNDAY, NIGHT_AFTER_MIDNIGHT}): D("5.00"),
                frozenset({SUNDAY, NIGHT}): D("2.00"),
            },
        )

    def test_christmas_eve_and_new_years_eve_from_two_pm(self) -> None:
        pieces = time_pieces(moment(2027, 12, 24, 12), moment(2027, 12, 24, 18), RULES)
        self.assertEqual(summary(pieces), {frozenset(): D("2.00"), frozenset({HIGH_HOLIDAY}): D("4.00")})
        pieces = time_pieces(moment(2027, 12, 31, 12), moment(2028, 1, 1, 2), RULES)
        self.assertEqual(
            summary(pieces),
            {
                frozenset(): D("2.00"),
                frozenset({HOLIDAY}): D("6.00"),
                frozenset({HOLIDAY, NIGHT}): D("4.00"),
                frozenset({HOLIDAY, NIGHT_AFTER_MIDNIGHT}): D("2.00"),
            },
        )

    def test_christmas_days_and_first_of_may_are_holidays_and_high_holidays(self) -> None:
        for day in (moment(2027, 12, 25, 10), moment(2027, 12, 26, 10), moment(2027, 5, 1, 10)):
            with self.subTest(day=day):
                pieces = time_pieces(day, day + datetime.timedelta(hours=2), RULES)
                self.assertTrue({HOLIDAY, HIGH_HOLIDAY} <= pieces[0].kinds)

    def test_the_holidays_of_the_state(self) -> None:
        corpus_christi = (moment(2027, 5, 27, 10), moment(2027, 5, 27, 12))
        self.assertEqual(summary(time_pieces(*corpus_christi, RULES)), {frozenset(): D("2.00")})
        rules = SurchargeRules(state="BY")
        self.assertEqual(summary(time_pieces(*corpus_christi, rules)), {frozenset({HOLIDAY}): D("2.00")})

    def test_another_night_window(self) -> None:
        rules = SurchargeRules.section_3b(night_start=datetime.time(22, 0), night_end=datetime.time(5, 0))
        pieces = time_pieces(march(10, 20), march(11, 6), rules)
        self.assertEqual(
            summary(pieces),
            {
                frozenset(): D("3.00"),
                frozenset({NIGHT}): D("3.00"),  # 22–24 and 4–5
                frozenset({NIGHT_AFTER_MIDNIGHT}): D("4.00"),
            },
        )
        # A night window within one day.
        rules = SurchargeRules.section_3b(night_start=datetime.time(0, 0), night_end=datetime.time(5, 0))
        self.assertEqual(
            summary(time_pieces(march(10, 22), march(11, 6), rules)),
            {frozenset(): D("3.00"), frozenset({NIGHT_AFTER_MIDNIGHT}): D("4.00"), frozenset({NIGHT}): D("1.00")},
        )

    def test_an_empty_or_reversed_period_has_no_pieces(self) -> None:
        self.assertEqual(time_pieces(march(10, 8), march(10, 8), RULES), [])
        self.assertEqual(time_pieces(march(10, 9), march(10, 8), RULES), [])


class ApplyingTests(SimpleTestCase):
    """PER-009: night adds to Sunday or holiday; of Sunday and holidays the highest counts (§ 3b (1) EStG)."""

    percents = {
        NIGHT: D("25"),
        NIGHT_AFTER_MIDNIGHT: D("40"),
        SUNDAY: D("50"),
        HOLIDAY: D("125"),
        HIGH_HOLIDAY: D("150"),
    }

    def test_combinations(self) -> None:
        cases = [
            ({NIGHT}, [(NIGHT, D("25"))]),
            ({SUNDAY}, [(SUNDAY, D("50"))]),
            ({SUNDAY, HOLIDAY}, [(HOLIDAY, D("125"))]),
            ({SUNDAY, HOLIDAY, HIGH_HOLIDAY, NIGHT}, [(NIGHT, D("25")), (HIGH_HOLIDAY, D("150"))]),
            ({SUNDAY, NIGHT_AFTER_MIDNIGHT}, [(NIGHT_AFTER_MIDNIGHT, D("40")), (SUNDAY, D("50"))]),
            (set(), []),
        ]
        for kinds, expected in cases:
            with self.subTest(kinds=kinds):
                self.assertEqual(applying_kinds(kinds, self.percents), expected)

    def test_the_higher_percentage_counts_also_when_set_otherwise(self) -> None:
        percents = {**self.percents, SUNDAY: D("100"), HOLIDAY: D("80")}
        self.assertEqual(applying_kinds({SUNDAY, HOLIDAY}, percents), [(SUNDAY, D("100"))])

    def test_zero_is_no_surcharge(self) -> None:
        percents = {**self.percents, NIGHT: D("0"), HOLIDAY: D("0")}
        self.assertEqual(applying_kinds({NIGHT, HOLIDAY, SUNDAY}, percents), [(SUNDAY, D("50"))])


class PiecesOfLinesTests(SimpleTestCase):
    """PER-009 with PER-035: planned hours and approved times by surcharge and side of the limit."""

    def test_planned_hours_by_hand_are_spread_as_the_hour_tiers_spread_them(self) -> None:
        # Saturday 18:00 to Sunday 02:00 – 6 hours on Saturday, 2 on Sunday – with 4 hours typed in: 2 a day.
        pieces = planned_pieces(march(13, 18), march(14, 2), D("4"), D("8"), RULES)
        self.assertEqual(
            summary(pieces),
            {
                frozenset(): D("0.67"),
                frozenset({NIGHT}): D("1.33"),
                frozenset({SUNDAY, NIGHT_AFTER_MIDNIGHT}): D("2.00"),
            },
        )
        self.assertEqual(sum(piece.hours for piece in pieces).quantize(D("0.01")), D("4.00"))

    def test_the_hours_beyond_the_limit_are_the_last_of_the_day(self) -> None:
        pieces = planned_pieces(march(12, 12), march(13, 2), D("14"), D("14"), RULES, D("10"))
        above = [piece for piece in pieces if piece.above_limit]
        self.assertEqual([(piece.hours, piece.kinds) for piece in above], [(D("2"), frozenset({NIGHT}))])
        self.assertEqual(sum(piece.hours for piece in pieces if not piece.above_limit), D("12"))

    def test_approved_times_count_their_break_in_proportion(self) -> None:
        entries = [(march(13, 19), march(14, 1), D("5"), D("30.00"))]  # 6 hours with 1 hour break
        pieces = entry_pieces(entries, RULES)
        self.assertEqual(
            summary(pieces),
            {
                frozenset(): D("0.83"),
                frozenset({NIGHT}): D("3.33"),
                frozenset({SUNDAY, NIGHT_AFTER_MIDNIGHT}): D("0.83"),
            },
        )
        self.assertEqual({piece.rate for piece in pieces}, {D("30.00")})

    def test_approved_times_reach_the_limit_on_the_day_they_start(self) -> None:
        entries = [
            (march(12, 8), march(12, 16), D("8"), D("30.00")),
            (march(12, 18), march(12, 23), D("5"), D("32.00")),
            (march(13, 0), march(13, 2), D("2"), D("32.00")),  # a new day, a new limit
        ]
        pieces = entry_pieces(entries, RULES, D("10"))
        above = [(piece.hours, piece.kinds, piece.rate) for piece in pieces if piece.above_limit]
        self.assertEqual(above, [(D("3"), frozenset({NIGHT}), D("32.00"))])

    def test_an_entry_without_end_or_hours_counts_nothing(self) -> None:
        self.assertEqual(entry_pieces([(march(12, 8), None, D("0"), D("30"))], RULES), [])

    def test_the_parts_add_up_per_kind(self) -> None:
        pieces = [
            WorkPiece(hours=D("2"), rules=rules_of(NIGHT)),
            WorkPiece(hours=D("2"), rules=rules_of(NIGHT), above_limit=True),
            WorkPiece(hours=D("1"), rules=rules_of(SUNDAY, NIGHT_AFTER_MIDNIGHT)),
        ]
        parts = surcharge_parts(pieces, PRICE, lambda piece: D("55") if piece.above_limit else D("45"))
        self.assertEqual(
            [(part.kind, part.hours, part.amount) for part in parts],
            [
                (NIGHT, D("4.00"), D("50.00")),
                (NIGHT_AFTER_MIDNIGHT, D("1.00"), D("18.00")),
                (SUNDAY, D("1.00"), D("22.50")),
            ],
        )
        self.assertEqual(total_of(parts), D("90.50"))
        # Without a rate, no surcharge.
        self.assertEqual(surcharge_parts(pieces, PRICE, lambda piece: None), [])


class CrewLineSurchargeTests(RentalarsTestCase):
    """PER-009: price and costs of crew lines with surcharges for night, Sunday and holidays."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.function = job_function("Tontechnik", price="45.00", guide="30.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "30.00"})
        self.project = make_project(start=march(10), end=march(28, 12))

    def line(self, start: datetime.datetime, end: datetime.datetime, **fields: object) -> CrewLine:
        fields.setdefault("billing", CrewBilling.PLAN)
        return plan(self.project, self.function, self.anna, start=start, end=end, **fields)

    def test_by_plan_saturday_evening_into_sunday(self) -> None:
        line = self.line(march(13, 18), march(14, 2))
        self.assertTrue(line.time_surcharges_on_price and line.time_surcharges_on_cost)
        price = crew.price_crew_line(line)
        self.assertEqual(
            [(part.kind, part.percent, part.hours, part.amount) for part in price.time_surcharges],
            [
                (NIGHT, D("25"), D("4.00"), D("45.00")),
                (NIGHT_AFTER_MIDNIGHT, D("40"), D("2.00"), D("36.00")),
                (SUNDAY, D("50"), D("2.00"), D("45.00")),
            ],
        )
        self.assertEqual(
            (price.time_surcharge_amount, price.base_amount, price.amount), (D("126.00"), D("486.00"), D("486.00"))
        )
        self.assertEqual(price.amount_before_time_surcharges, D("360.00"))
        self.assertEqual(
            (price.cost_time_surcharge_amount, price.cost), (D("84.00"), D("324.00"))
        )  # 240 + 30 + 24 + 30

    def test_by_effort_the_estimate_and_then_the_approved_times(self) -> None:
        line = self.line(march(13, 18), march(14, 2), billing=CrewBilling.EFFORT)
        price = crew.price_crew_lines(self.project)[0]
        self.assertEqual((price.amount, price.is_estimate), (D("486.00"), True))
        record_time(self.anna, self.project, self.function, march(13, 19), march(14, 1), break_minutes=60, approve=True)
        price = crew.price_crew_lines(self.project)[0]
        self.assertEqual(price.line, line)
        self.assertEqual(price.charged_hours, D("5.00"))
        self.assertEqual(
            [(part.kind, part.hours, part.amount) for part in price.time_surcharges],
            [
                (NIGHT, D("3.33"), D("37.50")),
                (NIGHT_AFTER_MIDNIGHT, D("0.83"), D("15.00")),
                (SUNDAY, D("0.83"), D("18.75")),
            ],
        )
        self.assertEqual(price.amount, D("296.25"))  # 225 + 71.25
        # What the times cost: 5 × 30 and the surcharges of the rate fixed on the entry.
        self.assertEqual((price.actual_cost_time_surcharge_amount, price.actual_cost), (D("47.50"), D("197.50")))
        self.assertEqual(price.cost, D("324.00"))  # the planned cost stays the plan's

    def test_with_hour_tiers_the_surcharge_of_the_rate_of_that_hour(self) -> None:
        product = self.function.service_product
        product.hours_limit, product.price_above_limit = D("10"), D("55.00")
        product.save()
        personnel.set_rate(self.anna, self.function, D("30.00"), march(1).date(), hourly_rate_above_limit=D("36.00"))
        line = self.line(march(12, 12), march(13, 2))  # Friday 12 hours, Saturday 2
        price = crew.price_crew_line(line)
        self.assertEqual(price.hours_above_limit, D("2"))
        self.assertEqual(
            [(part.kind, part.hours, part.amount) for part in price.time_surcharges],
            [(NIGHT, D("4.00"), D("50.00")), (NIGHT_AFTER_MIDNIGHT, D("2.00"), D("36.00"))],  # 2 × 45 + 2 × 55
        )
        self.assertEqual(price.amount, D("736.00"))  # 10 × 45 + 2 × 55 + 2 × 45 + 86
        self.assertEqual(price.cost, D("489.00"))  # 12 × 30 + 2 × 36 + 15 + 18 + 24

    def test_hand_typed_hours(self) -> None:
        line = self.line(march(13, 18), march(14, 2), planned_hours=D("4"))
        price = crew.price_crew_line(line)
        self.assertEqual(price.time_surcharge_amount, D("96.00"))  # 15 + 36 + 45
        self.assertEqual(price.amount, D("276.00"))

    def test_a_holiday_on_a_sunday_counts_once(self) -> None:
        line = self.line(march(28, 10), march(28, 14))  # Easter Sunday, in summer time
        self.assertEqual([part.kind for part in crew.price_crew_line(line).time_surcharges], [SUNDAY])
        switch_on(state="BB")  # in Brandenburg Easter Sunday is a holiday
        price = crew.price_crew_line(line)
        self.assertEqual([(part.kind, part.amount) for part in price.time_surcharges], [(HOLIDAY, D("225.00"))])

    def test_the_last_days_of_the_year(self) -> None:
        project = make_project("Silvester", start=moment(2027, 12, 24), end=moment(2028, 1, 2))
        eve = plan(project, self.function, self.anna, start=moment(2027, 12, 24, 12), end=moment(2027, 12, 24, 18))
        self.assertEqual(
            [(part.kind, part.hours, part.amount) for part in crew.price_crew_line(eve).time_surcharges],
            [(HIGH_HOLIDAY, D("4.00"), D("270.00"))],
        )
        new_year = plan(project, self.function, self.anna, start=moment(2027, 12, 31, 12), end=moment(2028, 1, 1, 2))
        price = crew.price_crew_line(new_year)
        self.assertEqual(
            [(part.kind, part.hours, part.amount) for part in price.time_surcharges],
            [
                (NIGHT, D("4.00"), D("45.00")),
                (NIGHT_AFTER_MIDNIGHT, D("2.00"), D("36.00")),
                (HOLIDAY, D("12.00"), D("675.00")),
            ],
        )
        self.assertEqual(price.amount, D("1386.00"))

    def test_the_night_into_and_out_of_summer_time(self) -> None:
        spring = self.line(march(27, 22), march(28, 6))
        price = crew.price_crew_line(spring)
        self.assertEqual(price.planned_hours, D("7.00"))
        self.assertEqual(
            [(part.kind, part.hours) for part in price.time_surcharges],
            [(NIGHT, D("4.00")), (NIGHT_AFTER_MIDNIGHT, D("3.00")), (SUNDAY, D("5.00"))],
        )
        self.assertEqual(price.time_surcharge_amount, D("211.50"))
        project = make_project("Herbst", start=moment(2027, 10, 29), end=moment(2027, 11, 1))
        autumn = plan(project, self.function, self.anna, start=moment(2027, 10, 30, 22), end=moment(2027, 10, 31, 6))
        price = crew.price_crew_line(autumn)
        self.assertEqual(price.planned_hours, D("9.00"))
        self.assertEqual(
            [(part.kind, part.hours) for part in price.time_surcharges],
            [(NIGHT, D("4.00")), (NIGHT_AFTER_MIDNIGHT, D("5.00")), (SUNDAY, D("7.00"))],
        )
        self.assertEqual(price.time_surcharge_amount, D("292.50"))

    def test_the_discount_includes_the_surcharges(self) -> None:
        line = self.line(march(13, 18), march(14, 2), discount_percent=D("10"))
        price = crew.price_crew_line(line)
        self.assertEqual(
            (price.base_amount, price.discount_amount, price.amount), (D("486.00"), D("48.60"), D("437.40"))
        )

    def test_flat_rate_and_per_day_get_none(self) -> None:
        flat = self.line(march(13, 18), march(14, 2), billing=CrewBilling.FLAT, unit_price=D("300"))
        day = self.line(march(13, 18), march(14, 2), billing=CrewBilling.DAY, unit_price=D("400"))
        for line, amount in ((flat, D("300.00")), (day, D("800.00"))):
            with self.subTest(billing=line.billing):
                price = crew.price_crew_line(line)
                self.assertEqual((price.time_surcharges, price.amount), ([], amount))
                self.assertEqual(price.cost_time_surcharges, [])

    def test_a_flat_rate_for_the_person_has_no_cost_surcharges(self) -> None:
        line = self.line(march(13, 18), march(14, 2), cost_flat_rate=D("200"))
        price = crew.price_crew_line(line)
        self.assertEqual(
            (price.cost, price.cost_time_surcharges, price.time_surcharge_amount), (D("200.00"), [], D("126.00"))
        )

    def test_an_open_place_costs_the_guide_value_with_surcharges(self) -> None:
        line = plan(self.project, self.function, start=march(13, 18), end=march(14, 2), billing=CrewBilling.PLAN)
        price = crew.price_crew_line(line)
        self.assertEqual((price.cost, price.cost_is_guide), (D("324.00"), True))

    def test_the_switches_of_a_line(self) -> None:
        line = self.line(march(13, 18), march(14, 2))
        crew.update_crew_line(line, rights=ALL_RIGHTS, time_surcharges_on_price=False)
        price = crew.price_crew_line(line)
        self.assertEqual((price.amount, price.cost), (D("360.00"), D("324.00")))
        crew.update_crew_line(line, rights=ALL_RIGHTS, time_surcharges_on_cost=False)
        self.assertEqual(crew.price_crew_line(line).cost, D("240.00"))

    def test_the_switches_need_the_rights(self) -> None:
        line = self.line(march(13, 18), march(14, 2))
        planner = Rights(module_levels={"projects": 2, "personnel": 2})
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=planner, time_surcharges_on_price=False)
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=planner, time_surcharges_on_cost=False)

    def test_new_lines_take_the_settings_and_the_product(self) -> None:
        switch_on(price=True, costs=False)
        line = self.line(march(13, 18), march(14, 2))
        self.assertEqual((line.time_surcharges_on_price, line.time_surcharges_on_cost), (True, False))
        product = self.function.service_product
        product.time_surcharges = False
        product.save()
        line = self.line(march(13, 18), march(14, 2))
        self.assertEqual((line.time_surcharges_on_price, line.time_surcharges_on_cost), (False, False))
        self.assertEqual(crew.price_crew_line(line).amount, D("360.00"))

    def test_lines_planned_while_switched_off_stay_without(self) -> None:
        switch_on(price=False, costs=False)
        line = self.line(march(13, 18), march(14, 2))
        switch_on()
        price = crew.price_crew_line(CrewLine.objects.get(pk=line.pk))
        self.assertEqual((price.amount, price.cost, price.time_surcharges), (D("360.00"), D("240.00"), []))

    def test_changed_percentages_hold_for_every_line_at_once(self) -> None:
        line = self.line(march(13, 18), march(14, 2))
        switch_on(price_night="30", price_night_after_midnight="30", price_sunday="0")
        self.assertEqual(crew.price_crew_line(line).time_surcharge_amount, D("81.00"))  # 6 h × 45 × 30 %

    def test_the_settings_are_read_once_for_all_lines(self) -> None:
        self.line(march(13, 18), march(14, 2))
        with CaptureQueriesContext(connection) as one:
            crew.price_crew_lines(self.project)
        for _index in range(4):
            self.line(march(13, 18), march(14, 2))
        with CaptureQueriesContext(connection) as five:
            prices = crew.price_crew_lines(self.project)
        self.assertEqual(len(five), len(one))
        self.assertEqual({price.time_surcharge_amount for price in prices}, {D("126.00")})
        switch_on(price=False, costs=False)
        CrewLine.objects.update(time_surcharges_on_price=False, time_surcharges_on_cost=False)
        with CaptureQueriesContext(connection) as without:
            crew.price_crew_lines(self.project)
        # No line needs the settings: three queries fewer – settings, rules, own holidays (PER-040).
        self.assertEqual(len(without), len(one) - 3)

    def test_project_totals_and_the_list_sums(self) -> None:
        self.line(march(13, 18), march(14, 2))
        prices = compute_project_prices(self.project)
        self.assertEqual((prices.personnel_total, prices.personnel_time_surcharges), (D("486.00"), D("126.00")))
        self.assertEqual(prices.personnel_cost, D("324.00"))
        attach_sums([self.project], rights=ALL_RIGHTS, user=make_user("paula", superuser=True))
        self.assertEqual(self.project.list_sums.personnel_revenue, D("486.00"))
        self.assertEqual(self.project.list_sums.personnel_cost, D("324.00"))

    def test_the_document_names_the_surcharges(self) -> None:
        price = crew.price_crew_line(self.line(march(13, 18), march(14, 2)))
        with translation.override("de"):
            position = _crew_position("1", price)
        self.assertEqual(
            (position.quantity, position.unit_price, position.amount), (D("8.00"), D("45.00"), D("486.00"))
        )
        self.assertIn(
            "inkl. Zuschläge 126,00 €: Nacht 25 % auf 4 Std. 45,00 €, Nacht 0–4 Uhr 40 % auf 2 Std. 36,00 €, "
            "Sonntag 50 % auf 2 Std. 45,00 €",
            position.details,
        )

    def test_a_copy_of_the_project_keeps_the_switches(self) -> None:
        line = self.line(march(13, 18), march(14, 2))
        crew.update_crew_line(line, rights=ALL_RIGHTS, time_surcharges_on_cost=False)
        copy = duplicate_project(
            self.project,
            name="Stadtfest 2",
            start=march(17),
            end=march(30),
            with_crew=True,
            rights=ALL_RIGHTS,
            user=None,
        )
        copied = copy.crew_lines.get()
        self.assertEqual((copied.time_surcharges_on_price, copied.time_surcharges_on_cost), (True, False))

    def test_the_settings_refuse_a_night_without_length(self) -> None:
        # PER-040: the night is a rule of the list.
        night = TimeSurchargeRule.objects.get(code=NIGHT)
        night.time_until = night.time_from
        with self.assertRaises(ValidationError):
            night.full_clean()
        night.time_until, night.price_percent = datetime.time(6), D("501")
        with self.assertRaises(ValidationError):
            night.full_clean()
