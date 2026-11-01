# SPDX-License-Identifier: GPL-3.0-or-later
"""Dates with an unknown day or month – the date of purchase of an old item (partial purchase date; MAT-050; MAT-088).

The requirement: a purchase date such as 00.00.2015 is allowed (day and month unknown). Of an item bought long ago people often know the year
only, or the month. ``MaterialItem.purchase_date`` stays an ordinary date – the **first day of the period that is
known** – and ``MaterialItem.purchase_date_precision`` says how much of it is known:

============  =====================  ===========================  ===================
precision     typed                  stored in ``purchase_date``  shown
============  =====================  ===========================  ===================
``day``       ``12.05.2015``         2015-05-12                   12.05.2015
``month``     ``00.05.2015``         2015-05-01                   05.2015
``year``      ``00.00.2015``         2015-01-01                   2015
============  =====================  ===========================  ===================

So the column keeps working in SQLite and MariaDB, sorts sensibly (a year before the dated items of that year) and can
be used by whoever needs a date (the depreciation starts with the first day of the period). Typed – in the forms, the
import, the API – are the German order ``12.05.2015`` (also with ``/`` as in English and with a two-digit year,
``12.05.15``), ``00.05.2015``, ``05.2015``, ``2015`` and the ISO forms ``2015-05-12``, ``2015-05-00``, ``2015-05``, ``2015-00-00``.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

DAY, MONTH, YEAR = "day", "month", "year"
#: From finest to coarsest.
PRECISIONS = (DAY, MONTH, YEAR)
#: The years taken: a typing mistake such as 215 or 20150 is refused, not stored.
MIN_YEAR, MAX_YEAR = 1900, 2999

_DMY = re.compile(r"^(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{4})$")
#: ``12.05.15``: what the date field of the forms took before (``%d.%m.%y``); 00 to 68 mean 2000 to 2068, 69 to 99 mean
#: 1969 to 1999 – the rule of ``strptime`` (R3-10).
_DMY_SHORT = re.compile(r"^(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{2})$")
_MY = re.compile(r"^(\d{1,2})\s*[./]\s*(\d{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$")
_YEAR = re.compile(r"^(\d{4})$")


@dataclass(frozen=True)
class PartialDate:
    """A date that may be known only to the month or the year: the first day of the period and the precision."""

    date: datetime.date
    precision: str = DAY

    def __post_init__(self) -> None:
        first = first_day(self.date, self.precision)
        if first != self.date:
            object.__setattr__(self, "date", first)

    def __str__(self) -> str:
        return display(self.date, self.precision)

    @property
    def iso(self) -> str:
        """``2015-05-12``, ``2015-05-00`` or ``2015-00-00`` – the ISO form with zeros for what is not known."""
        return iso_text(self.date, self.precision)


def first_day(value: datetime.date, precision: str) -> datetime.date:
    """The first day of the period the precision names: 2015-05-12 → 2015-05-01 for ``month``, 2015-01-01 for ``year``."""
    if precision == YEAR:
        return value.replace(month=1, day=1)
    if precision == MONTH:
        return value.replace(day=1)
    return value


def normalised(value: datetime.date | None, precision: str) -> tuple[datetime.date | None, str]:
    """The date and precision the way they are stored: no date means "day"; an unknown precision means "day"."""
    if value is None:
        return None, DAY
    if precision not in PRECISIONS:
        precision = DAY
    return first_day(value, precision), precision


def coarser(one: str, other: str) -> str:
    """The less precise of two precisions."""
    return max(one, other, key=PRECISIONS.index)


def display(value: datetime.date | None, precision: str = DAY) -> str:
    """The date as it is shown: ``12.05.2015``, ``05.2015`` or ``2015`` (``12/05/2015``, ``05/2015`` in English)."""
    if value is None:
        return ""
    from rentalars.core.i18n import is_english

    if precision == YEAR:
        return f"{value.year:04d}"
    separator = "/" if is_english() else "."
    if precision == MONTH:
        return f"{value.month:02d}{separator}{value.year:04d}"
    return f"{value.day:02d}{separator}{value.month:02d}{separator}{value.year:04d}"


def iso_text(value: datetime.date | None, precision: str = DAY) -> str:
    """``2015-05-12``, ``2015-05-00``, ``2015-00-00``; "" for no date – the form the API names the date in."""
    if value is None:
        return ""
    if precision == YEAR:
        return f"{value.year:04d}-00-00"
    if precision == MONTH:
        return f"{value.year:04d}-{value.month:02d}-00"
    return value.isoformat()


def parse(text: str) -> PartialDate:
    """A typed date as :class:`PartialDate`.

    Raises:
        ValueError: The text is no date, a day or month that does not exist, a day without a month, or a year outside
            1900 to 2999.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty")
    day: int | None = None
    month: int | None = None
    if match := _YEAR.match(text):
        year = int(match.group(1))
    elif match := _ISO.match(text):
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    elif match := _DMY.match(text):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    elif match := _DMY_SHORT.match(text):
        day, month, short = int(match.group(1)), int(match.group(2)), int(match.group(3))
        year = 2000 + short if short <= 68 else 1900 + short
    elif match := _MY.match(text):
        month, year = int(match.group(1)), int(match.group(2))
    else:
        raise ValueError(text)
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"year {year}")
    if month is None or month == 0:
        if day:
            raise ValueError("a day needs a month")
        return PartialDate(datetime.date(year, 1, 1), YEAR)
    if not 1 <= month <= 12:
        raise ValueError(f"month {month}")
    if not day:
        return PartialDate(datetime.date(year, month, 1), MONTH)
    return PartialDate(datetime.date(year, month, day), DAY)  # a day the month does not have: ValueError


