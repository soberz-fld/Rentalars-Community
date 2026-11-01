# SPDX-License-Identifier: GPL-3.0-or-later
"""The planning view of a project: lines with prices and availability side by side.

The planning page, the price overview and the API all need the same picture
of a project: its groups in order, each line with its amount (PRJ-033) and
its availability verdict (PRJ-012). This module builds that picture once, so
the three cannot drift apart (API-002).

Whether prices are *shown* is decided by the caller from the rights of the
user (AUT-019); this module always calculates them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import Any

from django.db.models import Exists, OuterRef, prefetch_related_objects
from django.utils.translation import gettext as _

from rentalars.availability.engine import UNCHECKED, AvailabilityEngine, LineAvailability
from rentalars.core.money import ZERO
from rentalars.products.models import KitComponent, Product
from rentalars.projects.crew import (
    CrewPrice,
    LooseTimes,
    PhaseShare,
    breakdown_by_phase,
    crew_warnings,
    unassigned_times,
)
from rentalars.projects.grouptree import MAX_DEPTH, PATH_SEPARATOR
from rentalars.projects.lines import line_label
from rentalars.projects.logistics import TripCharge, VehiclePrice, describe_trips, logistics_warnings
from rentalars.projects.models import CrewLine, Group, MaterialLine, Project, TripVehicle, VehicleLine
from rentalars.projects.price_updates import OldPrice, find_old_prices, shows_price_hint
from rentalars.projects.pricing import GroupPrices, LinePrice, ProjectPrices, compute_project_prices
from rentalars.projects.product_changes import LineChange, find_changes
from rentalars.projects.summary import summarize_crew, summarize_lines
from rentalars.projects.wishes import Wish, load_wishes


@dataclass
class LineStockInfo:
    """How one product of a line stands, with the product loaded for display."""

    product: Product
    #: Missing pieces; 0 if there are enough.
    quantity: int
    #: Stock figures for the tooltip "9 stock, 6 firm, 2 optional, 1 free".
    stock: int
    firm: int
    optional: int
    own_project: int
    free: int

    @property
    def summary(self) -> str:
        """The short line below the traffic light: "stock 9, elsewhere 6, optional 2" (VFG-003)."""
        text = _("stock %(stock)s, elsewhere %(firm)s") % {"stock": self.stock, "firm": self.firm}
        if self.optional:
            text += ", " + _("optional %(optional)s") % {"optional": self.optional}
        return text

    @property
    def explanation(self) -> str:
        """The same figures in full words, shown when the pointer rests on the traffic light."""
        return _(
            "Stock %(stock)s, firmly reserved elsewhere %(firm)s, optional %(optional)s, "
            "other lines of this project %(own)s"
        ) % {"stock": self.stock, "firm": self.firm, "optional": self.optional, "own": self.own_project}


@dataclass
class PlannedLine:
    """A material line with everything the planning shows about it."""

    line: MaterialLine
    price: LinePrice
    availability: LineAvailability
    #: Products this line is short of – the basis of the subrental suggestion (PRJ-054).
    shortages: list[LineStockInfo] = field(default_factory=list)
    #: Subrental lines that cover a shortage of this line.
    covered_by: list[MaterialLine] = field(default_factory=list)
    #: PRJ-084: the same subrentals as planned lines, shown as parts of this line right below it.
    covering: list[PlannedLine] = field(default_factory=list)
    #: PRJ-084: True for a subrental that covers a shortage of a line in the same section – it is shown
    #: as a part of that line (in its ``covering``), not as a line of its own.
    is_sub_row: bool = False
    #: PRJ-083: the line an alternative could replace – loaded with the planning, no query of its own.
    alternative_to: MaterialLine | None = None
    #: For kit lines: the components and how many of each this line needs (PRJ-016).
    components: list[tuple[Product, int]] = field(default_factory=list)
    #: Subrented pieces that are no longer needed (PRJ-056).
    excess_cover: int = 0
    #: PRJ-060: lines of other subprojects that take over pieces of this line.
    handed_to: list[MaterialLine] = field(default_factory=list)

    #: Stock figures to show next to the line: those of its own product, or
    #: for a kit those of its scarcest component. ``None`` if nothing is checked.
    stock_info: LineStockInfo | None = None
    #: The specific model or item the line asks for, with warnings (PRJ-064).
    wish: Wish | None = None

    @property
    def status(self) -> str:
        """The traffic light: ``unchecked``, ``ok``, ``tight`` or ``short``."""
        return self.availability.status

    @property
    def alternative_label(self) -> str:
        """PRJ-083: the line an alternative could replace, in short: "8 × LED-Scheinwerfer"; "" for none."""
        return line_label(self.alternative_to) if self.alternative_to is not None else ""


@dataclass
class PlannedCrewLine:
    """A crew line with everything the planning shows about it (PRJ-019, PRJ-022, PRJ-051)."""

    price: CrewPrice
    #: What is wrong with the plan for this person; empty if nothing (PRJ-022).
    warnings: list[str] = field(default_factory=list)

    @property
    def line(self) -> CrewLine:
        """The crew line itself."""
        return self.price.line


@dataclass
class PlannedVehicle:
    """A vehicle booking with everything the block "Logistik" shows about it (LOG-001, LOG-004, LOG-009)."""

    price: VehiclePrice
    #: What is wrong with the booking; empty if nothing (LOG-004, LOG-008, LOG-012 to LOG-014).
    warnings: list[str] = field(default_factory=list)
    #: LOG-008: the crew lines of the people who travel with it, the driver among them.
    crew: list[CrewLine] = field(default_factory=list)

    @property
    def line(self) -> VehicleLine:
        """The booking itself."""
        return self.price.line


@dataclass
class TripUse:
    """A motor vehicle on a trip with its trailer, and what each of them is charged for it (LOG-006, LOG-007)."""

    use: TripVehicle
    vehicle: VehicleLine
    trailer: VehicleLine | None
    vehicle_charge: TripCharge | None
    trailer_charge: TripCharge | None

    @property
    def amount(self) -> Decimal:
        """What the trip costs the customer before discounts: vehicle with surcharge, and the trailer per kilometre."""
        total = self.vehicle_charge.amount if self.vehicle_charge is not None else ZERO
        if self.trailer_charge is not None:
            total += self.trailer_charge.amount
        return total


@dataclass
class TripRow:
    """A trip of the project with its vehicles (LOG-007); ``trip`` is ``None`` for a trip that is gone."""

    key: str
    trip: Any
    uses: list[TripUse] = field(default_factory=list)

    @property
    def vehicle_ids(self) -> set[int]:
        """The bookings already on this trip, as motor vehicle or trailer."""
        found = {use.vehicle.pk for use in self.uses}
        found.update(use.trailer.pk for use in self.uses if use.trailer is not None)
        return found


@dataclass
class PlannedGroup:
    """A group with its lines and subtotal – and, since PRJ-037, its place in the tree of groups."""

    group: Group
    prices: GroupPrices
    lines: list[PlannedLine] = field(default_factory=list)
    #: PRJ-037: the group above (``None`` at the top level) and the subgroups in their order.
    parent: PlannedGroup | None = field(default=None, repr=False, compare=False)
    children: list[PlannedGroup] = field(default_factory=list, repr=False, compare=False)
    #: PRJ-083: the group an alternative group could replace.
    alternative_to: Group | None = field(default=None, repr=False, compare=False)

    @property
    def summary(self) -> str:
        """What the group contains, in one line, for the price overview without lines (PRJ-066)."""
        return summarize_lines(self.lines)

    @property
    def depth(self) -> int:
        """0 for a top-level group, 1 and 2 for the levels below (PRJ-037)."""
        return self.prices.depth

    @property
    def heading_level(self) -> int:
        """The HTML heading of the group's name: h3 at the top, h4 and h5 below (PRJ-037)."""
        return 3 + self.depth

    @property
    def path(self) -> str:
        """The names from the top down to this group: "Licht › Front-Traverse" (PRJ-037)."""
        names = [self.group.name]
        current = self.parent
        while current is not None:
            names.append(current.group.name)
            current = current.parent
        return PATH_SEPARATOR.join(reversed(names))

    @property
    def ancestors(self) -> list[PlannedGroup]:
        """The groups above, the nearest first (PRJ-037)."""
        found = []
        current = self.parent
        while current is not None:
            found.append(current)
            current = current.parent
        return found

    @property
    def can_take_subgroups(self) -> bool:
        """Whether a group can still be put into this one without going beyond three levels (PRJ-037)."""
        return self.depth + 1 < MAX_DEPTH

    @property
    def delete_question(self) -> str:
        """The question before deleting the group: what happens with its lines and subgroups (PRJ-037)."""
        if self.parent is None:
            if self.children:
                return _("Delete this group? Its lines move to “without group”, its subgroups to the top level.")
            return _("Delete this group? Its lines move to “without group”.")
        if self.children:
            return _("Delete this group? Its lines and subgroups move to the group “%(parent)s”.") % {
                "parent": self.parent.group.name
            }
        return _("Delete this group? Its lines move to the group “%(parent)s”.") % {"parent": self.parent.group.name}


