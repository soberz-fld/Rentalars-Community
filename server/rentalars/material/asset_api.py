# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the depreciation and the used sale from stock (API-002, API-014; MAT-086): what the pages do, as they do it.

One logic, two doors: the pages and these operations call :mod:`rentalars.material.book_values` and
:mod:`rentalars.material.sales`. A simplified standard setting, no tax advice; there is no DATEV export.

* ``GET|PATCH /material-items/{id}/asset`` – the asset data of an item with its valuation (``as_of``, default today:
  accumulated depreciation, book value, the schedule per year); ``PATCH`` records the item as merchandise, low-value
  or fixed asset or corrects it (``asset_kind``, ``useful_life_months``, ``ancillary_cost_net``,
  ``acquisition_cost_net``).
* ``GET /asset-register`` – the Anlagenspiegel page by page with the filters of the page (``kind``, ``location``,
  ``model``, ``q``, ``as_of``, ``year``, ``left``); ``sort`` by ``id`` (default), ``model``, ``kind``, ``acquired``,
  ``cost``, ``book_value``, ``-`` in front reverses. ``GET /asset-register/totals`` – the sums over the whole selection.
  ``GET /asset-register/csv`` – the whole selection as a file for a spreadsheet.
* ``POST /material-items/{id}/sale-preview`` – what a used sale would be: book value, gain or loss, what stops it or should
  give pause. Nothing is changed. ``POST /material-items/{id}/sell`` – the sale (``accept_warnings`` to go on despite warnings).
* ``GET /stock-sales`` – the sales with the filters ``year``, ``since``, ``until``, ``q``, ``reversed``; ``GET
  /stock-sales/summary`` – gain and loss per year; ``GET /stock-sales/csv``; ``GET /stock-sales/{id}``; ``POST
  /stock-sales/{id}/cancel`` – reverse a sale (``reason``); ``POST /stock-sales/{id}/invoice`` – a draft of an invoice for
  the customer who bought.

Rights as the pages: purchase prices and read access to the material to look; write access to the material to record, sell,
reverse (``rentalars.incoming.access``); the invoice needs the right to make documents without a project as well.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.pagination import StandardPagination
from rentalars.api.views import ModuleAPIView
from rentalars.core.tables import BYTE_ORDER_MARK
from rentalars.customers.models import Contact, Customer
from rentalars.incoming import access
from rentalars.masterdata.models import TaxRate
from rentalars.material import book_values, sales
from rentalars.material.asset_tables import ASSET_TABLE, SALES_TABLE
from rentalars.material.book_values import AssetRow
from rentalars.material.depreciation import Valuation
from rentalars.material.models import AssetKind, MaterialItem
from rentalars.material.sale_models import SaleFromStock


class _AssetView(ModuleAPIView):
    """The material module and the rights of the register (:mod:`rentalars.incoming.access`)."""

    module = Module.MATERIAL
    schema_tag = "accounting"

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Refuse callers who may not see – or, for anything but reading, may not change – before anything happens."""
        super().initial(request, *args, **kwargs)
        reading = request.method in {"GET", "HEAD", "OPTIONS"}
        if not (access.may_see(self.rights) if reading else access.may_change(self.rights)):
            raise PermissionDenied


def _item(pk: int) -> MaterialItem:
    """An item with its model, or 404."""
    return get_object_or_404(MaterialItem.objects.select_related("material_model", "installed_in"), pk=pk)


# --- The asset data of an item ------------------------------------------------------------------------------------------


def valuation_data(item: MaterialItem, valued: Valuation) -> dict[str, Any]:
    """An item's asset data with its valuation, as the API shows it (amounts in euros)."""
    return {
        "item": item.pk,
        "asset_kind": item.asset_kind,
        "useful_life_months": item.useful_life_months,
        "purchase_date": item.purchase_date_iso or None,
        "acquisition_cost_net": book_values.cost_of(item),
        "ancillary_cost_net": item.ancillary_cost_net,
        "as_of": valued.as_of,
        "state": valued.state,
        "state_text": book_values.state_label(valued),
        "accumulated_depreciation": valued.accumulated,
        "depreciation_in_year": valued.this_year,
        "opening_book_value": valued.opening_value,
        "book_value": valued.book_value,
        "months_done": valued.months_done,
        "months_left": valued.months_left,
        "last_month": valued.last_month,
        "schedule": [
            {
                "year": row.year,
                "months": row.months,
                "depreciation": row.depreciation,
                "accumulated": row.accumulated,
                "book_value": row.book_value,
            }
            for row in valued.rows
        ],
    }


