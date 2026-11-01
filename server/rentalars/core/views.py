# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the core module: start page, search, setup, administration."""

from __future__ import annotations

import datetime
from typing import Any
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.forms import (
    AccountingSwitchForm,
    CompanyProfileForm,
    NumberRangeForm,
    SetupForm,
    SystemSettingsForm,
    settings_sections,
)
from rentalars.core.history import describe
from rentalars.core.listing import end_of_day, paginate, query_date, start_of_day
from rentalars.core.middleware import SetupRequiredMiddleware
from rentalars.core.models import AuditLogEntry, CompanyProfile, NumberRange, NumberRangeKey, SystemSettings
from rentalars.core.search import global_search
from rentalars.core.setup import complete_setup, setup_token_is_valid
from rentalars.core.uploads import document_response, protected_file_response
from rentalars.material import numbering
from rentalars.projects.access import person_of, visible_projects
from rentalars.projects.models import FINISHED_STATUSES, ProjectStatus

#: How long the shortages of the start page are kept at most, even when nothing seems to change.
DASHBOARD_SHORTAGES_SECONDS = 300


def dashboard_shortages(projects: Any) -> tuple[list[Any], int]:
    """The first open shortages for the start page and how many there are (UIX-021).

    Judging every coming project costs about as much as the list of
    shortages itself, and the start page is opened far more often. The
    result is kept as long as nothing was changed: the key holds the newest
    entry of the change log, which every change of a line, a project or an
    item writes – and at most a few minutes, for what changes without an
    entry (time passing, imports in bulk). Only users who may read every
    project come here, so all of them share one result.
    """
    from django.core.cache import cache
    from django.db.models import Max

    from rentalars.availability.services import open_shortages

    newest = AuditLogEntry.objects.aggregate(newest=Max("pk"))["newest"] or 0
    key = f"rentalars:dashboard-shortages:{newest}"
    kept = cache.get(key)
    if kept is None:
        shortages = open_shortages(projects=projects)
        kept = (shortages[:6], len(shortages))
        cache.set(key, kept, DASHBOARD_SHORTAGES_SECONDS)
    return kept


