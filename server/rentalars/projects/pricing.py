# SPDX-License-Identifier: GPL-3.0-or-later
"""Price calculation for projects (PRJ-024, PRJ-033 ff., PRD-033 ff.).

Nothing calculated here is stored. Subtotals and totals are derived from the
lines every time they are needed (catalogue 7.3), so they can never be out of
step with the lines.

The calculation in five steps
-----------------------------
1. **Lines.** Each line gets its amount from quantity, unit price and billing
   mode (PRD-033), minus its own discount.
2. **Groups.** The amounts of a group's lines add up; then the group's
   discount or flat price applies (PRJ-039).
3. **Percentage surcharges.** Each is a percentage of the amounts it refers
   to – *after* discounts and *before* any other surcharge (PRD-039).
4. **Project total.** Subtotals of the counting groups, lines without group,
   personnel and project-wide surcharges (PRJ-034). Then the project's
   *overall discount*, if it has one (PRJ-123): in percent of that sum
   or as an amount, never more than the sum itself.
5. **Tax.** The net total is split by tax rate, tax is added (PRJ-024). The
   overall discount lowers every rate in the same proportion, like a group's
   discount does (:func:`_tax_lines`).

Personnel (PRJ-038, PRJ-051) is a block of its own next to the material: the
crew lines are priced in ``projects.crew`` and enter here as one sum. A
percentage surcharge can refer to it ("night surcharge on personnel"), and
"the whole project" includes it.

Logistics (LOG-009) is the third block: the vehicles and
trailers booked for the project, priced in ``projects.logistics`` by their
kilometres and days. It enters like the personnel – one sum in the net
total, in "the whole project" of a percentage surcharge, in the taxes by the
tax rate of each booking, its discounts among the discounts and its internal
costs (LOG-010) among the costs.

Optional and alternative lines (PRJ-075) are priced like every other line and
shown where they stand, but they enter no sum: not their group's, not the
project total, not the taxes. ``ProjectPrices.variant_lines`` lists them.

Customer material (PRJ-096) is the customer's own gear, taken along: its
lines get the amount 0 and are marked (``LinePrice.is_customer_material``).
Like a line taken over from another subproject they count as lines of the
project, but they take no share of a group's flat price and appear in no
split by tax rate (see ``projects.customer_material``).

Text lines carry only a text: amount 0, no share in a group's discount or flat price, no tax
(``LinePrice.is_text``).

Lines of a job function with a maximum discount (PER-026) never get more off
than that maximum – neither by their own discount nor by their group's; see
``projects.discounts``.

Worked example (acceptance scenarios 9 and 17)::

    Group "Front truss"    3 lines            420.00
    Group "Rear truss"     2 lines   310.00
                           10 % discount     - 31.00   279.00
    Without group          1 line              50.00
    Surcharge 10 % on both groups (420 + 279)  69.90
    ---------------------------------------------------
    Net total                                 818.90

Nested groups (PRJ-037)
-----------------------
Step 2 works from the bottom up. A group's sum is its own lines plus the
subtotals of its subgroups; then its own discount or flat price applies –
the subgroup's rule first, the parent's on the result. A flat price of a
parent replaces the sum of everything in it. Surcharges inside a group stay
outside that group's own discount (as before), but they are part of its
subtotal and so of what a parent's discount applies to. A subgroup that is
optional or alternative itself is not part of its parent's sum; a subgroup
of an optional or alternative group counts as optional or alternative too
(``Group.effective_kind``)::

    Group "Licht"          lighting desk        450.00
      "Front truss"        3 lines   420.00
      "Rear truss"         2 lines   279.00     699.00
                           together            1149.00
                           5 % discount        - 57.45
    Subtotal "Licht"                           1091.55

A reduction of a parent is spread over every line below it in proportion to
what the line contributes at that point, so a maximum discount (PER-026)
still holds for a line however many groups above it give a discount, and
the net amounts per tax rate stay exact (step 5). The base of a percentage
surcharge is a target's amount after its own discounts – those of the line
and its group, and of the subgroups inside a group target – not after a
discount of a group above it: the amount shown next to the target in the
planning.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Max

from rentalars.core.money import HUNDRED, ZERO, money, percentage_of
from rentalars.masterdata.models import RentalScaleRow, RentalScaleVersion, ScaleTable, TaxRate
from rentalars.products.models import BillingMode, ProductKind
from rentalars.projects.crew import (
    NO_TIMES,
    ApprovedTimes,
    CrewPrice,
    load_crew_lines,
    price_crew_line,
    price_crew_lines,
    surcharge_rules_for,
)
from rentalars.projects.discounts import limited_percent, lowest_amount, maximum_discounts_of_products
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.logistics import Logistics, VehiclePrice, load_logistics, price_logistics
from rentalars.projects.models import (
    CrewLine,
    Group,
    GroupKind,
    LineVariant,
    MaterialLine,
    Project,
    SurchargeTarget,
    SurchargeTargetType,
    TripVehicle,
)
from rentalars.projects.time_surcharges import SurchargeRules


@dataclass
class LinePrice:
    """The calculated price of one material line."""

    line: MaterialLine
    #: Rental days that apply to the line, or ``None`` if it is not billed per day.
    rental_days: int | None = None
    #: Where the rental days come from: one of :class:`DaysSource`, or ``""``.
    rental_days_source: str = ""
    #: Factor from the rental scale, or ``None`` if it is not billed per day.
    scale_factor: Decimal | None = None
    #: True if the scale table was edited after this line was created (PRD-037).
    scale_is_outdated: bool = False
    #: Amount before the line's own discount.
    base_amount: Decimal = ZERO
    discount_amount: Decimal = ZERO
    #: Net amount of the line as shown in the planning.
    amount: Decimal = ZERO
    #: For percentage surcharges: the amount the percentage is taken from.
    surcharge_base: Decimal | None = None
    #: For percentage surcharges: what it refers to, as text.
    surcharge_target_labels: list[str] = field(default_factory=list)
    #: What the supplier charges for a subrental line.
    purchase_cost: Decimal = ZERO
    #: True while the quantity is only an estimate (billing by effort).
    is_estimate: bool = False
    #: PRJ-075: False for optional and alternative lines – priced and shown, but not added up.
    counts: bool = True
    #: PRJ-060: taken over from another subproject; not charged here.
    is_takeover: bool = False
    #: PRJ-096: the customer's own material, taken along; never charged.
    is_customer_material: bool = False
    #: A text line carries only a text – no amount, no share of any group, no tax.
    is_text: bool = False
    #: PER-026: the highest discount the line may get, from its job function; ``None``: no limit.
    max_discount_percent: Decimal | None = None
    #: The line's own discount as it applies: as typed in, cut to the maximum (PER-026).
    discount_percent: Decimal = ZERO
    #: True if the maximum cut the line's own discount or its share of the group's (PER-026).
    discount_is_capped: bool = False
    #: What the line contributes after its group's discount or flat price, if a maximum discount in the
    #: group made the plain proportional share wrong (PER-026); ``None`` otherwise.
    group_share: Decimal | None = None


@dataclass
class _Share:
    """What one line contributes to the sum of a group, as the group's rules leave it (PRJ-037, PER-026).

    ``line_price`` is ``None`` for the flat price of a group without any
    line: it is taxed at the default rate (PRJ-039).
    """

    line_price: LinePrice | None
    amount: Decimal
    #: What the line contributed before the rule of the group that made this share.
    before: Decimal = ZERO
    #: True if a maximum discount (PER-026) fixed the share; a flat price is then spread over the others.
    fixed: bool = False


@dataclass
class GroupPrices:
    """The calculated subtotal of one group."""

    group: Group
    lines: list[LinePrice] = field(default_factory=list)
    #: Sum before the group's discount: its regular lines and the subtotals of its subgroups (PRJ-037).
    lines_total: Decimal = ZERO
    #: Reduction through the group's discount or flat price.
    discount: Decimal = ZERO
    #: Amount after discount or flat price, before surcharges in the group.
    base: Decimal = ZERO
    surcharges_total: Decimal = ZERO
    subtotal: Decimal = ZERO
    #: PER-026: what the maximum discounts of the lines took back from the group's discount or flat price.
    cap_excess: Decimal = ZERO
    #: PRJ-037: the subgroups, in their order, and the level of this group (0 at the top).
    children: list[GroupPrices] = field(default_factory=list, repr=False, compare=False)
    depth: int = 0
    #: Sum of the group's own regular lines, without subgroups (PRJ-037).
    own_lines_total: Decimal = ZERO
    #: Sum of the subtotals of the subgroups that are part of this group's sum (PRJ-037).
    children_total: Decimal = ZERO
    #: What every line below this group contributes to its subtotal; adds up to the subtotal exactly.
    shares: list[_Share] = field(default_factory=list, repr=False, compare=False)

    @property
    def counts_toward_total(self) -> bool:
        """Optional and alternative groups are shown but not added up (PRJ-040) – nor their subgroups (PRJ-037)."""
        return self.group.counts_toward_total

    @property
    def adds_to_parent(self) -> bool:
        """Whether the subtotal goes into the sum of the group above – or, at the top, the project total.

        A group that is optional or alternative itself stays outside, like
        an optional line stays outside its group's sum (PRJ-037, PRJ-075).
        """
        return self.group.kind == GroupKind.NORMAL


@dataclass
class TaxLine:
    """Net amount and tax for one tax rate."""

    tax_rate: TaxRate
    net: Decimal
    tax: Decimal


@dataclass
class ProjectPrices:
    """All sums of a project (PRJ-024, PRJ-034)."""

    project: Project
    #: Every group in the order of the planning: a group, its subgroups, the next group (PRJ-037).
    groups: list[GroupPrices] = field(default_factory=list)
    ungrouped: list[LinePrice] = field(default_factory=list)
    surcharges: list[LinePrice] = field(default_factory=list)
    by_line_id: dict[int, LinePrice] = field(default_factory=dict)
    by_group_id: dict[int, GroupPrices] = field(default_factory=dict)

    #: The crew lines with price and cost, in display order (PRJ-038).
    crew: list[CrewPrice] = field(default_factory=list)
    #: LOG-009: the bookings of vehicles and trailers with price and cost, in their order.
    logistics: list[VehiclePrice] = field(default_factory=list)
    #: LOG-007: the vehicles on the trips of the project, as loaded for the calculation.
    trip_vehicles: list[TripVehicle] = field(default_factory=list)

    groups_total: Decimal = ZERO
    ungrouped_total: Decimal = ZERO
    #: What the customer pays for the crew (PRJ-051).
    personnel_total: Decimal = ZERO
    #: LOG-009: what the customer pays for vehicles and trailers, after their discounts.
    logistics_total: Decimal = ZERO
    surcharges_total: Decimal = ZERO
    #: PRJ-123: the sum of groups, lines, personnel, logistics and surcharges before the overall discount,
    #: and what the project's overall discount takes off it (both zero without one).
    net_before_overall_discount: Decimal = ZERO
    overall_discount: Decimal = ZERO
    optional_total: Decimal = ZERO
    #: PRJ-075: optional and alternative lines, wherever they stand, with their sums.
    variant_lines: list[LinePrice] = field(default_factory=list)
    optional_lines_total: Decimal = ZERO
    alternative_lines_total: Decimal = ZERO

    #: Sum of all amounts before any discount, for the line "material net".
    material_before_discount: Decimal = ZERO
    discount_total: Decimal = ZERO
    net_total: Decimal = ZERO
    tax_lines: list[TaxLine] = field(default_factory=list)
    tax_total: Decimal = ZERO
    gross_total: Decimal = ZERO

    #: PRJ-025: internal costs and what remains.
    subrental_cost: Decimal = ZERO
    #: Planned cost of the crew: hourly rates and flat rates (PRJ-021, PER-018).
    personnel_cost: Decimal = ZERO
    #: LOG-010: the internal costs of the vehicles – per kilometre and day, or what a supplier charges.
    logistics_cost: Decimal = ZERO
    #: What the approved times of the crew actually cost.
    personnel_actual_cost: Decimal = ZERO
    #: PER-009: the surcharges for night, Sunday and holidays in ``personnel_total``, before discounts.
    personnel_time_surcharges: Decimal = ZERO
    #: PRJ-025: net minus subrentals, planned personnel and logistics; the margin subtracts the expenses as well.
    margin_before_expenses: Decimal = ZERO
    #: ZEI-019: the approved expenses and travel costs, if the caller loaded them (``PriceLookups.expenses``);
    #: otherwise :attr:`expenses_cost` reads them when first asked – one query, only where they are shown.
    expenses_loaded: Decimal | None = None

    has_estimates: bool = False
    outdated_scale_lines: int = 0
    #: PER-026: material and crew lines whose discount the maximum of their job function cut.
    capped_discount_lines: int = 0

    @property
    def expenses_cost(self) -> Decimal:
        """ZEI-019: the approved expenses and travel costs of the project – costs like the crew's (PRJ-025)."""
        if self.expenses_loaded is None:
            # The planning page loads the sum with the project (``expenses.approved_expenses_total``).
            noted = getattr(self.project, "approved_expenses_total", None)
            if noted is not None:
                self.expenses_loaded = money(noted)
            else:
                from rentalars.timetracking.expenses import approved_expense_sums

                self.expenses_loaded = approved_expense_sums([self.project.pk]).get(self.project.pk, ZERO)
        return self.expenses_loaded

    @property
    def contribution_margin(self) -> Decimal:
        """PRJ-025, PRJ-087: what remains after the supplier, the crew and their expenses (ZEI-019) are paid."""
        return self.margin_before_expenses - self.expenses_cost


