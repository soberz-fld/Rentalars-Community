# SPDX-License-Identifier: GPL-3.0-or-later
"""API of personnel for a phase, function by function (PRJ-120; API-002).

``GET /projects/{id}/phases/{phase}/staffing``
    What the dialog "Personal für diese Phase" starts with: the period of the
    phase and, per job function, its open places in the phase.

``POST /projects/{id}/phases/{phase}/staffing``
    ``functions``: a list of ``{"job_function": id, "places": n, "people": [person id or null, …]}`` – at most
    ten, one to fifty places each, no more people than places, nobody twice in a function – and ``firm`` (plan the
    people firmly, without request; PER-041). A person fills an open place of the function in the phase first;
    places beyond the open ones are added; an empty place stays open (``projects.staffing.staff_phase``). Every line
    has the period of the phase. 201 with the crew lines planned or filled, each with its warnings (PRJ-022).

Both need read access to the project and the right to plan its crew (edit access, or personnel planning), as
``/projects/{id}/crew-lines``. A new phase takes its places with ``places`` in ``POST /projects/{id}/phases``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects import crew, staffing
from rentalars.projects.access import ProjectAccess, may_plan_crew, project_for
from rentalars.projects.models import Project, ProjectPhase


class FunctionPlacesSerializer(serializers.Serializer):
    """One row: a job function, its places and – for the staffing – the person of each place."""

    job_function = serializers.PrimaryKeyRelatedField(queryset=JobFunction.objects.filter(is_active=True))
    places = serializers.IntegerField(min_value=1, max_value=staffing.MAX_PLACES)
    people = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), allow_null=True),
        required=False,
        default=list,
        help_text="The person of each place in turn; null or missing: the place stays open.",
    )


class StaffingSerializer(serializers.Serializer):
    """What ``POST /projects/{id}/phases/{phase}/staffing`` takes."""

    functions = FunctionPlacesSerializer(many=True)
    firm = serializers.BooleanField(required=False, default=False)

    def validate_functions(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One to ten rows."""
        if not value:
            raise serializers.ValidationError(_("Choose at least one job function."))
        if len(value) > staffing.MAX_ROWS:
            raise serializers.ValidationError(
                _("At most %(count)d job functions at once.") % {"count": staffing.MAX_ROWS}
            )
        return value


def rows_of(values: list[dict[str, Any]]) -> list[staffing.FunctionPlaces]:
    """The rows of validated values of :class:`FunctionPlacesSerializer`."""
    return [
        staffing.FunctionPlaces(row["job_function"], row["places"], list(row.get("people") or [])) for row in values
    ]


class PhaseStaffingView(ModuleAPIView):
    """``/projects/{id}/phases/{phase}/staffing`` – personnel for a phase, function by function (PRJ-120)."""

    module = Module.PROJECTS
    #: As the crew lines: personnel planning reads projects and still plans their crew – decided per project.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    def _phase(self, request: Request, project_pk: int, phase_pk: int) -> ProjectPhase:
        project = project_for(
            request, project_pk, ProjectAccess.READ, queryset=Project.objects.select_related("parent")
        )
        if not may_plan_crew(self.rights, project.access):
            raise PermissionDenied
        return get_object_or_404(ProjectPhase.objects.select_related("project"), pk=phase_pk, project=project)

    @extend_schema(
        responses={
            200: inline_serializer(
                "PhaseStaffingStart",
                {
                    "start": serializers.DateTimeField(),
                    "end": serializers.DateTimeField(),
                    "functions": serializers.ListField(child=serializers.DictField()),
                },
            )
        }
    )
    def get(self, request: Request, project_pk: int, phase_pk: int) -> Response:
        """The period of the phase and its open places per job function."""
        phase = self._phase(request, project_pk, phase_pk)
        moment = serializers.DateTimeField()
        return Response(
            {
                "start": moment.to_representation(phase.start),
                "end": moment.to_representation(phase.end),
                "functions": [
                    {"job_function": row.job_function.pk, "name": row.job_function.name, "open_places": row.places}
                    for row in staffing.open_rows(phase)
                ],
            }
        )

    @extend_schema(
        request=StaffingSerializer,
        responses={
            201: inline_serializer(
                "PhaseStaffed",
                {
                    "crew_lines": serializers.ListField(child=serializers.DictField()),
                },
            )
        },
    )
    def post(self, request: Request, project_pk: int, phase_pk: int) -> Response:
        """Plan the places: people fill open places of their function first; empty places stay open."""
        phase = self._phase(request, project_pk, phase_pk)
        serializer = StaffingSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        lines = staffing.staff_phase(
            phase,
            rows_of(serializer.validated_data["functions"]),
            rights=self.rights,
            firm=serializer.validated_data["firm"],
        )
        warnings = crew.crew_warnings(lines)
        return Response(
            {
                "crew_lines": [
                    {
                        "id": line.pk,
                        "job_function": line.job_function_id,
                        "person": line.person_id,
                        "request_status": line.request_status,
                        "warnings": warnings.get(line.pk, []),
                    }
                    for line in lines
                ]
            },
            status=status.HTTP_201_CREATED,
        )
