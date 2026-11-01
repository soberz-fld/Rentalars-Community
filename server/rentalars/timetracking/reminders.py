# SPDX-License-Identifier: GPL-3.0-or-later
"""Reminders of the times waiting for approval (ZEI-029; ZEI-013).

The requirement: authorised people get a notification at defined times (like the open points) when there are open times in time tracking (Personnel → Approve).

Who is reminded
---------------
Everybody who may approve times: write access to time tracking and the special right "approve times and record them
for others" (``services.may_manage``) – the role "Projektleitung" and "Personaldisposition" have it at first. Each of
them only of what they may approve, as the page Personal → Freigeben shows it: the times handed in of the projects
they may see and of the internal ones, those without project if their right holds for all projects
(``services.sees_entries_without_project``), and the expenses handed in of those projects (ZEI-019) – never of their
own. The reminder (``Kind.TIMES_TO_APPROVE``, "Zeiten warten auf meine Freigabe") counts them and leads to Personal →
Freigeben.

When (Einstellungen → Benachrichtigungen)
-----------------------------------------
Once a day at the time set (8:00 at first), on the minute timer of the tasks in the background (``run_jobs``) like
the shortage check and the reminders of invoices (DOK-015): a time counts once it has waited the days set since the
day it was handed in (1 at first: the morning after), and the reminder is repeated every few days (1 at first:
every morning) as long as something waits. Both are counted in days of the local calendar, never in hours: the
change to summer time, a reminder made up late or a run that started late do not skip a day. When nothing waits for a person any more, the next time handed in starts
anew. A check missed while the server was off is made up once at the next run; of two runs at the same moment only
one reminds; the first minute after the update only notes its time.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from django.db.models import Min, Q, QuerySet
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.core.i18n import for_user, local_pattern
from rentalars.projects.access import person_of
from rentalars.timetracking.models import Expense, TimeEntry, TimeEntryStatus
from rentalars.timetracking.services import manageable_projects, may_manage, sees_entries_without_project

logger = logging.getLogger(__name__)


def approvers() -> list[Any]:
    """The active users who may approve times (ZEI-013)."""
    from rentalars.accounts.models import User
    from rentalars.accounts.rights import rights_of

    users = User.objects.filter(is_active=True).prefetch_related("roles").order_by("pk")
    return [user for user in users if may_manage(rights_of(user))]


def waiting_for(user: Any, rights: Any) -> tuple[QuerySet[TimeEntry], QuerySet[Expense]]:
    """The times and expenses handed in that ``user`` may approve – not their own (see the module description)."""
    projects = manageable_projects(rights, user).values("pk")
    where = Q(project__in=projects)
    if sees_entries_without_project(rights):
        where |= Q(project__isnull=True)
    entries = TimeEntry.objects.filter(where, status=TimeEntryStatus.SUBMITTED)
    expenses = Expense.objects.filter(project__in=projects, status=TimeEntryStatus.SUBMITTED)
    own = person_of(user)
    if own is not None:
        entries, expenses = entries.exclude(person=own), expenses.exclude(person=own)
    return entries, expenses


def _settings() -> Any:
    from rentalars.core.models import NotificationSettings

    return NotificationSettings.load()


def _due_since(settings_row: Any, now: datetime.datetime) -> datetime.datetime:
    """Handed in before this moment counts: on a day at least ``approval_first_days`` before today (calendar days)."""
    day = timezone.localdate(now) - datetime.timedelta(days=settings_row.approval_first_days - 1)
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def is_repeat_due(last_reminded_at: datetime.datetime, every_days: int, now: datetime.datetime) -> bool:
    """Whether "again every N days" is due: ``every_days`` days of the calendar after the day of the last reminder.

    Counted in local dates, not in hours (ZEI-029): the run of the next morning is "a day later" even
    if only 23 hours passed – the switch to summer time, a reminder made up at 10:00 after a downtime, a run that
    started late the day before.
    """
    return timezone.localdate(now) >= timezone.localdate(last_reminded_at) + datetime.timedelta(days=every_days)


def remind_due(now: datetime.datetime | None = None) -> int:
    """Remind every approver for whom something is due now; returns how many were reminded."""
    from rentalars.accounts.rights import rights_of
    from rentalars.notifications.models import ApprovalNotice

    now = now or timezone.now()
    settings_row = _settings()
    since = _due_since(settings_row, now)
    notices = {notice.user_id: notice for notice in ApprovalNotice.objects.all()}
    reminded = 0
    for user in approvers():
        entries, expenses = waiting_for(user, rights_of(user))
        times = entries.filter(submitted_at__lt=since).count()
        costs = expenses.filter(submitted_at__lt=since).count()
        notice = notices.get(user.pk)
        if not times and not costs:
            if notice is not None and not entries.exists() and not expenses.exists():
                notice.delete()  # nothing waits any more: the next time handed in starts anew
            continue
        if notice is not None and not is_repeat_due(notice.last_reminded_at, settings_row.approval_every_days, now):
            continue
        try:
            remind(user, times, costs, oldest=_oldest(entries, expenses))
        except Exception:
            logger.exception("The times to approve could not be reminded of for user %s.", user.pk)
            continue
        if notice is None:
            ApprovalNotice.objects.create(user=user, first_reminded_at=now, last_reminded_at=now, count=1)
        else:
            notice.last_reminded_at, notice.count = now, notice.count + 1
            notice.save(update_fields=["last_reminded_at", "count"])
        reminded += 1
    return reminded


def _oldest(entries: QuerySet[TimeEntry], expenses: QuerySet[Expense]) -> datetime.datetime | None:
    moments = [
        entries.aggregate(first=Min("submitted_at"))["first"],
        expenses.aggregate(first=Min("submitted_at"))["first"],
    ]
    found = [moment for moment in moments if moment is not None]
    return min(found) if found else None


def remind(user: Any, times: int, expenses: int, *, oldest: datetime.datetime | None = None) -> None:
    """Send one reminder: how many times and expenses wait, since when – leading to Personal → Freigeben."""
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    with for_user(user):  # UIX-029: in the language of the approver
        parts = []
        if times:
            parts.append(ngettext("%(count)d time entry", "%(count)d time entries", times) % {"count": times})
        if expenses:
            parts.append(ngettext("%(count)d expense", "%(count)d expenses", expenses) % {"count": expenses})
        title = _("Waiting for your approval: %(what)s") % {"what": ", ".join(parts)}
        body = (
            _("The oldest was handed in on %(date)s. Approve them under Personnel → Approve.")
            % {"date": formats.date_format(timezone.localtime(oldest), local_pattern("D d.m.Y"))}
            if oldest is not None
            else ""
        )
    notify([user], Kind.TIMES_TO_APPROVE, title, body=body, url=reverse("timetracking:approval"))


def latest_slot(time_of_day: datetime.time, now: datetime.datetime) -> datetime.datetime:
    """The latest moment at or before ``now`` at the time of day of the reminders."""
    local = timezone.localtime(now)
    day = local.date() if local.time() >= time_of_day else local.date() - datetime.timedelta(days=1)
    return timezone.make_aware(datetime.datetime.combine(day, time_of_day))


def next_run(now: datetime.datetime | None = None) -> datetime.datetime | None:
    """When the times waiting are looked at next, for the settings page; ``None`` while switched off."""
    settings_row = _settings()
    if not settings_row.approval_reminders:
        return None
    now = now or timezone.now()
    slot = latest_slot(settings_row.approval_time, now)
    last = settings_row.approval_last_run
    if last is not None and last < slot:
        return now
    return slot + datetime.timedelta(days=1)


def run_due_approval_reminders(now: datetime.datetime | None = None) -> int | None:
    """Remind of the times waiting once a day at the time set; called every minute by ``run_jobs``.

    As the reminders of invoices (DOK-015): the first minute after the update
    or the installation only notes its time; a run missed while the server
    was off is made up once; of two runs at the same moment only one
    reminds – the moment is claimed by an update of the last run before. In
    the quiet minutes this costs one query.

    Returns:
        How many people were reminded, ``None`` if nothing was due.
    """
    from rentalars.core.models import NotificationSettings

    now = now or timezone.now()
    settings_row = NotificationSettings.load()
    if not settings_row.approval_reminders:
        return None
    rows = NotificationSettings.objects.filter(pk=1)
    last = settings_row.approval_last_run
    if last is None:
        rows.filter(approval_last_run__isnull=True).update(approval_last_run=now)
        return None
    slot = latest_slot(settings_row.approval_time, now)
    if last >= slot:
        return None
    if not rows.filter(approval_last_run__lt=slot).update(approval_last_run=now):
        return None
    reminded = remind_due(now)
    rows.update(approval_checked_at=now, approval_reminded=reminded)
    return reminded
