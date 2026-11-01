# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic of time tracking: recording, stopwatch, approval, reports (chapter 5.9).

Browser views and API views both call these functions (API-002).

Who may do what
---------------
* **Record own times** – everybody with write access to the module "time
  tracking" whose user account is linked to a person (AUT-012).
* **Record for others, approve, reject** – with the special right "approve
  times and record them for others" (ZEI-011, ZEI-013), for the projects the
  user may see.
* **See** – one's own entries always (ZEI-016); those of others with the
  special right. Hourly rates and amounts additionally need the right "see
  hourly rates and personnel costs" – except one's own rate (PER-010).

Two rules hold for every entry, however it is made:

* **Nothing in the future** (ZEI-022): neither begin nor end may lie after
  the moment the entry is saved. Hours are written down after they were
  worked; a stopwatch begins now.
* **A project can come later** (ZEI-023): an entry without project is
  allowed, with one of the person's own job functions (for
  somebody without any, every active one – ZEI-007). It counts nowhere
  and cannot be approved until a project is assigned – by the person while
  the entry is open, or by whoever approves.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Module, Rights, SpecialRight
from rentalars.api import webhooks
from rentalars.core.audit import record_event
from rentalars.core.i18n import local_pattern
from rentalars.core.money import ZERO, format_decimal, money
from rentalars.personnel.models import JobFunction, Person
from rentalars.personnel.services import job_functions_of, rate_for
from rentalars.projects.access import person_of, visible_projects
from rentalars.projects.crew import matching_crew_line
from rentalars.projects.models import (
    FINISHED_STATUSES,
    CaseStatus,
    CrewLine,
    Project,
    ProjectKind,
    ProjectStatus,
)
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus, hours_between

#: Fields of an entry a caller may change through :func:`update_entry`.
EDITABLE_FIELDS = frozenset({"project", "job_function", "start", "end", "break_minutes", "note"})

#: How long after its end a project is still offered first for booking times:
#: the hours of Saturday night are usually written down on Monday.
RECENT_DAYS = 7


# --- Rights -----------------------------------------------------------------------------


def may_manage(rights: Rights) -> bool:
    """Whether a user may record for others, approve and reject (ZEI-011, ZEI-013)."""
    return rights.can_write(Module.TIME_TRACKING) and rights.has(SpecialRight.APPROVE_TIMES)


def may_record_for(rights: Rights, user: Any, person: Person) -> bool:
    """Whether a user may record times of a person: the own ones, or – with the special right – anybody's."""
    if not rights.can_write(Module.TIME_TRACKING):
        return False
    own = person_of(user)
    return (own is not None and own.pk == person.pk) or may_manage(rights)


def may_see_rate_of(rights: Rights, user: Any, person: Person) -> bool:
    """Whether a user may see the hourly rate on entries of a person (AUT-019, PER-010).

    With the right for personnel costs: every rate. Without it: one's own,
    unless the installation has switched that off.
    """
    if rights.has(SpecialRight.PERSONNEL_COSTS):
        return True
    own = person_of(user)
    if own is None or own.pk != person.pk:
        return False
    from rentalars.core.models import SystemSettings

    return SystemSettings.load().people_see_own_rates


def manageable_projects(rights: Rights, user: Any) -> QuerySet[Project]:
    """The projects whose times a user with the approval right may see and approve.

    All projects the user may see (AUT-016), and the internal ones, which
    belong to everybody (ZEI-010).
    """
    visible = visible_projects(rights, user).values("pk")
    return Project.objects.filter(Q(pk__in=visible) | Q(is_internal=True))


def sees_entries_without_project(rights: Rights) -> bool:
    """Whether an approver sees the entries of others that have no project yet (ZEI-023).

    Entries without project belong to no project whose access could be
    checked. They are shown to approvers whose right holds for all projects,
    not to a crew chief limited to assigned projects.
    """
    return rights.has(SpecialRight.APPROVE_TIMES) and not rights.is_limited_to_assigned_projects(Module.PROJECTS)


def visible_entries(rights: Rights, user: Any) -> QuerySet[TimeEntry]:
    """The time entries a user may see (NFA-010, ZEI-016).

    One's own entries always; with the approval right also those of others
    in the projects the user may see, and those without project if the
    right holds for all projects (:func:`sees_entries_without_project`).
    """
    entries = TimeEntry.objects.all()
    if not rights.can_read(Module.TIME_TRACKING):
        return entries.none()
    own = person_of(user)
    mine = Q(person=own) if own is not None else Q(pk__in=[])
    if rights.has(SpecialRight.APPROVE_TIMES):
        others = Q(project__in=manageable_projects(rights, user).values("pk"))
        if sees_entries_without_project(rights):
            others |= Q(project__isnull=True)
        return entries.filter(mine | others)
    return entries.filter(mine) if own is not None else entries.none()


# --- What can be booked (ZEI-006, ZEI-007) ---------------------------------------------------


@dataclass
class ProjectChoice:
    """A project offered in the time entry form, with the job function to prefill."""

    project: Project
    #: "now": planned in it at the moment; "planned": planned in it at
    #: another time; "internal": internal project; "other": visible anyway;
    #: "service_case": an open service case (ZEI-024).
    reason: str
    job_function: JobFunction | None = None
    crew_line: CrewLine | None = None
    #: ZEI-024: for a service case, whether the person takes part in it (PRJ-108).
    takes_part: bool = False


# --- Service cases (ZEI-024) -------------------------------------------------------------------------


#: ZEI-024: the statuses in which a service case takes times from everybody who records times – PRJ-112:
#: every status but "done", as the button "Record time" on the page of the case.
OPEN_CASE_STATUSES = (
    CaseStatus.OPEN.value,
    CaseStatus.IN_PROGRESS.value,
    CaseStatus.WAITING.value,
    CaseStatus.CLOSING.value,
    CaseStatus.BACKLOG.value,
)


def is_open_service_case(project: Project | None) -> bool:
    """ZEI-024: whether times can be recorded on a project as on an open service case – by everybody."""
    return project is not None and project.is_service_case and project.case_status in OPEN_CASE_STATUSES


def open_service_cases() -> QuerySet[Project]:
    """ZEI-024: the service cases that are open or in progress, newest first."""
    return Project.objects.filter(kind=ProjectKind.SERVICE_CASE, case_status__in=OPEN_CASE_STATUSES).order_by(
        "-created_at", "-id"
    )


def participations_of(person: Person) -> dict[int, JobFunction | None]:
    """ZEI-024: the service cases a person takes part in (PRJ-108), with the job function given there – one query.

    The participants live in the projects module, which time tracking builds
    on; the model is looked up by name, as ``projects.crew`` does the other
    way round for time entries.
    """
    model = apps.get_model("projects", "ServiceCaseParticipant")
    return {
        participation.project_id: participation.job_function
        for participation in model.objects.filter(person=person).select_related("job_function")
    }


