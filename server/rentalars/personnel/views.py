# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the personnel module: people, job functions, availability, own profile."""

from __future__ import annotations

import datetime
import json
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.history import describe
from rentalars.core.listing import paginate
from rentalars.core.models import AuditLogEntry, SystemSettings
from rentalars.personnel import services
from rentalars.personnel.availability import people_availability
from rentalars.personnel.forms import (
    AbsenceForm,
    AvailabilityForm,
    JobFunctionForm,
    OwnProfileForm,
    PersonForm,
    QualificationForm,
    RateForm,
)
from rentalars.personnel.models import EmploymentKind, JobFunction, Person, Qualification
from rentalars.personnel.privacy import anonymise_person, export_person
from rentalars.personnel.tables import JOB_FUNCTION_TABLE, PERSON_TABLE
from rentalars.projects.access import person_of, visible_projects


def _messages_of(error: ValidationError) -> str:
    """Turn a validation error into one line for a message."""
    return " ".join(error.messages)


# --- People (PER-001, PER-002, PER-013) ------------------------------------------------


@module_required(Module.PERSONNEL)
def person_list(request: HttpRequest) -> HttpResponse:
    """All people with search, kind and job function (PER-001)."""
    # AUT-034: the roles of the accounts for the columns finances, personnel data, customer data – in one query.
    people = Person.objects.prefetch_related("rates__job_function", "user__roles").select_related("user")
    text = request.GET.get("q", "").strip()
    if text:
        people = people.filter(
            Q(first_name__icontains=text)
            | Q(last_name__icontains=text)
            | Q(email__icontains=text)
            | Q(company__icontains=text)
        )
    kind = request.GET.get("kind", "")
    if kind in EmploymentKind.values:
        people = people.filter(kind=kind)
    function_id = request.GET.get("job_function", "")
    if function_id.isdigit():
        people = people.filter(rates__job_function_id=int(function_id)).distinct()
    if not request.GET.get("inactive"):
        people = people.filter(is_active=True)
    table = PERSON_TABLE.state(request)
    people = table.order(people.prefetch_related("qualifications__qualification_type"))
    if table.wants_csv:
        return table.csv_response(people, _("People"))
    page = paginate(request, people)
    return render(
        request,
        "personnel/person_list.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "q": text,
            "kinds": EmploymentKind.choices,
            "kind": kind,
            "job_functions": JobFunction.objects.all(),
            "job_function_id": function_id,
            "tab": "people",
        },
    )


