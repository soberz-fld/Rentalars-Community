# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic for projects: creating, status changes, groups and lines.

Browser views and API views both call these functions (API-002). Every
function that changes a project first checks that the project is not closed
(PRJ-009).
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.availability.engine import AvailabilityEngine, LineAvailability
from rentalars.core.audit import record_event
from rentalars.core.models import NumberRange, NumberRangeKey
from rentalars.masterdata.models import TaxRate
from rentalars.products.models import CREW_ONLY_KINDS, LOGISTICS_KINDS, BillingMode, Product, ProductKind
from rentalars.projects.customer_material import may_plan
from rentalars.projects.discounts import line_discount_warning
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.models import (
    ALLOWED_TRANSITIONS,
    FINISHED_STATUSES,
    INHERITED_FIELDS,
    Group,
    GroupKind,
    LineVariant,
    MaterialLine,
    Project,
    ProjectStatus,
    SubrentalStatus,
    SurchargeTarget,
    SurchargeTargetType,
)

#: Line fields that only users with the price right may set (AUT-019).
PRICE_FIELDS = frozenset(
    {"unit_price", "discount_percent", "manual_scale_factor", "surcharge_percent", "billing_mode", "tax_rate"}
)

#: Line fields that need the right to see purchase prices (AUT-019).
PURCHASE_FIELDS = frozenset({"purchase_price"})

#: Group fields that only users with the price right may set.
GROUP_PRICE_FIELDS = frozenset({"discount_percent", "discount_amount", "flat_price"})
#: PRJ-123: the overall discount of a project – a price like the others (AUT-019).
OVERALL_DISCOUNT_FIELDS = frozenset({"overall_discount_percent", "overall_discount_amount"})

#: Line fields a caller may change through :func:`update_line`.
EDITABLE_LINE_FIELDS = (
    frozenset(
        {
            "title",
            "quantity",
            "unit",
            "start",
            "end",
            "group",
            "note",
            "is_sale",
            "hours",
            "quantity_is_estimate",
            "rental_days",
            "supplier",
            "subrental_status",
            # PRJ-097: fetched at the supplier – a trip of the project.
            "picked_up_at_supplier",
            "preferred_model",
            "preferred_item",
            # (piece share): all wished items at once, the first is ``preferred_item``.
            "preferred_items",
            # PRJ-075: optional or alternative line; PRJ-083: what an alternative could replace.
            "variant",
            "alternative_to",
            # PRJ-060: taken over from a line of another subproject.
            "taken_over_from",
        }
    )
    | PRICE_FIELDS
    | PURCHASE_FIELDS
)

#: Other modules can veto a status change, e.g. packing blocks "returned"
#: while parts are missing (PCK-019). A guard raises ``ValidationError``.
status_guards: list[Callable[[Project, str], None]] = []


@dataclass
class LineResult:
    """What saving a line returns: the line and its availability (PRJ-012)."""

    line: MaterialLine
    availability: LineAvailability
    #: What the user is to be told about the saved values, e.g. a discount above the maximum (PER-026).
    warnings: list[str] = field(default_factory=list)


def _take_wished_items(values: dict[str, Any]) -> list[Any] | None:
    """Split ``preferred_items`` (all wished items) off ``values`` (piece share; PRJ-064, PRD-052).

    The first item becomes ``preferred_item``; the others are returned for ``further_preferred_items`` of the line.
    Doubles are dropped. ``None`` when ``values`` do not name the wished items as a list.
    """
    if "preferred_items" not in values:
        return None
    items: list[Any] = []
    for item in values.pop("preferred_items") or []:
        if item.pk not in {known.pk for known in items}:
            items.append(item)
    values["preferred_item"] = items[0] if items else None
    return items[1:]


def _store_wished_items(line: MaterialLine, further: list[Any] | None) -> None:
    """Save the further wished items after the line is saved, and forget the pending ones (piece share)."""
    if further is not None:
        line.further_preferred_items.set(further)
    line.pending_further_items = None


# --- Projects ----------------------------------------------------------------


def ensure_editable(project: Project) -> None:
    """Refuse changes to a closed project (PRJ-009).

    Raises:
        ValidationError: The project is closed.
    """
    if project.is_locked:
        raise ValidationError(_("This project is closed. Reopen it before making changes."))


def ensure_plannable(project: Project) -> None:
    """PRJ-090: a service case has no planning – no material, no crew, no subprojects.

    Raises:
        ValidationError: The project is a service case.
    """
    if project.is_service_case:
        raise ValidationError(_("A service case has no planning. Turn it into a project first."))


@transaction.atomic
def _next_free_number() -> str:
    """Take the next project number that no project has yet (PRJ-003).

    Normally that is simply the next number of the range. If an administrator
    set the counter back, or numbers were taken over from elsewhere, numbers
    already in use are skipped instead of failing with "already exists".

    ADM-012, ADM-014: so are the former numbers of projects (``P-2026-0042``, now ``2026-0042`` again) – should the prefix be set to
    ``P-{year}-`` once more, the old number on a document still means the
    project it was printed for.
    """
    while True:
        _value, number = NumberRange.allocate(NumberRangeKey.PROJECT)
        if not Project.objects.filter(Q(number=number) | Q(former_number=number)).exists():
            return number


def create_project(**fields: Any) -> Project:
    """Create a project and give it the next project number (PRJ-003).

    Args:
        **fields: Field values of :class:`Project`; ``name``, ``customer``,
            ``start`` and ``end`` are required.

    Raises:
        ValidationError: A value is missing or invalid.
    """
    _take_default_addresses(fields, fields.get("customer"))
    project = Project(**fields)
    project.number = _next_free_number()
    project.full_clean()
    project.save()
    return project


#: PRJ-045: what a new subproject takes over from its whole project unless given; changeable afterwards.
PRESET_FIELDS = ("contact", "delivery_address", "venue", "venue_site", "manager", "start", "end")

#: PRJ-044: the statuses a whole project may have when a new part is added, and the status the part starts with.
_STATUS_OF_NEW_PART = {
    ProjectStatus.INQUIRY: ProjectStatus.INQUIRY,
    ProjectStatus.OPTION: ProjectStatus.OPTION,
    ProjectStatus.CONFIRMED_OPEN: ProjectStatus.CONFIRMED_OPEN,
    ProjectStatus.CONFIRMED: ProjectStatus.CONFIRMED_OPEN,
    ProjectStatus.OUT: ProjectStatus.CONFIRMED_OPEN,
    ProjectStatus.RETURNED: ProjectStatus.CONFIRMED_OPEN,
}


def _next_subproject_number(parent: Project) -> str:
    """Number a new part after its whole project: 2026-0042-1, 2026-0042-2 and so on (PRJ-044)."""
    taken = set(Project.objects.filter(number__startswith=f"{parent.number}-").values_list("number", flat=True))
    counter = 1
    while f"{parent.number}-{counter}" in taken:
        counter += 1
    return f"{parent.number}-{counter}"


