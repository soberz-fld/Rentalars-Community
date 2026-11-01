# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views for the people of a project: crew lines, deployment view, members.

* The block "personnel" of the planning page (PRJ-019 ff., PRJ-038): adding,
  editing and deleting crew lines answer with the refreshed block, like the
  material lines do (UIX-009). A line can be planned for a
  phase, also straight from the page "Zeitplanung" (PRJ-080; function by function: PRJ-120,
  ``staffing_views``); a new phase can be created from the list of phases, in a dialog
  (PRJ-094, ``course_views.phase_dialog``). Several lines (PRJ-117) are
  chosen and changed at once (:func:`crew_bulk`, :func:`crew_bulk_edit`),
  and a person can be planned firmly, without request.
* The deployment view (AUT-018, AUT-023, AUT-025): what crew and freelancers
  see of a project – time, place, job function, colleagues – and nothing else.
* The members of a project (AUT-016): who is given access to this one project.

All of them call the same services as the API (API-002).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.redirects import safe_next_url
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects import crew
from rentalars.projects.access import (
    ProjectAccess,
    may_plan_crew,
    module_level_in,
    person_of,
    project_for,
)
from rentalars.projects.crew_bulk import CrewBulkAction, CrewBulkResult, change_crew_lines, crew_line_label
from rentalars.projects.crew_bulk_forms import CrewBulkForm
from rentalars.projects.discounts import crew_discount_warning
from rentalars.projects.files import files_for_crew
from rentalars.projects.forms import CrewAddForm, CrewLineForm, MembershipForm
from rentalars.projects.models import CrewLine, Project, ProjectMembership, RequestStatus
from rentalars.projects.views import Touched, _error_text, _planning_response


def _project_for_crew_planning(request: HttpRequest, pk: int) -> Project:
    """Load a project for somebody who wants to change its crew lines.

    Raises:
        PermissionDenied: The user neither edits the project nor plans personnel.
    """
    project = project_for(request, pk, ProjectAccess.READ)
    if not may_plan_crew(request_rights(request), project.access):
        raise PermissionDenied
    return project


def _crew_response(request: HttpRequest, project: Project, *, close_dialog: bool = False) -> HttpResponse:
    """Answer a change of the crew with the refreshed block "personnel" and the totals.

    PRJ-110: a change made on the page "Zeitplanung" (``from=course``)
    leads back there instead, with the messages – from the dialog by the page
    script, else by a redirect.
    """
    if from_course(request):
        return _back_to_course(request, project)
    return _planning_response(request, project, close_dialog=close_dialog, touched=Touched(crew=True))


#: PRJ-110: the parameter that marks a change of a crew line made on the page "Zeitplanung".
FROM_COURSE = "course"


def from_course(request: HttpRequest) -> bool:
    """Whether the change of a crew line comes from the page "Zeitplanung" (PRJ-110)."""
    return FROM_COURSE in (request.GET.get("from"), request.POST.get("from"))


def _back_to_course(request: HttpRequest, project: Project) -> HttpResponse:
    """Back to the phases on "Zeitplanung" after a change of a crew line made there (PRJ-110).

    From the dialog over "Zeitplanung" the page reloads where it is
    (``HX-Refresh``): a redirect to the same page with "#phases" would only
    move to the anchor, not load it. From the form on a page of its own –
    with or without the page script – it leads to "Zeitplanung".
    """
    return back_to_course(request, project, "phases")


def back_to_course(request: HttpRequest, project: Project, anchor: str) -> HttpResponse:
    """The answer after a change made from "Zeitplanung" (PRJ-110, PRJ-111) – see :func:`_back_to_course`."""
    target = reverse("projects:course", args=[project.pk])
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        current = urlsplit(request.headers.get("HX-Current-URL", "")).path
        if current == target:
            response["HX-Refresh"] = "true"
        else:
            response["HX-Redirect"] = f"{target}#{anchor}"
        return response
    return redirect(f"{target}#{anchor}")


def _tell_warnings(request: HttpRequest, line: CrewLine) -> None:
    """PRJ-022, PRJ-110: name at once what is wrong with the line – the check of the crew dialog."""
    if line.person_id is None:
        return
    for warning in crew.crew_warnings([line]).get(line.pk, []):
        messages.warning(request, f"{line.person}: {warning}")


