# SPDX-License-Identifier: GPL-3.0-or-later
"""The own availability calendar: available, with limits, not available (PER-021, PER-027, PER-028).

A person colours periods of a calendar green, yellow or red, optionally with
a note ("only until 18:00", "driving licence C1E needed"). Personnel planning
sees the colours in the overview "who is free" (VFG-009), and the planning of
a project warns when somebody is planned in a red period (PRJ-022).

Colouring works like a paint brush, not like a list of entries:

* a new colour **replaces** whatever the person had entered in that period –
  an older entry is cut back, split in two or removed;
* "clear" removes the person's own entries in a period;
* a **series** (PER-028) paints the same colour on many days at once – daily,
  on chosen weekdays every n weeks, or monthly –, up to a year ahead.

Own entries therefore never overlap. Each keeps the moment it was entered
(``entered_at``): a piece left over from cutting keeps the moment of its
entry, and neighbouring entries of the same colour are not joined in the
database – they are shown as one.

Busy times read from the linked calendar (PER-022) are a layer of their own:
they are never touched here and are replaced as a whole with every reading of
that calendar. At any moment a person still has **one** availability
(PER-027). :func:`resolve` decides where an own entry and a busy time meet:

* the **newer statement counts** – an own entry by when it was entered, a
  busy time by when the appointment was last changed in the calendar;
* where the calendar does not say when, the **stricter** one counts, which
  is the busy time unless the own entry is red as well;
* busy times that overlap or touch are **one block**.

Browser views and API views both call these functions (API-002).
"""

from __future__ import annotations

import bisect
import datetime
import itertools
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.dates import WEEKDAYS_ABBR
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.core.i18n import local_pattern
from rentalars.personnel.models import (
    AvailabilityMark,
    AvailabilityRepeat,
    AvailabilitySeries,
    AvailabilitySource,
    AvailabilityState,
    Person,
)

#: The longest stretch that can be coloured in one step, in days.
MAX_DAYS = 400

#: How far a series reaches beyond its first day, in days (PER-028).
SERIES_MAX_DAYS = 366

#: The largest step of a series: every 52 weeks, every 12 months, every 365 days.
SERIES_MAX_INTERVAL = {AvailabilityRepeat.DAILY: 365, AvailabilityRepeat.WEEKLY: 52, AvailabilityRepeat.MONTHLY: 12}

#: Colours from strongest to weakest: a day shows the strongest of its periods.
STRENGTH = {AvailabilityState.UNAVAILABLE: 3, AvailabilityState.LIMITED: 2, AvailabilityState.AVAILABLE: 1}

Period = tuple[datetime.datetime, datetime.datetime]


