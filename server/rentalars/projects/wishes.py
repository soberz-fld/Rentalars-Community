# SPDX-License-Identifier: GPL-3.0-or-later
"""Wishes for specific material on a line: what was asked for, and can it be met (PRJ-064).

Planning counts products, not items (VFG-002): "6 cables", whichever six. A
line can still name the model or even the single item the planner would like
to have. That wish is a hint for the warehouse. It never blocks anything and
it never changes the availability figures – but it would be of little use if
nobody noticed that it cannot be met. This module finds those cases:

* the wished item is defective, in repair, retired …;
* the wished item sits firmly inside another item and cannot travel alone;
* another line wants the same item at the same time;
* more pieces of a model are wanted at the same time than are fit for use.

Example: project P1 wants the mixing desk 0042 from the 10th to the 12th.
Project P2 is planned for the 11th and also names 0042. Both lines are saved;
both show "0042 is also wanted for …" until one of them picks another desk.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q, Sum, prefetch_related_objects
from django.utils.translation import gettext as _

from rentalars.material.models import ItemBlock, MaterialItem, MaterialModel
from rentalars.products.models import Product
from rentalars.projects.models import FIRM_STATUSES, SOFT_STATUSES, MaterialLine, Project

#: Projects in these statuses hold on to material; wishes of other projects are ignored.
_RESERVING_STATUSES = FIRM_STATUSES | SOFT_STATUSES

#: How many project numbers a warning names before it says "and others".
_MAX_NAMED_PROJECTS = 3


@dataclass
class Wish:
    """The wish of one line, prepared for display."""

    model: MaterialModel | None
    item: MaterialItem | None
    #: Reasons why the wish cannot be met as things stand. Empty: all fine.
    warnings: list[str] = field(default_factory=list)
    #: (piece share) All wished items, the first one is ``item``. Each covers one piece of the line.
    items: list[MaterialItem] = field(default_factory=list)
    #: (piece share) How many pieces the line stands for (quantity × pieces per product).
    pieces: int = 1

    @property
    def label(self) -> str:
        """What is wished for, in words: ``item 0042 (Cordial CPM 5 FM)``, ``items 0042, 0043 (…)`` or ``model …``."""
        items = self.items or ([self.item] if self.item is not None else [])
        if len(items) > 1:
            return _("items %(items)s") % {"items": ", ".join(item_label(item) for item in items)}
        if items:
            return _("item %(id)s (%(model)s)") % {
                "id": items[0].display_id,
                "model": items[0].material_model.display_short_name,
            }
        if self.model is not None:
            return _("model %(model)s") % {"model": self.model.name}
        return ""

    @property
    def share(self) -> str:
        """Which part of the line the wished items are, if the line has several pieces: ``1 of 10 pieces``.

        The wished items are exactly these pieces; the others come from any item of the product (piece share).
        """
        items = self.items or ([self.item] if self.item is not None else [])
        if not items or self.pieces <= 1:
            return ""
        return _("%(count)d of %(total)d pieces") % {"count": len(items), "total": self.pieces}


def item_label(item: MaterialItem) -> str:
    """One item in a list of wished items: ``0042 (Cordial CPM 5 FM)`` (piece share)."""
    return f"{item.display_id} ({item.material_model.display_short_name})"


def _overlap(
    first: tuple[datetime.datetime, datetime.datetime], second: tuple[datetime.datetime, datetime.datetime]
) -> bool:
    """Whether two periods share at least one moment."""
    return first[0] < second[1] and second[0] < first[1]


def _name_projects(numbers: Iterable[str]) -> str:
    """Join project numbers for a warning: ``2027-0003, 2027-0007 and others``."""
    unique = sorted(set(numbers))
    text = ", ".join(unique[:_MAX_NAMED_PROJECTS])
    if len(unique) > _MAX_NAMED_PROJECTS:
        text += " " + _("and others")
    return text


def load_wishes(project: Project, lines: list[MaterialLine], *, shown: set[int] | None = None) -> dict[int, Wish]:
    """Return the wishes of a project's lines with their warnings (PRJ-064).

    Costs nothing for projects without wishes, and a fixed handful of
    queries otherwise – it does not grow with the number of lines (NFA-014).

    Args:
        project: The project.
        lines: All lines of the project; they compete with each other too.
        shown: The IDs of the lines to report on; ``None`` reports on all.

    Returns:
        ``{line id: Wish}`` for the lines that carry a wish.
    """
    wishing = [line for line in lines if line.preferred_item_id or line.preferred_model_id]
    reported = [line for line in wishing if shown is None or line.pk in shown]
    if not reported:
        return {}

    # Piece share: a line can wish for several items; one query for all of them, none without a wish.
    prefetch_related_objects([line for line in wishing if line.preferred_item_id], "further_preferred_items")
    item_ids = {item_id for line in wishing for item_id in line.wished_item_ids}
    model_ids = {line.preferred_model_id for line in wishing if line.preferred_model_id}
    items = MaterialItem.objects.select_related("material_model", "installed_in").in_bulk(item_ids)
    models = MaterialModel.objects.select_related("default_product").in_bulk(
        model_ids | {item.material_model_id for item in items.values()}
    )

    # Lines of other projects that hold on to the same items or models.
    elsewhere = list(
        MaterialLine.objects.filter(Q(preferred_item_id__in=item_ids) | Q(preferred_model_id__in=model_ids))
        .exclude(project=project)
        .filter(project__status__in=_RESERVING_STATUSES)
        .values_list(
            "preferred_item_id",
            "preferred_model_id",
            "start",
            "end",
            "quantity",
            "project__number",
            "product__pieces_per_product",
        )
    )
    # Piece share: the same for lines of other projects that name the item as a further one.
    elsewhere_further = list(
        MaterialLine.further_preferred_items.through.objects.filter(
            materialitem_id__in=item_ids, materialline__preferred_item__isnull=False
        )
        .exclude(materialline__project=project)
        .filter(materialline__project__status__in=_RESERVING_STATUSES)
        .values_list(
            "materialitem_id",
            "materialline__start",
            "materialline__end",
            "materialline__project__number",
        )
    )
    # Pieces per product; PRD-052: the lines count products, the model's items are counted in pieces –
    # each line wants as many items as its own product has pieces, whatever the model's default product says.
    own_pieces = dict(
        Product.objects.filter(pk__in={line.product_id for line in wishing if line.product_id}).values_list(
            "pk", "pieces_per_product"
        )
    )
    here = [
        (
            line.preferred_item_id,
            line.preferred_model_id,
            line.start,
            line.end,
            line.quantity * own_pieces.get(line.product_id, 1),
            project.number,
            line.pk,
        )
        for line in wishing
    ]
    # Piece share: the further wished items of the lines here, as items of their own.
    here_further = [
        (item_id, line.start, line.end, project.number, line.pk)
        for line in wishing
        for item_id in line.wished_item_ids[1:]
    ]

    # (R3-9) Periods in which a wished item is blocked (MAT-024); one query, none without wished items.
    blocks_of: dict[int, list[tuple[datetime.datetime, datetime.datetime, str]]] = defaultdict(list)
    if item_ids:
        for item_id, start, end, reason in ItemBlock.objects.filter(
            item_id__in=item_ids,
            start__lt=max(line.end for line in wishing),
            end__gt=min(line.start for line in wishing),
        ).values_list("item_id", "start", "end", "reason"):
            blocks_of[item_id].append((start, end, reason))

    # How many pieces of each wished model are fit for use (MAT-021).
    fit_for_use: dict[int, int] = dict(
        MaterialItem.objects.filter(material_model_id__in=model_ids)
        .operational()
        .values("material_model_id")
        .annotate(pieces=Sum("quantity"))
        .values_list("material_model_id", "pieces")
    )

    by_item: dict[int, list[tuple[datetime.datetime, datetime.datetime, str, int | None]]] = defaultdict(list)
    by_model: dict[int, list[tuple[datetime.datetime, datetime.datetime, Decimal, int | None]]] = defaultdict(list)
    for item_id, model_id, start, end, quantity, number, pieces in elsewhere:
        if item_id:
            by_item[item_id].append((start, end, number, None))
        if model_id:
            by_model[model_id].append((start, end, quantity * (pieces or 1), None))
    for item_id, start, end, number in elsewhere_further:
        by_item[item_id].append((start, end, number, None))
    for item_id, model_id, start, end, quantity, number, line_id in here:
        if item_id:
            by_item[item_id].append((start, end, number, line_id))
        if model_id:
            by_model[model_id].append((start, end, quantity, line_id))
    for item_id, start, end, number, line_id in here_further:
        by_item[item_id].append((start, end, number, line_id))

    wishes: dict[int, Wish] = {}
    for line in reported:
        wished = [items[item_id] for item_id in line.wished_item_ids if item_id in items]
        item = wished[0] if wished else None
        model = models.get(line.preferred_model_id) if line.preferred_model_id else None
        if item is not None and model is None:
            model = models.get(item.material_model_id)
        if item is None and model is None:
            continue  # the wished material was deleted in the meantime
        wish = Wish(model=model, item=item, items=wished, pieces=line.pieces_total)
        period = (line.start, line.end)

        for wished_item in wished:
            if not wished_item.is_operational:
                wish.warnings.append(
                    _("Item %(id)s is %(status)s.")
                    % {"id": wished_item.display_id, "status": wished_item.get_status_display()}
                )
            if wished_item.travels_only_with_container:
                wish.warnings.append(
                    _("Item %(id)s is permanently installed in %(container)s and does not travel on its own.")
                    % {"id": wished_item.display_id, "container": wished_item.installed_in.display_id}
                )
            for start, end, reason in blocks_of.get(wished_item.pk, ()):
                if _overlap(period, (start, end)):
                    wish.warnings.append(
                        _("Item %(id)s is blocked in this period: %(reason)s.")
                        % {"id": wished_item.display_id, "reason": reason}
                    )
                    break
            rivals = [
                number
                for start, end, number, line_id in by_item[wished_item.pk]
                if line_id != line.pk and _overlap(period, (start, end))
            ]
            if rivals:
                wish.warnings.append(
                    _("Item %(id)s is also wanted at the same time: %(projects)s.")
                    % {"id": wished_item.display_id, "projects": _name_projects(rivals)}
                )
        if item is None and model is not None:
            # The quantities are in items already (see above).
            wanted = sum(
                (quantity for start, end, quantity, _line_id in by_model[model.pk] if _overlap(period, (start, end))),
                Decimal("0"),
            )
            available = fit_for_use.get(model.pk, 0)
            if wanted > available:
                wish.warnings.append(
                    _(
                        "%(wanted)s pieces of the model %(model)s are wanted at the same time, "
                        "but only %(available)s are fit for use."
                    )
                    % {"wanted": int(wanted), "model": model.name, "available": available}
                )
        wishes[line.pk] = wish
    return wishes
