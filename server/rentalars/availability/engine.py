# SPDX-License-Identifier: GPL-3.0-or-later
"""The availability calculation: what is free, and when? See catalogue chapter 7.4.

The central rule (VFG-002)
--------------------------
::

    free(product, period) =
        plannable stock
      - highest quantity reserved at the same time within the period

Why the *peak* and not the *sum*: two projects that use the same six cables
one after the other need six cables, not twelve. What matters is how many
pieces are out at the busiest moment of the period asked about.

Example (acceptance scenario 2): the stock is 9. Project P1 is confirmed and
books 6 pieces from the 10th to the 12th. Project P2 asks for the 11th to the
13th. The busiest moment in that period has 6 pieces out, so 3 are free. If
P2 books 4, it is short of 1.

What counts as reserved
-----------------------
* Lines of projects that are confirmed or out reserve **firmly**; lines of
  projects in the status "option" reserve **softly** and are shown separately
  (PRJ-008, VFG-003). Inquiries and finished projects reserve nothing.
* Lines in optional or alternative groups only reserve softly (PRJ-040) –
  also in a subgroup of such a group (PRJ-037) – and so do optional and
  alternative lines (PRJ-075).
* Every reservation is extended by the buffer times of its product (VFG-005).
* A kit reserves its components (VFG-008).
* A reserved container (rack, case) also occupies the loose items inside it
  (VFG-016, VFG-017).
* The part of a line that is covered by a subrental does not touch the own
  stock (VFG-018).
* A sale occupies the stock from its start without end, until the pieces
  have actually been taken out of the stock (PRD-013).
* A blocked period of an item ("in repair until 15 November") occupies one
  piece of its product for that period, firmly (MAT-024).
* A loose item that was taken out of its container for a project
  (MAT-042) is not occupied by that project's container; it is free for
  others during the project.
* Material taken over from another part of the same whole project
  (PRJ-060) goes straight from one stage to the next. The pieces are
  occupied without a gap from the end of the line they come from until the
  end of the taking line, and there is no buffer between the two – they do
  not pass through the warehouse. If the two periods overlap, the pieces
  are counted twice and the overlap shows as a shortage, as it should.

Everything is calculated on demand from the current lines; no reservation
table exists that could get out of step.
"""

from __future__ import annotations

import datetime
import enum
import itertools
from collections import defaultdict
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db.models import Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from rentalars.availability.stock import NO_STOCK, ProductStock, stock_of_products
from rentalars.core.models import SystemSettings
from rentalars.masterdata.models import Category
from rentalars.material.models import ARCHIVED_STATUSES, OPERATIONAL_STATUSES, ConnectionType, MaterialItem
from rentalars.products.models import STOCK_KINDS, Product
from rentalars.products.services import KitStructure, flatten_kit, load_kit_structure
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.models import (
    FIRM_STATUSES,
    SOFT_STATUSES,
    Group,
    MaterialLine,
    Project,
    ProjectStatus,
)

#: Stands for "no end": sold material does not come back. Deliberately not the
#: last moment a date can hold: buffer times are added to period ends, and a
#: day of buffer on top of the very last day would be a date that does not exist.
FAR_FUTURE = datetime.datetime(9000, 1, 1, tzinfo=datetime.UTC)

#: Key under which the result for a not-yet-saved line is returned.
CANDIDATE_KEY = "candidate"

#: Statuses in which a *sale* still occupies stock that was not booked out yet.
_SALE_PENDING_STATUSES = frozenset({ProjectStatus.OUT.value, ProjectStatus.RETURNED.value, ProjectStatus.CLOSED.value})


class Firmness(enum.IntEnum):
    """How binding a reservation is (PRJ-008, VFG-003)."""

    NONE = 0
    SOFT = 1
    FIRM = 2


def firmness_of(project_status: str, *, group_counts: bool = True, is_sale: bool = False) -> Firmness:
    """Decide how firmly a line reserves its material.

    Args:
        project_status: The status of the line's project.
        group_counts: False for lines in optional or alternative groups, and for
            optional or alternative lines (PRJ-040, PRJ-075).
        is_sale: True for lines that sell instead of renting.
    """
    if is_sale and project_status in _SALE_PENDING_STATUSES:
        # Sold pieces are gone. Until they are booked out of the stock, the
        # line keeps them occupied, even if the project is long finished.
        return Firmness.FIRM
    if project_status in FIRM_STATUSES:
        return Firmness.FIRM if group_counts else Firmness.SOFT
    if project_status in SOFT_STATUSES:
        return Firmness.SOFT
    return Firmness.NONE


@dataclass
class Demand:
    """A quantity of one product that is occupied during a time span."""

    product_id: int
    #: Pieces taken from the own stock (after deducting covered pieces).
    quantity: int
    start: datetime.datetime
    end: datetime.datetime
    firmness: Firmness
    project_id: int | None = None
    line_id: int | None = None
    #: How the demand arises: "direct", "kit" or "container".
    via: str = "direct"
    #: Pieces the line needs before deducting the cover by a subrental.
    required: int = 0
    #: Pieces covered by a subrental (VFG-018).
    covered: int = 0
    project_number: str = ""
    project_name: str = ""
    #: The whole project the demand belongs to: its parent, or the project itself (PRJ-047).
    root_project_id: int | None = None


def peak_quantity(demands: Iterable[Demand], window_start: datetime.datetime, window_end: datetime.datetime) -> int:
    """Return the highest quantity occupied at the same time within a window (VFG-002).

    The demands are turned into events – "+6 at the 10th, 08:00" and "-6 at
    the 12th, 18:00" – and walked through in time order while a running total
    is kept. The highest total seen is the peak.

    Times are compared with date *and* time (VFG-004). A return and a start
    at the very same moment do not collide: the return is processed first.

    Example: demands of 6 (10th–12th) and 2 (12th–14th) within the window
    10th–14th give a peak of 6, not 8, because the two never overlap.
    """
    events: list[tuple[datetime.datetime, int]] = []
    for demand in demands:
        start = max(demand.start, window_start)
        end = min(demand.end, window_end)
        if start >= end or demand.quantity <= 0:
            continue
        events.append((start, demand.quantity))
        events.append((end, -demand.quantity))
    # Sorting by (time, change) puts releases (-) before takes (+) at equal times.
    events.sort()
    peak = 0
    running = 0
    for _moment, change in events:
        running += change
        peak = max(peak, running)
    return peak


@dataclass
class ProductAvailability:
    """Answer to "how much of this product is free in this period?" (VFG-011).

    Reads like the catalogue's example "9 stock, 6 firm, 2 optional, 1 free":
    ``stock.plannable``, ``firm``, ``optional`` and ``free_after_optional``.
    """

    product_id: int
    stock: ProductStock
    #: Peak of firm reservations in the period.
    firm: int
    #: What soft reservations (options) add on top of the firm peak.
    optional: int
    #: The reservations that overlap the period, for "who has it?".
    occupiers: list[Demand] = field(default_factory=list)
    #: False for products without own stock (PRD-030); the numbers are then meaningless.
    checked: bool = True

    @property
    def free(self) -> int:
        """Plannable stock minus firm reservations (VFG-002)."""
        return self.stock.plannable - self.firm

    @property
    def free_after_optional(self) -> int:
        """What remains if all options turn into orders (VFG-003)."""
        return self.stock.plannable - self.firm - self.optional


@dataclass
class ProductShortage:
    """How one product of a project line stands: enough, tight or short."""

    product_id: int
    #: Pieces the line needs of this product.
    required: int
    #: Pieces covered by subrental.
    covered: int
    #: Pieces missing after the cover – the open shortage (PRJ-013).
    shortage: int
    #: Pieces that would be missing without any cover.
    shortage_without_cover: int
    stock: int
    #: Firm reservations of other projects at their peak during the line's period.
    firm: int
    #: Soft reservations of other projects on top of that.
    optional: int
    #: Occupied by other lines of the same project.
    own_project: int
    tight: bool = False
    via: str = "direct"
    #: Of ``firm``: what other parts of the same whole project hold firmly at the peak (PRJ-047).
    family: int = 0

    @property
    def from_stock(self) -> int:
        """Pieces this line takes from the own stock."""
        return max(self.required - self.covered, 0)

    @property
    def free(self) -> int:
        """Free pieces for this line, never below zero."""
        return max(self.stock - self.firm - self.optional - self.own_project, 0)

    @property
    def excess_cover(self) -> int:
        """Subrented pieces that are no longer needed (PRJ-056)."""
        return max(self.covered - self.shortage_without_cover, 0)