def all_job_functions() -> list[JobFunction]:
    """ZEI-024: every active job function, by name – what can be booked on an open service case."""
    return list(JobFunction.objects.filter(is_active=True).order_by("name"))


def project_choices(
    person: Person,
    rights: Rights,
    user: Any,
    *,
    at: datetime.datetime | None = None,
    service_cases: bool = False,
) -> list[ProjectChoice]:
    """Return the projects a person can book on, the most likely first (ZEI-006).

    Order:

    1. projects in which the person is planned right now – a crew line whose
       period includes ``at``, or ended within the last days;
    2. other projects with a crew line of the person that are not finished;
    3. with ``service_cases`` (ZEI-024): the open service cases the person
       takes part in (PRJ-108);
    4. internal projects (warehouse, workshop, office – ZEI-010);
    5. further running projects the *user* may see, for those who book on
       projects without being planned in them (a project manager, say);
    6. with ``service_cases``: every other open service case – times are
       often worked on a case without anybody planning them.

    The first entry of the list is what the quick entry form preselects; its
    ``job_function`` is the one of the crew line (ZEI-006).
    """
    at = at or timezone.now()
    recent = at - datetime.timedelta(days=RECENT_DAYS)
    choices: dict[int, ProjectChoice] = {}

    lines = (
        CrewLine.objects.filter(person=person)
        .exclude(project__status=ProjectStatus.CANCELLED)
        # PRJ-048: a deployment in a part is booked on the part, which names its whole project.
        .select_related("project__parent", "job_function")
        .order_by("start")
    )
    current, others = [], []
    for line in lines:
        if line.start <= at and line.end >= recent:
            current.append(line)
        elif line.project.status not in FINISHED_STATUSES:
            others.append(line)
    # Among the current ones, the one that began last is the best guess.
    for line in sorted(current, key=lambda line: line.start, reverse=True):
        choices.setdefault(line.project_id, ProjectChoice(line.project, "now", line.job_function, line))
    for line in others:
        choices.setdefault(line.project_id, ProjectChoice(line.project, "planned", line.job_function, line))

    cases: list[Project] = []
    if service_cases:
        # ZEI-024: open service cases – those the person takes part in first.
        mine = participations_of(person)
        cases = list(open_service_cases().select_related("parent"))
        for case in cases:
            if case.pk in mine:
                # The job function the person was added with is the one to prefill.
                choices.setdefault(case.pk, ProjectChoice(case, "service_case", mine[case.pk], takes_part=True))

    internal = Project.objects.filter(is_internal=True).exclude(status__in=FINISHED_STATUSES).select_related("parent")
    for project in internal.order_by("name"):
        choices.setdefault(project.pk, ProjectChoice(project, "internal"))

    further = (
        visible_projects(rights, user)
        .exclude(status__in=FINISHED_STATUSES)
        .exclude(pk__in=list(choices))
        .filter(start__lte=at + datetime.timedelta(days=RECENT_DAYS), end__gte=recent)
        .select_related("parent")
        .order_by("-start")
    )
    if service_cases:
        further = further.exclude(kind=ProjectKind.SERVICE_CASE)
    for project in further[:30]:
        choices.setdefault(project.pk, ProjectChoice(project, "other"))
    for case in cases:
        choices.setdefault(case.pk, ProjectChoice(case, "service_case"))
    return list(choices.values())


def _by_name(function: JobFunction) -> str:
    return function.name.lower()


def job_functions_for(
    person: Person, project: Project | None, *, every: list[JobFunction] | None = None
) -> list[JobFunction]:
    """Return the job functions a person can book in a project (ZEI-007), never none.

    In this order, each part by name:

    1. those assigned to the person in the personnel data and those the
       person is planned in on the project (a crew line of the person);
    2. ZEI-007: the further job functions of the project's crew –
       crew lines of other people and open places, in the project and, for a
       whole project, in its parts (PRJ-048);
    3. ZEI-007: only where that leaves nothing – a person without job
       functions of their own on a project without crew – every active job
       function, as on a service case.

    Without project (ZEI-023) 1 is the person's own job functions, and 3
    applies as well. On an open service case every active job function
    (ZEI-024): nobody is planned there.

    ``every``: the active job functions, when the caller has read them
    already (the API answers for many projects at once).
    """
    if is_open_service_case(project):
        return sorted(every if every is not None else all_job_functions(), key=_by_name)
    own = {function.pk: function for function in job_functions_of(person)}
    crew: dict[int, JobFunction] = {}
    if project is not None:
        # One query: every job function of the project's crew, marked where the line is the person's own.
        lines = CrewLine.objects.filter(Q(project=project) | Q(project__parent=project), job_function=OuterRef("pk"))
        for function in JobFunction.objects.filter(Exists(lines)).annotate(mine=Exists(lines.filter(person=person))):
            (own if function.mine else crew).setdefault(function.pk, function)
    functions = sorted(own.values(), key=_by_name)
    functions += sorted((function for pk, function in crew.items() if pk not in own), key=_by_name)
    if not functions:
        functions = sorted(every if every is not None else all_job_functions(), key=_by_name)
    return functions


def crew_line_label(line: CrewLine) -> str:
    """ZEI-025: a crew line as a suggestion for a time: "Licht – Aufbau, Fr 16.10. 08:00–12:00".

    The job function, the phase where the line belongs to one (PRJ-080), and
    the line's period – so that it is clear which deployment is meant.
    """
    start, end = timezone.localtime(line.start), timezone.localtime(line.end)
    if start.date() == end.date():
        period = f"{date_format(start, local_pattern('D d.m.'))} {start:%H:%M}–{end:%H:%M}"
    else:
        period = f"{date_format(start, local_pattern('D d.m. H:i'))} – {end:{local_pattern('%d.%m. %H:%M')}}"
    name = line.job_function.name
    if line.phase_id:
        name = f"{name} – {line.phase.label}"
    return f"{name}, {period}"


def crew_lines_for(person: Person, project: Project | None) -> list[CrewLine]:
    """ZEI-025: the crew lines of a person in a project, in the order of their start – the suggestions."""
    if project is None:
        return []
    return list(
        project.crew_lines.filter(person=person).select_related("job_function", "phase").order_by("start", "id")
    )


def _may_book_on(person: Person, project: Project, rights: Rights, user: Any) -> bool:
    """Whether times of a person can be booked on a project at all."""
    if project.is_internal:
        return True
    if is_open_service_case(project):
        return True  # ZEI-024: everybody who records times may record them on an open service case
    if project.crew_lines.filter(person=person).exists():
        return True
    return visible_projects(rights, user).filter(pk=project.pk).exists()


# --- Recording (ZEI-004, ZEI-005, ZEI-008, ZEI-009) ---------------------------------------------


