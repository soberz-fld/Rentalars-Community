# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the monthly statements of service cases (DOK-016).

* ``GET /service-statements?month=2027-03`` – per customer the service cases
  of the month to bill (hours, net sum) and the statements made; the previous
  month without ``month``.
* ``POST /service-statements`` – ``{"customer", "month"}``: the draft of a
  customer and month (201); the one there is already (200).
* ``GET /service-statements/{id}`` – the statement with its cases, positions and totals.
* ``PATCH /service-statements/{id}`` – change a draft: ``introduction``, per
  case ``activity``, ``positions`` (by ``key``: ``title``, ``quantity``,
  ``unit``, ``unit_price``, ``tax_rate``, ``details``, ``removed``), ``add``
  (free positions), ``remove`` (the case leaves the statement);
  ``"refresh": true`` collects again afterwards.
* ``DELETE /service-statements/{id}`` – discard a draft (204).
* ``POST /service-statements/{id}/invoice`` – make the invoice (201); 400
  while "use Rentalars as accounting software" is off (DOK-014), as every invoice.
* ``POST /service-statements/{id}/mark`` – marked as invoiced elsewhere;
  ``{"marked": false}`` takes it back.

Everything needs the module Projects and the price right (AUT-019); reading
a statement needs read access to every case in it, changing it write access
to projects and edit access to every case – as making an invoice.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.core.money import money
from rentalars.documents import statements
from rentalars.documents.api import DocumentSerializer
from rentalars.documents.models import MonthlyStatement
from rentalars.documents.services import invoices_enabled


def _money(value: Any) -> str:
    return str(money(value))


def _position_data(position: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": position["key"],
        "source": position.get("source", ""),
        "title": position.get("title", ""),
        "details": position.get("details", ""),
        "article_number": position.get("article_number", ""),
        "quantity": position.get("quantity", "0"),
        "unit": position.get("unit", ""),
        "unit_code": position.get("unit_code", ""),
        "unit_price": _money(statements.as_decimal(position.get("unit_price"))),
        "tax_rate": position.get("tax_rate"),
        "tax_name": position.get("tax_name", ""),
        "tax_percent": position.get("tax_percent", "0"),
        "amount": _money(statements.amount_of(position)),
        "time_entries": position.get("entries") or [],
        "expense": position.get("expense"),
        "edited": bool(position.get("edited")),
        "removed": bool(position.get("removed")),
        "hint": position.get("hint", ""),
    }


def statement_data(statement: MonthlyStatement) -> dict[str, Any]:
    """A statement as the API shows it: its cases with activity and positions, the totals."""
    hints = statements.case_hints(statement) if statement.is_draft else {}
    totals = statements.totals_of(statement.content)
    return {
        "id": statement.pk,
        "customer": statement.customer_id,
        "customer_name": statement.customer.name,
        "customer_number": statement.customer.number,
        "month": statements.month_key(statement.month),
        "status": statement.status,
        "invoice": statement.invoice_id,
        "invoice_number": statement.invoice.number if statement.invoice_id else None,
        "created_at": statement.created_at,
        "created_by": statement.created_by_id,
        "changed_at": statement.changed_at,
        "marked_at": statement.marked_at,
        "introduction": statement.content.get("introduction", ""),
        "cases": [
            {
                "id": int(entry["case"]),
                "number": entry["number"],
                "name": entry.get("title", ""),
                "activity": entry.get("activity", ""),
                "activity_source": entry.get("activity_source", ""),
                "ai_model": entry.get("ai_model", ""),
                "net_total": _money(statements.case_total(entry)),
                "hours": str(statements.case_hours(entry)),
                "hints": hints.get(int(entry["case"]), []),
                "positions": [_position_data(position) for position in entry.get("positions", [])],
            }
            for entry in sorted(statement.content.get("cases", []), key=lambda entry: entry["number"])
        ],
        "net_total": _money(totals.net),
        "taxes": [
            {"name": share.name, "percent": str(share.percent), "net": _money(share.net), "tax": _money(share.tax)}
            for share in totals.taxes
        ],
        "gross_total": _money(totals.gross),
        "cancelled_invoices": statement.content.get("cancelled_invoices") or [],
    }


