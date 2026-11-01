# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the automations (ADM-013).

* ``/automations`` – the rules: list and create
* ``/automations/{id}`` – read, change, delete one rule – also one that came with Rentalars (ADM-019)
* ``/automations/restore-defaults`` – POST (ADM-019): create the missing rules that came with Rentalars
* ``/automations/runs`` – every run with its result, newest first; ``?automation=``, ``?status=``

A rule: ``trigger`` (``inquiry``, ``project_status``, ``crew_answer``,
``follow_up``; PRJ-112: ``case_follow_up``, ``case_communication``; MAT-057:
``defect``) with its
condition – ``mailbox`` (inquiry; empty: every mailbox that takes mails
without tag in), ``status`` (project_status; for the triggers of the service
cases the status of the case, empty for any), ``answer`` (crew_answer:
``accepted``, ``declined`` or empty for both), ``communication``
(case_communication: ``mail_in``, ``mail_out``, ``chat`` or empty for any) –
and ``action`` (``reply`` – only for inquiries –, ``notify``, ``open_item``;
``case_status`` with ``new_case_status`` – open, in_progress or done – only
for the service cases; MAT-057, only for ``defect``: ``create_case``
with ``subject`` and ``text`` as title and description of the case and
``user`` as the person responsible, ``create_inquiry`` with ``subject`` as
the subject in the list of inquiries) with ``recipient`` and ``user``
(notify), ``subject`` (the subject of the answer, the title of the
notification) and ``text``. ``{placeholders}`` as in the
browser. What does not fit together is refused with the field and the reason;
what does not belong to trigger and action is emptied.

Reading needs the module "administration" (settings), changing write access
to it – as in the browser, where the same checks (``Automation.problems``)
hold (API-002).

