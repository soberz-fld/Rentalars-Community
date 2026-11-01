# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the block "Logistik" of the planning (LOG-001 ff.).

Adding, editing and deleting a booking and putting vehicles on trips answer
with the refreshed blocks "Personal" and "Logistik" and the totals, as the
crew does (UIX-009). The dialogs open over the planning – without the page
script as pages of their own. The work is done in ``projects.logistics``,
which the API calls as well (API-002).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.projects import logistics
from rentalars.projects.access import ProjectAccess, may_plan_logistics, project_for
from rentalars.projects.discounts import vehicle_discount_warning
from rentalars.projects.logistics_forms import TripVehicleForm, VehicleAddForm, VehicleLineForm
from rentalars.projects.models import Project, VehicleLine
from rentalars.projects.views import Touched, _error_text, _planning_response


def _project_for_logistics(request: HttpRequest, pk: int) -> Project:
    """Load a project for somebody who wants to change its logistics.

    Raises:
        PermissionDenied: The user neither edits the project nor maintains the material (the fleet).
    """
    project = project_for(request, pk, ProjectAccess.READ)
    if not may_plan_logistics(request_rights(request), project.access) or project.is_locked:
        raise PermissionDenied
    return project


def _response(request: HttpRequest, project: Project, *, close_dialog: bool = False) -> HttpResponse:
    """The refreshed blocks "Personal" and "Logistik" with the totals; without the page script back to the planning."""
    if not request.headers.get("HX-Request"):
        return redirect(reverse("projects:detail", args=[project.pk]) + "#planning-logistics")
    return _planning_response(request, project, close_dialog=close_dialog, touched=Touched(crew=True, logistics=True))


def _tell_warnings(request: HttpRequest, project: Project, line: VehicleLine) -> None:
    """LOG-004: name at once what is wrong with the booking – booked twice, blocked, inspection due."""
    found = logistics.logistics_warnings(
        project, [line], list(project.trip_vehicles.all()), list(project.crew_lines.select_related("person"))
    )
    for warning in found.get(line.pk, []):
        messages.warning(request, f"{line.label}: {warning}")


@require_POST
@module_required(Module.PROJECTS)
def vehicle_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Book a vehicle or trailer for the project – chosen, or open (LOG-001, LOG-002)."""
    project = _project_for_logistics(request, pk)
    form = VehicleAddForm(request.POST, project=project)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return _response(request, project)
    try:
        line = logistics.add_vehicle_line(
            project,
            rights=request_rights(request),
            product=form.cleaned_data["product"],
            item=form.cleaned_data["item"],
            start=form.cleaned_data.get("start"),
            end=form.cleaned_data.get("end"),
            phase=form.cleaned_data.get("phase"),
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        _tell_warnings(request, project, line)
    return _response(request, project)


@module_required(Module.PROJECTS)
def vehicle_edit(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Edit a booking in a dialog: vehicle, period, billing, rates, supplier, costs (LOG-005, LOG-010)."""
    project = _project_for_logistics(request, pk)
    line = get_object_or_404(
        project.vehicle_lines.select_related("product", "item", "tax_rate", "supplier", "phase"), pk=line_pk
    )
    rights = request_rights(request)
    form = VehicleLineForm(
        request.POST or None,
        line=line,
        rights=rights,
        offer_new_phase=project.access >= ProjectAccess.EDIT,
    )
    if request.method == "POST" and form.is_valid():
        try:
            changes = form.changes()
            if changes:
                logistics.update_vehicle_line(line, rights=rights, **changes)
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            if "discount_percent" in changes and vehicle_discount_warning(line):
                messages.warning(request, vehicle_discount_warning(line))  # Cut to the maximum – and said
            _tell_warnings(request, project, line)
            return _response(request, project, close_dialog=True)
    context = {"form": form, "line": line, "project": project, "action": request.get_full_path()}
    if request.headers.get("HX-Request"):
        return render(request, "projects/_vehicle_form.html", context)
    return render(request, "projects/vehicle_form.html", context)


