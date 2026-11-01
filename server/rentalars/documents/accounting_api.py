# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the accounting: Lexware Office (DOK-011) and the DATEV export (DOK-012).

The same rights as in the browser (``accounting_views``): the settings, the
list of handings over and the DATEV files need the module "Administration"
(read; write for changes) and the price right. A single document is handed
over by whoever may make it (write access to the project and the price
right) or may change the settings and see prices.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.api.permissions import AUTHENTICATED_ONLY
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.documents import datev, lexware
from rentalars.documents.models import AccountingSettings, Document, LexwareTransfer, TransferState
from rentalars.projects.access import ProjectAccess, access_level


class AccountingSettingsSerializer(CleanModelSerializer):
    """How invoices reach the accounting. The API key is only written, never returned (DOK-011, DOK-012)."""

    lexware_api_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="The API key of Lexware Office. Only written, never returned; empty or left out keeps the key.",
    )
    lexware_api_key_set = serializers.SerializerMethodField()
    lexware_categories = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text='Posting category per tax rate, e.g. {"0": "<id>"}; rates left out take "Einnahmen".',
    )
    lexware_category_choices = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        read_only=True,
        help_text="The income categories Lexware Office named at the last check (id, name).",
    )
    datev_revenue_accounts = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text='Revenue account per tax rate, e.g. {"19": "8400"}; rates left out take the default of the chart.',
    )
    datev_effective_revenue_accounts = serializers.SerializerMethodField()

    class Meta:
        model = AccountingSettings
        fields = [
            "lexware_enabled",
            "lexware_api_key",
            "lexware_api_key_set",
            "lexware_api_key_hint",
            "lexware_automatic",
            "lexware_collective_contact",
            "lexware_categories",
            "lexware_category_choices",
            "lexware_organization",
            "lexware_checked_at",
            "datev_consultant_number",
            "datev_client_number",
            "datev_fiscal_year_start",
            "datev_account_length",
            "datev_chart",
            "datev_revenue_accounts",
            "datev_effective_revenue_accounts",
            "datev_debitor_mode",
            "datev_debitor_offset",
            "datev_collective_account",
            "invoice_format",
            "einvoice_blocks",
            "small_business",
            "retention_invoice_years",
            "retention_letter_years",
            "archive_check_days",
        ]
        read_only_fields = ["lexware_api_key_hint", "lexware_organization", "lexware_checked_at"]

    def get_lexware_api_key_set(self, accounting: AccountingSettings) -> bool:
        """Whether an API key is stored."""
        return accounting.has_lexware_api_key

    def get_datev_effective_revenue_accounts(self, accounting: AccountingSettings) -> dict[str, str]:
        """The revenue account each tax rate is booked on: entered or the default of the chart."""
        from rentalars.documents.accounting_forms import tax_rate_keys

        return {
            key: accounting.revenue_account_for(key)
            for key in tax_rate_keys(accounting)
            if accounting.revenue_account_for(key)
        }

    def update(self, instance: AccountingSettings, validated_data: dict[str, Any]) -> AccountingSettings:
        """Store a new key encrypted, then the rest by the rules of the model."""
        key = validated_data.pop("lexware_api_key", "")
        if key:
            instance.set_lexware_api_key(key)
        return super().update(instance, validated_data)


class _AccountingView(ModuleAPIView):
    """The module "Administration" by method, and always the price right (AUT-019)."""

    module = Module.ADMINISTRATION
    schema_tag = "accounting"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Refuse callers without the price right before anything happens."""
        super().initial(request, *args, **kwargs)
        if not self.rights.has(SpecialRight.PRICES):
            raise PermissionDenied


class AccountingSettingsView(_AccountingView):
    """``/accounting/settings`` – Lexware Office and DATEV (DOK-011, DOK-012)."""

    @extend_schema(responses=AccountingSettingsSerializer)
    def get(self, request: Request) -> Response:
        """The settings, without the API key."""
        return Response(AccountingSettingsSerializer(AccountingSettings.load()).data)

    @extend_schema(request=AccountingSettingsSerializer, responses=AccountingSettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change single settings; the key is only replaced when a new one is sent."""
        current = AccountingSettings.load()
        serializer = AccountingSettingsSerializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AccountingSettingsSerializer(current).data)


