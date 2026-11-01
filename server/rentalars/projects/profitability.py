# SPDX-License-Identifier: GPL-3.0-or-later
"""Keeping an eye on profitability: projects, customers and material (PRJ-115, MAT-053).

The requirements: a way to keep profitability in view, and, per item, an overview of how
much money the object has earned directly and what share of the purchase price that is.

Nothing here is stored. Every figure comes from the price calculation of the
planning (``projects.pricing``), the same one the project list sums up
(PRJ-085, ``projects.list_sums``): revenue net, the costs of subrentals and
crew, the approved expenses, and what remains – "Gewinn aus dem Projekt"
(PRJ-025, PRJ-087).

Projects (:func:`project_report`)
---------------------------------
Whole projects (with their parts, as the customer is billed) that were
confirmed – "Bestätigt – Einzelheiten offen" and every status after it, not
cancelled –, counted in the month their material comes back (``end``).
Service cases have no planning and are left out. Per month, per customer
and per project manager; the projects with the most and the least left over.

Material (:func:`line_revenues`, :func:`product_report`, :func:`item_revenue`)
------------------------------------------------------------------------------
What a line of a project brings in is its share of the net total: its amount
after its own discount and those of its groups – a flat price of a group
spread over its lines as the calculation spreads it (``GroupPrices.shares``).
Optional and alternative lines, customer material and lines taken over from
another subproject bring in nothing; surcharges belong to no material. Only
projects whose material went out count ("Unterwegs", "Wieder im Lager",
"Abgeschlossen").

* A product earns what its lines earn; a kit's line is shared out to its
  components in proportion to their own price (each component's price times
  its quantity; without prices evenly).
* An item earns what the lines of its product earned in the projects it went
  out with – one piece's share each time (*direct*, PCK-021: the item was
  assigned when packing). Pieces that went out without an item assigned are
  shared out evenly over the items the product had then (*estimated*): a
  scan is never needed (PCK-020), so for most cables nobody knows which one
  went.
* The share of the purchase price is what an item earned against what it
  cost. An item bought in a set (MAT-054) is compared together with its set:
  what the set earned against the price of the set.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from rentalars.core.money import ZERO, money
from rentalars.products.models import Product, ProductKind
from rentalars.projects.models import (
    EARNING_STATUSES,
    ORDER_STATUSES,
    MaterialLine,
    Project,
    ProjectKind,
    ProjectStatus,
)

#: Projects whose prices are calculated together.
CHUNK = 200


# --- The calculation of many projects at once -----------------------------------------------------------


def _calculate(projects: list[Project]) -> dict[int, Any]:
    """The price calculation of each project, a chunk at a time with a fixed number of queries each (PRJ-085)."""
    from rentalars.projects.list_sums import _prices_of

    results: dict[int, Any] = {}
    for start in range(0, len(projects), CHUNK):
        for pk, (prices, _hours) in _prices_of(projects[start : start + CHUNK]).items():
            results[pk] = prices
    return results


# --- Projects (PRJ-115) ------------------------------------------------------------------------------------


@dataclass
class Figures:
    """Revenue, costs and what remains – of a project, a month, a customer or all of them (PRJ-115)."""

    projects: int = 0
    material_revenue: Decimal = ZERO
    personnel_revenue: Decimal = ZERO
    #: LOG-009: vehicles and trailers.
    logistics_revenue: Decimal = ZERO
    subrental_cost: Decimal = ZERO
    personnel_cost: Decimal = ZERO
    expenses: Decimal = ZERO
    #: LOG-010: the internal costs of the vehicles.
    logistics_cost: Decimal = ZERO

    @property
    def revenue(self) -> Decimal:
        """Net total: material, personnel and logistics."""
        return self.material_revenue + self.personnel_revenue + self.logistics_revenue

    @property
    def costs(self) -> Decimal:
        """Subrentals, crew and their expenses, vehicles."""
        return self.subrental_cost + self.personnel_cost + self.expenses + self.logistics_cost

    @property
    def margin(self) -> Decimal:
        """What remains: "Gewinn aus dem Projekt" (PRJ-025)."""
        return self.revenue - self.costs

    @property
    def margin_percent(self) -> Decimal | None:
        """What remains in percent of the revenue; ``None`` without revenue."""
        if not self.revenue:
            return None
        return (self.margin * 100 / self.revenue).quantize(Decimal("0.1"))

    def add(self, other: Figures) -> None:
        """Add the figures of another project or group."""
        self.projects += other.projects
        self.material_revenue += other.material_revenue
        self.personnel_revenue += other.personnel_revenue
        self.logistics_revenue += other.logistics_revenue
        self.subrental_cost += other.subrental_cost
        self.personnel_cost += other.personnel_cost
        self.expenses += other.expenses
        self.logistics_cost += other.logistics_cost


@dataclass
class ProjectRow:
    """One whole project of the report with its figures."""

    project: Project
    figures: Figures


@dataclass
class Group:
    """The figures of one month, customer or project manager."""

    key: Any
    label: str
    figures: Figures = field(default_factory=Figures)


@dataclass
class ProjectReport:
    """PRJ-115: the projects of a period and their figures, summed up in several ways."""

    since: datetime.date
    until: datetime.date
    total: Figures
    months: list[Group]
    customers: list[Group]
    managers: list[Group]
    rows: list[ProjectRow]
    #: Only projects that are closed ("Abgeschlossen") – otherwise every order of the period.
    closed_only: bool = False

    @property
    def best(self) -> list[ProjectRow]:
        """The projects with the most left over."""
        return sorted(self.rows, key=lambda row: row.figures.margin, reverse=True)[:10]

    @property
    def worst(self) -> list[ProjectRow]:
        """The projects with the least left over – a loss first."""
        return sorted(self.rows, key=lambda row: row.figures.margin)[:10]

    @property
    def largest_month_revenue(self) -> Decimal:
        """For the bars of the months: the largest revenue of a month (at least 1)."""
        return max([group.figures.revenue for group in self.months] + [Decimal(1)])


def report_projects(
    queryset: Any, since: datetime.date, until: datetime.date, *, closed_only: bool = False
) -> list[Project]:
    """The whole projects of the report: orders whose material comes back between ``since`` and ``until``."""
    zone = timezone.get_current_timezone()
    start = datetime.datetime.combine(since, datetime.time.min, tzinfo=zone)
    end = datetime.datetime.combine(until + datetime.timedelta(days=1), datetime.time.min, tzinfo=zone)
    statuses = [ProjectStatus.CLOSED.value] if closed_only else list(ORDER_STATUSES)
    return list(
        queryset.filter(kind=ProjectKind.PROJECT, parent__isnull=True, status__in=statuses, end__gte=start, end__lt=end)
        .select_related("customer", "manager")
        .order_by("end", "pk")
    )


def figures_of(projects: list[Project]) -> dict[int, Figures]:
    """The figures of each whole project, its parts that are not cancelled included (PRJ-046)."""
    wholes = {project.pk: project for project in projects}
    parts: dict[int, list[Project]] = defaultdict(list)
    for part in Project.objects.filter(parent_id__in=list(wholes)).exclude(status=ProjectStatus.CANCELLED):
        parts[part.parent_id].append(part)
    every = list(projects) + [part for members in parts.values() for part in members]
    calculated = _calculate(every)
    result = {}
    for project in projects:
        figures = Figures(projects=1)
        for member in [project, *parts.get(project.pk, [])]:
            prices = calculated.get(member.pk)
            if prices is None:
                continue
            personnel, logistics = prices.personnel_total, prices.logistics_total
            if prices.overall_discount and prices.net_before_overall_discount:
                # PRJ-123: the overall discount is shared by the three kinds in proportion – not all of it by the material.
                factor = prices.net_total / prices.net_before_overall_discount
                personnel, logistics = money(personnel * factor), money(logistics * factor)
            figures.material_revenue += prices.net_total - personnel - logistics
            figures.personnel_revenue += personnel
            figures.logistics_revenue += logistics
            figures.subrental_cost += prices.subrental_cost
            figures.personnel_cost += prices.personnel_cost
            figures.expenses += prices.expenses_cost
            figures.logistics_cost += prices.logistics_cost
        result[project.pk] = figures
    return result


def _month_label(day: datetime.date) -> str:
    from rentalars.core.i18n import format_date

    return format_date(day, "F Y")


def project_report(
    queryset: Any, since: datetime.date, until: datetime.date, *, closed_only: bool = False
) -> ProjectReport:
    """PRJ-115: the figures of the whole projects of a period – per month, customer and project manager."""
    from django.utils.translation import gettext as _

    projects = report_projects(queryset, since, until, closed_only=closed_only)
    figures = figures_of(projects)
    total = Figures()
    months: dict[tuple[int, int], Group] = {}
    # Every month of the period has its row, also one without projects.
    day = since.replace(day=1)
    while day <= until:
        months[(day.year, day.month)] = Group((day.year, day.month), _month_label(day))
        day = (day + datetime.timedelta(days=32)).replace(day=1)
    customers: dict[Any, Group] = {}
    managers: dict[Any, Group] = {}
    rows = []
    for project in projects:
        own = figures[project.pk]
        rows.append(ProjectRow(project, own))
        total.add(own)
        back = timezone.localtime(project.end).date()
        months.setdefault((back.year, back.month), Group((back.year, back.month), _month_label(back))).figures.add(own)
        customer = project.customer
        customers.setdefault(
            project.customer_id, Group(project.customer_id, customer.name if customer else _("internal"))
        ).figures.add(own)
        manager = project.manager
        managers.setdefault(
            project.manager_id, Group(project.manager_id, str(manager) if manager else _("without project manager"))
        ).figures.add(own)
    return ProjectReport(
        since=since,
        until=until,
        total=total,
        months=[months[key] for key in sorted(months)],
        customers=sorted(customers.values(), key=lambda group: group.figures.revenue, reverse=True),
        managers=sorted(managers.values(), key=lambda group: group.figures.revenue, reverse=True),
        rows=rows,
        closed_only=closed_only,
    )


# --- Material (MAT-053) -------------------------------------------------------------------------------------


def line_contributions(prices: Any) -> dict[int, Decimal]:
    """What each material line contributes to the net total of its project (MAT-053).

    The amount after the line's own discount and those of all its groups,
    flat prices spread as the calculation spreads them – the shares of the
    top-level groups add up to their subtotals exactly. Optional and
    alternative lines and groups, customer material and lines taken over
    from another subproject contribute nothing.
    """
    contributions: dict[int, Decimal] = defaultdict(lambda: ZERO)

    def counts(line_price: Any) -> bool:
        return bool(line_price.counts and not line_price.is_customer_material and not line_price.is_takeover)

    for line_price in prices.ungrouped:
        if counts(line_price):
            contributions[line_price.line.pk] += line_price.amount
    for group_price in prices.groups:
        if group_price.depth != 0 or not group_price.adds_to_parent:
            continue
        for share in group_price.shares:
            if share.line_price is not None and counts(share.line_price):
                contributions[share.line_price.line.pk] += share.amount
    return dict(contributions)


def kit_shares(kit_ids: Iterable[int]) -> dict[int, list[tuple[int, int, Decimal]]]:
    """For each kit: ``(component, pieces per kit, share of the kit's price)`` – by the components' own prices.

    The share of a component is its price times its quantity against those
    of all components; components without any price share evenly.
    """
    from rentalars.products.models import KitComponent

    rows: dict[int, list[Any]] = defaultdict(list)
    for component in KitComponent.objects.filter(kit_id__in=list(kit_ids)).select_related("component"):
        rows[component.kit_id].append(component)
    result: dict[int, list[tuple[int, int, Decimal]]] = {}
    for kit_id, components in rows.items():
        weights = [(component.component.price or ZERO) * component.quantity for component in components]
        total = sum(weights, ZERO)
        if total:
            result[kit_id] = [
                (component.component_id, component.quantity, weight / total)
                for component, weight in zip(components, weights, strict=True)
            ]
        else:
            result[kit_id] = [
                (component.component_id, component.quantity, Decimal(1) / len(components)) for component in components
            ]
    return result


@dataclass
class LineRevenue:
    """What one line earned for one product: in all, and for each piece that went out.

    ``pieces`` counts items (MAT-053): for a product of several pieces – "3 × K-005", ten cables each – that
    is 30, so that every cable earns its share of the line and not the thirtieth of ten times its due.
    """

    project: Project
    line_id: int
    product_id: int
    amount: Decimal
    pieces: Decimal

    @property
    def per_piece(self) -> Decimal:
        """The share of one piece; nothing for a line without pieces."""
        return self.amount / self.pieces if self.pieces else ZERO


def earning_projects(queryset: Any = None, *, product_ids: Iterable[int] | None = None, **period: Any) -> list[Project]:
    """The projects whose material went out – with lines of these products (or kits containing them), if given."""
    from rentalars.products.models import KitComponent

    projects = Project.objects.all() if queryset is None else queryset
    projects = projects.filter(kind=ProjectKind.PROJECT, status__in=EARNING_STATUSES)
    if product_ids is not None:
        ids = set(product_ids)
        kits = set(KitComponent.objects.filter(component_id__in=ids).values_list("kit_id", flat=True))
        projects = projects.filter(
            pk__in=MaterialLine.objects.filter(Q(product_id__in=ids) | Q(product_id__in=kits)).values("project_id")
        )
    if period.get("since") is not None:
        projects = projects.filter(end__gte=period["since"])
    if period.get("until") is not None:
        projects = projects.filter(end__lt=period["until"])
    return list(projects.order_by("end", "pk"))


def line_revenues(projects: list[Project], *, product_ids: Iterable[int] | None = None) -> list[LineRevenue]:
    """What every material line of these projects earned, per product (kits shared out to their components)."""
    calculated = _calculate(projects)
    wanted = set(product_ids) if product_ids is not None else None
    lines = MaterialLine.objects.filter(project_id__in=[project.pk for project in projects], product__isnull=False)
    lines = lines.select_related("product").only("pk", "project_id", "product_id", "product__kind", "quantity")
    by_project = {project.pk: project for project in projects}
    kits = kit_shares({line.product_id for line in lines if line.product.kind == "kit"})
    # Items per piece of the products behind the lines (rare: one query, nothing found as a rule).
    behind = {line.product_id for line in lines} | {component for parts in kits.values() for component, _n, _s in parts}
    pieces_of = dict(
        Product.objects.filter(pk__in=behind, pieces_per_product__gt=1).values_list("pk", "pieces_per_product")
    )
    result: list[LineRevenue] = []
    contributions_of: dict[int, dict[int, Decimal]] = {}
    for line in lines:
        prices = calculated.get(line.project_id)
        if prices is None:
            continue
        if line.project_id not in contributions_of:
            contributions_of[line.project_id] = line_contributions(prices)
        amount = contributions_of[line.project_id].get(line.pk)
        if amount is None:
            continue
        project = by_project[line.project_id]
        if line.product_id in kits:
            for component_id, per_kit, share in kits[line.product_id]:
                if wanted is None or component_id in wanted:
                    result.append(
                        LineRevenue(
                            project,
                            line.pk,
                            component_id,
                            amount * share,
                            Decimal(line.quantity) * per_kit * pieces_of.get(component_id, 1),
                        )
                    )
        elif wanted is None or line.product_id in wanted:
            result.append(
                LineRevenue(
                    project,
                    line.pk,
                    line.product_id,
                    amount,
                    Decimal(line.quantity) * pieces_of.get(line.product_id, 1),
                )
            )
    return result


@dataclass
class ItemRevenue:
    """MAT-053: what one item earned, and against what it cost."""

    item: Any
    direct: Decimal = ZERO
    estimated: Decimal = ZERO
    projects: int = 0
    #: The purchase price of the item – or, bought in a set (MAT-054), that of the set.
    purchase_price: Decimal | None = None
    #: MAT-054: the set compared: what all its items earned.
    set_items: list[Any] = field(default_factory=list)
    set_revenue: Decimal = ZERO
    #: The projects it earned in (MAT-058 counts them over all items of a model).
    project_ids: set[int] = field(default_factory=set)

    @property
    def total(self) -> Decimal:
        """Direct and estimated together."""
        return money(self.direct + self.estimated)

    @property
    def compared(self) -> Decimal:
        """What is compared with the purchase price: the item's revenue, or the set's."""
        return money(self.set_revenue) if self.set_items else self.total

    @property
    def share_percent(self) -> Decimal | None:
        """The share of the purchase price earned, in percent; ``None`` without a price."""
        if not self.purchase_price:
            return None
        return (self.compared * 100 / self.purchase_price).quantize(Decimal("0.1"))


def _items_of_product(product_id: int) -> list[Any]:
    """Every item of a product – also archived ones: they earned money until they left."""
    from rentalars.material.models import MaterialItem

    return list(
        MaterialItem.objects.filter(
            Q(product_override_id=product_id)
            | Q(product_override__isnull=True, material_model__default_product_id=product_id)
        ).select_related("purchase_price_in")
    )


def revenues_of_items(items: list[Any]) -> dict[int, ItemRevenue]:
    """MAT-053: what each of these items earned – directly, and its share of the pieces nobody assigned."""
    from rentalars.packing.models import Allocation

    results = {item.pk: ItemRevenue(item=item) for item in items}
    by_product: dict[int, list[Any]] = defaultdict(list)
    for item in items:
        product = item.product
        if product is not None:
            by_product[product.pk].append(item)
    if not by_product:
        return results
    seen_projects: dict[int, set[int]] = defaultdict(set)
    _add_vehicle_revenues(results, by_product, seen_projects)
    projects = earning_projects(product_ids=by_product)
    revenues = line_revenues(projects, product_ids=by_product)
    # The items assigned to a line and product when packing (PCK-021): issued, not handed over from another part.
    assigned: dict[tuple[int, int], list[int]] = defaultdict(list)
    for line_id, product_id, item_id in Allocation.objects.filter(
        entry__line_id__in=[revenue.line_id for revenue in revenues],
        issued_at__isnull=False,
        handover__isnull=True,
        with_container__isnull=True,
    ).values_list("entry__line_id", "entry__product_id", "item_id"):
        assigned[(line_id, product_id)].append(item_id)
    all_of_product = {product_id: _items_of_product(product_id) for product_id in by_product}
    for revenue in revenues:
        per_piece = revenue.per_piece
        chosen = assigned.get((revenue.line_id, revenue.product_id), [])
        for item_id in chosen:
            if item_id in results:
                results[item_id].direct += per_piece
                seen_projects[item_id].add(revenue.project.pk)
        rest = max(revenue.pieces - len(chosen), ZERO)
        if not rest:
            continue
        # Pieces that went out without an item assigned: shared evenly over the items the product had then.
        present = [
            other for other in all_of_product.get(revenue.product_id, []) if other.created_at <= revenue.project.end
        ] or all_of_product.get(revenue.product_id, [])
        weight_total = sum((Decimal(other.quantity or 1) for other in present), ZERO)
        if not weight_total:
            continue
        for other in present:
            if other.pk in results:
                results[other.pk].estimated += per_piece * rest * Decimal(other.quantity or 1) / weight_total
                seen_projects[other.pk].add(revenue.project.pk)
    for item_id, result in results.items():
        result.project_ids = seen_projects[item_id]
        result.projects = len(result.project_ids)
    return results


def _add_vehicle_revenues(
    results: dict[int, ItemRevenue], by_product: dict[int, list[Any]], seen_projects: dict[int, set[int]]
) -> None:
    """LOG-001: what a vehicle earned – its bookings in the logistics, not material lines.

    A booking of a chosen vehicle counts for it directly; an open booking of
    its product (no vehicle chosen) is shared evenly over the vehicles the
    product had at the end of the project, as pieces of material without an
    item are. Each booking with what it adds to the net total: its amount
    after its own discount.
    """
    from rentalars.projects.models import VehicleLine

    vehicle_products = {
        product_id for product_id, items in by_product.items() if items[0].product.kind == ProductKind.VEHICLE
    }
    if not vehicle_products:
        return
    bookings = list(
        VehicleLine.objects.filter(
            product_id__in=vehicle_products, project__kind=ProjectKind.PROJECT, project__status__in=EARNING_STATUSES
        ).values_list("pk", "project_id", "product_id", "item_id")
    )
    if not bookings:
        return
    projects = list(Project.objects.filter(pk__in={booking[1] for booking in bookings}).order_by("end", "pk"))
    ends = {project.pk: project.end for project in projects}
    amounts = {
        vehicle_price.line.pk: vehicle_price.amount
        for prices in _calculate(projects).values()
        for vehicle_price in prices.logistics
    }
    all_of_product = {product_id: _items_of_product(product_id) for product_id in vehicle_products}
    for line_id, project_id, product_id, item_id in bookings:
        amount = amounts.get(line_id, ZERO)
        if item_id is not None:
            if item_id in results:
                results[item_id].direct += amount
                seen_projects[item_id].add(project_id)
            continue
        present = [
            other for other in all_of_product[product_id] if other.created_at <= ends[project_id]
        ] or all_of_product[product_id]
        for other in present:
            if other.pk in results:
                results[other.pk].estimated += amount / len(present)
                seen_projects[other.pk].add(project_id)


def item_revenue(item: Any) -> ItemRevenue:
    """MAT-053: what an item earned and the share of its purchase price – or, bought in a set, of the set's."""
    members = item.purchase_set  # MAT-054: the head first, empty if bought alone
    group = members or [item]
    revenues = revenues_of_items(group)
    result = revenues[item.pk]
    if members:
        head = members[0]
        result.purchase_price = head.purchase_price
        result.set_items = members
        result.set_revenue = sum((revenues[member.pk].total for member in members), ZERO)
    else:
        result.purchase_price = item.purchase_price
    return result


@dataclass
class ModelRevenue:
    """MAT-058: what all items of a material model earned, item by item and together."""

    material_model: Any
    #: Every item with what it earned, the highest first (:class:`ItemRevenue`; ``purchase_price`` its share).
    items: list[ItemRevenue] = field(default_factory=list)
    projects: int = 0

    @property
    def direct(self) -> Decimal:
        """Earned in projects the items were chosen for when packing."""
        return money(sum((row.direct for row in self.items), ZERO))

    @property
    def estimated(self) -> Decimal:
        """Their share of the pieces that went out without an item chosen."""
        return money(sum((row.estimated for row in self.items), ZERO))

    @property
    def total(self) -> Decimal:
        """Everything the items earned."""
        return money(self.direct + self.estimated)

    @property
    def purchase_total(self) -> Decimal | None:
        """What the items cost; a set's price spread evenly over its items (MAT-054); ``None`` without prices."""
        prices = [row.purchase_price for row in self.items if row.purchase_price is not None]
        return money(sum(prices, ZERO)) if prices else None

    @property
    def share_percent(self) -> Decimal | None:
        """What was earned in percent of what the items cost."""
        cost = self.purchase_total
        if not cost:
            return None
        return (self.total * 100 / cost).quantize(Decimal("0.1"))


def model_revenue(material_model: Any) -> ModelRevenue:
    """MAT-058: what every item of a model earned – the figures of MAT-053, added up for the model.

    Each item counts with its own purchase price; an item bought in a set
    (MAT-054) with its share of the set's price – the price spread evenly
    over the items of the set, as on the tab "Material" of the reports.
    """
    from rentalars.material.models import MaterialItem

    items = list(
        MaterialItem.objects.filter(material_model=material_model).select_related(
            "material_model__default_product", "product_override", "purchase_price_in"
        )
    )
    revenues = revenues_of_items(items)
    heads = {item.purchase_price_in_id or item.pk for item in items}
    prices = dict(MaterialItem.objects.filter(pk__in=heads).values_list("pk", "purchase_price"))
    # The size of each set: its head and the items whose price is included in the head's.
    members = dict(
        MaterialItem.objects.filter(purchase_price_in__in=heads)
        .values("purchase_price_in")
        .annotate(count=Count("pk"))
        .values_list("purchase_price_in", "count")
    )
    rows = []
    for item in items:
        row = revenues[item.pk]
        head = item.purchase_price_in_id or item.pk
        price = prices.get(head)
        if price is not None:
            row.purchase_price = money(price / (1 + members.get(head, 0)))
        rows.append(row)
    result = ModelRevenue(material_model=material_model, items=sorted(rows, key=lambda row: -row.total))
    result.projects = len(set().union(*(row.project_ids for row in rows)))
    return result


@dataclass
class ProductRow:
    """MAT-053: a product with what its items cost and what its lines earned."""

    product: Any
    items: int = 0
    purchase_total: Decimal = ZERO
    revenue: Decimal = ZERO

    @property
    def share_percent(self) -> Decimal | None:
        """What was earned in percent of what the items cost; ``None`` without prices."""
        if not self.purchase_total:
            return None
        return (self.revenue * 100 / self.purchase_total).quantize(Decimal("0.1"))


def product_report(queryset: Any = None, *, since: Any = None, until: Any = None) -> list[ProductRow]:
    """MAT-053: per product with items – the purchase prices of its items and what its lines earned.

    The price of a set bought together (MAT-054) is spread evenly over the
    items of the set, as the products of a set may differ.
    """
    from rentalars.material.models import MaterialItem
    from rentalars.products.models import Product

    rows: dict[int, ProductRow] = {}
    set_sizes: dict[int, int] = defaultdict(int)
    # Plain values, not objects: 20,000 items are read in a fraction of the time (NFA-012).
    items = list(
        MaterialItem.objects.values_list(
            "pk",
            "purchase_price",
            "purchase_price_in_id",
            "quantity",
            "product_override_id",
            "material_model__default_product_id",
        )
    )
    for pk, _price, head_pk, *_rest in items:
        set_sizes[head_pk or pk] += 1
    prices = {pk: price for pk, price, *_rest in items}
    products = Product.objects.in_bulk({override or default for *_rest, override, default in items} - {None})
    for pk, _price, head_pk, quantity, override, default in items:
        product = products.get(override or default)
        if product is None:
            continue
        row = rows.setdefault(product.pk, ProductRow(product=product))
        row.items += quantity or 1
        head = head_pk or pk
        price = prices.get(head)
        if price:
            row.purchase_total += price / set_sizes[head]
    projects = earning_projects(queryset, product_ids=list(rows), since=since, until=until)
    for revenue in line_revenues(projects, product_ids=list(rows)):
        if revenue.product_id in rows:
            rows[revenue.product_id].revenue += revenue.amount
    # LOG-001: vehicles earn through their bookings in the logistics.
    vehicle_ids = [pk for pk, row in rows.items() if row.product.kind == ProductKind.VEHICLE]
    if vehicle_ids:
        from rentalars.projects.models import VehicleLine

        booked = Project.objects.all() if queryset is None else queryset
        booked = booked.filter(
            kind=ProjectKind.PROJECT,
            status__in=EARNING_STATUSES,
            pk__in=VehicleLine.objects.filter(product_id__in=vehicle_ids).values("project_id"),
        )
        if since is not None:
            booked = booked.filter(end__gte=since)
        if until is not None:
            booked = booked.filter(end__lt=until)
        for prices in _calculate(list(booked.order_by("end", "pk"))).values():
            for vehicle_price in prices.logistics:
                if vehicle_price.line.product_id in rows:
                    rows[vehicle_price.line.product_id].revenue += vehicle_price.amount
    for row in rows.values():
        row.purchase_total = money(row.purchase_total)
        row.revenue = money(row.revenue)
    found = [row for row in rows.values() if row.purchase_total or row.revenue]
    return sorted(found, key=lambda row: (row.share_percent is None, -(row.share_percent or 0)))