def _check_overlap(entry: TimeEntry) -> None:
    """ZEI-009: the entries of a person must not overlap.

    ZEI-025: the parts of one period share its times; they are one period
    here, which must not overlap other entries.

    A running stopwatch counts from its start without end: nothing can be
    recorded "after" it until it is stopped.

    Raises:
        ValidationError: Another entry of the person covers part of the time.
    """
    others = TimeEntry.objects.filter(person_id=entry.person_id).exclude(pk=entry.pk)
    if entry.period_key is not None:
        others = others.exclude(period_key=entry.period_key)  # ZEI-025: the period is checked once
    if entry.end is None:
        clash = others.filter(Q(end__isnull=True) | Q(end__gt=entry.start)).order_by("start").first()
    else:
        clash = (
            others.filter(start__lt=entry.end)
            .filter(Q(end__isnull=True) | Q(end__gt=entry.start))
            .order_by("start")
            .first()
        )
    if clash is None:
        return
    if clash.end is None:
        message = _("The stopwatch has been running since %(start)s. Stop it first.") % {
            "start": timezone.localtime(clash.start).strftime(local_pattern("%d.%m. %H:%M"))
        }
    else:
        message = _("This overlaps with the entry from %(start)s to %(end)s (%(project)s).") % {
            "start": timezone.localtime(clash.start).strftime(local_pattern("%d.%m. %H:%M")),
            "end": timezone.localtime(clash.end).strftime("%H:%M"),
            "project": clash.project_label,
        }
    raise ValidationError({"start": message})


def _fixed_rate(person: Person, job_function: JobFunction, start: datetime.datetime, line: CrewLine | None) -> Decimal:
    """Return the hourly rate to write into a new entry (ZEI-008).

    The rate of the person in the job function on the day of the entry. A
    person planned in a function outside the own ones (PER-006) has no such
    rate; then the rate fixed on the crew line applies. Since rates are
    optional (PER-029), a person may have the function without an own rate:
    then, too, the rate of the crew line, and else the guide value of the job
    function.
    """
    rate = rate_for(person, job_function, timezone.localtime(start).date())
    if rate.own_hourly is not None:
        return rate.own_hourly
    if line is not None and line.hourly_rate is not None:
        return line.hourly_rate
    return rate.hourly if rate.hourly is not None else ZERO


def check_not_in_future(start: datetime.datetime | None, end: datetime.datetime | None) -> None:
    """ZEI-022: hours are written down after they were worked, never before.

    Neither begin nor end may lie after the present moment. A running
    stopwatch has no end yet; its begin is checked like any other.

    Raises:
        ValidationError: Begin or end lies in the future.
    """
    now = timezone.now()
    shown = timezone.localtime(now).strftime(local_pattern("%d.%m. %H:%M"))
    errors: dict[str, str] = {}
    if start is not None and start > now:
        errors["start"] = _("The begin lies in the future (now it is %(now)s). Times are recorded once worked.") % {
            "now": shown
        }
    if end is not None and end > now:
        errors["end"] = _("The end lies in the future (now it is %(now)s). Times are recorded once worked.") % {
            "now": shown
        }
    if errors:
        raise ValidationError(errors)


def _check_booking(
    person: Person, project: Project | None, job_function: JobFunction, rights: Rights, user: Any
) -> None:
    """Check that a person may book this job function on this project – or without project (ZEI-023).

    Raises:
        PermissionDenied: The user may not record times for this person.
        ValidationError: Person, project or job function do not fit together.
    """
    if not may_record_for(rights, user, person):
        raise PermissionDenied
    if not person.is_active:
        raise ValidationError({"person": _("%(person)s is deactivated.") % {"person": person}})
    if project is None:
        # ZEI-007: the person's own job functions – or, for somebody without any, every active one.
        if job_function.pk not in {function.pk for function in job_functions_for(person, None)}:
            raise ValidationError(
                {
                    "job_function": _(
                        "Without project only the job functions of %(person)s can be booked. "
                        "Choose the project to book %(function)s."
                    )
                    % {"function": job_function, "person": person}
                }
            )
        return
    if project.is_locked or project.status == ProjectStatus.CANCELLED:
        raise ValidationError({"project": _("Times cannot be booked on a closed or cancelled project.")})
    if not _may_book_on(person, project, rights, user):
        raise ValidationError({"project": _("%(person)s is not scheduled for this project.") % {"person": person}})
    if job_function.pk not in {function.pk for function in job_functions_for(person, project)}:
        raise ValidationError(
            {
                "job_function": _(
                    "%(function)s is neither one of the job functions of %(person)s nor planned for them in this project."
                )
                % {"function": job_function, "person": person}
            }
        )


@transaction.atomic
def create_entry(
    *,
    person: Person,
    project: Project | None,
    job_function: JobFunction,
    start: datetime.datetime,
    end: datetime.datetime | None,
    rights: Rights,
    user: Any,
    break_minutes: int = 0,
    note: str = "",
    submit: bool = False,
    crew_line: CrewLine | None = None,
    parts: Sequence[Part] | None = None,
) -> TimeEntry:
    """Record hours a person worked (ZEI-002, ZEI-004, ZEI-008, ZEI-009).

    Check and save happen in one protected step: the person's row is locked,
    so that two entries sent at the same moment – a double tap on the phone –
    cannot both pass the overlap check.

    Args:
        person: Who worked.
        project: On which project; ``None`` if that is not known yet (ZEI-023).
        job_function: As what; must be one of :func:`job_functions_for`.
        start: Begin of the work.
        end: End of the work; ``None`` starts a stopwatch (see :func:`start_timer`).
        rights: The rights of the caller.
        user: The caller.
        break_minutes: Break to subtract.
        note: A remark.
        submit: Hand the entry in for approval right away (status
            "submitted" instead of "recorded").
        crew_line: ZEI-025: the crew line the time counts towards, chosen
            from the suggestions; default: the matching line (ZEI-021).
        parts: ZEI-025: two or more job functions with their hours divide
            the period (:func:`share_hours`); ``job_function`` and
            ``crew_line`` are then ignored. One part is the same as giving
            its job function and crew line.

    Returns:
        The entry – for a divided period its first part; ``period_parts`` of
        the returned object lists every part.

    Raises:
        PermissionDenied: The caller may not record times for this person.
        ValidationError: The entry overlaps another one, lies in the future
            (ZEI-022), or person, project and job function do not fit together.
    """
    if parts is not None and len(parts) > 1:
        entries = _create_period(
            person=person,
            project=project,
            start=start,
            end=end,
            break_minutes=break_minutes,
            note=note,
            parts=parts,
            submit=submit,
            rights=rights,
            user=user,
        )
        return entries[0]
    if parts:
        job_function, crew_line = parts[0].job_function, parts[0].crew_line
    _check_booking(person, project, job_function, rights, user)
    _check_line(crew_line, person, project, job_function)
    check_not_in_future(start, end)
    Person.objects.select_for_update().filter(pk=person.pk).first()
    line = crew_line or (matching_crew_line(project, person, job_function, start) if project is not None else None)
    entry = TimeEntry(
        person=person,
        project=project,
        job_function=job_function,
        crew_line=line,
        start=start,
        end=end,
        break_minutes=break_minutes,
        note=note.strip(),
        hourly_rate=_fixed_rate(person, job_function, start, line),
    )
    entry.full_clean()
    _check_overlap(entry)
    if submit and end is not None:
        entry.status = TimeEntryStatus.SUBMITTED
        entry.submitted_at = timezone.now()
    entry.save()
    entry.period_parts = [entry]
    return entry


