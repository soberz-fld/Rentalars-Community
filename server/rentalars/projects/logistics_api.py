# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the logistics of a project: vehicle bookings and the vehicles on the trips (LOG-001 ff., LOG-015).

``GET``/``POST /projects/{id}/logistics``
    The vehicles and trailers booked for the project with what they cost
    the customer (price right) and the company (purchase price right) and
    their warnings; ``POST`` books one – a vehicle of the fleet (``item``),
    or a vehicle product (``product``) to be chosen later or rented in
    (``supplier``).

``GET``/``PUT``/``PATCH``/``DELETE /projects/{id}/logistics/{booking}``
    One booking.

``GET``/``POST /projects/{id}/trips/{key}/vehicles``
    The motor vehicles on one trip of the project, each with its trailer
    and kilometres (LOG-007); ``POST`` puts one on it.

``GET``/``PUT``/``PATCH``/``DELETE /projects/{id}/trip-vehicles/{id}``
    One vehicle on a trip; ``trip_key`` moves it to another trip.

``GET /projects/{id}/trips/{key}/route``
    LOG-017: the kilometres of a trip as the route service reckons them – a
    suggestion for ``planned_km``; 400 with the reason without a service or
    without a route.

Reading needs read access to the project; changing needs edit access – or
read access together with write access to the material, which holds the
fleet (``access.may_plan_logistics``). Prices and the charged kilometres'
amounts need the price right, internal costs the right to see purchase
prices (AUT-019). The work is done in ``projects.logistics``, as for the
page (API-002).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.masterdata.models import Supplier, TaxRate
from rentalars.material.models import MaterialItem
from rentalars.products.models import Product
from rentalars.projects import logistics
from rentalars.projects.access import ProjectAccess, may_plan_logistics, project_for
from rentalars.projects.discounts import vehicle_discount_warning
from rentalars.projects.models import Project, ProjectPhase, TripBilling, TripVehicle, VehicleBilling, VehicleLine
from rentalars.projects.pricing import compute_project_prices

DOCUMENT = inline_serializer("VehicleBooking", {"id": serializers.IntegerField()})
TRIP_VEHICLE = inline_serializer("TripVehicle", {"id": serializers.IntegerField()})


def charge_document(charge: logistics.TripCharge, *, with_prices: bool) -> dict[str, Any]:
    """What one trip adds to a booking (LOG-009)."""
    document: dict[str, Any] = {
        "trip_vehicle": charge.use.pk,
        "trip_key": charge.use.trip_key,
        "trip_title": charge.trip.title if charge.trip is not None else None,
        "trip_start": charge.trip.start if charge.trip is not None else None,
        "km": charge.km,
        "km_source": charge.km_source,
        "in_flat_rate": charge.in_flat_rate,
    }
    if with_prices:
        document.update(rate=charge.rate, surcharge_rate=charge.surcharge_rate, amount=charge.amount)
    return document


def vehicle_line_document(
    price: logistics.VehiclePrice, warnings: list[str] | None = None, *, with_prices: bool, with_costs: bool
) -> dict[str, Any]:
    """A booking with what was calculated for it, as far as the caller may see it (LOG-005, LOG-009, LOG-010)."""
    line = price.line
    document: dict[str, Any] = {
        "id": line.pk,
        "project": line.project_id,
        "product": line.product_id,
        "product_article_number": line.product.article_number,
        "vehicle_type": line.product.vehicle_type,
        "item": line.item_id,
        "item_display_id": line.item.display_id if line.item_id else None,
        "label": line.label,
        "title": line.title,
        "is_open": line.is_open,
        "supplier": line.supplier_id,
        "phase": line.phase_id,
        "start": line.start,
        "end": line.end,
        "note": line.note,
        "km_total": price.km_total,
        "days": price.days,
        "days_source": price.days_source or None,
        "trips": [charge_document(charge, with_prices=with_prices) for charge in price.charges],
        "warnings": warnings or [],
    }
    if with_prices:
        document.update(
            billing=line.billing,
            price_per_km=line.price_per_km,
            trailer_surcharge_per_km=line.trailer_surcharge_per_km,
            price_per_day=line.price_per_day,
            rental_days=line.rental_days,
            only_trip_days=line.only_trip_days,
            scale_factor=price.scale_factor,
            tax_rate=line.tax_rate_id,
            discount_percent=line.discount_percent,
            effective_discount_percent=price.discount_percent,
            max_discount_percent=price.max_discount_percent,
            discount_is_capped=price.discount_is_capped,
            surcharge_amount=price.surcharge_total,
            amount_before_discount=price.base_amount,
            discount=price.discount_amount,
            amount=price.amount,
            is_estimate=price.is_estimate,
        )
    if with_costs:
        document.update(
            cost_per_km=line.cost_per_km,
            cost_per_day=line.cost_per_day,
            subrental_cost=line.subrental_cost,
            cost=price.cost,
            cost_is_known=price.cost_is_known,
        )
    return document


