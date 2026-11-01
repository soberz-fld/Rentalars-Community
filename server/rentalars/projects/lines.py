# SPDX-License-Identifier: GPL-3.0-or-later
"""Working with lines of the planning: duplicating a line (PRJ-075), several lines at once (PRJ-082).

Browser views and API views both call these functions (API-002); like every
change of a project they refuse closed projects (PRJ-009).

Several lines at once (PRJ-082)
-------------------------------
The planning lets the planner tick lines and do one thing with all of them:
make them optional or no longer optional, an alternative to another line
(PRJ-083), move them into a group, give them a discount, or delete them.
:func:`change_lines` does that line by line through the same services as a
change of a single line – ``services.update_line`` and
``services.delete_line`` –, so every rule of a single line holds and the
history of the project names every line. A line the action cannot be done
with is left as it is and named with the reason; the others are changed all
the same.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.availability.engine import AvailabilityEngine
from rentalars.core.audit import record_event
from rentalars.projects.discounts import capped_lines_warning, capped_material_lines
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.models import (
    Group,
    GroupKind,
    LineVariant,
    MaterialLine,
    Project,
    SubrentalStatus,
    SurchargeTarget,
)
from rentalars.projects.services import (
    LineResult,
    _lock_products,
    check_plannable_as_material,
    delete_line,
    ensure_editable,
    update_line,
)

#: The fields a duplicate takes over from its line as they are (PRJ-075).
COPIED_FIELDS = (
    "group",
    "product",
    "title",
    "quantity",
    "unit",
    "start",
    "end",
    "note",
    "is_sale",
    "billing_mode",
    "unit_price",
    "list_price",
    "product_seen",
    "discount_percent",
    "tax_rate",
    "hours",
    "quantity_is_estimate",
    "rental_days",
    "scale_version",
    "manual_scale_factor",
    "surcharge_percent",
    "supplier",
    "purchase_price",
    "preferred_model",
    "variant",
    "alternative_to",
    "is_text",  # A text line is copied as a text line
)


def duplicate_line(line: MaterialLine, *, rights: Rights) -> LineResult:
    """Put a copy of a line directly below it, in the same group (PRJ-075).

    The copy has the same product, quantity, period, prices, discount, note
    and – for a percentage surcharge – the same targets. Typical use: the
    same spotlights once more, to make the copy an optional line or give it
    another period.

    Not copied:

    * a specific *item* the line asks for (PRJ-064) – the same item cannot go
      out twice; the wish for a model is copied;
    * the subrental status: a copied subrental is "open" again (PRJ-101);
    * anything about packing and stock (``stock_removed_quantity``, added
      while packing).

    A subrental that only covers the shortage of another line cannot be
    duplicated: the shortage is covered once.

    The availability of the copy is checked in the same protected step as
    for a new line (VFG-007); a shortage does not stop it (PRJ-013).

    Args:
        line: The line to duplicate.
        rights: The rights of the caller. Duplicating needs no price right:
            the prices are copied, not set.

    Raises:
        ValidationError: The project is closed, or the line covers a
            shortage.
    """
    project = line.project
    ensure_editable(project)
    if line.is_covering_subrental:
        raise ValidationError(_("A subrental that covers a shortage cannot be duplicated."))
    if line.product_id:
        check_plannable_as_material(line.product)  # PRD-044: a service line is not multiplied
    with transaction.atomic():
        engine = AvailabilityEngine()
        if line.product_id:
            _lock_products(engine.competing_products([line.product_id]))
        # Make room directly below the line; moving the others is no change worth a line in the history.
        project.material_lines.filter(group_id=line.group_id, position__gt=line.position).update(
            position=F("position") + 1
        )
        copy = MaterialLine(project=project, position=line.position + 1)
        for name in COPIED_FIELDS:
            setattr(copy, name, getattr(line, name))
        copy.quantity = Decimal(line.quantity)
        if line.is_subrental:
            copy.subrental_status = SubrentalStatus.OPEN  # PRJ-101: nothing is asked for the copy yet
        copy.full_clean()
        copy.save()
        SurchargeTarget.objects.bulk_create(
            SurchargeTarget(
                surcharge_line=copy,
                target_type=target.target_type,
                target_line_id=target.target_line_id,
                target_group_id=target.target_group_id,
            )
            for target in line.surcharge_targets.all()
        )
        record_event(copy, "line.duplicated", {"from_line": line.pk, "title": line.title})
        availability = engine.line_availability(copy)
    return LineResult(line=copy, availability=availability)


# --- Several lines at once (PRJ-082) ------------------------------------------------------------


class BulkAction:
    """What can be done with several lines at once (PRJ-082)."""

    OPTIONAL = "optional"
    #: No longer optional or an alternative: the line counts again.
    NORMAL = "normal"
    ALTERNATIVE = "alternative"
    MOVE = "move"
    DISCOUNT = "discount"
    DELETE = "delete"

    ALL = (OPTIONAL, NORMAL, ALTERNATIVE, MOVE, DISCOUNT, DELETE)


@dataclass
class SkippedLine:
    """A line the action was not done with, and why (PRJ-082)."""

    line: MaterialLine
    reason: str

    @property
    def label(self) -> str:
        """How the planning names the line: "8 × LED-Scheinwerfer"."""
        return line_label(self.line)


@dataclass
class BulkResult:
    """What :func:`change_lines` did."""

    action: str
    #: The lines that are different now (deleted ones included, with the values they had).
    changed: list[MaterialLine] = field(default_factory=list)
    #: Their IDs – a deleted line has none any more.
    changed_ids: list[int] = field(default_factory=list)
    #: The lines left as they were because the action cannot be done with them.
    skipped: list[SkippedLine] = field(default_factory=list)
    #: The lines that were already as asked, e.g. optional before.
    unchanged: list[MaterialLine] = field(default_factory=list)
    #: Groups of the lines before and after the change, ``None`` for "without group" – what the planning shows again.
    group_ids: set[int | None] = field(default_factory=set)
    #: Products of the lines and of what they cover – their availability may look different now.
    product_ids: set[int | None] = field(default_factory=set)
    #: What the user is to be told, e.g. that a discount is above the maximum of some lines (PER-026).
    warnings: list[str] = field(default_factory=list)


def line_label(line: MaterialLine) -> str:
    """A line in one short phrase: "8 × LED-Scheinwerfer RGBW" (PRJ-082, PRJ-083)."""
    if line.is_percent_surcharge or line.is_text:
        return line.title
    return f"{line.quantity_display} × {line.title}"


def _note(result: BulkResult, line: MaterialLine) -> None:
    """Remember group and products of a line for the refreshed planning."""
    result.group_ids.add(line.group_id)
    result.product_ids.update({line.product_id, line.covers_product_id})
    if line.covers_line_id:
        result.product_ids.add(line.covers_line.product_id)
        result.group_ids.add(line.covers_line.group_id)


def _rule_against(line: MaterialLine, action: str, selected: set[int]) -> str:
    """Why the action cannot be done with this line at all; "" if it can (PRJ-082).

    These are the rules of the planning that hold for single lines as well;
    everything else is decided by the services, whose refusal is named the
    same way.
    """
    covering = line.is_covering_subrental
    if line.is_text and action in {BulkAction.OPTIONAL, BulkAction.ALTERNATIVE, BulkAction.DISCOUNT}:
        return _("is a text line without price")
    if action in {BulkAction.OPTIONAL, BulkAction.ALTERNATIVE} and covering:
        return _("covers the shortage of another line and counts like it")
    if action in {BulkAction.OPTIONAL, BulkAction.ALTERNATIVE} and line.is_customer_material:
        return _("is customer material and is taken along")  # PRJ-096
    if action == BulkAction.DISCOUNT and line.is_customer_material:
        return _("is not charged")  # PRJ-096
    if action == BulkAction.MOVE:
        if covering and line.covers_line_id not in selected:
            return _("stands below the line whose shortage it covers and moves with it")
        if line.is_percent_surcharge:
            return _("a percentage surcharge stands where the amounts it refers to are")
    if action == BulkAction.DISCOUNT:
        if covering or line.is_takeover:
            return _("is not charged")
        if line.is_percent_surcharge:
            return _("a percentage surcharge has no discount")
    return ""


def _already(line: MaterialLine, action: str, values: dict[str, Any]) -> bool:
    """Whether the line is already as the action wants it."""
    if action == BulkAction.OPTIONAL:
        return line.variant == LineVariant.OPTIONAL
    if action == BulkAction.NORMAL:
        return not line.variant
    if action == BulkAction.ALTERNATIVE:
        return line.variant == LineVariant.ALTERNATIVE and line.alternative_to_id == values["alternative_to"].pk
    if action == BulkAction.MOVE:
        target = values["group"]
        return line.group_id == (target.pk if target is not None else None)
    if action == BulkAction.DISCOUNT:
        return line.discount_percent == values["discount_percent"]
    return False


def _check_request(
    project: Project,
    action: str,
    *,
    rights: Rights,
    alternative_to: MaterialLine | None,
    group: Group | None,
    discount_percent: Decimal | None,
) -> None:
    """Refuse a request that cannot be done with any line: unknown action, missing or foreign values."""
    if action not in BulkAction.ALL:
        raise ValidationError(_("Unknown action."))
    if action == BulkAction.ALTERNATIVE:
        if alternative_to is None:
            raise ValidationError({"alternative_to": _("Choose the line the lines are an alternative to.")})
        if alternative_to.project_id != project.pk:
            raise ValidationError({"alternative_to": _("The line belongs to a different project.")})
        if alternative_to.is_text:
            # (text lines; PRJ-128): a text line has no price; an alternative to it would count for nothing.
            raise ValidationError(
                {"alternative_to": _("A text line has no price and cannot be replaced by an alternative.")}
            )
        if alternative_to.is_covering_subrental:
            raise ValidationError(
                {"alternative_to": _("A subrental that covers a shortage cannot be replaced by an alternative.")}
            )
        if alternative_to.variant == LineVariant.ALTERNATIVE:
            raise ValidationError({"alternative_to": _("Choose a line that is not an alternative itself.")})
    if action == BulkAction.MOVE and group is not None and group.project_id != project.pk:
        raise ValidationError({"group": _("The group belongs to a different project.")})
    if action == BulkAction.DISCOUNT:
        if not rights.has(SpecialRight.PRICES):
            raise ValidationError(_("You do not have the right to set prices or discounts."))
        if discount_percent is None or not Decimal(0) <= discount_percent <= Decimal(100):
            raise ValidationError({"discount_percent": _("Enter a discount between 0 and 100 per cent.")})


def change_lines(
    project: Project,
    line_ids: list[int],
    action: str,
    *,
    rights: Rights,
    alternative_to: MaterialLine | None = None,
    group: Group | None = None,
    discount_percent: Decimal | None = None,
) -> BulkResult:
    """Do one thing with several lines of a project at once (PRJ-082).

    Actions (:class:`BulkAction`): ``optional``, ``normal`` (no longer
    optional or an alternative), ``alternative`` (to ``alternative_to``,
    PRJ-083), ``move`` (into ``group``; ``None`` is "without group"),
    ``discount`` (``discount_percent``, needs the price right) and
    ``delete``.

    Every line goes through the service for a single line, each in a step of
    its own: a line the action cannot be done with – material already
    issued, pieces taken over by another subproject (PRJ-060), a subrental
    that only covers a shortage – is skipped and named with the reason, and
    the others are changed all the same. A subrental that covers a shortage
    of a line moves with that line (PRJ-084).

    Args:
        project: The project; works the same for a subproject.
        line_ids: The IDs of the lines; all must belong to the project.
        action: What to do.
        rights: The rights of the caller.
        alternative_to: For ``alternative``: the line the others could replace.
        group: For ``move``: where the lines go.
        discount_percent: For ``discount``: the discount of every line.

    Raises:
        ValidationError: The project is closed, the action is unknown, a value
            it needs is missing or belongs to another project, or a line is
            not one of the project's.
    """
    ensure_editable(project)
    _check_request(
        project, action, rights=rights, alternative_to=alternative_to, group=group, discount_percent=discount_percent
    )
    wanted = {int(line_id) for line_id in line_ids}
    if not wanted:
        raise ValidationError(_("Choose at least one line."))
    lines = list(
        project.material_lines.filter(pk__in=wanted)
        .select_related("product", "covers_line", "project")
        .order_by("position", "id")
    )
    if len(lines) != len(wanted):
        raise ValidationError(_("Some of the lines do not belong to this project."))
    values = {"alternative_to": alternative_to, "group": group, "discount_percent": discount_percent}
    result = BulkResult(action=action)
    if group is not None or action == BulkAction.MOVE:
        result.group_ids.add(group.pk if group is not None else None)
    if action == BulkAction.DELETE:
        # The subrentals that cover a shortage of a deleted line lose their reason with it, and the
        # alternatives to it become optional (PRJ-083).
        result.group_ids.update(
            MaterialLine.objects.filter(covers_line_id__in=wanted).values_list("group_id", flat=True)
        )
        result.group_ids.update(
            MaterialLine.objects.filter(alternative_to_id__in=wanted).values_list("group_id", flat=True)
        )
    for line in lines:
        _note(result, line)
        reason = _rule_against(line, action, wanted)
        if reason:
            result.skipped.append(SkippedLine(line=line, reason=reason))
            continue
        if action == BulkAction.MOVE and line.is_covering_subrental:
            continue  # moves with the line it covers, which is among the chosen ones
        if action == BulkAction.ALTERNATIVE and line.pk == alternative_to.pk:
            result.skipped.append(SkippedLine(line=line, reason=_("is the line the others are an alternative to")))
            continue
        if action != BulkAction.DELETE and _already(line, action, values):
            result.unchanged.append(line)
            continue
        line_id = line.pk
        try:
            with transaction.atomic():
                _apply(line, action, values, rights=rights)
        except ValidationError as error:
            result.skipped.append(SkippedLine(line=line, reason=" ".join(error.messages)))
            continue
        result.changed.append(line)
        result.changed_ids.append(line_id)
    if action == BulkAction.DISCOUNT and discount_percent is not None:
        # The lines keep what was typed, the price takes their maximum – and the user is told which.
        capped = capped_lines_warning(discount_percent, capped_material_lines(result.changed, discount_percent))
        if capped:
            result.warnings.append(capped)
    return result


def _apply(line: MaterialLine, action: str, values: dict[str, Any], *, rights: Rights) -> None:
    """Do the action with one line, through the service for a single line."""
    if action == BulkAction.DELETE:
        delete_line(line)
    elif action == BulkAction.OPTIONAL:
        update_line(line, rights=rights, variant=LineVariant.OPTIONAL)
    elif action == BulkAction.NORMAL:
        update_line(line, rights=rights, variant=LineVariant.NORMAL)
    elif action == BulkAction.ALTERNATIVE:
        update_line(line, rights=rights, variant=LineVariant.ALTERNATIVE, alternative_to=values["alternative_to"])
    elif action == BulkAction.MOVE:
        update_line(line, rights=rights, group=values["group"])
    elif action == BulkAction.DISCOUNT:
        update_line(line, rights=rights, discount_percent=values["discount_percent"])


# --- What an alternative can replace (PRJ-083) --------------------------------------------------


def alternative_choices(project: Project, *, excluded: set[int]) -> list[tuple[str, list[tuple[int, str]]]]:
    """The lines an alternative can name, by group in the order of the planning (PRJ-083).

    Left out: the lines that are to become alternatives (``excluded``),
    subrentals that only cover a shortage, and lines that are alternatives
    themselves. Two queries, whatever the size of the project.

    Returns:
        ``[(group path or "Without group", [(line ID, "8 × LED-Scheinwerfer"), …]), …]``.
    """
    tree = GroupTree(project.groups.all())
    order = {group.pk: index for index, group in enumerate(tree.ordered)}
    candidates = (
        project.material_lines.filter(covers_line__isnull=True)
        .exclude(variant=LineVariant.ALTERNATIVE)
        .exclude(pk__in=excluded)
        .exclude(is_text=True)  # A text line is replaced by nothing
        .only("pk", "title", "quantity", "group_id", "position", "surcharge_percent", "product_id", "is_text")
    )
    by_group: dict[int | None, list[tuple[int, str]]] = {}
    for line in sorted(candidates, key=lambda line: (order.get(line.group_id, len(order)), line.position, line.pk)):
        label = (
            line.title
            if line.surcharge_percent is not None or line.is_text
            else f"{line.quantity_display} × {line.title}"
        )
        by_group.setdefault(line.group_id if line.group_id in order else None, []).append((line.pk, label))
    choices = [(tree.path(group), by_group[group.pk]) for group in tree.ordered if group.pk in by_group]
    if None in by_group:
        choices.append((_("Without group"), by_group[None]))
    return choices


def group_alternative_choices(group: Group) -> list[tuple[int, str]]:
    """The groups an alternative group can name: not itself, not above or below it, no alternative (PRJ-083)."""
    tree = GroupTree(group.project.groups.all())
    own = tree.by_id[group.pk]
    related = {other.pk for other in tree.ancestors(own)} | tree.subtree_ids(own)
    return [
        (other.pk, tree.path(other))
        for other in tree.ordered
        if other.pk not in related and other.kind != GroupKind.ALTERNATIVE
    ]
