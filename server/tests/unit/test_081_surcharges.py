# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "surcharges": surcharge rules usable in every country, own holidays (PER-040, PER-009).

The heart: the settings, turned into rules as the update does it, give exactly the surcharges as before –
checked against a frozen copy of the earlier calculation (:class:`Calculation080`) for many periods and settings.
"""

from __future__ import annotations

import datetime
import itertools
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory, SimpleTestCase
from django.test.utils import CaptureQueriesContext

from rentalars.accounts.rights import Rights
from rentalars.core.history import visible_changes
from rentalars.core.holidays import OwnHolidaySpec, calendar_of, holiday_rows, holidays_of
from rentalars.core.middleware import RequestCacheMiddleware
from rentalars.core.models import (
    AuditLogEntry,
    OwnHoliday,
    TimeSurchargeRule,
    TimeSurchargeSettings,
)
from rentalars.core.surcharge_presets import section_3b, windows_before
from rentalars.core.surcharges import load_rule_set, set_section_3b
from rentalars.projects import crew
from rentalars.projects.models import CrewBilling
from rentalars.projects.time_surcharges import (
    COST,
    PRICE,
    Rule,
    SurchargeRules,
    WorkPiece,
    applying,
    current_rules,
    surcharge_parts,
    time_pieces,
)
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    job_function,
    make_person,
    make_project,
    plan,
)

D = Decimal
BERLIN = ZoneInfo("Europe/Berlin")
CODES = ("night", "night_after_midnight", "sunday", "holiday", "high_holiday")


def moment(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime.datetime:
    """A moment in Berlin time."""
    return datetime.datetime(year, month, day, hour, minute, tzinfo=BERLIN)


# --- The calculation, frozen (projects/time_surcharges.py as) ---------------------------------


class Calculation080:
    """The surcharges as they were computed from the earlier settings – the reference for PER-040."""

    def __init__(self, *, night_start, night_end, started, state, price, cost) -> None:
        self.night_start, self.night_end, self.started, self.state = night_start, night_end, started, state
        self.percents = {PRICE: price, COST: cost}

    def is_night(self, clock: datetime.time) -> bool:
        if self.night_start == self.night_end:
            return False
        if self.night_start < self.night_end:
            return self.night_start <= clock < self.night_end
        return clock >= self.night_start or clock < self.night_end

    def day_kinds(self, day: datetime.date, clock: datetime.time) -> set[str]:
        kinds = set()
        if day.weekday() == 6:
            kinds.add("sunday")
        if day in holidays_of(day.year, self.state) or ((day.month, day.day) == (12, 31) and clock >= TWO_PM):
            kinds.add("holiday")
        if (day.month, day.day) in HIGH_DAYS or ((day.month, day.day) == (12, 24) and clock >= TWO_PM):
            kinds.add("high_holiday")
        return kinds

    def whole_day_kinds(self, day: datetime.date) -> set[str]:
        kinds = set()
        if day.weekday() == 6:
            kinds.add("sunday")
        if day in holidays_of(day.year, self.state):
            kinds.add("holiday")
        if (day.month, day.day) in HIGH_DAYS:
            kinds.add("high_holiday")
        return kinds

    def pieces(self, start: datetime.datetime, end: datetime.datetime, began: datetime.datetime | None = None):
        utc = datetime.UTC
        start, end = start.astimezone(utc), end.astimezone(utc)
        began = (began or start).astimezone(utc)
        clocks = {datetime.time(0), FOUR_AM, TWO_PM, self.night_start, self.night_end}
        found = set()
        day = start.astimezone(BERLIN).date() - datetime.timedelta(days=1)
        while day <= end.astimezone(BERLIN).date() + datetime.timedelta(days=1):
            for clock in clocks:
                for fold in (0, 1):
                    point = datetime.datetime.combine(day, clock).replace(tzinfo=BERLIN, fold=fold).astimezone(utc)
                    if start < point < end:
                        found.add(point)
            day += datetime.timedelta(days=1)
        result = []
        for first, last in itertools.pairwise([start, *sorted(found), end]):
            middle = (first + (last - first) / 2).astimezone(BERLIN)
            day, clock = middle.date(), middle.time()
            midnight = datetime.datetime.combine(day, datetime.time(0)).replace(tzinfo=BERLIN)
            early = self.started and clock < FOUR_AM and began < midnight
            kinds = self.day_kinds(day, clock)
            if early:
                kinds |= self.whole_day_kinds(day - datetime.timedelta(days=1))
            if self.is_night(clock):
                kinds.add("night_after_midnight" if early else "night")
            result.append((Decimal((last - first).total_seconds()) / Decimal(3600), frozenset(kinds)))
        return result

    def applying(self, kinds: frozenset[str], side: str) -> list[tuple[str, Decimal]]:
        percents = self.percents[side]
        result = []
        for night in ("night_after_midnight", "night"):
            if night in kinds:
                if percents[night] > 0:
                    result.append((night, percents[night]))
                break
        days = [kind for kind in ("sunday", "holiday", "high_holiday") if kind in kinds]
        if days:
            best = max(days, key=lambda kind: (percents[kind], ("sunday", "holiday", "high_holiday").index(kind)))
            if percents[best] > 0:
                result.append((best, percents[best]))
        return result

    def parts(self, start, end, side: str, rate: Decimal, began=None) -> list[tuple]:
        hours: dict[str, Decimal] = {}
        amounts: dict[str, Decimal] = {}
        for length, kinds in self.pieces(start, end, began):
            for kind, percent in self.applying(kinds, side):
                hours[kind] = hours.get(kind, D(0)) + length
                amounts[kind] = amounts.get(kind, D(0)) + length * rate * percent / 100
        return [
            (
                kind,
                self.percents[side][kind],
                hours[kind].quantize(D("0.01"), rounding=ROUND_HALF_UP),
                amounts[kind].quantize(D("0.01"), rounding=ROUND_HALF_UP),
            )
            for kind in CODES
            if kind in amounts and amounts[kind].quantize(D("0.01"), rounding=ROUND_HALF_UP) != 0
        ]


FOUR_AM, TWO_PM = datetime.time(4), datetime.time(14)
HIGH_DAYS = frozenset({(12, 25), (12, 26), (5, 1)})
LAW = {
    "night": D("25"),
    "night_after_midnight": D("40"),
    "sunday": D("50"),
    "holiday": D("125"),
    "high_holiday": D("150"),
}

#: Earlier settings to convert: night window, § 3b (3), state, percentages for price and costs.
VARIANTS = {
    "defaults": {},
    "without the rule before midnight": {"started": False},
    "night 22–5": {"night_start": datetime.time(22), "night_end": datetime.time(5)},
    "night 0–5": {"night_start": datetime.time(0), "night_end": datetime.time(5)},
    "night 1–3": {"night_start": datetime.time(1), "night_end": datetime.time(3)},
    "night 20–23": {"night_start": datetime.time(20), "night_end": datetime.time(23)},
    "night 3–1 over midnight": {"night_start": datetime.time(3), "night_end": datetime.time(1)},
    "Brandenburg": {"state": "BB"},
    "Bavaria, odd rates": {
        "state": "BY",
        "price": {
            **LAW,
            "night_after_midnight": D("10"),
            "sunday": D("100"),
            "holiday": D("100"),
            "high_holiday": D("0"),
        },
        "cost": {**LAW, "night": D("0"), "sunday": D("12.5"), "holiday": D("150"), "high_holiday": D("150")},
    },
}

#: Periods across the special days: Sundays, Christmas, New Year, 1 May, Easter, Corpus Christi, summer time.
PERIODS = [
    (moment(2027, 3, 10, 8), moment(2027, 3, 10, 16)),
    (moment(2027, 3, 13, 18), moment(2027, 3, 14, 3)),
    (moment(2027, 3, 13, 23, 30), moment(2027, 3, 14, 6, 15)),
    (moment(2027, 3, 14, 0), moment(2027, 3, 14, 3)),
    (moment(2027, 3, 14, 22), moment(2027, 3, 15, 5)),
    (moment(2027, 3, 27, 20), moment(2027, 3, 28, 6)),  # into summer time, Easter Sunday
    (moment(2027, 3, 28, 10), moment(2027, 3, 29, 2)),  # Easter Sunday into Easter Monday
    (moment(2027, 5, 26, 21), moment(2027, 5, 27, 9)),  # into Corpus Christi
    (moment(2027, 4, 30, 19, 45), moment(2027, 5, 2, 2, 10)),  # 1 May
    (moment(2027, 10, 30, 22), moment(2027, 10, 31, 6)),  # out of summer time
    (moment(2027, 12, 24, 12), moment(2027, 12, 27, 5)),  # Christmas, 70 hours
    (moment(2027, 12, 31, 12), moment(2028, 1, 1, 7)),  # New Year's Eve
    (moment(2026, 12, 24, 13, 7), moment(2026, 12, 24, 23, 59)),  # a Thursday
    (moment(2027, 12, 26, 20), moment(2027, 12, 27, 4, 30)),  # Boxing Day, a Sunday, into Monday
    (moment(2028, 1, 1, 0, 30), moment(2028, 1, 1, 2)),
]


def converted(variant: dict) -> tuple[Calculation080, SurchargeRules]:
    """The earlier calculation with these settings, and the rules the update makes of them."""
    values = {
        "night_start": datetime.time(20),
        "night_end": datetime.time(6),
        "started": True,
        "state": "",
        "price": LAW,
        "cost": LAW,
        **variant,
    }
    old = Calculation080(**values)
    rules = SurchargeRules.section_3b(
        night_start=values["night_start"],
        night_end=values["night_end"],
        started_before_midnight=values["started"],
        state=values["state"],
        price=values["price"],
        cost=values["cost"],
    )
    return old, rules


def new_parts(rules: SurchargeRules, start, end, side: str, rate: Decimal, began=None) -> list[tuple]:
    """The parts of the calculation, as tuples like :meth:`Calculation080.parts`."""
    pieces = [WorkPiece(hours=piece.hours, rules=piece.rules) for piece in time_pieces(start, end, rules, began=began)]
    return [
        (part.kind, part.percent, part.hours, part.amount) for part in surcharge_parts(pieces, side, lambda piece: rate)
    ]


class SameAs080Tests(SimpleTestCase):
    """PER-040: the converted settings give exactly the earlier surcharges – no price, cost or sum changes."""

    def test_every_variant_and_period_on_price_and_costs(self) -> None:
        checked = 0
        for name, variant in VARIANTS.items():
            old, rules = converted(variant)
            for (start, end), side, rate in itertools.product(PERIODS, (PRICE, COST), (D("45.00"), D("33.33"))):
                with self.subTest(variant=name, start=start, side=side, rate=rate):
                    self.assertEqual(new_parts(rules, start, end, side, rate), old.parts(start, end, side, rate))
                    checked += 1
        self.assertEqual(checked, len(VARIANTS) * len(PERIODS) * 4)

    def test_work_begun_the_evening_before(self) -> None:
        for name, variant in VARIANTS.items():
            old, rules = converted(variant)
            began = moment(2027, 3, 13, 22)
            with self.subTest(variant=name):
                start, end = moment(2027, 3, 14, 0), moment(2027, 3, 14, 5)
                self.assertEqual(
                    new_parts(rules, start, end, PRICE, D("45"), began), old.parts(start, end, PRICE, D("45"), began)
                )

    def test_the_rules_of_the_law(self) -> None:
        specs, until = section_3b()
        self.assertEqual(until, datetime.time(4))
        self.assertEqual(
            [(spec["code"], spec["kind"], spec["price_percent"]) for spec in specs],
            [
                ("night", "time", D("25")),
                ("night_after_midnight", "time", D("40")),
                ("sunday", "weekday", D("50")),
                ("holiday", "holiday", D("125")),
                ("holiday", "date", D("125")),
                ("high_holiday", "date", D("150")),
                ("high_holiday", "date", D("150")),
                ("high_holiday", "date", D("150")),
                ("high_holiday", "date", D("150")),
            ],
        )
        self.assertEqual([spec["position"] for spec in specs], list(range(1, 10)))

    def test_the_window_of_night_work_begun_before_midnight(self) -> None:
        t = datetime.time
        self.assertEqual(windows_before(t(20), t(6), t(4)), [(t(0), t(4))])
        self.assertEqual(windows_before(t(22), t(5), t(4)), [(t(0), t(4))])
        self.assertEqual(windows_before(t(1), t(3), t(4)), [(t(1), t(3))])
        self.assertEqual(windows_before(t(20), t(23), t(4)), [])
        self.assertEqual(windows_before(t(3), t(1), t(4)), [(t(0), t(1)), (t(3), t(4))])


# --- Rules of any country --------------------------------------------------------------------------------------


def rule(name: str, kind: str, price: str, cost: str | None = None, position: int = 0, **fields: object) -> Rule:
    """A rule made by hand."""
    return Rule(
        name=name,
        kind=kind,
        price_percent=D(price),
        cost_percent=D(cost if cost is not None else price),
        position=position,
        rule_id=position,
        **fields,
    )


#: Rules as a company in Austria might set them: own holidays, no German ones.
AUSTRIA = SurchargeRules(
    rules=(
        rule("Nacht", "time", "50", position=1, time_from=datetime.time(22), time_until=datetime.time(6)),
        rule("Samstag", "weekday", "50", position=2, weekdays="6", time_from=datetime.time(13)),
        rule("Sonntag", "weekday", "100", position=3, weekdays="7"),
        rule("Feiertag", "holiday", "100", position=4),
    ),
    german_holidays=False,
    own_holidays=(
        OwnHolidaySpec("Nationalfeiertag", "yearly", month=10, day=26),
        OwnHolidaySpec("Ostermontag", "easter", offset=1),
        OwnHolidaySpec("Betriebsfest", "once", date=datetime.date(2027, 6, 18)),
    ),
    next_day_until=None,
)


def keys(rules: SurchargeRules, start: datetime.datetime, end: datetime.datetime) -> dict:
    """Hours by the names of the rules that hold."""
    hours: dict = {}
    for piece in time_pieces(start, end, rules):
        names = frozenset(rule.name for rule in piece.rules)
        hours[names] = hours.get(names, D(0)) + piece.hours
    return {names: value.quantize(D("0.01")) for names, value in hours.items()}


class RulesOfAnyCountryTests(SimpleTestCase):
    """PER-040: time of day, weekdays, holidays and days of the year; highest day rule plus highest time rule."""

    def test_saturday_from_one_and_the_night(self) -> None:
        # Saturday 6 March 2027, 10:00 to 23:00.
        self.assertEqual(
            keys(AUSTRIA, moment(2027, 3, 6, 10), moment(2027, 3, 6, 23)),
            {frozenset(): D("3.00"), frozenset({"Samstag"}): D("9.00"), frozenset({"Samstag", "Nacht"}): D("1.00")},
        )

    def test_own_holidays_instead_of_the_german_ones(self) -> None:
        # 3 October is no holiday here, 26 October and Easter Monday are; Good Friday is not.
        self.assertEqual(
            keys(AUSTRIA, moment(2027, 10, 3, 10), moment(2027, 10, 3, 12)), {frozenset({"Sonntag"}): D("2.00")}
        )
        self.assertEqual(
            keys(AUSTRIA, moment(2027, 10, 26, 10), moment(2027, 10, 26, 12)), {frozenset({"Feiertag"}): D("2.00")}
        )
        self.assertEqual(
            keys(AUSTRIA, moment(2027, 3, 29, 10), moment(2027, 3, 29, 12)), {frozenset({"Feiertag"}): D("2.00")}
        )
        self.assertEqual(keys(AUSTRIA, moment(2027, 3, 26, 10), moment(2027, 3, 26, 12)), {frozenset(): D("2.00")})
        self.assertEqual(
            keys(AUSTRIA, moment(2027, 6, 18, 10), moment(2027, 6, 18, 12)), {frozenset({"Feiertag"}): D("2.00")}
        )

    def test_the_highest_day_rule_and_the_highest_time_rule_add_up(self) -> None:
        # Sunday 26 October 2025 – a holiday on a Sunday: 100 % once, plus the night.
        sunday_holiday = time_pieces(moment(2025, 10, 26, 22), moment(2025, 10, 26, 23), AUSTRIA)
        self.assertEqual(
            [(found.name, percent) for found, percent in applying(sunday_holiday[0].rules, PRICE)],
            [("Nacht", D("50")), ("Feiertag", D("100"))],
        )

    def test_with_the_same_percentage_the_rule_further_down_counts(self) -> None:
        first = rule("Sonntag", "weekday", "100", position=3, weekdays="7")
        second = rule("Feiertag", "holiday", "100", position=4)
        self.assertEqual(applying([second, first], PRICE), [(second, D("100"))])

    def test_price_and_costs_choose_on_their_own(self) -> None:
        sunday = rule("Sonntag", "weekday", "50", "10", position=1, weekdays="7")
        holiday = rule("Feiertag", "holiday", "25", "100", position=2)
        self.assertEqual(applying([sunday, holiday], PRICE), [(sunday, D("50"))])
        self.assertEqual(applying([sunday, holiday], COST), [(holiday, D("100"))])

    def test_a_rule_only_for_work_begun_before_midnight_replaces_the_other_time_rules(self) -> None:
        rules = SurchargeRules(
            rules=(
                rule("Nacht", "time", "25", position=1, time_from=datetime.time(20), time_until=datetime.time(6)),
                rule(
                    "Tiefe Nacht",
                    "time",
                    "10",
                    position=2,
                    time_from=datetime.time(0),
                    time_until=datetime.time(4),
                    begun_before_midnight=True,
                ),
            ),
            next_day_until=None,
        )
        self.assertEqual(
            keys(rules, moment(2027, 3, 10, 22), moment(2027, 3, 11, 5)),
            {frozenset({"Nacht"}): D("3.00"), frozenset({"Tiefe Nacht"}): D("4.00")},
        )
        # Begun at midnight: the night rule, not the one for work begun before.
        self.assertEqual(keys(rules, moment(2027, 3, 11, 0), moment(2027, 3, 11, 2)), {frozenset({"Nacht"}): D("2.00")})

    def test_the_next_day_until(self) -> None:
        sunday = rule("Sonntag", "weekday", "50", position=1, weekdays="7")
        reaching = SurchargeRules(rules=(sunday,), next_day_until=datetime.time(2))
        ending = SurchargeRules(rules=(sunday,), next_day_until=None)
        start, end = moment(2027, 3, 14, 23), moment(2027, 3, 15, 3)
        self.assertEqual(keys(reaching, start, end), {frozenset({"Sonntag"}): D("3.00"), frozenset(): D("1.00")})
        self.assertEqual(keys(ending, start, end), {frozenset({"Sonntag"}): D("1.00"), frozenset(): D("3.00")})

    def test_rules_of_the_same_name_and_percentage_are_one_part(self) -> None:
        christmas = (
            rule("Weihnachten", "date", "150", position=1, month=12, day=25),
            rule("Weihnachten", "date", "150", position=2, month=12, day=26),
            rule("Weihnachten", "date", "100", position=3, month=12, day=24, time_from=datetime.time(14)),
        )
        rules = SurchargeRules(rules=christmas, german_holidays=False, next_day_until=None)
        pieces = [
            WorkPiece(hours=p.hours, rules=p.rules)
            for p in time_pieces(moment(2027, 12, 24, 12), moment(2027, 12, 27), rules)
        ]
        parts = surcharge_parts(pieces, PRICE, lambda piece: D("10"))
        self.assertEqual(
            [(part.name, part.percent, part.hours, part.amount, part.kind) for part in parts],
            [
                ("Weihnachten", D("150"), D("48.00"), D("720.00"), "custom"),
                ("Weihnachten", D("100"), D("10.00"), D("100.00"), "custom"),
            ],
        )
        self.assertEqual(parts[0].as_dict()["rule"], 1)


class OwnHolidayTests(SimpleTestCase):
    """PER-040: own holidays – every year, once, from Easter Sunday."""

    def test_the_days(self) -> None:
        self.assertEqual(OwnHolidaySpec("x", "yearly", month=10, day=26).day_in(2027), datetime.date(2027, 10, 26))
        self.assertIsNone(OwnHolidaySpec("x", "yearly", month=2, day=29).day_in(2027))
        self.assertEqual(OwnHolidaySpec("x", "yearly", month=2, day=29).day_in(2028), datetime.date(2028, 2, 29))
        self.assertIsNone(OwnHolidaySpec("x", "once", date=datetime.date(2027, 6, 18)).day_in(2028))
        self.assertEqual(OwnHolidaySpec("x", "easter", offset=60).day_in(2027), datetime.date(2027, 5, 27))
        self.assertEqual(OwnHolidaySpec("x", "easter", offset=-2).day_in(2026), datetime.date(2026, 4, 3))

    def test_the_calendar(self) -> None:
        own = (OwnHolidaySpec("Nationalfeiertag", "yearly", month=10, day=26),)
        self.assertEqual(calendar_of(2027, "", False, own), {datetime.date(2027, 10, 26): [("Nationalfeiertag", True)]})
        both = calendar_of(2027, "BY", True, own)
        self.assertEqual(len(both), 14)
        rows = holiday_rows([2027], "", True, (OwnHolidaySpec("Neujahrsfest", "yearly", month=1, day=1),))
        self.assertEqual(
            [(str(name), is_own) for day, name, is_own in rows[:2]], [("Neujahr", False), ("Neujahrsfest", True)]
        )


# --- Stored rules, the button, the change log ------------------------------------------------------------------


class StoredRulesTests(RentalarsTestCase):
    """PER-040: rules and own holidays as stored; first use, the button, AUT-019 in the change log."""

    def test_a_new_installation_gets_the_rules_of_the_law(self) -> None:
        settings, rules, own = load_rule_set()
        self.assertTrue(settings.rules_set_up)
        self.assertEqual(settings.next_day_until, datetime.time(4))
        self.assertEqual([rule.code for rule in rules], [spec["code"] for spec in section_3b()[0]])
        self.assertEqual([rule.name for rule in rules][:3], ["Nacht", "Nacht 0–4 Uhr", "Sonntag"])
        self.assertEqual(own, [])
        self.assertEqual(current_rules().rules, tuple(Rule.of(row) for row in rules))

    def test_an_empty_list_is_no_surcharge_and_stays_empty(self) -> None:
        load_rule_set()
        for row in TimeSurchargeRule.objects.all():
            row.delete()
        self.assertEqual(current_rules().rules, ())
        self.assertEqual(TimeSurchargeRule.objects.count(), 0)

    def test_the_button_sets_the_rules_of_the_law_and_keeps_the_holidays(self) -> None:
        settings = TimeSurchargeSettings.load()
        settings.state, settings.next_day_until = "BY", None
        settings.save()
        OwnHoliday.objects.create(name="Betriebsfest", kind="once", date=datetime.date(2027, 6, 18))
        TimeSurchargeRule.objects.all().delete()
        TimeSurchargeRule.objects.create(name="Samstag", kind="weekday", weekdays="6", price_percent=D("20"))
        set_section_3b()
        settings = TimeSurchargeSettings.load()
        self.assertEqual((settings.state, settings.next_day_until), ("BY", datetime.time(4)))
        self.assertEqual(TimeSurchargeRule.objects.count(), 9)
        self.assertFalse(TimeSurchargeRule.objects.filter(name="Samstag").exists())
        self.assertEqual(OwnHoliday.objects.count(), 1)

    def test_the_change_log_hides_each_percentage_without_its_right(self) -> None:
        load_rule_set()
        night = TimeSurchargeRule.objects.get(code="night")
        night.price_percent, night.cost_percent, night.name = D("30"), D("35"), "Nachtarbeit"
        night.save()
        entry = AuditLogEntry.objects.filter(object_id=str(night.pk), action="updated").first()
        self.assertEqual(entry.parent_object_id, "1")  # in the history of the settings
        self.assertEqual(set(visible_changes(entry, ALL_RIGHTS)), {"price_percent", "cost_percent", "name"})
        self.assertEqual(
            set(visible_changes(entry, Rights(special_rights=frozenset({"prices"})))), {"price_percent", "name"}
        )
        self.assertEqual(set(visible_changes(entry, Rights())), {"name"})

    def test_the_rule_needs_the_values_of_its_kind(self) -> None:
        cases = [
            ({"kind": "time", "time_from": datetime.time(20)}, "time_until"),
            ({"kind": "time", "time_from": datetime.time(20), "time_until": datetime.time(20)}, "time_until"),
            ({"kind": "weekday"}, "weekdays"),
            ({"kind": "date", "day": 30, "month": 2}, "day"),
            ({"kind": "date"}, "day"),
        ]
        for values, field in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValidationError) as caught:
                    TimeSurchargeRule(name="x", **values).full_clean()
                self.assertIn(field, caught.exception.message_dict)
        # The values of the other kinds are emptied.
        holiday = TimeSurchargeRule(
            name="Feiertag", kind="holiday", time_until=datetime.time(3), weekdays="7", day=1, month=1
        )
        holiday.full_clean()
        self.assertEqual((holiday.time_until, holiday.weekdays, holiday.day), (None, "", None))
        leap = TimeSurchargeRule(name="Schalttag", kind="date", day=29, month=2)
        leap.full_clean()

    def test_an_own_holiday_needs_its_value(self) -> None:
        for kind, field in (("yearly", "day"), ("once", "date"), ("easter", "easter_offset")):
            with self.subTest(kind=kind), self.assertRaises(ValidationError) as caught:
                OwnHoliday(name="x", kind=kind).full_clean()
            self.assertIn(field, caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            OwnHoliday(name="x", kind="easter", easter_offset=300).full_clean()

    def test_the_rules_are_read_once_for_a_request(self) -> None:
        load_rule_set()
        seen = []

        def view(request):
            with CaptureQueriesContext(connection) as queries:
                current_rules()
                current_rules()
            seen.append(len(queries))
            from django.http import HttpResponse

            return HttpResponse("")

        RequestCacheMiddleware(view)(RequestFactory().get("/"))
        self.assertLessEqual(seen[0], 3)

    def test_a_crew_line_with_rules_of_another_country(self) -> None:
        settings = TimeSurchargeSettings.load()
        settings.on_price = settings.on_costs = True
        settings.german_holidays = False
        settings.save()
        for row in TimeSurchargeRule.objects.all():
            row.delete()
        TimeSurchargeRule.objects.create(
            name="Samstag", kind="weekday", weekdays="6", time_from=datetime.time(13), price_percent=D("50"), position=1
        )
        OwnHoliday.objects.create(name="Nationalfeiertag", kind="yearly", day=26, month=10)
        TimeSurchargeRule.objects.create(
            name="Feiertag", kind="holiday", price_percent=D("100"), cost_percent=D("100"), position=2
        )
        function = job_function("Tontechnik", price="40.00", guide="30.00")
        anna = make_person("Anna Becker", rates={"Tontechnik": "30.00"})
        project = make_project(start=moment(2027, 3, 1), end=moment(2027, 10, 30))
        saturday = plan(
            project, function, anna, start=moment(2027, 3, 6, 10), end=moment(2027, 3, 6, 18), billing=CrewBilling.PLAN
        )
        price = crew.price_crew_line(saturday)
        self.assertEqual(
            [(part.name, part.hours, part.amount) for part in price.time_surcharges],
            [("Samstag", D("5.00"), D("100.00"))],
        )
        self.assertEqual((price.amount, price.cost_time_surcharges), (D("420.00"), []))  # 0 % on the costs
        national = plan(
            project,
            function,
            anna,
            start=moment(2027, 10, 26, 8),
            end=moment(2027, 10, 26, 12),
            billing=CrewBilling.PLAN,
        )
        price = crew.price_crew_line(national)
        self.assertEqual([(part.name, part.amount) for part in price.time_surcharges], [("Feiertag", D("160.00"))])
        self.assertEqual(price.cost_time_surcharge_amount, D("120.00"))
        unity = plan(
            project, function, anna, start=moment(2027, 10, 3, 8), end=moment(2027, 10, 3, 12), billing=CrewBilling.PLAN
        )
        self.assertEqual(crew.price_crew_line(unity).time_surcharges, [])  # a Sunday, but no rule for it here


# --- The update ------------------------------------------------------------------------------------------------
