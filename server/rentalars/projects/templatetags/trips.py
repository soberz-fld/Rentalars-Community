# SPDX-License-Identifier: GPL-3.0-or-later
"""The trips of a project on the pages "Zeitplanung" and "Überblick" (PRJ-097).

::

    {% load trips %}
    {% project_trips project %}             {# Zeitplanung: with hints for the planner #}
    {% project_trips project for_crew=True %}  {# Überblick: what drivers need #}

PRJ-111: on "Zeitplanung", whoever may change the project changes,
removes, resets and adds trips; the removed ones are listed below the
trips, to be brought back.
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.projects.access import ProjectAccess
from rentalars.projects.models import Project
from rentalars.projects.trips import name_vehicles, trips_of

register = template.Library()


@register.inclusion_tag("projects/_trips.html", takes_context=True)
def project_trips(context: Any, project: Project, for_crew: bool = False) -> dict[str, Any]:
    """The panel "Fahrten": every trip with its route link, and the map of the places (PRJ-097, UIX-034)."""
    can_change = (
        not for_crew and getattr(project, "access", ProjectAccess.NONE) >= ProjectAccess.EDIT and not project.is_locked
    )
    every = trips_of(project, with_removed=can_change)
    trips = [trip for trip in every if not trip.is_removed]
    name_vehicles(project, trips)  # LOG-007
    return {
        "project": project,
        "trips": trips,
        "removed_trips": [trip for trip in every if trip.is_removed],
        "can_change_trips": can_change,  # PRJ-111
        "for_crew": for_crew,
        "has_places": bool(trips) or bool(project.venue_site_id or project.venue.strip()),
        "request": context.get("request"),
        "can": context.get("can"),
    }
