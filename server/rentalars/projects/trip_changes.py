# SPDX-License-Identifier: GPL-3.0-or-later
"""Trips changed, removed or added by hand (PRJ-111).

Rentalars determines the trips of a project from its phases and subrentals
(PRJ-097, ``projects.trips``). The planner can adjust them on the page
"Zeitplanung" and through the API (API-002, both call these functions):

* **change** a trip: departure, start, stops, destination, title and a note
  for the drivers. Only what differs from the determined trip is stored, so
  that a value left as it was still follows the phases;
* **remove** a trip: it stays removed, however the phases change;
* **reset** it ("zurücksetzen"): the adjustment is deleted, the determined
  trip is back;
* **add** a trip of their own – it has every value of its own and is
  removed for good.

Every function needs a project that is not closed (PRJ-009); who may call
them is decided by the views (edit access to the project). The adjustments
are logged in the history of the project (PRJ-032).
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.maps import MAX_WAYPOINTS
from rentalars.projects.models import Project, TripAdjustment
from rentalars.projects.services import ensure_editable
from rentalars.projects.trips import Trip, TripKind, computed_trips, trips_of


def find_trip(project: Project, key: str) -> Trip:
    """The trip of a project with this key, also a removed one (PRJ-111).

    Raises:
        ValidationError: The project has no such trip (any more).
    """
    for trip in trips_of(project, with_removed=True):
        if trip.key == key:
            return trip
    raise ValidationError(_("This trip does not exist (any more)."))


def _lock(project: Project) -> None:
    """Refuse a closed project and keep two planners from adjusting the same trip at the same moment."""
    ensure_editable(project)
    Project.objects.select_for_update().filter(pk=project.pk).values_list("pk", flat=True).first()


def _clean_stops(stops: Sequence[str] | None) -> list[str] | None:
    """The stops as addresses in one line each, without empty ones; ``None`` stays ``None``."""
    if stops is None:
        return None
    cleaned = [" ".join(str(stop).split()) for stop in stops]
    cleaned = [stop for stop in cleaned if stop]
    if len(cleaned) > MAX_WAYPOINTS:
        raise ValidationError(
            {"stops": _("At most %(count)d stops – Google Maps takes no more.") % {"count": MAX_WAYPOINTS}}
        )
    for stop in cleaned:
        if len(stop) > 250:
            raise ValidationError({"stops": _("An address of a stop is too long (at most 250 characters).")})
    return cleaned


def _one_line(text: str) -> str:
    return " ".join((text or "").split())


@transaction.atomic
def change_trip(
    project: Project,
    key: str,
    *,
    user: Any = None,
    start: datetime.datetime | None = None,
    origin: str = "",
    stops: Sequence[str] | None = None,
    destination: str = "",
    title: str = "",
    note: str = "",
) -> TripAdjustment | None:
    """Change a trip of a project (PRJ-111).

    The values are those the trip shall have. For a trip Rentalars
    determines, what equals the determined value is not stored – it keeps
    following the phases –, and an empty value keeps the determined one.
    A removed trip changed this way is shown again. For a trip of one's own
    every value is its own; start, departure and destination are needed.

    Returns:
        The adjustment, or ``None`` if nothing differs any more from the
        determined trip (then it is reset).

    Raises:
        ValidationError: The project is closed, the trip does not exist, or a value is invalid.
    """
    _lock(project)
    trip = find_trip(project, key)
    stops = _clean_stops(stops)
    origin, destination, title = _one_line(origin), _one_line(destination), _one_line(title)
    note = (note or "").strip()
    if trip.is_own:
        return _save_own(
            trip.adjustment,
            user=user,
            start=start,
            origin=origin,
            stops=stops or [],
            destination=destination,
            title=title,
            note=note,
        )
    determined = next((item for item in computed_trips(project) if item.key == key), None)
    if determined is None:  # pragma: no cover - find_trip found it a moment ago
        raise ValidationError(_("This trip does not exist (any more)."))
    adjustment = project.trip_adjustments.filter(trip_key=key).order_by("pk").first()
    if adjustment is None:
        adjustment = TripAdjustment(project=project, trip_key=key)
    adjustment.is_removed = False
    adjustment.start = start if start is not None and start != determined.start else None
    adjustment.origin = origin if origin and origin != determined.origin.address else ""
    determined_stops = [stop.address for stop in determined.stops]
    adjustment.stops = stops if stops is not None and stops != determined_stops else None
    adjustment.destination = destination if destination and destination != determined.destination.address else ""
    adjustment.title = title if title and title != determined.title else ""
    adjustment.note = note
    differs = any(
        (
            adjustment.start is not None,
            adjustment.origin,
            adjustment.stops is not None,
            adjustment.destination,
            adjustment.title,
            adjustment.note,
        )
    )
    if not differs:
        if adjustment.pk is not None:
            project.trip_adjustments.filter(trip_key=key).delete()
        return None
    adjustment.changed_by = user if getattr(user, "pk", None) else None
    adjustment.changed_at = timezone.now()
    adjustment.full_clean()
    adjustment.save()
    return adjustment


def _save_own(
    adjustment: TripAdjustment,
    *,
    user: Any,
    start: datetime.datetime | None,
    origin: str,
    stops: list[str],
    destination: str,
    title: str,
    note: str,
) -> TripAdjustment:
    """Store a trip of one's own; departure, start and destination are needed."""
    errors: dict[str, str] = {}
    if start is None:
        errors["start"] = _("Enter when the trip starts.")
    if not origin:
        errors["origin"] = _("Enter where the trip starts.")
    if not destination:
        errors["destination"] = _("Enter where the trip goes.")
    if errors:
        raise ValidationError(errors)
    adjustment.trip_key = ""
    adjustment.is_removed = False
    adjustment.start = start
    adjustment.origin = origin
    adjustment.stops = stops
    adjustment.destination = destination
    adjustment.title = title
    adjustment.note = note
    adjustment.changed_by = user if getattr(user, "pk", None) else None
    adjustment.changed_at = timezone.now()
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def add_trip(
    project: Project,
    *,
    user: Any = None,
    start: datetime.datetime | None,
    origin: str,
    destination: str,
    stops: Sequence[str] | None = None,
    title: str = "",
    note: str = "",
) -> TripAdjustment:
    """Add a trip of one's own to a project (PRJ-111), e.g. a second delivery.

    Raises:
        ValidationError: The project is closed, or departure, start or destination is missing.
    """
    _lock(project)
    return _save_own(
        TripAdjustment(project=project),
        user=user,
        start=start,
        origin=_one_line(origin),
        stops=_clean_stops(stops) or [],
        destination=_one_line(destination),
        title=_one_line(title),
        note=(note or "").strip(),
    )