@transaction.atomic
def create_subproject(parent: Project, **fields: Any) -> Project:
    """Add a part to a whole project (PRJ-044, PRJ-045).

    The part gets the customer and the billing address of the whole project
    – always; the contact, the delivery address, the venue, the project
    manager and the rental period unless other values are given. It is
    numbered after the whole project (``2026-0042-1``).

    A part of an inquiry is an inquiry, of an option an option. A part
    added to a confirmed project starts as "confirmed – details open": a
    new stage is rarely complete when it is added.

    Raises:
        ValidationError: The whole project is itself a subproject, is
            closed or cancelled, or a value is invalid.
    """
    ensure_editable(parent)
    ensure_plannable(parent)  # PRJ-090: a service case has no parts
    if parent.parent_id is not None:
        raise ValidationError(_("Subprojects cannot have subprojects of their own."))
    if parent.status not in _STATUS_OF_NEW_PART:
        raise ValidationError(_("A cancelled or closed project gets no new subprojects."))
    for name in INHERITED_FIELDS:
        fields[name] = getattr(parent, name)
    for name in PRESET_FIELDS:
        if fields.get(name) in (None, ""):
            fields[name] = getattr(parent, name)
    fields.setdefault("status", _STATUS_OF_NEW_PART[parent.status])
    project = Project(parent=parent, **fields)
    project.number = _next_subproject_number(parent)
    project.full_clean()
    project.save()
    return project


def _take_default_addresses(fields: dict[str, Any], customer: Any) -> None:
    """KND-005: the addresses the caller did not choose are the defaults of the customer."""
    from rentalars.customers.models import AddressKind

    for name, kind in (("billing_address", AddressKind.BILLING), ("delivery_address", AddressKind.DELIVERY)):
        if name not in fields:
            fields[name] = customer.default_address(kind) if customer is not None else None


@transaction.atomic
def update_project(project: Project, **changes: Any) -> Project:
    """Change the master data of a project.

    If the reservation period moves, all lines that still had exactly the old
    project period move with it. Lines whose period was set individually
    (PRJ-011) keep theirs.
    """
    ensure_editable(project)
    old_start, old_end = project.start, project.end
    if project.parent_id:
        # PRJ-045: customer and billing are those of the whole project.
        changes = {
            name: value
            for name, value in changes.items()
            if name not in INHERITED_FIELDS or value == getattr(project, name)
        }
    elif "customer" in changes and changes["customer"] != project.customer:
        # PRJ-096: customer material planned in the project (or its parts) belongs to the customer it has now.
        _check_customer_material_stays(project, changes["customer"])
        # Addresses of the former customer do not fit; the new one's defaults take their place.
        _take_default_addresses(changes, changes["customer"])
    for name, value in changes.items():
        setattr(project, name, value)
    project.full_clean()
    project.save()
    if (project.start, project.end) != (old_start, old_end):
        for line in project.material_lines.filter(start=old_start, end=old_end):
            line.start = project.start
            line.end = project.end
            line.save()
        # LOG-001: vehicle bookings with the project's period follow it as well.
        from rentalars.projects.logistics import follow_project_period

        follow_project_period(project, old_start, old_end)
    if project.parent_id is None:
        # L12: "as a whole" is judged on the wall clock, as the schedule does – across the change of the
        # clock the difference of the moments is an hour off, and the parts would stay behind or be refused.
        shift = wall_clock_shift(project.start, old_start)
        _update_subprojects(project, shift if wall_clock_shift(project.end, old_end) == shift else None)
    return project


def set_overall_discount(
    project: Project, *, rights: Rights, percent: Decimal | None = None, amount: Decimal | None = None
) -> Project:
    """Set or remove the overall discount of a project (PRJ-123).

    The discount is taken off the net total of the project – in percent of it,
    or as an amount, never both. Empty values remove it. The same function
    serves the page and the API (API-002).

    Raises:
        ValidationError: The project is closed or a service case, the caller
            may not set prices, or both a percentage and an amount are given.
    """
    ensure_editable(project)
    ensure_plannable(project)
    _check_price_rights(OVERALL_DISCOUNT_FIELDS, rights, price_fields=OVERALL_DISCOUNT_FIELDS)
    project.overall_discount_percent = percent or None
    project.overall_discount_amount = amount or None
    project.full_clean()
    project.save()
    return project


def set_overall_discount_to_target(
    project: Project, *, rights: Rights, net: Decimal | None = None, gross: Decimal | None = None
) -> Any:
    """Set the overall discount so that the project comes to a net or gross target amount (PRJ-123).

    The percentage that gets there is calculated now and stored; it is not recalculated when the project changes
    later (see :mod:`rentalars.projects.overall_target`). The same function serves the page and the API (API-002).

    Returns:
        The :class:`~rentalars.projects.overall_target.DiscountTarget` with the percentage and the resulting figures.

    Raises:
        ValidationError: As :func:`set_overall_discount`, and: both or no target, a target above the total without
            discount, a project without a total.
    """
    from rentalars.projects.overall_target import solve

    ensure_editable(project)
    ensure_plannable(project)
    _check_price_rights(OVERALL_DISCOUNT_FIELDS, rights, price_fields=OVERALL_DISCOUNT_FIELDS)
    result = solve(project, net=net, gross=gross)
    set_overall_discount(project, rights=rights, percent=result.percent)
    return result


def _check_customer_material_stays(project: Project, customer: Any) -> None:
    """PRJ-096: a project with customer material of its customer keeps that customer.

    Raises:
        ValidationError: The project or one of its parts plans material
            that belongs to its customer – not to the new one.
    """
    owner_id = customer.pk if customer is not None else None
    foreign = (
        MaterialLine.objects.filter(project_id__in=project.family_ids(), product__owner__isnull=False)
        .exclude(product__owner_id=owner_id)
        .select_related("product")
        .first()
    )
    if foreign is not None:
        raise ValidationError(
            {
                "customer": _(
                    "The project plans customer material of its customer (%(product)s). Remove those lines "
                    "before you choose another customer."
                )
                % {"product": foreign.title}
            }
        )


def _update_subprojects(parent: Project, shift: datetime.timedelta | None) -> None:
    """Carry changes of a whole project to its parts (PRJ-044, PRJ-045).

    * Customer and billing address follow. A contact or delivery address
      that belonged to the former customer is replaced by that of the whole
      project.
    * A rental period moved as a whole – same length, other dates – moves
      the parts along. Otherwise every part has to stay within the new
      period, or the change is refused.

    Args:
        parent: The whole project, already saved.
        shift: How far the period was moved as a whole; ``None`` if it was
            changed otherwise, ``timedelta(0)`` if not at all.
    """
    for part in parent.subprojects.all():
        if part.is_locked:
            continue
        changes: dict[str, Any] = {}
        for name in INHERITED_FIELDS:
            attname = Project._meta.get_field(name).attname
            if getattr(part, attname) != getattr(parent, attname):
                changes[name] = getattr(parent, name)
        if "customer" in changes:
            if part.contact_id and part.contact.customer_id != parent.customer_id:
                changes["contact"] = parent.contact
            if part.delivery_address_id and part.delivery_address.customer_id != parent.customer_id:
                changes["delivery_address"] = parent.delivery_address
        if shift:
            changes["start"] = moved(part.start, shift)
            changes["end"] = moved(part.end, shift)
            if part.event_start and part.event_end:
                changes["event_start"] = moved(part.event_start, shift)
                changes["event_end"] = moved(part.event_end, shift)
        elif part.start < parent.start or part.end > parent.end:
            raise ValidationError(
                {
                    "end": _(
                        "The subproject %(number)s %(name)s would no longer lie within the rental period. "
                        "Change its period first, or move the whole period at once."
                    )
                    % {"number": part.number, "name": part.name}
                }
            )
        if not changes:
            continue
        old_start, old_end = part.start, part.end
        for name, value in changes.items():
            setattr(part, name, value)
        part.full_clean()
        part.save()
        if (part.start, part.end) != (old_start, old_end):
            for line in part.material_lines.filter(start=old_start, end=old_end):
                line.start = part.start
                line.end = part.end
                line.save()


