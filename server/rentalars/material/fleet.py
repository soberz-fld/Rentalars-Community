# SPDX-License-Identifier: GPL-3.0-or-later
"""The fleet in the material administration: vehicles and trailers (LOG-002 ff.).

A vehicle or trailer is an item of a material model whose product is a
vehicle (``ProductKind.VEHICLE``). So it has its ID, status, files,
inspections (main inspection, DGUV/UVV – LOG-014), defects and label like
any item; its rates are those of its product (LOG-005), and what belongs to
the vehicle itself – licence plate, seats, driving licence class, towing
capacity, total weight – stands in :class:`~rentalars.material.models.Vehicle`
(LOG-003, LOG-012, LOG-013).

The vehicles are booked in the projects under "Logistik" (``projects.logistics``).
This module reads those bookings – the dependency goes from projects to
material, so the project modules are imported inside the functions – to show
per vehicle when it is booked, whether two bookings overlap (LOG-004), and
the utilization of the whole fleet as a timeline (LOG-018). Projects the
reader may not open appear as "Projekt" with their number, without name or
link (AUT-016).

The availability of material (``availability.engine``) never counts vehicles:
their products are no stock kind.

Moving a model that was planned as material into the fleet (LOG-016) is
:func:`move_model_to_fleet`: a new vehicle product, the old one and every
project line stay as they are.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.masterdata.models import Category, ProductKindDefault
from rentalars.material.models import MaterialItem, MaterialModel, TrackingMode, Vehicle
from rentalars.products.models import DEFAULT_BILLING_MODE, ProductKind, TrailerBilling, VehicleType

#: How far the item page and the fleet list look ahead for the bookings of a vehicle.
BOOKINGS_AHEAD_DAYS = 365

#: The fields of the vehicle data a caller may set (:func:`save_vehicle`).
VEHICLE_FIELDS = frozenset(
    {"licence_plate", "seats_min", "seats_max", "licence_class", "towing_capacity_kg", "gross_weight_kg"}
)

#: LOG-003, LOG-013: the fields only a motor vehicle has.
CAR_ONLY_FIELDS = frozenset({"seats_min", "seats_max", "towing_capacity_kg"})


# --- Which items are vehicles (LOG-002) --------------------------------------------------------------------------


def vehicle_items(queryset: QuerySet[MaterialItem] | None = None) -> QuerySet[MaterialItem]:
    """The items whose product is a vehicle – their own product, or else their model's (PRD-003).

    Written as in ``MaterialItemQuerySet.for_product``, so that the indexes
    serve it.
    """
    items = MaterialItem.objects.all() if queryset is None else queryset
    return items.filter(
        Q(product_override__kind=ProductKind.VEHICLE)
        | Q(product_override__isnull=True, material_model__default_product__kind=ProductKind.VEHICLE)
    )


def of_type(items: QuerySet[MaterialItem], vehicle_type: str) -> QuerySet[MaterialItem]:
    """Only the motor vehicles (``car``) or only the trailers (``trailer``) among vehicle items."""
    return items.filter(
        Q(product_override__vehicle_type=vehicle_type)
        | Q(product_override__isnull=True, material_model__default_product__vehicle_type=vehicle_type)
    )


def is_vehicle_item(item: MaterialItem) -> bool:
    """Whether the item belongs to a vehicle product: a vehicle or trailer of the fleet."""
    product = item.product
    return product is not None and product.is_vehicle


def vehicle_of(item: MaterialItem) -> Vehicle | None:
    """The vehicle data of an item, or ``None`` while none were saved."""
    try:
        return item.vehicle
    except ObjectDoesNotExist:
        return None


def seats_missing(item: MaterialItem, vehicle: Vehicle | None) -> bool:
    """LOG-003: a motor vehicle without its seats – the list and the item page point it out."""
    product = item.product
    if product is None or not product.is_car:
        return False
    return vehicle is None or vehicle.seats_min is None or vehicle.seats_max is None


@transaction.atomic
def save_vehicle(item: MaterialItem, *, replace: bool = False, **values: Any) -> Vehicle:
    """Set the vehicle data of an item – licence plate, seats, class, towing capacity, weight (LOG-002, LOG-003).

    The row is made when the data are saved the first time. The model checks
    the rules: a motor vehicle has its seats (min. at most max.), a trailer
    has no seats and tows nothing, a licence plate belongs to one vehicle.
    The change is noted in the history of the item.

    Args:
        item: An item of a vehicle product.
        replace: Every field not given is emptied (``PUT`` of the API);
            otherwise it keeps its value.
        **values: Fields of :data:`VEHICLE_FIELDS`.

    Raises:
        ValidationError: The item is no vehicle, a field is unknown, or a
            rule is violated.
    """
    if not is_vehicle_item(item):
        raise ValidationError(_("Only items of a vehicle product have vehicle data."))
    unknown = set(values) - VEHICLE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be set: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    vehicle = Vehicle.objects.filter(item=item).first() or Vehicle(item=item)
    if replace:
        for name in VEHICLE_FIELDS - set(values):
            setattr(vehicle, name, "" if name in ("licence_plate", "licence_class") else None)
    for name, value in values.items():
        setattr(vehicle, name, "" if value is None and name in ("licence_plate", "licence_class") else value)
    vehicle.full_clean()
    vehicle.save()
    return vehicle


# --- Bookings (LOG-004) --------------------------------------------------------------------------------------------


@dataclass
class Booking:
    """A booking of a vehicle in a project, as the fleet shows it (LOG-004)."""

    line: Any
    #: Whether the reader may open the project: only then are its name and link shown (AUT-016).
    visible: bool
    #: Whether another booking of the same vehicle overlaps this one – red in the lists and the utilization.
    overlaps: bool

    @property
    def project(self) -> Any:
        """The project of the booking."""
        return self.line.project

    @property
    def start(self) -> datetime.datetime:
        """Begin of the booking."""
        return self.line.start

    @property
    def end(self) -> datetime.datetime:
        """End of the booking."""
        return self.line.end

    @property
    def label(self) -> str:
        """The project's number and name – or "Projekt 2027-0042" for a project the reader may not open."""
        if self.visible:
            return f"{self.project.number} {self.project.name}"
        return _("Project %(number)s") % {"number": self.project.number}

    @property
    def url(self) -> str:
        """The page of the project, for a reader who may open it."""
        return reverse("projects:overview", args=[self.project]) if self.visible else ""

    @property
    def is_current(self) -> bool:
        """Whether the booking runs now."""
        now = timezone.now()
        return self.line.start <= now < self.line.end


