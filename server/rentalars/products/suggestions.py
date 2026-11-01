# SPDX-License-Identifier: GPL-3.0-or-later
"""Accessory and replacement suggestions for the planning of a project (PRD-023, VFG-015).

The requirement: suggestions for replacements and accessories. Two kinds of hints, shown beside the planning and never in its way:

**Accessories** (``suggest accessories``)
    For every product in the planning that has accessories (``ProductRelation``), the accessories that are not in the
    planning yet – neither as a line nor inside a kit of the planning. The quantity is the quantity of the product
    times the pieces per piece of the relation, rounded up: 6 speakers and 1 cable per speaker make 6 cables. A
    required accessory says so. One click adds the line (:func:`accept`).

**Replacements** (``suggest replacements``)
    For a line that is short in its period – or whose product is deactivated –, the replacement products of its
    product, each with what is free of it in the period of the line. The numbers are those of the planning: the
    replacement is judged by the availability engine as if it were added to the project
    (``AvailabilityEngine.check_candidate``), nothing is calculated again here. Shown only to who may see
    availability (AUT-032).

A suggestion can be dismissed for one project (``DismissedSuggestion``); it is not made again there. For the offer
the same hints are shown, without adding anything (:func:`suggestions_for_project` with ``for_offer``).

Browser and API call these functions (API-002).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.availability.engine import AvailabilityEngine, ProductAvailability, ProductShortage
from rentalars.products.models import Product
from rentalars.products.relation_models import DismissedSuggestion, ProductRelation, RelationKind
from rentalars.products.services import flatten_kit, load_kit_structure
from rentalars.projects.models import MaterialLine, Project

#: At most this many suggestions of each kind are made at once; the planner works through them step by step.
MAX_SUGGESTIONS = 12

#: At most this many short lines are judged for replacements at once (all in one run of the availability engine).
MAX_SHORT_LINES = 8

#: (R3-6) At most this many replacements are checked at once: each costs a run of the availability
#: engine (about five queries), and the panel is asked for after every change of the planning.
MAX_REPLACEMENT_CHECKS = 6


@dataclass
class AccessorySuggestion:
    """An accessory of a product of the planning that is not planned yet."""

    relation: ProductRelation
    #: The first line of the product that has the accessory.
    line: MaterialLine
    quantity: int
    #: What is free of the accessory in the period of the project; ``None`` for who may not see availability.
    availability: ProductAvailability | None = None
    #: (R3-4) Every relation that names this accessory at a product of the planning, ``relation``
    #: first. The quantity is the sum over all of them; the accessory is required if one of them says so.
    relations: list[ProductRelation] = field(default_factory=list)
    #: (R3-4) Pieces of the accessory the planning has already; the suggestion is for the rest.
    planned: int = 0

    def __post_init__(self) -> None:
        """A suggestion from a single relation names just that one."""
        if not self.relations:
            self.relations = [self.relation]

    @property
    def product(self) -> Product:
        """The product that has the accessory (the first one, if several have it)."""
        return self.relation.product

    @property
    def product_names(self) -> str:
        """The names of all products of the planning that have the accessory: ``Speaker Alpha, Speaker Beta``."""
        names: list[str] = []
        for relation in self.relations:
            if relation.product.name not in names:
                names.append(relation.product.name)
        return ", ".join(names)

    @property
    def accessory(self) -> Product:
        """The accessory."""
        return self.relation.related_product

    @property
    def is_required(self) -> bool:
        """Whether one of the products cannot be used without it."""
        return any(relation.is_required for relation in self.relations)

    @property
    def free(self) -> int | None:
        """The free pieces of the accessory, or ``None`` if unknown or not checked."""
        if self.availability is None or not self.availability.checked:
            return None
        return max(self.availability.free_after_optional, 0)

    @property
    def is_short(self) -> bool:
        """Whether less is free than the suggestion needs."""
        free = self.free
        return free is not None and free < self.quantity


@dataclass
class ReplacementSuggestion:
    """A replacement of a product whose line is short or deactivated."""

    relation: ProductRelation
    line: MaterialLine
    #: ``short`` (not enough in the period) or ``inactive`` (the product is deactivated).
    reason: str
    #: Pieces of the line's product that are missing.
    missing: int
    #: Pieces of the replacement that stand in for the missing ones.
    quantity: int
    #: The verdict of the availability engine for the replacement added to the project.
    detail: ProductShortage | None = None

    @property
    def replacement(self) -> Product:
        """The replacement."""
        return self.relation.related_product

    @property
    def free(self) -> int | None:
        """The free pieces of the replacement in the period of the line."""
        return None if self.detail is None else self.detail.free

    @property
    def covers(self) -> bool:
        """Whether the replacement covers the missing pieces completely."""
        return self.detail is not None and self.detail.shortage == 0


@dataclass
class Suggestions:
    """What the planning of a project suggests."""

    accessories: list[AccessorySuggestion] = field(default_factory=list)
    replacements: list[ReplacementSuggestion] = field(default_factory=list)
    #: Relations dismissed in this project, as ``(relation, kind)`` – to show and to bring back.
    dismissed: list[ProductRelation] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing to suggest."""
        return not self.accessories and not self.replacements

    @property
    def count(self) -> int:
        """How many suggestions there are (accessories and replacements)."""
        return len(self.accessories) + len(self.replacements)


