# SPDX-License-Identifier: GPL-3.0-or-later
"""Buchhaltung → Eingangsrechnungen as a table: columns to choose, sorting, groups and CSV (DOK-023, DOK-024).

The same table machinery as the outgoing documents (``core.tables``, UIX-015, UIX-040): every column sorts by the
database and groups by the field it shows. The amounts are those of the invoice in its own currency.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from rentalars.core.money import format_money
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day, link
from rentalars.incoming.models import IncomingInvoice, InvoiceStatus

STATUS_COLOURS = {InvoiceStatus.OPEN: "yellow", InvoiceStatus.CHECKED: "green", InvoiceStatus.BOOKED_IN: "accent"}


def _money(invoice: IncomingInvoice, value: Any) -> str:
    """An amount with the currency of the invoice; nothing without an amount."""
    if value is None:
        return ""
    return format_money(value, currency="€" if invoice.currency.upper() == "EUR" else invoice.currency)


def _number(invoice: IncomingInvoice) -> Any:
    """The invoice number, linked to the page of the invoice; a file name stands in for a missing number."""
    return link(reverse("incoming:detail", args=[invoice.pk]), invoice.invoice_number or invoice.original_name)


def _status(invoice: IncomingInvoice) -> Any:
    """The status as a badge."""
    return badge(invoice.get_status_display(), STATUS_COLOURS.get(invoice.status, ""))


def _file(invoice: IncomingInvoice) -> Any:
    """The original, in a tab of its own."""
    return format_html(
        '<a href="{}" target="_blank" rel="noopener">{}</a>',
        reverse("incoming:file", args=[invoice.pk]),
        _("Open the original"),
    )


def _reading(invoice: IncomingInvoice) -> str:
    """How the invoice was read: by AI, from the text, or not."""
    source = (invoice.reading or {}).get("source")
    return {"ai": str(_("by AI")), "text": str(_("from the text"))}.get(source or "", str(_("not read")))


def _user(invoice: IncomingInvoice) -> str:
    """Who uploaded the invoice."""
    user = invoice.created_by
    return (user.get_full_name() or user.username) if user is not None else ""


INCOMING_TABLE = TableDefinition(
    "incoming_invoices",
    [
        Column(
            "number",
            _("Invoice number"),
            cell=_number,
            text=lambda invoice: invoice.invoice_number or invoice.original_name,
            sort=("invoice_number", "original_name"),
            css="nowrap",
            fixed=True,
            group="invoice_number",
        ),
        Column(
            "supplier",
            _("Supplier"),
            cell=lambda invoice: invoice.supplier_label,
            sort=("supplier__name", "supplier_name", "-invoice_date"),
            group=lambda invoice: invoice.supplier_label,
        ),
        Column(
            "invoice_date",
            _("Invoice date"),
            cell=lambda invoice: date_text(invoice.invoice_date),
            text=lambda invoice: invoice.invoice_date,
            sort=("invoice_date", "pk"),
            css="nowrap",
            group="invoice_date",
        ),
        Column(
            "due_date",
            _("Due date"),
            cell=lambda invoice: date_text(invoice.due_date),
            text=lambda invoice: invoice.due_date,
            sort=("due_date", "pk"),
            css="nowrap",
            default=False,
            group="due_date",
        ),
        Column(
            "net",
            _("Net"),
            cell=lambda invoice: _money(invoice, invoice.total_net),
            text=lambda invoice: invoice.total_net,
            sort=("total_net", "pk"),
            css="num nowrap",
            group="total_net",
        ),
        Column(
            "tax",
            _("Tax"),
            cell=lambda invoice: _money(invoice, invoice.total_tax),
            text=lambda invoice: invoice.total_tax,
            sort=("total_tax", "pk"),
            css="num nowrap",
            default=False,
            group="total_tax",
        ),
        Column(
            "gross",
            _("Gross"),
            cell=lambda invoice: _money(invoice, invoice.total_gross),
            text=lambda invoice: invoice.total_gross,
            sort=("total_gross", "pk"),
            css="num nowrap",
            group="total_gross",
        ),
        Column(
            "currency",
            _("Currency"),
            cell=lambda invoice: invoice.currency,
            sort=("currency", "pk"),
            default=False,
            group="currency",
        ),
        Column(
            "status",
            _("Status"),
            cell=_status,
            text=lambda invoice: invoice.get_status_display(),
            sort=("status", "-invoice_date"),
            group="status",
            group_label=_status,
        ),
        Column(
            "positions",
            _("Positions"),
            cell=lambda invoice: str(getattr(invoice, "position_count", "")),
            sort=("position_count", "pk"),
            css="num",
            default=False,
            group="position_count",
        ),
        Column(
            "note",
            _("Note"),
            cell=lambda invoice: Truncator(invoice.note).chars(80),
            text=lambda invoice: invoice.note,
            sort=("note", "pk"),
            group="note",
        ),
        Column(
            "reading",
            _("Reading"),
            cell=_reading,
            sort=("reading__source", "pk"),
            default=False,
            group=_reading,
        ),
        Column(
            "file",
            _("File"),
            cell=_file,
            text=lambda invoice: invoice.original_name,
            sort=("original_name", "pk"),
            default=False,
        ),
        Column(
            "created_by",
            _("Uploaded by"),
            cell=_user,
            sort=("created_by__last_name", "created_by__first_name", "created_by__username", "pk"),
            default=False,
            group="created_by",
        ),
        Column(
            "created_at",
            _("Uploaded"),
            cell=lambda invoice: date_text(invoice.created_at),
            text=lambda invoice: invoice.created_at,
            sort=("created_at", "pk"),
            css="nowrap",
            default=False,
            **grouped_by_day("created_at"),
        ),
    ],
    default_sort="-invoice_date",
)
