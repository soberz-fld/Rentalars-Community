# SPDX-License-Identifier: GPL-3.0-or-later
"""Logistics: the vehicles and trailers of a project, their trips, prices and costs (LOG-001 ff.).

Below the personnel of the planning stands the block "Logistik". Vehicles
and trailers are not material lines: they are booked as *vehicle bookings*
(``VehicleLine``) – a vehicle product with its rates (LOG-005) and, once
chosen, the vehicle itself, an item of the fleet (LOG-002) – and put on the
trips of the project (``TripVehicle``, LOG-007): which motor vehicle drives
which trip, which trailer it pulls, how many kilometres are planned and
driven. Browser views and API views both call these functions (API-002).
Every function that changes a project first checks that it is not closed
(PRJ-009).

What a vehicle costs the customer (LOG-005, LOG-006, LOG-009)
-------------------------------------------------------------
=======================  ================================================
motor vehicle            per trip: kilometres × (price per km + trailer
                         surcharge per km, if it pulls a trailer on that
                         trip) – or the trip's flat rate
trailer per kilometre    per trip: kilometres × its price per km; on a
                         trip with a flat rate it is part of that rate
trailer per day          price per day × the factor of the rental scale for
                         its days, as material (PRD-033); without a scale
                         every day in full. The days as for material: typed
                         in on the booking, else those of its own period,
                         else the project's; or, switched on the booking,
                         only the days on which the trailer drives
=======================  ================================================

The kilometres of a trip are chosen per trip: the driven ones – while they
are missing the planned ones stand in, marked as an estimate –, the planned
ones, or a flat rate. The discount of a booking lowers its amount, at most
to the maximum discount of its product (PRD-041). The block adds up to the
subtotal "Logistik", part of the net total, the taxes and "the whole
project" of a percentage surcharge, like the personnel.

What it costs the company (LOG-010)
-----------------------------------
The kilometres of every trip (driven, else planned) × the internal cost per
kilometre; a trailer per day: its days × the internal cost per day (no
scale). A vehicle from a supplier costs what the supplier charges for the
booking instead. Visible only with the right to see purchase prices.

What is wrong with the plan (LOG-004, LOG-008, LOG-012 to LOG-014)
-----------------------------------------------------------------
:func:`logistics_warnings` names, per booking: the same vehicle booked
elsewhere at the same time (or twice in this project), a vehicle that is
not fit for use or blocked, an inspection due before the booking ends,
more people with the vehicle than it has seats, a driver without the
driving licence class, a trailer at a vehicle that may not tow it – and
trips that are gone. Nothing is prevented: the planner decides.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.i18n import format_date, local_pattern
from rentalars.core.money import ZERO, money, percentage_of
from rentalars.masterdata.models import ScaleTable
from rentalars.products.models import Product, ProductKind, TrailerBilling
from rentalars.projects.discounts import limited_percent
from rentalars.projects.models import (
    CrewLine,
    Project,
    ProjectPhase,
    ProjectStatus,
    TripBilling,
    TripVehicle,
    VehicleBilling,
    VehicleLine,
    started_days,
)
from rentalars.projects.services import ensure_editable, ensure_plannable, moved, wall_clock_shift

#: AUT-019: fields of a booking that need the price right – they decide only the price.
PRICE_FIELDS = frozenset(
    {
        "price_per_km",
        "trailer_surcharge_per_km",
        "price_per_day",
        "discount_percent",
        "tax_rate",
        "billing",
        "rental_days",
        "only_trip_days",
    }
)

#: AUT-019, LOG-010: fields that need the right to see purchase prices.
COST_FIELDS = frozenset({"cost_per_km", "cost_per_day", "subrental_cost"})

#: Fields a caller may change through :func:`update_vehicle_line`.
EDITABLE_FIELDS = frozenset({"product", "item", "title", "phase", "start", "end", "note", "supplier"}) | (
    PRICE_FIELDS | COST_FIELDS
)

#: Fields of a vehicle on a trip that need the price right: which kilometres are charged, and a flat rate.
TRIP_PRICE_FIELDS = frozenset({"billing", "flat_price"})

#: Fields a caller may change through :func:`update_trip_vehicle`.
TRIP_FIELDS = (
    frozenset({"trip_key", "vehicle_line", "trailer_line", "planned_km", "driven_km", "note"}) | TRIP_PRICE_FIELDS
)


def _check_rights(changes: Iterable[str], rights: Rights, price_fields: frozenset[str] = PRICE_FIELDS) -> None:
    """AUT-019: prices and costs can only be set by those who may see them."""
    touched = set(changes)
    if touched & price_fields and not rights.has(SpecialRight.PRICES):
        raise ValidationError(_("You do not have the right to set prices or discounts."))
    if touched & COST_FIELDS and not rights.has(SpecialRight.PURCHASE_PRICES):
        raise ValidationError(_("You do not have the right to see purchase prices and internal costs."))


# --- Bookings (LOG-001, LOG-002, LOG-005) -----------------------------------------------------------------------


def defaults_from_product(product: Product) -> dict[str, Any]:
    """The values a new booking copies from its vehicle product (LOG-005, LOG-010).

    The rates become the booking's own (PRJ-015): a change of the product
    later leaves the booking as it is. A trailer is billed as its product
    presets; its day price takes the rental scale of the product, fixed in
    its current version like a material line's (PRD-037).
    """
    scale = product.effective_rental_scale() if product.is_trailer else None
    return {
        "title": product.name,
        "billing": VehicleBilling.DAY
        if product.is_trailer and product.trailer_billing == TrailerBilling.DAY
        else VehicleBilling.KM,
        "price_per_km": product.price_per_km or ZERO,
        "trailer_surcharge_per_km": (product.trailer_surcharge_per_km or ZERO) if product.is_car else ZERO,
        "price_per_day": (product.price or ZERO) if product.is_trailer else ZERO,
        "scale_version": scale.current_version if scale is not None else None,
        "tax_rate": product.tax_rate,
        "cost_per_km": product.cost_per_km,
        "cost_per_day": product.cost_per_day if product.is_trailer else None,
    }


def _check_product(product: Product) -> None:
    if product.kind != ProductKind.VEHICLE:
        raise ValidationError({"product": _("Choose a vehicle or a trailer of the fleet.")})
    if not product.is_active:
        raise ValidationError({"product": _("This vehicle product is deactivated.")})


def _check_item(item: Any, product: Product) -> None:
    """LOG-002: a vehicle of the chosen product that is not archived (retired, sold, lost)."""
    if item.product != product:
        raise ValidationError({"item": _("Choose a vehicle of the product %(product)s.") % {"product": product.name}})
    if item.is_archived:
        raise ValidationError(
            {
                "item": _("%(vehicle)s is %(status)s.")
                % {"vehicle": item.display_id, "status": item.get_status_display()}
            }
        )


@transaction.atomic
def add_vehicle_line(
    project: Project,
    *,
    rights: Rights,
    product: Product,
    item: Any = None,
    start: datetime.datetime | None = None,
    end: datetime.datetime | None = None,
    phase: ProjectPhase | None = None,
    **overrides: Any,
) -> VehicleLine:
    """Book a vehicle or trailer for a project (LOG-001).

    Args:
        project: The project.
        rights: The rights of the caller.
        product: The vehicle product with the rates.
        item: The vehicle itself, an item of the product; ``None`` books it
            open – chosen later – or, with ``supplier``, from a supplier.
        start: Begin of the booking; default is the phase's, or the project's.
        end: End of the booking; default as ``start``.
        phase: The phase the booking belongs to.
        **overrides: ``title``, ``note``, ``supplier`` and – with the matching
            rights – rates, billing, days, discount and costs.

    Raises:
        ValidationError: The project is closed or a service case, the product
            is no vehicle, the vehicle is of another product or archived, or
            a value is invalid.
    """
    ensure_editable(project)
    ensure_plannable(project)
    _check_rights(overrides.keys(), rights)
    unknown = set(overrides) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be set: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    _check_product(product)
    if item is not None:
        _check_item(item, product)
    values = defaults_from_product(product)
    values.update(overrides)
    default_start, default_end = (phase.start, phase.end) if phase is not None else (project.start, project.end)
    last = project.vehicle_lines.aggregate(last=Max("position"))["last"] or 0
    line = VehicleLine(
        project=project,
        product=product,
        item=item,
        phase=phase,
        start=start or default_start,
        end=end or default_end,
        position=last + 1,
        **values,
    )
    line.full_clean()
    line.save()
    return line


@transaction.atomic
def update_vehicle_line(line: VehicleLine, *, rights: Rights, **changes: Any) -> VehicleLine:
    """Change a booking (LOG-001, LOG-005).

    * Another **product** brings its rates, unless they are given along;
      a vehicle of the old product no longer fits and is taken away.
    * Another **phase** given without a period brings the phase's period.
    * A booking that becomes a **motor vehicle** is billed per kilometre; a
      trailer no longer on any trip stays where it is.

    Raises:
        ValidationError: The project is closed, a field is not editable, a
            right is missing, or a value is invalid.
    """
    ensure_editable(line.project)
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    _check_rights(changes.keys(), rights)
    product = changes.get("product", line.product)
    if product.pk != line.product_id:
        _check_product(product)
        in_use = line.trip_uses.exists() or line.trailer_uses.exists() or line.crew_lines.exists()
        if in_use and product.vehicle_type != line.product.vehicle_type:
            raise ValidationError(
                {"product": _("The vehicle drives trips of the project. Choose a product of the same type.")}
            )
        for name, value in defaults_from_product(product).items():
            if name not in changes:
                setattr(line, name, value)
        if "item" not in changes and line.item_id is not None and line.item.product != product:
            line.item = None
    item = changes.get("item", line.item)
    if item is not None and ("item" in changes or "product" in changes):
        _check_item(item, product)
    phase = changes.get("phase", line.phase)
    if phase is not None and phase.pk != line.phase_id and "start" not in changes and "end" not in changes:
        changes = {**changes, "start": phase.start, "end": phase.end}
    for name, value in changes.items():
        setattr(line, name, value)
    if line.product.is_car:
        line.billing = VehicleBilling.KM
    line.full_clean()
    line.save()
    return line


def delete_vehicle_line(line: VehicleLine) -> None:
    """Remove a booking with its trips; crew lines and packing lists that named it keep going without it.

    Raises:
        ValidationError: The project is closed.
    """
    ensure_editable(line.project)
    line.crew_lines.update(is_driver=False)  # LOG-008: nobody drives a vehicle that is gone
    line.delete()


def move_with_phase(phase: ProjectPhase, old_start: datetime.datetime, old_end: datetime.datetime) -> list[VehicleLine]:
    """Move the bookings of a phase along after the phase's period changed – as the crew moves (PRJ-080, LOG-019).

    A booking with exactly the old period of the phase gets the new one;
    any other is shifted by the change of the phase's start and keeps its
    length (see ``crew.move_with_phase``).

    Returns:
        The bookings that moved.
    """
    ensure_editable(phase.project)
    shift = wall_clock_shift(phase.start, old_start)
    changed: list[VehicleLine] = []
    for line in phase.vehicle_lines.select_related("product", "project", "item").order_by("start", "id"):
        line.phase = phase
        if (line.start, line.end) == (old_start, old_end):
            start, end = phase.start, phase.end
        else:
            start, end = moved(line.start, shift), moved(line.end, shift)
            if end <= start:
                end = start + (line.end - line.start)
        if (start, end) == (line.start, line.end):
            continue
        line.start, line.end = start, end
        line.full_clean()
        line.save()
        changed.append(line)
    return changed


def follow_project_period(project: Project, old_start: datetime.datetime, old_end: datetime.datetime) -> None:
    """LOG-019: bookings with exactly the old period of the project take its new one – as material lines do (PRJ-011)."""
    for line in project.vehicle_lines.filter(start=old_start, end=old_end):
        line.start, line.end = project.start, project.end
        line.save()


# --- Vehicles on trips (LOG-006, LOG-007) ------------------------------------------------------------------------


def _check_trip(project: Project, trip_key: str) -> None:
    """The trip must be one of the project – a determined one, or one added by hand (PRJ-097, PRJ-111)."""
    from rentalars.projects.trips import trips_of

    if not any(trip.key == trip_key for trip in trips_of(project)):
        raise ValidationError({"trip_key": _("The project has no such trip.")})


def _lock(project: Project) -> None:
    """Hold the project's row until the transaction ends.

    The rules of a trip – a vehicle once, a trailer behind one vehicle – are
    checked in Python, so two requests at the same time must not both pass.
    """
    Project.objects.select_for_update().filter(pk=project.pk).values_list("pk", flat=True).first()


@transaction.atomic
def add_trip_vehicle(
    project: Project,
    *,
    rights: Rights,
    trip_key: str,
    vehicle_line: VehicleLine,
    trailer_line: VehicleLine | None = None,
    **values: Any,
) -> TripVehicle:
    """Put a motor vehicle of the project on one of its trips, with or without a trailer (LOG-007).

    Args:
        project: The project.
        rights: The rights of the caller; ``billing`` and ``flat_price`` need the price right.
        trip_key: The trip, as ``projects.trips`` names it (``to_venue-12``, ``own-3`` …).
        vehicle_line: The booking of the motor vehicle.
        trailer_line: The booking of the trailer it pulls, if any.
        **values: ``planned_km``, ``driven_km``, ``note``, ``billing``, ``flat_price``.

    Raises:
        ValidationError: The project is closed, the trip does not exist, the
            vehicle drives the trip already, the trailer is pulled by another
            vehicle there, or a value is invalid.
    """
    ensure_editable(project)
    _lock(project)
    unknown = set(values) - TRIP_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be set: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    _check_rights(values.keys(), rights, TRIP_PRICE_FIELDS)
    _check_trip(project, trip_key)
    if project.trip_vehicles.filter(trip_key=trip_key, vehicle_line=vehicle_line).exists():
        raise ValidationError({"vehicle_line": _("This vehicle drives this trip already.")})
    use = TripVehicle(
        project=project, trip_key=trip_key, vehicle_line=vehicle_line, trailer_line=trailer_line, **values
    )
    use.full_clean()
    use.save()
    return use


@transaction.atomic
def update_trip_vehicle(use: TripVehicle, *, rights: Rights, **changes: Any) -> TripVehicle:
    """Change a vehicle on a trip: trailer, kilometres, what is charged – or move it to another trip (LOG-007).

    Raises:
        ValidationError: The project is closed, a field is not editable, a
            right is missing, the trip does not exist, or a value is invalid.
    """
    ensure_editable(use.project)
    _lock(use.project)
    unknown = set(changes) - TRIP_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    _check_rights(changes.keys(), rights, TRIP_PRICE_FIELDS)
    if changes.get("trip_key", use.trip_key) != use.trip_key:
        _check_trip(use.project, changes["trip_key"])
    for name, value in changes.items():
        setattr(use, name, value)
    if use.billing != TripBilling.FLAT:
        use.flat_price = None
    use.full_clean()
    use.save()
    return use


def delete_trip_vehicle(use: TripVehicle) -> None:
    """Take a vehicle off a trip.

    Raises:
        ValidationError: The project is closed.
    """
    ensure_editable(use.project)
    use.delete()


# --- Prices and costs (LOG-005, LOG-006, LOG-009, LOG-010) -------------------------------------------------------


class KmSource:
    """Which kilometres a trip is charged with; the values appear in the API."""

    DRIVEN = "driven"
    PLANNED = "planned"
    #: The driven kilometres are charged but not known yet: the planned ones stand in (LOG-007).
    ESTIMATE = "estimate"
    FLAT = "flat"
    #: A trailer billed per day: the trip is listed, the days are charged.
    DAYS = "days"


@dataclass
class TripCharge:
    """What one trip adds to a booking: kilometres, rate and amount (LOG-009)."""

    use: TripVehicle
    #: The kilometres charged; ``None`` for a flat rate or while none are known.
    km: Decimal | None
    #: One of :class:`KmSource`.
    km_source: str
    #: The price per kilometre, for a motor vehicle with a trailer the trailer surcharge included.
    rate: Decimal = ZERO
    #: The trailer surcharge per kilometre in ``rate`` (LOG-006); 0 without a trailer.
    surcharge_rate: Decimal = ZERO
    #: The amount before the booking's discount; for a flat rate the flat rate.
    amount: Decimal = ZERO
    #: For a trailer billed per kilometre on a trip with a flat rate: its part is in the rate of the trip.
    in_flat_rate: bool = False
    #: The kilometres of the internal costs: driven, else planned (LOG-010).
    cost_km: Decimal | None = None
    #: The trip itself, filled in by :func:`describe_trips` where it is shown; ``None`` if it is gone.
    trip: Any = None

    @property
    def is_estimate(self) -> bool:
        """Whether the planned kilometres stand in for the driven ones (LOG-007)."""
        return self.km_source == KmSource.ESTIMATE

    @property
    def surcharge_amount(self) -> Decimal:
        """LOG-006: what the trailer surcharge adds on this trip."""
        if self.km is None or not self.surcharge_rate:
            return ZERO
        return money(self.km * self.surcharge_rate)


class DaysSource:
    """Where the days of a trailer billed per day come from (LOG-005)."""

    LINE = "line"  # typed in on the booking
    PERIOD = "period"  # the booking's own period, every started 24 hours
    PROJECT = "project"  # the project's rental days
    TRIPS = "trips"  # only the days with trips


@dataclass
class VehiclePrice:
    """What one booking costs the customer and the company (LOG-005, LOG-009, LOG-010)."""

    line: VehicleLine
    #: The trips of the booking with their kilometres and amounts, in the order of the trips.
    charges: list[TripCharge] = field(default_factory=list)
    #: Per day: the days and where they come from, and the factor of the rental scale.
    days: int | None = None
    days_source: str = ""
    scale_factor: Decimal | None = None
    #: The amount before the discount, the discount and the amount.
    base_amount: Decimal = ZERO
    discount_percent: Decimal = ZERO
    max_discount_percent: Decimal | None = None
    discount_is_capped: bool = False
    discount_amount: Decimal = ZERO
    amount: Decimal = ZERO
    #: LOG-010: the internal cost; ``cost_is_known`` is false while a rate is missing.
    cost: Decimal = ZERO
    cost_is_known: bool = True
    #: True while driven kilometres are charged that are not known yet.
    is_estimate: bool = False

    @property
    def km_total(self) -> Decimal:
        """The kilometres charged over all trips (a flat rate counts none)."""
        return sum((charge.km for charge in self.charges if charge.km is not None), ZERO)

    @property
    def surcharge_total(self) -> Decimal:
        """LOG-006: what the trailer surcharges add, before the discount."""
        return sum((charge.surcharge_amount for charge in self.charges if not charge.in_flat_rate), ZERO)

    @property
    def unit_kind(self) -> str:
        """What the customer is charged by, for documents and exports (LOG-011).

        ``"day"`` for a trailer per day, ``"km"`` when every charged trip goes
        by kilometres, ``"flat"`` when every one has a flat rate, ``"mixed"``
        for both – one flat position then, the trips named in its details.
        """
        if self.days is not None:
            return "day"
        flat = {charge.km_source == KmSource.FLAT for charge in self.charges if not charge.in_flat_rate}
        if flat == {True}:
            return "flat"
        return "mixed" if True in flat else "km"

    @property
    def quantity(self) -> Decimal:
        """The charged quantity: days, kilometres, the number of flat-rate trips, or 1 for mixed trips."""
        kind = self.unit_kind
        if kind == "day":
            return Decimal(self.days or 0)
        if kind == "flat":
            return Decimal(sum(1 for charge in self.charges if charge.km_source == KmSource.FLAT))
        if kind == "mixed":
            return Decimal("1")
        return self.km_total

    @property
    def unit_price(self) -> Decimal | None:
        """The price per unit of :attr:`quantity`, before the discount – for documents and exports.

        ``None`` when there is no single one: 100 km at 1.00 €
        with a trailer and 7 km at 0.80 € are 107 km for 105.60 €, not "107 km
        at 0.99 €"; the details name the rate of every trip, and the electronic
        invoice states the price of the whole quantity.
        """
        quantity = self.quantity
        if not quantity:
            return self.base_amount
        price = money(self.base_amount / quantity)
        return price if money(price * quantity) == self.base_amount else None


@dataclass
class Logistics:
    """The bookings of a project with their trips, loaded once (``load_logistics``)."""

    lines: list[VehicleLine] = field(default_factory=list)
    uses: list[TripVehicle] = field(default_factory=list)
    #: The keys of the trips the project has now (``trips.trip_keys_of``): a vehicle on a trip that is gone is not
    #: charged. ``None``: not known – every vehicle on a trip is charged.
    trip_keys: set[str] | None = None


def load_logistics(project: Project) -> Logistics:
    """Load the bookings of a project and the vehicles on its trips, two queries; none without bookings."""
    lines = list(
        project.vehicle_lines.select_related(
            "product", "item", "item__vehicle", "item__material_model", "tax_rate", "supplier", "phase"
        ).order_by("position", "id")
    )
    if not lines:
        return Logistics()
    from rentalars.projects.trips import trip_keys_of

    uses = list(project.trip_vehicles.order_by("id"))
    return Logistics(lines=lines, uses=uses, trip_keys=trip_keys_of([project.pk])[project.pk] if uses else None)


def load_logistics_of(project_ids: Iterable[int]) -> dict[int, Logistics]:
    """The same for many projects at once – two queries for all of them, three more with vehicles on trips (PRJ-085)."""
    ids = set(project_ids)
    found: dict[int, Logistics] = defaultdict(Logistics)
    if not ids:
        return found
    for line in (
        VehicleLine.objects.filter(project_id__in=ids)
        .select_related("product", "item", "tax_rate", "supplier")
        .order_by("position", "id")
    ):
        found[line.project_id].lines.append(line)
    if found:
        for use in TripVehicle.objects.filter(project_id__in=set(found)).order_by("id"):
            found[use.project_id].uses.append(use)
        with_uses = [project_id for project_id, logistics in found.items() if logistics.uses]
        if with_uses:
            from rentalars.projects.trips import trip_keys_of

            for project_id, keys in trip_keys_of(with_uses).items():
                found[project_id].trip_keys = keys
    return found


def trip_days_of(project: Project) -> dict[str, datetime.date]:
    """The local day each trip of the project starts on, by key – for trailers billed by the days with trips."""
    from rentalars.projects.trips import trips_of

    return {trip.key: timezone.localtime(trip.start).date() for trip in trips_of(project)}


def charged_uses(logistics: Logistics) -> list[TripVehicle]:
    """The vehicles on trips that are charged: not those on a trip that is gone.

    A trip goes when its phase is removed or it is removed by hand; the
    vehicles stay on it with their kilometres and a warning, so nothing typed
    in is lost – but neither the kilometres nor a trailer surcharge of a trip
    that is not there end up on an invoice.
    """
    if logistics.trip_keys is None:
        return list(logistics.uses)
    return [use for use in logistics.uses if use.trip_key in logistics.trip_keys]


def price_logistics(
    project: Project,
    logistics: Logistics,
    tables: dict[int, ScaleTable],
    *,
    trip_days: Callable[[], dict[str, datetime.date]] | None = None,
) -> list[VehiclePrice]:
    """Price every booking of a project (LOG-005, LOG-006, LOG-009, LOG-010).

    Args:
        project: The project.
        logistics: Its bookings and the vehicles on its trips.
        tables: The rental scale tables by version, those of the bookings among them.
        trip_days: Gives the day of each trip, by key; asked only if a trailer
            counts the days with trips – the trips cost a few queries.
            Default: :func:`trip_days_of`.

    Returns:
        One :class:`VehiclePrice` per booking, in their order.
    """
    by_vehicle: dict[int, list[TripVehicle]] = defaultdict(list)
    by_trailer: dict[int, list[TripVehicle]] = defaultdict(list)
    for use in charged_uses(logistics):
        by_vehicle[use.vehicle_line_id].append(use)
        if use.trailer_line_id:
            by_trailer[use.trailer_line_id].append(use)
    days_of_trips: dict[str, datetime.date] | None = None

    def known_trip_days() -> dict[str, datetime.date]:
        nonlocal days_of_trips
        if days_of_trips is None:
            days_of_trips = (trip_days or (lambda: trip_days_of(project)))()
        return days_of_trips

    prices = []
    for line in logistics.lines:
        if line.product.is_trailer:
            price = _price_trailer(line, by_trailer.get(line.pk, []), project, tables, known_trip_days)
        else:
            price = _price_car(line, by_vehicle.get(line.pk, []))
        _apply_discount(price)
        _apply_subrental_cost(price)
        prices.append(price)
    return prices


def _price_car(line: VehicleLine, uses: list[TripVehicle]) -> VehiclePrice:
    """A motor vehicle: per trip kilometres × (rate + surcharge with a trailer), or the flat rate (LOG-005, LOG-006)."""
    price = VehiclePrice(line=line)
    cost = ZERO
    for use in uses:
        cost_km = use.cost_km
        if use.billing == TripBilling.FLAT:
            charge = TripCharge(
                use=use, km=None, km_source=KmSource.FLAT, amount=money(use.flat_price or ZERO), cost_km=cost_km
            )
        else:
            surcharge = line.trailer_surcharge_per_km if use.trailer_line_id else ZERO
            rate = line.price_per_km + surcharge
            km = use.charged_km
            source = (
                KmSource.PLANNED
                if use.billing == TripBilling.PLANNED
                else (KmSource.ESTIMATE if use.km_is_estimate else KmSource.DRIVEN)
            )
            charge = TripCharge(
                use=use,
                km=km,
                km_source=source,
                rate=rate,
                surcharge_rate=surcharge,
                amount=money((km or ZERO) * rate),
                cost_km=cost_km,
            )
            price.is_estimate = price.is_estimate or charge.is_estimate
        price.charges.append(charge)
        cost += (cost_km or ZERO) * (line.cost_per_km or ZERO)
    price.base_amount = sum((charge.amount for charge in price.charges), ZERO)
    price.cost = money(cost)
    price.cost_is_known = line.cost_per_km is not None or not uses
    return price


def _price_trailer(
    line: VehicleLine,
    uses: list[TripVehicle],
    project: Project,
    tables: dict[int, ScaleTable],
    known_trip_days: Callable[[], dict[str, datetime.date]],
) -> VehiclePrice:
    """A trailer: per day with the rental scale, or per kilometre of the trips it is pulled on (LOG-005)."""
    price = VehiclePrice(line=line)
    cost_km_total = ZERO
    for use in uses:
        cost_km_total += use.cost_km or ZERO
        if line.billing == VehicleBilling.DAY:
            charge = TripCharge(use=use, km=None, km_source=KmSource.DAYS, cost_km=use.cost_km)
        elif use.billing == TripBilling.FLAT:
            charge = TripCharge(use=use, km=None, km_source=KmSource.FLAT, in_flat_rate=True, cost_km=use.cost_km)
        else:
            source = (
                KmSource.PLANNED
                if use.billing == TripBilling.PLANNED
                else (KmSource.ESTIMATE if use.km_is_estimate else KmSource.DRIVEN)
            )
            km = use.charged_km
            charge = TripCharge(
                use=use,
                km=km,
                km_source=source,
                rate=line.price_per_km,
                amount=money((km or ZERO) * line.price_per_km),
                cost_km=use.cost_km,
            )
            price.is_estimate = price.is_estimate or charge.is_estimate
        price.charges.append(charge)
    if line.billing == VehicleBilling.DAY:
        if line.only_trip_days:
            days_of = known_trip_days()
            price.days = len({days_of[use.trip_key] for use in uses if use.trip_key in days_of})
            price.days_source = DaysSource.TRIPS
        elif line.rental_days:
            price.days, price.days_source = line.rental_days, DaysSource.LINE
        elif line.has_own_period(project):
            price.days, price.days_source = started_days(line.start, line.end), DaysSource.PERIOD
        else:
            price.days, price.days_source = project.effective_rental_days, DaysSource.PROJECT
        table = tables.get(line.scale_version_id) if line.scale_version_id else None
        if not price.days:
            price.scale_factor = None
            price.base_amount = ZERO
        elif table is not None:
            # As material (PRD-033): the price per day × the factor of the rental scale for the days.
            price.scale_factor = table.factor_for(price.days)
            price.base_amount = money(line.price_per_day * price.scale_factor)
        else:
            # Without a rental scale every day counts in full.
            price.scale_factor = None
            price.base_amount = money(price.days * line.price_per_day)
        price.cost = money(price.days * (line.cost_per_day or ZERO))
        price.cost_is_known = line.cost_per_day is not None or not price.days
    else:
        price.base_amount = sum((charge.amount for charge in price.charges), ZERO)
        price.cost = money(cost_km_total * (line.cost_per_km or ZERO))
        price.cost_is_known = line.cost_per_km is not None or not uses
    return price


def _apply_discount(price: VehiclePrice) -> None:
    """The booking's discount, at most the maximum discount of its product (PRD-041)."""
    line = price.line
    maximum = line.product.max_discount_percent
    price.max_discount_percent = maximum
    price.discount_percent = limited_percent(line.discount_percent, maximum)
    price.discount_is_capped = price.discount_percent < line.discount_percent
    price.discount_amount = percentage_of(price.base_amount, price.discount_percent)
    price.amount = price.base_amount - price.discount_amount


