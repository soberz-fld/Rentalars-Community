# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the audits and to-dos of material items (MAT-069; API-002).

The same services as the pages (``material.audits``). The addresses:

* ``GET/POST /material-items/{id}/audits`` – where the item stands (last
  audit, next due date) and its audits; ``POST`` records one: "in order", or
  with the to-dos found (``todos``), to-dos found done (``done``) and a note;
  ``audited_at`` for an audit of the paper records, never in the future.
* ``GET/POST /material-items/{id}/todos`` – its to-dos (``?open=true`` only the
  open ones); ``POST`` notes one (``{"text": "Label fehlt"}``) – the same text
  open already is not noted twice.
* ``POST /material-items/{id}/todos/{todo}/done`` – tick a to-do done.
* ``GET /material-todos`` – the open to-dos of all items in use (filters
  ``text``, ``q``, ``item``; ``?open=false`` the done ones).
* ``POST /material-todos/done`` – tick several to-dos done at once, as the
  page "Material mit To-Do" does (``{"todos": [12, 13]}``).
* ``GET /material-audits/due`` – the items whose audit is due, oldest first.
* ``GET/PATCH /audit-settings`` – interval and quick picks (module
  "administration", as ``/label-settings``).

``/material-items`` carries ``last_audit``, ``next_audit``, ``audit_due`` and
``open_todos`` and filters by ``audit_due`` and ``open_todos``.

Reading needs read access to the material, recording write access – as for
inspections (MAT-031).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.material import audits
from rentalars.material.audit_models import ItemAudit, ItemTodo
from rentalars.material.models import MaterialItem

#: The most rows one list of this module delivers (as ``/inspections/due``).
MAX_ROWS = 2000


def _item(pk: Any) -> MaterialItem:
    return get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)


def _yes_no(value: str | None) -> bool | None:
    """``true``/``false`` of a query parameter; anything else is ``None``."""
    text = (value or "").strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return None


