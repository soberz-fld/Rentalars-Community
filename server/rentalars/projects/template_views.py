# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the project templates (PRJ-076): save a project as template, manage the templates."""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import ProjectTemplate
from rentalars.projects.project_templates import save_as_template
from rentalars.projects.template_tables import PROJECT_TEMPLATE_TABLE


class SaveTemplateForm(StyledForm):
    """Name and parts of a new template."""

    name = forms.CharField(label=gettext_lazy("Name of the template"), max_length=120)
    description = forms.CharField(
        label=gettext_lazy("Description"), required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    material = forms.BooleanField(label=gettext_lazy("Groups and material"), required=False, initial=True)
    # LOG-001: with the crew places the vehicle bookings, as open bookings.
    crew = forms.BooleanField(
        label=gettext_lazy("Crew places and vehicle bookings (open, without people and vehicles)"),
        required=False,
        initial=True,
    )
    course = forms.BooleanField(label=gettext_lazy("Schedule: phases and open items"), required=False, initial=True)
    replace = forms.BooleanField(
        label=gettext_lazy("Replace a template of the same name"), required=False, initial=False
    )


class TemplateForm(StyledModelForm):
    """Rename a template or change its description."""

    class Meta:
        model = ProjectTemplate
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


@module_required(Module.PROJECTS, Level.WRITE)
def template_create(request: HttpRequest, pk: int) -> HttpResponse:
    """Save this project as a template, in a dialog (PRJ-076)."""
    project = project_for(request, pk, ProjectAccess.READ)
    form = SaveTemplateForm(request.POST or None, initial={"name": project.name})
    saved = None
    if request.method == "POST" and form.is_valid():
        try:
            saved = save_as_template(
                project,
                name=form.cleaned_data["name"],
                description=form.cleaned_data["description"],
                rights=request_rights(request),
                user=request.user,
                material=form.cleaned_data["material"],
                crew=form.cleaned_data["crew"],
                course=form.cleaned_data["course"],
                replace=form.cleaned_data["replace"],
            )
        except ValidationError as error:
            form.add_error(None, error)
    page = "projects/_template_save.html" if request.headers.get("HX-Request") else "projects/template_save.html"
    return render(request, page, {"project": project, "form": form, "saved": saved})


@module_required(Module.PROJECTS, Level.WRITE)
def template_list(request: HttpRequest) -> HttpResponse:
    """All project templates (PRJ-076)."""
    templates = ProjectTemplate.objects.select_related("created_by")
    # UIX-040: a table of core.tables – columns, sorting, groups, CSV.
    table = PROJECT_TEMPLATE_TABLE.state(request)
    templates = table.order(templates)
    if table.wants_csv:
        return table.csv_response(templates, _("Project templates"))
    # UIX-050: paged like every list, as many per page as the user chose (UIX-012).
    page = table.paginate(templates)
    templates = list(page)
    return render(
        request,
        "projects/templates.html",
        {"templates": templates, "table": table, "rows": table.rows(page), "page": page},
    )


@module_required(Module.PROJECTS, Level.WRITE)
def template_edit(request: HttpRequest, template_pk: int) -> HttpResponse:
    """Rename a template or describe it."""
    template = get_object_or_404(ProjectTemplate, pk=template_pk)
    form = TemplateForm(request.POST or None, instance=template)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Template saved."))
        return redirect("projects:templates")
    return render(request, "projects/template_form.html", {"form": form, "template": template})


@require_POST
@module_required(Module.PROJECTS, Level.DELETE)
def template_delete(request: HttpRequest, template_pk: int) -> HttpResponse:
    """Delete a template; projects made from it stay as they are."""
    template = get_object_or_404(ProjectTemplate, pk=template_pk)
    template.delete()
    messages.success(request, _("Template “%(name)s” deleted.") % {"name": template.name})
    return redirect("projects:templates")