def trip_vehicle_document(use: TripVehicle, *, with_prices: bool) -> dict[str, Any]:
    """One vehicle on a trip (LOG-007)."""
    document: dict[str, Any] = {
        "id": use.pk,
        "project": use.project_id,
        "trip_key": use.trip_key,
        "vehicle_line": use.vehicle_line_id,
        "trailer_line": use.trailer_line_id,
        "planned_km": use.planned_km,
        "driven_km": use.driven_km,
        "charged_km": use.charged_km,
        "km_is_estimate": use.km_is_estimate,
        "note": use.note,
    }
    if with_prices:
        document.update(billing=use.billing, flat_price=use.flat_price)
    return document


class VehicleLineInput(serializers.Serializer):
    """A booking: what, when, at which rates (LOG-001, LOG-005, LOG-010).

    ``item`` books a vehicle of the fleet – its product follows; without it
    ``product`` books an open vehicle or, with ``supplier``, a rented one.
    Rates, billing and days need the price right; ``cost_per_km``,
    ``cost_per_day`` and ``subrental_cost`` the right to see purchase prices.
    """

    item = serializers.PrimaryKeyRelatedField(queryset=MaterialItem.objects.all(), required=False, allow_null=True)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False)
    title = serializers.CharField(max_length=200, required=False)
    phase = serializers.PrimaryKeyRelatedField(queryset=ProjectPhase.objects.all(), required=False, allow_null=True)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all(), required=False, allow_null=True)
    billing = serializers.ChoiceField(choices=VehicleBilling.values, required=False)
    price_per_km = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0"), required=False)
    trailer_surcharge_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0"), required=False
    )
    price_per_day = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False)
    rental_days = serializers.IntegerField(min_value=1, max_value=999, required=False, allow_null=True)
    only_trip_days = serializers.BooleanField(required=False)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False
    )
    tax_rate = serializers.PrimaryKeyRelatedField(queryset=TaxRate.objects.all(), required=False)
    cost_per_km = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    cost_per_day = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    subrental_cost = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )


