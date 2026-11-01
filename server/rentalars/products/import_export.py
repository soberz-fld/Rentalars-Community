# SPDX-License-Identifier: GPL-3.0-or-later
"""The products in the format of the product import (IMP-017; IMP-001, PRD-008).

One row per product with the columns of ``products.importer.IMPORT_FIELDS``: the article number, the
category as its path below the main category its letters name, kind, billing mode, vehicle type and the
billing of a trailer by their German names, unit and tax rate by their names, the owner of customer
material by its customer number (PRD-043).

"Preis" is the one price of a product – for a sale product its sale price, which "Verkaufspreis" repeats
(PRD-047). Prices, the maximum discount and the rates of vehicles need the right to see prices, the
internal costs of vehicles the right to see purchase prices (LOG-010) – as the import and the list ask.
Three queries in all, whatever the number of products.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.import_exports import (
    CategoryIndex,
    ExportColumn,
    ImportFormatExport,
    amount,
    chunked,
    label,
    number,
)
from rentalars.products.models import BillingMode, Product, ProductKind, TrailerBilling, VehicleType

PRODUCT_VALUES = (
    "pk",
    "article_number",
    "name",
    "category_id",
    "kind",
    "price",
    "sale_price",
    "max_discount_percent",
    "unit__name",
    "tax_rate__name",
    "billing_mode",
    "gtin",
    "description",
    "note",
    "minimum_stock",
    "pieces_per_product",
    "is_active",
    "owner__number",
    "vehicle_type",
    "price_per_km",
    "trailer_surcharge_per_km",
    "trailer_billing",
    "cost_per_km",
    "cost_per_day",
)


def _chunks(rights: Any) -> Iterator[list[dict[str, Any]]]:
    """The products in the order of their article numbers, each with the path of its category."""
    categories = CategoryIndex()
    products = Product.objects.order_by("article_number").values(*PRODUCT_VALUES)
    for chunk in chunked(products.iterator(chunk_size=2000)):
        for row in chunk:
            row["category_path"] = categories.path(row["category_id"])
        yield chunk


def _price(row: dict[str, Any]) -> str | None:
    """PRD-047: the price of the product – of a sale product its sale price."""
    return amount(row["sale_price"] if row["kind"] == ProductKind.SALE else row["price"])


EXPORT = ImportFormatExport(
    key="products",
    name=_("Products"),
    columns=(
        ExportColumn("article_number", lambda row: row["article_number"]),
        ExportColumn("name", lambda row: row["name"]),
        ExportColumn("category", lambda row: row["category_path"]),
        ExportColumn("kind", lambda row: label(ProductKind, row["kind"])),
        ExportColumn("price", _price, right=SpecialRight.PRICES),
        ExportColumn(
            "sale_price",
            lambda row: amount(row["sale_price"]) if row["kind"] == ProductKind.SALE else None,
            right=SpecialRight.PRICES,
        ),
        ExportColumn("max_discount", lambda row: number(row["max_discount_percent"]), right=SpecialRight.PRICES),
        ExportColumn("unit", lambda row: row["unit__name"]),
        ExportColumn("tax_rate", lambda row: row["tax_rate__name"]),
        ExportColumn("billing_mode", lambda row: label(BillingMode, row["billing_mode"])),
        ExportColumn("gtin", lambda row: row["gtin"]),
        ExportColumn("description", lambda row: row["description"]),
        ExportColumn("note", lambda row: row["note"]),
        # The import reads 0 as "no minimum stock".
        ExportColumn("minimum_stock", lambda row: row["minimum_stock"] or None),
        # Products of several pieces: always given, 1 included – the import reads it back as it is.
        ExportColumn("pieces_per_product", lambda row: row["pieces_per_product"]),
        ExportColumn("active", lambda row: row["is_active"]),
        ExportColumn("owner", lambda row: row["owner__number"]),
        ExportColumn("vehicle_type", lambda row: label(VehicleType, row["vehicle_type"])),
        ExportColumn("price_per_km", lambda row: amount(row["price_per_km"]), right=SpecialRight.PRICES),
        ExportColumn(
            "trailer_surcharge", lambda row: amount(row["trailer_surcharge_per_km"]), right=SpecialRight.PRICES
        ),
        # LOG-005: only a trailer is billed per day or per kilometre; the import leaves an empty cell alone.
        ExportColumn(
            "trailer_billing",
            lambda row: (
                label(TrailerBilling, row["trailer_billing"]) if row["vehicle_type"] == VehicleType.TRAILER else None
            ),
        ),
        ExportColumn("cost_per_km", lambda row: amount(row["cost_per_km"]), right=SpecialRight.PURCHASE_PRICES),
        ExportColumn("cost_per_day", lambda row: amount(row["cost_per_day"]), right=SpecialRight.PURCHASE_PRICES),
    ),
    chunks=_chunks,
)