def home(request: HttpRequest) -> HttpResponse:
    """The start page: what is due for this user, depending on the rights of the role (UIX-003).

    Each block shows only for those whose rights cover it, and only with
    what they may see (AUT-016): crew sees its own deployments and requests,
    the warehouse what is to be packed and what comes back today, project
    management the coming projects, open items and shortages, the office
    mails with unknown tags; everybody their follow-ups whose day has come
    (PRJ-105). Who the customer is shows only to those who may know (AUT-023).
    """
    from django.db.models import Q

    from rentalars.mail.models import Mailbox, UnknownTagMail
    from rentalars.notifications.services import unread
    from rentalars.packing.models import material_out
    from rentalars.projects.crew import open_requests_of
    from rentalars.projects.models import FIRM_STATUSES
    from rentalars.timetracking.services import running_timer

    rights = request_rights(request)
    now = timezone.now()
    today = timezone.localdate()
    zone = timezone.get_current_timezone()
    day_start = datetime.datetime.combine(today, datetime.time.min, tzinfo=zone)
    tomorrow_end = day_start + datetime.timedelta(days=2)
    context: dict[str, Any] = {
        "show_customers": rights.level_everywhere(Module.PROJECTS) >= Level.READ or rights.can_read(Module.CUSTOMERS),
        "notifications": list(unread(request.user)[:5]),
        "now": now,
        "today": today,
    }
    if rights.can_read(Module.PROJECTS):
        visible = visible_projects(rights, request.user)
        # PRJ-044: parts name their whole project.
        active = (
            visible.exclude(status__in=FINISHED_STATUSES).exclude(is_internal=True).select_related("customer", "parent")
        )
        # PRJ-090: service cases are no coming projects; they have their list under Projekte → Servicefälle.
        active = active.exclude(kind="service_case")
        # PCK-025: material is out also while a project is only partly issued and not "out" yet.
        active = active.annotate(material_out=material_out())
        is_out = Q(status=ProjectStatus.OUT) | Q(material_out=True)
        context["projects_out"] = active.filter(is_out).order_by("end")[:10]
        context["projects_upcoming"] = active.exclude(is_out).filter(end__gte=now).order_by("start")[:10]
        if rights.can_read(Module.PACKING):
            # UIX-003: what leaves the warehouse today or tomorrow, and what comes back today.
            context["to_pack"] = (
                active.filter(status__in=FIRM_STATUSES, start__lt=tomorrow_end)
                .exclude(status=ProjectStatus.OUT)
                .prefetch_related("packlists")
                .order_by("start")[:10]
            )
            context["coming_back"] = (
                active.filter(is_out).filter(end__lt=day_start + datetime.timedelta(days=1)).order_by("end")[:10]
            )
        from rentalars.projects.access import readable_projects
        from rentalars.projects.course import projects_with_open_items
        from rentalars.projects.service_cases import off_dashboards

        # PRJ-112: a service case in the backlog stays off the start page until its follow-up is due.
        with_items = projects_with_open_items(readable_projects(rights, request.user)).exclude(off_dashboards())
        own_items = with_items.filter(manager=request.user)
        # AUT-031 (Crew): "Offene Punkte" only for who reads the planning – the box leads to that page.
        if rights.reads_planning:
            context["open_item_projects"] = list((own_items if own_items.exists() else with_items)[:6])
        # PRJ-105: the user's follow-ups whose day has come, in every status; "done" where the user may edit.
        from rentalars.projects.access import ProjectAccess, access_of_many
        from rentalars.projects.follow_up import due_for

        follow_ups = list(due_for(request.user, readable_projects(rights, request.user)).select_related("parent")[:8])
        if follow_ups:
            levels = access_of_many(rights, request.user, [project.pk for project in follow_ups])
            for project in follow_ups:
                project.may_edit = rights.can_write(Module.PROJECTS) and levels[project.pk] >= ProjectAccess.EDIT
        context["follow_ups"] = follow_ups
        # PRJ-090: the service cases the user is responsible for and that still need them;
        # PRJ-108: and those the user takes part in.
        from rentalars.projects.service_cases import ACTIVE_STATUSES, cases

        mine = Q(manager=request.user)
        if person_of(request.user) is not None:
            mine |= Q(participants__person=person_of(request.user))
        context["own_cases"] = list(
            cases(visible)
            .filter(mine, case_status__in=ACTIVE_STATUSES)
            .exclude(off_dashboards())  # PRJ-112: the backlog until its follow-up is due
            .distinct()
            .order_by("-created_at")[:6]
        )
        if rights.has(SpecialRight.PRICES):
            # DOK-015: closed projects whose invoice is still open,
            # the user's own first; the list of projects filters all of them.
            from rentalars.core.models import NotificationSettings
            from rentalars.documents.invoice_reminders import finished_at, open_projects

            since = NotificationSettings.load().invoice_reminders_since
            open_invoices = [
                project
                for project in open_projects(readable_projects(rights, request.user))
                .select_related("customer")
                .order_by("-end")[:200]
                if since is None or (finished_at(project) or since) >= since
            ]
            own = [project for project in open_invoices if project.manager_id == request.user.pk]
            context["open_invoices"] = (own + [project for project in open_invoices if project not in own])[:8]
        if not rights.is_limited_to_assigned_projects(Module.PROJECTS) and rights.has(SpecialRight.AVAILABILITY):
            # UIX-021: every open shortage, not only those of the next two weeks. AUT-032: with the right to see
            # the availability of material.
            context["shortages"], context["shortage_count"] = dashboard_shortages(
                readable_projects(rights, request.user)
            )
    elif rights.case_work >= Level.READ:
        # AUT-033 (PRJ-108): the own service cases also without the module "projects".
        from rentalars.projects.service_cases import ACTIVE_STATUSES, cases, off_dashboards

        context["own_cases"] = list(
            cases(visible_projects(rights, request.user))
            .filter(case_status__in=ACTIVE_STATUSES)
            .exclude(off_dashboards())
            .order_by("-created_at")[:6]
        )
    # PRJ-023, PER-016: whoever is planned sees where and when, and what to answer.
    person = person_of(request.user)
    if person is not None:
        context["own_person"] = person
        context["own_requests"] = list(open_requests_of(person)[:6])
        context["own_deployments"] = (
            person.crew_lines.select_related("project__parent", "job_function")
            .exclude(project__status__in=FINISHED_STATUSES)
            .filter(end__gte=now - datetime.timedelta(hours=12))
            .exclude(request_status="declined")
            .order_by("start")[:8]
        )
        if rights.can_write(Module.TIME_TRACKING):
            context["running_timer"] = running_timer(person)
    if rights.can_read(Module.EMAIL):
        # EML-041, EML-042: mailboxes whose fetch fails, and the mails waiting under Projects → Inquiries.
        context["mail_problems"] = list(
            Mailbox.objects.filter(is_active=True, for_correspondence=True).exclude(last_error="")
        )
        context["unknown_mail_count"] = UnknownTagMail.objects.filter(resolved_at__isnull=True).count()
    return render(request, "core/home.html", context)