def change_status(project: Project, new_status: str, *, rights: Rights) -> None:
    """Move a project to another status (PRJ-008, PRJ-009).

    Rules:

    * Only the transitions listed in ``ALLOWED_TRANSITIONS`` are possible.
    * Reopening a closed project needs the special right for it.
    * Other modules may object through ``status_guards``.

    The change itself is recorded by the audit log, with user and time.

    Raises:
        ValidationError: The transition is not allowed.
    """
    if new_status == project.status:
        return
    if project.is_service_case:
        # PRJ-090: open, in progress, done – ``projects.service_cases.set_case_status``.
        raise ValidationError(_("A service case has statuses of its own: open, in progress, done."))
    if new_status not in ProjectStatus.values:
        raise ValidationError(_("Unknown status."))
    if new_status not in ALLOWED_TRANSITIONS.get(project.status, frozenset()):
        raise ValidationError(
            _("A project cannot go from “%(current)s” to “%(target)s”.")
            % {"current": project.get_status_display(), "target": ProjectStatus(new_status).label}
        )
    if project.status == ProjectStatus.CLOSED and not rights.has(SpecialRight.REOPEN_PROJECTS):
        raise ValidationError(_("Reopening a closed project requires a special right."))
    _check_family_status(project, new_status)
    for guard in status_guards:
        guard(project, new_status)
    project.status = new_status
    project.save()
    if new_status == ProjectStatus.CANCELLED:
        # PRJ-044: a cancelled whole project takes its parts along.
        for part in project.subprojects.exclude(status__in=FINISHED_STATUSES):
            change_status(part, ProjectStatus.CANCELLED, rights=rights)


def _check_family_status(project: Project, new_status: str) -> None:
    """The rules between a whole project and its parts (PRJ-044).

    * A whole project is closed when all its parts are closed or cancelled.
    * It is cancelled together with its parts; a part that is out stops that.
    * A part of a cancelled whole project cannot be taken up again on its own.

    Raises:
        ValidationError: One of the rules is broken.
    """
    if project.parent_id is None:
        parts = project.subprojects.all()
        if new_status == ProjectStatus.CLOSED:
            open_parts = parts.exclude(status__in=[ProjectStatus.CLOSED, ProjectStatus.CANCELLED])
            if open_parts.exists():
                raise ValidationError(
                    _("Close or cancel the subprojects first: %(numbers)s.")
                    % {"numbers": ", ".join(open_parts.values_list("number", flat=True))}
                )
        if new_status == ProjectStatus.CANCELLED:
            out = parts.filter(status=ProjectStatus.OUT)
            if out.exists():
                raise ValidationError(
                    _("Material of the subprojects %(numbers)s is out; they cannot be cancelled.")
                    % {"numbers": ", ".join(out.values_list("number", flat=True))}
                )
    elif project.parent.status == ProjectStatus.CANCELLED and new_status != ProjectStatus.CANCELLED:
        raise ValidationError(_("The whole project is cancelled. Take it up again first."))


def change_family_status(project: Project, new_status: str, *, rights: Rights) -> list[str]:
    """Move a whole project and, where the rules allow it, all its parts to a status (PRJ-044).

    The whole project changes first; a part for which the step is not
    allowed keeps its status.

    Returns:
        The numbers of the parts that kept their status.

    Raises:
        ValidationError: The whole project cannot change.
    """
    with transaction.atomic():
        change_status(project, new_status, rights=rights)
    kept: list[str] = []
    for part in project.subprojects.exclude(status=new_status):
        try:
            with transaction.atomic():
                change_status(part, new_status, rights=rights)
        except ValidationError:
            kept.append(part.number)
    return kept


def delete_project(project: Project) -> None:
    """Delete a project that never left the planning stage.

    Raises:
        ValidationError: The project was confirmed at some point or material
            was issued; such projects are cancelled, not deleted, so that
            their history stays (catalogue 7.3).
    """
    if project.status not in {ProjectStatus.INQUIRY, ProjectStatus.OPTION, ProjectStatus.CANCELLED}:
        raise ValidationError(
            _("Only inquiries, options and cancelled projects can be deleted. Cancel the project instead.")
        )
    if project.subprojects.exists():
        raise ValidationError(_("This project has subprojects and cannot be deleted."))
    if project.billed_documents.exists() or project.monthly_statements.exclude(status="draft").exists():
        # DOK-016: a service case billed by a monthly invoice or a marked monthly statement stays.
        raise ValidationError(_("This service case is billed by a monthly statement and cannot be deleted."))
    project.delete()


# --- Groups (PRJ-014, PRJ-039, PRJ-040) ------------------------------------


def _check_price_rights(changes: Iterable[str], rights: Rights, *, price_fields: frozenset[str]) -> None:
    """AUT-019: without the price right, price fields cannot be set either."""
    touched = set(changes)
    if touched & price_fields and not rights.has(SpecialRight.PRICES):
        raise ValidationError(_("You do not have the right to set prices or discounts."))
    if touched & PURCHASE_FIELDS and not rights.has(SpecialRight.PURCHASE_PRICES):
        raise ValidationError(_("You do not have the right to set purchase prices."))


def _last_position_among(project: Project, parent: Group | None) -> int:
    """The position of the last group with this parent (``None``: of the top level), 0 if there is none."""
    return project.groups.filter(parent=parent).aggregate(last=Max("position"))["last"] or 0


def add_group(project: Project, *, rights: Rights, **fields: Any) -> Group:
    """Add a group at the end of a project – or, with ``parent``, at the end of that group's subgroups (PRJ-037)."""
    ensure_editable(project)
    _check_price_rights(fields.keys(), rights, price_fields=GROUP_PRICE_FIELDS)
    if fields.get("alternative_to") is not None and "kind" not in fields:
        fields["kind"] = GroupKind.ALTERNATIVE  # PRJ-083: naming what it could replace makes it an alternative
    parent = fields.get("parent")
    if parent is not None and parent.project_id != project.pk:
        raise ValidationError({"parent": _("The parent group belongs to a different project.")})
    group = Group(project=project, position=_last_position_among(project, parent) + 1, **fields)
    group.full_clean()
    group.save()
    return group


def update_group(group: Group, *, rights: Rights, **changes: Any) -> Group:
    """Change name, description, kind or price adjustment of a group.

    A new ``parent`` moves the group with everything in it to the end of
    that group's subgroups, or of the top level (PRJ-037, see :func:`move_group`).
    ``alternative_to`` names the group an alternative group could replace
    (PRJ-083); naming one makes the group an alternative, any other kind
    clears it.
    """
    ensure_editable(group.project)
    _check_price_rights(changes.keys(), rights, price_fields=GROUP_PRICE_FIELDS)
    # PRJ-083: an alternative names the group it could replace; a group that is none names none.
    if changes.get("alternative_to") is not None and "kind" not in changes:
        changes["kind"] = GroupKind.ALTERNATIVE
    if "kind" in changes and changes["kind"] != GroupKind.ALTERNATIVE:
        changes["alternative_to"] = None
    with transaction.atomic():
        moves = "parent" in changes and _stored_parent_id(group) != getattr(changes["parent"], "pk", None)
        new_parent = changes.pop("parent", None)
        for name, value in changes.items():
            setattr(group, name, value)
        if moves:
            return move_group(group, parent=new_parent)
        group.full_clean()
        group.save()
    return group


def _stored_parent_id(group: Group) -> int | None:
    """The parent of a group as the database knows it – a form may have changed the instance already."""
    if group.pk is None:
        return None
    return Group.objects.filter(pk=group.pk).values_list("parent_id", flat=True).first()


