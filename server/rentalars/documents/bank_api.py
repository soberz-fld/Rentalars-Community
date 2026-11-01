# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the bank statements (DOK-050; API-002, API-014).

* ``GET /accounting/bank/transactions`` – the transactions of the statements read in (``state``: ``open`` (default), ``booked``,
  ``ignored``, ``all``), with the suggestions for the open ones; ``limit`` and ``offset``.
* ``POST /accounting/bank/transactions/{id}/book`` – enter the payment at the invoice the caller names (``side``, ``invoice``).
* ``POST /accounting/bank/transactions/{id}/ignore`` (with a ``reason``) and ``…/restore`` – set aside, take back.
* ``GET|POST /accounting/bank/imports`` – the statements read in; read a CAMT.053 or CSV file in (``multipart``, field ``file``).

Rights as for the page: ``bank.may_use`` to look, ``bank.may_change`` to read in, book and set aside – both sides of the books.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.views import ModuleAPIView
from rentalars.documents import bank
from rentalars.documents.bank_views import STATES, filtered
from rentalars.documents.models import BankImport, BankTransaction

MAX_LIMIT = 200


class SuggestionSerializer(serializers.Serializer):
    """An open invoice a transaction may belong to."""

    side = serializers.ChoiceField(choices=[bank.OUTGOING, bank.INCOMING])
    invoice = serializers.IntegerField(help_text="Id of the outgoing document or the incoming invoice.")
    number = serializers.CharField()
    party = serializers.CharField(allow_blank=True)
    remaining = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, help_text="The amount of the payment that booking would enter."
    )
    score = serializers.IntegerField()
    reasons = serializers.ListField(child=serializers.CharField())


class TransactionSerializer(serializers.Serializer):
    """A transaction of a statement."""

    id = serializers.IntegerField()
    statement = serializers.IntegerField()
    booked_on = serializers.DateField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, help_text="Negative: money left the account.")
    currency = serializers.CharField()
    counterparty = serializers.CharField(allow_blank=True)
    counterparty_iban = serializers.CharField(allow_blank=True)
    purpose = serializers.CharField(allow_blank=True)
    end_to_end_id = serializers.CharField(allow_blank=True)
    state = serializers.ChoiceField(choices=["open", "booked", "ignored"])
    ignore_reason = serializers.CharField(allow_blank=True)
    side = serializers.CharField(allow_null=True, help_text="``outgoing`` or ``incoming`` once booked.")
    invoice = serializers.IntegerField(allow_null=True, help_text="Id of the invoice it was booked at.")
    payment = serializers.IntegerField(allow_null=True)
    suggestions = SuggestionSerializer(many=True)


class TransactionPageSerializer(serializers.Serializer):
    """A page of transactions."""

    count = serializers.IntegerField()
    results = TransactionSerializer(many=True)


