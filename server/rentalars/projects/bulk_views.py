# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser: actions on the ticked rows of the lists of projects and service cases (``projects.bulk``).

The bar under the list (``projects/_bulk_projects.html``, ``projects/_bulk_cases.html``) posts here. Who may: the
module "projects" for writing – or, for service cases, working on a case (AUT-033); the service decides per record.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.core import bulk as core_bulk
from rentalars.core.forms import StyledForm
from rentalars.projects import bulk
from rentalars.projects.follow_up import NOTE_LENGTH
from rentalars.projects.models import CaseStatus, CaseWaitingFor

#: The tables the bars belong to and where they return to if the address is not ours.
PROJECT_TABLES = {"projects": "projects:list"}
CASE_TABLES = {"service_cases": "projects:cases", "my_service_cases": "projects:my_cases"}


class BulkForm(StyledForm):
    """The fields of the bars: a follow-up, a status, a person responsible. Each action uses its own and checks them."""

    follow_up_on = forms.DateField(label=gettext_lazy("Follow-up on"), required=False)
    follow_up_at = forms.TimeField(label=gettext_lazy("Time"), required=False)
    follow_up_user = forms.ModelChoiceField(label=gettext_lazy("For"), queryset=User.objects.none(), required=False)
    follow_up_note = forms.CharField(label=gettext_lazy("Note"), required=False, max_length=NOTE_LENGTH)
    case_status = forms.ChoiceField(
        label=gettext_lazy("Status"), choices=[("", "–"), *CaseStatus.choices], required=False
    )
    case_waiting_for = forms.ChoiceField(
        label=gettext_lazy("Waiting for"), choices=[("", "–"), *CaseWaitingFor.choices], required=False
    )
    manager = forms.ModelChoiceField(
        label=gettext_lazy("Person responsible"), queryset=User.objects.none(), required=False
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        people = User.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        self.fields["follow_up_user"].queryset = people
        self.fields["manager"].queryset = people
        self.fields["follow_up_user"].empty_label = "–"
        self.fields["manager"].empty_label = "–"
        for name in ("follow_up_on", "follow_up_at", "follow_up_note"):
            self.fields[name].required = False

    def values(self, request: HttpRequest) -> dict[str, Any]:
        """The cleaned fields under the names ``projects.bulk.change`` takes; the follow-up is for the user by default."""
        data = self.cleaned_data
        return {
            "on": data.get("follow_up_on"),
            "at": data.get("follow_up_at"),
            "note": data.get("follow_up_note") or "",
            "user": data.get("follow_up_user") or request.user,
            "status": data.get("case_status") or "",
            "waiting_for": data.get("case_waiting_for") or "",
            "manager": data.get("manager"),
        }


def empty_bar() -> BulkForm:
    """The unbound fields for the bars, with the form's own labels and choices."""
    return BulkForm()


def _act(request: HttpRequest, *, tables: dict[str, str], cases_only: bool) -> HttpResponse:
    """The common part: the chosen keys, the fields, the action, the messages, back to the list."""
    table_key = request.POST.get("table", "")
    if table_key not in tables:
        raise PermissionDenied
    target = core_bulk.back(request, reverse(tables[table_key]))
    ids = core_bulk.chosen_ids(request, table_key)
    form = BulkForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            messages.error(request, " ".join(errors))
        return redirect(target)
    try:
        result = bulk.change(
            ids,
            request.POST.get("action", ""),
            rights=request_rights(request),
            user=request.user,
            cases_only=cases_only,
            values=form.values(request),
        )
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
        return redirect(target)
    for level, text in bulk.summary(result):
        messages.add_message(request, getattr(messages, level.upper()), text)
    return redirect(target)


@require_POST
def projects_action(request: HttpRequest) -> HttpResponse:
    """Do one thing with the ticked projects: set or take off the follow-up."""
    if not request_rights(request).has_level(Module.PROJECTS, Level.WRITE):
        raise PermissionDenied
    return _act(request, tables=PROJECT_TABLES, cases_only=False)


@require_POST
def cases_action(request: HttpRequest) -> HttpResponse:
    """Do one thing with the ticked service cases: follow-up, status or the person responsible."""
    if not may_change_cases(request):
        raise PermissionDenied
    return _act(request, tables=CASE_TABLES, cases_only=True)


def may_change_projects(request: HttpRequest) -> bool:
    """Whether the list of projects offers its actions."""
    return request_rights(request).has_level(Module.PROJECTS, Level.WRITE)


def may_change_cases(request: HttpRequest) -> bool:
    """Whether a list of service cases offers its actions.

    Who writes projects; or who can work on service cases (AUT-033) – the service decides per case, as for the API.
    """
    rights = request_rights(request)
    if rights.has_level(Module.PROJECTS, Level.WRITE):
        return True
    return rights.case_work >= Level.WRITE