#: For the description of the API (API-004): what a statement looks like.
STATEMENT_SCHEMA = inline_serializer(
    "ServiceStatement",
    {
        "id": serializers.IntegerField(),
        "customer": serializers.IntegerField(),
        "customer_name": serializers.CharField(),
        "customer_number": serializers.CharField(),
        "month": serializers.CharField(help_text="YYYY-MM"),
        "status": serializers.ChoiceField(choices=["draft", "invoiced", "marked"]),
        "invoice": serializers.IntegerField(allow_null=True),
        "invoice_number": serializers.CharField(allow_null=True),
        "created_at": serializers.DateTimeField(),
        "created_by": serializers.IntegerField(allow_null=True),
        "changed_at": serializers.DateTimeField(),
        "marked_at": serializers.DateTimeField(allow_null=True),
        "introduction": serializers.CharField(),
        "cases": serializers.ListField(
            child=serializers.DictField(),
            help_text="Per case: id, number, name, activity, activity_source (proposal, user, ai), ai_model, "
            "net_total, hours, hints, positions (key, source – time, time_above, surcharge, expense, free –, title, "
            "details, article_number, quantity, unit, unit_code, unit_price, tax_rate, tax_name, tax_percent, "
            "amount, time_entries, expense, edited, removed, hint).",
        ),
        "net_total": serializers.DecimalField(max_digits=12, decimal_places=2),
        "taxes": serializers.ListField(child=serializers.DictField()),
        "gross_total": serializers.DecimalField(max_digits=12, decimal_places=2),
        "cancelled_invoices": serializers.ListField(child=serializers.DictField()),
    },
)


class StatementCreateSerializer(serializers.Serializer):
    """``POST /service-statements``."""

    customer = serializers.IntegerField()
    month = serializers.CharField(help_text="YYYY-MM; the month whose service cases are billed.")


class StatementChangeSerializer(serializers.Serializer):
    """``PATCH /service-statements/{id}`` – every part optional; all or nothing."""

    introduction = serializers.CharField(required=False, allow_blank=True)
    cases = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text='Per case {"id": <case>, "activity": …, "positions": [{"key": …, "title"/"quantity"/"unit"/'
        '"unit_price"/"tax_rate"/"details": …, "removed": bool}], "add": [{"title", "quantity", "unit", '
        '"unit_price", "tax_rate", "article_number"}], "remove": bool}. Numbers with a point.',
    )
    refresh = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Collect again afterwards: new times, expenses and cases of the month; activity texts, free "
        "positions and changed positions with the same times stay.",
    )


class _StatementView(ModuleAPIView):
    module = Module.PROJECTS

    def check_use(self, *, edit: bool = False) -> None:
        if not statements.may_use(self.rights) or (edit and not statements.may_change(self.rights)):
            raise PermissionDenied

    def statement(self, request: Request, pk: int, *, edit: bool = False) -> MonthlyStatement:
        self.check_use(edit=edit)
        statement = get_object_or_404(MonthlyStatement.objects.select_related("customer", "invoice"), pk=pk)
        statements.check_cases(statement.cases.all(), rights=self.rights, user=request.user, edit=edit)
        return statements.prune(statement)


