# SPDX-License-Identifier: GPL-3.0-or-later
"""The hint on every project page that products changed since the lines took them over (PRJ-072)."""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.accounts.rights import request_rights
from rentalars.projects.product_changes import count_changes

register = template.Library()


@register.inclusion_tag("projects/_product_change_hint.html", takes_context=True)
def product_change_hint(context: template.Context, project: Any) -> dict[str, Any]:
    """The hint "3 lines differ from their products" with a link to the planning.

    Only for a project that is not fully confirmed (inquiry, option, "confirmed – details open"), for whoever reads its planning, and not on the planning itself –
    that lists the changes line by line. Prices count only for who has the price right.
    """
    request = context.get("request")
    count = 0
    if (
        request is not None
        and project.shows_planning
        and not project.is_service_case
        and context.get("tab") != "planning"
    ):
        count = count_changes(project, request_rights(request))
    return {"project": project, "count": count}
