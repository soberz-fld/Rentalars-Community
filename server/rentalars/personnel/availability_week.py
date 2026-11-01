# SPDX-License-Identifier: GPL-3.0-or-later
"""The week of the availability calendar: seven day columns with hours (PER-030).

Next to the month (:func:`rentalars.personnel.marks.month_calendar`) the
availability calendar of a person shows a week, laid out like the week of
the planning calendar (VFG-021): one column per day, the hours from top to
bottom, a line for the current time.

In each column lie two layers:

* **the availability that counts** (PER-027, :func:`~rentalars.personnel.marks.effective_periods`)
  as bands over their hours – own entries green, yellow or red, the busy
  times of the linked calendars hatched red, joined into blocks;
* **the deployments** of the person (crew lines of projects that are not
  cancelled) as blocks over the right part of the column, side by side
  where they overlap. A deployment in a red period is framed in red.

The heads of the days carry the colour of the day as the month shows it and
are the buttons for choosing days, like the days of the month.

Positions are plain numbers – hours as decimals – that the template hands to
CSS through custom properties. Two queries, whatever is entered: the
entries and the crew lines of the week.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.personnel.marks import AvailabilityPeriod, CalendarDay, colour_day, day_start, effective_periods
from rentalars.personnel.models import AvailabilityState, Person

#: The hour the week opens at, unless something begins earlier (as in VFG-021).
DAY_STARTS_AT = 6

#: Shorter blocks are drawn as if they lasted this long, so that their text stays readable.
SHORTEST_HOURS = 0.75

#: The sign of each colour, as in the month: colour is never the only sign.
SIGNS: dict[str, str] = {
    AvailabilityState.AVAILABLE: "✓",
    AvailabilityState.LIMITED: "~",
    AvailabilityState.UNAVAILABLE: "✕",
}


def parse_week(text: str | None) -> datetime.date:
    """Read ``2027-03-10`` into the Monday of that week; anything else gives the Monday of this week."""
    day = None
    if text:
        try:
            day = datetime.date.fromisoformat(text)
        except ValueError:
            day = None
    if day is None or not 2000 <= day.year <= 2100:
        day = timezone.localdate()
    return day - datetime.timedelta(days=day.weekday())


def _hours(moment: datetime.datetime, midnight: datetime.datetime) -> float:
    """Hours on the wall clock since the midnight of a day: 8.5 is 08:30, also on the day the clocks change."""
    local = timezone.localtime(moment).replace(tzinfo=None)
    return (local - timezone.localtime(midnight).replace(tzinfo=None)).total_seconds() / 3600


def _times(
    start: datetime.datetime, end: datetime.datetime, begin: datetime.datetime, finish: datetime.datetime
) -> str:
    """What a period means for one day: "08:00–18:00", "from 08:00", "until 18:00" or "all day"."""
    if start <= begin and end >= finish:
        return _("all day")
    starts, ends = start >= begin, end <= finish
    first, last = timezone.localtime(start).strftime("%H:%M"), timezone.localtime(end).strftime("%H:%M")
    if starts and ends:
        return f"{first}–{last}"
    if starts:
        return _("from %(time)s") % {"time": first}
    if ends:
        return _("until %(time)s") % {"time": last}
    return _("all day")


@dataclass
class Band:
    """The piece of an availability period on one day (PER-030)."""

    period: AvailabilityPeriod
    begin: float
    end: float
    times: str

    @property
    def css(self) -> str:
        """The colour, and the hatching of a busy time of a linked calendar."""
        return f"{self.period.state}" + (" feed" if self.period.from_feed else "")

    @property
    def style(self) -> str:
        """Custom properties for CSS: start and length in hours."""
        return f"--start: {self.begin:.3f}; --length: {max(self.end - self.begin, SHORTEST_HOURS):.3f}"

    @property
    def sign(self) -> str:
        """✓, ~ or ✕."""
        return SIGNS.get(self.period.state, "")

    @property
    def text(self) -> str:
        """What the band says: the colour in words, the note or "busy in the linked calendar"."""
        parts = [self.period.get_state_display()]
        if self.period.from_feed:
            parts = [_("busy in the linked calendar")]
        if self.period.note:
            parts.append(self.period.note)
        return " · ".join(parts)


@dataclass
class Deployment:
    """The piece of a deployment (crew line) on one day (PER-030)."""

    line: Any
    begin: float
    end: float
    times: str
    label: str
    url: str
    #: The deployment lies (partly) in a period the person said "not available" for.
    clash: bool = False
    lane: int = 0
    lanes: int = 1

    @property
    def style(self) -> str:
        """Custom properties for CSS: start and length in hours, lane and lanes side by side."""
        length = max(self.end - self.begin, SHORTEST_HOURS)
        return f"--start: {self.begin:.3f}; --length: {length:.3f}; --lane: {self.lane}; --lanes: {self.lanes}"

    @property
    def status_css(self) -> str:
        """The colour of the project status, as in the planning calendar."""
        return f"status-{self.line.project.status}"


def _side_by_side(blocks: list[Deployment]) -> None:
    """Give overlapping deployments of one day lanes next to each other (like VFG-021)."""
    blocks.sort(key=lambda block: (block.begin, -block.end))
    group: list[Deployment] = []
    lane_ends: list[float] = []
    group_end = -1.0
    for block in blocks:
        finish = max(block.end, block.begin + SHORTEST_HOURS)
        if group and block.begin >= group_end:
            for member in group:
                member.lanes = len(lane_ends)
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
    for member in group:
        member.lanes = len(lane_ends)


@dataclass
class WeekDay:
    """One column of the week: the day as the month shows it, its bands and deployments."""

    day: CalendarDay
    bands: list[Band] = field(default_factory=list)
    deployments: list[Deployment] = field(default_factory=list)
    #: Hours since midnight of the current moment, if the day is today.
    now: float | None = None

    @property
    def is_weekend(self) -> bool:
        """Saturday or Sunday."""
        return self.day.day.weekday() >= 5

    @property
    def now_style(self) -> str:
        """Custom property for the line of the current time."""
        return f"--at: {self.now:.3f}" if self.now is not None else ""


@dataclass
class AvailabilityWeek:
    """A week of the availability calendar, Monday to Sunday, with hours (PER-030)."""

    monday: datetime.date
    days: list[WeekDay]
    #: The availability that counts in the week (PER-027), for the list under the calendar.
    periods: list[AvailabilityPeriod]
    scroll_hour: int

    @property
    def sunday(self) -> datetime.date:
        """The last day of the week."""
        return self.monday + datetime.timedelta(days=6)

    @property
    def previous(self) -> datetime.date:
        """The Monday of the week before."""
        return self.monday - datetime.timedelta(days=7)

    @property
    def next(self) -> datetime.date:
        """The Monday of the week after."""
        return self.monday + datetime.timedelta(days=7)

    @property
    def number(self) -> int:
        """The calendar week (ISO 8601)."""
        return self.monday.isocalendar().week

    @property
    def is_current(self) -> bool:
        """Whether the week is this week."""
        today = timezone.localdate()
        return self.monday <= today <= self.sunday

    @property
    def hours(self) -> list[str]:
        """The labels of the hour lines: "00:00" to "23:00"."""
        return [f"{hour:02d}:00" for hour in range(24)]


def _deployment_label(line: Any, *, own: bool, visible_ids: set[int] | None) -> tuple[str, str]:
    """Label and link of a deployment: the person sees their own (AUT-023), others what they may open (AUT-016)."""
    from rentalars.projects.family_labels import project_label

    project = line.project
    if own:
        return f"{line.job_function.name} · {project_label(project)}", reverse("projects:deployment", args=[project])
    if visible_ids is not None and project.pk in visible_ids:
        return f"{line.job_function.name} · {project_label(project)}", reverse("projects:overview", args=[project])
    return f"{line.job_function.name} · {_('planned')}", ""


def week_calendar(
    person: Person, monday: datetime.date, *, own: bool = True, visible_ids: set[int] | None = None
) -> AvailabilityWeek:
    """Build the week of the availability calendar of a person (PER-030).

    Args:
        person: The person.
        monday: Any day of the week; the week begins on its Monday.
        own: The person looks at their own week: deployments are named and
            lead to the deployment page.
        visible_ids: For others: the projects the reader may open; the
            others show as "planned" with the job function only (AUT-016).
    """
    from rentalars.projects.models import CrewLine, ProjectStatus

    monday = monday - datetime.timedelta(days=monday.weekday())
    begin = day_start(monday)
    finish = day_start(monday + datetime.timedelta(days=7))
    periods = effective_periods([person.pk], begin, finish).get(person.pk, [])
    lines = list(
        CrewLine.objects.filter(person=person, start__lt=finish, end__gt=begin)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .select_related("project__parent", "job_function")
        .order_by("start", "pk")
    )
    red = [period for period in periods if period.state == AvailabilityState.UNAVAILABLE]
    now = timezone.localtime()
    today = now.date()
    days: list[WeekDay] = []
    earliest = float(DAY_STARTS_AT)
    for offset in range(7):
        day = monday + datetime.timedelta(days=offset)
        day_begin, day_end = day_start(day), day_start(day + datetime.timedelta(days=1))
        entry = CalendarDay(day=day, in_month=True, is_today=day == today)
        colour_day(entry, periods)  # the head of the day says what the cell of the month says (PER-021)
        column = WeekDay(day=entry)
        if day == today:
            column.now = _hours(now, day_begin)
        length = _hours(day_end, day_begin)  # 23 or 25 hours on the days the clocks change
        for period in entry.periods:
            first = max(0.0, _hours(period.start, day_begin))
            last = min(length, _hours(period.end, day_begin))
            if last > first:
                column.bands.append(
                    Band(
                        period=period,
                        begin=first,
                        end=min(last, 24.0),
                        times=_times(period.start, period.end, day_begin, day_end),
                    )
                )
        for line in lines:
            if not (line.start < day_end and line.end > day_begin):
                continue
            entry.planned = True
            first = max(0.0, _hours(line.start, day_begin))
            last = min(length, _hours(line.end, day_begin))
            if last <= first:
                continue
            label, url = _deployment_label(line, own=own, visible_ids=visible_ids)
            column.deployments.append(
                Deployment(
                    line=line,
                    begin=first,
                    end=min(last, 24.0),
                    times=_times(line.start, line.end, day_begin, day_end),
                    label=label,
                    url=url,
                    clash=any(period.start < line.end and line.start < period.end for period in red),
                )
            )
            if line.start >= day_begin:
                earliest = min(earliest, first)
        _side_by_side(column.deployments)
        for band in column.bands:
            if band.begin > 0:  # whole days do not pull the view to midnight
                earliest = min(earliest, band.begin)
        days.append(column)
    return AvailabilityWeek(monday=monday, days=days, periods=periods, scroll_hour=max(0, math.floor(earliest)))
