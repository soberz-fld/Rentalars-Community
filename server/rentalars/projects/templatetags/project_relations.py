# SPDX-License-Identifier: GPL-3.0-or-later
"""The box "Verwandt" on the overview of a project and on the page of a service case (PRJ-119).

::

    {% load project_relations %}
    {% related_box project %}

Shown to whoever reads the project (or works on the case, AUT-033) – not with
the deployment view only, and not on a subproject, which is related through
its whole project. Each related project with number, name, kind, status and
link; one the reader may not open as "Projekt 2027-0042 (kein Zugriff)" only
(AUT-016). Whoever may edit the project links ("Verknüpfen") and unlinks
("Lösen") – see ``projects.relation_views``.
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.accounts.rights import request_rights
from rentalars.projects.access import ProjectAccess
from rentalars.projects.models import Project
from rentalars.projects.relations import may_link_from, related_entries

register = template.Library()


@register.inclusion_tag("projects/_relations.html", takes_context=True)
def related_box(context: Any, project: Project) -> dict[str, Any]:
    """The related projects of ``project`` as the reader may see them, and the form to link another one."""
    request = context["request"]
    access = getattr(project, "access", ProjectAccess.NONE)
    reads = access >= ProjectAccess.READ or getattr(project, "works_on_case", False)
    entries = related_entries(project, request_rights(request), request.user) if reads else []
    # A subproject is related through its whole project – unless it became a part with relations of its own: those
    # are shown, to be unlinked.
    show = reads and (project.parent_id is None or bool(entries))
    return {
        "show": show,
        "project": project,
        "entries": entries,
        "can_link": show and may_link_from(project),
        "can_unlink": show and access >= ProjectAccess.EDIT,
        "next": f"{request.get_full_path()}#related",
        "csrf_token": context.get("csrf_token"),
        "request": request,
    }