def visible_project_ids(rights: Any, user: Any) -> set[int]:
    """The projects the reader may open (AUT-016) – their names and links are shown."""
    from rentalars.projects.access import visible_projects

    return set(visible_projects(rights, user).values_list("pk", flat=True))


def bookings_for(
    item_ids: Iterable[int], start: datetime.datetime, end: datetime.datetime, visible_ids: set[int]
) -> dict[int, list[Booking]]:
    """The bookings of these vehicles that touch the period, with overlaps marked (LOG-004).

    A booking overlaps when another booking of the same vehicle in a project
    that is not cancelled runs at the same time – also one that lies partly
    outside the period: the bookings are read again over the whole span of
    those found. Two queries at most.
    """
    from rentalars.projects.logistics import bookings_of, overlapping_ids

    ids = list(item_ids)
    found = bookings_of(ids, start, end)
    lines = [line for own in found.values() for line in own]
    if not lines:
        return {}
    earliest = min(line.start for line in lines)
    latest = max(line.end for line in lines)
    wider = bookings_of(list(found), earliest, latest) if earliest < start or latest > end else found
    result: dict[int, list[Booking]] = {}
    for item_id, own in found.items():
        clashing = overlapping_ids(wider.get(item_id, own))
        result[item_id] = [
            Booking(line=line, visible=line.project_id in visible_ids, overlaps=line.pk in clashing) for line in own
        ]
    return result


def current_or_next(bookings: list[Booking]) -> Booking | None:
    """The booking that runs now, else the next one to come."""
    now = timezone.now()
    running = [booking for booking in bookings if booking.start <= now < booking.end]
    if running:
        return running[0]
    coming = [booking for booking in bookings if booking.start >= now]
    return coming[0] if coming else None


