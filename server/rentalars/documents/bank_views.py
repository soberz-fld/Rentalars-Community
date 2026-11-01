# SPDX-License-Identifier: GPL-3.0-or-later
"""Buchhaltung → Bank: read in bank statements, see the transactions with suggestions, book them (DOK-050).

* ``accounting/bank/`` – the transactions (open ones first) with the suggestions for each, the statements read in, the
  upload form;
* ``accounting/bank/upload/`` – read a CAMT.053 or CSV file in;
* ``accounting/bank/<id>/book/`` – enter the payment for a transaction at the invoice the person chose;
* ``accounting/bank/<id>/ignore/`` and ``…/restore/`` – set a transaction aside with a reason, or take it back.

Nothing is booked without a click: the suggestions only save the search. Rights: ``bank.may_use`` to look, ``bank.may_change``
to read in, book and set aside.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.listing import paginate
from rentalars.documents import bank, outgoing
from rentalars.documents.models import BankImport, BankTransaction

STATES = ("open", "booked", "ignored", "all")


def _require_use(request: HttpRequest) -> None:
    if not bank.may_use(request_rights(request)):
        raise PermissionDenied


def _require_change(request: HttpRequest) -> None:
    if not bank.may_change(request_rights(request)):
        raise PermissionDenied


def _back(request: HttpRequest) -> HttpResponse:
    state = request.POST.get("state", "")
    address = reverse("documents:bank")
    return redirect(f"{address}?state={state}" if state in STATES else address)


def filtered(state: str):
    """The transactions in a state: ``open`` (also those whose payment was voided), ``booked``, ``ignored`` or all."""
    from django.db.models import Q

    queryset = BankTransaction.objects.select_related(
        "bank_import", "outgoing_payment__document", "incoming_payment__invoice"
    )
    booked = (Q(outgoing_payment__isnull=False) & Q(outgoing_payment__voided_at__isnull=True)) | (
        Q(incoming_payment__isnull=False) & Q(incoming_payment__voided_at__isnull=True)
    )
    if state == "open":
        return queryset.filter(ignored_at__isnull=True).exclude(booked)
    if state == "booked":
        return queryset.filter(ignored_at__isnull=True).filter(booked)
    if state == "ignored":
        return queryset.filter(ignored_at__isnull=False)
    return queryset


@module_required(Module.PROJECTS)
def bank_page(request: HttpRequest) -> HttpResponse:
    """The transactions with suggestions, the statements and the upload."""
    _require_use(request)
    rights = request_rights(request)
    state = request.GET.get("state", "open")
    if state not in STATES:
        state = "open"
    page = paginate(request, filtered(state), key="bank")
    candidates = bank.load_candidates() if state in {"open", "all"} else []
    rows = [
        {
            "tx": tx,
            "state": tx.state,
            "suggestions": bank.suggestions(tx, candidates) if tx.state == "open" else [],
        }
        for tx in page
    ]
    return render(
        request,
        "documents/bank.html",
        {
            **outgoing.tabs(rights),
            "tab": "bank",
            "state": state,
            "states": [
                ("open", _("Open")),
                ("booked", _("Booked")),
                ("ignored", _("Ignored")),
                ("all", _("All")),
            ],
            "page": page,
            "rows": rows,
            "imports": list(BankImport.objects.all()[:10]),
            "open_count": filtered("open").count(),
            "may_change": bank.may_change(rights),
        },
    )


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def bank_upload(request: HttpRequest) -> HttpResponse:
    """Read a bank statement file in."""
    _require_change(request)
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, _("Choose the file of the bank."))
        return redirect("documents:bank")
    if upload.size > bank.MAX_BYTES:
        messages.error(request, _("The file is too large."))
        return redirect("documents:bank")
    try:
        created = bank.import_file(upload.read(), upload.name or "", user=request.user)
    except bank.BankFileError as error:
        messages.error(request, str(error))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("%(name)s was read in: %(new)d new transactions, %(known)d already known.")
            % {"name": created.name, "new": created.new_count, "known": created.skipped_count},
        )
    return redirect("documents:bank")


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def bank_book(request: HttpRequest, pk: int) -> HttpResponse:
    """Enter the payment for a transaction at the invoice the person chose."""
    _require_change(request)
    tx = get_object_or_404(BankTransaction, pk=pk)
    side = request.POST.get("side", "")
    try:
        target = int(request.POST.get("target", ""))
        bank.book(tx, side, target, user=request.user)
    except (ValueError, ValidationError) as error:
        text = " ".join(error.messages) if isinstance(error, ValidationError) else _("Choose the invoice.")
        messages.error(request, text)
    else:
        messages.success(request, _("The payment was entered."))
    return _back(request)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def bank_ignore(request: HttpRequest, pk: int) -> HttpResponse:
    """Set a transaction aside, with the reason."""
    _require_change(request)
    tx = get_object_or_404(BankTransaction, pk=pk)
    try:
        bank.ignore(tx, reason=request.POST.get("reason", ""), user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("The transaction was set aside."))
    return _back(request)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def bank_restore(request: HttpRequest, pk: int) -> HttpResponse:
    """Take an ignored transaction back."""
    _require_change(request)
    tx = get_object_or_404(BankTransaction, pk=pk)
    try:
        bank.restore(tx)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("The transaction is open again."))
    return _back(request)
