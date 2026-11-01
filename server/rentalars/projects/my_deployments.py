# SPDX-License-Identifier: GPL-3.0-or-later
"""My area → "Meine Einsätze": the own crew lines as a table (UIX-043).

The block "Meine Einsätze" of the start page shows the next deployments
(PRJ-023). Under "My area" they are the first tab – and the tab "My area"
opens with –, as a table of ``core.tables`` (UIX-015, UIX-040): columns,
sorting by every heading, groups, CSV. Filters:

* **period** – coming (default: not yet over, also what ended in the last
  twelve hours, as on the start page), past, or all; and a first and last
  day;
* **state** – firm, option or inquiry (as in the personnel plan, VFG-027),
  and where the request stands (asked, accepted, declined, not asked;
  "planned firmly" – without request, PER-041);
* **project** – one of the projects one is planned in.

Deployments in cancelled projects are no deployments and are left out. The
page needs an account that is a person (AUT-026), no right on a module:
everybody sees their own deployments, as on the start page. The project
leads to its overview (the deployment view, AUT-025).
"""

from __future__ import annotations

import datetime
from typing import Any

from django import forms
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext, pgettext_lazy

from rentalars.core.forms import StyledForm
from rentalars.core.listing import paginate
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day
from rentalars.projects.access import person_of
from rentalars.projects.models import ORDER_STATUSES, CrewLine, Project, ProjectStatus, RequestStatus

#: The statuses of a project whose crew is planned for good: "fest" in the personnel plan (VFG-027).
FIRM_STATUSES = ORDER_STATUSES

#: How long a deployment that is over still counts as coming – the same as on the start page.
STILL_COMING = datetime.timedelta(hours=12)


def state_order() -> Case:
    """0 firm, 1 option, 2 inquiry – annotated as ``deployment_state`` to sort and group by (UIX-043)."""
    return Case(
        When(project__status=ProjectStatus.OPTION, then=Value(1)),
        When(project__status=ProjectStatus.INQUIRY, then=Value(2)),
        default=Value(0),
        output_field=IntegerField(),
    )


def firmness(line: CrewLine) -> str:
    """``firm``, ``option`` or ``inquiry`` – the colours of the deployments in the personnel plan (VFG-027)."""
    status = line.project.status
    if status == ProjectStatus.OPTION:
        return "option"
    if status == ProjectStatus.INQUIRY:
        return "inquiry"
    return "firm"


def _firmness_label(line: CrewLine) -> str:
    return {"firm": _("firm"), "option": _("option"), "inquiry": pgettext("deployment", "inquiry")}[firmness(line)]


def _firmness_badge(line: CrewLine) -> Any:
    colour = {"firm": "orange", "option": "yellow", "inquiry": ""}[firmness(line)]
    return badge(_firmness_label(line), colour)


def _request_badge(line: CrewLine) -> Any:
    if not line.request_status:
        return format_html('<span class="muted">{}</span>', line.get_request_status_display())
    # PER-041: planned firmly counts like an accepted request.
    colours = {"requested": "yellow", "accepted": "green", "declined": "red", "firm": "green"}
    colour = colours.get(line.request_status, "")
    return badge(line.get_request_status_display(), colour)


def _project(line: CrewLine) -> Any:
    project = line.project
    url = reverse("projects:deployment", args=[project.pk])
    if project.parent_id:
        return format_html(
            '<a href="{}">{} {}</a><div class="muted small">{}</div>',
            url,
            project.number,
            project.name,
            _("Part of %(number)s %(name)s") % {"number": project.parent.number, "name": project.parent.name},
        )
    return format_html('<a href="{}">{} {}</a>', url, project.number, project.name)


def _venue(line: CrewLine) -> str:
    project = line.project
    if line.phase_id and line.phase.venue_site_id:
        return line.phase.venue_site.name
    if project.venue_site_id:
        return project.venue_site.name
    return (line.phase.location if line.phase_id else "") or project.venue or "–"


