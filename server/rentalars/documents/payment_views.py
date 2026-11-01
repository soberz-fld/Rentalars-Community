# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser pages of the payments on outgoing invoices, the open items and the check of the e-invoice (DOK-048, DOK-042).

* ``accounting/documents/<id>/payments/`` – the payments of one invoice with its balance; entering and voiding.
* ``accounting/open-items/`` – Buchhaltung → Offene Posten: what customers still owe (and, for who may see purchase prices,
  what is still to pay to suppliers), by due day, with the sums; as CSV.
* ``accounting/documents/<id>/check/`` – check the e-invoice of a document again.

Rights: seeing needs the list of outgoing documents (``outgoing.may_see``: the price right and every project); entering, voiding
and checking again need write access to the projects everywhere in addition.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, Rights, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.core.tables import formula_safe
from rentalars.documents import einvoice_check, outgoing, payments
from rentalars.documents.models import Document, DocumentKind
from rentalars.documents.payment_forms import PaymentForm, VoidForm
from rentalars.incoming import access as incoming_access
from rentalars.incoming import payments as incoming_payments


def may_enter(rights: Rights) -> bool:
    """Whether payments may be entered, voided and the e-invoice checked again: the list, and write access to all projects."""
    return outgoing.may_see(rights) and rights.level_everywhere(Module.PROJECTS) >= Level.WRITE


def _document(request: HttpRequest, pk: int, *, change: bool = False) -> Document:
    rights = request_rights(request)
    if not (may_enter(rights) if change else outgoing.may_see(rights)):
        raise PermissionDenied
    return get_object_or_404(
        Document.objects.select_related("project", "customer", "cancelled_by").prefetch_related(
            "payments", "partial_credits"
        ),
        pk=pk,
        kind=DocumentKind.INVOICE,
    )


def _back(document: Document) -> str:
    return reverse("documents:payments", args=[document.pk])


@module_required(Module.PROJECTS)
def document_payments(request: HttpRequest, pk: int) -> HttpResponse:
    """The payments of an invoice: balance, list, entering a payment and voiding one."""
    document = _document(request, pk, change=request.method == "POST")
    rights = request_rights(request)
    form = PaymentForm(request.POST or None, remaining=payments.balance(document).remaining)
    if request.method == "POST":
        action = request.POST.get("action", "add")
        if action == "void":
            void_form = VoidForm(request.POST)
            if void_form.is_valid():
                payment = get_object_or_404(document.payments, pk=void_form.cleaned_data["payment"])
                try:
                    payments.void(payment, reason=void_form.cleaned_data["reason"], user=request.user)
                except ValidationError as error:
                    messages.error(request, " ".join(error.messages))
                else:
                    messages.success(request, _("The payment was voided."))
            else:
                messages.error(request, _("Say why the payment is voided."))
            return redirect(_back(document))
        if form.is_valid():
            try:
                payments.record(document, user=request.user, **form.cleaned_data)
            except ValidationError as error:
                add_validation_error(form, error)
            else:
                messages.success(request, _("The payment was entered."))
                return redirect(_back(document))
    document = _document(request, pk)  # fresh sums after a change
    balance = payments.balance(document)
    return render(
        request,
        "documents/payments.html",
        {
            **outgoing.tabs(rights),
            "tab": "outgoing",
            "document": document,
            "balance": balance,
            "payments": list(document.payments.all()),
            "form": form,
            "void_form": VoidForm(),
            "may_enter": may_enter(rights),
            "is_free": document.is_free,
        },
    )


@require_POST
@module_required(Module.PROJECTS)
def document_check(request: HttpRequest, pk: int) -> HttpResponse:
    """Check the e-invoice of a document again against the rules (DOK-042)."""
    document = _document(request, pk, change=True)
    try:
        check = einvoice_check.recheck(document)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if check.ok:
            messages.success(request, _("The e-invoice meets the rules that are checked."))
        else:
            messages.warning(
                request,
                _("The e-invoice breaks %(count)d rules. See the list on the page.") % {"count": check.error_count},
            )
    target = request.POST.get("next", "")
    from django.utils.http import url_has_allowed_host_and_scheme

    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(_back(document))


# --- Open items ----------------------------------------------------------------------------------------------------


def _csv_response(name: str, header: list[str], rows: list[list[Any]]) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(header)
    writer.writerows([[formula_safe(cell) for cell in row] for row in rows])
    return response


