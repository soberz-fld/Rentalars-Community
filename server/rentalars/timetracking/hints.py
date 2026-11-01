# SPDX-License-Identifier: GPL-3.0-or-later
"""Hints at conspicuous time entries: a long working day, a short break, a short rest (ZEI-018).

The limits follow the German working time act and are settings
(``SystemSettings.time_hint_*``):

* **Long working day** (ArbZG § 3): more than 10 hours of work on one
  working day.
* **Short break** (ArbZG § 4): more than 6 hours of work need 30 minutes
  of break, more than 9 hours 45 minutes.
* **Short rest** (ArbZG § 5): less than 11 hours between the end of one
  working day and the begin of the next.

The hints are never blocking: an entry is saved, handed in and approved
like any other. One switch of the settings shows or hides all
of them (``SystemSettings.time_hints_enabled``): off, no hint appears
anywhere – entry, approval, report, CSV, API – and the limits are kept. They appear where times are entered (the confirmation of
the quick entry, "My times"), in the approval and in the report – with
the API (``hints`` of every time entry) and in the CSV file.

What an entry stores
--------------------
A time entry has a begin, an end and *one* number of break minutes; when
the break was taken is not known. A working day is therefore judged as a
whole:

* Its **hours of work** are the hours of its entries (begin to end minus
  the break, as stored on the entry).
* Its **break** is the break minutes of its entries plus the gaps between
  them – a gap counts if it lasts at least 15 minutes, the shortest break
  the act counts (§ 4).

Which entries form a working day
--------------------------------
The entries of a person in the order of their begin. The next entry
belongs to the same working day as the one before, unless

* the gap before it is at least the rest of the settings (11 hours), or
* the gap is at least 3 hours *and* it begins on another calendar day than
  the working day began.

So two entries of the same day with a lunch break are one working day; a
load-in in the morning and the show in the evening are one working day of
both; a night shift 22:00–06:00 is one working day although it ends on the
next date; an entry 18:00–23:00 and another 00:30–03:00 are one; and the
shift of the next morning is a new working day – whose rest since the
previous one is checked.

Long working day and short break concern every entry of the working day;
a short rest concerns the first entry of the later working day. Entries
that were sent back (rejected) and a running stopwatch do not count.
Entries in projects the reader may not see still count for the hints of the
entries the reader sees: the working day of the person is one, wherever
they worked – the hint says how long, not where.

Example: Monday 08:00–20:00 with 30 minutes of break is 11.5 hours of work
→ "long working day". Tuesday 06:00 again is a new working day after 10
hours → "short rest".
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_decimal
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus

#: A gap at least this long between two entries on different calendar days is a rest, not a break.
NIGHT_GAP = datetime.timedelta(hours=3)

#: A gap counts as break only if it lasts at least this long (ArbZG § 4: breaks of at least 15 minutes).
SHORTEST_BREAK = datetime.timedelta(minutes=15)

#: The rest that separates two working days when the hint at short rests is switched off.
DEFAULT_REST = datetime.timedelta(hours=11)

#: How far before and after the asked entries the other entries of the people are read, so that the
#: working day and the rest before it are complete.
CONTEXT = datetime.timedelta(days=2)


class HintKind:
    """The three kinds of hints (ZEI-018)."""

    LONG_DAY = "long_day"
    SHORT_BREAK = "short_break"
    SHORT_REST = "short_rest"


@dataclass(frozen=True)
class TimeHint:
    """One hint at an entry: its kind and the sentence shown."""

    kind: str
    message: str


@dataclass(frozen=True)
class HintLimits:
    """The limits of the settings; a limit of 0 switches its hint off."""

    day_hours: Decimal = Decimal("10")
    break_hours: Decimal = Decimal("6")
    break_minutes: int = 30
    long_break_hours: Decimal = Decimal("9")
    long_break_minutes: int = 45
    rest_hours: Decimal = Decimal("11")
    #: The switch "show hints at working times" of the settings; off, no hint at all.
    enabled: bool = True

    @classmethod
    def load(cls) -> HintLimits:
        """The limits as set in the settings (``SystemSettings``)."""
        from rentalars.core.models import SystemSettings

        settings = SystemSettings.load()
        return cls(
            day_hours=settings.time_hint_day_hours,
            break_hours=settings.time_hint_break_hours,
            break_minutes=settings.time_hint_break_minutes,
            long_break_hours=settings.time_hint_long_break_hours,
            long_break_minutes=settings.time_hint_long_break_minutes,
            rest_hours=settings.time_hint_rest_hours,
            enabled=settings.time_hints_enabled,
        )

    @property
    def any(self) -> bool:
        """Whether any hint is switched on – and the hints at all."""
        return self.enabled and bool(self.day_hours or self.break_minutes or self.long_break_minutes or self.rest_hours)

    @property
    def rest(self) -> datetime.timedelta:
        """The rest that separates working days."""
        return datetime.timedelta(hours=float(self.rest_hours)) if self.rest_hours else DEFAULT_REST

    def break_needed(self, worked: Decimal) -> int:
        """The minutes of break the hours of work of a working day need; 0: none."""
        needed = 0
        if self.break_minutes and worked > self.break_hours:
            needed = self.break_minutes
        if self.long_break_minutes and worked > self.long_break_hours:
            needed = max(needed, self.long_break_minutes)
        return needed


@dataclass(slots=True)
class Span:
    """What the hints need of a time entry – read as plain values, not as model objects (NFA-012).

    The report of a month asks for the hints of a few thousand entries; making a model object of each
    entry around them cost more than the hints themselves.
    """

    pk: int
    person_id: int
    start: datetime.datetime
    end: datetime.datetime | None
    break_minutes: int
    hours: Decimal
    #: ZEI-025: the key of the period the entry is a part of; ``None`` for an entry that is not divided.
    period_key: Any = None
    #: ZEI-025: the IDs of the parts a span of a whole period stands for.
    members: list[int] = field(default_factory=list)

    @classmethod
    def of(cls, entry: Any) -> Span:
        """The span of a time entry object – the caller's, with changes that may not be saved yet."""
        return cls(
            entry.pk,
            entry.person_id,
            entry.start,
            entry.end,
            entry.break_minutes or 0,
            entry.hours,
            getattr(entry, "period_key", None),
        )