@dataclass
class Planning:
    """The complete planning picture of a project."""

    project: Project
    prices: ProjectPrices
    #: Every group in the order of the planning: a group, its subgroups, the next group (PRJ-037).
    groups: list[PlannedGroup] = field(default_factory=list)
    ungrouped: list[PlannedLine] = field(default_factory=list)
    surcharges: list[PlannedLine] = field(default_factory=list)
    #: ``True`` for the picture :func:`build_patch` makes: prices and totals
    #: of the whole project, but lines and availability only for the
    #: sections that are shown again. Questions about *all* lines (how many
    #: pieces are missing?) cannot be answered from it and raise an error.
    partial: bool = False
    #: Whether the reader has the price right: prices are then part of the product changes (PRJ-072).
    see_prices: bool = False

    @property
    def all_lines(self) -> list[PlannedLine]:
        """Every line of the project in display order."""
        if self.partial:
            raise RuntimeError("A partial planning does not know all lines; use build_planning().")
        lines = [line for group in self.groups for line in group.lines]
        return lines + self.ungrouped + self.surcharges

    @property
    def root_groups(self) -> list[PlannedGroup]:
        """The top-level groups; each leads to its subgroups through ``children`` (PRJ-037)."""
        return [group for group in self.groups if group.parent is None]

    @property
    def ungrouped_summary(self) -> str:
        """What the lines without group contain, in one line (PRJ-066)."""
        return summarize_lines(self.ungrouped)

    @property
    def crew_summary(self) -> str:
        """Which personnel the project charges for, in one line: "2 × Stagehand" (PRJ-066)."""
        return summarize_crew(self.prices.crew)

    @cached_property
    def crew_by_phase(self) -> list[PhaseShare]:
        """The personnel by phase and job function, for the price overview (PRJ-088)."""
        return breakdown_by_phase(self.prices.crew)

    @property
    def surcharges_summary(self) -> str:
        """The names of the surcharges, in one line (PRJ-066)."""
        return ", ".join(planned.line.title for planned in self.surcharges)

    @property
    def short_lines(self) -> list[PlannedLine]:
        """Lines with an uncovered shortage (PRJ-013)."""
        return [line for line in self.all_lines if line.status == "short"]

    @property
    def shortage_total(self) -> int:
        """The number of missing pieces over the whole project."""
        return sum(line.availability.shortage_total for line in self.all_lines)

    @property
    def excess_cover_lines(self) -> list[PlannedLine]:
        """Lines whose subrental is (partly) no longer needed (PRJ-056)."""
        return [line for line in self.all_lines if line.excess_cover > 0]

    @cached_property
    def old_prices(self) -> list[OldPrice]:
        """Lines whose product asks another price now (PRJ-072) – only while the project is not fully confirmed."""
        if not shows_price_hint(self.project):
            return []
        return find_old_prices([planned.line for planned in self.all_lines], [price.line for price in self.prices.crew])

    @property
    def old_prices_not_by_hand(self) -> int:
        """How many of the old prices "take over all" changes: those not set by hand (PRJ-072)."""
        return sum(1 for old in self.old_prices if not old.set_by_hand)

    @cached_property
    def product_changes(self) -> list[LineChange]:
        """Lines whose product changed since they took it over (PRJ-072) – only while not fully confirmed.

        Prices are looked at only if ``see_prices`` is set (the reader has the price right).
        """
        if not shows_price_hint(self.project):
            return []
        return find_changes(
            [planned.line for planned in self.all_lines],
            [price.line for price in self.prices.crew],
            with_prices=self.see_prices,
        )

    @property
    def changes_not_by_hand(self) -> int:
        """How many changed lines "take over all" changes: those with no part set by hand (PRJ-072)."""
        return sum(1 for change in self.product_changes if not change.set_by_hand)

    # --- Personnel (PRJ-038) -------------------------------------------------
    # The crew is always complete, also in a partial planning: it is a block
    # of its own and small. Its warnings and the times without crew line are
    # looked up when somebody asks – a patch for a material line never does.

    @property
    def crew(self) -> list[PlannedCrewLine]:
        """The crew lines with price, cost and warnings, in display order."""
        # LOG-008: the vehicle a line names is one of the bookings loaded already – no query per line.
        vehicles = {price.line.pk: price.line for price in self.prices.logistics}
        for price in self.prices.crew:
            if price.line.vehicle_line_id in vehicles:
                price.line.vehicle_line = vehicles[price.line.vehicle_line_id]
        warnings = self.crew_warnings
        return [PlannedCrewLine(price=price, warnings=warnings.get(price.line.pk, [])) for price in self.prices.crew]

    @cached_property
    def crew_warnings(self) -> dict[int, list[str]]:
        """Double bookings, absences and missing job functions, by crew line (PRJ-022)."""
        return crew_warnings([price.line for price in self.prices.crew])

    @cached_property
    def loose_times(self) -> list[LooseTimes]:
        """Approved times of the project that count towards no crew line (ZEI-021)."""
        return unassigned_times(self.project)

    @property
    def open_places(self) -> int:
        """How many crew lines still wait for a person (PRJ-020)."""
        return sum(1 for price in self.prices.crew if price.line.is_vacant)

    # --- Logistics (LOG-001 ff.) ------------------------------------------
    # A block of its own below the personnel, always complete. The trips and the
    # warnings are looked up when the block is shown – a patch of a material line
    # never asks.

    @cached_property
    def trips(self) -> list[Any]:
        """The trips of the project with the changes by hand (PRJ-097, PRJ-111)."""
        from rentalars.projects.trips import trips_of

        return trips_of(self.project)

    @cached_property
    def logistics(self) -> list[PlannedVehicle]:
        """The vehicle bookings with price, cost and warnings, in their order; the charges name their trips."""
        if not self.prices.logistics:
            return []
        describe_trips(self.prices.logistics, self.trips)
        warnings = logistics_warnings(
            self.project,
            [price.line for price in self.prices.logistics],
            self.prices.trip_vehicles,
            [price.line for price in self.prices.crew],
            trip_keys={trip.key for trip in self.trips},
        )
        travelling: dict[int, list[CrewLine]] = defaultdict(list)
        for crew_price in self.prices.crew:
            if crew_price.line.vehicle_line_id:
                travelling[crew_price.line.vehicle_line_id].append(crew_price.line)
        return [
            PlannedVehicle(
                price=price, warnings=warnings.get(price.line.pk, []), crew=travelling.get(price.line.pk, [])
            )
            for price in self.prices.logistics
        ]

    @cached_property
    def trip_rows(self) -> list[TripRow]:
        """Every trip of the project with the vehicles on it – trips without any as well; trips that are gone last."""
        planned = self.logistics  # names the trips in the charges
        lines = {item.line.pk: item for item in planned}
        charges: dict[tuple[int, int], TripCharge] = {}
        for item in planned:
            for charge in item.price.charges:
                charges[(item.line.pk, charge.use.pk)] = charge
        rows = {trip.key: TripRow(key=trip.key, trip=trip) for trip in self.trips}
        gone: dict[str, TripRow] = {}
        for use in self.prices.trip_vehicles:
            vehicle = lines.get(use.vehicle_line_id)
            if vehicle is None:
                continue
            trailer = lines.get(use.trailer_line_id) if use.trailer_line_id else None
            row = rows.get(use.trip_key) or gone.setdefault(use.trip_key, TripRow(key=use.trip_key, trip=None))
            row.uses.append(
                TripUse(
                    use=use,
                    vehicle=vehicle.line,
                    trailer=trailer.line if trailer is not None else None,
                    vehicle_charge=charges.get((use.vehicle_line_id, use.pk)),
                    trailer_charge=charges.get((use.trailer_line_id, use.pk)) if trailer is not None else None,
                )
            )
        return list(rows.values()) + list(gone.values())

    @property
    def has_cars(self) -> bool:
        """Whether a motor vehicle is booked – only then can a trip get a vehicle (LOG-007)."""
        return any(price.line.product.is_car for price in self.prices.logistics)

    @property
    def logistics_summary(self) -> str:
        """The booked vehicles in one line, for the price overview without lines (PRJ-066)."""
        return ", ".join(price.line.label for price in self.prices.logistics)

    @property
    def logistics_warning_count(self) -> int:
        """How many bookings have a warning – for the hint above the planning."""
        return sum(1 for item in self.logistics if item.warnings)


