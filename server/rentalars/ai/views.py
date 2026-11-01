# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the AI (EML-040, EML-044, ADM-017).

In the settings ("Einstellungen → KI", module "Administration": read to
see, write to change):

* the local AI – installed or not, model, reachable, speed of a test prompt –
  and the switch "Zusammenfassungen mit lokaler KI";
* which provider serves which use: the summary, the reply draft, reading
  invoices (MAT-062, "Kauf einpflegen"); template suggestions are listed as
  "later";
* the OpenAI-compatible interfaces (providers), with a clear warning for a
  cloud service;
* the log of the calls, without content.

In a project and a service case, on the correspondence page: the short
overview without AI and the AI summary with "Zusammenfassen" (for who may
read the correspondence). In "Mail schreiben": "Entwurf vorschlagen" (for who
may write mails), when an administrator switched reply drafts on.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.ai import auto, correspondence, drafts, summary
from rentalars.ai import speed as speeds
from rentalars.ai.client import (
    AIError,
    available_models,
    endpoint_for,
    is_switched_on,
    local_endpoint,
    provider_endpoint,
    speed_test,
)
from rentalars.ai.cpu import read_cpuinfo
from rentalars.ai.forms import PRIVACY_CHOICES, AutoSettingsForm, ProviderForm, UsesForm
from rentalars.ai.local import LocalConfigError, local_server
from rentalars.ai.models import AICall, AIProvider, AISettings, AutoSummaryExclusion, AutoSummaryRun, Source, Use
from rentalars.ai.overview import overview_of
from rentalars.core.listing import paginate
from rentalars.core.models import BackgroundJob, JobStatus
from rentalars.mail import services as mail_services
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import Project


def KEY_REMOVED_TEXT() -> str:  # noqa: N802 - a text, looked up in the language of the request
    """What the page and the API say when a changed address took the stored key away (ADM-017)."""
    return _(
        "The address now leads to another server, so the stored API key was removed: it is never sent to another "
        "server. Enter the key for the new server."
    )


#: The operator's commands, shown on the settings page to copy.
INSTALL_COMMAND = "sudo rentalars ai install"
REMOVE_COMMAND = "sudo rentalars ai remove"


def _may_change(request: HttpRequest) -> bool:
    return request_rights(request).has_level(Module.ADMINISTRATION, Level.WRITE)


def _require_change(request: HttpRequest) -> None:
    if not _may_change(request):
        raise PermissionDenied


def local_status() -> dict[str, Any]:
    """The local AI for the settings page and the API: installed, model, reachable (EML-040)."""
    status: dict[str, Any] = {
        "installed": False,
        "error": "",
        "reachable": None,
        "reach_error": "",
        "models": [],
        # EML-040: AVX2 and FMA, physical cores – also before anything is installed.
        "cpu": read_cpuinfo(),
    }
    status["advice"] = speeds.advice(model="", speed=None, cpu=status["cpu"])
    try:
        server = local_server()
    except LocalConfigError as error:
        status["error"] = str(error)
        return status
    if server is None:
        return status
    status.update(installed=True, server=server)
    try:
        status["models"] = available_models(local_endpoint(server))
        status["reachable"] = True
    except AIError as error:
        status["reachable"] = False
        status["reach_error"] = str(error)
    status["model_offered"] = not status["models"] or server.model in status["models"]
    # EML-040: the measured speed, what a typical summary takes, and what would make it faster.
    measured = speeds.speed_of(local_endpoint(server))
    status["speed"] = measured
    status["typical"] = speeds.typical_summary(measured)
    status["advice"] = speeds.advice(model=server.model, speed=measured, cpu=status["cpu"])
    return status


# --- Settings --------------------------------------------------------------------------------------------