# --- Several job functions in one period (ZEI-025) --------------------------------------------------------------


@dataclass(frozen=True)
class Part:
    """ZEI-025: one job function of a period with its hours; ``hours=None``: the rest of the period."""

    job_function: JobFunction
    hours: Decimal | None = None
    #: The crew line the hours count towards, chosen from the suggestions; ``None``: the matching one.
    crew_line: CrewLine | None = None


def _hours_text(value: Decimal) -> str:
    return format_decimal(value, max_places=2)


def share_hours(parts: Sequence[Part], worked: Decimal) -> list[Decimal]:
    """ZEI-025: the hours of each part of a period; they add up to the hours worked in it.

    One part may leave its hours open: it gets the rest. Example: from 08:00
    to 16:30 with 30 minutes of break are 8 hours; "Ton 3" and "Licht" (open)
    give 3 and 5 hours.

    Raises:
        ValidationError: More than one part without hours, a part without
            hours above 0, or hours that do not add up (``parts``).
    """
    open_parts = [index for index, part in enumerate(parts) if part.hours is None]
    if len(open_parts) > 1:
        raise ValidationError({"parts": _("Leave the hours open at one job function at most: it gets the rest.")})
    if any(part.hours is not None and part.hours <= ZERO for part in parts):
        raise ValidationError({"parts": _("Every job function of the period needs hours above 0.")})
    shares = [part.hours.quantize(Decimal("0.01")) if part.hours is not None else ZERO for part in parts]
    given = sum(shares, ZERO)
    if open_parts:
        rest = worked - given
        if rest <= ZERO:
            raise ValidationError(
                {
                    "parts": _(
                        "The hours of the other job functions (%(given)s) leave nothing for %(function)s: "
                        "%(worked)s hours were worked."
                    )
                    % {
                        "given": _hours_text(given),
                        "function": parts[open_parts[0]].job_function,
                        "worked": _hours_text(worked),
                    }
                }
            )
        shares[open_parts[0]] = rest
    elif given != worked:
        raise ValidationError(
            {
                "parts": _(
                    "The hours of the job functions add up to %(given)s, but %(worked)s hours were worked "
                    "(begin to end minus the break)."
                )
                % {"given": _hours_text(given), "worked": _hours_text(worked)}
            }
        )
    return shares


def rescale_parts(parts: Sequence[Part], worked: Decimal) -> list[Part]:
    """ZEI-025: the parts of a period whose times changed, their hours in the same proportion as before.

    To the hundredth of an hour; what rounding leaves goes to the largest
    part, so that the hours still add up. Example: 3 and 5 of 8 hours, now
    6 hours → 2.25 and 3.75.
    """
    total = sum((part.hours or ZERO for part in parts), ZERO)
    if total <= ZERO or worked <= ZERO:
        return list(parts)
    hundredth = Decimal("0.01")
    shares = [((part.hours or ZERO) * worked / total).quantize(hundredth, rounding=ROUND_HALF_UP) for part in parts]
    largest = max(range(len(shares)), key=lambda index: shares[index])
    shares[largest] += worked - sum(shares, ZERO)
    return [Part(part.job_function, share, part.crew_line) for part, share in zip(parts, shares, strict=True)]


def _check_line(line: CrewLine | None, person: Person, project: Project | None, job_function: JobFunction) -> None:
    """ZEI-025: a crew line chosen for a time must be the person's, in this project and job function."""
    if line is None:
        return
    if project is None or line.project_id != project.pk:
        raise ValidationError({"crew_line": _("The crew line belongs to a different project.")})
    if line.person_id != person.pk:
        raise ValidationError({"crew_line": _("The crew line is planned for another person.")})
    if line.job_function_id != job_function.pk:
        raise ValidationError({"crew_line": _("The crew line is for another job function.")})


def _check_parts(person: Person, project: Project | None, parts: Sequence[Part], rights: Rights, user: Any) -> None:
    """ZEI-025: every part may be booked, and no job function and crew line is named twice."""
    seen: set[tuple[int, int | None]] = set()
    for part in parts:
        _check_booking(person, project, part.job_function, rights, user)
        _check_line(part.crew_line, person, project, part.job_function)
        key = (part.job_function.pk, part.crew_line.pk if part.crew_line else None)
        if key in seen:
            raise ValidationError(
                {
                    "parts": _("%(function)s is named twice. Add its hours up in one line.")
                    % {"function": part.job_function}
                }
            )
        seen.add(key)


def period_of(entry: TimeEntry) -> list[TimeEntry]:
    """ZEI-025: all parts of the period of an entry, in the order they were recorded; ``[entry]`` if not divided.

    The caller's object stands in the list in place of its row.
    """
    if entry.period_key is None:
        return [entry]
    rows = (
        TimeEntry.objects.filter(period_key=entry.period_key)
        .select_related("person", "project", "job_function", "crew_line")
        .order_by("id")
    )
    return [entry if row.pk == entry.pk else row for row in rows]


def with_periods(entries: Iterable[TimeEntry]) -> list[TimeEntry]:
    """ZEI-025: the entries and the other parts of their periods – one query.

    Handing in, approving, rejecting and deleting act on a whole period: a
    part alone cannot be approved while its other hours are sent back.
    """
    listed = list(entries)
    keys = {entry.period_key for entry in listed if entry.period_key is not None}
    if not keys:
        return listed
    known = {entry.pk for entry in listed}
    more = (
        TimeEntry.objects.filter(period_key__in=keys)
        .exclude(pk__in=known)
        .select_related("person", "project", "job_function")
        .order_by("id")
    )
    return listed + list(more)


