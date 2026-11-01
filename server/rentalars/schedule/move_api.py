# SPDX-License-Identifier: GPL-3.0-or-later
"""API for moving an appointment of a project to new times (VFG-026).

The timelines of the browser drag the rental period, the event period or a
phase and confirm the move in a dialog (``schedule.move_views``). The API
offers the same two steps, with the same functions (API-002,
``schedule.moves``):

* ``POST /projects/{id}/reschedule/preview`` – what the move would do,
  nothing changes: the periods that would move, the crew lines that would
  move along with who would be asked again (PER-034) and their warnings
  (PRJ-022), the rental period that would cover a phase (PRJ-100), the
  material missing before and after (PRJ-012). Every option is tried as if
  it were on, so that the answer says what each one does.
* ``POST /projects/{id}/reschedule`` – the move itself, with the options as
  sent.

The body names ``what`` (``period``, ``event``, ``phase`` with ``phase`` or –
VFG-031 – ``crew`` with ``crew_line``: a deployment as the
personnel plan drags it),
``start`` and ``end``, and the options ``move_crew`` (a phase takes its crew
along; default true), ``with_schedule`` (a rental period moved as a whole
takes the event, the phases and the crew along; default true) and
``extend_rental_period`` (a phase beyond the rental period extends it;
default false). Both need edit access to the project; a closed project
answers 400 (PRJ-009).

PRJ-121: ``follow`` for ``what=crew`` – the phase whose
only person the deployment is, or else the open places of its job function
with the same times, follow it, as on "Zeitplanung" (``moves.followers_of``).
Not sent, nothing follows (as before); sent, the preview tries it and names
what would follow in ``followers``.
"""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.views import ModuleAPIView
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import CrewLine, Project, ProjectPhase
from rentalars.schedule import moves


class RescheduleSerializer(serializers.Serializer):
    """What to move to which times, and the options (VFG-026)."""

    what = serializers.ChoiceField(
        choices=[(kind, kind) for kind in moves.KINDS],
        help_text=(
            "period: the rental period; event: the event period; phase: the phase named in `phase`; "
            "crew: the crew line named in `crew_line` (VFG-031)."
        ),
    )
    phase = serializers.IntegerField(required=False, allow_null=True, help_text="The phase, for what=phase.")
    crew_line = serializers.IntegerField(
        required=False, allow_null=True, help_text="The crew line (deployment), for what=crew (VFG-031)."
    )
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    move_crew = serializers.BooleanField(
        required=False, default=True, help_text="A phase takes its crew lines along (PRJ-080)."
    )
    with_schedule = serializers.BooleanField(
        required=False,
        default=True,
        help_text="A rental period moved as a whole – same length – takes the event, the phases and the crew along.",
    )
    extend_rental_period = serializers.BooleanField(
        required=False, default=False, help_text="A phase beyond the rental period extends it (PRJ-100)."
    )
    follow = serializers.BooleanField(
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "what=crew: the phase whose only person the deployment is – else the open places of its job "
            "function with the same times – follow it. Not sent: nothing follows."
        ),
    )


class FollowersSerializer(serializers.Serializer):
    """PRJ-121: what follows a deployment – its phase, or the open places of its job function."""

    phase = serializers.IntegerField(source="phase.pk", allow_null=True, default=None)
    open_places = serializers.SerializerMethodField()
    reason = serializers.CharField()

    def get_open_places(self, followers: Any) -> list[int]:
        """The open places that follow."""
        return [place.pk for place in followers.open_places]


class PeriodChangeSerializer(serializers.Serializer):
    """A period that moved."""

    kind = serializers.CharField(help_text="period, event, phase or part (a subproject).")
    label = serializers.CharField()
    old_start = serializers.DateTimeField(allow_null=True)
    old_end = serializers.DateTimeField(allow_null=True)
    new_start = serializers.DateTimeField()
    new_end = serializers.DateTimeField()


class CrewChangeSerializer(serializers.Serializer):
    """A crew line that moved along."""

    crew_line = serializers.IntegerField(source="line.pk")
    person = serializers.IntegerField(source="line.person_id", allow_null=True)
    old_start = serializers.DateTimeField()
    old_end = serializers.DateTimeField()
    new_start = serializers.DateTimeField(source="line.start")
    new_end = serializers.DateTimeField(source="line.end")
    asked_again = serializers.BooleanField(
        allow_null=True, help_text="PER-034: null – not asked again; else whether the person was told."
    )
    warnings = serializers.ListField(child=serializers.CharField(), help_text="PRJ-022, after the move.")


