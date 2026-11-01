# SPDX-License-Identifier: GPL-3.0-or-later
"""The material list in the format of the material import (IMP-017; IMP-002, MAT-011).

One row per item with the columns of the import (``material.importer.IMPORT_FIELDS``) – the 13 columns of
MAT-011 and the extras –, written so that the import finds everything again:

* the ID with its leading zeros, "Einsatz/Verbindung" as the ID of the container;
* article name, description, short name, manufacturer, power, product and the category-specific value
  of the material model, the category as its path (``Ton > Mikrofone``);
* the purchase price net, or ``#0851`` for an item bought in a set whose price is noted at 0851 (MAT-054,
  IMP-016) – only with the right to see purchase prices (AUT-019);
* the status by its German name, the storage location as its path, the quantity of bulk material;
* MAT-077: the protection class of the item – its own, else that of its model – as ``I``, ``II``, ``III``;
* MAT-073: after them one column per custom field, headed with its name, as the material
  import reads it (``customfields.importing``): ``12,5 m``, ``01.03.2027``, ``ja``. A field visible only
  with the right to see purchase prices only with that right (:data:`CUSTOM_FIELDS`).

The item's own description and own category-specific values (MAT-013) have no column in the import and
are not in the file. Five queries in all and one more per 2,000 items for the custom values, whatever the
number of items.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from typing import Any

from django.apps import apps
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.import_exports import (
    CategoryIndex,
    ColumnSource,
    ExportColumn,
    ImportFormatExport,
    amount,
    chunked,
    label,
    number,
)
from rentalars.core.tabular import normalise
from rentalars.material.models import ItemStatus, MaterialItem, MaterialModel, TrackingMode
from rentalars.material.numbering import format_inventory_number

#: What is read of each item; the material model and the storage location are added from their own queries.
ITEM_VALUES = (
    "pk",
    "inventory_number",
    "material_model_id",
    "serial_number",
    "note",
    "purchase_date",
    "purchase_date_precision",  # partial purchase date
    "purchase_note",
    "purchase_price",
    "purchase_price_in__inventory_number",
    "supplier__name",
    "supplier_article_number",
    "invoice_number",
    "quantity",
    "status",
    "storage_location_id",
    "storage_spot",
    "installed_in__inventory_number",
    "protection_class_override",
)

MODEL_VALUES = (
    "pk",
    "name",
    "category_id",
    "specification",
    "short_name",
    "manufacturer__name",
    "power_w",
    "default_product__article_number",
    "field_values",
    "tracking_mode",
    "protection_class",
)


def _chunks(rights: Any) -> Iterator[list[dict[str, Any]]]:
    """The items in the order of their IDs, each with its material model and the path of its storage location."""
    from rentalars.masterdata.models import location_paths

    categories = CategoryIndex()
    locations = location_paths()
    models = {row["pk"]: row for row in MaterialModel.objects.order_by().values(*MODEL_VALUES)}
    for model in models.values():
        model["category_path"] = categories.path(model["category_id"])
        model["primary_field"] = categories.primary_field(model["category_id"])
    items = MaterialItem.objects.order_by("inventory_number").values(*ITEM_VALUES)
    for chunk in chunked(items.iterator(chunk_size=2000)):
        for row in chunk:
            row["model"] = models[row["material_model_id"]]
            row["location"] = locations.get(row["storage_location_id"], "")
        yield chunk


def _category_specific(row: dict[str, Any]) -> str:
    """The category-specific value as the pages show it (``5 m``); the import reads it back (MAT-009)."""
    model = row["model"]
    values = model["field_values"] or {}
    unassigned = values.get("unassigned", "")
    field = model["primary_field"]
    if field is None:
        return unassigned
    return field.display_value(values.get(str(field.pk), "")) or unassigned


def _price(row: dict[str, Any]) -> str | None:
    """The purchase price, or ``#0851`` for an item whose price is included in that of 0851 (IMP-016)."""
    head = row["purchase_price_in__inventory_number"]
    if head is not None:
        return f"#{format_inventory_number(head)}"
    return amount(row["purchase_price"])


def _purchase_date(row: dict[str, Any]) -> Any:
    """Partial purchase date: the date; of an old item with an unknown day or month ``00.05.2015`` / ``00.00.2015``.

    The import reads that notation back, so a list exported and imported again keeps what was known.
    """
    bought, precision = row["purchase_date"], row["purchase_date_precision"]
    if bought is None or precision == "day":
        return bought
    return f"00.{bought.month:02d}.{bought.year:04d}" if precision == "month" else f"00.00.{bought.year:04d}"


