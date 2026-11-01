# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers for amounts of money (NFA-003).

Money is always a ``Decimal`` with two places, never a float: floats cannot
represent amounts like 0.10 exactly, and the errors add up in sums.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def money(value: Decimal | int | str) -> Decimal:
    """Round to whole cents, halves away from zero ("commercial rounding").

    Example: ``money(Decimal("72.995"))`` is ``Decimal("73.00")``.
    """
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def plain_decimal(value: Decimal | int | str) -> str:
    """A number without needless decimals, with a point: ``20.00`` → ``"20"``, ``7.50`` → ``"7.5"``, ``100`` → ``"100"``.

    For data and for texts that must not lose a zero before the point: ``"20".rstrip("0")`` is ``"2"``.
    """
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def percentage_of(amount: Decimal, percent: Decimal) -> Decimal:
    """Return ``percent`` per cent of ``amount``, rounded to cents."""
    return money(amount * percent / HUNDRED)


def _separators() -> tuple[str, str]:
    """Decimal and thousands separator of the active language: German ``,`` and ``.``, English ``.`` and ``,`` (UIX-029)."""
    from django.utils import translation

    if (translation.get_language() or "").lower().startswith("en"):
        return ".", ","
    return ",", "."


def decimal_separator() -> str:
    """The decimal separator of the active language: ``,`` (German) or ``.`` (English) (UIX-029)."""
    return _separators()[0]


def group_thousands(whole: str) -> str:
    """Digits with the thousands separator of the active language: ``20.115`` or ``20,115``."""
    _decimal, thousands = _separators()
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return thousands.join(reversed(groups)) or "0"


def format_money(value: Decimal | int | None, *, currency: str = "€") -> str:
    """Format an amount in the active language: German ``1.234,50 €``, English ``€1,234.50`` (UIX-029).

    ``None`` gives an empty text; ``currency=""`` the number alone.
    """
    if value is None:
        return ""
    rounded = money(value)
    sign = "-" if rounded < 0 else ""
    whole, cents = f"{abs(rounded):.2f}".split(".")
    decimal, _thousands = _separators()
    number = f"{group_thousands(whole)}{decimal}{cents}"
    if decimal == ".":
        return f"{sign}{currency}{number}"
    return f"{sign}{number} {currency}".strip()


def format_decimal(value: Decimal | int | None, *, max_places: int = 3) -> str:
    """Format a number without needless zeros in the active language: ``1,5`` (German) or ``1.5`` (English)."""
    if value is None:
        return ""
    number = Decimal(value)
    quantised = number.quantize(Decimal(1).scaleb(-max_places), rounding=ROUND_HALF_UP)
    text = format(quantised, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    decimal, _thousands = _separators()
    return text.replace(".", decimal)


def parse_decimal(text: str) -> Decimal:
    """Read a number typed in the format of the active language – ``1.234,5`` or ``1,234.5`` (UIX-029).

    Raises:
        decimal.InvalidOperation: Not a number.
    """
    decimal, thousands = _separators()
    cleaned = (text or "").strip().replace(" ", "").replace(thousands, "").replace(decimal, ".")
    return Decimal(cleaned)