@dataclass
class PriceLookups:
    """What the calculation looks up besides lines, groups and crew – loaded once for many projects (PRJ-085).

    The project list shows sums of every project on a page; given these, the
    calculation of all of them needs no query of its own
    (``projects.list_sums``). Each is what the calculation of one project
    would load for its lines.
    """

    #: Rental scale tables by version (:func:`load_scale_tables`).
    tables: dict[int, ScaleTable]
    #: Versions with a newer version of the same scale (:func:`outdated_version_ids`).
    outdated: set[int]
    #: Maximum discount per service product (PER-026).
    maximum_discounts: dict[int, Decimal]
    #: What each percentage surcharge refers to, by surcharge line.
    targets_by_line: dict[int, list[SurchargeTarget]]
    #: Approved hours and their cost per crew line (ZEI-021).
    approved: dict[int, ApprovedTimes]
    #: PER-009: the settings of the surcharges for night, Sunday and holidays; ``None``: read when a line needs them.
    time_surcharges: SurchargeRules | None = None
    #: ZEI-019: approved expenses per project (``timetracking.expenses.approved_expense_sums``); ``None``: read
    #: when the margin of a project is asked for.
    expenses: dict[int, Decimal] | None = None
    #: LOG-009: the bookings of vehicles and their trips per project (``logistics.load_logistics_of``);
    #: their scale versions are among ``tables``. ``None``: loaded per project.
    logistics: dict[int, Logistics] | None = None


