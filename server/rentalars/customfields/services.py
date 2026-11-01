# SPDX-License-Identifier: GPL-3.0-or-later
"""What the pages, the API and the import do with custom fields (MAT-073).

The fieldset of a material model and the values of an item are looked up
here, checked here and stored here, so that a form, the API and the import
follow the same rules:

* a value fits its field (type, options, pattern – :meth:`CustomField.clean_value`);
* a unique field has no value twice among the items;
* a field marked "only with the right to see purchase prices" is seen and set
  only with that right (AUT-019);
* a required field of the fieldset has a value when one item is created or
  changed; creating several items at once may leave it empty (the item page
  then says that it is missing).

Lists load what they show for all their rows at once (:func:`load_values`),
not row by row (NFA-012).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Rights
from rentalars.customfields.models import (
    ENTRIES_CACHE_KEY,
    LIST_FIELDS_CACHE_KEY,
    CustomField,
    CustomFieldValue,
    Fieldset,
    FieldsetEntry,
    ModelFieldset,
)
from rentalars.material.models import MaterialItem, MaterialModel

#: Where a model keeps its fieldset entries and an item its values once looked up (``__dict__``).
_ENTRIES = "_custom_field_entries"
_VALUES = "_custom_field_values"


# --- Fieldsets of material models ---------------------------------------------------------------


def fieldset_of(material_model: MaterialModel | None) -> Fieldset | None:
    """The fieldset of a material model, or ``None`` (one query, none if loaded with the model)."""
    if material_model is None or material_model.pk is None:
        return None
    try:
        return material_model.custom_fieldset.fieldset  # type: ignore[attr-defined]
    except ObjectDoesNotExist:
        return None


def fieldset_id_of(material_model: MaterialModel | None) -> int | None:
    """The ID of the model's fieldset, or ``None`` – no query if the assignment was loaded with the model."""
    if material_model is None or material_model.pk is None:
        return None
    try:
        return material_model.custom_fieldset.fieldset_id  # type: ignore[attr-defined]
    except ObjectDoesNotExist:
        return None


def entries_of(material_model: MaterialModel | None) -> list[FieldsetEntry]:
    """The fields of the model's fieldset in their order, each with "required"; kept with the model."""
    if material_model is None or material_model.pk is None:
        return []
    known = material_model.__dict__.get(_ENTRIES)
    if known is None:
        # A list of items has one instance of the model per item: the entries are kept for the request, too.
        from rentalars.core.models import _request_cache

        cache = _request_cache.get()
        key = (ENTRIES_CACHE_KEY, material_model.pk)
        known = cache.get(key) if cache is not None else None
        if known is None:
            known = list(
                FieldsetEntry.objects.filter(fieldset__assignments__material_model=material_model)
                .select_related("field")
                .order_by("position", "field__name")
            )
            if cache is not None:
                cache[key] = known
        material_model.__dict__[_ENTRIES] = known
    return known


def visible_entries(material_model: MaterialModel | None, rights: Rights | None) -> list[FieldsetEntry]:
    """The fields of the model's fieldset this user sees; ``None`` rights: all (the command on the server)."""
    return [entry for entry in entries_of(material_model) if rights is None or entry.field.visible_to(rights)]


@transaction.atomic
def assign_fieldset(material_model: MaterialModel, fieldset: Fieldset | None) -> bool:
    """Give a material model a fieldset, another one, or none; return whether anything changed.

    The values of its items stay as they are: a field that leaves the fieldset
    keeps its values, and they show again when it comes back.
    """
    current = ModelFieldset.objects.filter(material_model=material_model).first()
    material_model.__dict__.pop(_ENTRIES, None)
    material_model._state.fields_cache.pop("custom_fieldset", None)  # the assignment loaded with the model
    if fieldset is None:
        if current is None:
            return False
        current.delete()
        return True
    if current is None:
        ModelFieldset.objects.create(material_model=material_model, fieldset=fieldset)
        return True
    if current.fieldset_id == fieldset.pk:
        return False
    current.fieldset = fieldset
    current.save()
    return True


# --- Values of items ----------------------------------------------------------------------------


def stored_values(item: MaterialItem) -> dict[int, str]:
    """All stored values of an item by the ID of their field, empty ones left out; kept with the item."""
    known = item.__dict__.get(_VALUES)
    if known is None:
        known = {}
        if item.pk is not None:
            for field_id, value, protected in CustomFieldValue.objects.filter(item=item).values_list(
                "field_id", "value", "protected_value"
            ):
                if value or protected:
                    known[field_id] = protected or value
        item.__dict__[_VALUES] = known
    return known


def load_values(items: Iterable[MaterialItem], *, with_entries: bool = True) -> None:
    """Load the values of many items – and the fieldsets of their models – with three queries (NFA-012)."""
    items = [item for item in items if item.pk is not None]
    if not items:
        return
    by_item: dict[int, dict[int, str]] = {item.pk: {} for item in items}
    for item_id, field_id, value, protected in CustomFieldValue.objects.filter(item_id__in=by_item).values_list(
        "item_id", "field_id", "value", "protected_value"
    ):
        if value or protected:
            by_item[item_id][field_id] = protected or value
    for item in items:
        item.__dict__[_VALUES] = by_item[item.pk]
    if with_entries:
        load_entries([item.material_model for item in items])


