# SPDX-License-Identifier: GPL-3.0-or-later
"""``POST /projects/bulk`` and ``POST /service-cases/bulk`` – one thing done with several projects at once.

The rules and the answer are those of :mod:`rentalars.projects.bulk` (the browser's tick boxes use the same service,
API-002). Needs write access to the module "projects"; the service decides per project, so a project the caller may
not change is named under ``skipped`` with the reason, the others are changed.
"""

from __future__ import annotations

from typing import Any, ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.api.permissions import ModulePermission
from rentalars.api.views import ModuleAPIView
from rentalars.projects import bulk
from rentalars.projects.models import CaseStatus, CaseWaitingFor


class ProjectsBulkRequestSerializer(serializers.Serializer):
    """The projects and the action; the fields are the ones the action needs (``projects.bulk``)."""

    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=bulk.MAX_PROJECTS, help_text="Keys."
    )
    action = serializers.ChoiceField(choices=bulk.BulkAction.CASES)
    follow_up_on = serializers.DateField(required=False, help_text="follow_up (and status): the day.")
    follow_up_at = serializers.TimeField(required=False, allow_null=True, help_text="The time of the reminder.")
    follow_up_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        help_text="Whom the follow-up is for; the caller when left out.",
    )
    follow_up_note = serializers.CharField(required=False, allow_blank=True, max_length=250)
    status = serializers.ChoiceField(choices=CaseStatus.choices, required=False, help_text="status (cases only).")
    waiting_for = serializers.ChoiceField(
        choices=CaseWaitingFor.choices, required=False, help_text="status waiting: what the case waits for."
    )
    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), required=False, help_text="manager (cases only)."
    )


class ProjectsBulkSkippedSerializer(serializers.Serializer):
    """A project left as it was."""

    project = serializers.IntegerField()
    title = serializers.CharField()
    reason = serializers.CharField()


class ProjectsBulkResultSerializer(serializers.Serializer):
    """What the action did."""

    action = serializers.CharField()
    changed = serializers.ListField(child=serializers.IntegerField())
    unchanged = serializers.ListField(child=serializers.IntegerField(), help_text="Were that way already.")
    skipped = ProjectsBulkSkippedSerializer(many=True)


class _BulkView(ModuleAPIView):
    """The common part of both endpoints."""

    module = Module.PROJECTS
    action_levels: ClassVar[dict[Any, int]] = {None: Level.WRITE}
    cases_only = False

    def run(self, request: Request) -> Response:
        """Check the body, do the action for every project named, answer which changed and which were skipped."""
        serializer = ProjectsBulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = bulk.change(
            data["ids"],
            data["action"],
            rights=self.rights,
            user=request.user,
            cases_only=self.cases_only,
            values={
                "on": data.get("follow_up_on"),
                "at": data.get("follow_up_at"),
                "note": data.get("follow_up_note") or "",
                "user": data.get("follow_up_user") or request.user,
                "status": data.get("status") or "",
                "waiting_for": data.get("waiting_for") or "",
                "manager": data.get("manager"),
            },
        )
        return Response(
            {
                "action": result.action,
                "changed": result.changed_ids,
                "unchanged": [project.pk for project in result.unchanged],
                "skipped": [
                    {"project": skipped.key, "title": skipped.label, "reason": skipped.reason}
                    for skipped in result.skipped
                ],
            }
        )


class ProjectsBulkView(_BulkView):
    """``POST /projects/bulk`` – set or take off the follow-up of several projects."""

    @extend_schema(
        request=ProjectsBulkRequestSerializer, responses=ProjectsBulkResultSerializer, operation_id="projects_bulk"
    )
    def post(self, request: Request) -> Response:
        """``follow_up`` and ``clear_follow_up``; the other actions are for service cases."""
        return self.run(request)


class _CasesBulkPermission(ModulePermission):
    """The module level – or working on service cases (AUT-033); the service decides per case, as in the browser."""

    def has_permission(self, request: Any, view: Any) -> bool:
        """Write access to projects, or the right to work on service cases."""
        if super().has_permission(request, view):
            return True
        user = request.user
        return bool(user and user.is_authenticated and request_rights(request).case_work >= Level.WRITE)


class ServiceCasesBulkView(_BulkView):
    """``POST /service-cases/bulk`` – follow-up, status or person responsible of several service cases."""

    cases_only = True
    permission_classes: ClassVar[list[Any]] = [_CasesBulkPermission]

    @extend_schema(
        request=ProjectsBulkRequestSerializer, responses=ProjectsBulkResultSerializer, operation_id="service_cases_bulk"
    )
    def post(self, request: Request) -> Response:
        """``follow_up``, ``clear_follow_up``, ``status`` and ``manager``."""
        return self.run(request)
