# SPDX-License-Identifier: GPL-3.0-or-later
"""API of Buchhaltung → Ausgangsbelege (DOK-020; API-002).

* ``GET /accounting/documents`` – the outgoing documents page by page, with
  the filters of the page: ``kind`` (a kind, ``bookable`` – invoices and
  cancellations –, ``monthly`` – monthly invoices of service cases; several
  separated by commas), ``state`` (``not_sent``, ``sent``, ``cancelled``,
  ``not_cancelled``), ``lexware`` (``done``, ``failed``, ``missing``),
  ``customer``, ``project`` (also the cases a monthly invoice bills),
  ``since`` and ``until`` (the document date, both included), ``q`` (number,
  title, project, customer); ``sort`` by ``issued_on`` (default, newest
  first), ``number``, ``kind``, ``project``, ``customer``, ``net_total``,
  ``gross_total``, ``due_on`` or ``sent_at``, ``-`` in front for the
  reverse order.
* ``GET /accounting/documents/totals`` – with the same filters: count, net,
  tax and gross per kind, and invoices with cancellations together.

The rights of the page (``outgoing.may_see``): the module Projects for every
project and the price right; else 403. The amounts are those stored with the
documents (DOK-007); the PDF is fetched from ``/documents/{id}/pdf``.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.pagination import StandardPagination
from rentalars.api.views import ModuleAPIView
from rentalars.core.money import money
from rentalars.documents import outgoing
from rentalars.documents.models import Document, DocumentKind, MonthlyStatement, TransferState
from rentalars.documents.outgoing_tables import KIND_ORDER

#: ``sort`` of the list: the fields each key sorts by.
SORTS: dict[str, tuple[Any, ...]] = {
    "issued_on": ("issued_on", "number"),
    "number": ("number",),
    "kind": (KIND_ORDER, "issued_on"),
    "project": ("project__number", "issued_on"),
    "customer": ("customer__name", "project__number", "issued_on"),
    "net_total": ("net_total", "number"),
    "gross_total": ("gross_total", "number"),
    "due_on": ("due_on", "number"),
    "sent_at": ("sent_at", "number"),
}


def _ordering(sort: str) -> list[Any]:
    """The ``order_by`` of a ``sort`` key; ``-`` in front reverses every field of it."""
    descending = sort.startswith("-")
    fields = SORTS.get(sort.lstrip("-"))
    if fields is None:
        raise ValidationError({"sort": f"Unknown sort key; one of {', '.join(SORTS)}, '-' in front to reverse."})
    ordering: list[Any] = []
    for name in fields:
        if isinstance(name, str):
            ordering.append(f"-{name}" if descending else name)
        else:
            ordering.append(name.desc() if descending else name.asc())
    return [*ordering, "-pk" if descending else "pk"]


class OutgoingDocumentSerializer(serializers.Serializer):
    """An outgoing document as the list shows it (DOK-020)."""

    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=[str(kind) for kind in outgoing.CUSTOMER_KINDS])
    kind_label = serializers.CharField()
    billing_type = serializers.CharField(
        allow_blank=True,
        help_text="Empty for an ordinary document; advance, partial, final (invoices) or credit "
        "(a partial credit note, kind cancellation).",
    )
    credit_for = serializers.IntegerField(allow_null=True, help_text="The invoice a partial credit note credits.")
    number = serializers.CharField()
    title = serializers.CharField()
    issued_on = serializers.DateField()
    due_on = serializers.DateField(allow_null=True)
    project = serializers.IntegerField(
        allow_null=True,
        help_text="DOK-016: of a monthly invoice its first service case. Null for a document made in "
        "Accounting without a project.",
    )
    project_number = serializers.CharField(allow_blank=True)
    project_name = serializers.CharField(allow_blank=True)
    reference = serializers.CharField(
        allow_blank=True, help_text="The subject line of a document made without a project."
    )
    customer = serializers.IntegerField(
        allow_null=True, help_text="The customer of the document; null: internal project."
    )
    customer_name = serializers.CharField()
    customer_number = serializers.CharField()
    recipient = serializers.CharField(help_text="The first line of the address as printed on the document.")
    net_total = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    tax_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, help_text="Gross minus net of the stored totals."
    )
    gross_total = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    state = serializers.ChoiceField(choices=list(outgoing.STATE_LABELS))
    sent_at = serializers.DateTimeField(allow_null=True)
    sent_to = serializers.CharField(allow_blank=True)
    cancels = serializers.IntegerField(allow_null=True)
    cancels_number = serializers.CharField(allow_null=True)
    cancelled_by = serializers.IntegerField(allow_null=True)
    cancelled_by_number = serializers.CharField(allow_null=True)
    billed_projects = serializers.ListField(
        child=serializers.IntegerField(), help_text="DOK-016: the service cases a monthly invoice bills."
    )
    statement = serializers.IntegerField(allow_null=True, help_text="DOK-016: the monthly statement it was made of.")
    statement_month = serializers.CharField(allow_null=True, help_text="e.g. 2027-03")
    lexware_state = serializers.CharField(
        allow_blank=True, help_text=f"DOK-011: {', '.join(TransferState.values)}; empty: not handed over."
    )
    lexware_transferred_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    created_by = serializers.IntegerField(allow_null=True)
    created_by_name = serializers.CharField(allow_blank=True)
    pdf_url = serializers.CharField()
    xml_url = serializers.CharField(allow_blank=True)


def document_rows(documents: list[Document]) -> list[dict[str, Any]]:
    """The documents as the API shows them; the billed cases and statements of all of them in two queries."""
    from rentalars.documents.statements import month_key

    ids = [document.pk for document in documents]
    sources = {document.pk: document.cancels_id or document.pk for document in documents}
    billed: dict[int, list[int]] = {}
    for document_id, project_id in (
        Document.billed_projects.through.objects.filter(document_id__in=set(sources.values()))
        .order_by("project_id")
        .values_list("document_id", "project_id")
    ):
        billed.setdefault(document_id, []).append(project_id)
    statements = {
        invoice: (pk, month)
        for invoice, pk, month in MonthlyStatement.objects.filter(invoice_id__in=ids).values_list(
            "invoice_id", "pk", "month"
        )
    }
    rows = []
    for document in documents:
        project = document.project
        customer = document.customer
        transfer = getattr(document, "lexware_transfer", None)
        statement = statements.get(document.pk)
        user = document.created_by
        rows.append(
            {
                "id": document.pk,
                "kind": document.kind,
                "kind_label": str(DocumentKind(document.kind).label),
                "billing_type": document.billing_type,
                "credit_for": document.credit_for_id,
                "number": document.number,
                "title": document.title,
                "issued_on": document.issued_on,
                "due_on": document.due_on,
                "project": project.pk if project is not None else None,
                "project_number": project.number if project is not None else "",
                "project_name": project.name if project is not None else "",
                "reference": document.reference,
                "customer": document.customer_id,
                "customer_name": customer.name if customer is not None else (project.customer_name if project else ""),
                "customer_number": customer.number if customer is not None else "",
                "recipient": document.recipient_name or "",
                "net_total": document.net_total,
                "tax_total": (
                    document.gross_total - document.net_total
                    if document.net_total is not None and document.gross_total is not None
                    else None
                ),
                "gross_total": document.gross_total,
                "state": outgoing.state_of(document),
                "sent_at": document.sent_at,
                "sent_to": document.sent_to,
                "cancels": document.cancels_id,
                "cancels_number": document.cancels_number,
                "cancelled_by": document.cancelled_by_id,
                "cancelled_by_number": document.cancelled_by_number,
                "billed_projects": billed.get(sources[document.pk], []),
                "statement": statement[0] if statement else None,
                "statement_month": month_key(statement[1]) if statement else None,
                "lexware_state": transfer.state if transfer is not None else "",
                "lexware_transferred_at": transfer.transferred_at if transfer is not None else None,
                "created_at": document.created_at,
                "created_by": document.created_by_id,
                "created_by_name": (user.get_full_name() or user.username) if user is not None else "",
                "pdf_url": f"/api/v1/documents/{document.pk}/pdf",
                "xml_url": f"/api/v1/documents/{document.pk}/xml" if document.xml_file else "",
            }
        )
    return rows


#: The filters of both operations, for the description of the API (API-004).
FILTER_PARAMETERS = [
    OpenApiParameter(
        "kind",
        str,
        description="A kind (offer, order_confirmation, delivery_note, invoice, cancellation), 'bookable' "
        "(invoices and cancellations) or 'monthly' (monthly invoices of service cases); several separated by commas.",
    ),
    OpenApiParameter("state", str, enum=["not_sent", "sent", "cancelled", "not_cancelled"]),
    OpenApiParameter(
        "lexware",
        str,
        enum=["done", "failed", "missing"],
        description="DOK-011: handed to Lexware Office, failed, or an invoice or cancellation not handed over yet.",
    ),
    OpenApiParameter("customer", int, description="The customer of the document."),
    OpenApiParameter(
        "origin",
        str,
        enum=["project", "free"],
        description="Made on a project, or made in Accounting without one.",
    ),
    OpenApiParameter("project", int, description="The project – also the service cases a monthly invoice bills."),
    OpenApiParameter("since", str, description="Document date from, YYYY-MM-DD."),
    OpenApiParameter("until", str, description="Document date until, YYYY-MM-DD, included."),
    OpenApiParameter("q", str, description="Searched in number, title, project number and name, customer name."),
]


class _OutgoingView(ModuleAPIView):
    """The module Projects – for every project – and the price right (``outgoing.may_see``)."""

    module = Module.PROJECTS
    schema_tag = "accounting"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Refuse callers who may not see the list before anything happens."""
        super().initial(request, *args, **kwargs)
        if not outgoing.may_see(self.rights):
            raise PermissionDenied

    def filtered(self, request: Request) -> Any:
        """The documents of the filters; 400 for a filter that cannot be read."""
        filters = outgoing.parse(request.query_params)
        if filters.errors:
            raise ValidationError(filters.errors)
        return filters.apply(outgoing.documents())