class TripVehicleInput(serializers.Serializer):
    """A motor vehicle on a trip with its trailer and kilometres (LOG-006, LOG-007).

    ``billing`` (``driven``, ``planned``, ``flat``) and ``flat_price`` need the
    price right; ``trip_key`` (only when changing) moves it to another trip.
    """

    trip_key = serializers.CharField(max_length=40, required=False)
    vehicle_line = serializers.PrimaryKeyRelatedField(queryset=VehicleLine.objects.all(), required=False)
    trailer_line = serializers.PrimaryKeyRelatedField(
        queryset=VehicleLine.objects.all(), required=False, allow_null=True
    )
    planned_km = serializers.DecimalField(
        max_digits=8, decimal_places=1, min_value=Decimal("0"), required=False, allow_null=True
    )
    driven_km = serializers.DecimalField(
        max_digits=8, decimal_places=1, min_value=Decimal("0"), required=False, allow_null=True
    )
    billing = serializers.ChoiceField(choices=TripBilling.values, required=False)
    flat_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class _LogisticsView(ModuleAPIView):
    """Common ground: the module "projects" at read level; who may change is decided per project."""

    module = Module.PROJECTS
    schema_tag = "projects"
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    def project(self, request: Request, project_pk: int, *, change: bool = False) -> Project:
        """The project for a caller who may read it – and, to change, plan its logistics."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        if change and (not may_plan_logistics(self.rights, project.access) or project.is_locked):
            raise PermissionDenied(_("You may not change the logistics of this project."))
        return project

    @property
    def with_prices(self) -> bool:
        """AUT-019: prices only with the price right."""
        return self.rights.has(SpecialRight.PRICES)

    @property
    def with_costs(self) -> bool:
        """AUT-019, LOG-010: internal costs only with the right to see purchase prices."""
        return self.rights.has(SpecialRight.PURCHASE_PRICES)

    def documents(self, project: Project) -> list[dict[str, Any]]:
        """Every booking of the project, priced, with warnings and the trips named."""
        from rentalars.projects.trips import trips_of

        prices = compute_project_prices(project)
        trips = trips_of(project)
        logistics.describe_trips(prices.logistics, trips)
        warnings = logistics.logistics_warnings(
            project,
            [price.line for price in prices.logistics],
            prices.trip_vehicles,
            [price.line for price in prices.crew],
            trip_keys={trip.key for trip in trips},
        )
        return [
            vehicle_line_document(
                price, warnings.get(price.line.pk, []), with_prices=self.with_prices, with_costs=self.with_costs
            )
            for price in prices.logistics
        ]

    def document(self, project: Project, line_pk: int) -> dict[str, Any]:
        """One booking as :meth:`documents` gives it, or 404."""
        found = next((document for document in self.documents(project) if document["id"] == line_pk), None)
        if found is None:
            raise NotFound
        return found


class ProjectLogisticsView(_LogisticsView):
    """``GET``/``POST /projects/{id}/logistics`` – the vehicle bookings of a project (LOG-001, LOG-015)."""

    @extend_schema(responses={200: serializers.ListSerializer(child=DOCUMENT)})
    def get(self, request: Request, project_pk: int) -> Response:
        """The bookings with trips, kilometres, days, prices, costs and warnings."""
        return Response(self.documents(self.project(request, project_pk)))

    @extend_schema(request=VehicleLineInput, responses={201: DOCUMENT})
    def post(self, request: Request, project_pk: int) -> Response:
        """Book a vehicle of the fleet (``item``) or an open or rented one (``product``)."""
        project = self.project(request, project_pk, change=True)
        serializer = VehicleLineInput(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        item = values.pop("item", None)
        product = values.pop("product", None)
        if item is not None:
            product = product or item.product
        if product is None:
            raise ValidationError({"product": _("Choose a vehicle or a trailer of the fleet.")})
        if values.get("phase") is not None and values["phase"].project_id != project.pk:
            raise ValidationError({"phase": _("Choose a phase of this project.")})
        line = logistics.add_vehicle_line(
            project,
            rights=self.rights,
            product=product,
            item=item,
            start=values.pop("start", None),
            end=values.pop("end", None),
            phase=values.pop("phase", None),
            **values,
        )
        document = self.document(project, line.pk)
        if "discount_percent" in values and vehicle_discount_warning(line):  # See ``patch``
            document["warnings"] = [*document["warnings"], vehicle_discount_warning(line)]
        return Response(document, status=status.HTTP_201_CREATED)


class VehicleLineView(_LogisticsView):
    """``GET``/``PUT``/``PATCH``/``DELETE /projects/{id}/logistics/{booking}`` – one booking."""

    def line(self, project: Project, pk: int) -> VehicleLine:
        """The booking of the project named in the address, or 404."""
        line = project.vehicle_lines.select_related("product", "item", "project").filter(pk=pk).first()
        if line is None:
            raise NotFound
        return line

    @extend_schema(responses={200: DOCUMENT})
    def get(self, request: Request, project_pk: int, pk: int) -> Response:
        """One booking with its trips, prices, costs and warnings."""
        project = self.project(request, project_pk)
        self.line(project, pk)
        return Response(self.document(project, pk))

    @extend_schema(request=VehicleLineInput, responses={200: DOCUMENT})
    def patch(self, request: Request, project_pk: int, pk: int) -> Response:
        """Change a booking: another vehicle or product, period, rates, supplier, costs."""
        project = self.project(request, project_pk, change=True)
        line = self.line(project, pk)
        serializer = VehicleLineInput(data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if values.get("item") is not None and "product" not in values:
            values["product"] = values["item"].product
        if values.get("phase") is not None and values["phase"].project_id != project.pk:
            raise ValidationError({"phase": _("Choose a phase of this project.")})
        logistics.update_vehicle_line(line, rights=self.rights, **values)
        document = self.document(project, pk)
        if "discount_percent" in values and vehicle_discount_warning(line):
            # The discount above the maximum of the product is cut – and said, next to the other warnings.
            document["warnings"] = [*document["warnings"], vehicle_discount_warning(line)]
        return Response(document)

    @extend_schema(request=VehicleLineInput, responses={200: DOCUMENT})
    def put(self, request: Request, project_pk: int, pk: int) -> Response:
        """The same as ``PATCH``: fields left out keep their values."""
        return self.patch(request, project_pk, pk)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, project_pk: int, pk: int) -> Response:
        """Remove a booking with its trips."""
        project = self.project(request, project_pk, change=True)
        logistics.delete_vehicle_line(self.line(project, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class TripVehiclesView(_LogisticsView):
    """``GET``/``POST /projects/{id}/trips/{key}/vehicles`` – the vehicles on one trip (LOG-007)."""

    @extend_schema(responses={200: serializers.ListSerializer(child=TRIP_VEHICLE)})
    def get(self, request: Request, project_pk: int, key: str) -> Response:
        """The motor vehicles on the trip with trailer and kilometres."""
        project = self.project(request, project_pk)
        uses = project.trip_vehicles.filter(trip_key=key).order_by("id")
        return Response([trip_vehicle_document(use, with_prices=self.with_prices) for use in uses])

    @extend_schema(request=TripVehicleInput, responses={201: TRIP_VEHICLE})
    def post(self, request: Request, project_pk: int, key: str) -> Response:
        """Put a motor vehicle of the project on the trip, with a trailer or without."""
        project = self.project(request, project_pk, change=True)
        serializer = TripVehicleInput(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.pop("trip_key", None)
        vehicle_line = values.pop("vehicle_line", None)
        if vehicle_line is None:
            raise ValidationError({"vehicle_line": _("Choose a vehicle booked in this project.")})
        use = logistics.add_trip_vehicle(
            project,
            rights=self.rights,
            trip_key=key,
            vehicle_line=vehicle_line,
            trailer_line=values.pop("trailer_line", None),
            **{name: value for name, value in values.items() if value is not None},
        )
        return Response(trip_vehicle_document(use, with_prices=self.with_prices), status=status.HTTP_201_CREATED)


class TripVehicleView(_LogisticsView):
    """``GET``/``PUT``/``PATCH``/``DELETE /projects/{id}/trip-vehicles/{id}`` – one vehicle on a trip."""

    def use(self, project: Project, pk: int) -> TripVehicle:
        """The vehicle on a trip of the project named in the address, or 404."""
        use = project.trip_vehicles.select_related("project", "vehicle_line", "trailer_line").filter(pk=pk).first()
        if use is None:
            raise NotFound
        return use

    @extend_schema(responses={200: TRIP_VEHICLE})
    def get(self, request: Request, project_pk: int, pk: int) -> Response:
        """One vehicle on a trip."""
        project = self.project(request, project_pk)
        return Response(trip_vehicle_document(self.use(project, pk), with_prices=self.with_prices))

    @extend_schema(request=TripVehicleInput, responses={200: TRIP_VEHICLE})
    def patch(self, request: Request, project_pk: int, pk: int) -> Response:
        """Change trailer, kilometres, what is charged – or move it to another trip."""
        project = self.project(request, project_pk, change=True)
        use = self.use(project, pk)
        serializer = TripVehicleInput(data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        logistics.update_trip_vehicle(use, rights=self.rights, **serializer.validated_data)
        return Response(trip_vehicle_document(use, with_prices=self.with_prices))

    @extend_schema(request=TripVehicleInput, responses={200: TRIP_VEHICLE})
    def put(self, request: Request, project_pk: int, pk: int) -> Response:
        """The same as ``PATCH``: fields left out keep their values."""
        return self.patch(request, project_pk, pk)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, project_pk: int, pk: int) -> Response:
        """Take the vehicle off the trip."""
        project = self.project(request, project_pk, change=True)
        logistics.delete_trip_vehicle(self.use(project, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class TripRouteView(_LogisticsView):
    """``GET /projects/{id}/trips/{key}/route`` – the kilometres the route service reckons (LOG-017)."""

    @extend_schema(responses={200: inline_serializer("TripRoute", {"km": serializers.DecimalField(9, 1)})})
    def get(self, request: Request, project_pk: int, key: str) -> Response:
        """A suggestion for the planned kilometres; 400 with the reason if there is none."""
        from rentalars.core.routing import RouteError, trip_distance
        from rentalars.projects.trips import trips_of

        # As in the browser: only who may plan the logistics – the question may look up addresses.
        project = self.project(request, project_pk, change=True)
        trip = next((trip for trip in trips_of(project) if trip.key == key), None)
        if trip is None:
            raise NotFound(_("The project has no such trip."))
        try:
            km = trip_distance(trip)
        except RouteError as error:
            raise ValidationError(str(error)) from error
        return Response({"km": km})
