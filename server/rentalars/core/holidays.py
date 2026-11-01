# SPDX-License-Identifier: GPL-3.0-or-later
"""German public holidays per federal state, computed – no list to maintain, no network (PER-009).

The surcharges for work on holidays (``projects.time_surcharges``) need to
know which days are statutory holidays where the company works. § 3b (2)
EStG: "Die gesetzlichen Feiertage werden durch die am Ort der Arbeitsstätte
geltenden Vorschriften bestimmt" – the holiday laws of the federal states.
The state is a setting (``TimeSurchargeSettings.state``); without one only
the holidays of the whole country count.

What is computed:

* **Fixed days** – New Year, 1 May, 3 October (from 1990), Christmas, and
  the fixed days of single states (6 January, 8 March, 15 August, 20
  September, 31 October, 1 November, 8 August in Augsburg).
* **Days that move with Easter** – Good Friday, Easter Sunday and Monday,
  Ascension, Whit Sunday and Monday, Corpus Christi. Easter Sunday by the
  Gregorian computus (Meeus/Jones/Butcher), valid for every year from 1583.
* **Repentance Day** ("Buß- und Bettag") – the Wednesday before 23
  November: in Saxony; in the whole country until 1994.
* **Changes of the laws** – Reformation Day in Bremen, Hamburg, Lower
  Saxony and Schleswig-Holstein since 2018, in the whole country once in
  2017; Women's Day in Berlin since 2019 and in Mecklenburg-Western
  Pomerania since 2023; World Children's Day in Thuringia since 2019; Day of
  Liberation in Berlin in 2020 and 2025 only.

Holidays only of some communities of a state are offered as states of their
own: Bavaria with or without Assumption Day (in most Bavarian communities
it is a holiday), the city of Augsburg (Peace Festival), the communities of
Saxony and Thuringia that keep Corpus Christi. Easter Sunday and Whit Sunday
are statutory holidays only in Brandenburg; elsewhere they count as Sundays.

The state of the law is that of 2026. Every function here is plain
arithmetic; one year of one state is computed once and kept
(:func:`holidays_of`).

PER-040: the surcharges work in any country. Besides (or instead of)
the statutory holidays of Germany a company keeps its own holidays – a day
every year, a single date, or a number of days from Easter Sunday
(:class:`OwnHolidaySpec`); :func:`calendar_of` gives the days that count.
Nothing is asked from a service on the internet: Rentalars computes the
holidays itself, the movable ones from the date of Easter.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.utils.translation import gettext_lazy as _

#: ``""``: only the holidays of the whole country.
NATIONWIDE = ""

#: The choices of the setting, in the order of the states' names; codes as in ISO 3166-2:DE, plus the variants.
STATE_CHOICES = [
    (NATIONWIDE, _("only the holidays of the whole country")),
    ("BW", _("Baden-Württemberg")),
    ("BY", _("Bavaria (with Assumption Day, as in most communities)")),
    ("BYE", _("Bavaria without Assumption Day")),
    ("BYA", _("Bavaria, city of Augsburg (with the Peace Festival)")),
    ("BE", _("Berlin")),
    ("BB", _("Brandenburg")),
    ("HB", _("Bremen")),
    ("HH", _("Hamburg")),
    ("HE", _("Hesse")),
    ("MV", _("Mecklenburg-Western Pomerania")),
    ("NI", _("Lower Saxony")),
    ("NW", _("North Rhine-Westphalia")),
    ("RP", _("Rhineland-Palatinate")),
    ("SL", _("Saarland")),
    ("SN", _("Saxony")),
    ("SNF", _("Saxony, communities with Corpus Christi")),
    ("ST", _("Saxony-Anhalt")),
    ("SH", _("Schleswig-Holstein")),
    ("TH", _("Thuringia")),
    ("THF", _("Thuringia, communities with Corpus Christi")),
]
STATES = frozenset(code for code, _label in STATE_CHOICES)
#: The states without the empty choice – the API names their list ``FederalStateEnum`` (``settings.SPECTACULAR_SETTINGS``).
STATE_CHOICES_OF_THE_API = [(code, label) for code, label in STATE_CHOICES if code]

#: The names of the holidays, by key.
NAMES = {
    "new_year": _("New Year's Day"),
    "epiphany": _("Epiphany"),
    "womens_day": _("International Women's Day"),
    "good_friday": _("Good Friday"),
    "easter_sunday": _("Easter Sunday"),
    "easter_monday": _("Easter Monday"),
    "labour_day": _("Labour Day"),
    "liberation_day": _("Day of Liberation"),
    "ascension": _("Ascension Day"),
    "whit_sunday": _("Whit Sunday"),
    "whit_monday": _("Whit Monday"),
    "corpus_christi": _("Corpus Christi"),
    "peace_festival": _("Augsburg Peace Festival"),
    "assumption": _("Assumption Day"),
    "childrens_day": _("World Children's Day"),
    "unity_day": _("Day of German Unity"),
    "reformation_day": _("Reformation Day"),
    "all_saints": _("All Saints' Day"),
    "repentance_day": _("Day of Repentance and Prayer"),
    "christmas_day": _("Christmas Day"),
    "boxing_day": _("Second Day of Christmas"),
}

_BAVARIA = frozenset({"BY", "BYE", "BYA"})
_SAXONY = frozenset({"SN", "SNF"})
_THURINGIA = frozenset({"TH", "THF"})
_EPIPHANY = _BAVARIA | {"BW", "ST"}
_CORPUS_CHRISTI = _BAVARIA | {"BW", "HE", "NW", "RP", "SL", "SNF", "THF"}
_ASSUMPTION = frozenset({"BY", "BYA", "SL"})
_ALL_SAINTS = _BAVARIA | {"BW", "NW", "RP", "SL"}
_REFORMATION_ALWAYS = _SAXONY | _THURINGIA | {"BB", "MV", "ST"}
_REFORMATION_SINCE_2018 = frozenset({"HB", "HH", "NI", "SH"})


def easter_sunday(year: int) -> datetime.date:
    """Easter Sunday of a year in the Gregorian calendar (anonymous computus of Meeus, Jones and Butcher).

    Examples: 2026 → 5 April, 2027 → 28 March, 2038 → 25 April.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_shift = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_shift) // 451
    month, day = divmod(h + weekday_shift - 7 * m + 114, 31)
    return datetime.date(year, month, day + 1)