@require_POST
@module_required(Module.PROJECTS)
def vehicle_delete(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Remove a booking with its trips."""
    project = _project_for_logistics(request, pk)
    line = get_object_or_404(project.vehicle_lines, pk=line_pk)
    try:
        logistics.delete_vehicle_line(line)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _response(request, project)


def _trip_form_page(request: HttpRequest, context: dict[str, Any]) -> HttpResponse:
    if request.headers.get("HX-Request"):
        return render(request, "projects/_trip_vehicle_form.html", context)
    return render(request, "projects/trip_vehicle_form.html", context)


def _route_context(project: Project, key: str) -> dict[str, Any]:
    """LOG-017: whether the route service can suggest the kilometres of this trip, and the address to ask."""
    from rentalars.core.routing import route_service_enabled

    if not route_service_enabled() or not key:
        return {"route_url": ""}
    return {"route_url": reverse("projects:trip_route", args=[project.pk, key])}


@module_required(Module.PROJECTS)
def trip_vehicle_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Put a motor vehicle on a trip, with a trailer or without, and its kilometres (LOG-007)."""
    from rentalars.projects.trips import trips_of

    project = _project_for_logistics(request, pk)
    rights = request_rights(request)
    trips = trips_of(project)
    key = request.GET.get("trip", "") or request.POST.get("trip_key", "")
    form = TripVehicleForm(request.POST or None, project=project, trips=trips, rights=rights, trip_key=key)
    if request.method == "POST" and form.is_valid():
        values = form.values()
        try:
            logistics.add_trip_vehicle(
                project,
                rights=rights,
                trip_key=values.pop("trip_key"),
                vehicle_line=values.pop("vehicle_line"),
                trailer_line=values.pop("trailer_line", None),
                **values,
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            return _response(request, project, close_dialog=True)
    context = {"form": form, "project": project, "use": None, "action": request.get_full_path()}
    context.update(_route_context(project, key))
    return _trip_form_page(request, context)


@module_required(Module.PROJECTS)
def trip_vehicle_edit(request: HttpRequest, pk: int, use_pk: int) -> HttpResponse:
    """Change a vehicle on a trip: trailer, kilometres, what is charged – or move it to another trip (LOG-007)."""
    from rentalars.projects.trips import trips_of

    project = _project_for_logistics(request, pk)
    use = get_object_or_404(project.trip_vehicles.select_related("vehicle_line", "trailer_line"), pk=use_pk)
    rights = request_rights(request)
    form = TripVehicleForm(request.POST or None, project=project, trips=trips_of(project), rights=rights, use=use)
    if request.method == "POST" and form.is_valid():
        try:
            changes = form.values()
            if changes:
                logistics.update_trip_vehicle(use, rights=rights, **changes)
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            return _response(request, project, close_dialog=True)
    context = {"form": form, "project": project, "use": use, "action": request.get_full_path()}
    context.update(_route_context(project, use.trip_key))
    return _trip_form_page(request, context)


@require_POST
@module_required(Module.PROJECTS)
def trip_vehicle_delete(request: HttpRequest, pk: int, use_pk: int) -> HttpResponse:
    """Take a vehicle off a trip."""
    project = _project_for_logistics(request, pk)
    use = get_object_or_404(project.trip_vehicles, pk=use_pk)
    try:
        logistics.delete_trip_vehicle(use)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _response(request, project)


@module_required(Module.PROJECTS)
def trip_route(request: HttpRequest, pk: int, key: str) -> JsonResponse:
    """LOG-017: the kilometres of a trip as the route service reckons them – a suggestion for "planned km".

    Answers ``{"km": "123.4"}``, or ``{"error": "…"}`` when the service is off,
    an address cannot be found or no route is known.
    """
    from rentalars.core.routing import RouteError, trip_distance
    from rentalars.projects.trips import trips_of

    project = _project_for_logistics(request, pk)
    trip = next((trip for trip in trips_of(project) if trip.key == key), None)
    if trip is None:
        return JsonResponse({"error": _("The project has no such trip.")}, status=404)
    try:
        km = trip_distance(trip)
    except RouteError as error:
        return JsonResponse({"error": str(error)})
    return JsonResponse({"km": f"{km:.1f}"})