def whole_periods(spans: Iterable[Span]) -> list[Span]:
    """ZEI-025: the parts of a divided period as one span – its hours added up, its break once.

    The parts of a period share begin, end and break; counted one by one, a
    period of 8 hours in two job functions would look like two entries side
    by side with the break taken twice. The hints treat the period once.
    """
    result: list[Span] = []
    periods: dict[Any, Span] = {}
    for span in spans:
        if span.period_key is None:
            result.append(span)
            continue
        whole = periods.get(span.period_key)
        if whole is None:
            whole = Span(
                span.pk,
                span.person_id,
                span.start,
                span.end,
                span.break_minutes,
                span.hours,
                span.period_key,
                [span.pk],
            )
            periods[span.period_key] = whole
            result.append(whole)
        else:
            whole.hours += span.hours
            whole.members.append(span.pk)
    return result


@dataclass
class WorkingDay:
    """The entries of a person that belong to one working day, in the order of their begin."""

    entries: list[Any] = field(default_factory=list)
    _end: datetime.datetime | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        ends = [entry.end for entry in self.entries if entry.end is not None]
        self._end = max(ends) if ends else None

    def add(self, entry: Any) -> None:
        """Add the next entry; the end of the day follows."""
        self.entries.append(entry)
        if entry.end is not None and (self._end is None or entry.end > self._end):
            self._end = entry.end

    @property
    def start(self) -> datetime.datetime:
        """The begin of its first entry."""
        return self.entries[0].start

    @property
    def end(self) -> datetime.datetime:
        """The latest end of its entries."""
        assert self._end is not None
        return self._end

    @property
    def worked(self) -> Decimal:
        """The hours of work: the hours of its entries."""
        return sum((entry.hours for entry in self.entries), Decimal("0"))

    @property
    def break_minutes(self) -> int:
        """The break: the recorded break minutes and the gaps of at least 15 minutes between the entries."""
        minutes = sum(entry.break_minutes for entry in self.entries)
        latest_end = self.entries[0].end
        for entry in self.entries[1:]:
            if latest_end is not None:
                gap = entry.start - latest_end
                if gap >= SHORTEST_BREAK:
                    minutes += int(gap.total_seconds() // 60)
            latest_end = max(latest_end, entry.end) if latest_end and entry.end else entry.end
        return minutes


def working_days(entries: Iterable[Any], limits: HintLimits) -> list[WorkingDay]:
    """Group the finished entries of *one* person into working days (see the module description)."""
    rest = limits.rest
    zone = timezone.get_current_timezone()
    days: list[WorkingDay] = []
    day: WorkingDay | None = None
    for entry in sorted((entry for entry in entries if entry.end is not None), key=lambda entry: entry.start):
        if day is not None:
            gap = entry.start - day.end
            # A long gap is a rest when the entry begins on another calendar day; only then the dates count.
            if gap < rest and (
                gap < NIGHT_GAP or entry.start.astimezone(zone).date() == day.start.astimezone(zone).date()
            ):
                day.add(entry)
                continue
        day = WorkingDay([entry])
        days.append(day)
    return days


def _hours(value: Decimal) -> str:
    return format_decimal(value, max_places=2)


def hints_of_days(days: Sequence[WorkingDay], limits: HintLimits) -> dict[int, list[TimeHint]]:
    """The hints of the entries of consecutive working days of one person, by entry ID."""
    result: dict[int, list[TimeHint]] = defaultdict(list)
    previous: WorkingDay | None = None
    for day in days:
        worked = day.worked
        day_hints: list[TimeHint] = []
        if limits.day_hours and worked > limits.day_hours:
            day_hints.append(
                TimeHint(
                    HintKind.LONG_DAY,
                    _("Long working day: %(hours)s hours of work (more than %(limit)s).")
                    % {"hours": _hours(worked), "limit": _hours(limits.day_hours)},
                )
            )
        needed = limits.break_needed(worked)
        taken = day.break_minutes
        if needed and taken < needed:
            day_hints.append(
                TimeHint(
                    HintKind.SHORT_BREAK,
                    _("Short break: %(hours)s hours of work with %(taken)s minutes of break (at least %(needed)s).")
                    % {"hours": _hours(worked), "taken": taken, "needed": needed},
                )
            )
        for entry in day.entries:
            result[entry.pk].extend(day_hints)
        if previous is not None and limits.rest_hours:
            rest = day.start - previous.end
            if rest < limits.rest:
                ended = timezone.localtime(previous.end)
                result[day.entries[0].pk].append(
                    TimeHint(
                        HintKind.SHORT_REST,
                        _("Short rest: %(hours)s hours since the end at %(time)s on %(date)s (less than %(limit)s).")
                        % {
                            "hours": _hours(Decimal(rest.total_seconds()) / Decimal(3600)),
                            "time": ended.strftime("%H:%M"),
                            "date": ended.strftime(local_pattern("%d.%m.")),
                            "limit": _hours(limits.rest_hours),
                        },
                    )
                )
        previous = day
    return dict(result)


def _counts(entry: TimeEntry) -> bool:
    """Whether an entry takes part in the hints: finished and not sent back."""
    return entry.end is not None and entry.status != TimeEntryStatus.REJECTED


def hints_for(entries: Iterable[TimeEntry], *, limits: HintLimits | None = None) -> dict[int, list[TimeHint]]:
    """The hints of some entries, by entry ID; entries without hints are left out (ZEI-018).

    The other entries of the same people around them are read with one
    query, so that a working day and the rest before it are complete,
    whatever part of them the caller has (a page of a list, one project).
    """
    wanted = [entry for entry in entries if _counts(entry)]
    if not wanted:
        return {}
    limits = limits or HintLimits.load()
    if not limits.any:
        return {}
    low = min(entry.start for entry in wanted) - CONTEXT
    high = max(entry.end for entry in wanted if entry.end is not None) + CONTEXT
    around = (
        TimeEntry.objects.filter(
            person_id__in={entry.person_id for entry in wanted}, end__isnull=False, start__lt=high, end__gt=low
        )
        .exclude(status=TimeEntryStatus.REJECTED)
        .order_by("person_id", "start", "id")
        .values_list("id", "person_id", "start", "end", "break_minutes", "hours", "period_key")
    )
    by_person: dict[int, dict[int, Span]] = defaultdict(dict)
    for values in around:
        span = Span(*values)
        by_person[span.person_id][span.pk] = span
    # The caller's own objects may hold changes that are not saved yet (a candidate); they win.
    for entry in wanted:
        by_person[entry.person_id][entry.pk] = Span.of(entry)
    found: dict[int, list[TimeHint]] = {}
    wanted_ids = {entry.pk for entry in wanted}
    for person_entries in by_person.values():
        spans = whole_periods(person_entries.values())  # ZEI-025: a divided period counts once
        members = {span.pk: span.members or [span.pk] for span in spans}
        days = working_days(spans, limits)
        for pk, hints in hints_of_days(days, limits).items():
            for member in members.get(pk, [pk]):
                if member in wanted_ids and hints:
                    found[member] = hints
    return found


def attach_hints(entries: Iterable[Any]) -> int:
    """Note on every entry its hints as ``entry.hints`` (a list, maybe empty); returns how many have some."""
    listed = list(entries)
    found = hints_for(listed)
    for entry in listed:
        entry.hints = found.get(entry.pk, [])
    return sum(1 for entry in listed if entry.hints)


def hint_documents(hints: Iterable[TimeHint]) -> list[dict[str, str]]:
    """The hints as the API shows them: ``[{"kind": …, "message": …}]``."""
    return [{"kind": hint.kind, "message": hint.message} for hint in hints]