class DaysSource:
    """Where the rental days of a line come from; shown next to the number (PRJ-062)."""

    LINE = "line"  # typed in on the line
    PERIOD = "period"  # counted from the line's own period
    GROUP = "group"  # typed in on the group
    PROJECT = "project"  # the project's rental days


def resolve_rental_days_with_source(line: MaterialLine, group: Group | None, project: Project) -> tuple[int, str]:
    """Return the rental days that apply to a line and where they come from (PRJ-005, PRJ-062).

    The most specific entry wins:

    1. rental days typed in on the line;
    2. the line's own period, if it differs from the project's: every started
       24 hours count as one day. Moving a line to other dates therefore
       changes its price without anyone having to remember the rental days;
    3. rental days typed in on the group – or, for a subgroup without any,
       on the nearest group above it (PRJ-037);
    4. the rental days of the project (typed in, or suggested from the event
       period).

    Example: the project runs Friday to Sunday with 2 rental days. A line that
    is moved to Friday 10:00 until Saturday 10:00 is charged 1 day; a line
    that stays with the project is charged 2.
    """
    if line.rental_days:
        return line.rental_days, DaysSource.LINE
    if line.has_own_period(project):
        return line.days_of_own_period, DaysSource.PERIOD
    group_days = group.effective_rental_days if group is not None else None
    if group_days:
        return group_days, DaysSource.GROUP
    return project.effective_rental_days, DaysSource.PROJECT


def resolve_rental_days(line: MaterialLine, group: Group | None, project: Project) -> int:
    """Return the rental days that apply to a line; see :func:`resolve_rental_days_with_source`."""
    return resolve_rental_days_with_source(line, group, project)[0]


def load_scale_tables(version_ids: set[int]) -> dict[int, ScaleTable]:
    """Load the rows of several rental scale versions with two queries."""
    if not version_ids:
        return {}
    increments = dict(RentalScaleVersion.objects.filter(pk__in=version_ids).values_list("pk", "extra_day_increment"))
    rows: dict[int, list[tuple[int, Decimal]]] = defaultdict(list)
    for version_id, days, factor in RentalScaleRow.objects.filter(version_id__in=version_ids).values_list(
        "version_id", "days", "factor"
    ):
        rows[version_id].append((days, factor))
    return {
        version_id: ScaleTable(rows=rows.get(version_id, []), extra_day_increment=increment)
        for version_id, increment in increments.items()
    }


def outdated_version_ids(version_ids: set[int]) -> set[int]:
    """Return those versions for which a newer version of the same scale exists."""
    if not version_ids:
        return set()
    versions = list(RentalScaleVersion.objects.filter(pk__in=version_ids).values_list("pk", "scale_id", "number"))
    newest = dict(
        RentalScaleVersion.objects.filter(scale_id__in={scale_id for _pk, scale_id, _number in versions})
        .values("scale_id")
        .annotate(newest=Max("number"))
        .values_list("scale_id", "newest")
    )
    return {pk for pk, scale_id, number in versions if number < newest.get(scale_id, number)}


