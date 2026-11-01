# SPDX-License-Identifier: GPL-3.0-or-later
"""The years a dropdown offers (year dropdowns; UIX-054).

One place for the range of every year dropdown – the reports so far –, so that they agree: the past as before, and
three years ahead instead of one, because orders are planned that far. Nothing stored changes; this only builds the
list a page offers.
"""

from __future__ import annotations

from django.utils import timezone

#: How many years ahead of the current one a dropdown offers.
YEARS_AHEAD = 3

#: How many years back from the current one a dropdown offers.
YEARS_PAST = 5


def year_choices(*, past: int = YEARS_PAST, ahead: int = YEARS_AHEAD, selected: int | None = None) -> list[int]:
    """The years to choose from, the latest first: ``ahead`` years after the current one down to ``past`` before it.

    Args:
        past: How many years before the current year are offered.
        ahead: How many years after the current year are offered.
        selected: A year already chosen (e.g. from the address); it is offered even if it lies outside the range.

    Returns:
        The years, the latest first. The current year is the default selection of the pages: they preselect it
        themselves, this list only says what exists.
    """
    current = timezone.localdate().year
    years = set(range(current - past, current + ahead + 1))
    if selected is not None:
        years.add(selected)
    return sorted(years, reverse=True)