def search(request: HttpRequest) -> HttpResponse:
    """The global search over projects, customers, products and material (UIX-002)."""
    text = request.GET.get("q", "")
    groups = global_search(text, request_rights(request), request.user)
    return render(request, "core/search.html", {"q": text, "groups": groups})


def setup(request: HttpRequest) -> HttpResponse:
    """The first-run setup in the browser (NFA-033).

    Reachable without login, but only until it is completed, and on a server
    only with the one-time token from the installation script.
    """
    if SystemSettings.load().setup_completed:
        return redirect("core:home")

    token = request.GET.get("token") or request.session.get("setup_token")
    if not setup_token_is_valid(token):
        return render(request, "core/setup_locked.html", status=403)
    if token:
        request.session["setup_token"] = token

    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        administrator = complete_setup(form.cleaned_data)
        SetupRequiredMiddleware.reset()
        login(request, administrator, backend="rentalars.accounts.backends.EmailOrUsernameBackend")
        messages.success(request, _("Rentalars is set up. Welcome!"))
        return redirect("core:home")
    return render(request, "core/setup.html", {"form": form})


@module_required(Module.ADMINISTRATION)
def administration(request: HttpRequest) -> HttpResponse:
    """The entry page of the administration with links to all its parts."""
    from rentalars.masterdata.models import StorageLocation

    return render(
        request,
        "core/administration.html",
        {
            "user_count": User.objects.filter(is_active=True).count(),
            "company": CompanyProfile.load(),
            # MAT-052: which location new items get, next to the link to the storage locations.
            "default_location": StorageLocation.get_default(),
        },
    )


@module_required(Module.ADMINISTRATION)
def company_settings(request: HttpRequest) -> HttpResponse:
    """Company profile and system settings on one page (ADM-001, ADM-004).

    ADM-015: with "Answer to deployment requests" (PER-032), which
    was on the page of the mailboxes; it is still stored with the mail
    settings, and ``/mail/settings`` of the API still reads and changes it.
    """
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    company = CompanyProfile.load()
    system_settings = SystemSettings.load()
    posted = request.POST.get("form") if request.method == "POST" else None

    def sent(name: str) -> bool:
        return posted in (name, "all")

    company_form = CompanyProfileForm(
        request.POST if sent("company") else None,
        request.FILES if sent("company") else None,
        instance=company,
        prefix="company",
    )
    system_form = SystemSettingsForm(
        request.POST if sent("system") else None, instance=system_settings, prefix="system"
    )
    accounting_form = AccountingSwitchForm(
        request.POST if sent("accounting") else None, instance=system_settings, prefix="accounting"
    )
    if request.method == "POST":
        if not can_write:
            return render(request, "403.html", status=403)
        kind = request.POST.get("form")
        if kind == "all":
            # B1: one form, one button – nothing typed in one box is lost by saving another.
            all_forms = (company_form, system_form, accounting_form)
            checked = [form.is_valid() for form in all_forms]  # every form is checked, so all errors show at once
            if all(checked):
                with transaction.atomic():
                    for form in all_forms:
                        form.save()
                messages.success(request, _("Settings saved."))
                return redirect("core:company_settings")
        else:
            form = {"company": company_form, "accounting": accounting_form}.get(kind, system_form)
            if form.is_valid():
                form.save()
                messages.success(request, _("Settings saved."))
                return redirect("core:company_settings")
    from rentalars.core.routing import route_status
    from rentalars.mail.crew_answers import answer_mailbox

    return render(
        request,
        "core/settings.html",
        {
            "company_form": company_form,
            "system_form": system_form,
            "system_sections": settings_sections(system_form),
            "accounting_form": accounting_form,
            "company": company,
            "can_write": can_write,
            # ADM-015, PER-032: the mailbox the answers to deployment requests go to by mail, if one can take them.
            "crew_answer_mailbox": answer_mailbox(),
            # LOG-017: the route service for the kilometres of trips, read-only – the operator sets it up.
            "route": route_status(),
        },
    )


