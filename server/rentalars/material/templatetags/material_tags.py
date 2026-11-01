# SPDX-License-Identifier: GPL-3.0-or-later
"""Template tags of the material management (MAT-070).

``{% open_points_total as total %}``
    the number of open points – items without product, open to-dos, due
    audits – for the tab "Offene Punkte" in the row of tabs of every page of
    the material management (MAT-070).
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.material import audits

register = template.Library()

#: Where a request keeps the counts once asked, so that the row of tabs asks the database once per page.
_COUNTS_ATTRIBUTE = "_material_open_point_counts"


@register.simple_tag(takes_context=True)
def open_points_total(context: template.Context) -> int:
    """The sum of the numbers of the sub-tabs of "Offene Punkte" (MAT-070).

    The same counts as the sub-tabs (:func:`audits.open_point_counts`): on the
    pages of "Offene Punkte" the ones the view counted already, elsewhere
    three counting queries and the audit settings – not one per item. The
    row of tabs shows the tab only to who may read the material, and who
    may read it sees every item of these lists, so the sum is what the
    reader can open.
    """
    counts: dict[str, int] | None = context.get("open_counts")
    if counts is None:
        request: Any = context.get("request")
        counts = getattr(request, _COUNTS_ATTRIBUTE, None)
        if counts is None:
            counts = audits.open_point_counts()
            if request is not None:
                setattr(request, _COUNTS_ATTRIBUTE, counts)
    return sum(counts.values())
