# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic for packlists: rows, ticking, issue and return (chapter 5.8).

The guiding rule is PCK-020: packing, issue and return work completely on the
level of product and quantity. Nobody ever has to scan or pick an individual
item. Where the system can tell by itself which item it must be, it notes
that silently (PCK-021); where it matters to somebody, an item can be chosen
from a list (PCK-022).

Several packlists per project (PCK-008)
    The first packlist of a project is its *main* packlist and takes every
    line that was not given to another one (``LineAssignment``). Each
    packlist is packed, issued and returned on its own.

Issue per article (PCK-025, PCK-018)
    "Issue" books only what is ticked, with the ticked quantities; "issue
    everything" books every row in full, for packing done on paper. After a
    partial issue the packlist is *partly issued*: the rows not issued in
    full can still be ticked and issued later, and returns can be booked as
    soon as anything is out.

Return per piece (PCK-028)
    The return works like the issue: rows are ticked as back
    (``returned_quantity``), and "book the return" (:func:`take_back`) books
    what is ticked back into the warehouse (``taken_back_quantity``). That
    is possible as soon as anything is out, also while the rest of the
    packlist is still packed and issued. The rule is per piece: a piece that
    was taken back is done for this project and is never issued again here;
    what was not issued yet can still be issued. With 10 planned, 6 issued
    and 4 taken back, those 4 are done, the other 4 can still go out, and 2
    of the 6 are still out. Taken-back pieces are free for other projects at
    once (``availability.engine``); an item that came back is "available"
    again, but not chosen or allocated again in this project. Once nothing
    is out any more and nothing waits for its issue, booking the return
    completes it as well.

The project follows its packlists (PCK-025, PCK-019)
    It becomes "out" only once *everything* is out: every packlist with
    material from the warehouse is issued completely. While material is only
    partly out, the project keeps its status (e.g. "confirmed"); issued
    material is out all the same – for the availability, the items and the
    lists of what is out (:func:`material_out`). The project is "returned"
    once nothing is out any more and nothing waits for its issue: the return
    of every packlist is complete; see :func:`_project_after_packlists`.

Changes after packing started (PCK-015)
    With the first tick, every row's text and quantity is noted. A row whose
    quantity changed later, a new row and a row whose line disappeared are
    marked until somebody acknowledges the changes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Prefetch, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext, pgettext

from rentalars.api import webhooks
from rentalars.availability.stock import stock_of_products
from rentalars.core.audit import record_event
from rentalars.core.i18n import plural_of
from rentalars.core.money import decimal_separator
from rentalars.masterdata.models import location_paths
from rentalars.material import installations
from rentalars.material import services as material_services
from rentalars.material.models import ItemStatus, MaterialItem, MaterialModel, TrackingMode
from rentalars.packing.models import (
    OUT_STATUSES,
    Allocation,
    Extraction,
    Handover,
    LineAssignment,
    PackEntry,
    Packlist,
    PacklistStatus,
    material_out,
)
from rentalars.products.models import STOCK_KINDS, Product, ProductKind
from rentalars.products.services import flatten_kit, load_kit_structure
from rentalars.projects.grouptree import ordered_groups
from rentalars.projects.models import FINISHED_STATUSES, Group, MaterialLine, Project, ProjectStatus
from rentalars.projects.wishes import item_label

ZERO = Decimal("0")

#: Product kinds that are physically packed.
PACKABLE_KINDS = STOCK_KINDS | {ProductKind.KIT.value, ProductKind.SUBRENTAL.value}

#: How the rows of a packlist can be ordered (PCK-004).
ORDER_GROUPS, ORDER_CATEGORY, ORDER_LOCATION = "groups", "category", "location"
ORDERS = (ORDER_GROUPS, ORDER_CATEGORY, ORDER_LOCATION)


@dataclass
class ChosenItem:
    """An item allocated to a row: chosen beforehand (PCK-022) or noted at the issue (PCK-021)."""

    allocation_id: int
    item_id: int
    display_id: str
    is_issued: bool
    is_returned: bool
    #: MAT-032: its inspection is overdue.
    inspection_overdue: bool = False
    #: MAT-080: its own spot within the storage location, e.g. "01-A-1" – where to take it from.
    spot: str = ""


@dataclass
class WishedItem:
    """An item the planner wished for on the line of a row: exactly this one is to be packed (piece share)."""

    item_id: int
    display_id: str
    #: Its model, shortly – so that the packer finds the right one among similar items.
    name: str
    #: MAT-080: where to take it from.
    spot: str = ""
    #: Whether it is among the chosen items of the row already.
    is_chosen: bool = False
    #: Why this item cannot go out as things stand ("defective", "with 2027-0004"); empty if it can.
    problem: str = ""


@dataclass
class ContentLine:
    """A piece inside an allocated container, shown indented under it (MAT-037)."""

    depth: int
    display_id: str
    name: str
    #: ``along`` (travels with it), ``extracted`` (stays behind for this project, MAT-042) or ``built_in`` (bulk
    #: material built into it, MAT-040).
    state: str
    #: MAT-040: for ``built_in``, how many pieces; the line is information only and no part of any total.
    quantity: int = 0
    #: MAT-040: for ``built_in``, the unit of the bulk material ("m", "pcs.").
    unit: str = ""


@dataclass
class PassOn:
    """Pieces of a row that a line of a later subproject takes over (PRJ-060)."""

    #: The taking line, with its project.
    line: MaterialLine
    #: How many pieces of the row's product it takes over.
    planned: Decimal
    #: How many of them were handed over so far.
    handed: Decimal = ZERO

    @property
    def project(self) -> Project:
        """The subproject the pieces go on to."""
        return self.line.project

    @property
    def awaiting(self) -> Decimal:
        """What is still to be handed over."""
        return max(self.planned - self.handed, ZERO)


@dataclass
class HandoverBooking:
    """One booked handover into a takeover row (PRJ-060); it can be taken back."""

    handover_id: int
    quantity: Decimal
    at: Any
    by: str
    #: The subproject the pieces came from.
    from_project: Project


@dataclass
class BarSegment:
    """One state in the bar of a packlist (PCK-029)."""

    #: ``back``, ``ticked_back``, ``out``, ``packed`` or ``in_stock`` – also the CSS class.
    name: str
    quantity: Decimal
    #: The share of the bar in percent, with a point, for a CSS width.
    width: str
    #: What the state means, for the legend.
    label: str


@dataclass
class ProgressBar:
    """PCK-029: the pieces of a packlist in five states, for the bar and its legend.

    ===============  ===================================================  ================
    ``back``         booked back into the warehouse, or handed over to    orange
                     another subproject (PRJ-060)
    ``ticked_back``  ticked as back, not booked yet                       orange, hatched
    ``out``          issued and still out (sold pieces stay here)         green
    ``packed``       ticked as packed, not issued yet                     green, hatched
    ``in_stock``     still in the warehouse                               grey
    ===============  ===================================================  ================

    The bar fills from the left in this order, so that it grows as the
    material goes through packing, issue and return.
    """

    back: Decimal = ZERO
    ticked_back: Decimal = ZERO
    out: Decimal = ZERO
    packed: Decimal = ZERO
    in_stock: Decimal = ZERO

    #: The states from left to right.
    NAMES = ("back", "ticked_back", "out", "packed", "in_stock")

    def add(self, other: ProgressBar) -> None:
        """Add the pieces of another row or packlist."""
        for name in self.NAMES:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    @property
    def total(self) -> Decimal:
        """All pieces of the bar."""
        return sum((getattr(self, name) for name in self.NAMES), ZERO)

    @property
    def segments(self) -> list[BarSegment]:
        """The states with pieces, left to right, each with its width and its words for the legend."""
        labels = {
            "back": pgettext("packlist bar", "taken back"),
            "ticked_back": pgettext("packlist bar", "ticked as back"),
            "out": pgettext("packlist bar", "issued"),
            "packed": pgettext("packlist bar", "packed"),
            "in_stock": pgettext("packlist bar", "in the warehouse"),
        }
        total = self.total
        if total <= ZERO:
            return []
        return [
            BarSegment(
                name=name,
                quantity=getattr(self, name),
                width=f"{getattr(self, name) * 100 / total:.2f}",
                label=labels[name],
            )
            for name in self.NAMES
            if getattr(self, name) > ZERO
        ]

    @property
    def summary(self) -> str:
        """The legend as one sentence, for screen readers and the title of the bar."""
        return ", ".join(f"{_number(segment.quantity)} {segment.label}" for segment in self.segments)