def repentance_day(year: int) -> datetime.date:
    """The Day of Repentance and Prayer: the Wednesday before 23 November (16 to 22 November)."""
    before = datetime.date(year, 11, 22)
    return before - datetime.timedelta(days=(before.weekday() - 2) % 7)


@lru_cache(maxsize=256)
def holidays_of(year: int, state: str = NATIONWIDE) -> dict[datetime.date, str]:
    """The statutory holidays of one year in one federal state: ``{day: key of the name}`` (PER-009).

    Args:
        year: The year.
        state: A code of :data:`STATE_CHOICES`; ``""`` (or an unknown code) for the holidays of the whole country.

    Example: ``holidays_of(2026, "BY")`` has 13 days, among them 4 June (Corpus Christi) and 15 August.
    """
    easter = easter_sunday(year)

    def after_easter(days: int) -> datetime.date:
        return easter + datetime.timedelta(days=days)

    days: dict[datetime.date, str] = {
        datetime.date(year, 1, 1): "new_year",
        after_easter(-2): "good_friday",
        after_easter(1): "easter_monday",
        datetime.date(year, 5, 1): "labour_day",
        after_easter(39): "ascension",
        after_easter(50): "whit_monday",
        datetime.date(year, 12, 25): "christmas_day",
        datetime.date(year, 12, 26): "boxing_day",
    }
    if year >= 1990:
        days[datetime.date(year, 10, 3)] = "unity_day"
    if year < 1995:
        days[repentance_day(year)] = "repentance_day"
    if year == 2017:
        days[datetime.date(year, 10, 31)] = "reformation_day"  # the 500th anniversary, in every state
    if state not in STATES or state == NATIONWIDE:
        return days

    if state in _EPIPHANY:
        days[datetime.date(year, 1, 6)] = "epiphany"
    if (state == "BE" and year >= 2019) or (state == "MV" and year >= 2023):
        days[datetime.date(year, 3, 8)] = "womens_day"
    if state == "BB":
        days[easter] = "easter_sunday"
        days[after_easter(49)] = "whit_sunday"
    if state == "BE" and year in (2020, 2025):
        days[datetime.date(year, 5, 8)] = "liberation_day"
    if state in _CORPUS_CHRISTI:
        days[after_easter(60)] = "corpus_christi"
    if state == "BYA":
        days[datetime.date(year, 8, 8)] = "peace_festival"
    if state in _ASSUMPTION:
        days[datetime.date(year, 8, 15)] = "assumption"
    if state in _THURINGIA and year >= 2019:
        days[datetime.date(year, 9, 20)] = "childrens_day"
    if state in _REFORMATION_ALWAYS or (state in _REFORMATION_SINCE_2018 and year >= 2018):
        days[datetime.date(year, 10, 31)] = "reformation_day"
    if state in _ALL_SAINTS:
        days[datetime.date(year, 11, 1)] = "all_saints"
    if state in _SAXONY and year >= 1995:
        days[repentance_day(year)] = "repentance_day"
    return days


