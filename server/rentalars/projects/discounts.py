# SPDX-License-Identifier: GPL-3.0-or-later
"""The maximum discount of a job function (PER-026).

Personnel is often not to be discounted at all – the people are paid by the
hour whatever the customer gets – or only a little. A job function can
therefore name the highest discount any line of it may get
(``JobFunction.max_discount_percent``): empty means no limit, 0 means never
discounted.

Which lines are lines "of a job function"?

* every crew line: its job function is named on it (PRJ-019);
* every material line whose product is the service product of a job
  function – personnel planned as a product in a group, e.g. "D-001 sound
  engineer, hour" (PER-008). If a product serves several job functions, the
  strictest maximum applies.

Where can a discount come from?

==========================  ======================================================
the line's own discount     typed in, or the customer's standard discount, which
                            every new *material* line takes over (KND-006)
the group's discount        in percent, as an amount or as a flat price that is
                            lower than the sum of the lines (PRJ-039); spread over
                            the lines in proportion to their amounts
==========================  ======================================================

Crew lines stand in no group (PRJ-038), and there is no discount on the project
as a whole – a project discount would have to pass through
:func:`lowest_amount` as well.

The user is told (warning at a discount above the maximum; PER-044): the stored discount stays as typed, the price
takes the maximum – and whoever types a discount above it gets a warning at once: "The discount of 30 % is above
the maximum of this line (20 %); 20 % are applied." The functions at the end of this module word these warnings
for a material line, a crew line, a vehicle booking, several lines and a group; the views show them as messages
of the planning, the API names them in ``warnings``. The overall discount of the project (PRJ-123) has no
maximum and gives none.

The maximum limits the *sum* of these: first the line's own discount is cut to
the maximum; then the line takes only as much of its group's discount as is
left up to the maximum. What a line cannot take stays with the customer's
bill: the group's discount becomes smaller by that much and a flat price
higher. The stored values stay as they were typed in, so that raising the
maximum later brings the discount back.

Example: a group with a light desk at 400.00 and a sound engineer at 100.00
(job function "Tontechnik", maximum 5 %) gets a discount of 10 %, i.e. 50.00.
The desk takes its share of 40.00. The sound engineer would take 10.00, but
may only lose 5.00. The group's discount is 45.00, its subtotal 455.00.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.core.money import ZERO, format_decimal, format_money, percentage_of
from rentalars.personnel.models import JobFunction
from rentalars.products.models import ProductKind

if TYPE_CHECKING:
    from rentalars.projects.models import CrewLine, Group, MaterialLine, VehicleLine


def maximum_discounts_of_products(product_ids: Iterable[int]) -> dict[int, Decimal]:
    """Return the maximum discount for each of the products that is a job function's service product (PER-026).

    Args:
        product_ids: The products of the lines to price.

    Returns:
        ``{product id: maximum discount in percent}``; products without a
        limit are missing. With several job functions per product the lowest
        maximum counts.
    """
    ids = {product_id for product_id in product_ids if product_id}
    if not ids:
        return {}
    maximum: dict[int, Decimal] = {}
    rows = JobFunction.objects.filter(service_product_id__in=ids, max_discount_percent__isnull=False).values_list(
        "service_product_id", "max_discount_percent"
    )
    for product_id, percent in rows:
        maximum[product_id] = min(maximum.get(product_id, percent), percent)
    return maximum


def limited_percent(percent: Decimal, maximum: Decimal | None) -> Decimal:
    """Return a discount in percent, cut to the maximum if there is one (PER-026)."""
    if maximum is None:
        return percent
    return min(percent, maximum)


def lowest_amount(base_amount: Decimal, maximum: Decimal) -> Decimal:
    """Return the least a line may cost: its amount before discounts, less the maximum discount (PER-026).

    Example: 100.00 with a maximum of 5 % may come down to 95.00, not lower.
    """
    return base_amount - percentage_of(base_amount, maximum)


# --- Telling the user (warning at a discount above the maximum; PER-044) ---------------------------


def maximum_of_material_line(line: MaterialLine) -> Decimal | None:
    """The highest discount a material line may get: its product's, or its job function's for a service (PER-026).

    The stricter of the two counts, as in the price calculation. ``None``: no limit.
    """
    if not line.product_id:
        return None
    maximum = line.product.max_discount_percent
    if line.product.kind == ProductKind.SERVICE:
        function_maximum = maximum_discounts_of_products([line.product_id]).get(line.product_id)
        if function_maximum is not None and (maximum is None or function_maximum < maximum):
            maximum = function_maximum
    return maximum


def line_discount_warning(line: MaterialLine, entered: Decimal | None = None) -> str:
    """The warning for a material line whose discount is above its maximum; "" if it is not (PER-026).

    Args:
        line: The line, saved or with the typed values.
        entered: The typed discount if it is not the line's own.
    """
    entered = line.discount_percent if entered is None else entered
    maximum = maximum_of_material_line(line)
    if maximum is None or entered <= maximum:
        return ""
    return _(
        "The discount of %(entered)s %% is above the maximum of this line (%(maximum)s %%); %(maximum)s %% are applied."
    ) % {"entered": format_decimal(entered), "maximum": format_decimal(maximum)}


def crew_discount_warning(line: CrewLine, entered: Decimal | None = None) -> str:
    """The warning for a crew line whose discount is above the maximum of its job function; "" if it is not."""
    entered = line.discount_percent if entered is None else entered
    maximum = line.job_function.max_discount_percent
    if maximum is None or entered <= maximum:
        return ""
    return _(
        "The discount of %(entered)s %% is above the maximum of the job function “%(function)s” (%(maximum)s %%); "
        "%(maximum)s %% are applied."
    ) % {
        "entered": format_decimal(entered),
        "function": line.job_function.name,
        "maximum": format_decimal(maximum),
    }


def vehicle_discount_warning(line: VehicleLine, entered: Decimal | None = None) -> str:
    """The warning for a vehicle booking whose discount is above the maximum of its product; "" if it is not."""
    entered = line.discount_percent if entered is None else entered
    maximum = line.product.max_discount_percent
    if maximum is None or entered <= maximum:
        return ""
    return _(
        "The discount of %(entered)s %% is above the maximum of this booking (%(maximum)s %%); %(maximum)s %% are applied."
    ) % {"entered": format_decimal(entered), "maximum": format_decimal(maximum)}


def capped_lines_warning(entered: Decimal, capped: list[tuple[str, Decimal]]) -> str:
    """One warning for several lines changed at once: which lines have a lower maximum than the discount typed.

    Args:
        entered: The discount typed for all of them.
        capped: ``(name of the line, its maximum)`` for each line whose maximum is below ``entered``.

    Returns:
        The text; "" for an empty list.
    """
    if not capped:
        return ""
    return ngettext(
        "The discount of %(entered)s %% is above the maximum of one line: %(lines)s. The maximum is applied there.",
        "The discount of %(entered)s %% is above the maximum of %(count)d lines: %(lines)s. The maximum is applied there.",
        len(capped),
    ) % {
        "entered": format_decimal(entered),
        "count": len(capped),
        "lines": "; ".join(f"{name} ({format_decimal(maximum)} %)" for name, maximum in capped),
    }


def capped_material_lines(lines: Iterable[MaterialLine], entered: Decimal) -> list[tuple[str, Decimal]]:
    """The lines among ``lines`` whose maximum is below ``entered``, with their names, for :func:`capped_lines_warning`."""
    from rentalars.projects.lines import line_label

    found = []
    for line in lines:
        maximum = maximum_of_material_line(line)
        if maximum is not None and entered > maximum:
            found.append((line_label(line), maximum))
    return found


def group_discount_warning(group: Group, *, prices: Any = None) -> str:
    """The warning for a group whose discount or flat price the maximum discounts of its lines cut; "" if not.

    The group's discount (percent or amount) or flat price is spread over its lines (PRJ-039); a line with a
    maximum takes only so much of it (PER-026), and what it cannot take stays with the customer's bill. The
    warning says what was entered and what applies.

    Args:
        group: The saved group.
        prices: The project's calculated prices, if the caller has them; otherwise they are calculated here.
    """
    from rentalars.projects.pricing import compute_project_prices

    prices = prices or compute_project_prices(group.project)
    group_price = prices.by_group_id.get(group.pk)
    if group_price is None or group_price.cap_excess <= ZERO:
        return ""
    values = {"group": group.name}
    if group.flat_price is not None:
        return _(
            "The flat price of %(price)s for the group “%(group)s” is below what the maximum discounts of its lines "
            "allow; the group costs %(applied)s."
        ) % {**values, "price": format_money(group.flat_price), "applied": format_money(group_price.subtotal)}
    if group.discount_percent is not None:
        applied = (group_price.discount * 100 / group_price.lines_total).quantize(Decimal("0.01"))
        return _(
            "The discount of %(entered)s %% for the group “%(group)s” is above the maximum of some of its lines; "
            "%(applied)s %% are applied in all."
        ) % {**values, "entered": format_decimal(group.discount_percent), "applied": format_decimal(applied)}
    return _(
        "The discount of %(entered)s for the group “%(group)s” is above the maximum of some of its lines; "
        "%(applied)s are applied in all."
    ) % {**values, "entered": format_money(group.discount_amount), "applied": format_money(group_price.discount)}
