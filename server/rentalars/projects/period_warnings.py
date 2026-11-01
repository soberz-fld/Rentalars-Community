# SPDX-License-Identifier: GPL-3.0-or-later
"""Warnings about the periods of a project (PRJ-005, "event end").

The event period lies within the rental period – the material is out of the
warehouse for the event: ``event_end`` may be at most the end of the rental
period ("Material zurück bis"). An event that ends later is no error, saving
stays possible, but everybody who sets the period is told:

* the project form – live while the fields are typed (``app.js``, the
  element ``[data-event-warning]``) and, after saving, as a message;
* the API – the list ``warnings`` of the project (``ProjectSerializer``);
* dragging the event or the rental period in a timeline – the confirmation
  and the answer of ``/projects/{id}/reschedule`` (``schedule.moves``).

One function (:func:`project_warnings`) serves all of them (API-002).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.utils.translation import gettext as _


def event_after_material_back(
    end: datetime.datetime | None, event_end: datetime.datetime | None, *, is_service_case: bool = False
) -> bool:
    """Whether an event ends after the material is back (PRJ-005).

    Nothing to say without an event, without a rental period or for a service
    case, which has no rental period of its own.
    """
    return bool(not is_service_case and end and event_end and event_end > end)


def event_warning_text() -> str:
    """The warning, as shown to the user."""
    return _("The event ends after “Material back by”. Check the period.")


def project_warnings(project: Any) -> list[str]:
    """The warnings about the periods of a project – an empty list if everything fits (PRJ-005)."""
    if event_after_material_back(project.end, project.event_end, is_service_case=project.is_service_case):
        return [event_warning_text()]
    return []
