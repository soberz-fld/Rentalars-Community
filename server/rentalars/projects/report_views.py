# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages of "Auswertung": profitability of the projects and the material (PRJ-115, MAT-053).

Both read the price calculation of the planning (``projects.profitability``)
and follow its rights (AUT-019): revenue needs the price right, the costs of
subrentals the right to see purchase prices, the costs of the crew that to
see personnel costs, and what remains all of them. The pages are for whoever
may read the module "Auswertungen" (AUT-014) and every project – a figure
over some projects only would mislead.
"""

from __future__ import annotations

import csv
import datetime
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights
from rentalars.core.i18n import file_name
from rentalars.core.listing import query_date
from rentalars.core.money import format_money
from rentalars.core.tables import csv_text
from rentalars.core.years import year_choices
from rentalars.projects import profitability
from rentalars.projects.access import may_see_reports, readable_projects


def _rights_for_reports(request: HttpRequest) -> Any:
    """The rights of the reader – who may read the reports and every project and see prices; else 403."""
    rights = request_rights(request)
    if not may_see_reports(rights):
        raise PermissionDenied
    return rights


def _period(request: HttpRequest) -> tuple[datetime.date, datetime.date, str]:
    """The period asked for: a year (``?year=2026``, the current one at first) or from – until."""
    today = timezone.localdate()
    since = query_date(request.GET.get("since"))
    until = query_date(request.GET.get("until"))
    if since and until and since <= until:
        return since, until, ""
    year_text = request.GET.get("year", "")
    year = (
        int(year_text) if year_text.isascii() and year_text.isdigit() and 2000 <= int(year_text) <= 2100 else today.year
    )
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31), str(year)


def _visibility(rights: Any) -> dict[str, bool]:
    """Which figures the reader may see (AUT-019, as the columns of the project list, PRJ-085)."""
    material_costs = rights.has(SpecialRight.PURCHASE_PRICES)
    personnel_costs = rights.has(SpecialRight.PERSONNEL_COSTS)
    return {
        "material_costs": material_costs,
        "personnel_costs": personnel_costs,
        "margin": material_costs and personnel_costs,
    }


@module_required(Module.REPORTS)
def profitability_page(request: HttpRequest) -> HttpResponse:
    """PRJ-115: revenue, costs and what remains – per month, customer and project manager; CSV of the projects."""
    rights = _rights_for_reports(request)
    since, until, year = _period(request)
    closed_only = request.GET.get("closed") == "1"
    report = profitability.project_report(
        readable_projects(rights, request.user), since, until, closed_only=closed_only
    )
    shown = _visibility(rights)
    if request.GET.get("format") == "csv":
        return _projects_csv(report, shown)
    years = year_choices(selected=int(year) if year.isascii() and year.isdigit() else None)  # Three years ahead
    return render(
        request,
        "projects/report_profitability.html",
        {
            "report": report,
            "shown": shown,
            "year": year,
            "years": years,
            "closed_only": closed_only,
            "tab": "profitability",
        },
    )


def _projects_csv(report: profitability.ProjectReport, shown: dict[str, bool]) -> HttpResponse:
    """The projects of the report as a CSV file – the figures the reader may see (IMP-005)."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{file_name("list", _("Profitability"), extension="csv")}"'
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    head = [_("Number"), _("Project"), _("Customer"), _("Back on"), _("Status"), _("Material revenue")]
    head += [_("Personnel revenue"), _("Logistics revenue"), _("Total net")]
    if shown["material_costs"]:
        head += [_("Material costs"), _("Logistics costs")]
    if shown["personnel_costs"]:
        head += [_("Personnel costs"), _("Expenses")]
    if shown["margin"]:
        head += [_("Calculated profit"), _("Calculated margin in %")]
    writer.writerow(head)
    for row in report.rows:
        project, figures = row.project, row.figures
        cells: list[Any] = [
            # Names as typed by people – never as a formula of the spreadsheet ("CSV injection", csv_text).
            csv_text(project.number),
            csv_text(project.name),
            csv_text(project.customer.name) if project.customer_id else "",
            csv_text(timezone.localtime(project.end).date()),
            project.get_status_display(),
            format_money(figures.material_revenue),
            format_money(figures.personnel_revenue),
            format_money(figures.logistics_revenue),
            format_money(figures.revenue),
        ]
        if shown["material_costs"]:
            cells += [format_money(figures.subrental_cost), format_money(figures.logistics_cost)]
        if shown["personnel_costs"]:
            cells += [format_money(figures.personnel_cost), format_money(figures.expenses)]
        if shown["margin"]:
            cells += [
                format_money(figures.margin),
                figures.margin_percent if figures.margin_percent is not None else "",
            ]
        writer.writerow(cells)
    return response


@module_required(Module.REPORTS)
def material_report_page(request: HttpRequest) -> HttpResponse:
    """MAT-053: per product – what its items cost and what its lines earned; all time or one year."""
    rights = _rights_for_reports(request)
    if not rights.has(SpecialRight.PURCHASE_PRICES) or not rights.can_read(Module.MATERIAL):
        raise PermissionDenied
    year_text = request.GET.get("year", "")
    since = until = None
    if year_text.isascii() and year_text.isdigit() and 2000 <= int(year_text) <= 2100:
        zone = timezone.get_current_timezone()
        since = datetime.datetime(int(year_text), 1, 1, tzinfo=zone)
        until = datetime.datetime(int(year_text) + 1, 1, 1, tzinfo=zone)
    rows = profitability.product_report(readable_projects(rights, request.user), since=since, until=until)
    years = year_choices(selected=int(year_text) if since else None)  # The same range as the other report
    return render(
        request,
        "projects/report_material.html",
        {"rows": rows, "year": year_text if since else "", "years": years, "tab": "material"},
    )


@module_required(Module.MATERIAL)
def item_revenue_part(request: HttpRequest, item_pk: int) -> HttpResponse:
    """MAT-053: the block "Ertrag" of an item – loaded after the page, as it reads every project the item went out with.

    It sums up projects of all customers, so it is for whoever may read every
    project and see prices, as the pages of "Auswertungen".
    """
    from rentalars.material.models import MaterialItem

    rights = _rights_for_reports(request)
    item = get_object_or_404(
        MaterialItem.objects.select_related("material_model__default_product", "product_override", "purchase_price_in"),
        pk=item_pk,
    )
    return render(
        request,
        "material/_item_revenue.html",
        {
            "item": item,
            "revenue": profitability.item_revenue(item),
            "may_see_purchase_prices": rights.has(SpecialRight.PURCHASE_PRICES),
        },
    )


@module_required(Module.MATERIAL)
def model_revenue_part(request: HttpRequest, model_pk: int) -> HttpResponse:
    """MAT-058: the block "Ertrag" of a material model – every item's earnings, added up for the model."""
    from rentalars.material.models import MaterialModel

    rights = _rights_for_reports(request)
    material_model = get_object_or_404(MaterialModel, pk=model_pk)
    return render(
        request,
        "material/_model_revenue.html",
        {
            "model": material_model,
            "revenue": profitability.model_revenue(material_model),
            "may_see_purchase_prices": rights.has(SpecialRight.PURCHASE_PRICES),
        },
    )
