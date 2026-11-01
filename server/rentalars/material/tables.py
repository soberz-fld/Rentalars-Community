# SPDX-License-Identifier: GPL-3.0-or-later
"""The lists of the material module as tables with chosen columns (UIX-015, MAT-012).

The item list shows the 13 fields of MAT-011 by default, one row per item,
like the spreadsheet it replaces. Further columns can be switched on.
"""

from __future__ import annotations

from typing import Any

from django.db.models import F, Value
from django.db.models.functions import Coalesce, NullIf
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.money import format_decimal, format_money
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day, link, natural_key
from rentalars.core.templatetags.rentalars import status_colour
from rentalars.masterdata.models import remember_location_paths


def _set_price_cell(item: Any) -> SafeString:
    """MAT-054: the price of a member of a set is that of the item named – shown as "in 0851"."""
    return format_html(
        '<span class="muted" title="{}">#{}</span>',
        _("Included in the price of %(id)s") % {"id": item.purchase_price_in.display_id},
        item.purchase_price_in.display_id,
    )


def _purchase_prices(rights: Rights) -> bool:
    return rights.has(SpecialRight.PURCHASE_PRICES)


def _item_link(item: Any) -> Any:
    return link(reverse("material:item_detail", args=[item.pk]), item.display_id, "tape")


def _container(item: Any) -> Any:
    if not item.installed_in_id:
        return ""
    return link(reverse("material:item_detail", args=[item.installed_in_id]), item.installed_in.display_id, "tape")


def _model_name(item: Any) -> Any:
    model = item.material_model
    name = link(reverse("material:model_detail", args=[model.pk]), model.name)
    if model.is_bulk:
        return format_html('{} <span class="badge">{} {}</span>', name, item.quantity, _("pcs."))
    return name


def _product(product: Any) -> Any:
    if product is None:
        return ""
    return link(reverse("products:detail", args=[product.pk]), f"{product.article_number} {product.name}")


def _truncated(text: str, length: int) -> str:
    return text if len(text) <= length else text[: length - 1] + "…"


def _location(item: Any) -> str:
    """The storage location, with the spot within it: "Halle 1 › Regal 01-A-1" (MAT-080)."""
    location = item.effective_storage_location
    if location is None:
        return ""
    spot = item.effective_storage_spot
    return f"{location.path} {spot}" if spot else location.path


def _prepare_items(items: list[Any]) -> None:
    """The paths of all storage locations of the page from one query, not one per row and level."""
    remember_location_paths(item.effective_storage_location for item in items)