@transaction.atomic
def move_group(group: Group, *, parent: Group | None, position: int | None = None) -> Group:
    """Put a group – with its lines and subgroups – into another group or onto the top level (PRJ-037).

    The group takes ``position`` among its new siblings (1 = first); the
    groups behind it move one place down. Without a position it goes to the
    end. Positions count among the groups with the same parent, so both the
    old and the new siblings are numbered 1, 2, 3 … afterwards.

    Raises:
        ValidationError: The project is closed; ``parent`` belongs to another
            project, is the group itself or one of its subgroups; or the
            group with its subgroups would end up deeper than three levels.
            The messages are filed under ``parent``.
    """
    project = group.project
    ensure_editable(project)
    if parent is not None and parent.project_id != project.pk:
        raise ValidationError({"parent": _("The parent group belongs to a different project.")})
    old_parent_id = _stored_parent_id(group)
    group.parent = parent
    group.full_clean()  # PRJ-037: no cycle, at most three levels
    siblings = list(project.groups.filter(parent=parent).exclude(pk=group.pk).order_by("position", "id"))
    place = len(siblings) if position is None else max(0, min(int(position) - 1, len(siblings)))
    siblings.insert(place, group)
    for number, sibling in enumerate(siblings, start=1):
        if sibling is group or sibling.position != number:
            sibling.position = number
            sibling.save()
    if old_parent_id != group.parent_id:
        _renumber_children(project, old_parent_id)
    return group


def _renumber_children(project: Project, parent_id: int | None) -> None:
    """Number the groups with this parent 1, 2, 3 … in their present order (PRJ-037)."""
    for number, sibling in enumerate(project.groups.filter(parent_id=parent_id).order_by("position", "id"), start=1):
        if sibling.position != number:
            sibling.position = number
            sibling.save()


@transaction.atomic
def delete_group(group: Group, *, keep_lines: bool = True) -> None:
    """Delete a group.

    PRJ-037: what the group holds moves up one level into its place – its
    lines into the group above it (or to "without group" for a top-level
    group), its subgroups to where the group itself stood. Nothing but the
    group itself disappears.

    Groups and lines that were an alternative to what is deleted become
    optional (PRJ-083).

    Args:
        group: The group.
        keep_lines: ``True`` keeps lines and subgroups as described;
            ``False`` deletes them together with the group: every line and
            every subgroup below it.

    Raises:
        ValidationError: The project is closed, or material of a line to be
            deleted has already been issued.
    """
    project = group.project
    ensure_editable(project)
    if not keep_lines:
        tree = GroupTree(project.groups.all())
        doomed = tree.subtree_ids(tree.by_id[group.pk])
        for line in project.material_lines.filter(group_id__in=doomed).select_related("product"):
            delete_line(line)
        # PRJ-083: alternatives to a group that goes become optional.
        _alternatives_become_optional(
            project.groups.filter(alternative_to_id__in=doomed).exclude(pk__in=doomed).order_by("pk")
        )
        group.delete()  # the subgroups go with it
        return
    _alternatives_become_optional(group.alternatives.order_by("pk"))
    parent = group.parent if group.parent_id else None
    last = project.material_lines.filter(group=parent).aggregate(last=Max("position"))["last"] or 0
    for offset, line in enumerate(group.lines.order_by("position", "id"), start=1):
        line.group = parent
        line.position = last + offset
        line.save()
    # The subgroups take the place of the deleted group, in their order.
    siblings = list(project.groups.filter(parent=parent).order_by("position", "id"))
    children = list(group.children.order_by("position", "id"))
    place = next(index for index, sibling in enumerate(siblings) if sibling.pk == group.pk)
    siblings[place : place + 1] = children
    for number, sibling in enumerate(siblings, start=1):
        if sibling.parent_id != (parent.pk if parent else None) or sibling.position != number:
            sibling.parent = parent
            sibling.position = number
            sibling.save()
    group.delete()


def reorder_groups(project: Project, group_ids: list[int]) -> None:
    """Put the groups of a project into the given order.

    PRJ-037: positions count among siblings; the groups keep their parents,
    and of the list only the order among groups with the same parent
    matters. To move a group into another one, see :func:`move_group`.
    """
    ensure_editable(project)
    groups = {group.pk: group for group in project.groups.all()}
    for position, group_id in enumerate(group_ids, start=1):
        group = groups.get(group_id)
        if group is not None and group.position != position:
            group.position = position
            group.save()


# --- Lines (PRJ-010 ff.) -----------------------------------------------------


def seen_state_of(product: Product) -> dict[str, Any]:
    """What a line notes of its product besides the price when it takes the product over (PRJ-072).

    Returns:
        Name, unit, tax rate and billing mode of the product, as stored in ``MaterialLine.product_seen``.
    """
    seen: dict[str, Any] = {
        "name": product.name,
        "unit": product.unit_id,
        "tax_rate": product.tax_rate_id,
        "billing_mode": product.billing_mode,
    }
    if product.is_percent_surcharge and product.surcharge_percent is not None:
        seen["surcharge_percent"] = str(product.surcharge_percent)  # its price (stored as text: JSON has no Decimal)
    return seen


def defaults_from_product(product: Product, *, is_sale: bool | None = None, taken_over: bool = False) -> dict[str, Any]:
    """Return the values a new line copies from its product (PRJ-015).

    The copy is the point: later price changes of the product must not alter
    existing lines. ``list_price`` remembers the product's price at this
    moment, so that a later change of it can be pointed out (PRJ-072).

    Args:
        product: The product being planned.
        is_sale: Whether the line sells. ``None`` decides by the product:
            sale products and products without rental price are sold.
        taken_over: The line takes over pieces of another subproject (PRJ-060) and is not charged; renting a
            product without rental price is then no error – an older source line may rent a sale
            product whose price the update removed (PRD-047).

    Raises:
        ValidationError: PRD-047 (one price per product) – a sale asked for a
            product without sale price (a rental product is no longer sold:
            "Verkaufen statt vermieten" stays only for lines that sold it
            before), or renting a product without price.
    """
    if is_sale is None:
        is_sale = product.kind == ProductKind.SALE or (product.price is None and product.sale_price is not None)
    elif not product.owner_id and not product.is_percent_surcharge:
        # Customer material is checked by the line itself (PRJ-096); a percentage surcharge has no price.
        if is_sale and product.sale_price is None:
            raise ValidationError({"is_sale": _("This product has no sale price and cannot be sold.")})
        if not is_sale and product.price is None and not taken_over:
            raise ValidationError({"is_sale": _("This product has no rental price and can only be sold.")})
    values: dict[str, Any] = {
        "title": product.name,
        "unit": product.unit,
        "tax_rate": product.tax_rate,
        "is_sale": is_sale,
        "billing_mode": BillingMode.FLAT if is_sale else product.billing_mode,
        "unit_price": (product.sale_price if is_sale else product.price) or Decimal("0"),
        "scale_version": None,
        "surcharge_percent": None,
        "quantity_is_estimate": not is_sale and product.billing_mode == BillingMode.EFFORT,
    }
    if not is_sale:
        scale = product.effective_rental_scale()
        values["scale_version"] = scale.current_version if scale else None
    values["list_price"] = product.sale_price if is_sale else product.price
    values["product_seen"] = seen_state_of(product)
    if product.is_percent_surcharge:
        values["surcharge_percent"] = product.surcharge_percent
        values["unit_price"] = Decimal("0")
        values["list_price"] = None
    if product.kind == ProductKind.SUBRENTAL:
        values["subrental_status"] = SubrentalStatus.OPEN  # PRJ-101: nothing asked yet
    return values