class AssetDataInputSerializer(serializers.Serializer):
    """What may be changed of the asset data; everything is optional."""

    asset_kind = serializers.ChoiceField(
        choices=[("", ""), *AssetKind.choices], required=False, help_text="Empty takes the item out of the books."
    )
    useful_life_months = serializers.IntegerField(min_value=1, max_value=600, required=False, allow_null=True)
    ancillary_cost_net = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="May be negative (a share of a discount); the acquisition cost must stay 0 or more.",
    )
    acquisition_cost_net = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False, allow_null=True
    )


class ItemAssetView(_AssetView):
    """``GET|PATCH /material-items/{id}/asset``."""

    @extend_schema(
        parameters=[OpenApiParameter("as_of", str, description="The day, YYYY-MM-DD; default today.")],
        responses=inline_serializer("ItemAsset", {"item": serializers.IntegerField()}),
        operation_id="material_item_asset_read",
    )
    def get(self, request: Request, pk: int) -> Response:
        """The asset data, the book value on a day and the depreciation per year."""
        item = _item(pk)
        day = _day(request.query_params.get("as_of"), "as_of") or timezone.localdate()
        return Response(valuation_data(item, book_values.value_of(item, day)))

    @extend_schema(
        request=AssetDataInputSerializer,
        responses=inline_serializer("ItemAssetChanged", {"item": serializers.IntegerField()}),
        operation_id="material_item_asset_update",
    )
    def patch(self, request: Request, pk: int) -> Response:
        """Record the item as merchandise, low-value or fixed asset, or correct its asset data."""
        item = _item(pk)
        serializer = AssetDataInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        book_values.set_asset_data(
            item,
            kind=data.get("asset_kind", item.asset_kind),
            useful_life_months=data.get("useful_life_months", item.useful_life_months),
            ancillary_cost_net=data.get("ancillary_cost_net"),
            acquisition_cost_net=data.get("acquisition_cost_net"),
        )
        return Response(valuation_data(item, book_values.value_of(item)))


def _day(text: Any, name: str) -> Any:
    """A day typed as ``YYYY-MM-DD``; ``None`` for nothing. 400 for anything else."""
    import datetime

    if text in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(text))
    except ValueError as error:
        raise ApiValidationError({name: "Enter the day as YYYY-MM-DD."}) from error


# --- The Anlagenspiegel --------------------------------------------------------------------------------------------------

SORTS: dict[str, Any] = {
    "id": lambda row: row.item.inventory_number,
    "model": lambda row: row.item.material_model.name.casefold(),
    "kind": lambda row: row.valued.kind,
    "acquired": lambda row: (row.item.purchase_date is None, row.item.purchase_date),
    "cost": lambda row: (row.valued.cost is None, row.valued.cost),
    "book_value": lambda row: (row.valued.book_value is None, row.valued.book_value),
}

REGISTER_PARAMETERS = [
    OpenApiParameter("kind", str, enum=["fixed_asset", "low_value", "merchandise", "unclassified", "all"]),
    OpenApiParameter("location", int, description="A storage location."),
    OpenApiParameter("model", int, description="A material model."),
    OpenApiParameter("q", str, description="Searched in model, ID, serial number, note."),
    OpenApiParameter("as_of", str, description="The day the values are for, YYYY-MM-DD; default today."),
    OpenApiParameter(
        "year", int, description="The balance-sheet date 31 December of this year, unless as_of is given."
    ),
    OpenApiParameter("left", bool, description="Also items that left the stock (not in the sums)."),
]


