# SPDX-License-Identifier: GPL-3.0-or-later
"""Hour tiers per day: from a limit of hours a day on, an hour costs more (PER-035).

The requirement: different hourly rates by duration, e.g. a higher wage from a limit of 10 hours – for the price and for the costs, counted per day.

The service product of a job function carries the limit (``hours_limit``,
hours per day) and the price per hour from the limit; a crew line copies
both, as it copies its price (PRJ-015). The person's rate for the job
function, or the guide value of the function, carries the cost of an hour
from the limit. The limit applies to lines billed by the hour only – "by
plan" and "by effort" –, never to a flat rate or a line billed per day.

Which hours of a day count:

* **By plan:** the planned hours. While they are the length of the period
  (the suggestion, PRJ-073), each calendar day has the hours of the period
  that fall on it: Monday 08:00 to Tuesday 20:00 is 16 hours on Monday and
  20 on Tuesday. Planned hours typed in by hand are spread evenly over the
  calendar days the period touches: 20 hours from Monday 08:00 to Tuesday
  20:00 are 10 on each day.
* **By effort:** the approved times, each counted on the day it starts (a
  night shift belongs to the day it began). Until times are approved the
  planned hours stand in, as above.

Example: limit 10, 45.00 an hour, 55.00 from the limit; planned Monday
08:00 to 20:00 (12 hours) → 10 × 45.00 + 2 × 55.00 = 560.00.

The functions here are plain arithmetic on what the caller loaded – they ask
the database nothing.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

ZERO = Decimal("0")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class HourSplit:
    """Hours split at a limit: those up to the limit of their day and those beyond it."""

    normal: Decimal = ZERO
    above: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        """All hours."""
        return self.normal + self.above


def local_days(start: datetime.datetime, end: datetime.datetime) -> list[tuple[datetime.date, Decimal]]:
    """The hours of a period on each local calendar day it touches, in order of the days.

    Also used by the surcharges for night, Sunday and holiday work (PER-009, ``projects.time_surcharges``).
    """
    result: list[tuple[datetime.date, Decimal]] = []
    current = start
    while current < end:
        local = timezone.localtime(current)
        next_midnight = timezone.make_aware(
            datetime.datetime.combine(local.date() + datetime.timedelta(days=1), datetime.time()),
            local.tzinfo,
        )
        piece_end = min(end, next_midnight)
        seconds = Decimal((piece_end.astimezone(datetime.UTC) - current.astimezone(datetime.UTC)).total_seconds())
        result.append((local.date(), seconds / Decimal(3600)))
        current = piece_end
    return result


def planned_hours_per_day(
    start: datetime.datetime | None, end: datetime.datetime | None, planned: Decimal, period_hours: Decimal
) -> list[Decimal]:
    """The planned hours of a crew line on each calendar day of its period (PER-035).

    Args:
        start: Begin of the line's period.
        end: End of the line's period.
        planned: The planned hours of the line.
        period_hours: The hours suggested for the period (``models.suggested_hours``).

    Returns:
        One number per calendar day the period touches; together they are
        ``planned``. The hours of the period as they fall on each day if the
        planned hours are the suggested ones, else ``planned`` spread evenly.
    """
    if not start or not end or end <= start or planned <= ZERO:
        return [planned] if planned > ZERO else []
    days = local_days(start, end)
    if not days:
        return [planned]
    if planned == period_hours:
        shares = [hours for _day, hours in days]
    else:
        shares = [Decimal(1)] * len(days)
    total = sum(shares, ZERO)
    if total <= ZERO:
        return [planned]
    result = [(planned * share / total).quantize(CENT, rounding=ROUND_HALF_UP) for share in shares]
    # Rounding must not lose or add a cent of an hour: the last day takes the difference.
    result[-1] += planned - sum(result, ZERO)
    return result


def split_at_limit(hours_per_day: Iterable[Decimal], limit: Decimal | None) -> HourSplit:
    """Split hours at a limit per day: up to the limit of each day, and beyond it (PER-035).

    Example: ``[12, 8, 11]`` with the limit 10 → 28 normal, 3 beyond.
    """
    normal = above = ZERO
    for hours in hours_per_day:
        if limit is not None and hours > limit:
            normal += limit
            above += hours - limit
        else:
            normal += hours
    return HourSplit(normal=normal, above=above)


def approved_hours_per_day(entries: Iterable[tuple[datetime.date, Decimal, Decimal]]) -> list[Decimal]:
    """The approved hours of a line per day its entries start on (PER-035); ``entries`` as (day, hours, rate)."""
    by_day: dict[datetime.date, Decimal] = {}
    for day, hours, _rate in entries:
        by_day[day] = by_day.get(day, ZERO) + hours
    return [by_day[day] for day in sorted(by_day)]


def actual_cost_with_limit(
    entries: Iterable[tuple[datetime.date, Decimal, Decimal]], limit: Decimal | None, rate_above: Decimal | None
) -> Decimal:
    """What approved times cost when the hours of a day beyond the limit cost ``rate_above`` (PER-035).

    The entries of a day count in the order given (their start): the hours up
    to the limit at the rate fixed on each entry (ZEI-008), the rest at
    ``rate_above`` – or the entry's rate where there is none.
    """
    used: dict[datetime.date, Decimal] = {}
    cost = ZERO
    for day, hours, rate in entries:
        before = used.get(day, ZERO)
        used[day] = before + hours
        if limit is None or rate_above is None:
            cost += hours * rate
            continue
        within = max(min(hours, limit - before), ZERO)
        cost += within * rate + (hours - within) * rate_above
    return cost.quantize(CENT, rounding=ROUND_HALF_UP)
