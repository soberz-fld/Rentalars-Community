# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the custom fields (MAT-071, MAT-072, MAT-073; API-002).

* ``/custom-fields`` – the definitions (list, create, read, change, delete);
  ``DELETE …?delete_values=true`` deletes a field whose items have values,
  with the values – without it such a field is refused.
* ``/custom-fieldsets`` – the fieldsets with their fields
  (``fields: [{"field": 3, "position": 1, "required": true}]``); a fieldset a
  material model has cannot be deleted.
* ``fieldset`` at ``/material-models`` – the ID of the model's fieldset or
  ``null`` (:class:`FieldsetAssignmentField`).
* ``custom_fields`` at ``/material-items`` and in ``POST
  /material-models/{id}/items`` – ``{"Firmware": "1.3", "Prüfplakette bis":
  "2027-06-30"}`` (:class:`CustomValuesField`).

Every logged-in user reads the definitions, as the categories (master data);
changing them needs write access to the module "Settings", deleting the
level "delete". The values follow the item: reading needs material read,
setting material write; fields visible only with the right to see purchase
prices need that right, in both directions (AUT-019).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers

from rentalars.accounts.rights import NO_RIGHTS, Module, request_rights
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleViewSet
from rentalars.customfields import services
from rentalars.customfields.models import CustomField, Fieldset, FieldsetEntry


class CustomFieldSerializer(CleanModelSerializer):
    """A custom field (MAT-071): ``choices`` are the options of a choice list, ``pattern`` a regular expression."""

    value_count = serializers.SerializerMethodField(help_text="How many items have a value of this field.")

    class Meta:
        model = CustomField
        fields = [
            "id",
            "name",
            "field_type",
            "unit",
            "choices",
            "pattern",
            "help_text",
            "show_in_lists",
            "is_unique",
            "is_sensitive",
            "value_count",
        ]

    def get_value_count(self, field: CustomField) -> int:
        """How many items have a value of this field."""
        return services.value_count(field)


class FieldsetEntrySerializer(serializers.Serializer):
    """One field of a fieldset: the field's ID, its position, whether it is required there."""

    field = serializers.PrimaryKeyRelatedField(queryset=CustomField.objects.all())
    name = serializers.CharField(source="field.name", read_only=True)
    position = serializers.IntegerField(min_value=1, max_value=999, required=False, default=1)
    required = serializers.BooleanField(source="is_required", required=False, default=False)


