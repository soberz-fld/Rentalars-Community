# SPDX-License-Identifier: GPL-3.0-or-later
"""The rules and holidays of the surcharges as stored – reading, first use, "Nach § 3b EStG einstellen" (PER-040).

The calculation (``projects.time_surcharges``) reads them through
:func:`load_rule_set`; Einstellungen → Zuschläge (``core.surcharge_views``)
and the API (``core.surcharge_api``) change them.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from rentalars.core.audit import create_in_bulk
from rentalars.core.models import OwnHoliday, TimeSurchargeRule, TimeSurchargeSettings, _request_cache
from rentalars.core.surcharge_presets import section_3b

#: Where the rule set is kept for the rest of a request (``core.models._request_cache``).
_CACHE_KEY = "time_surcharge_rule_set"


def forget_cached_rules() -> None:
    """Drop the rule set kept for the request – after the rules or holidays were changed."""
    cache = _request_cache.get()
    if cache is not None:
        cache.pop(_CACHE_KEY, None)


def install_section_3b(settings: TimeSurchargeSettings) -> None:
    """Make the rules of § 3b EStG, as a new installation has them.

    Called when the settings row is saved for the first time (``TimeSurchargeSettings.save``).
    """
    specs, next_day_until = section_3b()
    create_in_bulk([TimeSurchargeRule(**values) for values in specs])
    settings.next_day_until = next_day_until
    settings.rules_set_up = True
    settings.save()
    forget_cached_rules()


def ensure_rules(settings: TimeSurchargeSettings | None = None) -> TimeSurchargeSettings:
    """The settings, with the rules of § 3b EStG made if that did not happen yet (PER-040)."""
    settings = settings or TimeSurchargeSettings.load()
    if not settings.rules_set_up:
        with transaction.atomic():
            settings = TimeSurchargeSettings.objects.select_for_update().get(pk=settings.pk)
            if not settings.rules_set_up:
                install_section_3b(settings)
    return settings


def set_section_3b() -> list[TimeSurchargeRule]:
    """The button "Nach § 3b EStG einstellen": replace every rule by those of the law (PER-040).

    The holidays (federal state, own holidays) and the switches stay as they
    are; ``next_day_until`` becomes 04:00. Each deleted and created rule is
    in the change log.
    """
    settings = ensure_rules()
    with transaction.atomic():
        for rule in TimeSurchargeRule.objects.all():
            rule.delete()
        specs, next_day_until = section_3b()
        created = create_in_bulk([TimeSurchargeRule(**values) for values in specs])
        settings.next_day_until = next_day_until
        settings.save()
    forget_cached_rules()
    return created


def load_rule_set() -> tuple[TimeSurchargeSettings, list[TimeSurchargeRule], list[OwnHoliday]]:
    """Settings, rules in their order and own holidays – kept for the rest of the request (PER-040).

    Three queries at most (two without a rule for holidays), once per request;
    the first use makes the rules of § 3b EStG.
    """
    cache = _request_cache.get()
    if cache is not None and _CACHE_KEY in cache:
        return cache[_CACHE_KEY]
    settings = ensure_rules()
    rules = list(TimeSurchargeRule.objects.order_by("position", "id"))
    own = list(OwnHoliday.objects.order_by("id")) if any(rule.kind == "holiday" for rule in rules) else []
    result: Any = (settings, rules, own)
    if cache is not None:
        cache[_CACHE_KEY] = result
    return result
