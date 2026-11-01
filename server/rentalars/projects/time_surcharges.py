# SPDX-License-Identifier: GPL-3.0-or-later
"""Surcharges for night, Sunday and holiday work on crew lines (PER-009; PER-040).

The requirement: surcharges (night, Sunday and holiday) – for the
price the customer pays and for the personnel costs, in the style of the
hour tiers (PER-035, ``projects.hour_tiers``). Usable internationally, with a button that adapts them to § 3b EStG.

Where the values come from
--------------------------
Einstellungen → Zuschläge holds a list of rules (``core.models.TimeSurchargeRule``),
each with a percentage for the price and one for the costs:

* **time of day** – a window, over midnight if it ends earlier than it
  begins (night 20:00–06:00); optionally only for work begun before
  midnight, and then instead of the other time-of-day rules;
* **weekday(s)** – e.g. Sunday, or Saturday from 13:00;
* **public holiday** – the statutory holidays of a German federal state
  (``core.holidays``, computed, no network) and/or the company's own ones;
* **a day of the year**, from a time if wanted – 24.12. from 14:00.

How they add up – the logic of § 3b EStG (§ 3b (1) "vorbehaltlich", R 3b
LStR), stated generally: of the rules of the "day" kinds (weekday, holiday,
day of the year) only the highest percentage counts; of the time-of-day rules
too; the two add up. Example with the rules of the law: a holiday on a
Sunday at 22:00 → night 25 % + holiday 125 % = 150 %. With the same
percentage the rule further down the list counts.

A further setting ``next_day_until`` (§ 3b (3) Nr. 2: 04:00): for work begun
before midnight a day with a surcharge reaches until that time of the next
day – every rule of the day kinds that held at the end of the day before
holds then too. Work "begins" at the start of the crew line's period, or of
the time entry.

The button "Nach § 3b EStG einstellen" (``core.surcharge_presets.section_3b``)
sets the rules of the law, which give exactly the surcharges.

==========================================  ======  =====================
rule of the law                             rate    § 3b EStG
==========================================  ======  =====================
night, 20:00 to 06:00                       25 %    (1) Nr. 1, (2)
night 00:00 to 04:00, begun before 00:00    40 %    (3) Nr. 1
Sunday                                      50 %    (1) Nr. 2
holiday, and 31 December from 14:00         125 %   (1) Nr. 3
24 December from 14:00, 25 and 26           150 %   (1) Nr. 4
December, 1 May
==========================================  ======  =====================

Rules with the same name and percentage are one kind of surcharge
(:class:`SurchargePart`): "Feiertag" is the holidays and 31 December from
14:00.

Which lines
-----------
Only crew lines billed by the hour – "by plan" and "by effort" –, never a
flat rate or a line billed per day (PER-029), as with the hour tiers. A line
carries two switches, ``time_surcharges_on_price`` and
``time_surcharges_on_cost``: a new line takes them from the settings and its
service product (a product can exclude its lines), and the planner may change
them; older lines have none.

Which hours – counted per period of time
-----------------------------------------
* **By plan** (and "by effort" while no time is approved): the planned period
  of the line, cut at every boundary – midnight, 04:00, 14:00 and every time
  of a rule. Planned hours other than the length of the period (typed in by
  hand) are spread over the calendar days as the hour tiers do it (evenly);
  within a day, the period's pieces count in proportion. Example: Monday
  08:00 to Tuesday 20:00 with 20 planned hours – 10 on each day; Monday's 16
  hours of period hold 4 night hours, so 2.5 of the 10 are night hours.
* **By effort**: each approved time entry with its own period; its break
  (ZEI-009) is taken off in proportion over the entry's period.

Hours are the hours that really pass: the night into summer time is an hour
shorter, the night out of it an hour longer.

With hour tiers (PER-035) the surcharge is a percentage of the rate that holds
for that hour: below the limit of the day the price (or cost rate) per hour,
beyond it the price (or cost rate) from the limit. The hours of a day beyond
the limit are its last ones – for an approved time, the last hours of the
entries of the day its start falls on, as PER-035 counts them.

The functions here are plain arithmetic on what the caller loaded; only
:func:`current_rules` reads the settings.
"""