class ItemTodoSerializer(serializers.ModelSerializer):
    """A to-do of an item; ``audit`` names the audit that noted it."""

    display_id = serializers.CharField(source="item.display_id", read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = ItemTodo
        fields = [
            "id",
            "item",
            "display_id",
            "text",
            "is_open",
            "audit",
            "created_by",
            "created_at",
            "done_at",
            "done_by",
        ]
        read_only_fields = fields


class ItemAuditSerializer(serializers.ModelSerializer):
    """An audit with the to-dos it noted."""

    todos = ItemTodoSerializer(many=True, read_only=True)

    class Meta:
        model = ItemAudit
        fields = ["id", "item", "audited_at", "audited_by", "result", "note", "todos"]
        read_only_fields = fields


class ItemAuditsView(ModuleAPIView):
    """``/material-items/{id}/audits`` (MAT-069)."""

    module = Module.MATERIAL

    @extend_schema(
        responses={
            200: inline_serializer(
                "ItemAuditState",
                {
                    "last_audit": serializers.DateTimeField(allow_null=True),
                    "next_audit": serializers.DateField(allow_null=True),
                    "audit_due": serializers.BooleanField(),
                    "no_due_reason": serializers.CharField(),
                    "audits": ItemAuditSerializer(many=True),
                },
            )
        }
    )
    def get(self, request: Request, pk: int) -> Response:
        """The last audit, the next due date (``no_due_reason``: off, archived, bulk) and the audits, newest first."""
        item = _item(pk)
        state = audits.state_of(item)
        return Response(
            {
                "last_audit": state.last.audited_at if state.last else None,
                "next_audit": state.due_date,
                "audit_due": state.is_due,
                "no_due_reason": state.no_due_reason,
                "audits": ItemAuditSerializer(item.audits.prefetch_related("todos__item"), many=True).data,
            }
        )

    @extend_schema(
        request=inline_serializer(
            "ItemAuditCreate",
            {
                "todos": serializers.ListField(child=serializers.CharField(), required=False),
                "done": serializers.ListField(child=serializers.IntegerField(), required=False),
                "note": serializers.CharField(required=False),
                "audited_at": serializers.DateTimeField(required=False),
            },
        ),
        responses={201: ItemAuditSerializer},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Record an audit: "in order" without ``todos``, else "with to-dos"; ``done`` ticks open to-dos done."""
        item = _item(pk)
        body = body_of(request)
        todos = body.get("todos") or []
        done = body.get("done") or []
        if not isinstance(todos, list) or not isinstance(done, list):
            raise ValidationError(_("“todos” and “done” are lists."))
        audited_at = None
        if body.get("audited_at"):
            audited_at = parse_datetime(str(body["audited_at"]))
            if audited_at is None:
                raise ValidationError({"audited_at": _("Give the moment as 2027-03-01T08:00:00+01:00.")})
        audit = audits.record_audit(
            item, todos=todos, done=done, note=body.get("note", ""), user=request.user, audited_at=audited_at
        )
        return Response(ItemAuditSerializer(audit).data, status=status.HTTP_201_CREATED)


class ItemTodosView(ModuleAPIView):
    """``/material-items/{id}/todos`` (MAT-069)."""

    module = Module.MATERIAL

    @extend_schema(parameters=[OpenApiParameter("open", bool)], responses=ItemTodoSerializer(many=True))
    def get(self, request: Request, pk: int) -> Response:
        """The to-dos of the item, oldest first; ``open=true`` only the open ones, ``open=false`` only the done."""
        todos = _item(pk).todos.select_related("item")
        wanted = _yes_no(request.query_params.get("open"))
        if wanted is not None:
            todos = todos.filter(done_at__isnull=wanted)
        return Response(ItemTodoSerializer(todos, many=True).data)

    @extend_schema(
        request=inline_serializer("ItemTodoCreate", {"text": serializers.CharField()}),
        responses={201: ItemTodoSerializer},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Note a to-do; the same text open on the item already is answered instead of noted twice."""
        todo = audits.add_todo(_item(pk), body_of(request).get("text", ""), user=request.user)
        return Response(ItemTodoSerializer(todo).data, status=status.HTTP_201_CREATED)


class ItemTodoDoneView(ModuleAPIView):
    """``/material-items/{id}/todos/{todo}/done`` (MAT-069)."""

    module = Module.MATERIAL

    @extend_schema(request=None, responses=ItemTodoSerializer)
    def post(self, request: Request, pk: int, todo_pk: int) -> Response:
        """Tick the to-do done; one done already stays as it is."""
        todo = get_object_or_404(ItemTodo.objects.select_related("item"), pk=todo_pk, item_id=pk)
        audits.complete_todo(todo, user=request.user)
        return Response(ItemTodoSerializer(todo).data)


class TodoListView(ModuleAPIView):
    """``/material-todos`` – the to-dos of all items (MAT-069)."""

    module = Module.MATERIAL

    @extend_schema(
        parameters=[
            OpenApiParameter("open", bool),
            OpenApiParameter("text", str),
            OpenApiParameter("q", str),
            OpenApiParameter("item", int),
        ],
        responses=ItemTodoSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        """Open to-dos of items in use by default – as Offene Punkte → Material mit To-Do; at most 2,000."""
        params = request.query_params
        if _yes_no(params.get("open")) is False:
            todos = ItemTodo.objects.filter(done_at__isnull=False).order_by("-done_at", "-id")
        else:
            todos = audits.open_todos().order_by("item__inventory_number", "created_at", "id")
        if params.get("text"):
            todos = todos.filter(text=params["text"])
        if params.get("item", "").isdigit():
            todos = todos.filter(item_id=int(params["item"]))
        text = params.get("q", "").strip()
        if text:
            condition = Q(text__icontains=text) | Q(item__material_model__name__icontains=text)
            if text.removeprefix("#").isdigit():
                condition |= Q(item__inventory_number=int(text.removeprefix("#")))
            todos = todos.filter(condition)
        return Response(ItemTodoSerializer(todos.select_related("item")[:MAX_ROWS], many=True).data)


class TodosDoneView(ModuleAPIView):
    """``POST /material-todos/done`` – tick several to-dos done at once (MAT-070, API-002).

    The same as the button of Offene Punkte → Material mit To-Do: write
    access to the material; to-dos done already stay as they are. The answer
    says how many were open and are done now, how many were done already and
    which IDs name no to-do.
    """

    module = Module.MATERIAL

    @extend_schema(
        request=inline_serializer(
            "TodosDone",
            {"todos": serializers.ListField(child=serializers.IntegerField(), min_length=1, max_length=MAX_ROWS)},
        ),
        responses=inline_serializer(
            "TodosDoneResult",
            {
                "done": serializers.IntegerField(help_text="To-dos that were open and are done now."),
                "already_done": serializers.IntegerField(help_text="To-dos named that were done before."),
                "not_found": serializers.ListField(child=serializers.IntegerField(), help_text="IDs of no to-do."),
            },
        ),
    )
    def post(self, request: Request) -> Response:
        """Tick the to-dos named in ``todos`` done; at most 2,000 at once."""
        ids = body_of(request).get("todos")
        if (
            not isinstance(ids, list)
            or not ids
            or len(ids) > MAX_ROWS
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in ids)
        ):
            raise ValidationError(
                {"todos": _("“todos” is a list of 1 to %(count)d IDs of to-dos.") % {"count": MAX_ROWS}}
            )
        wanted = set(ids)
        todos = list(ItemTodo.objects.filter(pk__in=wanted).select_related("item"))
        done = audits.complete_todos([todo for todo in todos if todo.is_open], user=request.user)
        return Response(
            {
                "done": done,
                "already_done": len(todos) - done,
                "not_found": sorted(wanted - {todo.pk for todo in todos}),
            }
        )


class DueAuditsView(ModuleAPIView):
    """``/material-audits/due`` – the items whose audit is due (MAT-069)."""

    module = Module.MATERIAL

    @extend_schema(
        responses={
            200: inline_serializer(
                "DueAudit",
                {
                    "item": serializers.IntegerField(),
                    "display_id": serializers.CharField(),
                    "name": serializers.CharField(),
                    "last_audit": serializers.DateTimeField(allow_null=True),
                    "next_audit": serializers.DateField(),
                    "open_todos": serializers.IntegerField(),
                },
                many=True,
            )
        }
    )
    def get(self, request: Request) -> Response:
        """Oldest first – the longest time since the last audit (or since creation); at most 2,000."""
        settings_row = audits.audit_settings()
        items = audits.due_items(MaterialItem.objects.select_related("material_model"), settings_row=settings_row)
        return Response(
            [
                {
                    "item": item.pk,
                    "display_id": item.display_id,
                    "name": item.material_model.name,
                    "last_audit": item.last_audit_at,
                    "next_audit": audits.due_date_for(item, item.last_audit_at, settings_row),
                    "open_todos": item.open_todo_count,
                }
                for item in items[:MAX_ROWS]
            ]
        )


class AuditSettingsSerializer(CleanModelSerializer):
    """Einstellungen → Audits: the interval (0: off) and the quick picks, one per line."""

    quick_todo_list = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        from rentalars.material.audit_models import AuditSettings

        model = AuditSettings
        fields = ["interval_months", "quick_todos", "quick_todo_list"]


class AuditSettingsView(ModuleAPIView):
    """``GET/PATCH /audit-settings`` (MAT-067, MAT-069)."""

    module = Module.ADMINISTRATION
    schema_tag = "settings"

    @extend_schema(responses=AuditSettingsSerializer)
    def get(self, request: Request) -> Response:
        """The interval and the quick picks."""
        return Response(AuditSettingsSerializer(audits.audit_settings()).data)

    @extend_schema(request=AuditSettingsSerializer, responses=AuditSettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change the fields sent; at most 12 quick picks of at most 60 characters."""
        serializer = AuditSettingsSerializer(audits.audit_settings(), data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        row: Any = serializer.save()
        return Response(AuditSettingsSerializer(row).data)