def _add_lines(request: HttpRequest, project: Project, form: CrewAddForm) -> list[CrewLine]:
    """Plan what a valid add form says; tell the planner about conflicts at once (PRJ-022).

    Raises:
        ValidationError: The service refused, see ``crew.add_crew_lines``.
    """
    lines = crew.add_crew_lines(
        project,
        rights=request_rights(request),
        job_function=form.cleaned_data["job_function"],
        person=form.cleaned_data["person"],
        count=form.cleaned_data["count"],
        start=form.cleaned_data["start"],
        end=form.cleaned_data["end"],
        phase=form.cleaned_data.get("phase"),
        firm=bool(form.cleaned_data.get("firm")),  # PER-041: planned firmly, without request
    )
    for warning in {text for texts in crew.crew_warnings(lines).values() for text in texts}:
        # PRJ-022: planned all the same, but the planner is told at once.
        messages.warning(request, f"{lines[0].person}: {warning}")
    return lines


@require_POST
@module_required(Module.PROJECTS)
def crew_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Plan a person, or one or several open places, on a project (PRJ-019, PRJ-020) – for a phase (PRJ-080)."""
    project = _project_for_crew_planning(request, pk)
    form = CrewAddForm(request.POST, project=project)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return _crew_response(request, project)
    try:
        _add_lines(request, project, form)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _crew_response(request, project)


def tell_asked_again(request: HttpRequest, line: CrewLine) -> None:
    """PER-034: tell the planner that new times asked the person again – or that the answer is to be entered."""
    told = getattr(line, "asked_again", None)
    if told is None:
        return
    if told:
        messages.info(request, _("%(person)s was asked again for the new times.") % {"person": line.person})
    else:
        messages.info(
            request,
            _("The times changed: the line is “asked” again. Enter the answer of %(person)s when it comes.")
            % {"person": line.person},
        )


@module_required(Module.PROJECTS)
def crew_edit(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Edit a crew line in a dialog: person, period, hours, meeting point, price and cost.

    PRJ-110: the same dialog opens from the phases on "Zeitplanung"
    (``?from=course``) – to fill an open place with a person, change the
    person, job function or times. Saved, the page "Zeitplanung" shows the
    phase again and names the warnings of the line (PRJ-022) and whether the
    person was asked again (PER-034). Without the page script the dialog is
    a page of its own.
    """
    project = _project_for_crew_planning(request, pk)
    line = get_object_or_404(
        project.crew_lines.select_related("job_function", "person", "service_product", "tax_rate", "phase"), pk=line_pk
    )
    rights = request_rights(request)
    form = CrewLineForm(
        request.POST or None,
        line=line,
        rights=rights,
        # PRJ-094: "New phase …" in the list of phases, for whoever may edit the project.
        offer_new_phase=project.access >= ProjectAccess.EDIT and not project.is_locked,
    )
    if request.method == "POST" and form.is_valid():
        was_firm = line.request_status == RequestStatus.FIRM
        try:
            changes = form.changes()
            if changes:
                crew.update_crew_line(line, rights=rights, **changes)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            if "discount_percent" in changes and crew_discount_warning(line):
                messages.warning(request, crew_discount_warning(line))  # Cut to the maximum – and said
            tell_asked_again(request, line)
            if not was_firm and line.request_status == RequestStatus.FIRM:
                # PER-041, PRJ-118: told, not asked.
                messages.success(request, _("%(person)s is planned firmly and is told.") % {"person": line.person})
            if from_course(request):
                messages.success(request, _("Crew line saved."))
                _tell_warnings(request, line)
            return _crew_response(request, project, close_dialog=True)
    context = {
        "form": form,
        "line": line,
        "project": project,
        "action": request.get_full_path(),
        "back_to_course": from_course(request),
    }
    if from_course(request) and not request.headers.get("HX-Request"):
        # "Back" leads to the phases on "Zeitplanung", also when the page was opened directly.
        request.back_url = reverse("projects:course", args=[project.pk]) + "#phases"  # type: ignore[attr-defined]
        return render(request, "projects/crew_line_form.html", context)
    return render(request, "projects/_crew_form.html", context)


