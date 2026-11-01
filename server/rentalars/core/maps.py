# SPDX-License-Identifier: GPL-3.0-or-later
"""Route links and maps at addresses (UIX-033, UIX-034).

UIX-033 – "Route in Google Maps"
    Every address – venue, customer and its further addresses, supplier, the
    company – carries a link into the route planning of Google Maps
    (:func:`route_url`). It is a plain link opening in a new tab, without
    referrer: the address leaves Rentalars only with the click. Every
    route starts where the viewer is – the link names no start, so Google
    Maps takes the current location; a trip with stops keeps them as
    waypoints (PRJ-097).

UIX-034 – a zoomable map (decided, see ``docs/dev/decisions.md``)
    Maps are those of OpenStreetMap. A page shows the button "Karte
    anzeigen"; only the click sends anything outside (NFA-050): the server
    asks the geocoder (Nominatim, ``core.geocoding``) where the addresses
    lie – once per address, the answer is kept in ``AddressPosition`` – and
    the browser loads the map pictures (tiles) – with the origin of
    the installation as referrer (``referrerPolicy`` of the tile layer in
    ``static/js/app.js``), as the tile usage policy of OpenStreetMap asks;
    the pages themselves send ``Referrer-Policy: same-origin``, which would
    send none. The setting "Karten sofort
    laden" makes every map load right away. A position that was not found or
    lies wrong is set by hand on the map; it then holds for every record
    with that address. Tile server, geocoder and attribution are settings of
    the configuration file (``[maps]``), so an own server can be used; empty
    ``tile_url`` switches maps off and leaves the route links.

A map belongs to a *target*: a venue, a customer (with its further
addresses), a supplier, the company (with the warehouse) or a project (the
places of its trips, PRJ-097). :func:`map_for` decides who may see it and
who may correct its positions, and collects its :class:`Place` objects.
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.templatetags.static import static
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, request_rights
from rentalars.core.audit import record_event
from rentalars.core.models import AddressPosition, CompanyProfile, PositionSource, SystemSettings

#: The route planning of Google Maps (Maps URLs, ``api=1``).
GOOGLE_DIRECTIONS = "https://www.google.com/maps/dir/"

#: Google Maps takes at most nine stops between start and destination.
MAX_WAYPOINTS = 9

#: How many addresses one opening of a map asks the geocoder about at most (one per second).
LOOKUPS_PER_REQUEST = 5

#: Seconds one opening of a map spends on the geocoder at most; the rest is asked at the next opening.
LOOKUP_BUDGET_SECONDS = 15.0

#: The kinds of records a map can belong to.
TARGETS = ("venue", "customer", "supplier", "company", "project")

#: UIX-034: the referrer policy of the map pictures. The pages send ``Referrer-Policy: same-origin``;
#: the tile usage policy of OpenStreetMap asks for a Referer, so the tiles carry the origin of the installation
#: (never the path of the page). The tiles load only after "Karte anzeigen" (or with "Karten sofort laden").
TILE_REFERRER_POLICY = "strict-origin-when-cross-origin"

#: Where an empty map is centred: Germany.
DEFAULT_CENTRE = (51.16, 10.45)
DEFAULT_ZOOM = 6


# --- Addresses and route links (UIX-033) --------------------------------------------------------------


def one_line(*parts: str) -> str:
    """Join address parts into one line without empty parts: "Hauptstraße 1, 12345 Musterstadt"."""
    cleaned = (" ".join((part or "").split()) for part in parts)
    return ", ".join(part for part in cleaned if part)


def address_key(address: str) -> str:
    """The key an address is kept under: the same for every spelling that differs only in spaces and case."""
    normalised = " ".join(address.split()).casefold()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def route_url(destination: str, *, waypoints: Sequence[str] = ()) -> str:
    """The link into the route planning of Google Maps, from where the viewer is (UIX-033, PRJ-097).

    UIX-033: the link names no start (``origin``) – Google Maps then
    starts at the current location of the device.

    Args:
        destination: Where to go, as an address in one line.
        waypoints: Stops on the way, in order; more than nine are left out.

    Returns:
        ``https://www.google.com/maps/dir/?api=1&destination=…&waypoints=…``,
        or ``""`` without a destination.
    """
    destination = " ".join(destination.split())
    if not destination:
        return ""
    params = {"api": "1", "destination": destination}
    stops = [" ".join(stop.split()) for stop in waypoints if stop and stop.strip()][:MAX_WAYPOINTS]
    if stops:
        params["waypoints"] = "|".join(stops)
    return GOOGLE_DIRECTIONS + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def warehouse_address() -> str:
    """Where trips start and end (PRJ-097): the warehouse of the company data, else the company's address."""
    return CompanyProfile.load().warehouse_one_line


