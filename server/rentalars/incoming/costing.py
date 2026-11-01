# SPDX-License-Identifier: GPL-3.0-or-later
"""The acquisition cost of the goods of an incoming invoice: ancillary costs spread over the positions (DOK-023, DOK-024).

The requirement: on purchase invoices, spread transport costs as ancillary acquisition costs; mark each position as
goods, low-value asset (GWG) or fixed asset with a depreciation period. The positions marked as ancillary cost (freight, packaging, customs …, also a
discount as a negative amount) are added up and spread over the goods positions, by

* **value** – the net amount of each goods position (the default),
* **quantity** – the number of pieces, or
* **weight** – the weight of each position (weight of one piece times the quantity).

Every share is a whole number of cents and the shares add up to exactly the ancillary costs (largest remainder).
The share of a position is spread over its pieces the same way (the first pieces get the odd cent). The
acquisition cost of a position is its net amount plus its share; per piece it is that divided by the quantity. All
amounts here are in euros: the amounts of an invoice in another currency are converted with the exchange rate of
the invoice.

The kind of each position – merchandise, low-value asset (GWG) or fixed asset – is the one chosen at the position,
else by the limit in the settings (:func:`rentalars.material.assets.kind_for`) applied to the cost per piece; the
useful life of a fixed asset is the one chosen, else the standard of the settings.

Nothing is stored here: the page, the API and the booking in (:mod:`rentalars.incoming.booking`) all call
:func:`costing_of`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from django.utils.translation import gettext as _

from rentalars.core.money import money
from rentalars.incoming.models import AllocationKey, IncomingInvoice, InvoicePosition
from rentalars.material import assets
from rentalars.material.models import AssetKind

HUNDRED = Decimal(100)


def to_cents(amount: Decimal) -> int:
    """An amount in whole cents, halves away from zero."""
    return int((amount * HUNDRED).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> Decimal:
    """Whole cents as an amount with two places."""
    return Decimal(cents).scaleb(-2)  # always two places: 297.00, not 297


def spread(amount: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Spread an amount over weights in whole cents; the shares add up to the amount exactly (largest remainder).

    A negative amount (a discount) is spread the same way, negated. Weights of 0 get nothing.

    Raises:
        ValueError: There is nothing to spread over – no weights, or they add up to nothing.
    """
    total_weight = sum(weights, Decimal(0))
    if not weights or total_weight <= 0:
        raise ValueError("nothing to spread over")
    cents = to_cents(amount)
    sign = -1 if cents < 0 else 1
    cents = abs(cents)
    raw = [Decimal(cents) * weight / total_weight for weight in weights]
    floors = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in raw]
    rest = cents - sum(floors)
    order = sorted(range(len(weights)), key=lambda index: raw[index] - floors[index], reverse=True)
    for index in order[:rest]:
        floors[index] += 1
    return [from_cents(sign * value) for value in floors]


def even_slice_cents(total_cents: int, pieces: int, start: int, count: int) -> int:
    """The cents of ``count`` pieces from piece ``start`` on, when ``total_cents`` is split evenly over ``pieces``.

    Piece i gets ``total // pieces`` cents and, for the first ``total % pieces`` pieces, one more – so the shares of
    all pieces add up to the total. Pieces beyond the last (a position booked again) get the plain share.
    """
    sign = -1 if total_cents < 0 else 1
    magnitude = abs(total_cents)
    base, odd = divmod(magnitude, max(pieces, 1))
    extra = max(0, min(start + count, odd) - min(start, odd))
    return sign * (count * base + extra)


def even_pieces(total: Decimal, pieces: int, start: int, count: int) -> list[Decimal]:
    """The amounts of ``count`` single pieces from piece ``start`` on (at most one step's worth of items)."""
    cents = to_cents(total)
    return [from_cents(even_slice_cents(cents, pieces, start + index, 1)) for index in range(count)]