@require_POST
@module_required(Module.PROJECTS)
def crew_delete(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Delete a crew line."""
    project = _project_for_crew_planning(request, pk)
    line = get_object_or_404(project.crew_lines, pk=line_pk)
    try:
        crew.delete_crew_line(line)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        if from_course(request):
            messages.success(request, _("Crew line removed."))  # PRJ-110
    return _crew_response(request, project)


@require_POST
@module_required(Module.PROJECTS)
def crew_request(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Ask the planned person whether they take the deployment (PER-016)."""
    project = _project_for_crew_planning(request, pk)
    line = get_object_or_404(project.crew_lines.select_related("person"), pk=line_pk)
    try:
        notified = crew.request_deployment(line, user=request.user)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        if notified:
            messages.success(request, _("%(person)s was asked.") % {"person": line.person})
            from rentalars.mail.server import request_goes_by_mail, warn_without_server

            if request_goes_by_mail(line):
                warn_without_server(request)  # EML-048: the mail of the request went nowhere
        else:
            messages.info(
                request,
                _("%(person)s has no account; the line is marked as asked. Enter the answer when it comes.")
                % {"person": line.person},
            )
    return _crew_response(request, project)


@require_POST
def crew_answer(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Accept or decline a deployment: the person themselves, or a planner for them (PER-016)."""
    project = project_for(request, pk, ProjectAccess.DEPLOYMENT)
    line = get_object_or_404(project.crew_lines.select_related("person", "job_function"), pk=line_pk)
    viewer = person_of(request.user)
    is_own = viewer is not None and line.person_id == viewer.pk
    if not is_own and not may_plan_crew(request_rights(request), project.access):
        raise PermissionDenied
    try:
        crew.answer_deployment(
            line, accept=request.POST.get("answer") == "accept", note=request.POST.get("note", ""), user=request.user
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("The answer was passed on."))
        # PER-042: "available" entered where the own calendar said "not available".
        if available := crew.available_text(line, own=is_own):
            messages.info(request, available)
    if request.headers.get("HX-Request") and not is_own:
        return _crew_response(request, project)
    if target := safe_next_url(request):
        return redirect(target)
    return redirect("projects:deployment", pk=pk)


# --- Several crew lines at once (PRJ-117) ------------------------------------------------------------


def chosen_crew_line_ids(data: QueryDict) -> list[int]:
    """The IDs of the crew lines a request names in ``crew_lines`` (one value per line)."""
    return [int(value) for value in data.getlist("crew_lines") if str(value).strip().isdigit()]


def _bulk_response(request: HttpRequest, project: Project, *, close_dialog: bool = False) -> HttpResponse:
    """The planning after a change of several crew lines; without the page script the planning page itself."""
    if request.headers.get("HX-Request"):
        return _crew_response(request, project, close_dialog=close_dialog)
    return redirect(reverse("projects:detail", args=[project.pk]) + "#planning-crew")


def _success_text(result: CrewBulkResult) -> str:
    """The message about the lines changed, in the words of the action."""
    count = len(result.changed)
    if result.action == CrewBulkAction.FIRM:
        text = ngettext(
            "%(count)d crew line planned firmly; the person is told.",
            "%(count)d crew lines planned firmly; the people are told.",
            count,
        )
    elif result.action == CrewBulkAction.ASK:
        text = ngettext("%(count)d deployment request sent.", "%(count)d deployment requests sent.", count)
    elif result.action == CrewBulkAction.DELETE:
        text = ngettext("%(count)d crew line deleted.", "%(count)d crew lines deleted.", count)
    else:
        text = ngettext("%(count)d crew line changed.", "%(count)d crew lines changed.", count)
    return text % {"count": count}


def report_crew_bulk_result(request: HttpRequest, result: CrewBulkResult) -> None:
    """Tell what was done with the chosen crew lines, and name every line left as it was, with the reason."""
    if result.changed:
        messages.success(request, _success_text(result))
    elif not result.skipped:
        messages.info(request, _("Nothing to change: the chosen crew lines are like that already."))
    for warning in result.warnings:
        messages.warning(request, warning)  # A discount above the maximum of some job functions
    if result.not_told:
        messages.info(
            request,
            _("Without an account, marked as asked: %(people)s. Enter the answers when they come.")
            % {"people": ", ".join(line.person.name for line in result.not_told)},
        )
    if result.asked_again:
        messages.info(
            request,
            ngettext(
                "%(count)d person was asked again for the new times.",
                "%(count)d people were asked again for the new times.",
                len(result.asked_again),
            )
            % {"count": len(result.asked_again)},
        )
    if result.skipped:
        messages.warning(
            request,
            _("Left as they are: %(lines)s")
            % {"lines": "; ".join(f"{skipped.label} ({skipped.reason})" for skipped in result.skipped)},
        )


@require_POST
@module_required(Module.PROJECTS)
def crew_bulk(request: HttpRequest, pk: int) -> HttpResponse:
    """Plan firmly, ask or delete the crew lines chosen on the planning (PRJ-117).

    The bar "chosen crew lines" sends ``crew_lines`` (one value per line)
    and ``action`` – ``firm``, ``ask`` or ``delete``; "fest einplanen" of a
    single line sends the same with one line. Values are set in the dialog
    of :func:`crew_bulk_edit`. Works without the page script too: the answer
    is then the planning page.
    """
    project = _project_for_crew_planning(request, pk)
    action = request.POST.get("action", "")
    try:
        result = change_crew_lines(
            project, chosen_crew_line_ids(request.POST), action, rights=request_rights(request), user=request.user
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        report_crew_bulk_result(request, result)
        if action == CrewBulkAction.ASK and result.changed:
            from rentalars.mail.server import request_goes_by_mail, warn_without_server

            if any(request_goes_by_mail(line) for line in result.changed):
                warn_without_server(request)  # EML-048: the mails of the requests went nowhere
    return _bulk_response(request, project)


@module_required(Module.PROJECTS)
def crew_bulk_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Set meeting point, note, phase, period, hours or vehicle on the chosen crew lines (PRJ-117).

    Opens as a dialog over the planning with the chosen lines named in the
    address (``crew_lines``). Without the page script the button of the bar
    sends the chosen lines with ``step=choose`` (a POST: the bar is a form
    with its token), and the dialog is a page of its own. Saved, the
    planning shows the block "Personal" again.
    """
    project = _project_for_crew_planning(request, pk)
    data = request.POST if request.method == "POST" else request.GET
    lines = list(
        project.crew_lines.filter(pk__in=chosen_crew_line_ids(data))
        .select_related("job_function", "person")
        .order_by("start", "position", "id")
    )
    if not lines:
        messages.error(request, _("Choose at least one crew line."))
        return _bulk_response(request, project)
    rights = request_rights(request)
    sent = request.method == "POST" and request.POST.get("step") != "choose"
    form = CrewBulkForm(request.POST if sent else None, project=project, rights=rights)
    if sent and form.is_valid():
        try:
            result = change_crew_lines(
                project,
                [line.pk for line in lines],
                CrewBulkAction.EDIT,
                rights=rights,
                user=request.user,
                values=form.values(),
            )
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            report_crew_bulk_result(request, result)
            return _bulk_response(request, project, close_dialog=True)
    context = {
        "form": form,
        "project": project,
        "lines": lines,
        "labels": [crew_line_label(line) for line in lines],
        "action": reverse("projects:crew_bulk_edit", args=[project.pk]),
    }
    if request.headers.get("HX-Request"):
        return render(request, "projects/_crew_bulk_form.html", context)
    request.back_url = reverse("projects:detail", args=[project.pk]) + "#planning-crew"  # type: ignore[attr-defined]
    return render(request, "projects/crew_bulk_form.html", context)


@require_POST
@module_required(Module.PROJECTS)
def crew_times(request: HttpRequest, pk: int) -> HttpResponse:
    """Put approved times without crew line on a line, or make a line of them (ZEI-021)."""
    project = _project_for_crew_planning(request, pk)
    person = get_object_or_404(Person, pk=request.POST.get("person") or 0)
    job_function = get_object_or_404(JobFunction, pk=request.POST.get("job_function") or 0)
    target = request.POST.get("line", "")
    try:
        if target == "new":
            crew.adopt_times_as_line(project, person, job_function, rights=request_rights(request))
        else:
            line = get_object_or_404(project.crew_lines, pk=target or 0)
            crew.assign_times(project, person, job_function, line)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _crew_response(request, project)


# --- Deployment view (AUT-018, AUT-023, AUT-025) ---------------------------------------


@module_required(Module.PROJECTS)
def deployment(request: HttpRequest, pk: int) -> HttpResponse:
    """The deployment view of a project: when, where, as what, and with whom (AUT-025).

    This is all that crew and freelancers see of a project (AUT-023): the
    period, the venue, the contact on site, their own crew lines, the
    colleagues on the same job with the contact data those have released
    (PER-019), a link to the packlist, and their own times. No prices, no
    customer, no hourly rates of others.

    Users who may read the project see the same page as a crew sheet, with
    all contact data. PRJ-081: the page prints cleanly, and its PDF
    "Einsatzübersicht" (``documents.deployment``) shows the same for the same
    person; both take the data from ``projects.deployment``.
    """
    from rentalars.core.models import SystemSettings
    from rentalars.projects.deployment import deployment_picture

    project = project_for(
        request,
        pk,
        ProjectAccess.DEPLOYMENT,
        queryset=Project.objects.select_related("contact", "manager", "customer", "venue_site", "parent"),
    )
    rights = request_rights(request)
    picture = deployment_picture(project, rights=rights, user=request.user)
    viewer = picture.viewer
    return render(
        request,
        "projects/deployment.html",
        {
            "project": project,
            "tab": "deployment",
            "own_lines": picture.own_rows,
            "colleagues": picture.rows,
            "viewer": viewer,
            "own_entries": picture.own_entries,
            "own_expenses": picture.own_expenses,  # ZEI-019
            "show_own_rate": rights.has(SpecialRight.PERSONNEL_COSTS) or SystemSettings.load().people_see_own_rates,
            "can_see_packlist": module_level_in(rights, request.user, project, Module.PACKING) >= Level.READ,
            "can_record": viewer is not None and rights.can_write(Module.TIME_TRACKING),
            # PRJ-006, KND-009, PRJ-007: when and where, and the files meant for the crew.
            "phases": picture.phases,
            "crew_files": project.files.select_related("document_type")
            if project.access >= ProjectAccess.READ
            else files_for_crew(project),
        },
    )


# --- Members (AUT-016) ---------------------------------------------------------------------


@module_required(Module.PROJECTS)
def members(request: HttpRequest, pk: int) -> HttpResponse:
    """Who has access to this one project, and at which level (AUT-016, AUT-025).

    Lists the explicit members and, for information, the people who see the
    deployment view because they are planned in a crew line (AUT-018). Only
    users who edit the project may change the members.

    AUT-035: one list of everybody assigned – members, members of the
    whole project, the crew planned with an account ("eingeplant als
    Tontechnik"), the people of a service case – each with the access that
    really holds (``projects.access_rows``); only memberships are changed here.
    """
    project = project_for(
        request, pk, ProjectAccess.READ, queryset=Project.objects.select_related("customer", "parent")
    )
    can_edit = project.access >= ProjectAccess.EDIT
    form = MembershipForm(request.POST or None, project=project)
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            membership, _created = ProjectMembership.objects.get_or_create(
                project=project, user=form.cleaned_data["user"], defaults={"level": form.cleaned_data["level"]}
            )
            if membership.level != form.cleaned_data["level"]:
                membership.level = form.cleaned_data["level"]
                membership.save()
            messages.success(
                request, _("%(user)s now has access to this project.") % {"user": form.cleaned_data["user"]}
            )
            return redirect("projects:members", pk=project.pk)
    from rentalars.projects.access_rows import access_rows

    return render(
        request,
        "projects/members.html",
        {
            "project": project,
            "tab": "members",
            # AUT-035: members, crew and the people of a case in one list, with the access that holds.
            "rows": access_rows(project),
            "form": form,
            "can_edit_members": can_edit,
        },
    )


@require_POST
@module_required(Module.PROJECTS)
def member_remove(request: HttpRequest, pk: int, membership_pk: int) -> HttpResponse:
    """Take the access to this project away from a user (AUT-016)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    membership = get_object_or_404(project.memberships.select_related("user"), pk=membership_pk)
    membership.delete()
    messages.success(request, _("%(user)s no longer is a member of this project.") % {"user": membership.user})
    return redirect("projects:members", pk=project.pk)
