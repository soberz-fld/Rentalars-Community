# SPDX-License-Identifier: GPL-3.0-or-later
"""Has the stock changed under an open planning page? (stock refresh; UIX-020, PRJ-012; UIX-056).

The problem: when a product is linked to a model while the project planning is open in a second tab, the stock in that tab was not updated.

The planning page used to follow only what changed *in the project* (key ``project:<pk>``). The availability column
depends on much more: which models belong to a product, which items exist and are blocked, how kits are built, and the
lines and status of all other projects. None of this writes the change log with this project as its parent, so a tab
that stayed open showed the old figures until it was loaded again by hand.

The key ``stock:<pk>`` closes this: its stamp is the newest change-log entry of each kind of object the availability is
calculated from. The question costs one indexed ``MAX(id)`` per kind (``AuditLogEntry.content_type`` is a foreign key
with an index, so each is answered from the end of the index whatever the size of the log) and nothing else – no
planning is built to ask it. Only when the stamp moved does the page ask :func:`rentalars.projects.views.planning_availability`
for the figures, which is the expensive part.

The stamp contains no ".", so the script does not count it after the page's own change (PER-033): saving a line in
this tab does not make the tab ask for itself. A change of the same user in another tab does – that is intended.

The stamp is global on purpose: "which products does this project use" would need a query per line on every poll, and a
change of a model or of another project's lines can move the figures of any product. So an unrelated save somewhere moves
the stamp of every open planning. What keeps this cheap is the page script: a tab asks for the figures at most once every
20 seconds however many saves it sees, runs one more refresh afterwards if a change arrived while it was asking, and gives
up a request after 15 seconds (R3-7). The buffers of the categories and the system settings are watched
as well.

Not covered: ticks on the packlists (``PackEntry`` writes no change-log entry), the extractions (no change-log entry
either); material that is taken out of the stock shows in the next stamp of the material it concerns, or with the next
load of the page.
"""

from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Max


def watched_models() -> list[type]:
    """The kinds of objects the availability is calculated from (imported late: this module is loaded by ``core``)."""
    from rentalars.core.models import SystemSettings
    from rentalars.masterdata.models import Category
    from rentalars.material.models import ItemBlock, MaterialItem, MaterialModel
    from rentalars.products.models import KitComponent, Product
    from rentalars.projects.models import MaterialLine, Project

    # (R3-7) The buffers around a use come from the categories and the system settings.
    return [
        MaterialModel,
        MaterialItem,
        ItemBlock,
        Product,
        KitComponent,
        MaterialLine,
        Project,
        Category,
        SystemSettings,
    ]


def stock_stamp(pk: int, user: Any) -> str:
    """The state of the stock figures for the planning of project ``pk``: any text that changes with them.

    Empty for whoever may not see the availability or not read the planning – the page then does not ask for figures
    (AUT-032).
    """
    from rentalars.accounts.rights import SpecialRight, rights_of
    from rentalars.core.models import AuditLogEntry
    from rentalars.projects.access import ProjectAccess, access_level
    from rentalars.projects.models import Project

    rights = rights_of(user)
    if not rights.has(SpecialRight.AVAILABILITY):
        return ""
    project = Project.objects.filter(pk=pk).first()
    if project is None or access_level(rights, user, project) < ProjectAccess.READ:
        return ""
    newest = []
    for model in watched_models():
        content_type = ContentType.objects.get_for_model(model)  # cached by Django after the first use
        # (stock watch; R4-1) "Highest ID of a kind" is answered from the index (content_type, id) of the
        # change log (core 0025) without reading rows: 0.2 ms at 1.7 million entries on MariaDB.
        newest.append(AuditLogEntry.objects.filter(content_type=content_type).aggregate(m=Max("pk"))["m"] or 0)
    return "-".join(str(number) for number in newest)