def line_amount(line: MaterialLine, rental_days: int | None, scale_factor: Decimal | None) -> Decimal:
    """Calculate the amount of a line before its discount (PRD-033).

    =================  ==========================================
    billing mode       amount
    =================  ==========================================
    daily rental       quantity × daily price × scale factor
    flat               quantity × price
    by the hour        quantity × hours × price
    by effort          quantity × price (quantity = effort)
    sale               quantity × sale price
    =================  ==========================================

    Example: 4 spotlights at 20.00 per day for 2 rental days with the factor
    1.5 cost 4 × 20.00 × 1.5 = 120.00 (acceptance scenario 17).
    """
    amount = line.quantity * line.unit_price
    if line.is_sale:
        return money(amount)
    if line.billing_mode in BillingMode.daily_modes():
        return money(amount * (scale_factor if scale_factor is not None else Decimal("1")))
    if line.billing_mode == BillingMode.HOURLY:
        return money(amount * (line.hours if line.hours is not None else Decimal("1")))
    return money(amount)


def compute_project_prices(
    project: Project,
    *,
    lines: list[MaterialLine] | None = None,
    groups: list[Group] | None = None,
    crew: list[CrewLine] | None = None,
    lookups: PriceLookups | None = None,
    logistics: Logistics | None = None,
) -> ProjectPrices:
    """Calculate all line amounts, subtotals and totals of a project.

    Args:
        project: The project to calculate.
        lines: The project's lines if the caller already loaded them (with
            ``select_related("product", "tax_rate")``); otherwise they are
            loaded here.
        groups: The project's groups if already loaded.
        crew: The project's crew lines if already loaded.
        logistics: The project's vehicle bookings and their trips if already loaded (LOG-009).
        lookups: Scale tables, maximum discounts, surcharge targets and
            approved hours, if the caller loaded them for several projects
            at once (PRJ-085); otherwise they are loaded here.

    Returns:
        A :class:`ProjectPrices` with one :class:`LinePrice` per line and one
        :class:`GroupPrices` per group. See the module description for the
        calculation steps.
    """
    if groups is None:
        groups = list(project.groups.all())
    if lines is None:
        lines = list(
            project.material_lines.select_related("product", "product__category", "tax_rate", "unit", "supplier")
        )

    prices = ProjectPrices(project=project)
    # PRJ-037: the groups as a tree – in the order of the planning, each knowing its subgroups.
    tree = GroupTree(groups)
    group_by_id = tree.by_id
    group_prices = {group.pk: GroupPrices(group=group, depth=tree.depth[group.pk]) for group in tree.ordered}
    for group in tree.ordered:
        parent = tree.parent_of(group)
        if parent is not None:
            group_prices[parent.pk].children.append(group_prices[group.pk])
    prices.groups = [group_prices[group.pk] for group in tree.ordered]
    prices.by_group_id = group_prices

    if lookups is not None:
        tables, outdated, maximum_discounts = lookups.tables, lookups.outdated, lookups.maximum_discounts
    else:
        version_ids = {line.scale_version_id for line in lines if line.scale_version_id}
        tables = load_scale_tables(version_ids)
        outdated = outdated_version_ids(version_ids)
        # PER-026: only service products can be limited; without such a line no query is needed.
        maximum_discounts = maximum_discounts_of_products(
            line.product_id for line in lines if line.product_id and line.product.kind == ProductKind.SERVICE
        )

    # Step 1: every line except percentage surcharges.
    for line in lines:
        group = group_by_id.get(line.group_id) if line.group_id else None
        line_price = _price_single_line(line, group, project, tables, outdated, maximum_discounts)
        prices.by_line_id[line.pk] = line_price
        if group is not None:
            group_prices[group.pk].lines.append(line_price)
        elif line.is_surcharge:
            prices.surcharges.append(line_price)
        else:
            prices.ungrouped.append(line_price)
        if not line_price.counts:
            prices.variant_lines.append(line_price)
        prices.has_estimates = prices.has_estimates or line_price.is_estimate
        if line_price.scale_is_outdated:
            prices.outdated_scale_lines += 1

    # Personnel: priced on its own, before the surcharges that may refer to it.
    if lookups is not None:
        crew = crew if crew is not None else load_crew_lines(project)
        rules = lookups.time_surcharges or surcharge_rules_for(crew)  # PER-009
        prices.crew = [price_crew_line(line, lookups.approved.get(line.pk, NO_TIMES), rules) for line in crew]
    else:
        prices.crew = price_crew_lines(project, crew)
    prices.personnel_total = sum((crew_price.amount for crew_price in prices.crew), ZERO)
    prices.personnel_cost = sum((crew_price.cost for crew_price in prices.crew), ZERO)
    prices.personnel_actual_cost = sum((crew_price.actual_cost for crew_price in prices.crew), ZERO)
    # PER-009: the surcharges for night, Sunday and holidays in it, before discounts.
    prices.personnel_time_surcharges = sum((crew_price.time_surcharge_amount for crew_price in prices.crew), ZERO)
    prices.has_estimates = prices.has_estimates or any(crew_price.is_estimate for crew_price in prices.crew)

    # Logistics (LOG-009): priced on its own as well, by kilometres and days.
    if logistics is None:
        known = lookups.logistics if lookups is not None else None
        logistics = known.get(project.pk, Logistics()) if known is not None else load_logistics(project)
    if logistics.lines:
        missing = {line.scale_version_id for line in logistics.lines if line.scale_version_id} - set(tables)
        if missing:
            tables = {**tables, **load_scale_tables(missing)}
        prices.logistics = price_logistics(project, logistics, tables)
        prices.trip_vehicles = logistics.uses
    prices.logistics_total = sum((vehicle_price.amount for vehicle_price in prices.logistics), ZERO)
    prices.logistics_cost = sum((vehicle_price.cost for vehicle_price in prices.logistics), ZERO)
    prices.has_estimates = prices.has_estimates or any(vehicle_price.is_estimate for vehicle_price in prices.logistics)

    # Steps 2 to 4 inside the groups, level by level from the bottom up (PRJ-037): a group's sum needs
    # the subtotals of its subgroups. Within one level, first every base after discount or flat price,
    # then the percentage surcharges inside the groups on the amounts after discount (PRD-039), then
    # the subtotals. Without subgroups this is the order of the steps above.
    targets_by_line = lookups.targets_by_line if lookups is not None else _load_surcharge_targets(lines)
    ungrouped_base = sum((lp.amount for lp in prices.ungrouped if lp.counts), ZERO)
    project_base: Decimal | None = None
    for depth in sorted({group_price.depth for group_price in prices.groups}, reverse=True):
        level = [group_price for group_price in prices.groups if group_price.depth == depth]
        for group_price in level:
            _apply_group_adjustment(group_price)
        if depth == 0:
            # The base for "whole project": everything that counts, without surcharges – the material,
            # the personnel and the logistics (PRD-031, LOG-009); no optional or alternative line (PRJ-075).
            project_base = (
                sum((gp.base for gp in level if gp.adds_to_parent), ZERO)
                + ungrouped_base
                + prices.personnel_total
                + prices.logistics_total
            )
        for group_price in level:
            in_group = [lp.line for lp in group_price.lines if lp.line.is_percent_surcharge]
            _price_percent_surcharges(prices, group_prices, in_group, targets_by_line, project_base)
            _finish_group(group_price)
    if project_base is None:
        project_base = ungrouped_base + prices.personnel_total + prices.logistics_total

    # Step 3 for the surcharges of the project's own block.
    project_surcharges = [lp.line for lp in prices.surcharges if lp.line.is_percent_surcharge]
    _price_percent_surcharges(prices, group_prices, project_surcharges, targets_by_line, project_base)

    # Step 4: the project total (PRJ-034). Optional and alternative lines stay outside (PRJ-075), and so do
    # optional and alternative groups – at whatever level they stand (PRJ-040, PRJ-037).
    for group_price in prices.groups:
        if not group_price.adds_to_parent:
            prices.optional_total += group_price.subtotal
        elif group_price.depth == 0:
            prices.groups_total += group_price.subtotal
    prices.ungrouped_total = ungrouped_base
    prices.surcharges_total = sum((lp.amount for lp in prices.surcharges if lp.counts), ZERO)
    prices.net_total = (
        prices.groups_total
        + prices.ungrouped_total
        + prices.personnel_total
        + prices.logistics_total
        + prices.surcharges_total
    )
    # PRJ-123: the overall discount of the project, taken off the whole sum.
    prices.net_before_overall_discount = prices.net_total
    prices.overall_discount = overall_discount_of(project, prices.net_total)
    prices.net_total -= prices.overall_discount
    for line_price in prices.variant_lines:
        if line_price.line.variant == LineVariant.ALTERNATIVE:
            prices.alternative_lines_total += line_price.amount
        else:
            prices.optional_lines_total += line_price.amount
    prices.capped_discount_lines = (
        sum(1 for lp in prices.by_line_id.values() if lp.discount_is_capped)
        + sum(1 for crew_price in prices.crew if crew_price.discount_is_capped)
        + sum(1 for vehicle_price in prices.logistics if vehicle_price.discount_is_capped)
    )

    _sum_discounts_and_costs(prices)
    if lookups is not None and lookups.expenses is not None:
        prices.expenses_loaded = lookups.expenses.get(project.pk, ZERO)  # ZEI-019, loaded for many projects

    # Step 5: tax per tax rate (PRJ-024).
    prices.tax_lines = _tax_lines(prices)
    prices.tax_total = sum((tax_line.tax for tax_line in prices.tax_lines), ZERO)
    prices.gross_total = prices.net_total + prices.tax_total
    return prices