(ADM-019) The four rules that come with Rentalars carry
``default_key`` (``case_closing_due``, ``case_closing_communication``,
``case_backlog_due``, ``defect_case``; ``null`` for the company's own rules)
and ``default_changed`` (whether one differs from how it came); both are
read-only. They are changed and deleted like any rule.
``POST /automations/restore-defaults`` creates those whose key is missing –
as they came, active – and leaves every rule that is there alone; it answers
with the rules it created (201), or an empty list (200).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from django.urls import path
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api.views import ModuleReadOnlyViewSet, ModuleViewSet
from rentalars.automations import defaults
from rentalars.automations.models import Automation, AutomationRun, RunStatus


class AutomationSerializer(serializers.ModelSerializer):
    """One rule "if …, then …"."""

    default_changed = serializers.BooleanField(
        read_only=True,
        help_text="Whether a rule that came with Rentalars differs from how it came; false for own rules.",
    )

    class Meta:
        model = Automation
        fields = [
            "id",
            "name",
            "is_active",
            "trigger",
            "mailbox",
            "status",
            "answer",
            "communication",  # PRJ-112
            "action",
            "recipient",
            "user",
            "new_case_status",  # PRJ-112
            "subject",
            "text",
            "created_at",
            "default_key",  # ADM-019
            "default_changed",  # ADM-019
        ]
        read_only_fields = ["created_at", "default_key", "default_changed"]
        extra_kwargs: ClassVar[dict[str, Any]] = {
            "default_key": {
                "help_text": (
                    "The key of a rule that came with Rentalars (case_closing_due, case_closing_communication, "
                    "case_backlog_due, defect_case); null for the company's own rules."
                )
            },
            "status": {
                "help_text": (
                    "project_status: the status of the project. case_follow_up, case_communication: the status of "
                    "the service case (open, in_progress, waiting, closing, backlog, done), empty for any (PRJ-112)."
                )
            },
            "new_case_status": {"help_text": "case_status: open, in_progress or done (PRJ-112)."},
        }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Check the rule as a whole, as the browser does; empty what does not belong to trigger and action."""
        rule = Automation()
        if self.instance is not None:
            for field in self.Meta.fields:
                if field != "id" and field not in self.Meta.read_only_fields:
                    setattr(rule, field, getattr(self.instance, field))
        for field, value in attrs.items():
            setattr(rule, field, value)
        rule.subject = (rule.subject or "").strip()
        rule.text = (rule.text or "").strip()
        rule.normalise()
        problems = rule.problems()
        if problems:
            raise serializers.ValidationError(problems)
        for field in (
            "mailbox",
            "status",
            "answer",
            "communication",
            "recipient",
            "user",
            "new_case_status",
            "subject",
            "text",
        ):
            attrs[field] = getattr(rule, field)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Automation:
        """Note who created the rule."""
        request = self.context.get("request")
        validated_data["created_by"] = getattr(request, "user", None)
        return super().create(validated_data)


class AutomationViewSet(ModuleViewSet):
    """``/automations`` (ADM-013)."""

    module = Module.ADMINISTRATION
    serializer_class = AutomationSerializer
    queryset = Automation.objects.all()
    pagination_class = None
    #: Deleting a rule is a change of the settings, as in the browser – also of one that came with Rentalars.
    action_levels: ClassVar[dict[str, int]] = {"destroy": Level.WRITE, "restore_defaults": Level.WRITE}

    def get_queryset(self) -> QuerySet[Automation]:
        """All rules, by name."""
        return Automation.objects.select_related("mailbox", "user").order_by("name", "pk")

    @extend_schema(request=None, responses={201: AutomationSerializer(many=True), 200: AutomationSerializer(many=True)})
    @action(detail=False, methods=["post"], url_path="restore-defaults")
    def restore_defaults(self, request: Request) -> Response:
        """(ADM-019) Create the missing rules that came with Rentalars; leave the others alone.

        Found by ``default_key``, not by name. Answers with the rules created now (201), or an empty list (200)
        if all were there.
        """
        created = defaults.restore(user=request.user)
        return Response(
            self.get_serializer(created, many=True).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AutomationRunSerializer(serializers.ModelSerializer):
    """One run of a rule: event, result, detail."""

    class Meta:
        model = AutomationRun
        fields = [
            "id",
            "automation",
            "automation_name",
            "trigger",
            "action",
            "created_at",
            "finished_at",
            "status",
            "project",
            "event",
            "recipient",
            "detail",
        ]


class AutomationRunViewSet(ModuleReadOnlyViewSet):
    """``/automations/runs`` (ADM-013: every run is logged and visible)."""

    module = Module.ADMINISTRATION
    serializer_class = AutomationRunSerializer
    queryset = AutomationRun.objects.none()
    filter_backends: ClassVar[list[Any]] = []

    @extend_schema(
        parameters=[
            OpenApiParameter("automation", int, description="Only the runs of this rule."),
            OpenApiParameter("status", str, enum=RunStatus.values, description="Only runs with this result."),
        ]
    )
    def list(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        """Every run, newest first."""
        return super().list(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[AutomationRun]:
        """The runs, filtered."""
        runs = AutomationRun.objects.order_by("-created_at", "-pk")
        automation = self.request.query_params.get("automation", "")
        if automation.isdigit():
            runs = runs.filter(automation_id=int(automation))
        status = self.request.query_params.get("status", "")
        if status in RunStatus.values:
            runs = runs.filter(status=status)
        return runs


#: Wired into ``api/urls.py``; ``runs`` before ``{id}``.
urlpatterns = [
    path("automations", AutomationViewSet.as_view({"get": "list", "post": "create"}), name="automation-list"),
    path(
        "automations/restore-defaults",
        AutomationViewSet.as_view({"post": "restore_defaults"}, filter_backends=[]),  # no list to search or sort
        name="automation-restore-defaults",
    ),  # ADM-019
    path("automations/runs", AutomationRunViewSet.as_view({"get": "list"}), name="automation-run-list"),
    path(
        "automations/<int:pk>",
        AutomationViewSet.as_view({"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}),
        name="automation-detail",
    ),
]
