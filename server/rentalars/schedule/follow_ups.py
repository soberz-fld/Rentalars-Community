# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning → Follow-ups: every follow-up as a table (VFG-034).

The last tab of "Planning" lists every project and service case with a
follow-up ("Wiedervorlage", PRJ-105) the user may see: day, time (PRJ-109),
for whom, note, project, kind and status. It is a ``core.tables`` table –
columns to choose, sorting by a click on a heading, CSV of the view and with
every column, grouping. Filters: for me or everybody, only due ones, a period
of days. A follow-up is done or moved from here as from the project: the same
dialog and the same rules (``projects.follow_up``), for who may edit that
project.

Who sees whose follow-ups: whoever may know whose projects they are (AUT-023:
all projects, or the customers) sees every follow-up of the projects they may
see; everybody else only the follow-ups that are for them.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import dateformat
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext, pgettext_lazy

from rentalars.accounts.rights import Module, Rights, module_required, request_rights
from rentalars.core.i18n import local_pattern
from rentalars.core.listing import paginate, query_date
from rentalars.core.tables import Column, TableDefinition, badge, link
from rentalars.core.templatetags.rentalars import icon, status_colour
from rentalars.projects.access import ProjectAccess, access_of_many, visible_projects
from rentalars.projects.follow_up import due_condition
from rentalars.projects.models import Project, ProjectKind
from rentalars.projects.tables import may_see_customers
from rentalars.projects.templatetags.service_cases import case_colour

#: ``?who=``: everybody's follow-ups or only the user's own.
WHO_CHOICES = (
    ("", pgettext_lazy("follow-ups of", "everybody")),
    ("mine", _("for me")),
)


def _detail_url(project: Any) -> str:
    if project.kind == ProjectKind.SERVICE_CASE:
        return reverse("projects:case_detail", args=[project.pk])
    return reverse("projects:overview", args=[project.pk])


def _day(project: Any) -> Any:
    """``Mo 20.10.2026`` with a mark when the follow-up is due."""
    day = dateformat.format(project.follow_up_on, local_pattern("D d.m.Y"))
    if project.follow_up_is_due:
        return format_html("{} {}", day, badge(pgettext("follow-up", "due"), "yellow"))
    return day


def _time(project: Any) -> str:
    """PRJ-109: ``14:30``; empty without a time."""
    return project.follow_up_at.strftime("%H:%M") if project.follow_up_at else ""


def _user(project: Any) -> str:
    return str(project.follow_up_user) if project.follow_up_user_id else ""


def _project(project: Any) -> Any:
    return link(_detail_url(project), f"{project.number} {project.name}")


def _status(project: Any) -> Any:
    if project.kind == ProjectKind.SERVICE_CASE:
        return badge(project.case_status_label, case_colour(project.case_status))  # PRJ-112
    return badge(project.get_status_display(), status_colour(project.status))


def _status_text(project: Any) -> str:
    if project.kind == ProjectKind.SERVICE_CASE:
        return project.case_status_label
    return str(project.get_status_display())


def _actions(project: Any) -> Any:
    """The buttons "Move" (the dialog of the project) and "Done", for who may edit the project.

    "Done" is a button of the one form ``follow-up-done`` below the table; it
    only names the address of the project, so the page carries one CSRF token.
    """
    if not getattr(project, "may_edit", False):
        return ""
    edit_url = reverse("projects:follow_up", args=[project.pk])
    next_query = getattr(project, "next_query", "")
    return format_html(
        '<span class="btn-row nowrap">'
        '<a class="btn secondary small" href="{}?{}" hx-get="{}?{}" hx-target="#dialog" aria-label="{}">{}{}</a>'
        '<button class="btn secondary small" type="submit" form="follow-up-done" formaction="{}" aria-label="{}">'
        "{}{}</button></span>",
        edit_url,
        next_query,
        edit_url,
        next_query,
        pgettext("follow-up", "Move follow-up of %(number)s") % {"number": project.number},
        icon("edit"),
        pgettext("follow-up", "Move"),
        reverse("projects:follow_up_done", args=[project.pk]),
        pgettext("follow-up", "Follow-up of %(number)s done") % {"number": project.number},
        icon("check"),
        pgettext("follow-up", "Done"),
    )


