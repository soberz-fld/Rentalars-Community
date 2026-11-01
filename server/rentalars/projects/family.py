# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole projects and their parts (PRJ-031, PRJ-044 to PRJ-049, PRJ-060).

A big production is planned as a *whole project* with *subprojects*: the
festival "Stadtfest 2027" with the stages "Marktplatz" and "Schlosspark".
There is exactly one level (PRJ-044). Every part is a project of its own –
number, name, venue, project manager, status, rental period, material lines
in groups, crew lines – and counts for availability like any other project
with its own period (PRJ-047).

What a part takes from its whole project (PRJ-045)
--------------------------------------------------
* Always: the customer and the billing address. They cannot be changed on
  the part; changing them on the whole project changes them on every part.
* As a preset: the contact, the delivery address, the venue, the project
  manager and the rental period. Each part can have its own.

The rental period of a part lies within that of the whole project. Moving the
whole period at once moves the parts along; shortening it is refused while a
part would stick out.

Material that moves on (PRJ-060)
--------------------------------
The same pieces can serve one stage after the other. A line of a later part
that names a line of an earlier part as ``taken_over_from`` takes over its
pieces: the availability counts them as one continuous reservation without
buffers in between, both packlists show them, and only the line they come
from is charged.

Who sees what (PRJ-049): see ``projects.access``.

This module answers the questions about the whole: the figures of every part
side by side with their sum (PRJ-046), and which shortages arise between the
parts (PRJ-047).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from rentalars.accounts.rights import Rights
from rentalars.availability.engine import AvailabilityEngine
from rentalars.projects.access import ProjectAccess, access_level
from rentalars.projects.models import MaterialLine, Project
from rentalars.projects.planning import PlannedLine, Planning, build_planning

ZERO = Decimal("0")


@dataclass
class PartFigures:
    """The figures of one part, or of the whole project's own lines (PRJ-046)."""

    project: Project
    #: True for the row of the lines kept on the whole project itself (central power, production office).
    is_whole: bool
    #: Material lines that are part of the total: no optional lines, no subrentals that only cover.
    lines: int = 0
    #: Their pieces – lines counted in pieces only.
    pieces: Decimal = ZERO
    crew_lines: int = 0
    #: Crew lines that still wait for a person (PRJ-020).
    open_places: int = 0
    #: Planned hours of the crew.
    hours: Decimal = ZERO
    net_total: Decimal = ZERO
    gross_total: Decimal = ZERO
    #: Missing pieces over all lines (PRJ-013).
    shortage: int = 0
    #: Lines taken over from another part (PRJ-060).
    takeovers: int = 0


@dataclass
class FamilyShortage:
    """A line that is short while other parts of the same whole project hold the product (PRJ-047)."""

    project: Project
    planned: PlannedLine
    missing: int
    #: Pieces other parts hold firmly at the busiest moment of the line.
    held_by_others: int


@dataclass
class Family:
    """A whole project with the figures of its parts, as far as the user may read them."""

    whole: Project
    parts: list[PartFigures] = field(default_factory=list)
    #: Parts the user may not read; they are left out of the figures and the sum.
    hidden: int = 0
    shortages: list[FamilyShortage] = field(default_factory=list)

    @property
    def total(self) -> PartFigures:
        """The sum of all parts shown (PRJ-046)."""
        total = PartFigures(project=self.whole, is_whole=True)
        for part in self.parts:
            for name in (
                "lines",
                "pieces",
                "crew_lines",
                "open_places",
                "hours",
                "net_total",
                "gross_total",
                "shortage",
                "takeovers",
            ):
                setattr(total, name, getattr(total, name) + getattr(part, name))
        return total

    @property
    def subprojects(self) -> list[PartFigures]:
        """The rows of the parts, without the whole project's own."""
        return [part for part in self.parts if not part.is_whole]