def _price_single_line(
    line: MaterialLine,
    group: Group | None,
    project: Project,
    tables: dict[int, ScaleTable],
    outdated: set[int],
    maximum_discounts: dict[int, Decimal] | None = None,
) -> LinePrice:
    """Step 1 for one line: rental days, scale factor, amount and discount.

    The discount is the line's own, cut to the maximum discount of its job
    function if its product is a job function's service product (PER-026),
    and to the product's own maximum discount (PRD-041); the stricter counts.
    """
    maximum = (maximum_discounts or {}).get(line.product_id) if line.product_id else None
    # PRD-041: the product is loaded with the line, so its own maximum costs no query.
    own_maximum = line.product.max_discount_percent if line.product_id else None
    if own_maximum is not None and (maximum is None or own_maximum < maximum):
        maximum = own_maximum
    line_price = LinePrice(
        line=line,
        is_estimate=line.quantity_is_estimate,
        counts=line.counts_toward_total,
        max_discount_percent=maximum,
        discount_percent=limited_percent(line.discount_percent, maximum),
    )
    line_price.discount_is_capped = line_price.discount_percent < line.discount_percent
    if line.is_subrental and line.purchase_price is not None:
        line_price.purchase_cost = money(line.quantity * line.purchase_price)

    if line.is_text:
        # A text line is worth nothing and is part of no sum.
        line_price.is_text = True
        return line_price

    if line.is_percent_surcharge:
        return line_price  # calculated in step 3, once its targets are known

    if line.is_covering_subrental:
        # PRJ-055: a subrental that only covers a shortage is not charged; the
        # customer pays for the original line.
        return line_price

    if line.is_customer_material:
        # PRJ-096: the customer's own material is taken along, never charged.
        line_price.is_customer_material = True
        return line_price

    if line.is_takeover:
        # PRJ-060: pieces taken over from another subproject are charged once, on the line they come from.
        line_price.is_takeover = True
        return line_price

    if line.uses_rental_days:
        line_price.rental_days, line_price.rental_days_source = resolve_rental_days_with_source(line, group, project)
        line_price.scale_factor = _scale_factor(line, line_price.rental_days, tables)
        line_price.scale_is_outdated = line.manual_scale_factor is None and line.scale_version_id in outdated

    line_price.base_amount = line_amount(line, line_price.rental_days, line_price.scale_factor)
    line_price.discount_amount = percentage_of(line_price.base_amount, line_price.discount_percent)
    line_price.amount = line_price.base_amount - line_price.discount_amount
    return line_price