def _create_period(
    *,
    person: Person,
    project: Project | None,
    start: datetime.datetime,
    end: datetime.datetime | None,
    break_minutes: int,
    note: str,
    parts: Sequence[Part],
    submit: bool,
    rights: Rights,
    user: Any,
) -> list[TimeEntry]:
    """ZEI-025: record a period worked in several job functions – one entry per part, linked by a key."""
    if end is None:
        raise ValidationError({"parts": _("A running stopwatch cannot be divided. Stop it, then divide the time.")})
    _check_parts(person, project, parts, rights, user)
    check_not_in_future(start, end)
    Person.objects.select_for_update().filter(pk=person.pk).first()
    probe = TimeEntry(
        person=person,
        project=project,
        job_function=parts[0].job_function,
        start=start,
        end=end,
        break_minutes=break_minutes,
    )
    probe.full_clean()
    shares = share_hours(parts, hours_between(start, end, break_minutes))
    key = uuid.uuid4()
    entries = []
    for part, share in zip(parts, shares, strict=True):
        line = part.crew_line or (
            matching_crew_line(project, person, part.job_function, start) if project is not None else None
        )
        entry = TimeEntry(
            person=person,
            project=project,
            job_function=part.job_function,
            crew_line=line,
            start=start,
            end=end,
            break_minutes=break_minutes,
            note=note.strip(),
            hourly_rate=_fixed_rate(person, part.job_function, start, line),
            period_key=key,
            hours=share,
        )
        entry.full_clean()
        entries.append(entry)
    _check_overlap(entries[0])
    submitted_at = timezone.now() if submit else None
    for entry in entries:
        if submitted_at is not None:
            entry.status, entry.submitted_at = TimeEntryStatus.SUBMITTED, submitted_at
        entry.save()
        entry.period_parts = entries
    return entries


@transaction.atomic
def save_period(
    entry: TimeEntry, *, parts: Sequence[Part], rights: Rights, user: Any, **changes: Any
) -> list[TimeEntry]:
    """ZEI-025: change an entry together with the division of its period into job functions.

    ``parts`` replace the job functions of the period: one part makes it an
    entry that is not divided, two or more divide it (:func:`share_hours`).
    ``changes`` – project, start, end, break, note – hold for every part.
    The rows of the period are reused in their order, missing ones created
    and extra ones deleted; the change log shows each step (ZEI-014).

    As for :func:`update_entry`: an approved period is locked; a rejected one
    is "recorded" again; the rate of a part is read again when its project,
    job function or crew line changes, not when only the times do (ZEI-008).

    Returns:
        The parts, in their order (one entry if the period is not divided).

    Raises:
        PermissionDenied: The caller may not record times for this person.
        ValidationError: As for :func:`update_entry`, and for parts that do
            not add up.
    """
    if not may_record_for(rights, user, entry.person):
        raise PermissionDenied
    unknown = set(changes) - (EDITABLE_FIELDS - {"job_function"})
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    if not parts:
        raise ValidationError({"parts": _("Choose the job function.")})
    person = entry.person
    Person.objects.select_for_update().filter(pk=person.pk).first()
    rows = period_of(entry)
    if any(not row.is_editable for row in rows):
        raise ValidationError(_("Approved times are locked. Somebody who approves times can take the approval back."))
    first = rows[0]
    project = changes.get("project", first.project)
    start, end = changes.get("start", first.start), changes.get("end", first.end)
    break_minutes = changes.get("break_minutes", first.break_minutes) or 0
    note = (changes.get("note", first.note) or "").strip()
    divided = len(parts) > 1
    if divided and end is None:
        raise ValidationError({"parts": _("A running stopwatch cannot be divided. Stop it, then divide the time.")})
    _check_parts(person, project, parts, rights, user)
    if (start, end) != (first.start, first.end):
        check_not_in_future(start, end)
    probe = TimeEntry(
        person=person,
        project=project,
        job_function=parts[0].job_function,
        start=start,
        end=end,
        break_minutes=break_minutes,
    )
    probe.full_clean()
    shares: list[Decimal | None] = (
        list(share_hours(parts, hours_between(start, end, break_minutes))) if divided else [None]
    )
    key = (first.period_key or uuid.uuid4()) if divided else None
    reopened = first.status == TimeEntryStatus.REJECTED
    kept: list[TimeEntry] = []
    for index, (part, share) in enumerate(zip(parts, shares, strict=True)):
        if index < len(rows):
            row = rows[index]
        else:
            row = TimeEntry(
                person=person,
                status=first.status,
                submitted_at=first.submitted_at,
                rejection_reason=first.rejection_reason,
            )
        new_project_id = project.pk if project is not None else None
        assignment_changed = (
            row.pk is None
            or row.project_id != new_project_id
            or row.job_function_id != part.job_function.pk
            or (part.crew_line is not None and part.crew_line.pk != row.crew_line_id)
        )
        row.project, row.job_function = project, part.job_function
        row.start, row.end, row.break_minutes, row.note = start, end, break_minutes, note
        if assignment_changed:
            row.crew_line = part.crew_line or (
                matching_crew_line(project, person, part.job_function, start) if project is not None else None
            )
            row.hourly_rate = _fixed_rate(person, part.job_function, start, row.crew_line)
        row.period_key = key
        row.hours = share if share is not None else ZERO
        if reopened:
            row.status, row.decided_at, row.decided_by = TimeEntryStatus.RECORDED, None, None
        row.full_clean()
        kept.append(row)
    for row in rows[len(parts) :]:
        row.delete()
    _check_overlap(kept[0])
    for row in kept:
        row.save()
        row.period_parts = kept
    return kept