from __future__ import annotations

import datetime
import itertools
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.utils import timezone

from rentalars.core import surcharge_presets as presets
from rentalars.core.holidays import NATIONWIDE, OwnHolidaySpec, calendar_of
from rentalars.core.money import money
from rentalars.projects.hour_tiers import local_days, planned_hours_per_day

ZERO = Decimal("0")
HUNDRED = Decimal("100")
HOUR = Decimal(3600)

#: The sides a percentage is for.
PRICE = "price"
COST = "cost"

#: The kinds of rule.
TIME, WEEKDAY, HOLIDAY_RULE, DATE = presets.TIME, presets.WEEKDAY, presets.HOLIDAY, presets.DATE
DAY_RULE_KINDS = presets.DAY_KINDS

#: The kinds of surcharge – the codes of the rules of § 3b EStG (``core.surcharge_presets``).
NIGHT = presets.NIGHT
NIGHT_AFTER_MIDNIGHT = presets.NIGHT_AFTER_MIDNIGHT
SUNDAY = presets.SUNDAY
HOLIDAY = presets.HOLIDAY_CODE
HIGH_HOLIDAY = presets.HIGH_HOLIDAY
KINDS = presets.CODES
#: The kind of a surcharge from a rule made by hand, in the API.
CUSTOM = "custom"

#: § 3b (3) EStG: until this hour, night work begun before midnight counts as such.
EARLY_MORNING_END = presets.EARLY_MORNING_END
#: § 3b (1) Nr. 3 and 4 EStG: 24 and 31 December count from this hour.
AFTERNOON = presets.AFTERNOON
#: Times at which a period is always cut, whatever the rules – those, so that its sums stay exact.
_FIXED_CLOCKS = frozenset({datetime.time(0, 0), EARLY_MORNING_END, AFTERNOON})
_END_OF_DAY = datetime.time(23, 59, 59, 999999)


@dataclass(frozen=True)
class Rule:
    """One rule of the surcharges (PER-040) – the values of ``core.models.TimeSurchargeRule``."""

    name: str
    kind: str
    price_percent: Decimal = ZERO
    cost_percent: Decimal = ZERO
    #: TIME: the window begins; the other kinds: from this time of the day on (``None``: the whole day).
    time_from: datetime.time | None = None
    #: TIME: the window ends.
    time_until: datetime.time | None = None
    #: WEEKDAY: ISO weekdays, "67" Saturday and Sunday.
    weekdays: str = ""
    month: int | None = None
    day: int | None = None
    #: TIME: only for work begun before midnight – and then instead of the other time-of-day rules.
    begun_before_midnight: bool = False
    #: The kind for the rules of § 3b EStG, else "".
    code: str = ""
    position: int = 0
    rule_id: int | None = None

    @classmethod
    def of(cls, row: Any) -> Rule:
        """The rule of a ``TimeSurchargeRule`` row."""
        return cls(
            name=row.name,
            kind=row.kind,
            price_percent=row.price_percent,
            cost_percent=row.cost_percent,
            time_from=row.time_from,
            time_until=row.time_until,
            weekdays=row.weekdays,
            month=row.month,
            day=row.day,
            begun_before_midnight=row.begun_before_midnight,
            code=row.code,
            position=row.position,
            rule_id=row.pk,
        )

    @property
    def key(self) -> str:
        """What names the rule in a :class:`TimePiece`: the code, else ``rule-<id>``."""
        return self.code or f"rule-{self.rule_id if self.rule_id is not None else self.position}"

    @property
    def order(self) -> tuple[int, int]:
        """The place in the list: position, then the order of creation."""
        return (self.position, self.rule_id or 0)

    @property
    def is_day_rule(self) -> bool:
        """Weekday, holiday or day of the year: of these only the highest counts."""
        return self.kind in DAY_RULE_KINDS

    def percent(self, side: str) -> Decimal:
        """The percentage for the price or for the costs."""
        return self.price_percent if side == PRICE else self.cost_percent

    def clocks(self) -> set[datetime.time]:
        """The times of day at which the rule may begin or end."""
        return {clock for clock in (self.time_from, self.time_until) if clock is not None}

    def in_window(self, clock: datetime.time) -> bool:
        """TIME: whether a time of day lies in the window; it may reach over midnight (20:00 to 06:00)."""
        start, end = self.time_from, self.time_until
        if start is None or end is None or start == end:
            return False
        if start < end:
            return start <= clock < end
        return clock >= start or clock < end

    def holds_on(self, day: datetime.date, clock: datetime.time, rules: SurchargeRules) -> bool:
        """Day kinds: whether the rule holds at this moment (``time_from`` included)."""
        if self.time_from is not None and clock < self.time_from:
            return False
        if self.kind == WEEKDAY:
            return str(day.isoweekday()) in self.weekdays
        if self.kind == HOLIDAY_RULE:
            return rules.is_holiday(day)
        if self.kind == DATE:
            return (day.month, day.day) == (self.month, self.day)
        return False


