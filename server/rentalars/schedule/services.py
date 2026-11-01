# SPDX-License-Identifier: GPL-3.0-or-later
"""What the calendar and the timelines show (PRJ-028, VFG-012, VFG-014, VFG-022 to VFG-024).

Pure reading: nothing here changes anything. Every overview only contains
what the user may see – the projects come from ``projects.access``.

A timeline has columns of whole days (the week modes), or – for one to ten
days – columns of one to six hours (:class:`Scale`, VFG-022, VFG-024). A bar
covers the columns its period touches and is cut to its exact start and end
inside them, so that a setup from 14:00 to 20:00 does not fill the whole day
(:attr:`Bar.style`). The month and week calendars are laid out in
``calendars``.
"""

from __future__ import annotations

import datetime
import itertools
import math
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rentalars.core.i18n import local_pattern
from rentalars.core.listing import query_date
from rentalars.products.models import STOCK_KINDS, ProductKind
from rentalars.projects.family_labels import part_of, short_name, whole_first
from rentalars.projects.models import CrewLine, Project, ProjectPhase, ProjectStatus

#: The longest span a timeline shows, in weeks.
MAX_WEEKS = 12


def day_range(first: datetime.date, count: int) -> list[datetime.date]:
    """``count`` days starting with ``first``."""
    return [first + datetime.timedelta(days=offset) for offset in range(count)]


def monday_of(day: datetime.date) -> datetime.date:
    """The Monday of the week of a day."""
    return day - datetime.timedelta(days=day.weekday())


def bounds(days: list[datetime.date]) -> tuple[datetime.datetime, datetime.datetime]:
    """Start of the first and end of the last day, in local time."""
    zone = timezone.get_current_timezone()
    start = datetime.datetime.combine(days[0], datetime.time.min, tzinfo=zone)
    return start, start + datetime.timedelta(days=len(days))


def span_from_request(request: Any, *, default_weeks: int = 4) -> tuple[list[datetime.date], dict[str, Any]]:
    """The days asked for: ``from`` (a date, default this Monday) and ``weeks`` (1 to 12)."""
    first = query_date(request.GET.get("from")) or monday_of(timezone.localdate())
    try:
        weeks = max(1, min(MAX_WEEKS, int(request.GET.get("weeks", default_weeks))))
    except ValueError:
        weeks = default_weeks
    days = day_range(first, weeks * 7)
    navigation = {
        "first": first,
        "weeks": weeks,
        "earlier": first - datetime.timedelta(days=7 * weeks),
        "later": first + datetime.timedelta(days=7 * weeks),
        "this_week": monday_of(timezone.localdate()),
        "week_choices": sorted({1, 2, 4, 8, 12, weeks}),
    }
    return days, navigation


def overlapping(queryset: QuerySet[Any], start: datetime.datetime, end: datetime.datetime) -> QuerySet[Any]:
    """Records whose period touches the span."""
    return queryset.filter(start__lt=end, end__gt=start)


def projects_or_phases_in(
    projects: QuerySet[Project], start: datetime.datetime, end: datetime.datetime
) -> QuerySet[Project]:
    """Projects whose period touches the span, or one of whose phases does (PRJ-092).

    A phase may lie outside the rental period of its project: the planning
    meeting weeks before, the follow-up work after the material is back.
    The timeline and the calendar of the API list such a project for the
    days of that phase. One subquery, no further query.
    """
    phase_in_span = Exists(overlapping(ProjectPhase.objects.filter(project=OuterRef("pk")), start, end))
    return projects.filter(Q(start__lt=end, end__gt=start) | phase_in_span)


@dataclass
class Bar:
    """One bar of a timeline: which columns it covers (1-based, for a CSS grid).

    ``lead`` and ``trail`` are the parts of these columns before the start
    and after the end of the period, as fractions of the bar's columns. A
    phase from 14:00 to 20:00 covers the column of its day, with a lead of
    14/24 and a trail of 4/24; drawn with them, it is as long as it lasts.
    """

    first: int
    last: int
    label: str
    css: str = ""
    title: str = ""
    url: str = ""
    record: Any = None
    lead: float = 0.0
    trail: float = 0.0
    #: VFG-026: what the page needs to drag the bar (``schedule.moves.Movable``), or ``None``.
    move: Any = None
    #: VFG-032, VFG-035: the bar takes part in a conflict. The one flag gives both the class
    #: ``is-conflict`` (filled red) and "conflict" at the end of the hover – they can no longer disagree.
    conflict: bool = False

    def __post_init__(self) -> None:
        if self.conflict:
            if "is-conflict" not in self.css.split():
                self.css = f"{self.css} is-conflict".strip()
            text = conflict_text()
            if not self.title.endswith(text):
                self.title = _joined(self.title, text)

    @property
    def span(self) -> str:
        """``grid-column`` value."""
        return f"{self.first} / {self.last + 1}"

    @property
    def style(self) -> str:
        """The inline style: the columns, and margins that cut the bar to its exact start and end.

        A percentage margin of a grid item refers to the width of its grid
        area, i.e. of the columns the bar covers. The pixel keeps the gap
        that every bar has at its ends. ``--fill`` (the part of the columns
        the bar covers) lets the style sheet shrink the padding of a short
        bar, which would otherwise widen it again.
        """
        style = f"grid-column: {self.span}"
        lead, trail = self.lead >= 0.0005, self.trail >= 0.0005
        if lead:
            style += f"; margin-left: calc({self.lead * 100:.3f}% + 1px)"
        if trail:
            style += f"; margin-right: calc({self.trail * 100:.3f}% + 1px)"
        if lead or trail:
            style += f"; --fill: {1 - self.lead - self.trail:.3f}"
        return style


