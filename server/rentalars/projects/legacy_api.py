# SPDX-License-Identifier: GPL-3.0-or-later
"""API of "Altprojekte importieren" (legacy import; API-002; PRJ-130).

The same steps as the pages (``projects.legacy_views``), with the same functions behind them
(:mod:`rentalars.projects.legacy_import`):

* ``POST /legacy-imports`` – upload one or several PDF invoices (multipart, ``files``). They are kept as a batch and read
  in the background (``job``; with AI if it is switched on for reading invoices, else by patterns). Nothing is created.
* ``GET /legacy-imports`` – the batches, newest first, page by page (API-007), with how many invoices are in which state.
* ``GET /legacy-imports/{id}`` – one batch: every invoice with its state, the proposal that was read (customer,
  invoice, positions, totals), the checks (``errors`` block taking it over, ``warnings`` want to be read) and the
  ``fingerprint`` of the proposal.
* ``PUT /legacy-imports/{id}/items/{item}`` – correct the proposal of an invoice that waits to be checked (the same
  structure as ``GET`` shows; what is not a known key, type or length is dropped) and join it to another invoice of the
  batch (``merge_into``: one project for both). Returns the item with the new checks.
* ``POST /legacy-imports/{id}/items/{item}/skip`` – do not take this invoice over.
* ``POST /legacy-imports/{id}/read`` – read the invoices that are not read yet (again).
* ``POST /legacy-imports/{id}/preview`` – ``{"items": [ids]}``: exactly what taking them over would create, per project.
* ``POST /legacy-imports/{id}/confirm`` – ``{"items": [ids], "fingerprints": {"id": "…"}}``: take them over. The
  fingerprints are those of ``preview``/``GET``; an invoice whose proposal changed since is refused.
* ``POST /legacy-imports/{id}/undo`` – take an import back (within a week, if nothing was changed on what it created).

Rights: the rights of the Buchhaltung (prices and every project, ``documents.outgoing.may_see``) to read; to change
anything write access to every project as well (``legacy_import.may_use``). New customers need write access to the
customers.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.pagination import StandardPagination
from rentalars.api.views import ModuleAPIView
from rentalars.projects import legacy_import
from rentalars.projects.legacy_draft import Draft
from rentalars.projects.legacy_models import ItemState, LegacyImportBatch, LegacyImportItem


def _may_read(view: ModuleAPIView) -> None:
    if not legacy_import.may_see_records(view.rights):
        raise PermissionDenied


def _may_change(view: ModuleAPIView) -> None:
    if not legacy_import.may_use(view.rights):
        raise PermissionDenied


def _batch(pk: int) -> LegacyImportBatch:
    return get_object_or_404(LegacyImportBatch.objects.select_related("job"), pk=pk)


def _issues(report: legacy_import.Report) -> dict[str, list[dict[str, str]]]:
    """The checks as data: ``field`` names the field ("" the invoice as a whole, ``lines.2.tax`` a position)."""
    return {
        "errors": [{"field": issue.key, "message": issue.message} for issue in report.errors],
        "warnings": [{"field": issue.key, "message": issue.message} for issue in report.warnings],
    }


def _item_data(item: LegacyImportItem, *, rights: Any, siblings: list[LegacyImportItem]) -> dict[str, Any]:
    """One invoice of a batch for an answer."""
    data: dict[str, Any] = {
        "id": item.pk,
        "file": item.original_name,
        "size": item.size,
        "sha256": item.sha256,
        "state": item.state,
        "message": item.message,
        "invoice_number": item.invoice_number,
        "invoice_date": item.invoice_date.isoformat() if item.invoice_date else None,
        "source": item.source,
        "merge_into": item.merge_into_id,
        "project": item.project.number if item.project_id else None,
        "customer": item.customer_id,
        "document": item.document_id,
        "paid": item.paid,
        "imported_at": item.imported_at.isoformat() if item.imported_at else None,
        "imported_by": item.imported_by_id,
    }
    if item.state == ItemState.READ:
        draft = legacy_import.draft_of(item)
        data["proposal"] = draft.to_json()
        data["fingerprint"] = legacy_import.fingerprint(item)
        data.update(_issues(legacy_import.check(draft, item, rights=rights, siblings=siblings)))
    return data


def _batch_data(batch: LegacyImportBatch, *, rights: Any, detail: bool) -> dict[str, Any]:
    """A batch for an answer; with ``detail`` all its invoices."""
    job = batch.job
    data: dict[str, Any] = {
        "id": batch.pk,
        "created_at": batch.created_at.isoformat(),
        "created_by": batch.created_by_id,
        "used_ai": batch.used_ai,
        "job": job.pk if job else None,
        "job_status": job.status if job else None,
        "counts": legacy_import.batch_summary(batch),
    }
    if detail:
        items = list(
            batch.items.select_related("project", "customer", "document", "merge_into").order_by("position", "pk")
        )
        open_items = [item for item in items if item.state == ItemState.READ]
        data["items"] = [_item_data(item, rights=rights, siblings=open_items) for item in items]
        data["undo_problems"] = (
            legacy_import.undo_problems(batch, rights=rights)
            if any(item.state == ItemState.IMPORTED for item in items)
            else []
        )
    return data


class ItemIdsSerializer(serializers.Serializer):
    """The invoices a step is about."""

    items = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=legacy_import.MAX_FILES
    )


class ConfirmSerializer(ItemIdsSerializer):
    """The invoices to take over, with the fingerprints of the proposals that were seen."""

    fingerprints = serializers.DictField(child=serializers.CharField(max_length=40), required=True)


def _chosen(batch: LegacyImportBatch, ids: list[int]) -> list[LegacyImportItem]:
    """The invoices of the batch that wait to be taken over, in the order of the batch."""
    items = list(batch.items.filter(pk__in=ids, state=ItemState.READ).order_by("position", "pk"))
    if len(items) != len(set(ids)):
        raise ValidationError({"items": ["Name only invoices of this batch that wait to be checked."]})
    return items


class BatchListView(ModuleAPIView):
    """``GET /legacy-imports`` and ``POST /legacy-imports`` (upload)."""

    module = Module.PROJECTS
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        responses={
            200: inline_serializer(
                "LegacyImportBatchRow",
                {
                    "id": serializers.IntegerField(),
                    "created_at": serializers.DateTimeField(),
                    "created_by": serializers.IntegerField(allow_null=True),
                    "used_ai": serializers.BooleanField(),
                    "job": serializers.IntegerField(allow_null=True),
                    "job_status": serializers.CharField(allow_null=True),
                    "counts": serializers.DictField(),
                },
                many=True,
            )
        },
        operation_id="legacy_imports_list",
    )
    def get(self, request: Request) -> Response:
        """The batches, newest first, page by page (``page``, ``page_size``; API-007)."""
        _may_read(self)
        batches = LegacyImportBatch.objects.select_related("job").order_by("-created_at", "-pk")
        # (R4-7) The standard paging of all lists: count, next, previous, results.
        paginator = StandardPagination()
        page = list(paginator.paginate_queryset(batches, request, view=self) or [])
        return paginator.get_paginated_response(
            [_batch_data(batch, rights=self.rights, detail=False) for batch in page]
        )

    @extend_schema(
        request=inline_serializer(
            "LegacyImportUpload", {"files": serializers.ListField(child=serializers.FileField())}
        ),
        responses={201: inline_serializer("LegacyImportStarted", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request) -> Response:
        """Keep the PDFs as a batch and start reading them; refused files are named in ``rejected``."""
        _may_change(self)
        files = request.FILES.getlist("files")
        if not files:
            raise ValidationError({"files": ["Send one or more PDF invoices as multipart field “files”."]})
        batch, rejected = legacy_import.add_files(files, user=request.user)
        answer: dict[str, Any] = {"rejected": [{"file": entry.name, "reason": entry.reason} for entry in rejected]}
        if batch is None:
            return Response({**answer, "id": None}, status=status.HTTP_400_BAD_REQUEST)
        legacy_import.start_reading(batch, user=request.user)
        batch = _batch(batch.pk)
        return Response(
            {**_batch_data(batch, rights=self.rights, detail=True), **answer}, status=status.HTTP_201_CREATED
        )


class BatchView(ModuleAPIView):
    """``GET /legacy-imports/{id}`` – a batch with its invoices, proposals and checks."""

    module = Module.PROJECTS

    @extend_schema(
        responses={200: inline_serializer("LegacyImportBatch", {"id": serializers.IntegerField()})},
        operation_id="legacy_imports_retrieve",
    )
    def get(self, request: Request, pk: int) -> Response:
        """One batch in detail."""
        _may_read(self)
        return Response(_batch_data(_batch(pk), rights=self.rights, detail=True))


class ItemView(ModuleAPIView):
    """``PUT /legacy-imports/{id}/items/{item}`` – correct the proposal of an invoice."""

    module = Module.PROJECTS
    parser_classes: ClassVar[list[Any]] = [JSONParser]

    @extend_schema(
        request=inline_serializer("LegacyImportItemChange", {"invoice": serializers.DictField(required=False)}),
        responses={200: inline_serializer("LegacyImportItem", {"id": serializers.IntegerField()})},
    )
    def put(self, request: Request, pk: int, item_pk: int) -> Response:
        """Replace the proposal (customer, invoice, lines, totals) and the joining; answers with the new checks."""
        _may_change(self)
        batch = _batch(pk)
        item = get_object_or_404(batch.items, pk=item_pk)
        if item.state != ItemState.READ:
            raise ValidationError({"state": ["Only an invoice that waits to be checked can be changed."]})
        data = request.data
        if not isinstance(data, dict):
            raise ValidationError({"detail": ["Send a JSON object."]})
        draft = Draft.from_json(
            {**legacy_import.draft_of(item).to_json(), **{k: v for k, v in data.items() if k != "merge_into"}}
        )
        target = None
        if data.get("merge_into") not in (None, ""):
            target_id = data["merge_into"]
            target = batch.items.filter(
                pk=target_id if isinstance(target_id, int) else -1, state=ItemState.READ
            ).first()
            if target is None or target.pk == item.pk or target.merge_into_id is not None or item.joined.exists():
                raise ValidationError(
                    {"merge_into": ["Join to another invoice of this batch that is a project of its own."]}
                )
        elif "merge_into" not in data:
            target = item.merge_into
        legacy_import.save_draft(item, draft, merge_into=target)
        item.refresh_from_db()
        siblings = list(batch.items.filter(state=ItemState.READ))
        return Response(_item_data(item, rights=self.rights, siblings=siblings))


class ItemSkipView(ModuleAPIView):
    """``POST /legacy-imports/{id}/items/{item}/skip`` – do not take this invoice over."""

    module = Module.PROJECTS

    @extend_schema(
        request=None, responses={200: inline_serializer("LegacyImportSkipped", {"id": serializers.IntegerField()})}
    )
    def post(self, request: Request, pk: int, item_pk: int) -> Response:
        """Drop the invoice and its kept file."""
        _may_change(self)
        item = get_object_or_404(_batch(pk).items, pk=item_pk)
        legacy_import.skip(item)
        return Response({"id": item.pk, "state": ItemState.SKIPPED})


class ReadView(ModuleAPIView):
    """``POST /legacy-imports/{id}/read`` – read what is not read yet."""

    module = Module.PROJECTS

    @extend_schema(
        request=None, responses={200: inline_serializer("LegacyImportRead", {"job": serializers.IntegerField()})}
    )
    def post(self, request: Request, pk: int) -> Response:
        """Start the task again for the invoices that wait to be read."""
        _may_change(self)
        batch = _batch(pk)
        job = legacy_import.start_reading(batch, user=request.user)
        return Response({"job": job.pk if job else None, "counts": legacy_import.batch_summary(batch)})


def _plan_data(plan: legacy_import.Plan) -> dict[str, Any]:
    """What taking a group of invoices over would create, as data."""
    return {
        "items": [item.pk for item in plan.items],
        "customer": plan.customer_name,
        "customer_new": plan.customer_new,
        "project": plan.project_name,
        "period": [plan.period[0].isoformat(), plan.period[1].isoformat()],
        "venue": plan.venue,
        "invoices": [
            {
                "item": entry["item"].pk,
                "number": entry["number"],
                "date": entry["date"].isoformat() if entry["date"] else None,
                "net": str(entry["net"]),
                "gross": str(entry["gross"]),
                "paid": entry["paid"],
            }
            for entry in plan.invoices
        ],
        "free_lines": plan.free_lines,
        "product_lines": plan.product_lines,
        "text_lines": plan.text_lines,
        "crew_lines": plan.crew_lines,
        "vehicle_lines": plan.vehicle_lines,
        "errors": plan.errors,
        "warnings": [issue.message for report in plan.reports.values() for issue in report.warnings],
        "fingerprints": {str(item.pk): legacy_import.fingerprint(item) for item in plan.items},
    }


class PreviewView(ModuleAPIView):
    """``POST /legacy-imports/{id}/preview`` – exactly what taking invoices over would create."""

    module = Module.PROJECTS
    parser_classes: ClassVar[list[Any]] = [JSONParser]

    @extend_schema(
        request=ItemIdsSerializer,
        responses={200: inline_serializer("LegacyImportPlans", {"plans": serializers.ListField()})},
    )
    def post(self, request: Request, pk: int) -> Response:
        """The plan per project; nothing is created."""
        _may_change(self)
        serializer = ItemIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chosen = _chosen(_batch(pk), serializer.validated_data["items"])
        plans = [
            legacy_import.summary(head, members, rights=self.rights)
            for head, members in legacy_import.groups_of(chosen)
        ]
        return Response({"plans": [_plan_data(plan) for plan in plans]})


class ConfirmView(ModuleAPIView):
    """``POST /legacy-imports/{id}/confirm`` – take the invoices over (per project, each all or nothing)."""

    module = Module.PROJECTS
    parser_classes: ClassVar[list[Any]] = [JSONParser]

    @extend_schema(
        request=ConfirmSerializer,
        responses={200: inline_serializer("LegacyImportConfirmed", {"results": serializers.ListField()})},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Create customer, closed project and historic invoice per group; a group that fails does not stop the others."""
        _may_change(self)
        serializer = ConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        batch = _batch(pk)
        chosen = _chosen(batch, values["items"])
        try:
            fingerprints = {int(key): value for key, value in values["fingerprints"].items()}
        except ValueError:
            raise ValidationError({"fingerprints": ["The keys are the ids of the invoices."]}) from None
        missing = [item.pk for item in chosen if item.pk not in fingerprints]
        if missing:
            raise ValidationError({"fingerprints": [f"Send the fingerprint of the invoices {missing}."]})
        outcomes = legacy_import.confirm(chosen, user=request.user, rights=self.rights, fingerprints=fingerprints)
        results = [
            {
                "items": [item.pk for item in outcome.items],
                "ok": outcome.ok,
                "errors": outcome.errors,
                "project": outcome.project.number if outcome.project is not None else None,
                "customer": outcome.customer.pk if outcome.customer is not None else None,
                "customer_created": outcome.customer_created,
                "documents": [document.number for document in outcome.documents],
            }
            for outcome in outcomes
        ]
        code = status.HTTP_200_OK if any(outcome.ok for outcome in outcomes) else status.HTTP_409_CONFLICT
        return Response({"results": results}, status=code)


class UndoView(ModuleAPIView):
    """``POST /legacy-imports/{id}/undo`` – take an import back."""

    module = Module.PROJECTS

    @extend_schema(
        request=None, responses={200: inline_serializer("LegacyImportUndone", {"invoices": serializers.IntegerField()})}
    )
    def post(self, request: Request, pk: int) -> Response:
        """Remove what the import created, if nothing was changed on it (see ``undo_problems``)."""
        _may_change(self)
        count = legacy_import.undo(_batch(pk), user=request.user, rights=self.rights)
        return Response({"invoices": count})
