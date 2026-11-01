# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the follow-up of a project – "Wiedervorlage" (PRJ-105).

The dialog sets or changes it from the head of every project page (or, without
the page script, a page of its own); "Done" removes it – from the head, the
start page or the dialog. The rules are in ``projects.follow_up``.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from django.views.decorators.http import require_http_methods, require_POST

from rentalars.accounts.models import User
from rentalars.accounts.rights import Level
from rentalars.core.forms import StyledForm
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.case_work import case_work_required
from rentalars.projects.follow_up import NOTE_LENGTH, clear_follow_up, set_follow_up, when_text
from rentalars.projects.models import Project


class FollowUpForm(StyledForm):
    """Day, time, user and note of a follow-up (PRJ-105, PRJ-109)."""

    follow_up_on = forms.DateField(label=gettext_lazy("Follow-up on"))
    # PRJ-109: optional; the reminder comes from that time on, without one in the morning of the day.
    follow_up_at = forms.TimeField(
        label=pgettext_lazy("follow-up", "Time"),
        required=False,
        help_text=gettext_lazy("Optional. Without a time the reminder comes in the morning."),
    )
    follow_up_user = forms.ModelChoiceField(
        label=gettext_lazy("For"),
        queryset=User.objects.none(),
        help_text=gettext_lazy("Gets a notification on that day, as set under “My account” → “Notifications”."),
    )
    follow_up_note = forms.CharField(
        label=gettext_lazy("Note"),
        required=False,
        max_length=NOTE_LENGTH,
        widget=forms.TextInput(attrs={"placeholder": gettext_lazy("e.g. follow up the offer")}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["follow_up_user"].queryset = User.objects.filter(is_active=True).order_by(
            "first_name", "last_name", "username"
        )


def _back(request: HttpRequest, project: Project) -> str:
    """Where to go afterwards: the page the request came from (``next``), else the project."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        return target
    return reverse("projects:detail", args=[project.pk])


def _done(request: HttpRequest, target: str) -> HttpResponse:
    """Close the dialog and show the page again, or go there without the page script."""
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = target
        return response
    return redirect(target)


@require_http_methods(["GET", "POST"])
@case_work_required(Level.WRITE)
def follow_up_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Set or change the follow-up of a project, in a dialog over the page (PRJ-105).

    The user is whoever sets it unless somebody else is chosen. AUT-033: of a service case also the person
    responsible and the people taking part (PRJ-108, ``projects.case_work``).
    """
    project = project_for(request, pk, ProjectAccess.EDIT, case_work=True)
    initial = {
        "follow_up_on": project.follow_up_on,
        "follow_up_at": project.follow_up_at,
        "follow_up_user": project.follow_up_user_id or request.user.pk,
        "follow_up_note": project.follow_up_note,
    }
    form = FollowUpForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            set_follow_up(
                project,
                on=form.cleaned_data["follow_up_on"],
                at=form.cleaned_data["follow_up_at"],
                note=form.cleaned_data["follow_up_note"],
                user=form.cleaned_data["follow_up_user"],
                by=request.user,
            )
        except ValidationError as error:
            for field, errors in error.message_dict.items():
                form.add_error(field if field in form.fields else None, errors)
        else:
            messages.success(
                request,
                _("Follow-up on %(day)s for %(user)s.")
                % {"day": when_text(project, "d.m.Y"), "user": project.follow_up_user},
            )
            return _done(request, _back(request, project))
    context = {
        "project": project,
        "form": form,
        "next": _back(request, project),
    }
    if request.headers.get("HX-Request"):
        return render(request, "projects/_follow_up_form.html", context)
    return render(request, "projects/follow_up_form.html", context)


@require_POST
@case_work_required(Level.WRITE)
def follow_up_done(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove the follow-up of a project: done, or no longer wanted (PRJ-105); AUT-033: see :func:`follow_up_edit`."""
    project = project_for(request, pk, ProjectAccess.EDIT, case_work=True)
    status_before = project.case_status
    if clear_follow_up(project):
        messages.success(request, _("The follow-up of %(project)s is done.") % {"project": project.number})
    if project.case_status != status_before:
        # PRJ-112: waiting, waiting to close and backlog need a follow-up; without it the case is open again.
        messages.info(request, _("The service case is “%(status)s” now.") % {"status": project.case_status_label})
    return _done(request, _back(request, project))
