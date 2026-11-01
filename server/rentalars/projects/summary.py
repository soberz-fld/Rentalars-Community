# SPDX-License-Identifier: GPL-3.0-or-later
"""A short description of what a group contains, for the price overview without lines (PRJ-066).

The price overview can show groups with their totals only (PRJ-036) – the
style of quote that names "Licht Front-Traverse … 321,00 €" without listing
every spotlight. The customer should still roughly know what the money buys.
So each group gets one line like

    8 × LED-Scheinwerfer RGBW, 6 × Traverse 4-Punkt 2 m

Rules:

* Lines of the same product are added up; a kit is named as the kit, not its
  components.
* Subrentals that only cover the shortage of another line are left out: the
  customer sees the line they cover (PRJ-055). Lines with quantity 0 too, and
  optional or alternative lines – the subtotal does not contain them (PRJ-075).
* Pieces are written "8 × name", flat-rate lines just "name", other units
  "50 m name".
* A group with many different things is not listed in full: the most
  valuable :data:`MAX_ITEMS` are named, in the order of the planning, and
  "and 12 more" is added. That is what "roughly" means here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from django.utils.translation import ngettext

from rentalars.core.money import format_decimal

#: How many different things a summary names before it says "and … more".
MAX_ITEMS = 6

#: Units whose quantity is counted in pieces ("8 ×") – the default master data (PRD-012); a
#: piece for renting and one for selling, "Stück" in older installations (ADM-011).
PIECE_UNITS = frozenset(
    {"Stück", "Stück (Miete)", "Stück (Verkauf)", "Piece (rental)", "Piece (sale)"}  # UIX-029: English start data
)

#: Units that stand for a flat amount: the quantity says nothing to the customer.
FLAT_UNITS = frozenset({"Pauschal", "Flat rate"})


@dataclass
class _Item:
    """One thing in the summary: a product, or a line without product, with its added quantity."""

    title: str
    unit_name: str
    unit_abbreviation: str
    quantity: Decimal
    amount: Decimal
    first_position: int

    def text(self) -> str:
        """The item as the customer reads it."""
        if self.unit_name in FLAT_UNITS:
            return self.title
        quantity = format_decimal(self.quantity)
        if not self.unit_name or self.unit_name in PIECE_UNITS:
            return f"{quantity} × {self.title}"
        return f"{quantity} {self.unit_abbreviation} {self.title}"


def summarize_lines(planned_lines: Iterable[object]) -> str:
    """Return the short description of a list of planned material lines (``planning.PlannedLine``).

    Returns an empty text for a list without anything to name.
    """
    items: dict[object, _Item] = {}
    for index, planned in enumerate(planned_lines):
        line = planned.line  # type: ignore[attr-defined]
        if line.is_covering_subrental or line.is_surcharge or not line.quantity or not line.counts_toward_total:
            continue
        key = ("product", line.product_id) if line.product_id else ("title", line.title)
        unit = line.unit
        amount = getattr(getattr(planned, "price", None), "amount", None) or Decimal("0")
        item = items.get(key)
        if item is None:
            items[key] = _Item(
                title=line.title,
                unit_name=unit.name if unit else "",
                unit_abbreviation=unit.abbreviation if unit else "",
                quantity=Decimal(line.quantity),
                amount=amount,
                first_position=index,
            )
        else:
            item.quantity += Decimal(line.quantity)
            item.amount += amount
    return _join(list(items.values()))


def summarize_crew(crew_prices: Iterable[object]) -> str:
    """Return the short description of the personnel block: "2 × Stagehand, 1 × Tontechnik".

    Counted per title of the crew line (the name of the service product), so
    the customer reads what they pay for, never who.
    """
    items: dict[str, _Item] = {}
    for index, price in enumerate(crew_prices):
        line = price.line  # type: ignore[attr-defined]
        item = items.setdefault(
            line.title, _Item(line.title, "Stück", "", Decimal("0"), Decimal("0"), first_position=index)
        )
        item.quantity += 1
        item.amount += price.amount or Decimal("0")  # type: ignore[attr-defined]
    return _join(list(items.values()))


def _join(items: list[_Item]) -> str:
    """Name up to :data:`MAX_ITEMS` items – the most valuable – in planning order, and count the rest."""
    if not items:
        return ""
    chosen = items
    if len(items) > MAX_ITEMS:
        chosen = sorted(items, key=lambda item: (-item.amount, item.first_position))[:MAX_ITEMS]
    chosen = sorted(chosen, key=lambda item: item.first_position)
    text = ", ".join(item.text() for item in chosen)
    rest = len(items) - len(chosen)
    if rest:
        text += " " + ngettext("and %(count)d more item", "and %(count)d more items", rest) % {"count": rest}
    return text
