# SPDX-License-Identifier: GPL-3.0-or-later
"""API of expenses and travel costs: record, approve, reimburse, report (ZEI-019, chapter 8).

The rules are those of the browser pages, because both call
``timetracking.expenses`` (API-002): everybody records and sees their own
expenses; recording for others, approving, sending back and marking as
reimbursed need the special right "approve times and record them for
others" (ZEI-011, ZEI-013).

A receipt is sent as the file field ``receipt`` of a ``multipart/form-data``
request; the other fields may then be form fields. Without a receipt JSON
works as everywhere.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of
from rentalars.core.i18n import file_name
from rentalars.core.uploads import document_response
from rentalars.personnel.models import Person
from rentalars.projects.access import person_of
from rentalars.projects.models import Project
from rentalars.timetracking import expenses
from rentalars.timetracking.models import Expense, ExpenseKind, TimeEntryStatus

#: Filter values of ``status`` besides the statuses of times.
EXTRA_STATUS_FILTERS = ("outstanding", "reimbursed")


def expense_document(expense: Expense) -> dict[str, Any]:
    """An expense as JSON (ZEI-019). Amounts of expenses are no rates: whoever sees the expense sees them."""
    return {
        "id": expense.pk,
        "person": expense.person_id,
        "person_name": expense.person.name,
        "project": expense.project_id,
        "project_number": expense.project.number,
        "kind": expense.kind,
        "date": expense.date,
        "kilometres": expense.kilometres,
        "km_rate": expense.km_rate,
        # ZEI-027: the kilometres of the way to work deducted from a trip, and those paid for.
        "commute_km": expense.commute_km,
        "billable_kilometres": expense.billable_kilometres if expense.kilometres is not None else None,
        "amount": expense.amount,
        "note": expense.note,
        "has_receipt": bool(expense.receipt),
        "receipt_url": reverse("api:expense-receipt", args=[expense.pk]) if expense.receipt else None,
        "status": expense.status,
        "submitted_at": expense.submitted_at,
        "decided_at": expense.decided_at,
        "rejection_reason": expense.rejection_reason,
        "is_reimbursed": expense.is_reimbursed,
        "reimbursed_on": expense.reimbursed_on,
    }


def filter_expenses(selection: Any, params: Any, *, default_excludes_rejected: bool) -> Any:
    """Narrow expenses by ``person``, ``project``, ``kind``, ``status``, ``from`` and ``to``."""
    for name in ("person", "project"):
        value = str(params.get(name, "") or "")
        if value.isdigit():
            selection = selection.filter(**{f"{name}_id": int(value)})
    if params.get("kind") in ExpenseKind.values:
        selection = selection.filter(kind=params["kind"])
    wanted = params.get("status", "")
    if wanted == "outstanding":
        selection = selection.filter(status=TimeEntryStatus.APPROVED, reimbursed_on__isnull=True)
    elif wanted == "reimbursed":
        selection = selection.filter(reimbursed_on__isnull=False)
    elif wanted in TimeEntryStatus.values:
        selection = selection.filter(status=wanted)
    elif default_excludes_rejected:
        selection = selection.exclude(status=TimeEntryStatus.REJECTED)
    since, until = parse_date(params.get("from", "") or ""), parse_date(params.get("to", "") or "")
    if since:
        selection = selection.filter(date__gte=since)
    if until:
        selection = selection.filter(date__lte=until)
    return selection


FILTER_PARAMETERS = [
    OpenApiParameter("person", int),
    OpenApiParameter("project", int),
    OpenApiParameter("kind", str, enum=ExpenseKind.values),
    OpenApiParameter(
        "status",
        str,
        enum=[*TimeEntryStatus.values, *EXTRA_STATUS_FILTERS],
        description="A status, or ``outstanding`` (approved, not reimbursed) or ``reimbursed``",
    ),
    OpenApiParameter("from", str, description="First day, YYYY-MM-DD"),
    OpenApiParameter("to", str, description="Last day, YYYY-MM-DD"),
]


class ExpenseSerializer(serializers.Serializer):
    """Input for an expense (ZEI-019).

    ``person`` may be left out: the expense is then for the person linked to
    the caller's account. A trip (``kind: travel``) with ``kilometres`` costs
    kilometres × the rate per kilometre of the settings; its ``amount`` is
    calculated – less the way to work of the person, twice the distance home –
    company once a day per project (ZEI-027; ``commute_km`` in the answer). Every other expense needs an ``amount``. ``receipt`` is a
    file (JPEG, PNG or PDF) in a ``multipart/form-data`` request;
    ``remove_receipt: true`` removes the stored one. ``submit: true`` hands
    the expense in for approval right away.
    """

    person = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), required=False)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    kind = serializers.ChoiceField(choices=ExpenseKind.choices)
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=9, decimal_places=2, required=False, allow_null=True)
    kilometres = serializers.DecimalField(max_digits=7, decimal_places=1, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=250)
    receipt = serializers.FileField(required=False, allow_null=True)
    remove_receipt = serializers.BooleanField(required=False)
    submit = serializers.BooleanField(required=False)


_IDS = inline_serializer("ExpenseChoice", {"ids": serializers.ListField(child=serializers.IntegerField())})
_REJECT = inline_serializer(
    "ExpenseRejection",
    {"ids": serializers.ListField(child=serializers.IntegerField()), "reason": serializers.CharField()},
)
_REIMBURSE = inline_serializer(
    "ExpenseReimbursement",
    {
        "ids": serializers.ListField(child=serializers.IntegerField()),
        "date": serializers.DateField(required=False, help_text="Day of the reimbursement; default today"),
    },
)
_CHANGED = {200: inline_serializer("ExpensesChanged", {"changed": serializers.IntegerField()})}
_ONE = inline_serializer("ExpenseDocument", {"id": serializers.IntegerField()})


class ExpenseViewSet(ModuleViewSet):
    """``/expenses`` – expenses and travel costs per project (ZEI-019).

    Filters: ``person``, ``project``, ``kind``, ``status`` (also
    ``outstanding`` and ``reimbursed``), ``from`` and ``to`` (days). Callers
    see their own expenses; with the right to approve also those of others
    in the projects they may see (NFA-010).
    """

    module = Module.TIME_TRACKING
    serializer_class = ExpenseSerializer
    queryset = Expense.objects.none()
    # Deleting an own expense that is not approved is part of recording, not a "delete" right.
    action_levels = {"destroy": Level.WRITE}

    def get_queryset(self) -> Any:
        """The expenses the caller may see, narrowed by the filters."""
        selection = expenses.visible_expenses(self.rights, self.request.user).select_related("person", "project")
        if self.action == "list":
            selection = filter_expenses(selection, self.request.query_params, default_excludes_rejected=False)
        return selection.order_by("-date", "-id")

    def _person(self, given: Person | None) -> Person:
        person = given or person_of(self.request.user)
        if person is None:
            raise ValidationError(
                {"person": _("Your user account is not linked to a person. Name the person the expense is for.")}
            )
        return person

    @extend_schema(
        parameters=FILTER_PARAMETERS,
        responses={200: inline_serializer("ExpenseList", {"id": serializers.IntegerField()}, many=True)},
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """List expenses, newest first."""
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([expense_document(expense) for expense in page])

    @extend_schema(responses={200: _ONE})
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """One expense."""
        return Response(expense_document(self.get_object()))

    @extend_schema(responses={201: _ONE})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Record an expense (ZEI-019); a trip with kilometres is priced with the rate of the settings."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.pop("remove_receipt", None)
        expense = expenses.create_expense(
            person=self._person(values.pop("person", None)),
            rights=self.rights,
            user=request.user,
            **values,
        )
        return Response(expense_document(expense), status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: _ONE})
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change an expense that is not approved yet; a new ``receipt`` replaces the stored one."""
        expense = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if "person" in values and values.pop("person").pk != expense.person_id:
            raise ValidationError(
                {"person": _("The person of an expense cannot be changed. Delete it and record a new one.")}
            )
        submit = values.pop("submit", False)
        expenses.update_expense(
            expense,
            rights=self.rights,
            user=request.user,
            receipt=values.pop("receipt", None),
            remove_receipt=values.pop("remove_receipt", False),
            **values,
        )
        if submit:
            expenses.submit_expenses([expense], rights=self.rights, user=request.user)
        return Response(expense_document(expense))

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change single fields of an expense."""
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete an expense that is not approved yet, with its receipt."""
        expenses.delete_expense(self.get_object(), rights=self.rights, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: None})
    @action(detail=True)
    def receipt(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The receipt: a photo (JPEG) or a PDF file; 404 if there is none."""
        expense = self.get_object()
        if not expense.receipt:
            raise Http404
        return document_response(expense.receipt.name, expenses.receipt_download_name(expense))

    # --- Approval and reimbursement ------------------------------------------------------------

    def _chosen(self, request: Request) -> list[Expense]:
        """The expenses a request names by ``ids``."""
        ids = body_of(request).get("ids")
        if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
            raise ValidationError({"ids": _("Give the IDs as a list of numbers.")})
        return list(
            expenses.visible_expenses(self.rights, request.user)
            .filter(pk__in=ids)
            .select_related("person__user", "project")
        )

    @extend_schema(request=_IDS, responses=_CHANGED)
    @action(detail=False, methods=["post"])
    def submit(self, request: Request) -> Response:
        """Hand expenses in for approval."""
        changed = expenses.submit_expenses(self._chosen(request), rights=self.rights, user=request.user)
        return Response({"changed": changed})

    @extend_schema(request=_IDS, responses=_CHANGED)
    @action(detail=False, methods=["post"])
    def approve(self, request: Request) -> Response:
        """Approve submitted expenses; from now on they are costs of their project (PRJ-025)."""
        return Response(
            {"changed": expenses.approve_expenses(self._chosen(request), rights=self.rights, user=request.user)}
        )

    @extend_schema(request=_REJECT, responses=_CHANGED)
    @action(detail=False, methods=["post"])
    def reject(self, request: Request) -> Response:
        """Send submitted expenses back with a ``reason``; the person is told."""
        changed = expenses.reject_expenses(
            self._chosen(request), str(body_of(request).get("reason", "")), rights=self.rights, user=request.user
        )
        return Response({"changed": changed})

    @extend_schema(request=_REIMBURSE, responses=_CHANGED)
    @action(detail=False, methods=["post"])
    def reimburse(self, request: Request) -> Response:
        """Mark approved expenses as reimbursed on ``date`` (default today); the person is told."""
        text = str(body_of(request).get("date") or "")
        day = parse_date(text) if text else None
        if text and day is None:
            raise ValidationError({"date": _("Enter the day as YYYY-MM-DD.")})
        changed = expenses.mark_reimbursed(self._chosen(request), rights=self.rights, user=request.user, on=day)
        return Response({"changed": changed})

    @extend_schema(request=None, responses={200: _ONE})
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        """Take back the approval of an expense that is not reimbursed; it is "submitted" again."""
        expense = self.get_object()
        expenses.take_back_approval(expense, rights=self.rights, user=request.user)
        return Response(expense_document(expense))

    @extend_schema(request=None, responses={200: _ONE})
    @action(detail=True, methods=["post"], url_path="take-back-reimbursement")
    def take_back_reimbursement(self, request: Request, pk: str | None = None) -> Response:
        """Take back a mark "reimbursed" set by mistake; the expense stays approved."""
        expense = self.get_object()
        expenses.take_back_reimbursement(expense, rights=self.rights, user=request.user)
        return Response(expense_document(expense))


class ExpenseReportView(ModuleAPIView):
    """``GET /reports/expenses`` – expenses per month and person, with sums (ZEI-019).

    Everybody gets a report of their own expenses; others' need the right to
    approve. Rejected expenses are left out unless asked for with
    ``status=rejected``. The same selection as a file:
    ``/reports/expenses/csv``.
    """

    module = Module.TIME_TRACKING

    def build_report(self, request: Request) -> expenses.ExpenseReport:
        """Return the report the query asks for."""
        selection = filter_expenses(
            expenses.visible_expenses(self.rights, request.user), request.query_params, default_excludes_rejected=True
        )
        return expenses.expense_report(selection)

    @extend_schema(
        parameters=FILTER_PARAMETERS,
        responses={200: inline_serializer("ExpenseReport", {"total": serializers.DecimalField(10, 2)})},
    )
    def get(self, request: Request) -> Response:
        """Return the sums per month and person, and the expenses behind them."""
        report = self.build_report(request)
        return Response(
            {
                "total": report.total,
                "reimbursed": report.reimbursed,
                "outstanding": report.outstanding,
                "rows": [
                    {
                        "month": row.month.strftime("%Y-%m"),
                        "person": row.person.pk,
                        "person_name": row.person.name,
                        "expenses": len(row.expenses),
                        "total": row.total,
                        "reimbursed": row.reimbursed,
                        "outstanding": row.outstanding,
                        "by_kind": row.by_kind,
                    }
                    for row in report.rows
                ],
                "expenses": [expense_document(expense) for expense in report.expenses],
            }
        )


class ExpenseReportCsvView(ExpenseReportView):
    """``GET /reports/expenses/csv`` – the expenses of the report as a file for a spreadsheet (ZEI-019)."""

    @extend_schema(parameters=FILTER_PARAMETERS, responses={(200, "text/csv"): str})
    def get(self, request: Request) -> HttpResponse:  # type: ignore[override]
        """Return one row per expense, with semicolons and decimal commas."""
        response = HttpResponse(
            expenses.expenses_csv(self.build_report(request)), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="{file_name("expenses", extension="csv")}"'
        return response
