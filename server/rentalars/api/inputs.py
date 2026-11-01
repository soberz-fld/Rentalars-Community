# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed reading of single values from a request body (hostile input; R4-2).

The endpoints that read single values from a JSON object do not use a serializer. A client may send anything for
such a value: a list, a number for a text, ``"abc"`` or ``1e999`` for an ID. These helpers turn every wrong type
into the uniform 400 answer of the API (API-008) instead of an internal error.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError


def int_or_400(value: Any, field: str, *, default: int | None = None) -> int:
    """Return ``value`` as a whole number: 4, 4.0 and ``"4"`` are accepted; ``None`` or empty give ``default``.

    Booleans, other floats (also ``inf`` and ``nan``), lists, objects and texts that are no integer are refused, as
    are numbers that no database column could hold.

    Args:
        value: What the client sent.
        field: The name of the field for the error answer.
        default: Returned for a missing (``None`` or empty) value; without it a missing value is refused.

    Raises:
        ValidationError: The value is no whole number (answered with 400).
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not None:
            return default
        raise ValidationError({field: [_("Enter a whole number.")]})
    number: int | None = None
    if isinstance(value, int) and not isinstance(value, bool):
        number = value
    elif isinstance(value, float) and value.is_integer():  # False for inf and nan
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.lstrip("+-").isascii() and text.lstrip("+-").isdigit() and len(text) <= 20:
            number = int(text)
    if number is None or abs(number) >= 2**63:
        raise ValidationError({field: [_("Enter a whole number.")]})
    return number


def str_or_400(value: Any, field: str, *, default: str = "") -> str:
    """Return ``value`` as a text: only a string (or ``None``, which gives ``default``) is accepted.

    Numbers, booleans, lists and objects are refused – they are never silently turned into text.

    Raises:
        ValidationError: The value is no text (answered with 400).
    """
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValidationError({field: [_("Enter a text.")]})
    return value