@module_required(Module.PERSONNEL)
def person_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One person: master data, job functions and rates, deployments, absences, times (PER-013)."""
    person = get_object_or_404(Person.objects.select_related("user"), pk=pk)
    rights = request_rights(request)
    may_see_rates = rights.has(SpecialRight.PERSONNEL_COSTS)
    now = timezone.now()
    # AUT-016: deployments in projects the reader may not see are counted, not named.
    visible = set(visible_projects(rights, request.user).values_list("pk", flat=True))
    lines = list(
        person.crew_lines.select_related("project__parent", "job_function")
        .filter(end__gte=now - datetime.timedelta(days=30))
        .order_by("start")[:100]
    )
    all_rates = list(services.rate_history(person))
    recent_entries: list[Any] = []
    if rights.can_read(Module.TIME_TRACKING) and rights.has(SpecialRight.APPROVE_TIMES):
        recent_entries = list(person.time_entries.select_related("project", "job_function").order_by("-start")[:20])
    return render(
        request,
        "personnel/person_detail.html",
        {
            "person": person,
            "may_see_rates": may_see_rates,
            "current_rates": services.current_rates(person),
            "all_rates": all_rates,
            # PER-029: functions with own rates – only those who see the rates may take them away.
            "rated_functions": {
                rate.job_function_id
                for rate in all_rates
                if rate.hourly_rate is not None or rate.daily_rate is not None
            },
            "rate_form": RateForm(),
            "deployments": [(line, line.project_id in visible) for line in lines],
            "absences": person.absences.filter(end__gte=now - datetime.timedelta(days=30)),
            "absence_form": AbsenceForm(),
            "qualifications": person.qualifications.select_related("qualification_type"),
            "qualification_form": QualificationForm(),
            "recent_entries": recent_entries,
            "tab": "person",
            "history": describe(list(AuditLogEntry.for_object(person)[:30]), rights),
        },
    )


@module_required(Module.PERSONNEL, Level.WRITE)
def person_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create a person or edit the master data."""
    person = get_object_or_404(Person, pk=pk) if pk else None
    if person is not None and person.anonymised_at:
        messages.error(request, _("This person was anonymised and can no longer be edited."))
        return redirect("personnel:person_detail", pk=person.pk)
    form = PersonForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, _("%(person)s saved.") % {"person": saved.name})
        if form.cleaned_data.get("invite") and saved.user.email:
            from rentalars.accounts.services import send_invitation
            from rentalars.mail.server import warn_without_server

            send_invitation(saved.user)
            if not warn_without_server(request):  # EML-048
                messages.success(request, _("The invitation was sent to %(email)s.") % {"email": saved.user.email})
        elif form.cleaned_data.get("invite"):
            # AUT-027: without an address there is no mail; the way in is a one-time password.
            messages.warning(
                request,
                _(
                    "No invitation was sent: the person has no e-mail address. "
                    "Set a one-time password on the page of the user instead."
                ),
            )
        return redirect("personnel:person_detail", pk=saved.pk)
    return render(request, "personnel/person_form.html", {"form": form, "person": person})


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def person_set_active(request: HttpRequest, pk: int) -> HttpResponse:
    """Deactivate a person or bring them back (PER-001)."""
    person = get_object_or_404(Person, pk=pk)
    try:
        services.set_person_active(person, active=request.POST.get("active") == "1", acting_user=request.user)
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    return redirect("personnel:person_detail", pk=person.pk)


@require_POST
@module_required(Module.PERSONNEL, Level.DELETE)
def person_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a person who was never planned and never recorded a time."""
    person = get_object_or_404(Person, pk=pk)
    try:
        services.delete_person(person)
    except ValidationError as error:
        messages.error(request, _messages_of(error))
        return redirect("personnel:person_detail", pk=pk)
    messages.success(request, _("Person deleted."))
    return redirect("personnel:person_list")


# --- Rates (PER-005, PER-007, PER-010, PER-029) ---------------------------------------------------


def _may_set_rates(request: HttpRequest) -> bool:
    """Hourly and day rates are set and seen only with the right to personnel costs (AUT-019, PER-029)."""
    return request_rights(request).has(SpecialRight.PERSONNEL_COSTS)


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def rate_set(request: HttpRequest, pk: int) -> HttpResponse:
    """Assign a job function, with rates if given, or enter new rates from a day on (PER-005, PER-007, PER-029).

    Without the right to personnel costs the form has only the job function:
    it is assigned without own rates – the guide values count –, and rates
    the person already has stay as they are.
    """
    person = get_object_or_404(Person, pk=pk)
    form = RateForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return redirect(reverse("personnel:person_detail", args=[person.pk]) + "#rates")
    job_function = form.cleaned_data["job_function"]
    rates = (form.cleaned_data["hourly_rate"], form.cleaned_data["daily_rate"], form.cleaned_data["valid_from"])
    above_limit = form.cleaned_data["hourly_rate_above_limit"]  # PER-035
    if not _may_set_rates(request):
        if any(value is not None for value in (*rates, above_limit)):
            raise PermissionDenied
        if services.assign_job_function(person, job_function):
            messages.success(
                request,
                _("%(function)s: assigned without own rates; the guide values of the job function count.")
                % {"function": job_function},
            )
        else:
            messages.info(
                request, _("%(function)s: the person has this job function already.") % {"function": job_function}
            )
        return redirect(reverse("personnel:person_detail", args=[person.pk]) + "#rates")
    try:
        services.set_rate(
            person, job_function, rates[0], rates[2], daily_rate=rates[1], hourly_rate_above_limit=above_limit
        )
    except ValidationError as error:
        messages.error(request, _messages_of(error))
    else:
        with_rate = rates[0] is not None or rates[1] is not None or above_limit is not None
        messages.success(
            request,
            (
                _("%(function)s: rate saved. Existing crew lines and time entries keep their rate.")
                if with_rate
                else _("%(function)s: assigned without own rates; the guide values of the job function count.")
            )
            % {"function": job_function},
        )
    return redirect(reverse("personnel:person_detail", args=[person.pk]) + "#rates")


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def rate_remove(request: HttpRequest, pk: int, function_pk: int) -> HttpResponse:
    """Take a job function away from a person (PER-005).

    Its rates go with it; so without the right to personnel costs only a
    function without own rates can be taken away (AUT-019).
    """
    person = get_object_or_404(Person, pk=pk)
    job_function = get_object_or_404(JobFunction, pk=function_pk)
    if not _may_set_rates(request) and services.has_own_rates(person, job_function):
        raise PermissionDenied
    services.remove_job_function(person, job_function)
    return redirect("personnel:person_detail", pk=person.pk)


# --- Absences (PER-011) -----------------------------------------------------------------------


def _save_absence(request: HttpRequest, person: Person) -> None:
    """Read the absence form and save; warnings and errors go into messages."""
    form = AbsenceForm(request.POST)
    form.instance.person = person
    if form.is_valid():
        try:
            warnings = services.save_absence(form.save(commit=False))
        except ValidationError as error:
            messages.error(request, _messages_of(error))
        else:
            messages.success(request, _("Absence saved."))
            for warning in warnings:
                messages.warning(request, warning)
    else:
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def absence_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Enter an absence of a person (PER-011)."""
    person = get_object_or_404(Person, pk=pk)
    _save_absence(request, person)
    return redirect("personnel:person_detail", pk=person.pk)


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def absence_delete(request: HttpRequest, pk: int, absence_pk: int) -> HttpResponse:
    """Delete an absence."""
    person = get_object_or_404(Person, pk=pk)
    get_object_or_404(person.absences, pk=absence_pk).delete()
    return redirect("personnel:person_detail", pk=person.pk)


