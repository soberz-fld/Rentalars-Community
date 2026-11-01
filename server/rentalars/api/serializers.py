# SPDX-License-Identifier: GPL-3.0-or-later
"""Building blocks shared by the serializers of all modules."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext as _
from rest_framework import serializers

from rentalars.accounts.rights import NO_RIGHTS, Rights, request_rights


class CleanModelSerializer(serializers.ModelSerializer):
    """A model serializer that runs the model's own validation.

    The REST framework validates field types but does not call a model's
    ``clean()``. The business rules of Rentalars live exactly there (and in
    the services), because the browser forms and the administration use them
    too. Calling ``full_clean()`` here makes the API obey the same rules
    (API-002).
    """

    def create(self, validated_data: dict[str, Any]) -> Any:
        """Create the object after validating it with the model's rules."""
        many_to_many = {
            name: validated_data.pop(name)
            for name in list(validated_data)
            if isinstance(self.Meta.model._meta.get_field(name), models.ManyToManyField)
        }
        instance = self.Meta.model(**validated_data)
        instance.full_clean()
        instance.save()
        for name, values in many_to_many.items():
            getattr(instance, name).set(values)
        return instance

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """Change the object after validating it with the model's rules."""
        many_to_many = {}
        for name, value in validated_data.items():
            if isinstance(instance._meta.get_field(name), models.ManyToManyField):
                many_to_many[name] = value
            else:
                setattr(instance, name, value)
        instance.full_clean()
        instance.save()
        for name, values in many_to_many.items():
            getattr(instance, name).set(values)
        return instance


class RightsMixin:
    """Gives a serializer access to the rights of the caller."""

    context: dict[str, Any]

    @property
    def rights(self) -> Rights:
        """The rights of the request, or none when used outside a request."""
        request = self.context.get("request")
        return request_rights(request) if request is not None else NO_RIGHTS


class RestrictedFieldsMixin(RightsMixin):
    """Hides fields from callers who lack a special right (AUT-019).

    A serializer lists the protected fields::

        restricted_fields = {"price": SpecialRight.PRICES}

    Without the right, the field is neither delivered nor accepted: the
    answer does not contain it at all, and sending it is rejected instead of
    being silently ignored. While the API description is generated (no
    request at hand) all fields are listed.
    """

    restricted_fields: ClassVar[dict[str, str]] = {}

    def _hidden_fields(self) -> set[str]:
        """Names of the protected fields this caller may not see."""
        if self.context.get("request") is None:
            return set()
        return {name for name, right in self.restricted_fields.items() if not self.rights.has(right)}

    def get_fields(self) -> dict[str, Any]:
        """Remove the fields the caller may not see."""
        fields = super().get_fields()  # type: ignore[misc]
        for name in self._hidden_fields():
            fields.pop(name, None)
        return fields

    def to_internal_value(self, data: Any) -> Any:
        """Reject input for fields the caller may not set."""
        if isinstance(data, dict):
            forbidden = sorted(self._hidden_fields() & set(data.keys()))
            if forbidden:
                raise serializers.ValidationError(
                    {name: [_("You do not have the right to set this field.")] for name in forbidden}
                )
        return super().to_internal_value(data)  # type: ignore[misc]


class ExpandableFieldsMixin:
    """Lets a client embed related objects with ``?expand=`` (API-007).

    By default a relation is delivered as its ID. A serializer can offer to
    deliver the related object itself::

        expandable_fields = {"customer": CustomerSerializer}

    ``GET /api/v1/projects/?expand=customer`` then returns the customer as a
    nested object. Several names are separated by commas. Embedded objects
    are not expanded further.
    """

    expandable_fields: ClassVar[dict[str, Any]] = {}
    context: dict[str, Any]

    def _requested_expansions(self) -> list[str]:
        """The valid names from the ``expand`` query parameter."""
        request = self.context.get("request")
        if request is None or self.context.get("is_embedded"):
            return []
        requested = getattr(request, "query_params", {}).get("expand", "")
        return [name.strip() for name in requested.split(",") if name.strip() in self.expandable_fields]

    def to_representation(self, instance: Any) -> Any:
        """Replace the IDs of the requested relations by the related objects."""
        data = super().to_representation(instance)  # type: ignore[misc]
        for name in self._requested_expansions():
            related = getattr(instance, name, None)
            if related is None:
                data[name] = None
                continue
            serializer_class = self.expandable_fields[name]
            context = {**self.context, "is_embedded": True}
            many = hasattr(related, "all")
            data[name] = serializer_class(related.all() if many else related, many=many, context=context).data
        return data