@transaction.atomic
def update_entry(
    entry: TimeEntry, *, rights: Rights, user: Any, crew_line: CrewLine | None = None, **changes: Any
) -> TimeEntry:
    """Change a time entry that is not approved yet (ZEI-012, ZEI-014).

    Changing a rejected entry puts it back to "recorded": it has to be
    handed in again. Changing project or job function re-reads the hourly
    rate, because it depends on them (ZEI-008); changing only the times does
    not.

    ZEI-025: for a part of a divided period, project, times, break and note
    change for the whole period, the job function for this part only; new
    times keep the proportion of the parts (:func:`rescale_parts`).
    ``crew_line`` names the deployment the entry counts towards (its job
    function with it); without it the matching line is taken.

    Raises:
        PermissionDenied: The caller may not record times for this person.
        ValidationError: The entry is approved (locked), a field cannot be
            changed, or the new values overlap another entry.
    """
    if not may_record_for(rights, user, entry.person):
        raise PermissionDenied
    if not entry.is_editable:
        raise ValidationError(_("Approved times are locked. Somebody who approves times can take the approval back."))
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})

    if crew_line is not None:
        changes.setdefault("job_function", crew_line.job_function)
    if entry.period_key is not None:
        parts = []
        for row in period_of(entry):
            if row.pk != entry.pk:
                parts.append(Part(row.job_function, row.hours, row.crew_line))
                continue
            function = changes.get("job_function", row.job_function)
            line = crew_line or (row.crew_line if function.pk == row.job_function_id else None)
            parts.append(Part(function, row.hours, line))
        common = {name: value for name, value in changes.items() if name != "job_function"}
        end = common.get("end", entry.end)
        if end is not None:
            worked = hours_between(
                common.get("start", entry.start), end, common.get("break_minutes", entry.break_minutes) or 0
            )
            if worked != entry.period_hours:
                parts = rescale_parts(parts, worked)
        kept = save_period(entry, parts=parts, rights=rights, user=user, **common)
        return next((row for row in kept if row.pk == entry.pk), kept[0])

    def changed(name: str) -> bool:
        value = changes.get(name, getattr(entry, name))
        return (value.pk if value is not None else None) != getattr(entry, f"{name}_id")

    assignment_changed = any(name in changes and changed(name) for name in ("project", "job_function"))
    assignment_changed = assignment_changed or (crew_line is not None and crew_line.pk != entry.crew_line_id)
    for name, value in changes.items():
        setattr(entry, name, value)
    if "note" in changes:
        entry.note = (entry.note or "").strip()
    if assignment_changed:
        _check_booking(entry.person, entry.project, entry.job_function, rights, user)
        _check_line(crew_line, entry.person, entry.project, entry.job_function)
        entry.crew_line = crew_line or (
            matching_crew_line(entry.project, entry.person, entry.job_function, entry.start)
            if entry.project is not None
            else None
        )
        entry.hourly_rate = _fixed_rate(entry.person, entry.job_function, entry.start, entry.crew_line)
    if "start" in changes or "end" in changes:
        check_not_in_future(entry.start, entry.end)
    Person.objects.select_for_update().filter(pk=entry.person_id).first()
    entry.full_clean()
    _check_overlap(entry)
    if entry.status == TimeEntryStatus.REJECTED:
        entry.status = TimeEntryStatus.RECORDED
        entry.decided_at = None
        entry.decided_by = None
    entry.save()
    return entry


@transaction.atomic
def delete_entry(entry: TimeEntry, *, rights: Rights, user: Any) -> None:
    """Delete a time entry that is not approved yet; the change log keeps what it said (ZEI-014).

    ZEI-025: a part of a divided period is deleted with the whole period.

    Raises:
        PermissionDenied: The caller may not record times for this person.
        ValidationError: The entry is approved.
    """
    if not may_record_for(rights, user, entry.person):
        raise PermissionDenied
    rows = period_of(entry)
    if any(not row.is_editable for row in rows):
        raise ValidationError(_("Approved times are locked and cannot be deleted."))
    for row in rows:
        row.delete()


# --- Stopwatch (ZEI-005) -----------------------------------------------------------------------


def running_timer(person: Person | None) -> TimeEntry | None:
    """Return the entry whose stopwatch is running for a person, if any."""
    if person is None:
        return None
    return TimeEntry.objects.filter(person=person, end__isnull=True).select_related("project", "job_function").first()


def start_timer(
    *,
    person: Person,
    project: Project | None,
    job_function: JobFunction,
    rights: Rights,
    user: Any,
    note: str = "",
    crew_line: CrewLine | None = None,
) -> TimeEntry:
    """Start the stopwatch: an entry that begins now and has no end yet (ZEI-005).

    ``crew_line`` (ZEI-025): the deployment chosen from the suggestions. A
    running stopwatch is one entry; it can be divided into job functions
    once it is stopped.

    Raises:
        ValidationError: A stopwatch is already running for the person.
    """
    now = timezone.now().replace(second=0, microsecond=0)
    return create_entry(
        person=person,
        project=project,
        job_function=job_function,
        start=now,
        end=None,
        rights=rights,
        user=user,
        note=note,
        crew_line=crew_line,
    )


@transaction.atomic
def stop_timer(*, person: Person, rights: Rights, user: Any, break_minutes: int = 0, submit: bool = False) -> TimeEntry:
    """Stop the stopwatch of a person; the entry ends now (ZEI-005).

    An entry shorter than a minute would have no length; it gets one minute.

    Raises:
        PermissionDenied: The caller may not record times for this person.
        ValidationError: No stopwatch is running.
    """
    if not may_record_for(rights, user, person):
        raise PermissionDenied
    entry = running_timer(person)
    if entry is None:
        raise ValidationError(_("No stopwatch is running."))
    now = timezone.now().replace(second=0, microsecond=0)
    entry.end = max(now, entry.start + datetime.timedelta(minutes=1))
    entry.break_minutes = break_minutes
    entry.full_clean()
    _check_overlap(entry)
    if submit:
        entry.status = TimeEntryStatus.SUBMITTED
        entry.submitted_at = timezone.now()
    entry.save()
    return entry


# --- Approval (ZEI-012, ZEI-013) ------------------------------------------------------------------


def submit_entries(entries: list[TimeEntry], *, rights: Rights, user: Any) -> int:
    """Hand entries in for approval (ZEI-012); returns how many changed.

    Entries that are submitted or approved already are left alone, and so is
    a running stopwatch.

    Raises:
        PermissionDenied: One of the entries belongs to somebody the caller
            may not record times for.

    ZEI-025: the other parts of a divided period are handed in with it.
    """
    changed = 0
    for entry in with_periods(entries):
        if not may_record_for(rights, user, entry.person):
            raise PermissionDenied
        if entry.is_running or entry.status not in {TimeEntryStatus.RECORDED, TimeEntryStatus.REJECTED}:
            continue
        entry.status = TimeEntryStatus.SUBMITTED
        entry.submitted_at = timezone.now()
        entry.rejection_reason = ""
        entry.save()
        changed += 1
    return changed


def _require_manager(entries: list[TimeEntry], rights: Rights, user: Any) -> None:
    """Approving and rejecting need the special right, and sight of the project (ZEI-013, ZEI-023)."""
    if not may_manage(rights):
        raise PermissionDenied
    allowed = set(
        manageable_projects(rights, user)
        .filter(pk__in={entry.project_id for entry in entries if entry.project_id})
        .values_list("pk", flat=True)
    )
    if sees_entries_without_project(rights):
        allowed.add(None)
    if any(entry.project_id not in allowed for entry in entries):
        raise PermissionDenied


@transaction.atomic
def assign_project(entry: TimeEntry, project: Project, *, rights: Rights, user: Any) -> TimeEntry:
    """Give an entry recorded without project its project (ZEI-023).

    Done by the person while the entry is open, or by an approver – who then
    needs sight of the entry (:func:`_require_manager`) besides the project.
    The status stays: a submitted entry can be approved right afterwards.

    Raises:
        PermissionDenied: The caller may neither change the entry nor manage it.
        ValidationError: The entry is approved, or the project does not fit
            the person and job function.
    """
    if may_manage(rights):
        _require_manager([entry], rights, user)
    return update_entry(entry, rights=rights, user=user, project=project)


