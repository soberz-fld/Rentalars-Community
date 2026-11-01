# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the planning overviews (PRJ-028, VFG-012, VFG-014, VFG-022, VFG-023).

* ``GET /calendar`` – the projects of a span with their phases (PRJ-028)
* ``GET /utilization`` – reserved quantity of products day by day (VFG-012)
* ``GET /personnel-plan`` – availability, deployments and absences of
  everybody who can be planned, with warnings (VFG-014, VFG-023)

The span is given as ``from`` (a date; default: Monday of this week) and
``weeks`` (1 to 12) – or ``days`` (1 to 84) for a span of single days, as
the pages show 1 to 10 days in hour columns (VFG-022, VFG-024); 84 days are
the longest span, as 12 weeks. Times are always exact; the hour columns of
the pages are a matter of display.
The shortage list (VFG-013) is ``GET /shortages``.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.views import ModuleAPIView
from rentalars.availability.services import utilization
from rentalars.masterdata.models import Category
from rentalars.personnel.marks import effective_periods
from rentalars.personnel.models import Absence, AvailabilityState, Person
from rentalars.products.models import Product
from rentalars.projects.access import visible_projects
from rentalars.projects.models import CrewLine, ProjectPhase, ProjectStatus
from rentalars.schedule import services

SPAN_PARAMETERS = [
    OpenApiParameter("from", str, description="First day, YYYY-MM-DD (default: Monday of this week)"),
    OpenApiParameter("weeks", int, description="Number of weeks, 1 to 12"),
    OpenApiParameter("days", int, description="Number of days instead of weeks, 1 to 84 (VFG-022, VFG-024)"),
]

#: At most this many products in one answer of ``/utilization``.
MAX_UTILIZATION_PRODUCTS = 200


def span_of(request: Request, *, default_weeks: int) -> list[datetime.date]:
    """The days asked for: ``weeks`` from ``from``, or ``days`` single days, 1 to 84 (VFG-022, VFG-024).

    Raises:
        ValidationError: ``from`` is no date, ``weeks`` or ``days`` no number.
    """
    raw_first = request.query_params.get("from", "")
    first = parse_date(raw_first) if raw_first else services.monday_of(timezone.localdate())
    if first is None:
        raise ValidationError({"from": _("Give the first day as YYYY-MM-DD.")})
    raw_days = request.query_params.get("days", "")
    if raw_days:
        try:
            days = int(raw_days)
        except ValueError as error:
            raise ValidationError({"days": _("Give the number of days as a number.")}) from error
        return services.day_range(first, max(1, min(services.MAX_WEEKS * 7, days)))
    try:
        weeks = int(request.query_params.get("weeks", default_weeks))
    except ValueError as error:
        raise ValidationError({"weeks": _("Give the number of weeks as a number.")}) from error
    weeks = max(1, min(services.MAX_WEEKS, weeks))
    return services.day_range(first, weeks * 7)


