# SPDX-License-Identifier: GPL-3.0-or-later
"""Payments on outgoing invoices and the open items (DOK-048).

What a customer still owes is *worked out*, never stored: the amount of the invoice – with the deduction of advance
invoices, as the final invoice stores it –, plus the credit notes and the cancellation (their amounts are negative),
minus the payments that were not voided. An invoice taken over from an old system (``Document.is_historic``) counts as
paid when the import knew it as paid and nobody entered a payment.

A payment is not changed and not deleted: a wrong one is voided with a reason and stays in the list.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, F, OuterRef, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.payment_base import MAX_AMOUNT, PaymentMethod
from rentalars.core.tax_split import ZERO, cents
from rentalars.documents.models import Document, DocumentKind, OutgoingPayment

# The states of an invoice in the books of the payments.
OPEN = "open"
PARTIAL = "partial"
PAID = "paid"
OVERPAID = "overpaid"
CANCELLED = "cancelled"
REFUND_DUE = "refund_due"

STATE_LABELS = {
    OPEN: _("open"),
    PARTIAL: _("partly paid"),
    PAID: _("paid"),
    OVERPAID: _("overpaid"),
    CANCELLED: _("cancelled"),
    REFUND_DUE: _("refund due"),
}


def state_label(state: str) -> str:
    """The state in words."""
    return str(STATE_LABELS.get(state, state))


@dataclass(frozen=True)
class Balance:
    """What an invoice demands, what was paid and what is left."""

    payable: Decimal
    paid: Decimal
    remaining: Decimal
    state: str
    due_on: datetime.date | None
    overdue: bool
    #: Counted as paid because the import of old projects knew it as paid (no payment was entered).
    imported_paid: bool = False

    @property
    def label(self) -> str:
        """The state in words."""
        return state_label(self.state)

    @property
    def needs_money(self) -> bool:
        """Whether the customer still owes something."""
        return self.remaining > 0


def state_for(payable: Decimal, paid: Decimal) -> str:
    """The state from the two amounts alone (no clock).

    A negative amount (a credit note of a supplier: the supplier owes us money) is read mirrored, so that "partly paid"
    and "overpaid" mean the same as for a positive amount.
    """
    if payable < 0:
        return state_for(-payable, -paid)
    remaining = payable - paid
    if payable == 0:
        if paid == 0:
            return CANCELLED
        return REFUND_DUE if paid > 0 else OVERPAID
    if remaining == 0:
        return PAID
    if remaining < 0:
        return OVERPAID
    return OPEN if paid == 0 else PARTIAL


def is_payable_kind(document: Document) -> bool:
    """Whether payments are entered at this document: an invoice with an amount."""
    return document.kind == DocumentKind.INVOICE and document.gross_total is not None


def credits_of(document: Document) -> Decimal:
    """The sum of the credit notes and of the cancellation of an invoice (negative amounts)."""
    total = ZERO
    for credit in document.partial_credits.all():
        total += credit.gross_total or ZERO
    cancellation = (
        document.cancelled_by
    )  # a cancellation names its invoice by ``cancels``, a credit note by ``credit_for``
    if cancellation is not None:
        total += cancellation.gross_total or ZERO
    return total


def payable_of(document: Document) -> Decimal:
    """What the invoice demands after credit notes and cancellation."""
    return cents((document.gross_total or ZERO) + credits_of(document))


def paid_of(document: Document) -> Decimal:
    """The payments that were not voided."""
    return cents(sum((p.amount for p in document.payments.all() if p.voided_at is None), ZERO))


def _legacy_paid(document: Document) -> tuple[bool, datetime.date | None]:
    item = getattr(document, "legacy_item", None)
    if item is None:
        return False, None
    return bool(item.paid), item.paid_on


def balance(document: Document, *, today: datetime.date | None = None) -> Balance:
    """The balance of one invoice."""
    today = today or timezone.localdate()
    payable = payable_of(document)
    paid = paid_of(document)
    imported = False
    if document.is_historic and paid == 0 and _legacy_paid(document)[0]:
        paid, imported = payable, True
    remaining = payable - paid
    state = state_for(payable, paid)
    return Balance(
        payable,
        paid,
        remaining,
        state,
        document.due_on,
        overdue=remaining > 0 and document.due_on is not None and document.due_on < today,
        imported_paid=imported,
    )


def check_amount(amount: Decimal | None) -> Decimal:
    """The amount of a payment: not zero, not beyond the field; rounded to cents."""
    if amount is None:
        raise ValidationError({"amount": _("Enter the amount.")})
    amount = cents(Decimal(amount))
    if amount == 0:
        raise ValidationError({"amount": _("A payment is not zero.")})
    if abs(amount) > MAX_AMOUNT:
        raise ValidationError({"amount": _("The amount is too large.")})
    return amount


def _check_day(day: datetime.date | None) -> datetime.date:
    if day is None:
        raise ValidationError({"paid_on": _("Enter the day of the payment.")})
    if day > timezone.localdate():
        raise ValidationError({"paid_on": _("The day of a payment is not in the future.")})
    return day


@transaction.atomic
def record(
    document: Document,
    *,
    paid_on: datetime.date | None,
    amount: Decimal | None,
    method: str = PaymentMethod.TRANSFER,
    reference: str = "",
    note: str = "",
    user: Any = None,
) -> OutgoingPayment:
    """Enter a payment of a customer at an invoice (DOK-048).

    Raises:
        ValidationError: The document is no invoice, the day lies in the future, the amount is zero or too large, or
            an old invoice of the import that counts as paid already.
    """
    document = Document.objects.select_for_update().get(pk=document.pk)
    if not is_payable_kind(document):
        raise ValidationError(_("Payments are entered at invoices."))
    paid_on = _check_day(paid_on)
    amount = check_amount(amount)
    if method not in PaymentMethod.values:
        raise ValidationError({"method": _("Unknown method of payment.")})
    if document.is_historic and balance(document).imported_paid:
        raise ValidationError(_("This invoice of the old system counts as paid; no payment is entered for it."))
    payment = OutgoingPayment(
        document=document,
        paid_on=paid_on,
        amount=amount,
        method=method,
        reference=reference.strip()[:200],
        note=note.strip()[:250],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    payment.full_clean(exclude=["document"])
    payment.save()
    record_event(
        document.project or document.customer or document,
        "payment.received",
        {"number": document.number, "amount": str(amount), "paid_on": paid_on.isoformat()},
    )
    return payment


@transaction.atomic
def void(payment: OutgoingPayment, *, reason: str, user: Any = None) -> OutgoingPayment:
    """Void a payment with a reason; it stays in the list but no longer counts.

    Raises:
        ValidationError: Without a reason, or voided already.
    """
    payment = OutgoingPayment.objects.select_for_update().select_related("document").get(pk=payment.pk)
    reason = reason.strip()
    if not reason:
        raise ValidationError({"void_reason": _("Say why the payment is voided.")})
    if payment.voided_at is not None:
        raise ValidationError(_("This payment is voided already."))
    payment.voided_at = timezone.now()
    payment.voided_by = user if getattr(user, "is_authenticated", False) else None
    payment.void_reason = reason[:250]
    payment.save()
    document = payment.document
    record_event(
        document.project or document.customer or document,
        "payment.voided",
        {"number": document.number, "amount": str(payment.amount)},
    )
    return payment


# --- The list of open items ------------------------------------------------------------------------------------


def with_balances() -> QuerySet[Document]:
    """The invoices with the amounts of their balance worked out in the database: ``payable``, ``paid_sum``."""
    paid = (
        OutgoingPayment.objects.filter(document=OuterRef("pk"), voided_at__isnull=True)
        .values("document")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    credits = (
        Document.objects.filter(credit_for=OuterRef("pk"))
        .values("credit_for")
        .annotate(total=Sum("gross_total"))
        .values("total")
    )
    decimal = DecimalField(max_digits=14, decimal_places=2)
    return (
        Document.objects.filter(kind=DocumentKind.INVOICE, gross_total__isnull=False)
        .annotate(
            credit_sum=Coalesce(Subquery(credits, output_field=decimal), Value(ZERO), output_field=decimal),
            cancel_sum=Coalesce(F("cancelled_by__gross_total"), Value(ZERO), output_field=decimal),
            paid_sum=Coalesce(Subquery(paid, output_field=decimal), Value(ZERO), output_field=decimal),
        )
        .annotate(payable=F("gross_total") + F("credit_sum") + F("cancel_sum"))
    )


def open_items(*, today: datetime.date | None = None) -> list[tuple[Document, Balance]]:
    """The invoices a customer still owes something for, oldest due day first (DOK-048).

    Invoices of the old system that the import knew as paid are not open; so is a cancelled one. An overpaid one is not
    open either – it is a refund due, which the page of the invoice shows.
    """
    today = today or timezone.localdate()
    rows = (
        with_balances()
        .filter(legacy_item__isnull=True)
        .filter(payable__gt=F("paid_sum"))
        .select_related("project", "customer")
        .order_by(F("due_on").asc(nulls_last=True), "number")
    )
    historic = (
        with_balances()
        .filter(legacy_item__paid=False, payable__gt=F("paid_sum"))
        .select_related("project", "customer")
        .order_by(F("due_on").asc(nulls_last=True), "number")
    )
    result: list[tuple[Document, Balance]] = []
    for document in [*rows, *historic]:
        payable, paid = cents(document.payable), cents(document.paid_sum)
        remaining = payable - paid
        result.append(
            (
                document,
                Balance(
                    payable,
                    paid,
                    remaining,
                    state_for(payable, paid),
                    document.due_on,
                    overdue=document.due_on is not None and document.due_on < today,
                ),
            )
        )
    result.sort(key=lambda row: (row[0].due_on is None, row[0].due_on or datetime.date.max, row[0].number))
    return result


def credit_items(*, today: datetime.date | None = None) -> list[tuple[Document, Balance]]:
    """The invoices that were paid more than they demand – what the company owes its customers back (DOK-053).

    An overpaid invoice, or one that was cancelled or credited after it was paid in full ("refund due"). The ``remaining``
    of such a balance is negative. An invoice of the old system is not listed: its payments are not in Rentalars.
    """
    today = today or timezone.localdate()
    rows = (
        with_balances()
        .filter(legacy_item__isnull=True, payable__lt=F("paid_sum"))
        .select_related("project", "customer")
        .order_by("number")
    )
    result: list[tuple[Document, Balance]] = []
    for document in rows:
        payable, paid = cents(document.payable), cents(document.paid_sum)
        result.append(
            (
                document,
                Balance(payable, paid, payable - paid, state_for(payable, paid), document.due_on, overdue=False),
            )
        )
    return result