@transaction.atomic
def approve_entries(entries: list[TimeEntry], *, rights: Rights, user: Any, notify: bool = True) -> int:
    """Approve entries, one or many at once (ZEI-012, ZEI-013); returns how many changed.

    ZEI-031 (time approval): each person whose times were approved is told
    once, whatever the number of entries (:func:`tell_decision`);
    ``notify=False`` leaves that to the caller (:func:`correct_and_approve`).

    Approved entries are locked. From now on they count: towards the crew
    line of the same person and job function (ZEI-021), in billing "by
    effort" (PRJ-061) and in the comparison of planned and actual hours.

    Entries that are not submitted – still being recorded, rejected, already
    approved – are left alone.

    Raises:
        PermissionDenied: The caller lacks the right to approve, or cannot
            see one of the projects.
        ValidationError: One of the entries has no project yet (ZEI-023).

    ZEI-025: a part of a divided period is approved with the whole period.
    """
    entries = with_periods(entries)
    _require_manager(entries, rights, user)
    without_project = [entry for entry in entries if entry.project_id is None]
    if without_project:
        raise ValidationError(
            {
                "project": ngettext(
                    "%(count)d time entry has no project yet. Assign one first, then approve.",
                    "%(count)d time entries have no project yet. Assign one first, then approve.",
                    len(without_project),
                )
                % {"count": len(without_project)}
            }
        )
    approved = []
    for entry in entries:
        if entry.status != TimeEntryStatus.SUBMITTED:
            continue
        if entry.crew_line_id is None:
            # The line may have been planned after the time was recorded.
            entry.crew_line = matching_crew_line(entry.project, entry.person, entry.job_function, entry.start)
        entry.status = TimeEntryStatus.APPROVED
        entry.decided_at = timezone.now()
        entry.decided_by = user
        entry.save()
        approved.append(entry)
    # API-012: one event per approved entry, recorded with the approval.
    webhooks.record_each("time_entry.approved", approved)
    if notify and approved:
        tell_decision(approved, APPROVED, actor=user)
    return len(approved)


@transaction.atomic
def reject_entries(entries: list[TimeEntry], reason: str, *, rights: Rights, user: Any) -> int:
    """Send entries back with a reason (ZEI-012); returns how many changed.

    ZEI-031 (time approval): each person is told once, with the reason
    (:func:`tell_decision`).

    Raises:
        PermissionDenied: As for :func:`approve_entries`.
        ValidationError: No reason was given – the person has to know what to correct.

    ZEI-025: a part of a divided period is sent back with the whole period.
    """
    entries = with_periods(entries)
    _require_manager(entries, rights, user)
    if not reason.strip():
        raise ValidationError({"reason": _("Say why the times are rejected, so that they can be corrected.")})
    changed = []
    for entry in entries:
        if entry.status != TimeEntryStatus.SUBMITTED:
            continue
        entry.status = TimeEntryStatus.REJECTED
        entry.rejection_reason = reason.strip()[:250]
        entry.decided_at = timezone.now()
        entry.decided_by = user
        entry.save()
        changed.append(entry)
    if changed:
        tell_decision(changed, REJECTED, actor=user, reason=reason.strip()[:250])
    return len(changed)


@transaction.atomic
def take_back_approval(entry: TimeEntry, *, rights: Rights, user: Any) -> None:
    """Unlock an approved entry: it is "submitted" again and can be corrected (ZEI-012).

    The step is logged like every change of an entry (ZEI-014), and it is an
    event for webhooks (API-012).

    Raises:
        PermissionDenied: As for :func:`approve_entries`.
        ValidationError: The entry is not approved, or an invoiced or marked
            monthly statement bills it (DOK-016).

    ZEI-025: the approval of a divided period is taken back for all its parts.
    """
    rows = period_of(entry)
    _require_manager(rows, rights, user)
    if entry.status != TimeEntryStatus.APPROVED:
        raise ValidationError(_("Only approved times can be unlocked."))
    # DOK-016: billed by a monthly statement – corrected, perhaps on another case, it would be billed twice.
    from rentalars.documents.statements import check_not_billed

    check_not_billed(time_entries=rows)
    for row in rows:
        if row.status != TimeEntryStatus.APPROVED:
            continue
        row.status = TimeEntryStatus.SUBMITTED
        row.decided_at = None
        row.decided_by = None
        row.save()
        record_event(row, "time_entry.approval_taken_back")
        webhooks.record("time_entry.approval_withdrawn", row)


# --- Correction by the approver, and telling the person (ZEI-030, ZEI-031) ----------------------------

#: What became of the times of a person, for :func:`tell_decision`.
APPROVED = "approved"
CORRECTED = "corrected"
REJECTED = "rejected"

#: How many entries a notification names one by one; more are counted.
LISTED_ENTRIES = 10


def entry_summary(entry: TimeEntry) -> str:
    """One entry in a line, in the active language: "Mo 01.03. 08:00–17:00 (−30 min), Tontechnik, 2027-001 Stadtfest"."""
    parts = [
        f"{date_format(timezone.localtime(entry.start), local_pattern('D d.m.'))} "
        f"{date_format(timezone.localtime(entry.start), 'H:i')}–"
        + (date_format(timezone.localtime(entry.end), "H:i") if entry.end else "…")
    ]
    if entry.break_minutes:
        parts[0] += f" (−{entry.break_minutes} min)"
    parts.append(entry.job_function.name)
    parts.append(entry.project_label)
    if entry.note:
        parts.append(f"„{entry.note}“")
    return ", ".join(parts)


def tell_decision(entries: Sequence[TimeEntry], what: str, *, actor: Any, reason: str = "", before: str = "") -> int:
    """Tell each person once what became of their times: approved, corrected and approved, or sent back (ZEI-031).

    One notification per person and action (``Kind.TIME_DECISION``, "Meine
    Zeiten freigegeben, korrigiert oder zurückgegeben"), in the person's
    language, naming the entries – a sending back with its reason, a
    correction with the values before. Only people with an active account;
    never the approver, who decided about their own times. Returns how many
    people were told.
    """
    from rentalars.core.i18n import for_user
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    by_person: dict[int, list[TimeEntry]] = {}
    for entry in entries:
        by_person.setdefault(entry.person_id, []).append(entry)
    told = 0
    for own in by_person.values():
        account = getattr(own[0].person, "user", None)
        if account is None or not account.is_active or (getattr(actor, "pk", None) == account.pk):
            continue
        count, hours = len(own), sum((entry.hours for entry in own), ZERO)
        with for_user(account):
            values = {"count": count, "hours": format_decimal(hours, max_places=2)}
            if what == CORRECTED:
                title = _("Your time was corrected and approved: %(entry)s") % {"entry": entry_summary(own[0])}
                lines = [_("Before: %(before)s") % {"before": before}] if before else []
            elif what == REJECTED:
                title = (
                    ngettext(
                        "%(count)d time entry sent back (%(hours)s h)",
                        "%(count)d time entries sent back (%(hours)s h)",
                        count,
                    )
                    % values
                )
                lines = [_("Reason: %(reason)s") % {"reason": reason}] if reason else []
            else:
                title = (
                    ngettext(
                        "%(count)d time entry approved (%(hours)s h)",
                        "%(count)d time entries approved (%(hours)s h)",
                        count,
                    )
                    % values
                )
                lines = []
            if what != CORRECTED:
                lines += [entry_summary(entry) for entry in own[:LISTED_ENTRIES]]
                if count > LISTED_ENTRIES:
                    lines.append(_("… and %(count)d more") % {"count": count - LISTED_ENTRIES})
            body = "\n".join(lines)
        if notify([account], Kind.TIME_DECISION, title, body=body, url=reverse("timetracking:my_times")):
            told += 1
    return told