def venue_address(venue: Any) -> str:
    """The address of a venue for routes and maps: its street and city, else its name."""
    if venue.street or venue.city:
        return venue.address_one_line
    return venue.name


# --- Places on a map ------------------------------------------------------------------------------------


@dataclass
class Place:
    """One address on a map or in a trip, with its label and – once known – its position."""

    label: str
    address: str
    #: What the place is, e.g. "Lager", "Lieferadresse"; shown next to the label.
    note: str = ""
    position: AddressPosition | None = None

    @property
    def key(self) -> str:
        """The key of its address (``AddressPosition.key``)."""
        return address_key(self.address)

    @property
    def has_address(self) -> bool:
        """Whether there is anything to look up or to route to."""
        return bool(self.address.strip())

    @property
    def route_url(self) -> str:
        """The link "Route in Google Maps" to this place, from where the viewer is (UIX-033)."""
        return route_url(self.address)

    @property
    def is_located(self) -> bool:
        """Whether the place has a position on the map."""
        return self.position is not None and self.position.is_known

    @property
    def source(self) -> str:
        """``found``, ``manual``, ``not_found`` or ``unknown`` (not asked yet)."""
        return self.position.source if self.position is not None else "unknown"


@dataclass
class MapPage:
    """A map of one target: its places, who may correct them, what went wrong while locating them."""

    target: str
    pk: int
    title: str
    #: The record the map belongs to; a position set by hand is logged there.
    record: models.Model
    places: list[Place]
    can_correct: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def located(self) -> list[Place]:
        """The places with a position, in their order."""
        return [place for place in self.places if place.is_located]

    def place(self, key: str) -> Place:
        """The place with an address key; refuses keys that are not on this map."""
        for place in self.places:
            if place.has_address and place.key == key:
                return place
        raise ValidationError(_("This address is not on the map."))


def maps_enabled() -> bool:
    """Whether maps are shown at all (``[maps] tile_url``); route links are always there."""
    return settings.RENTALARS_MAPS.enabled


def load_at_once() -> bool:
    """Whether maps load without a click (setting "Karten sofort laden")."""
    return SystemSettings.load().maps_load_at_once


def tile_origin() -> str:
    """The origin of the tile server, for the image sources of the content security policy.

    A server name with ``{s}`` (``https://{s}.tile.example``) becomes a
    wildcard for its sub-domains.
    """
    parsed = urllib.parse.urlsplit(settings.RENTALARS_MAPS.tile_url.replace("{s}", "subdomain"))
    if not parsed.scheme or not parsed.netloc:
        return ""
    host = parsed.netloc.replace("subdomain.", "*.")
    return f"{parsed.scheme}://{host}"


def _company_places() -> list[Place]:
    company = CompanyProfile.load()
    places = [Place(label=company.name or _("Company"), address=company.address_one_line, note=_("Company"))]
    warehouse = " ".join(company.warehouse_address.split())
    if warehouse and address_key(warehouse) != address_key(company.address_one_line):
        places.append(Place(label=_("Warehouse"), address=warehouse, note=_("Warehouse")))
    return places