def bar_for(start: datetime.datetime, end: datetime.datetime, days: list[datetime.date], **fields: Any) -> Bar | None:
    """The bar of a period within the shown days, or ``None`` if it lies outside."""
    local_start = timezone.localtime(start).date()
    # A period that ends at midnight does not occupy the following day.
    local_end = timezone.localtime(end - datetime.timedelta(seconds=1)).date()
    if local_end < days[0] or local_start > days[-1]:
        return None
    first = max(0, (local_start - days[0]).days) + 1
    last = min(len(days) - 1, (local_end - days[0]).days) + 1
    return Bar(first=first, last=last, **fields)


# --- Calendar of projects (PRJ-028) ------------------------------------------------------------


@dataclass
class CalendarEntry:
    """A project or phase on one day of the week view, with the times that concern that day."""

    record: Any
    times: str


@dataclass
class CalendarDay:
    """One day of the month or week calendar."""

    day: datetime.date
    in_month: bool
    projects: list[Project] = field(default_factory=list)
    phases: list[ProjectPhase] = field(default_factory=list)
    #: The week view: projects and phases with their times on this day.
    entries: list[CalendarEntry] = field(default_factory=list)
    phase_entries: list[CalendarEntry] = field(default_factory=list)
    #: VFG-039: the follow-ups of the day (``schedule.calendars.FollowUpMark``), if asked for.
    follow_ups: list[Any] = field(default_factory=list)

    @property
    def is_today(self) -> bool:
        """Whether it is today."""
        return self.day == timezone.localdate()


def month_calendar(projects: QuerySet[Project], year: int, month: int) -> list[list[CalendarDay]]:
    """The weeks of a month with the projects and phases of each day, Monday first (PRJ-028).

    The page draws the month with bars from :func:`calendars.month_weeks`
    (VFG-020); this is the same month as plain days.
    """
    from rentalars.schedule.calendars import month_weeks

    return [week.days for week in month_weeks(projects, year, month)]


def clock_text(moment: datetime.datetime, *, midnight_as_24: bool = False) -> str:
    """A time of day as the hover of the plans names it: "9:00 Uhr", "13:30 Uhr" (VFG-032)."""
    local = timezone.localtime(moment)
    hour = 24 if midnight_as_24 and local.hour == 0 and local.minute == 0 else local.hour
    # UIX-029: English names the time alone ("9:00"), German adds "Uhr".
    return pgettext("time of day", "%(time)s") % {"time": f"{hour}:{local.minute:02d}"}


def exact_period(start: datetime.datetime, end: datetime.datetime) -> str:
    """A period with its exact times, for the hover and the screen reader of a bar (VFG-032).

    "Mo 10.03., 9:00 Uhr bis 13:30 Uhr" within one day (an end at midnight is
    "24:00 Uhr"), "Mo 10.03., 22:00 Uhr bis Di 11.03., 2:00 Uhr" over
    midnight, "Mo 10.03. bis Fr 14.03." or "Mo 10.03., ganztägig" for whole
    days. The columns of a plan only show where a bar begins and ends
    approximately; the hover says it exactly.
    """
    begin, finish = timezone.localtime(start), timezone.localtime(end)
    midnight = datetime.time.min
    first_day = date_format(begin, local_pattern("D d.m."))
    if begin.time() == midnight and finish.time() == midnight:
        last = finish.date() - datetime.timedelta(days=1)
        if last <= begin.date():
            return _("%(day)s, all day") % {"day": first_day}
        return _("%(start)s to %(end)s") % {"start": first_day, "end": date_format(last, local_pattern("D d.m."))}
    next_midnight = finish.time() == midnight and finish.date() == begin.date() + datetime.timedelta(days=1)
    if finish.date() == begin.date() or next_midnight:
        times = _("%(start)s to %(end)s") % {
            "start": clock_text(begin),
            "end": clock_text(finish, midnight_as_24=True),
        }
        return f"{first_day}, {times}"
    return _("%(start)s to %(end)s") % {
        "start": f"{first_day}, {clock_text(begin)}",
        "end": f"{date_format(finish, local_pattern('D d.m.'))}, {clock_text(finish)}",
    }


def day_times(
    start: datetime.datetime, end: datetime.datetime, day_start: datetime.datetime, day_end: datetime.datetime
) -> str:
    """What a period means for one day: "08:00 – 18:00", "from 08:00", "until 18:00" or "all day"."""
    from django.utils.translation import gettext as _

    begins, finishes = start >= day_start, end <= day_end
    begin, finish = timezone.localtime(start).strftime("%H:%M"), timezone.localtime(end).strftime("%H:%M")
    if begins and finishes:
        return f"{begin} – {finish}"
    if begins:
        return _("from %(time)s") % {"time": begin}
    if finishes:
        return _("until %(time)s") % {"time": finish}
    return _("all day")


