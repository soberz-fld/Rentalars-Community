# SPDX-License-Identifier: GPL-3.0-or-later
"""The follow-up of a project – "Wiedervorlage" (PRJ-105).

A project of any status – typically an inquiry or an offer – gets a day, a
note and the user the follow-up is for; whoever sets it, unless somebody
else is chosen. On that day the user is notified, in the application and by
e-mail as the user's notification settings say (kind "follow_up",
:func:`notify_due_follow_ups`). PRJ-109: a follow-up may have a time
of day as well ("um 14:30"); it is then due – notified, marked, counted by
the filter "due" and the automations – from that time on. Until it is done the follow-up shows in the
head of the project, the start page shows the user's due follow-ups, and the
list of projects filters and shows them. "Done" removes it.

Setting or removing a follow-up does not change the planning: it is possible
in every status, a closed project included, for whoever may edit the
project. The change log notes who set which day for whom, so the history of
the project shows it.

Browser views and API call these functions alike (API-002).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy

from rentalars.core.i18n import for_user, local_pattern
from rentalars.projects.access import ProjectAccess, access_level
from rentalars.projects.models import CaseStatus, Project, ProjectKind

if TYPE_CHECKING:
    from rentalars.accounts.models import User

#: The fields of a follow-up; changed together, never through the form of the project.
FIELDS = ("follow_up_on", "follow_up_at", "follow_up_note", "follow_up_user", "follow_up_notified_at")

#: From this hour of the day on (local time) the follow-ups of the day without a time are notified – not in the
#: night. One with a time (PRJ-109) is notified from that time on.
NOTIFY_FROM_HOUR = 6

#: The longest note.
NOTE_LENGTH = 250

#: The filters of the list of projects and of the API: ``due`` – the day has come, ``mine`` – for the
#: user, any day, ``any`` – every project with a follow-up.
FILTER_CHOICES = (
    ("due", pgettext_lazy("follow-up", "due")),
    ("mine", gettext_lazy("for me")),
    ("any", gettext_lazy("all with follow-up")),
)
FILTERS = tuple(value for value, _label in FILTER_CHOICES)


def due_condition(now: datetime.datetime | None = None) -> Q:
    """The follow-ups that are due at this moment: the day has come and – with a time – that time (PRJ-109)."""
    local = timezone.localtime(now or timezone.now())
    return Q(follow_up_on__lt=local.date()) | Q(
        Q(follow_up_at__isnull=True) | Q(follow_up_at__lte=local.time()), follow_up_on=local.date()
    )


def when_text(project: Project, day_format: str = "D d.m.Y") -> str:
    """``Mo 20.10.2026`` or – with a time (PRJ-109) – ``Mo 20.10.2026 um 14:30``; empty without a follow-up."""
    if project.follow_up_on is None:
        return ""
    day = date_format(project.follow_up_on, local_pattern(day_format))  # UIX-029: 20/10/2026 in English
    if project.follow_up_at is None:
        return day
    return _("%(day)s at %(time)s") % {"day": day, "time": project.follow_up_at.strftime("%H:%M")}


def may_be_for(user: User | None, project: Project) -> bool:
    """Whether a follow-up of this project can be for this user: an active account that may open it."""
    if user is None or not user.is_active:
        return False
    return access_level(user.rights, user, project) >= ProjectAccess.READ


@transaction.atomic
def set_follow_up(
    project: Project,
    *,
    on: datetime.date | None,
    note: str = "",
    user: User | None = None,
    by: User | None = None,
    at: datetime.time | None = None,
    case_status: str | None = None,
) -> Project:
    """Set or change the follow-up of a project (PRJ-105).

    Args:
        project: The project, of any status.
        on: The day of the follow-up; a day in the past is allowed (it is due at once).
        note: What is to be done, e.g. "Angebot nachfassen".
        user: Who the follow-up is for; without one, ``by``.
        by: Who sets it.
        at: PRJ-109: the time of the reminder; without one the follow-up is
            notified on the morning of its day, as before.
        case_status: PRJ-112: the status a service case gets with this
            follow-up (``service_cases.set_case_status``); without it, its
            current one. A case waiting to close needs the time.

    A new day, time or user notifies again; changing only the note does not.

    Raises:
        ValidationError: No day, no user, a user who may not open the project,
            or a note that is too long.
    """
    user = user or by
    note = (note or "").strip()
    errors: dict[str, str] = {}
    if on is None:
        errors["follow_up_on"] = _("Choose the day of the follow-up.")
    if user is None:
        errors["follow_up_user"] = _("Choose who the follow-up is for.")
    elif not may_be_for(user, project):
        errors["follow_up_user"] = _("%(user)s may not open this project.") % {"user": user}
    if project.is_service_case and (case_status or project.case_status) == CaseStatus.CLOSING and at is None:
        # PRJ-112: the case is closed at that moment – the day alone is not enough.
        errors["follow_up_at"] = _("Choose the time at which the service case is closed.")
    if len(note) > NOTE_LENGTH:
        errors["follow_up_note"] = _("The note may have at most %(count)d characters.") % {"count": NOTE_LENGTH}
    if errors:
        raise ValidationError(errors)
    assert user is not None  # for the type checker: refused above
    if at is not None:
        at = at.replace(second=0, microsecond=0, tzinfo=None)
    fields = ["follow_up_on", "follow_up_at", "follow_up_note", "follow_up_user"]
    if (project.follow_up_on, project.follow_up_at, project.follow_up_user_id) != (on, at, user.pk):
        # A new day, time or user: notified again. Otherwise the note of the notification stays as it was.
        project.follow_up_notified_at = None
        fields.append("follow_up_notified_at")
    project.follow_up_on = on
    project.follow_up_at = at
    project.follow_up_note = note
    project.follow_up_user = user
    project.save(update_fields=fields)
    return project


@transaction.atomic
def clear_follow_up(project: Project) -> bool:
    """Remove the follow-up of a project – done or no longer wanted (PRJ-105).

    PRJ-112: a service case waiting, waiting to close or in the backlog has
    those statuses only with a follow-up; without it, it is open again.

    Returns:
        Whether anything was removed (a day, or only a note or a person).
    """
    from rentalars.projects.service_cases import FOLLOW_UP_STATUSES

    had = project.follow_up_on is not None
    if not had and not project.follow_up_note and project.follow_up_user_id is None:
        return False
    project.follow_up_on = None
    project.follow_up_at = None
    project.follow_up_note = ""
    project.follow_up_user = None
    project.follow_up_notified_at = None
    fields = list(FIELDS)
    if project.is_service_case and project.case_status in FOLLOW_UP_STATUSES:
        project.case_status = CaseStatus.OPEN
        project.case_waiting_for = ""
        fields += ["case_status", "case_waiting_for"]
    project.save(update_fields=fields)
    return True  # something was removed – a note or a person alone count


def filter_projects(projects: QuerySet[Project], kind: str, user: Any) -> QuerySet[Project]:
    """The projects of a filter of the list and the API: ``due``, ``mine`` or ``any`` (PRJ-105).

    ``due`` honours the time of a follow-up (PRJ-109). An unknown value
    leaves the projects as they are.
    """
    if kind == "due":
        return projects.filter(due_condition())
    if kind == "mine":
        return projects.filter(follow_up_on__isnull=False, follow_up_user=user)
    if kind == "any":
        return projects.filter(follow_up_on__isnull=False)
    return projects


def due_for(user: Any, projects: QuerySet[Project]) -> QuerySet[Project]:
    """The follow-ups of a user that are due, the oldest first – for the start page (PRJ-105, PRJ-109)."""
    return projects.filter(due_condition(), follow_up_user=user).order_by(
        "follow_up_on", F("follow_up_at").asc(nulls_first=True), "number"
    )


def _notify_until(now: datetime.datetime) -> datetime.date:
    """The last follow-up day to notify at this moment: today from the morning on, else yesterday."""
    local = timezone.localtime(now)
    if local.hour >= NOTIFY_FROM_HOUR:
        return local.date()
    return local.date() - datetime.timedelta(days=1)


def _closing_rule_active() -> bool:
    """PRJ-112: whether an active rule closes a case "waiting to close" when its follow-up is due (ADM-013)."""
    from rentalars.automations.models import Action, Automation, Trigger

    return Automation.objects.filter(
        is_active=True,
        trigger=Trigger.CASE_FOLLOW_UP,
        status=CaseStatus.CLOSING,
        action=Action.CASE_STATUS,
        new_case_status=CaseStatus.DONE,
    ).exists()


def notify_due_follow_ups(now: datetime.datetime | None = None) -> int:
    """Tell every user whose follow-up is due – once per follow-up (PRJ-105, PRJ-109).

    PRJ-112: the due follow-up of a service case is processed even
    with nobody to notify, so that its automations run (the trigger is
    independent of the notification). A case "waiting to close" gets no
    reminder while an active rule closes it at that moment; with the rule
    switched off it is notified as usual. A case in the backlog is notified
    as usual: that is the moment it is back on the dashboards.

    Run every minute with the tasks in the background (``run_jobs``). The
    follow-ups of a day without a time are notified from
    :data:`NOTIFY_FROM_HOUR` o'clock on; one set for today later in the day
    right away. One with a time is notified from that time on (PRJ-109). A follow-up whose user is
    gone or deactivated goes to the project manager. Whether it appears in the application,
    goes by e-mail or both, the user's notification settings decide.

    Returns:
        How many due follow-ups were processed (notified, or – PRJ-112 – handed to the automations).
    """
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    now = now or timezone.now()
    without_time = Q(follow_up_at__isnull=True, follow_up_on__lte=_notify_until(now))
    with_time = Q(due_condition(now), follow_up_at__isnull=False)
    due = (
        Project.objects.filter(without_time | with_time, follow_up_notified_at__isnull=True)
        # PRJ-112: a service case also without anybody to notify – its automations must run all the same.
        .filter(Q(follow_up_user__isnull=False) | Q(manager__isnull=False) | Q(kind=ProjectKind.SERVICE_CASE))
        .select_related("follow_up_user", "manager")
        .order_by("follow_up_on", F("follow_up_at").asc(nulls_first=True), "pk")
    )
    closed_by_rule = _closing_rule_active()
    count = 0
    for project in due[:500]:
        user = project.follow_up_user
        recipient = user if user is not None and user.is_active else project.manager
        # PRJ-112: a case waiting to close is closed by the rule at this moment – no reminder besides.
        quiet = closed_by_rule and project.is_service_case and project.case_status == CaseStatus.CLOSING
        if recipient is not None and not quiet:
            # UIX-029: in the language of the one who gets it.
            with for_user(recipient):
                body = _("Follow-up of %(day)s.") % {"day": when_text(project)}
                title = _("Follow-up: %(project)s") % {"project": project}
            if project.follow_up_note:
                body = f"{project.follow_up_note}\n\n{body}"
            notify(
                [recipient],
                Kind.FOLLOW_UP,
                title,
                body=body,
                url=reverse("projects:overview", args=[project]),
                project=project,
            )
        # Bookkeeping, not a change of the project: no entry in the change log.
        Project.objects.filter(pk=project.pk).update(follow_up_notified_at=now)
        # ADM-013: automations of the trigger "a follow-up is due" – once, like the notification.
        from rentalars.automations.engine import follow_up_due

        follow_up_due(project)
        if project.is_service_case:
            # PRJ-112, ADM-013: the trigger of the service cases, with their status as condition.
            from rentalars.automations.engine import case_follow_up_due

            case_follow_up_due(project)
        count += 1
    return count
