# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the fleet: vehicles and trailers, their data, bookings and availability (LOG-015).

The same functions as the pages (``material.fleet``, API-002). The addresses:

* ``GET /vehicles`` – every vehicle and trailer, the items of vehicle
  products; ``?type=car|trailer``, ``?status=`` (default: all but retired,
  sold and lost)
* ``GET /vehicles/{item}`` – one of them; ``PATCH`` changes its vehicle data,
  ``PUT`` replaces them (fields left out are emptied); the row is made with
  the first change (LOG-002, LOG-003)
* ``GET /vehicles/{item}/availability?start=…&end=…`` – its bookings in that
  period with ``overlaps``, and whether it is ``free`` (LOG-004)
* ``POST /material-models/{id}/to-fleet`` – a model planned as material so far
  becomes vehicles of the fleet with a new vehicle product (LOG-016)

Reading needs read access to the material, changing write access; taking a
model into the fleet makes a product and needs write access to the products
as well. A booking of a project the caller may not open is delivered without
project, number and name (AUT-016).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.pagination import StandardPagination
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.material import fleet
from rentalars.material.inspections import InspectionPlan
from rentalars.material.models import ARCHIVED_STATUSES, ItemStatus, MaterialItem, MaterialModel
from rentalars.products.models import TrailerBilling, VehicleType

_RELATED = ("material_model__category", "material_model__default_product", "product_override", "vehicle")


def _product_document(product: Any) -> dict[str, Any] | None:
    if product is None:
        return None
    return {"id": product.pk, "article_number": product.article_number, "name": product.name}


def vehicle_document(item: MaterialItem, due: Any = None) -> dict[str, Any]:
    """One vehicle or trailer as JSON: the item, its product, its vehicle data and its next inspection."""
    vehicle = fleet.vehicle_of(item)
    product = item.product
    return {
        "id": item.pk,
        "display_id": item.display_id,
        "licence_plate": vehicle.licence_plate if vehicle is not None else "",
        "type": product.vehicle_type if product is not None else "",
        "product": _product_document(product),
        "material_model": {"id": item.material_model_id, "name": item.material_model.name},
        "status": item.status,
        "seats_min": vehicle.seats_min if vehicle is not None else None,
        "seats_max": vehicle.seats_max if vehicle is not None else None,
        "seats_missing": fleet.seats_missing(item, vehicle),
        "licence_class": vehicle.licence_class if vehicle is not None else "",
        "towing_capacity_kg": vehicle.towing_capacity_kg if vehicle is not None else None,
        "gross_weight_kg": vehicle.gross_weight_kg if vehicle is not None else None,
        "next_inspection": (
            {
                "inspection_type": due.inspection_type.pk,
                "name": due.inspection_type.name,
                "due_date": due.due_date,
                "state": due.state,
            }
            if due is not None
            else None
        ),
    }


def _vehicle(pk: Any) -> MaterialItem:
    """The item of a vehicle product with this ID; any other item is "not found"."""
    return get_object_or_404(fleet.vehicle_items().select_related(*_RELATED), pk=pk)


def _due(item: MaterialItem) -> Any:
    dues = InspectionPlan().dues_for([item]).get(item.pk, [])
    return dues[0] if dues else None


class VehicleDocumentSerializer(serializers.Serializer):
    """How a vehicle or trailer is delivered – for the API description; :func:`vehicle_document` writes it."""

    id = serializers.IntegerField(help_text="The ID of the item.")
    display_id = serializers.CharField()
    licence_plate = serializers.CharField()
    type = serializers.CharField(help_text="car or trailer, from the vehicle product")
    product = inline_serializer(
        "VehicleProduct",
        {"id": serializers.IntegerField(), "article_number": serializers.CharField(), "name": serializers.CharField()},
    )
    material_model = inline_serializer(
        "VehicleMaterialModel", {"id": serializers.IntegerField(), "name": serializers.CharField()}
    )
    status = serializers.ChoiceField(choices=ItemStatus.choices)
    seats_min = serializers.IntegerField(allow_null=True)
    seats_max = serializers.IntegerField(allow_null=True)
    seats_missing = serializers.BooleanField(help_text="A motor vehicle without its seats (LOG-003).")
    licence_class = serializers.CharField()
    towing_capacity_kg = serializers.IntegerField(allow_null=True)
    gross_weight_kg = serializers.IntegerField(allow_null=True)
    next_inspection = inline_serializer(
        "VehicleNextInspection",
        {
            "inspection_type": serializers.IntegerField(),
            "name": serializers.CharField(),
            "due_date": serializers.DateField(allow_null=True),
            "state": serializers.CharField(),
        },
        allow_null=True,
    )