def of(value: datetime.date | None, precision: str) -> PartialDate | None:
    """The stored date and precision of an item as :class:`PartialDate`; ``None`` without a date."""
    if value is None:
        return None
    return PartialDate(value, precision if precision in PRECISIONS else DAY)


class PartialDateField(forms.Field):
    """A form field for a date that may lack day or month: the value is a:class:`PartialDate`.

    A text field – the browser's date picker cannot hold ``00.00.2015``. A form that stores the date splits the value
    with :func:`split_into` before the model is filled.
    """

    default_error_messages = {
        "invalid": _("Enter a date like 12.05.2015, 05.2015 or 2015 – 00.00.2015 for an unknown day and month."),
    }

    def __init__(self, *, input_formats: Any = None, **kwargs: Any) -> None:
        kwargs.setdefault("widget", forms.TextInput(attrs={"placeholder": _("DD.MM.YYYY"), "autocomplete": "off"}))
        super().__init__(**kwargs)

    def prepare_value(self, value: Any) -> Any:
        """What the field shows: the date as the language writes it, with what is unknown left out."""
        if isinstance(value, PartialDate):
            return str(value)
        if isinstance(value, datetime.datetime):
            return display(value.date())
        if isinstance(value, datetime.date):
            return display(value)
        return value

    def to_python(self, value: Any) -> PartialDate | None:
        """Turn the typed text (or a date) into a :class:`PartialDate`."""
        if value in self.empty_values:
            return None
        if isinstance(value, PartialDate):
            return value
        if isinstance(value, datetime.datetime):
            return PartialDate(value.date())
        if isinstance(value, datetime.date):
            return PartialDate(value)
        try:
            return parse(str(value))
        except ValueError as error:
            raise ValidationError(self.error_messages["invalid"], code="invalid") from error


def split_into(form: Any, cleaned: dict[str, Any], name: str = "purchase_date") -> None:
    """Replace the :class:`PartialDate` in ``cleaned[name]`` by its date and give the precision to the form's item.

    Call from the ``clean()`` of a model form, before the model is filled from the cleaned data.
    """
    value = cleaned.get(name)
    if isinstance(value, PartialDate):
        cleaned[name] = value.date
        form.instance.purchase_date_precision = value.precision
    elif name in cleaned and value is None:
        form.instance.purchase_date_precision = DAY