class OutcomeSerializer(serializers.Serializer):
    """What a move did – or would do."""

    changes = PeriodChangeSerializer(many=True)
    crew_lines = CrewChangeSerializer(many=True, source="crew")
    material_lines = serializers.IntegerField(help_text="Material lines that had the former rental period.")
    planned_hours_before = serializers.DecimalField(
        source="hours_before",
        max_digits=8,
        decimal_places=2,
        allow_null=True,
        help_text="VFG-031: the planned hours of a moved crew line before, if they followed its period (PRJ-023).",
    )
    planned_hours_after = serializers.DecimalField(
        source="hours_after", max_digits=8, decimal_places=2, allow_null=True, help_text="… and after."
    )
    rental_period_extended = serializers.BooleanField(source="extended")
    shortage_before = serializers.IntegerField(
        allow_null=True,
        help_text="Pieces missing before (PRJ-012); null if the rental period does not change, or for callers "
        "without the special right to see availability (AUT-032).",
    )
    shortage_after = serializers.IntegerField(allow_null=True, help_text="Pieces missing afterwards.")
    followers = FollowersSerializer(allow_null=True, help_text="What followed a deployment (what=crew).")
    vehicle_lines = serializers.IntegerField(help_text="Vehicle bookings that moved with a phase that followed.")
    warnings = serializers.ListField(
        child=serializers.CharField(),
        help_text="PRJ-005: for what=period or event – the event ends after the end of the rental period "
        '("material back by"). A warning: the move is made.',
    )


class RentalPeriodCoverSerializer(serializers.Serializer):
    """PRJ-100: the rental period that would cover the phase at its new times."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    blocked_by = serializers.IntegerField(
        source="blocked_by.pk", allow_null=True, default=None, help_text="The whole project to extend first."
    )


class PreviewSerializer(serializers.Serializer):
    """The answer of the preview."""

    possible = serializers.BooleanField(source="is_possible")
    errors = serializers.ListField(child=serializers.CharField())
    outcome = OutcomeSerializer(allow_null=True)
    rental_period_suggestion = RentalPeriodCoverSerializer(source="suggestion", allow_null=True)
    extension_error = serializers.CharField()
    offers_with_schedule = serializers.BooleanField(source="move.offers_schedule")


def _move_request(request: Request, project_pk: int) -> moves.MoveRequest:
    project = project_for(request, project_pk, ProjectAccess.EDIT, queryset=Project.objects.select_related("parent"))
    serializer = RescheduleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    phase = None
    if data["what"] == moves.PHASE:
        if not data.get("phase"):
            raise serializers.ValidationError({"phase": _("Name the phase to move.")})
        phase = get_object_or_404(ProjectPhase, pk=data["phase"], project=project)
    line = None
    if data["what"] == moves.CREW:
        if not data.get("crew_line"):
            raise serializers.ValidationError({"crew_line": _("Name the crew line to move.")})
        line = get_object_or_404(
            CrewLine.objects.select_related("job_function", "person", "phase"), pk=data["crew_line"], project=project
        )
    return moves.MoveRequest(
        project=project,
        what=data["what"],
        phase=phase,
        crew_line=line,
        start=data["start"],
        end=data["end"],
        move_crew=data["move_crew"],
        with_schedule=data["with_schedule"],
        extend=data["extend_rental_period"],
        follow=data.get("follow") if data["what"] == moves.CREW else None,  # PRJ-121
    )


class ReschedulePreviewView(ModuleAPIView):
    """``POST /projects/{id}/reschedule/preview`` – what moving an appointment would do (VFG-026)."""

    module = Module.PROJECTS

    @extend_schema(request=RescheduleSerializer, responses=PreviewSerializer)
    def post(self, request: Request, project_pk: int) -> Response:
        """Nothing changes; ``possible`` says whether the move can be made."""
        move = _move_request(request, project_pk)
        preview = moves.preview_move(move, rights=self.rights, user=request.user)
        return Response(PreviewSerializer(preview).data)


class RescheduleView(ModuleAPIView):
    """``POST /projects/{id}/reschedule`` – move the rental period, the event, a phase or a crew line (VFG-026, VFG-031)."""

    module = Module.PROJECTS

    @extend_schema(request=RescheduleSerializer, responses=OutcomeSerializer)
    def post(self, request: Request, project_pk: int) -> Response:
        """Move; 400 names why it is not possible (a closed project, a part outside its whole project …)."""
        move = _move_request(request, project_pk)
        outcome: Any = moves.perform_move(move, rights=self.rights, user=request.user)
        return Response(OutcomeSerializer(outcome).data)
