# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the trips changed, removed or added by hand on the page "Zeitplanung" (PRJ-111).

The form opens as a dialog over the page – or, without the page script, as
a page of its own – like the crew of a phase (PRJ-080). After saving, the
page "Zeitplanung" shows the trips again. The work is done in
``projects.trip_changes``, which the API calls as well (API-002).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required
from rentalars.projects import trip_changes
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.crew_views import back_to_course
from rentalars.projects.models import Project
from rentalars.projects.trip_forms import TripForm
from rentalars.projects.trips import Trip


def _trips_url(project: Project) -> str:
    return reverse("projects:course", args=[project.pk]) + "#trips"


def _done(request: HttpRequest, project: Project) -> HttpResponse:
    """Back to the trips on "Zeitplanung": from the dialog the page reloads where it is, else it leads there.

    A redirect to the same page with "#trips" would only move to the anchor, not load the page again.
    """
    return back_to_course(request, project, "trips")


def _messages_of(error: ValidationError) -> str:
    return " ".join(error.messages)


def _form_page(request: HttpRequest, project: Project, form: TripForm, trip: Trip | None) -> HttpResponse:
    context = {"project": project, "form": form, "trip": trip, "action": request.get_full_path()}
    if request.headers.get("HX-Request"):
        return render(request, "projects/_trip_form.html", context)
    # "Back" leads to the trips on "Zeitplanung", also when the page was opened directly (no trail to follow).
    request.back_url = _trips_url(project)  # type: ignore[attr-defined]
    return render(request, "projects/trip_form.html", context)


def _add_errors(form: TripForm, error: ValidationError) -> None:
    """Put the refusal of the service at its fields, or above the form."""
    if hasattr(error, "error_dict"):
        for name, errors in error.error_dict.items():
            target = name if name in form.fields else None
            for single in errors:
                for text in single.messages:
                    form.add_error(target, text)
    else:
        form.add_error(None, _messages_of(error))


@module_required(Module.PROJECTS, Level.WRITE)
def trip_edit(request: HttpRequest, pk: int, key: str) -> HttpResponse:
    """Change a trip: departure, start, stops, destination, title, note (PRJ-111)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        trip = trip_changes.find_trip(project, key)
    except ValidationError as error:
        messages.error(request, _messages_of(error))
        return _done(request, project)
    form = TripForm(request.POST or None, trip=trip)
    if request.method == "POST" and form.is_valid():
        try:
            trip_changes.change_trip(project, key, user=request.user, **form.values())
        except ValidationError as error:
            _add_errors(form, error)
        else:
            messages.success(request, _("Trip saved."))
            return _done(request, project)
    return _form_page(request, project, form, trip)


@module_required(Module.PROJECTS, Level.WRITE)
def trip_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a trip of one's own, e.g. a second delivery (PRJ-111)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    form = TripForm(request.POST or None, initial={"start": project.start})
    if request.method == "POST" and form.is_valid():
        try:
            trip_changes.add_trip(project, user=request.user, **form.values())
        except ValidationError as error:
            _add_errors(form, error)
        else:
            messages.success(request, _("Trip added."))
            return _done(request, project)
    return _form_page(request, project, form, None)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def trip_remove(request: HttpRequest, pk: int, key: str) -> HttpResponse:
    """Remove a trip; a determined one can be brought back with "Wiederherstellen" (PRJ-111)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        trip = trip_changes.remove_trip(project, key, user=request.user)
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    else:
        messages.success(request, _("Trip “%(title)s” removed.") % {"title": trip.title})
    return redirect(_trips_url(project))


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def trip_reset(request: HttpRequest, pk: int, key: str) -> HttpResponse:
    """Bring a trip back as Rentalars determines it – also a removed one (PRJ-111)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        trip = trip_changes.reset_trip(project, key)
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    else:
        messages.success(request, _("Trip “%(title)s” is as Rentalars determines it again.") % {"title": trip.title})
    return redirect(_trips_url(project))