@dataclass
class LineAvailability:
    """The availability verdict for one project line (PRJ-012)."""

    details: list[ProductShortage] = field(default_factory=list)

    @property
    def status(self) -> str:
        """``unchecked``, ``ok``, ``tight`` or ``short`` – the traffic light of PRJ-012."""
        if not self.details:
            return "unchecked"
        if any(detail.shortage > 0 for detail in self.details):
            return "short"
        if any(detail.tight for detail in self.details):
            return "tight"
        return "ok"

    @property
    def shortages(self) -> list[ProductShortage]:
        """Only the products that are short."""
        return [detail for detail in self.details if detail.shortage > 0]

    @property
    def shortage_total(self) -> int:
        """The sum of missing pieces over all products of the line."""
        return sum(detail.shortage for detail in self.details)

    @property
    def excess_cover_total(self) -> int:
        """Subrented pieces that are no longer needed, over all products (PRJ-056)."""
        return sum(detail.excess_cover for detail in self.details)

    @property
    def main(self) -> ProductShortage | None:
        """The detail to show first: the worst one."""
        if not self.details:
            return None
        return max(self.details, key=lambda detail: (detail.shortage, detail.tight, -detail.free))


UNCHECKED = LineAvailability()


@dataclass(frozen=True)
class _ProductInfo:
    """What the engine needs to know about a product."""

    product_id: int
    tracks_stock: bool
    buffer_before: datetime.timedelta
    buffer_after: datetime.timedelta


@dataclass
class _PlannedLine:
    """A material line reduced to what matters for availability."""

    line_id: int | None
    project_id: int | None
    project_status: str
    product_id: int
    quantity: int
    start: datetime.datetime
    end: datetime.datetime
    is_sale: bool = False
    removed_from_stock: int = 0
    group_counts: bool = True
    order: tuple[int, int, int] = (0, 0, 0)
    project_number: str = ""
    project_name: str = ""
    root_project_id: int | None = None
    #: PRJ-060: the line whose pieces this line takes over, the end of that line, and how many pieces.
    source_line_id: int | None = None
    received_from_end: datetime.datetime | None = None
    received: int = 0
    #: PRJ-060: how many of its pieces later lines take over from this one (see ``_link_takeovers``).
    handed_on: int = 0
    #: PCK-028: pieces booked back into the warehouse early, per product (the line's own, or the components of
    #: a kit), and when the latest of them came back. They are free again from then on.
    taken_back: dict[int, int] = field(default_factory=dict)
    taken_back_at: datetime.datetime | None = None

    @property
    def key(self) -> Any:
        """The key under which results for this line are reported."""
        return self.line_id if self.line_id is not None else CANDIDATE_KEY


def _hours(value: Decimal | None) -> datetime.timedelta | None:
    """Turn a number of hours into a time span; ``None`` stays ``None``."""
    return None if value is None else datetime.timedelta(hours=float(value))


def _merged_blocks(
    blocks: list[tuple[datetime.datetime, datetime.datetime, str, int, int]],
) -> list[tuple[datetime.datetime, datetime.datetime, str, int, int]]:
    """L13: blocks of one item that overlap or touch are one block – an item is one piece, whatever the reasons."""
    by_item: dict[tuple[int, int], list[tuple[datetime.datetime, datetime.datetime, str, int, int]]] = defaultdict(list)
    for block in blocks:
        by_item[(block[4], block[3])].append(block)
    merged = []
    for item_blocks in by_item.values():
        item_blocks.sort(key=lambda block: (block[0], block[1]))
        start, end, reason, number, product_id = item_blocks[0]
        for next_start, next_end, _next_reason, _n, _p in item_blocks[1:]:
            if next_start <= end:
                end = max(end, next_end)
                continue
            merged.append((start, end, reason, number, product_id))
            start, end, reason = next_start, next_end, _next_reason
        merged.append((start, end, reason, number, product_id))
    return merged