@module_required(Module.ADMINISTRATION)
def number_ranges(request: HttpRequest) -> HttpResponse:
    """Format and counters of the number ranges (ADM-003)."""
    # The general range "document" of stage 1 is not used: every kind of document counts on its own (DOK-005).
    ranges = list(NumberRange.objects.exclude(key=NumberRangeKey.DOCUMENT))
    forms = {
        number_range.pk: NumberRangeForm(
            request.POST if request.POST.get("range") == str(number_range.pk) else None,
            instance=number_range,
            prefix=f"range{number_range.pk}",
        )
        for number_range in ranges
    }
    if request.method == "POST":
        if not request_rights(request).can_write(Module.ADMINISTRATION):
            return render(request, "403.html", status=403)
        number_range = get_object_or_404(NumberRange, pk=request.POST.get("range"))
        form = forms[number_range.pk]
        if form.is_valid():
            form.save()
            numbering.reset_cache()
            messages.success(request, _("Number range saved."))
            return redirect("core:number_ranges")
    return render(
        request,
        "core/number_ranges.html",
        {"ranges": [(number_range, forms[number_range.pk]) for number_range in ranges]},
    )


@module_required(Module.ADMINISTRATION, Level.READ)
def audit_log(request: HttpRequest) -> HttpResponse:
    """The system-wide change log, filterable by object, user and period (ADM-005)."""
    entries = AuditLogEntry.objects.select_related("actor", "content_type")
    content_type_id = request.GET.get("type", "")
    user_id = request.GET.get("user", "")
    since = query_date(request.GET.get("since"))
    until = query_date(request.GET.get("until"))
    text = request.GET.get("q", "").strip()
    if content_type_id.isdigit():
        entries = entries.filter(content_type_id=int(content_type_id))
    if user_id.isdigit():
        entries = entries.filter(actor_id=int(user_id))
    if since:
        entries = entries.filter(timestamp__gte=start_of_day(since))
    if until:
        entries = entries.filter(timestamp__lt=end_of_day(until))
    if text:
        entries = entries.filter(object_repr__icontains=text)

    page = paginate(request, entries)
    logged_types = ContentType.objects.filter(
        pk__in=AuditLogEntry.objects.values_list("content_type_id", flat=True).distinct()
    )
    type_choices = sorted(
        (
            (content_type.pk, str(content_type.model_class()._meta.verbose_name))
            for content_type in logged_types
            if content_type.model_class() is not None
        ),
        key=lambda choice: choice[1].lower(),
    )
    return render(
        request,
        "core/audit_log.html",
        {
            "page": page,
            "history": describe(list(page.object_list), request_rights(request)),
            "type_choices": type_choices,
            "users": User.objects.order_by("username"),
            "filters": {
                "type": content_type_id,
                "user": user_id,
                "since": request.GET.get("since", ""),
                "until": request.GET.get("until", ""),
                "q": text,
            },
        },
    )


def media_file(request: HttpRequest, path: str) -> HttpResponse:
    """Deliver an uploaded file to logged-in users (NFA-007).

    Today the only uploads served here are the company logo and the
    logo for labels (MAT-056); files of other kinds have views of
    their own with their own rights check.
    """
    # No ".." (or "." or empty part): "company/../incoming/x.xml" would pass the prefix check and leave the folder.
    parts = path.split("/")
    if not path.startswith(("company/", "labels/")) or any(part in ("", ".", "..") or "\\" in part for part in parts):
        return render(request, "404.html", status=404)
    return protected_file_response(path)


