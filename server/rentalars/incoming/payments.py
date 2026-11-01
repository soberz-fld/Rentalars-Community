# SPDX-License-Identifier: GPL-3.0-or-later
"""Payments on incoming invoices (DOK-048): what is still to pay, and the payments made.

As for outgoing invoices (``documents.payments``) the rest is worked out, never stored. The amounts are those of the
invoice, in its currency; the euros follow by its exchange rate (``IncomingInvoice.rate``). A credit note of a supplier
has negative totals; a payment against it is the money received back and negative as well.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.payment_base import PaymentMethod
from rentalars.core.tax_split import ZERO, cents
from rentalars.documents.payments import _check_day, check_amount, state_for, state_label
from rentalars.incoming.models import IncomingInvoice, IncomingPayment


@dataclass(frozen=True)
class Balance:
    """What an incoming invoice demands, what was paid and what is left (in the currency of the invoice)."""

    payable: Decimal
    paid: Decimal
    remaining: Decimal
    state: str
    due_on: datetime.date | None
    overdue: bool

    @property
    def label(self) -> str:
        """The state in words."""
        return state_label(self.state)


def payable_of(invoice: IncomingInvoice) -> Decimal | None:
    """The gross total of the invoice; ``None`` while it is not entered."""
    return cents(invoice.total_gross) if invoice.total_gross is not None else None


def balance(invoice: IncomingInvoice, *, today: datetime.date | None = None) -> Balance | None:
    """The balance; ``None`` while the totals of the invoice are not known."""
    payable = payable_of(invoice)
    if payable is None:
        return None
    today = today or timezone.localdate()
    paid = cents(sum((p.amount for p in invoice.payments.all() if p.voided_at is None), ZERO))
    remaining = payable - paid
    return Balance(
        payable,
        paid,
        remaining,
        state_for(payable, paid),
        invoice.due_date,
        overdue=remaining > 0 and invoice.due_date is not None and invoice.due_date < today,
    )


@transaction.atomic
def record(
    invoice: IncomingInvoice,
    *,
    paid_on: datetime.date | None,
    amount: Decimal | None,
    method: str = PaymentMethod.TRANSFER,
    reference: str = "",
    note: str = "",
    user: Any = None,
) -> IncomingPayment:
    """Enter a payment to the supplier.

    Raises:
        ValidationError: The totals of the invoice are not entered, the day lies in the future, or the amount is
            zero or too large.
    """
    invoice = IncomingInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.total_gross is None:
        raise ValidationError(_("Enter the totals of the invoice first; a payment is compared with them."))
    paid_on = _check_day(paid_on)
    amount = check_amount(amount)
    if method not in PaymentMethod.values:
        raise ValidationError({"method": _("Unknown method of payment.")})
    payment = IncomingPayment(
        invoice=invoice,
        paid_on=paid_on,
        amount=amount,
        method=method,
        reference=reference.strip()[:200],
        note=note.strip()[:250],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    payment.full_clean(exclude=["invoice"])
    payment.save()
    record_event(
        invoice,
        "payment.made",
        {"number": invoice.invoice_number, "amount": str(amount), "paid_on": paid_on.isoformat()},
    )
    return payment


@transaction.atomic
def void(payment: IncomingPayment, *, reason: str, user: Any = None) -> IncomingPayment:
    """Void a payment with a reason; it stays in the list but no longer counts."""
    payment = IncomingPayment.objects.select_for_update().select_related("invoice").get(pk=payment.pk)
    reason = reason.strip()
    if not reason:
        raise ValidationError({"void_reason": _("Say why the payment is voided.")})
    if payment.voided_at is not None:
        raise ValidationError(_("This payment is voided already."))
    payment.voided_at = timezone.now()
    payment.voided_by = user if getattr(user, "is_authenticated", False) else None
    payment.void_reason = reason[:250]
    payment.save()
    record_event(
        payment.invoice, "payment.voided", {"number": payment.invoice.invoice_number, "amount": str(payment.amount)}
    )
    return payment


def open_items(*, today: datetime.date | None = None) -> list[tuple[IncomingInvoice, Balance]]:
    """The incoming invoices that are still to pay, oldest due day first."""
    today = today or timezone.localdate()
    rows: list[tuple[IncomingInvoice, Balance]] = []
    queryset = (
        IncomingInvoice.objects.filter(total_gross__isnull=False)
        .select_related("supplier")
        .prefetch_related("payments")
    )
    for invoice in queryset:
        found = balance(invoice, today=today)
        if found is not None and found.remaining > 0:
            rows.append((invoice, found))
    rows.sort(key=lambda row: (row[0].due_date is None, row[0].due_date or datetime.date.max, row[0].pk))
    return rows


def credit_items(*, today: datetime.date | None = None) -> list[tuple[IncomingInvoice, Balance]]:
    """What suppliers owe the company: a credit note not yet paid back, or an invoice paid too much (DOK-053).

    The ``remaining`` of such a balance is negative.
    """
    today = today or timezone.localdate()
    rows: list[tuple[IncomingInvoice, Balance]] = []
    queryset = (
        IncomingInvoice.objects.filter(total_gross__isnull=False)
        .select_related("supplier")
        .prefetch_related("payments")
    )
    for invoice in queryset:
        found = balance(invoice, today=today)
        if found is not None and found.remaining < 0:
            rows.append((invoice, found))
    rows.sort(key=lambda row: (row[0].supplier_label, row[0].pk))
    return rows