class LexwareCheckView(_AccountingView):
    """``POST /accounting/lexware/check`` – does the key work? Fetches the income categories (DOK-011)."""

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                "LexwareCheck",
                {
                    "organization": serializers.CharField(),
                    "tax_type": serializers.CharField(),
                    "small_business": serializers.BooleanField(),
                    "categories": serializers.ListField(child=serializers.DictField(child=serializers.CharField())),
                },
            )
        },
    )
    def post(self, request: Request) -> Response:
        """Ask Lexware Office for the account; 400 with the reason if that fails."""
        try:
            result = lexware.check_connection()
        except lexware.LexwareError as error:
            raise ValidationError(str(error)) from error
        return Response(
            {
                "organization": result.organization,
                "tax_type": result.tax_type,
                "small_business": result.small_business,
                "categories": result.categories,
            }
        )


#: The states of a handing over in the API; "none" when the document was never handed over.
TRANSFER_STATES = ["none", *TransferState.values]


class LexwareTransferSerializer(serializers.Serializer):
    """What became of a document in Lexware Office (DOK-011)."""

    document = serializers.IntegerField()
    number = serializers.CharField()
    transfer_state = serializers.ChoiceField(choices=TRANSFER_STATES)
    voucher_id = serializers.CharField(help_text="The voucher in Lexware Office.")
    contact_id = serializers.CharField(help_text="The contact the voucher is booked on; empty: collective contact.")
    pdf_uploaded = serializers.BooleanField()
    transferred_at = serializers.DateTimeField(allow_null=True)
    requested_at = serializers.DateTimeField(allow_null=True)
    attempts = serializers.IntegerField()
    error = serializers.CharField(help_text="Why the last attempt failed; empty if it did not.")
    error_code = serializers.CharField(
        help_text="auth, rate_limit, rejected, contact_conflict, voucher_conflict, unreachable, server or other."
    )


def transfer_data(document: Document, transfer: LexwareTransfer | None) -> dict[str, Any]:
    """The answer for one document."""
    if transfer is None:
        return {
            "document": document.pk,
            "number": document.number,
            "transfer_state": "none",
            "voucher_id": "",
            "contact_id": "",
            "pdf_uploaded": False,
            "transferred_at": None,
            "requested_at": None,
            "attempts": 0,
            "error": "",
            "error_code": "",
        }
    return {
        "document": document.pk,
        "number": document.number,
        "transfer_state": transfer.state,
        "voucher_id": transfer.voucher_id,
        "contact_id": transfer.contact_id,
        "pdf_uploaded": transfer.pdf_uploaded,
        "transferred_at": transfer.transferred_at,
        "requested_at": transfer.requested_at,
        "attempts": transfer.attempts,
        "error": transfer.error,
        "error_code": transfer.error_code,
    }