def is_holiday(day: datetime.date, state: str = NATIONWIDE) -> bool:
    """Whether a day is a statutory holiday in the state (PER-009)."""
    return day in holidays_of(day.year, state)


def holiday_list(years: Iterable[int], state: str = NATIONWIDE) -> list[tuple[datetime.date, str]]:
    """The holidays of some years as ``(day, name)`` in the order of the days – for the settings page."""
    found = [(day, str(NAMES[key])) for year in years for day, key in holidays_of(year, state).items()]
    return sorted(found)


#: PER-040: the kinds of an own holiday (``core.models.OwnHoliday``).
OWN_YEARLY = "yearly"
OWN_ONCE = "once"
OWN_EASTER = "easter"
#: The days from Easter Sunday an own holiday may lie: it stays in the year of its Easter.
EASTER_OFFSET_MIN, EASTER_OFFSET_MAX = -80, 240


@dataclass(frozen=True)
class OwnHolidaySpec:
    """An own holiday of the company (PER-040): a day every year, one single date, or days from Easter Sunday.

    Examples: Austria's national holiday ``("Nationalfeiertag", "yearly", month=10, day=26)``,
    a company party ``("Betriebsfest", "once", date=2027-06-18)``, Easter Monday
    ``("Ostermontag", "easter", offset=1)``.
    """

    name: str
    kind: str
    month: int | None = None
    day: int | None = None
    date: datetime.date | None = None
    offset: int | None = None

    def day_in(self, year: int) -> datetime.date | None:
        """The day of the holiday in a year, or ``None`` – 29 February in a common year, a single date elsewhen."""
        if self.kind == OWN_YEARLY and self.month and self.day:
            try:
                return datetime.date(year, self.month, self.day)
            except ValueError:
                return None
        if self.kind == OWN_ONCE and self.date is not None:
            return self.date if self.date.year == year else None
        if self.kind == OWN_EASTER and self.offset is not None:
            found = easter_sunday(year) + datetime.timedelta(days=self.offset)
            return found if found.year == year else None
        return None


@lru_cache(maxsize=256)
def calendar_of(
    year: int, state: str = NATIONWIDE, german: bool = True, own: tuple[OwnHolidaySpec, ...] = ()
) -> dict[datetime.date, list[tuple[Any, bool]]]:
    """The holidays that count for the surcharges in a year (PER-040): ``{day: [(name, own?), …]}``.

    Args:
        year: The year.
        state: The federal state of the statutory holidays (:func:`holidays_of`).
        german: Whether the statutory holidays of Germany count at all; off: only the own ones.
        own: The own holidays of the company.

    Example: ``calendar_of(2027, "", False, (OwnHolidaySpec("Nationalfeiertag", "yearly", 10, 26),))``
    → ``{2027-10-26: [("Nationalfeiertag", True)]}``.
    """
    days: dict[datetime.date, list[tuple[Any, bool]]] = {}
    if german:
        for day, key in holidays_of(year, state).items():
            # The lazy name: the list is kept (``lru_cache``) and shown in the language of each page.
            days.setdefault(day, []).append((NAMES[key], False))
    for holiday in own:
        day = holiday.day_in(year)
        if day is not None:
            days.setdefault(day, []).append((holiday.name, True))
    return days


def holiday_rows(
    years: Iterable[int], state: str = NATIONWIDE, german: bool = True, own: tuple[OwnHolidaySpec, ...] = ()
) -> list[tuple[datetime.date, str, bool]]:
    """The holidays of some years as ``(day, name, own?)`` in the order of the days – for the settings page."""
    return sorted(
        (day, str(name), is_own)
        for year in years
        for day, names in calendar_of(year, state, german, own).items()
        for name, is_own in names
    )


def state_label(state: str) -> str:
    """The name of a state as offered in the setting."""
    return str(dict(STATE_CHOICES).get(state, dict(STATE_CHOICES)[NATIONWIDE]))