class OutgoingDocumentListView(_OutgoingView):
    """``GET /accounting/documents`` – Buchhaltung → Ausgangsbelege (DOK-020)."""

    @extend_schema(
        parameters=[
            *FILTER_PARAMETERS,
            OpenApiParameter(
                "sort", str, description=f"One of {', '.join(SORTS)}; '-' in front reverses. Default: -issued_on."
            ),
        ],
        responses=OutgoingDocumentSerializer(many=True),
        operation_id="accounting_documents_list",
    )
    def get(self, request: Request) -> Response:
        """Page by page (``page``, ``page_size``), the newest first unless ``sort`` says otherwise."""
        documents = outgoing.for_list(self.filtered(request)).order_by(
            *_ordering(request.query_params.get("sort") or "-issued_on")
        )
        paginator = StandardPagination()
        page = list(paginator.paginate_queryset(documents, request, view=self) or [])
        return paginator.get_paginated_response(OutgoingDocumentSerializer(document_rows(page), many=True).data)


def _sum_data(entry: outgoing.KindSum) -> dict[str, Any]:
    """A sum as the API shows it: amounts as text with two places, ``None`` for a kind without amounts."""
    return {
        "kind": entry.kind,
        "label": entry.label,
        "count": entry.count,
        "net_total": str(money(entry.net)) if entry.priced else None,
        "tax_total": str(money(entry.tax)) if entry.priced else None,
        "gross_total": str(money(entry.gross)) if entry.priced else None,
    }