class LexwareTransferListView(_AccountingView):
    """``GET /accounting/lexware/transfers`` – the handings over, those that need attention first (DOK-011)."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "state",
                str,
                enum=TransferState.values,
                description="Only these; without: all that are not handed over yet (waiting, running, failed).",
            )
        ],
        responses=LexwareTransferSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        """At most 500, the latest change first."""
        transfers = LexwareTransfer.objects.select_related("document").order_by("-updated_at", "-pk")
        wanted = request.query_params.get("state", "")
        if wanted:
            if wanted not in TransferState.values:
                raise ValidationError({"state": "Unknown state."})
            transfers = transfers.filter(state=wanted)
        else:
            transfers = transfers.exclude(state=TransferState.DONE)
        return Response(
            LexwareTransferSerializer(
                [transfer_data(transfer.document, transfer) for transfer in transfers[:500]], many=True
            ).data
        )


class DocumentLexwareView(ModuleAPIView):
    """``/documents/{id}/lexware`` – the state in Lexware Office; ``POST`` hands the document over (DOK-011)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "accounting"

    def _document(self, request: Request, pk: int, *, write: bool) -> Document:
        document = get_object_or_404(Document.objects.select_related("project"), pk=pk)
        rights = self.rights
        if not rights.has(SpecialRight.PRICES):
            raise PermissionDenied
        if rights.has_level(Module.ADMINISTRATION, Level.WRITE if write else Level.READ):
            return document
        if document.project_id is None:
            # Free outgoing documents: no project – the rights of the list, or of changing it.
            from rentalars.documents import free, outgoing

            if not (free.may_change(rights) if write else outgoing.may_see(rights)):
                raise PermissionDenied
            return document
        if access_level(rights, request.user, document.project) < (ProjectAccess.EDIT if write else ProjectAccess.READ):
            raise PermissionDenied
        return document

    @extend_schema(responses=LexwareTransferSerializer)
    def get(self, request: Request, pk: int) -> Response:
        """Handed over, waiting, failed – or "none"."""
        document = self._document(request, pk, write=False)
        return Response(LexwareTransferSerializer(transfer_data(document, lexware.transfer_of(document))).data)

    @extend_schema(
        request=inline_serializer(
            "LexwareTransferRequest",
            {
                "new_contact": serializers.BooleanField(
                    required=False,
                    help_text="Create the customer as a new contact instead of looking for its customer number.",
                )
            },
        ),
        responses={202: LexwareTransferSerializer},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Hand the invoice or cancellation over in the background; 400 if it is there already or on the way.

        DOK-014: 400 as well while invoices are switched off.
        """
        document = self._document(request, pk, write=True)
        new_contact = body_of(request).get("new_contact") in (True, "true", "1", 1)
        transfer = lexware.request_transfer(document, user=request.user, new_contact=new_contact)
        return Response(
            LexwareTransferSerializer(transfer_data(document, transfer)).data, status=status.HTTP_202_ACCEPTED
        )


PERIOD_PARAMETERS = [
    OpenApiParameter("from", OpenApiTypes.DATE, required=True, description="First day, YYYY-MM-DD"),
    OpenApiParameter("to", OpenApiTypes.DATE, required=True, description="Last day, YYYY-MM-DD"),
    OpenApiParameter(
        "include_historic",
        OpenApiTypes.BOOL,
        required=False,
        description="Also export invoices taken over from an old system (default: left out, they were booked there)",
    ),
]


def _period(request: Request) -> tuple[datetime.date | None, datetime.date | None]:
    def day(name: str) -> datetime.date | None:
        value = request.query_params.get(name, "")
        try:
            return datetime.date.fromisoformat(value) if value else None
        except ValueError as error:
            raise ValidationError({name: "Not a date of the form YYYY-MM-DD."}) from error

    return day("from"), day("to")


def _historic(request: Request) -> bool:
    """Legacy import: ``?include_historic=true`` also exports the invoices taken over from an old system."""
    return str(request.query_params.get("include_historic", "")).lower() in {"1", "true", "on", "yes"}


def _csv(result: datev.DatevFile) -> HttpResponse:
    response = HttpResponse(result.content, content_type="text/csv; charset=windows-1252")
    response["Content-Disposition"] = f'attachment; filename="{result.name}"'
    return response


class DatevBookingsView(_AccountingView):
    """``GET /accounting/datev/bookings`` – the Buchungsstapel of a period, DATEV format (DOK-012)."""

    @extend_schema(parameters=PERIOD_PARAMETERS, responses={(200, "text/csv"): OpenApiTypes.BINARY})
    def get(self, request: Request) -> HttpResponse:
        """Windows-1252, one booking per invoice and tax rate; 400 names every problem (DOK-014: invoices off)."""
        date_from, date_to = _period(request)
        datev.check_period(AccountingSettings.load(), date_from, date_to)
        return _csv(
            datev.bookings_file(date_from, date_to, user=request.user, include_historic=_historic(request))  # type: ignore[arg-type]
        )


class DatevDebitorsView(_AccountingView):
    """``GET /accounting/datev/debitors`` – the customers of the invoices of a period as debitors (DOK-012)."""

    @extend_schema(parameters=PERIOD_PARAMETERS, responses={(200, "text/csv"): OpenApiTypes.BINARY})
    def get(self, request: Request) -> HttpResponse:
        """Windows-1252, one account per customer; 400 with one collective debitor account."""
        date_from, date_to = _period(request)
        datev.check_period(AccountingSettings.load(), date_from, date_to)
        return _csv(
            datev.debitors_file(date_from, date_to, user=request.user, include_historic=_historic(request))  # type: ignore[arg-type]
        )
