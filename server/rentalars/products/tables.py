# SPDX-License-Identifier: GPL-3.0-or-later
"""The product list as a table with columns to choose (UIX-015, IMP-005).

Stock figures are not fields of the product but counted from the material.
The view counts them once for all rows (``attach_stock``) before the table
draws its cells.
"""

from __future__ import annotations

from typing import Any

from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.availability.stock import NO_STOCK, stock_of_products
from rentalars.core.money import format_decimal, format_money
from rentalars.core.tables import Column, TableDefinition, badge, link
from rentalars.products.models import ProductKind


def _prices(rights: Rights) -> bool:
    return rights.has(SpecialRight.PRICES)


def _purchase_prices(rights: Rights) -> bool:
    """LOG-010: the internal costs of a vehicle need the right to see purchase prices."""
    return rights.has(SpecialRight.PURCHASE_PRICES)


def _trailer_billing(product: Any) -> str:
    """LOG-005: how a trailer is billed; empty for everything else."""
    return str(product.get_trailer_billing_display()) if product.is_trailer else ""


def attach_stock(products: list[Any]) -> list[Any]:
    """Count the stock of all products with one query and hang it on each as ``stock_info``."""
    stocks = stock_of_products([product.pk for product in products])
    for product in products:
        product.stock_info = stocks.get(product.pk, NO_STOCK)
    return products


def _name(product: Any) -> Any:
    name = link(reverse("products:detail", args=[product.pk]), product.name)
    if product.owner_id:
        # PRD-043: customer material is told apart at a glance.
        name = format_html("{} {}", name, badge(_("customer material"), "accent"))
    if not product.is_active:
        return format_html('{} <span class="badge">{}</span>', name, _("deactivated"))
    return name


def _owner(product: Any) -> str:
    """PRD-043: the customer the material belongs to; empty for own material."""
    return product.owner.name if product.owner_id else ""


def _price(product: Any) -> str:
    if product.owner_id:
        return ""  # PRD-043: customer material has no price
    if product.is_percent_surcharge:
        return f"{format_decimal(product.surcharge_percent)} %"
    return format_money(_one_price(product))


def _one_price(product: Any) -> Any:
    """PRD-047: the sale price of a sale product, the price of every other product."""
    return product.sale_price if product.kind == ProductKind.SALE else product.price


def _stock(product: Any) -> Any:
    if not product.tracks_stock:
        return format_html('<span class="muted">–</span>')
    stock = product.stock_info
    text = format_html("{}", stock.plannable)
    if stock.total != stock.plannable:
        text = format_html('{} <span class="muted">/ {}</span>', stock.plannable, stock.total)
    text = format_html("{} {}", text, product.unit.abbreviation)
    if stock.consists_of_pieces:
        # The stock counts products; the items behind them are what is physically there.
        text = format_html(
            '{} <span class="muted small" title="{}">({})</span>',
            text,
            _("Items that can be planned"),
            ngettext("%(count)s item", "%(count)s items", stock.plannable_pieces) % {"count": stock.plannable_pieces},
        )
    if product.minimum_stock and stock.operational < product.minimum_stock:
        return format_html("{} {}", text, badge(_("below minimum"), "red"))
    return text


def _is_low(product: Any) -> bool:
    return bool(
        product.minimum_stock and product.tracks_stock and product.stock_info.operational < product.minimum_stock
    )


def _stock_for_sorting(products: list[Any], request: Any) -> None:
    """UIX-015: the stock of every product of the list, before it is sorted by a stock column."""
    attach_stock(products)


