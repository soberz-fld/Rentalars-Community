# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of expenses and travel costs: my expenses, recording, receipts, report (ZEI-019).

Recording is a dialog like the quick time entry (ZEI-003): it opens from
"My expenses", from "My times", after a time was recorded and from the
deployment view of a project, and works on a phone with a photo of the
receipt. Without scripts the same block stands on a page of its own.
Approving happens with the times on the page "Freigeben" (``views.approval``).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.listing import paginate, query_date
from rentalars.core.uploads import document_response
from rentalars.personnel.models import Person
from rentalars.projects.access import person_of
from rentalars.projects.models import Project
from rentalars.timetracking import expenses as expense_services
from rentalars.timetracking import services
from rentalars.timetracking.expense_list_tables import EXPENSE_TABLE, MY_EXPENSE_TABLE
from rentalars.timetracking.forms import ExpenseFilterForm, ExpenseForm
from rentalars.timetracking.models import Expense, TimeEntryStatus
from rentalars.timetracking.views import _error_text, _next, _person_for


def _month_of(request: HttpRequest) -> datetime.date:
    """The first day of the month named by ``?month=2027-03``; the current month otherwise."""
    text = request.GET.get("month", "")
    day = query_date(f"{text}-01") if len(text) == 7 else None
    return (day or timezone.localdate()).replace(day=1)


def _next_month(month: datetime.date) -> datetime.date:
    return (month + datetime.timedelta(days=32)).replace(day=1)


# --- My expenses ------------------------------------------------------------------------------


@module_required(Module.TIME_TRACKING)
def my_expenses(request: HttpRequest) -> HttpResponse:
    """The own expenses month by month, with the sums and what is not handed in yet (ZEI-019, ZEI-016)."""
    rights = request_rights(request)
    person = person_of(request.user)
    month = _month_of(request)
    context: dict[str, Any] = {
        "person": person,
        "month": month,
        "previous_month": (month - datetime.timedelta(days=1)).replace(day=1),
        "next_month": _next_month(month),
        "month_end": _next_month(month) - datetime.timedelta(days=1),
        "is_current_month": month == timezone.localdate().replace(day=1),
        "can_record": rights.can_write(Module.TIME_TRACKING) and person is not None,
        "may_manage": services.may_manage(rights),
    }
    if person is not None:
        own = Expense.objects.filter(person=person)
        report = expense_services.expense_report(own.filter(date__gte=month, date__lt=_next_month(month)))
        # UIX-040: the expenses of the month as a table with columns, sorting, groups and CSV.
        table = MY_EXPENSE_TABLE.state(request)
        listed = table.order(report.expenses)
        if table.wants_csv:
            return table.csv_response(listed, _("My expenses") + f" {month:%Y-%m}")
        token = get_token(request)
        for expense in listed:  # what the cell with the buttons needs (``expense_list_tables._my_actions``)
            expense.can_record = context["can_record"]
            expense.csrf_token = token
            expense.back_to = request.get_full_path()
        context.update(
            report=report,
            table=table,
            rows=table.rows(listed),
            open_expenses=list(
                own.filter(status__in=[TimeEntryStatus.RECORDED, TimeEntryStatus.REJECTED])
                .select_related("project__parent")
                .order_by("date", "id")
            ),
        )
    template = (
        "timetracking/_my_expenses.html" if request.headers.get("HX-Request") else "timetracking/my_expenses.html"
    )
    return render(request, template, context)


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def expense_submit(request: HttpRequest) -> HttpResponse:
    """Hand in the own expenses that are not handed in yet (ZEI-019, as ZEI-012)."""
    rights = request_rights(request)
    person = person_of(request.user)
    if person is None:
        raise PermissionDenied
    open_ones = list(
        Expense.objects.filter(person=person, status__in=[TimeEntryStatus.RECORDED, TimeEntryStatus.REJECTED])
    )
    changed = expense_services.submit_expenses(open_ones, rights=rights, user=request.user)
    messages.success(request, expense_services.counts_message(changed, "submitted"))
    return redirect(_next(request, "timetracking:my_expenses"))


# --- Recording ---------------------------------------------------------------------------------


def _dialog_response(request: HttpRequest, template: str, context: dict[str, Any]) -> HttpResponse:
    """Answer with the block of the dialog: alone for the dialog, inside a page without scripts."""
    if request.headers.get("HX-Request"):
        return render(request, template, context)
    return render(request, "timetracking/expense_page.html", {**context, "fragment": template})


