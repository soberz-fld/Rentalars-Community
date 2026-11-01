# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of time tracking: my times, quick entry, stopwatch, approval, report (chapter 5.9).

The quick entry is a dialog that every page can open (ZEI-003): the button
sits in the navigation. It asks for as little as possible and answers
without leaving the page (acceptance scenario 5).
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, QueryDict
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.i18n import file_name, local_pattern
from rentalars.core.listing import end_of_day, paginate, query_date, start_of_day
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects.access import person_of
from rentalars.projects.models import CrewLine, Project
from rentalars.timetracking import expenses as expense_services
from rentalars.timetracking import services
from rentalars.timetracking.display import attach_clipboard, attach_pay, mark_periods
from rentalars.timetracking.export import report_csv
from rentalars.timetracking.forms import LINE_PREFIX, WITHOUT_PROJECT, CorrectionForm, ReportFilterForm, TimeEntryForm
from rentalars.timetracking.hints import attach_hints
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus
from rentalars.timetracking.pdf import render_timesheet_pdf, timesheet_is_too_long, too_long_message
from rentalars.timetracking.time_list_tables import (
    APPROVAL_TABLE,
    REPORT_ENTRY_TABLE,
    REPORT_SUM_TABLE,
    keep_periods_together,
)


def _error_text(error: ValidationError) -> str:
    """Turn a validation error into one line for a message."""
    return " ".join(error.messages)


