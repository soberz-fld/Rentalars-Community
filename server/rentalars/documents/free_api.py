# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the outgoing documents without a project (API-002).

The requirement: offers, invoices and so on can be made independently of projects and service cases.

A document without a project is made in two steps, as in the browser (:mod:`rentalars.documents.free`): a draft is
filled with lines, then issued.

* ``GET/POST /accounting/documents/drafts`` – the open drafts; make one (``kind``: ``offer``,
  ``order_confirmation``, ``invoice``; ``customer``; ``lines`` may be sent along).
* ``GET/PATCH/DELETE /accounting/documents/drafts/{id}`` – one draft with its lines and totals; change its header and
  texts; throw it away.
* ``POST /accounting/documents/drafts/{id}/lines`` – add a line (free, from a ``product``, or a text line);
  ``PATCH/DELETE .../lines/{line}`` change or remove one; ``POST .../lines/order`` sets the order.
* ``POST /accounting/documents/drafts/{id}/preview`` – the PDF as it would come out, marked as draft.
* ``POST /accounting/documents/drafts/{id}/issue`` – issue it: the number from the shared range, the PDF and for an
  invoice the XRechnung. The answer is the document (``project`` is ``null``); fetch it from ``/documents/{id}``,
  ``/documents/{id}/pdf`` and cancel an invoice with ``/documents/{id}/cancel``.
* ``POST /accounting/documents/{id}/send`` – send a document without a project by mail with its PDF attached.

Rights: the module Projects, the price right and read access to every project to look; write access to every
project to make, change, issue, send or cancel (:func:`rentalars.documents.free.may_change`); else 403.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.pagination import StandardPagination
from rentalars.api.views import ModuleAPIView
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress
from rentalars.documents import free, free_mail
from rentalars.documents.api import DocumentSerializer
from rentalars.documents.models import FREE_KINDS, Document, DocumentDraft, DraftLine
from rentalars.masterdata.models import TaxRate, Unit
from rentalars.products.models import Product


class DraftLineSerializer(serializers.ModelSerializer):
    """A line of a draft; ``amount`` is net after the discount, ``null`` for a text line."""

    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
        allow_null=True,
        help_text="Net after the discount; null for a text line.",
    )

    class Meta:
        model = DraftLine
        fields = [
            "id",
            "position",
            "product",
            "title",
            "note",
            "quantity",
            "unit",
            "unit_price",
            "tax_rate",
            "discount_percent",
            "is_text",
            "amount",
        ]
        read_only_fields = fields

    def to_representation(self, instance: DraftLine) -> dict[str, Any]:
        """The line with its amount (quantity × price less the discount)."""
        data = super().to_representation(instance)
        data["amount"] = None if instance.is_text else str(free.calculate([instance]).lines[0].amount)
        return data


class LineInputSerializer(serializers.Serializer):
    """What a line is made of. From a ``product`` the title, unit, price and tax rate start as the product's."""

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True, owner__isnull=True),
        required=False,
        allow_null=True,
        help_text="A product of the catalogue; services, vehicles and surcharges cannot be priced this way.",
    )
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True, help_text="Printed under the title.")
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, min_value=Decimal("0"))
    unit = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(), required=False, allow_null=True)
    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal("0"), help_text="Net."
    )
    tax_rate = serializers.PrimaryKeyRelatedField(queryset=TaxRate.objects.all(), required=False)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, min_value=Decimal("0"), max_value=Decimal("100")
    )
    is_text = serializers.BooleanField(required=False, help_text="A line of text only: no quantity, no amount.")


