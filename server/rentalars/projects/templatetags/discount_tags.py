# SPDX-License-Identifier: GPL-3.0-or-later
"""Template filters for the overall discount (discount target; PRJ-123)."""

from __future__ import annotations

from decimal import Decimal

from django import template

from rentalars.core.money import format_decimal

register = template.Library()


@register.filter
def percent_places(value: Decimal | None) -> str:
    """A percentage with all the places it was stored with, without needless zeros: ``12,3457`` (up to six places)."""
    return format_decimal(value, max_places=6) if value is not None else "0"
