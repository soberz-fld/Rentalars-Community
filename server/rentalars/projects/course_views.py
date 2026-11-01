# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views for the schedule of a project ("Zeitplanung"): phases, open items, files, duplicating.

PRJ-006 phases – with their crew (PRJ-080), also
created in a dialog from the crew planning (PRJ-094); a
phase beyond the rental period asks whether to extend it (PRJ-100) –, PRJ-059 open
items with their overview, PRJ-007 files, PRJ-029 duplicating. The page
shows a timeline of the project (PRJ-103, ``schedule.course_timeline``). The work is done in ``projects.course``,
``projects.files`` and ``projects.duplicate``, which the API calls as well
(API-002).
"""

from __future__ import annotations

import datetime
import json
from typing import Any
from urllib.parse import urlsplit

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.forms import DATETIME_FORMAT, add_validation_error
from rentalars.core.i18n import local_pattern
from rentalars.core.redirects import safe_next_url
from rentalars.core.uploads import document_response
from rentalars.notifications.services import project_changed
from rentalars.personnel.models import AvailabilityState
from rentalars.projects import course, files, staffing
from rentalars.projects.access import ProjectAccess, access_level, may_plan_crew, project_for, readable_projects
from rentalars.projects.case_work import case_work_required
from rentalars.projects.crew import crew_warnings
from rentalars.projects.crew_views import tell_asked_again
from rentalars.projects.duplicate import copy_project
from rentalars.projects.forms import (
    DuplicateForm,
    OpenItemsForm,
    PhaseForm,
    ProjectFileEditForm,
    ProjectFileForm,
    phase_label,
)
from rentalars.projects.models import OpenItem, Project, ProjectFile, ProjectPhase, ProjectStatus
from rentalars.projects.planning import build_planning
from rentalars.projects.staffing_forms import PhaseWithPlacesForm, edited_rows
from rentalars.schedule import course_timeline


def _messages_of(error: ValidationError) -> str:
    return " ".join(error.messages)


def _can_edit(project: Project) -> bool:
    return project.access >= ProjectAccess.EDIT and not project.is_locked


# --- Course: timeline, phases, open items (PRJ-006, PRJ-059, PRJ-103) ---------------------------


@module_required(Module.PROJECTS)
def course_page(request: HttpRequest, pk: int) -> HttpResponse:
    """The schedule ("Zeitplanung") of a project: its timeline, the phases with their crew, and what is still open.

    PRJ-080: under each phase the crew lines that belong to it – job
    function, person or "open", the period where it differs from the
    phase's, the hours – and, for whoever may plan crew, a button to plan
    personnel for the phase. Crew lines without phase follow under "Without
    phase". The page needs read access, with which the planning shows the
    crew as well; crew who only have the deployment view see the phases
    there, as before.

    PRJ-103: above the phases a timeline of the project – rental
    period, event, phases, crew by person – in hours or days, opened on the
    rental period. PRJ-102: the venue box is gone; the venue stays in the
    head of the project and in its form.

    The crew on the timeline as in the personnel plan – colours,
    exact times, conflicts filled red, availability for whoever reads the
    personnel (VFG-035). The crew lines of a phase can be changed, asked
    and removed from here as in the planning; each names its warnings
    (PRJ-110). The trips can be changed, removed and added (PRJ-111).
    """
    project = project_for(
        request, pk, ProjectAccess.READ, queryset=Project.objects.select_related("venue_site", "customer", "manager")
    )
    if project.is_service_case:
        # PRJ-090: a service case has no schedule; its open items are on its page.
        return redirect(reverse("projects:case_detail", args=[project]) + "#open-items")
    can_edit = _can_edit(project)
    phases = list(project.phases.select_related("venue_site"))
    phase_crew, without_phase = course.crew_by_phase(project, phases)
    # PRJ-103: the timeline of the project, from the phases and crew lines just loaded – no further query.
    scale, navigation = course_timeline.course_scale(request, project)
    crew_lines = [line for entry in phase_crew for line in entry.lines] + without_phase.lines
    reads_personnel = request_rights(request).can_read(Module.PERSONNEL)
    timeline_rows = course_timeline.course_rows(
        project,
        phases,
        crew_lines,
        scale,
        link_people=reads_personnel,
        movable=can_edit,  # VFG-026: rental period, event and phases dragged to other times
        # VFG-035: conflicts and – for whoever reads the personnel – availability, as in the personnel plan.
        crew=course_timeline.crew_picture(crew_lines, scale, with_availability=reads_personnel),
    )
    can_plan_crew = may_plan_crew(request_rights(request), project.access) and not project.is_locked
    # PRJ-110: the warnings of the crew dialog (PRJ-022) at each line of a phase, for whoever plans the crew.
    crew_line_warnings = crew_warnings(crew_lines) if can_plan_crew else {}
    for line in crew_lines:
        line.warnings = crew_line_warnings.get(line.pk, [])
    # PRJ-100: the phase just saved lies beyond the rental period – ask whether to extend it.
    extension = None
    asked = request.GET.get("extend", "")
    if can_edit and asked.isdigit():
        phase = next((phase for phase in phases if phase.pk == int(asked)), None)
        extension = course.rental_period_suggestion(phase, project) if phase is not None else None
    return render(
        request,
        "projects/course.html",
        {
            "project": project,
            "tab": "course",
            "can_edit": can_edit,
            "phases": phases,
            "phase_crew": phase_crew,
            "crew_without_phase": without_phase,
            "can_plan_crew": can_plan_crew,
            "open_items": project.open_items.select_related("done_by"),
            "phase_form": PhaseForm(initial=dict(zip(("start", "end"), course.first_guess(project), strict=True)))
            if can_edit
            else None,
            "items_form": OpenItemsForm() if can_edit else None,
            "suggest_confirmation": course.suggests_confirmation(project),
            "needs_items": project.status == ProjectStatus.CONFIRMED_OPEN and not project.open_items.exists(),
            "extension": extension,
            "scale": scale,
            "days": scale.days,
            "timeline_rows": timeline_rows,
            "crew_legend": course_timeline.crew_legend(project),
            # VFG-035: the availability is shown – and explained – for whoever reads the personnel.
            "availability_legend": AvailabilityState.choices
            if reads_personnel and any(line.person_id for line in crew_lines)
            else [],
            "timeline_movable": can_edit and scale.is_hourly,  # VFG-026
            **navigation,
        },
    )


@module_required(Module.PROJECTS, Level.WRITE)
def phase_edit(request: HttpRequest, pk: int, phase_pk: int | None = None) -> HttpResponse:
    """Add or change a phase (PRJ-006); its crew moves along if the box says so (PRJ-080).

    PRJ-100: a saved phase beyond the rental period leads to the page
    "Zeitplanung" with the question whether to extend the rental period.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    phase = get_object_or_404(ProjectPhase, pk=phase_pk, project=project) if phase_pk else None
    if phase is None:  # PRJ-116: after the latest phase, on one day – see course.first_guess
        start, end = course.first_guess(project)
        phase_or_new = ProjectPhase(project=project, start=start, end=end)
    else:
        phase_or_new = phase
    # PRJ-120: a new phase names job functions with places – "Weitere Funktion" and "Entfernen" send the
    # form back for one row more or less, without saving.
    if phase is None:
        form, edited = _phase_form(request, phase_or_new)
    else:
        form, edited = PhaseForm(request.POST or None, instance=phase_or_new), False
    if request.method == "POST" and not edited and form.is_valid():
        fields = {name: form.cleaned_data[name] for name in course.PHASE_FIELDS}
        try:
            if phase is None:
                saved, places = staffing.add_phase_with_places(
                    project, form.chosen_rows(), rights=request_rights(request), **fields
                )
                moved = []
                _tell_places(request, places)
            else:
                change = course.update_phase(phase, move_crew=form.cleaned_data.get("move_crew", False), **fields)
                saved, moved = change.phase, change.moved_crew_lines
                if change.moved_vehicle_lines:  # LOG-001
                    messages.info(
                        request,
                        ngettext(
                            "%(count)d vehicle booking moved along with the phase.",
                            "%(count)d vehicle bookings moved along with the phase.",
                            len(change.moved_vehicle_lines),
                        )
                        % {"count": len(change.moved_vehicle_lines)},
                    )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("Phase saved."))
            if moved:
                messages.info(
                    request,
                    ngettext(
                        "%(count)d crew line moved along with the phase.",
                        "%(count)d crew lines moved along with the phase.",
                        len(moved),
                    )
                    % {"count": len(moved)},
                )
                # PRJ-022: the moved lines are checked again, as after any change of the crew.
                warnings = crew_warnings(moved)
                for line in moved:
                    for warning in warnings.get(line.pk, []):
                        messages.warning(request, f"{line.person}: {warning}")
                    # PER-034: who was asked again for the new times of the phase.
                    tell_asked_again(request, line)
            if course.rental_period_suggestion(saved, project) is not None:
                return redirect(f"{reverse('projects:course', kwargs={'pk': project.pk})}?extend={saved.pk}")
            return redirect("projects:course", pk=project.pk)
    return render(request, "projects/phase_form.html", {"project": project, "phase": phase, "form": form})


