# SPDX-License-Identifier: GPL-3.0-or-later
"""The prices of a whole project with its subprojects (PRJ-045, PRJ-046, PRJ-060).

The price overview (PRJ-035, PRJ-036, DOK-009) and the priced documents –
offer, order confirmation, invoice (DOK-003, DOK-006, DOK-010) – show a
whole project with its parts in the same way, and both take it from here.

Billing happens at the whole project
------------------------------------
Customer and billing data are the whole project's (PRJ-045), so the customer
gets one offer, one order confirmation and one invoice for everything: the
whole project's own lines (the shared ones – central power supply, production
office, PRJ-046) first, then every part in the order of its number, each as a
block of its own with its subtotal. A part on its own is never billed.

* **Cancelled parts** are left out: nothing of them is offered or charged.
* **Every project keeps its own calculation.** Groups, discounts, flat
  prices and percentage surcharges work inside the project they belong to,
  exactly as on its planning page – a surcharge "on the whole project" of the
  whole project refers to the whole project's own lines.
* **The sum of everything** adds the net amounts of the projects per tax
  rate; the tax is calculated once per rate on that sum, as on any invoice
  (and as the electronic invoice demands, EN 16931 BR-CO-17). Net, tax and
  gross therefore always fit together; the gross sum can differ by a cent
  from adding up the gross totals of the parts one by one.
* **Material taken over** from another part (PRJ-060) is charged once, on
  the line it comes from (``projects.pricing``); the taking line costs
  nothing.

Who sees what: the price overview leaves out the parts a user may not read
(PRJ-049) and says how many; a priced document always contains every part
that is not cancelled (see ``documents.services``).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.availability.engine import AvailabilityEngine
from rentalars.core.i18n import local_pattern
from rentalars.core.money import HUNDRED, ZERO, money
from rentalars.masterdata.models import TaxRate
from rentalars.projects.models import Project, ProjectStatus
from rentalars.projects.planning import Planning, build_planning
from rentalars.projects.pricing import ProjectPrices, TaxLine


def period_label(project: Project) -> str:
    """The rental period in short: "10.03.–12.03.2027", or with both years if they differ."""
    start, end = timezone.localtime(project.start).date(), timezone.localtime(project.end).date()
    if start == end:
        return f"{start:{local_pattern('%d.%m.%Y')}}"
    if start.year == end.year:
        return f"{start:{local_pattern('%d.%m.')}}–{end:{local_pattern('%d.%m.%Y')}}"
    return f"{start:{local_pattern('%d.%m.%Y')}}–{end:{local_pattern('%d.%m.%Y')}}"


def part_title(project: Project) -> str:
    """How a part is named on paper, e.g. "Subproject 2026-0042-1 Bühne Marktplatz" (PRJ-046)."""
    return _("Subproject %(number)s %(name)s") % {"number": project.number, "name": project.name}


def part_heading(project: Project) -> str:
    """The heading of a part's block: number, name and rental period (PRJ-046)."""
    return f"{part_title(project)}, {period_label(project)}"


@dataclass
class PriceBlock:
    """One project of the family with its planning: the whole project's own lines, or one part."""

    project: Project
    planning: Planning
    #: True for the lines kept on the whole project itself (PRJ-046).
    is_whole: bool

    @property
    def prices(self) -> ProjectPrices:
        """The project's own price calculation."""
        return self.planning.prices

    @property
    def title(self) -> str:
        """The name of the part on paper, e.g. "Subproject 2026-0042-1 Bühne Marktplatz"."""
        return part_title(self.project)

    @property
    def heading(self) -> str:
        """The heading of the part's block, e.g. "Subproject 2026-0042-1 Bühne Marktplatz, 10.03.–12.03.2027"."""
        return part_heading(self.project)

    @property
    def shared_heading(self) -> str:
        """The heading of a whole project's own lines next to its parts (PRJ-046)."""
        return _("Shared lines of the whole project %(number)s") % {"number": self.project.number}

    @property
    def period(self) -> str:
        """The rental period in short."""
        return period_label(self.project)

    @property
    def is_empty(self) -> bool:
        """Whether the project has nothing to show: no lines, no crew, no vehicles (LOG-009)."""
        planning = self.planning
        prices = planning.prices
        return not (planning.groups or planning.ungrouped or planning.surcharges or prices.crew or prices.logistics)


@dataclass
class FamilyTotals:
    """The sum of several projects (PRJ-046): net per tax rate added up, the tax calculated on that sum."""

    net_total: Decimal = ZERO
    tax_lines: list[TaxLine] = field(default_factory=list)
    tax_total: Decimal = ZERO
    gross_total: Decimal = ZERO
    optional_total: Decimal = ZERO
    optional_lines_total: Decimal = ZERO
    alternative_lines_total: Decimal = ZERO
    has_estimates: bool = False


