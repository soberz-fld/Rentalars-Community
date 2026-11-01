# SPDX-License-Identifier: GPL-3.0-or-later
"""The trips of a project, determined by Rentalars (PRJ-097).

The catalogue says which trips a project has, from its phases (PRJ-006):

* **Packen** – the pickup of subrented material at the suppliers that is
  marked "wird beim Lieferanten abgeholt" (``MaterialLine.picked_up_at_supplier``):
  from the warehouse to every such supplier and back.
* **Aufbau** – from the warehouse to the venue, and back.
* **Abbau** – the same.
* **Nachbereitung** – as for "Packen": the subrented material goes back to
  the suppliers it was fetched from.

Without a phase "Packen" or "Nachbereitung" the pickups and returns still
count – at the start and the end of the subrentals. Every trip carries a
link into the route planning of Google Maps with its stops and destination;
it starts where the viewer is, not at the start of the trip (UIX-033).
No distance is computed: that would need a routing
service outside, so a link to the route planning of Google Maps
is all there is.

The warehouse is the address of the setting (``CompanyProfile.warehouse_address``),
else the address of the company. The venue of a phase is its venue of the
master data, else the venue of the project, else the place typed into the
phase, else the venue typed into the project, else the delivery address of
the project.

PRJ-111: the planner can change a trip – departure, start, stops,
destination, title, note –, remove it, or add a trip of their own
(``TripAdjustment``, written by ``projects.trip_changes``). The determined
trips stay the default: "zurücksetzen" deletes the adjustment, and a
removed trip stays removed however the phases change. Route links and the
map follow the changes.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext

from rentalars.core.maps import Place, address_key, one_line, route_url, venue_address, warehouse_address
from rentalars.products.models import ProductKind
from rentalars.projects.models import LineVariant, PhaseKind, Project, ProjectPhase


class TripKind:
    """What a trip is for; the values appear in the API."""

    PICKUP = "pickup"
    TO_VENUE = "to_venue"
    FROM_VENUE = "from_venue"
    RETURN = "return"
    #: PRJ-111: a trip added by hand.
    OWN = "own"


TRIP_TITLES = {
    (PhaseKind.SETUP, TripKind.TO_VENUE): gettext_lazy("To the setup"),
    (PhaseKind.SETUP, TripKind.FROM_VENUE): gettext_lazy("Back from the setup"),
    (PhaseKind.TEARDOWN, TripKind.TO_VENUE): gettext_lazy("To the teardown"),
    (PhaseKind.TEARDOWN, TripKind.FROM_VENUE): gettext_lazy("Back from the teardown"),
    (None, TripKind.PICKUP): gettext_lazy("Pickup at the suppliers"),
    (None, TripKind.RETURN): gettext_lazy("Return to the suppliers"),
}


@dataclass
class Trip:
    """One trip of a project: when, what for, from where over which stops to where."""

    kind: str
    start: datetime.datetime
    origin: Place
    destination: Place
    stops: list[Place] = field(default_factory=list)
    phase: ProjectPhase | None = None
    #: What is missing for a complete route, as sentences for the page.
    problems: list[str] = field(default_factory=list)
    #: PRJ-111: what names the trip in addresses and adjustments – ``to_venue-12``, ``pickup``, ``own-3``.
    key: str = ""
    #: PRJ-111: the change made by hand (``TripAdjustment``), or ``None``.
    adjustment: Any = None
    #: PRJ-111: a title given by hand, a note for the drivers, and whether the trip was removed.
    own_title: str = ""
    note: str = ""
    is_removed: bool = False
    #: LOG-007: the vehicles on the trip, each with its trailer – "Sprinter (B-RL 100) + Anhänger (…)";
    #: filled in by :func:`name_vehicles` where the trips are shown.
    vehicles: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        """What the trip is, e.g. "Fahrt zum Aufbau" – or the title given by hand (PRJ-111)."""
        if self.own_title:
            return self.own_title
        if self.kind == TripKind.OWN:
            return str(_("Own trip"))
        phase_kind = self.phase.kind if self.phase is not None and self.kind in ("to_venue", "from_venue") else None
        return str(TRIP_TITLES[(phase_kind, self.kind)])

    @property
    def is_own(self) -> bool:
        """Whether the trip was added by hand (PRJ-111)."""
        return self.kind == TripKind.OWN

    @property
    def is_changed(self) -> bool:
        """Whether a trip Rentalars determines was changed by hand (PRJ-111)."""
        return self.adjustment is not None and not self.is_own

    @property
    def places(self) -> list[Place]:
        """Start, stops and destination in the order of the trip."""
        return [self.origin, *self.stops, self.destination]

    @property
    def route_url(self) -> str:
        """The link into the route planning of Google Maps; empty if the destination has no address.

        UIX-033: from the viewer's current location over the stops of the trip to its destination.
        """
        if not self.destination.has_address:
            return ""
        stops = [stop.address for stop in self.stops if stop.has_address]
        return route_url(self.destination.address, waypoints=stops)


def _warehouse(address: str) -> Place:
    return Place(label=_("Warehouse"), address=address, note=_("Warehouse"))


def _venue_of(project: Project, phase: ProjectPhase | None) -> Place:
    """Where a phase takes place, as a place with an address (see the module text)."""
    if phase is not None and phase.venue_site_id:
        venue = phase.venue_site
        return Place(label=venue.name, address=venue_address(venue), note=_("Venue"))
    if project.venue_site_id:
        venue = project.venue_site
        return Place(label=venue.name, address=venue_address(venue), note=_("Venue"))
    if phase is not None and phase.location.strip():
        return Place(label=phase.location, address=phase.location, note=_("Venue"))
    if project.venue.strip():
        return Place(label=project.venue, address=project.venue, note=_("Venue"))
    if project.delivery_address_id:
        address = project.delivery_address
        text = one_line(address.street, f"{address.postal_code} {address.city}", address.country)
        return Place(label=address.label or text, address=text, note=_("Delivery address"))
    return Place(label=_("Venue"), address="", note=_("Venue"))


@dataclass
class _Pickup:
    """The subrentals of one supplier that are fetched there."""

    place: Place
    start: datetime.datetime
    end: datetime.datetime


def _pickups(project: Project) -> list[_Pickup]:
    """The suppliers whose subrentals of the project are picked up, with the period of those subrentals."""
    lines = (
        project.material_lines.filter(
            product__kind=ProductKind.SUBRENTAL,
            picked_up_at_supplier=True,
            supplier__isnull=False,
            variant=LineVariant.NORMAL,
        )
        .select_related("supplier")
        .order_by("start", "pk")
    )
    found: dict[int, _Pickup] = {}
    for line in lines:
        pickup = found.get(line.supplier_id)
        if pickup is None:
            supplier = line.supplier
            place = Place(label=supplier.name, address=supplier.address_one_line, note=_("Supplier"))
            found[line.supplier_id] = _Pickup(place=place, start=line.start, end=line.end)
        else:
            pickup.start = min(pickup.start, line.start)
            pickup.end = max(pickup.end, line.end)
    return list(found.values())


def _check(trip: Trip) -> Trip:
    """Note what is missing for the route of a trip."""
    if not trip.origin.has_address:
        trip.problems.append(_("The address of the warehouse is missing (Settings → Company data)."))
    for stop in trip.stops:
        if not stop.has_address:
            trip.problems.append(_("The supplier %(name)s has no address yet.") % {"name": stop.label})
    if not trip.destination.has_address:
        trip.problems.append(_("The phase and the project name no venue with an address."))
    return trip


def computed_trips(project: Project) -> list[Trip]:
    """The trips Rentalars determines for a project, in the order of time (PRJ-097) – without changes by hand."""
    address = warehouse_address()
    phases = list(project.phases.select_related("venue_site").order_by("start", "pk"))
    pickups = _pickups(project)
    stops = [pickup.place for pickup in pickups]
    trips: list[Trip] = []
    picked = returned = False
    for phase in phases:
        if phase.kind in (PhaseKind.SETUP, PhaseKind.TEARDOWN):
            venue = _venue_of(project, phase)
            trips.append(_check(Trip(TripKind.TO_VENUE, phase.start, _warehouse(address), venue, phase=phase)))
            trips.append(_check(Trip(TripKind.FROM_VENUE, phase.end, venue, _warehouse(address), phase=phase)))
        elif phase.kind == PhaseKind.LOADING and stops and not picked:
            trips.append(_round_trip(TripKind.PICKUP, phase.start, address, stops, phase))
            picked = True
        elif phase.kind == PhaseKind.AFTERCARE and stops and not returned:
            trips.append(_round_trip(TripKind.RETURN, phase.start, address, stops, phase))
            returned = True
    # Without a phase "Packen" or "Nachbereitung": at the start and the end of the subrentals.
    if stops and not picked:
        trips.append(_round_trip(TripKind.PICKUP, min(pickup.start for pickup in pickups), address, stops, None))
    if stops and not returned:
        trips.append(_round_trip(TripKind.RETURN, max(pickup.end for pickup in pickups), address, stops, None))
    # At the same time the material is fetched before it goes out, and brought back after it came in.
    order = {TripKind.PICKUP: 0, TripKind.TO_VENUE: 1, TripKind.FROM_VENUE: 2, TripKind.RETURN: 3}
    trips.sort(key=lambda trip: (trip.start, order[trip.kind]))
    for trip in trips:
        trip.key = trip_key(trip.kind, trip.phase)  # PRJ-111
    return trips


def trip_key(kind: str, phase: ProjectPhase | None) -> str:
    """The name of a determined trip that its adjustment refers to (PRJ-111).

    The trips to and from the venue come once per phase setup or teardown:
    ``to_venue-12``. Pickup and return come once per project, with or
    without a phase "Packen" or "Nachbereitung": ``pickup``, ``return``.
    """
    if kind in (TripKind.TO_VENUE, TripKind.FROM_VENUE) and phase is not None:
        return f"{kind}-{phase.pk}"
    return kind


def trips_of(project: Project, *, with_removed: bool = False) -> list[Trip]:
    """The trips of a project in the order of time, with the changes made by hand (PRJ-097, PRJ-111).

    The determined trips (:func:`computed_trips`) take what an adjustment
    fills in; removed ones are left out – or, with ``with_removed``, kept
    with ``is_removed`` for the page that offers them back. The trips added
    by hand join them. One query more than the determined trips.
    """
    trips = computed_trips(project)
    adjustments = list(project.trip_adjustments.all())
    if not adjustments:
        return trips
    by_key = {adjustment.trip_key: adjustment for adjustment in adjustments if adjustment.trip_key}
    shown: list[Trip] = []
    for trip in trips:
        adjustment = by_key.get(trip.key)
        if adjustment is not None:
            _adjust(trip, adjustment)
        if with_removed or not trip.is_removed:
            shown.append(trip)
    for adjustment in adjustments:
        if not adjustment.trip_key:
            shown.append(_own_trip(adjustment))
    shown.sort(key=lambda trip: trip.start)
    return shown


def trip_keys_of(project_ids: Iterable[int]) -> dict[int, set[str]]:
    """The keys of the trips each project has now – as :func:`trips_of` names them, three queries for all (LOG-007).

    For the prices of the logistics: a vehicle on a trip that is gone
    is not charged. The same rules as :func:`computed_trips` and
    :func:`trips_of`, without places and times: a trip there and back per
    phase "Aufbau" or "Abbau", pickup and return when subrentals are picked
    up at a supplier, less the trips removed by hand, plus the trips added
    by hand.
    """
    from rentalars.projects.models import MaterialLine, TripAdjustment

    ids = set(project_ids)
    keys: dict[int, set[str]] = {pk: set() for pk in ids}
    if not ids:
        return keys
    for project_id, phase_id in ProjectPhase.objects.filter(
        project_id__in=ids, kind__in=(PhaseKind.SETUP, PhaseKind.TEARDOWN)
    ).values_list("project_id", "pk"):
        keys[project_id] |= {f"{TripKind.TO_VENUE}-{phase_id}", f"{TripKind.FROM_VENUE}-{phase_id}"}
    for project_id in (
        MaterialLine.objects.filter(
            project_id__in=ids,
            product__kind=ProductKind.SUBRENTAL,
            picked_up_at_supplier=True,
            supplier__isnull=False,
            variant=LineVariant.NORMAL,
        )
        .values_list("project_id", flat=True)
        .distinct()
    ):
        keys[project_id] |= {TripKind.PICKUP, TripKind.RETURN}
    for project_id, adjustment_id, key, removed in TripAdjustment.objects.filter(project_id__in=ids).values_list(
        "project_id", "pk", "trip_key", "is_removed"
    ):
        if not key:
            keys[project_id].add(f"{TripKind.OWN}-{adjustment_id}")
        elif removed:
            keys[project_id].discard(key)
    return keys


def _given_place(address: str, note: str) -> Place:
    """A place typed in by hand: its address is its label (PRJ-111)."""
    return Place(label=address, address=address, note=note)


def _adjust(trip: Trip, adjustment: Any) -> None:
    """Put what an adjustment fills in into a determined trip, and check the route again (PRJ-111)."""
    trip.adjustment = adjustment
    trip.is_removed = adjustment.is_removed
    trip.own_title = adjustment.title
    trip.note = adjustment.note
    if adjustment.start is not None:
        trip.start = adjustment.start
    if adjustment.origin.strip():
        trip.origin = _given_place(adjustment.origin.strip(), _("Start"))
    if adjustment.stops is not None:
        trip.stops = [_given_place(stop, pgettext("trip", "Stop")) for stop in adjustment.stops if str(stop).strip()]
    if adjustment.destination.strip():
        trip.destination = _given_place(adjustment.destination.strip(), _("Destination"))
    trip.problems = []
    _check(trip)


def _own_trip(adjustment: Any) -> Trip:
    """A trip added by hand (PRJ-111)."""
    trip = Trip(
        TripKind.OWN,
        adjustment.start,
        _given_place(adjustment.origin, _("Start")),
        _given_place(adjustment.destination, _("Destination")),
        [_given_place(stop, pgettext("trip", "Stop")) for stop in adjustment.stops or [] if str(stop).strip()],
        key=f"{TripKind.OWN}-{adjustment.pk}",
        adjustment=adjustment,
        own_title=adjustment.title,
        note=adjustment.note,
    )
    return trip


def _round_trip(
    kind: str, start: datetime.datetime, warehouse: str, stops: list[Place], phase: ProjectPhase | None
) -> Trip:
    """From the warehouse to the suppliers and back."""
    return _check(Trip(kind, start, _warehouse(warehouse), _warehouse(warehouse), list(stops), phase=phase))


def name_vehicles(project: Project, trips: list[Trip]) -> None:
    """LOG-007: put the vehicles of the logistics on the trips they drive – for the drivers. One query."""
    if not trips:
        return
    by_key = {trip.key: trip for trip in trips}
    uses = project.trip_vehicles.select_related(
        "vehicle_line__item__vehicle", "vehicle_line__supplier", "trailer_line__item__vehicle", "trailer_line__supplier"
    ).order_by("id")
    for use in uses:
        trip = by_key.get(use.trip_key)
        if trip is None:
            continue
        label = use.vehicle_line.label
        if use.trailer_line_id:
            label = f"{label} + {use.trailer_line.label}"
        trip.vehicles.append(label)


def places_of(project: Project, trips: list[Trip] | None = None) -> list[Place]:
    """The places of a project for its map: warehouse, venues and suppliers, each address once.

    Without trips the venue of the project is still a place, so that crew
    and planners find it on the map.
    """
    if trips is None:
        trips = trips_of(project)
    address = warehouse_address()
    candidates: list[Place] = [_warehouse(address)]
    for trip in trips:
        candidates.extend(trip.places)
    if not trips:
        candidates.append(_venue_of(project, None))
    places: list[Place] = []
    seen: set[str] = set()
    for place in candidates:
        if not place.has_address or address_key(place.address) in seen:
            continue
        seen.add(address_key(place.address))
        places.append(place)
    return places


def trip_document(trip: Trip) -> dict[str, Any]:
    """One trip as the API shows it."""

    def place(item: Place) -> dict[str, Any]:
        return {"label": item.label, "note": item.note, "address": item.address}

    return {
        "kind": trip.kind,
        "title": trip.title,
        "start": trip.start,
        "phase": trip.phase.pk if trip.phase is not None else None,
        "origin": place(trip.origin),
        "stops": [place(stop) for stop in trip.stops],
        "destination": place(trip.destination),
        "route_url": trip.route_url,
        "problems": trip.problems,
        # PRJ-111, in addition: what names the trip, and what was done to it by hand.
        "key": trip.key,
        "note": trip.note,
        "is_changed": trip.is_changed,
        "is_removed": trip.is_removed,
        # LOG-007: the vehicles on the trip, where the caller named them (``name_vehicles``).
        "vehicles": trip.vehicles,
    }