class OutgoingDocumentSumSerializer(serializers.Serializer):
    """Count and totals of the filtered documents of one kind (DOK-020)."""

    kind = serializers.CharField(help_text="The kind, or 'bookable' for invoices and cancellations together.")
    label = serializers.CharField()
    count = serializers.IntegerField()
    net_total = serializers.CharField(allow_null=True, help_text="null for kinds without amounts.")
    tax_total = serializers.CharField(allow_null=True)
    gross_total = serializers.CharField(allow_null=True)


class OutgoingDocumentTotalsSerializer(serializers.Serializer):
    """The sums of the filtered documents per kind; invoices and cancellations together (DOK-020)."""

    count = serializers.IntegerField()
    kinds = OutgoingDocumentSumSerializer(many=True)
    bookable = OutgoingDocumentSumSerializer(allow_null=True, help_text="null unless both kinds are there.")


class OutgoingDocumentTotalsView(_OutgoingView):
    """``GET /accounting/documents/totals`` – the sums of the filtered documents (DOK-020)."""

    @extend_schema(
        parameters=FILTER_PARAMETERS,
        responses=OutgoingDocumentTotalsSerializer,
        operation_id="accounting_documents_totals",
    )
    def get(self, request: Request) -> Response:
        """Count, net, tax and gross per kind as stored; cancellations count negative."""
        found = outgoing.totals(self.filtered(request))
        return Response(
            {
                "count": found.count,
                "kinds": [_sum_data(entry) for entry in found.kinds],
                "bookable": _sum_data(found.bookable) if found.bookable is not None else None,
            }
        )