def row_data(row: AssetRow) -> dict[str, Any]:
    """A row of the register as the API shows it; the amounts are empty for an item without a book value or gone."""
    item, valued = row.item, row.valued
    shown = not row.left_stock and valued.book_value is not None
    return {
        "item": item.pk,
        "display_id": item.display_id,
        "model": item.material_model_id,
        "model_name": item.material_model.name,
        "asset_kind": valued.kind,
        "purchase_date": item.purchase_date_iso or None,
        "useful_life_months": item.useful_life_months if valued.kind == "fixed_asset" else None,
        "quantity": item.quantity if item.material_model.is_bulk else None,
        "acquisition_cost_net": valued.cost if shown else None,
        "accumulated_depreciation": valued.accumulated if shown else None,
        "depreciation_in_year": valued.this_year if shown else None,
        "opening_book_value": valued.opening_value if shown else None,
        "book_value": valued.book_value if shown else None,
        "state": valued.state,
        "state_text": book_values.state_label(valued),
        "status": item.status,
        "storage_location": item.storage_location_id,
        "sold_on": row.sold_on,
        "counts": row.counts,
    }


class AssetRegisterView(_AssetView):
    """``GET /asset-register`` – the Anlagenspiegel page by page."""

    def found(self, request: Request) -> book_values.Filters:
        """The filters of the address; 400 for one that cannot be read."""
        found = book_values.parse(request.query_params)
        if found.errors:
            raise ApiValidationError({name: str(message) for name, message in found.errors.items()})
        return found

    @extend_schema(
        parameters=[*REGISTER_PARAMETERS, OpenApiParameter("sort", str, description=f"One of {', '.join(SORTS)}.")],
        responses=inline_serializer("AssetRegisterRow", {"item": serializers.IntegerField()}, many=True),
        operation_id="asset_register_list",
    )
    def get(self, request: Request) -> Response:
        """Page by page (``page``, ``page_size``) in the order of the IDs unless ``sort`` says otherwise."""
        sort = request.query_params.get("sort") or "id"
        key = SORTS.get(sort.lstrip("-"))
        if key is None:
            raise ApiValidationError({"sort": f"Unknown sort key; one of {', '.join(SORTS)}, '-' in front to reverse."})
        rows, _summary = book_values.register(self.found(request))
        rows.sort(key=key, reverse=sort.startswith("-"))
        paginator = StandardPagination()
        page = list(paginator.paginate_queryset(rows, request, view=self) or [])
        return paginator.get_paginated_response([row_data(row) for row in page])


def _sums_data(sums: book_values.Sums) -> dict[str, Any]:
    """Count and sums of counted rows."""
    return {
        "count": sums.count,
        "acquisition_cost_net": sums.cost,
        "accumulated_depreciation": sums.accumulated,
        "depreciation_in_year": sums.this_year,
        "opening_book_value": sums.opening_value,
        "book_value": sums.book_value,
    }


class AssetRegisterTotalsView(AssetRegisterView):
    """``GET /asset-register/totals`` – the sums over the whole selection."""

    @extend_schema(
        parameters=REGISTER_PARAMETERS,
        responses=inline_serializer("AssetRegisterTotals", {"count": serializers.IntegerField()}),
        operation_id="asset_register_totals",
    )
    def get(self, request: Request) -> Response:  # type: ignore[override]
        """Sums in total and per kind; what has no book value, was bought later or had left is counted apart."""
        found = self.found(request)
        _rows, summary = book_values.register(found)
        return Response(
            {
                "as_of": found.day,
                **_sums_data(summary.total),
                "by_kind": {kind: _sums_data(sums) for kind, sums in summary.by_kind.items()},
                "without_book_value": summary.unvalued,
                "bought_later": summary.not_yet,
                "left_the_stock": summary.left,
            }
        )