class VehicleDataSerializer(serializers.Serializer):
    """The vehicle data a caller may change (LOG-002, LOG-003, LOG-012, LOG-013)."""

    licence_plate = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)
    seats_min = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=999)
    seats_max = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=999)
    licence_class = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=12)
    towing_capacity_kg = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, help_text="Motor vehicles only; 0: may not tow."
    )
    gross_weight_kg = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class VehicleListView(ModuleAPIView):
    """``GET /vehicles`` – the vehicles and trailers of the fleet (LOG-002, LOG-015)."""

    module = Module.MATERIAL

    @extend_schema(
        parameters=[
            OpenApiParameter("type", str, enum=VehicleType.values, description="Only motor vehicles or trailers."),
            OpenApiParameter("status", str, enum=ItemStatus.values, description="Default: all but archived."),
        ],
        responses=VehicleDocumentSerializer(many=True),
        operation_id="vehicles_list",
    )
    def get(self, request: Request) -> Response:
        """Page by page, by ID; with licence plate, type, seats, status and next inspection due."""
        items = fleet.vehicle_items().select_related(*_RELATED).order_by("inventory_number")
        vehicle_type = request.query_params.get("type", "")
        if vehicle_type:
            if vehicle_type not in VehicleType.values:
                raise ValidationError({"type": _("Choose “car” or “trailer”.")})
            items = fleet.of_type(items, vehicle_type)
        state = request.query_params.get("status", "")
        if state:
            if state not in ItemStatus.values:
                raise ValidationError({"status": _("Unknown status.")})
            items = items.filter(status=state)
        else:
            items = items.exclude(status__in=ARCHIVED_STATUSES)
        paginator = StandardPagination()
        page = list(paginator.paginate_queryset(items, request, view=self) or [])
        dues = InspectionPlan().dues_for(page)
        return paginator.get_paginated_response(
            [vehicle_document(item, (dues.get(item.pk) or [None])[0]) for item in page]
        )


class VehicleDetailView(ModuleAPIView):
    """``/vehicles/{item}`` – one vehicle or trailer; its vehicle data can be changed (LOG-002, LOG-003)."""

    module = Module.MATERIAL

    @extend_schema(responses=VehicleDocumentSerializer)
    def get(self, request: Request, pk: int) -> Response:
        """The vehicle with its data and next inspection due."""
        item = _vehicle(pk)
        return Response(vehicle_document(item, _due(item)))

    @extend_schema(request=VehicleDataSerializer, responses=VehicleDocumentSerializer)
    def patch(self, request: Request, pk: int) -> Response:
        """Change some of the vehicle data; what is left out stays."""
        return self._save(request, pk, replace=False)

    @extend_schema(request=VehicleDataSerializer, responses=VehicleDocumentSerializer)
    def put(self, request: Request, pk: int) -> Response:
        """Replace the vehicle data; what is left out is emptied."""
        return self._save(request, pk, replace=True)

    def _save(self, request: Request, pk: int, *, replace: bool) -> Response:
        item = _vehicle(pk)
        serializer = VehicleDataSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        fleet.save_vehicle(item, replace=replace, **serializer.validated_data)
        item = _vehicle(pk)
        return Response(vehicle_document(item, _due(item)))


def _moment(request: Request, name: str) -> datetime.datetime:
    """A moment of the query string, ISO 8601 with time zone."""
    text = request.query_params.get(name, "")
    moment = parse_datetime(text) if text else None
    if moment is None:
        raise ValidationError({name: _("Enter date and time in ISO format, e.g. 2027-03-10T08:00:00+01:00.")})
    if moment.tzinfo is None:
        raise ValidationError({name: _("The time needs a time zone, e.g. +01:00 or Z.")})
    return moment