FOLLOW_UP_TABLE = TableDefinition(
    "follow_ups",
    [
        Column(
            "day",
            _("Day"),
            cell=_day,
            text=lambda project: project.follow_up_on,
            sort=("follow_up_on", "follow_up_at", "number"),
            css="nowrap",
            fixed=True,
            group="follow_up_on",
            group_label=lambda project: dateformat.format(project.follow_up_on, local_pattern("l, d.m.Y")),
        ),
        # UIX-044: every column but the buttons groups – by its field; the status by what it shows.
        Column(
            "time",
            pgettext_lazy("follow-up", "Time"),
            cell=_time,
            sort=("follow_up_at", "follow_up_on"),
            css="nowrap",
            group="follow_up_at",
        ),
        Column(
            "user",
            pgettext_lazy("follow-up", "For"),
            cell=_user,
            sort=("follow_up_user__first_name", "follow_up_user__last_name", "follow_up_on"),
            group="follow_up_user_id",
            group_label=_user,
        ),
        Column(
            "note",
            _("Note"),
            cell=lambda project: project.follow_up_note,
            sort=("follow_up_note", "follow_up_on"),
            group="follow_up_note",
        ),
        Column(
            "project",
            _("Project"),
            cell=_project,
            text=lambda project: f"{project.number} {project.name}",
            sort="number",
            fixed=True,
            group="number",
        ),
        Column(
            "kind",
            _("Kind"),
            cell=lambda project: project.get_kind_display(),
            sort=("kind", "follow_up_on"),
            group="kind",
        ),
        Column("status", _("Status"), cell=_status, text=_status_text, sort=("kind", "status", "case_status")),
        Column(
            "customer",
            _("Customer"),
            cell=lambda project: project.customer.name if project.customer_id else "",
            sort=("customer__name", "follow_up_on"),
            default=False,
            visible_if=may_see_customers,
            group="customer",
        ),
        Column(
            "manager",
            _("Responsible"),
            cell=lambda project: str(project.manager) if project.manager_id else "",
            sort=("manager__first_name", "manager__last_name", "follow_up_on"),
            default=False,
            group="manager",
        ),
        Column("actions", _("Actions"), cell=_actions, css="actions", fixed=True, export=False, unsortable="buttons"),
    ],
    default_sort="day",
)


def visible_follow_ups(rights: Rights, user: Any) -> QuerySet[Project]:
    """The projects and service cases with a follow-up the user may see (VFG-034).

    Whoever may know whose projects they are (AUT-023) sees every follow-up of the projects they may see;
    everybody else only the follow-ups that are for them. The tab "Follow-ups" and – VFG-039 –
    the calendar of "Planning" show the same ones.
    """
    projects = visible_projects(rights, user).filter(follow_up_on__isnull=False)
    if not may_see_customers(rights):
        projects = projects.filter(follow_up_user=user)
    return projects


@module_required(Module.PROJECTS)
def follow_ups(request: HttpRequest) -> HttpResponse:
    """Every follow-up the user may see as a table (VFG-034), with filters for whom, due and period."""
    rights = request_rights(request)
    projects = visible_follow_ups(rights, request.user)
    show_everybody = may_see_customers(rights)
    who = request.GET.get("who", "")
    if who not in ("", "mine"):
        who = ""
    if who == "mine":
        projects = projects.filter(follow_up_user=request.user)
    due_only = bool(request.GET.get("due"))
    if due_only:
        projects = projects.filter(due_condition())
    # PRJ-112: service cases in the backlog only once their follow-up is due – or on request.
    with_backlog = bool(request.GET.get("backlog"))
    if not with_backlog:
        from rentalars.projects.service_cases import off_dashboards

        projects = projects.exclude(off_dashboards())
    since = query_date(request.GET.get("since"))
    until = query_date(request.GET.get("until"))
    if since:
        projects = projects.filter(follow_up_on__gte=since)
    if until:
        projects = projects.filter(follow_up_on__lte=until)
    table = FOLLOW_UP_TABLE.state(request)
    projects = table.order(projects.select_related("follow_up_user", "customer", "manager"))
    if table.wants_csv:
        return table.csv_response(projects, str(_("Follow-ups")))
    page = paginate(request, projects)
    records = list(page)  # the page keeps these objects: what is set on them shows in the rows
    if records and rights.can_write(Module.PROJECTS):
        levels = access_of_many(rights, request.user, [project.pk for project in records])
        next_query = urlencode({"next": request.get_full_path()})
        for project in records:
            project.may_edit = levels[project.pk] >= ProjectAccess.EDIT
            project.next_query = next_query
    return render(
        request,
        "schedule/follow_ups.html",
        {
            "tab": "follow_ups",
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "show_everybody": show_everybody,
            "who_choices": WHO_CHOICES,
            "filters": {
                "who": who,
                "due": due_only,
                "backlog": with_backlog,
                "since": request.GET.get("since", ""),
                "until": request.GET.get("until", ""),
            },
        },
    )