def _section_3b_rules(**options: Any) -> tuple[Rule, ...]:
    """The rules of § 3b EStG (``core.surcharge_presets.section_3b``) for the calculation."""
    specs, _until = presets.section_3b(**options)
    return tuple(Rule(**spec) for spec in specs)


@dataclass(frozen=True)
class SurchargeRules:
    """What decides about the surcharges: the rules, the holidays, the next day (PER-040).

    ``SurchargeRules()`` are the rules of § 3b EStG with the holidays of the
    whole of Germany – the defaults; :meth:`section_3b` builds them
    with other values of the settings.
    """

    rules: tuple[Rule, ...] = field(default_factory=_section_3b_rules)
    #: The federal state whose holidays count (``core.holidays``); "" for those of the whole country.
    state: str = NATIONWIDE
    #: Whether the statutory holidays of Germany count at all.
    german_holidays: bool = True
    own_holidays: tuple[OwnHolidaySpec, ...] = ()
    #: § 3b (3) Nr. 2 EStG: for work begun before midnight, the day rules of the day before hold until then.
    next_day_until: datetime.time | None = EARLY_MORNING_END

    @classmethod
    def section_3b(
        cls,
        *,
        night_start: datetime.time = presets.DEFAULT_NIGHT_START,
        night_end: datetime.time = presets.DEFAULT_NIGHT_END,
        started_before_midnight: bool = True,
        state: str = NATIONWIDE,
        price: Mapping[str, Decimal] | None = None,
        cost: Mapping[str, Decimal] | None = None,
    ) -> SurchargeRules:
        """The rules of the settings – night window, § 3b (3), federal state, percentages by kind."""
        specs, until = presets.section_3b(
            night_start=night_start,
            night_end=night_end,
            started_before_midnight=started_before_midnight,
            price=price,
            cost=cost,
        )
        return cls(rules=tuple(Rule(**spec) for spec in specs), state=state, next_day_until=until)

    @classmethod
    def from_rows(cls, settings: Any, rows: Iterable[Any], own: Iterable[Any] = ()) -> SurchargeRules:
        """The rules as stored (``core.surcharges.load_rule_set``)."""
        return cls(
            rules=tuple(Rule.of(row) for row in rows),
            state=settings.state,
            german_holidays=settings.german_holidays,
            own_holidays=tuple(holiday.spec() for holiday in own),
            next_day_until=settings.next_day_until,
        )

    def is_holiday(self, day: datetime.date) -> bool:
        """Whether a day is a holiday: statutory (if they count) or own."""
        return day in calendar_of(day.year, self.state, self.german_holidays, self.own_holidays)

    def clocks(self) -> set[datetime.time]:
        """Every time of day at which a surcharge may begin or end."""
        found = set(_FIXED_CLOCKS)
        for rule in self.rules:
            found |= rule.clocks()
        if self.next_day_until is not None:
            found.add(self.next_day_until)
        return found

    def applying_at(self, day: datetime.date, clock: datetime.time, began_before_midnight: bool) -> tuple[Rule, ...]:
        """The rules that hold at a moment, before choosing the highest (:func:`applying`).

        Args:
            day: The local day.
            clock: The local time of day.
            began_before_midnight: Whether the work began before 00:00 of ``day``.
        """
        times = [
            rule
            for rule in self.rules
            if rule.kind == TIME and rule.in_window(clock) and (began_before_midnight or not rule.begun_before_midnight)
        ]
        if any(rule.begun_before_midnight for rule in times):
            # § 3b (3) Nr. 1: 40 % from 0 to 4 o'clock instead of the 25 % of the night.
            times = [rule for rule in times if rule.begun_before_midnight]
        early = began_before_midnight and self.next_day_until is not None and clock < self.next_day_until
        before = day - datetime.timedelta(days=1)
        days = [
            rule
            for rule in self.rules
            if rule.is_day_rule
            and (rule.holds_on(day, clock, self) or (early and rule.holds_on(before, _END_OF_DAY, self)))
        ]
        return tuple(sorted({*times, *days}, key=lambda rule: (rule.order, rule.name)))