def has_relations() -> bool:
    """Whether any accessory or replacement exists at all – the planning shows nothing without (one cheap query)."""
    return ProductRelation.objects.exists()


def _planned_lines(project: Project) -> list[MaterialLine]:
    """The material lines of the project that count: with a product, no text line."""
    return list(project.material_lines.filter(product__isnull=False, is_text=False).select_related("product", "group"))


def _ceil(value: Decimal) -> int:
    """Whole pieces, rounded up – on the safe side; at least 1."""
    return max(math.ceil(value), 1)


def suggestions_for_project(
    project: Project, *, rights: Rights, include_dismissed: bool = False, engine: AvailabilityEngine | None = None
) -> Suggestions:
    """What the planning of a project suggests: accessories not planned yet, replacements for short lines.

    Args:
        project: The project.
        rights: The rights of the reader. Availability figures and the replacements – which tell that a line is
            short – only for who has the special right to see availability (AUT-032).
        include_dismissed: Also the suggestions dismissed in this project (to show them again).
        engine: The availability engine, if the caller has one at hand.
    """
    result = Suggestions()
    lines = _planned_lines(project)
    if not lines:
        return result
    product_ids = {line.product_id for line in lines}
    relations = list(
        ProductRelation.objects.filter(product_id__in=product_ids, related_product__is_active=True)
        .select_related("product", "related_product", "related_product__unit")
        .order_by("product__article_number", "kind", "position", "id")
    )
    dismissed_ids = set(DismissedSuggestion.objects.filter(project=project).values_list("relation_id", flat=True))
    if not include_dismissed:
        result.dismissed = [relation for relation in relations if relation.pk in dismissed_ids]
        relations = [relation for relation in relations if relation.pk not in dismissed_ids]
    elif dismissed_ids:
        result.dismissed = [relation for relation in relations if relation.pk in dismissed_ids]
    if not relations:
        return result
    sees_availability = rights.has(SpecialRight.AVAILABILITY)
    engine = engine or AvailabilityEngine()
    _accessories(project, lines, relations, result, engine, sees_availability)
    if sees_availability:
        _replacements(project, lines, relations, result, engine)
    return result


def _accessories(
    project: Project,
    lines: list[MaterialLine],
    relations: list[ProductRelation],
    result: Suggestions,
    engine: AvailabilityEngine,
    sees_availability: bool,
) -> None:
    """Fill ``result.accessories``: the accessories of the planned products that are not in the planning (enough).

    (R3-4) Several products can name the same accessory: the quantity is the sum over all of them,
    rounded up once, and it is required if one of them says so. An accessory that is planned already but in a smaller
    quantity than needed is suggested again for the rest, so a quantity lowered by the planner is noticed.
    """
    structure = load_kit_structure()
    planned: set[int] = set()
    inside_kits: set[int] = set()
    for line in lines:
        planned.add(line.product_id)
        if line.product_id in structure:
            inside_kits.update(flatten_kit(line.product_id, structure))
    quantity_of: dict[int, Decimal] = {}
    first_line: dict[int, MaterialLine] = {}
    for line in lines:
        if not line.counts_toward_total:
            continue
        quantity_of[line.product_id] = quantity_of.get(line.product_id, Decimal(0)) + line.quantity
        first_line.setdefault(line.product_id, line)
    by_accessory: dict[int, list[ProductRelation]] = {}
    for relation in relations:
        if relation.kind == RelationKind.ACCESSORY and relation.product_id in quantity_of:
            by_accessory.setdefault(relation.related_product_id, []).append(relation)
    found: list[AccessorySuggestion] = []
    for accessory_id, named in by_accessory.items():
        if accessory_id in inside_kits:
            continue
        needed = _ceil(
            sum((quantity_of[relation.product_id] * relation.quantity_per_piece for relation in named), Decimal(0))
        )
        have = 0
        if accessory_id in planned:
            if accessory_id not in quantity_of:
                continue  # only on lines that do not count (optional …): the planner has seen it
            have = math.ceil(quantity_of[accessory_id])
            if needed - have < 1:
                continue
        found.append(
            AccessorySuggestion(
                relation=named[0],
                line=first_line[named[0].product_id],
                quantity=needed - have,
                relations=named,
                planned=have,
            )
        )
    found = found[:MAX_SUGGESTIONS]
    if found and sees_availability:
        free = engine.availability(
            [suggestion.accessory.pk for suggestion in found],
            project.start,
            project.end,
            exclude_project_id=project.pk,
        )
        for suggestion in found:
            suggestion.availability = free.get(suggestion.accessory.pk)
    result.accessories = found


