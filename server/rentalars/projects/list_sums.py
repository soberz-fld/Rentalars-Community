# SPDX-License-Identifier: GPL-3.0-or-later
"""Sums of the projects in the project list: hours, revenue, costs, profit (PRJ-085).

The project list (UIX-015) offers columns with the sums of each project. They
are not shown unless somebody chooses them in the column chooser, and they
come from the price calculation of the planning (``projects.pricing``) –
nothing is stored, nothing is calculated a second way.

==================  =========================================================
column              what it shows
==================  =========================================================
planned man-hours   the planned hours of all crew lines (PRJ-019)
material revenue    net total without the personnel and the logistics: groups,
                    lines without group, surcharges – also a surcharge on
                    the personnel
personnel revenue   what the customer pays for the crew (PRJ-051)
logistics revenue   what the customer pays for vehicles and trailers
                    (LOG-009)
total net           as on the planning (PRJ-034)
total gross         net plus the tax of every rate (PRJ-024)
material costs      what suppliers charge for subrentals (PRJ-025)
personnel costs     the planned cost of the crew (PRJ-021, PER-018)
logistics costs     the internal costs of the vehicles (LOG-010)
profit              "Gewinn aus dem Projekt": net minus all costs, the
                    contribution margin of the calculation (PRJ-025)
==================  =========================================================

Material, personnel and logistics revenue add up to the net total.

Whole projects (PRJ-046)
------------------------
A whole project shows the sum of itself and every part that is not
cancelled – as its price overview and its offer do: what the customer is
billed. Gross is taken as on those: the net amounts of all included projects
added up per tax rate, the tax calculated once on that (``family_prices``).
A part shows its own sums. Parts whose planning the user may not read are
left out of the whole project's sum, as on the price overview (PRJ-049).

Who sees what (AUT-019)
-----------------------
The columns follow the planning: revenue, net and gross need the price
right; material costs the price right and the right to see purchase prices;
personnel costs the right to see personnel costs; the profit all three,
because it would give a cost away. Planned hours need no special right. A
column the user may not see is neither offered nor exported. Values appear
only for projects whose planning the user may read; a project somebody
knows only through the deployment view (AUT-023) shows empty cells.

Queries (NFA-014)
-----------------
The sums are calculated only when one of the columns is shown, for the
projects of the page – or, for the CSV file, in chunks of its rows. All
projects of a page together need a fixed number of queries, however many
there are: which of them the user may read, their parts, their groups,
lines and crew lines, the rental scales, maximum discounts, surcharge
targets and approved times – each loaded once for all of them
(``pricing.PriceLookups``), and the settings of the surcharges for night,
Sunday and holidays (PER-009).

Sorting (UIX-015): sorting by one of the columns needs the sums of
every project of the list, not only of one page. They are calculated in
chunks of :data:`CHUNK` and the list sorted in Python – for at most
``core.tables.PYTHON_SORT_MAX_ROWS`` projects; a longer list keeps its order
and says so.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.apps import apps

from rentalars.accounts.rights import Level, Module, Rights
from rentalars.core.money import ZERO
from rentalars.products.models import ProductKind
from rentalars.projects.crew import ApprovedTimes, approved_times, surcharge_rules_for
from rentalars.projects.logistics import load_logistics_of
from rentalars.projects.models import CrewLine, Group, MaterialLine, Project, ProjectStatus, SurchargeTarget
from rentalars.projects.pricing import (
    PriceLookups,
    ProjectPrices,
    compute_project_prices,
    load_scale_tables,
    outdated_version_ids,
)

#: The keys of the columns of :data:`projects.tables.PROJECT_TABLE` that need the sums.
SUM_COLUMNS = frozenset(
    {
        "planned_hours",
        "material_revenue",
        "personnel_revenue",
        "logistics_revenue",
        "net_total",
        "gross_total",
        "material_cost",
        "personnel_cost",
        "logistics_cost",
        "profit",
    }
)

#: Projects whose sums are calculated together when a CSV file is written.
CHUNK = 200


@dataclass
class ListSums:
    """The sums of one row of the project list (PRJ-085); for a whole project with its parts."""

    planned_hours: Decimal = ZERO
    material_revenue: Decimal = ZERO
    personnel_revenue: Decimal = ZERO
    #: LOG-009: what the customer pays for vehicles and trailers.
    logistics_revenue: Decimal = ZERO
    net_total: Decimal = ZERO
    gross_total: Decimal = ZERO
    material_cost: Decimal = ZERO
    personnel_cost: Decimal = ZERO
    #: LOG-010: the internal costs of the vehicles.
    logistics_cost: Decimal = ZERO
    profit: Decimal = ZERO


def wanted(shown_keys: Iterable[str]) -> bool:
    """Whether one of the shown columns needs the sums."""
    return bool(SUM_COLUMNS & set(shown_keys))


def _readable_ids(rights: Rights, user: Any, ids: set[int]) -> set[int]:
    """The projects among ``ids`` whose planning the user may read (AUT-016, PRJ-049); one query at most."""
    from rentalars.projects.access import readable_projects

    if rights.level_everywhere(Module.PROJECTS) >= Level.READ:
        return set(ids)
    return set(readable_projects(rights, user, Project.objects.filter(pk__in=ids)).values_list("pk", flat=True))


def _approved_by_line(project_ids: set[int]) -> dict[int, ApprovedTimes]:
    """Approved hours and their cost per crew line, of many projects at once (ZEI-021).

    The same as ``crew.approved_hours_by_line`` does for one project – with
    the entries per day for the hour tiers (PER-035), still one query.
    """
    entry_model = apps.get_model("timetracking", "TimeEntry")
    return approved_times(
        entry_model.objects.filter(project_id__in=project_ids, status="approved", crew_line__isnull=False)
    )


def _approved_expenses(project_ids: set[int]) -> dict[int, Decimal]:
    """Approved expenses and travel costs per project, of many projects at once (ZEI-019)."""
    from rentalars.timetracking.expenses import approved_expense_sums

    return approved_expense_sums(project_ids)


def _prices_of(projects: list[Project]) -> dict[int, tuple[ProjectPrices, Decimal]]:
    """The price calculation and the planned hours of each project, with a fixed number of queries."""
    from rentalars.projects.discounts import maximum_discounts_of_products

    ids = {project.pk for project in projects}
    groups: dict[int, list[Group]] = defaultdict(list)
    for group in Group.objects.filter(project_id__in=ids):
        groups[group.project_id].append(group)
    lines: dict[int, list[MaterialLine]] = defaultdict(list)
    for line in MaterialLine.objects.filter(project_id__in=ids).select_related(
        "product", "product__category", "tax_rate", "unit", "supplier"
    ):
        lines[line.project_id].append(line)
    crew: dict[int, list[CrewLine]] = defaultdict(list)
    for crew_line in (
        CrewLine.objects.filter(project_id__in=ids)
        .select_related("job_function", "person", "service_product", "tax_rate")
        .order_by("start", "position", "id")
    ):
        crew[crew_line.project_id].append(crew_line)

    # LOG-009: the vehicle bookings and their trips of all projects, two queries.
    logistics = load_logistics_of(ids)

    every_line = [line for project_lines in lines.values() for line in project_lines]
    version_ids = {line.scale_version_id for line in every_line if line.scale_version_id}
    version_ids |= {
        line.scale_version_id for found in logistics.values() for line in found.lines if line.scale_version_id
    }
    targets: dict[int, list[SurchargeTarget]] = defaultdict(list)
    percent_surcharges = [line.pk for line in every_line if line.is_percent_surcharge]
    if percent_surcharges:
        for target in SurchargeTarget.objects.filter(surcharge_line_id__in=percent_surcharges).select_related(
            "target_line", "target_group"
        ):
            targets[target.surcharge_line_id].append(target)
    lookups = PriceLookups(
        tables=load_scale_tables(version_ids),
        outdated=outdated_version_ids(version_ids),
        maximum_discounts=maximum_discounts_of_products(
            line.product_id for line in every_line if line.product_id and line.product.kind == ProductKind.SERVICE
        ),
        targets_by_line=targets,
        approved=_approved_by_line({pk for pk in ids if crew.get(pk)}) if crew else {},
        # PER-009: the settings of the surcharges, read once for all projects – if a crew line needs them.
        time_surcharges=surcharge_rules_for(line for lines_of in crew.values() for line in lines_of),
        # ZEI-019: the approved expenses of all projects, one query; the profit subtracts them.
        expenses=_approved_expenses(ids),
        logistics=logistics,
    )
    result = {}
    for project in projects:
        project_crew = crew.get(project.pk, [])
        prices = compute_project_prices(
            project,
            lines=lines.get(project.pk, []),
            groups=groups.get(project.pk, []),
            crew=project_crew,
            lookups=lookups,
        )
        result[project.pk] = (prices, sum((line.planned_hours for line in project_crew), ZERO))
    return result


def attach_sums(projects: list[Project], *, rights: Rights, user: Any) -> None:
    """Note the sums on each project as ``list_sums``: a :class:`ListSums`, or ``None`` (PRJ-085).

    ``None`` for a project whose planning the user may not read. Uses
    ``part_count`` (the number of parts) where the list annotated it, so
    that projects without parts ask for none.
    """
    from rentalars.projects.family_prices import sum_prices

    for project in projects:
        project.list_sums = None
    if not projects:
        return
    wholes = [project.pk for project in projects if not project.parent_id and getattr(project, "part_count", 1)]
    parts: dict[int, list[Project]] = defaultdict(list)
    if wholes:
        for part in (
            Project.objects.filter(parent_id__in=wholes)
            .exclude(status=ProjectStatus.CANCELLED)
            .order_by("number", "pk")
        ):
            parts[part.parent_id].append(part)
    rows = {project.pk: project for project in projects}
    every = {**{part.pk: part for members in parts.values() for part in members}, **rows}
    readable = _readable_ids(rights, user, set(every))
    calculated = _prices_of([project for pk, project in every.items() if pk in readable])
    for project in projects:
        if project.pk not in readable:
            continue
        members = [project.pk] + [part.pk for part in parts.get(project.pk, []) if part.pk in readable]
        all_prices = [calculated[pk][0] for pk in members]
        net = sum((prices.net_total for prices in all_prices), ZERO)
        personnel = sum((prices.personnel_total for prices in all_prices), ZERO)
        logistics_revenue = sum((prices.logistics_total for prices in all_prices), ZERO)
        project.list_sums = ListSums(
            planned_hours=sum((calculated[pk][1] for pk in members), ZERO),
            material_revenue=net - personnel - logistics_revenue,
            personnel_revenue=personnel,
            logistics_revenue=logistics_revenue,
            net_total=net,
            # One project alone: exactly its own gross total.
            gross_total=sum_prices(all_prices).gross_total,
            material_cost=sum((prices.subrental_cost for prices in all_prices), ZERO),
            personnel_cost=sum((prices.personnel_cost for prices in all_prices), ZERO),
            logistics_cost=sum((prices.logistics_cost for prices in all_prices), ZERO),
            profit=sum((prices.contribution_margin for prices in all_prices), ZERO),
        )


def with_sums(projects: Iterable[Project], *, rights: Rights, user: Any) -> Iterator[Project]:
    """The projects of a CSV file, their sums calculated a chunk at a time (PRJ-085, IMP-005)."""
    remaining = iter(projects)
    while chunk := list(itertools.islice(remaining, CHUNK)):
        attach_sums(chunk, rights=rights, user=user)
        yield from chunk