ITEM_TABLE = TableDefinition(
    "material_items",
    [
        # UIX-044: every column groups – by its field in the database; the computed ones (description,
        # category-specific value, product, short name) by what they show, for a list of at most 2,000 items.
        Column(
            "id",
            _("ID"),
            cell=_item_link,
            text=lambda item: item.display_id,
            sort="inventory_number",
            fixed=True,
            group="inventory_number",
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda item: badge(item.get_status_display(), status_colour(item.status)),
            text=lambda item: item.get_status_display(),
            sort=("status", "inventory_number"),
            group="status",
        ),
        Column(
            "name",
            _("Article name"),
            cell=_model_name,
            text=lambda item: item.material_model.name,
            sort=("material_model__name", "inventory_number"),
            group="material_model",
        ),
        Column(
            "category",
            _("Category"),
            cell=lambda item: item.material_model.category.name,
            sort=("material_model__category__name", "inventory_number"),
            group="material_model__category",
        ),
        Column(
            "specification",
            _("Description"),  # MAT-049: "Spezifikation" of MAT-011
            cell=lambda item: _truncated(item.effective_specification, 40),
            text=lambda item: item.effective_specification,
            sort=("material_model__specification", "inventory_number"),
        ),
        Column(
            "category_specific",
            _("Category-specific"),
            cell=lambda item: item.category_specific_display,
            # UIX-015: the value depends on the category's first field – sorted in Python, "5 m" before "10 m".
            sort=lambda item: natural_key(item.category_specific_display),
            css="nowrap",
        ),
        Column(
            "installed_in",
            _("Installed in"),
            cell=_container,
            text=lambda item: item.installed_in.display_id if item.installed_in_id else "",
            sort=("installed_in__inventory_number", "inventory_number"),
            group="installed_in",
        ),
        Column(
            "serial",
            _("Serial number"),
            cell=lambda item: item.serial_number,
            sort="serial_number",
            group="serial_number",
        ),
        Column(
            "note",
            _("Note"),
            cell=lambda item: _truncated(item.note, 40),
            text=lambda item: item.note,
            sort=("note", "inventory_number"),
            group="note",
            group_label=lambda item: item.note,
            default=False,
        ),
        Column(
            "purchased",
            _("Invoice date"),  # MAT-050: "Tag des Kaufs" of MAT-011
            # Partial purchase date: "2015" / "05.2015" for an old item; a year sorts before the dated items of it.
            cell=lambda item: item.purchase_date_text,
            text=lambda item: item.purchase_date if item.purchase_date_precision == "day" else item.purchase_date_text,
            sort=("purchase_date", "-purchase_date_precision", "inventory_number"),
            css="nowrap",
            group="purchase_date",
            default=False,
        ),
        Column(
            "purchase_note",
            _("Purchase note"),
            cell=lambda item: _truncated(item.purchase_note, 30),
            text=lambda item: item.purchase_note,
            sort=("purchase_note", "inventory_number"),
            group="purchase_note",
            group_label=lambda item: item.purchase_note,
            default=False,
        ),
        Column(
            "purchase_price",
            _("Purchase price"),
            # MAT-054, IMP-016: bought as a set – "#0851" names the item with the price, as the import reads it.
            cell=lambda item: _set_price_cell(item) if item.purchase_price_in_id else format_money(item.purchase_price),
            text=lambda item: (
                f"#{item.purchase_price_in.display_id}" if item.purchase_price_in_id else item.purchase_price
            ),
            sort="purchase_price",
            css="num",
            visible_if=_purchase_prices,
            group="purchase_price",
            default=False,
        ),
        Column(
            "supplier",
            _("Bought from"),
            cell=lambda item: item.supplier or "",
            sort=("supplier__name", "inventory_number"),
            group="supplier",
            default=False,
        ),
        Column(
            "supplier_number",
            _("Supplier's no."),
            cell=lambda item: item.supplier_article_number,
            sort=("supplier_article_number", "inventory_number"),
            group="supplier_article_number",
            default=False,
        ),
        # Not among the 13 fields of MAT-011: off unless switched on.
        Column(
            "invoice_number",
            _("Invoice number"),  # MAT-050
            cell=lambda item: item.invoice_number,
            sort=("invoice_number", "inventory_number"),
            default=False,
            group="invoice_number",
        ),
        Column(
            "product",
            _("Product"),
            cell=lambda item: _product(item.product),
            text=lambda item: f"{item.product.article_number} {item.product.name}" if item.product else "",
            # The item's own product first, else that of its model – as the cell shows it.
            sort=(
                Coalesce("product_override__article_number", "material_model__default_product__article_number"),
                "inventory_number",
            ),
            default=False,
        ),
        Column(
            "location",
            _("Storage location"),
            cell=_location,
            sort=("storage_location__name", "storage_spot", "inventory_number"),
            default=False,
            group="storage_location",
        ),
        Column(
            "manufacturer",
            _("Manufacturer"),
            cell=lambda item: item.material_model.manufacturer or "",
            sort=("material_model__manufacturer__name", "inventory_number"),
            default=False,
            group="material_model__manufacturer",
        ),
        Column(
            "short_name",
            _("Short name"),
            cell=lambda item: item.material_model.display_short_name,
            sort=("material_model__short_name", "inventory_number"),
            default=False,
        ),
        Column(
            "status_reason",
            _("Reason for the status"),
            cell=lambda item: _truncated(item.status_reason, 40),
            text=lambda item: item.status_reason,
            sort=("status_reason", "inventory_number"),
            default=False,
            group="status_reason",
            group_label=lambda item: item.status_reason,
        ),
        Column(
            "quantity",
            _("Quantity"),
            cell=lambda item: item.quantity,
            sort=("quantity", "inventory_number"),
            css="num",
            default=False,
            group="quantity",
        ),
        Column(
            "created",
            _("Created"),
            cell=lambda item: date_text(item.created_at),
            text=lambda item: item.created_at,
            sort="created_at",
            css="nowrap",
            default=False,
            **grouped_by_day("created_at"),
        ),
        # MAT-077: the item's own protection class, else that of its model – sorted and grouped the same way.
        Column(
            "protection_class",
            _("Protection class"),
            cell=lambda item: item.effective_protection_class,
            sort=(
                Coalesce(NullIf("protection_class_override", Value("")), "material_model__protection_class"),
                "inventory_number",
            ),
            default=False,
        ),
    ],
    default_sort="id",
    prepare=_prepare_items,
)


