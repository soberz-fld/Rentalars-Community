# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views for nested groups (PRJ-037) and for optional and alternative groups (PRJ-083).

Dragging a group on the planning page – or moving it with the arrow keys of
its handle – sends where it was dropped: the group above it (none for the
top level) and its place among the groups there. Like the other requests of
the planning page the answer is the refreshed planning (see
``views._planning_response``), and the view calls the same service as the
API (API-002).

Every group has the buttons "optional" and "Alternative" next to
edit, copy and delete (PRJ-083): the first switches the group between
optional and normal, the second asks in a dialog which group it could
replace.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.projects import services
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.forms import GroupAlternativeForm
from rentalars.projects.models import Group, GroupKind
from rentalars.projects.views import _error_text, _planning_response


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def group_move(request: HttpRequest, pk: int, group_pk: int) -> HttpResponse:
    """Put a group into another group, onto the top level, or to another place among its siblings (PRJ-037).

    The form sends ``parent`` (a group's ID, empty for the top level) and
    ``position`` (1 = first among the groups there; empty: at the end). A
    place that breaks a rule – inside itself, deeper than three levels – is
    refused with a message, and the planning shows the group where it was.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    group = get_object_or_404(Group, pk=group_pk, project=project)
    parent_id = request.POST.get("parent", "").strip()
    position = request.POST.get("position", "").strip()
    try:
        parent = project.groups.filter(pk=int(parent_id)).first() if parent_id.isdigit() else None
        if parent_id and parent is None:
            raise ValidationError(_("Choose one of the groups of this project."))
        if position and not position.isdigit():
            raise ValidationError(_("“%(value)s” is not a number.") % {"value": position})
        services.move_group(group, parent=parent, position=int(position) if position else None)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _planning_response(request, project)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def group_kind(request: HttpRequest, pk: int, group_pk: int) -> HttpResponse:
    """The button "optional" of a group: optional or normal again (PRJ-083, PRJ-040).

    The form sends ``kind``: ``optional`` or ``normal``. An alternative made
    normal no longer names the group it could replace.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    group = get_object_or_404(Group, pk=group_pk, project=project)
    kind = request.POST.get("kind", "")
    try:
        if kind not in {GroupKind.OPTIONAL, GroupKind.NORMAL}:
            raise ValidationError(_("Unknown action."))
        services.update_group(group, rights=request_rights(request), kind=kind)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _planning_response(request, project)


@module_required(Module.PROJECTS, Level.WRITE)
def group_alternative(request: HttpRequest, pk: int, group_pk: int) -> HttpResponse:
    """The dialog "Alternative to …" of a group: which group it could replace (PRJ-083)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    group = get_object_or_404(Group, pk=group_pk, project=project)
    form = GroupAlternativeForm(request.POST or None, group=group)
    if request.method == "POST" and form.is_valid():
        try:
            services.update_group(
                group,
                rights=request_rights(request),
                kind=GroupKind.ALTERNATIVE,
                alternative_to=form.cleaned_data["alternative_to"],
            )
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            return _planning_response(request, project, close_dialog=True)
    return render(
        request,
        "projects/_dialog_form.html",
        {
            "form": form,
            "title": _("“%(name)s” as an alternative") % {"name": group.name},
            "action": request.path,
            "submit_label": _("Mark as alternative"),
        },
    )
