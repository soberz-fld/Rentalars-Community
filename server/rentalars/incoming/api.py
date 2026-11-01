# SPDX-License-Identifier: GPL-3.0-or-later
"""API of Buchhaltung → Eingangsrechnungen (API-002, API-014; DOK-023, DOK-024): everything the pages do, as the pages do it.

One logic, two doors: the pages and these operations both call :mod:`rentalars.incoming.services`,
:mod:`rentalars.incoming.costing` and :mod:`rentalars.incoming.booking`.

* ``GET /incoming-invoices`` – the register page by page with the filters of the page: ``supplier`` (ID), ``status``
  (``open``, ``checked``, ``booked_in``), ``since`` and ``until`` (the invoice date, both included), ``q`` (invoice
  number, supplier, file name, note, descriptions of the positions); ``sort`` by ``invoice_date`` (default, newest
  first), ``invoice_number``, ``supplier``, ``due_date``, ``total_net``, ``total_gross``, ``status`` or
  ``created_at``, ``-`` in front for the reverse order.
* ``GET /incoming-invoices/totals`` – with the same filters: count, net, tax and gross in euros.
* ``POST /incoming-invoices`` – upload an invoice (multipart, ``file``: PDF, PNG, JPEG or WEBP, at most the upload size
  of the settings); it is read unless ``read`` is false: number, date, due date, a known supplier and totals from the
  text of a PDF at once, with AI switched on for reading invoices the positions as well (``reading_job``; poll
  ``/jobs/{id}`` or the invoice).
* ``GET|PATCH|DELETE /incoming-invoices/{id}`` – the invoice with its positions; change the head (everything may be
  corrected: ``note``, ``status``, ``allocation_key`` …); delete one without items made of it.
* ``GET /incoming-invoices/{id}/file`` – the original.
* ``GET /incoming-invoices/{id}/xml`` – the XML of an e-invoice (XRechnung, ZUGFeRD / Factur-X; the uploaded XML
  or the one attached to the PDF); 404 for an invoice that has none. An XML upload or a PDF with an XML is read exactly
  (no AI): ``einvoice`` of the invoice says what the file is (format, profile, type, IBAN, warnings).
* ``POST /incoming-invoices/{id}/read`` – read the file again.
* ``POST /incoming-invoices/{id}/supplier`` – create the supplier named on the invoice in the master data and link it.
* ``GET|POST /incoming-invoices/{id}/positions`` and ``GET|PATCH|DELETE /incoming-invoices/{id}/positions/{position}``
  – the positions; mark ancillary cost with ``position_type`` = ``ancillary``.
* ``GET /incoming-invoices/{id}/costing`` – the ancillary costs spread over the goods (``allocation_key`` to try
  another key; nothing is saved) with the acquisition cost per position and per piece, the kind of asset
  (``merchandise``, ``low_value``, ``fixed_asset``) and the useful life.
* ``POST /incoming-invoices/{id}/book`` – make items or quantities of bulk material from the goods positions. Without
  ``"confirm": true`` only the preview comes back (nothing is made); with it the items are made, all or nothing, as
  in "Kauf einpflegen" (``POST /purchases``), with the acquisition cost on each item and the link to its position.
* ``GET|PATCH /incoming-settings`` – the limit of a low-value asset and the standard useful life (module
  Administration).

Rights: whoever may see purchase prices and read the material sees the register; changing, reading and booking in need
write access to the material as well, deleting its delete level (:mod:`rentalars.incoming.access`).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.api.pagination import StandardPagination
from rentalars.api.permissions import ModulePermission
from rentalars.api.views import ModuleAPIView
from rentalars.core.uploads import document_response
from rentalars.incoming import access, booking, costing, filters, services
from rentalars.incoming.models import (
    AllocationKey,
    IncomingInvoice,
    InvoicePosition,
    InvoiceStatus,
    PositionType,
)
from rentalars.masterdata.models import Category, StorageLocation, Supplier, TaxAccount
from rentalars.material import purchases
from rentalars.material.asset_models import AssetSettings
from rentalars.material.forms import stock_products
from rentalars.material.models import AssetKind, MaterialItem, MaterialModel, TrackingMode

#: ``sort`` of the list: the fields each key sorts by.
SORTS: dict[str, tuple[str, ...]] = {
    "invoice_date": ("invoice_date",),
    "invoice_number": ("invoice_number",),
    "supplier": ("supplier__name", "supplier_name"),
    "due_date": ("due_date",),
    "total_net": ("total_net",),
    "total_gross": ("total_gross",),
    "status": ("status",),
    "created_at": ("created_at",),
}


def _ordering(sort: str) -> list[str]:
    """The ``order_by`` of a ``sort`` key; ``-`` in front reverses every field of it."""
    descending = sort.startswith("-")
    names = SORTS.get(sort.lstrip("-"))
    if names is None:
        raise ApiValidationError({"sort": f"Unknown sort key; one of {', '.join(SORTS)}, '-' in front to reverse."})
    return [*(f"-{name}" if descending else name for name in names), "-pk" if descending else "pk"]


# --- Output ------------------------------------------------------------------------------------------------------


class PositionSerializer(serializers.Serializer):
    """A position of an incoming invoice."""

    id = serializers.IntegerField(read_only=True)
    place = serializers.IntegerField(read_only=True, help_text="1, 2, 3 … in the order of the invoice.")
    description = serializers.CharField(max_length=250)
    article_number = serializers.CharField(max_length=120, required=False, allow_blank=True)
    manufacturer = serializers.CharField(max_length=120, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0, required=False)
    unit_price_net = serializers.DecimalField(
        max_digits=12,
        decimal_places=4,
        required=False,
        allow_null=True,
        help_text="In the currency of the invoice. Ancillary cost: the amount (a discount is negative).",
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, allow_null=True
    )
    tax_account = serializers.PrimaryKeyRelatedField(
        queryset=TaxAccount.objects.all(),
        required=False,
        allow_null=True,
        help_text="The tax account (Steuerkonto, master data /tax-accounts) the net amount is booked to.",
    )
    position_type = serializers.ChoiceField(choices=PositionType.choices, required=False)
    asset_kind = serializers.ChoiceField(
        choices=[("", ""), *AssetKind.choices],
        required=False,
        allow_blank=True,
        help_text="Empty: by the limit of the settings (up to it a low-value asset, above it a fixed asset).",
    )
    useful_life_months = serializers.IntegerField(min_value=1, max_value=600, required=False, allow_null=True)
    weight_kg = serializers.DecimalField(
        max_digits=8,
        decimal_places=3,
        min_value=0,
        required=False,
        allow_null=True,
        help_text="Weight of one piece, to spread ancillary costs by weight.",
    )
    serial_numbers = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    material_model = serializers.PrimaryKeyRelatedField(
        queryset=MaterialModel.objects.all(), required=False, allow_null=True
    )
    line_net = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True, help_text="Quantity times unit price."
    )
    booked_items = serializers.IntegerField(read_only=True, help_text="Items (rows) made of the position so far.")
    booked_pieces = serializers.IntegerField(
        read_only=True, help_text="Pieces made of it; a bulk row counts its quantity."
    )


def position_data(position: InvoicePosition, booked: dict[int, dict[str, int]]) -> dict[str, Any]:
    """A position as the API shows it."""
    done = booked.get(position.pk, {"rows": 0, "pieces": 0})
    return {
        "id": position.pk,
        "place": position.place,
        "description": position.description,
        "article_number": position.article_number,
        "manufacturer": position.manufacturer,
        "quantity": position.quantity,
        "unit_price_net": position.unit_price_net,
        "tax_rate": position.tax_rate,
        "tax_account": position.tax_account_id,
        "position_type": position.position_type,
        "asset_kind": position.asset_kind,
        "useful_life_months": position.useful_life_months,
        "weight_kg": position.weight_kg,
        "serial_numbers": position.serial_numbers,
        "material_model": position.material_model_id,
        "line_net": position.line_net,
        "booked_items": done["rows"],
        "booked_pieces": done["pieces"],
    }


class InvoiceSerializer(serializers.Serializer):
    """An incoming invoice (the list leaves out ``positions`` and ``duplicates``)."""

    id = serializers.IntegerField()
    supplier = serializers.IntegerField(allow_null=True, help_text="The supplier of the master data; null: not linked.")
    supplier_name = serializers.CharField(help_text="The supplier of the master data, else the name on the invoice.")
    invoice_number = serializers.CharField()
    invoice_date = serializers.DateField(allow_null=True)
    due_date = serializers.DateField(allow_null=True)
    currency = serializers.CharField()
    exchange_rate = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        allow_null=True,
        help_text="Euros for one unit of the currency; null until entered – needed before booking in an invoice in another currency.",
    )
    total_net = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    total_tax = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    total_gross = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    status = serializers.ChoiceField(choices=InvoiceStatus.choices)
    allocation_key = serializers.ChoiceField(choices=AllocationKey.choices)
    note = serializers.CharField()
    original_name = serializers.CharField()
    size = serializers.IntegerField()
    reading_state = serializers.CharField(help_text="none, running, done, failed")
    reading = serializers.DictField(help_text="source (ai, text, empty), ai, error, note, at")
    reading_job = serializers.IntegerField(allow_null=True, help_text="The task while the AI reads; see /jobs/{id}.")
    position_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    created_by = serializers.IntegerField(allow_null=True)
    file_url = serializers.CharField()
    einvoice_format = serializers.CharField(help_text="ubl or cii for a structured e-invoice, else empty.")
    einvoice = serializers.DictField(help_text="Profile, type, IBAN, warnings … of an e-invoice; empty otherwise.")
    xml_url = serializers.CharField(allow_null=True, help_text="The XML of an e-invoice, else null.")
    positions = PositionSerializer(many=True, required=False)
    duplicates = serializers.ListField(
        child=serializers.IntegerField(), required=False, help_text="Invoices that may be the same (file or number)."
    )


def invoice_data(invoice: IncomingInvoice, *, detail: bool = False) -> dict[str, Any]:
    """An invoice as the API shows it; ``detail`` adds the positions and possible duplicates."""
    count = invoice.position_count if hasattr(invoice, "position_count") else invoice.positions.count()
    data: dict[str, Any] = {
        "id": invoice.pk,
        "supplier": invoice.supplier_id,
        "supplier_name": invoice.supplier_label,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "currency": invoice.currency,
        "exchange_rate": invoice.exchange_rate,
        "total_net": invoice.total_net,
        "total_tax": invoice.total_tax,
        "total_gross": invoice.total_gross,
        "status": invoice.status,
        "allocation_key": invoice.allocation_key,
        "note": invoice.note,
        "original_name": invoice.original_name,
        "size": invoice.size,
        "reading_state": invoice.reading_state,
        "reading": invoice.reading or {},
        "reading_job": invoice.reading_job_id,
        "position_count": count,
        "created_at": invoice.created_at,
        "created_by": invoice.created_by_id,
        "file_url": f"/api/v1/incoming-invoices/{invoice.pk}/file",
        "einvoice_format": invoice.einvoice_format,
        "einvoice": invoice.einvoice,
        "xml_url": f"/api/v1/incoming-invoices/{invoice.pk}/xml" if invoice.xml_name else None,
    }
    if detail:
        booked = services.booked_counts(invoice)
        data["positions"] = [position_data(position, booked) for position in invoice.positions.order_by("place", "pk")]
        data["duplicates"] = [other.pk for other in services.duplicates(invoice)]
    return data


def costing_data(found: costing.Costing) -> dict[str, Any]:
    """The cost of the goods of an invoice as the API shows it (amounts in euros)."""
    return {
        "allocation_key": found.key,
        "problems": found.problems,
        "ancillary_total": found.ancillary_total,
        "ancillary": [
            {"position": position.pk, "description": position.description, "amount": amount}
            for position, amount in found.ancillary
        ],
        "goods_total": found.goods_total,
        "spread_total": found.spread_total,
        "total": found.total,
        "positions": [
            {
                "position": row.position.pk,
                "description": row.position.description,
                "quantity": row.quantity,
                "net": row.line,
                "ancillary_share": row.share,
                "acquisition_cost": row.total,
                "per_piece": row.per_piece,
                "asset_kind": row.kind,
                "useful_life_months": row.useful_life,
                "problems": row.problems,
            }
            for row in found.rows
        ],
    }


class CostingSerializer(serializers.Serializer):
    """Ancillary costs spread over the goods: what each goods position costs to acquire."""

    allocation_key = serializers.ChoiceField(choices=AllocationKey.choices)
    problems = serializers.ListField(child=serializers.CharField())
    ancillary_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    ancillary = serializers.ListField(child=serializers.DictField())
    goods_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    spread_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    positions = serializers.ListField(child=serializers.DictField())


# --- Input -------------------------------------------------------------------------------------------------------


class HeadInputSerializer(serializers.Serializer):
    """What may be changed at the head of an invoice; everything is optional."""

    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False, allow_null=True, help_text="A supplier of the master data."
    )
    supplier_name = serializers.CharField(
        max_length=120, required=False, allow_blank=True, help_text="A name: a supplier of that name is linked."
    )
    invoice_number = serializers.CharField(max_length=60, required=False, allow_blank=True)
    invoice_date = serializers.DateField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.RegexField(r"^[A-Za-z]{3}$", required=False, help_text="Three letters, e.g. EUR.")
    exchange_rate = serializers.DecimalField(
        max_digits=12, decimal_places=6, min_value=0, required=False, allow_null=True
    )
    total_net = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    total_tax = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    total_gross = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    allocation_key = serializers.ChoiceField(choices=AllocationKey.choices, required=False)
    status = serializers.ChoiceField(choices=InvoiceStatus.choices, required=False)
    note = serializers.CharField(required=False, allow_blank=True)

    def values(self) -> dict[str, Any]:
        """The checked values for :func:`rentalars.incoming.services.update_head`."""
        values = dict(self.validated_data)
        supplier = values.pop("supplier", serializers.empty)
        if supplier is not serializers.empty and "supplier_name" not in values:
            values["supplier_name"] = supplier.name if supplier is not None else ""
        if "currency" in values:
            values["currency"] = values["currency"].upper()
        return values


class PositionInputSerializer(PositionSerializer):
    """A position to add or change (``description`` is needed to add one)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["description"].required = not kwargs.get("partial", False)

    def values(self) -> dict[str, Any]:
        """The checked values for :func:`rentalars.incoming.services.add_position` and ``update_position``."""
        return dict(self.validated_data)