@dataclass
class PackRow:
    """One row of a packlist: what to pack, how much, and how far it got (PCK-002)."""

    line: MaterialLine
    product: Product
    group: Group | None
    #: Quantity to take (from the own stock or, for subrentals, from the supplier).
    required: Decimal
    packed: Decimal = ZERO
    issued: Decimal = ZERO
    returned: Decimal = ZERO
    #: The kit line this row was resolved from, if any (PCK-005).
    kit_title: str = ""
    is_subrental: bool = False
    is_sale: bool = False
    #: Bulk material is confirmed by typing the count (PCK-012).
    is_bulk: bool = False
    missing_resolved: bool = False
    missing_note: str = ""
    allocated_ids: list[str] = field(default_factory=list)
    chosen: list[ChosenItem] = field(default_factory=list)
    #: The specific model or item the planner asked for, in words (PRJ-064).
    wish: str = ""
    #: Piece share: the wished items one by one, with their spots; each covers one piece of the line.
    wished: list[WishedItem] = field(default_factory=list)
    #: PCK-015: ``new``, ``changed`` or ``removed`` since packing started; empty if unchanged.
    change: str = ""
    was_required: Decimal | None = None
    #: Notes for the packer: overdue inspections (MAT-032), where loose pieces lie (MAT-042).
    hints: list[str] = field(default_factory=list)
    #: MAT-037: what is inside the allocated container, and what of it stays behind.
    contents: list[ContentLine] = field(default_factory=list)
    #: PCK-006: weight and volume of the required quantity, if known for the product.
    weight_kg: Decimal | None = None
    volume_litres: Decimal | None = None
    #: PCK-004: where the product is kept, for the way through the warehouse.
    location: str = ""
    #: PRJ-060: the line of another subproject whose pieces this row takes over. They do not come from the
    #: warehouse: they are not packed there, and they are "issued" by the handover, not by the issue.
    takeover_from: MaterialLine | None = None
    #: PRJ-060: the handovers booked into this takeover row.
    handovers: list[HandoverBooking] = field(default_factory=list)
    #: PRJ-060: lines of later subprojects that take over pieces of this row.
    passes_on: list[PassOn] = field(default_factory=list)
    #: PRJ-060: pieces of this row handed over to another subproject; they count as back here.
    handed_over: Decimal = ZERO
    #: PCK-028: booked back into the warehouse; ``returned`` is what is ticked as back.
    taken_back: Decimal = ZERO
    #: PCK-027: when the packed and the returned quantity last changed.
    packed_changed_at: Any = None
    returned_changed_at: Any = None
    #: PCK-027: the server-side version of the two ticked quantities (``PackEntry.version``).
    version: int = 0
    #: How many items make up one piece of the product ("10-pack"); the quantities of the row count products.
    pieces_per_unit: int = 1

    @property
    def open_wished(self) -> list[WishedItem]:
        """Piece share: the wished items that are not among the chosen ones yet – the packer looks for them."""
        return [wished for wished in self.wished if not wished.is_chosen]

    @property
    def consists_of_pieces(self) -> bool:
        """Whether one piece of this row stands for several items – then ten items are chosen for each."""
        return self.pieces_per_unit > 1

    @property
    def pieces_required(self) -> int:
        """The items the row needs in all: its quantity times the items per piece."""
        return int(self.required) * self.pieces_per_unit

    @property
    def pieces_chosen(self) -> int:
        """The items chosen or noted for the row so far."""
        return len(self.chosen)

    @property
    def units_chosen(self) -> int:
        """For how many pieces of the row all their items are chosen – a piece with fewer is not complete."""
        return min(self.pieces_chosen // self.pieces_per_unit, int(self.required))

    @property
    def pieces_missing_for_next(self) -> int:
        """Items chosen towards the next piece of the row (0 to one less than its items per piece)."""
        if self.units_chosen >= int(self.required):
            return 0
        return self.pieces_chosen % self.pieces_per_unit

    @property
    def key(self) -> str:
        """Identifies the row in forms and API calls: ``<line id>-<product id>``."""
        return f"{self.line.pk}-{self.product.pk}"

    @property
    def title(self) -> str:
        """The text printed on the packlist."""
        if self.kit_title:
            return self.product.name  # a component of a kit is named by itself
        return self.line.title

    @property
    def is_takeover(self) -> bool:
        """Whether the pieces come from another subproject instead of the warehouse (PRJ-060)."""
        return self.takeover_from is not None

    @property
    def is_customer_material(self) -> bool:
        """PRJ-096: the customer's own material, stored here and taken along – packed and issued as usual."""
        return self.product.owner_id is not None

    @property
    def is_packed(self) -> bool:
        """Whether the whole required quantity is ticked – for a takeover: handed over (PRJ-060)."""
        if self.is_takeover:
            return self.required > ZERO and self.issued >= self.required
        return self.required > ZERO and self.packed >= self.required

    @property
    def is_fully_issued(self) -> bool:
        """Whether the whole required quantity went out (PCK-018)."""
        return self.issued >= self.required

    @property
    def to_issue(self) -> Decimal:
        """What is still to go out of the warehouse for this row; nothing for a takeover (PRJ-060)."""
        if self.is_takeover:
            return ZERO
        return max(self.required - self.issued, ZERO)

    @property
    def ready_to_issue(self) -> Decimal:
        """PCK-025: what is ticked and not issued yet – what "issue" books for this row."""
        if self.is_takeover:
            return ZERO
        return max(min(self.packed, self.required) - self.issued, ZERO)

    @property
    def is_issued_in_full(self) -> bool:
        """PCK-025: a row from the warehouse that went out completely; it is no longer packed."""
        return not self.is_takeover and self.required > ZERO and self.issued >= self.required

    @property
    def awaiting_handover(self) -> Decimal:
        """PRJ-060: pieces of a takeover row that have not arrived from the other subproject yet."""
        if not self.is_takeover:
            return ZERO
        return max(self.required - self.issued, ZERO)

    @property
    def handover_pending(self) -> Decimal:
        """PRJ-060: pieces of this row that later subprojects take over and that were not handed over yet."""
        return sum((passing.awaiting for passing in self.passes_on), ZERO)

    @property
    def missing(self) -> Decimal:
        """Issued but neither returned nor handed over to another subproject (PCK-016, PRJ-060).

        Sold material never comes back.
        """
        if self.is_sale:
            return ZERO
        return max(self.issued - self.returned - self.handed_over, ZERO)

    @property
    def back(self) -> Decimal:
        """What counts as back for this row: returned to the warehouse or handed over (PRJ-060)."""
        return min(self.returned + self.handed_over, self.issued)

    @property
    def returnable(self) -> Decimal:
        """The most that can come back to the warehouse: what was issued and not handed over (PRJ-060)."""
        return max(self.issued - self.handed_over, ZERO)

    @property
    def ready_to_take_back(self) -> Decimal:
        """PCK-028: what is ticked as back and not booked yet – what "book the return" books for this row."""
        if self.is_sale:
            return ZERO
        return max(min(self.returned, self.returnable) - self.taken_back, ZERO)

    @property
    def still_out(self) -> Decimal:
        """PCK-028: what is out by the books – issued, neither taken back nor handed over. Sold pieces never are."""
        if self.is_sale:
            return ZERO
        return max(self.issued - self.taken_back - self.handed_over, ZERO)

    @property
    def is_taken_back_in_full(self) -> bool:
        """PCK-028: everything issued of this row is booked back (or went on to another subproject)."""
        return not self.is_sale and self.issued > ZERO and self.still_out == ZERO

    @property
    def bar(self) -> ProgressBar:
        """PCK-029: the pieces of this row in the five states of the packlist bar."""
        base = self.required
        issued = min(self.issued, base)
        if self.is_takeover:
            # PRJ-060: pieces that have not arrived from the other subproject are not in this warehouse.
            base = issued
        handed = min(self.handed_over, issued)
        taken = ZERO if self.is_sale else min(self.taken_back, issued - handed)
        ticked = ZERO if self.is_sale else max(min(max(self.returned, self.taken_back), issued - handed) - taken, ZERO)
        packed = ZERO if self.is_takeover else max(min(self.packed, base) - issued, ZERO)
        return ProgressBar(
            back=taken + handed,
            ticked_back=ticked,
            out=issued - handed - taken - ticked,
            packed=packed,
            in_stock=max(base - issued - packed, ZERO),
        )

    @property
    def is_returned(self) -> bool:
        """Whether everything issued is back, or the rest was clarified (PCK-019)."""
        return self.missing == ZERO or self.missing_resolved

    @property
    def return_state(self) -> str:
        """Where the row stands once the material is out (PCK-016, PCK-023).

        ==============  ========================================================
        ``not_issued``  nothing of this row went out
        ``sold``        sold material; it does not come back
        ``back``        everything issued is back
        ``clarified``   something is missing and it was noted why (PCK-019)
        ``partial``     part of it is back, the rest is not
        ``out``         nothing is back yet
        ==============  ========================================================

        ``out`` is the normal state while a project runs and is not a
        problem: material that was issued an hour ago is not "missing". Only
        ``partial`` asks for attention by itself – somebody counted and came
        up short. Whether an ``out`` row is a problem shows when the return
        is to be completed.
        """
        if self.issued <= ZERO:
            return "not_issued"
        if self.is_sale:
            return "sold"
        if self.missing == ZERO:
            return "back"
        if self.missing_resolved:
            return "clarified"
        return "partial" if self.returned > ZERO else "out"


@dataclass
class RemovedRow:
    """A row that was on the packlist when packing started and is gone now (PCK-015)."""

    entry_id: int
    title: str
    article_number: str
    was_required: Decimal | None
    packed: Decimal


@dataclass
class PackSection:
    """The rows of one group, category or storage location (PRJ-014, PCK-004)."""

    group: Group | None
    rows: list[PackRow] = field(default_factory=list)
    title: str = ""

    @property
    def weight_kg(self) -> Decimal:
        """The known weight of the section's rows from the warehouse (PCK-006, PRJ-060)."""
        return sum((row.weight_kg for row in self.rows if row.weight_kg is not None and not row.is_takeover), ZERO)


@dataclass
class PackOverview:
    """A packlist prepared for display, PDF and API."""

    packlist: Packlist
    sections: list[PackSection]
    order: str = ORDER_GROUPS
    removed: list[RemovedRow] = field(default_factory=list)
    #: MAT-042: pieces taken out of their containers for this project, as text.
    extracted: list[str] = field(default_factory=list)

    @property
    def rows(self) -> list[PackRow]:
        """All rows in display order."""
        return [row for section in self.sections for row in section.rows]

    @property
    def warehouse_rows(self) -> list[PackRow]:
        """The rows packed and issued in the warehouse: all but the takeovers from other subprojects (PRJ-060)."""
        return [row for row in self.rows if not row.is_takeover]

    @property
    def takeover_rows(self) -> list[PackRow]:
        """The rows whose pieces come from another subproject (PRJ-060)."""
        return [row for row in self.rows if row.is_takeover]

    @property
    def takeover_total(self) -> Decimal:
        """Pieces that come from other subprojects instead of the warehouse (PRJ-060)."""
        return sum((row.required for row in self.takeover_rows), ZERO)

    @property
    def awaiting_handover_total(self) -> Decimal:
        """Pieces of takeover rows that have not arrived yet (PRJ-060)."""
        return sum((row.awaiting_handover for row in self.rows), ZERO)

    @property
    def handed_over_total(self) -> Decimal:
        """Pieces of this packlist that went on to another subproject (PRJ-060)."""
        return sum((row.handed_over for row in self.rows), ZERO)

    @property
    def required_total(self) -> Decimal:
        """Sum of all quantities to pack in the warehouse; takeovers are not packed there (PRJ-060)."""
        return sum((row.required for row in self.warehouse_rows), ZERO)

    @property
    def packed_total(self) -> Decimal:
        """Sum of all quantities already ticked."""
        return sum((min(row.packed, row.required) for row in self.warehouse_rows), ZERO)

    @property
    def progress_percent(self) -> int:
        """Packing progress from 0 to 100 (PCK-009)."""
        if self.required_total == ZERO:
            return 0
        return int(self.packed_total * 100 / self.required_total)

    @property
    def issued_total(self) -> Decimal:
        """Sum of the quantities that went out and are expected back."""
        return sum((row.issued for row in self.rows if not row.is_sale), ZERO)

    @property
    def returned_total(self) -> Decimal:
        """Sum of the quantities that are back – in the warehouse or handed over to another subproject (PRJ-060)."""
        return sum((row.back for row in self.rows if not row.is_sale), ZERO)

    @property
    def return_percent(self) -> int:
        """Return progress from 0 to 100."""
        if self.issued_total == ZERO:
            return 0
        return int(self.returned_total * 100 / self.issued_total)

    @property
    def taken_back_total(self) -> Decimal:
        """PCK-028: what is booked back into the warehouse."""
        return sum((min(row.taken_back, row.issued) for row in self.rows if not row.is_sale), ZERO)

    @property
    def ready_back_total(self) -> Decimal:
        """PCK-028: what is ticked as back and not booked yet – what "book the return" books."""
        return sum((row.ready_to_take_back for row in self.rows), ZERO)

    @property
    def still_out_total(self) -> Decimal:
        """PCK-028: what is out by the books – issued, neither taken back nor handed over."""
        return sum((row.still_out for row in self.rows), ZERO)

    @property
    def bar(self) -> ProgressBar:
        """PCK-029: all pieces of the packlist in the five states of its bar."""
        total = ProgressBar()
        for row in self.rows:
            total.add(row.bar)
        return total

    @property
    def missing_rows(self) -> list[PackRow]:
        """Rows with parts that did not come back and are not clarified (PCK-016)."""
        return [row for row in self.rows if row.missing > ZERO and not row.missing_resolved]

    @property
    def out_total(self) -> Decimal:
        """How many pieces are still out and not clarified."""
        return sum((row.missing for row in self.missing_rows), ZERO)

    @property
    def not_issued_total(self) -> Decimal:
        """What is still in the warehouse after a partial issue (PCK-018)."""
        return sum((row.to_issue for row in self.rows), ZERO)

    @property
    def warehouse_issued_total(self) -> Decimal:
        """PCK-025: how many of the pieces to take from the warehouse are out – sold ones included."""
        return sum((min(row.issued, row.required) for row in self.warehouse_rows), ZERO)

    @property
    def ready_total(self) -> Decimal:
        """PCK-025: what is ticked and not issued yet – what "issue" books."""
        return sum((row.ready_to_issue for row in self.warehouse_rows), ZERO)

    @property
    def is_all_ticked(self) -> bool:
        """Whether every row from the warehouse is ticked in full; "issue everything" then books the same."""
        return all(row.is_packed for row in self.warehouse_rows)

    @property
    def has_changes(self) -> bool:
        """Whether the planning changed since packing started (PCK-015)."""
        return bool(self.removed) or any(row.change for row in self.rows)

    @property
    def weight_kg(self) -> Decimal:
        """The known weight of all rows from the warehouse (PCK-006); takeovers do not go on its truck (PRJ-060)."""
        return sum((row.weight_kg for row in self.warehouse_rows if row.weight_kg is not None), ZERO)

    @property
    def volume_litres(self) -> Decimal:
        """The known volume of all rows from the warehouse (PCK-006, PRJ-060)."""
        return sum((row.volume_litres for row in self.warehouse_rows if row.volume_litres is not None), ZERO)

    @property
    def rows_without_weight(self) -> int:
        """How many rows have no weight – the sum is then a lower bound."""
        return sum(1 for row in self.warehouse_rows if row.weight_kg is None)


# --- The packlists of a project (PCK-001, PCK-008) ------------------------------------------------


def get_packlist(project: Project) -> Packlist:
    """Return the main packlist of a project, creating it on first use (PCK-001)."""
    packlist = project.packlists.order_by("id").first()
    if packlist is None:
        packlist = Packlist(project=project)
        packlist.save()
    return packlist


def ensure_main_packlists(projects: list[Project]) -> None:
    """Give each project of the list that has no packlist yet its main packlist (PCK-001, PCK-026).

    What :func:`get_packlist` does for one project, for many at once in a
    few queries – logged in the change log like a packlist created one by one.
    """
    from rentalars.core.audit import create_in_bulk

    having = set(Packlist.objects.filter(project__in=projects).values_list("project_id", flat=True).distinct())
    create_in_bulk([Packlist(project=project) for project in projects if project.pk not in having])


def packlists_of(project: Project) -> list[Packlist]:
    """All packlists of a project, the main one first."""
    get_packlist(project)
    return list(project.packlists.order_by("id"))


def is_main(packlist: Packlist) -> bool:
    """Whether this is the project's first packlist, which takes the lines given to no other."""
    return not Packlist.objects.filter(project_id=packlist.project_id, pk__lt=packlist.pk).exists()


def lines_of(packlist: Packlist) -> Any:
    """The material lines that belong on a packlist (PCK-008)."""
    lines = packlist.project.material_lines.filter(product__isnull=False)
    if is_main(packlist):
        return lines.filter(packlist_assignment__isnull=True)
    return lines.filter(packlist_assignment__packlist=packlist)


def packlist_of_line(line: MaterialLine) -> Packlist:
    """The packlist a line is packed on."""
    assignment = LineAssignment.objects.filter(line=line).select_related("packlist").first()
    return assignment.packlist if assignment else get_packlist(line.project)


@transaction.atomic
def create_packlist(
    project: Project, *, title: str, loading_at: Any = None, note: str = "", vehicle_line: Any = None
) -> Packlist:
    """Add a packlist to a project – per truck, trade or loading date (PCK-008).

    It starts empty; lines are given to it with :func:`assign_lines`. Since
    It may name the vehicle it is loaded into (LOG-001, a vehicle booked
    in the project's logistics).

    Raises:
        ValidationError: No title, the project is finished, or the vehicle is booked in another project.
    """
    get_packlist(project)
    if not (title or "").strip():
        raise ValidationError({"title": _("Give the packing list a title, e.g. “Truck 2”.")})
    if project.status in {ProjectStatus.CANCELLED, ProjectStatus.CLOSED, ProjectStatus.RETURNED}:
        raise ValidationError(_("The project is finished."))
    if vehicle_line is not None and vehicle_line.project_id != project.pk:
        raise ValidationError({"vehicle_line": _("Choose a vehicle booked in this project.")})
    packlist = Packlist(
        project=project,
        title=title.strip()[:120],
        loading_at=loading_at,
        note=(note or "")[:250],
        vehicle_line=vehicle_line,
    )
    packlist.full_clean()
    packlist.save()
    record_event(packlist, "packlist.created", {"title": packlist.title})
    return packlist


def update_packlist(packlist: Packlist, **fields: Any) -> Packlist:
    """Change title, loading time or note of a packlist – and the vehicle it is loaded into.

    LOG-001: ``vehicle_line`` is a vehicle booked in the project's logistics,
    or ``None``; the packing list names it as a hint, nothing else follows.

    Raises:
        ValidationError: The vehicle is booked in another project.
    """
    for name in ("title", "loading_at", "note"):
        if name in fields:
            setattr(packlist, name, fields[name] if fields[name] is not None or name == "loading_at" else "")
    if "vehicle_line" in fields:
        vehicle_line = fields["vehicle_line"]
        if vehicle_line is not None and vehicle_line.project_id != packlist.project_id:
            raise ValidationError({"vehicle_line": _("Choose a vehicle booked in this project.")})
        packlist.vehicle_line = vehicle_line
    packlist.full_clean()
    packlist.save()
    return packlist


@transaction.atomic
def delete_packlist(packlist: Packlist) -> None:
    """Remove a further packlist; its lines go back to the main packlist.

    Raises:
        ValidationError: It is the main packlist, or material of it was issued.
    """
    if is_main(packlist):
        raise ValidationError(_("The first packing list of a project cannot be deleted."))
    if packlist.is_issued:
        raise ValidationError(_("Material of this packing list was issued. It cannot be deleted."))
    record_event(packlist.project, "packlist.deleted", {"title": packlist.label})
    packlist.delete()


@transaction.atomic
def assign_lines(packlist: Packlist, line_ids: list[int], *, user: Any = None) -> int:
    """Put lines on a packlist (PCK-008). Returns how many moved.

    Ticks of the moved lines on their old packlist are dropped; a line whose
    material is already out stays where it is.

    Raises:
        ValidationError: A line belongs to another project, or its material
            was issued on its current packlist.
    """
    project = packlist.project
    lines = list(project.material_lines.filter(pk__in=line_ids))
    if len(lines) != len(set(line_ids)):
        raise ValidationError(_("Some lines do not belong to this project."))
    target_is_main = is_main(packlist)
    moved = 0
    for line in lines:
        current = packlist_of_line(line)
        if current.pk == packlist.pk:
            continue
        if PackEntry.objects.filter(packlist=current, line=line, issued_quantity__gt=0).exists():
            raise ValidationError(
                _("%(line)s was already issued on “%(packlist)s” and stays there.")
                % {"line": line.title, "packlist": current.label}
            )
        PackEntry.objects.filter(packlist=current, line=line).delete()
        if target_is_main:
            LineAssignment.objects.filter(line=line).delete()
        else:
            LineAssignment.objects.update_or_create(line=line, defaults={"packlist": packlist})
        moved += 1
    if moved:
        record_event(packlist, "packlist.lines_moved", {"count": moved, "title": packlist.label})
    return moved


def bulk_product_ids(product_ids: set[int]) -> set[int]:
    """Return those products whose stock is kept as bulk quantity (MAT-005)."""
    if not product_ids:
        return set()
    return set(
        MaterialModel.objects.filter(default_product_id__in=product_ids, tracking_mode=TrackingMode.BULK).values_list(
            "default_product_id", flat=True
        )
    )


# --- Building the packlist --------------------------------------------------


def build_overview(packlist: Packlist, *, order: str = ORDER_GROUPS, with_contents: bool = False) -> PackOverview:
    """Derive the rows of a packlist from the project's material lines (PCK-002).

    Rules:

    * Only physical things are packed: rental and sale products, kits and
      subrentals. Services, surcharges and free lines do not appear.
    * Kits are resolved into their components (PCK-005).
    * Of each line, only the part that comes from the own stock is listed;
      the part covered by a subrental appears as the subrental's own row,
      marked as such (PRJ-018, PRJ-055).
    * Lines in optional or alternative groups are left out: nothing is
      reserved for them (PRJ-040) – nor for the lines of their subgroups
      (PRJ-037). The same holds for optional and
      alternative lines (PRJ-075): they are packed once the customer chose
      them and they count – until then they are not on the packlist.
    * Prices never appear (PCK-007); a row does not even carry them.

    Args:
        packlist: The packlist.
        order: ``groups`` (as planned), ``category`` or ``location`` (the
            way through the warehouse, PCK-004).
        with_contents: List what is inside allocated containers (MAT-037).
    """
    project = packlist.project
    # PRJ-037: the groups in the order of the planning, a subgroup after its parent; the parents are
    # cached, so that "Licht › Front" and the kind inherited from above cost no query.
    groups = ordered_groups(project.groups.all())
    group_by_id = {group.pk: group for group in groups}
    lines = list(
        lines_of(packlist)
        .select_related(
            "product",
            "product__unit",
            "product__category",
            "unit",
            "supplier",
            "preferred_model",
            "preferred_item__material_model",
            "taken_over_from__project",
        )
        .prefetch_related(
            # Piece share: a line can wish for several items.
            Prefetch("further_preferred_items", queryset=MaterialItem.objects.select_related("material_model"))
        )
        .order_by("position", "id")
    )
    structure = load_kit_structure()

    covers: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    for covering in project.material_lines.filter(covers_line__isnull=False, covers_product__isnull=False).values(
        "covers_line_id", "covers_product_id", "quantity"
    ):
        covers[(covering["covers_line_id"], covering["covers_product_id"])] += covering["quantity"]

    component_ids: set[int] = set()
    for line in lines:
        if line.product.is_kit:
            component_ids.update(flatten_kit(line.product_id, structure).keys())
    components = {
        product.pk: product
        for product in Product.objects.filter(pk__in=component_ids).select_related("unit", "category")
    }

    entries = {(entry.line_id, entry.product_id): entry for entry in packlist.entries.select_related("product")}
    allocations: dict[int, list[Allocation]] = defaultdict(list)
    for allocation in (
        Allocation.objects.filter(entry__packlist=packlist, with_container__isnull=True)
        .select_related("item")
        .order_by("item__inventory_number")
    ):
        allocations[allocation.entry_id].append(allocation)

    sections: dict[int | None, PackSection] = {None: PackSection(group=None)}
    for group in groups:
        if group.counts_toward_total:
            sections[group.pk] = PackSection(group=group, title=group.path)

    rows: list[PackRow] = []
    seen_keys: set[tuple[int, int]] = set()
    for line in lines:
        group = group_by_id.get(line.group_id) if line.group_id else None
        if group is not None and not group.counts_toward_total:
            continue
        if not line.counts_toward_total:
            continue  # PRJ-075: optional and alternative lines are not packed
        if line.product.kind not in PACKABLE_KINDS:
            continue
        section = sections[group.pk if group else None]
        if line.product.is_kit:
            parts = [
                (components[product_id], line.quantity * per_kit)
                for product_id, per_kit in flatten_kit(line.product_id, structure).items()
                if product_id in components and components[product_id].kind in STOCK_KINDS
            ]
            kit_title = f"{line.quantity_display} × {line.title}"
        else:
            parts = [(line.product, line.quantity)]
            kit_title = ""
        for product, quantity in parts:
            required = max(quantity - covers.get((line.pk, product.pk), ZERO), ZERO)
            if required == ZERO:
                continue
            row = PackRow(
                line=line,
                product=product,
                group=group,
                required=required,
                pieces_per_unit=product.pieces_per_product,
                kit_title=kit_title,
                is_subrental=line.is_subrental,
                is_sale=line.is_sale,
                wish=_wish_text(line),
            )
            entry = entries.get((line.pk, product.pk))
            if entry is not None:
                row.packed = entry.packed_quantity
                row.issued = entry.issued_quantity
                row.returned = entry.returned_quantity
                row.taken_back = entry.taken_back_quantity
                row.packed_changed_at = entry.packed_changed_at
                row.returned_changed_at = entry.returned_changed_at
                row.version = entry.version
                row.handed_over = entry.handed_over_quantity
                row.missing_resolved = entry.missing_resolved
                row.missing_note = entry.missing_note
                row.chosen = [
                    ChosenItem(
                        allocation_id=allocation.pk,
                        item_id=allocation.item_id,
                        display_id=allocation.item.display_id,
                        is_issued=allocation.issued_at is not None,
                        is_returned=allocation.returned_at is not None,
                        spot=allocation.item.effective_storage_spot,
                    )
                    for allocation in allocations.get(entry.pk, [])
                ]
                row.allocated_ids = [chosen.display_id for chosen in row.chosen if chosen.is_issued]
            _add_wished_items(row)
            if packlist.packing_started_at is not None:
                if entry is None or entry.required_snapshot is None:
                    row.change = "new"
                elif entry.required_snapshot != required:
                    row.change = "changed"
                    row.was_required = entry.required_snapshot
            section.rows.append(row)
            rows.append(row)
            seen_keys.add((line.pk, product.pk))

    removed = [
        RemovedRow(
            entry_id=entry.pk,
            title=entry.title_snapshot or entry.product.name,
            article_number=entry.product.article_number,
            was_required=entry.required_snapshot,
            packed=entry.packed_quantity,
        )
        for key, entry in entries.items()
        if key not in seen_keys
        and entry.issued_quantity == ZERO
        and (entry.required_snapshot is not None or entry.packed_quantity > ZERO)
    ]

    bulk_ids = bulk_product_ids({row.product.pk for row in rows})
    for row in rows:
        row.is_bulk = row.product.pk in bulk_ids
    _add_takeovers(project, rows, entries, structure)
    _add_weights(rows)
    extracted = _add_hints(project, rows, with_contents=with_contents)

    if order == ORDER_CATEGORY:
        ordered = _sections_by(rows, lambda row: row.product.category.path)
    elif order == ORDER_LOCATION:
        _add_locations(rows)
        ordered = _sections_by(rows, lambda row: row.location, last=str(_("Without storage location")))
    else:
        order = ORDER_GROUPS
        ordered = [sections[group.pk] for group in groups if group.pk in sections] + [sections[None]]
        ordered = [section for section in ordered if section.rows]
    return PackOverview(packlist=packlist, sections=ordered, order=order, removed=removed, extracted=extracted)


def _add_takeovers(
    project: Project, rows: list[PackRow], entries: dict[tuple[int, int], PackEntry], structure: Any
) -> None:
    """Mark the rows that take over pieces of another subproject, and those whose pieces go on (PRJ-060).

    A row of line T with ``taken_over_from`` = S is a *takeover*: its pieces
    come from S's subproject, not from the warehouse. A row of line S names
    every later line that takes over from it, with the pieces planned and
    handed over so far – for a kit, per component. Two queries for the whole
    packlist, none for a project that is no part of a whole project
    (NFA-014: the packlist page of a big project stays within its queries).
    """
    if not rows:
        return
    for row in rows:
        if row.line.taken_over_from_id:
            row.takeover_from = row.line.taken_over_from
    if not project.is_in_family:
        return
    taking: dict[int, list[MaterialLine]] = defaultdict(list)
    for later in (
        MaterialLine.objects.filter(taken_over_from_id__in={row.line.pk for row in rows})
        .select_related("project")
        .order_by("project__number", "pk")
    ):
        taking[later.taken_over_from_id].append(later)
    entry_ids = {entry.pk for entry in entries.values()}
    handed: dict[tuple[int, int | None], Decimal] = defaultdict(lambda: ZERO)
    bookings: dict[int, list[HandoverBooking]] = defaultdict(list)
    if entry_ids:
        for handover in Handover.objects.filter(Q(source_id__in=entry_ids) | Q(target_id__in=entry_ids)).select_related(
            "target", "source__packlist__project", "handed_over_by"
        ):
            if handover.source_id in entry_ids:
                handed[(handover.source_id, handover.target.line_id)] += handover.quantity
            if handover.target_id in entry_ids:
                bookings[handover.target_id].append(
                    HandoverBooking(
                        handover_id=handover.pk,
                        quantity=handover.quantity,
                        at=handover.handed_over_at,
                        by=str(handover.handed_over_by or ""),
                        from_project=handover.source.packlist.project,
                    )
                )
    for row in rows:
        entry = entries.get((row.line.pk, row.product.pk))
        if entry is not None:
            row.handovers = bookings.get(entry.pk, [])
        per_line = flatten_kit(row.line.product_id, structure).get(row.product.pk, ZERO) if row.kit_title else 1
        for later in taking.get(row.line.pk, []):
            row.passes_on.append(
                PassOn(
                    line=later,
                    planned=later.quantity * per_line,
                    handed=handed.get((entry.pk, later.pk), ZERO) if entry is not None else ZERO,
                )
            )


def _sections_by(rows: list[PackRow], key: Any, *, last: str = "") -> list[PackSection]:
    """Rows grouped by a text and sorted by it, each section by article number (PCK-004)."""
    by_title: dict[str, list[PackRow]] = defaultdict(list)
    for row in rows:
        by_title[key(row) or last].append(row)
    titles = sorted(by_title, key=lambda title: (title == last, title.lower()))
    return [
        PackSection(group=None, title=title, rows=sorted(by_title[title], key=lambda row: row.product.article_number))
        for title in titles
    ]


def _add_weights(rows: list[PackRow]) -> None:
    """Weight and volume of each row from its material models (PCK-006).

    A product can be served by models of different weight; the heaviest one
    counts, so the sum never comes out too light for the truck.
    """
    product_ids = {row.product.pk for row in rows}
    weights: dict[int, Decimal] = {}
    volumes: dict[int, Decimal] = {}
    for model in MaterialModel.objects.filter(default_product_id__in=product_ids):
        if model.weight_kg is not None:
            weights[model.default_product_id] = max(weights.get(model.default_product_id, ZERO), model.weight_kg)
        volume = model.volume_litres
        if volume is not None:
            volumes[model.default_product_id] = max(volumes.get(model.default_product_id, ZERO), volume)
    for row in rows:
        # The weight of the model is that of one item; a piece of the row has as many of them as it stands for.
        if row.product.pk in weights:
            row.weight_kg = weights[row.product.pk] * row.required * row.pieces_per_unit
        if row.product.pk in volumes:
            row.volume_litres = volumes[row.product.pk] * row.required * row.pieces_per_unit


def _add_locations(rows: list[PackRow]) -> None:
    """The storage location of each row's product: where most of its items are (PCK-004).

    An installed item is where its outermost container is (MAT-038), up to
    three levels deep. Only plain values are read: a big project names
    thousands of items (NFA-012).
    """
    product_ids = {row.product.pk for row in rows}
    paths = location_paths()
    counts: dict[int, Counter[str]] = defaultdict(Counter)
    values = (
        MaterialItem.objects.filter(material_model__default_product_id__in=product_ids, product_override__isnull=True)
        .operational()
        .values_list(
            "material_model__default_product_id",
            "storage_location_id",
            "installed_in_id",
            "installed_in__storage_location_id",
            "installed_in__installed_in_id",
            "installed_in__installed_in__storage_location_id",
            "installed_in__installed_in__installed_in_id",
            "installed_in__installed_in__installed_in__storage_location_id",
        )
    )
    for product_id, own, first, first_place, second, second_place, third, third_place in values:
        location = own
        for container, place in ((first, first_place), (second, second_place), (third, third_place)):
            if container is None:
                break
            location = place
        counts[product_id][paths.get(location, "") if location else ""] += 1
    for row in rows:
        found = counts.get(row.product.pk)
        if found:
            places = [place for place, _count in found.most_common() if place]
            row.location = places[0] if places else ""
            if len(places) > 1:
                row.hints.append(_("also in: %(places)s") % {"places": ", ".join(places[1:4])})


def _add_hints(project: Project, rows: list[PackRow], *, with_contents: bool) -> list[str]:
    """Overdue inspections, loose pieces in containers, contents of containers (MAT-032, MAT-037, MAT-042).

    Returns the pieces taken out of their containers for this project, as text.
    """
    from rentalars.material.inspections import InspectionPlan
    from rentalars.material.services import content_tree

    product_ids = {row.product.pk for row in rows if not row.is_subrental}
    # A big project names thousands of items. Only their IDs are read for all of them (NFA-012);
    # whole objects only for the few that sit in another item.
    stock = MaterialItem.objects.operational()
    own_items = stock.filter(
        material_model__default_product_id__in=product_ids, product_override__isnull=True
    ).values_list("pk", "material_model_id", "material_model__default_product_id")
    override_items = stock.filter(product_override_id__in=product_ids).values_list(
        "pk", "material_model_id", "product_override_id"
    )
    ids_by_product: dict[int, list[int]] = defaultdict(list)
    model_of: dict[int, int] = {}
    for item_id, model_id, product_id in [*own_items, *override_items]:
        ids_by_product[product_id].append(item_id)
        model_of[item_id] = model_id
    installed_by_product: dict[int, list[MaterialItem]] = defaultdict(list)
    for item in (
        stock.filter(pk__in=list(model_of), installed_in__isnull=False)
        .select_related("material_model", "installed_in")
        .order_by("inventory_number")
    ):
        installed_by_product[item.product_override_id or item.material_model.default_product_id].append(item)
    plan = InspectionPlan()
    overdue: set[int] = set()
    if not plan.is_empty:
        inspected_models = plan.model_ids_with_types()
        overdue = plan.overdue_ids([item_id for item_id, model_id in model_of.items() if model_id in inspected_models])
    extractions = list(Extraction.objects.filter(project=project).select_related("item__material_model", "container"))
    extracted_ids = {extraction.item_id for extraction in extractions}

    # MAT-040: the bulk material built into the container of a row, for the "contains" lines – the container is
    # known from the chosen items, or is the only item of the product (PCK-021).
    container_ids_of: dict[int, list[int]] = {}
    for row in rows:
        own = ids_by_product.get(row.product.pk, [])
        chosen_ids = [chosen.item_id for chosen in row.chosen]
        container_ids_of[id(row)] = chosen_ids or (own if len(own) == 1 else [])
    built_in = installations.contents_of({item_id for ids in container_ids_of.values() for item_id in ids})

    for row in rows:
        own = ids_by_product.get(row.product.pk, [])
        count = sum(1 for item_id in own if item_id in overdue)
        if count:
            row.hints.append(
                ngettext(
                    "%(count)d item in stock with an overdue inspection",
                    "%(count)d items in stock with an overdue inspection",
                    count,
                )
                % {"count": count}
            )
        for chosen in row.chosen:
            chosen.inspection_overdue = chosen.item_id in overdue
        loose = [
            item
            for item in installed_by_product.get(row.product.pk, [])
            if item.is_planned_with_container and item.pk not in extracted_ids
        ]
        if loose:
            # MAT-042: the packer is told where loose pieces lie.
            row.hints.append(
                _("in containers: %(places)s")
                % {"places": ", ".join(f"{item.display_id} in {item.installed_in.display_id}" for item in loose[:4])}
            )
        # MAT-040: what is built into the container, as "contains" lines – always shown, they are part of it.
        for container_id in container_ids_of[id(row)]:
            row.contents.extend(_built_in_lines(built_in.get(container_id, []), depth=1))
        if with_contents:
            containers = container_ids_of[id(row)]  # a single item is known even before the issue (PCK-021)
            for container in MaterialItem.objects.filter(pk__in=containers).order_by("inventory_number"):
                tree = content_tree(container).depth_first
                inner_built_in = installations.contents_of([inner.pk for _depth, inner in tree])
                for depth, inner in tree:
                    row.contents.append(
                        ContentLine(
                            depth=depth,
                            display_id=inner.display_id,
                            name=inner.material_model.display_short_name,
                            state="extracted" if inner.pk in extracted_ids else "along",
                        )
                    )
                    row.contents.extend(_built_in_lines(inner_built_in.get(inner.pk, []), depth=depth + 1))

    # MAT-042: the packlist of the container names what stays behind.
    container_rows: dict[int, list[PackRow]] = defaultdict(list)
    for row in rows:
        container_rows[row.product.pk].append(row)
    texts = []
    for extraction in extractions:
        container = extraction.container
        text = _("%(item)s stays behind (taken out of %(container)s)") % {
            "item": f"{extraction.item.display_id} {extraction.item.material_model.display_short_name}",
            "container": container.display_id if container else "–",
        }
        texts.append(text)
        product = container.product if container else None
        for row in container_rows.get(product.pk if product else -1, []):
            row.hints.append(text)
    return texts


def _built_in_lines(installed: list[Any], *, depth: int) -> list[ContentLine]:
    """MAT-040: the bulk material built into a container as "contains" lines; the quantity is not counted again."""
    lines = []
    for entry in installed:
        product = entry.material.material_model.default_product
        lines.append(
            ContentLine(
                depth=depth,
                display_id=entry.material.display_id,
                name=entry.material.material_model.display_short_name,
                state="built_in",
                quantity=entry.quantity,
                unit=product.unit.abbreviation if product is not None else "",
            )
        )
    return lines


def _wish_text(line: MaterialLine) -> str:
    """The specific item or model a line asks for, as printed on the packlist (PRJ-064).

    Piece share: several wished items are listed, and for a line of several pieces it says which part of it
    they are: ``items 0042 (A), 0043 (A) – 2 of 10 pieces``.
    """
    if line.preferred_item_id:
        items = line.wished_items
        if len(items) > 1:
            text = _("items %(items)s") % {"items": ", ".join(item_label(item) for item in items)}
        else:
            item = items[0]
            text = _("item %(id)s (%(model)s)") % {
                "id": item.display_id,
                "model": item.material_model.display_short_name,
            }
        if line.pieces_total > 1:
            text += " – " + _("%(count)d of %(total)d pieces") % {"count": len(items), "total": line.pieces_total}
        return text
    if line.preferred_model_id:
        return _("model %(model)s") % {"model": line.preferred_model.name}
    return ""


def _add_wished_items(row: PackRow) -> None:
    """Note the items the line wishes for on its row, with their spots (piece share; PRJ-064).

    Only a row of the line's own product carries them – the components of a kit are no wish of the kit line.
    The packing list shows exactly these items, also before anything is chosen.
    """
    line = row.line
    if row.kit_title or not line.preferred_item_id or line.product_id != row.product.pk:
        return
    chosen = {item.item_id for item in row.chosen}
    row.wished = [
        WishedItem(
            item_id=item.pk,
            display_id=item.display_id,
            name=item.material_model.display_short_name,
            spot=item.effective_storage_spot if not item.installed_in_id else "",
            is_chosen=item.pk in chosen,
            problem="" if item.is_operational else item.get_status_display(),
        )
        for item in line.wished_items
    ]


# --- Packing (PCK-009, PCK-012) ----------------------------------------------


def find_row(overview: PackOverview, line_id: int, product_id: int) -> PackRow:
    """Find a row by line and product, or raise if the packlist has no such row."""
    for row in overview.rows:
        if row.line.pk == line_id and row.product.pk == product_id:
            return row
    raise ValidationError(_("This row is not on the packing list (any more)."))


def _entry_for(packlist: Packlist, row: PackRow) -> PackEntry:
    """Return the stored progress of a row, creating the record on first use."""
    entry, _created = PackEntry.objects.get_or_create(packlist=packlist, line=row.line, product=row.product)
    return entry


class _LockedEntries:
    """The entries of a packlist, locked and read anew (``select_for_update``), one query (PCK-027).

    Whoever changes the packed or the returned quantity of several rows takes
    them from here: a change of the offline sync in the meantime is then
    neither overwritten with an old value nor counted twice in the version.
    A row without entry gets one, locked as well. The packlist is locked
    first, in the order the sync locks (``packing.offline``), so that the two
    do not wait for each other.
    """

    def __init__(self, packlist: Packlist) -> None:
        self.packlist = packlist
        list(Packlist.objects.select_for_update().filter(pk=packlist.pk).values_list("pk", flat=True))
        self.entries = {
            (entry.line_id, entry.product_id): entry
            for entry in PackEntry.objects.select_for_update().filter(packlist=packlist)
        }

    def of(self, row: PackRow) -> PackEntry:
        """The locked entry of a row."""
        key = (row.line.pk, row.product.pk)
        if key not in self.entries:
            self.entries[key] = PackEntry.objects.select_for_update().get(pk=_entry_for(self.packlist, row).pk)
        return self.entries[key]


def _start_packing(packlist: Packlist, overview: PackOverview | None = None) -> None:
    """Note text and quantity of every row when packing starts, to show later changes (PCK-015)."""
    if packlist.packing_started_at is not None:
        return
    overview = overview or build_overview(packlist)
    for row in overview.rows:
        entry = _entry_for(packlist, row)
        entry.title_snapshot = row.title[:250]
        entry.required_snapshot = row.required
        # PCK-027: only the snapshot – the quantities of an entry read without lock are not written back.
        entry.save(update_fields=["title_snapshot", "required_snapshot"])
        row.change = ""
    packlist.packing_started_at = timezone.now()
    packlist.save()


def _derive_packing_status(packlist: Packlist) -> None:
    """Set open / in progress / packed from the ticks (PCK-014); a partly issued packlist stays so."""
    if packlist.status not in {PacklistStatus.OPEN, PacklistStatus.IN_PROGRESS, PacklistStatus.PACKED}:
        return
    overview = build_overview(packlist)
    if overview.packed_total == ZERO:
        status = PacklistStatus.OPEN
    elif all(row.is_packed for row in overview.warehouse_rows):  # PRJ-060: takeovers are not packed here
        status = PacklistStatus.PACKED
    else:
        status = PacklistStatus.IN_PROGRESS
    if packlist.status != status:
        packlist.status = status
        packlist.save()


@transaction.atomic
def set_packed(packlist: Packlist, line_id: int, product_id: int, quantity: Decimal, *, user: Any = None) -> PackRow:
    """Tick a row as packed, fully or with a quantity (PCK-009, PCK-012).

    Args:
        packlist: The packlist.
        line_id: The material line of the row.
        product_id: The product of the row (differs from the line's product
            for kit components).
        quantity: The packed quantity; limited to the range from what was
            issued already (PCK-018) to the required quantity.
        user: Who ticked.

    Raises:
        ValidationError: The material was already issued completely, or the
            row no longer exists.
    """
    if not packlist.can_be_packed:
        raise ValidationError(_("The material has already been issued. Packing can no longer be changed."))
    overview = build_overview(packlist)
    row = find_row(overview, line_id, product_id)
    _refuse_takeover(row)
    _start_packing(packlist, overview)
    entry = PackEntry.objects.select_for_update().get(pk=_entry_for(packlist, row).pk)
    entry.packed_quantity = max(entry.issued_quantity, min(Decimal(quantity), row.required), ZERO)
    entry.updated_by = user
    entry.save()
    _derive_packing_status(packlist)
    row.packed = entry.packed_quantity
    row.packed_changed_at = entry.packed_changed_at
    row.version = entry.version
    return row


@transaction.atomic
def pack_all(packlist: Packlist, *, user: Any = None) -> None:
    """Tick every row as completely packed."""
    if not packlist.can_be_packed:
        raise ValidationError(_("The material has already been issued. Packing can no longer be changed."))
    overview = build_overview(packlist)
    _start_packing(packlist, overview)
    locked = _LockedEntries(packlist)  # PCK-027
    for row in overview.warehouse_rows:  # PRJ-060: takeovers arrive by handover
        entry = locked.of(row)
        entry.packed_quantity = max(row.required, entry.issued_quantity)
        entry.updated_by = user
        entry.save()
    _derive_packing_status(packlist)


def _refuse_takeover(row: PackRow) -> None:
    """PRJ-060: pieces taken over from another subproject are not packed, chosen or issued in the warehouse.

    Raises:
        ValidationError: The row is a takeover.
    """
    if row.takeover_from is not None:
        raise ValidationError(
            _("These pieces come from %(project)s, not from the warehouse. Book their handover when they arrive.")
            % {"project": f"{row.takeover_from.project.number} {row.takeover_from.project.name}"}
        )


@transaction.atomic
def acknowledge_changes(packlist: Packlist, *, user: Any = None) -> None:
    """Take the current planning as the new state of the packlist (PCK-015).

    Rows of lines that disappeared are dropped with their ticks, unless
    something of them was issued; quantities and texts are noted anew.
    """
    overview = build_overview(packlist)
    for removed in overview.removed:
        PackEntry.objects.filter(pk=removed.entry_id, issued_quantity=ZERO).delete()
    locked = _LockedEntries(packlist)  # PCK-027
    for row in overview.rows:
        entry = locked.of(row)
        entry.title_snapshot = row.title[:250]
        entry.required_snapshot = row.required
        entry.packed_quantity = min(entry.packed_quantity, max(row.required, entry.issued_quantity))
        entry.updated_by = user
        entry.save()
    if packlist.packing_started_at is None:
        packlist.packing_started_at = timezone.now()
        packlist.save()
    record_event(packlist, "packlist.changes_acknowledged")
    _derive_packing_status(packlist)
    if _settle_issue_status(packlist):
        _project_after_packlists(packlist.project)


def _settle_issue_status(packlist: Packlist, overview: PackOverview | None = None) -> bool:
    """PCK-025: an issued packlist is "partly issued" while something of it is still in the warehouse.

    Called when the planning changed after the issue and the changes were
    acknowledged: a rest that is no longer needed makes the packlist
    "issued", a new row makes it "partly issued" again – the row can then be
    packed and issued like the others. Returns whether the status changed.
    """
    if packlist.status not in OUT_STATUSES:
        return False
    overview = overview or build_overview(packlist)
    complete = all(row.is_fully_issued for row in overview.warehouse_rows)  # PRJ-060: takeovers do not count
    status = PacklistStatus.ISSUED if complete else PacklistStatus.PARTLY_ISSUED
    if status == packlist.status:
        return False
    packlist.status = status
    packlist.save()
    return True


def _free_items(product: Product) -> list[MaterialItem]:
    """Items of a product that can be chosen for a row: fit for use and not travelling only inside a container."""
    items = MaterialItem.objects.for_product(product.pk).operational().select_related("material_model", "installed_in")
    return [item for item in items.order_by("inventory_number") if not item.travels_only_with_container]


def _back_from(project_id: int, items: list[MaterialItem]) -> set[int]:
    """PCK-028: those of the items that went out with this project and came back – not issued here again."""
    if not items:
        return set()
    return set(
        Allocation.objects.filter(
            entry__packlist__project_id=project_id,
            item__in=items,
            issued_at__isnull=False,
            returned_at__isnull=False,
        ).values_list("item_id", flat=True)
    )


def item_choices(packlist: Packlist, row: PackRow) -> list[tuple[MaterialItem, str, bool]]:
    """The items one could choose for a row, each with a note: where it lies, why not (PCK-022).

    Items out with or chosen for another project are offered with that note
    but cannot be chosen: the third value says whether the item is free.
    """
    from rentalars.material.inspections import InspectionPlan

    candidates = _free_items(row.product)
    busy = dict(
        Allocation.objects.filter(item__in=candidates, returned_at__isnull=True)
        .exclude(entry__packlist=packlist, entry__line=row.line, entry__product=row.product)
        .values_list("item_id", "entry__packlist__project__number")
    )
    back = _back_from(packlist.project_id, candidates)  # PCK-028
    plan = InspectionPlan()
    overdue = plan.overdue_ids([item.pk for item in candidates]) if not plan.is_empty else set()
    result = []
    for item in candidates:
        notes = []
        if item.pk in busy:
            notes.append(_("with %(project)s") % {"project": busy[item.pk]})
        elif item.pk in back:
            notes.append(_("came back from this project"))
        if item.is_installed:
            notes.append(_("in %(container)s") % {"container": item.installed_in.display_id})
        if item.pk in overdue:
            notes.append(_("inspection overdue"))
        result.append((item, ", ".join(notes), item.pk not in busy and item.pk not in back))
    # Piece share: the items the planner wished for are named and stand first.
    wished = row.line.wished_item_ids if row.line.product_id == row.product.pk and not row.kit_title else []
    if wished:
        result = [
            (item, ", ".join([str(_("wished by the planner")), *([note] if note else [])]), free)
            if item.pk in wished
            else (item, note, free)
            for item, note, free in result
        ]
        result.sort(key=lambda choice: wished.index(choice[0].pk) if choice[0].pk in wished else len(wished))
    return result


@transaction.atomic
def choose_items(
    packlist: Packlist, line_id: int, product_id: int, item_ids: list[int], *, user: Any = None
) -> list[str]:
    """Choose the items for a row beforehand, where it matters (PCK-022).

    Replaces the earlier choice; items that already went out stay. Nothing
    depends on it: a row without chosen items is issued all the same.

    Returns:
        Warnings, e.g. an item whose inspection is overdue (MAT-032).

    Raises:
        ValidationError: An item does not belong to the product, is not fit
            for use, is with another project, or more items than needed.
    """
    from rentalars.material.inspections import InspectionPlan

    if packlist.status in {PacklistStatus.ISSUED, PacklistStatus.RETURNED}:
        raise ValidationError(_("The material has already been issued."))
    overview = build_overview(packlist)
    row = find_row(overview, line_id, product_id)
    _refuse_takeover(row)
    _start_packing(packlist, overview)
    if row.is_bulk or row.is_subrental:
        raise ValidationError(_("For bulk material and subrentals no items are chosen."))
    entry = _entry_for(packlist, row)
    allowed = {item.pk: item for item in _free_items(row.product)}
    wanted = list(dict.fromkeys(int(item_id) for item_id in item_ids))
    unknown = [item_id for item_id in wanted if item_id not in allowed]
    if unknown:
        raise ValidationError(
            _("These items cannot be chosen for %(product)s.") % {"product": row.product.article_number}
        )
    issued = list(entry.allocations.filter(with_container__isnull=True, issued_at__isnull=False))
    issued_ids = {allocation.item_id for allocation in issued}
    new_ids = [item_id for item_id in wanted if item_id not in issued_ids]
    # A piece of a "10-pack" row is ten items.
    if len(issued) + len(new_ids) > row.pieces_required:
        raise ValidationError(_("More items chosen than the row needs."))
    busy = set(
        Allocation.objects.filter(item_id__in=new_ids, returned_at__isnull=True)
        .exclude(entry=entry)
        .values_list("item_id", flat=True)
    )
    if busy:
        raise ValidationError(
            _("%(items)s are chosen for or out with another project.")
            % {"items": ", ".join(allowed[item_id].display_id for item_id in busy)}
        )
    back = _back_from(packlist.project_id, [allowed[item_id] for item_id in new_ids])
    if back:
        # PCK-028: a piece that came back is done for this project.
        raise ValidationError(
            _("%(items)s came back from this project and are not issued again in it.")
            % {"items": ", ".join(allowed[item_id].display_id for item_id in sorted(back))}
        )
    # PCK-010: an item that was scanned stays scanned when the choice is made again.
    scanned = dict(
        entry.allocations.filter(issued_at__isnull=True, packed_scan_at__isnull=False).values_list(
            "item_id", "packed_scan_at"
        )
    )
    entry.allocations.filter(issued_at__isnull=True).delete()
    for item_id in new_ids:
        Allocation.objects.create(entry=entry, item_id=item_id, issued_at=None, packed_scan_at=scanned.get(item_id))
    if new_ids:
        record_event(
            packlist,
            "packlist.items_chosen",
            {"product": row.product.article_number, "items": ", ".join(allowed[i].display_id for i in new_ids)},
        )
    plan = InspectionPlan()
    overdue = plan.overdue_ids(new_ids) if new_ids and not plan.is_empty else set()
    return [_("The inspection of %(item)s is overdue.") % {"item": allowed[item_id].display_id} for item_id in overdue]


def may_not_add_material_text() -> str:
    """PCK-013: why somebody who packs may not add material – the same words in browser, API and sync."""
    return _("Only people who may change the project or pack for all projects may add material while packing.")


def may_add_material(rights: Any, user: Any, project: Project) -> bool:
    """Whether a user may add material while packing (PCK-013) – the one packing step with a financial effect.

    The rule for the role "Crew", which may pack: everything that implies writing but has no
    financial effect. The crew keeps strictly to the packing list; extra material must be added by authorised
    people. Material added while packing
    becomes a charged line of the project, so besides write on packing it
    needs either write on the project in it (as adding a line in the
    planning) or write on packing for all projects – the warehouse, whose
    role is not limited to assigned projects. Somebody who packs only in the
    projects assigned to them packs what is planned. Every other step of
    packing – ticking, choosing items, issue and return, missing parts and
    defects, further packing lists, handovers, taking items out of
    containers – has no financial effect and needs write on packing only.
    Ticking never goes beyond the packing list (``set_packed``,
    ``packing.offline``).
    """
    from rentalars.accounts.rights import Level, Module
    from rentalars.projects.access import ProjectAccess, access_level

    if rights.level_everywhere(Module.PACKING) >= Level.WRITE:
        return True
    return access_level(rights, user, project) >= ProjectAccess.EDIT


@transaction.atomic
def add_material(packlist: Packlist, product: Product, quantity: Decimal, *, user: Any, rights: Any) -> list[str]:
    """Add material while packing; it becomes a line of the project marked as addendum (PCK-013).

    The line goes on this packlist and is ticked as packed at once – it is
    in the hands of the packer already. Only for whom
    :func:`may_add_material` allows it.

    Returns:
        Warnings, e.g. a shortage the addendum causes – that one only for
        whom may see the availability of material (AUT-032).

    Raises:
        PermissionDenied: The caller may pack but not add material.
        ValidationError: The packlist is issued completely, or the product
            cannot be planned.
    """
    from rentalars.accounts.rights import SpecialRight
    from rentalars.projects.services import add_line

    if rights is not None and not may_add_material(rights, user, packlist.project):
        raise PermissionDenied(may_not_add_material_text())
    if not packlist.can_be_packed:
        raise ValidationError(_("The material has already been issued. Packing can no longer be changed."))
    if product.kind not in PACKABLE_KINDS:
        raise ValidationError(_("Only material can be added while packing."))
    if quantity <= ZERO:
        raise ValidationError({"quantity": _("Enter a quantity above zero.")})
    result = add_line(
        packlist.project, rights=rights, product=product, quantity=quantity, note=_("Added while packing")
    )
    line = result.line
    MaterialLine.objects.filter(pk=line.pk).update(is_addendum=True)
    if not is_main(packlist):
        LineAssignment.objects.create(line=line, packlist=packlist)
    record_event(packlist, "packlist.addendum", {"quantity": str(quantity), "product": product.article_number})
    overview = build_overview(packlist)
    _start_packing(packlist, overview)
    for row in overview.rows:
        if row.line.pk == line.pk:
            entry = _entry_for(packlist, row)
            entry.packed_quantity = row.required
            entry.title_snapshot = row.title[:250]
            entry.required_snapshot = row.required
            entry.updated_by = user
            entry.save()
    _derive_packing_status(packlist)
    warnings = []
    # AUT-032 (availability as a special right): the shortage only for whom may see availability – crew
    # lacks it at first; without rights (inside the application) it is said.
    sees_shortage = rights is None or rights.has(SpecialRight.AVAILABILITY)
    if sees_shortage and result.availability is not None and result.availability.shortage_total:
        warnings.append(
            _("Shortage: %(count)s × %(product)s are not free in the period.")
            % {"count": result.availability.shortage_total, "product": product.article_number}
        )
    return warnings


# --- Issue (PCK-014, PCK-018, PCK-020, PCK-021, PCK-025) -----------------------


@transaction.atomic
def issue(packlist: Packlist, *, user: Any = None, only_packed: bool = False) -> list[str]:
    """Book material out of the warehouse; the project follows (PCK-025).

    Args:
        packlist: The packlist.
        user: Who issues.
        only_packed: ``True`` is "issue", the main action on the packlist and
            the default of the API (PCK-025): only what is ticked goes out,
            with the ticked quantities. The packlist is then *partly issued*
            if something is left; the rest is packed and issued later
            (PCK-018). ``False`` is "issue everything": every row with its
            full quantity, for packing done on paper. In code it stays the
            default.

    Returns:
        Hints for the user, e.g. sold items that still have to be booked out,
        or an issued item whose inspection is overdue (MAT-032).

    Raises:
        ValidationError: Already issued, nothing to issue, or the project is
            cancelled or closed.
    """
    project = packlist.project
    if packlist.status in {PacklistStatus.ISSUED, PacklistStatus.RETURNED}:
        raise ValidationError(_("The material of this packing list has already been issued."))
    if project.status in {ProjectStatus.CANCELLED, ProjectStatus.CLOSED, ProjectStatus.RETURNED}:
        raise ValidationError(_("Material cannot be issued for a project that is cancelled or finished."))
    overview = build_overview(packlist)
    if not overview.rows:
        raise ValidationError(_("This packing list has no material to issue."))
    if not overview.warehouse_rows:
        raise ValidationError(
            _(
                "All material of this packing list comes from other subprojects. "
                "Book the handover when it arrives; there is nothing to issue from the warehouse."
            )
        )
    _start_packing(packlist, overview)

    hints: list[str] = []
    now = timezone.now()
    stocks = stock_of_products({row.product.pk for row in overview.warehouse_rows})
    issued_rows = 0
    complete = True
    # PRJ-060: takeover rows are left alone – their pieces are not taken from the warehouse, no free item
    # is allocated for them, and they do not keep the packlist "partly issued"; the handover issues them.
    locked = _LockedEntries(packlist)  # PCK-027: what the sync ticked meanwhile is issued, not overwritten
    for row in overview.warehouse_rows:
        entry = locked.of(row)
        target = min(entry.packed_quantity, row.required) if only_packed else row.required
        if not only_packed:
            entry.packed_quantity = max(entry.packed_quantity, row.required)
        addition = target - entry.issued_quantity
        if addition > ZERO:
            entry.issued_quantity = target
            issued_rows += 1
        entry.updated_by = user
        entry.save()
        if entry.issued_quantity < row.required:
            complete = False
        if addition <= ZERO:
            continue
        if row.is_sale:
            hint = _remove_sold_stock(entry, row)
            if hint:
                hints.append(hint)
        elif not row.is_subrental:
            # The items are dealt with, not the pieces – a piece of the row is several items.
            plannable = stocks[row.product.pk].plannable_pieces if row.product.pk in stocks else 0
            hints += _issue_items(entry, row, plannable, now, int(addition) * row.pieces_per_unit)
    if issued_rows == 0:
        raise ValidationError(
            _("Nothing is ticked that has not been issued yet. Tick what goes out, or issue everything.")
        )

    packlist.status = PacklistStatus.ISSUED if complete else PacklistStatus.PARTLY_ISSUED
    packlist.issued_at = packlist.issued_at or now
    packlist.issued_by = user
    packlist.save()
    if complete:
        record_event(packlist, "packlist.issued", {"rows": issued_rows, "only_packed": only_packed})
    else:
        record_event(packlist, "packlist.partly_issued", {"rows": issued_rows})
    # PCK-025: "out" only once everything is out; until then the project keeps its status.
    _project_after_packlists(project)
    webhooks.record("packing.issued", packlist)  # API-012
    if any(row.is_sale for row in overview.rows):
        # PRD-020: consumables left the stock for good; tell the warehouse if one fell below its minimum.
        from rentalars.material.services import check_low_stock

        check_low_stock()
    return hints


def _issue_items(entry: PackEntry, row: PackRow, plannable_stock: int, now: Any, count: int) -> list[str]:
    """Note the items that went out: the chosen ones first (PCK-022), then the obvious ones (PCK-021).

    ``plannable_stock`` and ``count`` are numbers of items: for a row whose pieces stand for several
    items, the pieces issued times the items per piece.

    Returns warnings for issued items whose inspection is overdue (MAT-032).
    """
    from rentalars.material.inspections import InspectionPlan

    if row.is_bulk:
        return []
    issued: list[Allocation] = []
    # PCK-010: the items that were scanned go out first – they are the ones in the hand.
    chosen = entry.allocations.filter(issued_at__isnull=True).select_related("item")
    for allocation in chosen.order_by(F("packed_scan_at").asc(nulls_last=True), "pk")[:count]:
        allocation.issued_at = now
        allocation.save()
        _set_in_use(allocation.item)
        issued.append(allocation)
    if count > len(issued):
        issued += _allocate_automatically(entry, row, plannable_stock, now, count - len(issued))
    for allocation in issued:
        _issue_contents(allocation, entry.packlist.project, now)
    plan = InspectionPlan()
    if plan.is_empty or not issued:
        return []
    overdue = plan.overdue_ids([allocation.item_id for allocation in issued])
    return [
        _("%(item)s went out although its inspection is overdue.") % {"item": allocation.item.display_id}
        for allocation in issued
        if allocation.item_id in overdue
    ]


def _set_in_use(item: MaterialItem) -> None:
    if item.status == ItemStatus.AVAILABLE:
        item.status = ItemStatus.IN_USE
        item.save()


def _allocate_automatically(
    entry: PackEntry, row: PackRow, plannable_stock: int, now: Any, count: int
) -> list[Allocation]:
    """Note which items went out where that is beyond doubt (PCK-021, PCK-024).

    Three cases are unambiguous:

    * the line names the one item that should go out (PRJ-064) – the
      packlist showed that wish, so this item is noted, provided it is fit
      for use and not out with another project;
    * the product has exactly one item that is fit for use – typical for
      racks, cases and single devices;
    * the whole plannable stock of the product is issued.

    In every other case nothing is noted and nothing is blocked: three of
    nine cables go out without anyone knowing which three (PCK-020).

    An item that is still out with another project is skipped; an item is
    never in two open allocations at once (catalogue 7.3). An item that came
    back from this project is skipped too: it is done here (PCK-028). With
    it out of the count, the one item left of a product is beyond doubt as
    well.
    """
    candidates = _free_items(row.product)
    back = _back_from(entry.packlist.project_id, candidates)
    remaining = [item for item in candidates if item.pk not in back]
    busy = set(
        Allocation.objects.filter(item__in=remaining, returned_at__isnull=True).values_list("item_id", flat=True)
    )
    usable = [item for item in remaining if item.pk not in busy]
    chosen: list[MaterialItem] = []

    # Piece share: every wished item covers one piece of the line, the first one first.
    wished_ids = row.line.wished_item_ids if row.line.product_id == row.product.pk else []
    if wished_ids:
        by_id = {item.pk: item for item in usable}
        chosen = [by_id[item_id] for item_id in wished_ids if item_id in by_id]

    # With several items to a piece, "beyond doubt" means: the items of exactly one piece are left, or the
    # whole stock goes out. Counted in items, as ``plannable_stock``; one item to a piece is the case as before.
    issued_total = int(entry.issued_quantity) * row.pieces_per_unit
    is_single_item = len(remaining) == row.pieces_per_unit
    is_whole_stock = issued_total >= plannable_stock and issued_total == len(candidates)
    if is_single_item or is_whole_stock:
        chosen += [item for item in usable if item not in chosen]

    created = []
    for item in chosen[:count]:
        created.append(Allocation.objects.create(entry=entry, item=item, issued_at=now))
        _set_in_use(item)
    return created


def _issue_contents(allocation: Allocation, project: Project, now: Any) -> None:
    """What is inside an issued container goes out with it (MAT-037).

    Fixed contents always; loose contents unless they were taken out for
    this project (MAT-042) – together with whatever is inside those.
    """
    from rentalars.material.services import content_tree

    extracted = set(Extraction.objects.filter(project=project).values_list("item_id", flat=True))
    pending = list(content_tree(allocation.item).children)
    while pending:
        node = pending.pop()
        item = node.item
        if item.pk in extracted:
            continue
        if not Allocation.objects.filter(item=item, returned_at__isnull=True).exists():
            Allocation.objects.create(entry=allocation.entry, item=item, issued_at=now, with_container=allocation)
            _set_in_use(item)
        pending.extend(node.children)


def _remove_sold_stock(entry: PackEntry, row: PackRow) -> str:
    """Take sold pieces out of the stock for good (PRD-013).

    Bulk material: the quantity of the bulk rows is reduced. Individual
    items: if it is beyond doubt which items were sold (see
    ``_allocate_automatically``), they are set to "sold". Otherwise the line
    keeps the pieces occupied and the user is asked to mark the sold items.

    Returns:
        A hint for the user if items still have to be marked, else ``""``.
    """
    line = row.line
    outstanding = int(entry.issued_quantity - line.stock_removed_quantity)
    if outstanding <= 0 or not row.product.tracks_stock:
        return ""
    # Sold pieces of a product of several items leave the stock as items; the line counts the pieces
    # (``stock_removed_quantity`` is in pieces of the product), so only whole pieces are taken out.
    per = row.pieces_per_unit
    needed = outstanding * per
    removed = 0
    items = list(MaterialItem.objects.for_product(row.product.pk).operational().select_related("material_model"))
    bulk_rows = [item for item in items if item.material_model.is_bulk]
    single_items = [item for item in items if not item.material_model.is_bulk and not item.travels_only_with_container]

    bulk_budget = needed
    if per > 1:
        bulk_budget = min(needed, sum(bulk_row.quantity for bulk_row in bulk_rows) // per * per)
    for bulk_row in bulk_rows:
        if removed >= bulk_budget:
            break
        take = min(bulk_row.quantity, bulk_budget - removed)
        bulk_row.quantity -= take
        bulk_row.save()
        removed += take

    remaining = needed - removed
    if remaining > 0 and ((per == 1 and len(single_items) == 1) or remaining == len(single_items)):
        for item in single_items[:remaining]:
            item.status = ItemStatus.SOLD
            item.save()
            removed += 1

    removed_pieces = removed // per
    if removed_pieces:
        line.stock_removed_quantity += removed_pieces
        line.save()
        record_event(line, "line.sold_stock_removed", {"quantity": removed_pieces})
    if removed_pieces < outstanding:
        return ngettext(
            "%(count)d sold piece of %(product)s is still counted in the stock. "
            "Set the sold item to the status “sold”.",
            "%(count)d sold pieces of %(product)s are still counted in the stock. "
            "Set the sold items to the status “sold”.",
            plural_of(outstanding - removed_pieces),
        ) % {"count": outstanding - removed_pieces, "product": row.product.article_number}
    return ""


def _still_to_issue(packlist: Packlist) -> bool:
    """PCK-025: whether material of a packlist is still to go out of the warehouse.

    A partly issued packlist has a rest; one that was not issued yet has if
    it holds rows from the warehouse – an empty further packlist, or one that
    only takes over pieces of another subproject (PRJ-060), has not.
    """
    if packlist.status == PacklistStatus.PARTLY_ISSUED:
        return True
    if packlist.status in {PacklistStatus.OPEN, PacklistStatus.IN_PROGRESS, PacklistStatus.PACKED}:
        return bool(build_overview(packlist).warehouse_rows)
    return False


def _project_after_packlists(project: Project) -> None:
    """The project follows its packlists (PCK-025, PCK-019).

    * "Out" once everything is out: material is out, and no packlist with
      material from the warehouse has anything left to issue. Sold rows and
      subrentals count like every row; pieces taken over from another
      subproject (PRJ-060) do not – their handover is no issue.
    * While material is only partly out, the project keeps its status – a
      project that is "out" stays so while a later addition waits.
    * "Returned" once nothing is out any more and nothing waits: the return
      of every packlist is complete. After a partial issue whose return was
      completed, the rest stays in the warehouse (PCK-018).
    * Nothing out, but something still to issue (an issue was taken back,
      or one packlist came back before the other went out): an "out"
      project has the status it had before it went out again (an
      option stays an option; "confirmed" where that is not known), any
      other keeps its status.
    """
    packlists = list(project.packlists.order_by("id"))
    is_out = any(packlist.is_out for packlist in packlists)
    came_back = any(packlist.status == PacklistStatus.RETURNED for packlist in packlists)
    waiting = any(_still_to_issue(packlist) for packlist in packlists)
    status = project.status
    if is_out:
        status = status if waiting else ProjectStatus.OUT
    elif came_back and not waiting and status not in FINISHED_STATUSES:
        status = ProjectStatus.RETURNED
    elif status == ProjectStatus.OUT:
        status = _status_before_out(project)
    if status != project.status:
        project.status = status
        project.save()


def _status_before_out(project: Project) -> str:
    """The status a project had before it became "out" – an option stays an option.

    Taken from the change log; "confirmed" where it holds nothing usable (the entry was cleared, or the project was
    never anything else).
    """
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.models import AuditAction, AuditLogEntry

    entries = AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(Project), object_id=str(project.pk), action=AuditAction.UPDATED
    ).order_by("-timestamp", "-id")
    allowed = {ProjectStatus.OPTION, ProjectStatus.CONFIRMED_OPEN, ProjectStatus.CONFIRMED}
    for entry in entries[:200]:
        change = (entry.changes or {}).get("status")
        if isinstance(change, list) and len(change) == 2 and change[1] == ProjectStatus.OUT:
            return ProjectStatus(change[0]) if change[0] in allowed else ProjectStatus.CONFIRMED
    return ProjectStatus.CONFIRMED


@transaction.atomic
def undo_issue(packlist: Packlist) -> None:
    """Take back an issue that was booked by mistake.

    Everything issued from the warehouse is taken back, also after several
    partial issues (PCK-025); the ticks stay. Items chosen beforehand stay
    chosen.

    Raises:
        ValidationError: Something was already returned, or sold stock was
            already removed (that cannot be reversed automatically).
    """
    if packlist.status not in OUT_STATUSES:
        raise ValidationError(_("There is no issue to take back."))
    if packlist.entries.filter(returned_quantity__gt=0).exists():
        raise ValidationError(_("Material has already been returned. The issue can no longer be taken back."))
    sold_lines = packlist.entries.filter(line__is_sale=True, line__stock_removed_quantity__gt=0)
    if sold_lines.exists():
        raise ValidationError(
            _(
                "Sold material was already taken out of the stock. Correct the stock by hand instead of taking back the issue."
            )
        )
    if packlist.entries.filter(handed_over_quantity__gt=0).exists():
        raise ValidationError(
            _("Material of this packing list went on to another subproject. Take back that handover first.")
        )
    # PRJ-060: what arrived from another subproject by handover stays; only the issue from the warehouse is undone.
    received = dict(
        Handover.objects.filter(target__packlist=packlist)
        .order_by()
        .values("target_id")
        .annotate(total=Sum("quantity"))
        .values_list("target_id", "total")
    )
    came_along = Q(handover__isnull=False) | Q(with_container__handover__isnull=False)
    for allocation in (
        Allocation.objects.filter(entry__packlist=packlist, issued_at__isnull=False)
        .exclude(came_along)
        .select_related("item")
    ):
        _release_item(allocation.item)
    Allocation.objects.filter(entry__packlist=packlist, with_container__isnull=False).exclude(came_along).delete()
    Allocation.objects.filter(entry__packlist=packlist, issued_at__isnull=False).exclude(came_along).delete()
    if received:
        for entry in packlist.entries.select_for_update():  # PCK-027: read anew, locked
            entry.issued_quantity = received.get(entry.pk, ZERO)
            entry.save()
        packlist.status = PacklistStatus.PARTLY_ISSUED
        packlist.save()
    else:
        packlist.entries.update(issued_quantity=ZERO)
        packlist.issued_at = None
        packlist.issued_by = None
        packlist.status = PacklistStatus.PACKED
        packlist.save()
        _derive_packing_status(packlist)
    record_event(packlist, "packlist.issue_undone")
    _project_after_packlists(packlist.project)
    webhooks.record("packing.issue_undone", packlist)  # API-012


# --- Return (PCK-016, PCK-017, PCK-019) ----------------------------------------


def _release_item(item: MaterialItem) -> None:
    """Set an item that came back to "available" again."""
    if item.status == ItemStatus.IN_USE:
        item.status = ItemStatus.AVAILABLE
        item.save()


def _close_allocations_if_back(entry: PackEntry, now: Any = None) -> None:
    """Once a row is completely taken back, its allocated items – and their contents – are back too (MAT-037).

    PRJ-060: pieces handed over to another subproject count as back. PCK-028:
    what counts is the booking, not the tick; the items are "available" again
    at once. While only part of a row is back it is not known which of its
    items came (PCK-020): they stay out until the row is complete.
    """
    if entry.taken_back_quantity + entry.handed_over_quantity < entry.issued_quantity:
        return
    now = now or timezone.now()
    for allocation in entry.allocations.filter(returned_at__isnull=True, issued_at__isnull=False).select_related(
        "item"
    ):
        allocation.returned_at = now
        allocation.save()
        _release_item(allocation.item)


def return_limits(row: PackRow) -> tuple[Decimal, Decimal]:
    """PCK-028: the lowest and highest quantity a row can be ticked as back with.

    Not below what is taken back already – a piece booked back stays back –
    and not above what was issued and did not go on to another subproject
    (PRJ-060): those pieces come back with the other one.
    """
    return row.taken_back, max(row.returnable, row.taken_back)


@transaction.atomic
def set_returned(packlist: Packlist, line_id: int, product_id: int, quantity: Decimal, *, user: Any = None) -> PackRow:
    """Tick a row as back, fully or with a quantity (PCK-016, PCK-018, PCK-028).

    The tick books nothing yet: :func:`take_back` books what is ticked. The
    quantity is held within :func:`return_limits`. More material back is an
    event for webhooks (API-012); a correction downwards is not.

    Raises:
        ValidationError: Nothing is out, or the row no longer exists.
    """
    if not packlist.is_out:
        raise ValidationError(_("Returns can only be booked while the material is out."))
    overview = build_overview(packlist)
    row = find_row(overview, line_id, product_id)
    if row.is_sale:
        raise ValidationError(_("Sold material is not returned."))
    lowest, highest = return_limits(row)
    entry = PackEntry.objects.select_for_update().get(pk=_entry_for(packlist, row).pk)
    before = entry.returned_quantity
    entry.returned_quantity = max(lowest, min(Decimal(quantity), highest))
    entry.updated_by = user
    entry.save()
    row.returned = entry.returned_quantity
    row.returned_changed_at = entry.returned_changed_at
    row.version = entry.version
    if entry.returned_quantity > before:
        webhooks.record("packing.returned", packlist)
    return row


@transaction.atomic
def return_all(packlist: Packlist, *, user: Any = None) -> None:
    """Tick everything that was issued as back; an event for webhooks if anything came back (API-012).

    Like "tick all rows" while packing, it books nothing yet (PCK-028).
    PRJ-060: pieces handed over to another subproject come back with that
    one, and pieces that a later subproject is still to take over are
    expected there, not in the warehouse: both are left out. Should such
    pieces come back after all, their row is ticked by hand.
    """
    if not packlist.is_out:
        raise ValidationError(_("Returns can only be booked while the material is out."))
    pending = {(row.line.pk, row.product.pk): row.handover_pending for row in build_overview(packlist).rows}
    came_back = False
    for entry in packlist.entries.select_for_update().select_related("line"):
        if entry.line is None or entry.line.is_sale:
            continue
        expected_elsewhere = entry.handed_over_quantity + pending.get((entry.line_id, entry.product_id), ZERO)
        returnable = max(entry.issued_quantity - expected_elsewhere, entry.returned_quantity, ZERO)
        came_back = came_back or entry.returned_quantity < returnable
        entry.returned_quantity = returnable
        entry.updated_by = user
        entry.save()
    if came_back:
        webhooks.record("packing.returned", packlist)


def _book_ticked_returns(packlist: Packlist, *, user: Any, now: Any) -> Decimal:
    """Book what is ticked as back and not booked yet; returns how many pieces (PCK-028).

    Rows that are taken back completely give their items free (MAT-037).
    """
    booked = ZERO
    with transaction.atomic():
        for entry in packlist.entries.select_for_update().select_related("line"):
            if entry.line is not None and entry.line.is_sale:
                continue
            target = min(entry.returned_quantity, max(entry.issued_quantity - entry.handed_over_quantity, ZERO))
            addition = target - entry.taken_back_quantity
            if addition <= ZERO:
                continue
            entry.taken_back_quantity = target
            entry.taken_back_at = now
            entry.updated_by = user
            entry.save()
            booked += addition
            _close_allocations_if_back(entry, now)
    return booked


@transaction.atomic
def take_back(packlist: Packlist, *, user: Any = None) -> Decimal:
    """Book what is ticked as back into the warehouse – "book the return" (PCK-028).

    Like the issue books what is ticked as packed, this books what is ticked
    as back, with the ticked quantities. It works as soon as anything is out,
    also while the rest of the packlist is still packed and issued (PCK-018).
    The pieces are free for other projects at once; the items of a row that
    is back completely are "available" again. A piece taken back is done for
    this project: it is not issued again here.

    Once nothing of the packlist is out any more and nothing waits for its
    issue or its handover, the return is complete as well: the packlist is
    "returned", and the project follows (PCK-019, PCK-025).

    Returns:
        How many pieces were booked.

    Raises:
        ValidationError: Nothing is out, or nothing is ticked that is not
            booked yet.
    """
    if not packlist.is_out:
        raise ValidationError(_("Returns can only be booked while the material is out."))
    now = timezone.now()
    booked = _book_ticked_returns(packlist, user=user, now=now)
    if booked <= ZERO:
        raise ValidationError(_("Nothing is ticked as back that has not been booked yet. Tick what came back."))
    record_event(packlist, "packlist.taken_back", {"quantity": _number(booked)})
    overview = build_overview(packlist)
    if (
        packlist.status == PacklistStatus.ISSUED
        and overview.still_out_total == ZERO
        and overview.awaiting_handover_total == ZERO
        and not overview.missing_rows
    ):
        _finish_return(packlist, user=user, now=now)
    return booked


def defect_candidates(packlist: Packlist) -> list[MaterialItem]:
    """The items a defect can be reported for on return: those that went out with this packlist (PCK-017)."""
    allocated = list(
        MaterialItem.objects.filter(allocations__entry__packlist=packlist, allocations__issued_at__isnull=False)
        .select_related("material_model")
        .distinct()
        .order_by("inventory_number")
    )
    return allocated


@transaction.atomic
def report_return_defect(
    packlist: Packlist, item: MaterialItem, description: str, *, photo: Any = None, user: Any = None
) -> Any:
    """Report a defect of one item while taking the material back (PCK-017, MAT-023).

    Any item of a product on this packlist can be named – the cables of a
    row were never assigned one by one, but the broken one is in the hand.

    Raises:
        ValidationError: The item has nothing to do with this packlist, or
            the report is incomplete.
    """
    from rentalars.material.services import report_defect

    if not packlist.is_issued:
        raise ValidationError(_("Defects on return can be reported once the material is out."))
    products = {row.product.pk for row in build_overview(packlist).rows}
    allocated = Allocation.objects.filter(entry__packlist=packlist, item=item).exists()
    if not allocated and (item.product is None or item.product.pk not in products):
        raise ValidationError(_("%(item)s is not part of this packing list.") % {"item": item.display_id})
    report = report_defect(
        item,
        description,
        photo=photo,
        context=_("Return of %(project)s") % {"project": packlist.project.number},
        user=user,
    )
    record_event(packlist, "packlist.defect_reported", {"item": item.display_id, "description": description[:200]})
    return report


def resolve_missing(packlist: Packlist, line_id: int, product_id: int, note: str, *, user: Any = None) -> str:
    """Mark the missing parts of a row as clarified, with an explanation (PCK-019).

    The stock is not changed by this. If pieces are lost for good, the
    warehouse sets the items to "lost" or reduces the bulk quantity. Since
    The items that did not come back are blocked when the return is
    completed (see ``_close_all_allocations``); for bulk material nothing
    knows which pieces are meant, so the answer is a hint: the pieces are
    still counted as stock until the quantity is corrected.

    Returns:
        A hint for the person (empty if there is nothing to add).

    Raises:
        ValidationError: No explanation was given.
    """
    if not note.strip():
        raise ValidationError(_("Please note briefly how the missing parts were clarified."))
    entry = PackEntry.objects.filter(packlist=packlist, line_id=line_id, product_id=product_id).first()
    if entry is None:
        raise ValidationError(_("This row is not on the packing list (any more)."))
    entry.missing_resolved = True
    entry.missing_note = note.strip()[:250]
    entry.updated_by = user
    # PCK-027: only these fields – the ticked quantities of an entry read without lock stay as they are.
    entry.save(update_fields=["missing_resolved", "missing_note", "updated_by", "updated_at"])
    record_event(
        packlist,
        "packlist.missing_resolved",
        {"product": entry.product.article_number, "quantity": str(entry.missing_quantity), "note": entry.missing_note},
    )
    if entry.missing_quantity > ZERO and entry.product.kind in STOCK_KINDS and not entry.allocations.exists():
        return _(
            "%(quantity)s × %(product)s are still counted as stock. If they are lost for good, reduce the quantity "
            "in the material list, or the next projects will be promised them."
        ) % {"quantity": _number(entry.missing_quantity), "product": entry.product.article_number}
    return ""


def handover_pending_text(rows: list[PackRow]) -> str:
    """PRJ-060: which of the missing pieces still wait for their handover to a later subproject, as a sentence.

    Such pieces count as missing until the handover is booked on the
    packlist of the later subproject (or they are returned or clarified).
    """
    count = ZERO
    numbers: list[str] = []
    for row in rows:
        waiting = min(row.handover_pending, row.missing)
        if waiting <= ZERO:
            continue
        count += waiting
        for passing in row.passes_on:
            if passing.awaiting > ZERO and passing.project.number not in numbers:
                numbers.append(passing.project.number)
    if not count:
        return ""
    return _(
        "%(count)s of the pieces still wait for their handover to %(projects)s; "
        "book it on the packing list there once they have arrived."
    ) % {"count": _number(count), "projects": ", ".join(numbers)}


def _number(value: Decimal) -> str:
    """A quantity without needless decimals, for texts."""
    return (
        str(int(value))
        if value == value.to_integral_value()
        else format(value.normalize(), "f").replace(".", decimal_separator())
    )


def unresolved_missing(packlist: Packlist) -> list[PackRow]:
    """Return the rows that block the status "returned" (PCK-019)."""
    if not packlist.is_out:
        return []
    return build_overview(packlist).missing_rows


@transaction.atomic
def complete_return(packlist: Packlist, *, user: Any = None) -> None:
    """Finish the return of a packlist (PCK-019).

    What is ticked as back and not booked yet is booked first (PCK-028). The
    project becomes "returned" once none of its packlists is out any more
    and none has anything left to issue. After a partial issue, what never
    went out simply stays in the warehouse (PCK-018): completing the return
    settles it, also for a project that never became "out" because not
    everything went out (PCK-025).

    Raises:
        ValidationError: Parts are missing and not clarified.
    """
    if not packlist.is_out:
        raise ValidationError(_("Returns can only be completed while the material is out."))
    missing = unresolved_missing(packlist)
    if missing:
        texts = [
            ngettext(
                "%(count)d row is not completely back. Book the return or clarify the missing parts first.",
                "%(count)d rows are not completely back. Book the return or clarify the missing parts first.",
                len(missing),
            )
            % {"count": len(missing)}
        ]
        waiting = handover_pending_text(missing)
        if waiting:
            texts.append(waiting)
        raise ValidationError(texts)
    now = timezone.now()
    _book_ticked_returns(packlist, user=user, now=now)
    _finish_return(packlist, user=user, now=now)


def _finish_return(packlist: Packlist, *, user: Any, now: Any) -> None:
    """The return of a packlist is complete: every item is back, the project follows (PCK-019, PCK-025)."""
    _close_all_allocations(packlist, now)
    packlist.status = PacklistStatus.RETURNED
    packlist.returned_at = now
    packlist.returned_by = user
    packlist.save()
    record_event(packlist, "packlist.returned")
    _project_after_packlists(packlist.project)
    webhooks.record("packing.returned", packlist)  # API-012: "complete" is true now


def _close_all_allocations(packlist: Packlist, now: Any) -> None:
    """Every item of the packlist is back – also of rows whose missing parts were clarified."""
    Allocation.objects.filter(entry__packlist=packlist, issued_at__isnull=True).delete()
    # Items of a row whose missing parts were only clarified did not all come back. Those that were not
    # scanned back – as many as the row is short – are blocked instead of "available": the warehouse decides
    # ("lost", "found"), and in the meantime they are not promised to the next project.
    shortfall = {
        entry.pk: int(max(entry.issued_quantity - entry.taken_back_quantity - entry.handed_over_quantity, ZERO))
        for entry in packlist.entries.all()
        if entry.missing_resolved and not (entry.line is not None and entry.line.is_sale)
    }
    for allocation in (
        Allocation.objects.filter(entry__packlist=packlist, returned_at__isnull=True)
        .select_related("item", "entry")
        .order_by("returned_scan_at", "pk")
    ):
        allocation.returned_at = now
        allocation.save()
        left = shortfall.get(allocation.entry_id, 0)
        if left > 0 and allocation.returned_scan_at is None and allocation.with_container_id is None:
            shortfall[allocation.entry_id] = left - 1
            if allocation.item.status == ItemStatus.IN_USE:
                reason = _("Missing after the return of %(project)s: %(note)s") % {
                    "project": packlist.project.number,
                    "note": allocation.entry.missing_note,
                }
                material_services.set_status(allocation.item, ItemStatus.BLOCKED, reason=reason)
            continue
        _release_item(allocation.item)


def guard_project_status(project: Project, new_status: str) -> None:
    """Keep project status and packlists in step (PCK-019, PCK-025).

    While material is out, the only way forward is "returned", and that only
    once everything is back or the missing parts are clarified – on every
    packlist of the project. A project whose material is only partly out
    keeps its status until everything is out (PCK-025); it can still be set
    to "out" by hand, or from one kind of "confirmed" to the other – never
    back to an option or an inquiry, and not cancelled. Nor can a whole
    project be cancelled while material of one of its parts is out (PRJ-044).

    Registered with ``projects.services.status_guards`` when the app starts.
    """
    if new_status == ProjectStatus.CANCELLED and project.parent_id is None:
        numbers = list(
            Project.objects.filter(parent=project)
            .filter(material_out("pk"))
            .order_by("number")
            .values_list("number", flat=True)
        )
        if numbers:
            raise ValidationError(
                _("Material of the subprojects %(numbers)s is out; they cannot be cancelled.")
                % {"numbers": ", ".join(numbers)}
            )
    out = [packlist for packlist in project.packlists.order_by("id") if packlist.is_out]
    if not out:
        return
    if project.status != ProjectStatus.OUT and new_status in {
        ProjectStatus.OUT,
        ProjectStatus.CONFIRMED,
        ProjectStatus.CONFIRMED_OPEN,
    }:
        return  # PCK-025: partly out – "out" by hand, or the other kind of "confirmed"
    if new_status != ProjectStatus.RETURNED:
        raise ValidationError(_("The material of this project is out. Take back the issue or book the return first."))
    missing = [row for packlist in out for row in unresolved_missing(packlist)]
    if missing:
        texts = [
            ngettext(
                "%(count)d packing list row is not completely back. Book the return or clarify the missing parts first.",
                "%(count)d packing list rows are not completely back. Book the return or clarify the missing parts first.",
                len(missing),
            )
            % {"count": len(missing)}
        ]
        waiting = handover_pending_text(missing)  # PRJ-060
        if waiting:
            texts.append(waiting)
        raise ValidationError(texts)
    # Setting the status by hand completes the return as well – with what is ticked as back booked (PCK-028).
    now = timezone.now()
    for packlist in out:
        _book_ticked_returns(packlist, user=None, now=now)
        packlist.status = PacklistStatus.RETURNED
        packlist.returned_at = now
        packlist.save()
        _close_all_allocations(packlist, now)


# --- Taking loose contents out of their container for a project (MAT-042) -----------------------


def _container_products(item: MaterialItem) -> dict[int, MaterialItem]:
    """The products of the containers around an item: ``{product id: container}``."""
    from rentalars.material.services import container_chain

    result: dict[int, MaterialItem] = {}
    for container in container_chain(item):
        product = container.product
        if product is not None:
            result.setdefault(product.pk, container)
    return result


def extraction_choices(item: MaterialItem, rights: Any, user: Any) -> list[Project]:
    """Running and coming projects that take the item's container along (MAT-042).

    Only for loose contents: a fixed item never leaves its container on its
    own (MAT-036).
    """
    from rentalars.projects.access import visible_projects
    from rentalars.projects.models import FINISHED_STATUSES

    if not item.is_planned_with_container:
        return []
    products = _container_products(item)
    if not products:
        return []
    taken = set(item.extractions.values_list("project_id", flat=True))
    return list(
        visible_projects(rights, user)
        .filter(material_lines__product_id__in=products, end__gt=timezone.now())
        .exclude(status__in=FINISHED_STATUSES)
        .exclude(pk__in=taken)
        .distinct()
        .order_by("start")[:30]
    )


def extract(project: Project, item: MaterialItem, *, user: Any = None) -> Extraction:
    """Take a loose item out of its container for one project (MAT-042).

    The item then does not travel with the container in this project: it is
    free for others meanwhile, and the packlist of the project names it as
    missing content of the container.

    Raises:
        ValidationError: The item is not loose in a container, the project
            does not take the container along, or it was taken out already.
    """
    from rentalars.projects.models import FINISHED_STATUSES

    if not item.is_planned_with_container:
        raise ValidationError(_("Only loosely contained items can be taken out for a project."))
    if project.status in FINISHED_STATUSES:
        raise ValidationError(_("The project is finished."))
    products = _container_products(item)
    if not project.material_lines.filter(product_id__in=products).exists():
        raise ValidationError(
            _("Project %(project)s does not take %(container)s along.")
            % {"project": project.number, "container": item.installed_in.display_id if item.installed_in else "–"}
        )
    if Extraction.objects.filter(project=project, item=item).exists():
        raise ValidationError(_("%(item)s is already taken out for this project.") % {"item": item.display_id})
    extraction = Extraction.objects.create(project=project, item=item, container=item.installed_in, created_by=user)
    record_event(
        project, "project.content_extracted", {"item": item.display_id, "container": item.installed_in.display_id}
    )
    record_event(item, "item.extracted", {"project": project.number})
    return extraction


def cancel_extraction(extraction: Extraction) -> None:
    """The item travels with its container again (MAT-042)."""
    record_event(extraction.project, "project.content_extraction_cancelled", {"item": extraction.item.display_id})
    extraction.delete()