def _apply_subrental_cost(price: VehiclePrice) -> None:
    """A vehicle from a supplier costs what the supplier charges, instead of the costs per kilometre and day."""
    line = price.line
    if line.supplier_id is not None:
        price.cost = money(line.subrental_cost or ZERO)
        price.cost_is_known = line.subrental_cost is not None


def describe_trips(prices: Iterable[VehiclePrice], trips: Iterable[Any]) -> None:
    """Put the trip into every charge, for the pages and documents that name it (LOG-009)."""
    by_key = {trip.key: trip for trip in trips}
    for price in prices:
        for charge in price.charges:
            charge.trip = by_key.get(charge.use.trip_key)
        # In the order of the trips; those that are gone last.
        price.charges.sort(
            key=lambda charge: (charge.trip is None, charge.trip.start if charge.trip is not None else timezone.now())
        )


# --- What is wrong with the plan (LOG-004, LOG-008, LOG-012 to LOG-014) -------------------------------------------


def _short(moment: datetime.datetime) -> str:
    return timezone.localtime(moment).strftime(local_pattern("%d.%m. %H:%M"))


def logistics_warnings(
    project: Project,
    lines: list[VehicleLine],
    uses: list[TripVehicle],
    crew: list[CrewLine],
    trip_keys: set[str] | None = None,
) -> dict[int, list[str]]:
    """Find what is wrong with the bookings of a project; nothing is prevented (see the module text).

    Args:
        project: The project.
        lines: Its bookings.
        uses: The vehicles on its trips.
        crew: Its crew lines.
        trip_keys: The keys of the project's trips, if the caller has them; a
            vehicle on a trip that is gone is pointed out. ``None``: not checked.

    Returns:
        ``{booking id: [warning, …]}`` for the bookings that have warnings.
        The number of queries does not grow with the number of bookings.
    """
    from rentalars.material.inspections import OVERDUE, InspectionPlan
    from rentalars.material.models import ItemBlock

    if not lines:
        return {}
    found: dict[int, list[str]] = defaultdict(list)
    booked = [line for line in lines if line.item_id is not None]
    by_id = {line.pk: line for line in lines}

    # LOG-004: the same vehicle booked at the same time – here or in another project that is not cancelled.
    if booked:
        earliest = min(line.start for line in booked)
        latest = max(line.end for line in booked)
        others = (
            VehicleLine.objects.filter(
                item_id__in={line.item_id for line in booked}, start__lt=latest, end__gt=earliest
            )
            .exclude(project__status=ProjectStatus.CANCELLED)
            .select_related("project")
        )
        elsewhere: dict[int, list[VehicleLine]] = defaultdict(list)
        for other in others:
            elsewhere[other.item_id].append(other)
        blocks: dict[int, list[Any]] = defaultdict(list)
        for block in ItemBlock.objects.filter(
            item_id__in={line.item_id for line in booked}, start__lt=latest, end__gt=earliest
        ):
            blocks[block.item_id].append(block)
        plan = InspectionPlan()
        dues = plan.dues_for([line.item for line in booked]) if not plan.is_empty else {}
        for line in booked:
            for other in elsewhere[line.item_id]:
                if other.pk == line.pk or not (other.start < line.end and line.start < other.end):
                    continue
                if other.project_id == line.project_id:
                    found[line.pk].append(_("Booked twice in this project at the same time."))
                else:
                    # Only the number: the reader may not be allowed to open the other project
                    # (AUT-016) – as the fleet names it ("Projekt 2027-0042").
                    found[line.pk].append(
                        _("Also booked for project %(number)s from %(start)s to %(end)s.")
                        % {"number": other.project.number, "start": _short(other.start), "end": _short(other.end)}
                    )
            if not line.item.is_operational:
                found[line.pk].append(_("The vehicle is %(status)s.") % {"status": line.item.get_status_display()})
            for block in blocks[line.item_id]:
                if block.start < line.end and line.start < block.end:
                    found[line.pk].append(
                        _("Blocked from %(start)s to %(end)s: %(reason)s")
                        % {"start": _short(block.start), "end": _short(block.end), "reason": block.reason}
                    )
            # LOG-014: an inspection due before the booking ends – overdue, or due during it.
            end_day = timezone.localtime(line.end).date()
            for due in dues.get(line.item_id, []):
                if due.state == OVERDUE:
                    found[line.pk].append(_("%(inspection)s is overdue.") % {"inspection": due.inspection_type.name})
                elif due.due_date is not None and due.due_date <= end_day:
                    found[line.pk].append(
                        _("%(inspection)s is due on %(date)s, before the booking ends.")
                        % {"inspection": due.inspection_type.name, "date": format_date(due.due_date)}
                    )

    _seat_and_licence_warnings(lines, by_id, crew, uses, found)
    _towing_warnings(by_id, uses, found)
    if trip_keys is not None:
        for use in uses:
            if use.trip_key not in trip_keys and use.vehicle_line_id in by_id:
                found[use.vehicle_line_id].append(
                    _(
                        "A trip it was put on is gone – its phase was removed or the trip deleted. It is not charged "
                        "for that trip: move it to another trip or remove it."
                    )
                )
    return {pk: texts for pk, texts in found.items() if texts}