@dataclass
class PositionCost:
    """What one goods position costs to acquire: its amount, its share of the ancillary costs, its kind."""

    position: InvoicePosition
    #: Net amount of the position in euros; ``None`` without a price.
    line: Decimal | None
    #: The weight of all pieces in kg, if known.
    weight: Decimal | None
    share: Decimal = Decimal("0.00")
    kind: str = ""
    useful_life: int | None = None
    #: What is wrong with this position for booking in: no price, a quantity that is not whole.
    problems: list[str] = field(default_factory=list)

    @property
    def kind_label(self) -> str:
        """The kind of asset as a word; empty when there is none."""
        return str(AssetKind(self.kind).label) if self.kind else ""

    @property
    def quantity(self) -> Decimal:
        """The quantity of the position."""
        return self.position.quantity

    @property
    def pieces(self) -> int:
        """The number of pieces; 0 if the quantity is not a whole number."""
        quantity = self.position.quantity
        return int(quantity) if quantity == quantity.to_integral_value() else 0

    @property
    def total(self) -> Decimal | None:
        """Amount plus share; ``None`` without a price."""
        return None if self.line is None else self.line + self.share

    @property
    def per_piece(self) -> Decimal | None:
        """The acquisition cost of one piece, on average; ``None`` without a price or a quantity."""
        if self.total is None or not self.position.quantity:
            return None
        return money(self.total / self.position.quantity)

    @property
    def share_per_piece(self) -> Decimal | None:
        """The share of the ancillary costs per piece, on average."""
        if not self.position.quantity:
            return None
        return money(self.share / self.position.quantity)

    def piece_price(self, start: int, count: int) -> list[Decimal]:
        """The net prices of ``count`` pieces from piece ``start`` (the odd cents to the first pieces)."""
        return even_pieces(self.line or Decimal(0), self.pieces, start, count)

    def piece_share(self, start: int, count: int) -> list[Decimal]:
        """The shares of the ancillary costs of ``count`` pieces from piece ``start``."""
        return even_pieces(self.share, self.pieces, start, count)

    def slice_price(self, start: int, count: int) -> Decimal:
        """The net price of ``count`` pieces together – the price of a bulk row."""
        return from_cents(even_slice_cents(to_cents(self.line or Decimal(0)), self.pieces, start, count))

    def slice_share(self, start: int, count: int) -> Decimal:
        """The share of the ancillary costs of ``count`` pieces together."""
        return from_cents(even_slice_cents(to_cents(self.share), self.pieces, start, count))