def _container(row: dict[str, Any]) -> str | None:
    number_of_container = row["installed_in__inventory_number"]
    return format_inventory_number(number_of_container) if number_of_container is not None else None


EXPORT = ImportFormatExport(
    key="material",
    name=_("Material"),
    columns=(
        ExportColumn("inventory_number", lambda row: format_inventory_number(row["inventory_number"])),
        ExportColumn("name", lambda row: row["model"]["name"]),
        ExportColumn("category", lambda row: row["model"]["category_path"]),
        ExportColumn("specification", lambda row: row["model"]["specification"]),
        ExportColumn("category_specific", _category_specific),
        ExportColumn("installed_in", _container),
        ExportColumn("serial_number", lambda row: row["serial_number"]),
        ExportColumn("note", lambda row: row["note"]),
        ExportColumn("purchase_date", _purchase_date),
        ExportColumn("purchase_note", lambda row: row["purchase_note"]),
        ExportColumn("purchase_price", _price, right=SpecialRight.PURCHASE_PRICES),
        ExportColumn("supplier", lambda row: row["supplier__name"]),
        ExportColumn("supplier_article_number", lambda row: row["supplier_article_number"]),
        ExportColumn("manufacturer", lambda row: row["model"]["manufacturer__name"]),
        ExportColumn("short_name", lambda row: row["model"]["short_name"]),
        # Bulk material only (MAT-005); an individual item always counts 1.
        ExportColumn(
            "quantity", lambda row: row["quantity"] if row["model"]["tracking_mode"] == TrackingMode.BULK else None
        ),
        ExportColumn("status", lambda row: label(ItemStatus, row["status"])),
        ExportColumn("storage_location", lambda row: row["location"]),
        ExportColumn("storage_spot", lambda row: row["storage_spot"]),
        ExportColumn("product", lambda row: row["model"]["default_product__article_number"]),
        ExportColumn("invoice_number", lambda row: row["invoice_number"]),
        ExportColumn("power", lambda row: number(row["model"]["power_w"])),
        # MAT-077: the class that applies to the item – its own, else its model's – as I, II or III.
        ExportColumn(
            "protection_class", lambda row: row["protection_class_override"] or row["model"]["protection_class"]
        ),
    ),
    chunks=_chunks,
)


# --- MAT-073: the custom values of the items ---------------------------------------------------


def _custom_columns(rights: Any) -> list[ExportColumn]:
    """One column per custom field the rights may see, headed with its name, in the order of the names.

    The material import fills a custom field from the column of its name, unless the column is taken by
    one of its own fields. A field whose name is a heading of a column the file leaves out for these rights
    (purchase price without that right: "Preis", "EK") would be taken by that field – it is left out.
    """
    if not apps.is_installed("rentalars.customfields"):
        return []
    from rentalars.customfields.models import CustomField
    from rentalars.material.importer import IMPORT_FIELDS

    present = {column.key for column in EXPORT.columns if not column.right or rights.has(column.right)}
    taken = {
        heading
        for field in IMPORT_FIELDS
        if field.key not in present
        for heading in (normalise(field.label), *field.aliases)
    }
    return [
        ExportColumn(f"custom.{field.pk}", partial(_custom_value, field), heading=field.name)
        for field in CustomField.objects.order_by("name")
        if field.visible_to(rights) and normalise(field.name) not in taken
    ]


def _custom_value(field: Any, row: dict[str, Any]) -> str:
    """The custom value of an item as the item's page shows it, which the import reads back: ``12,5 m``."""
    return field.display_value(row["custom"].get(field.pk, ""))


def _load_custom_values(chunk: list[dict[str, Any]]) -> None:
    """The custom values of a chunk of items, from one query."""
    if not apps.is_installed("rentalars.customfields"):
        return
    from rentalars.customfields.models import CustomFieldValue

    values: dict[int, dict[int, str]] = {row["pk"]: {} for row in chunk}
    for item_id, field_id, value, protected in CustomFieldValue.objects.filter(item_id__in=values).values_list(
        "item_id", "field_id", "value", "protected_value"
    ):
        if value or protected:
            values[item_id][field_id] = protected or value
    for row in chunk:
        row["custom"] = values[row["pk"]]


#: Registered in ``material.apps`` next to :data:`EXPORT` (``core.import_exports.register_columns``).
CUSTOM_FIELDS = ColumnSource(columns=_custom_columns, prepare=_load_custom_values)