def plannable_as_material(product: Product) -> bool:
    """PRD-044: whether a product can be a material line – a service is planned only with its job function.

    LOG-001: a vehicle neither – it is booked under "Logistik".
    """
    return product.kind not in CREW_ONLY_KINDS and product.kind not in LOGISTICS_KINDS


def check_plannable_as_material(product: Product) -> None:
    """Refuse a service as a material line, naming its job function (PRD-044).

    Lines of services planned earlier stay as they are; only new ones
    are refused – through the page, a template, a plot or the API.

    Raises:
        ValidationError: The product is a service.
    """
    if plannable_as_material(product):
        return
    if product.kind in LOGISTICS_KINDS:
        raise ValidationError(
            {
                "product": _("%(product)s is a vehicle. Vehicles and trailers are booked under Logistics.")
                % {"product": f"{product.article_number} {product.name}"}
            }
        )
    function = product.service_job_function
    if function is not None:
        message = _(
            "%(product)s is the service of the job function %(function)s. Plan it under Personnel: "
            "choose the job function there, and the line takes its price."
        ) % {"product": f"{product.article_number} {product.name}", "function": function.name}
    else:
        message = _("%(product)s is a service. Services are planned under Personnel with their job function.") % {
            "product": f"{product.article_number} {product.name}"
        }
    raise ValidationError({"product": message})


def _next_position(project: Project, group: Group | None) -> int:
    """Return the position after the last line of a group (or of "without group")."""
    last = project.material_lines.filter(group=group).aggregate(last=Max("position"))["last"]
    return (last or 0) + 1


def _lock_products(product_ids: Iterable[int]) -> None:
    """Take a row lock on the given products for the current transaction (VFG-007).

    Two users who book the same product at the same moment are thereby put
    in a queue: the second one waits until the first has saved and then sees
    that booking in its availability check. Without the lock both checks
    could run before either booking is stored, and both would report "free".

    The products are always locked in ascending ID order, so two requests
    can never wait for each other in a circle.

    L16: callers pass ``AvailabilityEngine.competing_products`` – the kit
    components and also the containers that carry the product and the loose
    contents of a container: a rack and a part of its contents draw on the same
    stock, and booked at the same moment both would have reported "free".
    """
    ids = sorted({product_id for product_id in product_ids if product_id})
    if ids:
        list(Product.objects.select_for_update().filter(pk__in=ids).order_by("pk").values_list("pk", flat=True))


def _availability_for(line: MaterialLine, engine: AvailabilityEngine) -> LineAvailability:
    """Return the availability verdict for a line that was just saved."""
    return engine.line_availability(line)


def add_line(
    project: Project,
    *,
    rights: Rights,
    product: Product | None = None,
    quantity: Decimal | int = 1,
    group: Group | None = None,
    start: datetime.datetime | None = None,
    end: datetime.datetime | None = None,
    **overrides: Any,
) -> LineResult:
    """Add a material line to a project (PRJ-010, PRJ-012, PRJ-013, PRJ-017).

    Check and save happen in one protected step (VFG-007): the product is
    locked, the line is stored, and the availability returned was calculated
    while the lock was still held.

    Overbooking is allowed (PRJ-013): a line with a shortage is saved all the
    same. The shortage is part of the result and stays visible until covered.

    Args:
        project: The project.
        rights: The rights of the caller; decide whether prices may be set.
        product: The product to plan; ``None`` creates a free line, which
            then needs ``title`` and ``tax_rate`` (the default rate is used
            if none is given).
        quantity: How many units.
        group: The group to put the line in, or ``None``.
        start: Begin of the line's period; default is the project's.
        end: End of the line's period; default is the project's.
        **overrides: Further field values, e.g. ``unit_price``, ``note``,
            ``is_sale``, ``supplier``, or a wish for specific material
            (``preferred_model``, ``preferred_item`` – PRJ-064).

    Raises:
        ValidationError: The project is closed, the product is deactivated
            (PRD-024), or a value is invalid.
    """
    ensure_editable(project)
    ensure_plannable(project)  # PRJ-090: not in a service case
    _check_price_rights(overrides.keys(), rights, price_fields=PRICE_FIELDS)

    values: dict[str, Any] = {}
    if product is not None:
        if not product.is_active:
            raise ValidationError(
                _("%(product)s is deactivated and cannot be added to projects.") % {"product": product}
            )
        check_plannable_as_material(product)
        values.update(
            defaults_from_product(
                product, is_sale=overrides.get("is_sale"), taken_over=overrides.get("taken_over_from") is not None
            )
        )
        # KND-006: the customer's standard discount, unless the line says otherwise.
        discount = project.customer.default_discount_percent if project.customer_id else None
        # PRJ-096: customer material is not charged and gets no discount.
        if (
            discount
            and "discount_percent" not in overrides
            and not product.is_percent_surcharge
            and not product.owner_id
        ):
            values["discount_percent"] = discount
    else:
        values["tax_rate"] = TaxRate.get_default()
        values["billing_mode"] = BillingMode.FLAT
        if not overrides.get("title"):
            raise ValidationError({"title": _("A line without product needs a title.")})
    values.update(overrides)
    further = _take_wished_items(values)

    with transaction.atomic():
        engine = AvailabilityEngine()
        if product is not None:
            _lock_products(engine.competing_products([product.pk]))
        line = MaterialLine(
            project=project,
            group=group,
            product=product,
            quantity=Decimal(quantity),
            start=start or project.start,
            end=end or project.end,
            position=_next_position(project, group),
            **values,
        )
        line.pending_further_items = further
        line.full_clean()
        line.save()
        _store_wished_items(line, further)
        availability = _availability_for(line, engine)
    warnings = []
    if "discount_percent" in overrides and line_discount_warning(line):
        warnings.append(line_discount_warning(line))  # A discount above the maximum is cut – and said
    return LineResult(line=line, availability=availability, warnings=warnings)


def add_text_line(
    project: Project,
    *,
    title: str,
    note: str = "",
    group: Group | None = None,
) -> LineResult:
    """Add a line that only carries a text – a heading or a remark – at the end of a group (text line; PRJ-128).

    The line has no product, quantity 0, no price and no discount (see
    ``MaterialLine.is_text``); it takes the period of the project and the
    default tax rate, which are needed to store it but never shown. It has no
    availability to check and needs no price right.

    Args:
        project: The project.
        title: The text (up to 200 characters).
        note: A longer text printed below it; optional.
        group: The group to put it in, or ``None`` for "without group".

    Raises:
        ValidationError: The project is closed or a service case, the text is empty or too long, or the group
            belongs to another project.
    """
    ensure_editable(project)
    ensure_plannable(project)
    with transaction.atomic():
        line = MaterialLine(
            project=project,
            group=group,
            product=None,
            title=(title or "").strip(),
            note=(note or "").strip(),
            quantity=Decimal("0"),
            start=project.start,
            end=project.end,
            position=_next_position(project, group),
            tax_rate=TaxRate.get_default(),
            billing_mode=BillingMode.FLAT,
            unit_price=Decimal("0"),
            is_text=True,
        )
        line.full_clean()
        line.save()
    return LineResult(line=line, availability=LineAvailability())