class DraftSerializer(serializers.ModelSerializer):
    """A draft of an outgoing document without a project, with its lines, totals and what stops issuing it."""

    lines = DraftLineSerializer(many=True, read_only=True)
    text_blocks = serializers.ListField(source="text_block_ids", child=serializers.IntegerField(), read_only=True)
    net_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    tax_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    gross_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    problems = serializers.ListField(
        child=serializers.CharField(), read_only=True, help_text="Why the draft cannot be issued yet; empty if it can."
    )

    class Meta:
        model = DocumentDraft
        fields = [
            "id",
            "kind",
            "customer",
            "billing_address",
            "contact",
            "issued_on",
            "payment_terms_days",
            "valid_until",
            "service_start",
            "service_end",
            "reference",
            "introduction",
            "closing",
            "text_blocks",
            "print_product_descriptions",
            "lines",
            "net_total",
            "tax_total",
            "gross_total",
            "problems",
            "created_at",
            "changed_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance: DocumentDraft) -> dict[str, Any]:
        """The draft with its lines and totals; the lines are read and added up once."""
        lines = free.lines_of(instance)
        calculation = free.calculate(lines)
        data = super().to_representation(instance)
        data["lines"] = DraftLineSerializer(lines, many=True, context={"calculation": calculation}).data
        data["net_total"] = str(calculation.net_total)
        data["tax_total"] = str(calculation.tax_total)
        data["gross_total"] = str(calculation.gross_total)
        data["problems"] = free.problems(instance)
        return data


class DraftChangeSerializer(serializers.Serializer):
    """The header and the texts of a draft."""

    # Only billing addresses, as the browser offers; that it is one of the customer's own is checked with the draft.
    billing_address = serializers.PrimaryKeyRelatedField(
        queryset=CustomerAddress.objects.filter(kind=AddressKind.BILLING), required=False, allow_null=True
    )
    contact = serializers.PrimaryKeyRelatedField(queryset=Contact.objects.all(), required=False, allow_null=True)
    issued_on = serializers.DateField(required=False, allow_null=True, help_text="Null: the day it is issued.")
    payment_terms_days = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=365)
    valid_until = serializers.DateField(required=False, allow_null=True, help_text="Offers only.")
    service_start = serializers.DateField(required=False, allow_null=True, help_text="Invoices only.")
    service_end = serializers.DateField(required=False, allow_null=True, help_text="Invoices only.")
    reference = serializers.CharField(
        max_length=200, required=False, allow_blank=True, help_text="Printed as subject line."
    )
    introduction = serializers.CharField(required=False, allow_blank=True)
    closing = serializers.CharField(required=False, allow_blank=True)
    text_blocks = serializers.ListField(child=serializers.IntegerField(), required=False)
    print_product_descriptions = serializers.BooleanField(
        required=False,
        allow_null=True,
        help_text="Print the description of each product under its position. Null at creation: as the template "
        "of the kind says.",
    )

    #: The fields that go to the service as they are named here; ``text_blocks`` is stored as ``text_block_ids``.
    RENAMED = {"text_blocks": "text_block_ids"}

    def values(self) -> dict[str, Any]:
        """The validated data under the names of :data:`rentalars.documents.free.DRAFT_FIELDS`."""
        return {self.RENAMED.get(name, name): value for name, value in self.validated_data.items()}


class DraftCreateSerializer(DraftChangeSerializer):
    """A new draft: kind and customer, the header and the texts, and the lines."""

    kind = serializers.ChoiceField(choices=[str(kind) for kind in FREE_KINDS])
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    lines = LineInputSerializer(many=True, required=False)

    def values(self) -> dict[str, Any]:
        """The header and texts for ``create_draft``; kind, customer and lines are passed separately."""
        values = super().values()
        for name in ("kind", "customer", "lines"):
            values.pop(name, None)
        return values


class LineOrderSerializer(serializers.Serializer):
    """The lines of a draft in the wished order."""

    lines = serializers.ListField(child=serializers.IntegerField(), help_text="IDs of the lines, first to last.")


class SendSerializer(serializers.Serializer):
    """The mail with a document."""

    to = serializers.CharField(max_length=500, help_text="Addresses separated by commas.")
    cc = serializers.CharField(max_length=500, required=False, allow_blank=True)
    bcc = serializers.CharField(max_length=500, required=False, allow_blank=True)
    subject = serializers.CharField(max_length=300, required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)
    signature = serializers.BooleanField(required=False, default=True)
    xml = serializers.BooleanField(required=False, default=False, help_text="Send the XRechnung along.")

    def validate_subject(self, value: str) -> str:
        """One line: white space and line breaks become single blanks."""
        return " ".join(value.split())