def _scale_factor(line: MaterialLine, rental_days: int, tables: dict[int, ScaleTable]) -> Decimal:
    """Return the factor for a line: set by hand, from its scale version, or the number of days (PRD-036).

    Without a scale every day counts in full (manual, section 8; the vehicles do the same): 5 days are the factor 5.
    """
    if line.manual_scale_factor is not None:
        return line.manual_scale_factor
    table = tables.get(line.scale_version_id) if line.scale_version_id else None
    if table is None:
        return Decimal(max(rental_days, 1))
    return table.factor_for(rental_days)


def _apply_group_adjustment(group_price: GroupPrices) -> None:
    """Step 2: apply the discount or flat price of a group (PRJ-039).

    The sum of a group is the amount of its regular lines plus the subtotals
    of its subgroups (PRJ-037) – of those that count: an optional or
    alternative subgroup stays outside, as optional and alternative lines do
    (PRJ-075). Lines with a maximum discount take only as much of the
    group's reduction as their maximum leaves (PER-026, see
    :func:`_limit_group_reduction`) – also lines deep down in a subgroup.
    """
    group = group_price.group
    # PRJ-096: customer material is no part of the sum, so a flat price is never spread onto it.
    regular = [
        lp
        for lp in group_price.lines
        if not lp.line.is_surcharge and lp.counts and not lp.is_customer_material and not lp.is_text
    ]
    counted_children = [child for child in group_price.children if child.adds_to_parent]
    group_price.own_lines_total = sum((lp.amount for lp in regular), ZERO)
    group_price.children_total = sum((child.subtotal for child in counted_children), ZERO)
    group_price.lines_total = group_price.own_lines_total + group_price.children_total

    if group.flat_price is not None:
        group_price.base = group.flat_price
        group_price.discount = max(group_price.lines_total - group.flat_price, ZERO)
    elif group.discount_percent is not None:
        group_price.discount = percentage_of(group_price.lines_total, group.discount_percent)
        group_price.base = group_price.lines_total - group_price.discount
    elif group.discount_amount is not None:
        # A discount can at most bring the group down to zero.
        group_price.discount = min(group.discount_amount, group_price.lines_total)
        group_price.base = group_price.lines_total - group_price.discount
    else:
        group_price.base = group_price.lines_total

    # What each line contributes before this group's rule: its own amount, or for a line in a
    # subgroup what that subgroup's rules left of it.
    items = [_Share(lp, lp.amount) for lp in regular]
    items += [_Share(share.line_price, share.amount) for child in counted_children for share in child.shares]
    group_price.shares = _limit_group_reduction(group_price, items)


def _limit_group_reduction(group_price: GroupPrices, items: list[_Share]) -> list[_Share]:
    """Keep the share of a group's reduction within the maximum discount of each line (PER-026).

    The reduction – discount or flat price below the sum of the lines – is
    spread over the lines in proportion to their amounts. A line with a
    maximum discount takes at most what brings it down to its lowest amount
    (amount before discounts less the maximum). The rest is not passed on to
    other lines: the group's reduction becomes smaller by it, and the group
    costs that much more.

    With subgroups (PRJ-037) the "amount" of a line in a subgroup is what
    the subgroup's rules left of it, and its lowest amount is still taken
    from its amount before *any* discount: however many groups above it
    give a discount, the line never gets more off than its maximum.

    Example: desk 400.00 and sound engineer 100.00 (maximum 5 %), group
    discount 10 % = 50.00. The engineer's share would be 10.00 but may only
    be 5.00; the group's discount becomes 45.00 and its base 455.00.

    Returns:
        What each item contributes after the reduction, in the same order.
    """
    reduction = group_price.lines_total - group_price.base
    limited = [
        item for item in items if item.line_price is not None and item.line_price.max_discount_percent is not None
    ]
    if reduction <= ZERO or not limited or group_price.lines_total == ZERO:
        factor = group_price.base / group_price.lines_total if group_price.lines_total else Decimal("1")
        return [_Share(item.line_price, item.amount * factor, before=item.amount) for item in items]
    own = {id(line_price) for line_price in group_price.lines}
    excess = Decimal("0")
    after: list[_Share] = []
    for item in items:
        share = item.amount * reduction / group_price.lines_total
        line_price = item.line_price
        is_limited = line_price is not None and line_price.max_discount_percent is not None
        if is_limited:
            allowed = max(item.amount - lowest_amount(line_price.base_amount, line_price.max_discount_percent), ZERO)
            if share > allowed:
                excess += share - allowed
                share = allowed
                line_price.discount_is_capped = True
        if line_price is not None and id(line_price) in own:
            line_price.group_share = item.amount - share
        after.append(_Share(line_price, item.amount - share, before=item.amount, fixed=is_limited))
    group_price.cap_excess = money(excess)
    group_price.base += group_price.cap_excess
    group_price.discount -= group_price.cap_excess
    return after


def _share_after_group_adjustment(line_price: LinePrice, group_price: GroupPrices | None) -> Decimal:
    """Return what a line contributes once the discount of its group is applied.

    The group discount is spread over the lines in proportion to their
    amounts – unless a maximum discount in the group made the shares differ
    (PER-026); then each line knows its own. Needed when a surcharge refers
    to single lines. A discount of a group above the line's group does not
    count here (PRJ-037, see the module text).
    """
    if line_price.group_share is not None:
        return line_price.group_share
    if group_price is None or group_price.lines_total == ZERO:
        return line_price.amount
    return line_price.amount * group_price.base / group_price.lines_total