def _csv(table: Any, rows: Any) -> str:
    """Rows as CSV text with every column of the table: semicolons, decimal commas, a byte order mark (IMP-005)."""
    out = io.StringIO()
    out.write(BYTE_ORDER_MARK)
    writer = csv.writer(out, delimiter=";")
    columns = [column for column in table.columns if column.export]
    writer.writerow([strip_tags(str(column.label)) for column in columns])
    for row in rows:
        writer.writerow([column.csv_value(row) for column in columns])
    return out.getvalue()


def _csv_response(text: str, name: str) -> HttpResponse:
    """A CSV file named after the list and the day, as the lists of the pages are."""
    response = HttpResponse(text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{slugify(name)}-{timezone.localdate():%Y-%m-%d}.csv"'
    return response


class AssetRegisterCsvView(AssetRegisterView):
    """``GET /asset-register/csv`` – the whole selection as a file for a spreadsheet."""

    @extend_schema(
        parameters=REGISTER_PARAMETERS, responses={(200, "text/csv"): str}, operation_id="asset_register_csv"
    )
    def get(self, request: Request) -> HttpResponse:  # type: ignore[override]
        """One row per item with every column of the page."""
        rows, _summary = book_values.register(self.found(request))
        return _csv_response(_csv(ASSET_TABLE, rows), _("Asset register"))


# --- Selling ---------------------------------------------------------------------------------------------------------------


class SaleInputSerializer(serializers.Serializer):
    """What a sale needs: the day, the price, the buyer."""

    sold_on = serializers.DateField()
    quantity = serializers.IntegerField(min_value=1, required=False, default=1, help_text="Bulk material only.")
    net_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    tax_rate = serializers.PrimaryKeyRelatedField(
        queryset=TaxRate.objects.filter(is_active=True), required=False, allow_null=True
    )
    # As on the page, only active customers can buy.
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.filter(is_active=True), required=False, allow_null=True
    )
    contact = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.filter(customer__is_active=True), required=False, allow_null=True
    )
    buyer_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
    accept_warnings = serializers.BooleanField(required=False, default=False)


def preview_data(plan: sales.Preview) -> dict[str, Any]:
    """The preview of a sale as the API shows it."""
    return {
        "item": plan.item.pk,
        "ok": plan.ok,
        "problems": plan.problems,
        "warnings": plan.warnings,
        "notes": plan.notes,
        "quantity": plan.quantity,
        "pieces": plan.pieces,
        "item_leaves_the_stock": plan.complete,
        "sold_on": plan.sold_on,
        "net_price": plan.net_price,
        "tax_percent": plan.tax_percent,
        "tax_amount": plan.tax_amount,
        "gross_price": plan.gross_price,
        "acquisition_cost_net": plan.cost,
        "accumulated_depreciation": plan.accumulated,
        "book_value": plan.book_value,
        "book_value_basis": plan.basis,
        "gain_loss": plan.gain_loss,
    }


def sale_data(sale: SaleFromStock) -> dict[str, Any]:
    """A sale as the API shows it."""
    return {
        "id": sale.pk,
        "item": sale.item_id,
        "item_display_id": sale.item.display_id,
        "model_name": sale.item.material_model.name,
        "quantity": sale.quantity,
        "sold_on": sale.sold_on,
        "customer": sale.customer_id,
        "contact": sale.contact_id,
        "buyer": sales.buyer_label(sale),
        "net_price": sale.net_price,
        "tax_rate": sale.tax_rate_id,
        "tax_percent": sale.tax_percent,
        "tax_amount": sale.tax_amount,
        "gross_price": sale.gross_price,
        "note": sale.note,
        "asset_kind": sale.asset_kind,
        "acquisition_cost_net": sale.cost,
        "accumulated_depreciation": sale.accumulated_depreciation,
        "book_value": sale.book_value,
        "book_value_basis": sale.book_value_basis,
        "gain_loss": sale.gain_loss,
        "item_left_the_stock": sale.item_left,
        "sold_by": sale.sold_by_id,
        "created_at": sale.created_at,
        "cancelled": sale.is_cancelled,
        "cancelled_at": sale.cancelled_at,
        "cancelled_by": sale.cancelled_by_id,
        "cancel_reason": sale.cancel_reason,
    }


