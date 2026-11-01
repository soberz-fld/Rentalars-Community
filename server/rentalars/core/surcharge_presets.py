# SPDX-License-Identifier: GPL-3.0-or-later
"""The rules of the surcharges as § 3b EStG has them – the preset of Einstellungen → Zuschläge (PER-040, PER-009).

The surcharges for night, Sunday and holiday work are a list of
rules (``core.models.TimeSurchargeRule``) that works in any country; the
calculation is ``projects.time_surcharges``. The button "Nach § 3b EStG
einstellen" replaces the list by the rules built here, and a new
installation starts with them. They are those, written as rules:

=====================================  ===========================  ======  ================
name                                   rule                         rate    § 3b EStG
=====================================  ===========================  ======  ================
Nacht                                  time of day 20:00–06:00      25 %    (1) Nr. 1, (2)
Nacht 0–4 Uhr                          time of day 00:00–04:00,     40 %    (3) Nr. 1
                                       only for work begun before
                                       midnight
Sonntag                                weekday Sunday               50 %    (1) Nr. 2
Feiertag                               public holiday               125 %   (1) Nr. 3
Feiertag                               31.12. from 14:00            125 %   (1) Nr. 3
Weihnachten und 1. Mai                 24.12. from 14:00            150 %   (1) Nr. 4
Weihnachten und 1. Mai                 25.12., 26.12., 1.5.         150 %   (1) Nr. 4
=====================================  ===========================  ======  ================

and ``next_day_until`` 04:00: a Sunday or holiday reaches until 04:00 of the
next day for work begun before midnight (§ 3b (3) Nr. 2). Rules with the same
name and rate are one kind of surcharge in the planning and the documents, so
"Feiertag" and "Weihnachten und 1. Mai" show as one line each.

``code`` marks the rules of the preset with their kind (``night``,
``night_after_midnight``, ``sunday``, ``holiday``, ``high_holiday``); the API
names a surcharge by it (``kind``). Rules made by hand have none.

Everything here is plain data.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.utils import translation
from django.utils.translation import pgettext

#: The kinds of rule (``TimeSurchargeRule.kind``).
TIME = "time"
WEEKDAY = "weekday"
HOLIDAY = "holiday"
DATE = "date"
#: Of the rules of these kinds only the highest counts at a time; the time-of-day rules add to it.
DAY_KINDS = (WEEKDAY, HOLIDAY, DATE)

#: The codes of the rules of the preset – the kinds of surcharge.
NIGHT = "night"
NIGHT_AFTER_MIDNIGHT = "night_after_midnight"
SUNDAY = "sunday"
HOLIDAY_CODE = "holiday"
HIGH_HOLIDAY = "high_holiday"
CODES = (NIGHT, NIGHT_AFTER_MIDNIGHT, SUNDAY, HOLIDAY_CODE, HIGH_HOLIDAY)

#: The rates of § 3b EStG, the same for the price and the costs.
DEFAULT_PERCENTS = {
    NIGHT: Decimal("25"),
    NIGHT_AFTER_MIDNIGHT: Decimal("40"),
    SUNDAY: Decimal("50"),
    HOLIDAY_CODE: Decimal("125"),
    HIGH_HOLIDAY: Decimal("150"),
}
DEFAULT_NIGHT_START = datetime.time(20, 0)
DEFAULT_NIGHT_END = datetime.time(6, 0)
#: § 3b (3) EStG: until this hour of the next day, work begun before midnight counts as such.
EARLY_MORNING_END = datetime.time(4, 0)
#: § 3b (1) Nr. 3 and 4 EStG: 24 and 31 December count from this hour.
AFTERNOON = datetime.time(14, 0)
#: ISO weekday of Sunday (``TimeSurchargeRule.weekdays`` holds ISO weekdays, 1 Monday to 7 Sunday).
ISO_SUNDAY = 7


def preset_names(language: str | None = None) -> dict[str, str]:
    """The names of the rules of the preset, in the language of the installation (or the one given, UIX-029)."""
    with translation.override(language or settings.LANGUAGE_CODE):
        return {
            NIGHT: pgettext("time surcharge", "Night"),
            # UIX-029: "Night 0–4", without "o'clock"; German stays "Nacht 0–4 Uhr".
            NIGHT_AFTER_MIDNIGHT: pgettext("time surcharge", "Night 0–4"),
            SUNDAY: pgettext("time surcharge", "Sunday"),
            HOLIDAY_CODE: pgettext("time surcharge", "Holiday"),
            HIGH_HOLIDAY: pgettext("time surcharge", "Christmas and 1 May"),
        }


def _minutes(clock: datetime.time) -> int:
    return clock.hour * 60 + clock.minute


def _clock(minutes: int) -> datetime.time:
    return datetime.time(minutes // 60, minutes % 60)


def windows_before(start: datetime.time, end: datetime.time, limit: datetime.time) -> list[tuple[Any, Any]]:
    """The parts of a time-of-day window (it may reach over midnight) between 00:00 and ``limit``.

    The rule "night 0–4, begun before midnight" holds only within the
    night window; this gives its windows. Examples: 20:00–06:00 → [00:00–04:00];
    22:00–05:00 → [00:00–04:00]; 01:00–03:00 → [01:00–03:00]; 20:00–23:00 → [].
    """
    first, last, top = _minutes(start), _minutes(end), _minutes(limit)
    if first == last:
        return []
    spans = [(first, last)] if first < last else [(0, last), (first, 24 * 60)]
    result = []
    for low, high in spans:
        low, high = max(low, 0), min(high, top)
        if low < high:
            result.append((_clock(low), _clock(high % (24 * 60))))
    return result


def section_3b(
    *,
    night_start: datetime.time = DEFAULT_NIGHT_START,
    night_end: datetime.time = DEFAULT_NIGHT_END,
    started_before_midnight: bool = True,
    price: Mapping[str, Decimal] | None = None,
    cost: Mapping[str, Decimal] | None = None,
    names: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], datetime.time | None]:
    """The rules of § 3b EStG as field values of ``TimeSurchargeRule``, and the value of ``next_day_until``.

    Args:
        night_start: Begin of the night window (a setting, by default 20:00).
        night_end: Its end (06:00).
        started_before_midnight: § 3b (3): the rate "0 to 4" for night work
            begun before midnight, and Sunday or holiday until 04:00 of the
            next day; off: neither.
        price: Percentages by code for the price; default those of the law.
        cost: The same for the costs.
        names: The names by code; default :func:`preset_names`.

    """
    price = {**DEFAULT_PERCENTS, **(price or {})}
    cost = {**DEFAULT_PERCENTS, **(cost or {})}
    names = names or preset_names()

    def rule(code: str, kind: str, **fields: Any) -> dict[str, Any]:
        values = {
            "name": names[code],
            "kind": kind,
            "time_from": None,
            "time_until": None,
            "weekdays": "",
            "month": None,
            "day": None,
            "begun_before_midnight": False,
            "price_percent": price[code],
            "cost_percent": cost[code],
            "code": code,
        }
        values.update(fields)
        return values

    rules = [rule(NIGHT, TIME, time_from=night_start, time_until=night_end)]
    if started_before_midnight:
        rules.extend(
            rule(NIGHT_AFTER_MIDNIGHT, TIME, time_from=start, time_until=end, begun_before_midnight=True)
            for start, end in windows_before(night_start, night_end, EARLY_MORNING_END)
        )
    rules.append(rule(SUNDAY, WEEKDAY, weekdays=str(ISO_SUNDAY)))
    rules.append(rule(HOLIDAY_CODE, HOLIDAY))
    rules.append(rule(HOLIDAY_CODE, DATE, month=12, day=31, time_from=AFTERNOON))
    rules.append(rule(HIGH_HOLIDAY, DATE, month=12, day=24, time_from=AFTERNOON))
    rules.extend(rule(HIGH_HOLIDAY, DATE, month=month, day=day) for month, day in ((12, 25), (12, 26), (5, 1)))
    for position, values in enumerate(rules, start=1):
        values["position"] = position
    return rules, (EARLY_MORNING_END if started_before_midnight else None)
