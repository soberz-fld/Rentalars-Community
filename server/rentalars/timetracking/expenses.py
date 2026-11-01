# SPDX-License-Identifier: GPL-3.0-or-later
"""Expenses and travel costs per project: recording, approval, reimbursement, report (ZEI-019).

Browser views and API views both call these functions (API-002).

What an expense is
------------------
Money a person spent for a project – meals (Verpflegung), a trip (Fahrt),
a night (Übernachtung), parking or tolls (Parken/Maut), something else
(Sonstiges) – with day, amount, note and a photo of the receipt. A trip
with the own car is entered as kilometres: the amount is kilometres × the
rate per kilometre of the settings (``SystemSettings.expense_km_rate``,
0.30 €), copied into the expense when it is recorded, like the hourly rate
into a time entry (ZEI-008).

The way to work (ZEI-027): a person with a distance home – company
(``Person.commute_km``) has twice that distance deducted once per project
and day from the trips by kilometre (:func:`commute_deduction`); the trip
keeps what was deducted (``Expense.commute_km``) and shows the calculation
("42 km − 28 km Arbeitsweg = 14 km"). A setting switches it off; trips
recorded before keep their amount.

Who may do what – as for times
------------------------------
* **Record own expenses** – everybody with write access to "time tracking"
  whose account is a person, on projects they are planned in, internal
  projects (ZEI-010) and projects they may see.
* **Record for others, approve, send back, mark as reimbursed** – with the
  special right "approve times and record them for others" (ZEI-011,
  ZEI-013), for the projects the user may see.
* **See** – one's own expenses always; those of others with the special
  right, in the projects the user may see. The amounts of expenses are no
  rates: whoever sees an expense sees its amount. The sum of a project in
  its prices needs the right for personnel costs (AUT-019, see
  ``projects.pricing``).

The life of an expense is that of a time entry (ZEI-012): recorded →
submitted → approved (locked) or rejected. Only approved expenses are
costs of the project (PRJ-025). Once the money is paid out, the office
marks them as reimbursed: they stay approved and are locked for good; a
mistaken mark can be taken back.

Receipts
--------
A photo (JPEG or PNG) or a PDF, up to the upload limit of the settings
(NFA-007). Photos are turned upright, reduced to 2,000 pixels on the long
side and stored as JPEG without their metadata – a photo from a phone
otherwise carries the place it was taken. A PDF is stored as it came, after
checking that it is one.
"""

from __future__ import annotations

import datetime
import io
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import DecimalField, OuterRef, Q, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Module, Rights, SpecialRight
from rentalars.core.i18n import for_user, local_pattern
from rentalars.core.money import ZERO, format_money, money
from rentalars.core.photos import PhotoError, render_photo_upload
from rentalars.core.uploads import max_upload_bytes
from rentalars.personnel.models import Person
from rentalars.projects.access import person_of
from rentalars.projects.models import Project, ProjectStatus
from rentalars.timetracking.models import Expense, ExpenseKind, TimeEntryStatus
from rentalars.timetracking.services import (
    _may_book_on,
    manageable_projects,
    may_manage,
    may_record_for,
)

#: Fields of an expense a caller may change through :func:`update_expense`.
EDITABLE_FIELDS = frozenset({"project", "kind", "date", "amount", "kilometres", "note"})

#: Photos of receipts are reduced to this many pixels on their long side.
RECEIPT_LONGEST_SIDE = 2000

#: The image formats a receipt may have; HEIC and the like arrive as JPEG from the browsers of phones.
RECEIPT_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "MPO"})


# --- Rights -----------------------------------------------------------------------------


def visible_expenses(rights: Rights, user: Any) -> QuerySet[Expense]:
    """The expenses a user may see (NFA-010, ZEI-016): one's own, and with the right to approve those of others."""
    expenses = Expense.objects.all()
    if not rights.can_read(Module.TIME_TRACKING):
        return expenses.none()
    own = person_of(user)
    mine = Q(person=own) if own is not None else Q(pk__in=[])
    if rights.has(SpecialRight.APPROVE_TIMES):
        return expenses.filter(mine | Q(project__in=manageable_projects(rights, user).values("pk")))
    return expenses.filter(mine) if own is not None else expenses.none()