@transaction.atomic
def correct_and_approve(
    entry: TimeEntry, *, rights: Rights, user: Any, crew_line: CrewLine | None = None, **changes: Any
) -> TimeEntry:
    """Correct a time waiting for approval and approve it in one step (ZEI-030).

    The requirement: whoever may approve an entry can also make the correction themselves, instead of only sending it back.

    Whoever may approve the entry (ZEI-013) changes its times, break, job
    function, project or note – as the person could while it was open
    (:func:`update_entry`, with its checks: nothing in the future, no
    overlap, a job function the person may book on the project) – and it is
    approved at once. The new project must be one the approver may approve
    for, too. For a part of a period divided into job functions (ZEI-025)
    times, break, project and note hold for the whole period, the job
    function for this part; the whole period is approved.

    The original values stay in the change log of the entry – every field
    with its value before, shown in the history of the person (ZEI-014) –
    and an event "corrected on approval" names them in one line. The person
    is told: corrected and approved, with the values before.

    Raises:
        PermissionDenied: The caller may not approve the entry, or not on its new project.
        ValidationError: The entry is not waiting for approval, a field cannot be
            changed, or the new values break a rule of recording.
    """
    rows = period_of(entry)
    _require_manager(rows, rights, user)
    if entry.status != TimeEntryStatus.SUBMITTED:
        raise ValidationError(
            _("Only times waiting for approval can be corrected here. Take an approval back first to correct it.")
        )
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    before = entry_summary(entry)
    effective = {}
    for name, value in changes.items():
        current = getattr(entry, f"{name}_id") if name in ("project", "job_function") else getattr(entry, name)
        if (value.pk if hasattr(value, "pk") else value) != current:
            effective[name] = value
    if "note" in effective:
        effective["note"] = (effective["note"] or "").strip()
    line_changed = crew_line is not None and crew_line.pk != entry.crew_line_id
    if effective or line_changed:
        entry = update_entry(entry, rights=rights, user=user, crew_line=crew_line, **effective)
        _require_manager(period_of(entry), rights, user)  # the new project, too
    approve_entries([entry], rights=rights, user=user, notify=False)
    entry.refresh_from_db()
    if effective or line_changed:
        record_event(entry, "time_entry.corrected", {"before": before, "after": entry_summary(entry)})
        tell_decision([entry], CORRECTED, actor=user, before=before)
    else:
        tell_decision([entry], APPROVED, actor=user)
    return entry


# --- Reports (ZEI-015 to ZEI-017) --------------------------------------------------------------------


@dataclass
class ReportRow:
    """One line of the hours report: a sum, or a single entry."""

    label: str
    hours: Decimal = ZERO
    #: Hours × the rates fixed on the entries; ``None`` if the reader may not see it.
    amount: Decimal | None = None
    entries: list[TimeEntry] = field(default_factory=list)
    #: UIX-015: the place of the row in the order of the report – for sorting the sums by their first column.
    position: int = 0


@dataclass
class HoursReport:
    """The hours report for a filter (ZEI-015)."""

    rows: list[ReportRow]
    total_hours: Decimal
    total_amount: Decimal | None
    entries: list[TimeEntry]
    #: What the rows are grouped by: "person", "project", "job_function" or "day".
    group_by: str


GROUPINGS = ("person", "project", "job_function", "day")


def hours_report(entries: QuerySet[TimeEntry], *, group_by: str = "person", rights: Rights, user: Any) -> HoursReport:
    """Add up time entries by person, project, job function or day (ZEI-015).

    Args:
        entries: The entries to report on, already narrowed to what the
            reader may see (:func:`visible_entries`) and to the filter.
        group_by: One of :data:`GROUPINGS`.
        rights: The rights of the reader.
        user: The reader.

    Amounts appear only where the reader may see the rates (AUT-019): with
    the right for personnel costs everywhere, otherwise for the reader's own
    entries (PER-010). A sum that would include a hidden amount is left out
    entirely rather than shown too small.

    A running stopwatch has no hours yet and is not part of the report.
    """
    if group_by not in GROUPINGS:
        group_by = "person"
    listed = list(
        entries.filter(end__isnull=False).select_related("person", "project", "job_function").order_by("start", "id")
    )
    may_see = {entry.person_id: may_see_rate_of(rights, user, entry.person) for entry in listed}
    all_visible = all(may_see.values())

    def key_of(entry: TimeEntry) -> tuple[Any, str]:
        if group_by == "project":
            return entry.project_id or 0, str(entry.project) if entry.project_id else _("Without project")
        if group_by == "job_function":
            return entry.job_function_id, entry.job_function.name
        if group_by == "day":
            day = timezone.localtime(entry.start).date()
            return day, day.strftime(local_pattern("%d.%m.%Y"))
        return entry.person_id, entry.person.sort_name

    rows: dict[Any, ReportRow] = {}
    for entry in listed:
        key, label = key_of(entry)
        row = rows.setdefault(key, ReportRow(label=label, amount=ZERO))
        row.hours += entry.hours
        row.entries.append(entry)
        if row.amount is not None:
            row.amount = row.amount + entry.amount if may_see[entry.person_id] else None
    ordered = sorted(rows.items(), key=lambda item: item[0] if group_by == "day" else item[1].label.lower())
    result_rows = [row for _key, row in ordered]
    for position, row in enumerate(result_rows):
        row.position = position
        if row.amount is not None:
            row.amount = money(row.amount)
    return HoursReport(
        rows=result_rows,
        total_hours=sum((row.hours for row in result_rows), ZERO),
        total_amount=money(sum((entry.amount for entry in listed), ZERO)) if all_visible and listed else None,
        entries=listed,
        group_by=group_by,
    )


def week_of(day: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Return Monday and Sunday of the week a day lies in."""
    monday = day - datetime.timedelta(days=day.weekday())
    return monday, monday + datetime.timedelta(days=6)