def _vehicle(line: CrewLine) -> str:
    """LOG-008: "Sprinter (B-RL 100), driver" – or a dash."""
    if not line.vehicle_line_id:
        return "–"
    label = line.vehicle_line.crew_label
    return f"{label}, {_('driver')}" if line.is_driver else label


MY_DEPLOYMENTS_TABLE = TableDefinition(
    "my_deployments",
    [
        Column(
            "project",
            gettext_lazy("Project"),
            cell=_project,
            text=lambda line: f"{line.project.number} {line.project.name}",
            sort=("project__number", "start"),
            fixed=True,
            group="project_id",
            group_label=lambda line: f"{line.project.number} {line.project.name}",
        ),
        Column(
            "function",
            gettext_lazy("As"),
            cell=lambda line: line.job_function.name,
            sort=("job_function__name", "start"),
            group="job_function_id",
            group_label=lambda line: line.job_function.name,
        ),
        Column(
            "start",
            gettext_lazy("From"),
            cell=lambda line: date_text(line.start),
            text=lambda line: line.start,
            sort=("start", "pk"),
            **grouped_by_day("start"),  # UIX-044: every column groups, a moment by its day
        ),
        Column(
            "end",
            gettext_lazy("Until"),
            cell=lambda line: date_text(line.end),
            text=lambda line: line.end,
            sort=("end", "pk"),
            **grouped_by_day("end"),
        ),
        Column(
            "phase",
            gettext_lazy("Phase"),
            cell=lambda line: line.phase.label if line.phase_id else "–",
            sort=("phase__start", "start"),
            default=False,
            group="phase",
        ),
        Column(
            "venue", gettext_lazy("Place"), cell=_venue, sort=("project__venue_site__name", "project__venue", "start")
        ),
        Column(
            "meeting_point",
            gettext_lazy("Meeting point"),
            cell=lambda line: line.meeting_point or "–",
            sort=("meeting_point", "start"),
            group="meeting_point",
            group_label=lambda line: line.meeting_point,
        ),
        # LOG-008: the vehicle of the project's logistics the person travels with – and whether they drive.
        Column(
            "vehicle",
            gettext_lazy("Vehicle"),
            cell=_vehicle,
            sort=("vehicle_line__title", "start"),
            default=False,
        ),
        Column(
            "hours",
            gettext_lazy("Planned hours"),
            cell=lambda line: line.planned_hours,
            sort=("planned_hours", "start"),
            css="num",
            default=False,
            group="planned_hours",
        ),
        Column(
            "state",
            pgettext_lazy("deployment", "State"),
            cell=_firmness_badge,
            text=_firmness_label,
            # Annotated by the view (``state_order``): firm, option, inquiry. UIX-044: grouped in Python by
            # the state shown – the statuses of the project in the database would split "firm".
            sort=("deployment_state", "start"),
        ),
        Column(
            "request",
            gettext_lazy("Request"),
            cell=_request_badge,
            text=lambda line: line.get_request_status_display(),
            sort=("request_status", "start"),
            group="request_status",
            group_label=lambda line: line.get_request_status_display(),
        ),
        Column(
            "note",
            gettext_lazy("Note"),
            cell=lambda line: line.note or "",
            sort=("note", "start"),
            default=False,
            group="note",
        ),
    ],
    default_sort="start",
)