class CalendarView(ModuleAPIView):
    """``GET /calendar`` – projects and their phases that touch the span (PRJ-028).

    Cancelled projects are left out unless ``all=1``. Only projects the
    caller may see are listed (AUT-016). A project is listed
    also when only one of its phases touches the span (PRJ-092).
    """

    module = Module.PROJECTS
    schema_tag = "schedule"

    @extend_schema(
        parameters=[*SPAN_PARAMETERS, OpenApiParameter("all", bool, description="Also cancelled projects")],
        responses={200: inline_serializer("CalendarEntries", {"id": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request) -> Response:
        """The projects of the span, sorted by start."""
        days = span_of(request, default_weeks=4)
        start, end = services.bounds(days)
        # PRJ-090: service cases are not in the calendar.
        projects = visible_projects(self.rights, request.user).exclude(kind="service_case")
        if not request.query_params.get("all"):
            projects = projects.exclude(status=ProjectStatus.CANCELLED)
        # PRJ-092: also a project with only a phase in the span (a planning meeting before, follow-up work after).
        projects = list(services.projects_or_phases_in(projects, start, end).order_by("start", "number"))
        phases: dict[int, list[ProjectPhase]] = {}
        for phase in ProjectPhase.objects.filter(project__in=[project.pk for project in projects]).select_related(
            "venue_site"
        ):
            phases.setdefault(phase.project_id, []).append(phase)
        return Response(
            [
                {
                    "id": project.pk,
                    "number": project.number,
                    "name": project.name,
                    # PRJ-044: the whole project of a part, else null.
                    "parent": project.parent_id,
                    "status": project.status,
                    "start": project.start,
                    "end": project.end,
                    "venue": project.venue,
                    "phases": [
                        {"kind": phase.kind, "label": phase.label, "start": phase.start, "end": phase.end}
                        for phase in phases.get(project.pk, [])
                    ],
                }
                for project in projects
            ]
        )


class UtilizationView(ModuleAPIView):
    """``GET /utilization`` – how much of products is reserved, day by day (VFG-012).

    Choose the products with ``product`` (repeatable) or ``category``. The
    figures sum up every project, so the caller needs project rights for
    all projects and read access to products.

    VFG-037: kits are answered as well. A kit's days
    count complete kits – ``stock`` kits in stock, ``firm`` and ``optional``
    the kits the reservations of its components take, ``free`` the complete
    kits still free –, and ``components`` lists its components (kits inside
    kits resolved) with ``per_kit``, the pieces one kit needs, and their own
    days. Every day has ``free`` (stock minus firm), every entry
    ``components`` (empty but for kits; VFG-037).
    """

    module = Module.PROJECTS
    schema_tag = "schedule"

    @extend_schema(
        parameters=[
            *SPAN_PARAMETERS,
            OpenApiParameter("product", int, many=True, description="Product IDs"),
            OpenApiParameter("category", int, description="All stock products of a category and its subcategories"),
        ],
        responses={200: inline_serializer("Utilization", {"product": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request) -> Response:
        """Per product and day: firm and optional reservations, stock and a level."""
        if self.rights.is_limited_to_assigned_projects(Module.PROJECTS) or not self.rights.can_read(Module.PRODUCTS):
            raise PermissionDenied
        if not self.rights.has(SpecialRight.AVAILABILITY):
            raise PermissionDenied  # AUT-032: availability as a special right
        days = span_of(request, default_weeks=2)
        products = Product.objects.filter(kind__in=services.UTILIZATION_KINDS)
        ids = [value for value in request.query_params.getlist("product") if value.isdigit()]
        category = request.query_params.get("category", "")
        if ids:
            products = products.filter(pk__in=[int(value) for value in ids])
        elif category.isdigit():
            products = products.filter(category_id__in=Category.objects.descendant_ids(int(category)), is_active=True)
        else:
            raise ValidationError({"product": _("Choose products or a category.")})
        chosen = list(products.order_by("article_number")[:MAX_UTILIZATION_PRODUCTS])
        rows = services.loads_with_kits(chosen, lambda product_ids: utilization(product_ids, days))
        return Response([_utilization_document(row) for row in rows])


def _utilization_document(row: services.UtilizationRow) -> dict[str, Any]:
    """One product, kit or component of ``/utilization`` with its days (VFG-012; VFG-037)."""
    document: dict[str, Any] = {
        "product": row.product.pk,
        "article_number": row.product.article_number,
        "name": row.product.name,
        "days": [
            {
                "day": load.day,
                "firm": load.firm,
                "optional": load.optional,
                "stock": load.stock,
                "free": load.free,
                "percent": load.percent,
                "level": load.level,
            }
            for load in row.loads
        ],
    }
    if row.per_kit:
        document["per_kit"] = row.per_kit
    else:
        document["components"] = [_utilization_document(part) for part in row.parts]
    return document


class PersonnelPlanView(ModuleAPIView):
    """``GET /personnel-plan`` – every active person, with what concerns the span (VFG-014, VFG-023).

    Listed are all active people, also those without a job
    function, as in the personnel plan (VFG-023); ``busy=1`` leaves out
    people without deployments or absences. ``entries`` holds deployments, absences and the availability
    the person marked (``type`` = ``availability``, ``state`` = available,
    limited or unavailable) as it counts: one at any moment, busy times of
    the linked calendar joined into blocks (PER-027). ``warnings`` names what needs attention:
    ``double_booking`` (deployments overlap), ``absence`` (planned during an
    absence), ``unavailable`` (planned although marked as not available);
    ``conflict`` is true if there is any.
    """

    module = Module.PERSONNEL
    schema_tag = "schedule"

    @extend_schema(
        parameters=[*SPAN_PARAMETERS, OpenApiParameter("busy", bool, description="Only people with entries")],
        responses={
            200: inline_serializer(
                "PersonnelPlan",
                {
                    "person": serializers.IntegerField(),
                    "name": serializers.CharField(),
                    "entries": serializers.ListField(child=serializers.DictField()),
                    "conflict": serializers.BooleanField(),
                    "warnings": serializers.ListField(child=serializers.ChoiceField(choices=services.WARNING_ORDER)),
                },
                many=True,
            )
        },
    )
    def get(self, request: Request) -> Response:
        """The rows of the personnel plan."""
        days = span_of(request, default_weeks=2)
        start, end = services.bounds(days)
        people = services.people_in_plan(
            Person.objects.filter(is_active=True), start, end, busy_only=bool(request.query_params.get("busy"))
        ).order_by("last_name", "first_name")
        lines = (
            services.overlapping(CrewLine.objects.filter(person__in=people), start, end)
            .exclude(project__status=ProjectStatus.CANCELLED)
            .select_related("project", "job_function")
            .order_by("start")
        )
        absences = services.overlapping(Absence.objects.filter(person__in=people), start, end).order_by("start")
        records: dict[int, dict[str, list[Any]]] = {}
        for kind, queryset in (("lines", lines), ("absences", absences)):
            for record in queryset:
                records.setdefault(record.person_id, {"lines": [], "absences": [], "marks": []})[kind].append(record)
        # PER-027: one availability at any moment; busy times of the linked calendar as blocks.
        for person_id, periods in effective_periods(people, start, end).items():
            records.setdefault(person_id, {"lines": [], "absences": [], "marks": []})["marks"] = periods
        rows = []
        for person in people:
            own = records.get(person.pk, {"lines": [], "absences": [], "marks": []})
            unavailable = [mark for mark in own["marks"] if mark.state == AvailabilityState.UNAVAILABLE]
            warnings, _involved = services.find_warnings(own["lines"], own["absences"], unavailable)
            entries: list[dict[str, Any]] = [
                {
                    "type": "deployment",
                    "start": line.start,
                    "end": line.end,
                    "project": line.project_id,
                    "project_number": line.project.number,
                    "job_function": line.job_function.name,
                    "request_status": line.request_status,
                }
                for line in own["lines"]
            ]
            entries += [
                {"type": "absence", "start": absence.start, "end": absence.end, "kind": absence.kind}
                for absence in own["absences"]
            ]
            entries += [
                {
                    "type": "availability",
                    "start": mark.start,
                    "end": mark.end,
                    "state": mark.state,
                    "source": mark.source,
                    "note": mark.note,
                }
                for mark in own["marks"]
            ]
            entries.sort(key=lambda entry: entry["start"])
            rows.append(
                {
                    "person": person.pk,
                    "name": person.name,
                    "entries": entries,
                    "conflict": bool(warnings),
                    "warnings": warnings,
                }
            )
        return Response(rows)
