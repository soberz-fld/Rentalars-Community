# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of personnel for a phase, function by function (PRJ-120; PRJ-080, PRJ-110).

"Personal für diese Phase" on the page "Zeitplanung" opens :func:`phase_staffing`
as a dialog over the page – or, without the page script, as a page of its own:

1. the job functions with their places – rows that "Weitere Funktion" and
   "Entfernen" add and remove; the open places of the phase are filled in;
2. one field per place for the person – in the dialog a type-ahead of the
   people with the job function (:func:`phase_people`), each with what the
   crew warnings would say at the period of the phase; without the script a
   list of them, shown after "Weiter zu den Personen". With the script the
   places follow the rows at once, as the serial numbers of "Neue Exemplare"
   follow the number of items.

"Einplanen" plans them with the period of the phase (``projects.staffing``)
and leads back to "Zeitplanung", telling the warnings at once (PRJ-022) as
the crew add form does.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects import crew, staffing
from rentalars.projects.crew_views import _project_for_crew_planning, back_to_course
from rentalars.projects.forms import people_choices
from rentalars.projects.staffing_forms import PhaseStaffingForm, edited_rows

#: How many people the type-ahead of a place suggests.
SUGGESTED_PEOPLE = 20


def _tell(request: HttpRequest, lines: list) -> None:
    """What was planned, and the warnings of the people at once (PRJ-022) – as the crew add form tells them."""
    staffed = [line for line in lines if line.person_id is not None]
    open_places = len(lines) - len(staffed)
    if staffed:
        messages.success(
            request,
            ngettext("%(count)d person planned.", "%(count)d people planned.", len(staffed)) % {"count": len(staffed)},
        )
    if open_places:
        messages.info(
            request,
            ngettext("%(count)d place is open.", "%(count)d places are open.", open_places) % {"count": open_places},
        )
    warnings = crew.crew_warnings(staffed)
    for line in staffed:
        for warning in warnings.get(line.pk, []):
            messages.warning(request, f"{line.person}: {warning}")


@module_required(Module.PROJECTS)
def phase_staffing(request: HttpRequest, pk: int, phase_pk: int) -> HttpResponse:
    """Plan personnel for one phase: job functions with places, then the people (PRJ-120).

    ``POST`` with ``add_row`` or ``remove_row`` answers with one row more or
    less, with ``refresh`` (the page script, after a row changed) or ``step``
    ("Weiter zu den Personen") with the places of the rows; only ``save``
    ("Einplanen") plans. Whoever may not plan the crew of the project gets
    "not allowed" (``crew_views._project_for_crew_planning``).
    """
    project = _project_for_crew_planning(request, pk)
    phase = get_object_or_404(project.phases.select_related("project"), pk=phase_pk)
    may_plan_any = request_rights(request).has(SpecialRight.PLAN_ANY_JOB_FUNCTION)
    in_dialog = bool(request.headers.get("HX-Request"))
    if request.method != "POST":
        form = PhaseStaffingForm(phase=phase, may_plan_any=may_plan_any, initial_rows=staffing.open_rows(phase))
    else:
        remove = request.POST.get("remove_row", "")
        add = "add_row" in request.POST
        if add or remove.isdigit():
            data = edited_rows(request.POST, add=add, remove=int(remove) if remove.isdigit() else None)
            form = PhaseStaffingForm(data, phase=phase, may_plan_any=may_plan_any).without_errors()
        elif "save" not in request.POST:
            form = PhaseStaffingForm(request.POST, phase=phase, may_plan_any=may_plan_any)
            if "step" not in request.POST:
                form.without_errors()  # the page script asks for the places of the rows: nothing is wrong yet
            else:
                form.is_valid()  # "Weiter zu den Personen": what is wrong with the rows is said now
        else:
            form = PhaseStaffingForm(request.POST, phase=phase, may_plan_any=may_plan_any)
            if form.is_valid():
                try:
                    lines = staffing.staff_phase(
                        phase, form.staffed_rows(), rights=request_rights(request), firm=form.cleaned_data["firm"]
                    )
                except ValidationError as error:
                    add_validation_error(form, error)
                else:
                    _tell(request, lines)
                    # Over "Zeitplanung" the page loads again where it is; a redirect to "#phases" would only scroll.
                    return back_to_course(request, project, "phases")
    context = {
        "form": form,
        "project": project,
        "phase": phase,
        "action": reverse("projects:phase_crew_add", args=[project.pk, phase.pk]),
        # The places are type-ahead fields in the dialog, lists on the page without the page script.
        "typeahead": in_dialog,
        "people_url": reverse("projects:phase_people", args=[project.pk, phase.pk]),
    }
    if in_dialog:
        return render(request, "projects/_phase_crew_form.html", context)
    return render(request, "projects/phase_crew_form.html", context)


@require_GET
@module_required(Module.PROJECTS)
def phase_people(request: HttpRequest, pk: int, phase_pk: int) -> JsonResponse:
    """The people for a place while typing: those with the job function, with the crew warnings at the phase's period.

    ``function`` names the job function, ``q`` what was typed. With the right to
    plan outside the job functions the others follow, as in the crew forms
    (PER-025). The answer is that of every type-ahead field; ``hint`` is what
    the warnings say (PRJ-022), else "no conflict".
    """
    project = _project_for_crew_planning(request, pk)
    phase = get_object_or_404(project.phases, pk=phase_pk)
    value = request.GET.get("function", "")
    function = JobFunction.objects.filter(is_active=True, pk=int(value)).first() if value.isdigit() else None
    text = request.GET.get("q", "").strip()
    if function is None or not text:
        return JsonResponse([], safe=False)
    may_plan_any = request_rights(request).has(SpecialRight.PLAN_ANY_JOB_FUNCTION)
    choices, _functions_of = people_choices(function, include_others=may_plan_any)
    allowed = [pk for pk, _label in choices]
    found = set(
        Person.objects.filter(pk__in=allowed)
        .filter(Q(first_name__icontains=text) | Q(last_name__icontains=text))
        .values_list("pk", flat=True)
    )
    people = list(Person.objects.filter(pk__in=found))
    hints = staffing.person_hints(phase, function, people)
    return JsonResponse(
        [{"id": pk, "label": label, "hint": hints.get(pk) or _("no conflict")} for pk, label in choices if pk in found][
            :SUGGESTED_PEOPLE
        ],
        safe=False,
    )
