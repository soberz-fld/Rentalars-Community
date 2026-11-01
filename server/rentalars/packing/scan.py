# SPDX-License-Identifier: GPL-3.0-or-later
"""Packing and taking back by scanning the label of an item (PCK-010, PCK-011, PCK-016, MAT-027, UIX-006).

The requirement: barcode and QR scanning in the browser – at the packing list, an item is marked packed or back by reading its
label (camera, hand scanner or typed ID; the code is resolved by :mod:`rentalars.material.scan`). The scan stays
voluntary (PCK-020): ticking a row by hand works as before, and what is scanned only counts up the same tick.

Packing (:func:`scan_pack`)
    The item is chosen for the row of its product (PCK-022) – the row that has it chosen already, else the first one
    that still needs items – and counted: "4 of 6". A piece of a "10-pack" row counts when its ten items
    are scanned. The row's tick (``packed``) is raised to the pieces scanned, never lowered. Items scanned go out
    first at the issue. Refused with a reason (PCK-011): the item belongs to no row, is defective or blocked, is with
    another project, or all items the row needs are chosen. Warned: its inspection is overdue (MAT-032).

Taking back (:func:`scan_return`)
    The item must have gone out with this packing list; the scan counts it back once, however often the code is read,
    and raises the row's tick (``returned``) to the pieces scanned back (PCK-016). Booking the return stays a step
    of its own (PCK-028). An item that went out inside a container comes back with it.

Bulk material is confirmed by its count (PCK-012): a scan of its label only points to the row.

What the answer tells (R1-15)
    A person who may pack but not read the material (``rights`` without the material level) is told nothing about an
    item that is not part of this packing list – not its status, product, container or project: such a code is answered
    like a code nobody knows. Packing and taking back lock the packing list first, so that two scans at once cannot
    overwrite each other's choice of items.

Browser (``packing.views``) and API (``packing.api``) call these functions (API-002).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, Rights
from rentalars.material import scan
from rentalars.material.models import MaterialItem
from rentalars.packing import services
from rentalars.packing.models import Allocation, Packlist

#: The statuses of an outcome. ``packed`` and ``returned`` changed something; the others tell why nothing did.
PACKED = "packed"
RETURNED = "returned"
DUPLICATE = "duplicate"
BULK = "bulk"
INFO = "info"
NOT_ON_LIST = "not_on_list"
REFUSED = "refused"
FULL = "full"
UNKNOWN = "unknown"

#: How the page shows an outcome: a green message, a yellow warning, a red refusal.
SUCCESS, WARNING, ERROR = "success", "warning", "error"


@dataclass
class ScanOutcome:
    """What a scan did at a packing list.

    Attributes:
        status: See the constants above.
        level: ``success``, ``warning`` or ``error`` – how to show ``message``.
        message: A sentence for the person at the packing list.
        warnings: Further notes, e.g. an overdue inspection (PCK-011).
        row: The key of the row that was meant or changed (``<line id>-<product id>``), for the page to highlight.
        item: The ID of the item, if the code was one.
        done: Pieces of the row scanned (packed or back) afterwards.
        required: Pieces the row needs (or that went out, when taking back).
    """

    status: str
    level: str
    message: str
    warnings: list[str] = field(default_factory=list)
    row: str = ""
    item: str = ""
    done: int = 0
    required: int = 0

    @property
    def changed(self) -> bool:
        """Whether the scan changed the packing list."""
        return self.status in {PACKED, RETURNED}


def _refuse(status: str, message: str, *, level: str = ERROR, item: str = "", row: str = "") -> ScanOutcome:
    return ScanOutcome(status, level, message, item=item, row=row)


def _top_container(item: MaterialItem) -> MaterialItem | None:
    """The case a fixed content travels with: the outermost container that itself travels only with a container."""
    container = item.installed_in
    while container is not None and container.travels_only_with_container and container.installed_in is not None:
        container = container.installed_in
    return container


def _container_on_list(packlist: Packlist, container: MaterialItem | None) -> bool:
    """Whether a case is part of the packing list: chosen for a row, or its product has a row."""
    if container is None:
        return False
    return Allocation.objects.filter(entry__packlist=packlist, item=container).exists() or bool(
        container.product is not None and _rows_of(packlist, container.product.pk)
    )


def _on_list(packlist: Packlist, item: MaterialItem) -> bool:
    """Whether an item belongs to the packing list: it is chosen for it, its product has a row, or its case is on it."""
    if Allocation.objects.filter(entry__packlist=packlist, item=item).exists():
        return True
    if item.travels_only_with_container:
        return _container_on_list(packlist, _top_container(item))
    return item.product is not None and bool(_rows_of(packlist, item.product.pk))


def _may_read_material(rights: Rights | None) -> bool:
    """Whether the person may see items beyond the packing list; ``None`` checks nothing (own check done)."""
    return rights is None or rights.can_read(Module.MATERIAL)


def _read_item(
    code: str, packlist: Packlist, rights: Rights | None = None
) -> tuple[MaterialItem | None, ScanOutcome | None]:
    """The item a code names, or the outcome that says why it is none.

    Several items with the same serial number: the one on the packing list is meant (R1-11); if there is none or more
    than one, the answer says the code is ambiguous. Without the right to read the material, a code that is no item of
    this packing list is answered like an unknown one (R1-15).
    """
    result = scan.resolve(code, prefer=lambda candidate: _on_list(packlist, candidate))
    unknown = _refuse(UNKNOWN, _("Nothing is known under “%(code)s”.") % {"code": result.code[:60]})
    if result.kind == scan.NONE:
        # The message may list the IDs of items with the same serial number: only for who may read the material.
        return None, (_refuse(UNKNOWN, result.message) if _may_read_material(rights) else unknown)
    if result.kind != scan.ITEM or result.item is None:
        if not _may_read_material(rights):
            return None, unknown
        return None, _refuse(
            REFUSED, _("%(title)s is no single item. Scan the label of the item.") % {"title": result.title}
        )
    if not _may_read_material(rights) and not _on_list(packlist, result.item):
        return None, unknown
    return result.item, None


def _busy_with(packlist: Packlist, item: MaterialItem) -> str:
    """The number of the other project the item is chosen for or out with, else ``""`` (PCK-011)."""
    allocation = (
        Allocation.objects.filter(item=item, returned_at__isnull=True)
        .exclude(entry__packlist=packlist)
        .select_related("entry__packlist__project")
        .first()
    )
    return allocation.entry.packlist.project.number if allocation else ""


def _rows_of(packlist: Packlist, product_id: int) -> list[services.PackRow]:
    """The rows of the packing list that take items of this product from the warehouse (no subrentals, no takeovers)."""
    overview = services.build_overview(packlist)
    return [row for row in overview.warehouse_rows if row.product.pk == product_id and not row.is_subrental]


@transaction.atomic
def scan_pack(packlist: Packlist, code: str, *, user: object = None, rights: Rights | None = None) -> ScanOutcome:
    """Mark an item as packed by its scanned label: choose it for its row and count the row up (PCK-010, PCK-011).

    ``rights`` are those of the person (R1-15); the packing list is locked while the scan is checked and made (R1-15).
    """
    packlist = Packlist.objects.select_for_update().get(pk=packlist.pk)
    item, problem = _read_item(code, packlist, rights)
    if problem is not None or item is None:
        return problem or _refuse(UNKNOWN, _("Nothing was entered."))
    shown = item.display_id
    if not packlist.can_be_packed:
        return _refuse(
            REFUSED, _("The material has already been issued. Packing can no longer be changed."), item=shown
        )
    product = item.product
    if product is None:
        return _refuse(
            NOT_ON_LIST,
            _("%(item)s belongs to no product and is not on this packing list.") % {"item": shown},
            item=shown,
        )
    if item.travels_only_with_container:
        # A fixed content of a case goes out with the case; it is not packed on its own.
        container = _top_container(item)
        if container is not None and _container_on_list(packlist, container):
            return ScanOutcome(
                INFO,
                SUCCESS,
                _("%(item)s sits in %(container)s and goes out with it.")
                % {"item": shown, "container": container.display_id},
                item=shown,
            )
        return _refuse(
            NOT_ON_LIST,
            _("%(item)s is fixed in %(container)s, which is not on this packing list.")
            % {"item": shown, "container": container.display_id if container else "?"},
            item=shown,
        )
    rows = _rows_of(packlist, product.pk)
    if item.material_model.is_bulk:
        row = rows[0] if rows else None
        if row is None:
            return _refuse(
                NOT_ON_LIST,
                _("%(item)s (%(product)s) is not on this packing list.") % {"item": shown, "product": product.name},
                item=shown,
            )
        return ScanOutcome(
            BULK,
            WARNING,
            _("%(product)s is bulk material: enter the count in its row.") % {"product": product.name},
            row=row.key,
            item=shown,
        )
    if not rows:
        return _refuse(
            NOT_ON_LIST,
            _("%(item)s (%(product)s) is not on this packing list.") % {"item": shown, "product": product.name},
            item=shown,
        )
    # PCK-011: what cannot be chosen is said, with the reason.
    if not item.is_operational:
        return _refuse(
            REFUSED,
            _("%(item)s cannot be packed: it is %(status)s.") % {"item": shown, "status": item.get_status_display()},
            item=shown,
            row=rows[0].key,
        )
    other = _busy_with(packlist, item)
    if other:
        return _refuse(
            REFUSED,
            _("%(item)s is chosen for or out with another project (%(project)s).") % {"item": shown, "project": other},
            item=shown,
            row=rows[0].key,
        )
    row = next((candidate for candidate in rows if any(c.item_id == item.pk for c in candidate.chosen)), None)
    if row is None:
        row = next((candidate for candidate in rows if candidate.pieces_chosen < candidate.pieces_required), None)
    if row is None:
        return _refuse(
            FULL,
            _("All %(count)d items of %(product)s are chosen already.")
            % {"count": rows[0].pieces_required, "product": product.name},
            level=WARNING,
            item=shown,
            row=rows[0].key,
        )
    entry = services._entry_for(packlist, row)
    now = timezone.now()
    warnings: list[str] = []
    allocation = entry.allocations.filter(item=item, with_container__isnull=True).first()
    if allocation is not None:
        if allocation.issued_at is not None or allocation.packed_scan_at is not None:
            return ScanOutcome(
                DUPLICATE,
                WARNING,
                _("%(item)s is already counted for %(product)s.") % {"item": shown, "product": row.product.name},
                row=row.key,
                item=shown,
                done=_scanned_pieces(entry),
                required=row.pieces_required,
            )
    else:
        kept = [c.item_id for c in row.chosen if not c.is_issued]
        try:
            warnings = services.choose_items(packlist, row.line.pk, row.product.pk, [*kept, item.pk], user=user)
        except ValidationError as error:
            return _refuse(REFUSED, " ".join(error.messages), item=shown, row=row.key)
        allocation = entry.allocations.get(item=item, with_container__isnull=True)
    allocation.packed_scan_at = now
    allocation.save(update_fields=["packed_scan_at"])
    scanned = _scanned_pieces(entry)
    units = scanned // row.pieces_per_unit
    if units > int(row.packed):
        services.set_packed(packlist, row.line.pk, row.product.pk, Decimal(units), user=user)
    if row.consists_of_pieces:
        message = _(
            "%(item)s packed: item %(done)d of %(total)d for %(product)s (%(units)d of %(required)d pieces)."
        ) % {
            "item": shown,
            "done": scanned,
            "total": row.pieces_required,
            "product": row.product.name,
            "units": units,
            "required": int(row.required),
        }
    else:
        message = _("%(item)s packed: %(done)d of %(total)d for %(product)s.") % {
            "item": shown,
            "done": scanned,
            "total": row.pieces_required,
            "product": row.product.name,
        }
    return ScanOutcome(
        PACKED,
        WARNING if warnings else SUCCESS,
        message,
        warnings=list(warnings),
        row=row.key,
        item=shown,
        done=scanned,
        required=row.pieces_required,
    )


def _scanned_pieces(entry: object) -> int:
    """How many items of a row were scanned while packing."""
    return entry.allocations.filter(packed_scan_at__isnull=False, with_container__isnull=True).count()  # type: ignore[attr-defined]


@transaction.atomic
def scan_return(packlist: Packlist, code: str, *, user: object = None, rights: Rights | None = None) -> ScanOutcome:
    """Mark an item as back by its scanned label: count its row up for the return (PCK-016).

    ``rights`` are those of the person (R1-15); the packing list is locked while the scan is made.
    """
    packlist = Packlist.objects.select_for_update().get(pk=packlist.pk)
    item, problem = _read_item(code, packlist, rights)
    if problem is not None or item is None:
        return problem or _refuse(UNKNOWN, _("Nothing was entered."))
    shown = item.display_id
    if not packlist.is_out:
        return _refuse(REFUSED, _("Returns can only be booked while the material is out."), item=shown)
    allocation = (
        Allocation.objects.filter(entry__packlist=packlist, item=item, issued_at__isnull=False)
        .select_related("entry", "entry__line", "with_container__item")
        .order_by("-issued_at", "-pk")
        .first()
    )
    if allocation is None:
        product = item.product
        if product is not None and _rows_of(packlist, product.pk):
            return _refuse(
                REFUSED,
                _("%(item)s was not noted as issued with this packing list. Tick its row by hand.") % {"item": shown},
                level=WARNING,
                item=shown,
            )
        return _refuse(NOT_ON_LIST, _("%(item)s did not go out with this packing list.") % {"item": shown}, item=shown)
    if allocation.returned_at is not None or allocation.returned_scan_at is not None:
        return ScanOutcome(DUPLICATE, WARNING, _("%(item)s is already counted as back.") % {"item": shown}, item=shown)
    allocation.returned_scan_at = timezone.now()
    allocation.save(update_fields=["returned_scan_at"])
    if allocation.with_container_id:
        container = allocation.with_container.item  # type: ignore[union-attr]
        return ScanOutcome(
            RETURNED,
            SUCCESS,
            _("%(item)s was in %(container)s and comes back with it.")
            % {"item": shown, "container": container.display_id},
            item=shown,
        )
    entry = allocation.entry
    overview = services.build_overview(packlist)
    row = services.find_row(overview, entry.line_id, entry.product_id)
    scanned = entry.allocations.filter(returned_scan_at__isnull=False, with_container__isnull=True).count()
    units = scanned // row.pieces_per_unit
    if units > int(row.returned):
        try:
            services.set_returned(packlist, row.line.pk, row.product.pk, Decimal(units), user=user)
        except ValidationError as error:
            return _refuse(REFUSED, " ".join(error.messages), item=shown, row=row.key)
    return ScanOutcome(
        RETURNED,
        SUCCESS,
        _("%(item)s is back: %(done)d of %(total)d for %(product)s.")
        % {
            "item": shown,
            "done": scanned,
            "total": entry.allocations.filter(with_container__isnull=True, issued_at__isnull=False).count(),
            "product": row.product.name,
        },
        row=row.key,
        item=shown,
        done=scanned,
        required=int(row.issued),
    )
