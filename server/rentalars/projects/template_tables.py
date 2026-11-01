# SPDX-License-Identifier: GPL-3.0-or-later
"""Projekte → Vorlagen as a table: columns to choose, sorting, groups and CSV (PRJ-076, UIX-040).

"Löschen" of a template sends a small form below the table (``delete-template-<id>``).
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Module, Rights
from rentalars.core.tables import Column, TableDefinition, date_text, grouped_by_day, hidden_label, link, text_lines


def _name(template: Any) -> SafeString:
    name = link(reverse("projects:template_content", args=[template.pk]), template.name)
    if template.description:
        # UIX-005: plain text with its line breaks, no "<p>…</p>" to read.
        return format_html('{}<div class="muted small">{}</div>', name, text_lines(template.description))
    return name


def _content(template: Any) -> str:
    counts = template.counts
    return gettext("%(groups)s groups, %(lines)s lines, %(crew)s crew places, %(phases)s phases") % counts


def _created(template: Any) -> str:
    when = date_text(timezone.localdate(template.created_at)) if template.created_at else ""
    return f"{when} · {template.created_by}" if template.created_by_id else when


def _may_delete(rights: Rights) -> bool:
    return rights.can_delete(Module.PROJECTS)


def _delete(template: Any) -> SafeString:
    return format_html(
        '<button class="link-btn danger" type="submit" form="delete-template-{}" data-confirm="{}">{}</button>',
        template.pk,
        gettext("Delete this template? Projects made from it stay as they are."),
        gettext("delete"),
    )


PROJECT_TEMPLATE_TABLE = TableDefinition(
    "project_templates",
    [
        # UIX-044: every column but the buttons groups; the content by what it shows (a few templates).
        Column(
            "name", _("Name"), cell=_name, text=lambda template: template.name, sort="name", fixed=True, group="name"
        ),
        # UIX-015: by the size of the template – groups, then lines, crew places, phases (a few templates).
        Column(
            "content",
            _("Content"),
            cell=_content,
            sort=lambda template: tuple(template.counts[key] for key in ("groups", "lines", "crew", "phases")),
        ),
        Column(
            "source",
            _("Made from"),
            cell=lambda template: template.source_number or "",
            sort=("source_number", "name"),
            group="source_number",
        ),
        Column(
            "created",
            _("Created"),
            cell=_created,
            text=lambda template: template.created_at,
            sort="created_at",
            **grouped_by_day("created_at"),
        ),
        Column(
            "created_by",
            _("Created by"),
            cell=lambda template: str(template.created_by) if template.created_by_id else "",
            sort=("created_by__username", "name"),
            default=False,
            group="created_by",
        ),
        Column(
            "actions",
            hidden_label(_("Actions")),  # UIX-029: lazy, in the reader's language
            cell=_delete,
            css="actions no-print",
            visible_if=_may_delete,
            fixed=True,
            export=False,
            unsortable="buttons",
        ),
    ],
    default_sort="name",
)