def load_entries(material_models: Iterable[MaterialModel]) -> None:
    """Load the fieldset entries of many material models with two queries (NFA-012)."""
    models = [model for model in material_models if model is not None and model.pk is not None]
    pending = {model.pk for model in models if _ENTRIES not in model.__dict__}
    if not pending:
        return
    fieldset_of_model = dict(
        ModelFieldset.objects.filter(material_model_id__in=pending).values_list("material_model_id", "fieldset_id")
    )
    entries: dict[int, list[FieldsetEntry]] = {}
    for entry in (
        FieldsetEntry.objects.filter(fieldset_id__in=set(fieldset_of_model.values()))
        .select_related("field")
        .order_by("position", "field__name")
    ):
        entries.setdefault(entry.fieldset_id, []).append(entry)
    for model in models:
        if model.pk in pending:
            model.__dict__[_ENTRIES] = list(entries.get(fieldset_of_model.get(model.pk), []))


def forget_values(item: MaterialItem) -> None:
    """Drop the values kept with an item, e.g. after they were changed elsewhere."""
    item.__dict__.pop(_VALUES, None)


@dataclass
class ValueRow:
    """One custom field of an item, ready to show."""

    field: CustomField
    stored: str
    required: bool = False

    @property
    def display(self) -> str:
        """The value for people, e.g. ``12,5 m``."""
        return self.field.display_value(self.stored)

    @property
    def missing(self) -> bool:
        """A required value nobody entered yet."""
        return self.required and not self.stored


def value_rows(item: MaterialItem, rights: Rights | None) -> list[ValueRow]:
    """The fields of the item's fieldset the user sees, in their order, with their values."""
    values = stored_values(item)
    return [
        ValueRow(entry.field, values.get(entry.field_id, ""), entry.is_required)
        for entry in visible_entries(item.material_model, rights)
    ]


def other_value_rows(item: MaterialItem, rights: Rights | None) -> list[ValueRow]:
    """Stored values of fields outside the fieldset of the item's model – kept, shown apart on the item page."""
    values = stored_values(item)
    inside = {entry.field_id for entry in entries_of(item.material_model)}
    others = [field_id for field_id in values if field_id not in inside]
    if not others:
        return []
    fields = CustomField.objects.filter(pk__in=others).order_by("name")
    return [ValueRow(field, values[field.pk]) for field in fields if rights is None or field.visible_to(rights)]


def missing_required(item: MaterialItem) -> list[CustomField]:
    """The required fields of the item's fieldset without a value."""
    values = stored_values(item)
    return [
        entry.field for entry in entries_of(item.material_model) if entry.is_required and not values.get(entry.field_id)
    ]


def check_unique(field: CustomField, canonical: str, *, item: Any = None, rights: Rights | None = None) -> None:
    """For a unique field: refuse a value another item has (case ignored).

    The other item is named only to who may see the value (AUT-019).

    Raises:
        ValidationError: Another item has the value.
    """
    if not field.is_unique or not canonical:
        return
    holder = field.holder_of(canonical, exclude_item=item)
    if holder is None:
        return
    if rights is not None and not field.visible_to(rights):
        raise ValidationError(_("The value of the field %(field)s is already taken.") % {"field": field.name})
    raise ValidationError(
        _("The item %(id)s already has the value “%(value)s” in the unique field %(field)s.")
        % {"id": holder.item.display_id, "value": canonical, "field": field.name}
    )


def store_values(item: MaterialItem, values: dict[CustomField, str]) -> list[tuple[CustomField, str, str]]:
    """Store checked canonical values of an item; each changed one is saved on its own (change log).

    Returns:
        ``(field, old text, new text)`` for every value that changed.
    """
    if not values:
        return []
    existing = {value.field_id: value for value in CustomFieldValue.objects.filter(item=item, field__in=list(values))}
    changes: list[tuple[CustomField, str, str]] = []
    for field, text in values.items():
        row = existing.get(field.pk)
        if row is None:
            if not text:
                continue
            row = CustomFieldValue(item=item, field=field)
            old = ""
        else:
            row.field = field
            old = row.stored
        if old == text and row.pk is not None and row.column_matches():
            continue
        row.put(text)
        row.save()
        if old != text:
            changes.append((field, old, text))
    forget_values(item)
    return changes


# --- Checking values from the API and the import ------------------------------------------------