class BookNewModelSerializer(serializers.Serializer):
    """A model that does not exist yet: made together with the items."""

    name = serializers.CharField(max_length=200)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(is_active=True))
    manufacturer = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    product = serializers.PrimaryKeyRelatedField(
        queryset=stock_products(), required=False, allow_null=True, default=None
    )
    keep_as_quantity = serializers.BooleanField(
        default=False, help_text="One row with the number of pieces (bulk material) instead of single items."
    )


class BookRowSerializer(serializers.Serializer):
    """What to make of one goods position."""

    position = serializers.PrimaryKeyRelatedField(queryset=InvoicePosition.objects.select_related("invoice"))
    material_model = serializers.PrimaryKeyRelatedField(
        queryset=MaterialModel.objects.all(), required=False, allow_null=True, default=None
    )
    new_model = BookNewModelSerializer(required=False, allow_null=True, default=None)
    count = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
        default=None,
        help_text="How many pieces. Empty: all that are left of the position.",
    )
    storage_location = serializers.PrimaryKeyRelatedField(
        queryset=StorageLocation.objects.filter(is_active=True), required=False, allow_null=True, default=None
    )
    serial_numbers = serializers.ListField(
        child=serializers.CharField(allow_blank=True, max_length=120), required=False, default=list
    )
    book_again = serializers.BooleanField(
        default=False, help_text="The position is booked in already: make more items of it."
    )
    asset_kind = serializers.ChoiceField(
        choices=[("", ""), *AssetKind.choices], required=False, allow_blank=True, help_text="Also kept at the position."
    )
    useful_life_months = serializers.IntegerField(min_value=1, max_value=600, required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Either an existing model or a new one."""
        if (attrs.get("material_model") is None) == (attrs.get("new_model") is None):
            raise serializers.ValidationError({"material_model": ["Name either material_model or new_model."]})
        return attrs


class BookSerializer(serializers.Serializer):
    """The decision of a booking: a row per goods position to book in, and the confirmation."""

    positions = BookRowSerializer(many=True, allow_empty=False, max_length=100)
    confirm = serializers.BooleanField(
        default=False, help_text="false: only the preview is answered. true: the items are made."
    )


def plan_data(plan: booking.Plan) -> dict[str, Any]:
    """The preview of a booking as the API shows it."""
    return {
        "ok": plan.ok,
        "problems": plan.problems,
        "warnings": plan.warnings,
        "piece_count": plan.piece_count,
        "rows": [
            {
                "position": row.position.pk,
                "model": row.model_name,
                "new_model": row.is_new_model,
                "bulk": row.is_bulk,
                "count": row.count,
                "net": row.price,
                "ancillary_share": row.share,
                "acquisition_cost": row.total,
                "per_piece": row.per_piece,
                "asset_kind": row.kind,
                "useful_life_months": row.useful_life,
                "booked_before": {"items": row.booked_rows, "pieces": row.booked_pieces},
                "problems": row.problems,
                "warnings": row.warnings,
            }
            for row in plan.rows
        ],
    }


def entries_of(rows: list[dict[str, Any]], invoice: IncomingInvoice) -> list[booking.Entry]:
    """The rows of a request as entries for :func:`rentalars.incoming.booking.plan`; 400 for a foreign position."""
    by_pk = {position.pk: position for position in invoice.positions.select_related("material_model")}
    entries = []
    for row in rows:
        position = by_pk.get(row["position"].pk)
        if position is None:
            raise ApiValidationError({"positions": [f"Position {row['position'].pk} belongs to another invoice."]})
        new = row.get("new_model")
        new_model = (
            purchases.NewModel(
                name=new["name"].strip(),
                category=new["category"],
                manufacturer=new.get("manufacturer", ""),
                product=new.get("product"),
                tracking_mode=TrackingMode.BULK if new.get("keep_as_quantity") else "",
            )
            if new
            else None
        )
        entries.append(
            booking.Entry(
                position=position,
                model=row.get("material_model"),
                new_model=new_model,
                count=row.get("count"),
                storage_location=row.get("storage_location"),
                serial_numbers=[serial for serial in row.get("serial_numbers") or [] if serial.strip()],
                book_again=bool(row.get("book_again")),
            )
        )
    return entries


# --- Views -------------------------------------------------------------------------------------------------------


class _IncomingView(ModuleAPIView):
    """The material module and the rights of the register (:mod:`rentalars.incoming.access`)."""

    module = Module.MATERIAL
    schema_tag = "accounting"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Refuse callers who may not see (or, for a change, may not change or delete) before anything happens."""
        super().initial(request, *args, **kwargs)
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            allowed = access.may_see(self.rights)
        elif request.method == "DELETE":
            allowed = self.may_delete_here()
        else:
            allowed = access.may_change(self.rights)
        if not allowed:
            raise PermissionDenied

    def may_delete_here(self) -> bool:
        """Whether these rights may delete what this view deletes: an invoice needs the delete level."""
        return access.may_delete(self.rights)

    @staticmethod
    def invoice_of(pk: int) -> IncomingInvoice:
        """An invoice, or 404."""
        return get_object_or_404(IncomingInvoice.objects.select_related("supplier", "reading_job"), pk=pk)

    def filtered(self, request: Request) -> Any:
        """The invoices of the filters; 400 for a filter that cannot be read."""
        found = filters.parse(request.query_params)
        if found.errors:
            raise ApiValidationError({name: str(message) for name, message in found.errors.items()})
        return found.apply(filters.invoices())


FILTER_PARAMETERS = [
    OpenApiParameter("supplier", int, description="The supplier of the master data."),
    OpenApiParameter("status", str, enum=list(InvoiceStatus.values)),
    OpenApiParameter("since", str, description="Invoice date from, YYYY-MM-DD."),
    OpenApiParameter("until", str, description="Invoice date until, YYYY-MM-DD, included."),
    OpenApiParameter("q", str, description="Searched in number, supplier, file name, note and position descriptions."),
]


class InvoiceListView(_IncomingView):
    """``GET|POST /incoming-invoices`` – the register and the upload."""

    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser]

    @extend_schema(
        parameters=[
            *FILTER_PARAMETERS,
            OpenApiParameter(
                "sort", str, description=f"One of {', '.join(SORTS)}; '-' in front reverses. Default: -invoice_date."
            ),
        ],
        responses=InvoiceSerializer(many=True),
        operation_id="incoming_invoices_list",
    )
    def get(self, request: Request) -> Response:
        """Page by page (``page``, ``page_size``), the newest invoice date first unless ``sort`` says otherwise."""
        invoices = self.filtered(request).order_by(*_ordering(request.query_params.get("sort") or "-invoice_date"))
        paginator = StandardPagination()
        page = list(paginator.paginate_queryset(invoices, request, view=self) or [])
        return paginator.get_paginated_response([invoice_data(invoice) for invoice in page])

    @extend_schema(
        request=inline_serializer(
            "IncomingInvoiceUpload",
            {"file": serializers.FileField(), "read": serializers.BooleanField(required=False, default=True)},
        ),
        responses={201: InvoiceSerializer},
        operation_id="incoming_invoices_create",
    )
    def post(self, request: Request) -> Response:
        """Keep the file as a new invoice and read it; nothing is booked in."""
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ApiValidationError({"file": "Choose a file."})
        read = str(request.data.get("read", "true")).lower() not in {"0", "false", "no", "off"}
        try:
            invoice = services.create_from_upload(uploaded, user=request.user, read=read)
        except ValidationError as error:
            raise ApiValidationError({"file": error.messages}) from error
        return Response(invoice_data(self.invoice_of(invoice.pk), detail=True), status=status.HTTP_201_CREATED)


