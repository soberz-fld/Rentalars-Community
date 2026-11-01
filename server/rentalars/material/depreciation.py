# SPDX-License-Identifier: GPL-3.0-or-later
"""Depreciation (AfA) and book value of assets – pure functions ("Mit Restbuchwert"; MAT-086).

The requirement: split transport costs on purchase invoices as ancillary acquisition costs per position, and mark each
position as goods, low-value asset (GWG) or fixed asset with a depreciation period. Decided: linear depreciation and the book value per item, used sale with gain or loss
against the book value, no DATEV export.

This is a **simplified standard setting, not tax advice**. The rules, all documented here and nowhere configurable:

Fixed asset (``fixed_asset``)
    Linear (straight line) over the useful life in months, pro rata temporis **by month**: the month of acquisition
    counts as a full month ("Monatsprinzip" – an asset bought on the 28th is depreciated for the whole month), and so
    does the month of the date a book value is asked for. After ``useful_life_months`` months nothing is left to
    depreciate. Not covered: degressive depreciation, special depreciation (Sonderabschreibung), the half-year rule
    for acquisitions during the year (it was abolished for movable assets in 2004 and is not applied), changes of the
    useful life, additions to the cost later.

Low-value asset (``low_value``, GWG)
    Written off completely in the year of acquisition. The write-off falls on the balance-sheet date, 31 December
    of that year: from that day on the book value is 0, before it – also in the year of acquisition – it is the
    full cost. (An asset sold before 31 December leaves the books at its cost.) The pool method (Sammelposten) is
    not covered.

Merchandise (``merchandise``)
    Not depreciated: the book value stays the cost until the item is sold.

Rounding
    Money is rounded to whole cents, halves up. The amount written off after ``k`` months is the *rounded cumulative*
    amount ``round(base × k / life)``, an instalment is the difference of two such amounts. So no instalment differs
    from the exact monthly amount by more than a cent, the amount of any year is as exact as the cents allow, and
    the last month balances: the instalments always add up to the depreciable base to the cent.

Memory value (Erinnerungswert)
    Optionally 1 € is left when the asset is fully depreciated (``memory=True``; the setting of Einstellungen →
    Eingangsrechnungen, off by default). The base is then the cost minus 1 €; an asset that cost 1 € or less is not
    depreciated at all.

Unknown dates
    A date of acquisition known to the year or the month only is stored as the **first day of that period**
    (``material.partial_dates``): the depreciation starts with January of a known year, with the first day's month
    otherwise. A date in the future is "not yet acquired": nothing is depreciated and there is no book value yet.

Everything here is a function of its arguments – no database, no clock (the caller says what "today" is).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, localcontext

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
#: What is left of a fully depreciated asset when the memory value is on.
MEMORY_VALUE = Decimal("1.00")

# The states of a valuation.
UNCLASSIFIED = "unclassified"  #: no kind of asset: nothing can be said
MERCHANDISE = "merchandise"  #: not depreciated
NO_COST = "no_cost"  #: a kind, but no cost
NO_DATE = "no_date"  #: depreciable, but no date of acquisition
NO_LIFE = "no_life"  #: a fixed asset without a useful life
NOT_YET = "not_yet"  #: the acquisition lies after the date asked for
RUNNING = "running"  #: being depreciated
WRITTEN_OFF = "written_off"  #: depreciated completely (a fixed asset at the end of its life, a GWG after its year)
LOW_VALUE_OPEN = "low_value_open"  #: a GWG in the year of acquisition, not written off yet

#: The states in which a book value exists.
VALUED_STATES = frozenset({MERCHANDISE, RUNNING, WRITTEN_OFF, LOW_VALUE_OPEN})

# The kinds, as ``MaterialItem.asset_kind`` names them (kept here so that this module imports nothing).
KIND_MERCHANDISE = "merchandise"
KIND_LOW_VALUE = "low_value"
KIND_FIXED_ASSET = "fixed_asset"


def money(value: Decimal | int | str) -> Decimal:
    """Round to whole cents, halves up – with room for huge values (the context of a thread has 28 digits)."""
    with localcontext() as context:
        context.prec = 80
        return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def month_number(day: datetime.date) -> int:
    """Months counted from year 0: January 2027 is 24324; the difference of two is the number of months between."""
    return day.year * 12 + day.month - 1


def first_of_month(day: datetime.date) -> datetime.date:
    """The first day of the month of a date."""
    return day.replace(day=1)


def months_counted(start: datetime.date, as_of: datetime.date) -> int:
    """How many months of depreciation have started by ``as_of``: the month of ``start`` and of ``as_of`` count in full.

    0 when ``as_of`` lies before the month of ``start``; 1 for any day in the month of acquisition.
    """
    return max(month_number(as_of) - month_number(start) + 1, 0)


def depreciable_base(cost: Decimal, *, memory: bool = False) -> Decimal:
    """What is written off over the life: the cost, or the cost minus the memory value (never below 0)."""
    if cost < 0:
        raise ValueError("The cost cannot be negative.")
    cost = money(cost)
    return max(cost - MEMORY_VALUE, ZERO) if memory else cost


def written_off_after(base: Decimal, life_months: int, months: int) -> Decimal:
    """The amount written off after ``months`` months of a life of ``life_months``: the rounded cumulative amount.

    0 for no month, the whole ``base`` from ``life_months`` months on (so the last month balances to the cent).
    """
    _check_life(life_months)
    if months <= 0 or base <= 0:
        return ZERO
    if months >= life_months:
        return money(base)
    with localcontext() as context:
        context.prec = 80
        return money(Decimal(base) * months / life_months)


def instalment(base: Decimal, life_months: int, month: int) -> Decimal:
    """The depreciation of the ``month``-th month (1 = the month of acquisition); 0 outside the life."""
    if month < 1 or month > life_months:
        return ZERO
    return written_off_after(base, life_months, month) - written_off_after(base, life_months, month - 1)


def _check_life(life_months: int) -> None:
    """A useful life is at least one month."""
    if int(life_months) < 1:
        raise ValueError("The useful life is at least one month.")


@dataclass(frozen=True)
class YearRow:
    """One year of the schedule."""

    year: int
    #: Months of the life that fall into this year (0 for a low-value asset: it is written off at once).
    months: int
    depreciation: Decimal
    #: Written off by the end of the year (31 December).
    accumulated: Decimal
    #: The book value on 31 December.
    book_value: Decimal


def schedule(
    kind: str,
    cost: Decimal,
    start: datetime.date,
    life_months: int | None = None,
    *,
    memory: bool = False,
) -> list[YearRow]:
    """The depreciation per year from the year of acquisition until the asset is written off.

    A fixed asset needs its useful life. A low-value asset has one row, the year of acquisition, with the whole
    cost. Merchandise has no schedule. The depreciation of the rows adds up to the base exactly.

    Raises:
        ValueError: A negative cost, or a fixed asset without a useful life of at least one month.
    """
    cost = money(cost)
    if cost < 0:
        raise ValueError("The cost cannot be negative.")
    if kind == KIND_LOW_VALUE:
        return [YearRow(start.year, 0, cost, cost, ZERO)]
    if kind != KIND_FIXED_ASSET:
        return []
    if life_months is None:
        raise ValueError("A fixed asset needs a useful life.")
    _check_life(life_months)
    base = depreciable_base(cost, memory=memory)
    first = month_number(start)
    last = first + life_months - 1
    rows: list[YearRow] = []
    previous = ZERO
    for year in range(first // 12, last // 12 + 1):
        # The months of the life that fall into this year: counted from the first one.
        begin = max(first, year * 12)
        end = min(last, year * 12 + 11)
        accumulated = written_off_after(base, life_months, end - first + 1)
        rows.append(YearRow(year, end - begin + 1, accumulated - previous, accumulated, cost - accumulated))
        previous = accumulated
    return rows


@dataclass(frozen=True)
class Valuation:
    """The book value of an asset on a day, and how it came about."""

    state: str
    kind: str = ""
    cost: Decimal | None = None
    life_months: int | None = None
    #: The first day of the month of acquisition; ``None`` without a date.
    start: datetime.date | None = None
    as_of: datetime.date | None = None
    #: Written off from the acquisition until ``as_of``; ``None`` when the state is "unclassified", "no cost" or "no date".
    accumulated: Decimal | None = None
    #: What was written off in the year of ``as_of`` up to ``as_of``.
    this_year: Decimal | None = None
    #: The book value on ``as_of``; ``None`` when there is none (see :data:`VALUED_STATES`).
    book_value: Decimal | None = None
    #: The book value at the end of the year before ``as_of`` (the opening value of the year).
    opening_value: Decimal | None = None
    #: The last month of the life of a fixed asset (first day of it).
    last_month: datetime.date | None = None
    #: The months of the life that are over / that remain on ``as_of``.
    months_done: int = 0
    months_left: int | None = None
    #: The yearly schedule (empty for merchandise and when nothing can be said).
    rows: list[YearRow] = field(default_factory=list)

    @property
    def has_book_value(self) -> bool:
        """Whether a book value could be worked out."""
        return self.book_value is not None


def _written_off(
    kind: str, base: Decimal, life: int | None, start: datetime.date, day: datetime.date, *, cost: Decimal
) -> Decimal:
    """The amount written off by the end of ``day`` (month principle; a GWG on 31 December of its year)."""
    if kind == KIND_LOW_VALUE:
        return cost if day >= datetime.date(start.year, 12, 31) else ZERO
    if kind == KIND_FIXED_ASSET and life is not None:
        return written_off_after(base, life, months_counted(start, day))
    return ZERO


def valuation(
    kind: str,
    cost: Decimal | None,
    acquired: datetime.date | None,
    life_months: int | None,
    as_of: datetime.date,
    *,
    memory: bool = False,
) -> Valuation:
    """The book value of an asset on ``as_of``: cost minus what was written off, never below 0.

    Args:
        kind: ``fixed_asset``, ``low_value``, ``merchandise`` – anything else is "unclassified".
        cost: The acquisition cost (net, with the ancillary costs); ``None`` if not known.
        acquired: The day of acquisition (for a date known to the month or year: the first day of the period).
        life_months: The useful life in months, for a fixed asset.
        as_of: The day the value is for.
        memory: Leave 1 € when the asset is fully depreciated.

    Without a kind, a cost, a date (for a fixed asset or a GWG) or a useful life (fixed asset) there is no book value
    (``None``); the state says what is missing. An acquisition after ``as_of`` is "not yet acquired": nothing is
    written off and there is no book value either.

    Raises:
        ValueError: A negative cost.
    """
    if kind not in (KIND_FIXED_ASSET, KIND_LOW_VALUE, KIND_MERCHANDISE):
        return Valuation(UNCLASSIFIED, as_of=as_of)
    if cost is None:
        return Valuation(NO_COST, kind=kind, life_months=life_months, as_of=as_of)
    cost = money(cost)
    if cost < 0:
        raise ValueError("The cost cannot be negative.")
    if kind == KIND_MERCHANDISE:
        return Valuation(
            MERCHANDISE, kind=kind, cost=cost, as_of=as_of, accumulated=ZERO, this_year=ZERO, book_value=cost,
            opening_value=cost,
        )  # fmt: skip
    if kind == KIND_FIXED_ASSET and not life_months:
        return Valuation(NO_LIFE, kind=kind, cost=cost, as_of=as_of)
    if acquired is None:
        return Valuation(NO_DATE, kind=kind, cost=cost, life_months=life_months, as_of=as_of)
    start = first_of_month(acquired)
    base = depreciable_base(cost, memory=memory)
    rows = schedule(kind, cost, start, life_months, memory=memory)
    last_month = None
    if kind == KIND_FIXED_ASSET:
        last = month_number(start) + int(life_months or 0) - 1
        last_month = datetime.date(last // 12, last % 12 + 1, 1)
    if acquired > as_of:
        return Valuation(
            NOT_YET, kind=kind, cost=cost, life_months=life_months, start=start, as_of=as_of, accumulated=ZERO,
            this_year=ZERO, last_month=last_month, rows=rows,
        )  # fmt: skip
    accumulated = _written_off(kind, base, life_months, start, as_of, cost=cost)
    year_start_before = datetime.date(as_of.year - 1, 12, 31)
    before = _written_off(kind, base, life_months, start, year_start_before, cost=cost)
    done = months_counted(start, as_of) if kind == KIND_FIXED_ASSET else 0
    left = max(int(life_months) - done, 0) if kind == KIND_FIXED_ASSET and life_months else None
    if kind == KIND_LOW_VALUE:
        state = WRITTEN_OFF if accumulated >= cost else LOW_VALUE_OPEN
    else:
        state = WRITTEN_OFF if done >= int(life_months or 0) else RUNNING
    return Valuation(
        state,
        kind=kind,
        cost=cost,
        life_months=life_months,
        start=start,
        as_of=as_of,
        accumulated=accumulated,
        this_year=accumulated - before,
        book_value=max(cost - accumulated, ZERO),
        opening_value=max(cost - before, ZERO),
        last_month=last_month,
        months_done=min(done, int(life_months or 0)),
        months_left=left,
        rows=rows,
    )


def scale(amount: Decimal, part: int, whole: int) -> Decimal:
    """``part`` of ``whole`` pieces of an amount, rounded to cents (a quantity of bulk material is sold)."""
    if whole <= 0 or part < 0 or part > whole:
        raise ValueError("The part must lie between 0 and the whole.")
    if part == whole:
        return money(amount)
    with localcontext() as context:
        context.prec = 80
        return money(Decimal(amount) * part / whole)