@dataclass
class Costing:
    """The acquisition cost of every goods position of an invoice, and what is wrong with it."""

    invoice: IncomingInvoice
    key: str
    rows: list[PositionCost]
    #: The ancillary cost positions and their amounts in euros.
    ancillary: list[tuple[InvoicePosition, Decimal]]
    #: Problems that stop booking in or make the figures wrong: no goods, no weight, nothing to spread over.
    problems: list[str] = field(default_factory=list)

    @property
    def ancillary_total(self) -> Decimal:
        """All ancillary costs together in euros."""
        return sum((amount for _position, amount in self.ancillary), Decimal("0.00"))

    @property
    def spread_total(self) -> Decimal:
        """What was spread over the goods; equals :attr:`ancillary_total` unless there was nothing to spread over."""
        return sum((row.share for row in self.rows), Decimal("0.00"))

    @property
    def goods_total(self) -> Decimal:
        """The net amounts of all goods positions in euros."""
        return sum((row.line or Decimal(0) for row in self.rows), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        """Goods and ancillary costs together: the acquisition cost of the whole invoice."""
        return self.goods_total + self.spread_total

    def row_of(self, position: InvoicePosition) -> PositionCost | None:
        """The row of a goods position."""
        return next((row for row in self.rows if row.position.pk == position.pk), None)


def _weight_of(position: InvoicePosition) -> Decimal | None:
    """The weight of all pieces of a position in kg: the weight of one piece named at the position, else of its model."""
    each = position.weight_kg
    if each is None and position.material_model_id and position.material_model.weight_kg is not None:
        each = position.material_model.weight_kg
    return None if each is None else each * position.quantity


def costing_of(
    invoice: IncomingInvoice, *, key: str | None = None, quantities: dict[int, Decimal] | None = None
) -> Costing:
    """Work out the acquisition cost of the goods of an invoice with its ancillary costs spread by ``key``.

    Args:
        invoice: The invoice; its positions are read from the database.
        key: ``value``, ``quantity`` or ``weight``; ``None``: the key chosen at the invoice.
        quantities: Positions (by pk) worked out with another number of pieces than they have: the person
            booking in chooses the number of pieces; the net amount of the position stays, the unit price follows. The
            positions are changed in memory only.
    """
    key = key if key in AllocationKey.values else (invoice.allocation_key or AllocationKey.VALUE)
    rate = invoice.rate
    missing_rate = rate is None
    if rate is None:
        rate = Decimal("1")  # only to show figures; the problem below stops booking in (R1-4)
    positions = list(invoice.positions.select_related("material_model").order_by("place", "pk"))
    for position in positions:
        if quantities and position.pk in quantities and position.line_net is not None:
            # In memory the unit price is exact (not cut to four places), so that the amount of the position stays.
            amount = position.line_net
            position.quantity = quantities[position.pk]
            position.unit_price_net = amount / quantities[position.pk]
    rows: list[PositionCost] = []
    ancillary: list[tuple[InvoicePosition, Decimal]] = []
    for position in positions:
        if position.is_ancillary:
            if position.line_net is not None:
                ancillary.append((position, money(position.line_net * rate)))
        elif position.is_goods:
            line = money(position.line_net * rate) if position.line_net is not None else None
            row = PositionCost(position=position, line=line, weight=_weight_of(position))
            if line is None:
                row.problems.append(_("The position has no price."))
            if not position.quantity or position.quantity <= 0:
                row.problems.append(_("The position has no quantity."))
            elif not row.pieces:
                row.problems.append(_("The quantity is not a whole number: pieces are counted whole."))
            rows.append(row)
    costing = Costing(invoice=invoice, key=key, rows=rows, ancillary=ancillary)
    if missing_rate:
        costing.problems.append(_("The invoice is not in euros: enter the exchange rate."))
    _spread_over_rows(costing)
    for row in rows:
        row.kind = assets.kind_for(row.per_piece, row.position.asset_kind)
        row.useful_life = assets.life_for(row.kind, row.position.useful_life_months)
    return costing


def _spread_over_rows(costing: Costing) -> None:
    """Fill in the share of every row; say what stops it (no goods, no weight, nothing to spread over)."""
    total = costing.ancillary_total
    if not costing.ancillary or not total:
        return
    rows = costing.rows
    if not rows:
        costing.problems.append(_("There are ancillary costs but no goods to spread them over."))
        return
    if costing.key == AllocationKey.WEIGHT:
        missing = [row.position for row in rows if row.weight is None]
        if missing:
            names = ", ".join(f"{position.place}. {position.description}"[:60] for position in missing[:5])
            costing.problems.append(
                _("To spread by weight every goods position needs a weight. Missing: %(names)s.") % {"names": names}
            )
            return
        weights = [row.weight or Decimal(0) for row in rows]
    elif costing.key == AllocationKey.QUANTITY:
        weights = [row.quantity for row in rows]
    else:
        weights = [row.line if row.line is not None and row.line > 0 else Decimal(0) for row in rows]
    try:
        shares = spread(total, weights)
    except ValueError:
        costing.problems.append(
            _("The ancillary costs cannot be spread by this key: the goods add up to nothing. Choose another one.")
        )
        return
    for row, share in zip(rows, shares, strict=True):
        row.share = share