class DeploymentFilterForm(StyledForm):
    """The filters of "Meine Einsätze" (UIX-043)."""

    PERIODS = (
        ("coming", gettext_lazy("coming")),
        ("past", gettext_lazy("past")),
        ("all", gettext_lazy("all")),
    )
    STATES = (
        ("", gettext_lazy("all")),
        ("firm", gettext_lazy("firm")),
        ("option", gettext_lazy("option")),
        ("inquiry", pgettext_lazy("deployment", "inquiry")),
    )
    REQUESTS = (
        ("", gettext_lazy("all")),
        ("requested", gettext_lazy("asked")),
        ("accepted", gettext_lazy("accepted")),
        ("firm", gettext_lazy("planned firmly")),  # PER-041
        ("declined", gettext_lazy("declined")),
        ("none", gettext_lazy("not asked")),
    )

    period = forms.ChoiceField(label=gettext_lazy("Period"), choices=PERIODS, required=False)
    since = forms.DateField(label=gettext_lazy("From"), required=False)
    until = forms.DateField(label=gettext_lazy("Until"), required=False)
    state = forms.ChoiceField(label=pgettext_lazy("deployment", "State"), choices=STATES, required=False)
    request = forms.ChoiceField(label=gettext_lazy("Request"), choices=REQUESTS, required=False)
    project = forms.TypedChoiceField(label=gettext_lazy("Project"), coerce=int, required=False, empty_value=None)

    def __init__(self, *args: Any, projects: list[Project], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["project"].choices = [("", _("all")), *((p.pk, f"{p.number} {p.name}") for p in projects)]
        for name in ("period", "state", "request", "project"):
            self.fields[name].widget.attrs["data-autosubmit"] = ""

    def value(self, name: str) -> Any:
        """A filter value, or its default if the form is not valid."""
        if self.is_valid():
            return self.cleaned_data.get(name)
        return None

    @property
    def active_count(self) -> int:
        """How many filters narrow the list beyond "coming" – for the summary next to the filter button."""
        if not self.is_valid():
            return 0
        data = self.cleaned_data
        count = int((data.get("period") or "coming") != "coming")
        return count + sum(1 for name in ("since", "until", "state", "request", "project") if data.get(name))


def filtered_lines(lines: QuerySet[CrewLine], form: DeploymentFilterForm) -> QuerySet[CrewLine]:
    """The crew lines the filters of "Meine Einsätze" leave (UIX-043)."""
    now = timezone.now()
    period = form.value("period") or "coming"
    if period == "coming":
        lines = lines.filter(end__gte=now - STILL_COMING)
    elif period == "past":
        lines = lines.filter(end__lt=now - STILL_COMING)
    since, until = form.value("since"), form.value("until")
    if since:
        lines = lines.filter(end__gt=timezone.make_aware(datetime.datetime.combine(since, datetime.time.min)))
    if until:
        next_day = until + datetime.timedelta(days=1)
        lines = lines.filter(start__lt=timezone.make_aware(datetime.datetime.combine(next_day, datetime.time.min)))
    state = form.value("state")
    if state == "firm":
        lines = lines.filter(project__status__in=FIRM_STATUSES)
    elif state in ("option", "inquiry"):
        lines = lines.filter(project__status=state)
    request_status = form.value("request")
    if request_status == "none":
        lines = lines.filter(request_status=RequestStatus.NONE)
    elif request_status:
        lines = lines.filter(request_status=request_status)
    project = form.value("project")
    if project:
        lines = lines.filter(project_id=project)
    return lines


def my_deployments(request: HttpRequest) -> HttpResponse:
    """My area → Meine Einsätze: the own deployments with filters, columns, sorting, groups and CSV (UIX-043)."""
    person = person_of(request.user)
    if person is None:
        raise PermissionDenied
    own = CrewLine.objects.filter(person=person).exclude(project__status=ProjectStatus.CANCELLED)
    projects = list(
        Project.objects.filter(pk__in=own.values("project_id"))
        .order_by("-start", "number")
        .only("pk", "number", "name")
    )
    form = DeploymentFilterForm(request.GET, projects=projects)
    lines = (
        filtered_lines(own, form)
        .select_related(
            "project__parent",
            "project__venue_site",
            "job_function",
            "phase__venue_site",
            # LOG-008: the vehicle the person travels with.
            "vehicle_line__item__vehicle",
            "vehicle_line__supplier",
        )
        .annotate(deployment_state=state_order())
    )
    table = MY_DEPLOYMENTS_TABLE.state(request)
    lines = table.order(lines)
    if table.wants_csv:
        return table.csv_response(lines, _("My deployments"))
    page = paginate(request, lines)
    return render(
        request,
        "projects/my_deployments.html",
        {
            "tab": "deployments",
            "form": form,
            "table": table,
            "page": page,
            "rows": table.rows(page),
            "own_person": person,
            "filter_names": ("period", "since", "until", "state", "request", "project"),
        },
    )
