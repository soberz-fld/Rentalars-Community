# SPDX-License-Identifier: GPL-3.0-or-later
"""Template helpers of the service cases (PRJ-090)."""

from __future__ import annotations

from django import template

register = template.Library()

#: The colour of the badge of each status: open is outlined, in progress yellow, done green; PRJ-112:
#: waiting in the accent colour, waiting to close dark, the backlog plain grey.
CASE_COLOURS = {
    "open": "outline",
    "in_progress": "yellow",
    "waiting": "accent",
    "closing": "solid",
    "backlog": "",
    "done": "green",
}


@register.filter
def case_colour(status: str) -> str:
    """The badge colour class of the status of a service case."""
    return CASE_COLOURS.get(status, "")
