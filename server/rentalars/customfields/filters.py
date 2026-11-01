# SPDX-License-Identifier: GPL-3.0-or-later
"""Searching and filtering items by their custom values (MAT-073; MAT-028).

* The item search (list, API, global search, suggestions) finds an item by
  the value of any custom field – never by one visible only with the right
  to see purchase prices: those are kept apart (``protected_value``).
* ``?cf<id>=text`` keeps the items whose value of that field contains the
  text – for each field marked "in lists", on the page and in the API. A
  sensitive field filters only for who may see it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db.models import Q, QuerySet

from rentalars.accounts.rights import Rights, request_rights
from rentalars.customfields import services
from rentalars.customfields.models import CustomFieldValue
from rentalars.customfields.tables import column_key


def search_condition(text: str) -> Q:
    """Items with a custom value containing ``text`` – values of sensitive fields left out (AUT-019)."""
    return Q(pk__in=CustomFieldValue.objects.filter(value__icontains=text).values("item_id"))


def filter_items(queryset: QuerySet[Any], data: Mapping[str, Any], *, request: Any = None) -> QuerySet[Any]:
    """Apply the text filters ``cf<id>=…`` of the fields marked "in lists" the user may see."""
    rights: Rights | None = request_rights(request) if request is not None else None
    for field in services.list_fields():
        text = str(data.get(column_key(field), "") or "").strip()
        if not text:
            continue
        if field.is_sensitive and (rights is None or not field.visible_to(rights)):
            continue
        matching = CustomFieldValue.objects.filter(field_id=field.pk, **{f"{field.column}__icontains": text})
        queryset = queryset.filter(pk__in=matching.values("item_id"))
    return queryset


def filter_choices(data: Mapping[str, Any], rights: Rights) -> list[dict[str, Any]]:
    """The text filters the item list offers: one per field marked "in lists" the user sees."""
    return [
        {"name": column_key(field), "label": field.name, "value": str(data.get(column_key(field), "") or "")}
        for field in services.list_fields(rights)
    ]