class InvoiceTotalsView(_IncomingView):
    """``GET /incoming-invoices/totals`` – count and sums of the filtered invoices."""

    @extend_schema(
        parameters=FILTER_PARAMETERS,
        responses=inline_serializer(
            "IncomingInvoiceTotals",
            {
                "count": serializers.IntegerField(),
                "net_total": serializers.DecimalField(max_digits=14, decimal_places=2),
                "tax_total": serializers.DecimalField(max_digits=14, decimal_places=2),
                "gross_total": serializers.DecimalField(max_digits=14, decimal_places=2),
                "foreign_currency": serializers.IntegerField(help_text="Invoices counted in euros with their rate."),
                "complete": serializers.BooleanField(
                    help_text="False when invoices are left out of the sums: no exchange rate yet, or no amounts."
                ),
                "missing_exchange_rate": serializers.IntegerField(
                    help_text="Invoices in another currency without an exchange rate: counted, but not summed."
                ),
                "without_amount": serializers.IntegerField(help_text="Invoices without any amount: they add nothing."),
            },
        ),
        operation_id="incoming_invoices_totals",
    )
    def get(self, request: Request) -> Response:
        """Over the whole list, not one page; other currencies are converted with the rate of the invoice."""
        found = filters.totals(self.filtered(request))
        return Response(
            {
                "count": found.count,
                "net_total": found.net,
                "tax_total": found.tax,
                "gross_total": found.gross,
                "foreign_currency": found.foreign,
                "complete": not found.incomplete,
                "missing_exchange_rate": found.missing_rate,
                "without_amount": found.without_amount,
            }
        )


