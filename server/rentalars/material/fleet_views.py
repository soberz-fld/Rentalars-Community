# SPDX-License-Identifier: GPL-3.0-or-later
"""The fleet in the material administration: list, utilization, vehicle data, transition (LOG-002 ff.).

* Materialverwaltung → Fuhrpark: every vehicle and trailer – the items of
  vehicle products – with licence plate, type, seats, driving licence class,
  status, next inspection and current or next booking (LOG-002, LOG-014).
* The utilization of the fleet: a timeline of the vehicles over the projects,
  overlapping bookings in red (LOG-004, LOG-018).
* The vehicle data of an item, in a dialog on the item page (LOG-003).
* "In den Fuhrpark übernehmen" on a model planned as material so far (LOG-016).

The business rules live in ``material.fleet``; the API calls the same
functions (API-002).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module, module_required, request_rights, require
from rentalars.core.forms import add_validation_error
from rentalars.core.listing import paginate
from rentalars.material import fleet
from rentalars.material.fleet_tables import FLEET_TABLE
from rentalars.material.forms import FleetTransitionForm, VehicleForm
from rentalars.material.models import ARCHIVED_STATUSES, ItemStatus, MaterialItem
from rentalars.products.models import VehicleType

#: What the list of the fleet and the utilization load with every vehicle.
_RELATED = (
    "material_model__category",
    "material_model__default_product",
    "product_override",
    "storage_location",
)


def _redirect(request: HttpRequest, target: str) -> HttpResponse:
    """Back to a page – with htmx by ``HX-Redirect``, which also closes the dialog."""
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = target
        return response
    return redirect(target)


def _filtered_vehicles(request: HttpRequest) -> Any:
    """The vehicle items narrowed by the filters ``type``, ``status`` and ``q`` of the address."""
    items = fleet.vehicle_items().select_related(*_RELATED)
    vehicle_type = request.GET.get("type", "")
    if vehicle_type in VehicleType.values:
        items = fleet.of_type(items, vehicle_type)
    status = request.GET.get("status", "")
    if status in ItemStatus.values:
        items = items.filter(status=status)
    else:
        # Retired, sold and lost vehicles stay out unless asked for (MAT-022).
        items = items.exclude(status__in=ARCHIVED_STATUSES)
    text = request.GET.get("q", "").strip()
    if text:
        items = items.filter(
            Q(vehicle__licence_plate__icontains=text)
            | Q(material_model__name__icontains=text)
            | Q(serial_number__icontains=text)
        )
    return items.order_by("inventory_number")


@module_required(Module.MATERIAL)
def fleet_list(request: HttpRequest) -> HttpResponse:
    """Materialverwaltung → Fuhrpark: the vehicles and trailers (LOG-002).

    Columns can be chosen, sorted and grouped (UIX-015, UIX-040); the
    filtered list comes as CSV (IMP-005). A motor vehicle without its seats
    says so (LOG-003); an overdue inspection is red (LOG-014); bookings that
    overlap are pointed out (LOG-004) – projects the user may not open
    without name or link (AUT-016).
    """
    rights = request_rights(request)
    items = fleet.attach(list(_filtered_vehicles(request)), fleet.visible_project_ids(rights, request.user))
    table = FLEET_TABLE.state(request)
    rows = table.order(items)
    if table.wants_csv:
        return table.csv_response(rows, _("Fleet"))
    page = paginate(request, rows)
    return render(
        request,
        "material/fleet.html",
        {
            "tab": "fleet",
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "types": VehicleType.choices,
            "vehicle_type": request.GET.get("type", ""),
            "statuses": ItemStatus.choices,
            "status": request.GET.get("status", ""),
            "q": request.GET.get("q", "").strip(),
            "has_vehicle_products": fleet.vehicle_products_exist(),
        },
    )


@module_required(Module.MATERIAL)
def fleet_utilization(request: HttpRequest) -> HttpResponse:
    """The utilization of the fleet: every vehicle and trailer with its bookings over the projects (LOG-018).

    Weeks of days or one to ten days in hours, as the timeline and the
    personnel plan (VFG-022, VFG-024); bookings that overlap are filled red
    (LOG-004). A booking of a project the user may not open shows "Projekt"
    with its number only, without name or link (AUT-016).
    """
    from rentalars.schedule.services import scale_from_request

    scale, navigation = scale_from_request(request, default_weeks=4)
    rights = request_rights(request)
    items = list(_filtered_vehicles(request))
    rows = fleet.utilization_rows(items, scale, fleet.visible_project_ids(rights, request.user))
    if request.GET.get("booked"):
        rows = [row for row in rows if row.bars]
    return render(
        request,
        "material/fleet_utilization.html",
        {
            "tab": "fleet",
            "scale": scale,
            "days": scale.days,
            "rows": rows,
            "types": VehicleType.choices,
            "vehicle_type": request.GET.get("type", ""),
            "booked_only": bool(request.GET.get("booked")),
            **navigation,
        },
    )


def vehicle_context(request: HttpRequest, item: MaterialItem) -> dict[str, Any]:
    """What the item page shows of a vehicle: its data and its current and coming bookings (LOG-002, LOG-004).

    Empty for an item that is no vehicle.
    """
    if not fleet.is_vehicle_item(item):
        return {}
    vehicle = fleet.vehicle_of(item)
    start, end = fleet.upcoming_window()
    rights = request_rights(request)
    bookings = fleet.bookings_for([item.pk], start, end, fleet.visible_project_ids(rights, request.user))
    return {
        "is_vehicle": True,
        "vehicle": vehicle,
        "vehicle_bookings": bookings.get(item.pk, [])[:20],
        "seats_missing": fleet.seats_missing(item, vehicle),
    }


@module_required(Module.MATERIAL, Level.WRITE)
def vehicle_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """The vehicle data of an item – licence plate, seats, class, towing capacity, weight (LOG-002, LOG-003).

    A dialog over the item page; without the page script a page of its own.
    The first save makes the row; every change is noted in the history of
    the item.
    """
    from rentalars.material.item_views import _load_item

    item = _load_item(pk)
    if not fleet.is_vehicle_item(item):
        raise Http404
    form = VehicleForm(request.POST or None, item=item)
    if request.method == "POST" and form.is_valid():
        try:
            fleet.save_vehicle(item, **form.changes())
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("Vehicle data of %(id)s saved.") % {"id": item.display_id})
            return _redirect(request, reverse("material:item_detail", args=[item.pk]) + "#vehicle")
    template = "material/_vehicle_form.html" if request.headers.get("HX-Request") else "material/vehicle_form.html"
    return render(request, template, {"form": form, "item": item})


@module_required(Module.MATERIAL, Level.WRITE)
def model_to_fleet(request: HttpRequest, pk: int) -> HttpResponse:
    """LOG-016: take a model planned as material so far into the fleet – with a new vehicle product.

    Needs the right to change products as well: a product is made. The old
    product and every project line stay as they are; afterwards a message
    names the open projects that still plan the old product as material.
    """
    from rentalars.material.views import _load_model

    rights = request_rights(request)
    require(rights.can_write(Module.PRODUCTS))
    material_model = _load_model(pk)
    problem = fleet.transition_problem(material_model)
    if problem:
        messages.error(request, problem)
        return _redirect(request, reverse("material:model_detail", args=[material_model.pk]))
    form = FleetTransitionForm(request.POST or None, material_model=material_model, rights=rights)
    if request.method == "POST" and form.is_valid():
        try:
            transition = fleet.move_model_to_fleet(material_model, rights, **form.values())
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(
                request,
                _("%(model)s is in the fleet now, with the vehicle product %(product)s.")
                % {"model": material_model.name, "product": transition.product.article_number},
            )
            hint = fleet.open_projects_message(transition, fleet.visible_project_ids(rights, request.user))
            if hint:
                messages.warning(request, hint)
            return _redirect(request, reverse("material:model_detail", args=[material_model.pk]))
    template = (
        "material/_fleet_transition_form.html"
        if request.headers.get("HX-Request")
        else "material/fleet_transition.html"
    )
    return render(request, template, {"form": form, "model": material_model})