def take_over_line(
    source: MaterialLine,
    project: Project,
    *,
    rights: Rights,
    quantity: Decimal | int | None = None,
    group: Group | None = None,
) -> LineResult:
    """Plan the pieces of a line of another subproject once more, in this one (PRJ-060).

    The new line has the product of the source line and, unless given, all
    the pieces that no other line takes over yet. Its period is that of the
    project. It is not charged: the pieces are charged on the source line.

    Raises:
        ValidationError: The two projects are not parts of the same whole
            project, the source line starts later, or more pieces are asked
            for than are left.
    """
    if source.product_id is None:
        raise ValidationError(_("Only lines with a product can be taken over."))
    if quantity is None:
        taken = source.taken_over_by.aggregate(total=Sum("quantity"))["total"] or 0
        quantity = max(source.quantity - taken, 0)
    return add_line(
        project,
        rights=rights,
        product=source.product,
        quantity=quantity,
        group=group,
        taken_over_from=source,
        is_sale=False,
    )


def update_line(line: MaterialLine, *, rights: Rights, **changes: Any) -> LineResult:
    """Change a material line (PRJ-011, PRJ-015).

    Switching between rental and sale takes over the matching price of the
    product, unless a unit price is passed along.

    Raises:
        ValidationError: The project is closed, a field is not editable, the
            caller lacks the price right, or a value is invalid.
    """
    ensure_editable(line.project)
    unknown = set(changes) - EDITABLE_LINE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    _check_price_rights(changes.keys(), rights, price_fields=PRICE_FIELDS)

    further = _take_wished_items(changes)
    if further is None and "preferred_item" in changes and changes["preferred_item"] is None:
        further = []  # taking back the wish takes back all of it
    line.pending_further_items = further

    if "is_sale" in changes and changes["is_sale"] != line.is_sale and line.product is not None:
        product_values = defaults_from_product(line.product, is_sale=changes["is_sale"])
        for name in ("billing_mode", "unit_price", "list_price", "scale_version", "quantity_is_estimate"):
            setattr(line, name, product_values[name])
        line.product_seen = {**line.product_seen, "billing_mode": product_values["product_seen"]["billing_mode"]}
    moves = "group" in changes and changes["group"] != line.group
    if moves:
        line.position = _next_position(line.project, changes["group"])
    if changes.get("alternative_to") is not None and "variant" not in changes:
        # PRJ-083: naming what a line could replace makes it an alternative.
        changes["variant"] = LineVariant.ALTERNATIVE
    if "variant" in changes:
        if changes["variant"] and not line.variant:
            check_may_become_variant(line)
        if changes["variant"] != LineVariant.ALTERNATIVE:
            # PRJ-083: only an alternative names what it could replace.
            changes["alternative_to"] = None

    with transaction.atomic():
        engine = AvailabilityEngine()
        if line.product_id:
            _lock_products(engine.competing_products([line.product_id]))
        if changes.get("preferred_item") is None and "preferred_item" in changes and "preferred_model" not in changes:
            # Taking back the wish for an item takes back the model it implied.
            line.preferred_model = None
        for name, value in changes.items():
            setattr(line, name, value)
        line.full_clean()
        line.save()
        _store_wished_items(line, further)
        if moves:
            _covering_lines_follow(line)
        availability = _availability_for(line, engine)
    warnings = []
    if "discount_percent" in changes and line_discount_warning(line):
        warnings.append(line_discount_warning(line))  # A discount above the maximum is cut – and said
    return LineResult(line=line, availability=availability, warnings=warnings)


def check_may_become_variant(line: MaterialLine) -> None:
    """Refuse to make a line optional or an alternative where that would break something (PRJ-075, PRJ-083).

    * A subrental that covers a shortage counts like the line it covers.
    * Material that has already been issued would drop off the packlist.
    * Pieces that other subprojects take over (PRJ-060) must stay planned.

    Raises:
        ValidationError: One of these holds.
    """
    if line.is_covering_subrental:
        raise ValidationError(
            _("A subrental that covers a shortage counts like the line it covers; it cannot be optional.")
        )
    if line.is_customer_material:
        raise ValidationError(_("Customer material is taken along; it cannot be optional or an alternative."))
    if line.pk is None:
        return
    if line.pack_entries.filter(issued_quantity__gt=0).exists():
        raise ValidationError(_("Material of this line has already been issued; it cannot become optional."))
    if line.taken_over_by.exists():
        raise ValidationError(_("Other subprojects take over pieces of this line; it cannot become optional."))


def _covering_lines_follow(line: MaterialLine) -> None:
    """Subrentals that cover a shortage of a line stay in its group (PRJ-084): they are shown below it."""
    for covering in line.covering_lines.exclude(group_id=line.group_id):
        covering.group_id = line.group_id
        covering.position = line.position
        covering.save()


def delete_line(line: MaterialLine) -> None:
    """Delete a material line.

    Subrentals that covered a shortage of this line are kept as lines of
    their own: the order with the supplier may already be placed. Lines
    that were an alternative to it become optional (PRJ-083).

    Raises:
        ValidationError: The project is closed, or material of this line has
            already been issued.
    """
    ensure_editable(line.project)
    if line.pack_entries.filter(issued_quantity__gt=0).exists():
        raise ValidationError(_("Material of this line has already been issued. The line cannot be deleted."))
    with transaction.atomic():
        _alternatives_become_optional(line.alternatives.all())
        line.delete()


def _alternatives_become_optional(alternatives: Iterable[MaterialLine] | Iterable[Group]) -> None:
    """PRJ-083: what was an alternative to something deleted stays as an option – with nothing to replace.

    Saved one by one, so that the history of the project shows the change.
    """
    for alternative in alternatives:
        if isinstance(alternative, Group):
            alternative.kind = GroupKind.OPTIONAL
        else:
            alternative.variant = LineVariant.OPTIONAL
        alternative.alternative_to = None
        alternative.save()


@transaction.atomic
def arrange_lines(project: Project, layout: list[tuple[int | None, list[int]]]) -> None:
    """Store the order of lines after dragging (PRJ-014).

    Args:
        project: The project.
        layout: For each group (``None`` = without group) the IDs of its
            lines in the wanted order. Lines can change groups this way.
    """
    ensure_editable(project)
    lines = {line.pk: line for line in project.material_lines.all()}
    groups = {group.pk: group for group in project.groups.all()}
    for group_id, line_ids in layout:
        if group_id is not None and group_id not in groups:
            raise ValidationError(_("Unknown group."))
        for position, line_id in enumerate(line_ids, start=1):
            line = lines.get(line_id)
            if line is None:
                continue
            if line.group_id != group_id or line.position != position:
                line.group_id = group_id
                line.position = position
                line.save()
    # A percentage surcharge belongs where its targets are (PRJ-058),
    # whatever it was dragged to.
    for line in project.material_lines.filter(surcharge_percent__isnull=False):
        _place_percent_surcharge(line)
    # PRJ-084: a subrental that covers a shortage is shown below its line and moves with it.
    for covering in project.material_lines.filter(covers_line__isnull=False).select_related("covers_line"):
        if covering.group_id != covering.covers_line.group_id:
            covering.group_id = covering.covers_line.group_id
            covering.position = covering.covers_line.position
            covering.save()


# --- Surcharges (PRD-031, PRD-039, PRJ-058) -----------------------------------


