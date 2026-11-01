# SPDX-License-Identifier: GPL-3.0-or-later
"""The page "In Teilprojekte gliedern" (PRJ-050): which groups become subprojects, and where the crew goes."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import Level, Module, module_required
from rentalars.core.forms import StyledForm
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import Project
from rentalars.projects.split import SplitPlan, result_message, split_into_subprojects, split_plan

#: The value of the crew choice that keeps a line at the whole project.
STAYS = ""


class SplitForm(StyledForm):
    """Which top-level groups become subprojects, and where each crew line goes (PRJ-050).

    The fields follow the plan (``projects.split.split_plan``): a checkbox per
    group that can become a subproject, a choice per crew line – it stays at
    the whole project or goes with one of those groups.
    """

    def __init__(self, *args: Any, plan: SplitPlan, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.plan = plan
        possible = [option for option in plan.groups if option.possible]
        self.fields["groups"] = forms.MultipleChoiceField(
            label=gettext_lazy("Groups that become subprojects"),
            choices=[(str(option.group.pk), option.group.name) for option in possible],
            widget=forms.CheckboxSelectMultiple,
            error_messages={"required": gettext_lazy("Choose at least one group.")},
        )
        crew_choices = [(STAYS, _("stays at the whole project"))] + [
            (str(option.group.pk), _("goes with “%(name)s”") % {"name": option.group.name}) for option in possible
        ]
        for line in plan.crew_lines:
            self.fields[f"crew_{line.pk}"] = forms.ChoiceField(label=str(line), choices=crew_choices, required=False)

    def crew_rows(self) -> list[tuple[Any, forms.BoundField]]:
        """Each crew line with its choice, for the template."""
        return [(line, self[f"crew_{line.pk}"]) for line in self.plan.crew_lines]

    def clean(self) -> dict[str, Any]:
        """A crew line can only go with a group that becomes a subproject."""
        data = super().clean()
        groups = set(data.get("groups") or [])
        for line in self.plan.crew_lines:
            value = data.get(f"crew_{line.pk}") or STAYS
            if value != STAYS and value not in groups:
                self.add_error(f"crew_{line.pk}", _("This group does not become a subproject."))
        return data

    def chosen(self) -> tuple[list[int], dict[int, int]]:
        """The groups chosen and, per crew line that goes along, its group."""
        groups = [int(value) for value in self.cleaned_data["groups"]]
        crew: dict[int, int] = {}
        for line in self.plan.crew_lines:
            value = self.cleaned_data.get(f"crew_{line.pk}") or STAYS
            if value != STAYS:
                crew[line.pk] = int(value)
        return groups, crew


@module_required(Module.PROJECTS, Level.WRITE)
def split(request: HttpRequest, pk: Any) -> HttpResponse:
    """In Teilprojekte gliedern – or, on a whole project, turn further groups into subprojects (PRJ-050).

    GET shows what would happen: the top-level groups – with what goes along
    and why one cannot go –, the crew lines with their choice, and what to
    know before. ``?group=`` ticks one group. POST does it and leads to the
    overview of the parts.
    """
    project = project_for(request, pk, ProjectAccess.EDIT, queryset=Project.objects.select_related("parent"))
    plan = split_plan(project)
    initial = {"groups": [request.GET["group"]]} if request.GET.get("group", "").isdigit() else {}
    form = SplitForm(request.POST if request.method == "POST" else None, plan=plan, initial=initial)
    if request.method == "POST" and plan.possible and form.is_valid():
        groups, crew = form.chosen()
        try:
            result = split_into_subprojects(project, groups, crew, user=request.user)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, result_message(result))
            for warning in result.warnings:
                messages.warning(request, warning)
            return redirect("projects:family", pk=project.pk)
    return render(
        request,
        "projects/split.html",
        {"project": project, "plan": plan, "form": form, "is_whole": project.has_subprojects},
    )