def _replacements(
    project: Project,
    lines: list[MaterialLine],
    relations: list[ProductRelation],
    result: Suggestions,
    engine: AvailabilityEngine,
) -> None:
    """Fill ``result.replacements``: for each short or deactivated line, the replacements and what is free of them.

    (R3-5, R3-6) A replacement that is planned already is not suggested again. The cost stays small:
    the lines are judged in ONE run of the engine (not one per line), the lines and groups of the project are loaded
    once for all candidates, and at most :data:`MAX_REPLACEMENT_CHECKS` candidates are checked (one run of the engine each).
    """
    by_product: dict[int, list[ProductRelation]] = {}
    for relation in relations:
        if relation.kind == RelationKind.REPLACEMENT:
            by_product.setdefault(relation.product_id, []).append(relation)
    if not by_product:
        return
    structure = load_kit_structure()
    planned = {line.product_id for line in lines}
    for line in lines:
        if line.product_id in structure:
            planned.update(flatten_kit(line.product_id, structure))
    wanting = [
        line for line in lines if line.product_id in by_product and line.counts_toward_total and not line.product.is_kit
    ]
    if not wanting:
        return
    verdicts: dict[Any, Any] | None = None
    all_lines: list[MaterialLine] = []
    groups: list[Any] = []
    judged = 0
    checked = 0
    found: list[ReplacementSuggestion] = []
    for line in wanting:
        if not line.product.is_active:
            reason, missing = "inactive", _ceil(line.quantity)
        else:
            if judged >= MAX_SHORT_LINES:
                continue
            judged += 1
            if verdicts is None:
                all_lines = list(project.material_lines.select_related("product"))
                groups = list(project.groups.all())
                verdicts = engine.project_availability(project, all_lines, groups)
            verdict = verdicts.get(line.pk)
            if verdict is None or verdict.status != "short":
                continue
            reason, missing = "short", max(verdict.shortage_total, 1)
        for relation in by_product[line.product_id]:
            if relation.related_product_id in planned or checked >= MAX_REPLACEMENT_CHECKS:
                continue
            checked += 1
            if not all_lines:
                all_lines = list(project.material_lines.select_related("product"))
                groups = list(project.groups.all())
            needed = _ceil(Decimal(missing) * relation.quantity_per_piece)
            check = engine.check_candidate(
                project, relation.related_product, needed, line.start, line.end, lines=all_lines, groups=groups
            )
            found.append(
                ReplacementSuggestion(
                    relation=relation,
                    line=line,
                    reason=reason,
                    missing=missing,
                    quantity=needed,
                    detail=check.main,
                )
            )
    # The ones that cover the shortage completely first, then the most that is free.
    found.sort(key=lambda suggestion: (not suggestion.covers, -(suggestion.free or 0)))
    result.replacements = found[:MAX_SUGGESTIONS]


# --- Taking a suggestion --------------------------------------------------------------------


