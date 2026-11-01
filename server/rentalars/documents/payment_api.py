# SPDX-License-Identifier: GPL-3.0-or-later
"""API of payments, open items, the check of e-invoices, the EÜR, the archive and the audit export (API-002, API-014).

Every operation of the pages has its endpoint here, with the rights of the page:

* ``/documents/{id}/payments`` – GET the balance and the payments of an outgoing invoice, POST a payment (DOK-048). Seeing: the list
  of outgoing documents (``outgoing.may_see``); entering: write access to all projects in addition.
* ``/payments/{id}/void`` – POST void a payment received, with a ``reason``. ``/incoming-invoices/{id}/payments`` and
  ``/incoming-payments/{id}/void`` – the same for incoming invoices, with the rights of the register.
* ``/documents/{id}/validation`` and ``/incoming-invoices/{id}/validation`` – GET the stored check of the e-invoice, POST check again
  (DOK-042).
* ``/accounting/open-items`` – what customers owe (``side=outgoing``) or what is still to pay (``side=incoming``).
* ``/accounting/euer`` – the EÜR of a ``year`` (DOK-045); ``/accounting/archive`` and ``/accounting/archive/verify`` (DOK-043);
  ``/accounting/audit-export`` – the ZIP; ``/accounting/procedure`` – the procedure documentation (DOK-046). These need the
  settings (read; write to check the archive) and both price rights.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.permissions import AUTHENTICATED_ONLY
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.core.api import JobSerializer
from rentalars.core.payment_base import MAX_AMOUNT, PaymentMethod
from rentalars.documents import (
    archive,
    audit_export,
    einvoice_check,
    euer,
    outgoing,
    payment_views,
    payments,
    procedure,
)
from rentalars.documents.models import Document, DocumentKind, OutgoingPayment
from rentalars.incoming import access as incoming_access
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice, IncomingPayment


class PaymentSerializer(serializers.Serializer):
    """A payment."""

    id = serializers.IntegerField()
    paid_on = serializers.DateField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, help_text="Gross; negative: a refund.")
    method = serializers.ChoiceField(choices=PaymentMethod.values)
    reference = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    voided_at = serializers.DateTimeField(allow_null=True)
    void_reason = serializers.CharField(allow_blank=True)


class BalanceSerializer(serializers.Serializer):
    """What an invoice demands, what was paid, what is left."""

    payable = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    remaining = serializers.DecimalField(max_digits=14, decimal_places=2)
    state = serializers.CharField(help_text="open, partial, paid, overpaid, cancelled or refund_due.")
    due_on = serializers.DateField(allow_null=True)
    overdue = serializers.BooleanField()
    imported_paid = serializers.BooleanField(
        help_text="Counted as paid because the import of old projects knew it as paid."
    )


class PaymentsSerializer(serializers.Serializer):
    """The balance and the payments of an invoice."""

    balance = BalanceSerializer(allow_null=True)
    payments = PaymentSerializer(many=True)


class PaymentInput(serializers.Serializer):
    """A payment to enter."""

    paid_on = serializers.DateField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=-MAX_AMOUNT, max_value=MAX_AMOUNT)
    method = serializers.ChoiceField(choices=PaymentMethod.values, default=PaymentMethod.TRANSFER)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    note = serializers.CharField(required=False, allow_blank=True, max_length=250)


class VoidInput(serializers.Serializer):
    """The reason to void a payment."""

    reason = serializers.CharField(max_length=250)


def _balance_data(balance: Any) -> dict[str, Any] | None:
    if balance is None:
        return None
    return {
        "payable": balance.payable,
        "paid": balance.paid,
        "remaining": balance.remaining,
        "state": balance.state,
        "due_on": balance.due_on,
        "overdue": balance.overdue,
        "imported_paid": getattr(balance, "imported_paid", False),
    }


def _payment_data(payment: Any) -> dict[str, Any]:
    return {
        "id": payment.pk,
        "paid_on": payment.paid_on,
        "amount": payment.amount,
        "method": payment.method,
        "reference": payment.reference,
        "note": payment.note,
        "created_at": payment.created_at,
        "voided_at": payment.voided_at,
        "void_reason": payment.void_reason,
    }


# --- Outgoing invoices -------------------------------------------------------------------------------------------


class _OutgoingPaymentView(ModuleAPIView):
    module = Module.PROJECTS
    schema_tag = "accounting"

    def allow(self, *, change: bool) -> None:
        """403 without the rights of the page (checked before anything is looked up, so a 404 tells nothing)."""
        allowed = payment_views.may_enter(self.rights) if change else outgoing.may_see(self.rights)
        if not allowed:
            raise PermissionDenied

    def document(self, pk: int, *, change: bool) -> Document:
        """The invoice; 403 without the rights of the page, 404 for another document."""
        self.allow(change=change)
        return get_object_or_404(
            Document.objects.select_related("project", "customer", "cancelled_by").prefetch_related(
                "payments", "partial_credits"
            ),
            pk=pk,
            kind=DocumentKind.INVOICE,
        )


class DocumentPaymentsView(_OutgoingPaymentView):
    """``/documents/{id}/payments`` – the payments of an outgoing invoice (DOK-048)."""

    @extend_schema(responses=PaymentsSerializer, operation_id="document_payments_list")
    def get(self, request: Request, pk: int) -> Response:
        """The balance and all payments, voided ones included."""
        document = self.document(pk, change=False)
        return Response(
            PaymentsSerializer(
                {
                    "balance": _balance_data(payments.balance(document)),
                    "payments": [_payment_data(p) for p in document.payments.all()],
                }
            ).data
        )

    @extend_schema(request=PaymentInput, responses={201: PaymentSerializer}, operation_id="document_payments_create")
    def post(self, request: Request, pk: int) -> Response:
        """Enter a payment; 400 for a day in the future, a zero amount, or an old invoice that counts as paid."""
        document = self.document(pk, change=True)
        form = PaymentInput(data=request.data)
        form.is_valid(raise_exception=True)
        payment = payments.record(document, user=request.user, **form.validated_data)
        return Response(PaymentSerializer(_payment_data(payment)).data, status=201)


class PaymentVoidView(_OutgoingPaymentView):
    """``POST /payments/{id}/void`` – void a payment received (DOK-048)."""

    @extend_schema(request=VoidInput, responses=PaymentSerializer, operation_id="payment_void")
    def post(self, request: Request, pk: int) -> Response:
        """The payment stays in the list but no longer counts; 400 without a reason or when voided already."""
        self.allow(change=True)
        payment = get_object_or_404(OutgoingPayment, pk=pk)
        self.document(payment.document_id, change=True)
        form = VoidInput(data=request.data)
        form.is_valid(raise_exception=True)
        voided = payments.void(payment, reason=form.validated_data["reason"], user=request.user)
        return Response(PaymentSerializer(_payment_data(voided)).data)


# --- Incoming invoices -------------------------------------------------------------------------------------------


class _IncomingPaymentView(ModuleAPIView):
    module = Module.MATERIAL
    schema_tag = "accounting"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """The rights of the register: seeing for a read, changing for the rest."""
        super().initial(request, *args, **kwargs)
        read = request.method in {"GET", "HEAD", "OPTIONS"}
        if not (incoming_access.may_see(self.rights) if read else incoming_access.may_change(self.rights)):
            raise PermissionDenied


class IncomingPaymentsView(_IncomingPaymentView):
    """``/incoming-invoices/{id}/payments`` – the payments to the supplier (DOK-048)."""

    @extend_schema(responses=PaymentsSerializer, operation_id="incoming_payments_list")
    def get(self, request: Request, pk: int) -> Response:
        """The balance (``null`` while the totals of the invoice are not entered) and all payments."""
        invoice = get_object_or_404(IncomingInvoice.objects.prefetch_related("payments"), pk=pk)
        return Response(
            PaymentsSerializer(
                {
                    "balance": _balance_data(incoming_payments.balance(invoice)),
                    "payments": [_payment_data(p) for p in invoice.payments.all()],
                }
            ).data
        )

    @extend_schema(request=PaymentInput, responses={201: PaymentSerializer}, operation_id="incoming_payments_create")
    def post(self, request: Request, pk: int) -> Response:
        """Enter a payment; 400 while the totals of the invoice are missing."""
        invoice = get_object_or_404(IncomingInvoice, pk=pk)
        form = PaymentInput(data=request.data)
        form.is_valid(raise_exception=True)
        payment = incoming_payments.record(invoice, user=request.user, **form.validated_data)
        return Response(PaymentSerializer(_payment_data(payment)).data, status=201)


class IncomingPaymentVoidView(_IncomingPaymentView):
    """``POST /incoming-payments/{id}/void`` – void a payment to a supplier."""

    @extend_schema(request=VoidInput, responses=PaymentSerializer, operation_id="incoming_payment_void")
    def post(self, request: Request, pk: int) -> Response:
        """The payment stays in the list but no longer counts."""
        payment = get_object_or_404(IncomingPayment, pk=pk)
        form = VoidInput(data=request.data)
        form.is_valid(raise_exception=True)
        voided = incoming_payments.void(payment, reason=form.validated_data["reason"], user=request.user)
        return Response(PaymentSerializer(_payment_data(voided)).data)


# --- The check of the e-invoice ----------------------------------------------------------------------------------


class ValidationSerializer(serializers.Serializer):
    """The result of the check against the rules of EN 16931 and the XRechnung."""

    checked = serializers.BooleanField(
        help_text="False: no check was made yet (an invoice without e-invoice has none)."
    )
    ok = serializers.BooleanField()
    errors = serializers.IntegerField()
    warnings = serializers.IntegerField()
    syntax = serializers.CharField(allow_blank=True)
    profile = serializers.CharField(allow_blank=True)
    ruleset = serializers.CharField(allow_blank=True)
    checked_at = serializers.CharField(allow_blank=True)
    findings = serializers.ListField(child=serializers.DictField(child=serializers.CharField(allow_blank=True)))


def _validation_data(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "checked": bool(report),
        "ok": bool(report.get("ok", False)),
        "errors": int(report.get("errors", 0)),
        "warnings": int(report.get("warnings", 0)),
        "syntax": report.get("syntax", ""),
        "profile": report.get("profile", ""),
        "ruleset": report.get("ruleset", ""),
        "checked_at": str(report.get("checked_at", "")),
        "findings": report.get("findings", []),
    }


class DocumentValidationView(_OutgoingPaymentView):
    """``/documents/{id}/validation`` – the check of the e-invoice of an outgoing invoice (DOK-042)."""

    @extend_schema(responses=ValidationSerializer, operation_id="document_validation_get")
    def get(self, request: Request, pk: int) -> Response:
        """The stored check made when the invoice was issued (or the last one asked for)."""
        document = self.document(pk, change=False)
        return Response(
            ValidationSerializer(_validation_data(einvoice_check.report_json(einvoice_check.check_of(document)))).data
        )

    @extend_schema(request=None, responses=ValidationSerializer, operation_id="document_validation_check")
    def post(self, request: Request, pk: int) -> Response:
        """Check the e-invoice again against the rules and keep the result."""
        document = self.document(pk, change=True)
        return Response(
            ValidationSerializer(_validation_data(einvoice_check.report_json(einvoice_check.recheck(document)))).data
        )


class IncomingValidationView(_IncomingPaymentView):
    """``/incoming-invoices/{id}/validation`` – the check of an incoming e-invoice (DOK-042)."""

    @extend_schema(responses=ValidationSerializer, operation_id="incoming_validation_get")
    def get(self, request: Request, pk: int) -> Response:
        """The stored check; ``checked`` false for an invoice without e-invoice."""
        invoice = get_object_or_404(IncomingInvoice, pk=pk)
        return Response(ValidationSerializer(_validation_data(invoice.einvoice_check or {})).data)

    @extend_schema(request=None, responses=ValidationSerializer, operation_id="incoming_validation_check")
    def post(self, request: Request, pk: int) -> Response:
        """Check again; 400 for an invoice without e-invoice."""
        invoice = get_object_or_404(IncomingInvoice, pk=pk)
        return Response(ValidationSerializer(_validation_data(einvoice_check.recheck_incoming(invoice))).data)


# --- Open items ----------------------------------------------------------------------------------------------------


class InvoiceOpenItemSerializer(serializers.Serializer):
    """One open invoice."""

    id = serializers.IntegerField()
    number = serializers.CharField(allow_blank=True)
    party = serializers.CharField(allow_blank=True, help_text="The customer or the supplier.")
    issued_on = serializers.DateField(allow_null=True)
    due_on = serializers.DateField(allow_null=True)
    currency = serializers.CharField()
    payable = serializers.DecimalField(max_digits=14, decimal_places=2)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    remaining = serializers.DecimalField(max_digits=14, decimal_places=2)
    state = serializers.CharField()
    overdue = serializers.BooleanField()
    direction = serializers.CharField(
        required=False,
        help_text="Only for side=credits: owe_customer (a refund is due) or owed_by_supplier (money to claim).",
    )


class OpenItemsView(ModuleAPIView):
    """``GET /accounting/open-items`` – what customers owe, or what is still to pay (DOK-048)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "accounting"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "side",
                OpenApiTypes.STR,
                enum=["outgoing", "incoming", "credits"],
                description="Default: outgoing. credits: refunds due to customers and money suppliers owe (DOK-053).",
            )
        ],
        responses=inline_serializer(
            "OpenItems",
            {
                "side": serializers.CharField(),
                "total": serializers.DecimalField(max_digits=14, decimal_places=2),
                "overdue": serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True),
                "owed_to_customers": serializers.DecimalField(max_digits=14, decimal_places=2, required=False),
                "owed_by_suppliers": serializers.DecimalField(max_digits=14, decimal_places=2, required=False),
                "items": InvoiceOpenItemSerializer(many=True),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        """The open invoices, the oldest due day first (the sums count the euro only); 403 without the rights for that side."""
        side = request.query_params.get("side", "outgoing")
        if side not in {"outgoing", "incoming", "credits"}:
            raise ApiValidationError({"side": "One of outgoing, incoming, credits."})
        today = timezone.localdate()
        items: list[dict[str, Any]] = []
        if side == "credits":
            return self._credits(today)
        if side == "outgoing":
            if not outgoing.may_see(self.rights):
                raise PermissionDenied
            for document, balance in payments.open_items(today=today):
                items.append(
                    {
                        "id": document.pk,
                        "number": document.number,
                        "party": document.customer.name if document.customer_id else "",
                        "issued_on": document.issued_on,
                        "due_on": balance.due_on,
                        "currency": "EUR",
                        "payable": balance.payable,
                        "paid": balance.paid,
                        "remaining": balance.remaining,
                        "state": balance.state,
                        "overdue": balance.overdue,
                    }
                )
        else:
            if not incoming_access.may_see(self.rights):
                raise PermissionDenied
            for invoice, balance in incoming_payments.open_items(today=today):
                items.append(
                    {
                        "id": invoice.pk,
                        "number": invoice.invoice_number,
                        "party": invoice.supplier_label,
                        "issued_on": invoice.invoice_date,
                        "due_on": balance.due_on,
                        "currency": invoice.currency,
                        "payable": balance.payable,
                        "paid": balance.paid,
                        "remaining": balance.remaining,
                        "state": balance.state,
                        "overdue": balance.overdue,
                    }
                )
        return Response(
            {
                "side": side,
                # amounts in another currency than the euro are listed but not added to the euro sums
                "total": sum((i["remaining"] for i in items if i["currency"] == "EUR"), payments.ZERO),
                "overdue": sum(
                    (i["remaining"] for i in items if i["overdue"] and i["currency"] == "EUR"), payments.ZERO
                ),
                "items": InvoiceOpenItemSerializer(items, many=True).data,
            }
        )

    def _credits(self, today: Any) -> Response:
        """The credit balances (DOK-053): refunds due to customers and money suppliers owe, for the sides the caller may see."""
        from rentalars.documents.payment_views import credit_rows

        rows = credit_rows(self.rights, today)
        if not (outgoing.may_see(self.rights) or incoming_access.may_see(self.rights)):
            raise PermissionDenied
        items = [
            {
                "id": r["entry"].pk,
                "number": r["number"],
                "party": r["party"],
                "issued_on": r["entry"].issued_on if r["direction"] == "owe_customer" else r["entry"].invoice_date,
                "due_on": r["balance"].due_on,
                "currency": r["currency"],
                "payable": r["balance"].payable,
                "paid": r["balance"].paid,
                "remaining": r["balance"].remaining,
                "state": r["balance"].state,
                "overdue": False,
                "direction": r["direction"],
            }
            for r in rows
        ]
        return Response(
            {
                "side": "credits",
                "total": None,
                "overdue": None,
                "owed_to_customers": sum(
                    (r["amount"] for r in rows if r["direction"] == "owe_customer"), payments.ZERO
                ),
                "owed_by_suppliers": sum(
                    (r["amount"] for r in rows if r["direction"] == "owed_by_supplier" and r["currency"] == "EUR"),
                    payments.ZERO,
                ),
                "items": InvoiceOpenItemSerializer(items, many=True).data,
            }
        )


# --- EÜR, archive, export, procedure documentation -------------------------------------------------------------------


class _BooksView(ModuleAPIView):
    """The settings (read; write for a change) and both price rights – the whole books of the company."""

    module = Module.ADMINISTRATION
    schema_tag = "accounting"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Refuse callers who may not see the books before anything happens."""
        super().initial(request, *args, **kwargs)
        if not outgoing.may_see_euer(self.rights):
            raise PermissionDenied


class EuerRowSerializer(serializers.Serializer):
    """A line of the EÜR."""

    label = serializers.CharField()
    net = serializers.CharField(help_text="A small business: gross.")
    tax = serializers.CharField()
    count = serializers.IntegerField()


class EuerSerializer(serializers.Serializer):
    """The EÜR of a year."""

    year = serializers.IntegerField()
    small_business = serializers.BooleanField()
    income = EuerRowSerializer(many=True)
    expenses = EuerRowSerializer(many=True)
    depreciation = inline_serializer("EuerSum", {"net": serializers.CharField(), "count": serializers.IntegerField()})
    disposals = inline_serializer(
        "EuerDisposals", {"net": serializers.CharField(), "count": serializers.IntegerField()}
    )
    income_net = serializers.CharField()
    expense_net = serializers.CharField()
    total_expense = serializers.CharField()
    profit = serializers.CharField(help_text="The result without turnover tax.")
    surplus = serializers.CharField(
        help_text="The surplus as the EÜR counts it: with turnover tax received, input tax and payments to the tax office."
    )
    tax_collected = serializers.CharField()
    input_tax = serializers.CharField()
    tax_balance = serializers.CharField()
    tax_office_vat = serializers.CharField()
    tax_office_income = serializers.CharField()
    vat_still_owed = serializers.CharField()
    warnings = serializers.ListField(child=serializers.CharField())
    entry_count = serializers.IntegerField()


class EuerView(_BooksView):
    """``GET /accounting/euer?year=`` – the EÜR of a year, prepared for the tax adviser (DOK-045)."""

    @extend_schema(
        parameters=[OpenApiParameter("year", OpenApiTypes.INT, description="Default: the current year.")],
        responses=EuerSerializer,
    )
    def get(self, request: Request) -> Response:
        """Income, expenses, depreciation and the profit; no tax advice."""
        raw = request.query_params.get("year")
        if raw not in (None, "") and not str(raw).isdigit():
            raise ApiValidationError({"year": "A year, e.g. 2026."})
        if raw not in (None, "") and not euer.FIRST_YEAR <= int(str(raw)) <= euer.LAST_YEAR:
            raise ApiValidationError({"year": f"Between {euer.FIRST_YEAR} and {euer.LAST_YEAR}."})
        year = euer.parse_year(raw, timezone.localdate().year)
        return Response(EuerSerializer(euer.compute(year).as_json()).data)


class ArchiveSerializer(serializers.Serializer):
    """The state of the archive of vouchers."""

    total = serializers.IntegerField()
    documents = serializers.IntegerField()
    incoming = serializers.IntegerField()
    ok = serializers.IntegerField()
    changed = serializers.IntegerField()
    missing = serializers.IntegerField()
    deleted = serializers.IntegerField()
    unchecked = serializers.IntegerField()
    pending = serializers.IntegerField(help_text="Vouchers that the next night archives.")
    last_checked_at = serializers.DateTimeField(allow_null=True)
    problems = serializers.ListField(child=serializers.DictField(child=serializers.CharField(allow_blank=True)))


class ArchiveView(_BooksView):
    """``GET /accounting/archive`` – the archive of vouchers (DOK-043)."""

    @extend_schema(responses=ArchiveSerializer)
    def get(self, request: Request) -> Response:
        """The numbers and the vouchers whose files changed or are missing."""
        info = archive.summary()
        info["problems"] = [
            {"source": r.source, "reference": r.reference, "status": r.status, "finding": r.finding}
            for r in archive.problems()[:100]
        ]
        return Response(ArchiveSerializer(info).data)


class ArchiveVerifyView(_BooksView):
    """``POST /accounting/archive/verify`` – archive what is new and check all files now."""

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "ArchiveVerified",
            {
                "registered": serializers.IntegerField(),
                "checked": serializers.IntegerField(),
                "problems": serializers.IntegerField(),
            },
        ),
    )
    def post(self, request: Request) -> Response:
        """Write access to the settings is checked by the module."""
        result = archive.run(everything=True)
        return Response({"registered": result.registered, "checked": result.checked, "problems": result.problems})


class AuditExportView(_BooksView):
    """``GET /accounting/audit-export?year=`` – the ZIP for an audit (DOK-046)."""

    @extend_schema(
        parameters=[
            OpenApiParameter("year", OpenApiTypes.STR, description="A year or ``all``. Default: the current year.")
        ],
        responses={(200, "application/zip"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request) -> HttpResponse:
        """Tables as CSV with ``index.xml``, the vouchers and ``SHA256SUMS``."""
        raw = request.query_params.get("year", "")
        if raw not in ("", "all") and not str(raw).isdigit():
            raise ApiValidationError({"year": "A year or all."})
        year = None if raw == "all" else euer.parse_year(raw, timezone.localdate().year)
        name = f"pruefexport-{year if year else 'alle'}.zip"
        return FileResponse(audit_export.build(year), as_attachment=True, filename=name, content_type="application/zip")

    @extend_schema(
        request=inline_serializer(
            "AuditExportStart", {"year": serializers.CharField(required=False, help_text="A year or all.")}
        ),
        responses={202: JobSerializer},
    )
    def post(self, request: Request) -> Response:
        """Make the ZIP as a task in the background (DOK-054); the answer is the task, ``/jobs/{id}/result`` the file.

        For a large archive: the request returns at once, the task writes the ZIP and notifies the caller.
        """
        raw = str(body_of(request).get("year", ""))
        if raw not in ("", "all") and not raw.isdigit():
            raise ApiValidationError({"year": "A year or all."})
        year = None if raw == "all" else euer.parse_year(raw, timezone.localdate().year)
        job = audit_export.start(year, user=request.user)
        job.refresh_from_db()
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ProcedureView(_BooksView):
    """``GET /accounting/procedure`` – the procedure documentation (DOK-046), as JSON or with ``as=pdf`` / ``as=md``."""

    @extend_schema(
        parameters=[OpenApiParameter("as", OpenApiTypes.STR, enum=["json", "pdf", "md"], description="Default: json.")],
        responses=inline_serializer(
            "Procedure",
            {
                "sections": serializers.ListField(
                    child=inline_serializer(
                        "ProcedureSection",
                        {
                            "heading": serializers.CharField(),
                            "paragraphs": serializers.ListField(child=serializers.CharField()),
                            "facts": serializers.ListField(child=serializers.ListField(child=serializers.CharField())),
                        },
                    )
                )
            },
        ),
    )
    def get(self, request: Request) -> Response | HttpResponse:
        """The chapters filled from the settings of the installation."""
        kind = request.query_params.get("as", "json")
        if kind == "pdf":
            return HttpResponse(procedure.render_pdf(), content_type="application/pdf")
        if kind == "md":
            return HttpResponse(procedure.as_markdown(), content_type="text/markdown; charset=utf-8")
        if kind != "json":
            raise ApiValidationError({"as": "One of json, pdf, md."})
        return Response(
            {
                "sections": [
                    {"heading": s.heading, "paragraphs": s.paragraphs, "facts": [list(f) for f in s.facts]}
                    for s in procedure.sections()
                ]
            }
        )