def check_values(
    material_model: MaterialModel,
    item: MaterialItem | None,
    given: dict[str, Any],
    rights: Rights | None,
    *,
    creating: bool,
    several: bool = False,
) -> dict[CustomField, str]:
    """Check values given by field name – from the API – against the fieldset of the model.

    Args:
        material_model: The model of the item (after the change, if the change moves it).
        item: The item, ``None`` while it is created.
        given: ``{field name: value}``; ``None`` or ``""`` empties a value.
        rights: The rights of the caller; ``None`` – the command on the server – may do everything.
        creating: The item is new: every required field needs a value (unless ``several``).
        several: Several items are created at once: required fields may stay empty, unique ones must.

    Returns:
        ``{field: canonical text}`` for the given fields.

    Raises:
        ValidationError: Under ``custom_fields``, one message per problem.
    """
    entries = {entry.field.name.casefold(): entry for entry in entries_of(material_model)}
    errors: list[str] = []
    cleaned: dict[CustomField, str] = {}
    reported: set[int] = set()
    if not isinstance(given, dict):
        raise ValidationError({"custom_fields": _("Expected an object of field names and values.")})
    for name, raw in given.items():
        entry = entries.get(str(name).strip().casefold())
        if entry is None:
            errors.append(
                _("%(field)s: the material model “%(model)s” has no such custom field.")
                % {"field": name, "model": material_model.name}
            )
            continue
        field = entry.field
        if rights is not None and not field.visible_to(rights):
            errors.append(_("%(field)s: you do not have the right to set this field.") % {"field": field.name})
            continue
        try:
            text = field.clean_value(raw)
            if several and field.is_unique and text:
                raise ValidationError(
                    _("A unique field cannot get the same value for several items. Leave it empty here.")
                )
            check_unique(field, text, item=item, rights=rights)
        except ValidationError as error:
            errors.append(f"{field.name}: {' '.join(error.messages)}")
            continue
        if entry.is_required and not text and not several:
            errors.append(_("%(field)s: a value is required.") % {"field": field.name})
            reported.add(field.pk)
            continue
        cleaned[field] = text
    if creating and not several:
        handled = {field.pk for field in cleaned} | reported
        for entry in entries.values():
            visible = rights is None or entry.field.visible_to(rights)
            if entry.is_required and entry.field_id not in handled and visible:
                errors.append(_("%(field)s: a value is required.") % {"field": entry.field.name})
    if errors:
        raise ValidationError({"custom_fields": errors})
    return cleaned


def api_values(item: MaterialItem, rights: Rights | None) -> dict[str, Any]:
    """The values of the item's fieldset for the API: ``{field name: value}`` – typed, ``None`` when empty.

    Numbers as text (``"12.5"``, as the API writes amounts), dates as
    ``2027-03-01``, yes/no as ``true``/``false``. Fields the caller may not
    see are left out (AUT-019).
    """
    result: dict[str, Any] = {}
    for row in value_rows(item, rights):
        value = row.field.typed_value(row.stored)
        if value is not None and not isinstance(value, bool | str):
            value = row.stored  # Decimal and date as their canonical text
        result[row.field.name] = value
    return result


# --- Definitions --------------------------------------------------------------------------------


def value_count(field: CustomField) -> int:
    """How many items have a value of this field."""
    return field.values.exclude(value="", protected_value="").count()


@transaction.atomic
def delete_field(field: CustomField, *, with_values: bool) -> int:
    """Delete a custom field; it leaves its fieldsets. Values of items are deleted only if asked for.

    Each value is deleted on its own, so that the history of its item tells.

    Returns:
        The number of values deleted.

    Raises:
        ValidationError: Items have values and ``with_values`` is not set.
    """
    count = value_count(field)
    if count and not with_values:
        raise ValidationError(
            ngettext(
                "%(count)s item has a value in the field “%(field)s”. Deleting the field deletes this value, too – "
                "confirm that, or keep the field.",
                "%(count)s items have a value in the field “%(field)s”. Deleting the field deletes these values, "
                "too – confirm that, or keep the field.",
                count,
            )
            % {"count": count, "field": field.name}
        )
    for value in field.values.select_related("item", "field"):
        value.delete()
    field.delete()
    return count


def fieldset_in_use(fieldset: Fieldset) -> int:
    """How many material models have this fieldset."""
    return fieldset.assignments.count()


def delete_fieldset(fieldset: Fieldset) -> None:
    """Delete a fieldset no material model has; the fields and the values of items stay.

    Raises:
        ValidationError: Material models have it.
    """
    count = fieldset_in_use(fieldset)
    if count:
        raise ValidationError(
            ngettext(
                "%(count)s material model has the fieldset “%(name)s”. Give it another fieldset or none first.",
                "%(count)s material models have the fieldset “%(name)s”. Give them another fieldset or none first.",
                count,
            )
            % {"count": count, "name": fieldset.name}
        )
    fieldset.delete()


def list_fields(rights: Rights | None = None) -> list[CustomField]:
    """The fields marked "in lists" – kept for the rest of the request – that a user with these rights sees."""
    from rentalars.core.models import _request_cache

    cache = _request_cache.get()
    fields = cache.get(LIST_FIELDS_CACHE_KEY) if cache is not None else None
    if fields is None:
        fields = list(CustomField.objects.filter(show_in_lists=True).order_by("name"))
        if cache is not None:
            cache[LIST_FIELDS_CACHE_KEY] = fields
    return [field for field in fields if rights is None or field.visible_to(rights)]
