# SPDX-License-Identifier: GPL-3.0-or-later
"""Buchhaltung → EÜR: the Einnahmen-Überschuss-Rechnung of a year, as a page and as CSV (DOK-045).

Rights: the settings (read) and both price rights (``outgoing.may_see_euer``) – the page adds up the incomes and the expenses
of the whole company. The figures are prepared for the tax adviser; they are no tax advice (see :mod:`rentalars.documents.euer`).
"""

from __future__ import annotations

import csv

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.tables import formula_safe
from rentalars.documents import euer, outgoing


def require_euer(request: HttpRequest) -> None:
    """Refuse who may not see the figures of the whole company."""
    if not outgoing.may_see_euer(request_rights(request)):
        raise PermissionDenied


@module_required(Module.ADMINISTRATION)
def euer_page(request: HttpRequest) -> HttpResponse:
    """The EÜR of a year; ``?format=csv`` gives the lines behind the figures."""
    require_euer(request)
    rights = request_rights(request)
    today = timezone.localdate()
    year = euer.parse_year(request.GET.get("year"), today.year)
    result = euer.compute(year)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="euer-{year}.csv"'
        response.write("﻿")
        csv.writer(response, delimiter=";").writerows(
            [[formula_safe(cell) for cell in row] for row in euer.csv_rows(result)]
        )
        return response
    years = list(range(today.year, today.year - 8, -1))
    if year not in years:
        years.append(year)
    return render(
        request,
        "documents/euer.html",
        {**outgoing.tabs(rights), "tab": "euer", "year": year, "years": sorted(years, reverse=True), "result": result},
    )
