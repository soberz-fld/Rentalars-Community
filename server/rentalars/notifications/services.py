# SPDX-License-Identifier: GPL-3.0-or-later
"""Sending notifications, and the settings of each user (UIX-005).

Other modules call :func:`notify` when something happened; this module
decides from the settings of each user whether it appears in the
application, goes by e-mail, both or neither.

E-mails go through the outgoing mail server of the configuration file
(``[email]``), not through the project mailbox: they are messages of the
system, not project correspondence. They are sent once the database change
that caused them is committed – a request that fails sends nothing.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Collection, Iterable
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext_lazy

from rentalars.accounts.rights import Level, Module
from rentalars.core.i18n import LazyCall, LocalText, for_user, format_date, written_for
from rentalars.notifications.categories import category_label, category_of, ordered_kinds
from rentalars.notifications.models import (
    ALWAYS_SENT,
    COMPANION_BY_DEFAULT,
    EMAIL_BY_DEFAULT,
    SETTING_LABELS,
    Kind,
    Notification,
    Preference,
    ShortageNotice,
)

if TYPE_CHECKING:
    from rentalars.accounts.models import User
    from rentalars.projects.models import Project

logger = logging.getLogger(__name__)


def preference(user: User, kind: str) -> tuple[bool, bool]:
    """``(in the application, by e-mail)`` for one user and kind, with the defaults applied."""
    in_app, by_email, _companion = choice(user, kind)
    return in_app, by_email


def choice(user: User, kind: str) -> tuple[bool, bool, bool]:
    """``(in the application, by e-mail, in the companion app)`` for one user and kind, defaults applied (UIX-039).

    A kind of:data:`ALWAYS_SENT` takes the defaults, whatever is stored (UIX-052).
    """
    stored = None if kind in ALWAYS_SENT else Preference.objects.filter(user=user, kind=kind).first()
    if stored is not None:
        return stored.in_app, stored.by_email, stored.companion
    return True, kind in EMAIL_BY_DEFAULT, kind in COMPANION_BY_DEFAULT


def switchable_kinds() -> list[str]:
    """Every kind a user can switch, in the order of the settings (UIX-052)."""
    return [kind for kind in ordered_kinds() if kind not in ALWAYS_SENT]


def setting_label(kind: str) -> str:
    """The name of a kind in the settings: a longer one where the plain name does not say enough (UIX-052)."""
    return str(SETTING_LABELS.get(kind) or dict(Kind.choices)[kind])


def preferences_of(user: User) -> list[dict[str, Any]]:
    """All kinds with the user's choice, for the settings page and the API.

    UIX-039: sorted by category (Projekt, Personal, Material, System), each
    with its category and the choice for the companion app. UIX-052: every kind
    but those of :data:`ALWAYS_SENT`, named as :func:`setting_label` says –
    "A task in the background is finished" names the tasks of the AI.
    """
    stored = {item.kind: item for item in Preference.objects.filter(user=user)}
    result = []
    for kind in switchable_kinds():
        item = stored.get(kind)
        category = category_of(kind)
        result.append(
            {
                "kind": kind,
                "label": setting_label(kind),
                "category": category,
                "category_label": category_label(category),
                "in_app": item.in_app if item else True,
                "by_email": item.by_email if item else kind in EMAIL_BY_DEFAULT,
                "companion": item.companion if item else kind in COMPANION_BY_DEFAULT,
            }
        )
    return result


def set_preference(user: User, kind: str, *, in_app: bool, by_email: bool, companion: bool | None = None) -> None:
    """Store the choice of a user for one kind; ``companion=None`` keeps the choice for the app as it is."""
    if kind not in Kind.values or kind in ALWAYS_SENT:
        raise ValueError(kind)
    values = {"in_app": in_app, "by_email": by_email}
    if companion is None:
        companion = choice(user, kind)[2]
    values["companion"] = companion
    Preference.objects.update_or_create(user=user, kind=kind, defaults=values)


def _absolute(url: str) -> str:
    if not url or url.startswith("http"):
        return url
    return f"{settings.RENTALARS_URL}{url}"


def _send_email(notification_ids: list[int]) -> None:
    """Send the e-mails of some notifications; a failure is logged, never raised."""
    for notification in Notification.objects.filter(pk__in=notification_ids).select_related("user"):
        if not notification.user.email:
            continue
        lines = [notification.body] if notification.body else []
        if notification.url:
            lines.append(_absolute(notification.url))
        lines.append("")
        try:
            # UIX-029: the mail – its last line and the footer (EML-045) – in the recipient's language.
            with for_user(notification.user):
                lines.append(_("You can switch these messages off under “My account” → “Notifications”."))
                sent = send_mail(
                    f"[Rentalars] {notification.title}",
                    "\n\n".join(lines),
                    None,
                    [notification.user.email],
                )
        except Exception:
            logger.warning("Notification %s could not be sent by e-mail.", notification.pk, exc_info=True)
            continue
        if not sent:
            continue  # EML-048: no mail server – it only went into the log of the server
        Notification.objects.filter(pk=notification.pk).update(emailed_at=timezone.now())


def notify(
    users: Iterable[User | None],
    kind: str,
    title: str | LocalText,
    *,
    body: str | LocalText = "",
    url: str = "",
    project: Project | None = None,
    exclude: User | None = None,
    email: bool = True,
) -> list[Notification]:
    """Tell some users about something (UIX-005).

    Args:
        users: Who should know. Duplicates, inactive accounts and ``None``
            are left out, and so is ``exclude`` – usually whoever caused it.
        kind: One of :class:`~rentalars.notifications.models.Kind`.
        title: One line, shown in the list and as the subject of the e-mail. A
            :class:`~rentalars.core.i18n.LocalText` is written in each
            recipient's language (UIX-029); a plain text stays as it is.
        body: Optional details, likewise.
        url: Where the notification leads, a path such as ``/projects/12/``.
        project: The project it is about, if any.
        exclude: A user who gets nothing, usually the one who acted.
        email: ``False`` leaves the e-mail out: the caller sends a mail of
            its own, such as the request with the buttons to answer by
            mail (PER-032).

    Returns:
        The notifications created in the application.

    Raises:
        ValueError: ``kind`` is not one of :class:`Kind` – each kind sent must be one the users can switch
            (UIX-052).
    """
    if kind not in Kind.values:
        raise ValueError(kind)
    created: list[Notification] = []
    to_email: list[int] = []
    seen: set[int] = set()
    for user in users:
        if user is None or not user.pk or user.pk in seen or not user.is_active:
            continue
        seen.add(user.pk)
        if exclude is not None and user.pk == exclude.pk:
            continue
        in_app, by_email, companion = choice(user, kind)
        by_email = by_email and email
        if not in_app and not by_email and not companion:
            continue
        notification = Notification.objects.create(
            user=user,
            kind=kind,
            # UIX-029: a LocalText (or a lazy text) is written in the language of each recipient.
            title=written_for(title, user)[:250],
            body=written_for(body, user),
            url=url[:500],
            project=project,
            # Wanted by e-mail or on the phone only: it is still kept, as already read.
            read_at=None if in_app else timezone.now(),
            # UIX-039: the companion app shows it on the phone.
            companion=companion,
        )
        if in_app:
            created.append(notification)
        if by_email:
            to_email.append(notification.pk)
    if to_email:
        transaction.on_commit(lambda: _send_email(to_email))
    return created


def unread(user: User) -> Any:
    """The unread notifications of a user, newest first."""
    return Notification.objects.filter(user=user, read_at__isnull=True)


def unread_count(user: User) -> int:
    """How many notifications the user has not read; shown on the bell."""
    return unread(user).count()


def mark_read(user: User, ids: Iterable[int] | None = None) -> int:
    """Mark some – or all – notifications of a user as read; returns how many."""
    notifications = unread(user)
    if ids is not None:
        notifications = notifications.filter(pk__in=list(ids))
    return notifications.update(read_at=timezone.now())


def delete_old_notifications() -> int:
    """Remove notifications after the retention period of the administration (NFA-011, daily maintenance)."""
    from rentalars.core.models import SystemSettings

    limit = timezone.now() - datetime.timedelta(days=SystemSettings.load().retention_notifications_days)
    deleted, _details = Notification.objects.filter(created_at__lt=limit).delete()
    return deleted


# --- Who should know ---------------------------------------------------------------------------


def _users_with(module: str, level: int) -> list[User]:
    from rentalars.accounts.models import User

    return [
        user
        for user in User.objects.filter(is_active=True).prefetch_related("roles")
        if user.is_superuser or user.rights.has_level(module, level)
    ]


def operators() -> list[User]:
    """Everybody who may change the administration: they run the installation (NFA-018)."""
    return _users_with(Module.ADMINISTRATION, Level.WRITE)


def personnel_planners() -> list[User]:
    """Everybody who may change people: personnel planning (PER-014)."""
    return _users_with(Module.PERSONNEL, Level.WRITE)


def warehouse_staff() -> list[User]:
    """Everybody who may change material: they deal with defects (UIX-005)."""
    return _users_with(Module.MATERIAL, Level.WRITE)


def project_people(project: Project) -> list[User]:
    """The project manager and the members who may edit the project."""
    from rentalars.projects.models import ProjectAccessLevel

    people: list[User] = [project.manager] if project.manager_id else []
    people += [
        membership.user
        for membership in project.memberships.filter(level=ProjectAccessLevel.EDIT).select_related("user")
    ]
    return people


def _may_see_shortage(project: Project, users: list[User]) -> list[User]:
    """Of these users those who may see a shortage of the project (AUT-032).

    They need the special right to see availability and the planning of the
    project: a role "Crew" managing a project sees neither.
    """
    from rentalars.accounts.rights import SpecialRight
    from rentalars.projects.access import ProjectAccess, access_level

    return [
        user
        for user in users
        if user is not None
        and user.rights.has(SpecialRight.AVAILABILITY)
        and access_level(user.rights, user, project) >= ProjectAccess.READ
    ]


def crew_users(project: Project, *, without: Collection[int] = ()) -> list[User]:
    """The users of the people planned in a project, for changes that concern them; ``without``: person IDs."""
    from rentalars.accounts.models import User

    users = User.objects.filter(is_active=True, person__crew_lines__project=project)
    if without:
        users = users.exclude(person__pk__in=list(without))
    return list(users.distinct())


# --- Messages of the system ---------------------------------------------------------------------------


def notify_operators_of_error(error: Any) -> None:
    """Tell the operators about an error of the application (NFA-018)."""
    # UIX-029: each operator reads it in his language.
    title = LocalText(gettext_lazy("Error in Rentalars: %(message)s"), message=error.message[:120])
    body = LocalText(
        gettext_lazy("Where: %(source)s\nHow often so far: %(count)d\nFirst: %(first)s\nLast: %(last)s"),
        source=error.source,
        count=error.count,
        first=LazyCall(format_date, timezone.localtime(error.first_seen), "d.m.Y H:i"),
        last=LazyCall(format_date, timezone.localtime(error.last_seen), "d.m.Y H:i"),
    )
    notify(operators(), Kind.SYSTEM_ERROR, title, body=body, url=reverse("core:self_check"))


def project_changed(
    project: Project, what: str, *, actor: User | None, crew_too: bool = False, crew_told: Collection[int] = ()
) -> None:
    """Tell the project manager – and the crew, if it concerns them – about a change (UIX-005).

    ``crew_told``: people of the crew who were told of the change already, each of their own lines (PRJ-118).
    """
    users = project_people(project) + (crew_users(project, without=crew_told) if crew_too else [])
    notify(
        users,
        Kind.PROJECT_CHANGE,
        LocalText(gettext_lazy("%(project)s: %(what)s"), project=project, what=what),
        url=reverse("projects:overview", args=[project]),
        project=project,
        exclude=actor,
    )


def _report_shortage(
    project: Project, title: LocalText, *, start: datetime.datetime, items: list[LocalText] | None = None
) -> None:
    """Tell who may see it about shortages of a project (UIX-005); ``start``: from when the material is missing.

    ``items``: lines put before the text, one per shortage (VFG-036: the list of a reminder).
    """
    # AUT-032: only who may see it; nobody of the project – those who may change projects.
    recipients = _may_see_shortage(project, project_people(project)) or _may_see_shortage(
        project, _users_with(Module.PROJECTS, Level.WRITE)
    )
    body = LocalText(
        gettext_lazy("From %(start)s. Shortage list: Planning → Shortages."),
        start=LazyCall(format_date, timezone.localtime(start), "d.m.Y H:i"),
    )
    if items:
        # Each line written in the language of each recipient, as the rest (UIX-029).
        body = LocalText("%(items)s%(text)s", items=LazyCall(_lines, items), text=body)
    notify(
        recipients,
        Kind.SHORTAGE,
        title,
        body=body,
        url=reverse("projects:overview", args=[project]),
        project=project,
    )


def _lines(items: list[Any]) -> str:
    """Texts one per line, each ending with a line break; written in the active language."""
    return "".join(f"{item}\n" for item in items)


def _remind_of_shortages(shortages: list[Any]) -> None:
    """VFG-036: remind of the known shortages of one project – one notification for all.

    One shortage keeps its title ("Still a shortage in …: 3 × Topteil
    missing"). Several get a short title with their number ("Still shortages
    in …: 7 products") and the whole list in the text, one per line, in the
    order found (in the title, which ends after 250 characters,
    a long list would lose its last products).
    """
    first = shortages[0]
    start = min(shortage.line.start for shortage in shortages)
    if len(shortages) == 1:
        title = LocalText(
            gettext_lazy("Still a shortage in %(project)s: %(quantity)d × %(product)s missing"),
            project=first.project,
            quantity=first.quantity,
            product=first.product.name,
        )
        _report_shortage(first.project, title, start=start)
        return
    title = LocalText(
        ngettext_lazy(
            "Still shortages in %(project)s: %(count)d product",
            "Still shortages in %(project)s: %(count)d products",
            len(shortages),
        ),
        project=first.project,
        count=len(shortages),
    )
    items = [
        LocalText(
            gettext_lazy("%(quantity)d × %(product)s missing"),
            quantity=shortage.quantity,
            product=shortage.product.name,
        )
        for shortage in shortages
    ]
    _report_shortage(first.project, title, start=start, items=items)


def check_shortages(*, horizon_days: int = 28, repeat: bool = False) -> int:
    """Report new shortages of the coming weeks to the project managers (UIX-005, VFG-013, VFG-036).

    Run at the time set under Einstellungen → Benachrichtigungen
    (:func:`run_due_shortage_check`).
    A shortage is reported once; it is reported again only if it grows.
    Shortages that disappeared are forgotten, so that a shortage that comes
    back is reported again.

    VFG-036: only the shortages of projects that were looked at are
    forgotten – a shortage already reported of a project that now begins
    beyond ``horizon_days`` (the lead time was shortened, the project moved)
    stays known and is not reported a second time when it comes near again.
    ``repeat`` reports every open shortage again, the known ones as "still
    missing" (VFG-036) – one
    reminder per project and check with all its known shortages, not one per
    shortage: switched on by default, a project short of ten products would
    otherwise send ten mails every morning. New and grown shortages are still
    reported one by one.

    Args:
        horizon_days: How far ahead: projects that begin within so many days.
        repeat: Report known shortages again (a reminder), not only new or grown ones.

    Returns:
        The number of shortages reported now – each shortage of a reminder counted.
    """
    from rentalars.availability.services import open_shortages
    from rentalars.projects.models import FINISHED_STATUSES

    current = open_shortages(horizon_days=horizon_days)
    until = timezone.now() + datetime.timedelta(days=horizon_days)
    known = {(notice.line_id, notice.product_id): notice for notice in ShortageNotice.objects.all()}
    still_there: set[tuple[int, int]] = set()
    # VFG-036: the known shortages to remind of, per project, in the order found.
    reminders: dict[int, list[Any]] = {}
    reported = 0
    for shortage in current:
        key = (shortage.line.pk, shortage.product.pk)
        still_there.add(key)
        notice = known.get(key)
        again = notice is not None and notice.quantity >= shortage.quantity
        if again and not repeat:
            continue
        reported += 1
        ShortageNotice.objects.update_or_create(
            line_id=key[0], product_id=key[1], defaults={"quantity": shortage.quantity, "reported_at": timezone.now()}
        )
        if again:
            reminders.setdefault(shortage.project.pk, []).append(shortage)
            continue
        _report_shortage(
            shortage.project,
            LocalText(
                gettext_lazy("Shortage in %(project)s: %(quantity)d × %(product)s missing"),
                project=shortage.project,
                quantity=shortage.quantity,
                product=shortage.product.name,
            ),
            start=shortage.line.start,
        )
    for shortages in reminders.values():
        _remind_of_shortages(shortages)
    gone = [notice.pk for key, notice in known.items() if key not in still_there]
    if gone:
        # VFG-036: what lies beyond the lead time was not looked at – it stays known. Two plain queries: MariaDB
        # refuses a DELETE whose subquery reads the same table.
        beyond = set(
            ShortageNotice.objects.filter(pk__in=gone, line__project__start__gt=until)
            .exclude(line__project__status__in=FINISHED_STATUSES)
            .values_list("pk", flat=True)
        )
        ShortageNotice.objects.filter(pk__in=[pk for pk in gone if pk not in beyond]).delete()
    return reported


def run_due_shortage_check(now: datetime.datetime | None = None) -> int | None:
    """Run the shortage check when its time has come (VFG-036); called every minute by ``run_jobs``.

    Due is the latest moment of the schedule (time of day, how often) that
    lies after the last check – so a check missed while the server was off is
    made up once at the next run. A moment is claimed by an update of the
    last check before checking: of two runs at the same time only one checks.
    Without a last check (the first minute after the update or the
    installation) the time is only noted: the first check is at the next time
    set.

    In the quiet minutes this costs one query.

    Returns:
        The number of shortages reported, ``None`` if no check was due.
    """
    from rentalars.core.models import NotificationSettings, ShortageInterval
    from rentalars.notifications.schedule import holiday_test, latest_slot

    now = now or timezone.now()
    settings = NotificationSettings.load()
    if settings.shortage_interval == ShortageInterval.OFF:
        return None
    rows = NotificationSettings.objects.filter(pk=1)
    last = settings.shortage_last_run
    if last is None:
        rows.filter(shortage_last_run__isnull=True).update(shortage_last_run=now)
        return None
    # Without the holidays the latest moment is never earlier: the quick test first.
    slot = latest_slot(settings, now)
    if slot is None or last >= slot:
        return None
    if settings.shortage_interval == ShortageInterval.WORKDAYS:
        slot = latest_slot(settings, now, holiday_test())
        if slot is None or last >= slot:
            return None
    if not rows.filter(shortage_last_run__lt=slot).update(shortage_last_run=now):
        return None
    reported = check_shortages(horizon_days=settings.shortage_lead_weeks * 7, repeat=settings.shortage_repeat)
    rows.update(shortage_checked_at=now, shortage_reported=reported)
    return reported


#: VFG-036: the fields that decide when the check runs; changing one starts the schedule anew.
SCHEDULE_FIELDS = ("shortage_interval", "shortage_weekday", "shortage_time")


def schedule_changed(now: datetime.datetime | None = None) -> None:
    """The time or the interval of the shortage check was changed: the new one counts from the next moment on.

    Without this, a time set earlier than now (or switching the check on
    again) would make up the moment already past at once (VFG-036).
    """
    from rentalars.core.models import NotificationSettings

    NotificationSettings.objects.filter(pk=1).update(shortage_last_run=now or timezone.now())