def _phase_form(request: HttpRequest, phase: ProjectPhase, **options: Any) -> tuple[PhaseWithPlacesForm, bool]:
    """The form of a new phase with rows "Funktion + Plätze" (PRJ-120).

    Returns the form and whether it came back only for one row more or less
    ("Weitere Funktion", "Entfernen") – then nothing is saved and no error shown.
    """
    if request.method != "POST":
        return PhaseWithPlacesForm(instance=phase, **options), False
    remove = request.POST.get("remove_row", "")
    if "add_row" in request.POST or remove.isdigit():
        data = edited_rows(
            request.POST, add="add_row" in request.POST, remove=int(remove) if remove.isdigit() else None
        )
        return PhaseWithPlacesForm(data, instance=phase, **options).without_errors(), True
    return PhaseWithPlacesForm(request.POST, instance=phase, **options), False


def _over_planning(request: HttpRequest, project: Project) -> bool:
    """Whether the dialog stands over the planning page of the project (the page the request came from)."""
    path = urlsplit(request.headers.get("HX-Current-URL", "")).path
    try:
        match = resolve(path)
    except Resolver404:
        return False
    return match.view_name == "projects:detail" and str(match.kwargs.get("pk")) == str(project.pk)


def _planning_places_part(request: HttpRequest, project: Project) -> str:
    """PRJ-120: the crew lines and the totals of the planning, out of band.

    Only the lines (``_planning_crew_lines.html``), not the crew add form below
    them: it opened the dialog "Neue Phase …" and keeps what was typed (PRJ-094).
    The same parts the patch of a crew change sends (``views._planning_response``).
    """
    from rentalars.projects.views import _planning_context

    return render_to_string("projects/_phase_places_oob.html", _planning_context(request, project), request=request)


