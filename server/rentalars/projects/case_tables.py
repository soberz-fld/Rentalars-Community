# SPDX-License-Identifier: GPL-3.0-or-later
"""The table of the own service cases under "My area" (PRJ-108), built with ``core.tables`` (UIX-015, UIX-040)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Module, Rights
from rentalars.core.i18n import local_pattern
from rentalars.core.tables import Column, TableDefinition, grouped_by_day
from rentalars.projects.models import CaseStatus
from rentalars.projects.tables import may_see_customers
from rentalars.projects.templatetags.service_cases import case_colour


def _participation(case: Any) -> Any:
    found = getattr(case, "my_participation", None) or []
    return found[0] if found else None


def _role(case: Any) -> str:
    """How the user is in the case: taking part (as a job function), responsible, or both."""
    participation = _participation(case)
    parts = []
    if participation is not None:
        parts.append(
            str(_("taking part as %(function)s") % {"function": participation.job_function.name})
            if participation.job_function_id
            else str(_("taking part"))
        )
    if getattr(case, "viewer_is_manager", False):  # annotated by ``case_views.my_cases``
        parts.append(str(_("responsible")))
    return ", ".join(parts)


def _link(case: Any, text: str) -> Any:
    return format_html('<a href="{}">{}</a>', reverse("projects:case_detail", args=[case]), text)


def _customers(rights: Rights) -> bool:
    return may_see_customers(rights)


def _records_times(rights: Rights) -> bool:
    return rights.can_write(Module.TIME_TRACKING)


def _record_time(case: Any) -> Any:
    """ZEI-024: a time on an open case, right from the list – also unplanned."""
    if case.case_status == CaseStatus.DONE:
        return ""
    url = f"{reverse('timetracking:quick')}?project={case.pk}"
    return format_html(
        '<a class="btn secondary small" href="{}" hx-get="{}" hx-target="#dialog" aria-label="{}">{}</a>',
        url,
        url,
        _("Record time on %(case)s") % {"case": case.number},
        _("Record time"),
    )


MY_CASES_TABLE = TableDefinition(
    "my_service_cases",
    [
        Column(
            "number",
            _("Number"),
            cell=lambda case: _link(case, case.number),
            text=lambda case: case.number,
            sort="number",
            fixed=True,
            group="number",
        ),
        # UIX-044: every column but the button groups – by its field; part, note and customer (or who
        # reported it) by what they show, as one's own cases are few.
        Column(
            "name",
            _("Subject"),
            cell=lambda case: _link(case, case.name),
            text=lambda case: case.name,
            sort="name",
            group="name",
        ),
        # UIX-015: the part and the note are the user's own – sorted in Python (one's own cases are few).
        Column("role", _("My part"), cell=_role, sort=_role),
        Column(
            "note",
            _("Note"),
            cell=lambda case: _participation(case).note if _participation(case) is not None else "",
            sort=lambda case: _participation(case).note if _participation(case) is not None else "",
        ),
        Column(
            "customer",
            _("Customer or who reported it"),
            cell=lambda case: (
                case.customer.name
                if case.customer_id
                else (_("internal") if case.is_internal else (case.case_contact or "–"))
            ),
            sort=("customer__name", "case_contact", "-created_at"),
            visible_if=_customers,
        ),
        Column(
            "manager",
            _("Responsible"),
            cell=lambda case: str(case.manager) if case.manager_id else "–",
            sort=("manager__last_name", "manager__first_name", "-created_at"),
            group="manager",
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda case: format_html(
                '<span class="badge {}">{}</span>', case_colour(case.case_status), case.case_status_label
            ),
            text=lambda case: case.case_status_label,  # PRJ-112
            sort=("case_status", "-created_at"),
            group="case_status",
            group_label=lambda case: case.get_case_status_display(),
        ),
        Column(
            "created",
            _("Created"),
            cell=lambda case: f"{timezone.localtime(case.created_at):{local_pattern('%d.%m.%Y %H:%M')}}",
            sort="created_at",
            **grouped_by_day("created_at"),
        ),
        Column(
            "record",
            _("Times"),
            cell=_record_time,
            visible_if=_records_times,
            export=False,
            fixed=True,
            unsortable="a button",
        ),
    ],
    default_sort="-created",
)