@dataclass
class PlanningPatch:
    """The parts of a planning that a change touched (NFA-013).

    After a line was added, changed or deleted, the browser does not need the
    whole planning again – in a project with 500 lines that would be close to
    a megabyte of HTML. It gets the groups in which something can look
    different now; surcharges and totals are always sent along. The hints
    above the planning ("3 pieces are missing") speak about all lines; the
    page fetches them with a second, separate request.
    """

    groups: list[PlannedGroup] = field(default_factory=list)
    #: PRJ-037: groups whose subtotal with subgroups is sent again – the groups above every group in
    #: the patch: a change in a subgroup changes the sums of all groups above it.
    totals: list[PlannedGroup] = field(default_factory=list)
    #: Whether the section "without group" is part of the patch.
    ungrouped: bool = False
    #: Whether the block "personnel" is part of the patch (after a change of a crew line).
    crew: bool = False
    #: LOG-001: whether the block "Logistik" is part of the patch – sent with the personnel, since a crew
    #: line names its vehicle and the vehicle counts its people.
    logistics: bool = False


#: Stands for the section "surcharges" where group IDs stand for groups and
#: ``None`` for "without group".
_SURCHARGES = "surcharges"


def _section_of(line: MaterialLine, group_ids: Iterable[int]) -> int | str | None:
    """Tell in which section of the planning page a line is shown.

    A subrental that covers a shortage is shown below the line it covers
    (PRJ-084), so it is in that line's section, wherever it stands itself.
    The covered line is loaded with the planning (``load_lines``).

    Returns:
        The ID of its group; ``None`` for "without group"; ``_SURCHARGES``
        for a surcharge that belongs to no group (PRD-031).
    """
    if line.covers_line_id is not None and line.covers_line is not None:
        line = line.covers_line
    if line.group_id and line.group_id in group_ids:
        return line.group_id
    return _SURCHARGES if line.is_surcharge else None