def _require_manager(expenses: list[Expense], rights: Rights, user: Any) -> None:
    """Approving, sending back and reimbursing need the special right and sight of the project (ZEI-013)."""
    if not may_manage(rights):
        raise PermissionDenied
    allowed = set(
        manageable_projects(rights, user)
        .filter(pk__in={expense.project_id for expense in expenses})
        .values_list("pk", flat=True)
    )
    if any(expense.project_id not in allowed for expense in expenses):
        raise PermissionDenied


# --- Receipts ---------------------------------------------------------------------------------


def prepare_receipt(uploaded: Any) -> tuple[ContentFile, str]:
    """Check a receipt and return what is stored: ``(content, file name)`` (NFA-007).

    Raises:
        ValidationError: Neither a photo nor a PDF, or larger than the upload limit.
    """
    size = getattr(uploaded, "size", 0) or 0
    limit = max_upload_bytes()
    if size > limit:
        raise ValidationError(
            {"receipt": _("The file is too large (at most %(megabytes)d MB).") % {"megabytes": limit // 1048576}}
        )
    uploaded.seek(0)
    head = uploaded.read(5)
    uploaded.seek(0)
    if head == b"%PDF-":
        return ContentFile(uploaded.read()), "beleg.pdf"
    wrong = _("A receipt is a photo (JPEG or PNG) or a PDF file.")
    try:
        # Made anew like every photo (limits of the pixels, colour profile, transparent areas) – with the
        # place, without the device, the time and the rest.
        rendered = render_photo_upload(
            uploaded,
            size=size,
            max_bytes=limit,
            not_a_photo=wrong,
            longest_side=RECEIPT_LONGEST_SIDE,
            formats=RECEIPT_IMAGE_FORMATS,
        )
    except PhotoError as error:
        message = str(error)
        raise ValidationError({"receipt": wrong if "accepted as" in message else message}) from error
    finally:
        uploaded.seek(0)
    return ContentFile(rendered.photo), "beleg.jpg"


def _store_receipt(expense: Expense, uploaded: Any) -> str:
    """Put a checked receipt on the expense (not saved yet); returns the name of the file it replaces."""
    content, name = prepare_receipt(uploaded)
    old = expense.receipt.name if expense.receipt else ""
    expense.receipt.save(name, content, save=False)
    return old


def _remove_file_later(name: str) -> None:
    """Delete a stored receipt once the change that dropped it is committed."""
    if not name:
        return
    storage = Expense._meta.get_field("receipt").storage

    def remove() -> None:
        if storage.exists(name):
            storage.delete(name)

    transaction.on_commit(remove)


def receipt_download_name(expense: Expense) -> str:
    """The name a receipt is shown or saved under: ``Beleg-2027-03-10-17.jpg``."""
    extension = Path(expense.receipt.name).suffix.lower() or ".jpg"
    return f"Beleg-{expense.date:%Y-%m-%d}-{expense.pk}{extension}"


# --- Recording ----------------------------------------------------------------------------------


def _check_project(person: Person, project: Project, rights: Rights, user: Any) -> None:
    """An expense is booked like a time: on a project the person is planned in, an internal one, or a visible one."""
    if project.is_locked or project.status == ProjectStatus.CANCELLED:
        raise ValidationError({"project": _("Expenses cannot be booked on a closed or cancelled project.")})
    if not _may_book_on(person, project, rights, user):
        raise ValidationError({"project": _("%(person)s is not scheduled for this project.") % {"person": person}})


def _check_date(day: datetime.date | None) -> None:
    """Expenses are recorded once they were spent (as times, ZEI-022)."""
    if day is not None and day > timezone.localdate():
        raise ValidationError(
            {"date": _("The day lies in the future. Expenses are recorded once the money was spent.")}
        )


def _km_rate() -> Decimal:
    from rentalars.core.models import SystemSettings

    return SystemSettings.load().expense_km_rate


def commute_deduction(
    person: Person,
    project_id: int | None,
    day: datetime.date | None,
    kilometres: Decimal | None,
    *,
    exclude_pk: int | None = None,
) -> Decimal | None:
    """The kilometres of the way to work a trip by kilometre has deducted (ZEI-027).

    Twice the distance home – company of the person (there and back) is
    deducted once per person, project and day: from the first trip of the
    day as far as it goes, the rest from the next ones. What the other
    trips of that day already had deducted is fixed on them; a trip that
    is changed is calculated again without itself (``exclude_pk``).

    Returns:
        The kilometres to deduct, or ``None``: no distance entered for the
        person, the deduction switched off in the settings, no kilometres,
        or nothing left of the day's way to work.
    """
    from rentalars.core.models import SystemSettings

    if kilometres is None or not person.commute_km or project_id is None or day is None:
        return None
    if not SystemSettings.load().expense_deduct_commute:
        return None
    others = Expense.objects.filter(
        person=person, project_id=project_id, date=day, kind=ExpenseKind.TRAVEL, commute_km__isnull=False
    )
    if exclude_pk is not None:
        others = others.exclude(pk=exclude_pk)
    used = others.aggregate(total=Sum("commute_km"))["total"] or Decimal("0")
    left = person.commute_km * 2 - used
    if left <= 0:
        return None
    return min(kilometres, left)


@transaction.atomic
def create_expense(
    *,
    person: Person,
    project: Project,
    kind: str,
    date: datetime.date,
    rights: Rights,
    user: Any,
    amount: Decimal | None = None,
    kilometres: Decimal | None = None,
    note: str = "",
    receipt: Any = None,
    submit: bool = False,
) -> Expense:
    """Record an expense of a person for a project (ZEI-019).

    Args:
        person: Who spent the money.
        project: For which project.
        kind: One of :class:`ExpenseKind`.
        date: The day it was spent; not in the future.
        rights: The rights of the caller.
        user: The caller.
        amount: The amount; for a trip with kilometres it is calculated.
        kilometres: For a trip with the own car.
        note: What it was, e.g. "Lager – Stadthalle und zurück".
        receipt: An uploaded file, a photo or a PDF.
        submit: Hand it in for approval right away.

    Raises:
        PermissionDenied: The caller may not record for this person.
        ValidationError: Something does not fit; the message names the field.
    """
    if not may_record_for(rights, user, person):
        raise PermissionDenied
    if not person.is_active:
        raise ValidationError({"person": _("%(person)s is deactivated.") % {"person": person}})
    _check_project(person, project, rights, user)
    _check_date(date)
    expense = Expense(
        person=person,
        project=project,
        kind=kind,
        date=date,
        amount=amount,
        kilometres=kilometres if kind == ExpenseKind.TRAVEL else None,
        km_rate=_km_rate() if kind == ExpenseKind.TRAVEL and kilometres is not None else None,
        note=(note or "").strip(),
    )
    if expense.is_by_kilometre:
        expense.commute_km = commute_deduction(person, project.pk, date, kilometres)  # ZEI-027
    expense.apply_kind()
    expense.full_clean()
    if receipt:
        _store_receipt(expense, receipt)
    if submit:
        expense.status = TimeEntryStatus.SUBMITTED
        expense.submitted_at = timezone.now()
    expense.save()
    return expense


@transaction.atomic
def update_expense(
    expense: Expense,
    *,
    rights: Rights,
    user: Any,
    receipt: Any = None,
    remove_receipt: bool = False,
    **changes: Any,
) -> Expense:
    """Change an expense that is not approved yet (ZEI-012, ZEI-014).

    Changing a sent-back expense puts it back to "recorded": it has to be
    handed in again. A trip keeps the rate per kilometre it was recorded
    with; a trip entered anew with kilometres takes the current one.

    Raises:
        PermissionDenied: The caller may not record for this person.
        ValidationError: The expense is approved, or a value does not fit.
    """
    if not may_record_for(rights, user, expense.person):
        raise PermissionDenied
    if not expense.is_editable:
        raise ValidationError(_("Approved expenses are locked. Somebody who approves can take the approval back."))
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    if "project" in changes and changes["project"].pk != expense.project_id:
        _check_project(expense.person, changes["project"], rights, user)
    # ZEI-027: what the way to work deducts depends on these; an unchanged trip keeps its deduction.
    trip_before = (expense.project_id, expense.kind, expense.date, expense.kilometres)
    for name, value in changes.items():
        setattr(expense, name, value)
    if "date" in changes:
        _check_date(expense.date)
    if expense.kind == ExpenseKind.TRAVEL and expense.kilometres is not None and expense.km_rate is None:
        expense.km_rate = _km_rate()
    if (expense.project_id, expense.kind, expense.date, expense.kilometres) != trip_before:
        expense.commute_km = (
            commute_deduction(
                expense.person, expense.project_id, expense.date, expense.kilometres, exclude_pk=expense.pk
            )
            if expense.is_by_kilometre
            else None
        )
    expense.apply_kind()
    expense.full_clean()
    dropped = ""
    if receipt:
        dropped = _store_receipt(expense, receipt)
    elif remove_receipt and expense.receipt:
        dropped = expense.receipt.name
        expense.receipt = ""
    if expense.status == TimeEntryStatus.REJECTED:
        expense.status = TimeEntryStatus.RECORDED
        expense.decided_at = None
        expense.decided_by = None
    expense.save()
    _remove_file_later(dropped)
    return expense


def delete_expense(expense: Expense, *, rights: Rights, user: Any) -> None:
    """Delete an expense that is not approved yet, with its receipt; the change log keeps what it said.

    Raises:
        PermissionDenied: The caller may not record for this person.
        ValidationError: The expense is approved.
    """
    if not may_record_for(rights, user, expense.person):
        raise PermissionDenied
    if not expense.is_editable:
        raise ValidationError(_("Approved expenses are locked and cannot be deleted."))
    with transaction.atomic():
        name = expense.receipt.name if expense.receipt else ""
        expense.delete()
        _remove_file_later(name)


# --- Approval and reimbursement (as ZEI-012, ZEI-013) ----------------------------------------------


def submit_expenses(expenses: list[Expense], *, rights: Rights, user: Any) -> int:
    """Hand expenses in for approval; returns how many changed.

    Raises:
        PermissionDenied: One of them belongs to somebody the caller may not record for.
    """
    changed = 0
    for expense in expenses:
        if not may_record_for(rights, user, expense.person):
            raise PermissionDenied
        if expense.status not in {TimeEntryStatus.RECORDED, TimeEntryStatus.REJECTED}:
            continue
        expense.status = TimeEntryStatus.SUBMITTED
        expense.submitted_at = timezone.now()
        expense.rejection_reason = ""
        expense.save()
        changed += 1
    return changed


@transaction.atomic
def approve_expenses(expenses: list[Expense], *, rights: Rights, user: Any) -> int:
    """Approve submitted expenses (ZEI-013); from now on they are costs of their project (PRJ-025).

    Raises:
        PermissionDenied: The caller lacks the right, or cannot see one of the projects.
    """
    _require_manager(expenses, rights, user)
    changed = 0
    for expense in expenses:
        if expense.status != TimeEntryStatus.SUBMITTED:
            continue
        expense.status = TimeEntryStatus.APPROVED
        expense.decided_at = timezone.now()
        expense.decided_by = user if getattr(user, "pk", None) else None
        expense.save()
        changed += 1
    return changed


def _notify(expenses: list[Expense], what: str, body: str, *, actor: Any) -> None:
    """Tell the people of some expenses that they were sent back or reimbursed (UIX-005)."""
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    by_person: dict[int, list[Expense]] = defaultdict(list)
    for expense in expenses:
        by_person[expense.person_id].append(expense)
    for own in by_person.values():
        person = own[0].person
        user = getattr(person, "user", None)
        # UIX-029: written in the person's language, the amount in its format.
        with for_user(user):
            values = {"count": len(own), "amount": format_money(sum((expense.amount for expense in own), ZERO))}
            if what == "rejected":
                title = ngettext(
                    "%(count)d expense sent back (%(amount)s)", "%(count)d expenses sent back (%(amount)s)", len(own)
                )
            else:
                title = ngettext(
                    "%(count)d expense reimbursed (%(amount)s)", "%(count)d expenses reimbursed (%(amount)s)", len(own)
                )
            title = title % values
        notify(
            [user],
            Kind.EXPENSE,
            title,
            body=body,
            url=reverse("timetracking:my_expenses"),
            exclude=actor if getattr(actor, "pk", None) else None,
        )


@transaction.atomic
def reject_expenses(expenses: list[Expense], reason: str, *, rights: Rights, user: Any) -> int:
    """Send submitted expenses back with a reason; the person is told (ZEI-012, UIX-005).

    Raises:
        PermissionDenied: As for :func:`approve_expenses`.
        ValidationError: No reason was given.
    """
    _require_manager(expenses, rights, user)
    if not reason.strip():
        raise ValidationError({"reason": _("Say why the expenses are sent back, so that they can be corrected.")})
    changed = []
    for expense in expenses:
        if expense.status != TimeEntryStatus.SUBMITTED:
            continue
        expense.status = TimeEntryStatus.REJECTED
        expense.rejection_reason = reason.strip()[:250]
        expense.decided_at = timezone.now()
        expense.decided_by = user if getattr(user, "pk", None) else None
        expense.save()
        changed.append(expense)
    if changed:
        _notify(changed, "rejected", reason.strip(), actor=user)
    return len(changed)


@transaction.atomic
def take_back_approval(expense: Expense, *, rights: Rights, user: Any) -> None:
    """Unlock an approved expense that is not reimbursed: it is "submitted" again.

    Raises:
        PermissionDenied: As for :func:`approve_expenses`.
        ValidationError: The expense is not approved, already reimbursed, or
            billed by an invoiced or marked monthly statement (DOK-016).
    """
    _require_manager([expense], rights, user)
    if expense.status != TimeEntryStatus.APPROVED:
        raise ValidationError(_("Only approved expenses can be unlocked."))
    if expense.is_reimbursed:
        raise ValidationError(_("The expense is reimbursed. Take back the reimbursement first."))
    from rentalars.documents.statements import check_not_billed

    check_not_billed(expenses=[expense])  # DOK-016: billed by a monthly statement
    expense.status = TimeEntryStatus.SUBMITTED
    expense.decided_at = None
    expense.decided_by = None
    expense.save()


@transaction.atomic
def mark_reimbursed(expenses: list[Expense], *, rights: Rights, user: Any, on: datetime.date | None = None) -> int:
    """Mark approved expenses as paid out to the person; the person is told (ZEI-019).

    Expenses that are not approved, or reimbursed already, are left alone.

    Raises:
        PermissionDenied: As for :func:`approve_expenses`.
        ValidationError: The day lies in the future.
    """
    _require_manager(expenses, rights, user)
    day = on or timezone.localdate()
    if day > timezone.localdate():
        raise ValidationError({"date": _("The day of the reimbursement lies in the future.")})
    changed = []
    for expense in expenses:
        if expense.status != TimeEntryStatus.APPROVED or expense.is_reimbursed:
            continue
        expense.reimbursed_on = day
        expense.reimbursed_by = user if getattr(user, "pk", None) else None
        expense.save()
        changed.append(expense)
    if changed:
        _notify(changed, "reimbursed", "", actor=user)
    return len(changed)


@transaction.atomic
def take_back_reimbursement(expense: Expense, *, rights: Rights, user: Any) -> None:
    """Take back a mark "reimbursed" set by mistake; the expense stays approved.

    Raises:
        PermissionDenied: As for :func:`approve_expenses`.
        ValidationError: The expense is not reimbursed.
    """
    _require_manager([expense], rights, user)
    if not expense.is_reimbursed:
        raise ValidationError(_("The expense is not marked as reimbursed."))
    expense.reimbursed_on = None
    expense.reimbursed_by = None
    expense.save()


# --- Report: per month and person (ZEI-019) ------------------------------------------------------


@dataclass
class ExpenseRow:
    """The expenses of one person in one month, with their sums."""

    month: datetime.date
    person: Person
    expenses: list[Expense] = field(default_factory=list)
    total: Decimal = ZERO
    reimbursed: Decimal = ZERO
    #: Sum per kind, in the order of :class:`ExpenseKind`.
    by_kind: dict[str, Decimal] = field(default_factory=dict)

    @property
    def outstanding(self) -> Decimal:
        """Approved and not reimbursed yet."""
        return sum(
            (
                expense.amount
                for expense in self.expenses
                if expense.status == TimeEntryStatus.APPROVED and not expense.is_reimbursed
            ),
            ZERO,
        )


@dataclass
class ExpenseReport:
    """Expenses by month and person, with sums (ZEI-019)."""

    rows: list[ExpenseRow]
    expenses: list[Expense]
    total: Decimal
    reimbursed: Decimal
    outstanding: Decimal
    #: ``(name of the kind, sum)`` in the order of :class:`ExpenseKind`, only kinds that occur.
    by_kind: list[tuple[str, Decimal]]


def expense_report(expenses: QuerySet[Expense]) -> ExpenseReport:
    """Add up expenses per month and person (ZEI-019).

    Args:
        expenses: The expenses to report on, already narrowed to what the
            reader may see (:func:`visible_expenses`) and to the filter.
    """
    listed = list(expenses.select_related("person", "project__parent").order_by("date", "id"))
    rows: dict[tuple[datetime.date, int], ExpenseRow] = {}
    by_kind: dict[str, Decimal] = {}
    for expense in listed:
        month = expense.date.replace(day=1)
        row = rows.setdefault((month, expense.person_id), ExpenseRow(month=month, person=expense.person))
        row.expenses.append(expense)
        row.total += expense.amount
        row.by_kind[expense.kind] = row.by_kind.get(expense.kind, ZERO) + expense.amount
        by_kind[expense.kind] = by_kind.get(expense.kind, ZERO) + expense.amount
        if expense.is_reimbursed:
            row.reimbursed += expense.amount
    ordered = sorted(rows.values(), key=lambda row: (row.month, row.person.sort_name.lower()))
    return ExpenseReport(
        rows=ordered,
        expenses=listed,
        total=money(sum((row.total for row in ordered), ZERO)),
        reimbursed=money(sum((row.reimbursed for row in ordered), ZERO)),
        outstanding=money(sum((row.outstanding for row in ordered), ZERO)),
        by_kind=[(str(kind.label), by_kind[kind.value]) for kind in ExpenseKind if kind.value in by_kind],
    )


def expenses_csv(report: ExpenseReport) -> str:
    """The expenses of a report as CSV text, one row per expense, sorted by month and person (ZEI-019).

    Semicolons and decimal commas, as German spreadsheet programs expect
    them, like the hours report (ZEI-017).
    """
    import csv

    from rentalars.core.money import format_decimal
    from rentalars.timetracking.export import BYTE_ORDER_MARK

    text = io.StringIO()
    text.write(BYTE_ORDER_MARK)
    writer = csv.writer(text, delimiter=";")
    writer.writerow(
        [
            _("Month"),
            _("Person"),
            _("Project number"),
            _("Project"),
            _("Day"),
            _("Kind"),
            _("Kilometres"),
            _("Way to work deducted (km)"),  # ZEI-027
            _("Rate per kilometre"),
            _("Amount"),
            _("Note"),
            _("Receipt"),
            _("Status"),
            _("Reimbursed on"),
        ]
    )
    for row in report.rows:
        for expense in row.expenses:
            writer.writerow(
                [
                    f"{row.month:%m/%Y}",
                    expense.person.sort_name,
                    expense.project.number,
                    expense.project.name,
                    f"{expense.date:{local_pattern('%d.%m.%Y')}}",
                    expense.get_kind_display(),
                    format_decimal(expense.kilometres, max_places=1) if expense.kilometres is not None else "",
                    format_decimal(expense.commute_km, max_places=1) if expense.commute_km else "",
                    format_money(expense.km_rate, currency="").strip() if expense.km_rate is not None else "",
                    format_money(expense.amount, currency="").strip(),
                    expense.note,
                    _("yes") if expense.receipt else _("no"),
                    expense.status_label,
                    f"{expense.reimbursed_on:{local_pattern('%d.%m.%Y')}}" if expense.reimbursed_on else "",
                ]
            )
    return text.getvalue()


# --- Costs of projects (PRJ-025) ------------------------------------------------------------------


def approved_expense_sums(project_ids: set[int] | list[int]) -> dict[int, Decimal]:
    """The approved expenses of some projects, by project ID – one query (ZEI-019, PRJ-025, PRJ-085)."""
    if not project_ids:
        return {}
    return {
        row["project_id"]: money(row["total"] or ZERO)
        for row in Expense.objects.filter(project_id__in=list(project_ids), status=TimeEntryStatus.APPROVED)
        .values("project_id")
        .annotate(total=Sum("amount"))
    }


def approved_expenses_total() -> Coalesce:
    """The approved expenses of a project as an annotation of a project query (ZEI-019, PRJ-025).

    ``Project.objects.annotate(approved_expenses_total=approved_expenses_total())``
    brings the sum along with the project: the totals of the planning then
    need no query of their own (``ProjectPrices.expenses_cost``).
    """
    total = (
        Expense.objects.filter(project=OuterRef("pk"), status=TimeEntryStatus.APPROVED)
        .order_by()
        .values("project")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    amount = DecimalField(max_digits=14, decimal_places=2)
    return Coalesce(Subquery(total, output_field=amount), Value(ZERO), output_field=amount)


def counts_message(count: int, verb: str) -> str:
    """A message such as "3 expenses approved." for the pages."""
    messages = {
        "approved": ngettext("%(count)d expense approved.", "%(count)d expenses approved.", count),
        "rejected": ngettext("%(count)d expense sent back.", "%(count)d expenses sent back.", count),
        "submitted": ngettext(
            "%(count)d expense handed in for approval.", "%(count)d expenses handed in for approval.", count
        ),
        "reimbursed": ngettext(
            "%(count)d expense marked as reimbursed.", "%(count)d expenses marked as reimbursed.", count
        ),
    }
    return messages[verb] % {"count": count}
