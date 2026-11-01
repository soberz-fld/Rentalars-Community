# SPDX-License-Identifier: GPL-3.0-or-later
"""The schedule of a project – "Zeitplanung": phases and open items (PRJ-006, PRJ-059).

Phases
    "Loading Friday 10–12, setup Friday 14–20 in hall 3, event Saturday …"
    Each phase has its period and place; together they tell the crew what
    happens when and where. They do not reserve anything: the material is
    reserved for the period of the project.

Crew per phase (PRJ-080)
    A crew line can belong to a phase. The page lists per phase who works
    (:func:`crew_by_phase`), and moving a phase can move its crew along
    (:func:`update_phase` with ``move_crew``, see ``crew.move_with_phase``).
    Removing a phase keeps its crew lines with their periods; they are then
    listed under "without phase".

Phases beyond the rental period (PRJ-100)
    A phase that begins before or ends after the rental period – the setup
    on the evening before – does not change the rental period by itself.
    After saving such a phase the pages ask whether the rental period should
    be extended to cover it (:func:`rental_period_suggestion`), and only an
    explicit "yes" extends it (:func:`extend_rental_period`), with the usual
    checks of a changed rental period. Phases of the kind "Planning and
    meetings" never ask: a site visit weeks before must not block material.
    The API only tells (``outside_rental_period``, ``rental_period_suggestion``).

Open items
    What still has to be clarified for a confirmed order (PRJ-059). In the
    status "Confirmed – details open" they say *what* is open. The overview
    of open items lists every project with open items; once the last item
    of such a project is done, its page suggests switching to "Confirmed"
    (scenario 20).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.projects.models import CrewLine, OpenItem, PhaseKind, Project, ProjectPhase, ProjectStatus
from rentalars.projects.services import ensure_editable, update_project

#: Fields of a phase that can be set.
PHASE_FIELDS = ("kind", "title", "start", "end", "venue_site", "location", "notes")

#: PRJ-116: how long a new phase is at first when the guess would end on a later day than it begins.
GUESSED_PHASE_LENGTH = datetime.timedelta(hours=1)

#: PRJ-116 (phase length; PRJ-124): a new phase is at most this long at first; the user may make it longer.
DEFAULT_PHASE_LENGTH = datetime.timedelta(hours=8)


# --- Phases (PRJ-006) ---------------------------------------------------------------------


def first_guess(
    project: Project, start: datetime.datetime | None = None, end: datetime.datetime | None = None
) -> tuple[datetime.datetime, datetime.datetime]:
    """The period a new phase starts with (PRJ-116) – on the page "Zeitplanung" and in "Neue Phase …".

    Previously a new phase started with the whole rental period, or with the
    one typed in the crew or vehicle form, which is the rental period until it
    is changed. Over several days that was a trap: whoever changed only the
    times kept the end on the last day, and the moved start took the end along
    (UIX-025) – "Anfahrt Mo 08:15 – Di 09:00", "Aufbau Mo 09:00 – Di 10:00",
    vehicles booked twice and trailers charged for two days. Now:

    * a period typed in the form counts if it differs from the rental period;
    * otherwise the phase begins where the latest phase ends, while that lies
      within the rental period – phases usually follow one another (loading,
      travel, setup) – else at the start of the rental period;
    * (phase length; PRJ-124) a guess lasts at most eight hours
      (:data:`DEFAULT_PHASE_LENGTH`) and never reaches beyond the end of the
      rental period – a rental period shorter than that gives the phase its
      end. Only a default: a period typed in the form, or a longer phase set
      later, is not cut;
    * a period typed in the form that would end on a later day than it begins
      lasts one hour, so that changing the times gives a phase on that day; a
      phase over several days is set on purpose, with the day of its end.
    """
    typed = start is not None and end is not None and end > start and (start, end) != (project.start, project.end)
    if not typed:
        start, end = project.start, project.end
        latest = project.phases.order_by("-end").values_list("end", flat=True).first()
        if latest is not None and start <= latest < end:
            start = latest
        # Within eight hours a phase may well cross midnight (a night event): no cut to one hour then.
        return start, min(end, start + DEFAULT_PHASE_LENGTH)
    assert start is not None and end is not None
    if timezone.localtime(end).date() != timezone.localtime(start).date():
        end = start + GUESSED_PHASE_LENGTH
    return start, end


def add_phase(project: Project, **fields: Any) -> ProjectPhase:
    """Add a phase to a project."""
    ensure_editable(project)
    phase = ProjectPhase(project=project, **{name: value for name, value in fields.items() if name in PHASE_FIELDS})
    phase.full_clean()
    phase.save()
    return phase


@dataclass
class PhaseChange:
    """What changing a phase did: the phase, and the crew lines that moved along with it (PRJ-080)."""

    phase: ProjectPhase
    moved_crew_lines: list[CrewLine] = field(default_factory=list)
    #: LOG-001: the vehicle bookings of the phase that moved along with the crew.
    moved_vehicle_lines: list[Any] = field(default_factory=list)


@transaction.atomic
def update_phase(phase: ProjectPhase, *, move_crew: bool = False, **changes: Any) -> PhaseChange:
    """Change a phase; with ``move_crew`` its crew lines follow a new period (PRJ-006, PRJ-080).

    The browser form asks whether the crew of the phase moves along – ticked
    by default – whenever the phase has crew lines; the API takes
    ``move_crew`` (default true). How the lines move is described at
    ``crew.move_with_phase``. Without ``move_crew`` the lines keep their
    periods and their link to the phase.
    """
    from rentalars.projects import logistics
    from rentalars.projects.crew import move_with_phase

    ensure_editable(phase.project)
    # The stored period: a model form has already put the new values on the instance while checking them.
    old_start, old_end = ProjectPhase.objects.filter(pk=phase.pk).values_list("start", "end").get()
    for name, value in changes.items():
        if name in PHASE_FIELDS:
            setattr(phase, name, value)
    phase.full_clean()
    phase.save()
    change = PhaseChange(phase=phase)
    if move_crew and (phase.start, phase.end) != (old_start, old_end):
        change.moved_crew_lines = move_with_phase(phase, old_start, old_end)
        # LOG-001: the vehicles of the phase go along with its crew.
        change.moved_vehicle_lines = logistics.move_with_phase(phase, old_start, old_end)
    return change


def delete_phase(phase: ProjectPhase) -> None:
    """Remove a phase; its crew lines stay with their periods, only without the phase (PRJ-080)."""
    ensure_editable(phase.project)
    phase.delete()


# --- Phases beyond the rental period (PRJ-100) ----------------------------------------------------

#: PRJ-100: phases of these kinds never suggest extending the rental period – a site visit weeks before the
#: event must not block material for all that time.
KINDS_WITHOUT_EXTENSION = frozenset({PhaseKind.PLANNING})


def lies_outside_rental_period(phase: ProjectPhase, project: Project | None = None) -> bool:
    """Whether the phase begins before or ends after the rental period of its project (PRJ-100)."""
    project = project or phase.project
    return phase.start < project.start or phase.end > project.end


@dataclass(frozen=True)
class RentalPeriodSuggestion:
    """PRJ-100: the rental period that would cover a phase lying partly outside it.

    ``blocked_by`` names the whole project of a subproject whose rental period
    does not cover the suggestion: a subproject lies within its whole project
    (PRJ-045), so that period has to be extended first.
    """

    phase: ProjectPhase
    project: Project
    start: datetime.datetime
    end: datetime.datetime
    blocked_by: Project | None = None


def rental_period_suggestion(phase: ProjectPhase, project: Project | None = None) -> RentalPeriodSuggestion | None:
    """The rental period to suggest after saving a phase, or ``None`` if there is nothing to ask (PRJ-100).

    Nothing is asked for a phase within the rental period, nor for a phase of
    a kind that never extends it (:data:`KINDS_WITHOUT_EXTENSION`). The
    suggestion keeps the present rental period and widens it just as far as
    the phase needs: an earlier start, a later end, or both.
    """
    project = project or phase.project
    if phase.kind in KINDS_WITHOUT_EXTENSION or not lies_outside_rental_period(phase, project):
        return None
    start, end = min(project.start, phase.start), max(project.end, phase.end)
    blocked_by = None
    if project.parent_id is not None:
        parent = project.parent
        if start < parent.start or end > parent.end:
            blocked_by = parent
    return RentalPeriodSuggestion(phase=phase, project=project, start=start, end=end, blocked_by=blocked_by)


def extend_rental_period(phase: ProjectPhase, project: Project | None = None) -> RentalPeriodSuggestion | None:
    """Extend the rental period so that it covers the phase – once the user has agreed (PRJ-100).

    The change runs through ``services.update_project`` like any change of
    the period in the project form: a closed project refuses it (PRJ-009), a
    subproject stays within its whole project (PRJ-045), the parts of a whole
    project stay within it, material lines that had the former period take
    the new one, and the change log notes it.

    Returns:
        What was extended, or ``None`` if there is nothing to extend (the
        period covers the phase, or the phase is of a kind that never asks).

    Raises:
        ValidationError: One of these checks refuses the new period.
    """
    project = project or phase.project
    suggestion = rental_period_suggestion(phase, project)
    if suggestion is None:
        return None
    update_project(project, start=suggestion.start, end=suggestion.end)
    return suggestion


@dataclass
class PhaseCrew:
    """A phase with its crew lines – or, with ``phase=None``, the crew lines without phase (PRJ-080)."""

    phase: ProjectPhase | None
    lines: list[CrewLine] = field(default_factory=list)


def crew_by_phase(project: Project, phases: list[ProjectPhase]) -> tuple[list[PhaseCrew], PhaseCrew]:
    """The crew lines of a project by phase, for the page "Zeitplanung" (PRJ-080).

    Args:
        project: The project.
        phases: Its phases, already loaded, in their order.

    Returns:
        One entry per phase – also those without crew – and the entry of
        the lines without phase. One query, whatever the number of lines.
    """
    by_phase = {phase.pk: PhaseCrew(phase=phase) for phase in phases}
    without = PhaseCrew(phase=None)
    for line in project.crew_lines.select_related("job_function", "person").order_by("start", "position", "id"):
        by_phase.get(line.phase_id, without).lines.append(line)
    return [by_phase[phase.pk] for phase in phases], without


# --- Open items (PRJ-059) ------------------------------------------------------------------------


def add_open_items(project: Project, texts: list[str]) -> list[OpenItem]:
    """Note one or more open items; empty lines are skipped.

    Raises:
        ValidationError: Nothing was given.
    """
    ensure_editable(project)
    items = []
    for text in texts:
        text = text.strip()
        if not text:
            continue
        item = OpenItem(project=project, text=text[:250])
        item.full_clean()
        item.save()
        items.append(item)
    if not items:
        raise ValidationError(_("Enter what is still open."))
    return items


def set_open_item_done(item: OpenItem, *, done: bool, user: Any) -> OpenItem:
    """Mark an open item as done – or as open again."""
    ensure_editable(item.project)
    item.is_done = done
    item.done_at = timezone.now() if done else None
    item.done_by = user if done and getattr(user, "pk", None) else None
    item.save()
    return item


def update_open_item(item: OpenItem, text: str) -> OpenItem:
    """Change the text of an open item."""
    ensure_editable(item.project)
    item.text = text.strip()[:250]
    item.full_clean()
    item.save()
    return item


def delete_open_item(item: OpenItem) -> None:
    """Remove an open item that was noted by mistake."""
    ensure_editable(item.project)
    item.delete()


def suggests_confirmation(project: Project) -> bool:
    """Whether to suggest the status "Confirmed": all open items are done (PRJ-059, scenario 20)."""
    if project.status != ProjectStatus.CONFIRMED_OPEN:
        return False
    counts = project.open_items.aggregate(total=Count("pk"), open=Count("pk", filter=Q(is_done=False)))
    return bool(counts["total"]) and counts["open"] == 0


def projects_with_open_items(projects: QuerySet[Project]) -> QuerySet[Project]:
    """The projects that have open items – or are "Confirmed – details open" without noting any.

    Annotated with ``open_count`` and ``done_count``; sorted by start.
    """
    return (
        projects.annotate(
            open_count=Count("open_items", filter=Q(open_items__is_done=False)),
            done_count=Count("open_items", filter=Q(open_items__is_done=True)),
        )
        .filter(Q(open_count__gt=0) | Q(status=ProjectStatus.CONFIRMED_OPEN))
        .exclude(status__in=[ProjectStatus.CLOSED, ProjectStatus.CANCELLED])
        .select_related("customer", "manager", "parent")
        .order_by("start", "number")
    )