# --- Qualifications (PER-014) ------------------------------------------------------------------


@module_required(Module.PERSONNEL, Level.WRITE)
def qualification_edit(request: HttpRequest, pk: int, qualification_pk: int | None = None) -> HttpResponse:
    """Record a qualification of a person or change it, with the scan of the certificate (PER-014)."""
    person = get_object_or_404(Person, pk=pk)
    qualification = (
        get_object_or_404(Qualification, pk=qualification_pk, person=person)
        if qualification_pk
        else Qualification(person=person)
    )
    form = QualificationForm(request.POST or None, request.FILES or None, instance=qualification)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_qualification(form.save(commit=False), document=form.cleaned_data.get("upload"))
        except ValidationError as error:
            if hasattr(error, "error_dict"):
                for field, errors in error.error_dict.items():
                    form.add_error(field if field in form.fields else None, errors)
            else:
                form.add_error("upload", error)
        else:
            messages.success(request, _("Qualification saved."))
            return redirect(reverse("personnel:person_detail", args=[person.pk]) + "#qualifications")
    return render(
        request,
        "personnel/qualification_form.html",
        {"form": form, "person": person, "qualification": qualification},
    )


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def qualification_delete(request: HttpRequest, pk: int, qualification_pk: int) -> HttpResponse:
    """Remove a qualification with its certificate."""
    services.delete_qualification(get_object_or_404(Qualification, pk=qualification_pk, person_id=pk))
    messages.success(request, _("Qualification removed."))
    return redirect(reverse("personnel:person_detail", args=[pk]) + "#qualifications")


def qualification_document(request: HttpRequest, pk: int, qualification_pk: int) -> HttpResponse:
    """The certificate: for personnel planning, and for the person it belongs to (NFA-010)."""
    from rentalars.core.uploads import document_response

    qualification = get_object_or_404(Qualification, pk=qualification_pk, person_id=pk)
    own = person_of(request.user)
    if not request_rights(request).can_read(Module.PERSONNEL) and (own is None or own.pk != pk):
        raise PermissionDenied
    if not qualification.document:
        raise Http404
    return document_response(qualification.document.name, qualification.document_name or "nachweis.pdf")


