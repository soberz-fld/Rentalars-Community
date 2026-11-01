# SPDX-License-Identifier: GPL-3.0-or-later
"""Project templates: start a new project from a proven one (PRJ-076, which carries out PRJ-030).

"Save as template" takes a copy of a project's structure:

* the groups with their settings, nested as they are (PRJ-037),
* the material lines: product, quantity, sale or rental, note, model wish,
  optional or alternative (PRJ-075) – lines without product with their title
  and price, text lines (``"is_text"``; PRJ-128) with their text,
* the crew places: job function, hours, meeting point, note, and their phase
  (PRJ-080, when the course is kept as well) – without people,
* with the crew places, the vehicle bookings (LOG-001): the
  vehicle product, title, note, phase and period – as open bookings, without
  the vehicle itself and with the rates of the product on the day the
  template is used,
* the course: phases with their times, and the open items,
* the notes of the project.

Times are kept relative to the start of the project. A line or crew place
with the project's own period gets the period of the new project; one with
a period of its own keeps its place relative to the start, cut to the new
period (the same rule as duplicating, PRJ-029).

What a template does **not** keep, on purpose: customer, venue, status,
people and prices of products. A template is used weeks or months later;
the prices are then those of the products on that day, and the customer's
standard discount applies (KND-006) – as if the lines were added by hand.
Only a group's own price arrangements (discount, flat price) and the price
of lines without product are kept, and only if whoever saves the template
may see prices.

Whole projects and their parts (PRJ-044, PRJ-060): a template holds one
project. Made from a whole project, it keeps only the whole project's own
groups, lines and crew – the parts are saved as templates one by one. A line
taken over from another part is kept as a normal line: in a project made
from the template it plans and charges its pieces itself. A template can be
applied to a part as well, when the part is created (``family_views``).

The content is plain JSON with keys of products and job functions. A
product or job function that is gone or deactivated when the template is
used is left out and named in the result.

Versions of the content: 1 has no nesting; 2 gives every
group the key of its parent group (``"parent"``, ``None`` at the top level,
PRJ-037) and lists parents before their subgroups. A template of version 1
is read as one with every group at the top level – it needs no conversion.
Lines have a ``"key"`` as well, and an alternative names the
key of the line or group it could replace in ``"alternative_to"``
(PRJ-083); a template without these keys is read as before, and an
alternative whose counterpart is left out becomes optional.

An entry with its own period may say ``"anchor": "end"``: its
seconds then count from the end of the project. "Save as template" does not
write it; the template "Dry Hire" of the start data uses it, so that the
return and the follow-up work lie at the end of a rental of any length
(PRJ-095, ``projects.defaults``).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.audit import record_event
from rentalars.personnel.models import JobFunction
from rentalars.products.models import Product
from rentalars.projects import services
from rentalars.projects.customer_material import may_plan
from rentalars.projects.grouptree import MAX_DEPTH, GroupTree
from rentalars.projects.models import (
    Group,
    GroupKind,
    LineVariant,
    MaterialLine,
    OpenItem,
    Project,
    ProjectPhase,
    ProjectTemplate,
)

#: Version of the content, so that later releases can read templates of earlier ones (see the module text).
CONTENT_VERSION = 2


def _offsets(project: Project, start: datetime.datetime, end: datetime.datetime) -> dict[str, Any]:
    """``{"own_period": False}`` for the project's period, else the wall-clock seconds from the project's start."""
    if (start, end) == (project.start, project.end):
        return {"own_period": False}
    base = timezone.localtime(project.start).replace(tzinfo=None)
    return {
        "own_period": True,
        "start": (timezone.localtime(start).replace(tzinfo=None) - base).total_seconds(),
        "end": (timezone.localtime(end).replace(tzinfo=None) - base).total_seconds(),
    }


def _period(offsets: dict[str, Any], project: Project) -> tuple[datetime.datetime, datetime.datetime]:
    """The period in a new project: its own period, or the kept place relative to its start, cut to it.

    PRJ-095: with ``"anchor": "end"`` the seconds count from the end of the
    project instead (negative: before it) – the return of a dry hire stays
    at the end of a rental of any length.
    """
    if not offsets.get("own_period"):
        return project.start, project.end
    anchor = project.end if offsets.get("anchor") == "end" else project.start
    base = timezone.localtime(anchor).replace(tzinfo=None)
    start = timezone.make_aware(base + datetime.timedelta(seconds=offsets["start"]))
    end = timezone.make_aware(base + datetime.timedelta(seconds=offsets["end"]))
    start = max(project.start, min(start, project.end))
    end = min(project.end, max(end, project.start))
    if end <= start:
        return project.start, project.end
    return start, end


def _decimal(value: Any) -> str | None:
    return None if value is None else str(value)


def capture(project: Project, *, rights: Rights, material: bool = True, crew: bool = True, course: bool = True) -> dict:
    """The content of a template made from ``project`` (see the module text for what is kept)."""
    with_prices = rights.has(SpecialRight.PRICES)
    content: dict[str, Any] = {
        "version": CONTENT_VERSION,
        "length_seconds": (project.end - project.start).total_seconds(),
        "notes": project.notes,
        "rental_days": project.rental_days,
        "groups": [],
        "lines": [],
        "crew": [],
        "vehicles": [],
        "phases": [],
        "open_items": [],
    }
    if material:
        tree = GroupTree(project.groups.all())
        for group in tree.ordered:
            parent = tree.parent_of(group)
            content["groups"].append(
                {
                    "key": group.pk,
                    # PRJ-037: the parent's key; parents come before their subgroups.
                    "parent": parent.pk if parent is not None else None,
                    "name": group.name,
                    "description": group.description,
                    "kind": group.kind,
                    "alternative_to": group.alternative_to_id,  # PRJ-083
                    "rental_days": group.rental_days,
                    "discount_percent": _decimal(group.discount_percent) if with_prices else None,
                    "discount_amount": _decimal(group.discount_amount) if with_prices else None,
                    "flat_price": _decimal(group.flat_price) if with_prices else None,
                }
            )
        group_order = {group.pk: index for index, group in enumerate(tree.ordered)}
        lines = sorted(
            project.material_lines.all(), key=lambda line: (group_order.get(line.group_id, -1), line.position, line.pk)
        )
        for line in lines:
            if line.is_covering_subrental:
                continue
            content["lines"].append(
                {
                    "key": line.pk,
                    "group": line.group_id,
                    "product": line.product_id,
                    "title": line.title if line.product_id is None else "",
                    "unit_price": _decimal(line.unit_price) if with_prices and line.product_id is None else None,
                    "quantity": str(line.quantity),
                    "is_sale": line.is_sale,
                    "hours": _decimal(line.hours),
                    "quantity_is_estimate": line.quantity_is_estimate,
                    "rental_days": line.rental_days,
                    "note": line.note,
                    "variant": getattr(line, "variant", ""),
                    "is_text": line.is_text,  # A text line is part of a template
                    "alternative_to": line.alternative_to_id,  # PRJ-083
                    "preferred_model": line.preferred_model_id,
                    **_offsets(project, line.start, line.end),
                }
            )
    phase_keys: dict[int, int] = {}
    if course:
        # PRJ-080: a crew place names its phase by the phase's place in this list.
        phase_keys = {
            pk: index for index, pk in enumerate(project.phases.order_by("start", "id").values_list("pk", flat=True))
        }
    if crew:
        for line in project.crew_lines.order_by("start", "position", "id"):
            content["crew"].append(
                {
                    "job_function": line.job_function_id,
                    "planned_hours": _decimal(line.planned_hours),
                    "meeting_point": line.meeting_point,
                    "note": line.note,
                    "phase": phase_keys.get(line.phase_id) if line.phase_id else None,
                    **_offsets(project, line.start, line.end),
                }
            )
    if crew:
        # LOG-001, LOG-019: the vehicle bookings as open bookings of their product.
        for vehicle_line in project.vehicle_lines.order_by("position", "id"):
            content["vehicles"].append(
                {
                    "product": vehicle_line.product_id,
                    "title": vehicle_line.title,
                    "note": vehicle_line.note,
                    "only_trip_days": vehicle_line.only_trip_days,
                    "phase": phase_keys.get(vehicle_line.phase_id) if vehicle_line.phase_id else None,
                    **_offsets(project, vehicle_line.start, vehicle_line.end),
                }
            )
    if course:
        for phase in project.phases.order_by("start", "id"):
            content["phases"].append(
                {
                    "kind": phase.kind,
                    "title": phase.title,
                    "location": phase.location,
                    "notes": phase.notes,
                    "venue_site": phase.venue_site_id,
                    **_offsets(project, phase.start, phase.end),
                    "own_period": True,
                }
            )
        content["open_items"] = [item.text for item in project.open_items.order_by("id")]
    return content


def save_as_template(
    project: Project,
    *,
    name: str,
    description: str = "",
    rights: Rights,
    user: Any = None,
    material: bool = True,
    crew: bool = True,
    course: bool = True,
    replace: bool = False,
) -> ProjectTemplate:
    """Store a template made from ``project`` (PRJ-076).

    Raises:
        ValidationError: The name is empty, or taken and ``replace`` is not set.
    """
    name = (name or "").strip()
    if not name:
        raise ValidationError({"name": _("Give the template a name.")})
    template = ProjectTemplate.objects.filter(name__iexact=name).first()
    if template is not None and not replace:
        raise ValidationError({"name": _("A template with this name exists already. Tick “replace” to overwrite it.")})
    template = template or ProjectTemplate(name=name)
    template.description = description
    template.content = capture(project, rights=rights, material=material, crew=crew, course=course)
    template.source_number = project.number
    if user is not None and getattr(user, "pk", None):
        template.created_by = user
    template.full_clean()
    template.save()
    record_event(project, "project.saved_as_template", {"template": template.name})
    return template


def _parents_first(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The groups of a template's content with every parent before its subgroups (PRJ-037).

    Templates write them in this order anyway; this keeps a template
    usable whose list was put together differently.
    """
    keys = {data.get("key") for data in groups}
    placed: set[Any] = set()
    ordered: list[dict[str, Any]] = []
    waiting = list(groups)
    while waiting:
        ready = [data for data in waiting if data.get("parent") in placed or data.get("parent") not in keys]
        if not ready:
            ready = waiting  # a cycle: whatever is left goes to the top level
        for data in ready:
            placed.add(data.get("key"))
            ordered.append(data)
        waiting = [data for data in waiting if data not in ready]
    return ordered