def load_lines(project: Project) -> list[MaterialLine]:
    """Load the lines of a project with everything the planning touches.

    Product, category, unit, tax rate and supplier are fetched with one small
    query each (``prefetch_related``) instead of being joined to every line:
    500 lines share a handful of units and tax rates, and building each of
    them 500 times over costs more than the five extra queries (NFA-014).
    """
    lines = list(
        project.material_lines.annotate(
            # PRJ-060: whether a line of another subproject takes over pieces of this one – within the same query.
            hands_on=Exists(MaterialLine.objects.filter(taken_over_from=OuterRef("pk")))
        )
        .prefetch_related(
            "product",
            "product__category",
            "product__unit",
            "tax_rate",
            "unit",
            "supplier",
            "covers_line",
            "covers_product",
            # PRJ-060: where taken-over pieces come from; no query for a project without such lines.
            "taken_over_from",
            "taken_over_from__project",
        )
        .order_by("position", "id")
    )
    # (update test; PRD-052, PRJ-064) The wished items of all lines at once – the planning document asks every
    # line for them (500 queries for 500 lines before); no query at all for a project without such a wish.
    prefetch_related_objects(
        [line for line in lines if line.preferred_item_id], "preferred_item", "further_preferred_items"
    )
    return lines


def handed_on(lines: list[MaterialLine]) -> dict[int, list[MaterialLine]]:
    """For lines of a project: the lines of other subprojects that take over their pieces (PRJ-060).

    One query; ``{line id: [taking lines]}``.
    """
    ids = [line.pk for line in lines if line.pk is not None and line.product_id is not None]
    if not ids:
        return {}
    found: dict[int, list[MaterialLine]] = defaultdict(list)
    for taking in MaterialLine.objects.filter(taken_over_from_id__in=ids).select_related("project").order_by("pk"):
        found[taking.taken_over_from_id].append(taking)
    return found