class _SaleView(_AssetView):
    """Shared by the views that take a sale as a request."""

    def checked(self, request: Request) -> dict[str, Any]:
        """The checked input; a customer or contact needs read access to the customers (their names are not for everybody)."""
        serializer = SaleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if (data.get("customer") or data.get("contact")) and not self.rights.can_read(Module.CUSTOMERS):
            raise PermissionDenied
        return data


class ItemSalePreviewView(_SaleView):
    """``POST /material-items/{id}/sale-preview``."""

    @extend_schema(
        request=SaleInputSerializer,
        responses=inline_serializer("SalePreview", {"ok": serializers.BooleanField()}),
        operation_id="material_item_sale_preview",
    )
    def post(self, request: Request, pk: int) -> Response:
        """What the sale would be; nothing is changed (``buyer_name``, ``customer`` and ``note`` are not needed)."""
        serializer = SaleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = sales.preview(
            _item(pk),
            quantity=data["quantity"],
            sold_on=data["sold_on"],
            net_price=data["net_price"],
            tax_rate=data.get("tax_rate"),
        )
        return Response(preview_data(plan))


class ItemSellView(_SaleView):
    """``POST /material-items/{id}/sell``."""

    @extend_schema(
        request=SaleInputSerializer,
        responses={201: inline_serializer("SaleMade", {"id": serializers.IntegerField()})},
        operation_id="material_item_sell",
    )
    def post(self, request: Request, pk: int) -> Response:
        """Sell the item (or a quantity of bulk material) out of the stock; 400 with the reasons when it cannot be."""
        data = self.checked(request)
        sale = sales.sell(
            _item(pk),
            sold_on=data["sold_on"],
            net_price=data["net_price"],
            quantity=data["quantity"],
            tax_rate=data.get("tax_rate"),
            customer=data.get("customer"),
            contact=data.get("contact"),
            buyer_name=data["buyer_name"],
            note=data["note"],
            user=request.user,
            accept_warnings=data["accept_warnings"],
        )
        return Response(sale_data(_sale(sale.pk)), status=status.HTTP_201_CREATED)


# --- The sales -----------------------------------------------------------------------------------------------------------


def _sale(pk: int) -> SaleFromStock:
    """A sale with what the API shows, or 404."""
    return get_object_or_404(sales.sales(), pk=pk)


SALES_SORTS = {
    "sold_on": ("sold_on",),
    "net_price": ("net_price",),
    "gain_loss": ("gain_loss",),
    "book_value": ("book_value",),
    "item": ("item__inventory_number",),
}

SALES_PARAMETERS = [
    OpenApiParameter("year", int),
    OpenApiParameter("since", str, description="From this day, YYYY-MM-DD."),
    OpenApiParameter("until", str, description="Until this day, YYYY-MM-DD, included."),
    OpenApiParameter("q", str, description="Searched in buyer, note, model, serial number, ID."),
    OpenApiParameter("reversed", bool, description="Also reversed sales."),
]


class StockSalesView(_AssetView):
    """``GET /stock-sales`` – the sales page by page."""

    def filtered(self, request: Request) -> Any:
        """The sales of the filters; 400 for one that cannot be read."""
        found = sales.parse_filters(request.query_params)
        if found.errors:
            raise ApiValidationError({name: str(message) for name, message in found.errors.items()})
        return found.apply(sales.sales())

    @extend_schema(
        parameters=[
            *SALES_PARAMETERS,
            OpenApiParameter(
                "sort", str, description=f"One of {', '.join(SALES_SORTS)}; '-' reverses. Default -sold_on."
            ),
        ],
        responses=inline_serializer("StockSale", {"id": serializers.IntegerField()}, many=True),
        operation_id="stock_sales_list",
    )
    def get(self, request: Request) -> Response:
        """Page by page, the latest sale first unless ``sort`` says otherwise."""
        sort = request.query_params.get("sort") or "-sold_on"
        names = SALES_SORTS.get(sort.lstrip("-"))
        if names is None:
            raise ApiValidationError(
                {"sort": f"Unknown sort key; one of {', '.join(SALES_SORTS)}, '-' in front to reverse."}
            )
        ordered = [f"-{name}" if sort.startswith("-") else name for name in names]
        queryset = self.filtered(request).order_by(*ordered, "-pk" if sort.startswith("-") else "pk")
        paginator = StandardPagination()
        page = list(paginator.paginate_queryset(queryset, request, view=self) or [])
        return paginator.get_paginated_response([sale_data(sale) for sale in page])