def map_for(request: Any, target: str, pk: int) -> MapPage:
    """The map of a target for the user of a request, without positions yet.

    Raises:
        Http404: No such target or record – or the user may not see it.
        PermissionDenied: The user may not see this map.
    """
    from rentalars.customers.models import Customer, Venue
    from rentalars.masterdata.models import Supplier

    rights = request_rights(request)
    if target == "venue":
        if not rights.can_read(Module.CUSTOMERS):
            raise PermissionDenied
        venue = get_object_or_404(Venue, pk=pk)
        return MapPage(
            target=target,
            pk=venue.pk,
            title=venue.name,
            record=venue,
            places=[Place(label=venue.name, address=venue_address(venue), note=_("Venue"))],
            can_correct=rights.can_write(Module.CUSTOMERS),
        )
    if target == "customer":
        if not rights.can_read(Module.CUSTOMERS):
            raise PermissionDenied
        customer = get_object_or_404(Customer, pk=pk)
        places = [
            Place(
                label=customer.name,
                address=one_line(customer.street, f"{customer.postal_code} {customer.city}", customer.country),
                note=_("Billing address"),
            )
        ]
        for address in customer.addresses.all():
            places.append(
                Place(
                    label=address.label or capfirst(str(address.get_kind_display())),
                    address=one_line(address.street, f"{address.postal_code} {address.city}", address.country),
                    note=capfirst(str(address.get_kind_display())),
                )
            )
        return MapPage(
            target=target,
            pk=customer.pk,
            title=customer.name,
            record=customer,
            places=[place for place in places if place.has_address],
            can_correct=rights.can_write(Module.CUSTOMERS) and not customer.is_anonymised,
        )
    if target == "supplier":
        from rentalars.projects.subrentals import may_create_supplier, may_see_suppliers

        if not may_see_suppliers(rights):
            raise PermissionDenied
        supplier = get_object_or_404(Supplier, pk=pk)
        places = [Place(label=supplier.name, address=supplier.address_one_line, note=_("Supplier"))]
        return MapPage(
            target=target,
            pk=supplier.pk,
            title=supplier.name,
            record=supplier,
            places=[place for place in places if place.has_address],
            can_correct=may_create_supplier(rights),
        )
    if target == "company":
        if not rights.can_read(Module.ADMINISTRATION):
            raise PermissionDenied
        company = CompanyProfile.load()
        return MapPage(
            target=target,
            pk=1,
            title=company.name or _("Company"),
            record=company,
            places=[place for place in _company_places() if place.has_address],
            can_correct=rights.can_write(Module.ADMINISTRATION),
        )
    if target == "project":
        from rentalars.projects.access import ProjectAccess, project_for
        from rentalars.projects.models import Project
        from rentalars.projects.trips import places_of

        project = project_for(
            request, pk, ProjectAccess.DEPLOYMENT, queryset=Project.objects.select_related("venue_site")
        )
        return MapPage(
            target=target,
            pk=project.pk,
            title=f"{project.number} {project.name}",
            record=project,
            places=places_of(project),
            can_correct=project.access >= ProjectAccess.EDIT,
        )
    raise Http404


# --- Positions (UIX-034) --------------------------------------------------------------------------------


def attach_positions(places: Iterable[Place]) -> None:
    """Give every place the position kept for its address, in one query."""
    places = [place for place in places if place.has_address]
    known = {row.key: row for row in AddressPosition.objects.filter(key__in={place.key for place in places})}
    for place in places:
        place.position = known.get(place.key)


def locate(page: MapPage, *, limit: int = LOOKUPS_PER_REQUEST) -> None:
    """Find the positions of the places of a map: kept ones from the database, missing ones from the geocoder.

    Addresses the geocoder was asked about before are not asked again, also
    when it did not find them. Should it not answer, nothing is kept and the
    problem is noted on the page: the next opening of the map asks again.
    """
    from rentalars.core import geocoding

    attach_positions(page.places)
    missing = [place for place in page.places if place.has_address and place.position is None]
    if not missing:
        return
    if not settings.RENTALARS_MAPS.geocoder_url:
        page.problems.append(_("No map search is configured: set the position by hand."))
        return
    asked: dict[str, AddressPosition | None] = {}
    deadline = time.monotonic() + LOOKUP_BUDGET_SECONDS
    for place in missing:
        if place.key in asked:
            place.position = asked[place.key]
            continue
        if len(asked) >= limit or time.monotonic() > deadline:
            page.problems.append(_("Not all addresses could be looked up yet. Open the map again in a moment."))
            break
        try:
            found = geocoding.look_up(place.address)
        except geocoding.GeocoderError as error:
            page.problems.append(str(error))
            break
        position, _created = AddressPosition.objects.get_or_create(
            key=place.key,
            defaults={
                "address": place.address[:500],
                "latitude": found.latitude if found else None,
                "longitude": found.longitude if found else None,
                "source": PositionSource.FOUND if found else PositionSource.NOT_FOUND,
                "found_name": found.name if found else "",
            },
        )
        asked[place.key] = position
        place.position = position


def _coordinate(value: Any, limit: int, name: str) -> Decimal:
    try:
        number = Decimal(str(value).strip().replace(",", ".")).quantize(Decimal("0.000001"))
    except (ArithmeticError, ValueError) as error:
        raise ValidationError({name: _("Enter a number.")}) from error
    if not -limit <= number <= limit:
        raise ValidationError({name: _("Enter a value between %(low)s and %(high)s.") % {"low": -limit, "high": limit}})
    return number


def set_position(page: MapPage, key: str, latitude: Any, longitude: Any, *, user: Any) -> AddressPosition:
    """Set the position of an address of a map by hand (UIX-034); it holds for every record with that address.

    Raises:
        PermissionDenied: The user may not correct this map.
        ValidationError: The address is not on the map, or a coordinate is no number within its range.
    """
    if not page.can_correct:
        raise PermissionDenied
    place = page.place(key)
    lat = _coordinate(latitude, 90, "latitude")
    lon = _coordinate(longitude, 180, "longitude")
    position, _created = AddressPosition.objects.update_or_create(
        key=place.key,
        defaults={
            "address": place.address[:500],
            "latitude": lat,
            "longitude": lon,
            "source": PositionSource.MANUAL,
            "found_name": "",
            "updated_at": timezone.now(),
            "updated_by": user if getattr(user, "is_authenticated", False) else None,
        },
    )
    record_event(
        page.record,
        "map.position_set",
        {"address": place.address, "latitude": str(lat), "longitude": str(lon)},
    )
    place.position = position
    return position


