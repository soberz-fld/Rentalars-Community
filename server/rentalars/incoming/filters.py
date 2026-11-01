# SPDX-License-Identifier: GPL-3.0-or-later
"""The filters of the list of incoming invoices, shared by the page and the API (DOK-023, DOK-024).

Supplier, status, a range of invoice dates and a text search (invoice number, supplier, file name, note, descriptions
of the positions). Empty values filter nothing.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db.models import Count, Exists, OuterRef, Q, QuerySet
from django.utils.translation import gettext as _

from rentalars.incoming.models import IncomingInvoice, InvoicePosition, InvoiceStatus
from rentalars.masterdata.models import Supplier

#: The largest ID a filter takes: a bigger number fits no row and would overflow the integer of the database (R1-10).
MAX_ID = 2**31 - 1


@dataclass
class Filters:
    """What the list is narrowed to."""

    supplier: int | None = None
    status: str = ""
    since: datetime.date | None = None
    until: datetime.date | None = None
    text: str = ""
    #: What could not be read, by parameter – the API answers 400 with it; the page ignores the value.
    errors: dict[str, str] = field(default_factory=dict)

    def apply(self, queryset: QuerySet[IncomingInvoice]) -> QuerySet[IncomingInvoice]:
        """Narrow the invoices; conditions on related rows are ``EXISTS``, so no invoice comes twice."""
        if self.supplier is not None:
            queryset = queryset.filter(supplier_id=self.supplier)
        if self.status:
            queryset = queryset.filter(status=self.status)
        if self.since is not None:
            queryset = queryset.filter(invoice_date__gte=self.since)
        if self.until is not None:
            queryset = queryset.filter(invoice_date__lte=self.until)
        if self.text:
            positions = InvoicePosition.objects.filter(invoice=OuterRef("pk"), description__icontains=self.text)
            queryset = queryset.filter(
                Q(invoice_number__icontains=self.text)
                | Q(supplier_name__icontains=self.text)
                | Q(supplier__name__icontains=self.text)
                | Q(original_name__icontains=self.text)
                | Q(note__icontains=self.text)
                | Exists(positions)
            )
        return queryset


def status_choices() -> list[tuple[str, str]]:
    """The choices of the filter "status"."""
    return [(str(value), str(label)) for value, label in InvoiceStatus.choices]


def parse(params: Any) -> Filters:
    """Read the filters from the address (``request.GET``, ``request.query_params``).

    ``supplier``, ``status``, ``since`` and ``until`` (days of the invoice date, both included) and ``q``.
    """
    errors: dict[str, str] = {}
    supplier = None
    text = (params.get("supplier") or "").strip()
    if text:
        if text.isdigit() and int(text) <= MAX_ID:
            supplier = int(text)
        else:
            errors["supplier"] = _("Enter the ID as a number.")
    status = (params.get("status") or "").strip()
    if status and status not in InvoiceStatus.values:
        errors["status"] = _("Unknown value “%(value)s”.") % {"value": status}
        status = ""
    days: dict[str, datetime.date | None] = {}
    for name in ("since", "until"):
        value = (params.get(name) or "").strip()
        days[name] = None
        if value:
            try:
                days[name] = datetime.date.fromisoformat(value)
            except ValueError:
                errors[name] = _("Enter the day as YYYY-MM-DD.")
    return Filters(
        supplier=supplier,
        status=status,
        since=days["since"],
        until=days["until"],
        text=" ".join((params.get("q") or "").split())[:100],
        errors=errors,
    )


def invoices() -> QuerySet[IncomingInvoice]:
    """Every incoming invoice with the number of its positions, in no particular order."""
    return IncomingInvoice.objects.select_related("supplier", "created_by").annotate(position_count=Count("positions"))


def suppliers_of_invoices() -> QuerySet[Supplier]:
    """The suppliers that have invoices – the choices of the filter."""
    return Supplier.objects.filter(pk__in=IncomingInvoice.objects.values("supplier")).order_by("name")


@dataclass
class Totals:
    """Count and sums of the filtered invoices; sums in euros, invoices in other currencies counted separately."""

    count: int
    net: Decimal
    tax: Decimal
    gross: Decimal
    foreign: int
    #: Invoices in another currency without an exchange rate – they are counted but add nothing to the sums.
    missing_rate: int = 0
    #: Invoices that have no totals typed or read yet – they add nothing to the sums either.
    without_amount: int = 0

    @property
    def incomplete(self) -> bool:
        """Whether the sums leave invoices out (so that they must not be read as the whole)."""
        return bool(self.missing_rate or self.without_amount)


def totals(queryset: QuerySet[IncomingInvoice]) -> Totals:
    """Count, net, tax and gross of the filtered invoices – over the whole list, not one page, in one query.

    Amounts of an invoice in another currency are converted with its exchange rate; an invoice without an amount
    adds nothing. The credit note of an e-invoice (it stands with the amounts its file gives, positive) is taken off.
    """
    net = tax = gross = Decimal(0)
    count = foreign = missing_rate = without_amount = 0
    for currency, rate, total_net, total_tax, total_gross, reading in queryset.order_by().values_list(
        "currency", "exchange_rate", "total_net", "total_tax", "total_gross", "reading"
    ):
        count += 1
        factor = Decimal(-1) if ((reading or {}).get("einvoice") or {}).get("credit_note") else Decimal(1)
        if (currency or "EUR").upper() != "EUR":
            foreign += 1
            if rate is None:
                missing_rate += 1  # no rate entered yet – nothing is converted 1:1 by accident
                continue
            factor *= rate
        if total_net is None and total_tax is None and total_gross is None:
            without_amount += 1
        net += (total_net or 0) * factor
        tax += (total_tax or 0) * factor
        gross += (total_gross or 0) * factor
    cents = Decimal("0.01")
    return Totals(
        count=count,
        net=net.quantize(cents),
        tax=tax.quantize(cents),
        gross=gross.quantize(cents),
        foreign=foreign,
        missing_rate=missing_rate,
        without_amount=without_amount,
    )
