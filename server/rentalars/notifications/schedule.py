# SPDX-License-Identifier: GPL-3.0-or-later
"""When the shortage check is due (VFG-036).

The company sets a time of day and how often – every day, on working days
(Monday to Friday without the holidays of Einstellungen → Zuschläge), once a
week on one day, or never (:class:`~rentalars.core.notification_settings.NotificationSettings`).
These functions turn that into moments:

* :func:`latest_slot` – the latest moment at or before *now* at which a check
  was due. The minute timer (``run_jobs``) checks once that moment is later
  than the last check: a check missed because the server was off is made up
  once at the next run, as ``Persistent=true`` did for the nightly timer.
* :func:`next_run` – when the next check will happen, for the settings page
  and the API.

All moments are in the time zone of the installation (``[rentalars]
time_zone``).
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from django.utils import timezone

from rentalars.core.notification_settings import ShortageInterval

#: How far a search for the next or the latest day of a check goes: Christmas with a weekend is shorter.
_SEARCH_DAYS = 21

HolidayTest = Callable[[datetime.date], bool]


def holiday_test() -> HolidayTest:
    """Whether a day is a holiday as Einstellungen → Zuschläge sets them: statutory ones (if on) and own ones.

    Reads the settings without creating them (the first use of the surcharge
    settings makes their rules – not the business of a notification): without
    a row, the statutory holidays of the whole of Germany count, as the
    defaults there.
    """
    from rentalars.core.holidays import NATIONWIDE, calendar_of
    from rentalars.core.models import OwnHoliday, TimeSurchargeSettings

    stored = TimeSurchargeSettings.objects.filter(pk=1).first()
    state = stored.state if stored is not None else NATIONWIDE
    german = stored.german_holidays if stored is not None else True
    own = tuple(holiday.spec() for holiday in OwnHoliday.objects.order_by("id"))
    years: dict[int, Any] = {}

    def is_holiday(day: datetime.date) -> bool:
        if day.year not in years:
            years[day.year] = calendar_of(day.year, state, german, own)
        return day in years[day.year]

    return is_holiday


def counts(settings: Any, day: datetime.date, is_holiday: HolidayTest | None = None) -> bool:
    """Whether a check is due on ``day`` at all; without ``is_holiday`` no day counts as a holiday."""
    interval = settings.shortage_interval
    if interval == ShortageInterval.DAILY:
        return True
    if interval == ShortageInterval.WEEKLY:
        return day.isoweekday() == settings.shortage_weekday
    if interval == ShortageInterval.WORKDAYS:
        return day.isoweekday() <= 5 and not (is_holiday is not None and is_holiday(day))
    return False


def _moment(day: datetime.date, clock: datetime.time) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime.combine(day, clock))


def latest_slot(
    settings: Any, now: datetime.datetime, is_holiday: HolidayTest | None = None
) -> datetime.datetime | None:
    """The latest moment at or before ``now`` at which a check was due; ``None`` when switched off.

    Without ``is_holiday`` the holidays are not left out, so the moment is
    never earlier than with them – a quick first test.
    """
    if settings.shortage_interval == ShortageInterval.OFF:
        return None
    local = timezone.localtime(now)
    day = local.date()
    if local.time() < settings.shortage_time:
        day -= datetime.timedelta(days=1)
    for _step in range(_SEARCH_DAYS):
        if counts(settings, day, is_holiday):
            return _moment(day, settings.shortage_time)
        day -= datetime.timedelta(days=1)
    return None


def first_slot_after(
    settings: Any, moment: datetime.datetime, is_holiday: HolidayTest | None = None
) -> datetime.datetime | None:
    """The first moment of a check after ``moment``; ``None`` when switched off."""
    if settings.shortage_interval == ShortageInterval.OFF:
        return None
    local = timezone.localtime(moment)
    day = local.date()
    if local.time() >= settings.shortage_time:
        day += datetime.timedelta(days=1)
    for _step in range(_SEARCH_DAYS):
        if counts(settings, day, is_holiday):
            return _moment(day, settings.shortage_time)
        day += datetime.timedelta(days=1)
    return None


def next_run(settings: Any, now: datetime.datetime | None = None) -> datetime.datetime | None:
    """When the next check happens: ``now`` if one is overdue (the next minute), ``None`` when switched off."""
    if settings.shortage_interval == ShortageInterval.OFF:
        return None
    now = now or timezone.now()
    is_holiday = holiday_test() if settings.shortage_interval == ShortageInterval.WORKDAYS else None
    last = settings.shortage_last_run
    latest = latest_slot(settings, now, is_holiday)
    if last is not None and latest is not None and last < latest:
        return now
    return first_slot_after(settings, now, is_holiday)