def build_planning(project: Project, *, engine: AvailabilityEngine | None = None) -> Planning:
    """Assemble groups, lines, prices and availability of a project.

    The number of database queries does not grow with the number of lines:
    lines, groups, prices and availability are each loaded for the whole
    project at once (NFA-014).

    Args:
        project: The project.
        engine: An availability engine to reuse, if the caller has one.
    """
    groups = list(project.groups.all())
    lines = load_lines(project)
    prices = compute_project_prices(project, lines=lines, groups=groups)
    availability = (engine or AvailabilityEngine()).project_availability(project, lines, groups)
    return _assemble(project, groups, lines, prices, availability)


def build_patch(
    project: Project,
    engine: AvailabilityEngine,
    *,
    product_ids: Iterable[int | None],
    group_ids: Iterable[int | None],
) -> tuple[Planning, PlanningPatch]:
    """Build what must be shown again after a change of one line (NFA-013).

    A section of the planning page is shown again if

    * the changed line is or was in it (``group_ids``; ``None`` stands for
      "without group"),
    * it holds a line that draws on the same stock as the changed line: the
      same product, a kit that contains it, a container that carries it
      (:meth:`AvailabilityEngine.competing_products`), or a subrental that
      covers such a line – their traffic lights may have changed,
    * it holds a percentage surcharge – its amount follows the lines it
      refers to (PRD-039),
    * a discount or flat price of a group above the changed line is spread
      over its lines, and one of them has a maximum discount (PRJ-037,
      PER-026, see :func:`_price_family`).

    Besides, the subtotals of all groups above a section shown again go
    along (``PlanningPatch.totals``, PRJ-037): a change in "Licht › Front"
    changes the sum of "Licht".

    Prices are calculated for the whole project, because the totals are part
    of every answer. Availability is the expensive part (it reads the stock
    and the reservations of all other projects), so it is calculated only for
    the lines in the sections shown again – and for the lines elsewhere in
    the project that compete with them, without which their verdicts would
    be wrong (PRJ-042). In a project with 500 lines this is the difference
    between judging 500 lines and a few dozen.

    Args:
        project: The project as it is *after* the change.
        engine: The availability engine to use.
        product_ids: The products of the changed line, before and after.
        group_ids: The groups of the changed line, before and after.

    Returns:
        A partial :class:`Planning` (see ``Planning.partial``) and the patch
        that names the sections to send.

    Example: a cable K-010 is added to the group "Stage". The group "FOH"
    holds a speaker set that contains the same cable. Both groups are part of
    the patch; the group "Lighting" with its spotlights is not – its lines
    are neither judged nor sent.
    """
    groups = list(project.groups.all())
    lines = load_lines(project)
    prices = compute_project_prices(project, lines=lines, groups=groups)
    known_groups = {group.pk for group in groups}

    def draws_on(line: MaterialLine, products: set[int]) -> bool:
        """Whether a line takes from, or covers a shortage of, one of the products."""
        if line.product_id in products or line.covers_product_id in products:
            return True
        return bool(line.covers_line_id and line.covers_line.product_id in products)

    changed = engine.competing_products(product_id for product_id in product_ids if product_id)
    shown: set[int | str | None] = {_SURCHARGES}
    shown.update(group_id for group_id in group_ids if group_id is None or group_id in known_groups)
    for line in lines:
        if line.is_percent_surcharge or draws_on(line, changed):
            shown.add(_section_of(line, known_groups))
    # PRJ-037: a discount or flat price above a changed group can cap lines of other groups below it.
    for section in list(shown):
        if isinstance(section, int):
            shown.update(_price_family(prices, lines, section))

    shown_lines = [line for line in lines if _section_of(line, known_groups) in shown]
    needed: set[int] = set()
    for line in shown_lines:
        needed.update(
            product_id
            for product_id in (
                line.product_id,
                line.covers_product_id,
                line.covers_line.product_id if line.covers_line_id else None,
            )
            if product_id
        )
    competing = engine.competing_products(needed)
    shown_ids = {line.pk for line in shown_lines}
    judged = [line for line in lines if line.pk in shown_ids or draws_on(line, competing)]
    availability = engine.project_availability(project, judged, groups)

    planning = _assemble(project, groups, lines, prices, availability, only=shown_ids)
    planning.partial = True
    totals = _totals_to_send(planning, shown)
    patch = PlanningPatch(
        groups=[group for group in planning.groups if group.group.pk in shown],
        totals=[group for group in planning.groups if group.group.pk in totals],
        ungrouped=None in shown,
    )
    return planning, patch


