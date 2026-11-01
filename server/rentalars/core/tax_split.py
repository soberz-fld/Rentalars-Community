# SPDX-License-Identifier: GPL-3.0-or-later
"""Splitting a gross amount over tax rates (DOK-045) – a pure function.

A payment of 119,00 on an invoice of 100,00 at 19 % and 100,00 at 0 % is 119/219 of the invoice: the EÜR needs how much
of it is net, how much tax, and at which rate. The amount is split in proportion to the gross amounts of the rates of the
invoice; every part is rounded to the cent and the largest part takes what the rounding left, so that the parts always add
up to the amount, to the cent.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def cents(value: Decimal) -> Decimal:
    """Whole cents, halves up."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def split[K: Hashable](
    amount: Decimal, shares: Sequence[tuple[K, Decimal, Decimal]]
) -> list[tuple[K, Decimal, Decimal]]:
    """Split a gross amount: ``shares`` are ``(key, net, tax)`` of the invoice, the result ``(key, net, tax)`` of the amount.

    The sign of the amount is kept (a refund is negative). Shares without a gross amount get nothing. If no share has an
    amount at all, nothing can be split and the result is empty – the caller decides what that means (the EÜR warns and
    does not count the payment). A single-share invoice gets the amount exactly: tax by the ratio of the share, net the rest.
    """
    amount = cents(amount)
    rows = [(key, net, tax) for key, net, tax in shares if net + tax != 0]
    if not rows:
        return []
    total = sum((net + tax for _key, net, tax in rows), ZERO)
    if total == 0:
        return []
    gross_parts = [cents(amount * (net + tax) / total) for _key, net, tax in rows]
    left = amount - sum(gross_parts, ZERO)
    if left:
        largest = max(range(len(rows)), key=lambda index: abs(rows[index][1] + rows[index][2]))
        gross_parts[largest] += left
    result: list[tuple[K, Decimal, Decimal]] = []
    for (key, net, tax), part in zip(rows, gross_parts, strict=True):
        gross = net + tax
        tax_part = cents(part * tax / gross)
        result.append((key, part - tax_part, tax_part))
    return result