def accept(
    project: Project, relation_id: int, *, rights: Rights, line_id: int | None = None, quantity: int | None = None
) -> Any:
    """Add the accessory or replacement of a suggestion to the planning as a new line (PRD-023, VFG-015).

    The line gets the group of the line it belongs to. Nothing is changed in the line it is a replacement for:
    the planner decides what to do with it.

    Args:
        project: The project.
        relation_id: The accessory or replacement.
        rights: The rights of the caller.
        line_id: The line the suggestion was made for; default: the first line of the product.
        quantity: Pieces to add; default: the quantity the suggestion names.

    Returns:
        The result of adding the line (``projects.services.LineResult``).

    Raises:
        ValidationError: The relation does not belong to a product of the planning, the quantity is wrong, or the
            line cannot be added (closed project, deactivated product …).
    """
    from rentalars.projects import services as project_services

    relation = (
        ProductRelation.objects.filter(pk=relation_id)
        .select_related("product", "related_product", "related_product__unit")
        .first()
    )
    lines = [
        line for line in _planned_lines(project) if relation is not None and line.product_id == relation.product_id
    ]
    if relation is None or not lines:
        raise ValidationError(_("This suggestion does not belong to a product of this planning."))
    line = next((candidate for candidate in lines if candidate.pk == line_id), lines[0])
    # (R3-4, R3-5) What is planned already decides, so a second click adds nothing more.
    planned = _planned_lines(project)
    have = sum(
        (
            candidate.quantity
            for candidate in planned
            if candidate.product_id == relation.related_product_id and candidate.counts_toward_total
        ),
        Decimal(0),
    )
    if relation.kind == RelationKind.ACCESSORY:
        needed = _accessory_need(planned, relation)
        missing = needed - math.ceil(have)
        if have and missing < 1:
            raise ValidationError(
                _("%(name)s is already in the planning in the quantity needed.") % {"name": relation.related_product}
            )
        if quantity is None:
            quantity = missing if have else needed
    else:
        if have:
            raise ValidationError(_("%(name)s is already in the planning.") % {"name": relation.related_product})
        if quantity is None:
            verdict = AvailabilityEngine().line_availability(line)
            quantity = _ceil(Decimal(max(verdict.shortage_total, 1)) * relation.quantity_per_piece)
    if quantity < 1:
        raise ValidationError({"quantity": _("Enter a quantity of at least 1.")})
    result = project_services.add_line(
        project, rights=rights, product=relation.related_product, quantity=Decimal(quantity), group=line.group
    )
    DismissedSuggestion.objects.filter(project=project, relation=relation).delete()
    return result


def _accessory_need(planned: list[MaterialLine], relation: ProductRelation) -> int:
    """How many pieces of the accessory of ``relation`` the planning needs: the sum over all products that name it.

    (R3-4) Whatever product of the planning names the accessory counts, not just the one of the
    relation the planner clicked. Rounded up once, at least 1.
    """
    quantity_of: dict[int, Decimal] = {}
    for line in planned:
        if line.counts_toward_total:
            quantity_of[line.product_id] = quantity_of.get(line.product_id, Decimal(0)) + line.quantity
    named = ProductRelation.objects.filter(
        related_product_id=relation.related_product_id, kind=RelationKind.ACCESSORY, product_id__in=quantity_of
    )
    return _ceil(sum((quantity_of[row.product_id] * row.quantity_per_piece for row in named), Decimal(0)))


def dismiss(project: Project, relation_ids: list[int], *, user: Any = None) -> int:
    """Dismiss suggestions in one project; they are not made again there. Returns how many were newly dismissed."""
    relations = ProductRelation.objects.filter(pk__in=relation_ids)
    done = 0
    for relation in relations:
        _row, created = DismissedSuggestion.objects.get_or_create(
            project=project, relation=relation, defaults={"dismissed_by": user if getattr(user, "pk", None) else None}
        )
        done += int(created)
    return done


def restore(project: Project, relation_ids: list[int] | None = None) -> int:
    """Bring dismissed suggestions back – the given ones, or all of this project. Returns how many."""
    rows = DismissedSuggestion.objects.filter(project=project)
    if relation_ids is not None:
        rows = rows.filter(relation_id__in=relation_ids)
    count = rows.count()
    rows.delete()
    return count


# --- Managing the relations of a product -----------------------------------------------------


def relations_of(product: Product) -> dict[str, list[ProductRelation]]:
    """The accessories and replacements of a product, each in its order."""
    rows = list(
        ProductRelation.objects.filter(product=product)
        .select_related("related_product", "related_product__unit")
        .order_by("position", "id")
    )
    return {
        RelationKind.ACCESSORY: [row for row in rows if row.kind == RelationKind.ACCESSORY],
        RelationKind.REPLACEMENT: [row for row in rows if row.kind == RelationKind.REPLACEMENT],
    }


