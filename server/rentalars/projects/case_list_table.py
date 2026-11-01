# SPDX-License-Identifier: GPL-3.0-or-later
"""Projekte → Servicefälle as a table: columns to choose, sorting, groups and CSV (PRJ-090, UIX-040).

The list of service cases is built with
:mod:`rentalars.core.tables` like the list of projects. The customer columns
follow the same rule as there (AUT-023). (The own cases under "My area",
PRJ-108, are ``projects.case_tables``.)
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.i18n import local_pattern
from rentalars.core.tables import Column, TableDefinition, badge, date_text, link
from rentalars.projects.templatetags.service_cases import CASE_COLOURS


def _url(case: Any) -> str:
    return reverse("projects:case_detail", args=[case])


def _subject(case: Any) -> Any:
    """The subject, with the day (and time) of the follow-up below it (PRJ-105, PRJ-109)."""
    name = link(_url(case), case.name)
    if case.follow_up_on:
        note = gettext("Follow-up on %(day)s") % {"day": date_text(case.follow_up_on)}
        follow_up_at = getattr(case, "follow_up_at", None)
        if follow_up_at:
            note += " " + gettext("at %(time)s") % {"time": follow_up_at.strftime("%H:%M")}
        return format_html('{}<div class="muted small">{}</div>', name, note)
    return name


def _follow_up(case: Any) -> str:
    """``20.10.2026 14:30``: the day of the follow-up and, if set, its time."""
    if not case.follow_up_on:
        return ""
    follow_up_at = getattr(case, "follow_up_at", None)
    return date_text(case.follow_up_on) + (f" {follow_up_at:%H:%M}" if follow_up_at else "")


def without_contacts(cases: Any) -> Any:
    """PRJ-122: the cases as a reader sees them who may not see customers – only the customer's name.

    The contact and who reported the case are left out of the rows (a copy in memory, never saved); the list
    and its CSV file then show the name and nothing else of the customer's side.
    """
    for case in cases:
        case.contact_id = None
        case.case_contact = ""
        yield case


def _reporter(case: Any) -> Any:
    """The customer and contact, or – without a customer – who reported the case."""
    if case.customer_id:
        if case.contact_id:
            return format_html('{}<div class="muted small">{}</div>', case.customer.name, case.contact.name)
        return case.customer.name
    return case.case_contact or ""


def _reporter_text(case: Any) -> str:
    if case.customer_id:
        return f"{case.customer.name} – {case.contact.name}" if case.contact_id else case.customer.name
    return case.case_contact or ""


def _mails(case: Any) -> Any:
    count = getattr(case, "mail_count", 0)
    if not count:
        return ""
    latest = (
        timezone.localtime(case.last_mail_at).strftime(local_pattern("%d.%m.%Y %H:%M")) if case.last_mail_at else ""
    )
    return format_html('{}<div class="muted small">{}</div>', count, gettext("latest %(when)s") % {"when": latest})


CASE_TABLE = TableDefinition(
    "service_cases",
    [
        Column(
            "number",
            _("Number"),
            cell=lambda case: link(_url(case), case.number),
            text=lambda case: case.number,
            sort="number",
            css="nowrap",
            fixed=True,
            group="number",
        ),
        # UIX-044: every column groups – by its field; the mails by what they show.
        Column(
            "subject",
            _("Subject"),
            cell=_subject,
            text=lambda case: case.name,
            sort="name",
            group="name",
            group_label=lambda case: case.name,
        ),
        Column(
            "customer",
            _("Customer or who reported it"),
            cell=_reporter,
            text=_reporter_text,
            sort=("customer__name", "case_contact", "-created_at"),
            group="customer",  # PRJ-122: the name shows in every role; contact and reporter: ``without_contacts``
            group_label=lambda case: case.customer.name if case.customer_id else "",
        ),
        Column(
            "manager",
            _("Responsible"),
            cell=lambda case: str(case.manager) if case.manager_id else "",
            sort=("manager__last_name", "manager__username", "-created_at"),
            group="manager",
        ),
        Column(
            "status",
            _("Status"),
            # PRJ-112: "Waiting for a reply" names what a waiting case waits for.
            cell=lambda case: badge(case.case_status_label, CASE_COLOURS.get(case.case_status, "")),
            text=lambda case: case.case_status_label,
            sort=("case_status", "-created_at"),
            group="case_status",
        ),
        Column(
            "created",
            _("Created"),
            cell=lambda case: date_text(case.created_at),
            text=lambda case: case.created_at,
            sort="created_at",
            css="nowrap",
            group="created_at__date",
            group_value=lambda case: timezone.localdate(case.created_at),
            group_label=lambda case: date_text(timezone.localdate(case.created_at)),
        ),
        Column(
            "mails",
            _("Mails"),
            cell=_mails,
            text=lambda case: getattr(case, "mail_count", 0),
            sort=("mail_count", "-created_at"),
        ),
        Column(
            "follow_up",
            _("Follow-up"),
            cell=_follow_up,
            sort=("follow_up_on", "follow_up_at", "-created_at"),
            css="nowrap",
            default=False,
            group="follow_up_on",
            group_label=lambda case: date_text(case.follow_up_on),
        ),
        Column(
            "notes",
            _("Description"),
            cell=lambda case: case.notes,
            sort=("notes", "-created_at"),
            default=False,
            group="notes",
        ),
    ],
    default_sort="-created",
)