def week_calendar(projects: QuerySet[Project], monday: datetime.date) -> list[CalendarDay]:
    """The seven days of a week with every project and phase and their times on each day (PRJ-028).

    The week as a list of days. The page shows the week as a time grid
    (:func:`calendars.week_grid`, VFG-021); the times per day ("from 08:00",
    "all day") are the same.
    """
    days = day_range(monday, 7)
    span_start, span_end = bounds(days)
    shown = list(
        overlapping(projects, span_start, span_end)
        .select_related("customer", "venue_site", "parent")
        .order_by("start", "number")
    )
    phases = list(
        overlapping(ProjectPhase.objects.filter(project__in=[project.pk for project in shown]), span_start, span_end)
        .select_related("project", "venue_site")
        .order_by("start")
    )
    result = []
    for day in days:
        day_start, day_end = bounds([day])
        today = [project for project in shown if project.start < day_end and project.end > day_start]
        today_phases = [phase for phase in phases if phase.start < day_end and phase.end > day_start]
        result.append(
            CalendarDay(
                day=day,
                in_month=True,
                projects=today,
                phases=today_phases,
                entries=[
                    CalendarEntry(project, day_times(project.start, project.end, day_start, day_end))
                    for project in today
                ],
                phase_entries=[
                    CalendarEntry(phase, day_times(phase.start, phase.end, day_start, day_end))
                    for phase in today_phases
                ],
            )
        )
    return result


def project_timeline(
    projects: QuerySet[Project], scale: Scale | list[datetime.date], *, movable: Any = None
) -> list[tuple[Project, list[Bar]]]:
    """Rows of the timeline of projects: the reservation period and the phases (PRJ-028).

    ``scale`` gives the columns: days, or hours of a few days (VFG-022); a
    plain list of days means day columns.

    The parts of a whole project follow right after it, and their bars say
    whose part they are (PRJ-044).

    PRJ-092: a project has a row also where only one of its phases lies –
    the planning meeting weeks before the rental period, the follow-up work
    after the material is back –, as the month and week calendars show such
    phases as well. Its row then holds just the phase.

    VFG-026: in hour columns, ``movable`` – a function that is given the
    projects shown and returns the IDs of those the user may change
    (``schedule.moves.movable_project_ids``) – lets their rental period and
    phases be dragged: those bars carry :attr:`Bar.move`.
    """
    from rentalars.schedule.moves import PERIOD, PHASE
    from rentalars.schedule.moves import movable as movable_bar

    scale = scale if isinstance(scale, Scale) else Scale(days=scale)
    start, end = bounds(scale.days)
    shown = whole_first(
        projects_or_phases_in(projects, start, end).select_related("customer", "parent").order_by("start", "number")
    )
    phases: dict[int, list[ProjectPhase]] = {}
    for phase in overlapping(ProjectPhase.objects.filter(project__in=[p.pk for p in shown]), start, end).select_related(
        "venue_site"
    ):
        phases.setdefault(phase.project_id, []).append(phase)
    may_move = movable(shown) if movable is not None and scale.is_hourly else set()
    rows = []
    for project in shown:
        bars = []
        main = scale.bar(
            project.start,
            project.end,
            label=project.name,
            css=f"status-{project.status}",
            title=" · ".join(text for text in (str(project.get_status_display()), part_of(project)) if text),
            record=project,
        )
        if main is not None:
            if project.pk in may_move:
                main.move = movable_bar(project, PERIOD, project.start, project.end, scale)
            bars.append(main)
        for phase in sorted(phases.get(project.pk, []), key=lambda item: item.start):
            bar = scale.bar(phase.start, phase.end, label=phase.label, css="phase", title=phase.place, record=phase)
            if bar is not None:
                if project.pk in may_move:
                    bar.move = movable_bar(
                        project,
                        PHASE,
                        phase.start,
                        phase.end,
                        scale,
                        phase=phase,
                        name=f"{project.number} {phase.label}",
                    )
                bars.append(bar)
        rows.append((project, bars))
    return rows


# --- Hour columns for one to ten days (VFG-022, VFG-024) -------------------------------------------

#: VFG-024: the timeline and the personnel plan show 1 to 10 days in hour columns.
MIN_DAYS = 1
MAX_DAYS = 10

#: The number of days offered when switching from weeks to days, unless another was chosen before.
#: VFG-028: four days, and the pages of the planning open with them (three).
DEFAULT_DAYS = 4

#: Hours per column to choose from; each divides the 24 hours of a day.
HOUR_STEPS = (1, 2, 3, 6)

#: At most this many hour columns are in view at once, so that their headings stay readable.
MAX_VISIBLE_COLUMNS = 40

#: VFG-033: in hour columns the page holds the chosen span and this many spans before and after it, to scroll
#: into (one each).
SPANS_AROUND = 2


