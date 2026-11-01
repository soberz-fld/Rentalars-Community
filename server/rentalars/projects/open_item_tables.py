# SPDX-License-Identifier: GPL-3.0-or-later
"""Projekte → Offene Punkte as a table: columns to choose, sorting, groups and CSV (PRJ-059, PRJ-098, UIX-040).

A row is a project with its open items and its shortages not resolved yet,
computed by ``course_views.open_items_overview`` – a list, so the table sorts
and groups it in Python.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import dateformat
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.i18n import local_pattern
from rentalars.core.tables import Column, TableDefinition, badge
from rentalars.core.templatetags.rentalars import status_colour
from rentalars.projects import family_labels
from rentalars.projects.tables import may_see_customers


def _project(row: Any) -> SafeString:
    project = row["project"]
    name = format_html(
        '<a href="{}">{} {}</a>', reverse("projects:course", args=[project]), project.number, project.name
    )
    notes = []
    if project.parent_id:
        notes.append(family_labels.part_of(project))
    who = " · ".join(str(part) for part in (project.customer_name, project.manager or "") if part)
    if who:
        notes.append(who)
    return format_html(
        "{}{}", name, format_html_join("", '<div class="muted small">{}</div>', ((note,) for note in notes))
    )


def _period(row: Any) -> str:
    project = row["project"]
    if project.is_service_case:  # PRJ-090: a service case has no period
        return "–"
    return f"{dateformat.format(project.start, local_pattern('D d.m.Y'))} – {dateformat.format(project.end, local_pattern('D d.m.Y'))}"


def _status_text(row: Any) -> str:
    project = row["project"]
    if project.is_service_case:
        return f"{gettext('service case')} {project.case_status_label}"  # PRJ-112
    return str(project.get_status_display())


def _status(row: Any) -> SafeString:
    project = row["project"]
    if project.is_service_case:
        return format_html("{} {}", badge(gettext("service case"), "accent"), project.case_status_label)
    return badge(project.get_status_display(), status_colour(project.status))


def _shortage_text(shortage: Any) -> str:
    if shortage.subrented:
        return gettext("Shortage: %(count)s × %(product)s (%(subrented)s subrented, %(open)s open)") % {
            "count": shortage.missing_before_cover,
            "product": shortage.product.name,
            "subrented": shortage.subrented,
            "open": shortage.quantity,
        }
    return gettext("Shortage: %(count)s × %(product)s") % {"count": shortage.quantity, "product": shortage.product.name}


def _open(row: Any) -> SafeString:
    project = row["project"]
    parts = [format_html("<div>• {}</div>", item.text) for item in row["items"]]
    # PRJ-098: shortages not resolved yet, as further points; each leads to its line in the planning.
    parts += [
        format_html(
            '<div class="open-shortage">• <a href="{}#line-{}">{}</a></div>',
            # The line sits in the Planung tab, not in the Überblick that other project links open.
            reverse("projects:detail", args=[project]),
            shortage.line.pk,
            _shortage_text(shortage),
        )
        for shortage in row["shortages"]
    ]
    if not parts:
        if row["suggest_confirmation"]:
            return badge(gettext("all done – can be confirmed"), "green")
        return format_html('<span class="muted">{}</span>', gettext("nothing noted yet"))
    return format_html_join("", "{}", ((part,) for part in parts))


def _open_text(row: Any) -> str:
    return "; ".join([item.text for item in row["items"]] + [_shortage_text(s) for s in row["shortages"]])


OPEN_ITEMS_TABLE = TableDefinition(
    "open_items",
    [
        Column(
            "project",
            _("Project"),
            cell=_project,
            text=lambda row: f"{row['project'].number} {row['project'].name}",
            sort=lambda row: row["project"].number,
            fixed=True,
        ),
        Column(
            "customer",
            _("Customer"),
            cell=lambda row: row["project"].customer_name,
            sort=lambda row: row["project"].customer_name,
            default=False,
            visible_if=may_see_customers,
            group=lambda row: row["project"].customer_id,
        ),
        Column(
            "manager",
            _("Project manager"),
            cell=lambda row: str(row["project"].manager or ""),
            sort=lambda row: str(row["project"].manager or ""),
            default=False,
            group=lambda row: row["project"].manager_id,
        ),
        Column(
            "period",
            _("Period"),
            cell=_period,
            sort=lambda row: (row["project"].start, row["project"].number),
            css="nowrap",
        ),
        Column(
            "status",
            _("Status"),
            cell=_status,
            text=_status_text,
            sort=_status_text,
            group=_status_text,
        ),
        Column(
            "open",
            _("Still open"),
            cell=_open,
            text=_open_text,
            sort=lambda row: len(row["items"]) + len(row["shortages"]),
        ),
    ],
    default_sort="period",
)