PRODUCT_TABLE = TableDefinition(
    "products",
    [
        Column(
            "number",
            _("Article no."),
            cell=lambda product: link(reverse("products:detail", args=[product.pk]), product.article_number, "artno"),
            text=lambda product: product.article_number,
            sort="article_number",
            fixed=True,
            group="article_number",
        ),
        # UIX-044: every column groups – by its field; price, stock and buffer by what they show.
        Column("name", _("Name"), cell=_name, text=lambda product: product.name, sort="name", group="name"),
        Column(
            "category",
            _("Category"),
            cell=lambda product: product.category.name,
            sort=("category__name", "article_number"),
            group="category",
        ),
        Column(
            # PRD-043: the owner of customer material; empty for own material.
            "owner",
            _("Owner"),
            cell=_owner,
            sort=("owner__name", "article_number"),
            default=False,
            group="owner",
        ),
        Column(
            "kind",
            _("Kind"),
            cell=lambda product: capfirst(product.get_kind_display()),
            sort=("kind", "article_number"),
            group="kind",
        ),
        # PRD-047: "Price" is the one price of every product – the sale price of a sale
        # product; the column "Sale price" is gone. The import reads "Preis" the same way.
        Column(
            "price",
            _("Price"),
            cell=_price,
            text=lambda product: product.surcharge_percent if product.is_percent_surcharge else _one_price(product),
            sort=(Coalesce("price", "sale_price"), "article_number"),
            css="num",
            visible_if=_prices,
        ),
        Column(
            # PRD-041: empty is no limit, 0 never discounted.
            "max_discount",
            _("Maximum discount"),
            cell=lambda product: (
                f"{format_decimal(product.max_discount_percent)} %" if product.max_discount_percent is not None else "–"
            ),
            text=lambda product: product.max_discount_percent,
            sort=("max_discount_percent", "article_number"),
            css="num",
            default=False,
            visible_if=_prices,
            group="max_discount_percent",
        ),
        Column(
            "stock",
            _("Stock"),
            cell=_stock,
            text=lambda product: product.stock_info.plannable if product.tracks_stock else None,
            # UIX-015: the stock is counted, not stored – sorted in Python after counting it for the list.
            sort=lambda product: product.stock_info.plannable if product.tracks_stock else None,
            sort_prepare=_stock_for_sorting,
            css="num nowrap",
        ),
        Column(
            "total_stock",
            _("Total stock"),
            cell=lambda product: product.stock_info.total if product.tracks_stock else "",
            sort=lambda product: product.stock_info.total if product.tracks_stock else None,
            sort_prepare=_stock_for_sorting,
            css="num",
            default=False,
        ),
        Column(
            "pieces_per_product",
            _("Pieces per product"),
            cell=lambda product: product.pieces_per_product if product.pieces_per_product > 1 else "",
            text=lambda product: product.pieces_per_product,
            sort=("pieces_per_product", "article_number"),
            css="num",
            default=False,
            group="pieces_per_product",
        ),
        Column(
            "minimum_stock",
            _("Minimum stock"),
            cell=lambda product: product.minimum_stock or "",
            text=lambda product: product.minimum_stock,
            sort=("minimum_stock", "article_number"),
            css="num",
            default=False,
            group="minimum_stock",
        ),
        Column(
            "below_minimum",
            _("Below minimum"),
            cell=lambda product: badge(_("yes"), "red") if _is_low(product) else "",
            text=_is_low,
            # Those below the minimum last; descending first.
            sort=_is_low,
            sort_prepare=_stock_for_sorting,
            default=False,
        ),
        Column(
            "unit",
            _("Unit"),
            cell=lambda product: product.unit.name,
            sort="unit__name",
            default=False,
            group="unit",
        ),
        Column(
            "billing_mode",
            _("Billing mode"),
            cell=lambda product: product.get_billing_mode_display(),
            sort=("billing_mode", "article_number"),
            default=False,
            visible_if=_prices,
            group="billing_mode",
        ),
        Column(
            "tax_rate",
            _("Tax rate"),
            cell=lambda product: str(product.tax_rate),
            sort=("tax_rate__rate", "article_number"),
            default=False,
            visible_if=_prices,
            group="tax_rate",
        ),
        Column("gtin", _("GTIN/EAN"), cell=lambda product: product.gtin, sort="gtin", default=False, group="gtin"),
        Column(
            "buffer",
            _("Buffer before/after (h)"),
            cell=lambda product: " / ".join(
                format_decimal(value) if value is not None else "–"
                for value in (product.buffer_before_hours, product.buffer_after_hours)
            ),
            sort=("buffer_before_hours", "buffer_after_hours", "article_number"),
            default=False,
        ),
        # LOG-002, LOG-005, LOG-010: the type, rates and costs of a vehicle – the headings the import reads.
        Column(
            "vehicle_type",
            _("Vehicle type"),
            cell=lambda product: product.get_vehicle_type_display() if product.vehicle_type else "",
            sort=("vehicle_type", "article_number"),
            default=False,
            group="vehicle_type",
        ),
        Column(
            "price_per_km",
            _("Price per km"),
            cell=lambda product: format_money(product.price_per_km),
            text=lambda product: product.price_per_km,
            sort=("price_per_km", "article_number"),
            css="num",
            default=False,
            visible_if=_prices,
            group="price_per_km",
        ),
        Column(
            "trailer_surcharge",
            _("Trailer surcharge per km"),
            cell=lambda product: format_money(product.trailer_surcharge_per_km),
            text=lambda product: product.trailer_surcharge_per_km,
            sort=("trailer_surcharge_per_km", "article_number"),
            css="num",
            default=False,
            visible_if=_prices,
            group="trailer_surcharge_per_km",
        ),
        Column(
            "trailer_billing",
            _("Trailer billed"),
            cell=_trailer_billing,
            sort=("vehicle_type", "trailer_billing", "article_number"),
            default=False,
        ),
        Column(
            "cost_per_km",
            _("Internal cost per km"),
            cell=lambda product: format_money(product.cost_per_km),
            text=lambda product: product.cost_per_km,
            sort=("cost_per_km", "article_number"),
            css="num",
            default=False,
            visible_if=_purchase_prices,
            group="cost_per_km",
        ),
        Column(
            "cost_per_day",
            _("Internal cost per day"),
            cell=lambda product: format_money(product.cost_per_day),
            text=lambda product: product.cost_per_day,
            sort=("cost_per_day", "article_number"),
            css="num",
            default=False,
            visible_if=_purchase_prices,
            group="cost_per_day",
        ),
        Column(
            "active",
            _("Active"),
            cell=lambda product: _("yes") if product.is_active else _("no"),
            text=lambda product: product.is_active,
            sort=("is_active", "article_number"),
            default=False,
            group="is_active",
        ),
    ],
    default_sort="number",
    row_css=lambda product: "" if product.is_active else "is-muted",
)