def _model_name(material_model: Any) -> Any:
    name = link(reverse("material:model_detail", args=[material_model.pk]), material_model.name)
    if material_model.is_bulk:
        return format_html('{} <span class="badge">{}</span>', name, _("bulk"))
    return name


def _model_product(material_model: Any) -> Any:
    if material_model.default_product_id is None:
        return badge(_("none"), "yellow")
    product = material_model.default_product
    return link(reverse("products:detail", args=[product.pk]), product.article_number, "artno")


MODEL_TABLE = TableDefinition(
    "material_models",
    [
        # UIX-044: every column groups – by its field; items, category-specific value, dimensions and
        # volume by what they show.
        Column(
            "name",
            _("Article name"),
            cell=_model_name,
            text=lambda model: model.name,
            sort="name",
            fixed=True,
            group="name",
        ),
        Column(
            "category",
            _("Category"),
            cell=lambda model: model.category.path,
            sort=("category__name", "name"),
            group="category",
        ),
        Column(
            "manufacturer",
            _("Manufacturer"),
            cell=lambda model: model.manufacturer or "",
            sort=("manufacturer__name", "name"),
            group="manufacturer",
        ),
        Column(
            "product",
            _("Product"),
            cell=_model_product,
            text=lambda model: model.default_product.article_number if model.default_product_id else "",
            sort=("default_product__article_number", "name"),
            group="default_product",
        ),
        Column("items", _("Items"), cell=lambda model: model.item_count, sort="item_count", css="num"),
        Column(
            "short_name",
            _("Short name"),
            cell=lambda model: model.short_name,
            sort="short_name",
            default=False,
            group="short_name",
        ),
        Column(
            "specification",
            _("Description"),  # MAT-049
            cell=lambda model: _truncated(model.specification, 40),
            text=lambda model: model.specification,
            sort=("specification", "name"),
            default=False,
            group="specification",
            group_label=lambda model: model.specification,
        ),
        Column(
            "category_specific",
            _("Category-specific"),
            cell=lambda model: model.category_specific_display,
            sort=lambda model: natural_key(model.category_specific_display),
            css="nowrap",
            default=False,
        ),
        Column(
            "weight",
            _("Weight (kg)"),
            cell=lambda model: format_decimal(model.weight_kg),
            text=lambda model: model.weight_kg,
            sort=("weight_kg", "name"),
            css="num",
            default=False,
            group="weight_kg",
        ),
        Column(
            "dimensions",
            _("Dimensions"),
            cell=lambda model: model.dimensions_display,
            sort=("length_cm", "width_cm", "height_cm", "name"),
            css="nowrap",
            default=False,
        ),
        Column(
            "volume",
            _("Volume (l)"),
            cell=lambda model: format_decimal(model.volume_litres),
            text=lambda model: model.volume_litres,
            # Empty where a dimension is missing, as the cell (MAT-016).
            sort=(F("length_cm") * F("width_cm") * F("height_cm"), "name"),
            css="num",
            default=False,
        ),
        Column(
            "power",
            _("Power (W)"),  # MAT-049
            cell=lambda model: format_decimal(model.power_w),
            text=lambda model: model.power_w,
            sort=("power_w", "name"),
            css="num",
            default=False,
            group="power_w",
        ),
        Column(
            "tracking",
            _("Tracked as"),
            cell=lambda model: model.get_tracking_mode_display(),
            sort=("tracking_mode", "name"),
            default=False,
            group="tracking_mode",
        ),
        Column(
            "protection_class",
            _("Protection class"),  # MAT-077
            cell=lambda model: model.protection_class,
            sort=("protection_class", "name"),
            default=False,
            group="protection_class",
        ),
    ],
    default_sort="name",
)