@dataclass
class FamilyPrices:
    """A project with the parts that belong into its prices (PRJ-046).

    For a whole project with parts: its own lines and every part that is not
    cancelled (and that the user may read, if asked for a user). For a
    project without parts, and for a part, just the project.
    """

    project: Project
    blocks: list[PriceBlock]
    totals: FamilyTotals
    #: Parts left out because the user may not read their planning (PRJ-049).
    hidden: int = 0
    #: Parts left out because they are cancelled.
    cancelled: list[Project] = field(default_factory=list)

    @property
    def own(self) -> PriceBlock:
        """The block of the project asked for."""
        return self.blocks[0]

    @property
    def parts(self) -> list[PriceBlock]:
        """The blocks of the parts, in the order of their numbers."""
        return self.blocks[1:]

    @property
    def has_parts(self) -> bool:
        """Whether parts are shown with the project: a whole project with at least one part included."""
        return bool(self.parts)

    @property
    def is_part(self) -> bool:
        """Whether the project asked for is a part of a whole project."""
        return self.project.parent_id is not None

    @property
    def projects(self) -> list[Project]:
        """Every project included, the project asked for first."""
        return [block.project for block in self.blocks]

    @property
    def has_crew(self) -> bool:
        """Whether any included project has crew lines – then the personnel can be broken down (PRJ-088)."""
        return any(block.prices.crew for block in self.blocks)


def sum_prices(all_prices: list[ProjectPrices]) -> FamilyTotals:
    """Add up the sums of several projects (PRJ-046).

    The net amounts are added per tax rate, and the tax is calculated on
    each such sum – once, as for any invoice (EN 16931 BR-CO-17). For one
    project alone this gives exactly its own sums.
    """
    nets: dict[int, Decimal] = defaultdict(lambda: ZERO)
    rates: dict[int, TaxRate] = {}
    totals = FamilyTotals()
    for prices in all_prices:
        for tax_line in prices.tax_lines:
            rates[tax_line.tax_rate.pk] = tax_line.tax_rate
            nets[tax_line.tax_rate.pk] += tax_line.net
        totals.net_total += prices.net_total
        totals.optional_total += prices.optional_total
        totals.optional_lines_total += prices.optional_lines_total
        totals.alternative_lines_total += prices.alternative_lines_total
        totals.has_estimates = totals.has_estimates or prices.has_estimates
    totals.tax_lines = sorted(
        (TaxLine(tax_rate=rates[pk], net=net, tax=money(net * rates[pk].rate / HUNDRED)) for pk, net in nets.items()),
        key=lambda tax_line: -tax_line.tax_rate.rate,
    )
    totals.tax_total = sum((tax_line.tax for tax_line in totals.tax_lines), ZERO)
    totals.gross_total = totals.net_total + totals.tax_total
    return totals


def billed_parts(project: Project) -> tuple[list[Project], list[Project]]:
    """The parts of a whole project that belong into its prices, and the cancelled ones left out (PRJ-046).

    A part, or a project without parts, has none.
    """
    if project.parent_id:
        return [], []
    parts = list(
        project.subprojects.select_related("customer", "manager", "venue_site", "parent").order_by("number", "pk")
    )
    cancelled = [part for part in parts if part.status == ProjectStatus.CANCELLED]
    return [part for part in parts if part.status != ProjectStatus.CANCELLED], cancelled


def family_prices(
    project: Project, *, rights: Any = None, user: Any = None, engine: AvailabilityEngine | None = None
) -> FamilyPrices:
    """Put together the plannings and the sum of a project and the parts in its prices (PRJ-046).

    Args:
        project: A whole project, a part or a project on its own.
        rights: The rights of the user to show it to; with ``user``, parts
            whose planning the user may not read are left out (PRJ-049).
            ``None``: every part that is not cancelled, as on a document.
        user: The user, with ``rights``.
        engine: An availability engine to share; one serves all projects.
    """
    from rentalars.projects.access import ProjectAccess, access_level

    parts, cancelled = billed_parts(project)
    hidden = 0
    if rights is not None and parts:
        readable = [part for part in parts if access_level(rights, user, part) >= ProjectAccess.READ]
        hidden = len(parts) - len(readable)
        parts = readable
    engine = engine or AvailabilityEngine()
    blocks = [PriceBlock(project=project, planning=build_planning(project, engine=engine), is_whole=bool(parts))]
    blocks += [PriceBlock(project=part, planning=build_planning(part, engine=engine), is_whole=False) for part in parts]
    return FamilyPrices(
        project=project,
        blocks=blocks,
        totals=sum_prices([block.prices for block in blocks]),
        hidden=hidden,
        cancelled=cancelled,
    )
