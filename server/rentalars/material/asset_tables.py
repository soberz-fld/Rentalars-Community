# SPDX-License-Identifier: GPL-3.0-or-later
"""The Anlagenspiegel and the list of sales from stock as tables: columns to choose, sorting, groups and CSV (MAT-086).

The same table machinery as the other lists (``core.tables``, UIX-015, UIX-040). The Anlagenspiegel is a table over
computed rows (:class:`rentalars.material.book_values.AssetRow` – the book values are worked out, not stored), so every
column sorts and groups in Python; the sales are records of the database. Both pages are for who sees purchase
prices (``rentalars.incoming.access``), so the CSV files are too: the page refuses everybody else before the table.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.money import format_money
from rentalars.core.tables import Column, TableDefinition, badge, date_text, link
from rentalars.material import book_values, sales
from rentalars.material.book_values import AssetRow
from rentalars.material.models import AssetKind
from rentalars.material.sale_models import SaleFromStock

KIND_COLOURS = {AssetKind.FIXED_ASSET: "accent", AssetKind.LOW_VALUE: "yellow", AssetKind.MERCHANDISE: ""}


def _money(value: Decimal | None) -> str:
    """An amount in euros; nothing without an amount."""
    return format_money(value) if value is not None else ""


def _kind(kind: str) -> str:
    """The kind of asset in words; "" for none."""
    return str(AssetKind(kind).label) if kind in AssetKind.values else ""


def _shown(row: AssetRow, name: str) -> Decimal | None:
    """A value of the valuation – nothing for an item that had left the stock or has no book value."""
    if row.left_stock or row.valued.book_value is None:
        return None
    return getattr(row.valued, name)


def _state(row: AssetRow) -> str:
    """What became of the item: where it left the stock, or the state of its valuation."""
    if row.left_stock:
        if row.sold_on is not None:
            return gettext("sold on %(date)s") % {"date": date_text(row.sold_on)}
        return str(row.item.get_status_display())
    return book_values.state_label(row.valued)


def _life(row: AssetRow) -> str:
    """The useful life in months of a fixed asset."""
    return str(row.item.useful_life_months) if row.item.useful_life_months and row.valued.kind == "fixed_asset" else ""


def _amount_column(key: str, label: Any, name: str, *, default: bool = True) -> Column:
    """A column of an amount of the valuation (right-aligned, sorted by the amount)."""
    return Column(
        key,
        label,
        cell=lambda row: _money(_shown(row, name)),
        text=lambda row: _shown(row, name),
        sort=lambda row: _shown(row, name),
        css="num nowrap",
        default=default,
        group=lambda row: _shown(row, name),
    )


ASSET_TABLE = TableDefinition(
    "asset_register",
    [
        Column(
            "id",
            _("ID"),
            cell=lambda row: link(reverse("material:item_detail", args=[row.item.pk]), row.item.display_id, "tape"),
            text=lambda row: row.item.display_id,
            sort=lambda row: row.item.inventory_number,
            fixed=True,
            group=lambda row: row.item.inventory_number,
        ),
        Column(
            "model",
            _("Model"),
            cell=lambda row: link(
                reverse("material:model_detail", args=[row.item.material_model_id]), row.item.material_model.name
            ),
            text=lambda row: row.item.material_model.name,
            sort=lambda row: row.item.material_model.name.casefold(),
            group=lambda row: row.item.material_model_id,
            group_label=lambda row: row.item.material_model.name,
        ),
        Column(
            "kind",
            _("Kind of asset"),
            cell=lambda row: (
                badge(_kind(row.valued.kind), KIND_COLOURS.get(row.valued.kind, ""))
                if row.valued.kind
                else gettext("not recorded")
            ),
            text=lambda row: _kind(row.valued.kind),
            sort=lambda row: _kind(row.valued.kind),
            group=lambda row: row.valued.kind,
            group_label=lambda row: _kind(row.valued.kind) or gettext("not recorded"),
        ),
        Column(
            "acquired",
            _("Date of purchase"),
            cell=lambda row: row.item.purchase_date_text,
            text=lambda row: row.item.purchase_date_text,
            sort=lambda row: row.item.purchase_date,
            css="nowrap",
            group=lambda row: row.item.purchase_date.year if row.item.purchase_date else None,
            group_label=lambda row: row.item.purchase_date.year if row.item.purchase_date else gettext("(no entry)"),
        ),
        Column(
            "life",
            _("Useful life (months)"),
            cell=_life,
            text=lambda row: row.item.useful_life_months,
            sort=lambda row: row.item.useful_life_months,
            css="num",
            group=lambda row: row.item.useful_life_months,
        ),
        Column(
            "quantity",
            _("Quantity"),
            cell=lambda row: str(row.item.quantity) if row.item.material_model.is_bulk else "",
            text=lambda row: row.item.quantity if row.item.material_model.is_bulk else None,
            sort=lambda row: row.item.quantity if row.item.material_model.is_bulk else None,
            css="num",
            default=False,
            group=lambda row: row.item.quantity if row.item.material_model.is_bulk else None,
        ),
        _amount_column("cost", _("Acquisition cost (net)"), "cost"),
        _amount_column("accumulated", _("Depreciation so far"), "accumulated"),
        _amount_column("this_year", _("Depreciation in the year"), "this_year"),
        _amount_column("opening", _("Book value at the start of the year"), "opening_value", default=False),
        _amount_column("book_value", _("Book value"), "book_value"),
        Column(
            "state",
            _("State"),
            cell=_state,
            text=_state,
            sort=_state,
            group=_state,
        ),
        Column(
            "location",
            _("Storage location"),
            cell=lambda row: row.item.effective_storage_location.path if row.item.effective_storage_location else "",
            text=lambda row: row.item.effective_storage_location.path if row.item.effective_storage_location else "",
            sort=lambda row: row.item.effective_storage_location.path if row.item.effective_storage_location else "",
            default=False,
            group=lambda row: row.item.effective_storage_location.path if row.item.effective_storage_location else "",
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda row: row.item.get_status_display(),
            text=lambda row: row.item.get_status_display(),
            sort=lambda row: str(row.item.get_status_display()),
            default=False,
            group=lambda row: row.item.status,
            group_label=lambda row: row.item.get_status_display(),
        ),
        Column(
            "serial",
            _("Serial number"),
            cell=lambda row: row.item.serial_number,
            text=lambda row: row.item.serial_number,
            sort=lambda row: row.item.serial_number,
            default=False,
            group=lambda row: row.item.serial_number,
        ),
    ],
    default_sort="id",
)


# --- Sales from stock -----------------------------------------------------------------------------------------------


def _sale_link(sale: SaleFromStock) -> Any:
    """The day of the sale, linked to the page of the sale."""
    return link(reverse("material:sale_detail", args=[sale.pk]), date_text(sale.sold_on))


def _result(sale: SaleFromStock) -> Any:
    """The gain (green) or loss (red) of a sale; a reversed sale shows none."""
    if sale.is_cancelled:
        return ""
    return badge(format_money(sale.gain_loss), "green" if sale.gain_loss >= 0 else "red")


def _result_text(sale: SaleFromStock) -> Decimal | None:
    """The gain or loss for the CSV file; nothing for a reversed sale."""
    return None if sale.is_cancelled else sale.gain_loss


def _state_of_sale(sale: SaleFromStock) -> str:
    """The words "reversed on …" for a reversed sale; a sale that stands needs none."""
    if sale.is_cancelled:
        return gettext("reversed on %(date)s") % {"date": date_text(sale.cancelled_at)}
    return ""


def _user(user: Any) -> str:
    """The name of a user."""
    return (user.get_full_name() or user.username) if user is not None else ""


def _item_cell(sale: SaleFromStock) -> Any:
    """The ID of the item, linked, and its model."""
    item = sale.item
    return format_html(
        '{} <span class="muted">{}</span>',
        link(reverse("material:item_detail", args=[item.pk]), item.display_id, "tape"),
        item.material_model.name,
    )


SALES_TABLE = TableDefinition(
    "stock_sales",
    [
        Column(
            "sold_on",
            _("Sold on"),
            cell=_sale_link,
            text=lambda sale: sale.sold_on,
            sort=("sold_on", "id"),
            css="nowrap",
            fixed=True,
            group="sold_on",
            group_label=lambda sale: date_text(sale.sold_on),
        ),
        Column(
            "year",
            _("Year"),
            cell=lambda sale: str(sale.sold_on.year),
            text=lambda sale: sale.sold_on.year,
            sort=("sold_on", "id"),
            default=False,
            group=lambda sale: sale.sold_on.year,
        ),
        Column(
            "item",
            _("Item"),
            cell=_item_cell,
            text=lambda sale: f"{sale.item.display_id} {sale.item.material_model.name}",
            sort=("item__inventory_number", "id"),
            group="item__inventory_number",
            group_label=lambda sale: f"{sale.item.display_id} {sale.item.material_model.name}",
        ),
        Column(
            "buyer",
            _("Buyer"),
            cell=lambda sale: sales.buyer_label(sale),
            text=lambda sale: sales.buyer_label(sale),
            sort=lambda sale: sales.buyer_label(sale).casefold(),
            group=lambda sale: sales.buyer_label(sale),
        ),
        Column(
            "quantity",
            _("Quantity"),
            cell=lambda sale: str(sale.quantity),
            sort=("quantity", "id"),
            css="num",
            default=False,
            group="quantity",
        ),
        Column(
            "net",
            _("Price (net)"),
            cell=lambda sale: format_money(sale.net_price),
            text=lambda sale: sale.net_price,
            sort=("net_price", "id"),
            css="num nowrap",
            group="net_price",
        ),
        Column(
            "tax",
            _("Tax"),
            cell=lambda sale: format_money(sale.tax_amount),
            text=lambda sale: sale.tax_amount,
            sort=("tax_percent", "net_price", "id"),
            css="num nowrap",
            default=False,
            group="tax_percent",
            group_label=lambda sale: f"{sale.tax_percent.normalize():f} %",
        ),
        Column(
            "gross",
            _("Price (gross)"),
            cell=lambda sale: format_money(sale.gross_price),
            text=lambda sale: sale.gross_price,
            sort=("net_price", "id"),
            css="num nowrap",
            default=False,
            group="net_price",
        ),
        Column(
            "kind",
            _("Kind of asset"),
            cell=lambda sale: _kind(sale.asset_kind),
            sort=("asset_kind", "id"),
            default=False,
            group="asset_kind",
            group_label=lambda sale: _kind(sale.asset_kind) or gettext("not recorded"),
        ),
        Column(
            "cost",
            _("Acquisition cost (net)"),
            cell=lambda sale: _money(sale.cost),
            text=lambda sale: sale.cost,
            sort=("cost", "id"),
            css="num nowrap",
            default=False,
            group="cost",
        ),
        Column(
            "book_value",
            _("Book value at the sale"),
            cell=lambda sale: format_money(sale.book_value),
            text=lambda sale: sale.book_value,
            sort=("book_value", "id"),
            css="num nowrap",
            group="book_value",
        ),
        Column(
            "gain_loss",
            _("Gain or loss"),
            cell=_result,
            text=_result_text,
            sort=("gain_loss", "id"),
            css="num nowrap",
            group="gain_loss",
        ),
        Column(
            "state",
            _("State"),
            cell=_state_of_sale,
            sort=("cancelled_at", "id"),
            group=lambda sale: sale.is_cancelled,
            group_label=lambda sale: gettext("reversed") if sale.is_cancelled else gettext("stands"),
        ),
        Column(
            "note",
            _("Note"),
            cell=lambda sale: sale.note,
            text=lambda sale: sale.note,
            sort=("note", "id"),
            default=False,
            group="note",
        ),
        Column(
            "sold_by",
            _("Sold by"),
            cell=lambda sale: _user(sale.sold_by),
            sort=("sold_by__last_name", "sold_by__first_name", "sold_by__username", "id"),
            default=False,
            group="sold_by",
            group_label=lambda sale: _user(sale.sold_by),
        ),
    ],
    default_sort="-sold_on",
    row_css=lambda sale: "is-muted" if sale.is_cancelled else "",
)
