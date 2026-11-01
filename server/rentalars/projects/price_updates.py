# SPDX-License-Identifier: GPL-3.0-or-later
"""Prices that changed since the lines took them over (PRJ-072).

A line copies the price of its product when it is created, and keeps it when
the product's price changes later (PRJ-015): what was quoted stays quoted. For
a project that is not fully confirmed yet – an inquiry, an option, or "Confirmed – details open" –
the old price is usually not intended, though. Its planning therefore says "3 lines have an
old price", shows old and new prices and takes over the new ones on request,
for all lines or line by line. A confirmed project (details settled) keeps its prices; the hint
does not appear there, and the API answers only when asked.

What counts as "old"?
    Every line remembers the price of its product at the moment it took the
    price over (``list_price``). A line is outdated when the product's price is
    no longer that one: the rental price for a rented line, the sale price for
    a sold one, the price of the service product for a crew line.

Prices set by hand
    A line whose unit price differs from ``list_price`` had its price set by
    hand – a special price for this customer. Such a line is listed too, but
    "take over all new prices" leaves it alone: the planner decides line by
    line, either taking over the new price or keeping the own one. Keeping it
    notes the new product price as seen, so that the hint goes away until the
    product's price changes again.

Older lines
    Their ``list_price`` was filled where the unit price still equalled the
    product's price. For the others it is unknown whether the price was set
    by hand or the product's price changed; they count as set by hand.

Not looked at: lines without product, percentage surcharges (their percentage
is not a price) and subrentals that only cover a shortage (they are not
charged, PRJ-055).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.projects.models import UNSETTLED_STATUSES, CrewLine, MaterialLine, Project
from rentalars.projects.services import ensure_editable

#: PRJ-072: the statuses in which the planning points out changed products – the project is not fully confirmed:
#: an inquiry, an option, or confirmed with the details still open (status "Bestätigt – Einzelheiten offen").
CHANGE_NOTICE_STATUSES = UNSETTLED_STATUSES


def shows_price_hint(project: Project) -> bool:
    """Whether the planning of the project points out old prices (PRJ-072): only until it is fully confirmed (also while the details are open)."""
    return project.status in CHANGE_NOTICE_STATUSES


def current_price_of_line(line: MaterialLine) -> Decimal | None:
    """The price the product of a material line asks today, or ``None`` if the line is not looked at."""
    product = line.product
    if product is None or line.is_percent_surcharge or line.is_covering_subrental:
        return None
    return product.sale_price if line.is_sale else product.price


def current_price_of_crew_line(line: CrewLine) -> Decimal | None:
    """The price the service product of a crew line asks today, or ``None`` without product."""
    return line.service_product.price if line.service_product_id else None


@dataclass
class OldPrice:
    """A line whose product asks a different price now (PRJ-072)."""

    line: MaterialLine | CrewLine
    #: The price the line charges.
    unit_price: Decimal
    #: The price of the product when the line took it over; ``None``: not known (older line).
    list_price: Decimal | None
    #: The price of the product today.
    new_price: Decimal

    @property
    def is_crew(self) -> bool:
        """Whether this is a crew line (its price comes from the service product of the job function)."""
        return isinstance(self.line, CrewLine)

    @property
    def key(self) -> str:
        """Names the line in forms and API calls: ``m12`` for material line 12, ``c5`` for crew line 5."""
        return f"{'c' if self.is_crew else 'm'}{self.line.pk}"

    @property
    def set_by_hand(self) -> bool:
        """Whether the unit price was set by hand – or it is not known whether it was."""
        return self.list_price is None or self.unit_price != self.list_price

    @property
    def article_number(self) -> str:
        """The article number of the product the price comes from."""
        product = self.line.service_product if self.is_crew else self.line.product
        return product.article_number if product is not None else ""

    @property
    def title(self) -> str:
        """The title of the line."""
        return self.line.title


def find_old_prices(material_lines: Iterable[MaterialLine], crew_lines: Iterable[CrewLine] = ()) -> list[OldPrice]:
    """Pick out the lines whose product asks a different price than when they took it over (PRJ-072).

    Args:
        material_lines: Material lines with their products loaded.
        crew_lines: Crew lines with their service products loaded.

    Returns:
        The outdated lines, material lines first, each in the order given.
    """
    found: list[OldPrice] = []
    for line in material_lines:
        new_price = current_price_of_line(line)
        found.extend(_compare(line, new_price))
    for crew_line in crew_lines:
        found.extend(_compare(crew_line, current_price_of_crew_line(crew_line)))
    return found


def _compare(line: MaterialLine | CrewLine, new_price: Decimal | None) -> list[OldPrice]:
    """The line as an :class:`OldPrice` in a list, or an empty list if its price is current."""
    if new_price is None:
        return []
    reference = line.list_price if line.list_price is not None else line.unit_price
    if reference == new_price:
        return []
    return [OldPrice(line=line, unit_price=line.unit_price, list_price=line.list_price, new_price=new_price)]


def old_prices(project: Project) -> list[OldPrice]:
    """The lines of a project whose product's price changed since they took it over (PRJ-072)."""
    material_lines = project.material_lines.select_related("product").order_by("group__position", "position", "id")
    crew_lines = project.crew_lines.select_related("service_product").order_by("start", "position", "id")
    return find_old_prices(material_lines, crew_lines)