@module_required(Module.PERSONNEL)
def person_timeline(request: HttpRequest, pk: int) -> HttpResponse:
    """When the person is planned, available or absent, and when a qualification expires (PER-020, PER-027)."""
    from rentalars.personnel.models import AvailabilityState
    from rentalars.schedule.services import span_from_request
    from rentalars.schedule.timelines import person_timeline as build

    person = get_object_or_404(Person, pk=pk)
    days, navigation = span_from_request(request, default_weeks=4)
    visible = set(visible_projects(request_rights(request), request.user).values_list("pk", flat=True))
    return render(
        request,
        "personnel/person_timeline.html",
        {
            "person": person,
            "timeline": build(person, days, visible),
            "tab": "timeline",
            "availability_legend": AvailabilityState.choices,
            **navigation,
        },
    )


# --- Availability (VFG-009, VFG-010) -------------------------------------------------------------


@module_required(Module.PERSONNEL)
def availability(request: HttpRequest) -> HttpResponse:
    """Who is free, planned or absent in a period – optionally only people with one job function (VFG-010)."""
    settings_ = SystemSettings.load()
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    zone = timezone.get_current_timezone()
    initial = {
        "start": datetime.datetime.combine(tomorrow, settings_.default_start_time, tzinfo=zone),
        "end": datetime.datetime.combine(tomorrow, settings_.default_end_time, tzinfo=zone),
    }
    if initial["end"] <= initial["start"]:
        initial["end"] += datetime.timedelta(days=1)  # noon to noon (PRJ-068)
    form = AvailabilityForm(request.GET if "start" in request.GET else None, initial=initial)
    rows = None
    start, end = initial["start"], initial["end"]
    job_function = None
    if form.is_bound and form.is_valid():
        start, end, job_function = (
            form.cleaned_data["start"],
            form.cleaned_data["end"],
            form.cleaned_data["job_function"],
        )
    if not form.is_bound or form.is_valid():
        rows = people_availability(start, end, job_function=job_function)
    rights = request_rights(request)
    visible = set(visible_projects(rights, request.user).values_list("pk", flat=True))
    return render(
        request,
        "personnel/availability.html",
        {"form": form, "rows": rows, "start": start, "end": end, "visible_project_ids": visible, "tab": "availability"},
    )


# --- Job functions (PER-004, PER-008) ---------------------------------------------------------------


@module_required(Module.PERSONNEL)
def job_function_list(request: HttpRequest) -> HttpResponse:
    """All job functions with their service products (PER-004, PER-008); the product links to its page (PER-037)."""
    from django.db.models import Count

    functions = JobFunction.objects.select_related("service_product").annotate(
        people_count=Count("rates__person", distinct=True)
    )
    table = JOB_FUNCTION_TABLE.state(request)
    functions = table.order(functions)
    if table.wants_csv:
        return table.csv_response(functions, _("Job functions"))
    page = table.paginate(functions)  # UIX-050 (UIX-012)
    rows = list(page)
    rights = request_rights(request)
    may_edit = rights.can_write(Module.PERSONNEL)
    may_open_products = rights.can_read(Module.PRODUCTS)
    for function in rows:
        function.may_edit = may_edit
        function.may_open_product = may_open_products
    return render(
        request,
        "personnel/job_function_list.html",
        {"table": table, "rows": table.rows(rows), "page": page, "tab": "functions"},
    )


@module_required(Module.PERSONNEL, Level.WRITE)
def job_function_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or edit a job function; a new one brings its service product of the same name (PRD-044)."""
    job_function = get_object_or_404(JobFunction.objects.select_related("service_product"), pk=pk) if pk else None
    rights = request_rights(request)
    form = JobFunctionForm(
        request.POST or None,
        instance=job_function,
        may_see_costs=rights.has(SpecialRight.PERSONNEL_COSTS),
        may_see_prices=rights.has(SpecialRight.PRICES),  # PER-026
    )
    if request.method == "POST" and form.is_valid():
        try:
            saved = form.save()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            if job_function is None:
                product = saved.service_product
                messages.success(
                    request,
                    _("Job function saved, with its service product %(product)s.")
                    % {"product": f"{product.article_number} {product.name}"},
                )
            else:
                messages.success(request, _("Job function saved."))
            return redirect("personnel:job_function_list")
    return render(
        request,
        "personnel/job_function_form.html",
        {
            "form": form,
            "job_function": job_function,
            "product": job_function.service_product if job_function is not None else None,
            "may_open_product": rights.can_read(Module.PRODUCTS),
            "may_see_prices": rights.has(SpecialRight.PRICES),
        },
    )


@require_POST
@module_required(Module.PERSONNEL, Level.DELETE)
def job_function_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a job function that nobody has and that was never planned – with its service product (PRD-044).

    Others are deactivated.
    """
    job_function = get_object_or_404(JobFunction, pk=pk)
    try:
        services.delete_job_function(job_function)
    except ValidationError as error:
        messages.error(request, _messages_of(error))
        return redirect("personnel:job_function_edit", pk=pk)
    messages.success(request, _("Job function deleted."))
    return redirect("personnel:job_function_list")