def _price_family(prices: ProjectPrices, lines: list[MaterialLine], group_id: int) -> set[int]:
    """The groups whose lines can show other figures after a change in this group (PRJ-037, PER-026).

    A discount or flat price is spread over every line below the group that
    gives it. A line with a maximum discount may then be capped – or no
    longer be – when any other line below that group changes. So if a group
    at or above the changed one has a discount or flat price, and a line
    with a maximum discount stands anywhere below the topmost such group,
    every group below it is shown again. Without either, nothing else is.
    """
    group_price = prices.by_group_id[group_id]
    ruled = [group for group in [group_price.group, *group_price.group.ancestors] if group.has_price_rule]
    if not ruled:
        return set()
    family: set[int] = set()
    stack = [prices.by_group_id[ruled[-1].pk]]
    while stack:
        current = stack.pop()
        family.add(current.group.pk)
        stack.extend(current.children)
    limited = any(
        prices.by_line_id[line.pk].max_discount_percent is not None for line in lines if line.group_id in family
    )
    return family if limited else set()


def _totals_to_send(planning: Planning, shown: set[int | str | None]) -> set[int]:
    """The groups whose subtotal with subgroups goes with a patch: every group above a group shown again (PRJ-037).

    A group with subgroups shows that subtotal below its last subgroup; it
    changes with every change of a line anywhere below the group.
    """
    totals: set[int] = set()
    for group in planning.groups:
        if group.group.pk not in shown:
            continue
        for candidate in [group, *group.ancestors]:
            if candidate.children:
                totals.add(candidate.group.pk)
    return totals