@dataclass
class PriceUpdate:
    """What :func:`take_over_new_prices` did."""

    taken_over: int = 0
    kept: int = 0


@transaction.atomic
def take_over_new_prices(
    project: Project,
    *,
    rights: Rights,
    keys: Iterable[str] = (),
    automatic: bool = False,
    everything: bool = False,
    keep: Iterable[str] = (),
) -> PriceUpdate:
    """Bring the prices of lines up to date with their products, or keep them knowingly (PRJ-072).

    Taking over sets the unit price and ``list_price`` to the product's price
    of today; the discount of the line stays. Keeping notes the product's
    price in ``list_price`` and leaves the unit price as it is: the line now
    counts as priced by hand, and the hint is gone.

    Args:
        project: The project.
        rights: The rights of the caller; prices need the price right (AUT-019).
        keys: The lines to take over, by :attr:`OldPrice.key`.
        automatic: Take over every line whose price was not set by hand.
        everything: Take over every outdated line, set by hand or not.
        keep: The lines whose own price stays, by key.

    Returns:
        How many lines were taken over and kept. Lines that are not outdated
        (any more) are passed over silently: pressing a button twice does no
        harm.

    Raises:
        ValidationError: The project is closed or confirmed (what was agreed stays agreed, PRJ-015), the
            caller may not set prices, or a line is named to be taken over and kept at once.
    """
    ensure_editable(project)
    if not shows_price_hint(project):
        raise ValidationError(_("This project is confirmed; its lines keep the values that were agreed."))
    if not rights.has(SpecialRight.PRICES):
        raise ValidationError(_("You do not have the right to set prices or discounts."))
    take, kept_keys = set(keys), set(keep)
    if take & kept_keys:
        raise ValidationError(_("A line cannot take over the new price and keep its own at the same time."))
    result = PriceUpdate()
    for old in old_prices(project):
        line = old.line
        if old.key in kept_keys:
            keep_own_price(old)
            line.save()
            result.kept += 1
        elif everything or old.key in take or (automatic and not old.set_by_hand):
            apply_new_price(old)
            line.save()
            result.taken_over += 1
    return result


def keep_own_price(old: OldPrice) -> None:
    """Note the product's price as seen and leave the unit price as it is; the caller saves the line."""
    old.line.list_price = old.new_price


def apply_new_price(old: OldPrice) -> None:
    """Give the line the product's price of today; the discount stays. The caller saves the line."""
    line = old.line
    line.unit_price = old.new_price
    line.list_price = old.new_price
    if old.is_crew and line.service_product_id:
        # PER-035: the hour tiers of the service product come along with its price.
        product = line.service_product
        tiers = product.hours_limit is not None and product.price_above_limit is not None
        line.hours_limit = product.hours_limit if tiers else None
        line.unit_price_above_limit = product.price_above_limit if tiers else None