@dataclass
class ApplyResult:
    """What applying a template did: how much was created, and what was left out."""

    lines: int = 0
    crew: int = 0
    #: LOG-001: the vehicle bookings made.
    vehicles: int = 0
    phases: int = 0
    left_out: list[str] = field(default_factory=list)


@transaction.atomic
def _link_alternatives(content: dict[str, Any], groups: dict[Any, Group], lines: dict[Any, MaterialLine]) -> None:
    """PRJ-083: alternatives of the template name the copies of what they replace.

    An alternative whose counterpart was left out (a deactivated product) has
    nothing to replace and becomes optional – as when that line is deleted.
    """
    for entries, made, model in ((content.get("groups", []), groups, Group), (content.get("lines", []), lines, None)):
        for data in entries:
            target_key = data.get("alternative_to")
            item = made.get(data.get("key"))
            if target_key is None or item is None:
                continue
            item.alternative_to = made.get(target_key)
            try:
                if item.alternative_to is None:
                    raise ValidationError("nothing to replace")
                item.full_clean()
            except ValidationError:
                item.alternative_to = None
                if model is Group:
                    item.kind = GroupKind.OPTIONAL
                else:
                    item.variant = LineVariant.OPTIONAL
            item.save()


def _apply_vehicles(
    content: dict[str, Any], project: Project, phases: list[ProjectPhase], rights: Rights, result: ApplyResult
) -> None:
    """LOG-001, LOG-019: the vehicle bookings of a template as open bookings, at the rates of the product today."""
    from rentalars.projects.logistics import add_vehicle_line

    entries = content.get("vehicles", [])
    products = Product.objects.in_bulk([data["product"] for data in entries])
    for data in entries:
        product = products.get(data["product"])
        if product is None or not product.is_active or not product.is_vehicle:
            result.left_out.append(_("a vehicle product that no longer exists or is deactivated"))
            continue
        start, end = _period(data, project)
        key = data.get("phase")
        phase = phases[key] if isinstance(key, int) and 0 <= key < len(phases) else None
        overrides: dict[str, Any] = {"note": data.get("note", "")}
        if data.get("title"):
            overrides["title"] = data["title"][:200]
        if data.get("only_trip_days") and product.is_trailer and rights.has(SpecialRight.PRICES):
            overrides["only_trip_days"] = True
        add_vehicle_line(project, rights=rights, product=product, start=start, end=end, phase=phase, **overrides)
        result.vehicles += 1


