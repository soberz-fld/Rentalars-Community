# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the profitability reports (PRJ-115, MAT-053; API-002).

* ``GET /reports/profitability`` – revenue, costs and what remains of the
  confirmed projects of a period: in total, per month, per customer, per
  project manager and per project. ``?year=2026`` (the current one if not
  given) or ``?since=…&until=…``; ``?closed=1`` only closed projects.
* ``GET /reports/material`` – per product with items: what its items cost
  and what its lines earned; ``?year=`` for one year, else all time.
* ``GET /material-items/{id}/revenue`` – what one item earned and the share
  of its purchase price (of its set's, if bought in a set, MAT-054).

The rights are those of the pages (AUT-019): reading every project and the
price right; the costs of subrentals need the right to see purchase prices,
those of the crew the right to see personnel costs – a figure the caller may
not see is left out, not sent as 0.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.views import ModuleAPIView
from rentalars.core.listing import query_date
from rentalars.core.money import money
from rentalars.projects import profitability
from rentalars.projects.access import may_see_reports, readable_projects


def _report_rights(view: Any) -> Any:
    """The rights of the caller – the module "Reports", every project and prices (:func:`may_see_reports`)."""
    rights = view.rights
    if not may_see_reports(rights):
        raise PermissionDenied
    return rights


def _figures(figures: profitability.Figures, rights: Any) -> dict[str, Any]:
    """The figures the caller may see, as strings of money (two decimals)."""
    data: dict[str, Any] = {
        "projects": figures.projects,
        "material_revenue": str(figures.material_revenue),
        "personnel_revenue": str(figures.personnel_revenue),
        "logistics_revenue": str(figures.logistics_revenue),  # LOG-009
        "revenue": str(figures.revenue),
    }
    material_costs = rights.has(SpecialRight.PURCHASE_PRICES)
    personnel_costs = rights.has(SpecialRight.PERSONNEL_COSTS)
    if material_costs:
        data["subrental_cost"] = str(figures.subrental_cost)
        data["logistics_cost"] = str(figures.logistics_cost)  # LOG-010
    if personnel_costs:
        data["personnel_cost"] = str(figures.personnel_cost)
        data["expenses"] = str(figures.expenses)
    if material_costs and personnel_costs:
        data["costs"] = str(figures.costs)
        data["margin"] = str(figures.margin)
        data["margin_percent"] = str(figures.margin_percent) if figures.margin_percent is not None else None
    return data


def _money(help_text: str = "") -> serializers.Field:
    return serializers.DecimalField(max_digits=14, decimal_places=2, help_text=help_text)


def _figure_fields() -> dict[str, serializers.Field]:
    """The figures of a row; costs, profit and margin only for callers with the rights for them (AUT-019)."""
    return {
        "projects": serializers.IntegerField(),
        "material_revenue": _money(),
        "personnel_revenue": _money(),
        "logistics_revenue": _money("Vehicles and trailers (LOG-009)."),
        "revenue": _money("Net, after discounts."),
        "subrental_cost": _money("Only with the right to see purchase prices."),
        "logistics_cost": _money(
            "Internal costs of the vehicles (LOG-010); only with the right to see purchase prices."
        ),
        "personnel_cost": _money("Only with the right to see personnel costs."),
        "expenses": _money("Approved expenses; only with the right to see personnel costs."),
        "costs": _money("Only with both rights."),
        "margin": _money("What remains (PRJ-087); only with both rights."),
        "margin_percent": serializers.DecimalField(max_digits=7, decimal_places=1, allow_null=True),
    }


#: One class for months, customers and project managers, so that the description names it once.
_GROUP_CLASS = inline_serializer(
    "ProfitabilityGroup",
    {"key": serializers.CharField(allow_null=True), "label": serializers.CharField(), **_figure_fields()},
).__class__
PROFITABILITY_REPORT = inline_serializer(
    "ProfitabilityReport",
    {
        "since": serializers.DateField(),
        "until": serializers.DateField(),
        "closed_only": serializers.BooleanField(),
        "total": inline_serializer("ProfitabilityFigures", _figure_fields()),
        "months": _GROUP_CLASS(many=True),
        "customers": _GROUP_CLASS(many=True),
        "managers": _GROUP_CLASS(many=True),
        "projects": inline_serializer(
            "ProfitabilityProject",
            {
                "id": serializers.IntegerField(),
                "number": serializers.CharField(),
                "name": serializers.CharField(),
                "customer": serializers.IntegerField(allow_null=True),
                "status": serializers.CharField(),
                "end": serializers.DateTimeField(),
                **_figure_fields(),
            },
            many=True,
        ),
    },
)


PERIOD_PARAMETERS = [
    OpenApiParameter("year", int, description="The year; the current one if neither year nor since/until is given."),
    OpenApiParameter("since", datetime.date, description="With until: the first day of the period."),
    OpenApiParameter("until", datetime.date, description="With since: the last day of the period."),
    OpenApiParameter("closed", bool, description="1: only closed projects."),
]


class ProfitabilityReportView(ModuleAPIView):
    """``GET /reports/profitability`` – PRJ-115."""

    module = Module.REPORTS
    schema_tag = "reports"

    @extend_schema(
        parameters=PERIOD_PARAMETERS,
        responses={200: PROFITABILITY_REPORT},
    )
    def get(self, request: Request) -> Response:
        """Projects counted in the month their material comes back; whole projects with their parts."""
        rights = _report_rights(self)
        today = timezone.localdate()
        since = query_date(request.query_params.get("since"))
        until = query_date(request.query_params.get("until"))
        if not (since and until and since <= until):
            year_text = str(request.query_params.get("year", ""))
            year = int(year_text) if year_text.isdigit() and 2000 <= int(year_text) <= 2100 else today.year
            since, until = datetime.date(year, 1, 1), datetime.date(year, 12, 31)
        closed_only = str(request.query_params.get("closed", "")) in {"1", "true"}
        report = profitability.project_report(
            readable_projects(rights, request.user), since, until, closed_only=closed_only
        )

        def groups(items: list[profitability.Group]) -> list[dict[str, Any]]:
            return [
                {
                    "key": str(group.key) if group.key is not None else None,
                    "label": group.label,
                    **_figures(group.figures, rights),
                }
                for group in items
            ]

        return Response(
            {
                "since": report.since,
                "until": report.until,
                "closed_only": closed_only,
                "total": _figures(report.total, rights),
                "months": groups(report.months),
                "customers": groups(report.customers),
                "managers": groups(report.managers),
                "projects": [
                    {
                        "id": row.project.pk,
                        "number": row.project.number,
                        "name": row.project.name,
                        "customer": row.project.customer_id,
                        "status": row.project.status,
                        "end": row.project.end,
                        **_figures(row.figures, rights),
                    }
                    for row in report.rows
                ],
            }
        )


class MaterialReportView(ModuleAPIView):
    """``GET /reports/material`` – MAT-053: per product, what its items cost and what its lines earned."""

    module = Module.REPORTS
    schema_tag = "reports"

    @extend_schema(
        parameters=[OpenApiParameter("year", int, description="One year; all time if not given.")],
        responses={
            200: inline_serializer(
                "MaterialReport",
                {
                    "product": serializers.IntegerField(),
                    "article_number": serializers.CharField(),
                    "name": serializers.CharField(),
                    "items": serializers.IntegerField(),
                    "purchase_total": _money("What its items cost; a set's price spread over the set."),
                    "revenue": _money("What its lines earned, after discounts."),
                    "share_percent": serializers.DecimalField(max_digits=7, decimal_places=1, allow_null=True),
                },
                many=True,
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Sorted by the share of the purchase prices earned, the highest first."""
        rights = _report_rights(self)
        if not rights.has(SpecialRight.PURCHASE_PRICES) or not rights.can_read(Module.MATERIAL):
            raise PermissionDenied
        year_text = str(request.query_params.get("year", ""))
        since = until = None
        if year_text.isdigit() and 2000 <= int(year_text) <= 2100:
            zone = timezone.get_current_timezone()
            since = datetime.datetime(int(year_text), 1, 1, tzinfo=zone)
            until = datetime.datetime(int(year_text) + 1, 1, 1, tzinfo=zone)
        rows = profitability.product_report(readable_projects(rights, request.user), since=since, until=until)
        return Response(
            [
                {
                    "product": row.product.pk,
                    "article_number": row.product.article_number,
                    "name": row.product.name,
                    "items": row.items,
                    "purchase_total": str(row.purchase_total),
                    "revenue": str(row.revenue),
                    "share_percent": str(row.share_percent) if row.share_percent is not None else None,
                }
                for row in rows
            ]
        )


class ItemRevenueView(ModuleAPIView):
    """``GET /material-items/{id}/revenue`` – MAT-053: what an item earned, and the share of its purchase price."""

    module = Module.MATERIAL
    schema_tag = "material"

    @extend_schema(
        responses={
            200: inline_serializer(
                "ItemRevenue",
                {
                    "item": serializers.IntegerField(),
                    "display_id": serializers.CharField(),
                    "total": _money(),
                    "direct": _money("In projects it was chosen for when packing."),
                    "estimated": _money("Its share of the pieces that went out without an item chosen."),
                    "projects": serializers.IntegerField(),
                    "set_items": serializers.ListField(child=serializers.IntegerField(), help_text="MAT-054"),
                    "set_revenue": _money("What the whole set earned; null if not bought as a set."),
                    "purchase_price": _money("Only with the right to see purchase prices; the set's for a set."),
                    "share_percent": serializers.DecimalField(
                        max_digits=7,
                        decimal_places=1,
                        allow_null=True,
                        help_text="Only with the right to see purchase prices.",
                    ),
                },
            )
        }
    )
    def get(self, request: Request, pk: int) -> Response:
        """``direct``: in projects it was chosen for when packing; ``estimated``: its share of the rest."""
        from rentalars.material.models import MaterialItem

        if not may_see_reports(self.rights):
            raise PermissionDenied  # sums up projects of all customers – a report
        item = get_object_or_404(
            MaterialItem.objects.select_related(
                "material_model__default_product", "product_override", "purchase_price_in"
            ),
            pk=pk,
        )
        revenue = profitability.item_revenue(item)
        data: dict[str, Any] = {
            "item": item.pk,
            "display_id": item.display_id,
            "total": str(revenue.total),
            "direct": str(money(revenue.direct)),
            "estimated": str(money(revenue.estimated)),
            "projects": revenue.projects,
            # MAT-054: bought in a set – the set is compared with its price.
            "set_items": [member.pk for member in revenue.set_items],
            "set_revenue": str(money(revenue.set_revenue)) if revenue.set_items else None,
        }
        if self.rights.has(SpecialRight.PURCHASE_PRICES):
            data["purchase_price"] = str(revenue.purchase_price) if revenue.purchase_price is not None else None
            data["share_percent"] = str(revenue.share_percent) if revenue.share_percent is not None else None
        return Response(data)


class ModelRevenueView(ModuleAPIView):
    """``GET /material-models/{id}/revenue`` – MAT-058: what the items of a model earned, item by item."""

    module = Module.MATERIAL
    schema_tag = "material"

    @extend_schema(
        responses={
            200: inline_serializer(
                "ModelRevenue",
                {
                    "material_model": serializers.IntegerField(),
                    "total": _money(),
                    "direct": _money("In projects an item was chosen for when packing."),
                    "estimated": _money("The share of the pieces that went out without an item chosen."),
                    "projects": serializers.IntegerField(),
                    "purchase_total": _money(
                        "Only with the right to see purchase prices; a set's price spread evenly."
                    ),
                    "share_percent": serializers.DecimalField(max_digits=7, decimal_places=1, allow_null=True),
                    "items": inline_serializer(
                        "ModelRevenueItem",
                        {
                            "item": serializers.IntegerField(),
                            "display_id": serializers.CharField(),
                            "total": _money(),
                            "projects": serializers.IntegerField(),
                            "purchase_price": _money("Only with the right to see purchase prices."),
                        },
                        many=True,
                    ),
                },
            )
        }
    )
    def get(self, request: Request, pk: int) -> Response:
        """Sorted by what each item earned, the highest first."""
        from rentalars.material.models import MaterialModel

        if not may_see_reports(self.rights):
            raise PermissionDenied  # sums up projects of all customers – a report
        revenue = profitability.model_revenue(get_object_or_404(MaterialModel, pk=pk))
        prices = self.rights.has(SpecialRight.PURCHASE_PRICES)
        data: dict[str, Any] = {
            "material_model": pk,
            "total": str(revenue.total),
            "direct": str(revenue.direct),
            "estimated": str(revenue.estimated),
            "projects": revenue.projects,
            "items": [
                {
                    "item": row.item.pk,
                    "display_id": row.item.display_id,
                    "total": str(row.total),
                    "projects": row.projects,
                    **(
                        {"purchase_price": str(row.purchase_price) if row.purchase_price is not None else None}
                        if prices
                        else {}
                    ),
                }
                for row in revenue.items
            ],
        }
        if prices:
            data["purchase_total"] = str(revenue.purchase_total) if revenue.purchase_total is not None else None
            data["share_percent"] = str(revenue.share_percent) if revenue.share_percent is not None else None
        return Response(data)