def _vehicle_data(line: VehicleLine) -> Any:
    """The data of the booked vehicle (``material.Vehicle``), or ``None``."""
    if line.item_id is None:
        return None
    try:
        return line.item.vehicle
    except ObjectDoesNotExist:  # no data saved yet
        return None


def required_licence_class(vehicle_line: VehicleLine, trailer_line: VehicleLine | None) -> str:
    """LOG-012: the class a driver needs – that of the combination, which the trailer names, else the vehicle's."""
    trailer = _vehicle_data(trailer_line) if trailer_line is not None else None
    if trailer is not None and trailer.licence_class:
        return trailer.licence_class
    vehicle = _vehicle_data(vehicle_line)
    return vehicle.licence_class if vehicle is not None else ""


def _seat_and_licence_warnings(
    lines: list[VehicleLine],
    by_id: dict[int, VehicleLine],
    crew: list[CrewLine],
    uses: list[TripVehicle],
    found: dict[int, list[str]],
) -> None:
    """LOG-008, LOG-012: more people than seats; a driver without the class of the vehicle or combination."""
    from rentalars.personnel.models import Qualification, QualificationType

    with_vehicle = [line for line in crew if line.vehicle_line_id in by_id]
    by_vehicle: dict[int, list[CrewLine]] = defaultdict(list)
    for line in with_vehicle:
        by_vehicle[line.vehicle_line_id].append(line)
    for vehicle_id, travelling in by_vehicle.items():
        vehicle = _vehicle_data(by_id[vehicle_id])
        if vehicle is not None and vehicle.seats_max and len(travelling) > vehicle.seats_max:
            found[vehicle_id].append(
                ngettext(
                    "%(count)d people travel with it, it has %(seats)d seat.",
                    "%(count)d people travel with it, it has %(seats)d seats.",
                    vehicle.seats_max,
                )
                % {"count": len(travelling), "seats": vehicle.seats_max}
            )
        drivers = [line for line in travelling if line.is_driver]
        if len(drivers) > 1:
            found[vehicle_id].append(_("More than one driver is chosen for it."))
    # LOG-012: only if driving licences name their classes (Settings → qualifications).
    drivers = [line for line in with_vehicle if line.is_driver and line.person_id]
    if not drivers or not QualificationType.objects.exclude(licence_classes="").exists():
        return
    # L7: a licence counts if it is valid until the end of the booking – not just today.
    licences: dict[int, list[tuple[set[str], datetime.date | None]]] = defaultdict(list)
    for qualification in Qualification.objects.filter(
        person_id__in={line.person_id for line in drivers}, qualification_type__is_active=True
    ).exclude(qualification_type__licence_classes=""):
        licences[qualification.person_id].append(
            (set(qualification.qualification_type.covered_classes), qualification.valid_until)
        )
    trailers: dict[int, VehicleLine | None] = {}
    for use in uses:
        if use.trailer_line_id in by_id:
            trailers[use.vehicle_line_id] = by_id[use.trailer_line_id]
    for line in drivers:
        vehicle_line = by_id[line.vehicle_line_id]
        needed = required_licence_class(vehicle_line, trailers.get(vehicle_line.pk))
        if not needed:
            continue
        # The booking ends at the instant ``end``: one that ends at midnight sharp still belongs to the day before.
        end_day = (timezone.localtime(vehicle_line.end) - datetime.timedelta(microseconds=1)).date()
        covering = [(classes, until) for classes, until in licences[line.person_id] if needed in classes]
        if any(until is None or until >= end_day for _classes, until in covering):
            continue
        if covering:
            expiry = max(until for _classes, until in covering if until is not None)
            found[vehicle_line.pk].append(
                _("The driving licence of class %(class)s of %(person)s runs out on %(date)s, before the booking ends.")
                % {"person": line.person, "class": needed, "date": format_date(expiry)}
            )
        else:
            found[vehicle_line.pk].append(
                _("The driver %(person)s has no driving licence of class %(class)s.")
                % {"person": line.person, "class": needed}
            )


