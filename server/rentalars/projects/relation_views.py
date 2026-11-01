# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of related projects and service cases (PRJ-119).

The box "Verwandt" on the overview of a project and on the page of a service
case (``templatetags.project_relations``) lists the related ones; whoever may
edit the project links another one there – searched by number or name, as
the other project fields do (type-ahead, :func:`relation_suggest`) – and
unlinks one. Both forms post normally and lead back to the page they are
on, so they work without the page script as well. The work is done in
``projects.relations``, which the API calls too (API-002).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.projects import relations
from rentalars.projects.access import ProjectAccess, access_level, project_for
from rentalars.projects.models import Project, ProjectRelation


def _back(request: HttpRequest, project: Project) -> HttpResponse:
    """Back to the page the box is on: ``next`` if it is one of ours, else the overview or the case."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    if project.is_service_case:
        return redirect(reverse("projects:case_detail", args=[project]) + "#related")
    return redirect(reverse("projects:deployment", args=[project]) + "#related")


def _project_for_linking(request: HttpRequest, pk: int) -> Project:
    """The project at hand, for a user who may change its relations: edit access, a whole project or a case."""
    project = project_for(request, pk, ProjectAccess.EDIT, queryset=Project.objects.select_related("parent"))
    if not relations.may_link_from(project):
        raise PermissionDenied
    return project


@require_GET
@module_required(Module.PROJECTS, Level.WRITE)
def relation_suggest(request: HttpRequest, pk: int) -> JsonResponse:
    """Projects and service cases to link while typing: number and name, those the user may read.

    The answer is that of every type-ahead field: ``id`` is the number, which
    the form sends; ``hint`` says what it is and for whom.
    """
    project = _project_for_linking(request, pk)
    found = relations.suggestions(project, request_rights(request), request.user, request.GET.get("q", ""))
    return JsonResponse(
        [
            {
                "id": other.number,
                "label": f"{other.number} {other.name}",
                "hint": _("service case") if other.is_service_case else (other.customer_name or ""),
            }
            for other in found
        ],
        safe=False,
    )


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def relation_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Link a project or service case: the one chosen among the suggestions, else the number typed."""
    project = _project_for_linking(request, pk)
    chosen = request.POST.get("project_number", "").strip() or request.POST.get("project_text", "")
    other = relations.other_for(request_rights(request), request.user, chosen)
    if other is None:
        messages.error(request, _("There is no project or service case with this number that you may see."))
        return _back(request, project)
    try:
        relations.link(project, other, note=request.POST.get("note", ""), user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("Related to %(number)s.") % {"number": other.number})
    return _back(request, project)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def relation_remove(request: HttpRequest, pk: int, relation_pk: int) -> HttpResponse:
    """Unlink a related project or case – which needs read access to it, as linking does.

    Also from a subproject that became a part with relations of its own: those can be unlinked, not added to.
    """
    project = project_for(request, pk, ProjectAccess.EDIT, queryset=Project.objects.select_related("parent"))
    relation = get_object_or_404(
        ProjectRelation.objects.filter(Q(first=project) | Q(second=project)).select_related("first", "second"),
        pk=relation_pk,
    )
    other = relation.other_than(project)
    if access_level(request_rights(request), request.user, other) < ProjectAccess.READ:
        raise PermissionDenied
    relations.unlink(relation, seen_from=project)
    messages.success(request, _("No longer related to %(number)s.") % {"number": other.number})
    return _back(request, project)
