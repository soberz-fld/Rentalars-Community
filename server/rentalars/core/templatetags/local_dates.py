# SPDX-License-Identifier: GPL-3.0-or-later
"""The filters ``date`` and ``time`` in the language of the page (UIX-029).

A built-in library (``TEMPLATES`` in the settings): it replaces Django's two
filters in every template. Templates keep writing the German patterns they
always had – ``|date:"d.m.Y"``, ``|date:"D d.m. H:i"`` –; while English is
active, the pattern is turned into the British one first (``d/m/Y``,
``D d/m H:i``, see :func:`rentalars.core.i18n.local_pattern`). Without a
pattern, or with ``"SHORT_DATE_FORMAT"`` and the like, Django's formats of
the language apply as before.
"""

from __future__ import annotations

from typing import Any

from django import template
from django.template import defaultfilters

from rentalars.core.i18n import local_pattern

register = template.Library()


@register.filter(expects_localtime=True, is_safe=False)
def date(value: Any, arg: str | None = None) -> str:
    """Django's ``date`` with the pattern in the form of the active language."""
    return defaultfilters.date(value, local_pattern(arg) if arg else arg)


@register.filter(expects_localtime=True, is_safe=False)
def time(value: Any, arg: str | None = None) -> str:
    """Django's ``time`` with the pattern in the form of the active language."""
    return defaultfilters.time(value, local_pattern(arg) if arg else arg)
