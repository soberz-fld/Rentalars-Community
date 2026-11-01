# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the trips of a project (PRJ-097; changed by hand, PRJ-111).

``GET /projects/{id}/trips``
    The trips Rentalars determines from the phases and addresses of the
    project, in the order of time, each with start, stops, destination and
    its link into the route planning of Google Maps. Readable for everybody
    who sees the deployment view of the project – the drivers included.
    PRJ-111: with the changes made by hand and the trips added by hand;
    ``?removed=true`` lists the removed ones as well (``is_removed``), for
    whoever may change the project.

``POST /projects/{id}/trips``
    PRJ-111: add a trip of one's own (start, origin, destination needed).

``PATCH /projects/{id}/trips/{key}`` and ``DELETE /projects/{id}/trips/{key}``
    PRJ-111: change a trip – what equals the determined value is not stored
    and keeps following the phases – or remove it: a determined trip stays
    removed until it is reset, a trip of one's own is deleted.

``POST /projects/{id}/trips/{key}/reset``
    PRJ-111: the trip as Rentalars determines it again – also a removed one.

Changing needs edit access to the project and the right to write projects;
removing counts as a change of the project, not as deleting a record. The
work is done in ``projects.trip_changes``, as for the page (API-002).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.core.maps import MAX_WAYPOINTS
from rentalars.projects import trip_changes
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import Project
from rentalars.projects.trips import Trip, name_vehicles, trip_document, trips_of

TRIP_PLACE = inline_serializer(
    "TripPlace",
    {"label": serializers.CharField(), "note": serializers.CharField(), "address": serializers.CharField()},
)

TRIP = inline_serializer(
    "Trip",
    {
        "kind": serializers.ChoiceField(choices=["pickup", "to_venue", "from_venue", "return", "own"]),
        "title": serializers.CharField(),
        "start": serializers.DateTimeField(),
        "phase": serializers.IntegerField(allow_null=True),
        "origin": TRIP_PLACE,
        "stops": serializers.ListField(child=TRIP_PLACE),
        "destination": TRIP_PLACE,
        "route_url": serializers.CharField(),
        "problems": serializers.ListField(child=serializers.CharField()),
        # PRJ-111
        "key": serializers.CharField(help_text="Names the trip in /projects/{id}/trips/{key}."),
        "note": serializers.CharField(help_text="A note for the drivers, given by hand."),
        "is_changed": serializers.BooleanField(help_text="A determined trip changed by hand."),
        "is_removed": serializers.BooleanField(help_text="Removed; listed only with ?removed=true."),
        # LOG-007
        "vehicles": serializers.ListField(
            child=serializers.CharField(), help_text="The vehicles on the trip, each with its trailer (LOG-007)."
        ),
    },
)


class TripChangeSerializer(serializers.Serializer):
    """What a trip shall be (PRJ-111). For a determined trip a field left out keeps its value."""

    title = serializers.CharField(required=False, allow_blank=True, max_length=120)
    start = serializers.DateTimeField(required=False)
    origin = serializers.CharField(required=False, allow_blank=True, max_length=250)
    stops = serializers.ListField(
        child=serializers.CharField(max_length=250), required=False, allow_null=True, max_length=MAX_WAYPOINTS
    )
    destination = serializers.CharField(required=False, allow_blank=True, max_length=250)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class TripCreateSerializer(TripChangeSerializer):
    """A trip of one's own (PRJ-111): when, from where, to where."""

    start = serializers.DateTimeField()
    origin = serializers.CharField(max_length=250)
    destination = serializers.CharField(max_length=250)


def _found(project: Project, key: str) -> Trip:
    try:
        return trip_changes.find_trip(project, key)
    except ValidationError as error:
        raise NotFound(" ".join(error.messages)) from error


def _document_of(project: Project, key: str) -> dict[str, Any]:
    return trip_document(_found(project, key))


class ProjectTripsView(ModuleAPIView):
    """``GET /projects/{id}/trips`` – the trips with their route links (PRJ-097); ``POST`` adds one (PRJ-111)."""

    module = Module.PROJECTS
    schema_tag = "projects"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "removed", bool, description="PRJ-111: list the removed trips as well (needs edit access)."
            )
        ],
        responses={200: serializers.ListSerializer(child=TRIP)},
    )
    def get(self, request: Request, project_pk: int) -> Response:
        """Warehouse ↔ venue at setup and teardown, pickups and returns at suppliers – in the order of time."""
        project = project_for(
            request, project_pk, ProjectAccess.DEPLOYMENT, queryset=Project.objects.select_related("venue_site")
        )
        with_removed = request.query_params.get("removed") in ("true", "1") and project.access >= ProjectAccess.EDIT
        trips = trips_of(project, with_removed=with_removed)
        name_vehicles(project, trips)  # LOG-007: which vehicles drive them
        return Response([trip_document(trip) for trip in trips])

    @extend_schema(request=TripCreateSerializer, responses={201: TRIP})
    def post(self, request: Request, project_pk: int) -> Response:
        """PRJ-111: add a trip of one's own, e.g. a second delivery."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        serializer = TripCreateSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        adjustment = trip_changes.add_trip(project, user=request.user, **serializer.validated_data)
        return Response(_document_of(project, f"own-{adjustment.pk}"), status=201)


class ProjectTripView(ModuleAPIView):
    """``PATCH`` and ``DELETE /projects/{id}/trips/{key}`` – change or remove a trip (PRJ-111)."""

    module = Module.PROJECTS
    schema_tag = "projects"
    #: Removing a trip is a change of the project, not the deletion of a record: "write" for both methods.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.WRITE}

    @extend_schema(request=TripChangeSerializer, responses={200: TRIP})
    def patch(self, request: Request, project_pk: int, key: str) -> Response:
        """Change a trip; a determined one keeps what is left out. Equal to the determined trip again, it is reset."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        trip = _found(project, key)
        serializer = TripChangeSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = {
            "title": trip.title,
            "start": trip.start,
            "origin": trip.origin.address,
            "stops": [stop.address for stop in trip.stops],
            "destination": trip.destination.address,
            "note": trip.note,
            **serializer.validated_data,
        }
        if values["stops"] is None:
            values["stops"] = []
        trip_changes.change_trip(project, key, user=request.user, **values)
        return Response(_document_of(project, key))

    @extend_schema(responses={204: None})
    def delete(self, request: Request, project_pk: int, key: str) -> Response:
        """Remove a trip: a determined one until it is reset, one of one's own for good."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        _found(project, key)
        trip_changes.remove_trip(project, key, user=request.user)
        return Response(status=204)


class ProjectTripResetView(ModuleAPIView):
    """``POST /projects/{id}/trips/{key}/reset`` – the trip as Rentalars determines it again (PRJ-111)."""

    module = Module.PROJECTS
    schema_tag = "projects"

    @extend_schema(request=None, responses={200: TRIP})
    def post(self, request: Request, project_pk: int, key: str) -> Response:
        """Delete the changes made by hand; a removed trip is back."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        _found(project, key)
        trip = trip_changes.reset_trip(project, key)
        return Response(trip_document(trip))