def current_rules() -> SurchargeRules:
    """The rules as set in the settings – read once for the request (``core.surcharges.load_rule_set``)."""
    from rentalars.core.surcharges import load_rule_set

    return SurchargeRules.from_rows(*load_rule_set())


@dataclass(frozen=True)
class TimePiece:
    """A stretch of a period within which every surcharge stays the same."""

    #: The local calendar day the piece lies on.
    day: datetime.date
    #: The hours that really pass in it.
    hours: Decimal
    #: The rules that hold in it (:meth:`SurchargeRules.applying_at`).
    rules: tuple[Rule, ...] = ()

    @property
    def kinds(self) -> frozenset[str]:
        """The keys of the rules – for the rules of § 3b EStG the kinds (``night``, ``sunday`` …)."""
        return frozenset(rule.key for rule in self.rules)


@dataclass(frozen=True)
class WorkPiece:
    """Worked or planned hours with the same surcharges, rate and side of the limit of the day (PER-035)."""

    hours: Decimal
    rules: tuple[Rule, ...] = ()
    #: PER-035: whether these hours lie beyond the limit of hours of their day.
    above_limit: bool = False
    #: The cost rate fixed on the time entry (ZEI-008); ``None`` for planned hours.
    rate: Decimal | None = None

    @property
    def kinds(self) -> frozenset[str]:
        """The keys of the rules (:attr:`TimePiece.kinds`)."""
        return frozenset(rule.key for rule in self.rules)


def _boundaries(start: datetime.datetime, end: datetime.datetime, rules: SurchargeRules) -> list[datetime.datetime]:
    """The moments between start and end at which a surcharge may begin or end, in UTC and in order."""
    zone = timezone.get_current_timezone()
    clocks = rules.clocks()
    first = timezone.localtime(start).date() - datetime.timedelta(days=1)
    last = timezone.localtime(end).date() + datetime.timedelta(days=1)
    found = set()
    day = first
    while day <= last:
        for clock in clocks:
            naive = datetime.datetime.combine(day, clock)
            # Both readings of a clock time the change from summer time repeats.
            for fold in (0, 1):
                moment = naive.replace(tzinfo=zone, fold=fold).astimezone(datetime.UTC)
                if start < moment < end:
                    found.add(moment)
        day += datetime.timedelta(days=1)
    return sorted(found)


