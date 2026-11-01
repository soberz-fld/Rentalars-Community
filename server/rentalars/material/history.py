# SPDX-License-Identifier: GPL-3.0-or-later
"""The history of a material item (MAT-025).

Three kinds of entries are merged into one timeline: status changes and field
changes (from the audit log) and deployments in projects (from the packing
module, where an item was allocated – PCK-021).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights
from rentalars.core.history import FieldChange, describe
from rentalars.core.models import AuditLogEntry
from rentalars.material.models import ItemAudit, ItemTodo, MaterialItem, Vehicle


@dataclass
class ItemHistoryRow:
    """One line of an item's history."""

    timestamp: datetime.datetime
    #: "change", "event" or "deployment"
    kind: str
    summary: str
    user: str = ""
    changes: list[FieldChange] = field(default_factory=list)
    project_id: int | None = None
    project_number: str = ""


def item_history(item: MaterialItem, rights: Rights, *, limit: int = 200) -> list[ItemHistoryRow]:
    """Return the newest history rows of an item, newest first.

    Args:
        item: The item.
        rights: The rights of the reader; purchase prices only show with the
            matching right (AUT-019).
        limit: The maximum number of audit log entries to include.
    """
    # The packing module builds on material, so it is imported here and not at
    # the top of the file: material itself works without packing.
    from rentalars.packing.models import Allocation

    rows: list[ItemHistoryRow] = []
    logged = AuditLogEntry.for_object(item, include_children=False)
    vehicle = Vehicle.objects.filter(item=item).first()
    if vehicle is not None:
        # LOG-002: the vehicle data – licence plate, seats … – belong to the history of the item.
        logged = logged | AuditLogEntry.for_object(vehicle, include_children=False)
    # MAT-069: the audits of the item and its to-dos, each in one readable line.
    from rentalars.material.audits import history_summary

    logged = logged | AuditLogEntry.objects.filter(
        parent_content_type=ContentType.objects.get_for_model(MaterialItem),
        parent_object_id=str(item.pk),
        content_type__in=[ContentType.objects.get_for_model(ItemAudit), ContentType.objects.get_for_model(ItemTodo)],
    )
    entries = list(logged[:limit])
    for described in describe(entries, rights):
        summary = history_summary(described.entry)
        rows.append(
            ItemHistoryRow(
                timestamp=described.entry.timestamp,
                kind="event" if described.entry.event or summary else "change",
                summary=summary or described.summary,
                user=described.actor,
                changes=[] if summary else described.changes,
            )
        )
    allocations = Allocation.objects.filter(item=item, issued_at__isnull=False).select_related(
        "entry__packlist__project"
    )
    for allocation in allocations:
        project = allocation.entry.packlist.project
        rows.append(
            ItemHistoryRow(
                timestamp=allocation.issued_at,
                kind="deployment",
                summary=_("Issued for project %(project)s") % {"project": project},
                project_id=project.pk,
                project_number=project.number,
            )
        )
        if allocation.returned_at:
            rows.append(
                ItemHistoryRow(
                    timestamp=allocation.returned_at,
                    kind="deployment",
                    summary=_("Returned from project %(project)s") % {"project": project},
                    project_id=project.pk,
                    project_number=project.number,
                )
            )
    # MAT-073: the values of the item's custom fields, "Eigenes Feld „Firmware“: 1.2 → 1.3".
    from rentalars.customfields.history import value_rows

    rows.extend(value_rows(item, rights, limit=limit))
    rows.sort(key=lambda row: row.timestamp, reverse=True)
    return rows