def _next(request: HttpRequest, default: str) -> str:
    """Return where to go after a form was sent: the page named in ``next``, if it is one of ours."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return reverse(default)


def _person_for(request: HttpRequest, *, source: Any = None) -> Person | None:
    """Return whose times a request is about (ZEI-011).

    Normally the person linked to the user. Somebody who may record for
    others can name another person with ``person=<id>``.
    """
    rights = request_rights(request)
    data = source if source is not None else request.GET
    person_id = str(data.get("person", "") or "")
    if person_id.isdigit() and services.may_manage(rights):
        return get_object_or_404(Person, pk=int(person_id))
    return person_of(request.user)


# --- My times (ZEI-016) -----------------------------------------------------------------


@module_required(Module.TIME_TRACKING)
def my_times(request: HttpRequest) -> HttpResponse:
    """The own times week by week, the stopwatch, and what is not handed in yet (ZEI-016)."""
    rights = request_rights(request)
    person = person_of(request.user)
    day = query_date(request.GET.get("week")) or timezone.localdate()
    monday, sunday = services.week_of(day)
    context: dict[str, Any] = {
        "person": person,
        "monday": monday,
        "sunday": sunday,
        "previous_week": monday - datetime.timedelta(days=7),
        "next_week": monday + datetime.timedelta(days=7),
        "is_current_week": monday <= timezone.localdate() <= sunday,
        "may_manage": services.may_manage(rights),
        "can_record": rights.can_write(Module.TIME_TRACKING) and person is not None,
    }
    if person is not None:
        entries = (
            TimeEntry.objects.filter(person=person, start__gte=start_of_day(monday), start__lt=end_of_day(sunday))
            # ZEI-026: the crew line with its phase and service product – for the day rate and the text to copy.
            .select_related(
                "project", "job_function__service_product", "crew_line__phase", "crew_line__service_product"
            )
            .order_by("start", "id")
        )
        report = services.hours_report(entries, group_by="day", rights=rights, user=request.user)
        open_entries = list(
            TimeEntry.objects.filter(
                person=person, status__in=[TimeEntryStatus.RECORDED, TimeEntryStatus.REJECTED], end__isnull=False
            )
            .select_related("project", "job_function")
            .order_by("start")
        )
        # ZEI-018: hints at the entries of the week and at those not handed in yet, asked for together.
        attach_hints(report.entries + open_entries)
        # ZEI-025: the parts of divided periods; ZEI-026: rate or day rate, and the text to copy.
        mark_periods(report.entries)
        mark_periods(open_entries)
        attach_clipboard(report.entries)
        context.update(
            report=report,
            running=services.running_timer(person),
            open_entries=open_entries,
            show_rate=services.may_see_rate_of(rights, request.user, person),
            week_amount=attach_pay(report.entries),
            # ZEI-024: the hint at the companion app, until the user puts it away.
            companion_hint=context["can_record"] and not companion_hint_dismissed(request.user),
        )
    template = "timetracking/_my_times.html" if request.headers.get("HX-Request") else "timetracking/my_times.html"
    return render(request, template, context)


# --- Quick entry (ZEI-003 to ZEI-007) ----------------------------------------------------------


def _quick_response(request: HttpRequest, template: str, context: dict[str, Any]) -> HttpResponse:
    """Answer with a block of the quick entry: alone for the dialog, inside a page otherwise.

    The buttons "record time" are links. With scripts they load the block
    into the dialog; without scripts, through a bookmark or a link in a
    message they lead to the same block on a page of its own.
    """
    if request.headers.get("HX-Request"):
        return render(request, template, context)
    return render(request, "timetracking/quick_page.html", {**context, "fragment": template})


def _quick_context(
    request: HttpRequest, form: TimeEntryForm | None, person: Person | None, **extra: Any
) -> dict[str, Any]:
    """Everything the quick entry dialog shows."""
    rights = request_rights(request)
    return {
        "form": form,
        "person": person,
        "running": services.running_timer(person),
        "may_manage": services.may_manage(rights),
        "people": Person.objects.filter(is_active=True) if services.may_manage(rights) else None,
        **extra,
    }


@module_required(Module.TIME_TRACKING, Level.WRITE)
def quick_entry(request: HttpRequest) -> HttpResponse:
    """The dialog for recording a time: project, job function, day, begin, end – and done (ZEI-003).

    ``GET`` shows the dialog; choosing another project loads it again with
    the job functions of that project (ZEI-007), keeping what was typed.
    ``POST`` saves and answers with a short confirmation in the same dialog,
    so that the page behind it is never left (acceptance scenario 5).
    """
    rights = request_rights(request)
    person = _person_for(request, source=request.POST if request.method == "POST" else request.GET)
    if person is None:
        return _quick_response(request, "timetracking/_quick.html", _quick_context(request, None, None))
    if not services.may_record_for(rights, request.user, person):
        raise PermissionDenied

    if request.method == "POST":
        form = TimeEntryForm(request.POST, person=person, rights=rights, user=request.user)
        if form.is_valid():
            try:
                entry = services.create_entry(
                    person=person, rights=rights, user=request.user, submit=form.cleaned_data["submit"], **form.values()
                )
            except ValidationError as error:
                form.add_error(None, _error_text(error))
            else:
                attach_hints([entry])  # ZEI-018: shown right when the time is entered, never blocking
                response = _quick_response(
                    request,
                    "timetracking/_quick_done.html",
                    # ZEI-025: every part of a divided period with its hours.
                    {"entry": entry, "person": person, "parts": getattr(entry, "period_parts", [entry])},
                )
                response["HX-Trigger"] = "timesChanged"
                return response
        return _quick_response(request, "timetracking/_quick.html", _quick_context(request, form, person))

    typed = {
        name: request.GET[name] for name in ("day", "begin", "end", "break_minutes", "note") if name in request.GET
    }
    project_id = request.GET.get("project", "")
    form = TimeEntryForm(
        person=person,
        rights=rights,
        user=request.user,
        project_id=int(project_id)
        if project_id.isdigit()
        else (WITHOUT_PROJECT if project_id == WITHOUT_PROJECT else None),
        initial=typed,
    )
    return _quick_response(request, "timetracking/_quick.html", _quick_context(request, form, person))


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def timer_start(request: HttpRequest) -> HttpResponse:
    """Start the stopwatch on a project and job function (ZEI-005)."""
    rights = request_rights(request)
    person = _person_for(request, source=request.POST)
    if person is None:
        raise PermissionDenied
    try:
        chosen = request.POST.get("project", "")
        project = None if chosen == WITHOUT_PROJECT else get_object_or_404(Project, pk=chosen or 0)
        function_value = request.POST.get("job_function", "")
        crew_line = None
        if function_value.startswith(LINE_PREFIX):
            # ZEI-025: a deployment chosen from the suggestions names its job function.
            line_id = function_value.removeprefix(LINE_PREFIX)
            crew_line = get_object_or_404(CrewLine, pk=int(line_id) if line_id.isdigit() else 0)
            job_function = crew_line.job_function
        else:
            job_function = get_object_or_404(JobFunction, pk=function_value if function_value.isdigit() else 0)
        services.start_timer(
            person=person,
            project=project,
            job_function=job_function,
            rights=rights,
            user=request.user,
            crew_line=crew_line,
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    if request.headers.get("HX-Request"):
        form = TimeEntryForm(person=person, rights=rights, user=request.user)
        response = render(
            request, "timetracking/_quick.html", _quick_context(request, form, person, with_messages=True)
        )
        response["HX-Trigger"] = "timesChanged"
        return response
    return redirect("timetracking:my_times")


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def timer_stop(request: HttpRequest) -> HttpResponse:
    """Stop the stopwatch; the entry ends now (ZEI-005)."""
    rights = request_rights(request)
    person = _person_for(request, source=request.POST)
    if person is None:
        raise PermissionDenied
    entry = None
    try:
        break_text = request.POST.get("break_minutes", "") or "0"
        entry = services.stop_timer(
            person=person,
            rights=rights,
            user=request.user,
            break_minutes=int(break_text) if break_text.isdigit() else 0,
            submit=request.POST.get("submit") == "on",
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    if request.headers.get("HX-Request") and entry is not None:
        attach_hints([entry])  # ZEI-018
        response = render(request, "timetracking/_quick_done.html", {"entry": entry, "person": person})
        response["HX-Trigger"] = "timesChanged"
        return response
    return redirect("timetracking:my_times")


@module_required(Module.TIME_TRACKING, Level.WRITE)
def entry_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Correct an entry that is not approved yet, in a dialog (ZEI-012, ZEI-014)."""
    rights = request_rights(request)
    entry = get_object_or_404(
        services.visible_entries(rights, request.user).select_related("person", "project", "job_function"), pk=pk
    )
    if not services.may_record_for(rights, request.user, entry.person):
        raise PermissionDenied
    form = TimeEntryForm(request.POST or None, person=entry.person, rights=rights, user=request.user, entry=entry)
    if request.method == "POST" and form.is_valid():
        try:
            # ZEI-025: the whole period with its job functions and their hours.
            services.save_period(entry, rights=rights, user=request.user, **form.period_values())
            if form.cleaned_data["submit"]:
                services.submit_entries([entry], rights=rights, user=request.user)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            response = HttpResponse(status=204)
            # In this order: the page must know that times changed before the dialog closes.
            response["HX-Trigger"] = "timesChanged, closeDialog"
            return response
    return render(request, "timetracking/_entry_form.html", {"form": form, "entry": entry, "action": request.path})


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def entry_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an entry that is not approved yet."""
    rights = request_rights(request)
    entry = get_object_or_404(services.visible_entries(rights, request.user).select_related("person"), pk=pk)
    try:
        services.delete_entry(entry, rights=rights, user=request.user)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return redirect(_next(request, "timetracking:my_times"))


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def submit(request: HttpRequest) -> HttpResponse:
    """Hand in entries for approval: the ticked ones, or all that are open (ZEI-012)."""
    rights = request_rights(request)
    person = person_of(request.user)
    entries = services.visible_entries(rights, request.user).select_related("person")
    ids = [int(value) for value in request.POST.getlist("entry") if value.isdigit()]
    if ids:
        entries = entries.filter(pk__in=ids)
    elif person is not None:
        entries = entries.filter(person=person, status__in=[TimeEntryStatus.RECORDED, TimeEntryStatus.REJECTED])
    else:
        entries = entries.none()
    changed = services.submit_entries(list(entries), rights=rights, user=request.user)
    messages.success(
        request,
        ngettext(
            "%(count)d time entry handed in for approval.", "%(count)d time entries handed in for approval.", changed
        )
        % {"count": changed},
    )
    return redirect("timetracking:my_times")


# --- The hint at the companion app (ZEI-024) ------------------------------------------------------------

#: Where the choice to put the hint away is kept: with the other choices a user makes about lists and pages.
COMPANION_HINT_KEY = "times.companion-app-hint"


def companion_hint_dismissed(user: Any) -> bool:
    """ZEI-024: whether the user put the hint at the companion app away (kept per user, one query)."""
    from rentalars.core.models import TablePreference

    return TablePreference.columns_of(user, COMPANION_HINT_KEY) is not None


@require_POST
@module_required(Module.TIME_TRACKING)
def companion_hint_dismiss(request: HttpRequest) -> HttpResponse:
    """ZEI-024: put the hint at the companion app away for good – for this user, on every device."""
    from rentalars.core.models import TablePreference

    TablePreference.save_columns(request.user, COMPANION_HINT_KEY, ["dismissed"])
    if request.headers.get("HX-Request"):
        return HttpResponse("")
    return redirect("timetracking:my_times")


# --- Approval (ZEI-012, ZEI-013) ------------------------------------------------------------------


def _require_manager(request: HttpRequest) -> None:
    """Approving needs the special right (ZEI-013)."""
    if not services.may_manage(request_rights(request)):
        raise PermissionDenied


def _filtered(request: HttpRequest, entries: Any, form: ReportFilterForm) -> Any:
    """Apply the filter of the report and approval pages to a list of entries."""
    if not form.is_valid():
        return entries
    data = form.cleaned_data
    if data.get("person"):
        entries = entries.filter(person=data["person"])
    if data.get("project") == WITHOUT_PROJECT:
        entries = entries.filter(project__isnull=True)
    elif data.get("project"):
        entries = entries.filter(project_id=int(data["project"]))
    if data.get("job_function"):
        entries = entries.filter(job_function=data["job_function"])
    if data.get("since"):
        entries = entries.filter(start__gte=start_of_day(data["since"]))
    if data.get("until"):
        entries = entries.filter(start__lt=end_of_day(data["until"]))
    return entries


def _filter_form(request: HttpRequest, *, with_expenses: bool = False) -> ReportFilterForm:
    """Build the filter form with the people and projects the user may choose from.

    ``with_expenses``: the people and projects of expenses as well – the
    approval lists them with the times (ZEI-019).
    """
    rights = request_rights(request)
    visible = services.visible_entries(rights, request.user)
    people = Q(pk__in=visible.values("person_id"))
    projects = Q(pk__in=visible.values("project_id"))
    if with_expenses:
        expenses = expense_services.visible_expenses(rights, request.user)
        people |= Q(pk__in=expenses.values("person_id"))
        projects |= Q(pk__in=expenses.values("project_id"))
    return ReportFilterForm(
        request.GET or None,
        people=Person.objects.filter(people).order_by("last_name", "first_name"),
        projects=Project.objects.filter(projects).select_related("parent").order_by("-start"),
    )


def _filtered_expenses(expenses: Any, form: ReportFilterForm) -> Any:
    """Apply the filter of the approval page to a list of expenses (ZEI-019)."""
    if not form.is_valid():
        return expenses
    data = form.cleaned_data
    if data.get("person"):
        expenses = expenses.filter(person=data["person"])
    if data.get("project") == WITHOUT_PROJECT:
        return expenses.none()
    if data.get("project"):
        expenses = expenses.filter(project_id=int(data["project"]))
    if data.get("since"):
        expenses = expenses.filter(date__gte=data["since"])
    if data.get("until"):
        expenses = expenses.filter(date__lte=data["until"])
    return expenses


@module_required(Module.TIME_TRACKING)
def approval(request: HttpRequest) -> HttpResponse:
    """The times waiting for approval, project by project (ZEI-013); each can be corrected and approved (ZEI-030)."""
    _require_manager(request)
    rights = request_rights(request)
    form = _filter_form(request, with_expenses=True)
    entries = list(
        _filtered(
            request,
            services.visible_entries(rights, request.user)
            .filter(status=TimeEntryStatus.SUBMITTED)
            .select_related("person", "project__parent", "job_function", "crew_line"),
            form,
        ).order_by("project__start", "project_id", "start", "person_id", "id")
    )
    # ZEI-018: long working days, short breaks and rests are pointed out; approving stays possible.
    attach_hints(entries)
    # UIX-040: sorted by the chosen column within each project; the parts of a period stay together (ZEI-025).
    table = APPROVAL_TABLE.state(request)
    entries = keep_periods_together(table.order(entries))
    # ZEI-025: the parts of a period stand together; the first carries the tick for the whole period.
    mark_periods(entries)
    # ZEI-019: the expenses waiting for approval stand with the times of their project.
    expenses = list(
        _filtered_expenses(
            expense_services.visible_expenses(rights, request.user)
            .filter(status=TimeEntryStatus.SUBMITTED)
            .select_related("person", "project__parent"),
            form,
        ).order_by("project__start", "project_id", "date", "id")
    )
    # Entries without project first: they need a step before they can be approved (ZEI-023).
    by_project: dict[int | None, dict[str, Any]] = {}

    def group_of(project: Project | None) -> dict[str, Any]:
        key = project.pk if project is not None else None
        return by_project.setdefault(
            key, {"project": project, "entries": [], "hours": 0, "expenses": [], "expense_total": 0}
        )

    for entry in sorted(entries, key=lambda entry: entry.project_id is not None):
        entry.back_to = request.get_full_path()  # ZEI-030: "Korrigieren" leads back to the list as it is filtered
        group = group_of(entry.project)
        group["entries"].append(entry)
        group["hours"] += entry.hours
    for expense in expenses:
        group = group_of(expense.project)
        group["expenses"].append(expense)
        group["expense_total"] += expense.amount
    without = by_project.get(None)
    if without is not None:
        for entry in without["entries"]:
            entry.project_options = [
                choice.project
                for choice in services.project_choices(entry.person, rights, request.user, at=entry.start)
            ]
    if table.wants_csv:
        return table.csv_response([entry for group in by_project.values() for entry in group["entries"]], _("Approve"))
    # Only the times without project have the column to assign one (ZEI-023).
    with_project = dataclasses.replace(table, columns=[column for column in table.columns if column.key != "assign"])
    for group in by_project.values():
        group["rows"] = (table if group["project"] is None else with_project).rows(group["entries"])
    return render(
        request,
        "timetracking/approval.html",
        {
            "form": form,
            "table": table,
            "groups": list(by_project.values()),
            "query": request.GET.urlencode(),
            "show_rates": rights.has(SpecialRight.PERSONNEL_COSTS),
            "tab": "approval",
        },
    )


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def decide(request: HttpRequest) -> HttpResponse:
    """Approve or reject the ticked entries, one or many at once (ZEI-013)."""
    _require_manager(request)
    rights = request_rights(request)
    ids = [int(value) for value in request.POST.getlist("entry") if value.isdigit()]
    entries = list(
        services.visible_entries(rights, request.user)
        .filter(pk__in=ids)
        .select_related("person", "project", "job_function")
    )
    # ZEI-019: the ticked expenses of the same project are decided together with the times.
    expense_ids = [int(value) for value in request.POST.getlist("expense") if value.isdigit()]
    expenses = (
        list(
            expense_services.visible_expenses(rights, request.user)
            .filter(pk__in=expense_ids)
            .select_related("person__user", "project")
        )
        if expense_ids
        else []
    )
    reason = request.POST.get("reason", "")
    try:
        if not entries and not expenses:
            raise ValidationError(_("Tick the entries first."))
        if request.POST.get("decision") == "reject":
            if not reason.strip():
                raise ValidationError(_("Say why the times are rejected, so that they can be corrected."))
            if entries:
                changed = services.reject_entries(entries, reason, rights=rights, user=request.user)
                messages.success(
                    request,
                    ngettext("%(count)d time entry sent back.", "%(count)d time entries sent back.", changed)
                    % {"count": changed},
                )
            if expenses:
                changed = expense_services.reject_expenses(expenses, reason, rights=rights, user=request.user)
                messages.success(request, expense_services.counts_message(changed, "rejected"))
        else:
            if entries:
                changed = services.approve_entries(entries, rights=rights, user=request.user)
                messages.success(
                    request,
                    ngettext("%(count)d time entry approved.", "%(count)d time entries approved.", changed)
                    % {"count": changed},
                )
            if expenses:
                changed = expense_services.approve_expenses(expenses, rights=rights, user=request.user)
                messages.success(request, expense_services.counts_message(changed, "approved"))
    except ValidationError as error:
        messages.error(request, _error_text(error))
    # Back to the list as it was filtered.
    query = QueryDict(request.POST.get("query", "")).urlencode()
    return redirect(reverse("timetracking:approval") + (f"?{query}" if query else ""))


def _back_to(request: HttpRequest, url: str) -> HttpResponse:
    """Back to a page – from a dialog by the page script (``HX-Redirect``), else by a redirect."""
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


@module_required(Module.TIME_TRACKING, Level.WRITE)
def entry_correct(request: HttpRequest, pk: int) -> HttpResponse:
    """Correct a time waiting for approval and approve it in one step (ZEI-030).

    "Korrigieren" on Personal → Freigeben opens the dialog – without the
    page script a page of its own – with the times, break, job function,
    project and note of the entry. Saved, the entry is approved, its values
    before stay in the change log, and the person is told
    (``services.correct_and_approve``, as ``POST
    /time-entries/{id}/correct``). ``next`` leads back to the list as it was
    filtered.
    """
    _require_manager(request)
    rights = request_rights(request)
    entry = get_object_or_404(
        services.visible_entries(rights, request.user).select_related("person", "project", "job_function"), pk=pk
    )
    target = request.POST.get("next") or request.GET.get("next") or ""
    allowed = target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()})
    back = target if allowed else reverse("timetracking:approval")
    if entry.status != TimeEntryStatus.SUBMITTED:
        messages.error(request, _("This time is no longer waiting for approval."))
        return _back_to(request, back)
    form = CorrectionForm(request.POST or None, entry=entry, rights=rights, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            services.correct_and_approve(entry, rights=rights, user=request.user, **form.correction())
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(
                request, _("The time of %(person)s was corrected and approved.") % {"person": entry.person}
            )
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                # As the entry dialog: the page knows that times changed before the dialog closes, then reloads.
                response["HX-Trigger"] = "timesChanged, closeDialog"
                return response
            return redirect(back)
    context = {"form": form, "entry": entry, "action": request.path, "back": back}
    if request.headers.get("HX-Request"):
        return render(request, "timetracking/_entry_correct.html", context)
    request.back_url = back  # type: ignore[attr-defined]
    return render(request, "timetracking/entry_correct.html", context)


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def entry_assign(request: HttpRequest, pk: int) -> HttpResponse:
    """Give an entry recorded without project its project, so that it can be approved (ZEI-023)."""
    rights = request_rights(request)
    entry = get_object_or_404(services.visible_entries(rights, request.user).select_related("person"), pk=pk)
    project = get_object_or_404(Project, pk=request.POST.get("project") or 0)
    try:
        services.assign_project(entry, project, rights=rights, user=request.user)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("The time now belongs to %(project)s.") % {"project": project})
    return redirect(_next(request, "timetracking:my_times"))


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def entry_reopen(request: HttpRequest, pk: int) -> HttpResponse:
    """Take back the approval of an entry, so that it can be corrected (ZEI-012)."""
    _require_manager(request)
    rights = request_rights(request)
    entry = get_object_or_404(services.visible_entries(rights, request.user).select_related("project", "person"), pk=pk)
    try:
        services.take_back_approval(entry, rights=rights, user=request.user)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("The approval was taken back. The entry is “submitted” again."))
    return redirect(_next(request, "timetracking:report"))


# --- Report (ZEI-015 to ZEI-017) ----------------------------------------------------------------------


@module_required(Module.TIME_TRACKING)
def report(request: HttpRequest) -> HttpResponse:
    """Hours by person, project, job function and period, with sums (ZEI-015).

    Everybody sees their own times here (ZEI-016); with the right to approve
    also those of others. Amounts need the right to see personnel costs,
    except for one's own entries (PER-010). ``?format=csv`` and
    ``?format=pdf`` deliver the same selection as a file (ZEI-017).
    """
    rights = request_rights(request)
    form = _filter_form(request)
    entries = services.visible_entries(rights, request.user)
    status = request.GET.get("status", "")
    if status in TimeEntryStatus.values:
        entries = entries.filter(status=status)
    else:
        entries = entries.exclude(status=TimeEntryStatus.REJECTED)
    # Without a filter: the current month, so that the page never starts with ten years of entries.
    # "format" only chooses the kind of file, "page" and "per_page" the part of the list: the CSV,
    # the PDF and page 2 of the page as it was first shown therefore hold the same month (ZEI-017).
    is_default_period = not any(
        key not in ("format", "page", "per_page")
        and not key.startswith((REPORT_ENTRY_TABLE.prefix, REPORT_SUM_TABLE.prefix))
        for key in request.GET
    )
    period_text = ""
    if is_default_period:
        month_start = timezone.localdate().replace(day=1)
        entries = entries.filter(start__gte=start_of_day(month_start))
        period_text = _("from %(date)s") % {"date": f"{month_start:{local_pattern('%d.%m.%Y')}}"}
    entries = _filtered(request, entries, form)
    group_by = request.GET.get("group_by", "person")
    result = services.hours_report(entries, group_by=group_by, rights=rights, user=request.user)
    mark_periods(result.entries)  # ZEI-025
    # ZEI-018: the hints at the entries; "only with hints" narrows the report to those entries.
    hinted = attach_hints(result.entries)
    if form.is_bound and form.is_valid() and form.cleaned_data.get("with_hints"):
        hinted_ids = [entry.pk for entry in result.entries if entry.hints]
        kept = {entry.pk: entry.hints for entry in result.entries if entry.hints}
        result = services.hours_report(
            entries.filter(pk__in=hinted_ids), group_by=group_by, rights=rights, user=request.user
        )
        for entry in result.entries:
            entry.hints = kept.get(entry.pk, [])

    output = request.GET.get("format", "")
    if output == "csv":
        return _report_csv(result, rights, request.user)
    query = request.GET.copy()
    query.pop("format", None)
    if output == "pdf" and timesheet_is_too_long(result):
        messages.error(request, too_long_message(result))
        return redirect(f"{reverse('timetracking:report')}?{query.urlencode()}")
    if output == "pdf":
        response = HttpResponse(
            render_timesheet_pdf(result, _period_text(form) or period_text), content_type="application/pdf"
        )
        response["Content-Disposition"] = f'inline; filename="{file_name("timesheet", extension="pdf")}"'
        return response
    # UIX-040: the entries as a table with columns, sorting, groups and their own CSV (``entries_format=csv``).
    table = REPORT_ENTRY_TABLE.state(request)
    listed = table.order(result.entries)
    if table.wants_csv:
        return table.csv_response(listed, _("Hours report"))
    # The sums cover every entry; the list below them shows one page at a time, so that a month
    # of a hundred people does not become a page of several megabytes (NFA-012).
    query.pop("page", None)
    query.pop("per_page", None)
    for name in [name for name in query if name.startswith((REPORT_ENTRY_TABLE.prefix, REPORT_SUM_TABLE.prefix))]:
        query.pop(name)  # the file of the report and the PDF do not depend on the order of the list
    page = paginate(request, listed)
    # UIX-015: the sums sort by each of their headings too (``sums_sort``).
    sums = REPORT_SUM_TABLE.state(request)
    may_manage = services.may_manage(rights)
    token = get_token(request)
    for entry in page:  # what the cell with the buttons needs (``time_list_tables._report_actions``)
        entry.may_manage, entry.csrf_token, entry.back_to = may_manage, token, request.get_full_path()
    return render(
        request,
        "timetracking/report.html",
        {
            "form": form,
            "report": result,
            "sums": sums,
            "sum_rows": sums.order(result.rows),
            "table": table,
            "rows": table.rows(page),
            "page": page,
            "query": query.urlencode(),
            "may_manage": services.may_manage(rights),
            "is_default_period": is_default_period,
            "hinted": hinted,
            "tab": "report",
        },
    )


def _period_text(form: ReportFilterForm) -> str:
    """Describe the chosen period for the head of the timesheet."""
    data = form.cleaned_data if form.is_bound and form.is_valid() else {}
    since, until = data.get("since"), data.get("until")
    if since and until:
        return f"{since:{local_pattern('%d.%m.%Y')}} – {until:{local_pattern('%d.%m.%Y')}}"
    if since:
        return _("from %(date)s") % {"date": f"{since:{local_pattern('%d.%m.%Y')}}"}
    if until:
        return _("until %(date)s") % {"date": f"{until:{local_pattern('%d.%m.%Y')}}"}
    return ""


def _report_csv(result: services.HoursReport, rights: Any, user: Any) -> HttpResponse:
    """The entries of a report as a CSV file for a spreadsheet (ZEI-017); see ``export.report_csv``."""
    response = HttpResponse(report_csv(result, rights, user), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{file_name("hours", extension="csv")}"'
    return response