def apply_template(template: ProjectTemplate, project: Project, *, rights: Rights) -> ApplyResult:
    """Fill ``project`` with the content of ``template`` (PRJ-076).

    Lines go in through the same service as lines added by hand, so that
    prices, the customer's discount and the availability check are those of
    today (PRJ-010, KND-006). People are not planned; the crew places are
    open (PRJ-020).

    Raises:
        ValidationError: The project is closed.
    """
    from rentalars.projects.crew import add_crew_lines

    services.ensure_editable(project)
    content = template.content or {}
    result = ApplyResult()
    if content.get("notes") and not project.notes:
        project.notes = content["notes"]
        project.save()

    groups: dict[Any, Group] = {}
    positions: dict[Any, int] = {None: services._last_position_among(project, None)}
    with_prices = rights.has(SpecialRight.PRICES)
    for data in _parents_first(content.get("groups", [])):
        # PRJ-037: version 1 knows no parents; a parent that is missing puts the group at the top.
        parent = groups.get(data.get("parent"))
        if parent is not None and parent.depth + 1 >= MAX_DEPTH:
            parent = None
        parent_key = parent.pk if parent is not None else None
        positions[parent_key] = positions.get(parent_key, 0) + 1
        group = Group(
            project=project,
            parent=parent,
            name=data["name"],
            description=data.get("description", ""),
            kind=data.get("kind") or Group._meta.get_field("kind").default,
            rental_days=data.get("rental_days"),
            position=positions[parent_key],
        )
        if with_prices:
            for name in ("discount_percent", "discount_amount", "flat_price"):
                if data.get(name) is not None:
                    setattr(group, name, Decimal(data[name]))
        group.full_clean()
        group.save()
        groups[data["key"]] = group

    products = Product.objects.in_bulk([data["product"] for data in content.get("lines", []) if data.get("product")])
    lines: dict[Any, MaterialLine] = {}
    for data in content.get("lines", []):
        product = products.get(data.get("product")) if data.get("product") else None
        if data.get("product") and (product is None or not product.is_active):
            result.left_out.append(_("a product that no longer exists or is deactivated"))
            continue
        if product is not None and not may_plan(product, project):
            # PRJ-096: customer material goes only into projects of its owner.
            result.left_out.append(_("customer material of another customer: %(product)s") % {"product": product.name})
            continue
        if product is not None and not services.plannable_as_material(product):
            # PRD-044: a service is planned with its job function under Personnel, not as material.
            result.left_out.append(_("a service, planned under Personnel: %(product)s") % {"product": product.name})
            continue
        if data.get("is_text"):
            # A text line carries only its text – no period, price or quantity.
            added = services.add_text_line(
                project,
                title=data.get("title") or _("Text"),
                note=data.get("note", ""),
                group=groups.get(data.get("group")),
            )
            result.lines += 1
            if data.get("key") is not None:
                lines[data["key"]] = added.line
            continue
        start, end = _period(data, project)
        overrides: dict[str, Any] = {"note": data.get("note", "")}
        for name in ("quantity_is_estimate", "rental_days", "variant"):
            if data.get(name) not in (None, ""):
                overrides[name] = data[name]
        if data.get("hours") is not None:
            overrides["hours"] = Decimal(data["hours"])
        if data.get("preferred_model"):
            overrides["preferred_model_id"] = data["preferred_model"]
        if product is not None:
            # PRD-047: a template from before may sell a rental product, which has no sale price
            # any more – such a line takes the product's one price, as a new line does.
            if (
                data.get("is_sale") is not None
                and (product.sale_price if data["is_sale"] else product.price) is not None
            ):
                overrides["is_sale"] = data["is_sale"]
        else:
            overrides["title"] = data.get("title") or _("Line")
            if with_prices and data.get("unit_price") is not None:
                overrides["unit_price"] = Decimal(data["unit_price"])
        added = services.add_line(
            project,
            rights=rights,
            product=product,
            quantity=Decimal(data.get("quantity") or "1"),
            group=groups.get(data.get("group")),
            start=start,
            end=end,
            **overrides,
        )
        result.lines += 1
        if data.get("key") is not None:
            lines[data["key"]] = added.line
    _link_alternatives(content, groups, lines)

    # The phases first, so that the crew places can belong to them again (PRJ-080).
    phases: list[ProjectPhase] = []
    for data in content.get("phases", []):
        start, end = _period(data, project)
        phases.append(
            ProjectPhase.objects.create(
                project=project,
                kind=data.get("kind") or ProjectPhase._meta.get_field("kind").default,
                title=data.get("title", ""),
                start=start,
                end=end,
                location=data.get("location", ""),
                notes=data.get("notes", ""),
                venue_site_id=data.get("venue_site"),
            )
        )
        result.phases += 1

    functions = JobFunction.objects.in_bulk([data["job_function"] for data in content.get("crew", [])])
    for data in content.get("crew", []):
        function = functions.get(data["job_function"])
        if function is None or not function.is_active:
            result.left_out.append(_("a job function that no longer exists or is deactivated"))
            continue
        start, end = _period(data, project)
        overrides = {"meeting_point": data.get("meeting_point", ""), "note": data.get("note", "")}
        if data.get("own_period") and data.get("planned_hours") is not None:
            overrides["planned_hours"] = Decimal(data["planned_hours"])
        key = data.get("phase")
        phase = phases[key] if isinstance(key, int) and 0 <= key < len(phases) else None
        add_crew_lines(project, rights=rights, job_function=function, start=start, end=end, phase=phase, **overrides)
        result.crew += 1
    _apply_vehicles(content, project, phases, rights, result)
    for text in content.get("open_items", []):
        OpenItem.objects.create(project=project, text=text)

    record_event(project, "project.from_template", {"template": template.name, "left_out": len(result.left_out)})
    return result