def _load_surcharge_targets(lines: list[MaterialLine]) -> dict[int, list[SurchargeTarget]]:
    """What the percentage surcharges among the lines refer to, with one query – none without such a line."""
    surcharge_lines = [line for line in lines if line.is_percent_surcharge]
    targets_by_line: dict[int, list[SurchargeTarget]] = defaultdict(list)
    if surcharge_lines:
        for target in SurchargeTarget.objects.filter(surcharge_line__in=surcharge_lines).select_related(
            "target_line", "target_group"
        ):
            targets_by_line[target.surcharge_line_id].append(target)
    return targets_by_line


def _price_percent_surcharges(
    prices: ProjectPrices,
    group_prices: dict[int, GroupPrices],
    surcharge_lines: list[MaterialLine],
    targets_by_line: dict[int, list[SurchargeTarget]],
    project_base: Decimal | None,
) -> None:
    """Step 3: calculate percentage surcharges from their targets (PRD-031, PRD-039).

    All surcharges are calculated from the same amounts – those after
    discounts and without any surcharge. Two surcharges on the same target
    therefore stand side by side; none is charged on top of another.

    Args:
        prices: The prices calculated so far.
        group_prices: The groups by ID.
        surcharge_lines: The percentage surcharges to calculate now.
        targets_by_line: What each surcharge refers to (:func:`_load_surcharge_targets`).
        project_base: The base for "the whole project"; ``None`` while it
            cannot be known yet – for a surcharge inside a subgroup, whose
            own group is part of it (PRJ-037). Such a surcharge counts
            nothing for the project; a surcharge on the whole project
            belongs into the project's block anyway (PRJ-058).
    """
    for line in surcharge_lines:
        line_price = prices.by_line_id[line.pk]
        is_project_level = line.group_id is None
        base = ZERO
        for target in targets_by_line.get(line.pk, []):
            amount, label = _target_amount(
                target, prices, group_prices, project_base, is_project_level, surcharge_counts=line_price.counts
            )
            base += amount
            line_price.surcharge_target_labels.append(label)
        line_price.surcharge_base = money(base)
        line_price.base_amount = percentage_of(line_price.surcharge_base, line.surcharge_percent or ZERO)
        line_price.discount_amount = percentage_of(line_price.base_amount, line_price.discount_percent)
        line_price.amount = line_price.base_amount - line_price.discount_amount


def _target_amount(
    target: SurchargeTarget,
    prices: ProjectPrices,
    group_prices: dict[int, GroupPrices],
    project_base: Decimal | None,
    is_project_level: bool,
    *,
    surcharge_counts: bool = True,
) -> tuple[Decimal, str]:
    """Return the amount one target contributes to a surcharge's base, and its label.

    A surcharge in the project's surcharge block only counts targets that are
    part of the project total; an optional group contributes nothing there.
    An optional or alternative line (PRJ-075) contributes only to a surcharge
    that is optional or alternative itself – the surcharge that comes with it
    if the customer chooses it.
    """
    if target.target_type == SurchargeTargetType.PROJECT:
        return project_base if project_base is not None else ZERO, str(SurchargeTargetType.PROJECT.label)
    if target.target_type == SurchargeTargetType.PERSONNEL:
        return prices.personnel_total, str(SurchargeTargetType.PERSONNEL.label)
    if target.target_type == SurchargeTargetType.GROUP and target.target_group_id in group_prices:
        group_price = group_prices[target.target_group_id]
        # PRJ-037: the group's amount after its own rules (and those of its subgroups), as the planning shows it.
        if is_project_level and not group_price.counts_toward_total:
            return ZERO, group_price.group.name
        return group_price.base, group_price.group.name
    if target.target_type == SurchargeTargetType.LINE and target.target_line_id in prices.by_line_id:
        target_price = prices.by_line_id[target.target_line_id]
        if target_price.line.is_surcharge:
            return ZERO, target_price.line.title  # never a surcharge on a surcharge
        if surcharge_counts and not target_price.counts:
            return ZERO, target_price.line.title
        group_price = group_prices.get(target_price.line.group_id) if target_price.line.group_id else None
        if is_project_level and group_price is not None and not group_price.counts_toward_total:
            return ZERO, target_price.line.title
        return _share_after_group_adjustment(target_price, group_price), target_price.line.title
    return ZERO, ""


def _finish_group(group_price: GroupPrices) -> None:
    """Step 4 for one group: add the surcharges that sit inside the group, and note what every line contributes.

    The contributions (``GroupPrices.shares``) add up to the subtotal. The
    group above takes them as its starting point (PRJ-037), and the split
    by tax rate of step 5 is made from those of the top-level groups.
    """
    surcharges = [lp for lp in group_price.lines if lp.line.is_surcharge and lp.counts]
    group_price.surcharges_total = sum((lp.amount for lp in surcharges), ZERO)
    if group_price.group.flat_price is None:
        group_price.subtotal = group_price.base + group_price.surcharges_total
        group_price.shares += [_Share(lp, lp.amount, before=lp.amount) for lp in surcharges]
        return
    # A flat price is the price of the whole group, surcharges included – raised by what the
    # maximum discounts of its lines did not allow to take off (PER-026).
    group_price.subtotal = group_price.group.flat_price + group_price.cap_excess
    # Lines with a maximum discount carry exactly their share; the rest of the flat price is
    # split over the others in proportion to what they contributed before (PER-026).
    fixed = [share for share in group_price.shares if share.fixed]
    others = [share for share in group_price.shares if not share.fixed]
    others += [_Share(lp, lp.amount, before=lp.amount) for lp in surcharges]
    if not fixed and not others:
        # A flat price without any line: taxed at the default rate (PRJ-039).
        group_price.shares = [_Share(None, group_price.subtotal)]
        return
    remaining = group_price.subtotal - sum((share.amount for share in fixed), ZERO)
    calculated = sum((share.before for share in others), ZERO)
    for share in others:
        # Nothing to take the proportion from: split evenly.
        share.amount = remaining / len(others) if calculated == ZERO else share.before * remaining / calculated
    group_price.shares = fixed + others


