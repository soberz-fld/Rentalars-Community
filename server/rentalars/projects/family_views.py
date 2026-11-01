# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for whole projects and their parts (PRJ-031, PRJ-044 to PRJ-049, PRJ-060).

* Add a part to a whole project.
* The overview of a whole project: every part with its figures, their sum,
  and the shortages between the parts (PRJ-046, PRJ-047).
* Take over material from another part (PRJ-060).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.projects import services
from rentalars.projects.access import ProjectAccess, access_level, project_for
from rentalars.projects.family import build_family, takeover_sources
from rentalars.projects.forms import ProjectForm
from rentalars.projects.models import Project
from rentalars.projects.project_templates import apply_template
from rentalars.projects.views import Touched, _error_text, _planning_response


@module_required(Module.PROJECTS, Level.WRITE)
def subproject_create(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a part to a whole project (PRJ-044, PRJ-045).

    The form offers what a part has of its own; customer and billing are
    shown as those of the whole project. Contact, venue, project manager
    and rental period start as the whole project's.
    """
    parent = project_for(request, pk, ProjectAccess.EDIT, queryset=Project.objects.select_related("customer"))
    if parent.parent_id:
        raise Http404
    initial = {
        "start": parent.start,
        "end": parent.end,
        "manager": parent.manager_id,
        "contact": parent.contact_id,
        "delivery_address": parent.delivery_address_id,
        "venue_site": parent.venue_site_id,
        "venue": parent.venue,
    }
    form = ProjectForm(request.POST or None, parent=parent, initial=initial, rights=request_rights(request))
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        template = data.pop("template", None)
        if "delivery_address" in form.fields and form.fields["delivery_address"].widget.is_hidden:
            data.pop("delivery_address", None)
        try:
            with transaction.atomic():
                part = services.create_subproject(parent, **data)
                if template is not None:
                    # PRJ-076: a part can start from a template as well – a stage, say.
                    applied = apply_template(template, part, rights=request_rights(request))
                    for text in sorted(set(applied.left_out)):
                        messages.warning(request, _("Left out from the template: %(what)s") % {"what": text})
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("Subproject %(number)s added.") % {"number": part.number})
            return redirect("projects:detail", pk=part.pk)
    return render(request, "projects/form.html", {"form": form, "project": None, "parent": parent})


@module_required(Module.PROJECTS)
def family_overview(request: HttpRequest, pk: int) -> HttpResponse:
    """The whole project with all its parts side by side and their sum (PRJ-046, PRJ-047).

    Reachable from the whole project and from every part. Parts the user
    may not read are left out of figures and sum; the page says how many.
    Prices only with the price right (AUT-019).
    """
    project = project_for(
        request, pk, ProjectAccess.READ, queryset=Project.objects.select_related("customer", "manager", "parent")
    )
    rights = request_rights(request)
    family = build_family(project, rights=rights, user=request.user)
    return render(
        request,
        "projects/family.html",
        {
            "project": project,
            "family": family,
            "can_see_prices": rights.has(SpecialRight.PRICES),
            "can_add": (
                project.parent_id is None
                and project.access >= ProjectAccess.EDIT
                and rights.can_write(Module.PROJECTS)
                and not project.is_locked
            ),
            "tab": "family",
        },
    )


@module_required(Module.PROJECTS, Level.WRITE)
def takeover(request: HttpRequest, pk: int) -> HttpResponse:
    """Take over material from another part of the same whole project (PRJ-060).

    GET shows the lines of the other parts that can be taken over; POST
    plans one of them in this project, with as many pieces as asked for.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    rights = request_rights(request)
    readable: dict[int, bool] = {}
    sources = []
    for line in takeover_sources(project):
        if line.project_id not in readable:
            # PRJ-049: only parts whose planning the user may read.
            readable[line.project_id] = access_level(rights, request.user, line.project) >= ProjectAccess.READ
        if readable[line.project_id]:
            sources.append(line)
    if request.method == "POST":
        source = next((line for line in sources if str(line.pk) == request.POST.get("source")), None)
        if source is None:
            raise Http404
        group = project.groups.filter(pk=request.POST.get("group") or 0).first()
        try:
            quantity = Decimal((request.POST.get("quantity") or "").replace(",", ".") or source.left_to_take_over)
        except InvalidOperation:
            quantity = Decimal("-1")
        try:
            if quantity <= 0:
                raise ValidationError(_("Enter how many pieces to take over."))
            result = services.take_over_line(source, project, rights=rights, quantity=quantity, group=group)
        except ValidationError as error:
            messages.error(request, _error_text(error))
            return _planning_response(request, project, close_dialog=True)
        messages.success(
            request,
            _("%(quantity)s × %(title)s taken over from %(number)s.")
            % {"quantity": result.line.quantity_display, "title": result.line.title, "number": source.project.number},
        )
        touched = Touched()
        touched.add(result.line)
        return _planning_response(request, project, close_dialog=True, touched=touched)
    return render(
        request,
        "projects/_takeover_dialog.html",
        {"project": project, "sources": sources, "groups": list(project.groups.all())},
    )
