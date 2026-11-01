# SPDX-License-Identifier: GPL-3.0-or-later
"""Timelines of a single product, material model, item or person (VFG-019, PER-020).

The planning section shows many products or people side by side. These
timelines show one of them in detail, on its own page – "when is this free,
who has it, what blocks it":

* **Product**: per day how many pieces are free, and below one bar per
  project with the quantity it takes; blocked items as bars of their own.
* **Material model**: the same for the product(s) its items belong to, and
  one row per item.
* **Item**: when it was or is out with which project, when it is wished for
  on a line, when it travels with its container, when it is blocked or
  taken out of its case for a project, when its next inspection is due.
* **Person**: deployments and absences, and when a qualification expires.

Everything is read from the same sources as the rest of the application;
nothing here is stored. Projects the reader may not open appear with their
number only, without a link (AUT-016).
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.availability.engine import Firmness
from rentalars.availability.services import DayLoad, utilization, utilization_with_demands
from rentalars.projects.models import FINISHED_STATUSES, MaterialLine, ProjectStatus
from rentalars.schedule.services import Bar, bar_for, bounds, crew_bar_css


@dataclass
class TimelineRow:
    """One row of a timeline: bars over the days, or a number per day."""

    label: str
    sublabel: str = ""
    url: str = ""
    bars: list[Bar] = field(default_factory=list)
    loads: list[DayLoad] | None = None
    css: str = ""

    @property
    def is_empty(self) -> bool:
        """Whether nothing happens in this row within the span."""
        return not self.bars and not self.loads


@dataclass
class Timeline:
    """Everything one timeline section shows."""

    days: list[datetime.date]
    rows: list[TimelineRow]
    note: str = ""

    @property
    def has_bars(self) -> bool:
        """Whether any row has something in the span."""
        return any(not row.is_empty for row in self.rows)


def _project_label(number: str, name: str, visible: bool) -> str:
    return f"{number} {name}" if visible else number


@dataclass(frozen=True)
class _FamilyLine:
    """What a timeline says about a line of a part (PRJ-044, PRJ-060)."""

    #: "part of 2026-0042 Stadtfest", or empty for a line of a whole project.
    part_of: str
    #: The number of the part whose pieces the line takes over, and from when they come.
    taken_over_from: str
    received_from: datetime.datetime | None


def _family_lines(demands: list[Any]) -> dict[int, _FamilyLine]:
    """The lines among the demands that belong to parts or take pieces over (PRJ-044, PRJ-060).

    One query, and only if a part is among the demands at all: a demand
    whose whole project is not its own project belongs to a part.
    """
    if not any(demand.root_project_id not in (None, demand.project_id) for demand in demands):
        return {}
    line_ids = {demand.line_id for demand in demands if demand.line_id}
    rows = (
        MaterialLine.objects.filter(pk__in=line_ids)
        .filter(Q(project__parent__isnull=False) | Q(taken_over_from__isnull=False))
        .values_list(
            "pk",
            "start",
            "project__parent__number",
            "project__parent__name",
            "taken_over_from__project__number",
            "taken_over_from__end",
        )
    )
    result = {}
    for pk, start, whole_number, whole_name, source_number, source_end in rows:
        result[pk] = _FamilyLine(
            part_of=_("part of %(number)s %(name)s") % {"number": whole_number, "name": whole_name}
            if whole_number
            else "",
            taken_over_from=source_number or "",
            received_from=min(source_end, start) if source_end else None,
        )
    return result


def _demand_bars(
    demands: list[Any], days: list[datetime.date], visible_ids: set[int], *, quantity_prefix: bool = True
) -> list[TimelineRow]:
    """One row per project (and one for blocked items) from the demands of a product.

    A part of a whole project says whose part it is; pieces taken over from
    another part (PRJ-060) are a bar of their own that begins where the
    line they come from ends – they go straight from one stage to the next.
    """
    family = _family_lines(demands)
    by_project: dict[Any, list[Any]] = defaultdict(list)
    for demand in demands:
        key = ("blocked", demand.project_number) if demand.via == "blocked" else demand.project_id
        by_project[key].append(demand)
    rows: list[TimelineRow] = []
    for _key, entries in sorted(by_project.items(), key=lambda pair: min(d.start for d in pair[1])):
        first = entries[0]
        if first.via == "blocked":
            row = TimelineRow(label=_("%(id)s blocked") % {"id": first.project_number}, css="blocked")
            for demand in entries:
                bar = bar_for(demand.start, demand.end, days, label=demand.project_name, css="blocked")
                if bar is not None:
                    row.bars.append(bar)
            rows.append(row)
            continue
        visible = first.project_id in visible_ids
        row = TimelineRow(
            label=_project_label(first.project_number, first.project_name, visible),
            sublabel=family[first.line_id].part_of if visible and first.line_id in family else "",
            url=reverse("projects:overview", args=[first.project_id]) if visible else "",
        )
        for demand in entries:
            via = {"kit": _("in a kit"), "container": _("inside a container")}.get(demand.via, "")
            label = f"{demand.quantity}×" if quantity_prefix else ""
            if via:
                label = f"{label} {via}".strip()
            css = "status-confirmed" if demand.firmness == Firmness.FIRM else "status-option"
            title = row.label
            line = family.get(demand.line_id)
            if line is not None and line.taken_over_from and demand.start == line.received_from:
                # PRJ-060: straight from the other part, not from the warehouse.
                css += " takeover"
                label = f"{label} {_('taken over')}".strip()
                title = _("%(project)s – taken over from %(number)s") % {
                    "project": row.label,
                    "number": line.taken_over_from,
                }
            bar = bar_for(demand.start, demand.end, days, label=label, css=css, url=row.url, title=title)
            if bar is not None:
                row.bars.append(bar)
        if row.bars:
            rows.append(row)
    return rows


def product_timeline(product: Any, days: list[datetime.date], visible_ids: set[int]) -> Timeline:
    """Free pieces per day and who takes how many (VFG-019).

    Args:
        product: A product with own stock (rental or sale product).
        days: The days to show.
        visible_ids: Projects the reader may open; others show their number only.
    """
    if not product.tracks_stock:
        return Timeline(days=days, rows=[], note=_("This product has no stock of its own."))
    all_loads, all_demands = utilization_with_demands([product.pk], days)
    loads = all_loads.get(product.pk, [])
    rows = [
        TimelineRow(
            label=_("free"),
            sublabel=_("of %(stock)d") % {"stock": loads[0].stock} if loads else "",
            loads=loads,
            css="free",
        )
    ]
    rows += _demand_bars(all_demands.get(product.pk, []), days, visible_ids)
    return Timeline(days=days, rows=rows)


def model_timeline(model: Any, days: list[datetime.date], visible_ids: set[int], *, max_items: int = 40) -> Timeline:
    """The product(s) of a model and one row per item (VFG-019)."""
    from rentalars.material.models import ARCHIVED_STATUSES, MaterialItem
    from rentalars.products.models import Product

    items = list(
        MaterialItem.objects.filter(material_model=model)
        .exclude(status__in=ARCHIVED_STATUSES)
        .select_related(
            "material_model__category", "installed_in", "product_override", "material_model__default_product"
        )
        .order_by("inventory_number")[: max_items + 1]
    )
    product_ids = {item.product.pk for item in items if item.product is not None}
    if model.default_product_id:
        product_ids.add(model.default_product_id)
    rows: list[TimelineRow] = []
    loads = utilization(sorted(product_ids), days)
    for product in Product.objects.filter(pk__in=product_ids).order_by("article_number"):
        if product.pk in loads:
            rows.append(
                TimelineRow(
                    label=_("free: %(product)s") % {"product": product.article_number},
                    sublabel=_("of %(stock)d") % {"stock": loads[product.pk][0].stock},
                    url=reverse("products:detail", args=[product]),
                    loads=loads[product.pk],
                    css="free",
                )
            )
    note = ""
    if len(items) > max_items:
        items = items[:max_items]
        note = _("Only the first %(count)d items are shown.") % {"count": max_items}
    if not model.is_bulk:
        for item, bars in item_bars(items, days, visible_ids).items():
            rows.append(
                TimelineRow(
                    label=item.display_id,
                    sublabel=item.get_status_display() if not item.is_operational else "",
                    url=reverse("material:item_detail", args=[item.pk]),
                    bars=bars,
                    css="item",
                )
            )
    return Timeline(days=days, rows=rows, note=note)


def item_timeline(item: Any, days: list[datetime.date], visible_ids: set[int], plan: Any = None) -> Timeline:
    """Everything that happens to one item, and how free its product is (VFG-019)."""
    rows: list[TimelineRow] = []
    bars = item_bars([item], days, visible_ids, plan).get(item, [])
    kinds = [
        ("deployment", _("deployments")),
        ("wish", _("wished for")),
        ("container", _("with its container")),
        ("extracted", _("taken out of its container")),
        ("blocked", _("blocked")),
        ("inspection", _("inspection due")),
    ]
    for kind, label in kinds:
        own = [bar for bar in bars if kind in bar.css.split()]
        if own:
            rows.append(TimelineRow(label=label, bars=own, css=kind))
    product = item.product
    if product is not None and product.tracks_stock and not item.travels_only_with_container:
        all_loads, all_demands = utilization_with_demands([product.pk], days)
        loads = all_loads.get(product.pk)
        if loads:
            rows.append(
                TimelineRow(
                    label=_("free: %(product)s") % {"product": product.article_number},
                    sublabel=_("of %(stock)d") % {"stock": loads[0].stock},
                    url=reverse("products:detail", args=[product]),
                    loads=loads,
                    css="free",
                )
            )
            # Who needs the product: any free piece may go, this one among them.
            demands = [
                demand
                for demand in all_demands.get(product.pk, [])
                # (pieces per product; PRD-052): the blocks of a product of several pieces are joined in
                # one number field, "0003, 0004".
                if not (
                    demand.via == "blocked"
                    and item.display_id in {part.strip() for part in demand.project_number.split(",")}
                )
            ]
            rows += _demand_bars(demands, days, visible_ids)
    note = ""
    if item.travels_only_with_container:
        note = _("This item is permanently installed and travels with its container; it is never planned on its own.")
    return Timeline(days=days, rows=rows, note=note)


@dataclass(frozen=True)
class ItemEvent:
    """Something that happens to an item: in its timeline and its calendar link (VFG-019; VFG-040).

    ``kind`` is ``deployment`` (out with a project, or ``issued=False``: chosen
    for its packing list), ``wish``, ``container`` (travelling with the
    container ``container`` it is installed in), ``extracted``, ``blocked``
    or ``inspection``. ``key`` names the record behind it and stays the same
    while the record changes – the calendar link builds its stable UIDs from
    it. An inspection has no period of its own: ``start`` and ``end`` are
    ``None`` and ``due`` says when it is due; who shows it decides where an
    overdue one goes.
    """

    item_id: int
    kind: str
    key: str
    start: datetime.datetime | None = None
    end: datetime.datetime | None = None
    project: Any = None
    issued: bool = False
    container: str = ""
    reason: str = ""
    due: Any = None


def item_events(
    items: list[Any], start: datetime.datetime, end: datetime.datetime, plan: Any = None
) -> dict[int, list[ItemEvent]]:
    """What happens to each item between ``start`` and ``end``, by item ID (VFG-019; VFG-040).

    The data of :func:`item_bars` – deployments, wishes, container trips,
    extractions, blocks – with their exact periods, and the inspections
    that apply with their due dates. A fixed number of queries, however
    many items and events. ``plan`` is the
    :class:`~rentalars.material.inspections.InspectionPlan` of the request,
    if there is one already.
    """
    from rentalars.material.inspections import InspectionPlan
    from rentalars.material.models import ItemBlock
    from rentalars.packing.models import Allocation, Extraction

    result: dict[int, list[ItemEvent]] = {item.pk: [] for item in items}
    if not items:
        return result
    now = timezone.now()

    def add(event: ItemEvent) -> None:
        if event.start is not None and event.end is not None and (event.start >= end or event.end <= start):
            return
        result[event.item_id].append(event)

    # Out with a project, or chosen for one (PCK-021, PCK-022).
    allocations = (
        Allocation.objects.filter(item_id__in=result)
        .filter(Q(returned_at__isnull=True) | Q(returned_at__gt=start))
        .select_related("entry__packlist__project__parent")
    )
    for allocation in allocations:
        project = allocation.entry.packlist.project
        add(
            ItemEvent(
                item_id=allocation.item_id,
                kind="deployment",
                key=f"allocation-{allocation.pk}",
                start=allocation.issued_at or project.start,
                end=allocation.returned_at or max(project.end, now if allocation.issued_at else project.end),
                project=project,
                issued=allocation.issued_at is not None,
            )
        )

    # Wished for on a line (PRJ-064): the planner wants this very item.
    for line in (
        MaterialLine.objects.filter(preferred_item_id__in=result, start__lt=end, end__gt=start)
        .exclude(project__status__in=FINISHED_STATUSES)
        .select_related("project__parent")
    ):
        add(
            ItemEvent(
                item_id=line.preferred_item_id,
                kind="wish",
                key=f"wish-{line.pk}",
                start=line.start,
                end=line.end,
                project=line.project,
            )
        )

    # Piece share: a line can wish for several items, each covers one piece of it.
    for link in (
        MaterialLine.further_preferred_items.through.objects.filter(
            materialitem_id__in=result,
            materialline__start__lt=end,
            materialline__end__gt=start,
            materialline__preferred_item__isnull=False,  # (R3-1) further pins count with a first one
        )
        .exclude(materialline__project__status__in=FINISHED_STATUSES)
        .select_related("materialline__project__parent")
    ):
        wishing = link.materialline
        add(
            ItemEvent(
                item_id=link.materialitem_id,
                kind="wish",
                key=f"wish-{wishing.pk}-{link.materialitem_id}",
                start=wishing.start,
                end=wishing.end,
                project=wishing.project,
            )
        )

    # Travelling with the container it is installed in (MAT-036, MAT-037).
    container_of = {item.pk: item.installed_in_id for item in items if item.installed_in_id}
    if container_of:
        for allocation in (
            Allocation.objects.filter(item_id__in=set(container_of.values()), issued_at__isnull=False)
            .filter(Q(returned_at__isnull=True) | Q(returned_at__gt=start))
            .select_related("entry__packlist__project__parent", "item")
        ):
            project = allocation.entry.packlist.project
            for item_id, container_id in container_of.items():
                if container_id == allocation.item_id:
                    add(
                        ItemEvent(
                            item_id=item_id,
                            kind="container",
                            key=f"container-{allocation.pk}",
                            start=allocation.issued_at,
                            end=allocation.returned_at or max(project.end, now),
                            project=project,
                            container=allocation.item.display_id,
                        )
                    )

    # Taken out of its container for a project (MAT-042).
    for extraction in Extraction.objects.filter(item_id__in=result).select_related("project__parent"):
        project = extraction.project
        add(
            ItemEvent(
                item_id=extraction.item_id,
                kind="extracted",
                key=f"extraction-{extraction.pk}",
                start=project.start,
                end=project.end,
                project=project,
            )
        )

    # Blocked (MAT-024).
    for block in ItemBlock.objects.filter(item_id__in=result, start__lt=end, end__gt=start):
        add(
            ItemEvent(
                item_id=block.item_id,
                kind="blocked",
                key=f"block-{block.pk}",
                start=block.start,
                end=block.end,
                reason=block.reason,
            )
        )

    # The inspections that apply, with their due dates (MAT-031).
    plan = plan or InspectionPlan()
    if not plan.is_empty:
        for item_id, dues in plan.dues_for(items).items():
            for due in dues:
                add(ItemEvent(item_id=item_id, kind="inspection", key=f"inspection-{due.inspection_type.pk}", due=due))
    return result


def _item_event_bar(event: ItemEvent, days: list[datetime.date], visible_ids: set[int]) -> Bar | None:
    """The bar of one event of an item within the shown days (VFG-019)."""
    if event.kind == "inspection":
        # MAT-031: a one-day marker on the due date, or on the first day if overdue.
        due = event.due
        day = due.due_date or days[0]
        day = max(day, days[0]) if due.state == "overdue" else day
        moment = datetime.datetime.combine(day, datetime.time(12), tzinfo=timezone.get_current_timezone())
        return bar_for(
            moment,
            moment + datetime.timedelta(hours=1),
            days,
            label=due.inspection_type.name,
            css=f"inspection marker is-{due.state}",
            title=due.state_label,
        )
    if event.start is None or event.end is None:
        return None
    if event.kind == "blocked":
        return bar_for(event.start, event.end, days, label=event.reason, css="blocked")
    project = event.project
    visible = project.pk in visible_ids
    label = _project_label(project.number, project.name, visible)
    url = reverse("projects:overview", args=[project]) if visible else ""
    if event.kind == "deployment":
        return bar_for(
            event.start,
            event.end,
            days,
            label=label,
            css="deployment status-out" if event.issued else "deployment status-confirmed chosen",
            url=url,
            title="" if event.issued else _("chosen for the packing list"),
        )
    if event.kind == "wish":
        return bar_for(
            event.start,
            event.end,
            days,
            label=label,
            css="wish status-option" if project.status == ProjectStatus.OPTION else "wish status-confirmed",
            url=url,
            title=_("wished for on a line"),
        )
    if event.kind == "container":
        return bar_for(
            event.start,
            event.end,
            days,
            label=_("in %(id)s: %(project)s") % {"id": event.container, "project": label},
            css="container status-out",
            url=url,
        )
    return bar_for(
        event.start,
        event.end,
        days,
        label=_("not in its case for %(project)s") % {"project": label},
        css="extracted",
        url=url,
    )


def item_bars(
    items: list[Any], days: list[datetime.date], visible_ids: set[int], plan: Any = None
) -> dict[Any, list[Bar]]:
    """The bars of each item: deployments, wishes, container trips, extractions, blocks, inspections.

    ``plan`` is the :class:`~rentalars.material.inspections.InspectionPlan` of
    the request, if the page has one already. The data comes from
    :func:`item_events` – the calendar link of an item reads the same
    (VFG-040).
    """
    if not items:
        return {}
    start, end = bounds(days)
    by_id = {item.pk: item for item in items}
    result: dict[Any, list[Bar]] = {item: [] for item in items}
    for item_id, events in item_events(items, start, end, plan).items():
        for event in events:
            bar = _item_event_bar(event, days, visible_ids)
            if bar is not None:
                result[by_id[item_id]].append(bar)
    for bars in result.values():
        bars.sort(key=lambda bar: bar.first)
    return result


def person_timeline(person: Any, days: list[datetime.date], visible_ids: set[int]) -> Timeline:
    """Deployments, availability and expiring qualifications of one person (PER-020).

    A deployment in a project the reader may not open shows as "planned"
    with the job function only (AUT-016).

    The row "availability" shows what the personnel plan shows on top of a
    person (VFG-023): the availability that counts (PER-027) – own entries
    green, yellow, red, the busy times of the linked calendars as blocks –
    and the absences.

    VFG-032: as in the personnel plan, every bar names its exact
    times in its title, and a deployment that overlaps another one, an
    absence or a "not available" is marked ``is-conflict`` (filled red).
    """
    from rentalars.personnel.marks import effective_periods
    from rentalars.personnel.models import Absence, AvailabilityState
    from rentalars.projects.models import CrewLine
    from rentalars.schedule.services import exact_period, find_warnings, overlapping

    start, end = bounds(days)
    lines = list(
        overlapping(CrewLine.objects.filter(person=person), start, end)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .select_related("project", "job_function")
        .order_by("start")
    )
    periods = effective_periods([person.pk], start, end).get(person.pk, [])
    absences = list(overlapping(Absence.objects.filter(person=person), start, end).order_by("start"))
    _warnings, involved = find_warnings(
        lines, absences, [period for period in periods if period.state == AvailabilityState.UNAVAILABLE]
    )

    def joined(*parts: str) -> str:
        return " · ".join(part for part in parts if part)

    deployments = TimelineRow(label=_("deployments"))
    for line in lines:
        project = line.project
        visible = project.pk in visible_ids
        conflict = id(line) in involved
        bar = bar_for(
            line.start,
            line.end,
            days,
            label=f"{_project_label(project.number, project.name, visible)} · {line.job_function.name}",
            # VFG-027: the colours of the personnel plan; VFG-032: a conflict filled red – class and hover
            # from the one flag.
            css=crew_bar_css(line),
            title=joined(
                exact_period(line.start, line.end),
                _("requested, not yet answered") if line.request_status == "requested" else "",
            ),
            conflict=conflict,
            url=reverse("projects:overview", args=[project]) if visible else "",
        )
        if bar is not None:
            deployments.bars.append(bar)
    availability = TimelineRow(label=_("availability"), css="availability")
    states = dict(AvailabilityState.choices)
    for period in periods:
        title = joined(
            exact_period(period.start, period.end),
            period.note,
            _("from the linked calendar") if period.from_feed else "",
        )
        bar = bar_for(
            period.start,
            period.end,
            days,
            label=str(states.get(period.state, period.state)),
            css=f"availability is-{period.state}" + (" from-feed" if period.from_feed else ""),
            title=title,
        )
        if bar is not None:
            availability.bars.append(bar)
    for absence in absences:
        bar = bar_for(
            absence.start,
            absence.end,
            days,
            label=absence.get_kind_display(),
            css="absence",
            title=joined(exact_period(absence.start, absence.end), absence.note),
        )
        if bar is not None:
            availability.bars.append(bar)
    availability.bars.sort(key=lambda bar: bar.first)
    rows = [deployments, availability]
    expiring = _qualification_markers(person, days)
    if expiring:
        rows.append(TimelineRow(label=_("qualifications"), bars=expiring, css="qualification"))
    return Timeline(days=days, rows=rows)


def _qualification_markers(person: Any, days: list[datetime.date]) -> list[Bar]:
    """A marker on the day a qualification of the person expires (PER-014)."""
    from rentalars.personnel.models import Qualification

    zone = timezone.get_current_timezone()
    markers = []
    for qualification in Qualification.objects.filter(
        person=person, valid_until__gte=days[0], valid_until__lte=days[-1]
    ).select_related("qualification_type"):
        moment = datetime.datetime.combine(qualification.valid_until, datetime.time(12), tzinfo=zone)
        bar = bar_for(
            moment,
            moment + datetime.timedelta(hours=1),
            days,
            label=_("%(name)s expires") % {"name": qualification.qualification_type.name},
            css=f"marker is-{'overdue' if qualification.state == 'expired' else 'soon'}",
        )
        if bar is not None:
            markers.append(bar)
    return markers


def timeline_document(timeline: Any) -> dict[str, Any]:
    """A timeline as JSON: the days and the rows with their bars or numbers."""
    days = timeline.days
    return {
        "days": days,
        "note": timeline.note,
        "rows": [
            {
                "label": row.label,
                "sublabel": row.sublabel,
                "kind": row.css,
                "bars": [
                    {
                        "from": days[bar.first - 1],
                        "until": days[bar.last - 1],
                        "label": bar.label,
                        "kind": bar.css,
                        "url": bar.url,
                    }
                    for bar in row.bars
                ],
                "free": [
                    {"day": load.day, "free": load.free, "options": load.optional, "stock": load.stock}
                    for load in row.loads or []
                ],
            }
            for row in timeline.rows
        ],
    }