def overall_discount_of(project: Project, net: Decimal) -> Decimal:
    """What the overall discount of the project takes off ``net`` (PRJ-123).

    A percentage is taken of the sum, rounded to the cent; an amount is taken
    as it is but never more than the sum – the project does not become
    negative through its discount. Nothing is taken off a sum that is zero or
    below.
    """
    if net <= ZERO:
        return ZERO
    percent, amount = project.overall_discount_percent, project.overall_discount_amount
    if percent:
        return discount_for_percent(net, percent)
    if amount:
        return min(money(amount), net)
    return ZERO


def discount_for_percent(net: Decimal, percent: Decimal) -> Decimal:
    """What a percentage takes off ``net``: rounded to the cent, never more than ``net`` (PRJ-123)."""
    return min(money(net * percent / HUNDRED), net)


def totals_after_overall_discount(prices: ProjectPrices, discount: Decimal) -> tuple[Decimal, Decimal]:
    """The net and the gross total if the overall discount took ``discount`` off the sum before it.

    (discount target; PRJ-123.) Works on the prices of a project calculated with any overall discount –
    the sum before it and the shares per tax rate do not depend on it – and splits the reduced sum by tax rate
    exactly as :func:`compute_project_prices` does, so the figures are those the project will show.
    """
    probe = copy.copy(prices)
    probe.overall_discount = discount
    probe.net_total = prices.net_before_overall_discount - discount
    tax = sum((tax_line.tax for tax_line in _tax_lines(probe)), ZERO)
    return probe.net_total, probe.net_total + tax


def _sum_discounts_and_costs(prices: ProjectPrices) -> None:
    """Add up the informational sums: amounts before discount, discounts, costs.

    Optional and alternative lines are left out (PRJ-075), and so are
    optional and alternative groups with everything below them (PRJ-040,
    PRJ-037); the discounts of crew lines are part of the discounts
    (PER-026). With nested groups the discount of every level counts once:
    a parent's discount is taken from what its subgroups' discounts left.
    """
    counted_lines: list[LinePrice] = list(prices.ungrouped) + list(prices.surcharges)
    group_discounts = ZERO
    for group_price in prices.groups:
        if not group_price.counts_toward_total:
            continue
        counted_lines.extend(group_price.lines)
        if group_price.group.flat_price is not None:
            # With a flat price, the "discount" is whatever the flat price
            # undercuts the calculated sum of lines and surcharges by.
            calculated = group_price.lines_total + group_price.surcharges_total
            group_discounts += max(calculated - group_price.subtotal, ZERO)
        else:
            group_discounts += group_price.discount
    counted_lines = [lp for lp in counted_lines if lp.counts]

    prices.material_before_discount = sum((lp.base_amount for lp in counted_lines), ZERO)
    prices.discount_total = (
        sum((lp.discount_amount for lp in counted_lines), ZERO)
        + group_discounts
        + sum((crew_price.discount_amount for crew_price in prices.crew), ZERO)
        + sum((vehicle_price.discount_amount for vehicle_price in prices.logistics), ZERO)
    )
    prices.subrental_cost = sum((lp.purchase_cost for lp in counted_lines), ZERO)
    # PRJ-025: what remains after the supplier, the crew and the vehicles (LOG-010) are paid.
    # The expenses of the crew (ZEI-019) are subtracted by ``ProjectPrices.contribution_margin``.
    prices.margin_before_expenses = (
        prices.net_total - prices.subrental_cost - prices.personnel_cost - prices.logistics_cost
    )


def _tax_lines(prices: ProjectPrices) -> list[TaxLine]:
    """Step 5: split the net total by tax rate and calculate the tax.

    A group discount or flat price lowers all lines of the group in the same
    proportion, so each tax rate carries its fair share of the reduction –
    with nested groups (PRJ-037) through every level, see
    :func:`_finish_group` – and so does the overall discount of the project
    (PRJ-123). Rounding differences of a cent are put on the
    largest share, so that the net amounts per tax rate always add up
    exactly to the net total.
    """
    shares: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    tax_rates: dict[int, TaxRate] = {}

    def add(tax_rate: TaxRate, amount: Decimal) -> None:
        tax_rates[tax_rate.pk] = tax_rate
        shares[tax_rate.pk] += amount

    for line_price in list(prices.ungrouped) + list(prices.surcharges):
        if line_price.counts and not line_price.is_customer_material and not line_price.is_text:  # PRJ-096: no tax
            add(line_price.line.tax_rate, line_price.amount)

    for crew_price in prices.crew:
        add(crew_price.line.tax_rate, crew_price.amount)

    for vehicle_price in prices.logistics:  # LOG-009
        add(vehicle_price.line.tax_rate, vehicle_price.amount)

    default_rate: TaxRate | None = None
    for group_price in prices.groups:
        if group_price.depth != 0 or not group_price.adds_to_parent:
            continue  # subgroups are part of their top-level group's shares
        for share in group_price.shares:
            if share.line_price is not None:
                add(share.line_price.line.tax_rate, share.amount)
                continue
            # A flat price without any line: taxed at the default rate.
            default_rate = default_rate or TaxRate.get_default()
            if default_rate is not None:
                add(default_rate, share.amount)

    if prices.overall_discount:
        # PRJ-123: the overall discount lowers every rate in the same proportion.
        factor = prices.net_total / prices.net_before_overall_discount
        shares = defaultdict(lambda: Decimal("0"), {pk: amount * factor for pk, amount in shares.items()})
    rounded = {pk: money(amount) for pk, amount in shares.items()}
    difference = prices.net_total - sum(rounded.values(), ZERO)
    if rounded and difference != ZERO:
        largest = max(rounded, key=lambda pk: abs(rounded[pk]))
        rounded[largest] += difference

    tax_lines = [
        TaxLine(tax_rate=tax_rates[pk], net=net, tax=money(net * tax_rates[pk].rate / HUNDRED))
        for pk, net in rounded.items()
    ]
    tax_lines.sort(key=lambda tax_line: -tax_line.tax_rate.rate)
    return tax_lines