class AvailabilityEngine:
    """Calculates availability for products and for the lines of a project.

    One engine object is created per request. It loads reference data (kits,
    categories, contents of containers) once and reuses it for all questions
    of that request, which keeps a planning page with hundreds of lines at a
    handful of database queries (NFA-013, NFA-014).

    Example::

        engine = AvailabilityEngine()
        answer = engine.availability([product.pk], start, end)[product.pk]
        answer.free       # pieces free against firm reservations
    """

    def __init__(self, *, now: datetime.datetime | None = None) -> None:
        self.now = now or timezone.now()
        self._kit_structure: KitStructure | None = None
        self._categories: dict[int, tuple[int | None, Any, Any, bool]] | None = None
        self._defaults: tuple[datetime.timedelta, datetime.timedelta] | None = None
        self._product_info: dict[int, _ProductInfo] = {}
        self._container_index: dict[int, dict[int, dict[int, int]]] | None = None
        self._max_buffer: datetime.timedelta | None = None
        self._flattened: dict[int, dict[int, int]] = {}
        #: For installed items: the chain of containers around them, nearest first (MAT-042).
        self._container_chains: dict[int, list[int]] = {}
        self._extractions: dict[int, dict[tuple[int, int], int]] | None = None
        self._blocks: list[tuple[datetime.datetime, datetime.datetime, str, int, int]] | None = None
        #: Products that consist of several items, ``{product: pieces}``; learned while the container index
        #: and the blocked periods are loaded (no query of its own) – see :meth:`pieces_of`.
        self._pieces: dict[int, int] = {}

    # --- Reference data, loaded once per engine ---------------------------

    def flatten(self, product_id: int) -> dict[int, int]:
        """Resolve a product into its base products; results are remembered."""
        if product_id not in self._flattened:
            self._flattened[product_id] = flatten_kit(product_id, self.kit_structure)
        return self._flattened[product_id]

    @property
    def kit_structure(self) -> KitStructure:
        """Which kit consists of which components."""
        if self._kit_structure is None:
            self._kit_structure = load_kit_structure()
        return self._kit_structure

    def pieces_of(self, product_id: int) -> int:
        """How many items make up one piece of a product (``Product.pieces_per_product``; PRD-052); 1 for most.

        Reservations count products. Two things the engine meets are items,
        though – the loose contents of a container (VFG-016) and the blocked
        periods of single items (MAT-024). They are turned into products with
        this number: the loose contents of a container rounded up (on the safe side),
        a blocked cable takes a 10-pack out of the plan only if the stock of packs gets smaller without it. The number is
        known for the products met in the container index and in the blocks,
        which is where it is asked for.
        """
        return self._pieces.get(product_id, 1)

    def _category_table(self) -> dict[int, tuple[int | None, Any, Any, bool]]:
        """All categories as ``{id: (parent id, buffer before, buffer after, has own stock)}``."""
        if self._categories is None:
            self._categories = {
                pk: (parent_id, before, after, has_own_stock)
                for pk, parent_id, before, after, has_own_stock in Category.objects.values_list(
                    "pk", "parent_id", "buffer_before_hours", "buffer_after_hours", "has_own_stock"
                )
            }
        return self._categories

    def _default_buffers(self) -> tuple[datetime.timedelta, datetime.timedelta]:
        """The system-wide buffer times (VFG-005)."""
        if self._defaults is None:
            system_settings = SystemSettings.load()
            self._defaults = (
                datetime.timedelta(hours=float(system_settings.buffer_before_hours)),
                datetime.timedelta(hours=float(system_settings.buffer_after_hours)),
            )
        return self._defaults

    def product_info(self, product_ids: Iterable[int]) -> dict[int, _ProductInfo]:
        """Return buffer times and stock tracking for products (VFG-005, PRD-030).

        Buffers: the most specific value wins, separately for "before" and
        "after" – the product, then its category and the categories above
        it, then the system default.

        Stock tracking: rental and sale products in a main category that has
        own stock. Everything else (services, transport and surcharges –
        PRJ-053 –, subrental, kits themselves) is not checked.
        """
        missing = {product_id for product_id in product_ids if product_id not in self._product_info}
        if missing:
            categories = self._category_table()
            default_before, default_after = self._default_buffers()
            for pk, kind, category_id, before_hours, after_hours in Product.objects.filter(pk__in=missing).values_list(
                "pk", "kind", "category_id", "buffer_before_hours", "buffer_after_hours"
            ):
                before = _hours(before_hours)
                after = _hours(after_hours)
                has_own_stock = True
                current: int | None = category_id
                seen: set[int] = set()
                while current is not None and current in categories and current not in seen:
                    seen.add(current)
                    parent_id, category_before, category_after, has_own_stock = categories[current]
                    if before is None:
                        before = _hours(category_before)
                    if after is None:
                        after = _hours(category_after)
                    current = parent_id
                # ``has_own_stock`` now holds the value of the main category,
                # the last one visited on the way up.
                self._product_info[pk] = _ProductInfo(
                    product_id=pk,
                    tracks_stock=kind in STOCK_KINDS and has_own_stock,
                    buffer_before=before if before is not None else default_before,
                    buffer_after=after if after is not None else default_after,
                )
        return self._product_info

    def _preload_product_info(self, planned_lines: Iterable[_PlannedLine]) -> None:
        """Load buffers and stock tracking for all products of the given lines with one query.

        ``_demands_of_line`` asks for these values line by line. Without this
        step a project with 500 lines would send 500 small queries.
        """
        self.product_info({base_id for planned in planned_lines for base_id in self.flatten(planned.product_id)})

    def _largest_buffer(self) -> datetime.timedelta:
        """The largest buffer configured anywhere; widens database queries safely."""
        if self._max_buffer is None:
            default_before, default_after = self._default_buffers()
            hours = [default_before.total_seconds() / 3600, default_after.total_seconds() / 3600]
            for model in (Category, Product):
                maxima = model.objects.aggregate(before=Max("buffer_before_hours"), after=Max("buffer_after_hours"))
                hours.extend(float(value) for value in maxima.values() if value is not None)
            self._max_buffer = datetime.timedelta(hours=max(hours))
        return self._max_buffer

    @property
    def container_index(self) -> dict[int, dict[int, dict[int, int]]]:
        """Which products carry which other products inside them (VFG-016, VFG-017).

        Structure: ``{container product: {content product: {container item: count}}}``.

        Only contents that are *planned with their container* are listed:
        loose items and fixed items marked "can be rented on its own"
        (MAT-036, MAT-041). Purely fixed items are left out; they never count
        towards the free stock anyway.

        Example: receiver 0311 (product T-050) lies loosely in case 0600
        (product S-060). The index then contains ``{S-060: {T-050: {0600: 1}}}``,
        which reads: "whoever plans an S-060 may get case 0600 and with it
        one T-050".

        Nesting is followed upwards: an item in a drawer in a rack is
        occupied when the drawer is planned and when the rack is planned.
        """
        if self._container_index is None:
            self._container_index = self._build_container_index()
        return self._container_index

    @property
    def extractions(self) -> dict[int, dict[tuple[int, int], int]]:
        """Contents taken out of their containers for a project (MAT-042).

        Structure: ``{project: {(container item, content product): pieces}}``
        – for every container around the extracted item, so that a receiver
        taken out of a drawer is missing from the drawer and from the rack
        the drawer sits in.
        """
        if self._extractions is None:
            from rentalars.packing.models import Extraction

            self.container_index  # noqa: B018 - building the index fills the chains of the installed items
            result: dict[int, dict[tuple[int, int], int]] = defaultdict(dict)
            rows = list(
                Extraction.objects.filter(project__status__in=FIRM_STATUSES | SOFT_STATUSES).values_list(
                    "project_id", "item_id"
                )
            )
            item_products = dict(
                MaterialItem.objects.with_product_id()
                .filter(pk__in=[item_id for _project_id, item_id in rows])
                .values_list("pk", "effective_product_id")
            )
            for project_id, item_id in rows:
                product_id = item_products.get(item_id)
                if product_id is None:
                    continue
                for container_id in self._container_chains.get(item_id, []):
                    key = (container_id, product_id)
                    result[project_id][key] = result[project_id].get(key, 0) + 1
            self._extractions = dict(result)
        return self._extractions

    def _build_container_index(self) -> dict[int, dict[int, dict[int, int]]]:
        """Load all installed items and derive the index; two queries."""
        fields = (
            "pk",
            "installed_in_id",
            "effective_product_id",
            "connection_type",
            "individually_rentable",
            "status",
            "effective_pieces",
        )
        installed = list(
            MaterialItem.objects.with_product_id()
            .annotate(
                effective_pieces=Coalesce(
                    "product_override__pieces_per_product", "material_model__default_product__pieces_per_product"
                )
            )
            .filter(installed_in__isnull=False)
            .exclude(status__in=ARCHIVED_STATUSES)
            .values_list(*fields)
        )
        nodes: dict[int, tuple[int | None, int | None, bool, bool]] = {}
        for pk, parent_id, product_id, connection, rentable, status, pieces in installed:
            only_with_container = connection == ConnectionType.FIXED and not rentable
            nodes[pk] = (parent_id, product_id, only_with_container, status in OPERATIONAL_STATUSES)
            if product_id is not None and pieces and pieces > 1:
                self._pieces[product_id] = pieces
        outer_ids = {parent_id for _pk, parent_id, *_rest in installed if parent_id not in nodes}
        for pk, product_id, status, pieces in (
            MaterialItem.objects.with_product_id()
            .annotate(
                effective_pieces=Coalesce(
                    "product_override__pieces_per_product", "material_model__default_product__pieces_per_product"
                )
            )
            .filter(pk__in=outer_ids)
            .values_list("pk", "effective_product_id", "status", "effective_pieces")
        ):
            nodes[pk] = (None, product_id, False, status in OPERATIONAL_STATUSES)
            # (pieces per product; PRD-052): a container of several items is met here as well.
            if product_id is not None and pieces and pieces > 1:
                self._pieces[product_id] = pieces

        index: dict[int, dict[int, dict[int, int]]] = {}
        for pk, (parent_id, product_id, only_with_container, operational) in nodes.items():
            if parent_id is None or product_id is None or only_with_container or not operational:
                continue
            # Walk up through all containers around this item.
            seen = {pk}
            current = parent_id
            chain = self._container_chains.setdefault(pk, [])
            while current is not None and current in nodes and current not in seen:
                seen.add(current)
                chain.append(current)
                next_parent, container_product, container_fixed, container_operational = nodes[current]
                # A container that is itself fixed in something else cannot be
                # planned on its own; it is skipped, the walk continues upwards.
                if container_product is not None and container_operational and not container_fixed:
                    counts = index.setdefault(container_product, {}).setdefault(product_id, {})
                    counts[current] = counts.get(current, 0) + 1
                current = next_parent
        return index

    # --- From lines to demands ----------------------------------------------

    def _interval(
        self, planned: _PlannedLine, info: _ProductInfo, *, received: bool = False, handed_on: bool = False
    ) -> tuple[datetime.datetime, datetime.datetime]:
        """Return the occupied time span of a line including buffers (VFG-005).

        Args:
            planned: The line.
            info: Buffers of the product.
            received: For pieces taken over from another line (PRJ-060): they are
                occupied from the end of that line on, without a buffer before.
            handed_on: For pieces a later line takes over (PRJ-060): no buffer after.
        """
        start = planned.start - info.buffer_before
        if received and planned.received_from_end is not None:
            start = min(planned.received_from_end, planned.start)
        if planned.is_sale:
            return start, FAR_FUTURE
        end = planned.end
        if planned.project_status == ProjectStatus.OUT and end < self.now:
            # Overdue: the material is demonstrably still out, and nobody knows when it comes back – it stays
            # occupied until it is booked in.
            return start, FAR_FUTURE
        return start, end if handed_on else end + info.buffer_after

    def _segments(
        self, planned: _PlannedLine, info: _ProductInfo, pieces: int, per_piece: int
    ) -> list[tuple[int, datetime.datetime, datetime.datetime]]:
        """Split the pieces of a line by their way in and out (PRJ-060).

        Most lines have one segment: all pieces from the start minus the buffer
        before until the end plus the buffer after. Pieces taken over from an
        earlier line start at that line's end; pieces handed on to a later
        line end without buffer. Returns ``[(pieces, start, end)]``, never empty.
        """
        if planned.is_sale or (not planned.received and not planned.handed_on):
            return [(pieces, *self._interval(planned, info))]
        received = min(planned.received * per_piece, pieces)
        handed = min(planned.handed_on * per_piece, pieces)
        through = min(received, handed)
        segments = [
            (through, *self._interval(planned, info, received=True, handed_on=True)),
            (received - through, *self._interval(planned, info, received=True)),
            (handed - through, *self._interval(planned, info, handed_on=True)),
            (pieces - max(received, handed), *self._interval(planned, info)),
        ]
        return [segment for segment in segments if segment[0] > 0] or [(pieces, *self._interval(planned, info))]

    def _demands_of_line(
        self,
        planned: _PlannedLine,
        covers: dict[tuple[int | None, int], int],
        allocated: dict[tuple[int | None, int], list[int]],
        wanted: set[int] | None,
    ) -> Iterator[Demand]:
        """Yield everything one line occupies: itself, kit components, container contents.

        Args:
            planned: The line.
            covers: ``{(line id, product id): pieces covered by subrental}``.
            allocated: ``{(line id, product id): [item ids]}`` of items
                already assigned to the line (PCK-021).
            wanted: Only yield demands for these products; ``None`` yields all.
        """
        firmness = firmness_of(planned.project_status, group_counts=planned.group_counts, is_sale=planned.is_sale)
        requirements = {
            base_id: planned.quantity * per_piece for base_id, per_piece in self.flatten(planned.product_id).items()
        }
        is_kit = planned.product_id in self.kit_structure
        infos = self.product_info(requirements.keys())

        for base_id, required in requirements.items():
            info = infos.get(base_id)
            if info is None or not info.tracks_stock:
                continue
            covered = covers.get((planned.line_id, base_id), 0)
            from_stock = required - covered
            if planned.is_sale and base_id == planned.product_id:
                from_stock -= planned.removed_from_stock
            from_stock = max(from_stock, 0)
            # PCK-028: pieces taken back early are done for this project – free for others from their return on.
            back = 0 if planned.is_sale else min(planned.taken_back.get(base_id, 0), from_stock)
            from_stock -= back
            per_piece = required // planned.quantity if planned.quantity else 0
            # PRJ-060: usually one segment; pieces taken over or handed on have their own span.
            segments = self._segments(planned, info, from_stock, per_piece)
            common = {
                "firmness": firmness,
                "project_id": planned.project_id,
                "line_id": planned.line_id,
                "project_number": planned.project_number,
                "project_name": planned.project_name,
                "root_project_id": planned.root_project_id,
            }
            if back and planned.taken_back_at is not None and (wanted is None or base_id in wanted):
                start, end = self._interval(planned, info)
                if min(planned.taken_back_at, end) > start:
                    yield Demand(
                        product_id=base_id,
                        quantity=back,
                        required=back,
                        via="kit" if is_kit else "direct",
                        start=start,
                        end=min(planned.taken_back_at, end),
                        **common,
                    )
            if wanted is None or base_id in wanted:
                for index, (pieces, start, end) in enumerate(segments):
                    # The cover (VFG-018) is told once, with the last segment.
                    cover = covered if index == len(segments) - 1 else 0
                    yield Demand(
                        product_id=base_id,
                        quantity=pieces,
                        required=pieces + cover,
                        covered=cover,
                        via="kit" if is_kit else "direct",
                        start=start,
                        end=end,
                        **common,
                    )
            # VFG-016: loose contents are occupied together with their container.
            extracted = self.extractions.get(planned.project_id, {}) if planned.project_id else {}
            for content_id, counts in self.container_index.get(base_id, {}).items():
                if wanted is not None and content_id not in wanted:
                    continue
                if extracted:
                    # MAT-042: what was taken out for this project does not travel with the container.
                    counts = {
                        container: count - extracted.get((container, content_id), 0)
                        for container, count in counts.items()
                    }
                # (pieces per product; PRD-052): the counts are per container item, a planned container
                # product is as many items as its pieces ("1 × S-600" of 2 cases occupies the contents of both).
                implied = _contents_for(
                    counts, from_stock * self.pieces_of(base_id), allocated.get((planned.line_id, base_id), [])
                )
                if implied <= 0:
                    continue
                # The contents are counted in items; a product of several pieces takes a whole product
                # for each started pack – on the safe side, as for blocked items (``pieces_of``).
                per_content = self.pieces_of(content_id)
                if per_content > 1:
                    implied = -(-implied // per_content)
                content_cover = covers.get((planned.line_id, content_id), 0)
                spread = _spread(implied, [pieces for pieces, _start, _end in segments])
                for index, ((_pieces, start, end), share) in enumerate(zip(segments, spread, strict=True)):
                    cover = content_cover if index == len(segments) - 1 else 0
                    if share <= 0 and not cover:
                        continue
                    yield Demand(
                        product_id=content_id,
                        quantity=max(share - cover, 0),
                        required=share,
                        covered=cover,
                        via="container",
                        start=start,
                        end=end,
                        **common,
                    )

    def products_that_occupy(self, product_ids: Iterable[int]) -> set[int]:
        """Return every product whose lines can occupy the given products.

        A line matters for a product if it plans the product itself, a
        container that carries it as loose content (VFG-016), or a kit that
        contains either of the two (VFG-008).

        Example: for the cable K-010 the result is K-010 itself and the kit
        T-100 "speaker set", because every set takes a cable along.
        """
        direct = set(product_ids)
        for container_product, contents in self.container_index.items():
            if direct & contents.keys():
                direct.add(container_product)
        occupying = set(direct)
        for kit_id in self.kit_structure:
            if direct & self.flatten(kit_id).keys():
                occupying.add(kit_id)
        return occupying

    def competing_products(self, product_ids: Iterable[int]) -> set[int]:
        """Return every product whose lines draw on the same stock as the given products.

        This answers "which lines can change their verdict when a line for
        one of these products changes?". The given products are first broken
        down into what they really take from the shelf – a kit into its
        components, a container also into its loose contents – and then
        :meth:`products_that_occupy` collects everything that takes from the
        same pieces.

        Example: for the kit T-100 "speaker set" (two speakers T-010 and a
        cable K-010) the result contains T-100, T-010 and K-010. A line that
        plans loose cables K-010 therefore competes with every speaker set.
        """
        occupied: set[int] = set()
        for product_id in product_ids:
            occupied.update(self.flatten(product_id))
        for base_id in list(occupied):
            # Loose contents travel with their container and are judged along with it.
            occupied.update(self.container_index.get(base_id, {}))
        return self.products_that_occupy(occupied)

    def collect_demands(
        self, product_ids: set[int], window_start: datetime.datetime, window_end: datetime.datetime
    ) -> dict[int, list[Demand]]:
        """All reservations of some products within a window, per product (for the timelines, VFG-012)."""
        return self._collect_demands(product_ids, window_start, window_end)

    def _collect_demands(
        self,
        product_ids: set[int],
        window_start: datetime.datetime,
        window_end: datetime.datetime,
        *,
        exclude_project_id: int | None = None,
        exclude_project_ids: Collection[int] = (),
    ) -> dict[int, list[Demand]]:
        """Load all reservations that may occupy the given products in a window.

        A line matters for a product if it plans the product itself, a kit
        that contains it, or a container that carries it.

        Args:
            product_ids: The products asked about.
            window_start: Begin of the time span looked at.
            window_end: Its end.
            exclude_project_id: Leave out the lines of this project.
            exclude_project_ids: Leave out the lines of all these projects.
        """
        if not product_ids:
            return defaultdict(list)
        planned_lines = self._planned_from_database(
            product_ids,
            window_start,
            window_end,
            exclude_project_id=exclude_project_id,
            exclude_project_ids=exclude_project_ids,
        )
        _link_takeovers(planned_lines)
        return self._demands_of_lines(planned_lines, product_ids, window_start, window_end)

    def _planned_from_database(
        self,
        product_ids: set[int],
        window_start: datetime.datetime,
        window_end: datetime.datetime,
        *,
        exclude_project_id: int | None = None,
        exclude_project_ids: Collection[int] = (),
    ) -> list[_PlannedLine]:
        """Load the reserving lines that may occupy the given products in a window; see ``_collect_demands``."""
        line_products = self.products_that_occupy(product_ids)

        # Packing builds on this engine, see _load_allocations.
        from rentalars.packing.models import PackEntry, material_out, taken_back_of

        margin = self._largest_buffer()
        # PCK-025: issued material is out whatever the project's status says – a project whose material is
        # only partly out keeps its status until everything is out. Its lines count as "out" here: firm, and
        # still occupied after their end while the material is not back.
        reserving = (
            Q(project__status__in=FIRM_STATUSES | SOFT_STATUSES)
            | Q(is_sale=True, project__status__in=_SALE_PENDING_STATUSES)
            | Q(material_out=True)
        )
        # PRJ-060: a line taken over from another one is occupied from that line's end on.
        overlapping = (Q(start__lt=window_end + margin) | Q(taken_over_from__end__lt=window_end + margin)) & (
            Q(end__gt=window_start - margin)
            | Q(is_sale=True)
            | Q(project__status=ProjectStatus.OUT)
            | Q(material_out=True)
        )
        # PCK-028: what of a line was taken back early comes with the same query.
        rows = (
            MaterialLine.objects.annotate(material_out=material_out("project_id"), **taken_back_of())
            .filter(reserving, overlapping, product_id__in=line_products)
            .order_by()
        )
        if exclude_project_id is not None:
            rows = rows.exclude(project_id=exclude_project_id)
        if exclude_project_ids:
            rows = rows.exclude(project_id__in=exclude_project_ids)
        values = list(
            rows.values(
                "pk",
                "project_id",
                "project__status",
                "material_out",
                "project__number",
                "project__name",
                "project__parent_id",
                "product_id",
                "quantity",
                "start",
                "end",
                "is_sale",
                "stock_removed_quantity",
                "group__kind",
                "group__parent__kind",
                "group__parent__parent__kind",
                "variant",
                "taken_over_from_id",
                "taken_over_from__end",
                "taken_over_from__quantity",
                "taken_back",
                "taken_back_at",
                "kit_taken_back",
            )
        )
        planned_lines = [
            _PlannedLine(
                line_id=row["pk"],
                project_id=row["project_id"],
                project_status=ProjectStatus.OUT if row["material_out"] else row["project__status"],
                product_id=row["product_id"],
                quantity=int(row["quantity"]),
                start=row["start"],
                end=row["end"],
                is_sale=row["is_sale"],
                removed_from_stock=int(row["stock_removed_quantity"]),
                # PRJ-040, PRJ-075: optional groups and optional lines reserve softly – PRJ-037: also
                # the lines in a subgroup of an optional group (at most two levels above, see grouptree).
                group_counts=all(
                    row[kind] in (None, "normal")
                    for kind in ("group__kind", "group__parent__kind", "group__parent__parent__kind")
                )
                and not row["variant"],
                project_number=row["project__number"],
                project_name=row["project__name"],
                root_project_id=row["project__parent_id"] or row["project_id"],
                source_line_id=row["taken_over_from_id"],
                received_from_end=row["taken_over_from__end"],
                received=(
                    min(int(row["quantity"]), int(row["taken_over_from__quantity"])) if row["taken_over_from_id"] else 0
                ),
                taken_back={row["product_id"]: int(row["taken_back"])} if row["taken_back"] else {},
                taken_back_at=row["taken_back_at"],
            )
            for row in values
        ]
        # PCK-028: the components of kits taken back early – one more query, only if there are any.
        kits = {row["pk"] for row in values if row["kit_taken_back"]}
        if kits:
            by_line = {planned.line_id: planned for planned in planned_lines}
            for line_id, product_id, quantity, moment in PackEntry.objects.filter(
                line_id__in=kits, taken_back_quantity__gt=0
            ).values_list("line_id", "product_id", "taken_back_quantity", "taken_back_at"):
                planned = by_line[line_id]
                planned.taken_back[product_id] = int(quantity)
                if moment is not None and (planned.taken_back_at is None or moment > planned.taken_back_at):
                    planned.taken_back_at = moment
        return planned_lines

    def _demands_of_lines(
        self,
        planned_lines: list[_PlannedLine],
        product_ids: set[int],
        window_start: datetime.datetime,
        window_end: datetime.datetime,
    ) -> dict[int, list[Demand]]:
        """Turn reserving lines into demands per product, plus the blocked periods of items (MAT-024)."""
        demands: dict[int, list[Demand]] = defaultdict(list)
        line_ids = [planned.line_id for planned in planned_lines]
        covers = _load_covers(line_ids)
        allocated = _load_allocations(line_ids, set(self.container_index.keys()))

        self._preload_product_info(planned_lines)
        for planned in planned_lines:
            for demand in self._demands_of_line(planned, covers, allocated, product_ids):
                if demand.quantity > 0 and demand.firmness != Firmness.NONE:
                    demands[demand.product_id].append(demand)
        for demand in self._block_demands(product_ids, window_start, window_end):
            demands[demand.product_id].append(demand)
        return demands

    @property
    def blocks(self) -> list[tuple[datetime.datetime, datetime.datetime, str, int, int]]:
        """Blocked periods of items that count towards the plannable stock (MAT-024).

        ``(start, end, reason, inventory number, product)``. Loaded once per
        engine: the table is small – a few blocks per month – and a planning
        page asks for several windows.

        Only items that count towards the plannable stock are taken: a
        defective item or one fixed in a rack is not part of the free stock
        anyway, and blocking it must not take a second piece away.
        """
        if self._blocks is None:
            from rentalars.material.models import ItemBlock

            rows = (
                ItemBlock.objects.filter(item__status__in=OPERATIONAL_STATUSES)
                .filter(
                    Q(item__installed_in__isnull=True)
                    | Q(item__connection_type=ConnectionType.LOOSE)
                    | Q(item__individually_rentable=True)
                )
                .values_list(
                    "start",
                    "end",
                    "reason",
                    "item__inventory_number",
                    "item__product_override_id",
                    "item__material_model__default_product_id",
                    "item__product_override__pieces_per_product",
                    "item__material_model__default_product__pieces_per_product",
                )
            )
            self._blocks = []
            for start, end, reason, number, override_id, model_product_id, override_pieces, model_pieces in rows:
                product_id = override_id or model_product_id
                if product_id is None:
                    continue
                pieces = override_pieces if override_id else model_pieces
                if pieces and pieces > 1:
                    self._pieces[product_id] = pieces
                self._blocks.append((start, end, reason, number, product_id))
            self._blocks = _merged_blocks(self._blocks)
        return self._blocks

    def _block_demands(
        self, product_ids: set[int], window_start: datetime.datetime, window_end: datetime.datetime
    ) -> Iterator[Demand]:
        """Blocked periods of items as firm demands of one piece each (MAT-024)."""
        from rentalars.material.numbering import format_inventory_number

        several: dict[int, list[tuple[datetime.datetime, datetime.datetime, str, int]]] = defaultdict(list)
        for start, end, reason, number, product_id in self.blocks:
            if product_id not in product_ids or start >= window_end or end <= window_start:
                continue
            if self.pieces_of(product_id) > 1:
                several[product_id].append((start, end, reason, number))
                continue
            yield Demand(
                product_id=product_id,
                quantity=1,
                start=start,
                end=end,
                firmness=Firmness.FIRM,
                via="blocked",
                required=1,
                project_number=format_inventory_number(number),
                project_name=reason,
            )
        if several:
            # (pieces per product; PRD-052): the plannable items, to tell how many products a block takes.
            plannable = {
                product_id: stock.plannable_pieces for product_id, stock in stock_of_products(several.keys()).items()
            }
            for product_id, blocked in several.items():
                yield from _block_demands_in_products(
                    product_id, blocked, self.pieces_of(product_id), plannable.get(product_id, 0)
                )

    # --- Questions the rest of the application asks ------------------------

    def availability(
        self,
        product_ids: Iterable[int],
        start: datetime.datetime,
        end: datetime.datetime,
        *,
        exclude_project_id: int | None = None,
    ) -> dict[int, ProductAvailability]:
        """Answer "how much is free?" for several products and one period (VFG-001, API-009).

        Args:
            product_ids: Products to look at. Kits are answered through their
                components (VFG-008): a kit is "free" as often as its scarcest
                component allows.
            start: Begin of the period (with time, VFG-004).
            end: End of the period.
            exclude_project_id: Ignore the reservations of this project –
                "what would be free if this project did not exist?"

        Returns:
            One :class:`ProductAvailability` per requested product.
        """
        requested = list(dict.fromkeys(product_ids))
        base_ids: set[int] = set()
        for product_id in requested:
            base_ids.update(self.flatten(product_id).keys())
        infos = self.product_info(base_ids)
        tracked = {product_id for product_id in base_ids if infos.get(product_id) and infos[product_id].tracks_stock}

        demands = self._collect_demands(tracked, start, end, exclude_project_id=exclude_project_id)
        stocks = stock_of_products(tracked)

        per_base: dict[int, ProductAvailability] = {}
        for product_id in base_ids:
            if product_id not in tracked:
                per_base[product_id] = ProductAvailability(product_id, NO_STOCK, 0, 0, checked=False)
                continue
            product_demands = demands.get(product_id, [])
            firm = peak_quantity((d for d in product_demands if d.firmness == Firmness.FIRM), start, end)
            total = peak_quantity(product_demands, start, end)
            occupiers = sorted(
                (d for d in product_demands if d.start < end and d.end > start),
                key=lambda d: (d.start, d.project_number),
            )
            per_base[product_id] = ProductAvailability(
                product_id=product_id,
                stock=stocks.get(product_id, NO_STOCK),
                firm=firm,
                optional=total - firm,
                occupiers=occupiers,
            )

        result: dict[int, ProductAvailability] = {}
        for product_id in requested:
            if product_id in self.kit_structure:
                result[product_id] = self._kit_availability(product_id, per_base)
            else:
                result[product_id] = per_base[product_id]
        return result

    def _kit_availability(self, kit_id: int, per_base: dict[int, ProductAvailability]) -> ProductAvailability:
        """Derive the availability of a kit from its scarcest component (VFG-008).

        Example: a kit needs 1 speaker and 1 cable. 4 speakers and 9 cables
        are in stock, 3 speakers and 8 cables are reserved. Then 1 speaker
        and 1 cable are free, so 1 kit is free.
        """
        components = self.flatten(kit_id)
        limits_stock: list[int] = []
        limits_free: list[int] = []
        limits_free_after_optional: list[int] = []
        occupiers: list[Demand] = []
        for component_id, per_kit in components.items():
            component = per_base.get(component_id)
            if component is None or not component.checked or per_kit <= 0:
                continue
            limits_stock.append(component.stock.plannable // per_kit)
            limits_free.append(max(component.free, 0) // per_kit)
            limits_free_after_optional.append(max(component.free_after_optional, 0) // per_kit)
            occupiers.extend(component.occupiers)
        if not limits_stock:
            return ProductAvailability(kit_id, NO_STOCK, 0, 0, checked=False)
        sets_in_stock = min(limits_stock)
        sets_free = min(limits_free)
        sets_free_after_optional = min(limits_free_after_optional)
        return ProductAvailability(
            product_id=kit_id,
            stock=ProductStock(total=sets_in_stock, operational=sets_in_stock, plannable=sets_in_stock),
            firm=sets_in_stock - sets_free,
            optional=sets_free - sets_free_after_optional,
            occupiers=occupiers,
        )

    def project_availability(
        self,
        project: Project,
        lines: list[MaterialLine],
        groups: list[Group] | None = None,
    ) -> dict[Any, LineAvailability]:
        """Judge every line of a project – enough, tight or short (PRJ-012, PRJ-013, PRJ-042).

        The lines of the project are processed in their order. Each line is
        checked against the firm reservations of *other* projects plus what
        the *earlier lines of this project* already take. That is how the
        same product in two groups is counted together (PRJ-042).

        Example (acceptance scenario 9): stock 6, the same spotlight with 4
        pieces in each of two groups. The first line fits (shortage 0); for
        the second only 2 are left, so it is short of 2.

        The project's own status does not matter here: an inquiry shows its
        would-be shortages too, so that planning sees them before confirming.

        Args:
            project: The project.
            lines: Its material lines (with ``product`` loaded). A line
                without primary key is treated as a candidate that is not
                saved yet; its result has the key ``CANDIDATE_KEY``.
            groups: Its groups, if already loaded.

        Returns:
            ``{line id: LineAvailability}``. Lines that need no check (free
            lines, services, surcharges, subrentals) get ``UNCHECKED``.
        """
        results: dict[Any, LineAvailability] = {}
        for line in lines:
            results[line.pk if line.pk is not None else CANDIDATE_KEY] = LineAvailability()
        if project.is_finished:
            return results

        # PRJ-037: the groups as a tree – for the order of the planning, and so that a subgroup of an
        # optional group knows it is optional too without asking the database.
        tree = GroupTree(groups if groups is not None else project.groups.all())
        group_by_id = tree.by_id
        planned_lines: list[_PlannedLine] = []
        covers: dict[tuple[int | None, int], int] = defaultdict(int)
        for line in lines:
            if line.covers_line_id and line.covers_product_id:
                covers[(line.covers_line_id, line.covers_product_id)] += int(line.quantity)
            if line.product_id is None:
                continue
            group = group_by_id.get(line.group_id) if line.group_id else None
            counts = (group is None or group.counts_toward_total) and line.counts_toward_total
            planned_lines.append(
                _PlannedLine(
                    line_id=line.pk,
                    project_id=project.pk,
                    # The project is judged as if it were confirmed, see above.
                    project_status=ProjectStatus.CONFIRMED,
                    product_id=line.product_id,
                    quantity=int(line.quantity),
                    start=line.start,
                    end=line.end,
                    is_sale=line.is_sale,
                    removed_from_stock=int(line.stock_removed_quantity),
                    group_counts=counts,
                    order=(0 if counts else 1, tree.index[group.pk] if group else -1, line.position),
                    root_project_id=project.parent_id or project.pk,
                    source_line_id=line.taken_over_from_id,
                )
            )
        _attach_sources(planned_lines, lines)
        allocated = _load_allocations(
            [planned.line_id for planned in planned_lines if planned.line_id], set(self.container_index.keys())
        )

        self._preload_product_info(planned_lines)

        def own_demands() -> dict[int, list[tuple[_PlannedLine, Demand]]]:
            own: dict[int, list[tuple[_PlannedLine, Demand]]] = defaultdict(list)
            for planned in planned_lines:
                for demand in self._demands_of_line(planned, covers, allocated, None):
                    own[demand.product_id].append((planned, demand))
            return own

        own = own_demands()
        if not own:
            return results

        window_start = min(demand.start for entries in own.values() for _planned, demand in entries)
        window_end = max(demand.end for entries in own.values() for _planned, demand in entries)
        product_ids = set(own.keys())
        others_planned = self._planned_from_database(
            product_ids, window_start, window_end, exclude_project_id=project.pk
        )
        if _link_takeovers([*planned_lines, *others_planned]):
            # PRJ-060: own lines that hand pieces on lose their buffer after; judge them with that.
            own = own_demands()
        others = self._demands_of_lines(others_planned, product_ids, window_start, window_end)
        stocks = stock_of_products(own.keys())
        root = project.parent_id or project.pk

        for product_id, entries in own.items():
            plannable = stocks.get(product_id, NO_STOCK).plannable
            others_firm = [d for d in others.get(product_id, []) if d.firmness == Firmness.FIRM]
            others_soft = [d for d in others.get(product_id, []) if d.firmness == Firmness.SOFT]
            family_firm = [d for d in others_firm if d.root_project_id == root]
            taken_by_earlier_lines: list[Demand] = []
            entries.sort(key=lambda entry: (entry[0].order, entry[0].line_id or 0))
            merged: dict[tuple[Any, str], ProductShortage] = {}
            for planned, demand in entries:
                firm_peak = peak_quantity(others_firm, demand.start, demand.end)
                occupied = peak_quantity(others_firm + taken_by_earlier_lines, demand.start, demand.end)
                occupied_with_options = peak_quantity(
                    others_firm + others_soft + taken_by_earlier_lines, demand.start, demand.end
                )
                shortage = _clamp(occupied + demand.quantity - plannable, 0, demand.quantity)
                shortage_without_cover = _clamp(occupied + demand.required - plannable, 0, demand.required)
                detail = ProductShortage(
                    product_id=product_id,
                    required=demand.required,
                    covered=demand.covered,
                    shortage=shortage,
                    shortage_without_cover=shortage_without_cover,
                    stock=plannable,
                    firm=firm_peak,
                    optional=occupied_with_options - occupied,
                    own_project=occupied - firm_peak,
                    tight=shortage == 0 and demand.quantity > 0 and occupied_with_options + demand.quantity > plannable,
                    via=demand.via,
                    family=peak_quantity(family_firm, demand.start, demand.end) if family_firm else 0,
                )
                # PRJ-060: the segments of a line that takes over or hands on are one detail.
                earlier = merged.get((planned.key, demand.via)) if planned.received or planned.handed_on else None
                if earlier is None:
                    merged[(planned.key, demand.via)] = detail
                    results[planned.key].details.append(detail)
                else:
                    _merge_detail(earlier, detail)
                if planned.group_counts:
                    # Lines of optional groups and optional lines do not take
                    # stock away from the lines that count (PRJ-040, PRJ-075).
                    taken_by_earlier_lines.append(demand)
        return results

    def projects_that_may_be_short(self, projects: Iterable[Project]) -> set[int]:
        """Pick out the projects in which a shortage is possible at all (PRJ-057, NFA-012).

        The overview of all open shortages has to look at every running and
        coming project. Judging each of them exactly costs a handful of
        queries per project – with a thousand projects that is thousands of
        queries for a list that is usually short. This method answers a
        cheaper question first, with a fixed number of queries: *can* this
        project be short of anything? Only the projects it returns need the
        exact calculation of :meth:`project_availability`.

        The test errs on the safe side. A project is returned if, for one of
        its products, the stock is smaller than the busiest moment of

        * the firm reservations of all other projects, plus
        * everything the project itself needs of the product – counted in
          full, without deducting subrentals and as if all its lines ran at
          the same time as the busiest moment of the others.

        The exact calculation can only come to a smaller or equal figure, so
        no project with a real shortage is left out. Projects without any
        shortage may be returned; the exact calculation then finds nothing.

        Example: 50 cables in stock. Project A takes 30 from the 10th to the
        12th, project B 30 from the 11th to the 13th, project C 10 in the
        following month; all three are confirmed. A and B are returned (30 +
        30 is more than 50 on the 11th), C is not. If B were only an inquiry,
        it would reserve nothing: A has what it needs, and only B is returned.

        Args:
            projects: The projects to look at, e.g. all that are not finished.

        Returns:
            The IDs of the projects that need the exact calculation.
        """
        from rentalars.packing.models import material_out  # packing builds on this engine, see _load_allocations

        status_of = {project.pk: project.status for project in projects if not project.is_finished}
        if not status_of:
            return set()
        rows = (
            MaterialLine.objects.filter(project_id__in=status_of, product_id__isnull=False)
            .annotate(material_out=material_out("project_id"))  # PCK-025: partly out counts as out
            .order_by()  # the order does not matter here; sorting thousands of lines would only cost time
            .values(
                "pk",
                "project_id",
                "material_out",
                "product_id",
                "quantity",
                "start",
                "end",
                "is_sale",
                "stock_removed_quantity",
                "taken_over_from_id",
                "taken_over_from__end",
            )
        )
        planned_lines = [
            _PlannedLine(
                line_id=row["pk"],
                project_id=row["project_id"],
                # The real status, so that material of an overdue project
                # counts as still out – as the other projects see it.
                project_status=ProjectStatus.OUT if row["material_out"] else status_of[row["project_id"]],
                product_id=row["product_id"],
                quantity=int(row["quantity"]),
                start=row["start"],
                end=row["end"],
                is_sale=row["is_sale"],
                removed_from_stock=int(row["stock_removed_quantity"]),
                # PRJ-060: taken-over pieces are out from the end of the line they come from – on the safe
                # side, all of the line; the buffers of the line handing them on stay.
                source_line_id=row["taken_over_from_id"],
                received_from_end=row["taken_over_from__end"],
                received=int(row["quantity"]) if row["taken_over_from_id"] else 0,
            )
            for row in rows
        ]
        allocated = _load_allocations([planned.line_id for planned in planned_lines], set(self.container_index.keys()))
        self._preload_product_info(planned_lines)

        # own[product][project] = what the project needs of the product, in full.
        own: dict[int, dict[int, list[Demand]]] = defaultdict(lambda: defaultdict(list))
        for planned in planned_lines:
            for demand in self._demands_of_line(planned, {}, allocated, None):
                demand.quantity = max(demand.quantity, demand.required)
                if demand.quantity > 0 and planned.project_id is not None:
                    own[demand.product_id][planned.project_id].append(demand)
        if not own:
            return set()

        every_demand = [
            demand for per_project in own.values() for demands in per_project.values() for demand in demands
        ]
        window_start = min(demand.start for demand in every_demand)
        window_end = max(demand.end for demand in every_demand)
        stocks = stock_of_products(own.keys())

        # Step 1, for all projects at once: where even everything together
        # never exceeds the stock, nobody can be short. "Everything" is what
        # the projects looked at need, plus the firm reservations of all
        # other projects (finished ones with sold goods, for instance).
        of_other_projects = self._collect_demands(
            set(own.keys()), window_start, window_end, exclude_project_ids=status_of.keys()
        )
        scarce: set[int] = set()
        for product_id, per_project in own.items():
            firm = [d for d in of_other_projects.get(product_id, []) if d.firmness == Firmness.FIRM]
            everything = [demand for demands in per_project.values() for demand in demands]
            if peak_quantity(firm + everything, window_start, window_end) > stocks.get(product_id, NO_STOCK).plannable:
                scarce.add(product_id)
        if not scarce:
            return set()

        # Step 2, only for the scarce products: project by project against
        # the firm reservations of all others, as the exact calculation does.
        reservations = self._collect_demands(scarce, window_start, window_end)
        candidates: set[int] = set()
        for product_id in scarce:
            plannable = stocks.get(product_id, NO_STOCK).plannable
            firm = [demand for demand in reservations.get(product_id, []) if demand.firmness == Firmness.FIRM]
            for project_id, demands in own[product_id].items():
                if project_id in candidates:
                    continue
                others_firm = [demand for demand in firm if demand.project_id != project_id]
                start = min(demand.start for demand in demands)
                end = max(demand.end for demand in demands)
                if peak_quantity(others_firm + demands, start, end) > plannable:
                    candidates.add(project_id)
        return candidates

    def line_availability(self, line: MaterialLine) -> LineAvailability:
        """Judge one saved line with as little work as possible (PRJ-012, VFG-007).

        This is the check that runs while the products of a new line are
        locked, so it should be quick even in a project with hundreds of
        lines. The verdict of a line only depends on the lines that compete
        for the same products. Only those are loaded: lines for the same
        products, for kits that contain them, for containers that carry
        them, and the subrentals that cover any of these lines.

        The result is the same as ``project_availability(...)[line.pk]``;
        a test compares the two for every line of the sample data.
        """
        if line.product_id is None or line.pk is None:
            return LineAvailability()
        competing = self.competing_products([line.product_id])
        project = line.project
        lines = list(
            project.material_lines.filter(
                Q(product_id__in=competing) | Q(covers_line__product_id__in=competing) | Q(pk=line.pk)
            ).select_related("product")
        )
        return self.project_availability(project, lines).get(line.pk, LineAvailability())

    def check_candidate(
        self,
        project: Project,
        product: Product,
        quantity: int,
        start: datetime.datetime,
        end: datetime.datetime,
        *,
        exclude_line_id: int | None = None,
        group: Group | None = None,
        is_sale: bool = False,
        lines: list[MaterialLine] | None = None,
        groups: list[Group] | None = None,
    ) -> LineAvailability:
        """Judge a line that is being typed and not saved yet (PRJ-012).

        The candidate is checked as the *last* line of the project, i.e.
        against other projects and all existing lines of this project.

        Args:
            project: The project the line would belong to.
            product: The product being planned.
            quantity: How many pieces.
            start: Begin of the line's period.
            end: End of the line's period.
            exclude_line_id: When an existing line is being edited: its ID,
                so that it is not counted against itself.
            group: The group the line would be in.
            is_sale: Whether the line sells instead of renting.
            lines: The lines of the project with ``product`` loaded, if the caller has them at hand and judges several
                candidates (R3-6) – they are not changed. Default: loaded here.
            groups: The groups of the project, likewise.
        """
        lines = list(project.material_lines.select_related("product")) if lines is None else list(lines)
        if exclude_line_id is not None:
            # An existing line is being edited: judge it with the typed values
            # in its place, so that subrentals covering it stay attached.
            for line in lines:
                if line.pk == exclude_line_id:
                    line.product = product
                    line.group = group
                    line.quantity = Decimal(quantity)
                    line.start = start
                    line.end = end
                    line.is_sale = is_sale
                    return self.project_availability(project, lines, groups).get(exclude_line_id, UNCHECKED)
        candidate = MaterialLine(
            project=project,
            group=group,
            product=product,
            quantity=Decimal(quantity),
            start=start,
            end=end,
            is_sale=is_sale,
            position=10**9,
        )
        results = self.project_availability(project, [*lines, candidate], groups)
        return results.get(CANDIDATE_KEY, UNCHECKED)


def _block_demands_in_products(
    product_id: int,
    blocked: list[tuple[datetime.datetime, datetime.datetime, str, int]],
    pieces: int,
    plannable_pieces: int,
) -> Iterator[Demand]:
    """Blocked items of a product of several pieces as demands for whole products (MAT-024).

    The stock is the plannable items divided by the pieces per product,
    rounded down. A blocked item takes a product out of the plan only if the
    stock gets smaller without it: with 105 cables in packs of ten and one
    blocked, there are still ten packs; with 100 cables there are nine.
    So the period is cut at every start and end of a block, and each section
    demands the difference of the two stocks, with all items and with the
    items not blocked in it. The section names the items and reasons, like
    the demand of a single block.
    """
    from rentalars.material.numbering import format_inventory_number

    moments = sorted({moment for start, end, _reason, _number in blocked for moment in (start, end)})
    for section_start, section_end in itertools.pairwise(moments):
        active = [entry for entry in blocked if entry[0] <= section_start and entry[1] >= section_end]
        if not active:
            continue
        taken = plannable_pieces // pieces - max(plannable_pieces - len(active), 0) // pieces
        if taken <= 0:
            continue  # the blocked items are spare pieces: no product is lost
        yield Demand(
            product_id=product_id,
            quantity=taken,
            start=section_start,
            end=section_end,
            firmness=Firmness.FIRM,
            via="blocked",
            required=taken,
            project_number=", ".join(format_inventory_number(number) for _s, _e, _r, number in active),
            project_name="; ".join(dict.fromkeys(reason for _s, _e, reason, _n in active)),
        )


def _link_takeovers(planned_lines: list[_PlannedLine]) -> bool:
    """Tell every line how many of its pieces later lines take over (PRJ-060).

    Only lines in the list count: a line that takes over but does not reserve
    (its project is an inquiry, say) is not loaded, and the line it would take
    from keeps its buffer.

    Returns:
        Whether any line hands pieces on.
    """
    handed: dict[int, int] = defaultdict(int)
    for planned in planned_lines:
        if planned.source_line_id is not None and planned.received:
            handed[planned.source_line_id] += planned.received
    for planned in planned_lines:
        planned.handed_on = handed.get(planned.line_id, 0) if planned.line_id is not None else 0
    return bool(handed)


def _attach_sources(planned_lines: list[_PlannedLine], lines: list[MaterialLine]) -> None:
    """Fill in end and quantity of the lines that planned lines take over from (PRJ-060).

    One query, and only if a line takes over at all.
    """
    taking = [planned for planned in planned_lines if planned.source_line_id is not None]
    if not taking:
        return
    known = {line.pk: (line.end, line.quantity) for line in lines if line.pk is not None}
    missing = {planned.source_line_id for planned in taking} - known.keys()
    if missing:
        for pk, end, quantity in MaterialLine.objects.filter(pk__in=missing).values_list("pk", "end", "quantity"):
            known[pk] = (end, quantity)
    for planned in taking:
        source = known.get(planned.source_line_id)
        if source is None:
            planned.source_line_id = None
            continue
        planned.received_from_end = source[0]
        planned.received = min(planned.quantity, int(source[1]))


def _merge_detail(detail: ProductShortage, segment: ProductShortage) -> None:
    """Add the verdict for another segment of the same line and product to its detail (PRJ-060)."""
    detail.required += segment.required
    detail.covered += segment.covered
    detail.shortage += segment.shortage
    detail.shortage_without_cover += segment.shortage_without_cover
    detail.firm = max(detail.firm, segment.firm)
    detail.optional = max(detail.optional, segment.optional)
    detail.own_project = max(detail.own_project, segment.own_project)
    detail.family = max(detail.family, segment.family)
    detail.tight = detail.shortage == 0 and (detail.tight or segment.tight)


def _spread(total: int, parts: list[int]) -> list[int]:
    """Divide ``total`` in proportion to ``parts``; the remainder goes to the last part.

    Example: 10 contents over segments of 2 and 3 pieces give 4 and 6.
    """
    if len(parts) == 1:
        return [total]
    whole = sum(parts)
    if whole <= 0:
        return [0] * (len(parts) - 1) + [total]
    shares = [total * part // whole for part in parts[:-1]]
    return [*shares, total - sum(shares)]


def _clamp(value: int, lowest: int, highest: int) -> int:
    """Limit ``value`` to the range from ``lowest`` to ``highest``."""
    return max(lowest, min(value, highest))


def _contents_for(counts: dict[int, int], quantity: int, allocated_items: list[int]) -> int:
    """Return how many content pieces go along with ``quantity`` planned containers (VFG-017).

    Planning works with products, not with items, so it is unknown *which*
    cases will be packed. The calculation is cautious: it assumes the cases
    with the most contents – until concrete items are allocated; then their
    actual contents count.

    Example: three cases, containing 2, 1 and 0 receivers. Two planned cases
    occupy 2 + 1 = 3 receivers. If the case with 0 receivers is already
    allocated, they occupy 0 + 2 = 2.

    Args:
        counts: ``{container item id: number of content pieces in it}``.
        quantity: Number of containers planned.
        allocated_items: IDs of container items already allocated to the line.
    """
    if quantity <= 0:
        return 0
    known = allocated_items[:quantity]
    total = sum(counts.get(item_id, 0) for item_id in known)
    open_slots = quantity - len(known)
    if open_slots > 0:
        remaining = sorted((count for item_id, count in counts.items() if item_id not in known), reverse=True)
        total += sum(remaining[:open_slots])
    return total


#: Above this number of lines the helpers below no longer send the line IDs to
#: the database. A list of ten thousand IDs costs more to write, send and read
#: than fetching the few rows of the whole table and picking the right ones here.
_MANY_LINES = 500


def _load_covers(line_ids: list[int | None]) -> dict[tuple[int | None, int], int]:
    """Load how many pieces of which line are covered by subrentals (VFG-018)."""
    covers: dict[tuple[int | None, int], int] = {}
    ids = {line_id for line_id in line_ids if line_id is not None}
    if not ids:
        return covers
    covering = MaterialLine.objects.filter(covers_line_id__isnull=False, covers_product_id__isnull=False)
    if len(ids) <= _MANY_LINES:
        covering = covering.filter(covers_line_id__in=ids)
    rows = covering.order_by().values("covers_line_id", "covers_product_id").annotate(pieces=Sum("quantity"))
    for row in rows:
        if row["covers_line_id"] in ids:
            covers[(row["covers_line_id"], row["covers_product_id"])] = int(row["pieces"] or 0)
    return covers


def _load_allocations(
    line_ids: list[int | None], container_products: set[int]
) -> dict[tuple[int | None, int], list[int]]:
    """Load which container items are already allocated to which line (VFG-017).

    The packing module owns the allocations; it is imported here, inside the
    function, because packing itself builds on this engine.
    """
    allocated: dict[tuple[int | None, int], list[int]] = defaultdict(list)
    ids = {line_id for line_id in line_ids if line_id is not None}
    if not ids or not container_products:
        return allocated
    from rentalars.packing.models import Allocation

    allocations = Allocation.objects.filter(entry__product_id__in=container_products, returned_at__isnull=True)
    if len(ids) <= _MANY_LINES:
        allocations = allocations.filter(entry__line_id__in=ids)
    for line_id, product_id, item_id in allocations.values_list("entry__line_id", "entry__product_id", "item_id"):
        if line_id in ids:
            allocated[(line_id, product_id)].append(item_id)
    return allocated
