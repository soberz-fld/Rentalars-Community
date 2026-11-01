# SPDX-License-Identifier: GPL-3.0-or-later
"""API for several crew lines at once (PRJ-117; API-002).

``POST /projects/{id}/crew-lines/bulk``
    The same as choosing crew lines on the planning page: ``edit`` (set the
    values given), ``firm`` (plan firmly, without request), ``ask`` (send the
    deployment requests) or ``delete``. Every line goes through the service
    for a single line; lines the action cannot be done with are named in
    ``skipped`` with the reason. See ``projects.crew_bulk``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api.views import ModuleAPIView
from rentalars.projects.access import ProjectAccess, may_plan_crew, project_for
from rentalars.projects.crew_bulk import EDIT_FIELDS, CrewBulkAction, change_crew_lines
from rentalars.projects.models import ProjectPhase, VehicleLine


class CrewBulkValuesSerializer(serializers.Serializer):
    """For ``edit``: the values to set on every line; only the fields sent are set."""

    meeting_point = serializers.CharField(max_length=200, required=False, allow_blank=True, help_text="Empty: none.")
    note = serializers.CharField(required=False, allow_blank=True, help_text="Replaces the note; empty: none.")
    phase = serializers.PrimaryKeyRelatedField(
        queryset=ProjectPhase.objects.all(),
        required=False,
        allow_null=True,
        help_text="A phase of this project, null: without phase. Without start and end the lines take its period.",
    )
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    planned_hours = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=0, required=False)
    vehicle_line = serializers.PrimaryKeyRelatedField(
        queryset=VehicleLine.objects.all(),
        required=False,
        allow_null=True,
        help_text="A motor vehicle booked in this project (LOG-008), null: no vehicle.",
    )
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, help_text="Needs the price right."
    )


class CrewBulkRequestSerializer(serializers.Serializer):
    """One thing to do with several crew lines (PRJ-117)."""

    lines = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False, help_text="IDs of the crew lines."
    )
    action = serializers.ChoiceField(
        choices=list(CrewBulkAction.ALL),
        help_text="edit (needs values); firm (plan firmly, without request); ask (send the requests); delete.",
    )
    values = CrewBulkValuesSerializer(required=False, help_text=f"For edit: some of {', '.join(EDIT_FIELDS)}.")


class SkippedCrewLineSerializer(serializers.Serializer):
    """A crew line the action was not done with."""

    line = serializers.IntegerField()
    title = serializers.CharField(help_text="Title and person, e.g. “Tontechnik – Anna Becker”.")
    reason = serializers.CharField()


class CrewBulkResultSerializer(serializers.Serializer):
    """What was done with the crew lines."""

    action = serializers.CharField()
    changed = serializers.ListField(
        child=serializers.IntegerField(), help_text="IDs of the lines changed, asked or deleted."
    )
    unchanged = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Lines that were like that already: planned firmly or accepted, asked for these times, same values.",
    )
    skipped = SkippedCrewLineSerializer(many=True)
    not_told = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="ask: lines marked “asked” whose person nobody could tell (no account, no request mail).",
    )
    asked_again = serializers.ListField(
        child=serializers.IntegerField(), help_text="edit: lines asked again for their new times (PER-034)."
    )
    warnings = serializers.ListField(
        child=serializers.CharField(),
        help_text="E.g. that the discount is above the maximum of some job functions; the maximum applies there.",
    )


class CrewBulkView(ModuleAPIView):
    """``POST /projects/{id}/crew-lines/bulk`` – one thing done with several crew lines at once (PRJ-117).

    Needs what changing a single crew line needs: edit access to the
    project, or read access together with write access to personnel
    (``access.may_plan_crew``); a discount also the price right (AUT-019).
    The people concerned are told once per request.
    """

    module = Module.PROJECTS
    # Personnel planning reads projects and still plans their crew – as ``CrewLineViewSet``.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    @extend_schema(request=CrewBulkRequestSerializer, responses=CrewBulkResultSerializer)
    def post(self, request: Request, project_pk: int) -> Response:
        """Do the action with every line named; answer which lines changed and which were skipped, and why."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        if not may_plan_crew(self.rights, project.access):
            raise PermissionDenied
        serializer = CrewBulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = change_crew_lines(
            project,
            data["lines"],
            data["action"],
            rights=self.rights,
            user=request.user,
            values=dict(data.get("values") or {}),
        )
        return Response(
            {
                "action": result.action,
                "changed": result.changed_ids,
                "unchanged": [line.pk for line in result.unchanged],
                "skipped": [
                    {"line": skipped.line.pk, "title": skipped.label, "reason": skipped.reason}
                    for skipped in result.skipped
                ],
                "not_told": [line.pk for line in result.not_told],
                "asked_again": [line.pk for line in result.asked_again],
                "warnings": result.warnings,
            }
        )