@transaction.atomic
def set_surcharge_targets(line: MaterialLine, targets: list[dict[str, Any]]) -> None:
    """Define what a percentage surcharge refers to.

    Args:
        line: A percentage surcharge line.
        targets: A list of dictionaries with the key ``type`` (``line``,
            ``group``, ``personnel`` or ``project``) and, for lines and
            groups, ``id``.

    Raises:
        ValidationError: The line is not a percentage surcharge, or a target
            does not belong to the project or is itself a surcharge.
    """
    ensure_editable(line.project)
    if not line.is_percent_surcharge:
        raise ValidationError(_("Only percentage surcharges refer to other amounts."))
    new_targets: list[SurchargeTarget] = []
    for target in targets:
        target_type = target.get("type")
        if target_type == SurchargeTargetType.LINE:
            target_line = line.project.material_lines.filter(pk=target.get("id")).select_related("product").first()
            if target_line is None or target_line.pk == line.pk:
                raise ValidationError(_("The surcharge refers to a line that does not exist in this project."))
            if target_line.is_surcharge:
                raise ValidationError(_("A surcharge cannot refer to another surcharge."))
            if target_line.is_text:
                # (text lines; PRJ-128): a text line has no amount a percentage could be taken from.
                raise ValidationError(_("A surcharge cannot refer to a text line."))
            new_targets.append(SurchargeTarget(surcharge_line=line, target_type=target_type, target_line=target_line))
        elif target_type == SurchargeTargetType.GROUP:
            target_group = line.project.groups.filter(pk=target.get("id")).first()
            if target_group is None:
                raise ValidationError(_("The surcharge refers to a group that does not exist in this project."))
            new_targets.append(SurchargeTarget(surcharge_line=line, target_type=target_type, target_group=target_group))
        elif target_type in {SurchargeTargetType.PROJECT, SurchargeTargetType.PERSONNEL}:
            new_targets.append(SurchargeTarget(surcharge_line=line, target_type=target_type))
        else:
            raise ValidationError(_("Unknown kind of surcharge target."))
    line.surcharge_targets.all().delete()
    SurchargeTarget.objects.bulk_create(new_targets)
    record_event(line, "line.surcharge_targets_changed", {"targets": [str(target) for target in new_targets]})
    _place_percent_surcharge(line)


def _place_percent_surcharge(line: MaterialLine) -> None:
    """Put a percentage surcharge where PRJ-058 wants it.

    If everything it refers to lies in one single group, the surcharge stands
    in that group. In all other cases – several groups, personnel, the whole
    project – it stands in the project's own block "surcharges", i.e. without
    group.
    """
    group_ids: set[int | None] = set()
    for target in line.surcharge_targets.select_related("target_line"):
        if target.target_type == SurchargeTargetType.GROUP:
            group_ids.add(target.target_group_id)
        elif target.target_type == SurchargeTargetType.LINE and target.target_line is not None:
            group_ids.add(target.target_line.group_id)
        else:
            group_ids.add(None)
    wanted_group_id = group_ids.pop() if len(group_ids) == 1 else None
    if line.group_id != wanted_group_id:
        line.group_id = wanted_group_id
        line.position = _next_position(line.project, Group.objects.filter(pk=wanted_group_id).first())
        line.save()


# --- Rental scales (PRD-037) ---------------------------------------------------


@transaction.atomic
def refresh_scale_versions(project: Project) -> int:
    """Switch all lines of a project to the current state of their rental scales (PRD-037).

    Lines normally keep calculating with the table as it was when they were
    created. This function is the deliberate "bring this project up to
    date". Factors set by hand stay untouched.

    Returns:
        The number of lines that now calculate with a newer table.
    """
    ensure_editable(project)
    changed = 0
    for line in project.material_lines.select_related("product", "product__category", "scale_version"):
        if line.product is None or not line.uses_rental_days:
            continue
        scale = line.product.effective_rental_scale()
        current = scale.current_version if scale else None
        if (current.pk if current else None) != line.scale_version_id:
            line.scale_version = current
            line.save()
            changed += 1
    return changed


# --- Subrental (PRJ-018, PRJ-054, PRJ-055) -------------------------------------


def default_subrental_product() -> Product | None:
    """Return the general product "subrental" that covers shortages (PRD-040)."""
    return Product.objects.filter(kind=ProductKind.SUBRENTAL, is_active=True).order_by("article_number").first()


@transaction.atomic
def accept_subrental_suggestion(
    line: MaterialLine,
    short_product: Product,
    quantity: int,
    *,
    rights: Rights,
    supplier: Any = None,
    purchase_price: Decimal | None = None,
    status: str = SubrentalStatus.OPEN,
) -> MaterialLine:
    """Create the subrental line that covers a shortage (PRJ-054, PRJ-055).

    The new line

    * is of the general subrental product (category E, PRD-040),
    * takes its title from the missing product,
    * has the quantity of the shortage and the period of the original line,
    * is linked to the original line and therefore costs the customer
      nothing extra – its purchase price only shows up in the costs.

    From then on the original line takes only the remaining pieces from the
    own stock (VFG-018). The planning shows it as a part of the original
    line, below it (PRJ-084): what is asked is supplier, quantity, purchase
    price and status – never a rental price.

    Args:
        line: The line that is short.
        short_product: The product that is missing. For a kit line this is
            the component, otherwise the line's own product.
        quantity: How many pieces to subrent.
        rights: The rights of the caller.
        supplier: The supplier, if already known.
        purchase_price: What the supplier charges per piece, if known.
        status: Where the subrental stands with the supplier (PRJ-057);
            "open" by default, any other status needs the supplier (PRJ-101).

    Raises:
        ValidationError: No subrental product exists, the quantity is not
            positive, or a status other than "open" comes without supplier.
    """
    ensure_editable(line.project)
    if short_product.owner_id is not None:
        # PRJ-096: nobody else can supply the customer's own material.
        raise ValidationError(_("Customer material cannot be subrented. Check its items or the other projects."))
    if quantity < 1:
        raise ValidationError(_("The quantity to subrent must be at least 1."))
    subrental_product = default_subrental_product()
    if subrental_product is None:
        raise ValidationError(_("There is no active subrental product (category E). Create one first."))
    if purchase_price is not None and not rights.has(SpecialRight.PURCHASE_PRICES):
        raise ValidationError(_("You do not have the right to set purchase prices."))

    # Make room directly below the original line.
    for later in line.project.material_lines.filter(group=line.group, position__gt=line.position).order_by("-position"):
        later.position += 1
        later.save()

    values = defaults_from_product(subrental_product, is_sale=False)
    values.update(
        title=short_product.name,
        unit=short_product.unit,
        unit_price=Decimal("0"),
        supplier=supplier,
        purchase_price=purchase_price,
        subrental_status=status or SubrentalStatus.OPEN,
    )
    subrental = MaterialLine(
        project=line.project,
        group=line.group,
        product=subrental_product,
        quantity=Decimal(quantity),
        start=line.start,
        end=line.end,
        position=line.position + 1,
        covers_line=line,
        covers_product=short_product,
        **values,
    )
    subrental.full_clean()
    subrental.save()
    return subrental


# --- Copying groups (PRJ-041) --------------------------------------------------


@transaction.atomic
def wall_clock_shift(new: datetime.datetime, old: datetime.datetime) -> datetime.timedelta:
    """The shift between two moments as the clock on the wall sees it (PRJ-029).

    From 08:00 in March to 08:00 in April is 31 days, although an hour less
    passes because summer time begins in between. :func:`moved` applies such
    a shift, so that a setup at 08:00 stays at 08:00 in the copy.
    """
    return timezone.localtime(new).replace(tzinfo=None) - timezone.localtime(old).replace(tzinfo=None)


def moved(moment: datetime.datetime, shift: datetime.timedelta) -> datetime.datetime:
    """A moment moved by a wall-clock shift of :func:`wall_clock_shift`."""
    local = timezone.localtime(moment).replace(tzinfo=None) + shift
    return timezone.make_aware(local)


