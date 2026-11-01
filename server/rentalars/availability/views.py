# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views built on the availability engine: shortages and subrentals (PRJ-057)."""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights, require
from rentalars.availability.services import open_shortages, subrental_lines
from rentalars.availability.shortage_tables import BOTTLENECK_TABLE, SHORTAGE_TABLE, SUBRENTAL_TABLE
from rentalars.masterdata.models import Supplier
from rentalars.projects.access import readable_projects


@module_required(Module.PROJECTS)
def shortages(request: HttpRequest) -> HttpResponse:
    """All open shortages and all subrentals of running and coming projects.

    Of the projects whose planning the user may read (AUT-016); for most
    users that is every project.

    AUT-032: refused (403) without the special right to see the availability of
    material, and to a role with the overview only (the role "Crew").
    """
    rights = request_rights(request)
    require(rights.has(SpecialRight.AVAILABILITY) and rights.reads_planning)
    projects = readable_projects(rights, request.user)
    weeks = request.GET.get("weeks", "")
    horizon = int(weeks) * 7 if weeks.isdigit() and 0 < int(weeks) <= 52 else 365
    shortages = open_shortages(projects=projects, horizon_days=horizon)
    # VFG-013: the same shortages by product, with the projects they hit.
    by_product: dict[int, dict[str, Any]] = {}
    for shortage in shortages:
        entry = by_product.setdefault(
            shortage.product.pk,
            {"product": shortage.product, "missing": 0, "projects": [], "first": shortage.line.start},
        )
        entry["missing"] = max(entry["missing"], shortage.quantity)
        entry["first"] = min(entry["first"], shortage.line.start)
        if shortage.project not in entry["projects"]:
            entry["projects"].append(shortage.project)
    # PRJ-106: the subrentals of one supplier – the way there from the supplier in the master data.
    subrentals = subrental_lines(projects)
    chosen = request.GET.get("supplier", "")
    supplier = Supplier.objects.filter(pk=int(chosen)).first() if chosen.isdigit() else None
    suppliers = Supplier.objects.filter(
        Q(pk__in=subrentals.filter(supplier__isnull=False).values("supplier_id")) | Q(pk=getattr(supplier, "pk", None))
    )
    if supplier is not None:
        subrentals = subrentals.filter(supplier=supplier)
    # UIX-040: three tables of core.tables, each with its own prefix in the address.
    bottleneck_table = BOTTLENECK_TABLE.state(request)
    shortage_table = SHORTAGE_TABLE.state(request)
    subrental_table = SUBRENTAL_TABLE.state(request)
    bottlenecks = bottleneck_table.order(list(by_product.values()))
    shortages = shortage_table.order(shortages)
    subrentals = subrental_table.order(subrentals)
    for table, rows, name in (
        (bottleneck_table, bottlenecks, _("Bottlenecks by product")),
        (shortage_table, shortages, _("Open shortages")),
        (subrental_table, subrentals, _("Subrentals")),
    ):
        if table.wants_csv:
            return table.csv_response(rows, name)
    # UIX-050 (UIX-012): each of the three tables pages on its own (its prefix in the address).
    bottleneck_page = bottleneck_table.paginate(bottlenecks)
    shortage_page = shortage_table.paginate(shortages)
    subrental_page = subrental_table.paginate(subrentals)
    return render(
        request,
        "availability/shortages.html",
        {
            "tab": "shortages",
            "shortages": shortages,
            "by_product": bottlenecks,
            "subrentals": subrentals,
            "bottleneck_table": bottleneck_table,
            "bottleneck_rows": bottleneck_table.rows(bottleneck_page),
            "bottleneck_page": bottleneck_page,
            "shortage_table": shortage_table,
            "shortage_rows": shortage_table.rows(shortage_page),
            "shortage_page": shortage_page,
            "subrental_table": subrental_table,
            "subrental_rows": subrental_table.rows(subrental_page),
            "subrental_page": subrental_page,
            "suppliers": list(suppliers.order_by("name")),
            "supplier": supplier,
            "weeks": weeks if horizon != 365 else "",
            "week_choices": [2, 4, 6, 8, 12],
        },
    )
