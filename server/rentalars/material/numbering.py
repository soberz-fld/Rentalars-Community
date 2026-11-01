# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory IDs of material items (MAT-003).

An ID is a consecutive number shown with leading zeros: ``0001``, ``0002`` …
After ``9999`` the count continues with ``10000``. The number is stored as an
integer, so sorting follows the numeric value and not the text.
"""

from __future__ import annotations

import time

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from rentalars.core.models import NumberRange, NumberRangeKey

#: MAT-003: IDs have at least four digits.
DEFAULT_MIN_DIGITS = 4

#: The configured width is read from the database at most this often.
_CACHE_SECONDS = 30.0
_cached_min_digits: tuple[float, int] | None = None


def _min_digits() -> int:
    """Return the configured minimum width of material IDs (ADM-003).

    Formatting an ID happens thousands of times on a list page. The value is
    therefore kept in memory for a short time instead of being queried for
    every single ID.
    """
    global _cached_min_digits
    now = time.monotonic()
    if _cached_min_digits is not None and now - _cached_min_digits[0] < _CACHE_SECONDS:
        return _cached_min_digits[1]
    digits = (
        NumberRange.objects.filter(key=NumberRangeKey.MATERIAL_ITEM).values_list("min_digits", flat=True).first()
        or DEFAULT_MIN_DIGITS
    )
    _cached_min_digits = (now, int(digits))
    return int(digits)


def reset_cache() -> None:
    """Forget the cached width; called after the number range was edited and in tests."""
    global _cached_min_digits
    _cached_min_digits = None


def format_inventory_number(number: int) -> str:
    """Format an ID for display: ``42`` becomes ``0042``, ``10000`` stays ``10000``."""
    return f"{number:0{_min_digits()}d}"


def parse_inventory_number(text: object) -> int:
    """Turn typed or imported text into the numeric ID.

    Accepts ``"0042"``, ``"42"`` and numbers read from spreadsheets such as
    ``42`` or ``42.0``. IMP-015: a leading ``#`` marks a cell as an ID
    in many lists – ``"#0042"`` and ``"# 0042"`` are ``0042`` as well.

    Raises:
        ValidationError: The text is not a positive whole number.
    """
    if isinstance(text, bool):
        raise ValidationError(_("“%(value)s” is not a valid ID.") % {"value": text})
    if isinstance(text, int):
        number = text
    elif isinstance(text, float) and text.is_integer():
        number = int(text)
    else:
        cleaned = str(text).strip().removeprefix("#").strip()
        if cleaned.endswith(".0"):
            cleaned = cleaned[:-2]
        if not cleaned.isdigit():
            raise ValidationError(_("“%(value)s” is not a valid ID.") % {"value": text})
        number = int(cleaned)
    if number < 1:
        raise ValidationError(_("IDs start at 1."))
    return number


def allocate_inventory_number() -> int:
    """Take the next free ID.

    The counter normally points to a free number. Should an ID above the
    counter already exist (entered by hand), the allocation skips forward
    until it finds a free one.
    """
    from rentalars.material.models import MaterialItem

    while True:
        number, _formatted = NumberRange.allocate(NumberRangeKey.MATERIAL_ITEM)
        if not MaterialItem.objects.filter(inventory_number=number).exists():
            return number


def id_range_for_prefix(typed: str) -> tuple[int, int] | None:
    """Return the range of IDs whose printed form starts with the typed digits.

    Used by search-as-you-type fields: someone who has typed ``05`` so far is
    on the way to ``0500`` … ``0599``. IDs are stored as numbers, so "starts
    with" is turned into a range of numbers:

    ========  ==================  =====================
    typed     printed IDs         stored numbers
    ========  ==================  =====================
    ``05``    ``0500``–``0599``   500 to 599
    ``050``   ``0500``–``0509``   500 to 509
    ``0500``  ``0500``            500 to 500
    ========  ==================  =====================

    Returns ``None`` if the text is not made of digits or is longer than an
    ID with the configured number of digits.
    """
    typed = typed.strip()
    width = _min_digits()
    if not typed.isdigit() or len(typed) > width:
        return None
    scale = 10 ** (width - len(typed))
    return int(typed) * scale, (int(typed) + 1) * scale - 1