def hours_per_column(days: int) -> int:
    """The finest hour step that keeps the columns of ``days`` days readable (VFG-024).

    1 day: one hour per column; 2 and 3 days: two hours; 4 and 5 days: three
    hours; 6 to 10 days: six hours – at most 40 columns in view. The bars are
    exact to the minute whatever the step; the step only sets the headings
    and the lines behind the bars.
    """
    return next((step for step in HOUR_STEPS if days * 24 // step <= MAX_VISIBLE_COLUMNS), HOUR_STEPS[-1])


@dataclass(frozen=True)
class ColumnHead:
    """The heading of one hour column (VFG-022)."""

    label: str
    title: str
    css: str = ""


@dataclass
class Scale:
    """The columns of a timeline: one per day, or one per one to six hours (VFG-022, VFG-024).

    In the week modes every column is a day (``hours`` = 24) and the days are
    exactly the chosen weeks. For 1 to 10 days a column covers some hours
    (:func:`hours_per_column`), and ``days`` holds the chosen span plus
    :data:`SPANS_AROUND` spans before and after it (VFG-033): the bar area scrolls sideways, and the page opens scrolled to
    the chosen span (``focus`` is the index of its first column, ``visible``
    the number of its columns).

    Hour columns follow the wall clock: every day has 24 hours of them, also
    the days the clocks change.
    """

    days: list[datetime.date]
    hours: int = 24
    focus: int = 0
    visible: int = 0

    def __post_init__(self) -> None:
        if not self.visible:
            self.visible = self.columns

    @property
    def columns(self) -> int:
        """Number of columns."""
        return len(self.days) * 24 // self.hours

    @property
    def is_hourly(self) -> bool:
        """Whether the columns are hours rather than days."""
        return self.hours < 24

    @property
    def per_day(self) -> int:
        """Columns per day."""
        return 24 // self.hours

    def offset(self, moment: datetime.datetime) -> float:
        """Hours on the wall clock from the start of the first day to a moment."""
        local = timezone.localtime(moment).replace(tzinfo=None)
        return (local - datetime.datetime.combine(self.days[0], datetime.time.min)).total_seconds() / 3600

    def bar(self, start: datetime.datetime, end: datetime.datetime, **fields: Any) -> Bar | None:
        """The bar of a period, or ``None`` if it lies outside.

        The bar covers every column the period touches – at least one – and
        knows which parts of its first and last column lie before the start
        and after the end (``lead``, ``trail``). The bar does not fill
        those columns completely; otherwise a phase would look longer than it
        lasted: a setup from 14:00 to 20:00 filled the whole day, one from
        22:00 to 02:00 two days, one from 07:30 to 08:15 two columns of two
        hours each. What lies outside the shown days is cut off without a
        margin.
        """
        begin, finish = self.offset(start), self.offset(end)
        total = self.columns * self.hours
        if finish <= 0 or begin >= total:
            return None
        first = max(0, math.floor(begin / self.hours))
        last = min(self.columns - 1, max(first, math.ceil(finish / self.hours) - 1))
        area_start, area_end = first * self.hours, (last + 1) * self.hours
        width = area_end - area_start
        lead = min(max(begin - area_start, 0.0), width) / width
        trail = min(max(area_end - finish, 0.0), width - lead * width) / width
        return Bar(first=first + 1, last=last + 1, lead=lead, trail=trail, **fields)

    @property
    def day_heads(self) -> list[tuple[datetime.date, str]]:
        """Every day with the CSS classes of its heading (weekend, today)."""
        today = timezone.localdate()
        return [
            (day, " ".join(name for name, on in (("weekend", day.weekday() >= 5), ("today", day == today)) if on))
            for day in self.days
        ]

    @property
    def hour_heads(self) -> list[ColumnHead]:
        """The headings of the hour columns: "08", with the day and hours as title."""
        heads = []
        for day in self.days:
            for index in range(self.per_day):
                hour = index * self.hours
                title = f"{date_format(day, local_pattern('D d.m.'))}, {hour:02d}:00–{(hour + self.hours) % 24:02d}:00"
                heads.append(ColumnHead(label=f"{hour:02d}", title=title, css="day-start" if index == 0 else ""))
        return heads

    @property
    def periods(self) -> list[tuple[datetime.datetime, datetime.datetime]]:
        """Start and end of every column, on the wall clock like the columns themselves (VFG-029)."""
        zone = timezone.get_current_timezone()
        starts = [
            datetime.datetime.combine(day, datetime.time(index * self.hours), tzinfo=zone)
            for day in self.days
            for index in range(self.per_day)
        ]
        ends = [
            *starts[1:],
            datetime.datetime.combine(self.days[-1] + datetime.timedelta(days=1), datetime.time.min, tzinfo=zone),
        ]
        return list(zip(starts, ends, strict=True))

    @property
    def spans(self) -> int:
        """How many times the chosen span fits into the columns: 1 for weeks, 5 for days in hours (VFG-033)."""
        return max(1, self.columns // max(1, self.visible))

    @property
    def span_days(self) -> int:
        """The number of days in view in hour columns, 0 for weeks (VFG-033: the style sheet adds hourly lines)."""
        return self.visible * self.hours // 24 if self.is_hourly else 0

    @property
    def grid_style(self) -> str:
        """Custom properties of the grid: columns, days (lines between days), hours per column, spans (VFG-033)."""
        return f"--cols: {self.columns}; --days: {len(self.days)}; --hours: {self.hours}; --spans: {self.spans}"

    @property
    def row_style(self) -> str:
        """``grid-template-columns`` of a row of bars."""
        if self.is_hourly:
            return f"grid-template-columns: repeat({self.columns}, minmax(0, 1fr))"
        return f"grid-template-columns: repeat({self.columns}, minmax(28px, 1fr))"


def day_count_of(value: Any) -> int:
    """A number of days for the hour columns (1 to 10), or 0 if the value is none (VFG-024)."""
    text = str(value or "")
    return int(text) if text.isdigit() and MIN_DAYS <= int(text) <= MAX_DAYS else 0


def scale_from_request(request: Any, *, default_weeks: int = 4, default_days: int = 0) -> tuple[Scale, dict[str, Any]]:
    """The columns asked for: weeks of days, or ``days`` = 1 to 10 with hour columns (VFG-022, VFG-024).

    ``from`` and ``weeks`` keep their meaning from before (1 to 12 weeks of
    day columns, see :func:`span_from_request`). ``days`` switches to hour
    columns for that many days starting on ``from`` (default: today);
    ``weeks`` is then kept for the way back. Another value of ``days`` means
    weeks. "Earlier" and "later" move by the shown span. ``day_count`` is the
    number of days the switch to days offers.

    VFG-028: with ``default_days`` an address that asks for neither ``days``
    nor ``weeks`` shows that many days in hours; without it, weeks as before.
    """
    today = timezone.localdate()
    asked = request.GET.get("days", "")
    if not asked and "weeks" not in request.GET and default_days:
        asked = str(default_days)
    count = day_count_of(asked)
    if not count:
        days, navigation = span_from_request(request, default_weeks=default_weeks)
        first, last = days[0], days[-1]
        navigation.update(
            zoom=0,
            last=last,
            today_from=navigation["this_week"],
            day_from=today if first <= today <= last else first,
            week_from=first,
            day_count=DEFAULT_DAYS,
            day_choices=day_choices(),
        )
        return Scale(days=days), navigation
    first = query_date(request.GET.get("from")) or today
    try:
        weeks = max(1, min(MAX_WEEKS, int(request.GET.get("weeks", default_weeks))))
    except ValueError:
        weeks = default_weeks
    hours = hours_per_column(count)
    per_span = count * 24 // hours
    # VFG-033: two spans before and two after the chosen one to scroll into (one each).
    scale = Scale(
        days=day_range(first - datetime.timedelta(days=count * SPANS_AROUND), (2 * SPANS_AROUND + 1) * count),
        hours=hours,
        focus=per_span * SPANS_AROUND,
        visible=per_span,
    )
    navigation = {
        "first": first,
        "last": first + datetime.timedelta(days=count - 1),
        "zoom": count,
        "weeks": weeks,
        "earlier": first - datetime.timedelta(days=count),
        "later": first + datetime.timedelta(days=count),
        "this_week": monday_of(today),
        "today_from": today,
        "day_from": first,
        "week_from": monday_of(first),
        "week_choices": sorted({1, 2, 4, 8, 12, weeks}),
        "day_count": count,
        "day_choices": day_choices(),
    }
    return scale, navigation


def day_choices() -> list[int]:
    """The numbers of days the control offers (VFG-024)."""
    return list(range(MIN_DAYS, MAX_DAYS + 1))


# --- Material utilization in days or hours (VFG-012, VFG-029) ----------------------------------------

#: VFG-025: the kinds the material utilization shows – those with stock, and kits and their components (VFG-037).
UTILIZATION_KINDS = STOCK_KINDS | {ProductKind.KIT.value}


@dataclass
class LoadRun:
    """Neighbouring hour columns of the utilization with the same load, drawn as one cell (VFG-029).

    Ten days in six-hour columns are 120 columns per product; most of them
    hold the same figure as their neighbours. One cell per run keeps the
    page small and the figures readable.
    """

    first: int
    last: int
    load: Any
    start: datetime.datetime
    end: datetime.datetime

    @property
    def style(self) -> str:
        """``grid-column`` value."""
        return f"grid-column: {self.first} / {self.last + 1}"

    @property
    def stock(self) -> int:
        """The plannable stock, as a day's load names it."""
        return self.load.stock

    @property
    def period(self) -> str:
        """The period of the run in words: "Mo 01.03. 06:00–18:00", or with two dates over midnight."""
        start, end = timezone.localtime(self.start), timezone.localtime(self.end)
        begin = f"{date_format(start, local_pattern('D d.m.'))} {start:%H:%M}"
        if end.date() == start.date():
            return f"{begin}–{end:%H:%M}"
        if end.time() == datetime.time.min and end.date() == start.date() + datetime.timedelta(days=1):
            return f"{begin}–24:00"
        return f"{begin} – {date_format(end, local_pattern('D d.m.'))} {end:%H:%M}"


@dataclass
class UtilizationRow:
    """One row of the material utilization (VFG-012) – a product, a kit, or a component of a kit.

    ``loads`` holds a :class:`~rentalars.availability.services.DayLoad` per
    column, or :class:`LoadRun` cells in hour columns (VFG-029).

    VFG-037: for a kit the loads count complete
    kits (:func:`kit_loads`), and ``parts`` holds a row per component with
    ``per_kit``, the pieces one kit needs.
    """

    product: Any
    loads: list[Any]
    parts: list[UtilizationRow] = field(default_factory=list)
    per_kit: int = 0

    def __iter__(self) -> Any:
        """Unpack as ``product, loads`` – as a pair."""
        return iter((self.product, self.loads))

    @property
    def is_kit(self) -> bool:
        """Whether the row counts complete kits."""
        return bool(self.parts)

    @property
    def stock(self) -> int:
        """The plannable stock – of complete kits for a kit –, as the first column names it."""
        return self.loads[0].stock if self.loads else 0


def kit_loads(per_kit: dict[int, int], loads: dict[int, list[Any]]) -> list[Any]:
    """How many complete kits are reserved and free in each column (VFG-037; VFG-008).

    As the availability engine answers for a kit over one period
    (``AvailabilityEngine._kit_availability``), here column by column: a
    kit is in stock as often as its scarcest component allows, and free as
    often as the free pieces of its scarcest component allow. ``firm`` are
    the kits the firm reservations take, ``optional`` those options take in
    addition – so that ``free`` is the number of complete kits still free.
    More reserved of a component than there is makes ``firm`` exceed
    ``stock``: a shortage, as for a product.

    Example: a kit needs 2 speakers and 1 stand; 9 speakers (4 reserved) and
    3 stands (1 reserved, 1 more as an option) give a stock of 3 kits, 2
    free and 1 free after the options – ``firm`` 1, ``optional`` 1.

    Args:
        per_kit: Component product → pieces one kit needs; only components
            with stock of their own (those in ``loads``).
        loads: The loads of the components, a list of equal length each.
    """
    from rentalars.availability.services import DayLoad

    columns = zip(*(loads[component_id] for component_id in per_kit), strict=True)
    quantities = list(per_kit.values())
    result = []
    for column in columns:
        stock = min(load.stock // quantity for load, quantity in zip(column, quantities, strict=True))
        free = min((load.stock - load.firm) // quantity for load, quantity in zip(column, quantities, strict=True))
        after_options = min(
            (load.stock - load.firm - load.optional) // quantity
            for load, quantity in zip(column, quantities, strict=True)
        )
        first = column[0]
        result.append(
            DayLoad(
                day=first.day,
                firm=stock - free,
                optional=free - after_options,
                stock=stock,
                start=first.start,
                end=first.end,
            )
        )
    return result


def loads_with_kits(products: list[Any], measure: Any) -> list[UtilizationRow]:
    """The utilization rows of products and kits, measured once for all (VFG-012; VFG-037).

    A kit is measured through the base products it finally consists of
    (``products.services.flatten_kit``: kits inside kits are resolved, their
    quantities multiplied); its components follow in the order of the kit.
    Products without stock of their own are left out, and so is a kit none
    of whose components has stock.

    Args:
        products: The products and kits to show, in order.
        measure: ``measure(product_ids)`` returns the loads of those of the
            products that have stock of their own – ``availability.services.utilization``
            or ``utilization_in_periods`` with the columns bound.
    """
    from rentalars.products.models import Product
    from rentalars.products.services import flatten_kit, load_kit_structure

    kits = [product for product in products if product.is_kit]
    structure = load_kit_structure() if kits else {}
    parts = {kit.pk: flatten_kit(kit.pk, structure) for kit in kits}
    component_ids = [component_id for flat in parts.values() for component_id in flat]
    ids = list(dict.fromkeys([product.pk for product in products if not product.is_kit] + component_ids))
    loads = measure(ids) if ids else {}
    components = Product.objects.select_related("unit").in_bulk(component_ids) if component_ids else {}
    rows: list[UtilizationRow] = []
    for product in products:
        if not product.is_kit:
            if product.pk in loads:
                rows.append(UtilizationRow(product, loads[product.pk]))
            continue
        per_kit = {
            component_id: quantity
            for component_id, quantity in parts[product.pk].items()
            if component_id in loads and quantity > 0
        }
        if not per_kit:
            continue
        part_rows = [
            UtilizationRow(components[component_id], loads[component_id], per_kit=quantity)
            for component_id, quantity in per_kit.items()
        ]
        rows.append(UtilizationRow(product, kit_loads(per_kit, loads), parts=part_rows))
    return rows


def _join_runs(loads: list[Any], periods: list[tuple[datetime.datetime, datetime.datetime]]) -> list[LoadRun]:
    """Neighbouring hour columns with the same figures as one :class:`LoadRun` each (VFG-029)."""
    runs: list[LoadRun] = []
    for index, load in enumerate(loads, start=1):
        last = runs[-1] if runs else None
        if last is not None and (last.load.firm, last.load.optional) == (load.firm, load.optional):
            last.last, last.end = index, periods[index - 1][1]
        else:
            runs.append(LoadRun(first=index, last=index, load=load, start=load.start, end=load.end))
    return runs


def utilization_rows(products: list[Any], scale: Scale) -> list[UtilizationRow]:
    """The rows of the material utilization: per product its loads by day, or runs of hour columns (VFG-029).

    In the week modes a row holds one :class:`~rentalars.availability.services.DayLoad`
    per day, as since 0.4. In hour columns (one to ten days, as on the
    timeline and the personnel plan) it holds :class:`LoadRun` cells: the
    peak within each column, neighbouring columns with the same figures
    joined. Products without stock of their own are left out. The same
    queries as for days, whatever the number of columns.

    VFG-037: a kit has a row of complete kits, with
    the rows of its components (:func:`loads_with_kits`).
    """
    from rentalars.availability.services import utilization, utilization_in_periods

    if not scale.is_hourly:
        return loads_with_kits(products, lambda ids: utilization(ids, scale.days))
    periods = scale.periods
    rows = loads_with_kits(products, lambda ids: utilization_in_periods(ids, periods))
    for row in rows:
        row.loads = _join_runs(row.loads, periods)
        for part in row.parts:
            part.loads = _join_runs(part.loads, periods)
    return rows


def utilization_address(product_id: int, start: datetime.datetime, end: datetime.datetime) -> str:
    """The material utilization with one product over a period (PRD-051).

    Up to ten days are shown in hour columns (``days``), longer periods in
    weeks of days (``weeks``, at most twelve) – from the first day of the
    period on (VFG-029).

    Example: 10 March 08:00 to 24 March 08:00 gives
    ``/schedule/products/?product=7&from=2027-03-10&weeks=3``.
    """
    first = timezone.localtime(start).date()
    until = timezone.localtime(end)
    last = until.date() - datetime.timedelta(days=1) if until.time() == datetime.time.min else until.date()
    count = max((last - first).days + 1, 1)
    query = f"product={product_id}&from={first.isoformat()}"
    if count <= MAX_DAYS:
        query += f"&days={count}"
    else:
        query += f"&weeks={min(MAX_WEEKS, math.ceil(count / 7))}"
    return f"{reverse('schedule:products')}?{query}"


# --- Personnel plan (VFG-014, VFG-023) ----------------------------------------------------------

#: Why a person is marked in the personnel plan (VFG-023, PRJ-022), in the order they are named.
WARNING_DOUBLE_BOOKING = "double_booking"
WARNING_ABSENCE = "absence"
WARNING_UNAVAILABLE = "unavailable"
WARNING_ORDER = (WARNING_DOUBLE_BOOKING, WARNING_ABSENCE, WARNING_UNAVAILABLE)


def warning_labels() -> dict[str, str]:
    """The text of each warning of the personnel plan (VFG-023)."""
    return {
        WARNING_DOUBLE_BOOKING: _("Deployments overlap each other"),
        WARNING_ABSENCE: _("Planned during an absence"),
        WARNING_UNAVAILABLE: _("Planned although marked as not available"),
    }


def _overlap(first: Any, second: Any) -> bool:
    return first.start < second.end and second.start < first.end


def find_warnings(deployments: list[Any], absences: list[Any], unavailable: list[Any]) -> tuple[list[str], set[int]]:
    """What is wrong with the plan of one person, and which entries take part (VFG-023, PRJ-022).

    Compared are the real times, not the columns: two deployments on the
    same day, one in the morning and one in the evening, are no double
    booking. Periods that only touch – one ends when the next begins – do
    not overlap either.

    Args:
        deployments: Crew lines of the person (anything with ``start`` and ``end``).
        absences: Absences of the person.
        unavailable: Periods the person marked as not available.

    Returns:
        The warnings in the order of :data:`WARNING_ORDER`, and the ``id()``
        of every entry that takes part in one.
    """
    found: set[str] = set()
    involved: set[int] = set()
    for index, line in enumerate(deployments):
        for other in deployments[index + 1 :]:
            if _overlap(line, other):
                found.add(WARNING_DOUBLE_BOOKING)
                involved.update((id(line), id(other)))
        for code, periods in ((WARNING_ABSENCE, absences), (WARNING_UNAVAILABLE, unavailable)):
            for period in periods:
                if _overlap(line, period):
                    found.add(code)
                    involved.update((id(line), id(period)))
    return [code for code in WARNING_ORDER if code in found], involved


@dataclass
class PlanRow:
    """One person in the personnel plan (VFG-014, VFG-023).

    ``availability`` is the top bar: what the person said about themselves
    (available, with limits, not available) and the absences the planning
    entered. ``bars`` are the deployments below it.
    """

    person: Any
    availability: list[Bar] = field(default_factory=list)
    bars: list[Bar] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def conflict(self) -> bool:
        """Whether anything needs attention."""
        return bool(self.warnings)

    @property
    def warning_text(self) -> str:
        """The warnings as one sentence, for the badge and its text alternative."""
        labels = warning_labels()
        return "; ".join(labels[code] for code in self.warnings)


def crew_bar_css(line: CrewLine) -> str:
    """The CSS classes of a deployment bar in the personnel plan and on a person's timeline (VFG-027).

    ``crew`` gives the bar the colours of the legend "deployments": firm
    (orange) as soon as the project is confirmed – also while it is out,
    back or closed –, option (yellow), inquiry (grey). The bar does not
    take the colours of the project statuses of the calendar, of which the
    legend names only two, and showed them as a thin edge only.
    ``requested``: the person was asked and has not answered yet.
    """
    css = f"crew status-{line.project.status}"
    return css + " requested" if line.request_status == "requested" else css


def people_in_plan(
    people: QuerySet[Any], start: datetime.datetime, end: datetime.datetime, *, busy_only: bool = False
) -> QuerySet[Any]:
    """The people the personnel plan shows (VFG-014, VFG-023; fix).

    Without "Only people with deployments or absences" (``busy_only``) every
    person given – the active ones – is in the plan, also office accounts
    without a job function (every account is a person, AUT-026). The plan
    includes people without a job function whether or not they were
    deployed in the span, so that the unticked box did not show everybody.
    With ``busy_only`` only people with a deployment or an absence in the
    span remain.
    """
    if busy_only:
        return people.filter(busy_people_filter(start, end)).distinct()
    return people


def _joined(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


def conflict_text() -> str:
    """What the hover and the screen reader add to a bar that takes part in a warning (VFG-032)."""
    return _("conflict")


def personnel_rows(people: QuerySet[Any], scale: Scale, *, movable: Any = None) -> list[PlanRow]:
    """Rows of the personnel plan: availability on top, deployments below, warnings (VFG-014, VFG-023).

    Four queries, whatever the number of people: the people, their
    deployments, absences and availability entries in the span.

    VFG-032: the title of every bar – the hover, and the hidden text of the
    screen reader – names its exact times (:func:`exact_period`) and, for a
    bar that takes part in a warning, "conflict"; such a deployment is
    filled red by the style sheet (``is-conflict``).

    VFG-031: in hour columns, ``movable`` – a function that is given the
    projects of the deployments shown and returns the IDs of those the user
    may change (``schedule.moves.movable_project_ids``) – lets their
    deployments be dragged like the phases on the timeline (VFG-026): those
    bars carry :attr:`Bar.move`. At most one query more, for a role limited
    to assigned projects.
    """
    from rentalars.personnel.marks import effective_periods
    from rentalars.personnel.models import Absence, AvailabilitySource, AvailabilityState
    from rentalars.schedule.moves import CREW
    from rentalars.schedule.moves import movable as movable_bar

    start, end = bounds(scale.days)
    rows = {person.pk: PlanRow(person=person) for person in people}
    lines: dict[int, list[CrewLine]] = {}
    for line in (
        overlapping(CrewLine.objects.filter(person__in=people), start, end)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .select_related("project__parent", "job_function")
        .order_by("start")
    ):
        lines.setdefault(line.person_id, []).append(line)
    absences: dict[int, list[Any]] = {}
    for absence in overlapping(Absence.objects.filter(person__in=people), start, end).order_by("start"):
        absences.setdefault(absence.person_id, []).append(absence)
    # PER-027: one availability at any moment; busy times of the linked calendar as blocks.
    marks: dict[int, list[Any]] = dict(effective_periods(rows.keys(), start, end))
    states = dict(AvailabilityState.choices)
    from_feed = _("from the linked calendar")
    may_move: set[int] = set()
    if movable is not None and scale.is_hourly:
        projects = {line.project_id: line.project for own in lines.values() for line in own}
        may_move = movable(list(projects.values())) if projects else set()

    for person_id, row in rows.items():
        own_lines, own_absences, own_marks = (
            lines.get(person_id, []),
            absences.get(person_id, []),
            marks.get(person_id, []),
        )
        unavailable = [mark for mark in own_marks if mark.state == AvailabilityState.UNAVAILABLE]
        row.warnings, involved = find_warnings(own_lines, own_absences, unavailable)

        for line in own_lines:
            css = crew_bar_css(line)
            bar = scale.bar(
                line.start,
                line.end,
                label=f"{line.project.number} {line.job_function.name}",
                css=css,
                # PRJ-044, PRJ-048: a deployment in a part names the whole project as well.
                title=_joined(short_name(line.project), exact_period(line.start, line.end)),
                conflict=id(line) in involved,  # class and hover from the one flag
                url=reverse("projects:overview", args=[line.project]),
                record=line,
            )
            if bar is not None:
                if line.project_id in may_move:
                    bar.move = movable_bar(
                        line.project,
                        CREW,
                        line.start,
                        line.end,
                        scale,
                        crew_line=line,
                        name=f"{row.person.name}: {line.project.number} {line.job_function.name}",
                    )
                row.bars.append(bar)
        for mark in own_marks:
            css = f"availability is-{mark.state}" + (" from-feed" if mark.source == AvailabilitySource.FEED else "")
            bar = scale.bar(
                mark.start,
                mark.end,
                label=str(states.get(mark.state, mark.state)),
                css=css,
                title=_joined(
                    exact_period(mark.start, mark.end),
                    mark.note,
                    from_feed if mark.source == AvailabilitySource.FEED else "",
                ),
                conflict=id(mark) in involved,
                record=mark,
            )
            if bar is not None:
                row.availability.append(bar)
        for absence in own_absences:
            bar = scale.bar(
                absence.start,
                absence.end,
                label=absence.get_kind_display(),
                css="absence",
                title=_joined(exact_period(absence.start, absence.end), absence.note),
                conflict=id(absence) in involved,
                record=absence,
            )
            if bar is not None:
                row.availability.append(bar)
        row.bars.sort(key=lambda bar: bar.first)
        row.availability.sort(key=lambda bar: bar.first)
    return list(rows.values())


def has_conflicts(bars: list[Bar]) -> bool:
    """Whether bars of one row overlap – a person planned twice, or planned while absent."""
    ordered = sorted(bars, key=lambda bar: bar.first)
    return any(later.first <= earlier.last for earlier, later in itertools.pairwise(ordered))


def busy_people_filter(start: datetime.datetime, end: datetime.datetime) -> Q:
    """People with a deployment or absence in the span."""
    return Q(crew_lines__start__lt=end, crew_lines__end__gt=start) | Q(absences__start__lt=end, absences__end__gt=start)
