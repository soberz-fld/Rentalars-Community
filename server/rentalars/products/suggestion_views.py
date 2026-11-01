# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the suggestions in the planning of a project (PRD-023, VFG-015).

A slot in the planning (and in the offer step) fetches the panel; the panel offers each suggestion with a button
to add it and a button to dismiss it for this project. Nothing here blocks anything: no suggestion is taken
without a click, and with no accessories or replacements named at all the slot stays empty. The work is done by
:mod:`rentalars.products.suggestions`; the API calls the same functions (API-002).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.i18n import plural_of
from rentalars.products import suggestions
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import Project


def _whole_number_list(values: list[str]) -> list[int]:
    """The entries of a list that are whole numbers."""
    return [int(value) for value in values if value.isascii() and value.isdigit()]


def panel_response(request: HttpRequest, project: Project, *, offer: bool = False) -> HttpResponse:
    """Render the panel with the current suggestions of a project."""
    rights = request_rights(request)
    found = suggestions.suggestions_for_project(project, rights=rights)
    context: dict[str, Any] = {
        "project": project,
        "found": found,
        "offer": offer,
        "can_edit": project.access >= ProjectAccess.EDIT
        and rights.can_write(Module.PROJECTS)
        and not project.is_locked
        and not offer,
        "sees_availability": rights.has(SpecialRight.AVAILABILITY),
    }
    return render(request, "projects/_suggestions.html", context)


@require_GET
@module_required(Module.PROJECTS)
def suggestions_panel(request: HttpRequest, pk: int) -> HttpResponse:
    """The suggestions of a project; ``?offer=1`` for the offer step, which only shows them."""
    project = project_for(request, pk, ProjectAccess.READ)
    return panel_response(request, project, offer=request.GET.get("offer") == "1")


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def suggestion_accept(request: HttpRequest, pk: int, relation_pk: int) -> HttpResponse:
    """Add the accessory or replacement of a suggestion to the planning; the planning answers (PRD-023, VFG-015)."""
    from rentalars.projects.views import Touched, _error_text, _planning_response

    project = project_for(request, pk, ProjectAccess.EDIT)
    touched = Touched()
    line_text = request.POST.get("line", "")
    quantity_text = request.POST.get("quantity", "").strip()
    try:
        quantity = int(quantity_text) if quantity_text else None
    except ValueError:
        messages.error(request, _("Enter a whole number of pieces."))
        return _planning_response(request, project, touched=touched)
    try:
        result = suggestions.accept(
            project,
            relation_pk,
            rights=request_rights(request),
            line_id=int(line_text) if line_text.isascii() and line_text.isdigit() else None,
            quantity=quantity,
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        touched.add(result.line)
        if result.availability.status == "short" and request_rights(request).has(SpecialRight.AVAILABILITY):
            messages.warning(
                request,
                ngettext(
                    "%(title)s was added, but %(count)d piece is missing in this period.",
                    "%(title)s was added, but %(count)d pieces are missing in this period.",
                    plural_of(result.availability.shortage_total),
                )
                % {"title": result.line.title, "count": result.availability.shortage_total},
            )
    return _planning_response(request, project, touched=touched)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def suggestion_dismiss(request: HttpRequest, pk: int) -> HttpResponse:
    """Dismiss suggestions in this project; they are not made again here."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    suggestions.dismiss(project, _whole_number_list(request.POST.getlist("relation")), user=request.user)
    return panel_response(request, project)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def suggestion_restore(request: HttpRequest, pk: int) -> HttpResponse:
    """Bring back the dismissed suggestions of this project."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    suggestions.restore(project)
    return panel_response(request, project)