def whole_of(project: Project) -> Project:
    """The whole project: the parent of a subproject, else the project itself."""
    return project.parent if project.parent_id else project


def members(project: Project) -> list[Project]:
    """The whole project and its parts, in the order of their numbers."""
    whole = whole_of(project)
    parts = list(whole.subprojects.select_related("customer", "manager", "venue_site").order_by("number", "pk"))
    return [whole, *parts]


def has_parts(project: Project) -> bool:
    """Whether a project is a part, or has parts."""
    return bool(project.parent_id) or project.subprojects.exists()


def figures_of(planning: Planning, *, is_whole: bool) -> PartFigures:
    """Count what a planning holds (PRJ-046)."""
    figures = PartFigures(project=planning.project, is_whole=is_whole)
    for planned in planning.all_lines:
        line = planned.line
        if line.is_covering_subrental or line.is_surcharge or not line.counts_toward_total or line.is_text:
            continue  # Text lines; PRJ-128: a text line is no position of the material
        figures.lines += 1
        if line.product_id and (line.product.tracks_stock or line.product.is_kit):
            figures.pieces += line.quantity
        if line.taken_over_from_id:
            figures.takeovers += 1
        figures.shortage += planned.availability.shortage_total
    for crew in planning.prices.crew:
        figures.crew_lines += 1
        figures.hours += crew.planned_hours or ZERO
        if crew.line.is_vacant:
            figures.open_places += 1
    figures.net_total = planning.prices.net_total
    figures.gross_total = planning.prices.gross_total
    return figures


def build_family(project: Project, *, rights: Rights, user: Any) -> Family:
    """Put together the figures of a whole project and all its parts the user may read (PRJ-046, PRJ-047).

    One availability engine serves all parts, so reference data is loaded
    once. Each part costs the queries of one planning page.
    """
    engine = AvailabilityEngine()
    everything = members(project)
    family = Family(whole=everything[0])
    for member in everything:
        if access_level(rights, user, member) < ProjectAccess.READ:
            family.hidden += 1
            continue
        planning = build_planning(member, engine=engine)
        family.parts.append(figures_of(planning, is_whole=member.pk == family.whole.pk))
        for planned in planning.all_lines:
            for detail in planned.availability.details:
                if detail.shortage > 0 and detail.family > 0:
                    family.shortages.append(
                        FamilyShortage(
                            project=member, planned=planned, missing=detail.shortage, held_by_others=detail.family
                        )
                    )
    return family


def takeover_sources(project: Project) -> list[MaterialLine]:
    """Lines of the other parts of the same whole project that this project can take over from (PRJ-060).

    Lines with a product that has a stock of its own, that are no sale, that
    start before this project does, and of which not every piece is taken
    over already.
    """
    family = [pk for pk in project.family_ids() if pk != project.pk]
    if not family:
        return []
    candidates = (
        MaterialLine.objects.filter(project_id__in=family, product__isnull=False, is_sale=False)
        .filter(start__lt=project.start)
        .exclude(variant__gt="")
        .exclude(covers_line__isnull=False)
        .select_related("project", "product")
        .order_by("project__number", "position", "pk")
    )
    sources = []
    taken = _taken_quantities([line.pk for line in candidates])
    for line in candidates:
        if not (line.product.tracks_stock or line.product.is_kit):
            continue
        line.left_to_take_over = line.quantity - taken.get(line.pk, ZERO)
        if line.left_to_take_over > 0:
            sources.append(line)
    return sources


def _taken_quantities(line_ids: list[int]) -> dict[int, Decimal]:
    """How many pieces of each line other lines take over already."""
    from django.db.models import Sum

    if not line_ids:
        return {}
    return {
        row["taken_over_from_id"]: row["total"] or ZERO
        for row in MaterialLine.objects.filter(taken_over_from_id__in=line_ids)
        .order_by()
        .values("taken_over_from_id")
        .annotate(total=Sum("quantity"))
    }