def _towing_warnings(by_id: dict[int, VehicleLine], uses: list[TripVehicle], found: dict[int, list[str]]) -> None:
    """LOG-013: a trailer at a vehicle that may not tow it – none at all, or not its weight."""
    seen: set[tuple[int, int]] = set()
    for use in uses:
        if use.trailer_line_id not in by_id or use.vehicle_line_id not in by_id:
            continue
        if (use.vehicle_line_id, use.trailer_line_id) in seen:
            continue
        seen.add((use.vehicle_line_id, use.trailer_line_id))
        vehicle = _vehicle_data(by_id[use.vehicle_line_id])
        trailer = _vehicle_data(by_id[use.trailer_line_id])
        if vehicle is None or vehicle.towing_capacity_kg is None:
            continue
        if vehicle.towing_capacity_kg == 0:
            found[use.vehicle_line_id].append(_("It may not tow a trailer."))
        elif trailer is not None and trailer.gross_weight_kg and trailer.gross_weight_kg > vehicle.towing_capacity_kg:
            found[use.vehicle_line_id].append(
                _("The trailer %(trailer)s weighs up to %(weight)s kg; it may tow %(capacity)s kg.")
                % {
                    "trailer": by_id[use.trailer_line_id].label,
                    "weight": trailer.gross_weight_kg,
                    "capacity": vehicle.towing_capacity_kg,
                }
            )


# --- Bookings of the fleet over all projects (LOG-004, LOG-018) ---------------------------------------------------


def bookings_of(
    item_ids: Iterable[int], start: datetime.datetime, end: datetime.datetime
) -> dict[int, list[VehicleLine]]:
    """The bookings of these vehicles that touch the period, in projects that are not cancelled; one query."""
    found: dict[int, list[VehicleLine]] = defaultdict(list)
    for line in (
        VehicleLine.objects.filter(item_id__in=list(item_ids), start__lt=end, end__gt=start)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .select_related("project", "project__customer")
        .order_by("start", "id")
    ):
        found[line.item_id].append(line)
    return found


def overlapping_ids(lines: list[VehicleLine]) -> set[int]:
    """The bookings among these – of one vehicle – that overlap another (LOG-004, red in the utilization)."""
    ordered = sorted(lines, key=lambda line: line.start)
    clashing: set[int] = set()
    for index, line in enumerate(ordered):
        for other in ordered[index + 1 :]:
            if other.start >= line.end:
                break
            clashing.update({line.pk, other.pk})
    return clashing
