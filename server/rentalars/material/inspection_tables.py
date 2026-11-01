# SPDX-License-Identifier: GPL-3.0-or-later
"""Materialverwaltung → Prüfungen as a table: columns to choose, sorting, groups and CSV (MAT-032, UIX-040).

The rows are pairs ``(item, due)`` computed by ``material.inspections`` – not a
queryset – so the table sorts and groups them in Python.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.tables import Column, TableDefinition, badge, date_text, link
from rentalars.core.templatetags.rentalars import status_colour


class DueRow(tuple):  # type: ignore[type-arg]
    """A row ``(item, due)`` of the overview that knows the key of its item – the tick box of a row carries it (MAT-082)."""

    __slots__ = ()

    @property
    def pk(self) -> int:
        """The key of the item."""
        return int(self[0].pk)


def _last(row: Any) -> SafeString:
    due = row[1]
    if not due.last_date:
        return format_html('<span class="muted">{}</span>', gettext("never"))
    if not due.last_passed:
        return format_html("{} {}", date_text(due.last_date), badge(gettext("failed"), "red"))
    return format_html("{}", date_text(due.last_date))


def _due(row: Any) -> SafeString:
    due = row[1]
    colour = "red" if due.state == "overdue" else "yellow"
    return badge(date_text(due.due_date) if due.due_date else gettext("now"), colour)


def _location(row: Any) -> str:
    location = row[0].effective_storage_location
    if location is None:
        return ""
    spot = row[0].effective_storage_spot
    return f"{location.path} {spot}" if spot else location.path


INSPECTION_TABLE = TableDefinition(
    "inspections_due",
    [
        Column(
            "id",
            _("ID"),
            cell=lambda row: link(reverse("material:item_inspections", args=[row[0].pk]), row[0].display_id, "tape"),
            text=lambda row: row[0].display_id,
            sort=lambda row: row[0].inventory_number,
            fixed=True,
        ),
        Column(
            "model",
            _("Article name"),
            cell=lambda row: row[0].material_model.name,
            sort=lambda row: row[0].material_model.name,
            group=lambda row: row[0].material_model_id,
        ),
        Column(
            "inspection",
            _("Inspection"),
            cell=lambda row: row[1].inspection_type.name,
            sort=lambda row: row[1].inspection_type.name,
            group=lambda row: row[1].inspection_type.pk,
        ),
        Column(
            "last",
            _("Last"),
            cell=_last,
            text=lambda row: row[1].last_date,
            sort=lambda row: row[1].last_date or datetime.date.min,
        ),
        Column(
            "due",
            _("Due"),
            cell=_due,
            text=lambda row: row[1].due_date,
            sort=lambda row: row[1].due_date or datetime.date.min,
            group=lambda row: row[1].state,
            group_label=lambda row: badge(row[1].state_label, "red" if row[1].state == "overdue" else "yellow"),
        ),
        Column(
            "location",
            _("Storage location"),
            cell=_location,
            sort=_location,
            group=_location,
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda row: badge(row[0].get_status_display(), status_colour(row[0].status)),
            text=lambda row: row[0].get_status_display(),
            sort=lambda row: str(row[0].get_status_display()),
            group=lambda row: row[0].status,
        ),
    ],
    default_sort="due",
)
