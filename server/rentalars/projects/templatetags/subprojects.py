# SPDX-License-Identifier: GPL-3.0-or-later
"""Template filters that name a subproject as part of its whole project (PRJ-044).

``{% load subprojects %}``, then ``{{ project|part_of }}`` gives "Teil von
2026-0042 Stadtfest" for a part and nothing for any other project;
``{{ project|project_label }}`` gives "2026-0042-1 Bühne Marktplatz
(Stadtfest)". See ``projects.family_labels``.
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.projects import family_labels

register = template.Library()


@register.filter
def part_of(project: Any) -> str:
    """``part of 2026-0042 Stadtfest`` for a part, else an empty text."""
    return family_labels.part_of(project)


@register.filter
def project_label(project: Any) -> str:
    """``2026-0042-1 Bühne Marktplatz (Stadtfest)`` for a part, ``2026-0042 Stadtfest`` for any other project."""
    return family_labels.project_label(project) if project is not None else ""