class StatementListView(_StatementView):
    """``/service-statements`` – the overview of a month; ``POST`` makes a draft (DOK-016)."""

    @extend_schema(
        operation_id="service_statements_list",
        parameters=[OpenApiParameter("month", str, description="YYYY-MM; default: the previous month.")],
        responses=inline_serializer(
            "ServiceStatementOverview",
            {
                "month": serializers.CharField(),
                "invoices_enabled": serializers.BooleanField(),
                "times_without_project": serializers.IntegerField(
                    allow_null=True, help_text="ZEI-023: times of the month without project – with approve_times."
                ),
                "customers": serializers.ListField(
                    child=serializers.DictField(),
                    help_text="Per customer: customer, customer_name, customer_number, billable_cases (id, number, "
                    "name, done_in_month, hours, net_total), hours, net_total, statements (id, status, net_total, "
                    "invoice, invoice_number, cases).",
                ),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        """Per customer the service cases of the month to bill and the statements made – of the cases the caller reads."""
        self.check_use()
        text = request.query_params.get("month")
        month = statements.parse_month(text) if text else statements.previous_month()
        if month is None:
            raise ApiValidationError({"month": ["YYYY-MM"]})
        rows = statements.overview(month, rights=self.rights, user=request.user)
        return Response(
            {
                "month": statements.month_key(month),
                "invoices_enabled": invoices_enabled(),
                "times_without_project": statements.times_without_project(month)
                if self.rights.has(SpecialRight.APPROVE_TIMES)
                else None,
                "customers": [
                    {
                        "customer": row.customer.pk,
                        "customer_name": row.customer.name,
                        "customer_number": row.customer.number,
                        "billable_cases": [
                            {
                                "id": item.case.pk,
                                "number": item.case.number,
                                "name": item.case.name,
                                "done_in_month": item.done_in_month,
                                "hours": str(item.hours),
                                "net_total": _money(item.net_total),
                            }
                            for item in row.collected
                        ],
                        "hours": str(row.hours),
                        "net_total": _money(row.net_total),
                        "statements": [
                            {
                                "id": statement.pk,
                                "status": statement.status,
                                "net_total": _money(statement.net_total),
                                "invoice": statement.invoice_id,
                                "invoice_number": statement.invoice.number if statement.invoice_id else None,
                                "cases": [case.pk for case in statement.cases.all()],
                            }
                            for statement in row.statements
                        ],
                    }
                    for row in rows
                ],
            }
        )

    @extend_schema(request=StatementCreateSerializer, responses={201: STATEMENT_SCHEMA, 200: STATEMENT_SCHEMA})
    def post(self, request: Request) -> Response:
        """The draft of a customer and month (201) – or the one there is (200); 400 with nothing to bill."""
        from rentalars.customers.models import Customer

        self.check_use(edit=True)
        serializer = StatementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        month = statements.parse_month(serializer.validated_data["month"])
        if month is None:
            raise ApiValidationError({"month": ["YYYY-MM"]})
        customer = get_object_or_404(Customer, pk=serializer.validated_data["customer"])
        statement, created = statements.create_statement(customer, month, user=request.user, rights=self.rights)
        return Response(statement_data(statement), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class StatementDetailView(_StatementView):
    """``/service-statements/{id}`` – read, change or discard a statement (DOK-016)."""

    @extend_schema(responses=STATEMENT_SCHEMA)
    def get(self, request: Request, pk: int) -> Response:
        """The statement with its cases, positions and totals."""
        return Response(statement_data(self.statement(request, pk)))

    @extend_schema(request=StatementChangeSerializer, responses=STATEMENT_SCHEMA)
    def patch(self, request: Request, pk: int) -> Response:
        """Change a draft – and collect again with ``refresh``; 400 for a statement that is no draft."""
        statement = self.statement(request, pk, edit=True)
        serializer = StatementChangeSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        changes = {key: value for key, value in serializer.validated_data.items() if key != "refresh"}
        statement = statements.update_statement(statement, changes, user=request.user)
        if serializer.validated_data.get("refresh"):
            statements.refresh(statement, user=request.user, rights=self.rights)
        statement.refresh_from_db()
        return Response(statement_data(statement))

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: int) -> Response:
        """Discard a draft; its cases, times and expenses are free again. 400 for an invoiced or marked one."""
        statements.delete_statement(self.statement(request, pk, edit=True))
        return Response(status=status.HTTP_204_NO_CONTENT)


class StatementInvoiceView(_StatementView):
    """``POST /service-statements/{id}/invoice`` – make the invoice of a draft (DOK-006, DOK-016)."""

    @extend_schema(
        request=None,
        responses={
            201: inline_serializer(
                "ServiceStatementInvoice", {"statement": STATEMENT_SCHEMA, "invoice": DocumentSerializer()}
            )
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        """The invoice: one section per case, of the first case, billing all (DOK-015). 400 while invoices are off."""
        statement = self.statement(request, pk, edit=True)
        document = statements.create_invoice(statement, user=request.user, rights=self.rights)
        statement.refresh_from_db()
        return Response(
            {"statement": statement_data(statement), "invoice": DocumentSerializer(document).data},
            status=status.HTTP_201_CREATED,
        )


class StatementMarkView(_StatementView):
    """``POST /service-statements/{id}/mark`` – marked as invoiced in another program, or taken back (DOK-016)."""

    @extend_schema(
        request=inline_serializer(
            "ServiceStatementMark",
            {"marked": serializers.BooleanField(required=False, default=True, help_text="false takes it back.")},
        ),
        responses=STATEMENT_SCHEMA,
    )
    def post(self, request: Request, pk: int) -> Response:
        """Tick "Rechnung gestellt" on every case and mark the statement – or, with ``marked: false``, undo it.

        Marking only while invoices are written in another program (DOK-014 off): else 400, as for a statement
        whose cases cannot be billed any more or whose times changed since they were collected.
        """
        statement = self.statement(request, pk, edit=True)
        field = serializers.BooleanField()
        try:
            marked = field.to_internal_value(body_of(request).get("marked", True))
        except serializers.ValidationError as error:
            raise ApiValidationError({"marked": error.detail}) from error
        if marked:
            statement = statements.mark(statement, user=request.user, rights=self.rights)
        else:
            statement = statements.unmark(statement, user=request.user, rights=self.rights)
        return Response(statement_data(statement))