class _FreeView(ModuleAPIView):
    """Shared rights: looking needs ``free.may_see``, everything else ``free.may_change``."""

    module = Module.PROJECTS

    def check(self, *, change: bool) -> None:
        if not (free.may_change(self.rights) if change else free.may_see(self.rights)):
            raise PermissionDenied

    def draft(self, pk: int, *, change: bool) -> DocumentDraft:
        self.check(change=change)
        return get_object_or_404(DocumentDraft.objects.select_related("customer"), pk=pk)

    def line(self, pk: int, line_pk: int) -> DraftLine:
        draft = self.draft(pk, change=True)
        return get_object_or_404(
            DraftLine.objects.select_related("tax_rate", "unit", "product", "draft"), pk=line_pk, draft=draft
        )


def _line_values(data: dict[str, Any]) -> dict[str, Any]:
    """The validated data of a line for the service; nothing is sent that was not given."""
    return dict(data)


class DraftListView(_FreeView):
    """``/accounting/documents/drafts`` – the open drafts; ``POST`` makes one."""

    @extend_schema(responses=DraftSerializer(many=True), operation_id="accounting_drafts_list")
    def get(self, request: Request) -> Response:
        """The drafts, the newest change first, page by page (``page``, ``page_size``) like every list."""
        self.check(change=False)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(free.drafts_queryset(), request, view=self)
        return paginator.get_paginated_response(DraftSerializer(page or [], many=True).data)

    @extend_schema(
        request=DraftCreateSerializer, responses={201: DraftSerializer}, operation_id="accounting_drafts_create"
    )
    def post(self, request: Request) -> Response:
        """Make a draft, with its lines if they are sent along; the number is used only when it is issued."""
        self.check(change=True)
        serializer = DraftCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        values = serializer.values()
        draft = free.create_draft(data["customer"], data["kind"], user=request.user, **values)
        try:
            for line in data.get("lines", []):
                free.add_line(draft, **_line_values(line))
        except Exception:
            free.delete_draft(draft)
            raise
        return Response(DraftSerializer(draft).data, status=status.HTTP_201_CREATED)


class DraftDetailView(_FreeView):
    """``/accounting/documents/drafts/{id}`` – one draft; ``PATCH`` changes its header and texts; ``DELETE`` throws it away."""

    @extend_schema(responses=DraftSerializer, operation_id="accounting_drafts_retrieve")
    def get(self, request: Request, pk: int) -> Response:
        """The draft with its lines and totals."""
        return Response(DraftSerializer(self.draft(pk, change=False)).data)

    @extend_schema(request=DraftChangeSerializer, responses=DraftSerializer, operation_id="accounting_drafts_update")
    def patch(self, request: Request, pk: int) -> Response:
        """Change the header and the texts; the kind and the customer stay."""
        draft = self.draft(pk, change=True)
        serializer = DraftChangeSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        free.update_draft(draft, **serializer.values())
        return Response(DraftSerializer(draft).data)

    @extend_schema(responses={204: None}, operation_id="accounting_drafts_delete")
    def delete(self, request: Request, pk: int) -> Response:
        """Throw the draft away; no number was used."""
        free.delete_draft(self.draft(pk, change=True))
        return Response(status=status.HTTP_204_NO_CONTENT)


class DraftLineListView(_FreeView):
    """``POST /accounting/documents/drafts/{id}/lines`` – add a line."""

    @extend_schema(
        request=LineInputSerializer, responses={201: DraftLineSerializer}, operation_id="accounting_draft_lines_create"
    )
    def post(self, request: Request, pk: int) -> Response:
        """Add a line at the end: free, from a ``product``, or a text line (``is_text``)."""
        draft = self.draft(pk, change=True)
        serializer = LineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        line = free.add_line(draft, **_line_values(serializer.validated_data))
        return Response(DraftLineSerializer(line).data, status=status.HTTP_201_CREATED)