@module_required(Module.TIME_TRACKING, Level.WRITE)
def expense_new(request: HttpRequest) -> HttpResponse:
    """The dialog for recording an expense: project, kind, day, amount or kilometres, receipt (ZEI-019).

    ``?project=`` preselects a project (the deployment view). Somebody who
    may record for others – the office – chooses the person in the dialog
    (``person=``); choosing another one loads the dialog again with the
    projects of that person, keeping what was typed (as ZEI-006, ZEI-011).
    """
    rights = request_rights(request)
    may_manage = services.may_manage(rights)
    source = request.POST if request.method == "POST" else request.GET
    person = _person_for(request, source=source)
    context: dict[str, Any] = {
        "person": person,
        "may_manage": may_manage,
        "people": Person.objects.filter(is_active=True).order_by("last_name", "first_name") if may_manage else None,
    }
    if person is None:
        return _dialog_response(request, "timetracking/_expense_new.html", context)
    if not services.may_record_for(rights, request.user, person):
        raise PermissionDenied
    project_id = source.get("project", "")
    typed = {
        name: request.GET[name]
        for name in ("kind", "date", "amount", "kilometres", "note")
        if request.method == "GET" and request.GET.get(name)
    }
    form = ExpenseForm(
        request.POST or None,
        request.FILES or None,
        person=person,
        rights=rights,
        user=request.user,
        project_id=int(project_id) if str(project_id).isdigit() else None,
        initial=typed,
    )
    if request.method == "POST" and form.is_valid():
        try:
            expense = expense_services.create_expense(
                person=person,
                rights=rights,
                user=request.user,
                receipt=form.cleaned_data.get("receipt"),
                submit=form.cleaned_data["submit"],
                **form.values(),
            )
        except ValidationError as error:
            _add_errors(form, error)
        else:
            response = _dialog_response(request, "timetracking/_expense_done.html", {**context, "expense": expense})
            response["HX-Trigger"] = "expensesChanged"
            return response
    return _dialog_response(request, "timetracking/_expense_new.html", {**context, "form": form})


def _add_errors(form: ExpenseForm, error: ValidationError) -> None:
    """Show an error of the services at its field, or above the form."""
    if hasattr(error, "error_dict"):
        for name, field_errors in error.error_dict.items():
            target = name if name in form.fields else None
            for field_error in field_errors:
                form.add_error(target, field_error)
    else:
        form.add_error(None, _error_text(error))


def _own_expense(request: HttpRequest, pk: int) -> Expense:
    """An expense the user may see, for changing it: own, or with the right to record for others."""
    rights = request_rights(request)
    expense = get_object_or_404(
        expense_services.visible_expenses(rights, request.user).select_related("person", "project__parent"), pk=pk
    )
    if not services.may_record_for(rights, request.user, expense.person):
        raise PermissionDenied
    return expense


@module_required(Module.TIME_TRACKING, Level.WRITE)
def expense_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Correct an expense that is not approved yet, in a dialog (ZEI-019, as ZEI-012)."""
    rights = request_rights(request)
    expense = _own_expense(request, pk)
    if not expense.is_editable:
        messages.error(request, _("Approved expenses are locked. Somebody who approves can take the approval back."))
        return redirect("timetracking:my_expenses")
    form = ExpenseForm(
        request.POST or None,
        request.FILES or None,
        person=expense.person,
        rights=rights,
        user=request.user,
        expense=expense,
    )
    if request.method == "POST" and form.is_valid():
        try:
            expense_services.update_expense(
                expense,
                rights=rights,
                user=request.user,
                receipt=form.cleaned_data.get("receipt"),
                remove_receipt=form.cleaned_data.get("remove_receipt", False),
                **form.values(),
            )
            if form.cleaned_data["submit"]:
                expense_services.submit_expenses([expense], rights=rights, user=request.user)
        except ValidationError as error:
            _add_errors(form, error)
        else:
            if not request.headers.get("HX-Request"):
                messages.success(request, _("The expense was saved."))
                return redirect(_next(request, "timetracking:my_expenses"))
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "expensesChanged, closeDialog"
            return response
    return _dialog_response(
        request,
        "timetracking/_expense_form.html",
        {"form": form, "expense": expense, "action": request.get_full_path()},
    )


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def expense_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an expense that is not approved yet, with its receipt."""
    rights = request_rights(request)
    expense = _own_expense(request, pk)
    try:
        expense_services.delete_expense(expense, rights=rights, user=request.user)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("The expense was deleted."))
    return redirect(_next(request, "timetracking:my_expenses"))


@module_required(Module.TIME_TRACKING)
def expense_receipt(request: HttpRequest, pk: int) -> HttpResponse:
    """The receipt of an expense, for whoever may see the expense (NFA-007)."""
    expense = get_object_or_404(expense_services.visible_expenses(request_rights(request), request.user), pk=pk)
    if not expense.receipt:
        raise Http404
    return document_response(expense.receipt.name, expense_services.receipt_download_name(expense))


# --- Report, reimbursement ------------------------------------------------------------------------------


