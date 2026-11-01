# SPDX-License-Identifier: GPL-3.0-or-later
"""The periods of a project marked in the calendars of the period pickers (PRJ-099).

``{% load period_marks %}``, then on the element around the fields:

* ``data-calendar-marks="{% project_period_marks project %}"`` – the rental
  period and, if given, the event period of a saved project; for the forms
  of a phase (page "Zeitplanung" and the dialog over the crew planning).
* ``data-calendar-marks="{% form_period_marks %}"`` – the same two periods
  read from the fields of the project form while it is filled in, so that
  the calendar of the one shows the other as typed so far.

The page script (UIX-036, ``static/js/app.js``) reads the list and hatches
the days of each period in the calendars opened from the fields inside,
with a small legend; a period whose fields are the ones being chosen is
left out. Both tags return JSON text; the template escapes it for the
attribute.
"""

from __future__ import annotations

import json
from typing import Any

from django import template
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.forms import DATETIME_FORMAT

register = template.Library()

#: The kinds of marks the stylesheet knows: two different hatchings.
RENTAL, EVENT = "rental", "event"


def _moment(value: Any) -> str:
    return timezone.localtime(value).strftime(DATETIME_FORMAT)


def project_marks(project: Any) -> list[dict[str, str]]:
    """The rental period and the event period of a project, as marks for the calendars (PRJ-099)."""
    marks = [
        {"kind": RENTAL, "label": _("Rental period"), "start": _moment(project.start), "end": _moment(project.end)}
    ]
    if project.event_start and project.event_end:
        marks.append(
            {
                "kind": EVENT,
                "label": _("Event"),
                "start": _moment(project.event_start),
                "end": _moment(project.event_end),
            }
        )
    return marks


@register.simple_tag
def project_period_marks(project: Any) -> str:
    """JSON: the saved periods of the project."""
    return json.dumps(project_marks(project), ensure_ascii=False)


@register.simple_tag
def form_period_marks() -> str:
    """JSON: the periods of the project form, named by their fields."""
    return json.dumps(
        [
            {"kind": RENTAL, "label": _("Rental period"), "fields": ["start", "end"]},
            {"kind": EVENT, "label": _("Event"), "fields": ["event_start", "event_end"]},
        ],
        ensure_ascii=False,
    )