def shifted_period(
    line: Any, source: Project, target: Project, shift: datetime.timedelta
) -> tuple[datetime.datetime, datetime.datetime]:
    """The period of a copied line in a duplicated project (PRJ-029).

    A line with the period of its project gets the period of the new
    project. A line with a period of its own keeps its place relative to the
    start, cut to the new period where it would stick out.
    """
    if (line.start, line.end) == (source.start, source.end):
        return target.start, target.end
    start = max(target.start, min(moved(line.start, shift), target.end))
    end = min(target.end, max(moved(line.end, shift), target.start))
    if end <= start:
        return target.start, target.end
    return start, end


@transaction.atomic
def copy_group(
    group: Group,
    target_project: Project,
    *,
    rights: Rights,
    shift: datetime.timedelta | None = None,
    line_copies: dict[int, MaterialLine] | None = None,
    group_copies: dict[int, Group] | None = None,
) -> Group:
    """Copy a group with its lines, within a project or into another (PRJ-041).

    Copied are the group's settings and its lines with their prices as they
    stand – and every subgroup below it with its lines, in the same
    arrangement (PRJ-037). Not copied are subrentals that cover a shortage
    (the shortage of the copy is a different question) and everything about
    packing. Customer material goes along only into a project of its owner
    (PRJ-096).

    Within the same project the copy stands at the end of the original's
    siblings, inside the same parent group; in another project it is added
    at the end of the top level.

    In another project the lines take over that project's period – or, when
    a whole project is duplicated (``shift`` given, PRJ-029), their period
    moves along with the project's start.

    ``line_copies``, if given, receives the copies of the lines by the ID of
    their original: duplicating a whole project with its parts links the
    lines taken over between the parts to the copies (PRJ-029, PRJ-060).
    ``group_copies`` receives the copies of the groups the same way.

    Copied alternatives name the copies of what they replace, see
    :func:`relink_alternatives` (PRJ-083). With ``line_copies`` given that
    is left to the caller, who may copy what they replace later.
    """
    ensure_editable(target_project)
    same_project = target_project.pk == group.project_id
    tree = GroupTree(group.project.groups.all())
    source = tree.by_id[group.pk]
    parent = tree.parent_of(source) if same_project else None
    with_prices = rights.has(SpecialRight.PRICES)
    new_groups: dict[int, Group] = {}
    copies: dict[int, MaterialLine] = {}
    for original in [source, *tree.descendants(source)]:
        if original is source:
            new_parent = parent
            name = _("%(name)s (copy)") % {"name": group.name} if same_project else group.name
            position = _last_position_among(target_project, parent) + 1
        else:
            new_parent = new_groups[original.parent_id]
            name, position = original.name, original.position
        new_group = Group(
            project=target_project,
            parent=new_parent,
            name=name,
            description=original.description,
            position=position,
            kind=original.kind,
            rental_days=original.rental_days,
        )
        if with_prices:
            new_group.discount_percent = original.discount_percent
            new_group.discount_amount = original.discount_amount
            new_group.flat_price = original.flat_price
        new_group.full_clean()
        new_group.save()
        new_groups[original.pk] = new_group
        copies.update(_copy_lines(original, new_group, target_project, same_project=same_project, shift=shift))

    # Surcharges inside the copied groups keep referring to the copies of their targets.
    for target in SurchargeTarget.objects.filter(surcharge_line_id__in=copies.keys()):
        if target.target_type == SurchargeTargetType.LINE and target.target_line_id in copies:
            SurchargeTarget.objects.create(
                surcharge_line=copies[target.surcharge_line_id],
                target_type=SurchargeTargetType.LINE,
                target_line=copies[target.target_line_id],
            )
        elif target.target_type == SurchargeTargetType.GROUP and target.target_group_id in new_groups:
            SurchargeTarget.objects.create(
                surcharge_line=copies[target.surcharge_line_id],
                target_type=SurchargeTargetType.GROUP,
                target_group=new_groups[target.target_group_id],
            )
    if group_copies is not None:
        group_copies.update(new_groups)
    if line_copies is not None:
        line_copies.update(copies)
    else:
        relink_alternatives(copies, new_groups, same_project=same_project)
    new_group = new_groups[group.pk]
    record_event(new_group, "group.copied", {"from_project": group.project.number, "from_group": group.name})
    return new_group


def relink_alternatives(
    line_copies: dict[int, MaterialLine], group_copies: dict[int, Group], *, same_project: bool
) -> None:
    """Copies of alternatives name the copies of what they replace (PRJ-083).

    If the line or group an original replaces was copied as well, its copy
    names that copy. Otherwise, within the same project, it names the same
    line or group as the original; in another project there is nothing to
    replace, and the copy becomes optional.

    Args:
        line_copies: The copies of lines by the ID of their original.
        group_copies: The copies of groups by the ID of their original.
        same_project: Whether the copies stand in the project of the originals.
    """
    for copies, model in ((line_copies, MaterialLine), (group_copies, Group)):
        if not copies:
            continue
        targets = dict(
            model.objects.filter(pk__in=copies, alternative_to__isnull=False).values_list("pk", "alternative_to_id")
        )
        for original_id, target_id in sorted(targets.items()):
            copy = copies[original_id]
            if target_id in copies:
                copy.alternative_to = copies[target_id]
            elif same_project:
                copy.alternative_to_id = target_id
            elif model is Group:
                copy.kind = GroupKind.OPTIONAL
            else:
                copy.variant = LineVariant.OPTIONAL
            copy.save()


def _copy_lines(
    group: Group,
    new_group: Group,
    target_project: Project,
    *,
    same_project: bool,
    shift: datetime.timedelta | None,
) -> dict[int, MaterialLine]:
    """Copy the lines of one group into another (PRJ-041); returns the copies by the ID of their original."""
    copies: dict[int, MaterialLine] = {}
    for line in group.lines.select_related("product").order_by("position", "id"):
        if line.is_covering_subrental:
            continue
        if line.product_id and not may_plan(line.product, target_project):
            continue  # PRJ-096: customer material goes only into projects of its owner
        if line.product_id and not plannable_as_material(line.product):
            continue  # PRD-044: a service is planned with the crew, never as a new material line
        if same_project:
            period = (line.start, line.end)
        elif shift is not None:
            period = shifted_period(line, group.project, target_project, shift)
        else:
            period = (target_project.start, target_project.end)
        copy = MaterialLine(
            project=target_project,
            group=new_group,
            product=line.product,
            title=line.title,
            quantity=line.quantity,
            unit=line.unit,
            start=period[0],
            end=period[1],
            position=line.position,
            note=line.note,
            is_sale=line.is_sale,
            billing_mode=line.billing_mode,
            unit_price=line.unit_price,
            discount_percent=line.discount_percent,
            tax_rate=line.tax_rate,
            hours=line.hours,
            quantity_is_estimate=line.quantity_is_estimate,
            rental_days=line.rental_days,
            scale_version=line.scale_version,
            manual_scale_factor=line.manual_scale_factor,
            surcharge_percent=line.surcharge_percent,
            supplier=line.supplier,
            purchase_price=line.purchase_price,
            subrental_status=SubrentalStatus.OPEN if line.is_subrental else "",  # PRJ-101
            preferred_model=line.preferred_model,
            preferred_item=line.preferred_item,
            variant=line.variant,
            list_price=line.list_price,
            product_seen=line.product_seen,
            is_text=line.is_text,  # A text line is copied as it is
        )
        copy.full_clean()
        copy.save()
        copy.copy_further_items_of(line)  # piece share (no more than the copy has pieces)
        copies[line.pk] = copy
    return copies