def time_pieces(
    start: datetime.datetime, end: datetime.datetime, rules: SurchargeRules, *, began: datetime.datetime | None = None
) -> list[TimePiece]:
    """Cut a period into pieces that each have the same surcharges, in order (PER-009, PER-040).

    Args:
        start: Begin of the period.
        end: End of the period.
        rules: The settings.
        began: When the work began, for work begun before midnight; default ``start``.

    Example with the rules of § 3b EStG: Saturday 18:00 to Sunday 03:00 →
    Saturday 18–20 nothing, 20–24 night, Sunday 0–3 Sunday and night "0 to 4".
    """
    if not start or not end or end <= start:
        return []
    zone = timezone.get_current_timezone()
    start, end = start.astimezone(datetime.UTC), end.astimezone(datetime.UTC)
    began = (began or start).astimezone(datetime.UTC)
    cuts = [start, *_boundaries(start, end, rules), end]
    pieces = []
    for piece_start, piece_end in itertools.pairwise(cuts):
        middle = (piece_start + (piece_end - piece_start) / 2).astimezone(zone)
        day, clock = middle.date(), middle.time()
        midnight = timezone.make_aware(datetime.datetime.combine(day, datetime.time(0, 0)), zone)
        # The day of the piece is that of its start, as the hour tiers count (``hour_tiers.local_days``).
        pieces.append(
            TimePiece(
                day=timezone.localtime(piece_start, zone).date(),
                hours=Decimal((piece_end - piece_start).total_seconds()) / HOUR,
                rules=rules.applying_at(day, clock, began < midnight),
            )
        )
    return pieces


def _split_at_limit(
    hours: Decimal, rules: tuple[Rule, ...], used: Decimal, limit: Decimal | None, rate: Decimal | None = None
) -> list[WorkPiece]:
    """One stretch of hours of a day, of which ``used`` went before: the part up to the limit and the rest."""
    if limit is None:
        return [WorkPiece(hours=hours, rules=rules, rate=rate)]
    within = max(min(hours, limit - used), ZERO)
    pieces = []
    if within > ZERO:
        pieces.append(WorkPiece(hours=within, rules=rules, rate=rate))
    if hours - within > ZERO:
        pieces.append(WorkPiece(hours=hours - within, rules=rules, above_limit=True, rate=rate))
    return pieces


def planned_pieces(
    start: datetime.datetime | None,
    end: datetime.datetime | None,
    planned: Decimal,
    period_hours: Decimal,
    rules: SurchargeRules,
    limit: Decimal | None = None,
) -> list[WorkPiece]:
    """The planned hours of a crew line, by surcharge and side of the limit (PER-009, PER-035).

    Args:
        start: Begin of the line's period.
        end: End of the line's period.
        planned: The planned hours.
        period_hours: The hours suggested for the period (``CrewLine.period_hours``).
        rules: The settings.
        limit: PER-035: the limit of hours per day, if the line has hour tiers.

    The hours of each calendar day are those of ``hour_tiers.planned_hours_per_day``;
    the pieces of the period on that day share them in proportion to their length.
    """
    if not start or not end or end <= start or planned <= ZERO:
        return []
    days = local_days(start, end)
    shares = planned_hours_per_day(start, end, planned, period_hours)
    if len(shares) != len(days):
        return []
    factor = {day: share / hours for (day, hours), share in zip(days, shares, strict=True) if hours > ZERO}
    used: dict[datetime.date, Decimal] = {}
    result: list[WorkPiece] = []
    for piece in time_pieces(start, end, rules):
        hours = piece.hours * factor.get(piece.day, ZERO)
        if hours <= ZERO:
            continue
        before = used.get(piece.day, ZERO)
        used[piece.day] = before + hours
        result.extend(_split_at_limit(hours, piece.rules, before, limit))
    return result


def entry_pieces(
    entries: Iterable[tuple[datetime.datetime, datetime.datetime | None, Decimal, Decimal]],
    rules: SurchargeRules,
    limit: Decimal | None = None,
) -> list[WorkPiece]:
    """Approved times, by surcharge and side of the limit (PER-009, PER-035, ZEI-021).

    Args:
        entries: ``(start, end, hours, hourly rate)`` of each entry, in the order of their start.
        rules: The settings.
        limit: PER-035: the limit of hours per day, if the line has hour tiers.

    An entry's hours count on the day it starts (PER-035); its break is
    taken off its pieces in proportion. Each piece keeps the entry's rate.
    """
    used: dict[datetime.date, Decimal] = {}
    result: list[WorkPiece] = []
    for start, end, hours, rate in entries:
        if end is None or end <= start or hours <= ZERO:
            continue
        pieces = time_pieces(start, end, rules)
        length = sum((piece.hours for piece in pieces), ZERO)
        if length <= ZERO:
            continue
        day = timezone.localtime(start).date()
        for piece in pieces:
            share = piece.hours * hours / length
            before = used.get(day, ZERO)
            used[day] = before + share
            result.extend(_split_at_limit(share, piece.rules, before, limit, rate))
    return result


