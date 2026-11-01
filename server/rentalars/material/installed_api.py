# SPDX-License-Identifier: GPL-3.0-or-later
"""API for bulk material built into an item (built-in quantity material; MAT-040).

The same functions as the item page (API-002), in ``material.installations``:

* ``GET  /material-items/{id}/built-in`` – for a case, rack or vehicle: what is built into it; for a bulk row:
  where it is built in and how much of it is free
* ``POST /material-items/{id}/built-in`` – build a quantity of a bulk row into the item: ``{"material": 17,
  "quantity": 10, "note": "spare"}``
* ``POST /material-items/{id}/built-in/{material}/remove`` – take it out again: ``{"quantity": 4}``, or no
  quantity for all of it

What is built in leaves the free stock of the bulk row and returns to it when it is taken out.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.inputs import int_or_400, str_or_400
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.material import installations
from rentalars.material.installed_models import InstalledQuantity
from rentalars.material.models import MaterialItem


def whole_number(value: Any) -> int:
    """A quantity from a request as a whole number: 4, "4" and 4.0 are, 3.9 and "3.9" are refused – never cut to 3 (R1-13).

    Raises:
        ValidationError: The value is no whole number.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value.strip())
    raise ValidationError({"quantity": _("Enter a whole number.")})


def _item(pk: Any) -> MaterialItem:
    return get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)


def installed_document(installed: InstalledQuantity) -> dict[str, Any]:
    """One built-in quantity: the container, the bulk row, how many, who and when."""
    material, container = installed.material, installed.container
    product = material.material_model.default_product
    return {
        "id": installed.pk,
        "container": container.pk,
        "container_id": container.display_id,
        "container_name": container.material_model.display_short_name,
        "material": material.pk,
        "material_id": material.display_id,
        "material_name": material.material_model.display_short_name,
        "quantity": installed.quantity,
        "unit": product.unit.abbreviation if product is not None else "",
        "note": installed.note,
        "installed_by": str(installed.installed_by) if installed.installed_by_id else None,
        "installed_at": installed.installed_at,
    }


def built_in_document(item: MaterialItem) -> dict[str, Any]:
    """What is built into an item, or where a bulk row is built in – with the free stock of a bulk row."""
    if item.material_model.is_bulk:
        places = installations.installed_places(item)
        return {
            "item": item.pk,
            "is_bulk": True,
            "free": item.quantity,
            "built_in_total": sum(place.quantity for place in places),
            "built_into": [installed_document(place) for place in places],
            "built_in": [],
        }
    return {
        "item": item.pk,
        "is_bulk": False,
        "free": None,
        "built_in_total": None,
        "built_into": [],
        "built_in": [installed_document(row) for row in installations.installed_in(item)],
    }


class ItemBuiltInView(ModuleAPIView):
    """``/material-items/{id}/built-in``: bulk material built into an item (MAT-040)."""

    module = Module.MATERIAL

    @extend_schema(responses={200: inline_serializer("ItemBuiltIn", {"item": serializers.IntegerField()})})
    def get(self, request: Request, pk: int) -> Response:
        """List what is built into the item, or where the bulk row is built in."""
        return Response(built_in_document(_item(pk)))

    @extend_schema(
        request=inline_serializer(
            "ItemBuiltInAdd",
            {
                "material": serializers.IntegerField(help_text="Database ID of the bulk row."),
                "quantity": serializers.IntegerField(),
                "note": serializers.CharField(required=False),
            },
        ),
        responses={201: inline_serializer("ItemBuiltInAdded", {"item": serializers.IntegerField()})},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Build a quantity of a bulk row into the item; it leaves the free stock."""
        container = _item(pk)
        body = body_of(request)
        # (hostile input; R4-2b) A wrong type for an ID, a quantity or a note is a 400, never a 500.
        material = get_object_or_404(
            MaterialItem.objects.select_related("material_model"),
            pk=int_or_400(body.get("material"), "material", default=0),
        )
        quantity = whole_number(body.get("quantity"))
        installations.install_quantity(
            container, material, quantity, user=request.user, note=str_or_400(body.get("note"), "note")
        )
        return Response(built_in_document(container), status=status.HTTP_201_CREATED)


class ItemBuiltInRemoveView(ModuleAPIView):
    """``/material-items/{id}/built-in/{material}/remove``: take built-in material out again (MAT-040)."""

    module = Module.MATERIAL

    @extend_schema(
        request=inline_serializer("ItemBuiltInRemove", {"quantity": serializers.IntegerField(required=False)}),
        responses={200: inline_serializer("ItemBuiltInRemoved", {"item": serializers.IntegerField()})},
    )
    def post(self, request: Request, pk: int, material_pk: int) -> Response:
        """Take a quantity – or all of it – out; it is free stock again."""
        container = _item(pk)
        material = _item(material_pk)
        raw = body_of(request).get("quantity")
        quantity = None if raw in (None, "") else whole_number(raw)
        installations.remove_quantity(container, material, quantity, user=request.user)
        return Response(built_in_document(container))
