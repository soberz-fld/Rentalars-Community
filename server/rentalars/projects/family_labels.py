# SPDX-License-Identifier: GPL-3.0-or-later
"""How a subproject is named outside its own pages (PRJ-044).

A part has a number and a name of its own – ``2026-0042-1 Bühne
Marktplatz`` – and wherever it is listed, it should be recognisable as a part
of its whole project: in the calendar, the timelines, the search, the start
page, the shortages, the time entry. These helpers say it the same way
everywhere:

* :func:`part_of` – ``part of 2026-0042 Stadtfest`` (in German "Teil von
  …"), for a second line, a title or a tooltip;
* :func:`project_label` – ``2026-0042-1 Bühne Marktplatz (Stadtfest)``, where
  only one line of text fits, as in a selection list;
* :func:`short_name` – ``Bühne Marktplatz (Stadtfest)``, for the bars of the
  calendar, which show names without numbers;
* :func:`whole_first` – a list of projects with every part right after its
  whole project.

All of them read ``project.parent``: callers load the projects with
``select_related("parent")`` (or ``"project__parent"``), so that a list does
not ask the database once per row.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.utils.translation import gettext as _


def part_of(project: Any) -> str:
    """``part of 2026-0042 Stadtfest`` for a part of a whole project, else an empty text (PRJ-044)."""
    if project is None or not getattr(project, "parent_id", None):
        return ""
    parent = project.parent
    # The same words as the project list (projects.tables).
    return _("part of %(number)s %(name)s") % {"number": parent.number, "name": parent.name}


def short_name(project: Any) -> str:
    """The name with the whole project's in brackets: ``Bühne Marktplatz (Stadtfest)`` (PRJ-044)."""
    if not getattr(project, "parent_id", None):
        return project.name
    return f"{project.name} ({project.parent.name})"


def project_label(project: Any) -> str:
    """Number and name, for a part with the whole project's name: ``2026-0042-1 Bühne Marktplatz (Stadtfest)``."""
    return f"{project.number} {short_name(project)}"


def _number_key(number: str) -> tuple[int, str]:
    return len(number), number


def whole_first[T](projects: Iterable[T], *, key: Any = None) -> list[T]:
    """The projects in their order, but every part right after its whole project (PRJ-044).

    The parts of a whole project follow it in the order of their numbers.
    A part whose whole project is not in the list keeps its own place.

    Args:
        projects: Projects, or records that carry a project.
        key: Gets the project of a record; default: the record is the project.
    """
    items = list(projects)
    project_of = key or (lambda item: item)
    present = {project_of(item).pk for item in items}
    parts: dict[int, list[T]] = {}
    for item in items:
        parent_id = project_of(item).parent_id
        if parent_id in present:
            parts.setdefault(parent_id, []).append(item)
    if not parts:
        return items
    ordered: list[T] = []
    for item in items:
        project = project_of(item)
        if project.parent_id in present:
            continue
        ordered.append(item)
        # 2026-0042-2 before 2026-0042-10: the numbers of the parts differ only in their ending.
        ordered.extend(sorted(parts.get(project.pk, []), key=lambda part: _number_key(project_of(part).number)))
    return ordered