class FieldsetSerializer(CleanModelSerializer):
    """A fieldset with its fields in their order, and the material models that have it (read only).

    The list of fields is called ``fields``; a serializer uses that name for
    itself, so the field is added in :meth:`get_fields`.
    """

    material_models = serializers.SerializerMethodField(help_text="IDs of the material models with this fieldset.")

    class Meta:
        model = Fieldset
        fields = ["id", "name", "description", "material_models"]

    def get_fields(self) -> dict[str, Any]:
        """The fields of the model, and ``fields``: the custom fields of the fieldset."""
        fields = super().get_fields()
        fields["fields"] = FieldsetEntrySerializer(source="entries_in_order", many=True, required=False)
        return fields

    def get_material_models(self, fieldset: Fieldset) -> list[int]:
        """IDs of the material models with this fieldset."""
        return list(fieldset.assignments.order_by("material_model_id").values_list("material_model_id", flat=True))

    def validate_fields(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Each field once."""
        ids = [entry["field"].pk for entry in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(_("A field can be part of a fieldset only once."))
        return value

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> Fieldset:
        """Create the fieldset with its fields."""
        entries = validated_data.pop("entries_in_order", [])
        fieldset = super().create(validated_data)
        self._set_entries(fieldset, entries)
        return fieldset

    @transaction.atomic
    def update(self, instance: Fieldset, validated_data: dict[str, Any]) -> Fieldset:
        """Change the fieldset; ``fields``, if sent, replace its fields."""
        entries = validated_data.pop("entries_in_order", None)
        fieldset = super().update(instance, validated_data)
        if entries is not None:
            self._set_entries(fieldset, entries)
        return fieldset

    @staticmethod
    def _set_entries(fieldset: Fieldset, entries: list[dict[str, Any]]) -> None:
        """Make the fields of the fieldset these – each saved on its own, so that the change log tells."""
        existing = {entry.field_id: entry for entry in fieldset.entries.all()}
        wanted = {entry["field"].pk: entry for entry in entries}
        for field_id, entry in existing.items():
            if field_id not in wanted:
                entry.delete()
        for field_id, values in wanted.items():
            entry = existing.get(field_id) or FieldsetEntry(fieldset=fieldset, field=values["field"])
            position, required = values.get("position", 1), values.get("is_required", False)
            if entry.pk is None or (entry.position, entry.is_required) != (position, required):
                entry.position, entry.is_required = position, required
                entry.save()


class CustomFieldViewSet(ModuleViewSet):
    """``/custom-fields`` – the definitions of the custom fields of items (MAT-071)."""

    module = Module.ADMINISTRATION
    read_for_all = True
    schema_tag = "masterdata"
    queryset = CustomField.objects.order_by("name")
    serializer_class = CustomFieldSerializer
    filterset_fields = ["field_type", "show_in_lists", "is_unique", "is_sensitive"]
    search_fields = ["name"]
    ordering_fields = ["name"]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "delete_values", OpenApiTypes.BOOL, description="Also delete the values items have of this field."
            )
        ]
    )
    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        """Delete a field; a field items have values of only with ``delete_values=true``."""
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance: CustomField) -> None:
        """Values are deleted only if asked for (``delete_values``)."""
        wanted = str(self.request.query_params.get("delete_values", "")).lower() in {"1", "true", "yes"}
        services.delete_field(instance, with_values=wanted)


class FieldsetViewSet(ModuleViewSet):
    """``/custom-fieldsets`` – the fieldsets; a material model gets one (MAT-072)."""

    module = Module.ADMINISTRATION
    read_for_all = True
    schema_tag = "masterdata"
    queryset = Fieldset.objects.order_by("name")
    serializer_class = FieldsetSerializer
    search_fields = ["name"]
    ordering_fields = ["name"]

    def perform_destroy(self, instance: Fieldset) -> None:
        """A fieldset a material model has stays (as master data in use, ADM-006)."""
        services.delete_fieldset(instance)


# --- Fields of the material API -------------------------------------------------------------------------


def _rights_of(field: serializers.Field) -> Any:
    request = field.context.get("request")
    return request_rights(request) if request is not None else NO_RIGHTS


@extend_schema_field({"type": "integer", "nullable": True, "description": "The ID of the fieldset (custom fields)."})
class FieldsetAssignmentField(serializers.Field):
    """``fieldset`` of a material model: the ID of its fieldset or ``null``; written after the model is saved."""

    #: The key the value takes in the validated data; the serializer stores it with :func:`save_fieldset`.
    KEY = "_custom_fieldset"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("source", "*")
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def validate_empty_values(self, data: Any) -> tuple[bool, Any]:
        """``null`` means "no fieldset": it reaches :meth:`to_internal_value` instead of being dropped."""
        if data is None:
            return True, {self.KEY: None}
        return super().validate_empty_values(data)

    def to_representation(self, material_model: Any) -> int | None:
        """The ID of the model's fieldset."""
        return services.fieldset_id_of(material_model)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Turn the ID into the fieldset; ``null`` or ``""`` remove it."""
        if data in (None, ""):
            return {self.KEY: None}
        try:
            return {self.KEY: Fieldset.objects.get(pk=int(data))}
        except (TypeError, ValueError, Fieldset.DoesNotExist) as error:
            raise serializers.ValidationError(_("There is no fieldset with this ID.")) from error


#: Marks that no ``fieldset`` was sent: the model keeps its fieldset.
NOT_SENT = object()


def take_fieldset(validated_data: dict[str, Any]) -> Any:
    """Take the fieldset sent with ``fieldset`` out of the validated data (``NOT_SENT`` if none was sent)."""
    return validated_data.pop(FieldsetAssignmentField.KEY, NOT_SENT)


def store_fieldset(material_model: Any, taken: Any) -> None:
    """Give the saved model the fieldset taken by :func:`take_fieldset` – if one was sent."""
    if taken is not NOT_SENT:
        services.assign_fieldset(material_model, taken)


@extend_schema_field(
    {
        "type": "object",
        "additionalProperties": True,
        "description": "The values of the custom fields of the item's fieldset by field name; null empties one.",
    }
)
class CustomValuesField(serializers.Field):
    """``custom_fields`` of an item: ``{field name: value}`` of the fields of its model's fieldset.

    Read: every field of the fieldset the caller may see, ``null`` when empty;
    numbers and dates as text (``"12.5"``, ``"2027-06-30"``), yes/no as
    ``true``/``false``. Write: the fields sent are checked against the
    fieldset (unknown names, types, options, patterns, unique values,
    required values, the right for sensitive fields) and stored after the
    item; fields not sent stay as they are.
    """

    KEY = "_custom_fields"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("source", "*")
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def to_representation(self, item: Any) -> dict[str, Any]:
        """The values the caller may see."""
        return services.api_values(item, _rights_of(self))

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Keep the values for the serializer, which checks them against the item's model."""
        if not isinstance(data, dict):
            raise serializers.ValidationError(_("Expected an object of field names and values."))
        return {self.KEY: data}


def checked_values(
    serializer: serializers.Serializer,
    validated_data: dict[str, Any],
    material_model: Any,
    item: Any,
    *,
    creating: bool,
    several: bool = False,
) -> dict[CustomField, str] | None:
    """Take the custom values out of the validated data and check them; ``None`` if none were sent.

    Raises:
        ValidationError: Under ``custom_fields``.
    """
    given = validated_data.pop(CustomValuesField.KEY, None)
    rights = _rights_of(serializer)
    if given is None:
        if creating and not several:
            # A new item needs its required values even if no ``custom_fields`` were sent.
            return services.check_values(material_model, None, {}, rights, creating=True)
        return None
    return services.check_values(material_model, item, given, rights, creating=creating, several=several)


def store_checked(items: list[Any], values: dict[CustomField, str] | None) -> None:
    """Store checked values for the items (after they were saved)."""
    if not values:
        return
    for item in items:
        services.store_values(item, values)


def load_page(page: list[Any] | None) -> None:
    """Load the custom values of a page of items, and the fieldsets of their models, at once (NFA-012)."""
    if page:
        services.load_values(page)


__all__ = [
    "CustomFieldSerializer",
    "CustomFieldViewSet",
    "CustomValuesField",
    "FieldsetAssignmentField",
    "FieldsetSerializer",
    "FieldsetViewSet",
    "checked_values",
    "store_checked",
    "store_fieldset",
    "take_fieldset",
]