def _tell_places(request: HttpRequest, lines: list[Any]) -> None:
    """PRJ-120: how many open places the new phase brought."""
    if lines:
        messages.info(
            request,
            ngettext(
                "%(count)d open place planned in the phase.", "%(count)d open places planned in the phase.", len(lines)
            )
            % {"count": len(lines)},
        )


def _period_text(start: datetime.datetime, end: datetime.datetime) -> str:
    """A period as the pages show it: "Fr 23.10. 14:00 – Di 27.10. 18:00"."""
    return " – ".join(date_format(timezone.localtime(moment), local_pattern("D d.m. H:i")) for moment in (start, end))


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def phase_extend_period(request: HttpRequest, pk: int, phase_pk: int) -> HttpResponse:
    """Extend the rental period to cover a phase – the answer "Extend" to the question after saving it (PRJ-100).

    The period changes as in the project form: with its checks, the change
    log and the message to the people of the project (UIX-005). If the
    longer period leaves the project short of material, a warning says so.
    From the dialog over the crew planning (PRJ-094) the answer stays in the
    dialog; the page then offers to show the new periods.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    phase = get_object_or_404(ProjectPhase, pk=phase_pk, project=project)
    in_dialog = bool(request.headers.get("HX-Request"))
    shortage_before = build_planning(project).shortage_total
    errors: list[str] = []
    notes: list[tuple[str, str]] = []
    try:
        extended = course.extend_rental_period(phase, project)
    except ValidationError as error:
        errors.append(_messages_of(error))
    else:
        if extended is None:
            notes.append(("info", _("The rental period already covers the phase.")))
        else:
            period = _period_text(project.start, project.end)
            notes.append(("success", _("Rental period extended: %(period)s.") % {"period": period}))
            project_changed(
                project,
                _("new period %(start)s – %(end)s")
                % {
                    "start": timezone.localtime(project.start).strftime(local_pattern("%d.%m. %H:%M")),
                    "end": timezone.localtime(project.end).strftime(local_pattern("%d.%m. %H:%M")),
                },
                actor=request.user,
                crew_too=True,
            )
            shortage = build_planning(project).shortage_total
            # AUT-032: the warning for who may see the availability of material.
            if shortage > shortage_before and request_rights(request).has(SpecialRight.AVAILABILITY):
                notes.append(
                    (
                        "warning",
                        ngettext(
                            "With the new rental period %(count)d piece is missing. See the lines marked in red.",
                            "With the new rental period %(count)d pieces are missing. See the lines marked in red.",
                            shortage,
                        )
                        % {"count": shortage},
                    )
                )
    if in_dialog:
        response = render(
            request,
            "projects/_phase_extend_done.html",
            {"project": project, "errors": errors, "notes": notes},
        )
        if not errors:
            # The planning underneath still shows the former periods; the page offers to show the new ones.
            response["HX-Trigger"] = "rentalPeriodChanged"
        return response
    for text in errors:
        messages.error(request, text)
    for level, text in notes:
        getattr(messages, level)(request, text)
    return redirect("projects:course", pk=project.pk)


def _moment(value: str) -> datetime.datetime | None:
    """A moment from the address ("2027-03-10T08:00"), or ``None`` for anything else."""
    try:
        parsed = parse_datetime(value or "")
    except ValueError:  # well-formed, but no such day ("2027-02-30T10:00")
        return None
    if parsed is None:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


@module_required(Module.PROJECTS, Level.WRITE)
def phase_dialog(request: HttpRequest, pk: int) -> HttpResponse:
    """A new phase in a dialog over the crew planning (PRJ-094).

    The list of phases in the crew forms of the planning offers "New phase …"
    – the page script adds it for whoever may edit the project. It opens this
    form: kind, label, period and place, as on the page "Zeitplanung". The
    period starts as the one typed in the crew form (``?start=&end=``), else
    as the project's. Saved, the answer closes the dialog and names the new
    phase (``phaseCreated``); the script puts it into the lists and chooses
    it, and the crew form keeps what was typed. PRJ-100: a phase beyond the
    rental period keeps the dialog open with the question whether to extend
    the rental period (``keepDialog``), answered by :func:`phase_extend_period`.

    Without the page script the entry is not offered; whoever reaches the
    address all the same is led to the page for a new phase.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    if not request.headers.get("HX-Request"):
        return redirect("projects:phase_create", pk=project.pk)
    # PRJ-116: the period typed in the form if it differs from the rental period, on one day.
    start, end = course.first_guess(project, _moment(request.GET.get("start", "")), _moment(request.GET.get("end", "")))
    # IDs of their own: the dialog can stand over the dialog of a crew line, with fields of the same names.
    # PRJ-120: with rows "Funktion + Plätze", as on the page.
    form, edited = _phase_form(request, ProjectPhase(project=project, start=start, end=end), auto_id="new-phase-%s")
    form.fields.pop("notes")
    if request.method == "POST" and not edited and form.is_valid():
        try:
            phase, _places = staffing.add_phase_with_places(
                project,
                form.chosen_rows(),
                rights=request_rights(request),
                **{name: form.cleaned_data[name] for name in course.PHASE_FIELDS if name in form.cleaned_data},
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            created = {
                "id": phase.pk,
                "label": phase_label(phase),
                "start": timezone.localtime(phase.start).strftime(DATETIME_FORMAT),
                "end": timezone.localtime(phase.end).strftime(DATETIME_FORMAT),
            }
            # PRJ-100: beyond the rental period the dialog stays open and asks whether to extend it.
            extension = course.rental_period_suggestion(phase, project)
            # PRJ-120: places of the new phase show at once in the planning underneath (out of band).
            places = _planning_places_part(request, project) if _places and _over_planning(request, project) else ""
            events: dict[str, Any] = {"phaseCreated": created}
            if extension is not None:
                created["keepDialog"] = True
                response = render(
                    request, "projects/_phase_extend_question.html", {"project": project, "extension": extension}
                )
                response.content += places.encode()
            elif places:
                # The dialog closes ("phaseCreated"); only the parts out of band are put in place. Retargeted, so that
                # the dialog does not hear of a swap – it would open again (app.js, PRJ-094).
                response = HttpResponse(places)
                response["HX-Retarget"] = "#planning-crew-lines"
                response["HX-Reswap"] = "none"
            else:
                response = HttpResponse(status=204)
            if places:
                events["planningChanged"] = True  # the hints above the planning follow (_planning_notes.html)
            response["HX-Trigger"] = json.dumps(events)
            return response
    form.fields["kind"].widget.attrs["autofocus"] = True
    return render(
        request, "projects/_phase_dialog.html", {"project": project, "form": form, "action": request.get_full_path()}
    )


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def phase_delete(request: HttpRequest, pk: int, phase_pk: int) -> HttpResponse:
    """Remove a phase."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        course.delete_phase(get_object_or_404(ProjectPhase, pk=phase_pk, project=project))
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    else:
        messages.success(request, _("Phase removed."))
    return redirect("projects:course", pk=pk)


def _items_back(project: Project) -> HttpResponse:
    """Back to the open items: the schedule of a project, the page of a service case (AUT-033; PRJ-090)."""
    if project.is_service_case:
        return redirect(reverse("projects:case_detail", args=[project]) + "#open-items")
    return redirect("projects:course", pk=project.pk)


@require_POST
@case_work_required(Level.WRITE)
def open_items_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Note one or more open items (PRJ-059); AUT-033: of a service case also those working on it (PRJ-108)."""
    project = project_for(request, pk, ProjectAccess.EDIT, case_work=True)
    form = OpenItemsForm(request.POST)
    if form.is_valid():
        try:
            items = course.add_open_items(project, form.items())
        except ValidationError as error:
            messages.error(request, _messages_of(error))
        else:
            messages.success(
                request,
                ngettext("%(count)d open item noted.", "%(count)d open items noted.", len(items))
                % {"count": len(items)},
            )
    else:
        messages.error(request, _("Enter what is still open."))
    return _items_back(project)


@require_POST
@case_work_required(Level.WRITE)
def open_item_toggle(request: HttpRequest, pk: int, item_pk: int) -> HttpResponse:
    """Tick an open item as done – or untick it; AUT-033: see :func:`open_items_add`."""
    project = project_for(request, pk, ProjectAccess.EDIT, case_work=True)
    item = get_object_or_404(OpenItem, pk=item_pk, project=project)
    try:
        course.set_open_item_done(item, done=request.POST.get("done") == "1", user=request.user)
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    if course.suggests_confirmation(project):
        messages.info(request, _("All open items are done. The project can now be set to “Confirmed”."))
    if target := safe_next_url(request):
        return redirect(target)
    return _items_back(project)


@require_POST
@case_work_required(Level.WRITE)
def open_item_delete(request: HttpRequest, pk: int, item_pk: int) -> HttpResponse:
    """Remove an open item noted by mistake; AUT-033: see :func:`open_items_add`."""
    project = project_for(request, pk, ProjectAccess.EDIT, case_work=True)
    try:
        course.delete_open_item(get_object_or_404(OpenItem, pk=item_pk, project=project))
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    return _items_back(project)


@module_required(Module.PROJECTS)
def open_items_overview(request: HttpRequest) -> HttpResponse:
    """All projects with open items (PRJ-059, scenario 20) – and their shortages not resolved yet (PRJ-098).

    PRJ-098: the open shortages of a project stand among its open items as
    further points, each leading to its line in the planning. They are those
    of the shortages page – the same calculation (``open_shortages``), once
    for all projects, not per project –, so a project lacking material is
    listed even without open items. Both cover the projects whose planning
    the user may read.
    """
    from rentalars.accounts.rights import require
    from rentalars.availability.services import open_shortages

    rights = request_rights(request)
    # AUT-031 (Crew): the page sums up the planning – nothing for a role with the overview only.
    require(rights.reads_planning)
    readable = readable_projects(rights, request.user)
    projects = list(course.projects_with_open_items(readable).prefetch_related("open_items"))
    shortages: dict[int, list[Any]] = {}
    # AUT-032: the shortages among the open items only with the right to see availability.
    for shortage in open_shortages(projects=readable) if rights.has(SpecialRight.AVAILABILITY) else []:
        shortages.setdefault(shortage.project.pk, []).append(shortage)
    listed = {project.pk for project in projects}
    if set(shortages) - listed:
        projects += readable.filter(pk__in=set(shortages) - listed).select_related("customer", "manager", "parent")
        projects.sort(key=lambda project: (project.start, project.number))
    rows: list[dict[str, Any]] = []
    for project in projects:
        items = project.open_items.all() if project.pk in listed else []
        rows.append(
            {
                "project": project,
                "items": [item for item in items if not item.is_done],
                "shortages": shortages.get(project.pk, []),
                "suggest_confirmation": project.status == ProjectStatus.CONFIRMED_OPEN
                and getattr(project, "open_count", 0) == 0
                and getattr(project, "done_count", 0) > 0,
            }
        )
    # UIX-040: columns, sorting, groups and CSV (projects/open_item_tables.py).
    from rentalars.projects.open_item_tables import OPEN_ITEMS_TABLE

    table = OPEN_ITEMS_TABLE.state(request)
    rows = table.order(rows)
    if table.wants_csv:
        return table.csv_response(rows, _("Open items"))
    page = table.paginate(rows)  # UIX-050 (UIX-012)
    return render(
        request,
        "projects/open_items.html",
        {"rows": rows, "table": table, "table_rows": table.rows(page), "page": page, "tab": "open_items"},
    )


# --- Files (PRJ-007) -----------------------------------------------------------------------------


def files_of(project: Project) -> QuerySet[ProjectFile]:
    """The files of a project as the tab "Documents" lists them (PRJ-007, PRJ-079)."""
    # PRJ-106: a document of a supplier of subrentals names its supplier.
    return project.files.select_related("document_type", "uploaded_by", "source_attachment__mail", "supplier")


def new_file_form(project: Project) -> ProjectFileForm | None:
    """An empty upload form – for whoever may change the project (PRJ-007)."""
    return ProjectFileForm() if _can_edit(project) else None


def _files_url(pk: int) -> str:
    """The files are on the tab "Documents" (PRJ-079)."""
    return reverse("documents:list", args=[pk]) + "#files"


@module_required(Module.PROJECTS)
def files_page(request: HttpRequest, pk: int) -> HttpResponse:
    """Upload a file to a project (PRJ-007); the files themselves are on the tab "Documents" (PRJ-079).

    The address stays: links and bookmarks to the former tab "Files" lead to
    the files on the tab "Documents".
    """
    project = project_for(request, pk, ProjectAccess.READ)
    if request.method != "POST":
        return redirect(_files_url(pk))
    if not _can_edit(project):
        raise Http404
    form = ProjectFileForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            files.add_file(
                project,
                form.cleaned_data["file"],
                user=request.user,
                title=form.cleaned_data["title"],
                document_type=form.cleaned_data["document_type"],
                visible_to_crew=form.visibility(),
                # PRJ-089: console and version of a show file.
                show_system=form.cleaned_data["show_system"],
                show_version=form.cleaned_data["show_version"],
            )
        except ValidationError as error:
            form.add_error("file", _messages_of(error))
        else:
            messages.success(request, _("File stored."))
            return redirect(_files_url(pk))
    from rentalars.documents.views import render_document_list

    return render_document_list(request, project, file_form=form)


def _file_of(request: HttpRequest, pk: int, file_pk: int) -> ProjectFile:
    """A file the user may open: any file with read access, crew files with the deployment view."""
    project = project_for(request, pk, ProjectAccess.DEPLOYMENT)
    project_file = get_object_or_404(ProjectFile, pk=file_pk, project=project)
    if project.access < ProjectAccess.READ and not project_file.visible_to_crew:
        raise Http404
    return project_file


def file_download(request: HttpRequest, pk: int, file_pk: int) -> HttpResponse:
    """Hand out a project file after checking the rights (NFA-007, AUT-023)."""
    rights = request_rights(request)
    if not rights.can_read(Module.PROJECTS):
        raise Http404
    project_file = _file_of(request, pk, file_pk)
    return document_response(project_file.file.name, project_file.original_name)


@module_required(Module.PROJECTS, Level.WRITE)
def file_edit(request: HttpRequest, pk: int, file_pk: int) -> HttpResponse:
    """Change title, document type or visibility of a file."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    project_file = get_object_or_404(ProjectFile, pk=file_pk, project=project)
    form = ProjectFileEditForm(request.POST or None, instance=project_file)
    if request.method == "POST" and form.is_valid():
        try:
            files.update_file(project_file, **{name: form.cleaned_data[name] for name in form.Meta.fields})
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("File saved."))
            return redirect(_files_url(pk))
    return render(request, "projects/file_form.html", {"project": project, "project_file": project_file, "form": form})


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def file_delete(request: HttpRequest, pk: int, file_pk: int) -> HttpResponse:
    """Remove a file from the project."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        files.delete_file(get_object_or_404(ProjectFile, pk=file_pk, project=project))
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    else:
        messages.success(request, _("File removed."))
    return redirect(_files_url(pk))


# --- Duplicating (PRJ-029) --------------------------------------------------------------------------


@module_required(Module.PROJECTS, Level.WRITE)
def duplicate(request: HttpRequest, pk: int) -> HttpResponse:
    """Make a new project from this one, for another period.

    A whole project comes with its parts unless the box is unticked; a part
    becomes a new part of the same whole project – for whoever may edit
    that – or a project of its own (PRJ-029, PRJ-044).
    """
    source = project_for(request, pk, ProjectAccess.READ, queryset=Project.objects.select_related("parent"))
    rights = request_rights(request)
    if rights.is_limited_to_assigned_projects(Module.PROJECTS) and source.access < ProjectAccess.EDIT:
        raise Http404
    may_add_part = bool(source.parent_id) and access_level(rights, request.user, source.parent) >= ProjectAccess.EDIT
    form = DuplicateForm(
        request.POST or None,
        initial={"name": source.name, "start": source.start, "end": source.end, "with_material": True},
        source=source,
        may_add_part=may_add_part,
    )
    if request.method == "POST" and form.is_valid():
        try:
            result = copy_project(
                source,
                name=form.cleaned_data["name"],
                start=form.cleaned_data["start"],
                end=form.cleaned_data["end"],
                with_material=form.cleaned_data["with_material"],
                with_crew=form.cleaned_data["with_crew"],
                with_logistics=form.cleaned_data["with_logistics"],
                with_subprojects=form.cleaned_data.get("with_subprojects", False),
                as_subproject=form.cleaned_data.get("as_subproject", False),
                rights=rights,
                user=request.user,
            )
        except ValidationError as error:
            form.add_error(None, _messages_of(error))
        else:
            copy = result.project
            if rights.is_limited_to_assigned_projects(Module.PROJECTS):
                from rentalars.projects.models import ProjectAccessLevel, ProjectMembership

                ProjectMembership.objects.get_or_create(
                    project=copy, user=request.user, defaults={"level": ProjectAccessLevel.EDIT}
                )
            messages.success(
                request,
                _("Project %(number)s was made from %(source)s.") % {"number": copy.number, "source": source.number},
            )
            if result.parts:
                messages.success(
                    request,
                    _("With the subprojects %(numbers)s.")
                    % {"numbers": ", ".join(part.number for part in result.parts)},
                )
            if result.dropped_takeovers:
                messages.warning(
                    request,
                    ngettext(
                        "%(count)d line taken over from another subproject is a normal line in the copy.",
                        "%(count)d lines taken over from other subprojects are normal lines in the copy.",
                        result.dropped_takeovers,
                    )
                    % {"count": result.dropped_takeovers},
                )
            return redirect("projects:detail", pk=copy.pk)
    return render(request, "projects/duplicate.html", {"project": source, "form": form})