def _assemble(
    project: Project,
    groups: list[Group],
    lines: list[MaterialLine],
    prices: ProjectPrices,
    availability: dict[int, LineAvailability],
    *,
    only: set[int] | None = None,
) -> Planning:
    """Put lines, prices and availability verdicts together, section by section.

    Args:
        project: The project.
        groups: All its groups; their order and nesting come from ``prices`` (PRJ-037).
        lines: All lines of the project.
        prices: The prices of the whole project.
        availability: The verdicts by line ID; a line without one counts as
            not checked.
        only: The IDs of the lines to put into the picture; ``None`` takes
            all. Used for a patch, which shows some sections only. The other
            lines still count as "covered by": a subrental can sit in
            another group than the line it covers (PRJ-055).
    """
    short_product_ids = {detail.product_id for verdict in availability.values() for detail in verdict.details}
    products = {
        product.pk: product for product in Product.objects.filter(pk__in=short_product_ids).select_related("unit")
    }

    covered_by: dict[int, list[MaterialLine]] = defaultdict(list)
    for line in lines:
        if line.covers_line_id:
            covered_by[line.covers_line_id].append(line)

    placed = lines if only is None else [line for line in lines if line.pk in only]
    kit_ids = {line.product_id for line in placed if line.product_id and line.product.is_kit}
    components: dict[int, list[KitComponent]] = defaultdict(list)
    if kit_ids:
        for component in KitComponent.objects.filter(kit_id__in=kit_ids).select_related("component"):
            components[component.kit_id].append(component)

    wishes = load_wishes(project, lines, shown=only)
    # PRJ-060: only for lines that hand pieces on (``load_lines`` knows which); usually no query at all.
    passed_on = handed_on([line for line in placed if getattr(line, "hands_on", True)])

    planning = Planning(project=project, prices=prices)
    # PRJ-037: in the order of the planning, each group linked with the one above and the ones below.
    planned_groups = {
        group_prices.group.pk: PlannedGroup(group=group_prices.group, prices=group_prices)
        for group_prices in prices.groups
    }
    for group_prices in prices.groups:
        planned = planned_groups[group_prices.group.pk]
        for child in group_prices.children:
            planned_groups[child.group.pk].parent = planned
            planned.children.append(planned_groups[child.group.pk])
    planning.groups = [planned_groups[group_prices.group.pk] for group_prices in prices.groups]
    for planned_group in planning.groups:
        # PRJ-083: what an alternative group could replace, from the groups at hand.
        target = planned_groups.get(planned_group.group.alternative_to_id)
        planned_group.alternative_to = target.group if target is not None else None
    lines_by_id = {line.pk: line for line in lines}
    planned_by_id: dict[int, PlannedLine] = {}

    for line in placed:
        verdict = availability.get(line.pk, UNCHECKED)
        planned = PlannedLine(
            line=line,
            price=prices.by_line_id[line.pk],
            availability=verdict,
            covered_by=covered_by.get(line.pk, []),
            excess_cover=verdict.excess_cover_total,
            wish=wishes.get(line.pk),
            handed_to=passed_on.get(line.pk, []),
            alternative_to=lines_by_id.get(line.alternative_to_id) if line.alternative_to_id else None,
        )
        planned_by_id[line.pk] = planned
        for detail in verdict.details:
            info = LineStockInfo(
                product=products[detail.product_id],
                quantity=detail.shortage,
                stock=detail.stock,
                firm=detail.firm,
                optional=detail.optional,
                own_project=detail.own_project,
                free=detail.free,
            )
            if detail.shortage > 0:
                planned.shortages.append(info)
            if detail.product_id == line.product_id:
                planned.stock_info = info
        if planned.stock_info is None and verdict.main is not None:
            main = verdict.main
            planned.stock_info = LineStockInfo(
                product=products[main.product_id],
                quantity=main.shortage,
                stock=main.stock,
                firm=main.firm,
                optional=main.optional,
                own_project=main.own_project,
                free=main.free,
            )
        if line.product_id in components:
            planned.components = [
                (component.component, component.quantity * int(line.quantity))
                for component in components[line.product_id]
            ]

        section = _section_of(line, planned_groups)
        if section == _SURCHARGES:
            planning.surcharges.append(planned)
        elif section is None:
            planning.ungrouped.append(planned)
        else:
            planned_groups[section].lines.append(planned)
    # PRJ-084: a subrental that covers a shortage is a part of the line it covers, shown right below it.
    for planned in planned_by_id.values():
        covered = planned_by_id.get(planned.line.covers_line_id) if planned.line.covers_line_id else None
        if covered is not None:
            covered.covering.append(planned)
            planned.is_sub_row = True
    return planning
