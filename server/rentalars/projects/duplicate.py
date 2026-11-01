# SPDX-License-Identifier: GPL-3.0-or-later
"""Duplicating a project for a new period (PRJ-029).

The yearly city festival, the second evening of a tour: the new project is
made from an old one in one step. Copied are

* always: customer, contact, venue, notes, the phases – moved by the
  distance between the old and the new start;
* with "material": all groups – nested as they are (PRJ-037) – and lines
  with their prices as they stand, their periods moved the same way
  (``services.shifted_period``);
* with "personnel": the crew lines as open places – job function, period,
  hours, days, price, and the copy of their phase (PRJ-080) – but without
  the people: who has time on the new dates is a new question (PRJ-020).
* with "logistics" (LOG-001): the vehicle bookings with their
  vehicles, rates and the copy of their phase, moved like the lines; and
  the vehicles on the trips that exist in the copy as well – those of the
  phases setup and teardown, pickup and return – with trailer, planned
  kilometres and what is charged; driven kilometres start empty. A booked
  vehicle that is busy on the new dates is pointed out on the planning
  (LOG-004). Crew lines copied with the personnel keep their vehicle.

Not copied: status (the copy starts as an inquiry), subrentals that cover a
shortage, open items, files, mails, members, packing and times. The project
manager of the copy is whoever duplicates it.

Whole projects and their parts (PRJ-044, PRJ-060)
-------------------------------------------------
* A whole project is copied **with its subprojects** unless asked otherwise
  (``with_subprojects``). Every part is copied as described above, moved by
  the same distance as the whole project: it keeps its place relative to
  the start and its length – cut to the new period where that is shorter,
  as lines are. Lines taken over from one part by another
  (``MaterialLine.taken_over_from``) are taken over between the copies.
  The new parts are numbered after the new whole project; a part cancelled
  on its own is not copied (of a cancelled whole project, all parts are).
  What a part sets differently from its whole project –
  its own project manager, delivery address, contact or venue – it keeps.
* A **part** is copied as a new part of the same whole project
  (``as_subproject``, the default): its period has to lie within that of
  the whole project, and it starts in the status a new part gets there. A
  line taken over from another part stays taken over where that still
  works – the pieces left and the order in time permit it – and becomes a
  normal line otherwise. Copied as a project of its own, every line is a
  normal line.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.audit import record_event
from rentalars.projects.customer_material import may_plan
from rentalars.projects.models import (
    CrewLine,
    Group,
    MaterialLine,
    Project,
    ProjectPhase,
    ProjectStatus,
    SubrentalStatus,
    TripVehicle,
    VehicleLine,
)
from rentalars.projects.services import (
    copy_group,
    create_project,
    create_subproject,
    moved,
    plannable_as_material,
    relink_alternatives,
    shifted_period,
    wall_clock_shift,
)


@dataclass
class Duplicate:
    """What duplicating made: the new project, its new parts, and the take-overs that could not be kept."""

    project: Project
    parts: list[Project] = field(default_factory=list)
    #: PRJ-060: lines that were taken over in the original and are normal lines in the copy.
    dropped_takeovers: int = 0


@transaction.atomic
def copy_project(
    source: Project,
    *,
    name: str,
    start: datetime.datetime,
    end: datetime.datetime,
    with_material: bool = True,
    with_crew: bool = False,
    with_logistics: bool = False,
    with_subprojects: bool = True,
    as_subproject: bool = True,
    rights: Rights,
    user: Any,
) -> Duplicate:
    """Create a copy of a project for a new period; for a whole project with its parts (PRJ-029, PRJ-044).

    Args:
        source: The project to copy.
        name: The name of the copy; empty: that of the source.
        start: Start of the new rental period.
        end: End of the new rental period.
        with_material: Copy groups and lines.
        with_crew: Copy the crew lines as open places.
        with_logistics: Copy the vehicle bookings and the vehicles on the trips (LOG-001).
        with_subprojects: For a whole project: copy its parts as well.
        as_subproject: For a part: make the copy a new part of the same
            whole project; otherwise a project of its own.
        rights: The rights of the user; prices of groups only with the price right.
        user: Becomes the project manager of the copy.

    Raises:
        ValidationError: The new period is invalid or – for a new part – lies
            outside that of the whole project, or the customer of the source
            can no longer be used.
    """
    if end <= start:
        raise ValidationError({"end": _("The end must be after the start.")})
    if source.customer_id and (not source.customer.is_active or source.customer.is_anonymised):
        raise ValidationError(_("The customer of this project is deactivated; activate it first."))
    shift = wall_clock_shift(start, source.start)
    manager = user if getattr(user, "pk", None) else source.manager
    fields = _period_fields(source, start, end, shift)
    fields.update(name=name.strip() or source.name, contact=source.contact, venue=source.venue, notes=source.notes)
    fields.update(venue_site=source.venue_site, manager=manager)
    as_part = bool(source.parent_id) and as_subproject
    if as_part:
        # PRJ-044: a new part of the same whole project; customer and billing come from there.
        fields["delivery_address"] = source.delivery_address
        project = create_subproject(source.parent, **fields)
    else:
        project = create_project(customer=source.customer, is_internal=source.is_internal, **fields)
    result = Duplicate(project=project)
    copies: dict[int, MaterialLine] = {}
    options = {"with_material": with_material, "with_crew": with_crew, "with_logistics": with_logistics}
    _copy_contents(source, project, shift, rights, copies, **options)
    if with_material or with_crew or with_logistics:
        _copy_overall_discount(source, project, rights)  # a copy without anything to sum up gets no discount
    if with_subprojects and not source.parent_id:
        parts = source.subprojects.order_by("number", "pk")
        if source.status != ProjectStatus.CANCELLED:
            # A stage cancelled on its own is left behind; a cancelled festival is copied whole.
            parts = parts.exclude(status=ProjectStatus.CANCELLED)
        for part in parts:
            new_part = _copy_part(part, source, project, shift, manager)
            _copy_contents(part, new_part, shift, rights, copies, **options)
            if with_material or with_crew or with_logistics:
                _copy_overall_discount(part, new_part, rights)
            result.parts.append(new_part)
    result.dropped_takeovers = _take_over_again(copies, keep_outside=as_part)
    record_event(
        project,
        "project.duplicated",
        {
            "from": source.number,
            "material": with_material,
            "personnel": with_crew,
            "logistics": with_logistics,
            "subprojects": [part.number for part in result.parts],
        },
    )
    return result


def duplicate_project(source: Project, **options: Any) -> Project:
    """Create a copy of a project for a new period and return it (PRJ-029); see :func:`copy_project`."""
    return copy_project(source, **options).project


def _copy_overall_discount(source: Project, copy: Project, rights: Any) -> None:
    """PRJ-123: the copy has the overall discount of the source.

    Like the discounts of the groups, only for who may set prices.
    """
    if not rights.has(SpecialRight.PRICES):
        return
    if source.overall_discount_percent is None and source.overall_discount_amount is None:
        return
    copy.overall_discount_percent = source.overall_discount_percent
    copy.overall_discount_amount = source.overall_discount_amount
    copy.save()


def _period_fields(
    source: Project, start: datetime.datetime, end: datetime.datetime, shift: datetime.timedelta
) -> dict[str, Any]:
    """Rental period, event period and rental days of a copy (PRJ-029)."""
    event_start = event_end = None
    if source.event_start and source.event_end:
        event_start, event_end = moved(source.event_start, shift), moved(source.event_end, shift)
        if event_start < start or event_end > end:
            # The new period is shorter; the event cannot simply move along.
            event_start = event_end = None
    return {
        "start": start,
        "end": end,
        "event_start": event_start,
        "event_end": event_end,
        "rental_days": source.rental_days if source.event_start is None or event_start is not None else None,
    }


def _copy_part(part: Project, source: Project, whole: Project, shift: datetime.timedelta, manager: Any) -> Project:
    """A part of the source as a part of the copy of its whole project (PRJ-029, PRJ-044).

    The period moves with the whole project and is cut to its new period.
    What the part sets differently from its whole project it keeps; what it
    took over as preset comes from the copy of the whole project.
    """
    start, end = shifted_period(part, source, whole, shift)
    fields = _period_fields(part, start, end, shift)
    fields.update(name=part.name, contact=part.contact, venue=part.venue, venue_site=part.venue_site, notes=part.notes)
    # PRJ-045: presets of the whole project come from its copy; a part's own choice stays.
    fields["manager"] = manager if part.manager_id == source.manager_id else part.manager
    if part.delivery_address_id != source.delivery_address_id:
        fields["delivery_address"] = part.delivery_address
    new_part = create_subproject(whole, **fields)
    record_event(new_part, "project.duplicated", {"from": part.number, "whole_project": whole.number})
    return new_part


def _copy_contents(
    source: Project,
    project: Project,
    shift: datetime.timedelta,
    rights: Rights,
    copies: dict[int, MaterialLine],
    *,
    with_material: bool,
    with_crew: bool,
    with_logistics: bool = False,
) -> None:
    """Phases, and on request material, logistics and crew, of one project into its copy."""
    phases: dict[int, ProjectPhase] = {}
    for phase in source.phases.all():
        phases[phase.pk] = ProjectPhase.objects.create(
            project=project,
            kind=phase.kind,
            title=phase.title,
            start=moved(phase.start, shift),
            end=moved(phase.end, shift),
            venue_site=phase.venue_site,
            location=phase.location,
            notes=phase.notes,
        )
    if with_material:
        _copy_material(source, project, shift, rights, copies)
    vehicles = _copy_logistics(source, project, shift, phases) if with_logistics else {}
    if with_crew:
        _copy_crew(source, project, shift, rights, phases, vehicles)


def _take_over_again(copies: dict[int, MaterialLine], *, keep_outside: bool) -> int:
    """Let the copies of taken-over lines take over again (PRJ-060); returns how many could not.

    A line that took over from a line that was copied as well takes over
    from that copy. One that took over from a line that was not copied
    keeps taking over from it if ``keep_outside`` – a part copied into the
    same whole project. Where the rules of taking over no longer hold (too
    few pieces left, the order in time changed by a shorter period), the
    copy stays a normal line.
    """
    if not copies:
        return 0
    sources = dict(
        MaterialLine.objects.filter(pk__in=copies, taken_over_from__isnull=False).values_list(
            "pk", "taken_over_from_id"
        )
    )
    dropped = 0
    for original_id, source_id in sorted(sources.items()):
        copy = copies[original_id]
        if source_id in copies:
            copy.taken_over_from = copies[source_id]
        elif keep_outside:
            copy.taken_over_from_id = source_id
        else:
            dropped += 1
            continue
        try:
            copy.full_clean()
        except ValidationError:
            dropped += 1
            continue
        copy.save(update_fields=["taken_over_from"])
    return dropped


def _copy_material(
    source: Project,
    project: Project,
    shift: datetime.timedelta,
    rights: Rights,
    copies: dict[int, MaterialLine],
) -> None:
    # PRJ-037: each top-level group is copied with its subgroups, so the copy keeps the arrangement.
    own_copies: dict[int, MaterialLine] = {}
    group_copies: dict[int, Group] = {}
    for group in source.groups.filter(parent__isnull=True).order_by("position", "id"):
        copy_group(group, project, rights=rights, shift=shift, line_copies=own_copies, group_copies=group_copies)
    for line in source.material_lines.filter(group__isnull=True).select_related("product").order_by("position", "id"):
        if line.is_covering_subrental:
            continue
        if line.product_id and not may_plan(line.product, project):
            continue  # PRJ-096: customer material goes only into projects of its owner
        if line.product_id and not plannable_as_material(line.product):
            continue  # PRD-044: a service is planned with the crew, never as a new material line
        start, end = shifted_period(line, source, project, shift)
        copy = MaterialLine(
            project=project,
            group=None,
            product=line.product,
            title=line.title,
            quantity=line.quantity,
            unit=line.unit,
            start=start,
            end=end,
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
            is_text=line.is_text,
        )
        copy.full_clean()
        copy.save()
        copy.copy_further_items_of(line)  # piece share (no more than the copy has pieces)
        own_copies[line.pk] = copy
    # PRJ-083: alternatives name the copies of what they replace, wherever in the project those stand.
    relink_alternatives(own_copies, group_copies, same_project=False)
    copies.update(own_copies)


def _copy_logistics(
    source: Project, project: Project, shift: datetime.timedelta, phases: dict[int, ProjectPhase]
) -> dict[int, VehicleLine]:
    """LOG-001, LOG-019: the vehicle bookings, and the vehicles on the trips the copy has as well.

    A trip of a phase is named by the phase (``to_venue-12``), so it becomes
    the trip of the copied phase; pickup and return keep their names; trips
    added by hand are not copied (see the module text).

    Returns:
        The copies by the ID of the booking they were made from.
    """
    copies: dict[int, VehicleLine] = {}
    for line in source.vehicle_lines.select_related("product").order_by("position", "id"):
        start, end = shifted_period(line, source, project, shift)
        copy = VehicleLine(
            project=project,
            product=line.product,
            item=line.item if line.item_id and not line.item.is_archived else None,
            title=line.title,
            position=line.position,
            phase=phases.get(line.phase_id) if line.phase_id else None,
            start=start,
            end=end,
            note=line.note,
            billing=line.billing,
            price_per_km=line.price_per_km,
            trailer_surcharge_per_km=line.trailer_surcharge_per_km,
            price_per_day=line.price_per_day,
            rental_days=line.rental_days,
            only_trip_days=line.only_trip_days,
            scale_version=line.scale_version,
            discount_percent=line.discount_percent,
            tax_rate=line.tax_rate,
            cost_per_km=line.cost_per_km,
            cost_per_day=line.cost_per_day,
            supplier=line.supplier,
            subrental_cost=line.subrental_cost,
        )
        copy.full_clean()
        copy.save()
        copies[line.pk] = copy

    def new_key(key: str) -> str | None:
        kind, _sep, number = key.partition("-")
        if not number:
            return key  # pickup, return
        if kind in ("to_venue", "from_venue") and number.isdigit() and int(number) in phases:
            return f"{kind}-{phases[int(number)].pk}"
        return None  # a trip of one's own, or one that is gone

    for use in source.trip_vehicles.order_by("id"):
        key = new_key(use.trip_key)
        if key is None or use.vehicle_line_id not in copies:
            continue
        TripVehicle.objects.create(
            project=project,
            trip_key=key,
            vehicle_line=copies[use.vehicle_line_id],
            trailer_line=copies.get(use.trailer_line_id) if use.trailer_line_id else None,
            planned_km=use.planned_km,
            billing=use.billing,
            flat_price=use.flat_price,
            note=use.note,
        )
    return copies


def _copy_crew(
    source: Project,
    project: Project,
    shift: datetime.timedelta,
    rights: Rights,
    phases: dict[int, ProjectPhase],
    vehicles: dict[int, VehicleLine] | None = None,
) -> None:
    """The crew lines as open places; each keeps its phase – the copy of it (PRJ-080) – and its days (PER-029).

    LOG-008: a line keeps its vehicle and whether it drives, if the vehicle was copied as well.
    """
    vehicles = vehicles or {}
    for line in source.crew_lines.order_by("start", "position", "id"):
        start, end = shifted_period(line, source, project, shift)
        copy = CrewLine(
            project=project,
            job_function=line.job_function,
            person=None,
            start=start,
            end=end,
            phase=phases.get(line.phase_id) if line.phase_id else None,
            planned_hours=line.planned_hours,
            days=line.days,
            meeting_point=line.meeting_point,
            note=line.note,
            position=line.position,
            service_product=line.service_product,
            title=line.title,
            billing=line.billing,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate,
            discount_percent=line.discount_percent,
            list_price=line.list_price,
            # PER-035: the hour tiers agreed for the line; the rate from the limit goes with the person.
            hours_limit=line.hours_limit,
            unit_price_above_limit=line.unit_price_above_limit,
            # PER-009: the surcharges for night, Sunday and holidays as on the line.
            time_surcharges_on_price=line.time_surcharges_on_price,
            time_surcharges_on_cost=line.time_surcharges_on_cost,
            vehicle_line=vehicles.get(line.vehicle_line_id) if line.vehicle_line_id else None,
            is_driver=line.is_driver and line.vehicle_line_id in vehicles,
        )
        copy.full_clean()
        copy.save()