def upcoming_window() -> tuple[datetime.datetime, datetime.datetime]:
    """From now on, :data:`BOOKINGS_AHEAD_DAYS` ahead: the bookings the item page and the fleet list show."""
    now = timezone.now()
    return now, now + datetime.timedelta(days=BOOKINGS_AHEAD_DAYS)


# --- The fleet list (LOG-002) -------------------------------------------------------------------------------------


def attach(items: list[MaterialItem], visible_ids: set[int], plan: Any = None) -> list[MaterialItem]:
    """Hang on every item what the fleet list shows: its vehicle data, next inspection due, current or next booking.

    ``fleet_vehicle`` (or ``None``), ``fleet_due`` (the most urgent
    inspection, or ``None`` – LOG-014), ``fleet_booking`` (a :class:`Booking`
    or ``None``) and ``fleet_overlap`` (any upcoming booking overlaps). A
    fixed number of queries, however many vehicles.
    """
    from rentalars.material.inspections import InspectionPlan

    if not items:
        return items
    plan = plan or InspectionPlan()
    dues = plan.dues_for(items)
    vehicles = {vehicle.item_id: vehicle for vehicle in Vehicle.objects.filter(item__in=items)}
    start, end = upcoming_window()
    bookings = bookings_for([item.pk for item in items], start, end, visible_ids)
    for item in items:
        item.fleet_vehicle = vehicles.get(item.pk)
        own_dues = dues.get(item.pk, [])
        item.fleet_due = own_dues[0] if own_dues else None
        own = bookings.get(item.pk, [])
        item.fleet_booking = current_or_next(own)
        item.fleet_overlap = any(booking.overlaps for booking in own)
    return items


# --- Utilization of the fleet (LOG-018) ---------------------------------------------------------------------------


@dataclass
class FleetRow:
    """One vehicle in the utilization: its bookings as bars, blocked periods too (LOG-018)."""

    item: MaterialItem
    vehicle: Vehicle | None
    bars: list[Any] = field(default_factory=list)

    @property
    def conflict(self) -> bool:
        """Whether bookings of the vehicle overlap within the shown span (LOG-004)."""
        return any(bar.conflict for bar in self.bars)

    @property
    def name(self) -> str:
        """The licence plate, else the ID of the item."""
        plate = self.vehicle.licence_plate if self.vehicle is not None else ""
        return plate or self.item.display_id


def utilization_rows(items: list[MaterialItem], scale: Any, visible_ids: set[int]) -> list[FleetRow]:
    """The rows of the utilization of the fleet: per vehicle its bookings over the projects (LOG-018).

    A bar per booking with project number and name (only the number for a
    project the reader may not open), at its exact times; bookings that
    overlap are filled red (LOG-004) – the colours are those of the
    deployments in the personnel plan (firm, option, inquiry). Blocked
    periods of the vehicle (MAT-024) are bars of their own. Four queries,
    whatever the number of vehicles.
    """
    from rentalars.material.models import ItemBlock
    from rentalars.schedule.services import bounds, exact_period

    start, end = bounds(scale.days)
    vehicles = {vehicle.item_id: vehicle for vehicle in Vehicle.objects.filter(item__in=items)}
    bookings = bookings_for([item.pk for item in items], start, end, visible_ids)
    blocks: dict[int, list[Any]] = defaultdict(list)
    for block in ItemBlock.objects.filter(item__in=items, start__lt=end, end__gt=start).order_by("start"):
        blocks[block.item_id].append(block)
    rows = []
    for item in items:
        row = FleetRow(item=item, vehicle=vehicles.get(item.pk))
        for booking in bookings.get(item.pk, []):
            line = booking.line
            period = exact_period(line.start, line.end)
            bar = scale.bar(
                line.start,
                line.end,
                label=booking.label,
                css=f"crew vehicle-booking status-{booking.project.status}",
                title=f"{line.title} · {period}" if booking.visible and line.title else period,
                url=booking.url,
                record=line,
                conflict=booking.overlaps,
            )
            if bar is not None:
                row.bars.append(bar)
        for block in blocks.get(item.pk, []):
            bar = scale.bar(
                block.start,
                block.end,
                label=_("blocked"),
                css="blocked",
                title=" · ".join((block.reason, exact_period(block.start, block.end))),
                record=block,
            )
            if bar is not None:
                row.bars.append(bar)
        row.bars.sort(key=lambda bar: (bar.first, bar.last))
        rows.append(row)
    return rows


