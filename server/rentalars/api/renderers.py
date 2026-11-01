# SPDX-License-Identifier: GPL-3.0-or-later
"""How answers of the API are written as JSON (API-003)."""

from __future__ import annotations

import decimal
from typing import Any

from rest_framework.renderers import JSONRenderer
from rest_framework.utils.encoders import JSONEncoder


class DecimalAsStringEncoder(JSONEncoder):
    """Writes decimal numbers as strings, e.g. ``"1668.40"``.

    Amounts of money and quantities must arrive exactly as calculated. A JSON
    number would be read as a binary floating point value by most programs,
    and ``0.1 + 0.2`` is not ``0.3`` there. Fields of serializers are already
    delivered as strings; this encoder makes documents that views assemble by
    hand (totals, planning, price overview) follow the same rule.
    """

    def default(self, obj: Any) -> Any:
        """Turn a ``Decimal`` into its exact text; leave the rest to the framework."""
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        return super().default(obj)


class RentalarsJSONRenderer(JSONRenderer):
    """The JSON renderer of the API: UTF-8, decimals as strings."""

    encoder_class = DecimalAsStringEncoder