class DraftLineDetailView(_FreeView):
    """``/accounting/documents/drafts/{id}/lines/{line}`` – change or remove a line."""

    @extend_schema(
        request=LineInputSerializer, responses=DraftLineSerializer, operation_id="accounting_draft_lines_update"
    )
    def patch(self, request: Request, pk: int, line_pk: int) -> Response:
        """Change the texts, quantity, unit, price, tax rate or discount of a line."""
        line = self.line(pk, line_pk)
        serializer = LineInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = _line_values(serializer.validated_data)
        values.pop("product", None)
        values.pop("is_text", None)
        free.update_line(line, **values)
        return Response(DraftLineSerializer(line).data)

    @extend_schema(responses={204: None}, operation_id="accounting_draft_lines_delete")
    def delete(self, request: Request, pk: int, line_pk: int) -> Response:
        """Take the line out of the draft."""
        free.delete_line(self.line(pk, line_pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class DraftLineOrderView(_FreeView):
    """``POST /accounting/documents/drafts/{id}/lines/order`` – put the lines in order."""

    @extend_schema(request=LineOrderSerializer, responses=DraftSerializer, operation_id="accounting_draft_lines_order")
    def post(self, request: Request, pk: int) -> Response:
        """The lines named come first in this order; the others follow in their old order."""
        draft = self.draft(pk, change=True)
        serializer = LineOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        free.reorder_lines(draft, serializer.validated_data["lines"])
        return Response(DraftSerializer(draft).data)


class DraftPreviewView(_FreeView):
    """``POST /accounting/documents/drafts/{id}/preview`` – the PDF as it would come out."""

    @extend_schema(
        request=None,
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
        operation_id="accounting_drafts_preview",
    )
    def post(self, request: Request, pk: int) -> HttpResponse:
        """A PDF marked as draft; no number is used. 400 if the draft cannot be issued yet."""
        return HttpResponse(free.preview(self.draft(pk, change=False)), content_type="application/pdf")


class AlreadyIssued(exceptions.APIException):
    """The draft is gone because somebody issued it a moment before: 409."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "already_issued"
    default_detail = gettext_lazy("This draft was already issued or deleted.")


class DraftIssueView(_FreeView):
    """``POST /accounting/documents/drafts/{id}/issue`` – issue the draft."""

    @extend_schema(request=None, responses={201: DocumentSerializer}, operation_id="accounting_drafts_issue")
    def post(self, request: Request, pk: int) -> Response:
        """The document gets its number from the range of its kind; the draft is gone.

        400 if it cannot be issued, 409 if somebody issued it at the same moment.
        """
        try:
            document = free.issue(self.draft(pk, change=True), user=request.user)
        except DjangoValidationError as error:
            if getattr(error, "code", None) == "already_issued":
                raise AlreadyIssued(error.messages[0]) from error
            raise
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class DocumentSendView(_FreeView):
    """``POST /accounting/documents/{id}/send`` – send a document without a project by mail."""

    @extend_schema(request=SendSerializer, responses=DocumentSerializer, operation_id="accounting_documents_send")
    def post(self, request: Request, pk: int) -> Response:
        """The PDF goes along (the XRechnung with ``xml``); the document is noted as sent. 400: sending is not set up."""
        self.check(change=True)
        document = get_object_or_404(Document.objects.select_related("customer"), pk=pk, project__isnull=True)
        serializer = SendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        proposal = free_mail.initial_for(document)
        free_mail.send_document_mail(
            document,
            to=data["to"],
            cc=data.get("cc", ""),
            bcc=data.get("bcc", ""),
            subject=data.get("subject") or proposal["subject"],
            body=data.get("body") or proposal["body"],
            with_signature=data["signature"],
            with_xml=data["xml"],
            user=request.user,
        )
        document.refresh_from_db()
        return Response(DocumentSerializer(document).data)