class StockSalesSummaryView(StockSalesView):
    """``GET /stock-sales/summary`` – gain and loss per year."""

    @extend_schema(
        parameters=SALES_PARAMETERS,
        responses=inline_serializer("StockSalesSummary", {"years": serializers.ListField()}),
        operation_id="stock_sales_summary",
    )
    def get(self, request: Request) -> Response:  # type: ignore[override]
        """Per year (newest first): sales, net prices, book values, gains, losses and their sum. Reversed sales do not count."""
        return Response(
            {
                "years": [
                    {
                        "year": sums.year,
                        "count": sums.count,
                        "net_price": sums.net,
                        "book_value": sums.book_value,
                        "gains": sums.gain,
                        "losses": sums.loss,
                        "gain_loss": sums.result,
                    }
                    for sums in sales.sums_by_year(self.filtered(request))
                ]
            }
        )


class StockSalesCsvView(StockSalesView):
    """``GET /stock-sales/csv`` – the sales of the filters as a file for a spreadsheet."""

    @extend_schema(parameters=SALES_PARAMETERS, responses={(200, "text/csv"): str}, operation_id="stock_sales_csv")
    def get(self, request: Request) -> HttpResponse:  # type: ignore[override]
        """One row per sale with every column of the page."""
        queryset = self.filtered(request).order_by("-sold_on", "-pk")
        return _csv_response(_csv(SALES_TABLE, queryset), _("Sales from stock"))


class StockSaleView(_AssetView):
    """``GET /stock-sales/{id}``."""

    @extend_schema(
        responses=inline_serializer("StockSaleRead", {"id": serializers.IntegerField()}),
        operation_id="stock_sales_read",
    )
    def get(self, request: Request, pk: int) -> Response:
        """One sale."""
        return Response(sale_data(_sale(pk)))


class StockSaleCancelView(_AssetView):
    """``POST /stock-sales/{id}/cancel``."""

    @extend_schema(
        request=inline_serializer("StockSaleCancel", {"reason": serializers.CharField(max_length=250)}),
        responses=inline_serializer("StockSaleCancelled", {"id": serializers.IntegerField()}),
        operation_id="stock_sales_cancel",
    )
    def post(self, request: Request, pk: int) -> Response:
        """Reverse the sale (Storno): the item is in the stock again; the sale stays, marked as reversed."""
        sale = _sale(pk)
        sales.cancel(sale, reason=str(request.data.get("reason") or ""), user=request.user)
        return Response(sale_data(_sale(pk)))


class StockSaleInvoiceView(_AssetView):
    """``POST /stock-sales/{id}/invoice``."""

    @extend_schema(
        request=None,
        responses={201: inline_serializer("StockSaleInvoice", {"draft": serializers.IntegerField()})},
        operation_id="stock_sales_invoice",
    )
    def post(self, request: Request, pk: int) -> Response:
        """Make the draft of an invoice for the buyer; it is issued in Buchhaltung → Ausgangsbelege (needs a customer)."""
        from django.urls import reverse

        from rentalars.documents import free

        if not free.may_change(self.rights):
            raise PermissionDenied
        try:
            draft = sales.invoice_draft(_sale(pk), user=request.user)
        except ValidationError as error:
            raise ApiValidationError({"sale": error.messages}) from error
        return Response(
            {"draft": draft.pk, "url": reverse("documents:free_edit", args=[draft.pk])}, status=status.HTTP_201_CREATED
        )
