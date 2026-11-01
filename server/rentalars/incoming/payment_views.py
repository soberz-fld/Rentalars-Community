# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser pages of the payments on incoming invoices and of the check of their e-invoice (DOK-048, DOK-042).

``accounting/incoming/<id>/payments/`` – what is paid of an invoice and what is still to pay; entering and voiding a payment.
``accounting/incoming/<id>/check/`` – check the e-invoice against the rules again.

Rights as for the register (``incoming.access``): purchase prices and read access to the material to look, write access to the
material to enter, void and check.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.documents import einvoice_check, outgoing
from rentalars.documents.payment_forms import PaymentForm, VoidForm
from rentalars.incoming import access, payments
from rentalars.incoming.models import IncomingInvoice


def _invoice(pk: int) -> IncomingInvoice:
    return get_object_or_404(IncomingInvoice.objects.select_related("supplier").prefetch_related("payments"), pk=pk)


@module_required(Module.MATERIAL)
def invoice_payments(request: HttpRequest, pk: int) -> HttpResponse:
    """The payments of an incoming invoice: balance, list, entering and voiding."""
    rights = request_rights(request)
    access.require_see(rights)
    invoice = _invoice(pk)
    balance = payments.balance(invoice)
    form = PaymentForm(request.POST or None, remaining=balance.remaining if balance else None)
    target = reverse("incoming:payments", args=[pk])
    if request.method == "POST":
        access.require_change(rights)
        if request.POST.get("action") == "void":
            void_form = VoidForm(request.POST)
            if void_form.is_valid():
                payment = get_object_or_404(invoice.payments, pk=void_form.cleaned_data["payment"])
                try:
                    payments.void(payment, reason=void_form.cleaned_data["reason"], user=request.user)
                except ValidationError as error:
                    messages.error(request, " ".join(error.messages))
                else:
                    messages.success(request, _("The payment was voided."))
            else:
                messages.error(request, _("Say why the payment is voided."))
            return redirect(target)
        if form.is_valid():
            try:
                payments.record(invoice, user=request.user, **form.cleaned_data)
            except ValidationError as error:
                add_validation_error(form, error)
            else:
                messages.success(request, _("The payment was entered."))
                return redirect(target)
        invoice = _invoice(pk)
        balance = payments.balance(invoice)
    return render(
        request,
        "incoming/payments.html",
        {
            **outgoing.tabs(rights),
            "tab": "incoming",
            "invoice": invoice,
            "balance": balance,
            "payments": list(invoice.payments.all()),
            "form": form,
            "void_form": VoidForm(),
            "may_change": access.may_change(rights),
        },
    )


@require_POST
@module_required(Module.MATERIAL)
def invoice_check(request: HttpRequest, pk: int) -> HttpResponse:
    """Check the e-invoice of an incoming invoice against the rules again (DOK-042)."""
    access.require_change(request_rights(request))
    invoice = _invoice(pk)
    try:
        report = einvoice_check.recheck_incoming(invoice)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if report["ok"]:
            messages.success(request, _("The e-invoice meets the rules that are checked."))
        else:
            messages.warning(
                request,
                _("The e-invoice breaks %(count)d rules. See the list on the page.") % {"count": report["errors"]},
            )
    return redirect(reverse("incoming:detail", args=[pk]) + "#incoming-einvoice")
