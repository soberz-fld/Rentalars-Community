# SPDX-License-Identifier: GPL-3.0-or-later
"""The month and the week of the calendar, laid out for the page (PRJ-028, PRJ-067, VFG-020, VFG-021).

Month (VFG-020)
    Each week is one row of seven days. A project that lasts several days is
    one continuous bar over its days in that row; at the end of the week it
    breaks and continues in the next row. Bars are stacked in lanes: each
    bar takes the lowest lane that is free on all of its days. Projects
    beyond the lanes shown are counted per day ("+3").

Week (VFG-021)
    A time grid like that of a desktop calendar: one column per day, the
    hours from top to bottom. Whatever lasts 24 hours or more, or exactly
    whole days, lies in the all-day strip at the top, again as bars in
    lanes. Everything shorter is a block in its day column, placed and sized
    by its start and end; a block that crosses midnight is split into one
    piece per day. Blocks that overlap stand side by side. Projects and
    their phases (PRJ-006) are both shown, phases framed in dashes.

Positions are plain numbers (columns, lanes, hours as decimals) that the
templates hand to CSS through custom properties; nothing here knows pixels.
All of it is computed from two queries – the projects and their phases –
whatever their number (NFA-012).

Options (VFG-039)
    Whether the phases of the projects are shown (``phases``, as
    by default), and whether the follow-ups (PRJ-105, PRJ-109) the user may
    see are shown (``follow_ups``, a queryset of projects and service cases
    with a follow-up): in the month under the bars of their day, in the week
    at their time – one without a time in the all-day strip. One more query.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Any

from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.projects.family_labels import part_of, short_name
from rentalars.projects.models import Project, ProjectKind, ProjectPhase
from rentalars.schedule.services import CalendarDay, bounds, day_range, day_times, monday_of, overlapping

#: Lanes of bars a week row of the month shows; further projects are counted per day.
MONTH_LANES = 5

#: Lanes of the all-day strip of the week before "show all" is needed.
WEEK_ALL_DAY_LANES = 3

#: The hour the week grid opens at, unless something starts earlier (VFG-021).
DAY_STARTS_AT = 6

#: Shorter blocks are laid out as if they lasted this long, so that their text stays readable.
SHORTEST_BLOCK_HOURS = 0.75

#: The narrowest a block may get, in pixels: a day with blocks side by side widens its column instead.
LANE_MIN_WIDTH = 62

#: VFG-039: how long a follow-up with a time stands in the week grid – a mark, not an appointment.
FOLLOW_UP_MINUTES = 30


def _local_naive(moment: datetime.datetime) -> datetime.datetime:
    return timezone.localtime(moment).replace(tzinfo=None)


def _moment(value: datetime.datetime) -> str:
    return date_format(timezone.localtime(value), local_pattern("d.m. H:i"))


def period_text(start: datetime.datetime, end: datetime.datetime) -> str:
    """A period for titles and screen readers: "10.03. 08:00 – 12.03. 18:00"."""
    return f"{_moment(start)} – {_moment(end)}"


def lasts_whole_days(start: datetime.datetime, end: datetime.datetime) -> bool:
    """Whether a period belongs in the all-day strip: 24 hours or more, or from midnight to midnight.

    Measured on the wall clock, so that the day the clocks change counts as
    a whole day as well.
    """
    local_start, local_end = _local_naive(start), _local_naive(end)
    if local_end - local_start >= datetime.timedelta(hours=24):
        return True
    return local_start.time() == datetime.time.min and local_end.time() == datetime.time.min


@dataclass
class Segment:
    """A bar within one row of days: of the month's week, or of the week's all-day strip.

    ``first`` and ``last`` are columns counted from 1; ``lane`` counts from 0.
    """

    record: Any
    project: Project
    first: int
    last: int
    label: str
    css: str
    title: str
    url: str
    #: The bar began before the row / goes on after it.
    starts_before: bool = False
    ends_after: bool = False
    #: "from 08:00" / "until 18:00" where the period starts or ends within the row, not at midnight.
    start_note: str = ""
    end_note: str = ""
    lane: int = 0
    shown: bool = True
    sort_key: tuple[Any, ...] = ()
    #: VFG-039: what the entry is, said instead of the status – "Follow-up".
    kind_label: str = ""

    @property
    def style(self) -> str:
        """Place in the grid of the row: the columns, and the lane below the line of dates."""
        return f"grid-column: {self.first} / {self.last + 1}; grid-row: {self.lane + 2}"

    @property
    def strip_style(self) -> str:
        """Place in the all-day strip of the week, which has no line of dates."""
        return f"grid-column: {self.first} / {self.last + 1}; grid-row: {self.lane + 1}"

    @property
    def status_label(self) -> str:
        """The status of the project, said in words – colour is never the only sign; or what the entry is."""
        return self.kind_label or str(self.project.get_status_display())


def _segment(
    record: Any, project: Project, days: list[datetime.date], *, label: str, css: str, title: str
) -> Segment | None:
    """The segment of a project or phase within a row of days, or ``None`` if it lies outside."""
    start, end = record.start, record.end
    local_start = _local_naive(start)
    # A period that ends at midnight does not occupy the following day.
    local_last = _local_naive(end - datetime.timedelta(seconds=1))
    if local_last.date() < days[0] or local_start.date() > days[-1]:
        return None
    first = max(0, (local_start.date() - days[0]).days) + 1
    last = min(len(days) - 1, (local_last.date() - days[0]).days) + 1
    starts_before, ends_after = local_start.date() < days[0], local_last.date() > days[-1]
    local_end = _local_naive(end)
    start_note = ""
    if not starts_before and local_start.time() != datetime.time.min:
        start_note = _("from %(time)s") % {"time": local_start.strftime("%H:%M")}
    end_note = ""
    if not ends_after and local_end.time() != datetime.time.min:
        end_note = _("until %(time)s") % {"time": local_end.strftime("%H:%M")}
    return Segment(
        record=record,
        project=project,
        first=first,
        last=last,
        label=label,
        css=css,
        title=title,
        url=reverse("projects:overview", args=[project]),
        starts_before=starts_before,
        ends_after=ends_after,
        start_note=start_note,
        end_note=end_note,
        sort_key=(start, getattr(project, "number", "")),
    )


def assign_lanes(segments: list[Segment]) -> int:
    """Stack segments in lanes: each takes the lowest lane free on all its columns (VFG-020).

    Earlier segments go first, and of those starting on the same day the
    longer one, so that long bars stay at the top and the rows stay calm.

    Returns:
        The number of lanes used.
    """
    lane_ends: list[int] = []
    for segment in sorted(segments, key=lambda item: (item.first, item.first - item.last, item.sort_key)):
        for lane, last in enumerate(lane_ends):
            if last < segment.first:
                segment.lane, lane_ends[lane] = lane, segment.last
                break
        else:
            segment.lane = len(lane_ends)
            lane_ends.append(segment.last)
    return len(lane_ends)


def hide_beyond(segments: list[Segment], lanes: int, columns: int) -> list[int]:
    """Hide the segments beyond the first ``lanes`` lanes; how many are hidden per column."""
    hidden = [0] * columns
    for segment in segments:
        segment.shown = segment.lane < lanes
        if not segment.shown:
            for column in range(segment.first, segment.last + 1):
                hidden[column - 1] += 1
    return hidden


def project_title(project: Project) -> str:
    """What the title of a bar says: number, name, whole project of a part (PRJ-044), customer, venue, period."""
    parts = [f"{project.number} {project.name}"]
    if project.parent_id:
        parts.append(part_of(project))
    if project.customer_id:
        parts.append(project.customer.name)
    if project.venue_label:
        parts.append(project.venue_label)
    parts.append(period_text(project.start, project.end))
    return " · ".join(parts)


def phase_title(phase: ProjectPhase) -> str:
    """What the title of a phase says: phase, project, place, period."""
    parts = [f"{phase.label}: {phase.project.number} {short_name(phase.project)}"]
    if phase.place:
        parts.append(phase.place)
    parts.append(period_text(phase.start, phase.end))
    return " · ".join(parts)


# --- Month (VFG-020) ------------------------------------------------------------------------------


@dataclass
class MonthWeek:
    """One row of the month: seven days, the bars over them, and what did not fit."""

    days: list[CalendarDay]
    segments: list[Segment]
    lanes: int
    hidden: list[int]

    @property
    def number(self) -> int:
        """Calendar week (ISO)."""
        return self.days[0].day.isocalendar().week

    @property
    def shown_lanes(self) -> int:
        """Lanes drawn in this row."""
        return min(self.lanes, MONTH_LANES)

    @property
    def rows_style(self) -> str:
        """``grid-template-rows``: the line of dates, one row per lane, then room for the rest."""
        lanes = f" repeat({self.shown_lanes}, auto)" if self.shown_lanes else ""
        return f"grid-template-rows: auto{lanes} 1fr"

    @property
    def extra_row(self) -> int:
        """The grid row below the lanes: "+3" and the phases of the day."""
        return self.shown_lanes + 2

    @property
    def cells(self) -> list[tuple[CalendarDay, int, int]]:
        """Every day with its column and the number of its projects not drawn."""
        return [(day, index + 1, self.hidden[index]) for index, day in enumerate(self.days)]


def month_weeks(
    projects: QuerySet[Project],
    year: int,
    month: int,
    *,
    phases: bool = True,
    follow_ups: QuerySet[Project] | None = None,
) -> list[MonthWeek]:
    """The weeks of a month with the projects as continuous bars (PRJ-028, VFG-020).

    Two queries: the projects of the shown weeks and their phases. VFG-039: without
    ``phases`` no phases; with ``follow_ups`` the follow-ups of these projects and cases on their days.
    """
    first = datetime.date(year, month, 1)
    start = monday_of(first)
    following = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    end = following + datetime.timedelta(days=(7 - following.weekday()) % 7)
    days = day_range(start, (end - start).days)
    span_start, span_end = bounds(days)
    shown = list(
        overlapping(projects, span_start, span_end)
        .select_related("customer", "venue_site", "parent")
        .order_by("start", "number")
    )
    shown_phases = (
        list(
            overlapping(ProjectPhase.objects.filter(project__in=projects), span_start, span_end)
            .select_related("project")
            .order_by("start")
        )
        if phases
        else []
    )
    marks = follow_ups_of(follow_ups, days)
    weeks = []
    for offset in range(0, len(days), 7):
        week_days = days[offset : offset + 7]
        cells = []
        for day in week_days:
            day_start, day_end = bounds([day])
            cells.append(
                CalendarDay(
                    day=day,
                    in_month=day.month == month,
                    projects=[project for project in shown if project.start < day_end and project.end > day_start],
                    phases=[phase for phase in shown_phases if phase.start < day_end and phase.end > day_start],
                    follow_ups=[mark for mark in marks if mark.day == day],
                )
            )
        segments = [
            segment
            for project in shown
            if (
                segment := _segment(
                    project,
                    project,
                    week_days,
                    # PRJ-044: "Bühne Marktplatz (Stadtfest)" – a part with the name of its whole project.
                    label=short_name(project),
                    css=f"status-{project.status}",
                    title=project_title(project),
                )
            )
            is not None
        ]
        lanes = assign_lanes(segments)
        hidden = hide_beyond(segments, MONTH_LANES, 7)
        segments.sort(key=lambda segment: (segment.lane, segment.first))
        weeks.append(MonthWeek(days=cells, segments=segments, lanes=lanes, hidden=hidden))
    return weeks


# --- Week (VFG-021) -------------------------------------------------------------------------------


@dataclass
class TimedBlock:
    """A project or phase in the column of one day, placed by its hours (VFG-021)."""

    record: Any
    project: Project
    is_phase: bool
    #: Hours since midnight, as decimals: 8.5 is 08:30.
    begin: float
    end: float
    label: str
    times: str
    title: str
    url: str
    lane: int = 0
    lanes: int = 1
    #: VFG-039: a follow-up at its time (PRJ-109), with its note.
    is_follow_up: bool = False
    note: str = ""
    kind_label: str = ""

    @property
    def css(self) -> str:
        """Status colour, and the frame of a phase; a follow-up has a colour of its own."""
        if self.is_follow_up:
            return "follow-up"
        return f"status-{self.project.status}" + (" phase" if self.is_phase else "")

    @property
    def style(self) -> str:
        """Custom properties for CSS: start and length in hours, lane and lanes side by side."""
        length = max(self.end - self.begin, SHORTEST_BLOCK_HOURS)
        return f"--start: {self.begin:.3f}; --length: {length:.3f}; --lane: {self.lane}; --lanes: {self.lanes}"

    @property
    def status_label(self) -> str:
        """The status of the project, said in words; or what the entry is (a follow-up)."""
        return self.kind_label or str(self.project.get_status_display())


def arrange_side_by_side(blocks: list[TimedBlock]) -> None:
    """Give overlapping blocks of one day lanes next to each other (VFG-021).

    Blocks that overlap directly or through others form a group; within a
    group each block takes the first lane free at its start, and all blocks
    of the group share the width by the number of lanes the group needs.
    """
    blocks.sort(key=lambda block: (block.begin, -block.end))
    group: list[TimedBlock] = []
    lane_ends: list[float] = []
    group_end = -1.0

    def close() -> None:
        for member in group:
            member.lanes = len(lane_ends)

    for block in blocks:
        finish = max(block.end, block.begin + SHORTEST_BLOCK_HOURS)
        if group and block.begin >= group_end:
            close()
            group, lane_ends = [], []
        for lane, last in enumerate(lane_ends):
            if last <= block.begin:
                block.lane, lane_ends[lane] = lane, finish
                break
        else:
            block.lane = len(lane_ends)
            lane_ends.append(finish)
        group.append(block)
        group_end = max(group_end, finish) if len(group) > 1 else finish
    if group:
        close()


@dataclass
class WeekColumn:
    """One day of the week grid with its blocks."""

    day: datetime.date
    blocks: list[TimedBlock] = field(default_factory=list)
    #: Hours since midnight of the current moment, if the day is today.
    now: float | None = None
    #: All-day bars of this day beyond the lanes shown before "show all".
    hidden: int = 0

    @property
    def is_today(self) -> bool:
        """Whether it is today."""
        return self.now is not None

    @property
    def is_weekend(self) -> bool:
        """Saturday or Sunday."""
        return self.day.weekday() >= 5

    @property
    def now_style(self) -> str:
        """Custom property for the line of the current time."""
        return f"--at: {self.now:.3f}" if self.now is not None else ""

    @property
    def lanes(self) -> int:
        """The most blocks of this day standing side by side."""
        return max((block.lanes for block in self.blocks), default=1)


@dataclass
class WeekGrid:
    """The week as a time grid: the all-day strip and one column of blocks per day (VFG-021)."""

    columns: list[WeekColumn]
    all_day: list[Segment]
    all_day_lanes: int
    scroll_hour: int

    @property
    def hours(self) -> list[str]:
        """The labels of the hour lines: "00:00" to "23:00"."""
        return [f"{hour:02d}:00" for hour in range(24)]

    @property
    def columns_style(self) -> str:
        """``grid-template-columns``: the hours, then one track per day.

        A day with blocks side by side gets a wider minimum, so that each
        block keeps a readable width; the grid then scrolls sideways.
        """
        tracks = " ".join(
            f"minmax(max(var(--wk-col-min), {column.lanes * LANE_MIN_WIDTH}px), {min(2, column.lanes)}fr)"
            if column.lanes > 1
            else "minmax(var(--wk-col-min), 1fr)"
            for column in self.columns
        )
        return f"grid-template-columns: var(--wk-gutter) {tracks}"

    @property
    def all_day_style(self) -> str:
        """``grid-template-rows`` of the all-day strip: one row per lane, then the "+n" row."""
        return f"grid-template-rows: repeat({max(1, self.all_day_lanes)}, auto) auto"

    @property
    def collapsed_lanes(self) -> int:
        """Lanes shown before "show all"."""
        return WEEK_ALL_DAY_LANES

    @property
    def has_hidden(self) -> bool:
        """Whether some all-day bars wait behind "show all"."""
        return self.all_day_lanes > WEEK_ALL_DAY_LANES

    @property
    def more_row(self) -> int:
        """The grid row of the "+n" buttons, below every lane."""
        return max(1, self.all_day_lanes) + 1


def _blocks_of_day(
    record: Any, project: Project, day: datetime.date, *, is_phase: bool, label: str, title: str
) -> TimedBlock | None:
    """The piece of a period on one day, or ``None`` if it does not touch the day."""
    day_start, day_end = bounds([day])
    if record.start >= day_end or record.end <= day_start:
        return None
    midnight = datetime.datetime.combine(day, datetime.time.min)
    begin = max(0.0, (_local_naive(record.start) - midnight).total_seconds() / 3600)
    end = min(24.0, (_local_naive(record.end) - midnight).total_seconds() / 3600)
    if end <= begin:
        return None
    return TimedBlock(
        record=record,
        project=project,
        is_phase=is_phase,
        begin=begin,
        end=end,
        label=label,
        times=day_times(record.start, record.end, day_start, day_end),
        title=title,
        url=reverse("projects:overview", args=[project]),
    )


def week_grid(
    projects: QuerySet[Project],
    monday: datetime.date,
    *,
    phases: bool = True,
    follow_ups: QuerySet[Project] | None = None,
) -> WeekGrid:
    """The seven days of a week as a time grid with every project and phase (PRJ-067, VFG-021).

    Two queries: the projects of the week (with customer and venue) and the
    phases of the visible projects in the week. VFG-039:
    without ``phases`` no phases; with ``follow_ups`` the follow-ups of the
    week – at their time, or in the all-day strip without one.
    """
    days = day_range(monday, 7)
    span_start, span_end = bounds(days)
    shown = list(
        overlapping(projects, span_start, span_end)
        .select_related("customer", "venue_site", "parent")
        .order_by("start", "number")
    )
    # Phases of every listed project, also of one whose own period lies outside the week.
    shown_phases = (
        list(
            overlapping(ProjectPhase.objects.filter(project__in=projects), span_start, span_end)
            .select_related("project__parent", "venue_site")
            .order_by("start")
        )
        if phases
        else []
    )
    now = timezone.localtime()
    columns = []
    for day in days:
        column = WeekColumn(day=day)
        if day == now.date():
            column.now = (
                now.replace(tzinfo=None) - datetime.datetime.combine(day, datetime.time.min)
            ).total_seconds() / 3600
        columns.append(column)
    all_day: list[Segment] = []
    entries: list[tuple[Any, Project, bool, str, str, str]] = [
        (project, project, False, short_name(project), f"status-{project.status}", project_title(project))
        for project in shown
    ]
    entries += [
        (
            phase,
            phase.project,
            True,
            f"{phase.label} · {short_name(phase.project)}",
            f"status-{phase.project.status} phase",
            phase_title(phase),
        )
        for phase in shown_phases
    ]
    for record, project, is_phase, label, css, title in entries:
        if lasts_whole_days(record.start, record.end):
            segment = _segment(record, project, days, label=label, css=css, title=title)
            if segment is not None:
                all_day.append(segment)
            continue
        for column in columns:
            block = _blocks_of_day(record, project, column.day, is_phase=is_phase, label=label, title=title)
            if block is not None:
                column.blocks.append(block)
    _add_follow_ups(follow_ups_of(follow_ups, days), days, columns, all_day)
    lanes = assign_lanes(all_day)
    for column, count in zip(columns, hide_beyond(all_day, WEEK_ALL_DAY_LANES, 7), strict=True):
        column.hidden = count
    for segment in all_day:
        segment.shown = True  # all are in the page; CSS hides the extra lanes until "show all"
    all_day.sort(key=lambda segment: (segment.lane, segment.first))
    # Open at the working hours, or earlier if something begins earlier – not for pieces continued from the night before.
    earliest = min(
        (block.begin for column in columns for block in column.blocks if block.record.start >= bounds([column.day])[0]),
        default=DAY_STARTS_AT,
    )
    for column in columns:
        arrange_side_by_side(column.blocks)
    return WeekGrid(
        columns=columns,
        all_day=all_day,
        all_day_lanes=lanes,
        scroll_hour=min(DAY_STARTS_AT, math.floor(earliest)),
    )


# --- Follow-ups (VFG-039) ------------------------------------------------------------------


@dataclass
class FollowUpMark:
    """A follow-up (PRJ-105) of a project or service case as the calendar shows it: on its day, at its time (PRJ-109)."""

    project: Project

    @property
    def day(self) -> datetime.date:
        """The day of the follow-up."""
        return self.project.follow_up_on

    @property
    def time(self) -> datetime.time | None:
        """The time of the follow-up, if one was given (PRJ-109)."""
        return self.project.follow_up_at

    @property
    def start(self) -> datetime.datetime:
        """The moment of the follow-up; midnight for one without a time."""
        zone = timezone.get_current_timezone()
        return datetime.datetime.combine(self.day, self.time or datetime.time.min, tzinfo=zone)

    @property
    def end(self) -> datetime.datetime:
        """Half an hour later, at most until midnight; the end of the day for one without a time."""
        midnight = bounds([self.day])[1]
        if self.time is None:
            return midnight
        return min(self.start + datetime.timedelta(minutes=FOLLOW_UP_MINUTES), midnight)

    @property
    def time_text(self) -> str:
        """``14:30``, or nothing without a time."""
        return self.time.strftime("%H:%M") if self.time else ""

    @property
    def url(self) -> str:
        """The project or the service case."""
        if self.project.kind == ProjectKind.SERVICE_CASE:
            return reverse("projects:case_detail", args=[self.project.pk])
        return reverse("projects:overview", args=[self.project])

    @property
    def label(self) -> str:
        """Number and name of the project or case."""
        return f"{self.project.number} {short_name(self.project)}"

    @property
    def title(self) -> str:
        """What the title says: follow-up, project, for whom, note, day and time."""
        parts = [_("Follow-up: %(project)s") % {"project": self.label}]
        if self.project.follow_up_user_id:
            parts.append(_("for %(name)s") % {"name": self.project.follow_up_user})
        if self.project.follow_up_note:
            parts.append(self.project.follow_up_note)
        parts.append(date_format(self.day, local_pattern("d.m.Y")) + (f" {self.time_text}" if self.time else ""))
        return " · ".join(parts)


def follow_ups_of(projects: QuerySet[Project] | None, days: list[datetime.date]) -> list[FollowUpMark]:
    """The follow-ups on the shown days of the projects and cases given, by day and time (VFG-039)."""
    if projects is None:
        return []
    found = (
        projects.filter(follow_up_on__gte=days[0], follow_up_on__lte=days[-1])
        .select_related("follow_up_user", "parent")
        .order_by("follow_up_on", "follow_up_at", "number")
    )
    # Those without a time first, as the database may sort them either way.
    return sorted((FollowUpMark(project) for project in found), key=lambda mark: (mark.day, mark.time is not None))


def _add_follow_ups(
    marks: list[FollowUpMark], days: list[datetime.date], columns: list[WeekColumn], all_day: list[Segment]
) -> None:
    """Put the follow-ups into the week: at their time in the column of their day, else in the all-day strip."""
    label = _("Follow-up")
    for mark in marks:
        if mark.time is None:
            segment = _segment(mark, mark.project, days, label=mark.label, css="follow-up", title=mark.title)
            if segment is not None:
                segment.url = mark.url
                segment.start_note = label  # said in words, not by the colour only
                segment.kind_label = label
                all_day.append(segment)
            continue
        column = next((column for column in columns if column.day == mark.day), None)
        block = (
            _blocks_of_day(mark, mark.project, mark.day, is_phase=False, label=mark.label, title=mark.title)
            if column is not None
            else None
        )
        if column is None or block is None:
            continue
        block.url = mark.url
        block.times = f"{label} {mark.time_text}"
        block.is_follow_up = True
        block.note = mark.project.follow_up_note
        block.kind_label = label
        column.blocks.append(block)