def vehicle_products_exist() -> bool:
    """Whether any product is a vehicle – else the fleet list says how to start one."""
    from rentalars.products.models import Product

    return Product.objects.filter(kind=ProductKind.VEHICLE).exists()


# --- From material to the fleet (LOG-016) ---------------------------------------------------------------------------


def is_vehicle_category(category: Category) -> bool:
    """Whether the category or one above it presets the product kind "vehicle" – as the start category FZ "Fuhrpark".

    (LOG-020; LOG-016) Walks the parents
    in memory where they were loaded with the category.
    """
    return any(level.default_product_kind == ProductKindDefault.VEHICLE for level in category.ancestors_and_self())


def transition_problem(material_model: MaterialModel) -> str:
    """Why a model cannot be taken into the fleet, or "" (LOG-016).

    Customer material stays the customer's; a vehicle is a single item, not
    a bulk quantity; only material planned as a rental product – or not
    planned yet – becomes vehicles, and a model in the fleet is there already.
    (LOG-020) Only a model of a vehicle
    category (:func:`is_vehicle_category`) comes into the fleet – a cable
    never does. The page, its dialog and the API all ask here.
    """
    old = material_model.default_product
    if material_model.category.holds_customer_material or (old is not None and old.owner_id is not None):
        return _("Customer material cannot be taken into the fleet.")
    if old is not None and old.kind == ProductKind.VEHICLE:
        return _("%(model)s belongs to the fleet already.") % {"model": material_model.name}
    if not is_vehicle_category(material_model.category):
        return _("Only models of a vehicle category (product kind “vehicle”) are taken into the fleet.")
    if old is not None and old.kind != ProductKind.RENTAL:
        return _("Only material planned as a rental product can be taken into the fleet; %(product)s is %(kind)s.") % {
            "product": old.article_number,
            "kind": old.get_kind_display(),
        }
    if material_model.tracking_mode == TrackingMode.BULK:
        return _("A vehicle is a single item: a model kept as a bulk quantity cannot become one.")
    return ""


@dataclass
class FleetTransition:
    """What :func:`move_model_to_fleet` did."""

    product: Any
    old_product: Any
    #: Items that named the old product themselves and now name the new one.
    items_moved: int
    #: Open projects (neither closed nor cancelled) that still plan the old product as material lines.
    open_projects: list[Any]