@module_required(Module.ADMINISTRATION)
def self_check(request: HttpRequest) -> HttpResponse:
    """The state of the installation (NFA-037, NFA-049); with a test mail to oneself."""
    from django.core.mail import send_mail

    from rentalars.core.selfcheck import run_checks

    if request.method == "POST" and request.POST.get("action") == "test_mail":
        if not request.user.email:
            messages.error(request, _("Your account has no e-mail address."))
        else:
            from rentalars.mail.server import not_sent_text

            try:
                sent = send_mail(
                    _("Rentalars: test mail"),
                    _("This mail was sent from the self-check of Rentalars. Sending works."),
                    None,
                    [request.user.email],
                )
            except Exception as error:
                messages.error(request, _("The test mail could not be sent: %(error)s") % {"error": error})
            else:
                if sent:
                    messages.success(request, _("A test mail went to %(address)s.") % {"address": request.user.email})
                else:
                    # EML-048: without a mail server it only went into the log of the server.
                    messages.warning(request, not_sent_text())
        return redirect("core:self_check")
    report = run_checks()
    return render(request, "core/self_check.html", {"report": report})


@require_POST
def table_columns(request: HttpRequest, key: str) -> HttpResponse:
    """Save which columns a user wants to see in a list (UIX-015).

    The form of the column chooser posts the ticked columns; "default" forgets
    the choice. Afterwards the list opens again as it was – with its filters,
    but without ``cols`` in the address, which would hide the saved choice.
    """
    from rentalars.core.models import TablePreference
    from rentalars.core.tables import REGISTRY

    definition = REGISTRY.get(key)
    if definition is None:
        raise Http404
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=False):
        target = "/"
    if request.POST.get("reset"):
        TablePreference.save_columns(request.user, key, None)
    else:
        allowed = {column.key for column in definition.available(request_rights(request))}
        chosen = [column for column in request.POST.getlist("columns") if column in allowed]
        TablePreference.save_columns(request.user, key, chosen or None)
    parts = urlsplit(target)
    parameters = QueryDict(parts.query, mutable=True)
    parameters.pop(definition.param("cols"), None)  # UIX-040: a table with a prefix
    parameters.pop("page", None)
    query = parameters.urlencode()
    return redirect(f"{parts.path}?{query}" if query else parts.path)


# --- Tasks in the background (NFA-041) ----------------------------------------------------------


def _own_job(request: HttpRequest, pk: int) -> Any:
    """A task of the current user; nobody else sees it or its result."""
    from rentalars.core.models import BackgroundJob

    job = get_object_or_404(BackgroundJob, pk=pk)
    # Only the one who started it: a result can hold the data of everybody (the full export, IMP-006).
    if job.created_by_id is None or job.created_by_id != request.user.pk:
        raise Http404
    return job


def job_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """How far a task in the background got; its result when it is done (NFA-041).

    While the task runs, the block asks again every two seconds (htmx) and
    the rest of the application can be used meanwhile.
    """
    job = _own_job(request, pk)
    template = "core/_job.html" if request.headers.get("HX-Request") else "core/job.html"
    return render(request, template, {"job": job})


def job_result(request: HttpRequest, pk: int) -> HttpResponse:
    """The file a task made, for the one who started it."""
    job = _own_job(request, pk)
    if not job.result_file:
        raise Http404
    return document_response(job.result_file.name, job.result_name or "ergebnis")


def job_list(request: HttpRequest) -> HttpResponse:
    """The own tasks of the last days."""
    from rentalars.core.job_tables import JOB_TABLE
    from rentalars.core.models import BackgroundJob

    # UIX-040: a table of core.tables with paging instead of the last 50 tasks.
    table = JOB_TABLE.state(request)
    jobs = table.order(BackgroundJob.objects.filter(created_by=request.user))
    if table.wants_csv:
        return table.csv_response(jobs, _("Tasks in the background"))
    page = paginate(request, jobs)
    return render(
        request,
        "core/job_list.html",
        {"jobs": page.object_list, "page": page, "table": table, "rows": table.rows(page)},
    )
