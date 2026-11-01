# SPDX-License-Identifier: GPL-3.0-or-later
"""The overall discount by a target amount ("Zielbetrag netto / brutto"; PRJ-123).

The requirement: next to the overall discount in percent or euro, two options (one for net, one for gross) to enter a target amount; the percentage is adjusted automatically.

The user types the total the project should come to – net or gross, after the discount – and this module finds the
percentage that gets there. Only the percentage is stored (``Project.overall_discount_percent``); the project is not
calculated again for it when it changes later – more material changes the total, the percentage stays.

How the percentage is found:

* **Net target.** The discount is the sum before the discount minus the target. The percentage is the one with the
  fewest decimals (2 to 6) whose discount, rounded to the cent as :func:`rentalars.projects.pricing.overall_discount_of`
  does it, is exactly that amount. Six places reach the cent for projects up to a million euros.
* **Gross target.** The gross total follows from the net total by the tax of every rate, which the pricing code
  calculates per rate (a discount lowers every rate in the same proportion, a cent of rounding goes to the largest
  share). So it is not a plain division: the discount in cents is searched (bisection over the pricing code's own tax
  split, :func:`~rentalars.projects.pricing.totals_after_overall_discount`) until the gross total is the target or,
  where the rounding of the tax makes the exact cent impossible, the nearest one. Then the percentage is found as
  above.

Whatever the way, the answer states the figures the project will show with the stored percentage (``DiscountTarget``),
so the page and the API tell "exact" or "nearest possible".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from rentalars.core.money import CENT, HUNDRED, ZERO, money
from rentalars.projects.models import Project
from rentalars.projects.pricing import (
    ProjectPrices,
    compute_project_prices,
    discount_for_percent,
    totals_after_overall_discount,
)

#: How many decimals the stored percentage may have (``Project.overall_discount_percent``).
PERCENT_PLACES = 6


@dataclass(frozen=True)
class DiscountTarget:
    """What a target amount leads to: the percentage to store and the figures the project will show with it."""

    #: The percentage to store; ``None`` when no discount is needed (the target is the sum without discount).
    percent: Decimal | None
    #: ``net`` or ``gross`` – what the target was given in.
    mode: str
    target: Decimal
    net_before: Decimal
    gross_before: Decimal
    discount: Decimal
    net_total: Decimal
    gross_total: Decimal

    @property
    def reached(self) -> Decimal:
        """The amount in the unit of the target that the stored percentage leads to."""
        return self.net_total if self.mode == "net" else self.gross_total

    @property
    def is_exact(self) -> bool:
        """Whether the total is the target to the cent."""
        return self.reached == self.target


def figures_of(
    prices: ProjectPrices, *, percent: Decimal | None = None, amount: Decimal | None = None
) -> tuple[Decimal, Decimal, Decimal]:
    """The discount, the net and the gross total a percentage or an amount leads to – as the project will show them."""
    net_before = prices.net_before_overall_discount
    if net_before <= ZERO:
        discount = ZERO
    elif percent:
        discount = discount_for_percent(net_before, percent)
    elif amount:
        discount = min(money(amount), net_before)
    else:
        discount = ZERO
    net, gross = totals_after_overall_discount(prices, discount)
    return discount, net, gross


def prices_without_discount(project: Project) -> ProjectPrices:
    """The prices of the project as they stand; the sum before the overall discount does not depend on it."""
    return compute_project_prices(project)


def _percent_for(net_before: Decimal, discount: Decimal) -> Decimal | None:
    """The percentage with the fewest decimals that takes off exactly ``discount`` (the nearest if none does)."""
    if discount <= ZERO:
        return None
    exact = discount / net_before * HUNDRED
    for places in range(2, PERCENT_PLACES + 1):
        candidate = min(exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), HUNDRED)
        if discount_for_percent(net_before, candidate) == discount:
            return candidate
    step = Decimal(1).scaleb(-PERCENT_PLACES)
    nearest = exact.quantize(step, rounding=ROUND_HALF_UP)
    options = [min(max(nearest + shift * step, ZERO), HUNDRED) for shift in (-1, 0, 1)]
    return min(options, key=lambda option: abs(discount_for_percent(net_before, option) - discount))


def _discount_for_gross(prices: ProjectPrices, gross_target: Decimal) -> Decimal:
    """The discount in cents that brings the gross total to the target, or as near to it as the tax rounding allows."""
    net_before = prices.net_before_overall_discount

    def gross_with(cents: int) -> Decimal:
        return totals_after_overall_discount(prices, Decimal(cents) / 100)[1]

    low, high = 0, int(net_before / CENT)
    while low < high:
        middle = (low + high) // 2
        if gross_with(middle) <= gross_target:
            high = middle
        else:
            low = middle + 1
    best = low
    if best > 0 and abs(gross_with(best - 1) - gross_target) < abs(gross_with(best) - gross_target):
        best -= 1
    return Decimal(best) / 100


def solve(
    project: Project,
    *,
    net: Decimal | None = None,
    gross: Decimal | None = None,
    prices: ProjectPrices | None = None,
) -> DiscountTarget:
    """The percentage that brings the total of the project to the target – net or gross (exactly one is given).

    Raises:
        ValidationError: Both or none of the targets are given, the target is negative or above the total without
            discount (a discount cannot raise the price), or the project has no total to discount yet.
    """
    if (net is None) == (gross is None):
        raise ValidationError(_("Give either a net or a gross target amount."))
    prices = prices or prices_without_discount(project)
    net_before = prices.net_before_overall_discount
    gross_before = totals_after_overall_discount(prices, ZERO)[1]
    if net_before <= ZERO:
        raise ValidationError(_("The project has nothing to discount yet: its total is 0."))
    mode = "net" if net is not None else "gross"
    target = money(net if net is not None else gross)  # type: ignore[arg-type]
    if target < ZERO:
        raise ValidationError(_("The target amount cannot be negative."))
    ceiling = net_before if mode == "net" else gross_before
    if target > ceiling:
        raise ValidationError(
            _("The target amount is higher than the total without discount (%(total)s). A discount cannot raise it.")
            % {"total": _money(ceiling)}
        )
    discount = net_before - target if mode == "net" else _discount_for_gross(prices, target)
    percent = _percent_for(net_before, discount)
    given, net_total, gross_total = figures_of(prices, percent=percent)
    return DiscountTarget(
        percent=percent,
        mode=mode,
        target=target,
        net_before=net_before,
        gross_before=gross_before,
        discount=given,
        net_total=net_total,
        gross_total=gross_total,
    )


@dataclass(frozen=True)
class Preview:
    """What the values typed into the dialog of the overall discount lead to (the live preview)."""

    net_before: Decimal
    gross_before: Decimal
    #: ``percent``, ``amount``, ``target_net``, ``target_gross`` – or ``None`` when nothing is typed.
    mode: str | None
    percent: Decimal | None
    discount: Decimal
    net_total: Decimal
    gross_total: Decimal
    #: For a target: the amount asked for; ``None`` otherwise.
    target: Decimal | None = None

    @property
    def is_target(self) -> bool:
        """Whether the percentage is calculated from a target amount."""
        return self.mode in {"target_net", "target_gross"}

    @property
    def is_exact(self) -> bool:
        """Whether the total is the target to the cent (always true for anything that is no target)."""
        if self.target is None:
            return True
        return (self.net_total if self.mode == "target_net" else self.gross_total) == self.target


def preview_of(project: Project, values: dict[str, Any], mode: str | None) -> Preview | str:
    """The figures the typed value of the dialog leads to; an error text if it cannot be used.

    Args:
        project: The project.
        values: The cleaned values of ``OverallDiscountForm``.
        mode: The field that counts (``OverallDiscountForm.chosen``).
    """
    prices = prices_without_discount(project)
    net_before = prices.net_before_overall_discount
    gross_before = totals_after_overall_discount(prices, ZERO)[1]
    target = None
    try:
        if mode in {"target_net", "target_gross"}:
            target = values[mode]
            result = solve(
                project,
                net=values["target_net"] if mode == "target_net" else None,
                gross=values["target_gross"] if mode == "target_gross" else None,
                prices=prices,
            )
            percent, discount, net_total, gross_total = (
                result.percent,
                result.discount,
                result.net_total,
                result.gross_total,
            )
        else:
            percent = values.get("percent") if mode == "percent" else None
            amount = values.get("amount") if mode == "amount" else None
            discount, net_total, gross_total = figures_of(prices, percent=percent, amount=amount)
    except ValidationError as error:
        return " ".join(error.messages)
    return Preview(
        net_before=net_before,
        gross_before=gross_before,
        mode=mode,
        percent=percent,
        discount=discount,
        net_total=net_total,
        gross_total=gross_total,
        target=money(target) if target is not None else None,
    )


def _money(value: Decimal) -> str:
    """An amount in the active language for a message."""
    from rentalars.core.money import format_money

    return format_money(value)