# --- Privacy (NFA-009) ---------------------------------------------------------------------------------


@module_required(Module.PERSONNEL, Level.DELETE)
def person_export(request: HttpRequest, pk: int) -> HttpResponse:
    """Everything stored about a person as a file, for a request for information (NFA-009).

    Needs the highest level of the module: the file contains the hourly
    rates and all times of the person.
    """
    if not request_rights(request).has(SpecialRight.PERSONNEL_COSTS):
        raise PermissionDenied
    person = get_object_or_404(Person, pk=pk)
    body = json.dumps(export_person(person), ensure_ascii=False, indent=2)
    response = HttpResponse(body, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="person-{person.pk}.json"'
    return response


@require_POST
@module_required(Module.PERSONNEL, Level.DELETE)
def person_anonymise(request: HttpRequest, pk: int) -> HttpResponse:
    """Erase what identifies a person; deployments and times stay (NFA-009)."""
    person = get_object_or_404(Person, pk=pk)
    anonymise_person(person)
    messages.success(request, _("The person was anonymised. Deployments and times are kept without the name."))
    return redirect("personnel:person_detail", pk=person.pk)


# --- The own profile (PER-012, PER-019) ---------------------------------------------------------------------


def _own_person(request: HttpRequest) -> Person:
    """Return the person linked to the logged-in user, or refuse (AUT-012)."""
    person = person_of(request.user)
    if person is None:
        raise PermissionDenied
    return person


def own_profile(request: HttpRequest) -> HttpResponse:
    """The tab "Personnel data" of "My area" (UIX-026): contact data and who may see them, own absences.

    Needs no right on the personnel module – everybody may see and release
    their own data (PER-019) and say when they are not available (PER-012).
    The own availability and the calendars are on the tab "Availability"
    (:func:`rentalars.personnel.calendar_views.own_availability`).
    """
    person = _own_person(request)
    form = OwnProfileForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
        return redirect("personnel:own_profile")
    rights = request_rights(request)
    may_see_own_rates = rights.has(SpecialRight.PERSONNEL_COSTS) or SystemSettings.load().people_see_own_rates
    now = timezone.now()
    return render(
        request,
        "personnel/own_profile.html",
        {
            "person": person,
            "form": form,
            # PER-010, PER-029: the functions always, their hourly and day rates only if the person may see them.
            "current_rates": services.current_rates(person),
            "may_see_own_rates": may_see_own_rates,
            "absences": person.absences.filter(end__gte=now - datetime.timedelta(days=30)),
            "absence_form": AbsenceForm(),
            "qualifications": person.qualifications.select_related("qualification_type"),
            "deployments": person.crew_lines.select_related("project__parent", "job_function")
            .filter(end__gte=now - datetime.timedelta(days=1))
            .order_by("start")[:50],
        },
    )


@require_POST
def own_absence_add(request: HttpRequest) -> HttpResponse:
    """Enter an absence of one's own (PER-012)."""
    _save_absence(request, _own_person(request))
    return redirect("personnel:own_profile")


@require_POST
def own_absence_delete(request: HttpRequest, absence_pk: int) -> HttpResponse:
    """Delete an absence of one's own."""
    get_object_or_404(_own_person(request).absences, pk=absence_pk).delete()
    return redirect("personnel:own_profile")