class VehicleAvailabilityView(ModuleAPIView):
    """``GET /vehicles/{item}/availability?start=…&end=…`` – bookings in a period and whether it is free (LOG-004)."""

    module = Module.MATERIAL

    @extend_schema(
        parameters=[
            OpenApiParameter("start", str, required=True, description="Start, ISO 8601 with time zone"),
            OpenApiParameter("end", str, required=True, description="End, ISO 8601 with time zone"),
        ],
        responses={200: inline_serializer("VehicleAvailability", {"free": serializers.BooleanField()})},
    )
    def get(self, request: Request, pk: int) -> Response:
        """Free: no booking of a project that is not cancelled, no blocked period, and fit for use.

        Every booking says whether it ``overlaps`` another booking of the
        vehicle. Project, number and name only for projects the caller may
        open.
        """
        item = _vehicle(pk)
        start, end = _moment(request, "start"), _moment(request, "end")
        if end <= start:
            raise ValidationError({"end": _("The end must be after the start.")})
        visible = fleet.visible_project_ids(self.rights, request.user)
        bookings = fleet.bookings_for([item.pk], start, end, visible).get(item.pk, [])
        blocked = item.blocks.filter(start__lt=end, end__gt=start).exists()
        return Response(
            {
                "vehicle": item.pk,
                "display_id": item.display_id,
                "start": start,
                "end": end,
                "operational": item.is_operational,
                "blocked": blocked,
                "free": item.is_operational and not blocked and not bookings,
                "bookings": [
                    {
                        "project": booking.project.pk if booking.visible else None,
                        "project_number": booking.project.number if booking.visible else None,
                        "project_name": booking.project.name if booking.visible else None,
                        "start": booking.start,
                        "end": booking.end,
                        "overlaps": booking.overlaps,
                    }
                    for booking in bookings
                ],
            }
        )


class ModelToFleetSerializer(serializers.Serializer):
    """The new vehicle product of a model taken into the fleet (LOG-016)."""

    vehicle_type = serializers.ChoiceField(choices=VehicleType.choices)
    price_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, required=False, allow_null=True, help_text="Price right."
    )
    trailer_surcharge_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, required=False, allow_null=True, help_text="Price right; cars."
    )
    trailer_billing = serializers.ChoiceField(choices=TrailerBilling.choices, required=False)
    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
        help_text="Price right; trailers: the day price. Default: the price of the product so far.",
    )
    cost_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, required=False, allow_null=True, help_text="Purchase price right."
    )
    cost_per_day = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, required=False, allow_null=True, help_text="Trailers."
    )


class ModelToFleetView(ModuleAPIView):
    """``POST /material-models/{id}/to-fleet`` – take a model planned as material into the fleet (LOG-016)."""

    module = Module.MATERIAL

    @extend_schema(
        request=ModelToFleetSerializer,
        responses={201: inline_serializer("FleetTransition", {"items_moved": serializers.IntegerField()})},
    )
    def post(self, request: Request, pk: int) -> Response:
        """A new vehicle product becomes the model's; the old product and every project line stay as they are.

        ``open_projects`` names the open projects the caller may open that
        still plan the old product as material lines; ``open_projects_hidden``
        counts the others.
        """
        if not self.rights.can_write(Module.PRODUCTS):
            raise PermissionDenied(_("Taking a model into the fleet makes a product: it needs write access to them."))
        material_model = get_object_or_404(MaterialModel.objects.select_related("category", "default_product"), pk=pk)
        serializer = ModelToFleetSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        transition = fleet.move_model_to_fleet(material_model, self.rights, **values)
        visible = fleet.visible_project_ids(self.rights, request.user)
        named = [project for project in transition.open_projects if project.pk in visible]
        return Response(
            {
                "material_model": material_model.pk,
                "product": _product_document(transition.product),
                "old_product": _product_document(transition.old_product),
                "items_moved": transition.items_moved,
                "open_projects": [
                    {"id": project.pk, "number": project.number, "name": project.name} for project in named
                ],
                "open_projects_hidden": len(transition.open_projects) - len(named),
            },
            status=status.HTTP_201_CREATED,
        )