@module_required(Module.ADMINISTRATION)
def settings_page(request: HttpRequest) -> HttpResponse:
    """Einstellungen → KI (EML-040, ADM-017)."""
    ai_settings = AISettings.load()
    form = UsesForm.for_settings(request.POST or None, ai_settings)
    if request.method == "POST":
        _require_change(request)
        if form.is_valid():
            form.apply(ai_settings)
            ai_settings.save()
            messages.success(request, _("The uses of AI were saved."))
            return redirect("ai:settings")
    providers = list(AIProvider.objects.order_by("name"))
    summary_source, summary_provider = ai_settings.source_of(Use.SUMMARY)
    draft_source, draft_provider = ai_settings.source_of(Use.DRAFT)
    invoice_source, invoice_provider = ai_settings.source_of(Use.INVOICE)  # MAT-062
    return render(
        request,
        "ai/settings.html",
        {
            "local": local_status(),
            "ai_settings": ai_settings,
            "form": form,
            "providers": providers,
            "summary_source": summary_source,
            "summary_provider": summary_provider,
            "draft_source": draft_source,
            "draft_provider": draft_provider,
            "invoice_source": invoice_source,
            "invoice_provider": invoice_provider,
            "calls": AICall.objects.select_related("user", "project")[:10],
            "auto_state": auto.consent_state(ai_settings),
            "last_run": AutoSummaryRun.objects.filter(dry_run=False).first(),
            "can_write": _may_change(request),
            "install_command": INSTALL_COMMAND,
            "remove_command": REMOVE_COMMAND,
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def local_summaries(request: HttpRequest) -> HttpResponse:
    """The switch "Zusammenfassungen mit lokaler KI" (EML-040): on sets the local AI for summaries, off turns them off."""
    ai_settings = AISettings.load()
    if request.POST.get("on") == "1":
        ai_settings.summary_source, ai_settings.summary_provider = Source.LOCAL, None
        messages.success(request, _("Summaries are now made by the local AI."))
    else:
        ai_settings.summary_source, ai_settings.summary_provider = Source.OFF, None
        messages.success(request, _("Summaries with AI are switched off. The short overview stays."))
    ai_settings.save()
    return redirect("ai:settings")


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def local_speed_test(request: HttpRequest) -> HttpResponse:
    """Send a short test prompt to the local AI and note how fast it wrote (EML-040)."""
    try:
        server = local_server()
    except LocalConfigError as error:
        messages.error(request, str(error))
        return redirect("ai:settings")
    if server is None:
        messages.error(request, _("The local AI is not installed. The operator installs it on the server."))
        return redirect("ai:settings")
    try:
        answer = speed_test(local_endpoint(server), user=request.user)
    except AIError as error:
        messages.error(request, str(error))
        return redirect("ai:settings")
    store_speed(answer.seconds, answer.tokens_per_second, server.model, prompt_per_second=answer.prompt_per_second)
    messages.success(request, speed_message(answer))
    return redirect("ai:settings")


def speed_message(answer: Any) -> str:
    """What the speed test found: the time, and reading and writing speed where the server reports them."""
    from django.utils.formats import number_format

    text = _("The local AI answered in %(seconds)s seconds.") % {"seconds": number_format(answer.seconds, 1)}
    if answer.prompt_per_second and answer.tokens_per_second:
        text += " " + _("It reads %(reading)s and writes %(writing)s tokens per second.") % {
            "reading": number_format(answer.prompt_per_second, 1),
            "writing": number_format(answer.tokens_per_second, 1),
        }
    return text


def store_speed(
    seconds: float, tokens_per_second: float | None, model: str, *, prompt_per_second: float | None = None
) -> None:
    """Keep the result of the speed test for the status (EML-040).

    Only the speed fields are written: an administrator may change the
    uses at the same moment.
    """
    AISettings.load()  # the row exists
    AISettings.objects.filter(pk=1).update(
        local_test_at=timezone.now(),
        local_test_seconds=round(seconds, 2),
        local_test_tokens_per_second=round(tokens_per_second, 1) if tokens_per_second else None,
        local_test_prompt_per_second=round(prompt_per_second, 1) if prompt_per_second else None,
        local_test_model=model[:200],
    )


@module_required(Module.ADMINISTRATION, Level.WRITE)
def provider_edit(request: HttpRequest, provider_pk: int | None = None) -> HttpResponse:
    """Create or change an OpenAI-compatible interface (ADM-017)."""
    provider = get_object_or_404(AIProvider, pk=provider_pk) if provider_pk else None
    form = ProviderForm(request.POST or None, instance=provider)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, _("The interface “%(name)s” was saved.") % {"name": saved.name})
        if form.key_removed:
            messages.warning(request, KEY_REMOVED_TEXT())
        return redirect("ai:settings")
    return render(
        request,
        "ai/provider_form.html",
        {
            "form": form,
            "provider": provider,
            "can_delete": request_rights(request).has_level(Module.ADMINISTRATION, Level.DELETE),
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def provider_delete(request: HttpRequest, provider_pk: int) -> HttpResponse:
    """Delete an interface; uses that chose it are switched off (ADM-017)."""
    provider = get_object_or_404(AIProvider, pk=provider_pk)
    ai_settings = AISettings.load()
    for use in (Use.SUMMARY, Use.DRAFT, Use.INVOICE):
        source, chosen = ai_settings.source_of(use)
        if source == Source.PROVIDER and chosen == provider:
            setattr(ai_settings, f"{use}_source", Source.OFF)
            setattr(ai_settings, f"{use}_provider", None)
    ai_settings.save()
    name = provider.name
    provider.delete()
    messages.success(request, _("The interface “%(name)s” was deleted.") % {"name": name})
    return redirect("ai:settings")


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def provider_check(request: HttpRequest, provider_pk: int) -> HttpResponse:
    """Ask an interface for its models: does it answer, does it know the model (ADM-017)."""
    provider = get_object_or_404(AIProvider, pk=provider_pk)
    try:
        models = available_models(provider_endpoint(provider), timeout=min(provider.timeout_seconds, 15))
    except AIError as error:
        messages.error(request, str(error))
        return redirect("ai:settings")
    if not models or provider.model in models:
        messages.success(request, _("“%(name)s” answers.") % {"name": provider.name})
    else:
        messages.warning(
            request,
            _("“%(name)s” answers, but does not offer the model “%(model)s”. It offers: %(models)s")
            % {"name": provider.name, "model": provider.model, "models": ", ".join(models[:15])},
        )
    return redirect("ai:settings")


@module_required(Module.ADMINISTRATION)
def call_log(request: HttpRequest) -> HttpResponse:
    """Every call to a language model: use, provider, model, duration, sizes – never the content (ADM-017)."""
    page = paginate(request, AICall.objects.select_related("user", "project"))
    return render(request, "ai/calls.html", {"page": page})


# --- The summary in a project ------------------------------------------------------------------------------


def _readable_project(request: HttpRequest, pk: int) -> Project:
    """The project, for who may read its correspondence (EML-029); the project is checked first (AUT-020).

    EML-055: overview, summary and draft read every message – also those with lock, so the price right too.
    """
    project = project_for(request, pk, ProjectAccess.READ)
    mail_services.require_mail_read_all(request_rights(request))
    return project


def summary_context(request: HttpRequest, project: Project, *, job: BackgroundJob | None = None) -> dict[str, Any]:
    """What the block "Überblick" of the correspondence shows (EML-040, EML-044)."""
    rights = request_rights(request)
    project_ids = correspondence.project_ids_for(rights, request.user, project)
    unavailable = ""
    switched_on = is_switched_on(Use.SUMMARY)
    endpoint = None
    if switched_on:
        try:
            endpoint = endpoint_for(Use.SUMMARY)
        except AIError as error:
            unavailable = str(error)
    running = summary.running_job(project)
    shown_job = running or job
    # EML-040: how long "Zusammenfassen" will take – with a warning when it is long.
    found = None
    if endpoint is not None and (shown_job is None or shown_job.is_finished):
        found = summary.estimate_for(project_ids, endpoint)
    return {
        "estimate": found,
        "speed_unknown": endpoint is not None and endpoint.is_local and speeds.speed_of(endpoint) is None,
        "project": project,
        "overview": overview_of(project_ids),
        "shown": summary.shown_summary(project, rights=rights, user=request.user),
        "job": shown_job,
        "job_running": shown_job is not None and not shown_job.is_finished,
        "switched_on": switched_on,
        "unavailable": unavailable,
        "leaves_company": bool(endpoint and endpoint.leaves_company),
        "endpoint": endpoint,
        **_auto_context(request, project),
    }


def _auto_context(request: HttpRequest, project: Project) -> dict[str, Any]:
    """What the block says about the automatic summaries and who may switch them off for this project."""
    rights = request_rights(request)
    ai_settings = AISettings.load()
    customer_id = project.customer_id
    access = getattr(project, "access", None)
    may_write_project = access is not None and access >= ProjectAccess.EDIT
    return {
        "auto_on": auto.consent_state(ai_settings) == "ok",
        "auto_excluded_project": AutoSummaryExclusion.objects.filter(project=project).exists(),
        "auto_excluded_customer": bool(
            customer_id and AutoSummaryExclusion.objects.filter(customer_id=customer_id).exists()
        ),
        "can_switch_project": may_write_project,
        "can_switch_customer": bool(customer_id) and rights.has_level(Module.CUSTOMERS, Level.WRITE),
        "window_start": ai_settings.auto_window_start,
        "window_end": ai_settings.auto_window_end,
    }


@module_required(Module.PROJECTS)
def summary_block(request: HttpRequest, pk: int) -> HttpResponse:
    """The block "Überblick": the short overview and the AI summary; POST starts "Zusammenfassen" (EML-040)."""
    project = _readable_project(request, pk)
    job = None
    error = ""
    if request.method == "POST":
        try:
            job = summary.start(
                project, user=request.user, rights=request_rights(request), include_chat=request.POST.get("chat") == "1"
            )
        except AIError as failure:
            error = str(failure)
        if not request.headers.get("HX-Request"):
            if error:
                messages.error(request, error)
            else:
                messages.success(request, _("The summary is being written. You can go on working meanwhile."))
            return redirect("mail:project_mails", pk=project.pk)
    elif request.GET.get("job", "").isdigit():
        job = BackgroundJob.objects.filter(
            pk=int(request.GET["job"]), kind="ai_summary", params__project=project.pk
        ).first()
    context = summary_context(request, project, job=job)
    context["error"] = error
    # EML-050: the summary is folded on every page load – open only when the block was asking for this job
    # (or started it, and it finished at once) and it is done, so that whoever pressed "Zusammenfassen" sees it.
    context["just_written"] = job is not None and job.is_finished and job.status == "done"
    return render(request, "ai/_summary.html", context)


# --- The reply draft in "Write mail" -----------------------------------------------------------------------


def _writing_project(request: HttpRequest, pk: int) -> Project:
    project = _readable_project(request, pk)
    mail_services.require_mail_write(request_rights(request))
    return project


@require_POST
@module_required(Module.PROJECTS)
def draft_start(request: HttpRequest, pk: int) -> HttpResponse:
    """The button “Entwurf vorschlagen”: start a reply draft in the background (ADM-017)."""
    project = _writing_project(request, pk)
    answer = request.POST.get("answer", "")
    context: dict[str, Any] = {"project": project, "answer": answer, "error": ""}
    try:
        context["job"] = drafts.start(project, user=request.user, mail_pk=int(answer) if answer.isdigit() else None)
    except AIError as error:
        context["error"] = str(error)
    template = "ai/_draft.html" if request.headers.get("HX-Request") else "ai/draft_page.html"
    return render(request, template, context)


@module_required(Module.PROJECTS)
def draft_job(request: HttpRequest, pk: int, job_pk: int) -> HttpResponse:
    """How far the draft got, and the draft – for whoever asked for it (ADM-017)."""
    project = _writing_project(request, pk)
    job = get_object_or_404(BackgroundJob, pk=job_pk, kind="ai_draft", created_by=request.user)
    if job.params.get("project") != project.pk:
        raise PermissionDenied
    context = {"project": project, "job": job, "answer": str(job.params.get("mail", "")), "error": ""}
    if job.status == JobStatus.FAILED:
        context["error"] = job.message
    template = "ai/_draft.html" if request.headers.get("HX-Request") else "ai/draft_page.html"
    return render(request, template, context)


# --- Automatic summaries --------------------------------------------------------------------------


def consent_notice(ai_settings: AISettings) -> dict[str, Any]:
    """What the page says before the automatic summaries are switched on: which provider, which data go, which do not.

    The texts are built from the settings, so that the notice always tells what really happens.
    """
    try:
        endpoint = endpoint_for(Use.SUMMARY)
    except AIError as error:
        return {"endpoint": None, "problem": str(error)}
    sent = [_("Mails of the project and its parts: subject, text without quoted earlier mails, names of the senders")]
    if ai_settings.auto_include_notes:
        sent.append(_("Notes written into the correspondence (phone calls, talks)"))
    if ai_settings.auto_include_chat:
        sent.append(_("Messages of the chat of the project"))
    if ai_settings.auto_include_locked:
        sent.append(_("Messages with lock (prices and calculation)"))
    if ai_settings.send_attachment_names:
        sent.append(_("Names of attached files"))
    sent.append(_("The number and name of the project"))
    removed = [str(label) for key, label in PRIVACY_CHOICES if key in (ai_settings.privacy_remove or [])]
    return {
        "endpoint": endpoint,
        "problem": "",
        "sent": sent,
        "removed": removed,
        "never": [
            _("Prices, calculation and margins"),
            _("Personnel costs and times"),
            _("Contact data and bank data of customers from the master data"),
            _("Files and their content, photos, documents"),
            _("Passwords, tokens, API keys"),
        ],
        "leaves_company": endpoint.leaves_company,
    }


def auto_page_context(request: HttpRequest, form: AutoSettingsForm, **more: Any) -> dict[str, Any]:
    """The context of the page "Automatische Zusammenfassungen"."""
    ai_settings = AISettings.load()
    runs = list(AutoSummaryRun.objects.filter(dry_run=False).select_related("triggered_by")[:20])
    for run in runs:
        run.reason_text = auto.reason_label(run.reason) if run.reason else ""  # type: ignore[attr-defined]
    return {
        "form": form,
        "ai_settings": ai_settings,
        "state": auto.consent_state(ai_settings),
        "notice": consent_notice(ai_settings),
        "runs": runs,
        "can_write": _may_change(request),
        **more,
    }


@module_required(Module.ADMINISTRATION)
def auto_settings(request: HttpRequest) -> HttpResponse:
    """Einstellungen → KI → Automatische Zusammenfassungen: opt in, the caps, the data classes, the runs."""
    ai_settings = AISettings.load()
    form = AutoSettingsForm(request.POST or None, instance=ai_settings, user=request.user)
    if request.method == "POST":
        _require_change(request)
        if form.is_valid():
            form.save()
            messages.success(request, _("The settings of the automatic summaries were saved."))
            return redirect("ai:auto_settings")
    return render(request, "ai/auto_settings.html", auto_page_context(request, form))


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def auto_preview(request: HttpRequest) -> HttpResponse:
    """Show what the next run would summarise (dry run: no model is asked, nothing is stored)."""
    record = auto.run(dry_run=True, ignore_window=True, user=request.user)
    form = AutoSettingsForm(instance=AISettings.load(), user=request.user)
    return render(request, "ai/auto_settings.html", auto_page_context(request, form, preview=record))


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def auto_run_now(request: HttpRequest) -> HttpResponse:
    """Start a run now, outside the window – a task of its own; only if the summaries are switched on."""
    from rentalars.core.jobs import start_job

    ai_settings = AISettings.load()
    if auto.consent_state(ai_settings) != "ok":
        messages.error(request, _("Switch the automatic summaries on first, with the provider you agree to."))
        return redirect("ai:auto_settings")
    start_job("ai_auto_summaries", {"now": True}, user=request.user, title=_("Automatic AI summaries"))
    messages.success(request, _("The run was started. The result appears in the list of runs."))
    return redirect("ai:auto_settings")


@require_POST
@module_required(Module.PROJECTS)
def auto_switch_project(request: HttpRequest, pk: int) -> HttpResponse:
    """Switch "no automatic AI summaries" on or off for a project; the people who change the project may."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    mail_services.require_mail_read_all(request_rights(request))
    auto.set_exclusion(project=project, excluded=request.POST.get("excluded") == "1", user=request.user)
    if request.headers.get("HX-Request"):
        return render(request, "ai/_summary.html", {**summary_context(request, project), "error": ""})
    return redirect("mail:project_mails", pk=project.pk)


@require_POST
@module_required(Module.CUSTOMERS, Level.WRITE)
def auto_switch_customer(request: HttpRequest, pk: int, project_pk: int) -> HttpResponse:
    """The same for all projects of a customer; asked from the block of one of his projects."""
    from rentalars.customers.models import Customer

    customer = get_object_or_404(Customer, pk=pk)
    project = project_for(request, project_pk, ProjectAccess.READ)
    mail_services.require_mail_read_all(request_rights(request))
    if project.customer_id != customer.pk:
        raise PermissionDenied
    auto.set_exclusion(customer=customer, excluded=request.POST.get("excluded") == "1", user=request.user)
    if request.headers.get("HX-Request"):
        return render(request, "ai/_summary.html", {**summary_context(request, project), "error": ""})
    return redirect("mail:project_mails", pk=project.pk)
