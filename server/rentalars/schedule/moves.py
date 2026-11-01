# SPDX-License-Identifier: GPL-3.0-or-later
"""Moving appointments by dragging them in a timeline (VFG-026).

In the view "Tage" of Planung → Zeitstrahl and in the timeline of a project
on its tab "Zeitplanung" (PRJ-103), the rental period of a project, its event
and its phases can be dragged – by the bar to move it, by one of its ends to
change the start or the end, in steps of 15 minutes (:data:`STEP_MINUTES`);
with the keyboard, the arrow keys do the same. Dropping does not change
anything yet: a dialog shows the former and the new times and what follows,
and only "Verschieben" in it saves.

What can be moved, and by whom
    The rental period (:data:`PERIOD`), the event period (:data:`EVENT`) and a
    phase (:data:`PHASE`) – by whoever may edit the project (AUT-025), and
    only while the project may change: a closed project stays as it is
    (PRJ-009). :func:`movable_project_ids` finds these projects for a whole
    timeline at once.

What moving does – what the forms do with new times
    * A **phase**: ``projects.course.update_phase``. Its crew lines move
      along unless the box is unticked (PRJ-080, ``crew.move_with_phase``);
      a moved line that was asked for or accepted asks its person again
      (PER-034). A phase that then lies beyond the rental period offers to
      extend it (PRJ-100); only a ticked box extends it
      (``course.extend_rental_period``, with all checks of a new period).
    * The **rental period**: ``projects.services.update_project`` – material
      lines that had exactly the former period take the new one; the parts
      of a whole project move along when it moves as a whole, otherwise they
      must stay within it; a part stays within its whole project (PRJ-044,
      PRJ-045). Moved as a whole – as long as before on the wall clock, at
      other times – the event, every phase with its crew and the crew
      without phase move along by as much (of the parts that move along as
      well), unless the box is unticked: the job moves to another day. The
      vehicle bookings of the logistics move with them (LOG-001). The
      people of the project hear of the new rental period (UIX-005), as
      after the project form.
    * The **event period**: ``update_project``; nothing else follows.
    * A **deployment** (:data:`CREW`, VFG-031): a crew line
      dragged in the personnel plan, through ``projects.crew.update_crew_line``
      as the crew dialog does it – the planned hours follow the period if
      they were the suggested ones (PRJ-023), a line that was asked for or
      accepted asks its person again (PER-034), the warnings of the line at
      its new times are named (PRJ-022). Its phase keeps its times.
    * PRJ-121: the crew bars of the timeline on
      "Zeitplanung" are dragged as well, and there what belongs to nobody
      else follows the person (:func:`followers_of`, the box ``follow``):

      - **the phase**, when the person is the only person in it: it moves
        as if dragged itself (``course.update_phase`` with its crew – the
        open places – and its vehicles, LOG-001). A deployment with the
        period of the phase gives the phase its new period; one with a
        period of its own moves the phase by as much as its start (as
        ``crew.move_with_phase`` does the other way round) – a changed end
        alone leaves the phase as it is;
      - otherwise **the open places of its job function** that have the
        same times in the same phase (or, as the line, none) – when the
        person is the only person among them: they take the new times.

      Nothing follows an open place dragged, nor in the personnel plan,
      where the phase is not in view (``follow`` is ``None`` there).

The confirmation (:func:`preview_move`)
    What the dialog names is found by doing the move in a transaction that
    is rolled back: the same functions run as when saving, so the dialog
    cannot promise something else than what happens. Nothing leaves the
    database before a transaction is committed – notifications and mails
    are sent ``on_commit``, webhooks and the change log are rows of the same
    transaction –, so the trial sends nothing. The material missing
    (PRJ-012) is counted before and after when the rental period changes.

The API offers the same (``schedule.move_api``): ``POST
/projects/{id}/reschedule/preview`` and ``POST /projects/{id}/reschedule``.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.utils.translation import ngettext, pgettext

from rentalars.accounts.rights import Level, Module, Rights
from rentalars.core.i18n import local_pattern
from rentalars.projects.models import CrewLine, Project, ProjectPhase, ProjectStatus

#: The rental period of a project.
PERIOD = "period"
#: The event period of a project.
EVENT = "event"
#: A phase of a project.
PHASE = "phase"
#: VFG-031: a deployment (crew line) of a person, dragged in the personnel plan.
CREW = "crew"
#: What can be moved.
KINDS = (PERIOD, EVENT, PHASE, CREW)

#: VFG-026: dragged times snap to this many minutes, and an arrow key moves by as much.
STEP_MINUTES = 15

#: A moment on the wall clock as the pages and the dialog pass it on: ``2027-03-10T14:15``.
WALL_FORMAT = "%Y-%m-%dT%H:%M"


def wall_clock(moment: datetime.datetime) -> str:
    """A moment in local time as ``2027-03-10T14:15`` – what the date and time fields hold."""
    return timezone.localtime(moment).strftime(WALL_FORMAT)


def period_text(start: datetime.datetime | None, end: datetime.datetime | None) -> str:
    """A period as the dialog names it: "Fr 10.03. 14:00 – 20:00", over midnight with both dates."""
    if start is None or end is None:
        return ""
    begin, finish = timezone.localtime(start), timezone.localtime(end)
    text = f"{date_format(begin, local_pattern('D d.m.'))} {begin:%H:%M} – "
    if finish.date() == begin.date():
        return text + f"{finish:%H:%M}"
    return text + f"{date_format(finish, local_pattern('D d.m.'))} {finish:%H:%M}"


# --- Who may move what ------------------------------------------------------------------------


def movable_project_ids(rights: Rights, user: Any, projects: list[Project]) -> set[int]:
    """The projects among ``projects`` whose appointments this user may drag (VFG-026).

    Edit access to the project (AUT-025) and a project that may change (not
    closed, PRJ-009). One query at most, for a role limited to assigned
    projects; none otherwise – the timeline shows many projects (scenario 11).
    """
    from rentalars.projects.access import _membership_filter

    if not rights.can_write(Module.PROJECTS):
        return set()
    open_ids = {project.pk for project in projects if not project.is_locked}
    if not open_ids:
        return set()
    if rights.level_everywhere(Module.PROJECTS) >= Level.WRITE:
        return open_ids
    if not rights.is_limited_to_assigned_projects(Module.PROJECTS):
        return set()
    # A role for assigned projects edits where a membership says "edit" (AUT-018, PRJ-049).
    from rentalars.projects.models import ProjectAccessLevel

    return set(
        Project.objects.filter(pk__in=open_ids)
        .filter(_membership_filter(user, [ProjectAccessLevel.EDIT]))
        .values_list("pk", flat=True)
    )


@dataclass(frozen=True)
class Movable:
    """What a page needs to drag one bar of a timeline (VFG-026).

    ``key`` names the bar across page loads (``phase-12``), ``url`` is the
    dialog with the consequences, ``start`` and ``end`` are the present times
    on the wall clock. ``grips``: the ends that lie within the shown columns
    and can be dragged; an end beyond them cannot be reached.
    """

    key: str
    url: str
    name: str
    start: str
    end: str
    start_shown: bool = True
    end_shown: bool = True

    @property
    def attrs(self) -> str:
        """The data attributes of the bar, for ``app.js``."""
        return format_html(
            ' data-tl-move="{}" data-tl-key="{}" data-tl-name="{}" data-tl-start="{}" data-tl-end="{}"'
            ' aria-describedby="tl-move-hint" draggable="false"',
            self.url,
            self.key,
            self.name,
            self.start,
            self.end,
        )

    @property
    def grips(self) -> str:
        """The two ends of the bar to drag, where they are in view; hidden from assistive technology."""
        return format_html(
            "{}{}",
            format_html('<span class="tl-grip is-start" aria-hidden="true"></span>') if self.start_shown else "",
            format_html('<span class="tl-grip is-end" aria-hidden="true"></span>') if self.end_shown else "",
        )


def movable(
    project: Project,
    what: str,
    start: datetime.datetime,
    end: datetime.datetime,
    scale: Any,
    *,
    phase: ProjectPhase | None = None,
    crew_line: CrewLine | None = None,
    name: str = "",
    origin: str = "",
) -> Movable:
    """The :class:`Movable` of one bar of ``scale`` (``schedule.services.Scale``).

    ``origin``: the page the dialog is asked from – ``course`` for "Zeitplanung", where a deployment takes its phase
    along (PRJ-121;:func:`followers_of`).
    """
    query: dict[str, Any] = {"what": what}
    if phase is not None:
        query["phase"] = phase.pk
    if crew_line is not None:
        query["line"] = crew_line.pk
    if origin:
        query["from"] = origin
    first, last = scale.offset(start), scale.offset(end)
    return Movable(
        key=key_of(project, what, phase, crew_line),
        url=f"{reverse('schedule:move', args=[project])}?{urlencode(query)}",
        name=name or label_of(project, what, phase, crew_line),
        start=wall_clock(start),
        end=wall_clock(end),
        start_shown=first >= 0,
        end_shown=last <= scale.columns * scale.hours,
    )


def key_of(project: Project, what: str, phase: ProjectPhase | None = None, crew_line: CrewLine | None = None) -> str:
    """The key of a bar across page loads: ``period-7``, ``phase-12``, ``crew-40``."""
    if crew_line is not None:
        return f"{what}-{crew_line.pk}"
    return f"{what}-{phase.pk if phase is not None else project.pk}"


def label_of(project: Project, what: str, phase: ProjectPhase | None = None, crew_line: CrewLine | None = None) -> str:
    """What is moved, in words: "Aufbau", "Mietzeitraum 2026-0042", "Einsatz von Anna Beck als Licht"."""
    if what == CREW and crew_line is not None:
        if crew_line.person_id is None:
            return _("Open place as %(function)s") % {"function": crew_line.job_function.name}
        return _("Deployment of %(person)s as %(function)s") % {
            "person": crew_line.person.name,
            "function": crew_line.job_function.name,
        }
    if what == PHASE and phase is not None:
        return phase.label
    if what == EVENT:
        return _("Event %(number)s") % {"number": project.number}
    return _("Rental period %(number)s") % {"number": project.number}


# --- One move -------------------------------------------------------------------------------------


@dataclass
class MoveRequest:
    """One move: what, to which times, and the answers of the dialog (VFG-026).

    ``move_crew``: a phase takes its crew lines along (PRJ-080).
    ``with_schedule``: a rental period moved as a whole takes the event, the
    phases and the crew along. ``extend``: a phase beyond the rental period
    extends it (PRJ-100). The former times are noted when the request is made.
    """

    project: Project
    what: str
    start: datetime.datetime
    end: datetime.datetime
    phase: ProjectPhase | None = None
    #: VFG-031: the crew line, for :data:`CREW`.
    crew_line: CrewLine | None = None
    move_crew: bool = True
    with_schedule: bool = True
    extend: bool = False
    #: PRJ-121: a deployment takes its phase – or the open places of its job function – along
    #: (:func:`followers_of`); ``None``: not offered (the personnel plan, an API call that does not name it).
    follow: bool | None = None
    old_start: datetime.datetime | None = field(default=None, init=False)
    old_end: datetime.datetime | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.what == CREW and self.crew_line is not None:
            self.old_start, self.old_end = self.crew_line.start, self.crew_line.end
        elif self.what == PHASE and self.phase is not None:
            self.old_start, self.old_end = self.phase.start, self.phase.end
        elif self.what == EVENT:
            self.old_start, self.old_end = self.project.event_start, self.project.event_end
        else:
            self.old_start, self.old_end = self.project.start, self.project.end

    @property
    def key(self) -> str:
        """The key of the bar (see :class:`Movable`)."""
        return key_of(self.project, self.what, self.phase, self.crew_line)

    @property
    def name(self) -> str:
        """What is moved, in words."""
        return label_of(self.project, self.what, self.phase, self.crew_line)

    @property
    def changes_anything(self) -> bool:
        """Whether the new times differ from the former ones."""
        return (self.start, self.end) != (self.old_start, self.old_end)

    @property
    def is_shift(self) -> bool:
        """Moved as a whole: as long as before on the wall clock, at other times."""
        from rentalars.projects.services import wall_clock_shift

        if self.old_start is None or self.old_end is None or self.start == self.old_start:
            return False
        return wall_clock_shift(self.start, self.old_start) == wall_clock_shift(self.end, self.old_end)

    @property
    def offers_schedule(self) -> bool:
        """Whether the dialog asks to move the event, the phases and the crew along."""
        return self.what == PERIOD and self.is_shift


@dataclass
class PeriodChange:
    """A period that moved: the rental period, the event, a phase or a part (``kind``: :data:`KINDS` or ``part``)."""

    kind: str
    label: str
    old_start: datetime.datetime | None
    old_end: datetime.datetime | None
    new_start: datetime.datetime
    new_end: datetime.datetime

    @property
    def before(self) -> str:
        """The former period in words."""
        return period_text(self.old_start, self.old_end)

    @property
    def after(self) -> str:
        """The new period in words."""
        return period_text(self.new_start, self.new_end)


@dataclass
class CrewChange:
    """A crew line that moved along, with whether its person is asked again (PER-034) and its warnings (PRJ-022)."""

    line: CrewLine
    old_start: datetime.datetime
    old_end: datetime.datetime
    #: ``None``: not asked again; else whether the person was told (by a notification or a mail).
    asked_again: bool | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def who(self) -> str:
        """The person, or "open" for an open place."""
        return self.line.person.name if self.line.person_id else pgettext("crew", "open")

    @property
    def before(self) -> str:
        """The former period in words."""
        return period_text(self.old_start, self.old_end)

    @property
    def after(self) -> str:
        """The new period in words."""
        return period_text(self.line.start, self.line.end)


@dataclass
class MoveOutcome:
    """What a move did – or, in the trial of :func:`preview_move`, would do."""

    move: MoveRequest
    project: Project
    changes: list[PeriodChange] = field(default_factory=list)
    crew: list[CrewChange] = field(default_factory=list)
    #: Material lines that had the former rental period and took the new one.
    material_lines: int = 0
    #: PRJ-100: the rental period was extended to cover the phase.
    extended: bool = False
    #: PRJ-012: pieces missing before and after – only when the rental period changes.
    shortage_before: int | None = None
    shortage_after: int | None = None
    #: VFG-031: the planned hours of a moved deployment before and after (PRJ-023), if they changed.
    hours_before: Any = None
    hours_after: Any = None
    #: PRJ-121: what followed the deployment – its phase or the open places of its function.
    followers: Followers | None = None
    #: LOG-001: the vehicle bookings that moved along with a phase that followed a deployment.
    vehicle_lines: int = 0
    #: PRJ-121: the phase that followed a deployment, as it is now – the one a rental period may be extended for.
    followed_phase: ProjectPhase | None = None

    @property
    def warnings(self) -> list[str]:
        """PRJ-005 (event end; PRJ-127): the event ends after "material back by" – for a move of the rental period or the event.

        A warning only; the move is made. For the other kinds of move the periods are not what was changed.
        """
        from rentalars.projects.period_warnings import project_warnings

        return project_warnings(self.project) if self.move.what in (PERIOD, EVENT) else []

    @property
    def asked_again(self) -> list[CrewChange]:
        """The crew lines whose people are asked again for the new times (PER-034)."""
        return [change for change in self.crew if change.asked_again is not None]

    @property
    def with_warnings(self) -> list[CrewChange]:
        """The crew lines with a warning after the move (PRJ-022)."""
        return [change for change in self.crew if change.warnings]

    @property
    def shortage_grew(self) -> bool:
        """Whether more material is missing than before."""
        return self.shortage_after is not None and self.shortage_after > (self.shortage_before or 0)

    @property
    def changes_rental_period(self) -> bool:
        """Whether the rental period of the project changed – moved, or extended for a phase."""
        return any(change.kind == PERIOD for change in self.changes)


@dataclass
class Followers:
    """What follows a deployment dragged on the timeline of its project (PRJ-121).

    ``phase``: the phase, whose only person the deployment is; ``open_places``:
    else the open places of its job function with the same times there.
    """

    line: CrewLine
    phase: ProjectPhase | None = None
    open_places: list[CrewLine] = field(default_factory=list)

    @property
    def label(self) -> str:
        """The box of the dialog: "Phase „Aufbau“ mitverschieben"."""
        if self.phase is not None:
            return _("Move the phase “%(phase)s” along") % {"phase": self.phase.label}
        return _("Move the open places as %(function)s along") % {"function": self.line.job_function.name}

    @property
    def reason(self) -> str:
        """Why it follows: "Die Phase „Aufbau“ wird mitverschoben, weil Anna die einzige Person darin ist."."""
        person = self.line.person.name if self.line.person_id else ""
        if self.phase is not None:
            return _("The phase “%(phase)s” moves along because %(person)s is the only person in it.") % {
                "phase": self.phase.label,
                "person": person,
            }
        return ngettext(
            "The open place as %(function)s moves along because %(person)s is the only person of this job function "
            "there.",
            "The %(count)d open places as %(function)s move along because %(person)s is the only person of this job "
            "function there.",
            len(self.open_places),
        ) % {"count": len(self.open_places), "function": self.line.job_function.name, "person": person}


def followers_of(line: CrewLine) -> Followers | None:
    """What follows a deployment dragged on "Zeitplanung" – see the module description (PRJ-121).

    * The phase, when the line has a person and no other line of its phase
      has one (open places do not count: they belong to nobody yet).
    * Else the open places of its job function in the same phase – or, for a
      line without phase, among the lines without phase – with exactly the
      same times, when no other line among them has a person.

    ``None`` when nothing follows: an open place, a person sharing the phase
    and the job function with others. Two queries at most.
    """
    if line.person_id is None:
        return None
    if line.phase_id is not None and not (
        CrewLine.objects.filter(phase_id=line.phase_id, person__isnull=False).exclude(pk=line.pk).exists()
    ):
        return Followers(line=line, phase=line.phase)
    same = CrewLine.objects.filter(
        project_id=line.project_id,
        job_function_id=line.job_function_id,
        phase_id=line.phase_id,
        start=line.start,
        end=line.end,
    ).exclude(pk=line.pk)
    places = list(same.filter(person__isnull=True).select_related("job_function", "project", "phase"))
    if not places or any(other.person_id is not None for other in same):
        return None
    return Followers(line=line, open_places=sorted(places, key=lambda place: (place.position, place.pk)))


def check_move(move: MoveRequest) -> None:
    """The rules every move must keep before anything is tried (VFG-026).

    Raises:
        ValidationError: The project is closed (PRJ-009), the end is not
            after the start, the project has no event period to move, or the
            phase belongs to another project.
    """
    from rentalars.projects.services import ensure_editable

    ensure_editable(move.project)
    if move.what not in KINDS:
        raise ValidationError({"what": _("Unknown appointment.")})
    if move.what == PHASE and (move.phase is None or move.phase.project_id != move.project.pk):
        raise ValidationError({"phase": _("The phase does not belong to this project.")})
    if move.what == CREW and (move.crew_line is None or move.crew_line.project_id != move.project.pk):
        raise ValidationError({"line": _("The crew line does not belong to this project.")})
    if move.what == EVENT and move.old_start is None:
        raise ValidationError({"what": _("The project has no event period.")})
    if move.end <= move.start:
        raise ValidationError({"end": _("The end must be after the start.")})


def _crew_times(lines: Any) -> dict[int, tuple[datetime.datetime, datetime.datetime]]:
    return {line.pk: (line.start, line.end) for line in lines}


@transaction.atomic
def apply_move(move: MoveRequest, *, rights: Rights, user: Any = None) -> MoveOutcome:
    """Move a rental period, event period or phase to new times (VFG-026); see the module description.

    Works on fresh copies of the project and the phase: the objects of
    ``move`` keep their former values.

    PRJ-118: whoever is planned hears of the move once – the changes of all
    their lines in one message (``projects.crew_changes``); the message
    "new period" of a moved rental period (UIX-005) goes to the crew only
    if they got none of those – nor a new request for the new times (PER-034).

    Raises:
        ValidationError: :func:`check_move`, or a check of the new period
            (a part outside its whole project, the parts of a whole project
            outside its new period, an extension that is not possible).
    """
    from rentalars.projects.crew_changes import one_notice_per_person

    with one_notice_per_person() as notices:
        outcome = _apply_move(move, rights=rights)
        if outcome.changes_rental_period and user is not None:
            told = {notice.person.pk for notice in notices}
            # Asked again for the new times (PER-034): the request is their message.
            told |= {change.line.person_id for change in outcome.crew if change.asked_again}
            _tell_people(outcome.project, user, told=told)
    return outcome


def _apply_move(move: MoveRequest, *, rights: Rights) -> MoveOutcome:
    from rentalars.projects import course
    from rentalars.projects.crew import crew_warnings

    check_move(move)
    project = Project.objects.select_related("parent").get(pk=move.project.pk)
    outcome = MoveOutcome(move=move, project=project)
    before: dict[int, tuple[datetime.datetime, datetime.datetime]] = {}
    moved_lines: list[CrewLine] = []
    if move.what == PHASE:
        phase = ProjectPhase.objects.get(pk=move.phase.pk)  # type: ignore[union-attr]
        old = (phase.start, phase.end)
        before.update(_crew_times(phase.crew_lines.all()))
        change = course.update_phase(phase, move_crew=move.move_crew, start=move.start, end=move.end)
        outcome.changes.append(PeriodChange(PHASE, phase.label, *old, phase.start, phase.end))
        moved_lines += change.moved_crew_lines
        if move.extend:
            _extend_for(phase, project, outcome)
    elif move.what == EVENT:
        _update_project(project, outcome, {"event_start": move.start, "event_end": move.end})
    elif move.what == CREW:
        moved_lines += _move_crew_line(move, outcome, before, rights)
        if move.extend and outcome.followed_phase is not None:
            # PRJ-121: a phase that followed its only person beyond the rental period – as when it is dragged (PRJ-100).
            _extend_for(outcome.followed_phase, project, outcome)
    else:
        moved_lines += _move_rental_period(project, move, outcome, before, rights)
    if moved_lines:
        warnings = crew_warnings(moved_lines)
        for line in moved_lines:
            old_start, old_end = before.get(line.pk, (line.start, line.end))
            outcome.crew.append(
                CrewChange(
                    line=line,
                    old_start=old_start,
                    old_end=old_end,
                    asked_again=getattr(line, "asked_again", None),
                    warnings=warnings.get(line.pk, []),
                )
            )
    return outcome


def _extend_for(phase: ProjectPhase, project: Project, outcome: MoveOutcome) -> None:
    """PRJ-100: extend the rental period to cover the moved phase, noting what changed (``course.extend_rental_period``)."""
    from rentalars.projects import course

    old_period = (project.start, project.end)
    lines = project.material_lines.filter(start=project.start, end=project.end, is_text=False).count()  # PRJ-128
    if course.extend_rental_period(phase, project) is not None:
        outcome.extended = True
        outcome.material_lines = lines
        outcome.changes.append(PeriodChange(PERIOD, _("Rental period"), *old_period, project.start, project.end))


def followed_phase_times(
    line: CrewLine, phase: ProjectPhase, start: datetime.datetime, end: datetime.datetime
) -> tuple[datetime.datetime, datetime.datetime] | None:
    """PRJ-121: the new times of a phase that follows its only person moved to ``start`` – ``end``; ``None``: it stays.

    A deployment with the period of the phase gives it the new period; one with times of its own moves it by as much
    as its start – a changed end alone leaves the phase as it is (see the module description).
    """
    from rentalars.projects.services import moved, wall_clock_shift

    if (line.start, line.end) == (phase.start, phase.end):
        return start, end
    shift = wall_clock_shift(start, line.start)
    if not shift:
        return None
    return moved(phase.start, shift), moved(phase.end, shift)


def _move_crew_line(
    move: MoveRequest,
    outcome: MoveOutcome,
    before: dict[int, tuple[datetime.datetime, datetime.datetime]],
    rights: Rights,
) -> list[CrewLine]:
    """VFG-031: a deployment to new times, as the crew dialog changes it (``crew.update_crew_line``).

    PRJ-121: with ``follow`` its phase or the open places of its job function follow
    (:func:`followers_of`). Returns the deployment first, then what moved along.
    """
    from rentalars.projects.crew import update_crew_line

    related = ("job_function", "person", "project", "phase", "service_product")
    line = CrewLine.objects.select_related(*related).get(pk=move.crew_line.pk)  # type: ignore[union-attr]
    before[line.pk] = (line.start, line.end)
    hours = line.planned_hours
    followers = followers_of(line) if move.follow else None
    along: list[CrewLine] = []
    if followers is not None and followers.phase is not None:
        moved_with_phase = _phase_follows(line, followers.phase, move, outcome, before)
        if moved_with_phase is None:
            followers = None  # only the end of a deployment with times of its own changed: the phase stays
        else:
            along += moved_with_phase
            line = CrewLine.objects.select_related(*related).get(pk=line.pk)  # as the phase left it
    if (line.start, line.end) != (move.start, move.end):
        line = update_crew_line(line, rights=rights, start=move.start, end=move.end)
    outcome.changes.insert(0, PeriodChange(CREW, move.name, *before[line.pk], line.start, line.end))
    if line.planned_hours != hours:
        outcome.hours_before, outcome.hours_after = hours, line.planned_hours
    if followers is not None and followers.open_places:
        for place in followers.open_places:
            before[place.pk] = (place.start, place.end)
            along.append(update_crew_line(place, rights=rights, start=line.start, end=line.end))
    outcome.followers = followers
    return [line, *(other for other in along if other.pk != line.pk)]


def _phase_follows(
    line: CrewLine,
    phase: ProjectPhase,
    move: MoveRequest,
    outcome: MoveOutcome,
    before: dict[int, tuple[datetime.datetime, datetime.datetime]],
) -> list[CrewLine] | None:
    """PRJ-121: the phase of a deployment that is its only person follows it, with its crew and vehicles.

    Returns the crew lines that moved with the phase, or ``None`` if the phase stays (see the module description).
    """
    from rentalars.projects import course

    phase = ProjectPhase.objects.get(pk=phase.pk)
    old = (phase.start, phase.end)
    times = followed_phase_times(line, phase, move.start, move.end)
    if times is None:
        return None
    before.update(_crew_times(phase.crew_lines.all()))
    change = course.update_phase(phase, move_crew=True, start=times[0], end=times[1])
    outcome.changes.append(PeriodChange(PHASE, phase.label, *old, phase.start, phase.end))
    outcome.vehicle_lines = len(change.moved_vehicle_lines)
    outcome.followed_phase = phase
    return change.moved_crew_lines


def _update_project(project: Project, outcome: MoveOutcome, changes: dict[str, Any]) -> None:
    """Change the periods of the project through the service of the project form, noting what changed."""
    from rentalars.projects.services import update_project

    old = {name: getattr(project, name) for name in ("start", "end", "event_start", "event_end")}
    update_project(project, **changes)
    if (project.start, project.end) != (old["start"], old["end"]):
        outcome.changes.append(
            PeriodChange(PERIOD, _("Rental period"), old["start"], old["end"], project.start, project.end)
        )
    if (project.event_start, project.event_end) != (old["event_start"], old["event_end"]) and project.event_start:
        outcome.changes.append(
            PeriodChange(
                EVENT, _("Event"), old["event_start"], old["event_end"], project.event_start, project.event_end
            )
        )


def _move_rental_period(
    project: Project,
    move: MoveRequest,
    outcome: MoveOutcome,
    before: dict[int, tuple[datetime.datetime, datetime.datetime]],
    rights: Rights,
) -> list[CrewLine]:
    """The rental period to new times; moved as a whole, the schedule follows unless unticked."""
    from rentalars.projects.services import moved, wall_clock_shift

    old_start, old_end = project.start, project.end
    follow = move.with_schedule and move.is_shift
    shift = wall_clock_shift(move.start, old_start)
    changes: dict[str, Any] = {"start": move.start, "end": move.end}
    if follow and project.event_start and project.event_end:
        changes["event_start"] = moved(project.event_start, shift)
        changes["event_end"] = moved(project.event_end, shift)
    # (text lines; PRJ-128): a text line has no period worth counting.
    outcome.material_lines = project.material_lines.filter(start=old_start, end=old_end, is_text=False).count()
    parts = {part.pk: (part.start, part.end) for part in project.subprojects.all()} if not project.parent_id else {}
    _update_project(project, outcome, changes)
    lines: list[CrewLine] = []
    if follow:
        lines += _shift_schedule(project, shift, outcome, before, rights)
    for part in Project.objects.filter(pk__in=parts).order_by("number"):
        if (part.start, part.end) == parts[part.pk]:
            continue
        outcome.changes.append(PeriodChange("part", str(part), *parts[part.pk], part.start, part.end))
        if follow and not part.is_locked:
            lines += _shift_schedule(part, wall_clock_shift(part.start, parts[part.pk][0]), outcome, before, rights)
    return lines


def _shift_schedule(
    project: Project,
    shift: datetime.timedelta,
    outcome: MoveOutcome,
    before: dict[int, tuple[datetime.datetime, datetime.datetime]],
    rights: Rights,
) -> list[CrewLine]:
    """Move every phase with its crew, and the crew without phase, by ``shift`` on the wall clock."""
    from rentalars.projects import course
    from rentalars.projects.crew import update_crew_line
    from rentalars.projects.services import moved

    lines: list[CrewLine] = []
    before.update(_crew_times(project.crew_lines.all()))
    for phase in project.phases.order_by("start", "pk"):
        old = (phase.start, phase.end)
        change = course.update_phase(
            phase, move_crew=True, start=moved(phase.start, shift), end=moved(phase.end, shift)
        )
        label = phase.label if project.pk == outcome.project.pk else f"{project.number}: {phase.label}"
        outcome.changes.append(PeriodChange(PHASE, label, *old, phase.start, phase.end))
        lines += change.moved_crew_lines
    for line in project.crew_lines.filter(phase__isnull=True).select_related(
        "job_function", "person", "project", "service_product"
    ):
        start, end = moved(line.start, shift), moved(line.end, shift)
        if end <= start:
            end = start + (line.end - line.start)
        lines.append(update_crew_line(line, rights=rights, start=start, end=end))
    # LOG-019: vehicle bookings without phase and with a period of their own move the same way; those with
    # the project's period followed it already (``logistics.follow_project_period``).
    for vehicle_line in project.vehicle_lines.filter(phase__isnull=True).exclude(start=project.start, end=project.end):
        start, end = moved(vehicle_line.start, shift), moved(vehicle_line.end, shift)
        if end <= start:
            end = start + (vehicle_line.end - vehicle_line.start)
        vehicle_line.start, vehicle_line.end = start, end
        vehicle_line.save()
    return lines


def _tell_people(project: Project, user: Any, *, told: set[int]) -> None:
    """UIX-005: a new rental period concerns everybody planned in the project – as after the project form.

    ``told``: the people who were told of their moved lines already (PRJ-118).
    """
    from rentalars.notifications.services import project_changed

    project_changed(
        project,
        _("new period %(start)s – %(end)s")
        % {
            "start": timezone.localtime(project.start).strftime(local_pattern("%d.%m. %H:%M")),
            "end": timezone.localtime(project.end).strftime(local_pattern("%d.%m. %H:%M")),
        },
        actor=user,
        crew_too=True,
        crew_told=told,
    )


# --- The confirmation -------------------------------------------------------------------------------


@dataclass
class MovePreview:
    """What the dialog shows before anything is saved (VFG-026).

    ``outcome`` is the trial with every box ticked that can be: the crew
    moving along, the schedule following a rental period moved as a whole,
    and – if possible – the extension of the rental period, so that the
    dialog can say what each box would do. ``suggestion`` is the rental
    period that would cover the phase at its new times (PRJ-100);
    ``extension_error`` why it cannot be extended.
    """

    move: MoveRequest
    outcome: MoveOutcome | None = None
    errors: list[str] = field(default_factory=list)
    suggestion: Any = None
    extension_error: str = ""
    #: How many crew lines the phase has, for the box "move the crew along".
    phase_crew: int = 0

    @property
    def followers(self) -> Followers | None:
        """PRJ-121: what follows the deployment in the trial – its phase or the open places of its job function."""
        return self.outcome.followers if self.outcome is not None else None

    @property
    def offers_follow(self) -> bool:
        """PRJ-121: whether the dialog offers the box "follow" – on "Zeitplanung", and something would follow."""
        return self.move.follow is not None and self.followers is not None

    @property
    def can_extend(self) -> bool:
        """Whether the dialog offers to extend the rental period (PRJ-100)."""
        return self.suggestion is not None and self.suggestion.blocked_by is None and not self.extension_error

    @property
    def is_possible(self) -> bool:
        """Whether "Verschieben" may be pressed."""
        return not self.errors and self.move.changes_anything

    @property
    def schedule_changes(self) -> list[PeriodChange]:
        """What follows a rental period moved as a whole: the event, the phases, the parts."""
        if self.outcome is None or self.move.what != PERIOD:
            return []
        return [change for change in self.outcome.changes if change.kind != PERIOD]

    @property
    def new_text(self) -> str:
        """The new times in words."""
        return period_text(self.move.start, self.move.end)

    @property
    def parts(self) -> list[PeriodChange]:
        """PRJ-044: the parts of a whole project that move along with its rental period."""
        return [change for change in self.outcome.changes if change.kind == "part"] if self.outcome else []

    @property
    def material_note(self) -> tuple[str, str] | None:
        """PRJ-012: what the new rental period means for the material – level and text – if it changes."""
        outcome = self.outcome
        if outcome is None or outcome.shortage_after is None or not outcome.changes_rental_period:
            return None
        count = outcome.shortage_after
        if outcome.shortage_grew:
            return (
                "warning",
                ngettext(
                    "With the new rental period %(count)d piece is missing.",
                    "With the new rental period %(count)d pieces are missing.",
                    count,
                )
                % {"count": count},
            )
        if count == 0:
            return ("success", _("The material is enough for the new rental period."))
        return (
            "info",
            ngettext(
                "As now, %(count)d piece is missing.",
                "As now, %(count)d pieces are missing.",
                count,
            )
            % {"count": count},
        )


class _Trial(Exception):  # noqa: N818 – not an error: carries the outcome out of the rolled-back transaction
    def __init__(self, outcome: MoveOutcome) -> None:
        super().__init__("trial")
        self.outcome = outcome


def _shortage(project_ids: list[int]) -> int:
    """PRJ-012: the pieces missing in these projects, as the planning shows them."""
    from rentalars.availability.engine import AvailabilityEngine
    from rentalars.projects.planning import build_planning

    engine = AvailabilityEngine()
    return sum(
        build_planning(project, engine=engine).shortage_total
        for project in Project.objects.filter(pk__in=project_ids).exclude(status=ProjectStatus.CANCELLED)
    )


def _sees_shortage(rights: Rights) -> bool:
    """AUT-032 (availability as a special right): only who may see availability learns what is missing.

    Without the right the shortage is not even counted – that saves the planning of the projects twice.
    """
    from rentalars.accounts.rights import SpecialRight

    return rights.has(SpecialRight.AVAILABILITY)


def _shortage_scope(move: MoveRequest) -> list[int]:
    """The projects whose material a move can leave short: the project, and the parts a whole project takes along."""
    project = move.project
    if move.what == PERIOD and not project.parent_id:
        return [project.pk, *Project.objects.filter(parent_id=project.pk).values_list("pk", flat=True)]
    return [project.pk]


def _trial(move: MoveRequest, *, rights: Rights, user: Any, count_shortage: bool) -> MoveOutcome:
    """Do the move and undo it again; the outcome tells what it would do."""
    try:
        with transaction.atomic():
            outcome = apply_move(move, rights=rights, user=user)
            if count_shortage:
                outcome.shortage_after = _shortage(_shortage_scope(move))
            raise _Trial(outcome)
    except _Trial as trial:
        return trial.outcome


def _suggestion_for_follower(move: MoveRequest) -> Any:
    """PRJ-121: the rental period that would cover the phase following the deployment of ``move`` (PRJ-100), or ``None``.

    The rules of a dragged phase: nothing for a phase within the rental period, nor for "Planung und Besprechungen".
    """
    from rentalars.projects import course

    line = CrewLine.objects.select_related("phase", "person", "job_function").get(pk=move.crew_line.pk)  # type: ignore[union-attr]
    followers = followers_of(line)
    if followers is None or followers.phase is None:
        return None
    times = followed_phase_times(line, followers.phase, move.start, move.end)
    if times is None:
        return None
    probe = copy.copy(followers.phase)
    probe.start, probe.end = times
    return course.rental_period_suggestion(probe, move.project)


def preview_move(move: MoveRequest, *, rights: Rights, user: Any = None) -> MovePreview:
    """What a move would do, without changing anything (VFG-026); see "The confirmation" above."""
    from rentalars.projects import course

    preview = MovePreview(move=move)
    try:
        check_move(move)
    except ValidationError as error:
        preview.errors = list(error.messages)
        return preview
    if move.what == PHASE and move.phase is not None:
        preview.phase_crew = move.phase.crew_lines.count()
        probe = copy.copy(move.phase)
        probe.start, probe.end = move.start, move.end
        preview.suggestion = course.rental_period_suggestion(probe, move.project)
    elif move.what == CREW and move.follow is not None and move.crew_line is not None:
        # PRJ-121: a phase that would follow its only person beyond the rental period – the choice of PRJ-100.
        preview.suggestion = _suggestion_for_follower(move)
    if not move.changes_anything:
        return preview
    try_extension = preview.suggestion is not None and preview.suggestion.blocked_by is None
    trial = dataclasses.replace(
        move,
        move_crew=True,
        with_schedule=True,
        extend=try_extension,
        follow=True if move.follow is not None else None,  # PRJ-121: what the box "follow" would do, if offered
    )
    material = (move.what == PERIOD or try_extension) and _sees_shortage(rights)  # AUT-032
    before = _shortage(_shortage_scope(move)) if material else None
    try:
        preview.outcome = _trial(trial, rights=rights, user=user, count_shortage=material)
    except ValidationError as error:
        if not try_extension:
            preview.errors = list(error.messages)
            return preview
        # The phase can move, but the rental period cannot follow it: say why, and try without.
        preview.extension_error = " ".join(error.messages)
        try:
            preview.outcome = _trial(
                dataclasses.replace(trial, extend=False), rights=rights, user=user, count_shortage=False
            )
        except ValidationError as second:
            preview.errors = list(second.messages)
            return preview
    if preview.outcome is not None and material:
        preview.outcome.shortage_before = before
    return preview


def perform_move(move: MoveRequest, *, rights: Rights, user: Any = None) -> MoveOutcome:
    """Move for good, as "Verschieben" in the dialog and the API do it (VFG-026).

    Around :func:`apply_move`, the material missing is counted before and
    after when the rental period can change (PRJ-012), so that the answer can
    warn as the project form and PRJ-100 do – only for whom may see the
    availability of material (AUT-032); for the others both stay ``None``.

    Raises:
        ValidationError: As :func:`apply_move`.
    """
    material = (move.what == PERIOD or (move.what in (PHASE, CREW) and move.extend)) and _sees_shortage(rights)
    before = _shortage(_shortage_scope(move)) if material else None
    outcome = apply_move(move, rights=rights, user=user)
    if material and outcome.changes_rental_period:
        outcome.shortage_before = before
        outcome.shortage_after = _shortage(_shortage_scope(move))
    return outcome