@transaction.atomic
def move_model_to_fleet(
    material_model: MaterialModel,
    rights: Any,
    *,
    vehicle_type: str,
    price_per_km: Decimal | None = None,
    trailer_surcharge_per_km: Decimal | None = None,
    trailer_billing: str = TrailerBilling.DAY,
    price: Decimal | None = None,
    cost_per_km: Decimal | None = None,
    cost_per_day: Decimal | None = None,
) -> FleetTransition:
    """Take a model that was planned as material into the fleet (LOG-016).

    A *new* vehicle product is made in the category of the model – the next
    free article number, the name, unit, tax rate and rental scale of the old
    product (else the presets of the category) – and becomes the product of
    the model; items that named the old product themselves follow. The old
    product and every project line stay as they are: the update changes no
    price and no sum. Open projects that still plan the old product as
    material are named, so that the planner books the vehicles under
    "Logistik" instead.

    The rates need the price right, the internal costs the right to see
    purchase prices (AUT-019, LOG-010). The day price of a trailer starts as
    the price of the old product. Without the price right the price per
    kilometre starts at 0, as a product made from a model does (MAT-051):
    somebody with the right enters it.

    Raises:
        ValidationError: The model is customer material, kept in bulk, its
            product is no rental product, a right is missing, or the new
            product breaks a rule of the products.
    """
    from rentalars.accounts.rights import SpecialRight
    from rentalars.products import services as product_services
    from rentalars.products.models import Product
    from rentalars.projects.models import MaterialLine, Project, ProjectStatus

    material_model = (
        MaterialModel.objects.select_for_update()
        .select_related("category", "default_product__owner")
        .get(pk=material_model.pk)
    )
    old = material_model.default_product
    problem = transition_problem(material_model)
    if problem:
        raise ValidationError(problem)
    if vehicle_type not in VehicleType.values:
        raise ValidationError({"vehicle_type": _("Choose whether this is a motor vehicle or a trailer.")})
    prices = {"price_per_km": price_per_km, "trailer_surcharge_per_km": trailer_surcharge_per_km, "price": price}
    if any(value is not None for value in prices.values()) and not rights.has(SpecialRight.PRICES):
        raise ValidationError(_("You do not have the right to set prices or discounts."))
    costs = {"cost_per_km": cost_per_km, "cost_per_day": cost_per_day}
    if any(value is not None for value in costs.values()) and not rights.has(SpecialRight.PURCHASE_PRICES):
        raise ValidationError(_("You do not have the right to see purchase prices and internal costs."))

    category = material_model.category
    presets = product_services.presets_for_category(category)
    is_car = vehicle_type == VehicleType.CAR
    if not is_car and price is None and old is not None:
        price = old.price  # the day price of a trailer: as the material was rented so far
    if not rights.has(SpecialRight.PRICES):
        by_km = is_car or trailer_billing == TrailerBilling.KM
        price_per_km = Decimal("0") if by_km else None
        if not is_car and trailer_billing == TrailerBilling.DAY and price is None:
            price = Decimal("0")
    product = Product(
        category=category,
        article_number=presets["article_number"],
        name=(old.name if old is not None else material_model.name)[:200],
        description=old.description if old is not None else "",
        kind=ProductKind.VEHICLE,
        vehicle_type=vehicle_type,
        unit=old.unit if old is not None else presets["unit"],
        tax_rate=old.tax_rate if old is not None else presets["tax_rate"],
        billing_mode=DEFAULT_BILLING_MODE[ProductKind.VEHICLE],
        price_per_km=price_per_km,
        trailer_surcharge_per_km=trailer_surcharge_per_km if is_car else None,
        trailer_billing=TrailerBilling.DAY if is_car else trailer_billing,
        price=None if is_car else price,
        cost_per_km=cost_per_km,
        cost_per_day=None if is_car else cost_per_day,
    )
    if old is not None:
        product.rental_scale_mode, product.rental_scale = old.rental_scale_mode, old.rental_scale
        product.max_discount_percent = old.max_discount_percent
    product_services.save_product(product, rights)
    material_model.default_product = product
    material_model.full_clean()
    material_model.save()
    moved = 0
    if old is not None:
        for item in MaterialItem.objects.filter(material_model=material_model, product_override=old):
            item.product_override = None
            item.save()
            moved += 1
    record_event(
        material_model,
        "material_model.taken_into_fleet",
        {"product": product.article_number, "old_product": old.article_number if old is not None else "–"},
    )
    open_projects: list[Any] = []
    if old is not None:
        project_ids = (
            MaterialLine.objects.filter(product=old)
            .exclude(project__status__in=[ProjectStatus.CLOSED, ProjectStatus.CANCELLED])
            .values("project_id")
        )
        open_projects = list(Project.objects.filter(pk__in=project_ids).order_by("start", "number"))
    return FleetTransition(product=product, old_product=old, items_moved=moved, open_projects=open_projects)


def open_projects_message(transition: FleetTransition, visible_ids: set[int]) -> str:
    """LOG-016: the hint after the move – which open projects still plan the old product as material.

    Only projects the reader may open are named; the others are counted
    (AUT-016). Empty if there are none.
    """
    if not transition.open_projects or transition.old_product is None:
        return ""
    named = [f"{project.number} {project.name}" for project in transition.open_projects if project.pk in visible_ids]
    others = len(transition.open_projects) - len(named)
    if others:
        named.append(_("%(count)d more you cannot open") % {"count": others})
    return _(
        "These open projects still plan %(product)s as material: %(projects)s. Its items are vehicles now – book "
        "them under “Logistik” there and remove the material lines; prices and sums stay until then."
    ) % {"product": transition.old_product.article_number, "projects": ", ".join(named)}