def forget_position(page: MapPage, key: str, *, user: Any) -> None:
    """Forget the position of an address: the next opening of a map asks the geocoder again.

    Raises:
        PermissionDenied: The user may not correct this map.
        ValidationError: The address is not on the map.
    """
    if not page.can_correct:
        raise PermissionDenied
    place = page.place(key)
    deleted, _counts = AddressPosition.objects.filter(key=place.key).delete()
    if deleted:
        record_event(page.record, "map.position_forgotten", {"address": place.address})
    place.position = None


def forget_addresses(addresses: Iterable[str]) -> int:
    """Remove the kept positions of addresses, e.g. of a customer that is anonymised (KND-010)."""
    keys = {address_key(address) for address in addresses if address and address.strip()}
    if not keys:
        return 0
    deleted, _counts = AddressPosition.objects.filter(key__in=keys).delete()
    return deleted


def addresses_in_use() -> set[str]:
    """The keys of every address Rentalars knows: of records and of the places of projects."""
    from rentalars.customers.models import Customer, CustomerAddress, Venue
    from rentalars.masterdata.models import Supplier
    from rentalars.projects.models import Project, ProjectPhase

    keys = {place.key for place in _company_places() if place.has_address}
    keys.add(address_key(warehouse_address()))
    for venue in Venue.objects.only("name", "street", "postal_code", "city", "country").iterator():
        keys.add(address_key(venue_address(venue)))
    for parts in Customer.objects.values_list("street", "postal_code", "city", "country").iterator():
        keys.add(address_key(one_line(parts[0], f"{parts[1]} {parts[2]}", parts[3])))
    for parts in CustomerAddress.objects.values_list("street", "postal_code", "city", "country").iterator():
        keys.add(address_key(one_line(parts[0], f"{parts[1]} {parts[2]}", parts[3])))
    for supplier in Supplier.objects.only("street", "postal_code", "city", "country").iterator():
        keys.add(address_key(supplier.address_one_line))
    for text in Project.objects.exclude(venue="").values_list("venue", flat=True).iterator():
        keys.add(address_key(text))
    for text in ProjectPhase.objects.exclude(location="").values_list("location", flat=True).iterator():
        keys.add(address_key(text))
    return keys


def delete_unused_positions() -> int:
    """Remove the positions of addresses no record has any more (daily maintenance, UIX-034)."""
    used = addresses_in_use()
    unused = [pk for pk, key in AddressPosition.objects.values_list("pk", "key").iterator() if key not in used]
    deleted = 0
    for start in range(0, len(unused), 500):
        count, _counts = AddressPosition.objects.filter(pk__in=unused[start : start + 500]).delete()
        deleted += count
    return deleted


# --- What the page and the API get --------------------------------------------------------------------


def map_data(page: MapPage) -> dict[str, Any]:
    """What the script of the page needs to draw the map (``data-map``)."""
    config = settings.RENTALARS_MAPS
    return {
        "tiles": config.tile_url,
        "maxZoom": config.max_zoom,
        "referrerPolicy": TILE_REFERRER_POLICY,
        "attribution": config.attribution or _("© OpenStreetMap contributors"),
        "attributionUrl": config.attribution_url,
        "centre": list(DEFAULT_CENTRE),
        "zoom": DEFAULT_ZOOM,
        "leaflet": {"js": static("vendor/leaflet/leaflet.js"), "css": static("vendor/leaflet/leaflet.css")},
        "texts": {"zoomIn": _("Zoom in"), "zoomOut": _("Zoom out")},
        "places": [
            {
                "key": place.key,
                "number": number,
                "label": place.label,
                "address": place.address,
                "lat": float(place.position.latitude) if place.is_located else None,
                "lon": float(place.position.longitude) if place.is_located else None,
            }
            for number, place in enumerate(page.places, start=1)
            if place.has_address
        ],
    }


def place_document(place: Place) -> dict[str, Any]:
    """One place as the API shows it."""
    located = place.is_located
    return {
        "label": place.label,
        "note": place.note,
        "address": place.address,
        "key": place.key if place.has_address else None,
        "route_url": place.route_url,
        "position": place.source,
        "latitude": place.position.latitude if located else None,
        "longitude": place.position.longitude if located else None,
    }