@dataclass(frozen=True)
class SurchargePart:
    """One kind of surcharge of a crew line: on how many hours, at which percentage, how much (PER-009).

    A kind is the rules of the same name and percentage (PER-040).
    """

    name: str
    percent: Decimal
    hours: Decimal
    amount: Decimal
    #: The code (``night`` …) for the rules of § 3b EStG, else :data:`CUSTOM`.
    kind: str = CUSTOM
    #: The first rule of the kind.
    rule_id: int | None = None

    @property
    def label(self) -> str:
        """The name of the kind, e.g. "Nacht"."""
        return self.name

    @property
    def short_label(self) -> str:
        """The name for the planning and a document."""
        return self.name

    def as_dict(self) -> dict[str, Any]:
        """For the API."""
        return {
            "kind": self.kind,
            "rule": self.rule_id,
            "label": self.label,
            "percent": self.percent,
            "hours": self.hours,
            "amount": self.amount,
        }


def applying(rules: Iterable[Rule], side: str) -> list[tuple[Rule, Decimal]]:
    """The surcharges that count for hours under these rules, with their percentages (§ 3b (1) EStG, PER-040).

    The highest time-of-day rule adds to the highest of the day rules; with
    the same percentage the rule further down the list counts; a percentage
    of 0 is no surcharge. Example with the rules of the law: Sunday, holiday
    and night → ``[(night, 25), (holiday, 125)]``.
    """
    rules = list(rules)
    result = []
    for group in ([rule for rule in rules if not rule.is_day_rule], [rule for rule in rules if rule.is_day_rule]):
        if group:
            best = max(group, key=lambda rule: (rule.percent(side), rule.order))
            if best.percent(side) > ZERO:
                result.append((best, best.percent(side)))
    return result


def surcharge_parts(
    pieces: Iterable[WorkPiece], side: str, base: Callable[[WorkPiece], Decimal | None]
) -> list[SurchargePart]:
    """Add up the surcharges of some hours per kind (PER-009, PER-040).

    Args:
        pieces: The hours (:func:`planned_pieces`, :func:`entry_pieces`).
        side: :data:`PRICE` or :data:`COST` – which percentages count.
        base: The rate a piece's surcharge is a percentage of – the price or
            cost rate per hour that holds for it (PER-035); ``None``: no rate,
            no surcharge.

    Returns:
        One part per kind (the rules of the same name and percentage) with an
        amount, in the order of the rules; hours to two places, amounts to
        cents. The amounts of the parts add up to the surcharge of the line.
    """
    hours: dict[tuple[str, Decimal], Decimal] = {}
    amounts: dict[tuple[str, Decimal], Decimal] = {}
    first: dict[tuple[str, Decimal], Rule] = {}
    for piece in pieces:
        rate = base(piece)
        if rate is None:
            continue
        for rule, percent in applying(piece.rules, side):
            key = (rule.name, percent)
            if key not in first or rule.order < first[key].order:
                first[key] = rule
            hours[key] = hours.get(key, ZERO) + piece.hours
            amounts[key] = amounts.get(key, ZERO) + piece.hours * rate * percent / HUNDRED
    parts = []
    for key in sorted(amounts, key=lambda key: first[key].order):
        if money(amounts[key]) == ZERO:
            continue
        rule = first[key]
        parts.append(
            SurchargePart(
                name=rule.name,
                percent=key[1],
                hours=hours[key].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                amount=money(amounts[key]),
                kind=rule.code or CUSTOM,
                rule_id=rule.rule_id,
            )
        )
    return parts


def total_of(parts: Iterable[SurchargePart]) -> Decimal:
    """The sum of the parts, in cents."""
    return money(sum((part.amount for part in parts), ZERO))