class InvoiceView(_IncomingView):
    """``GET|PATCH|DELETE /incoming-invoices/{id}``."""

    @extend_schema(responses=InvoiceSerializer, operation_id="incoming_invoices_read")
    def get(self, request: Request, pk: int) -> Response:
        """The invoice with its positions."""
        return Response(invoice_data(self.invoice_of(pk), detail=True))

    @extend_schema(request=HeadInputSerializer, responses=InvoiceSerializer, operation_id="incoming_invoices_update")
    def patch(self, request: Request, pk: int) -> Response:
        """Correct the head: number, dates, supplier, currency, amounts, key, status, note."""
        invoice = self.invoice_of(pk)
        serializer = HeadInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_head(invoice, serializer.values())
        return Response(invoice_data(self.invoice_of(pk), detail=True))

    @extend_schema(responses={204: None}, operation_id="incoming_invoices_delete")
    def delete(self, request: Request, pk: int) -> Response:
        """Delete the invoice with its positions and its file; refused once items were made of it."""
        services.delete_invoice(self.invoice_of(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvoiceFileView(_IncomingView):
    """``GET /incoming-invoices/{id}/file`` – the original."""

    @extend_schema(responses={(200, "application/octet-stream"): bytes}, operation_id="incoming_invoices_file")
    def get(self, request: Request, pk: int) -> Any:
        """The file as uploaded: a PDF or a picture shown, everything else downloaded."""
        invoice = self.invoice_of(pk)
        return document_response(invoice.file.name, invoice.original_name)


class InvoiceXmlView(_IncomingView):
    """``GET /incoming-invoices/{id}/xml`` – the XML of an e-invoice."""

    @extend_schema(responses={(200, "application/xml"): bytes}, operation_id="incoming_invoices_xml")
    def get(self, request: Request, pk: int) -> Any:
        """The XML as a download; 404 if the invoice is no e-invoice."""
        return services.xml_response(self.invoice_of(pk))


class InvoiceReadView(_IncomingView):
    """``POST /incoming-invoices/{id}/read`` – read the file again."""

    @extend_schema(request=None, responses=InvoiceSerializer, operation_id="incoming_invoices_read_again")
    def post(self, request: Request, pk: int) -> Response:
        """Empty fields of the head are filled; positions that are not booked in and that nobody typed or corrected are replaced."""
        invoice = self.invoice_of(pk)
        try:
            services.start_reading(invoice, user=request.user)
        except ValidationError as error:
            raise ApiValidationError({"detail": error.messages}) from error  # 400, not 500
        return Response(invoice_data(self.invoice_of(pk), detail=True))


class InvoiceSupplierView(_IncomingView):
    """``POST /incoming-invoices/{id}/supplier`` – create the named supplier in the master data."""

    @extend_schema(request=None, responses=InvoiceSerializer, operation_id="incoming_invoices_create_supplier")
    def post(self, request: Request, pk: int) -> Response:
        """The supplier named on the invoice becomes a supplier of the master data (one of that name is linked)."""
        invoice = self.invoice_of(pk)
        services.create_supplier(invoice)
        return Response(invoice_data(self.invoice_of(pk), detail=True))


class PositionListView(_IncomingView):
    """``GET|POST /incoming-invoices/{id}/positions``."""

    @extend_schema(responses=PositionSerializer(many=True), operation_id="incoming_positions_list")
    def get(self, request: Request, pk: int) -> Response:
        """The positions in the order of the invoice."""
        invoice = self.invoice_of(pk)
        booked = services.booked_counts(invoice)
        return Response([position_data(item, booked) for item in invoice.positions.order_by("place", "pk")])

    @extend_schema(
        request=PositionInputSerializer, responses={201: PositionSerializer}, operation_id="incoming_positions_create"
    )
    def post(self, request: Request, pk: int) -> Response:
        """Add a position at the end; mark ancillary cost with ``position_type`` = ``ancillary``."""
        invoice = self.invoice_of(pk)
        serializer = PositionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        position = services.add_position(invoice, serializer.values())
        return Response(position_data(position, services.booked_counts(invoice)), status=status.HTTP_201_CREATED)


class PositionPermission(ModulePermission):
    """The module level of the view; removing a position needs write access like any other correction, not delete."""

    def has_permission(self, request: Request, view: Any) -> bool:
        """``DELETE`` asks for the write level (the page lets writers remove positions too)."""
        if request.method == "DELETE":
            return bool(
                request.user
                and request.user.is_authenticated
                and request_rights(request).has_level(view.module, Level.WRITE)
            )
        return super().has_permission(request, view)


class PositionView(_IncomingView):
    """``GET|PATCH|DELETE /incoming-invoices/{id}/positions/{position}``.

    Removing a position is part of correcting the invoice, as on the page: write access is enough.
    """

    permission_classes: ClassVar[list[Any]] = [PositionPermission]

    def may_delete_here(self) -> bool:
        """Whoever may change an invoice may remove a position of it."""
        return access.may_change(self.rights)

    @staticmethod
    def position_of(invoice: IncomingInvoice, position_pk: int) -> InvoicePosition:
        """A position of the invoice, or 404."""
        return get_object_or_404(invoice.positions.select_related("material_model"), pk=position_pk)

    @extend_schema(responses=PositionSerializer, operation_id="incoming_positions_read")
    def get(self, request: Request, pk: int, position_pk: int) -> Response:
        """One position."""
        invoice = self.invoice_of(pk)
        position = self.position_of(invoice, position_pk)
        return Response(position_data(position, services.booked_counts(invoice)))

    @extend_schema(
        request=PositionInputSerializer, responses=PositionSerializer, operation_id="incoming_positions_update"
    )
    def patch(self, request: Request, pk: int, position_pk: int) -> Response:
        """Change a position; one that was booked in keeps its quantity, price and type."""
        invoice = self.invoice_of(pk)
        position = self.position_of(invoice, position_pk)
        serializer = PositionInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_position(position, serializer.values())
        return Response(position_data(position, services.booked_counts(invoice)))

    @extend_schema(responses={204: None}, operation_id="incoming_positions_delete")
    def delete(self, request: Request, pk: int, position_pk: int) -> Response:
        """Remove a position that is not booked in."""
        invoice = self.invoice_of(pk)
        services.delete_position(self.position_of(invoice, position_pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CostingView(_IncomingView):
    """``GET /incoming-invoices/{id}/costing`` – ancillary costs spread over the goods."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "allocation_key", str, enum=list(AllocationKey.values), description="Try another key; nothing is saved."
            )
        ],
        responses=CostingSerializer,
        operation_id="incoming_invoices_costing",
    )
    def get(self, request: Request, pk: int) -> Response:
        """Acquisition cost per goods position and per piece, the kind of asset and the useful life."""
        key = request.query_params.get("allocation_key")
        if key and key not in AllocationKey.values:
            raise ApiValidationError({"allocation_key": f"One of {', '.join(AllocationKey.values)}."})
        return Response(costing_data(costing.costing_of(self.invoice_of(pk), key=key or None)))


class BookView(_IncomingView):
    """``POST /incoming-invoices/{id}/book`` – make items or quantities from the goods positions."""

    @extend_schema(
        request=BookSerializer,
        responses={
            200: inline_serializer("IncomingBookPreview", {"confirmed": serializers.BooleanField()}),
            201: inline_serializer("IncomingBooked", {"ids": serializers.CharField()}),
        },
        operation_id="incoming_invoices_book",
    )
    def post(self, request: Request, pk: int) -> Response:
        """Preview (``confirm`` false, answer 200) or book in (``confirm`` true, answer 201); all or nothing."""
        invoice = self.invoice_of(pk)
        serializer = BookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data["positions"]
        entries = entries_of(rows, invoice)
        for row, entry in zip(rows, entries, strict=True):
            self.remember_asset_choice(row, entry.position)
        invoice = self.invoice_of(pk)
        entries = entries_of(rows, invoice)
        preview = booking.plan(invoice, entries, rights=self.rights)
        if not serializer.validated_data["confirm"]:
            return Response({"confirmed": False, "preview": plan_data(preview)})
        made = booking.book(invoice, entries, rights=self.rights, user=request.user)
        items = MaterialItem.objects.filter(pk__in=[item.pk for item in made.items]).order_by("inventory_number")
        return Response(
            {
                "confirmed": True,
                "ids": made.ids,
                "items": [
                    {
                        "id": item.pk,
                        "inventory_number": item.inventory_number,
                        "material_model": item.material_model_id,
                        "position": item.source_position_id,
                        "purchase_price": item.purchase_price,
                        "ancillary_cost_net": item.ancillary_cost_net,
                        "acquisition_cost_net": item.acquisition_cost_net,
                        "asset_kind": item.asset_kind,
                        "useful_life_months": item.useful_life_months,
                    }
                    for item in items
                ],
                "new_models": [model.pk for model in made.new_models],
                "warnings": made.warnings,
                "invoice": invoice_data(self.invoice_of(pk), detail=True),
            },
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def remember_asset_choice(row: dict[str, Any], position: InvoicePosition) -> None:
        """Keep the kind of asset and the useful life named in the request with the position, as the page does."""
        values = {name: row[name] for name in ("asset_kind", "useful_life_months") if name in row}
        if values:
            services.update_position(position, values)


class IncomingSettingsSerializer(serializers.Serializer):
    """The limit of a low-value asset and the standard useful life."""

    low_value_limit_net = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    default_useful_life_months = serializers.IntegerField(min_value=1, max_value=600)
    keep_memory_value = serializers.BooleanField(
        help_text="Depreciation: a fully depreciated fixed asset stays in the books with 1 EUR (Erinnerungswert). Default off."
    )


class SettingsView(ModuleAPIView):
    """``GET|PATCH /incoming-settings`` – Einstellungen → Eingangsrechnungen."""

    module = Module.ADMINISTRATION
    schema_tag = "accounting"

    @extend_schema(responses=IncomingSettingsSerializer, operation_id="incoming_settings_read")
    def get(self, request: Request) -> Response:
        """The limit of a low-value asset (GWG, net) and the standard useful life in months."""
        return Response(IncomingSettingsSerializer(AssetSettings.load()).data)

    @extend_schema(
        request=IncomingSettingsSerializer,
        responses=IncomingSettingsSerializer,
        operation_id="incoming_settings_update",
    )
    def patch(self, request: Request) -> Response:
        """Change one or both values."""
        serializer = IncomingSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        current = AssetSettings.load()
        for name, value in serializer.validated_data.items():
            setattr(current, name, value)
        try:
            current.full_clean()
        except ValidationError as error:
            raise ApiValidationError(error.message_dict) from error
        current.save()
        return Response(IncomingSettingsSerializer(current).data)
