# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the maps at addresses (UIX-033, UIX-034).

``GET /maps/{target}/{id}``
    The places of a map – a venue, a customer with its further addresses, a
    supplier, the company with the warehouse (``company``, id 1) or the
    places of a project's trips (``project``) – each with its route link
    into Google Maps and its position. Positions not known yet are looked
    up (Nominatim, at most five per call); the answer says how a position
    came about: ``found``, ``manual``, ``not_found`` or ``unknown``.
``PUT /maps/{target}/{id}/positions/{key}``
    Set the position of one address of that map by hand; it holds for every
    record with that address.
``DELETE /maps/{target}/{id}/positions/{key}``
    Forget it: the next call looks the address up again.

Who may read a map may read its record (for a project: the deployment
view); who may correct it may change its record (for a project: edit it).
"""

from __future__ import annotations

from typing import Any

from django.http import Http404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.api.permissions import AUTHENTICATED_ONLY
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.core import maps

PLACE = inline_serializer(
    "MapPlace",
    {
        "label": serializers.CharField(),
        "note": serializers.CharField(),
        "address": serializers.CharField(),
        "key": serializers.CharField(allow_null=True),
        "route_url": serializers.CharField(),
        "position": serializers.ChoiceField(choices=["found", "manual", "not_found", "unknown"]),
        "latitude": serializers.DecimalField(9, 6, allow_null=True),
        "longitude": serializers.DecimalField(9, 6, allow_null=True),
    },
)

MAP = inline_serializer(
    "Map",
    {
        "target": serializers.CharField(),
        "id": serializers.IntegerField(),
        "title": serializers.CharField(),
        "can_correct": serializers.BooleanField(),
        "maps_enabled": serializers.BooleanField(),
        "places": serializers.ListField(child=PLACE),
        "problems": serializers.ListField(child=serializers.CharField()),
    },
)


def _page(request: Request, target: str, pk: int) -> maps.MapPage:
    if target not in maps.TARGETS:
        raise Http404
    return maps.map_for(request, target, pk)


def map_document(page: maps.MapPage) -> dict[str, Any]:
    """A map as the API shows it."""
    return {
        "target": page.target,
        "id": page.pk,
        "title": page.title,
        "can_correct": page.can_correct,
        "maps_enabled": maps.maps_enabled(),
        "places": [maps.place_document(place) for place in page.places],
        "problems": page.problems,
    }


class MapView(ModuleAPIView):
    """``GET /maps/{target}/{id}`` – the places of a map with route links and positions (UIX-033, UIX-034)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "maps"

    @extend_schema(responses={200: MAP})
    def get(self, request: Request, target: str, pk: int) -> Response:
        """The places with their positions; missing ones are looked up now.

        Targets: ``venue``, ``customer``, ``supplier``, ``company`` (id 1), ``project``.
        """
        page = _page(request, target, pk)
        maps.locate(page)
        return Response(map_document(page))


class MapPositionView(ModuleAPIView):
    """``/maps/{target}/{id}/positions/{key}`` – set a position by hand or forget it (UIX-034)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "maps"

    @extend_schema(
        request=inline_serializer(
            "MapPositionChange",
            {"latitude": serializers.DecimalField(9, 6), "longitude": serializers.DecimalField(9, 6)},
        ),
        responses={200: MAP},
    )
    def put(self, request: Request, target: str, pk: int, key: str) -> Response:
        """Set the position of an address of the map by hand; it holds for every record with that address."""
        page = _page(request, target, pk)
        body = body_of(request)
        maps.set_position(page, key, body.get("latitude", ""), body.get("longitude", ""), user=request.user)
        maps.attach_positions(page.places)
        return Response(map_document(page))

    @extend_schema(responses={200: MAP})
    def delete(self, request: Request, target: str, pk: int, key: str) -> Response:
        """Forget the position of an address; the next opening of a map looks it up again."""
        page = _page(request, target, pk)
        maps.forget_position(page, key, user=request.user)
        maps.attach_positions(page.places)
        return Response(map_document(page))
