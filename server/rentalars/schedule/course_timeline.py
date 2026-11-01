# SPDX-License-Identifier: GPL-3.0-or-later
"""The timeline of one project on its tab "Zeitplanung" (PRJ-103).

Planung → Zeitstrahl shows every project in one row (PRJ-028). This timeline
shows one project, with a row for each of its parts:

* the rental period, in the colour of the project status;
* the event, if the project names one;
* every phase, in its own row (PRJ-006, PRJ-092);
* the crew by person: one row per person with the bars of their crew lines,
  coloured as in the personnel plan (``services.crew_bar_css``, VFG-027) –
  firm, option or inquiry by the project, paler with a dashed band while the
  person has not answered a request; a declined request is struck through;
* the open places, one row per job function.

The columns are those of the planning overviews (``services.Scale``): one to
ten days in hour columns or one to twelve weeks of days (VFG-022, VFG-024),
with every bar at its exact times and the same navigation (``_zoom.html``).
An address without ``from``, ``days`` and ``weeks`` opens on the rental
period of the project (:func:`default_span`); the choice is not remembered
for the session, as the project decides what is worth seeing.

Nothing is read from the database here: the page passes the phases and the
crew lines it loaded anyway (PRJ-080), so the timeline costs no query.

VFG-026: in hour columns, whoever may change the project drags the
rental period, the event and the phases to other times, or moves them with
the arrow keys; a click on such a bar opens the same dialog with its times
to change (``schedule.moves``, ``schedule.move_views``).

PRJ-121: the bars of the people – and of the open
places – are dragged the same way (``moves.CREW``, as in the personnel plan,
VFG-031), with the same dialog and the same right (edit access to the
project). A person who is the only person of their phase takes the phase
along – or, else, the open places of their job function with the same times
(``moves.followers_of``); the dialog says so and asks.

VFG-035: the crew is shown as in the personnel plan (VFG-027,
VFG-032): the colours of firm, option and inquiry with the dashed band of
"angefragt", the exact times in the hover, a deployment that takes part in
a conflict – an overlap with another deployment of the person, also in
another project, an absence, "nicht verfügbar" – filled red, with "!" and
the warnings before the name, and the same legend. Whoever may read the
personnel sees the availability of each person above their deployments,
hatched, and the absences. That costs three queries
(:func:`crew_picture`) – the other deployments, the absences and the
availability of the people in the shown span –, whatever their number.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from django.http import QueryDict
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rentalars.personnel.availability import period_text
from rentalars.projects.models import CrewLine, Project, ProjectPhase, ProjectStatus, RequestStatus
from rentalars.schedule import moves
from rentalars.schedule.services import (
    MAX_DAYS,
    MAX_WEEKS,
    Bar,
    Scale,
    bounds,
    crew_bar_css,
    exact_period,
    find_warnings,
    overlapping,
    scale_from_request,
    warning_labels,
)


@dataclass
class CourseRow:
    """One row of the timeline of a project: a label and the bars of one thing.

    ``kind`` names the group – ``period``, ``event``, ``phase``, ``person`` or
    ``open`` –, ``starts_group`` marks the first row of the phases and of the
    crew, which the page sets off by a line.
    """

    label: str
    kind: str
    sublabel: str = ""
    url: str = ""
    title: str = ""
    bars: list[Bar] = field(default_factory=list)
    starts_group: bool = False
    #: VFG-035: a person's availability and absences above the deployments – ``None`` where not shown.
    availability: list[Bar] | None = None
    #: VFG-035: the warnings of a person (``services.WARNING_ORDER``), as in the personnel plan.
    warnings: list[str] = field(default_factory=list)

    @property
    def conflict(self) -> bool:
        """Whether a deployment of the person takes part in a conflict (VFG-035)."""
        return bool(self.warnings)

    @property
    def warning_text(self) -> str:
        """The warnings as one sentence, for the badge "!" and its text alternative (VFG-035)."""
        labels = warning_labels()
        return "; ".join(labels[code] for code in self.warnings)


@dataclass
class CrewPicture:
    """What the personnel plan knows about the crew of a project in the shown span (VFG-035).

    ``involved``: the crew lines of the project that take part in a conflict;
    ``warnings``: per person the warnings of the personnel plan;
    ``availability``: per person the bars of availability and absences, or
    ``None`` if the reader may not see them.
    """

    involved: set[int] = field(default_factory=set)
    warnings: dict[int, list[str]] = field(default_factory=dict)
    availability: dict[int, list[Bar]] | None = None


def crew_picture(lines: list[CrewLine], scale: Scale, *, with_availability: bool) -> CrewPicture:
    """Conflicts, warnings and availability of the people of a project in the shown span (VFG-035).

    The checks are those of the personnel plan (``services.find_warnings``,
    VFG-023): two deployments of a person that overlap – in this project or
    another one that is not cancelled –, a deployment during an absence or
    in a period marked "not available". Three queries: the deployments, the
    absences and the availability of these people in the span.

    Args:
        lines: The crew lines of the project, loaded.
        scale: The columns shown.
        with_availability: Whether the reader may see the availability of
            the people (the right to read the personnel, as for the
            personnel plan); the conflicts are shown either way, as the
            warnings of the crew in the planning are (PRJ-022).
    """
    from rentalars.personnel.marks import effective_periods
    from rentalars.personnel.models import Absence, AvailabilitySource, AvailabilityState

    people = {line.person_id for line in lines if line.person_id is not None}
    shown = {line.pk for line in lines}
    picture = CrewPicture(availability={} if with_availability else None)
    if not people:
        return picture
    start, end = bounds(scale.days)
    deployments: dict[int, list[CrewLine]] = {}
    for line in (
        overlapping(CrewLine.objects.filter(person_id__in=people), start, end)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .only("pk", "person_id", "start", "end")
    ):
        deployments.setdefault(line.person_id, []).append(line)
    absences: dict[int, list[Any]] = {}
    for absence in overlapping(Absence.objects.filter(person_id__in=people), start, end).order_by("start"):
        absences.setdefault(absence.person_id, []).append(absence)
    marks = effective_periods(people, start, end)
    states = dict(AvailabilityState.choices)
    from_feed = _("from the linked calendar")
    for person_id in people:
        own_lines, own_absences, own_marks = (
            deployments.get(person_id, []),
            absences.get(person_id, []),
            marks.get(person_id, []),
        )
        unavailable = [mark for mark in own_marks if mark.state == AvailabilityState.UNAVAILABLE]
        warnings, involved = find_warnings(own_lines, own_absences, unavailable)
        if warnings:
            picture.warnings[person_id] = warnings
        picture.involved.update(line.pk for line in own_lines if id(line) in involved and line.pk in shown)
        if picture.availability is None:
            continue
        bars: list[Bar] = []
        for mark in own_marks:
            css = f"availability is-{mark.state}" + (" from-feed" if mark.source == AvailabilitySource.FEED else "")
            bars += _bars(
                scale.bar(
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
                )
            )
        for absence in own_absences:
            bars += _bars(
                scale.bar(
                    absence.start,
                    absence.end,
                    label=absence.get_kind_display(),
                    css="absence",
                    title=_joined(exact_period(absence.start, absence.end), absence.note),
                    conflict=id(absence) in involved,
                )
            )
        bars.sort(key=lambda bar: bar.first)
        picture.availability[person_id] = bars
    return picture


def project_days(project: Project) -> tuple[datetime.date, int]:
    """The first day of the rental period and its number of days, in local time."""
    first = timezone.localtime(project.start).date()
    # A period that ends at midnight does not occupy the following day.
    last = timezone.localtime(project.end - datetime.timedelta(seconds=1)).date()
    return first, max(1, (last - first).days + 1)


def default_span(project: Project) -> dict[str, str]:
    """The span the timeline opens with: the rental period (PRJ-103).

    Up to ten days in hour columns (VFG-024), a longer project in weeks of
    days from its first day, at most twelve.
    """
    first, count = project_days(project)
    if count <= MAX_DAYS:
        return {"from": first.isoformat(), "days": str(count)}
    return {"from": first.isoformat(), "weeks": str(min(MAX_WEEKS, math.ceil(count / 7)))}


def course_scale(request: Any, project: Project) -> tuple[Scale, dict[str, Any]]:
    """The columns of the timeline of a project, and the navigation of ``_zoom.html`` (PRJ-103).

    The address chooses the span as on the planning pages (``from``, ``days``
    or ``weeks``, see ``services.scale_from_request``); without any of them
    the rental period of the project is shown (:func:`default_span`). An
    address with ``from`` only – "earlier", "later", scrolling to the end of
    the hour columns – keeps the kind of columns the project opens with.
    "Days" in the week view offers as many days as the project has, at most
    ten.
    """
    asked: Any = request
    if "days" not in request.GET and "weeks" not in request.GET:
        query = QueryDict(mutable=True)
        query.update(request.GET)
        for name, value in default_span(project).items():
            query.setdefault(name, value)
        asked = SimpleNamespace(GET=query)
    _first, count = project_days(project)
    weeks = min(MAX_WEEKS, math.ceil(count / 7))
    scale, navigation = scale_from_request(asked, default_weeks=weeks)
    if not navigation["zoom"]:
        navigation["day_count"] = min(MAX_DAYS, count)
    return scale, navigation


def short_period(start: datetime.datetime, end: datetime.datetime) -> str:
    """The text on a bar: "09:00–14:00" within one day – the heading names the day –, else with the dates."""
    begin, finish = timezone.localtime(start), timezone.localtime(end)
    if finish.date() == begin.date():
        return f"{begin:%H:%M}–{finish:%H:%M}"
    midnight = datetime.time.min
    if begin.time() != midnight and finish.time() == midnight and finish.date() == begin.date() + datetime.timedelta(1):
        return f"{begin:%H:%M}–24:00"
    return period_text(start, end)


def _joined(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


def _crew_title(line: CrewLine) -> str:
    """The tooltip of a crew bar: who, job function, exact times (VFG-035), where the request stands.

    "conflict" is added by the bar itself (``Bar.conflict``), from the flag that also fills it red.
    """
    if line.person_id is None:
        state = pgettext("crew", "open")
    else:
        state = str(line.get_request_status_display()) if line.request_status else ""
    who = line.person.name if line.person_id is not None else ""
    return _joined(
        who,
        line.job_function.name,
        exact_period(line.start, line.end),
        state,
    )


def course_rows(
    project: Project,
    phases: list[ProjectPhase],
    lines: list[CrewLine],
    scale: Scale,
    *,
    link_people: bool = False,
    movable: bool = False,
    crew: CrewPicture | None = None,
) -> list[CourseRow]:
    """The rows of the timeline of a project (PRJ-103).

    Args:
        project: The project.
        phases: Its phases, loaded.
        lines: Its crew lines, loaded with job function and person.
        scale: The columns to show.
        link_people: Whether the names lead to the people (the reader may
            open the personnel).
        movable: Whether the reader may change the project: in hour columns
            the rental period, the event and the phases can then be dragged
            (VFG-026) – the crew lines as well (PRJ-121).
        crew: VFG-035: conflicts, warnings and availability of the people
            (:func:`crew_picture`); without it no conflict is marked.

    Returns:
        The rental period, the event (if any), one row per phase, one per
        person with crew lines and one per job function with open places.
        A row whose period lies outside the shown span stays, without a bar.
    """
    status = f"status-{project.status}"
    status_text = str(project.get_status_display())
    movable = movable and scale.is_hourly
    rows = [
        CourseRow(
            label=_("Rental period"),
            kind="period",
            title=status_text,
            bars=_bars(
                scale.bar(
                    project.start,
                    project.end,
                    label=short_period(project.start, project.end),
                    css=status,
                    title=_joined(_("Rental period"), period_text(project.start, project.end), status_text),
                    move=moves.movable(project, moves.PERIOD, project.start, project.end, scale) if movable else None,
                )
            ),
        )
    ]
    if project.event_start and project.event_end:
        rows.append(
            CourseRow(
                label=_("Event"),
                kind="event",
                bars=_bars(
                    scale.bar(
                        project.event_start,
                        project.event_end,
                        label=short_period(project.event_start, project.event_end),
                        css=f"{status} event-period",
                        title=_joined(_("Event"), period_text(project.event_start, project.event_end)),
                        move=moves.movable(project, moves.EVENT, project.event_start, project.event_end, scale)
                        if movable
                        else None,
                    )
                ),
            )
        )
    for index, phase in enumerate(sorted(phases, key=lambda phase: (phase.start, phase.pk))):
        details = _joined(str(phase.get_kind_display()) if phase.title else "", phase.place)
        rows.append(
            CourseRow(
                label=phase.label,
                kind="phase",
                sublabel=details,
                title=_joined(phase.label, details),
                starts_group=index == 0,
                bars=_bars(
                    scale.bar(
                        phase.start,
                        phase.end,
                        label=short_period(phase.start, phase.end),
                        css="phase",
                        title=_joined(phase.label, period_text(phase.start, phase.end), phase.place),
                        move=moves.movable(project, moves.PHASE, phase.start, phase.end, scale, phase=phase)
                        if movable
                        else None,
                    )
                ),
            )
        )
    people: dict[int, CourseRow] = {}
    open_places: dict[int, CourseRow] = {}
    for line in sorted(lines, key=lambda line: (line.start, line.position, line.pk)):
        if line.person_id is not None:
            row = people.get(line.person_id)
            if row is None:
                row = people[line.person_id] = CourseRow(
                    label=line.person.name,
                    kind="person",
                    url=reverse("personnel:person_detail", args=[line.person_id]) if link_people else "",
                )
            css = crew_bar_css(line)
            if line.request_status == RequestStatus.DECLINED:
                css += " declined"
            # VFG-035: filled red with "conflict" in the hover, as in the personnel plan – from the one flag.
            in_conflict = crew is not None and line.pk in crew.involved
        else:
            row = open_places.get(line.job_function_id)
            if row is None:
                row = open_places[line.job_function_id] = CourseRow(
                    label=line.job_function.name, kind="open", sublabel=pgettext("crew", "open")
                )
            css = "crew open-place"
            in_conflict = False
        row.bars += _bars(
            scale.bar(
                line.start,
                line.end,
                label=line.job_function.name,
                css=css,
                title=_crew_title(line),
                conflict=in_conflict,
                # PRJ-121: dragged as in the personnel plan; the phase may follow (``from=course``).
                move=moves.movable(project, moves.CREW, line.start, line.end, scale, crew_line=line, origin="course")
                if movable
                else None,
            )
        )
    if crew is not None:
        for person_id, row in people.items():
            row.warnings = crew.warnings.get(person_id, [])
            if crew.availability is not None:
                row.availability = crew.availability.get(person_id, [])
    crew_rows = [*people.values(), *open_places.values()]
    if crew_rows:
        crew_rows[0].starts_group = True
    return rows + crew_rows


def crew_legend(project: Project) -> list[tuple[str, str]]:
    """The samples of the crew bars below the timeline – those of the personnel plan, and two of the project.

    VFG-035: firm, option, inquiry, requested and conflict as in the
    legend of the personnel plan (VFG-027, VFG-032); declined and open
    places exist only here.
    """
    return [
        ("crew status-confirmed", _("firm")),
        ("crew status-option", _("option")),
        ("crew status-inquiry", pgettext("deployment", "inquiry")),
        ("crew status-confirmed requested", _("requested")),
        ("crew status-confirmed is-conflict", _("conflict")),
        (f"crew status-{project.status} declined", _("declined")),
        ("crew open-place", pgettext("crew", "open")),
    ]


def _bars(bar: Bar | None) -> list[Bar]:
    return [bar] if bar is not None else []
