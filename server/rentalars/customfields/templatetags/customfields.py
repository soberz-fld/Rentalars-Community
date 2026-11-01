# SPDX-License-Identifier: GPL-3.0-or-later
"""Template tags that show custom fields on the pages of the material module (MAT-073).

The pages of material models and items show the fieldset and the values
without their views having to know about custom fields:

``{% item_custom_fields item as custom %}``
    the values of an item the reader may see, the missing required ones and
    the values kept from fields outside the fieldset;
``{% model_fieldset model as fieldset %}``
    the fieldset of a material model with its fields;
``{% custom_list_filters as custom_filters %}``
    the text filters of the item list;
``{% items_missing_required items as missing %}``
    the items of a list that lack a required value (after a purchase);
``{% custom_field_names as names %}``
    the fields the material import reads from columns of their name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django import template

from rentalars.accounts.rights import Rights, request_rights
from rentalars.customfields import services
from rentalars.customfields.filters import filter_choices
from rentalars.customfields.models import CustomField, Fieldset, FieldsetEntry
from rentalars.customfields.tables import value_html

register = template.Library()


def _rights(context: template.Context) -> Rights | None:
    rights = context.get("rights")
    if rights is not None:
        return rights
    request = context.get("request")
    return request_rights(request) if request is not None else None


@dataclass
class ItemValues:
    """What the item page shows of the custom fields."""

    fieldset: Fieldset | None
    rows: list[dict[str, Any]] = field(default_factory=list)
    others: list[dict[str, Any]] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        """The names of required fields without a value."""
        return [row["name"] for row in self.rows if row["missing"]]

    @property
    def shown(self) -> bool:
        """Whether there is anything to show."""
        return bool(self.rows or self.others)


def _row(value_row: services.ValueRow) -> dict[str, Any]:
    return {
        "name": value_row.field.label_with_unit,
        "html": value_html(value_row.field, value_row.stored),
        "missing": value_row.missing,
        "required": value_row.required,
        "sensitive": value_row.field.is_sensitive,
    }


@register.simple_tag(takes_context=True)
def item_custom_fields(context: template.Context, item: Any) -> ItemValues:
    """The custom fields of an item for its page; fields the reader may not see are left out (AUT-019)."""
    rights = _rights(context)
    if rights is None or item is None:
        return ItemValues(None)
    return ItemValues(
        services.fieldset_of(item.material_model),
        [_row(row) for row in services.value_rows(item, rights)],
        [_row(row) for row in services.other_value_rows(item, rights)],
    )


@dataclass
class ModelFieldsetInfo:
    """The fieldset of a material model with its fields, for the model page."""

    fieldset: Fieldset
    entries: list[FieldsetEntry]


@register.simple_tag
def model_fieldset(material_model: Any) -> ModelFieldsetInfo | None:
    """The fieldset of a material model, or ``None``."""
    fieldset = services.fieldset_of(material_model)
    if fieldset is None:
        return None
    return ModelFieldsetInfo(fieldset, services.entries_of(material_model))


@register.simple_tag(takes_context=True)
def custom_list_filters(context: template.Context) -> list[dict[str, Any]]:
    """The text filters of the item list – one per field marked "in lists" the reader sees."""
    rights = _rights(context)
    request = context.get("request")
    if rights is None or request is None:
        return []
    return filter_choices(request.GET, rights)


@register.simple_tag
def items_missing_required(items: Any) -> list[Any]:
    """The items that lack a value of a required custom field."""
    items = list(items or [])
    services.load_values(items)
    return [item for item in items if services.missing_required(item)]


@register.simple_tag(takes_context=True)
def custom_field_names(context: template.Context) -> list[str]:
    """The names of the custom fields the material import reads – those the reader may set (AUT-019)."""
    rights = _rights(context)
    return [field.name for field in CustomField.objects.order_by("name") if rights is None or field.visible_to(rights)]
