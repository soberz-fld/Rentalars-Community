# SPDX-License-Identifier: GPL-3.0-or-later
"""Bulk material built into an item: installing and taking out (built-in quantity material; MAT-040).

A rack case holds 10 m of cable and 4 connectors; a vehicle carries a box of screws. The cable, connectors and
screws are bulk material (MAT-005, one row with a quantity). :func:`install_quantity` builds a quantity of such a
row into an item, :func:`remove_quantity` takes it out again.

The rules
---------
* The quantity built in leaves the *free* stock: the quantity of the bulk row is reduced by it, and raised again
  when the material is taken out. So the stock of the product, the availability and the packing – which all read
  the quantity of the row – never count what sits in a case twice.
* Only a bulk row that is fit for use can be built in, and only into an item of individual items that is not
  archived – never into bulk material (MAT-040: bulk material cannot itself be the target of a built-in).
* Both movements are written to the history of the container *and* of the bulk row as an event with the quantity,
  the user and the time; the change of the row's quantity is logged by the change log as for any change.
* A case that goes out takes what is built in along: nothing has to be booked, as the quantity is no longer free
  stock. The packing list names it under the case (``packing.services``).

Browser and API call these functions (API-002).
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.material.installed_models import InstalledQuantity
from rentalars.material.models import OPERATIONAL_STATUSES, MaterialItem


def _label(item: MaterialItem) -> str:
    """The ID and the short name of an item, as the events name it."""
    return f"{item.display_id} {item.material_model.display_short_name}"


def container_problem(container: MaterialItem) -> str | None:
    """Why material cannot be built into this item, or ``None`` (MAT-040)."""
    if container.material_model.is_bulk:
        return str(_("Bulk material cannot contain other items."))
    if container.is_archived:
        return str(_("The item %(id)s is archived and cannot contain other items.") % {"id": container.display_id})
    return None


def material_problem(material: MaterialItem) -> str | None:
    """Why this item cannot be built in as bulk material, or ``None`` (MAT-040)."""
    if not material.material_model.is_bulk:
        return str(
            _("%(id)s is not bulk material. Items of individual pieces are installed with “Installed in”.")
            % {"id": material.display_id}
        )
    if material.status not in OPERATIONAL_STATUSES:
        return str(_("%(id)s is not fit for use and cannot be built in.") % {"id": material.display_id})
    return None


def pieces_out_with_projects(row: MaterialItem) -> int:
    """Pieces of the product of a bulk row that are out of the warehouse with projects and not taken back (R1-13).

    "Out" bulk material is not taken off the quantity of its rows – it comes back to them –, so it must not be
    built in or sold in the meantime. Sold pieces never come back and were taken off the rows when they went out,
    so they do not count (L5).
    """
    from rentalars.packing.models import PackEntry

    product = row.product
    if product is None:
        return 0
    out = sum(
        (
            entry.out_quantity
            for entry in PackEntry.objects.filter(product=product, issued_quantity__gt=0).exclude(line__is_sale=True)
        ),
        Decimal(0),
    )
    return int(out) * max(product.pieces_per_product or 1, 1)


def committed_quantity(row: MaterialItem) -> int:
    """How many pieces of a bulk row are committed to projects that have them out (the rest is free; R1-13).

    The pieces that are out came from the rows of the product; the other rows are taken first, what they cannot
    cover is committed to this row.
    """
    out = pieces_out_with_projects(row)
    if not out:
        return 0
    product = row.product
    others = (
        MaterialItem.objects.for_product(product.pk)
        .filter(material_model__tracking_mode="bulk")
        .operational()
        .exclude(pk=row.pk)
        .aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    return min(row.quantity, max(out - others, 0))


def free_quantity(row: MaterialItem) -> int:
    """How many pieces of a bulk row can be built in or sold now: its quantity less what projects have out."""
    return max(row.quantity - committed_quantity(row), 0)


@transaction.atomic
def install_quantity(
    container: MaterialItem, material: MaterialItem, quantity: int, *, user: Any = None, note: str = ""
) -> InstalledQuantity:
    """Build a quantity of a bulk row into an item (MAT-040).

    Args:
        container: The item that takes the material: a case, rack, vehicle, device.
        material: The bulk row the quantity comes from.
        quantity: How many pieces (meters, screws …); at least 1, at most what is free.
        user: Who builds it in.
        note: An optional remark, e.g. "spare cable".

    Returns:
        The installed quantity of this pair; when the pair existed, with the quantity added.

    Raises:
        ValidationError: The container or the material does not fit, or less than ``quantity`` is free.
    """
    if quantity < 1:
        raise ValidationError({"quantity": _("Enter a quantity of at least 1.")})
    # Check the rows as they are now, locked – not the objects the caller loaded earlier.
    container = MaterialItem.objects.select_for_update().select_related("material_model").get(pk=container.pk)
    row = MaterialItem.objects.select_for_update().select_related("material_model").get(pk=material.pk)
    problem = container_problem(container) or material_problem(row)
    if problem:
        raise ValidationError(problem)
    free = free_quantity(row)
    if quantity > free:
        message = _("Only %(free)s of %(id)s are free; %(wanted)s cannot be built in.") % {
            "free": free,
            "id": row.display_id,
            "wanted": quantity,
        }
        if free < row.quantity:
            message += " " + _("%(out)s pieces are out with projects.") % {"out": row.quantity - free}
        raise ValidationError({"quantity": message})
    row.quantity -= quantity
    row.save()
    material.quantity = row.quantity
    installed, created = InstalledQuantity.objects.select_for_update().get_or_create(
        container=container,
        material=row,
        defaults={
            "quantity": quantity,
            "note": note.strip()[:250],
            "installed_by": user if getattr(user, "pk", None) else None,
            "installed_at": timezone.now(),
        },
    )
    if not created:
        installed.quantity += quantity
        if note.strip():
            installed.note = note.strip()[:250]
        installed.save()
    details = {"quantity": quantity, "item": _label(row), "container": _label(container)}
    record_event(container, "item.quantity_installed", details)
    record_event(row, "item.quantity_built_in", details)
    return installed


@transaction.atomic
def remove_quantity(
    container: MaterialItem, material: MaterialItem, quantity: int | None = None, *, user: Any = None
) -> int:
    """Take built-in material out of an item; it is free stock again (MAT-040).

    Args:
        container: The item it sits in.
        material: The bulk row.
        quantity: How many pieces to take out; ``None``: all of it.
        user: Who takes it out (the change log names the actor already; the argument is kept for symmetry).

    Returns:
        The number of pieces taken out.

    Raises:
        ValidationError: Nothing of this material sits in the container, or less than ``quantity`` does.
    """
    installed = InstalledQuantity.objects.select_for_update().filter(container=container, material=material).first()
    if installed is None:
        raise ValidationError(
            _("Nothing of %(id)s is built into %(container)s.")
            % {"id": material.display_id, "container": container.display_id}
        )
    taken = installed.quantity if quantity is None else quantity
    if taken < 1:
        raise ValidationError({"quantity": _("Enter a quantity of at least 1.")})
    if taken > installed.quantity:
        raise ValidationError(
            {
                "quantity": _("Only %(built)s of %(id)s are built into %(container)s.")
                % {"built": installed.quantity, "id": material.display_id, "container": container.display_id}
            }
        )
    row = MaterialItem.objects.select_for_update().select_related("material_model").get(pk=material.pk)
    row.quantity += taken
    row.save()
    material.quantity = row.quantity
    if taken == installed.quantity:
        installed.delete()
    else:
        installed.quantity -= taken
        installed.save()
    details = {"quantity": taken, "item": _label(row), "container": _label(container)}
    record_event(container, "item.quantity_removed", details)
    record_event(row, "item.quantity_taken_out", details)
    return taken


def installed_in(container: MaterialItem) -> list[InstalledQuantity]:
    """What is built into an item, by the ID of the bulk row (the bill of material of the container)."""
    return list(
        InstalledQuantity.objects.filter(container=container)
        .select_related("material__material_model__default_product__unit", "installed_by")
        .order_by("material__inventory_number")
    )


def installed_places(material: MaterialItem) -> list[InstalledQuantity]:
    """Where a bulk row is built in, by the ID of the container."""
    return list(
        InstalledQuantity.objects.filter(material=material)
        .select_related("container__material_model", "installed_by")
        .order_by("container__inventory_number")
    )


def installed_totals(material_ids: Iterable[int]) -> dict[int, int]:
    """How many pieces of each bulk row are built in somewhere; rows with none are missing (one query)."""
    ids = list(material_ids)
    if not ids:
        return {}
    return {
        row["material_id"]: int(row["total"])
        for row in InstalledQuantity.objects.filter(material_id__in=ids)
        .values("material_id")
        .annotate(total=Sum("quantity"))
        .order_by()
    }


def contents_of(container_ids: Iterable[int]) -> dict[int, list[InstalledQuantity]]:
    """What is built into each of the given containers, for lists such as the packing list (one query)."""
    ids = list(container_ids)
    result: dict[int, list[InstalledQuantity]] = {}
    if not ids:
        return result
    for installed in (
        InstalledQuantity.objects.filter(container_id__in=ids)
        .select_related("material__material_model__default_product__unit")
        .order_by("material__inventory_number")
    ):
        result.setdefault(installed.container_id, []).append(installed)
    return result