def used_as_relation(product: Product) -> list[ProductRelation]:
    """Where the product is an accessory or replacement of another product (for the page of the product)."""
    return list(
        ProductRelation.objects.filter(related_product=product)
        .select_related("product")
        .order_by("kind", "product__article_number")
    )


def add_relation(
    product: Product,
    related: Product,
    kind: str,
    *,
    note: str = "",
    is_required: bool = False,
    quantity_per_piece: Decimal | int | str = 1,
    both_ways: bool = False,
) -> ProductRelation:
    """Name an accessory or replacement of a product, at the end of its list (PRD-023, VFG-015).

    Args:
        product: The product that has it.
        related: The accessory or replacement.
        kind: :class:`RelationKind`.
        note: A remark for the planner.
        is_required: An accessory the product cannot be used without.
        quantity_per_piece: Pieces of ``related`` per piece of ``product``.
        both_ways: A replacement is also entered the other way round (``product`` replaces ``related``), with
            the reciprocal number of pieces rounded to two decimals.

    Raises:
        ValidationError: The pair is not allowed or exists already.
    """
    if kind not in RelationKind.values:
        raise ValidationError({"kind": _("Unknown kind of relation.")})
    last = (
        ProductRelation.objects.filter(product=product, kind=kind)
        .order_by("-position")
        .values_list("position", flat=True)
        .first()
    )
    relation = ProductRelation(
        product=product,
        related_product=related,
        kind=kind,
        note=(note or "").strip(),
        is_required=bool(is_required) and kind == RelationKind.ACCESSORY,
        quantity_per_piece=Decimal(str(quantity_per_piece).replace(",", ".")),
        position=(last or 0) + 1 if last is not None else 0,
    )
    _validate(relation)
    relation.save()
    if both_ways and kind == RelationKind.REPLACEMENT:
        reverse_quantity = (Decimal(1) / relation.quantity_per_piece).quantize(Decimal("0.01"))
        if not ProductRelation.objects.filter(product=related, related_product=product, kind=kind).exists():
            backwards = ProductRelation(
                product=related,
                related_product=product,
                kind=kind,
                note=relation.note,
                quantity_per_piece=max(reverse_quantity, Decimal("0.01")),
            )
            _validate(backwards)
            backwards.save()
    return relation


def update_relation(relation: ProductRelation, **changes: Any) -> ProductRelation:
    """Change note, ``is_required``, ``quantity_per_piece`` or ``position`` of a relation."""
    for name in ("note", "is_required", "quantity_per_piece", "position"):
        if name in changes:
            value = changes[name]
            if name == "quantity_per_piece":
                value = Decimal(str(value).replace(",", "."))
            if name == "note":
                value = (value if isinstance(value, str) else "").strip()  # (hostile input; R4-2d)
            setattr(relation, name, value)
    _validate(relation)
    relation.save()
    return relation


def move_relation(relation: ProductRelation, direction: str) -> None:
    """Move a relation one place up or down in the list of its kind; the positions are renumbered."""
    siblings = list(
        ProductRelation.objects.filter(product_id=relation.product_id, kind=relation.kind).order_by("position", "id")
    )
    index = next((i for i, row in enumerate(siblings) if row.pk == relation.pk), None)
    if index is None:
        return
    target = index - 1 if direction == "up" else index + 1
    if not 0 <= target < len(siblings):
        return
    siblings[index], siblings[target] = siblings[target], siblings[index]
    for position, row in enumerate(siblings):
        if row.position != position:
            row.position = position
            row.save()


def delete_relation(relation: ProductRelation) -> None:
    """Remove an accessory or replacement from its product (suggestions already made for it disappear)."""
    relation.delete()


def _validate(relation: ProductRelation) -> None:
    """Run the rules of the model and name a pair that exists already in the words of the form."""
    relation.full_clean(exclude=["product", "related_product"], validate_unique=False)
    relation.clean()
    if relation.kind == RelationKind.REPLACEMENT and relation.product.is_kit:
        raise ValidationError(
            {"related_product": _("A kit is short in its components. Name the replacements at those products.")}
        )
    clash = ProductRelation.objects.filter(
        Q(product=relation.product, related_product=relation.related_product, kind=relation.kind)
    ).exclude(pk=relation.pk)
    if clash.exists():
        raise ValidationError({"related_product": _("This product is already named there.")})
