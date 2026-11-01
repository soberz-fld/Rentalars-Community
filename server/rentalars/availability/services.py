# SPDX-License-Identifier: GPL-3.0-or-later
"""Overviews built on the availability engine: shortages and subrentals (PRJ-057)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.db.models import QuerySet
from django.utils import timezone

from rentalars.availability.engine import AvailabilityEngine, Demand, LineAvailability, ProductShortage
from rentalars.products.models import Product, ProductKind
from rentalars.projects.models import FINISHED_STATUSES, MaterialLine, Project


@dataclass
class OpenShortage:
    """One uncovered shortage: which line of which project lacks how much of what."""

    project: Project
    line: MaterialLine
    product: Product
    detail: ProductShortage

    @property
    def quantity(self) -> int:
        """The number of missing pieces."""
        return self.detail.shortage

    @property
    def missing_before_cover(self) -> int:
        """The pieces the stock does not give, before subrentals cover a part of them (PRJ-098)."""
        return max(self.detail.shortage_without_cover, self.detail.shortage)

    @property
    def subrented(self) -> int:
        """Of :attr:`missing_before_cover`, the pieces a subrental covers already (PRJ-098)."""
        return self.missing_before_cover - self.detail.shortage

    @property
    def held_by_other_parts(self) -> int:
        """Of the missing pieces, as many as other parts of the same whole project hold firmly (PRJ-047).

        Without those parts the line would lack that many pieces less; the
        shortages page then points to the overview of the whole project.
        """
        return min(self.detail.family, self.detail.shortage)


def shortages_of_project(
    project: Project, availability: dict[int, LineAvailability], lines: list[MaterialLine]
) -> list[OpenShortage]:
    """Turn the per-line verdicts of a project into a flat list of shortages."""
    short_product_ids = {detail.product_id for verdict in availability.values() for detail in verdict.shortages}
    products = {product.pk: product for product in Product.objects.filter(pk__in=short_product_ids)}
    result: list[OpenShortage] = []
    for line in lines:
        verdict = availability.get(line.pk)
        if verdict is None:
            continue
        for detail in verdict.shortages:
            result.append(OpenShortage(project=project, line=line, product=products[detail.product_id], detail=detail))
    return result


def open_shortages(*, horizon_days: int = 365, projects: QuerySet[Project] | None = None) -> list[OpenShortage]:
    """List all uncovered shortages of running and coming projects (PRJ-057, PRJ-013).

    Every project that is not finished and ends in the future (or is still
    out) is judged with the same calculation its planning page uses, so the
    list and the project pages always agree.

    That calculation is only run for the projects in which a shortage is
    possible at all; a quick test over all projects at once sorts out the
    others first (see :meth:`AvailabilityEngine.projects_that_may_be_short`).
    With a thousand projects and no shortage the page is then answered with
    about a dozen queries instead of several thousand (NFA-012).

    Args:
        horizon_days: How far into the future projects are considered.
        projects: The projects to look at; default: all. A caller passes the
            projects its user may read (AUT-016).
    """
    now = timezone.now()
    projects = list(
        (Project.objects.all() if projects is None else projects)
        .exclude(status__in=FINISHED_STATUSES)
        .filter(end__gte=now - datetime.timedelta(days=30), start__lte=now + datetime.timedelta(days=horizon_days))
        .select_related("customer", "parent")
        .order_by("start")
    )
    engine = AvailabilityEngine(now=now)
    may_be_short = engine.projects_that_may_be_short(projects)
    result: list[OpenShortage] = []
    for project in projects:
        if project.pk not in may_be_short:
            continue
        lines = list(project.material_lines.select_related("product"))
        availability = engine.project_availability(project, lines)
        result.extend(shortages_of_project(project, availability, lines))
    return result


def subrental_lines(projects: QuerySet[Project] | None = None) -> QuerySet[MaterialLine]:
    """Return all subrental lines of projects that are not finished (PRJ-057).

    Args:
        projects: Only lines of these projects; default: all (AUT-016).
    """
    lines = MaterialLine.objects.all()
    if projects is not None:
        lines = lines.filter(project__in=projects.values("pk"))
    return (
        lines.filter(product__kind=ProductKind.SUBRENTAL)
        .exclude(project__status__in=FINISHED_STATUSES)
        .select_related(
            "project", "project__customer", "project__parent", "supplier", "covers_line", "covers_product", "product"
        )
        .order_by("start", "project__number")
    )


@dataclass
class DayLoad:
    """How much of a product is reserved on one day (VFG-012)."""

    day: datetime.date
    firm: int
    optional: int
    stock: int
    #: VFG-029: the period of a load that covers some hours rather than the whole day.
    start: datetime.datetime | None = None
    end: datetime.datetime | None = None

    @property
    def percent(self) -> int:
        """Firm reservations as a share of the plannable stock."""
        if self.stock <= 0:
            return 100 if self.firm else 0
        return round(100 * self.firm / self.stock)

    @property
    def free(self) -> int:
        """Pieces not firmly reserved; negative if more is reserved than there is."""
        return self.stock - self.firm

    @property
    def free_level(self) -> str:
        """For showing the free pieces: ``short`` (below zero), ``tight`` (none left, or options beyond) or ``ok``."""
        if self.firm > self.stock:
            return "short"
        if self.free == 0 or self.firm + self.optional > self.stock:
            return "tight"
        return "ok"

    @property
    def level(self) -> str:
        """``free``, ``tight`` (80 % or options beyond the stock) or ``short`` (more than there is)."""
        if self.firm > self.stock:
            return "short"
        if self.percent >= 80 or self.firm + self.optional > self.stock:
            return "tight"
        if self.firm or self.optional:
            return "used"
        return "free"


def utilization(product_ids: list[int], days: list[datetime.date]) -> dict[int, list[DayLoad]]:
    """The reserved quantity of products day by day, for the timeline per product (VFG-012).

    Uses the same calculation as everything else (VFG-002): per day the peak
    of the reservations within that day – firm, and what options add.
    Products without stock of their own (services, kits) are left out; a kit
    shows through its components.
    """
    return utilization_with_demands(product_ids, days)[0]


def utilization_with_demands(
    product_ids: list[int], days: list[datetime.date]
) -> tuple[dict[int, list[DayLoad]], dict[int, list[Demand]]]:
    """:func:`utilization`, and the demands of the days it was worked out from.

    For the timelines, which show both the free pieces and who takes them
    (VFG-019): the demands are collected once, not twice.
    """
    from rentalars.availability.engine import Firmness, peak_quantity
    from rentalars.availability.stock import stock_of_products

    if not days:
        return {}, {}
    zone = timezone.get_current_timezone()
    window_start = datetime.datetime.combine(days[0], datetime.time.min, tzinfo=zone)
    window_end = datetime.datetime.combine(days[-1] + datetime.timedelta(days=1), datetime.time.min, tzinfo=zone)
    engine = AvailabilityEngine()
    infos = engine.product_info(product_ids)
    tracked = {product_id for product_id in product_ids if infos.get(product_id) and infos[product_id].tracks_stock}
    demands = engine.collect_demands(tracked, window_start, window_end)
    stocks = stock_of_products(tracked)
    result: dict[int, list[DayLoad]] = {}
    for product_id in product_ids:
        if product_id not in tracked:
            continue
        product_demands = demands.get(product_id, [])
        stock = stocks[product_id].plannable if product_id in stocks else 0
        loads = []
        for day in days:
            start = datetime.datetime.combine(day, datetime.time.min, tzinfo=zone)
            end = start + datetime.timedelta(days=1)
            firm = peak_quantity((d for d in product_demands if d.firmness == Firmness.FIRM), start, end)
            total = peak_quantity(product_demands, start, end)
            loads.append(DayLoad(day=day, firm=firm, optional=total - firm, stock=stock))
        result[product_id] = loads
    return result, demands


def utilization_in_periods(
    product_ids: list[int], periods: list[tuple[datetime.datetime, datetime.datetime]]
) -> dict[int, list[DayLoad]]:
    """The reserved quantity of products in each of some periods, e.g. the hour columns of a timeline (VFG-029).

    The same calculation as :func:`utilization` – the peak of the firm
    reservations within the period, and what options add –, for periods of
    any length instead of whole days. The demands are collected once for
    all periods: as many queries as for the days.

    Args:
        product_ids: The products.
        periods: Start and end of each period, in order.

    Returns:
        Per product with stock of its own a load for each period, with its
        ``start`` and ``end`` and the day it begins on.
    """
    from rentalars.availability.engine import Firmness, peak_quantity
    from rentalars.availability.stock import stock_of_products

    if not periods:
        return {}
    engine = AvailabilityEngine()
    infos = engine.product_info(product_ids)
    tracked = {product_id for product_id in product_ids if infos.get(product_id) and infos[product_id].tracks_stock}
    demands = engine.collect_demands(tracked, periods[0][0], periods[-1][1])
    stocks = stock_of_products(tracked)
    result: dict[int, list[DayLoad]] = {}
    for product_id in product_ids:
        if product_id not in tracked:
            continue
        product_demands = demands.get(product_id, [])
        firm_demands = [demand for demand in product_demands if demand.firmness == Firmness.FIRM]
        stock = stocks[product_id].plannable if product_id in stocks else 0
        loads = []
        for start, end in periods:
            firm = peak_quantity(firm_demands, start, end)
            total = peak_quantity(product_demands, start, end)
            loads.append(
                DayLoad(
                    day=timezone.localtime(start).date(),
                    firm=firm,
                    optional=total - firm,
                    stock=stock,
                    start=start,
                    end=end,
                )
            )
        result[product_id] = loads
    return result