def _report_selection(request: HttpRequest) -> tuple[Any, ExpenseFilterForm, bool]:
    """The expenses the report shows, its filter form, and whether the current month stands in for a filter."""
    rights = request_rights(request)
    visible = expense_services.visible_expenses(rights, request.user)
    people = Person.objects.filter(pk__in=visible.values("person_id")).order_by("last_name", "first_name")
    projects = Project.objects.filter(pk__in=visible.values("project_id")).select_related("parent").order_by("-start")
    form = ExpenseFilterForm(request.GET or None, people=people, projects=projects)
    expenses = visible
    # Without a filter: the current month, as in the hours report (ZEI-017).
    is_default_period = not any(key not in ("format", "page", "per_page") for key in request.GET)
    if is_default_period:
        expenses = expenses.filter(date__gte=timezone.localdate().replace(day=1))
    data = form.cleaned_data if form.is_bound and form.is_valid() else {}
    if data.get("person"):
        expenses = expenses.filter(person=data["person"])
    if data.get("project"):
        expenses = expenses.filter(project=data["project"])
    if data.get("kind"):
        expenses = expenses.filter(kind=data["kind"])
    if data.get("since"):
        expenses = expenses.filter(date__gte=data["since"])
    if data.get("until"):
        expenses = expenses.filter(date__lte=data["until"])
    status = data.get("status", "")
    if status == "outstanding":
        expenses = expenses.filter(status=TimeEntryStatus.APPROVED, reimbursed_on__isnull=True)
    elif status == "reimbursed":
        expenses = expenses.filter(reimbursed_on__isnull=False)
    elif status in TimeEntryStatus.values:
        expenses = expenses.filter(status=status)
    else:
        expenses = expenses.exclude(status=TimeEntryStatus.REJECTED)
    return expenses, form, is_default_period


@module_required(Module.TIME_TRACKING)
def expense_report(request: HttpRequest) -> HttpResponse:
    """Expenses per month and person, with sums; ``?format=csv`` as a file (ZEI-019).

    Everybody sees their own expenses here; with the right to approve also
    those of others in the projects they may see, and can mark approved
    expenses as reimbursed.
    """
    rights = request_rights(request)
    expenses, form, is_default_period = _report_selection(request)
    report = expense_services.expense_report(expenses)
    # UIX-040: the expenses as a table – columns, sorting, groups; ``?format=csv`` the view, ``&cols=all`` every
    # column (with all columns the file, ``expenses.expenses_csv``).
    table = EXPENSE_TABLE.state(request)
    listed = table.order(report.expenses)
    if table.wants_csv:
        return table.csv_response(listed, _("Expenses"))
    query = request.GET.copy()
    for name in ("format", "page", "per_page"):
        query.pop(name, None)
    page = paginate(request, listed)
    return render(
        request,
        "timetracking/expense_report.html",
        {
            "form": form,
            "report": report,
            "table": table,
            "rows": table.rows(page),
            "page": page,
            "query": query.urlencode(),
            "may_manage": services.may_manage(rights),
            "is_default_period": is_default_period,
            "today": timezone.localdate(),
            "tab": "expenses",
        },
    )


def _back_to_report(request: HttpRequest) -> HttpResponse:
    query = QueryDict(request.POST.get("query", "")).urlencode()
    return redirect(reverse("timetracking:expense_report") + (f"?{query}" if query else ""))


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def expense_reimburse(request: HttpRequest) -> HttpResponse:
    """Mark the ticked approved expenses as reimbursed, on the day given (ZEI-019)."""
    rights = request_rights(request)
    if not services.may_manage(rights):
        raise PermissionDenied
    ids = [int(value) for value in request.POST.getlist("expense") if value.isdigit()]
    chosen = list(
        expense_services.visible_expenses(rights, request.user).filter(pk__in=ids).select_related("person__user")
    )
    try:
        if not chosen:
            raise ValidationError(_("Tick the expenses first."))
        day = query_date(request.POST.get("reimbursed_on")) or timezone.localdate()
        changed = expense_services.mark_reimbursed(chosen, rights=rights, user=request.user, on=day)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, expense_services.counts_message(changed, "reimbursed"))
    return _back_to_report(request)


@require_POST
@module_required(Module.TIME_TRACKING, Level.WRITE)
def expense_reopen(request: HttpRequest, pk: int) -> HttpResponse:
    """Take back a reimbursement, or – for an expense not reimbursed – the approval (ZEI-019, as ZEI-012)."""
    rights = request_rights(request)
    if not services.may_manage(rights):
        raise PermissionDenied
    expense = get_object_or_404(expense_services.visible_expenses(rights, request.user), pk=pk)
    try:
        if expense.is_reimbursed:
            expense_services.take_back_reimbursement(expense, rights=rights, user=request.user)
            messages.success(request, _("The expense is no longer marked as reimbursed."))
        else:
            expense_services.take_back_approval(expense, rights=rights, user=request.user)
            messages.success(request, _("The approval was taken back. The expense is “submitted” again."))
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _back_to_report(request)