def day_start(day: datetime.date) -> datetime.datetime:
    """Local midnight at the beginning of a day (correct across the change to summer time)."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time()))


def _check_period(start: datetime.datetime, end: datetime.datetime) -> None:
    if end <= start:
        raise ValidationError({"end": _("The end must be after the start.")})
    if end - start > datetime.timedelta(days=MAX_DAYS):
        raise ValidationError({"end": _("At most %(days)d days at once.") % {"days": MAX_DAYS}})


def _check_state(state: str) -> None:
    if state not in AvailabilityState.values:
        raise ValidationError({"state": _("Choose available, available with limits or not available.")})


# --- Painting ----------------------------------------------------------------------------------


def _joined(periods: Iterable[Period], *, touching: bool) -> list[Period]:
    """Sort periods and join those that overlap – with ``touching`` also those that only touch."""
    joined: list[list[datetime.datetime]] = []
    for start, end in sorted(periods):
        if joined and (start < joined[-1][1] or (touching and start == joined[-1][1])):
            joined[-1][1] = max(joined[-1][1], end)
        else:
            joined.append([start, end])
    return [(start, end) for start, end in joined]


def _subtract(start: datetime.datetime, end: datetime.datetime, periods: Sequence[Period]) -> list[Period]:
    """What is left of ``start``–``end`` outside sorted, separate ``periods``."""
    starts = [begin for begin, _finish in periods]
    pieces: list[Period] = []
    cursor = start
    index = max(bisect.bisect_right(starts, start) - 1, 0)
    while index < len(periods) and periods[index][0] < end:
        begin, finish = periods[index]
        if finish > cursor:
            if begin > cursor:
                pieces.append((cursor, begin))
            cursor = finish
            if cursor >= end:
                break
        index += 1
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def _cut_own_marks(person: Person, periods: Iterable[Period]) -> int:
    """Make room for periods: cut back, split or remove the person's own entries in them.

    A piece that is left keeps the colour, note, series and moment of entry
    of the entry it comes from. Returns how many entries were touched.
    """
    periods = _joined(periods, touching=True)
    if not periods:
        return 0
    changed = 0
    overlapping = AvailabilityMark.objects.select_for_update().filter(
        person=person, source=AvailabilitySource.OWN, start__lt=periods[-1][1], end__gt=periods[0][0]
    )
    for mark in overlapping.order_by("start", "pk"):
        pieces = _subtract(mark.start, mark.end, periods)
        if pieces == [(mark.start, mark.end)]:
            continue  # lies in a gap between the periods
        changed += 1
        if not pieces:
            mark.delete()
            continue
        (mark.start, mark.end), *rest = pieces
        mark.save(update_fields=["start", "end"])
        for start, end in rest:
            AvailabilityMark.objects.create(
                person=person,
                start=start,
                end=end,
                state=mark.state,
                note=mark.note,
                source=AvailabilitySource.OWN,
                entered_at=mark.entered_at,
                series_id=mark.series_id,
            )
    return changed


def _paint(
    person: Person,
    periods: Sequence[Period],
    state: str,
    note: str = "",
    *,
    series: AvailabilitySeries | None = None,
) -> list[AvailabilityMark]:
    """Colour periods in one step: what was entered there is replaced; all new entries get the same moment."""
    _check_state(state)
    for start, end in periods:
        _check_period(start, end)
    note = (note or "").strip()
    _cut_own_marks(person, periods)
    now = timezone.now()
    marks = [
        AvailabilityMark(person=person, start=start, end=end, state=state, note=note, entered_at=now, series=series)
        for start, end in _joined(periods, touching=False)
    ]
    if not marks:
        return []
    # One check is enough: the entries differ in their periods only, and those were checked above.
    marks[0].full_clean()
    if len(marks) == 1:
        marks[0].save()
    else:
        AvailabilityMark.objects.bulk_create(marks, batch_size=500)
    return marks


@transaction.atomic
def mark_period(
    person: Person, start: datetime.datetime, end: datetime.datetime, state: str, note: str = ""
) -> AvailabilityMark:
    """Colour a period of a person green, yellow or red (PER-021).

    What the person had entered in the period before is replaced. An entry
    of the same colour next to it stays an entry of its own (it keeps its
    moment of entry, PER-027); the calendar shows both as one period.

    Returns:
        The new entry.

    Raises:
        ValidationError: The period is empty, longer than :data:`MAX_DAYS`,
            or the colour is unknown.
    """
    return _paint(person, [(start, end)], state, note)[0]


def unavailable_in(person: Person, start: datetime.datetime, end: datetime.datetime) -> bool:
    """Whether the person's own entries say "not available" somewhere in the period (PER-042; PER-021).

    Own entries only, those of a series included (PER-028) – busy times of the linked calendars (PER-022) are not
    the person's own calendar and do not count here.
    """
    return AvailabilityMark.objects.filter(
        person=person,
        source=AvailabilitySource.OWN,
        state=AvailabilityState.UNAVAILABLE,
        start__lt=end,
        end__gt=start,
    ).exists()


@transaction.atomic
def mark_available_for_deployment(
    person: Person, start: datetime.datetime, end: datetime.datetime, note: str = ""
) -> AvailabilityMark | None:
    """Enter "available" for exactly the period of an accepted deployment (PER-042; PER-016, PER-021).

    The requirement: when somebody accepts an invitation for a period in which their own calendar has "not available", an entry "available" is created automatically for the period of the accepted function.

    Only where an own entry "not available" overlaps the period (:func:`unavailable_in`). The period is coloured
    like any other entry (:func:`mark_period`): what the person had entered in it is replaced – an entry or the
    occurrence of a series reaching beyond it is cut back or split, the rest keeps its colour and series. The
    new entry is an own entry made now: the person changes or removes it on the own calendar like any other, and
    as the newer statement it counts over older busy times of a linked calendar (PER-027) – the linked calendar
    itself is never changed.

    Returns:
        The new entry; ``None`` when nothing "not available" was there, or the deployment is longer than
        :data:`MAX_DAYS` (left as it is).
    """
    if end <= start or not unavailable_in(person, start, end):
        return None
    if end - start > datetime.timedelta(days=MAX_DAYS):
        return None
    return mark_period(person, start, end, AvailabilityState.AVAILABLE, note[:250])


@transaction.atomic
def clear_period(person: Person, start: datetime.datetime, end: datetime.datetime) -> int:
    """Remove what the person entered in a period (PER-021); returns how many entries were touched."""
    _check_period(start, end)
    return _cut_own_marks(person, [(start, end)])


def day_periods(
    first: datetime.date,
    last: datetime.date,
    start_time: datetime.time | None = None,
    end_time: datetime.time | None = None,
) -> list[Period]:
    """Turn days chosen in the calendar into periods (PER-021).

    Without times the days are one period, from the midnight before the
    first day to the midnight after the last. With times the colour applies
    on *each* of the days between the two times – "Monday to Friday, from
    18:00" –; an end time before the start time reaches into the next day.

    Raises:
        ValidationError: The last day is before the first, the stretch is
            longer than :data:`MAX_DAYS`, or only one of the times is given.
    """
    if last < first:
        raise ValidationError({"end_day": _("The last day must not be before the first.")})
    if (last - first).days >= MAX_DAYS:
        raise ValidationError({"end_day": _("At most %(days)d days at once.") % {"days": MAX_DAYS}})
    if (start_time is None) != (end_time is None):
        raise ValidationError({"end_time": _("Give both times, or none for whole days.")})
    if start_time is None or end_time is None:
        return [(day_start(first), day_start(last + datetime.timedelta(days=1)))]
    periods = []
    day = first
    while day <= last:
        begin = timezone.make_aware(datetime.datetime.combine(day, start_time))
        finish_day = day if end_time > start_time else day + datetime.timedelta(days=1)
        periods.append((begin, timezone.make_aware(datetime.datetime.combine(finish_day, end_time))))
        day += datetime.timedelta(days=1)
    return periods


@transaction.atomic
def mark_days(
    person: Person,
    first: datetime.date,
    last: datetime.date,
    state: str | None,
    *,
    note: str = "",
    start_time: datetime.time | None = None,
    end_time: datetime.time | None = None,
) -> int:
    """Colour or clear days chosen in the calendar (PER-021); ``state=None`` clears.

    Returns:
        The number of periods coloured or cleared.
    """
    periods = day_periods(first, last, start_time, end_time)
    if state is None:
        _cut_own_marks(person, periods)
    else:
        _paint(person, periods, state, note)
    return len(periods)


def _own(mark: AvailabilityMark) -> None:
    if mark.source != AvailabilitySource.OWN:
        raise ValidationError(_("This period comes from the linked calendar and changes with it only."))


@transaction.atomic
def change_mark(
    mark: AvailabilityMark,
    *,
    start: datetime.datetime | None = None,
    end: datetime.datetime | None = None,
    state: str | None = None,
    note: str | None = None,
) -> AvailabilityMark:
    """Change an own entry: its period, colour or note (PER-021).

    The changed entry is coloured anew, so it replaces what lies in its new
    period like any other colouring and counts as entered now. An entry of a
    series leaves the series with that: it is a statement of its own now.

    Raises:
        ValidationError: The entry comes from the linked calendar, or a value is invalid.
    """
    _own(mark)
    values = {
        "start": start or mark.start,
        "end": end or mark.end,
        "state": state or mark.state,
        "note": mark.note if note is None else note,
    }
    _check_period(values["start"], values["end"])
    mark.delete()
    return mark_period(mark.person, values["start"], values["end"], values["state"], values["note"])


def delete_mark(mark: AvailabilityMark) -> None:
    """Remove an own entry (PER-021).

    Raises:
        ValidationError: The entry comes from the linked calendar.
    """
    _own(mark)
    mark.delete()


# --- Series (PER-028) --------------------------------------------------------------------------


def _months_later(day: datetime.date, months: int) -> datetime.date | None:
    """The same day of the month ``months`` later, or ``None`` if that month is too short."""
    index = day.month - 1 + months
    try:
        return day.replace(year=day.year + index // 12, month=index % 12 + 1)
    except ValueError:
        return None


def series_limit(series: AvailabilitySeries) -> datetime.date:
    """The last day an occurrence of the series may begin on: its end, at most a year after the first day."""
    limit = series.first_day + datetime.timedelta(days=SERIES_MAX_DAYS)
    return min(series.until, limit) if series.until else limit


def series_occurrences(series: AvailabilitySeries) -> list[tuple[datetime.date, datetime.date]]:
    """The occurrences of a series as ``(first day, last day)``, in order (PER-028).

    Daily: every ``interval`` days. Weekly: on the chosen weekdays (the
    weekday of the first day if none is chosen) of every ``interval``-th
    week, counted from the week of the first day. Monthly: on the same day
    of every ``interval``-th month; months without that day are skipped, as
    calendar programs do. At most ``count`` occurrences, none beginning after
    :func:`series_limit`.
    """
    length = datetime.timedelta(days=(series.last_day - series.first_day).days)
    limit = series_limit(series)
    count = series.count or SERIES_MAX_DAYS + 1
    interval = max(series.interval or 1, 1)
    starts: list[datetime.date] = []
    if series.repeat == AvailabilityRepeat.DAILY:
        day = series.first_day
        while day <= limit and len(starts) < count:
            starts.append(day)
            day += datetime.timedelta(days=interval)
    elif series.repeat == AvailabilityRepeat.WEEKLY:
        weekdays = series.weekday_numbers or [series.first_day.weekday()]
        monday = series.first_day - datetime.timedelta(days=series.first_day.weekday())
        while monday <= limit and len(starts) < count:
            for weekday in weekdays:
                day = monday + datetime.timedelta(days=weekday)
                if series.first_day <= day <= limit and len(starts) < count:
                    starts.append(day)
            monday += datetime.timedelta(weeks=interval)
    else:
        months = 0
        while len(starts) < count:
            day = _months_later(series.first_day, months)
            month_first = _months_later(series.first_day.replace(day=1), months)
            if month_first is None or month_first > limit:
                break
            if day is not None and day <= limit:
                starts.append(day)
            months += interval
    return [(start, start + length) for start in starts]


def check_series(series: AvailabilitySeries) -> None:
    """Check the rule of a series before it is painted (PER-028).

    Raises:
        ValidationError: A value is missing or out of range.
    """
    _check_state(series.state)
    if series.repeat not in AvailabilityRepeat.values:
        raise ValidationError({"repeat": _("Choose how the entry repeats.")})
    if series.last_day < series.first_day:
        raise ValidationError({"end_day": _("The last day must not be before the first.")})
    if (series.start_time is None) != (series.end_time is None):
        raise ValidationError({"end_time": _("Give both times, or none for whole days.")})
    largest = SERIES_MAX_INTERVAL[AvailabilityRepeat(series.repeat)]
    if not 1 <= (series.interval or 0) <= largest:
        raise ValidationError({"interval": _("Repeat every 1 to %(largest)d.") % {"largest": largest}})
    if series.until is not None and series.until < series.first_day:
        raise ValidationError({"until": _("The series must not end before its first day.")})
    if series.count is not None and not 1 <= series.count <= SERIES_MAX_DAYS:
        raise ValidationError({"count": _("A series has 1 to %(largest)d occurrences.") % {"largest": SERIES_MAX_DAYS}})
    if series.until is None and series.count is None:
        raise ValidationError({"until": _("Say until when the series repeats, or how often.")})
    if any(not part.strip().isdigit() or int(part) > 6 for part in series.weekdays.split(",") if part.strip()):
        raise ValidationError({"weekdays": _("Choose weekdays from Monday to Sunday.")})
    occurrences = series_occurrences(series)
    if not occurrences:
        raise ValidationError({"until": _("The series has no occurrence. Check the first day and the repetition.")})
    span = (series.last_day - series.first_day).days + 1
    if span > MAX_DAYS:
        raise ValidationError({"end_day": _("At most %(days)d days at once.") % {"days": MAX_DAYS}})


def _paint_series(series: AvailabilitySeries, *, from_day: datetime.date | None = None) -> int:
    """Paint the occurrences of a series, those from ``from_day`` on; returns how many periods."""
    cutoff = day_start(from_day) if from_day else None
    periods: list[Period] = []
    for first, last in series_occurrences(series):
        for start, end in day_periods(first, last, series.start_time, series.end_time):
            if cutoff is not None:
                if end <= cutoff:
                    continue
                start = max(start, cutoff)
            periods.append((start, end))
    _paint(series.person, periods, series.state, series.note, series=series)
    return len(periods)


SERIES_FIELDS = (
    "state",
    "note",
    "first_day",
    "last_day",
    "start_time",
    "end_time",
    "repeat",
    "interval",
    "weekdays",
    "until",
    "count",
)


def _weekdays_text(weekdays: Iterable[int] | str) -> str:
    if isinstance(weekdays, str):
        return weekdays
    return ",".join(str(day) for day in sorted(set(weekdays)))


@transaction.atomic
def create_series(person: Person, **values: object) -> AvailabilitySeries:
    """Enter an availability that repeats, and paint its occurrences (PER-028).

    ``values`` are the fields of :class:`AvailabilitySeries` named in
    :data:`SERIES_FIELDS`; ``weekdays`` may be a list of numbers.

    Raises:
        ValidationError: The rule is incomplete or out of range.
    """
    values = {key: value for key, value in values.items() if key in SERIES_FIELDS}
    values["weekdays"] = _weekdays_text(values.get("weekdays") or "")
    values["note"] = str(values.get("note") or "").strip()
    series = AvailabilitySeries(person=person, **values)
    check_series(series)
    series.full_clean()
    series.save()
    _paint_series(series)
    return series


@transaction.atomic
def change_series(
    series: AvailabilitySeries, *, from_day: datetime.date | None = None, **values: object
) -> AvailabilitySeries:
    """Change a series from a day on – today unless given (PER-028).

    What is over stays as it was; from that day on the occurrences are
    removed and painted anew after the changed rule – like "this and the
    following appointments" in a calendar program.

    Raises:
        ValidationError: The changed rule is incomplete or out of range.
    """
    from_day = from_day or timezone.localdate()
    changed = AvailabilitySeries(pk=series.pk, person=series.person, created_at=series.created_at)
    for name in SERIES_FIELDS:
        setattr(changed, name, getattr(series, name))
    for name, value in values.items():
        if name in SERIES_FIELDS:
            setattr(changed, name, value)
    changed.weekdays = _weekdays_text(changed.weekdays or "")
    changed.note = (changed.note or "").strip()
    check_series(changed)
    changed.full_clean(validate_unique=False)
    _remove_series_marks(series, from_day)
    changed.save()
    _paint_series(changed, from_day=from_day)
    return changed


def _remove_series_marks(series: AvailabilitySeries, from_day: datetime.date | None) -> int:
    """Remove the entries of a series, all or from the beginning of a day on; returns how many were touched."""
    marks = AvailabilityMark.objects.select_for_update().filter(series=series)
    if from_day is None:
        return marks.delete()[0]
    cutoff = day_start(from_day)
    removed = marks.filter(start__gte=cutoff).delete()[0]
    return removed + marks.filter(start__lt=cutoff, end__gt=cutoff).update(end=cutoff)


@transaction.atomic
def remove_series(series: AvailabilitySeries, *, from_day: datetime.date | None = None) -> int:
    """Remove a series: all its entries, or those from a day on (PER-028).

    From a day on, the series ends the day before; a series without any
    entry before that day goes completely. Returns how many entries were
    removed or cut back.
    """
    touched = _remove_series_marks(series, from_day)
    if from_day is None or from_day <= series.first_day:
        AvailabilityMark.objects.filter(series=series).update(series=None)
        series.delete()
        return touched
    series.until = from_day - datetime.timedelta(days=1)
    series.count = None
    series.save(update_fields=["until", "count"])
    return touched


def describe_series(series: AvailabilitySeries) -> str:
    """The rule of a series in one line: "every 2 weeks on Tue, Thu, 18:00–23:00, until 31.12.2026"."""
    interval = series.interval or 1
    if series.repeat == AvailabilityRepeat.DAILY:
        rule = _("daily") if interval == 1 else _("every %(count)d days") % {"count": interval}
    elif series.repeat == AvailabilityRepeat.WEEKLY:
        days = ", ".join(str(WEEKDAYS_ABBR[day]) for day in (series.weekday_numbers or [series.first_day.weekday()]))
        rule = (
            _("weekly on %(days)s") % {"days": days}
            if interval == 1
            else _("every %(count)d weeks on %(days)s") % {"count": interval, "days": days}
        )
    else:
        rule = (
            _("monthly on the %(day)d.") % {"day": series.first_day.day}
            if interval == 1
            else _("every %(count)d months on the %(day)d.") % {"count": interval, "day": series.first_day.day}
        )
    parts = [rule]
    span = (series.last_day - series.first_day).days + 1
    if span > 1:
        parts.append(ngettext("%(count)d day long", "%(count)d days long", span) % {"count": span})
    if series.start_time is not None and series.end_time is not None:
        parts.append(f"{series.start_time:%H:%M}–{series.end_time:%H:%M}")
    else:
        parts.append(_("whole day"))
    parts.append(_("from %(date)s") % {"date": date_format(series.first_day, local_pattern("d.m.Y"))})
    if series.until:
        parts.append(_("until %(date)s") % {"date": date_format(series.until, local_pattern("d.m.Y"))})
    if series.count:
        parts.append(ngettext("%(count)d time", "%(count)d times", series.count) % {"count": series.count})
    return ", ".join(parts)


# --- One availability at any moment (PER-027) ---------------------------------------------------------


@dataclass(frozen=True)
class AvailabilityPeriod:
    """A stretch of time with the availability that counts there (PER-027).

    Made by :func:`resolve` from the entries and busy times of one person:
    periods never overlap, an own entry shows where it is the newer
    statement, and busy times of the linked calendar that overlap or touch
    are one period. Offers the same fields as an :class:`AvailabilityMark`,
    so the overviews and warnings take either.
    """

    person_id: int
    start: datetime.datetime
    end: datetime.datetime
    state: str
    source: str
    note: str = ""
    #: The own entries the period shows; empty for busy times.
    mark_ids: tuple[int, ...] = ()
    #: The series these entries belong to.
    series_ids: tuple[int, ...] = ()

    @property
    def from_feed(self) -> bool:
        """The period is a busy time of the linked calendar (PER-022)."""
        return self.source == AvailabilitySource.FEED

    @property
    def in_series(self) -> bool:
        """The period was entered as (part of) a series (PER-028)."""
        return bool(self.series_ids)

    def get_state_display(self) -> str:
        """The colour in words, like the field of a mark."""
        return str(dict(AvailabilityState.choices).get(self.state, self.state))

    def get_source_display(self) -> str:
        """Where the period comes from, like the field of a mark."""
        return str(dict(AvailabilitySource.choices).get(self.source, self.source))


def _counts(own: AvailabilityMark, busy: list[AvailabilityMark]) -> bool:
    """Whether an own entry counts against busy times at the same moment (PER-027).

    The newer statement counts. If the calendar does not say when an
    appointment changed – or an own entry has no moment –, the stricter one
    counts, and of two equally strict ones the own entry, which has a note.
    """
    times = [mark.entered_at for mark in busy]
    if own.entered_at is not None and all(time is not None for time in times):
        return own.entered_at >= max(times)  # type: ignore[type-var]
    return STRENGTH.get(own.state, 0) >= STRENGTH[AvailabilityState.UNAVAILABLE]


def resolve(marks: Iterable[AvailabilityMark]) -> list[AvailabilityPeriod]:
    """Turn the entries and busy times of one person into the availability that counts (PER-027).

    Every moment gets one availability; see the module documentation for
    the rules. Neighbouring periods with the same colour, note and source
    are joined, busy times always.
    """
    marks = sorted(marks, key=lambda mark: (mark.start, mark.pk or 0))
    if not marks:
        return []
    person_id = marks[0].person_id
    points = sorted({mark.start for mark in marks} | {mark.end for mark in marks})
    pieces: list[tuple[datetime.datetime, datetime.datetime, AvailabilityMark | None]] = []
    active: list[AvailabilityMark] = []
    following = 0
    for begin, finish in itertools.pairwise(points):
        while following < len(marks) and marks[following].start <= begin:
            active.append(marks[following])
            following += 1
        active = [mark for mark in active if mark.end > begin]
        if not active:
            continue
        own = [mark for mark in active if mark.source == AvailabilitySource.OWN]
        busy = [mark for mark in active if mark.source != AvailabilitySource.OWN]
        # Own entries do not overlap; should they after all (older data), the newest counts.
        latest = max(own, key=lambda mark: (mark.entered_at or mark.created_at, mark.pk or 0)) if own else None
        if latest is not None and (not busy or _counts(latest, busy)):
            pieces.append((begin, finish, latest))
        else:
            pieces.append((begin, finish, None))

    periods: list[AvailabilityPeriod] = []
    for begin, finish, mark in pieces:
        state = mark.state if mark is not None else AvailabilityState.UNAVAILABLE
        source = AvailabilitySource.OWN if mark is not None else AvailabilitySource.FEED
        note = mark.note if mark is not None else ""
        ids = (mark.pk,) if mark is not None and mark.pk else ()
        series = (mark.series_id,) if mark is not None and mark.series_id else ()
        previous = periods[-1] if periods else None
        if (
            previous is not None
            and previous.end == begin
            and (previous.state, previous.source, previous.note) == (state, source, note)
        ):
            periods[-1] = AvailabilityPeriod(
                person_id=person_id,
                start=previous.start,
                end=finish,
                state=state,
                source=source,
                note=note,
                mark_ids=previous.mark_ids + tuple(pk for pk in ids if pk not in previous.mark_ids),
                series_ids=previous.series_ids + tuple(pk for pk in series if pk not in previous.series_ids),
            )
        else:
            periods.append(
                AvailabilityPeriod(
                    person_id=person_id,
                    start=begin,
                    end=finish,
                    state=state,
                    source=source,
                    note=note,
                    mark_ids=ids,
                    series_ids=series,
                )
            )
    return periods


def effective_periods(
    people: Iterable[int] | QuerySet[Person], start: datetime.datetime, end: datetime.datetime
) -> dict[int, list[AvailabilityPeriod]]:
    """The availability that counts for some people in a period, by person (PER-027).

    ``people`` are ids, or a query of people. One query, whatever the
    number of people. Only periods that overlap ``start``–``end`` are
    returned; they are not cut at its edges.
    """
    marks = AvailabilityMark.objects.filter(start__lt=end, end__gt=start)
    if isinstance(people, QuerySet):
        marks = marks.filter(person__in=people.values("pk"))
    else:
        ids = list(set(people))
        if not ids:
            return {}
        marks = marks.filter(person_id__in=ids)
    by_person: dict[int, list[AvailabilityMark]] = defaultdict(list)
    for mark in marks:
        by_person[mark.person_id].append(mark)
    return {
        person_id: [period for period in resolve(marks) if period.start < end and period.end > start]
        for person_id, marks in by_person.items()
    }


# --- The month calendar ------------------------------------------------------------------------


@dataclass
class CalendarDay:
    """One day of the month calendar (PER-021)."""

    day: datetime.date
    in_month: bool
    is_today: bool
    #: The strongest colour of the day: ``available``, ``limited``, ``unavailable`` or ``""``.
    state: str = ""
    #: The strongest colour covers only a part of the day.
    partial: bool = False
    #: The strongest colour comes from the linked calendar (PER-022).
    from_feed: bool = False
    #: The person is planned in a crew line on this day.
    planned: bool = False
    periods: list[AvailabilityPeriod] = field(default_factory=list)

    @property
    def label(self) -> str:
        """What the day says, for the tooltip and for screen readers."""
        parts = [f"{self.day:{local_pattern('%d.%m.%Y')}}"]
        names = dict(AvailabilityState.choices)
        if self.state:
            text = str(names[self.state])
            if self.partial:
                text = _("%(state)s, part of the day") % {"state": text}
            if self.from_feed:
                text = _("%(state)s (from the linked calendar)") % {"state": text}
            parts.append(text)
        if self.planned:
            parts.append(_("planned"))
        return " – ".join(parts)


@dataclass
class MonthCalendar:
    """A month of the availability calendar, Monday to Sunday (PER-021)."""

    month: datetime.date
    weeks: list[list[CalendarDay]]
    #: The availability that counts in the weeks shown (PER-027).
    periods: list[AvailabilityPeriod]

    @property
    def previous(self) -> datetime.date:
        """The first day of the month before."""
        return (self.month - datetime.timedelta(days=1)).replace(day=1)

    @property
    def next(self) -> datetime.date:
        """The first day of the month after."""
        return (self.month + datetime.timedelta(days=32)).replace(day=1)

    @property
    def month_periods(self) -> list[AvailabilityPeriod]:
        """The periods that touch the month itself, for the list under the calendar."""
        begin = day_start(self.month)
        finish = day_start(self.next)
        return [period for period in self.periods if period.start < finish and period.end > begin]


def colour_day(entry: CalendarDay, periods: Sequence[AvailabilityPeriod]) -> None:
    """Give a day of the calendar its periods and the strongest colour among them (PER-021).

    Used by the month and by the heads of the week (PER-030).
    """
    day_begin, day_end = day_start(entry.day), day_start(entry.day + datetime.timedelta(days=1))
    entry.periods = [period for period in periods if period.start < day_end and period.end > day_begin]
    if not entry.periods:
        return
    strongest = max(entry.periods, key=lambda period: STRENGTH.get(period.state, 0))
    entry.state = strongest.state
    top = [period for period in entry.periods if period.state == strongest.state]
    covered = _joined(((period.start, period.end) for period in top), touching=True)
    entry.partial = not any(start <= day_begin and end >= day_end for start, end in covered)
    entry.from_feed = all(period.from_feed for period in top)


def parse_month(text: str | None) -> datetime.date:
    """Read ``2026-11`` into the first day of that month; anything else gives the current month."""
    if text:
        try:
            year, month = (int(part) for part in text.split("-", 1))
            if 2000 <= year <= 2100:
                return datetime.date(year, month, 1)
        except ValueError:
            pass
    return timezone.localdate().replace(day=1)


def month_calendar(person: Person, month: datetime.date) -> MonthCalendar:
    """Build the month calendar of a person with the availability and deployments of every day (PER-021).

    Two queries, whatever is entered: the entries and the crew lines of the
    weeks shown.
    """
    from rentalars.projects.models import CrewLine, ProjectStatus

    month = month.replace(day=1)
    first = month - datetime.timedelta(days=month.weekday())
    last_of_month = (month + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    last = last_of_month + datetime.timedelta(days=6 - last_of_month.weekday())
    begin, finish = day_start(first), day_start(last + datetime.timedelta(days=1))
    periods = effective_periods([person.pk], begin, finish).get(person.pk, [])
    planned_days: set[datetime.date] = set()
    lines = (
        CrewLine.objects.filter(person=person, start__lt=finish, end__gt=begin)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .values_list("start", "end")
    )
    for start, end in lines:
        day = max(timezone.localtime(start).date(), first)
        stop = min(timezone.localtime(end - datetime.timedelta(seconds=1)).date(), last)
        while day <= stop:
            planned_days.add(day)
            day += datetime.timedelta(days=1)

    today = timezone.localdate()
    weeks: list[list[CalendarDay]] = []
    day = first
    while day <= last:
        week = []
        for _weekday in range(7):
            entry = CalendarDay(day=day, in_month=day.month == month.month, is_today=day == today)
            entry.planned = day in planned_days
            colour_day(entry, periods)
            week.append(entry)
            day += datetime.timedelta(days=1)
        weeks.append(week)
    return MonthCalendar(month=month, weeks=weeks, periods=periods)