@transaction.atomic
def remove_trip(project: Project, key: str, *, user: Any = None) -> Trip:
    """Remove a trip (PRJ-111): a determined one stays removed until it is reset, one's own is deleted.

    Returns:
        The trip as it was, to name it in the message.

    Raises:
        ValidationError: The project is closed or the trip does not exist.
    """
    _lock(project)
    trip = find_trip(project, key)
    if trip.is_own:
        trip.adjustment.delete()
        return trip
    adjustment = project.trip_adjustments.filter(trip_key=key).order_by("pk").first()
    if adjustment is None:
        adjustment = TripAdjustment(project=project, trip_key=key)
    adjustment.is_removed = True
    adjustment.changed_by = user if getattr(user, "pk", None) else None
    adjustment.changed_at = timezone.now()
    adjustment.save()
    return trip


@transaction.atomic
def reset_trip(project: Project, key: str) -> Trip:
    """Bring back the trip as Rentalars determines it – also a removed one (PRJ-111, "zurücksetzen").

    Returns:
        The trip as Rentalars determines it.

    Raises:
        ValidationError: The project is closed, the trip does not exist, or it is a trip of one's own.
    """
    _lock(project)
    trip = find_trip(project, key)
    if trip.kind == TripKind.OWN:
        raise ValidationError(_("A trip of your own has nothing to reset; remove it instead."))
    project.trip_adjustments.filter(trip_key=key).delete()
    return find_trip(project, key)