class StatementSerializer(serializers.Serializer):
    """A bank statement that was read in."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    file_format = serializers.CharField()
    account_iban = serializers.CharField(allow_blank=True)
    first_day = serializers.DateField(allow_null=True)
    last_day = serializers.DateField(allow_null=True)
    imported_at = serializers.DateTimeField()
    new_count = serializers.IntegerField()
    skipped_count = serializers.IntegerField()


class UploadSerializer(serializers.Serializer):
    """The file of the bank."""

    file = serializers.FileField()


class BookInput(serializers.Serializer):
    """The invoice to enter the payment at."""

    side = serializers.ChoiceField(choices=[bank.OUTGOING, bank.INCOMING])
    invoice = serializers.IntegerField()


class IgnoreInput(serializers.Serializer):
    """Why a transaction is set aside."""

    reason = serializers.CharField(max_length=250)


def _suggestion_data(suggestion: bank.Suggestion) -> dict[str, Any]:
    candidate = suggestion.candidate
    return {
        "side": candidate.side,
        "invoice": candidate.target.pk,
        "number": candidate.number,
        "party": candidate.party,
        "remaining": candidate.remaining,
        "amount": suggestion.amount,
        "score": suggestion.score,
        "reasons": list(suggestion.reasons),
    }


def transaction_data(tx: BankTransaction, found: list[bank.Suggestion] | None = None) -> dict[str, Any]:
    """The transaction as the API shows it."""
    state = tx.state
    payment = tx.payment if state == "booked" else None
    side = None
    invoice = None
    if payment is not None:
        side = bank.OUTGOING if tx.outgoing_payment_id else bank.INCOMING
        invoice = payment.document_id if side == bank.OUTGOING else payment.invoice_id
    return {
        "id": tx.pk,
        "statement": tx.bank_import_id,
        "booked_on": tx.booked_on,
        "amount": tx.amount,
        "currency": tx.currency,
        "counterparty": tx.counterparty,
        "counterparty_iban": tx.counterparty_iban,
        "purpose": tx.purpose,
        "end_to_end_id": tx.end_to_end_id,
        "state": state,
        "ignore_reason": tx.ignore_reason,
        "side": side,
        "invoice": invoice,
        "payment": payment.pk if payment is not None else None,
        "suggestions": [_suggestion_data(s) for s in found or []],
    }


class _BankView(ModuleAPIView):
    module = Module.PROJECTS
    schema_tag = "accounting"
    change = False

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """403 without the rights of the page, before anything is looked up."""
        super().initial(request, *args, **kwargs)
        if not (bank.may_change(self.rights) if request.method not in ("GET", "HEAD") else bank.may_use(self.rights)):
            raise PermissionDenied


class TransactionListView(_BankView):
    """``GET /accounting/bank/transactions``."""

    @extend_schema(
        parameters=[
            OpenApiParameter("state", OpenApiTypes.STR, enum=list(STATES), description="Default: open."),
            OpenApiParameter("limit", OpenApiTypes.INT, description=f"Up to {MAX_LIMIT}; default 100."),
            OpenApiParameter("offset", OpenApiTypes.INT),
            OpenApiParameter("suggestions", OpenApiTypes.BOOL, description="Default true; false skips the matching."),
        ],
        responses=TransactionPageSerializer,
        operation_id="bank_transactions_list",
    )
    def get(self, request: Request) -> Response:
        """The transactions, open first by default; the open ones come with the invoices they may belong to."""
        state = request.query_params.get("state", "open")
        if state not in STATES:
            raise ApiValidationError({"state": f"One of {', '.join(STATES)}."})
        try:
            limit = min(int(request.query_params.get("limit", 100)), MAX_LIMIT)
            offset = int(request.query_params.get("offset", 0))
        except ValueError as error:
            raise ApiValidationError({"limit": "A number."}) from error
        if limit < 1 or offset < 0:
            raise ApiValidationError({"limit": "Positive numbers."})
        queryset = filtered(state)
        rows = list(queryset[offset : offset + limit])
        with_suggestions = request.query_params.get("suggestions", "true").lower() not in {"0", "false", "no"}
        candidates = bank.load_candidates() if with_suggestions and any(r.state == "open" for r in rows) else []
        results = [
            transaction_data(tx, bank.suggestions(tx, candidates) if tx.state == "open" else None) for tx in rows
        ]
        return Response(TransactionPageSerializer({"count": queryset.count(), "results": results}).data)


class _TransactionView(_BankView):
    def transaction(self, pk: int) -> BankTransaction:
        return get_object_or_404(BankTransaction.objects.select_related("bank_import"), pk=pk)


class TransactionBookView(_TransactionView):
    """``POST /accounting/bank/transactions/{id}/book``."""

    @extend_schema(request=BookInput, responses={200: TransactionSerializer}, operation_id="bank_transaction_book")
    def post(self, request: Request, pk: int) -> Response:
        """Enter the payment of the transaction at the named invoice; 400 if it is booked or set aside already."""
        form = BookInput(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            tx = bank.book(
                self.transaction(pk), form.validated_data["side"], form.validated_data["invoice"], user=request.user
            )
        except ValidationError as error:
            raise ApiValidationError(serializers.as_serializer_error(error)) from error
        tx = BankTransaction.objects.select_related("outgoing_payment", "incoming_payment").get(pk=tx.pk)
        return Response(TransactionSerializer(transaction_data(tx)).data)


class TransactionIgnoreView(_TransactionView):
    """``POST /accounting/bank/transactions/{id}/ignore``."""

    @extend_schema(request=IgnoreInput, responses={200: TransactionSerializer}, operation_id="bank_transaction_ignore")
    def post(self, request: Request, pk: int) -> Response:
        """Set a transaction aside with a reason; 400 without one."""
        form = IgnoreInput(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            tx = bank.ignore(self.transaction(pk), reason=form.validated_data["reason"], user=request.user)
        except ValidationError as error:
            raise ApiValidationError(serializers.as_serializer_error(error)) from error
        return Response(TransactionSerializer(transaction_data(tx)).data)


class TransactionRestoreView(_TransactionView):
    """``POST /accounting/bank/transactions/{id}/restore``."""

    @extend_schema(request=None, responses={200: TransactionSerializer}, operation_id="bank_transaction_restore")
    def post(self, request: Request, pk: int) -> Response:
        """Take an ignored transaction back; 400 if it is not ignored."""
        try:
            tx = bank.restore(self.transaction(pk))
        except ValidationError as error:
            raise ApiValidationError(serializers.as_serializer_error(error)) from error
        return Response(TransactionSerializer(transaction_data(tx)).data)


class StatementListView(_BankView):
    """``/accounting/bank/imports`` – the statements read in, and reading a file in."""

    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @extend_schema(responses=StatementSerializer(many=True), operation_id="bank_imports_list")
    def get(self, request: Request) -> Response:
        """The statements read in, the latest first."""
        return Response(StatementSerializer(BankImport.objects.all()[:200], many=True).data)

    @extend_schema(
        request={"multipart/form-data": UploadSerializer},
        responses={201: StatementSerializer},
        operation_id="bank_imports_create",
    )
    def post(self, request: Request) -> Response:
        """Read a CAMT.053 or CSV file in; 400 if it is none, is too large, or was read in before."""
        form = UploadSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        upload = form.validated_data["file"]
        if upload.size > bank.MAX_BYTES:
            raise ApiValidationError({"file": "The file is too large."})
        try:
            created = bank.import_file(upload.read(), upload.name or "", user=request.user)
        except bank.BankFileError as error:
            raise ApiValidationError({"file": str(error)}) from error
        except ValidationError as error:
            raise ApiValidationError({"file": error.messages}) from error
        return Response(StatementSerializer(created).data, status=status.HTTP_201_CREATED)