def open_items(request: HttpRequest) -> HttpResponse:
    """Buchhaltung → Offene Posten: customers' open invoices; with the purchase prices also those still to pay."""
    rights = request_rights(request)
    see_out = outgoing.may_see(rights)
    see_in = incoming_access.may_see(rights)
    if not (see_out or see_in):
        raise PermissionDenied
    side = request.GET.get("side") or ("outgoing" if see_out else "incoming")
    if side == "outgoing" and not see_out:
        side = "incoming"
    if side == "incoming" and not see_in:
        side = "outgoing"
    today = timezone.localdate()
    if side == "credits":
        return _credits_page(request, rights, see_out, see_in, today)
    if side == "outgoing":
        items = payments.open_items(today=today)
        total = sum((balance.remaining for _document, balance in items), Decimal("0.00"))
        overdue = sum((balance.remaining for _document, balance in items if balance.overdue), Decimal("0.00"))
        if request.GET.get("format") == "csv":
            return _csv_response(
                "offene-posten-ausgang.csv",
                [
                    _("Number"),
                    _("Customer"),
                    _("Project"),
                    _("Date"),
                    _("Due on"),
                    _("Gross"),
                    _("Paid"),
                    _("Open"),
                    _("Status"),
                ],
                [
                    [
                        document.number,
                        document.customer.name if document.customer_id else "",
                        document.project.number if document.project_id else "",
                        document.issued_on.isoformat(),
                        document.due_on.isoformat() if document.due_on else "",
                        balance.payable,
                        balance.paid,
                        balance.remaining,
                        _("overdue") if balance.overdue else balance.label,
                    ]
                    for document, balance in items
                ],
            )
    else:
        items = incoming_payments.open_items(today=today)
        total = sum((balance.remaining for _invoice, balance in items), Decimal("0.00"))
        overdue = sum((balance.remaining for _invoice, balance in items if balance.overdue), Decimal("0.00"))
        if request.GET.get("format") == "csv":
            return _csv_response(
                "offene-posten-eingang.csv",
                [
                    _("Number"),
                    _("Supplier"),
                    _("Date"),
                    _("Due on"),
                    _("Currency"),
                    _("Gross"),
                    _("Paid"),
                    _("Open"),
                    _("Status"),
                ],
                [
                    [
                        invoice.invoice_number,
                        invoice.supplier_label,
                        invoice.invoice_date.isoformat() if invoice.invoice_date else "",
                        invoice.due_date.isoformat() if invoice.due_date else "",
                        invoice.currency,
                        balance.payable,
                        balance.paid,
                        balance.remaining,
                        _("overdue") if balance.overdue else balance.label,
                    ]
                    for invoice, balance in items
                ],
            )
    return render(
        request,
        "documents/open_items.html",
        {
            **outgoing.tabs(rights),
            "tab": "open_items",
            "side": side,
            "see_out": see_out,
            "see_in": see_in,
            "items": items,
            "total": total,
            "overdue": overdue,
            "today": today,
        },
    )


def credit_rows(rights: Rights, today: Any = None) -> list[dict[str, Any]]:
    """What the company owes customers back and what suppliers owe it, for whoever may see each side (DOK-053).

    A row is ``{"direction": "owe_customer" | "owed_by_supplier", "entry", "balance", "number", "party", "currency",
    "amount"}``; ``amount`` is positive.
    """
    rows: list[dict[str, Any]] = []
    if outgoing.may_see(rights):
        for document, found in payments.credit_items(today=today):
            rows.append(
                {
                    "direction": "owe_customer",
                    "entry": document,
                    "balance": found,
                    "number": document.number,
                    "party": document.customer.name if document.customer_id else "",
                    "currency": "EUR",
                    "amount": -found.remaining,
                }
            )
    if incoming_access.may_see(rights):
        for invoice, found in incoming_payments.credit_items(today=today):
            rows.append(
                {
                    "direction": "owed_by_supplier",
                    "entry": invoice,
                    "balance": found,
                    "number": invoice.invoice_number,
                    "party": invoice.supplier_label,
                    "currency": invoice.currency,
                    "amount": -found.remaining,
                }
            )
    return rows


def _credits_page(request: HttpRequest, rights: Rights, see_out: bool, see_in: bool, today: Any) -> HttpResponse:
    rows = credit_rows(rights, today)
    owed_to_customers = sum((r["amount"] for r in rows if r["direction"] == "owe_customer"), Decimal("0.00"))
    owed_by_suppliers = sum(
        (r["amount"] for r in rows if r["direction"] == "owed_by_supplier" and r["currency"] == "EUR"), Decimal("0.00")
    )
    if request.GET.get("format") == "csv":
        return _csv_response(
            "guthaben.csv",
            [_("Direction"), _("Number"), _("Party"), _("Currency"), _("Gross"), _("Paid"), _("Credit")],
            [
                [
                    _("we owe the customer") if r["direction"] == "owe_customer" else _("the supplier owes us"),
                    r["number"],
                    r["party"],
                    r["currency"],
                    r["balance"].payable,
                    r["balance"].paid,
                    r["amount"],
                ]
                for r in rows
            ],
        )
    return render(
        request,
        "documents/open_items.html",
        {
            **outgoing.tabs(rights),
            "tab": "open_items",
            "side": "credits",
            "see_out": see_out,
            "see_in": see_in,
            "credits": rows,
            "owed_to_customers": owed_to_customers,
            "owed_by_suppliers": owed_by_suppliers,
            "today": today,
        },
    )
