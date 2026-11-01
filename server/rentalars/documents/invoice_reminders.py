# SPDX-License-Identifier: GPL-3.0-or-later
"""Reminders of invoices not written yet, and "Rechnung gestellt" (DOK-015).

The requirement: if invoicing is switched on in the system, a finished project reminds regularly to write the invoice; if it is switched off, a flag "invoiced" lets the user tick it off when the invoice was written with other software.

When a project counts as invoiced
---------------------------------
* Invoices made in Rentalars (DOK-014 on): it has an invoice that is not
  cancelled – the whole project, which bills its parts (PRJ-046). DOK-016
: a monthly invoice of service cases bills every case of its
  statement (``Document.billed_projects``), not only the case it belongs to;
  cancelled, it leaves them open again (:func:`invoices_of`).
* Invoices written in another program (DOK-014 off): somebody ticked
  "Rechnung gestellt" (``Project.invoice_status = issued``). The mark can be
  set with invoices on as well – for an invoice of the time before Rentalars.
* Either way "Keine Rechnung" (``not_needed``) ends the reminders of a
  project that is never invoiced: free of charge, billed with another one.

Which projects are reminded of (:func:`due_projects`)
-----------------------------------------------------
Whole projects (not parts) with a customer, not internal, in the status
"Abgeschlossen", closed at or after the cut-off
(``NotificationSettings.invoice_reminders_since`` – the closed projects of
the years before would otherwise all be reminded of at once), with something
to charge (a net total above 0), neither invoiced nor marked "no invoice".
With "service cases too" also done service cases with something to charge –
a case has no lines (PRJ-090), so that is work recorded on it: times or
expenses not rejected – and done after the setting
was last switched on (``NotificationSettings.invoice_cases_since``: without this every case done
earlier would be reminded of at once and every week after). The lists –
the filter "Rechnung offen" of the project list and "Noch zu schreibende
Rechnungen" on the start page – keep showing the older cases: they remind
nobody, and an open invoice is still open.

When (Einstellungen → Benachrichtigungen)
-----------------------------------------
Once a day at the time set (9:00 at first), on the minute timer of the tasks
like the shortage check (``run_jobs``): the first reminder that many days
after the project was closed (1 at first), then every few days (7 at first)
until the invoice is there – both counted in days of the local calendar. A project closed again after it was opened
starts anew. Each reminder goes to the project manager and to the person
named in the settings – only to those who may see prices (AUT-019): only
they can make the invoice or tick the mark.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.i18n import LocalText
from rentalars.documents.models import PART_BILLING, Document, DocumentKind
from rentalars.projects.models import CaseStatus, InvoiceMark, Project, ProjectKind, ProjectStatus

logger = logging.getLogger(__name__)


class InvoiceState:
    """What the head of a project and the lists say about its invoice (DOK-015)."""

    #: The project gets no invoice of its own: internal, a part, cancelled, or a service case – or it was closed
    #: And its invoice is not followed (``InvoiceMark.EARLIER``).
    NONE = ""
    #: Not invoiced yet.
    OPEN = "open"
    #: An invoice of Rentalars that is not cancelled, or "Rechnung gestellt" ticked.
    INVOICED = "invoiced"
    #: Marked "Keine Rechnung".
    NOT_NEEDED = "not_needed"


def _settings() -> Any:
    from rentalars.core.models import NotificationSettings

    return NotificationSettings.load()


def invoices_on() -> bool:
    """Whether invoices are made in Rentalars (DOK-014)."""
    from rentalars.documents.services import invoices_enabled

    return invoices_enabled()


def valid_invoices() -> QuerySet[Document]:
    """The invoices that are not cancelled and bill a whole project – not the advance and partial invoices.

    A project with an advance invoice only is not invoiced yet: its final invoice is still to come.
    """
    return Document.objects.filter(kind=DocumentKind.INVOICE, cancelled_by__isnull=True).exclude(
        billing_type__in=PART_BILLING
    )


def invoices_of(project: Project) -> QuerySet[Document]:
    """The valid invoices that bill a project: its own and – DOK-016 – a monthly invoice that bills it."""
    return valid_invoices().filter(Q(project=project) | Q(billed_projects=project)).distinct()


def invoiced_ids(project_ids: Iterable[int]) -> set[int]:
    """Which of these projects a valid invoice bills – its own or a monthly invoice (DOK-016); two queries."""
    ids = set(project_ids)
    if not ids:
        return set()
    own = set(valid_invoices().filter(project_id__in=ids).values_list("project_id", flat=True))
    billed = set(valid_invoices().filter(billed_projects__in=ids).values_list("billed_projects", flat=True))
    return (own | billed) & ids


def gets_invoice(project: Project, *, service_cases: bool | None = None) -> bool:
    """Whether a project is invoiced on its own: a whole project with a customer, not internal, not cancelled.

    A service case only with the setting "service cases too" (``service_cases``; read when not given).
    """
    if project.parent_id or project.is_internal or not project.customer_id:
        return False
    if project.is_service_case:
        wanted = _settings().invoice_service_cases if service_cases is None else service_cases
        return bool(wanted)
    return project.status != ProjectStatus.CANCELLED


def state_of(project: Project, *, has_invoice: bool | None = None) -> str:
    """The state of the invoice of a project (:class:`InvoiceState`); ``has_invoice`` saves the query if known."""
    if not gets_invoice(project):
        return InvoiceState.NONE
    if project.invoice_status == InvoiceMark.NOT_NEEDED:
        return InvoiceState.NOT_NEEDED
    if project.invoice_status == InvoiceMark.ISSUED:
        return InvoiceState.INVOICED
    if has_invoice is None:
        has_invoice = invoices_of(project).exists()
    if has_invoice:
        return InvoiceState.INVOICED
    # Closed earlier (InvoiceMark.EARLIER): not followed – neither open nor invoiced.
    return InvoiceState.NONE if project.invoice_status == InvoiceMark.EARLIER else InvoiceState.OPEN


def is_finished(project: Project) -> bool:
    """Whether the work is done, so that the invoice is due: a project closed, a service case done."""
    if project.is_service_case:
        return project.case_status == CaseStatus.DONE
    return project.status == ProjectStatus.CLOSED


def finished_at(project: Project) -> datetime.datetime | None:
    """When the project was closed (the service case done): the time of change of its status (PRJ-113)."""
    if not is_finished(project):
        return None
    key = "case_status" if project.is_service_case else "status"
    moment = parse_datetime(str((project.field_changed_at or {}).get(key) or ""))
    return moment or project.created_at


def set_invoice_status(project: Project, status: str, *, user: Any = None) -> Project:
    """Tick "Rechnung gestellt", mark "Keine Rechnung" or open it again (DOK-015).

    Works on a closed project too: the mark is bookkeeping, not a change of
    the project (PRJ-009). The change log keeps who set it and when.

    Raises:
        ValidationError: Not a known mark, or a project that is not invoiced on its own.
    """
    if status not in (InvoiceMark.OPEN, InvoiceMark.ISSUED, InvoiceMark.NOT_NEEDED):
        # "earlier" is set by the update alone.
        raise ValidationError({"invoice_status": _("Unknown state of the invoice.")})
    if status and not gets_invoice(project):
        raise ValidationError(
            {"invoice_status": _("This project gets no invoice of its own: it is internal, a part or cancelled.")}
        )
    if project.invoice_status != status:
        project.invoice_status = status
        project.save(update_fields=["invoice_status"])
    if status:
        forget_reminders([project.pk])
    return project


def forget_reminders(project_ids: Iterable[int]) -> None:
    """Remove the reminder bookkeeping of projects that need no further reminder."""
    from rentalars.notifications.models import InvoiceNotice

    InvoiceNotice.objects.filter(project_id__in=list(project_ids)).delete()


# --- Which projects are open ------------------------------------------------------------------------------


def open_condition(*, service_cases: bool = False, enabled: bool | None = None) -> Q:
    """The projects whose invoice is open, as a condition for a query (the list's filter, the start page).

    Whole projects with a customer, not internal, closed – with "service
    cases too" also done service cases –, not marked, and with invoices made
    in Rentalars without a valid invoice. A net total of 0 is not looked at
    here; :func:`due_projects` leaves such projects out of the reminders.
    """
    finished = Q(kind=ProjectKind.PROJECT, status=ProjectStatus.CLOSED)
    if service_cases:
        finished |= Q(kind=ProjectKind.SERVICE_CASE, case_status=CaseStatus.DONE)
    condition = (
        finished
        & Q(parent__isnull=True, is_internal=False, customer__isnull=False)
        & Q(invoice_status=InvoiceMark.OPEN)
    )
    if invoices_on() if enabled is None else enabled:
        condition &= ~Exists(valid_invoices().filter(project_id=OuterRef("pk")))
        # DOK-016: a case billed by a monthly invoice of service cases.
        condition &= ~Exists(valid_invoices().filter(billed_projects=OuterRef("pk")))
    return condition


def open_projects(queryset: QuerySet[Project] | None = None) -> QuerySet[Project]:
    """The projects whose invoice is still open – as the settings say about service cases."""
    projects = Project.objects.all() if queryset is None else queryset
    return projects.filter(open_condition(service_cases=_settings().invoice_service_cases))


def with_invoice_numbers(queryset: QuerySet[Project]) -> QuerySet[Project]:
    """The projects with ``invoice_number``: the number of their valid invoice, if any – one subquery.

    DOK-016: also a monthly invoice that bills a service case.
    """
    from django.db.models import Subquery

    newest = (
        valid_invoices()
        .filter(Q(project_id=OuterRef("pk")) | Q(billed_projects=OuterRef("pk")))
        .order_by("-created_at")
        .values("number")[:1]
    )
    return queryset.annotate(invoice_number=Subquery(newest))


def _net_totals(projects: list[Project]) -> dict[int, Any]:
    """The net total of each project – what there is to charge – calculated as the project list does (PRJ-085)."""
    from rentalars.projects.list_sums import _prices_of

    if not projects:
        return {}
    return {pk: prices.net_total for pk, (prices, _hours) in _prices_of(projects).items()}


def due_projects(now: datetime.datetime | None = None) -> list[Project]:
    """The projects to remind of now: open, closed long enough ago, not reminded of for long enough (DOK-015).

    Not those closed before ``invoice_reminders_since``, nor service cases done before
    ``invoice_cases_since``.
    """
    from rentalars.notifications.models import InvoiceNotice

    now = now or timezone.now()
    settings_row = _settings()
    since = settings_row.invoice_reminders_since
    # Review: service cases only once done after "service cases too" was switched on.
    cases_since = settings_row.invoice_cases_since
    candidates = list(open_projects().select_related("manager", "customer").order_by("number", "pk"))
    notices = {notice.project_id: notice for notice in InvoiceNotice.objects.filter(project__in=candidates)}
    first = datetime.timedelta(days=settings_row.invoice_first_days)
    every = datetime.timedelta(days=settings_row.invoice_every_days)
    today = timezone.localdate(now)
    due = []
    for project in candidates:
        finished = finished_at(project)
        if finished is None or (since is not None and finished < since):
            continue
        if project.is_service_case and cases_since is not None and finished < cases_since:
            continue
        notice = notices.get(project.pk)
        if notice is not None and notice.first_reminded_at < finished:
            # Closed again after it was opened: the reminders start anew.
            notice.delete()
            notice = None
        if notice is None:
            # Counted in days of the calendar: the check runs once a day at its time, so
            # "a day after" a project closed at 17:00 is the next morning's check, not the one after it.
            if today < timezone.localtime(finished).date() + first:
                continue
        elif today < timezone.localdate(notice.last_reminded_at) + every:
            # Days of the calendar as well (as ZEI-029): counted in hours, the week across the change
            # to summer time, a reminder made up late or a check that started late would skip a day.
            continue
        due.append(project)
    totals = _net_totals([project for project in due if not project.is_service_case])
    worked = _cases_with_work([project.pk for project in due if project.is_service_case])
    return [
        project
        for project in due
        if (project.pk in worked if project.is_service_case else totals.get(project.pk, 0) > 0)
    ]


def _cases_with_work(case_ids: list[int]) -> set[int]:
    """The service cases with something to charge: times or expenses recorded on them and not rejected."""
    from rentalars.timetracking.models import Expense, TimeEntry, TimeEntryStatus

    if not case_ids:
        return set()
    found = set(
        TimeEntry.objects.filter(project_id__in=case_ids)
        .exclude(status=TimeEntryStatus.REJECTED)
        .values_list("project_id", flat=True)
    )
    found |= set(
        Expense.objects.filter(project_id__in=case_ids)
        .exclude(status=TimeEntryStatus.REJECTED)
        .values_list("project_id", flat=True)
    )
    return found


def recipients_of(project: Project) -> list[Any]:
    """Who is reminded of a project: its manager and the person of the settings.

    Only who may see prices and read the project – a reminder names the
    project (a person of the settings limited to
    assigned projects is not told about the others).
    """
    from rentalars.accounts.rights import SpecialRight, rights_of
    from rentalars.projects.access import ProjectAccess, access_level

    settings_row = _settings()
    people = [project.manager if project.manager_id else None, settings_row.invoice_user]
    found = []
    for user in people:
        if user is None or not user.is_active or user in found:
            continue
        rights = rights_of(user)
        if rights.has(SpecialRight.PRICES) and access_level(rights, user, project) >= ProjectAccess.READ:
            found.append(user)
    return found


def target_url(project: Project) -> str:
    """Where a reminder leads: "Rechnung erstellen" with invoices made here, else the project with the tick box."""
    if invoices_on():
        return f"{reverse('documents:list', args=[project.pk])}?kind={DocumentKind.INVOICE}#make-document"
    if project.is_service_case:
        return reverse("projects:case_detail", args=[project.pk])
    return reverse("projects:overview", args=[project.pk])


def remind(project: Project, *, now: datetime.datetime | None = None) -> int:
    """Remind of one project now; returns how many people were told."""
    from rentalars.core.i18n import LazyCall, format_date
    from rentalars.notifications.models import InvoiceNotice, Kind
    from rentalars.notifications.services import notify

    now = now or timezone.now()
    users = recipients_of(project)
    finished = finished_at(project) or now
    notice, created = InvoiceNotice.objects.get_or_create(
        project=project, defaults={"first_reminded_at": now, "last_reminded_at": now, "count": 1}
    )
    if not created:
        notice.last_reminded_at = now
        notice.count += 1
        notice.save(update_fields=["last_reminded_at", "count"])
    if not users:
        logger.info("Nobody to remind of the invoice of %s.", project.number)
        return 0
    if invoices_on():
        body = LocalText(
            gettext_lazy("Closed on %(date)s. Make the invoice in Rentalars – or mark the project “No invoice”."),
            date=LazyCall(format_date, timezone.localtime(finished), "d.m.Y"),
        )
    else:
        body = LocalText(
            gettext_lazy(
                "Closed on %(date)s. Once the invoice is written in your accounting program, tick “Invoice issued” "
                "in the project – or mark it “No invoice”."
            ),
            date=LazyCall(format_date, timezone.localtime(finished), "d.m.Y"),
        )
    notify(
        users,
        Kind.INVOICE_REMINDER,
        LocalText(
            gettext_lazy("Invoice still to be written: %(number)s %(name)s"), number=project.number, name=project.name
        ),
        body=body,
        url=target_url(project),
        project=project,
    )
    return len(users)


def latest_slot(time_of_day: datetime.time, now: datetime.datetime) -> datetime.datetime:
    """The latest moment at or before ``now`` at the time of day of the reminders."""
    local = timezone.localtime(now)
    day = local.date() if local.time() >= time_of_day else local.date() - datetime.timedelta(days=1)
    return timezone.make_aware(datetime.datetime.combine(day, time_of_day))


def next_run(now: datetime.datetime | None = None) -> datetime.datetime | None:
    """When the reminders are looked at next, for the settings page; ``None`` while they are switched off."""
    settings_row = _settings()
    if not settings_row.invoice_reminders:
        return None
    now = now or timezone.now()
    slot = latest_slot(settings_row.invoice_time, now)
    last = settings_row.invoice_last_run
    if last is not None and last < slot:
        return now
    return slot + datetime.timedelta(days=1)


def run_due_invoice_reminders(now: datetime.datetime | None = None) -> int | None:
    """Remind of open invoices once a day at the time set; called every minute by ``run_jobs`` (DOK-015).

    As the shortage check (VFG-036): the first minute after the update or the
    installation only notes its time; a run missed while the server was off is
    made up once; of two runs at the same time only one reminds (the last run
    is claimed by an update before). In the quiet minutes this costs one query.

    Returns:
        How many projects were reminded of, ``None`` if nothing was due.
    """
    from rentalars.core.models import NotificationSettings

    now = now or timezone.now()
    settings_row = NotificationSettings.load()
    if not settings_row.invoice_reminders:
        return None
    rows = NotificationSettings.objects.filter(pk=1)
    last = settings_row.invoice_last_run
    if last is None:
        rows.filter(invoice_last_run__isnull=True).update(invoice_last_run=now)
        if settings_row.invoice_reminders_since is None:
            rows.filter(invoice_reminders_since__isnull=True).update(invoice_reminders_since=now)
        return None
    slot = latest_slot(settings_row.invoice_time, now)
    if last >= slot:
        return None
    if not rows.filter(invoice_last_run__lt=slot).update(invoice_last_run=now):
        return None
    reminded = 0
    for project in due_projects(now):
        try:
            remind(project, now=now)
            reminded += 1
        except Exception:
            logger.exception("The invoice of %s could not be reminded of.", project.number)
    rows.update(invoice_checked_at=now, invoice_reminded=reminded)
    return reminded
