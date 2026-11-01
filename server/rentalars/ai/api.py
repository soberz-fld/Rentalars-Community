# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the AI (EML-040, EML-044, ADM-017; API-002).

In a project or service case (rights: who may read the correspondence, EML-029):

* ``GET  /projects/{id}/correspondence-summary`` – the short overview without AI, the stored AI summary
  (with ``stale``), a summary being written and whether summaries are switched on
* ``POST /projects/{id}/correspondence-summary`` – start "Zusammenfassen" (202, the task in
  ``/jobs/{id}``); ``include_chat`` takes the chat in
* ``PATCH /projects/{id}/correspondence-summary`` – ``{"auto_summaries": false}`` switches the automatic
  summaries off for this project (who may change the project)
* ``GET/PATCH /customers/{id}/ai-summaries`` – the same switch for all projects of a customer
* ``POST /projects/{id}/mails/reply-draft`` – a reply draft by AI (who may write mails); 202, the
  draft arrives in ``result.text`` of ``/jobs/{id}``

The text of a summary is **untrusted**: it comes from a model that read mails anybody could write. The API gives it
as plain text (``format: "plain"``, tags, images and links already made inert); a client must not render it as HTML
or Markdown.

The settings (module "Administration"):

* ``GET/PATCH /ai/settings`` – which provider serves which use, and the state of the local AI
* ``POST /ai/local/speed-test`` – a test prompt to the local AI
* ``GET/POST /ai/providers``, ``GET/PUT/PATCH/DELETE /ai/providers/{id}`` – the OpenAI-compatible
  interfaces; the API key can be set (``api_key``) or removed (``""``), never read
* ``GET  /ai/calls`` – the log of the calls, without content
* ``GET/PATCH /ai/auto-summaries`` – the automatic summaries: opt in, window, caps, statuses, data classes
* ``GET  /ai/auto-summaries/runs`` – the runs of the nightly job with their errors
* ``POST /ai/auto-summaries/dry-run`` – what the next run would summarise (no model is asked)
* ``POST /ai/auto-summaries/run`` – start a run now (a task, 202)
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.ai import auto, correspondence, drafts, summary
from rentalars.ai import speed as speeds
from rentalars.ai.client import AIError, endpoint_for, is_switched_on, local_endpoint, speed_test, validate_base_url
from rentalars.ai.forms import AutoSettingsForm, decode_source, encode_source
from rentalars.ai.local import LocalConfigError, local_server
from rentalars.ai.models import AICall, AIProvider, AISettings, AutoSummaryExclusion, AutoSummaryRun, Use
from rentalars.ai.overview import Overview, overview_of
from rentalars.api.inputs import str_or_400
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of
from rentalars.mail import services as mail_services
from rentalars.projects.access import ProjectAccess, project_for


class AIUnavailable(APIException):
    """The use is switched off, its server is missing or does not answer, or there is nothing to do."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "ai_unavailable"
    default_detail = "The AI cannot do this now."


def _project(request: Request, project_pk: int) -> Any:
    """The project, for a caller who may read its correspondence; the project is checked first (AUT-020).

    EML-055: overview, summary and draft read every message – also those with lock, so the price right too.
    """
    project = project_for(request, project_pk, ProjectAccess.READ)
    mail_services.require_mail_read_all(request_rights(request))
    return project


def _auto_document(project: Any) -> dict[str, Any]:
    """Whether the automatic summaries are on and whether this project, or its customer, is excluded."""
    ai_settings = AISettings.load()
    customer_excluded = bool(
        project.customer_id and AutoSummaryExclusion.objects.filter(customer_id=project.customer_id).exists()
    )
    project_excluded = AutoSummaryExclusion.objects.filter(project=project).exists()
    return {
        "on": auto.consent_state(ai_settings) == "ok",
        "project_excluded": project_excluded,
        "customer_excluded": customer_excluded,
        "window": [ai_settings.auto_window_start.strftime("%H:%M"), ai_settings.auto_window_end.strftime("%H:%M")],
    }


def overview_document(overview: Overview) -> dict[str, Any]:
    """The short overview without AI as JSON (EML-044)."""

    def mail_ref(mail: Any) -> dict[str, Any]:
        return {"id": mail.pk, "project": mail.project_id, "subject": mail.subject, "date": mail.date}

    return {
        "mail_count": overview.mail_count,
        "received": overview.received,
        "sent": overview.sent,
        "first_date": overview.first.date if overview.first else None,
        "last_date": overview.last.date if overview.last else None,
        "last_writer": overview.last_writer,
        "last_is_incoming": overview.last_is_incoming,
        "writers": [{"name": person.name, "mails": person.written} for person in overview.writers],
        "recipients": overview.recipients,
        "dates": [{"date": item.date, "text": item.text, "mail": mail_ref(item.mail)} for item in overview.dates],
        "amounts": [{"text": item.text, "mail": mail_ref(item.mail)} for item in overview.amounts],
        "questions": [{"text": item.text, "mail": mail_ref(item.mail)} for item in overview.questions],
        "attachments": [
            {"id": item.pk, "filename": item.filename, "mail": mail_ref(item.mail)} for item in overview.attachments
        ],
        "more_attachments": overview.more_attachments,
    }


class CorrespondenceSummaryView(ModuleAPIView):
    """``/projects/{id}/correspondence-summary`` – overview and AI summary of the correspondence (EML-040, EML-044)."""

    module = Module.PROJECTS
    schema_tag = "ai"
    # Summarising is reading: who may read the correspondence may start it.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    @extend_schema(responses={200: inline_serializer("CorrespondenceSummary", {"overview": serializers.DictField()})})
    def get(self, request: Request, project_pk: int) -> Response:
        """The overview without AI, the stored summary and its state."""
        project = _project(request, project_pk)
        rights = request_rights(request)
        shown = summary.shown_summary(project, rights=rights, user=request.user)
        stored = shown.summary
        running = summary.running_job(project)
        return Response(
            {
                "overview": overview_document(
                    overview_of(correspondence.project_ids_for(rights, request.user, project))
                ),
                "summary": None
                if stored is None
                else {
                    "text": stored.text,
                    "made_by_ai": True,
                    "model": stored.model,
                    "provider": stored.provider_label,
                    "is_local": stored.is_local,
                    "language": stored.language,
                    "created_at": stored.created_at,
                    "mail_count": stored.mail_count,
                    "include_chat": stored.include_chat,
                    "stale": shown.stale,
                    "new_mails": shown.new_mails,
                    # How it was made; the text is plain text, never HTML or Markdown to render.
                    "format": "plain",
                    "automatic": stored.is_automatic,
                    "covers_locked": stored.covers_locked,
                    "dropped_entries": stored.dropped_entries,
                },
                "versions": [
                    {
                        "id": version.pk,
                        "text": version.text,
                        "format": "plain",
                        "model": version.model,
                        "provider": version.provider_label,
                        "created_at": version.created_at,
                        "automatic": version.is_automatic,
                    }
                    for version in shown.versions
                ],
                "auto_summaries": _auto_document(project),
                "summary_hidden": shown.hidden,
                "running_job": running.pk if running else None,
                "switched_on": is_switched_on(Use.SUMMARY),
                # EML-040: how long "Zusammenfassen" would take; null without a measured speed.
                "estimate": _estimate(request, project) if running is None else None,
            }
        )

    @extend_schema(
        request=inline_serializer("SummaryAutoSwitch", {"auto_summaries": serializers.BooleanField()}),
        responses={200: inline_serializer("SummaryAuto", {"on": serializers.BooleanField()})},
    )
    def patch(self, request: Request, project_pk: int) -> Response:
        """Switch the automatic summaries off (``false``) or on (``true``) for this project."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        mail_services.require_mail_read_all(request_rights(request))
        value = body_of(request).get("auto_summaries")
        if not isinstance(value, bool):
            raise serializers.ValidationError({"auto_summaries": [_("Send true or false.")]})
        auto.set_exclusion(project=project, excluded=not value, user=request.user)
        return Response(_auto_document(project))

    @extend_schema(
        request=inline_serializer("SummaryStart", {"include_chat": serializers.BooleanField(required=False)}),
        responses={202: inline_serializer("SummaryStarted", {"job": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Start the summary in the background; ``/jobs/{job}`` tells how far it got."""
        project = _project(request, project_pk)
        body = body_of(request)
        include_chat = str(body.get("include_chat", "")).lower() in {"1", "true", "yes", "on"}
        try:
            job = summary.start(project, user=request.user, rights=request_rights(request), include_chat=include_chat)
        except AIError as error:
            raise AIUnavailable(str(error)) from error
        return Response({"job": job.pk, "status": job.status}, status=status.HTTP_202_ACCEPTED)


class ReplyDraftView(ModuleAPIView):
    """``POST /projects/{id}/mails/reply-draft`` – a reply draft by AI (ADM-017)."""

    module = Module.PROJECTS
    schema_tag = "ai"
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    @extend_schema(
        request=inline_serializer("ReplyDraftStart", {"answer_to": serializers.IntegerField(required=False)}),
        responses={202: inline_serializer("ReplyDraftStarted", {"job": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Start the draft for the mail ``answer_to`` (else the newest received one); it arrives in ``/jobs/{job}``."""
        project = _project(request, project_pk)
        mail_services.require_mail_write(request_rights(request))
        answer = body_of(request).get("answer_to")
        try:
            job = drafts.start(project, user=request.user, mail_pk=int(answer) if str(answer or "").isdigit() else None)
        except AIError as error:
            raise AIUnavailable(str(error)) from error
        return Response({"job": job.pk, "status": job.status}, status=status.HTTP_202_ACCEPTED)


# --- Settings ----------------------------------------------------------------------------------------------


def _local_document() -> dict[str, Any]:
    from rentalars.ai.views import local_status

    state = local_status()
    server = state.get("server")
    ai_settings = AISettings.load()
    return {
        "installed": state["installed"],
        "error": state["error"],
        "reachable": state["reachable"],
        "reach_error": state["reach_error"],
        "model": server.model if server else None,
        "model_name": server.label if server else None,
        "model_licence": server.model_licence if server else None,
        "server": server.server if server else None,
        "url": server.url if server else None,
        "context": server.context if server else None,
        "speed_test": {
            "at": ai_settings.local_test_at,
            "seconds": ai_settings.local_test_seconds,
            "tokens_per_second": ai_settings.local_test_tokens_per_second,
            # EML-040: reading the prompt, apart from writing (llama.cpp timings).
            "prompt_tokens_per_second": ai_settings.local_test_prompt_per_second,
        }
        if ai_settings.local_test_at
        else None,
        # EML-040: the processor, a typical summary, and what would make it faster.
        "cpu": {
            "model": state["cpu"].model,
            "physical_cores": state["cpu"].physical,
            "logical_cores": state["cpu"].logical,
            "missing": state["cpu"].missing,
            "virtual_machine": state["cpu"].in_vm,
        },
        "threads": server.threads if server else None,
        "typical_summary": speeds.as_json(state.get("typical")),
        "advice": {"texts": state["advice"].texts, "command": state["advice"].command},
    }


def _estimate(request: Request, project: Any) -> dict[str, Any] | None:
    """How long the summary of the project would take, as the page says it."""
    try:
        endpoint = endpoint_for(Use.SUMMARY)
    except AIError:
        return None
    project_ids = correspondence.project_ids_for(request_rights(request), request.user, project)
    return speeds.as_json(summary.estimate_for(project_ids, endpoint))


def settings_document() -> dict[str, Any]:
    """``/ai/settings``: per use ``off``, ``local`` or ``p<id>`` of a provider, and the local AI."""
    ai_settings = AISettings.load()
    return {
        "summary": encode_source(ai_settings.summary_source, ai_settings.summary_provider),
        "draft": encode_source(ai_settings.draft_source, ai_settings.draft_provider),
        # MAT-062: reading an uploaded invoice.
        "invoice": encode_source(ai_settings.invoice_source, ai_settings.invoice_provider),
        "template_suggestions": "later",
        "local": _local_document(),
    }


class AISettingsView(ModuleAPIView):
    """``/ai/settings`` – which provider serves which use (EML-040, ADM-017)."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"

    @extend_schema(responses={200: inline_serializer("AISettings", {"summary": serializers.CharField()})})
    def get(self, request: Request) -> Response:
        """The uses and the state of the local AI."""
        return Response(settings_document())

    @extend_schema(
        request=inline_serializer(
            "AISettingsChange",
            {
                "summary": serializers.CharField(required=False, help_text="off, local or p<id> of a provider"),
                "draft": serializers.CharField(required=False, help_text="off, local or p<id> of a provider"),
                "invoice": serializers.CharField(required=False, help_text="off, local or p<id> of a provider"),
            },
        ),
        responses={200: inline_serializer("AISettingsChanged", {"summary": serializers.CharField()})},
    )
    def patch(self, request: Request) -> Response:
        """Choose the provider of a use: ``off``, ``local`` or ``p<id>``."""
        body = body_of(request)
        ai_settings = AISettings.load()
        errors: dict[str, list[str]] = {}
        for use in ("summary", "draft", "invoice"):
            if use not in body:
                continue
            value = str(body.get(use) or "")
            source, provider = decode_source(value)
            if encode_source(source, provider) != value:
                errors[use] = [
                    _("Unknown choice “%(value)s”: use off, local or p followed by the ID of an interface.")
                    % {"value": value}
                ]
                continue
            setattr(ai_settings, f"{use}_source", source)
            setattr(ai_settings, f"{use}_provider", provider)
        if errors:
            raise serializers.ValidationError(errors)
        ai_settings.save()
        return Response(settings_document())


class LocalSpeedTestView(ModuleAPIView):
    """``POST /ai/local/speed-test`` – a short test prompt to the local AI (EML-040)."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"

    @extend_schema(
        request=None,
        responses={200: inline_serializer("SpeedTest", {"seconds": serializers.FloatField()})},
    )
    def post(self, request: Request) -> Response:
        """Measure how fast the local AI answers; the result is kept for the settings page."""
        from rentalars.ai.views import store_speed

        try:
            server = local_server()
            if server is None:
                raise AIError(_("The local AI is not installed. The operator installs it on the server."))
            answer = speed_test(local_endpoint(server), user=request.user)
        except (AIError, LocalConfigError) as error:
            raise AIUnavailable(str(error)) from error
        store_speed(answer.seconds, answer.tokens_per_second, server.model, prompt_per_second=answer.prompt_per_second)
        return Response(
            {
                "seconds": round(answer.seconds, 2),
                "tokens_per_second": answer.tokens_per_second,
                "prompt_tokens_per_second": answer.prompt_per_second,
                "model": server.model,
            }
        )


class AIProviderSerializer(serializers.ModelSerializer):
    """An OpenAI-compatible interface (ADM-017). ``api_key`` is write-only; ``""`` removes it."""

    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=True)
    has_api_key = serializers.BooleanField(read_only=True)
    leaves_company = serializers.BooleanField(read_only=True)
    #: ADM-017: the address now leads to another server and no new key came with it – the stored one was removed.
    api_key_removed = serializers.SerializerMethodField()

    class Meta:
        model = AIProvider
        fields = [
            "id",
            "name",
            "base_url",
            "model",
            "api_key",
            "has_api_key",
            "timeout_seconds",
            "context_tokens",
            "leaves_company",
            "api_key_removed",
        ]

    def get_api_key_removed(self, provider: AIProvider) -> str:
        """Empty, or the text saying that the stored key was removed with the change of server."""
        from rentalars.ai.views import KEY_REMOVED_TEXT

        return KEY_REMOVED_TEXT() if getattr(provider, "api_key_removed", False) else ""

    def validate_base_url(self, value: str) -> str:
        """An address the guard lets through (NFA-071)."""
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_base_url(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return value.strip().rstrip("/")

    def _store(self, provider: AIProvider, values: dict[str, Any]) -> AIProvider:
        key = values.pop("api_key", None)
        new_url = values.pop("base_url", provider.base_url)
        for name, value in values.items():
            setattr(provider, name, value)
        # ADM-017: a key never follows a changed server; without a new key it is removed.
        provider.api_key_removed = provider.take_address(new_url, new_key=key)  # type: ignore[attr-defined]
        provider.full_clean()
        provider.save()
        return provider

    def create(self, validated_data: dict[str, Any]) -> AIProvider:
        """Create it; the key is stored encrypted."""
        return self._store(AIProvider(), dict(validated_data))

    def update(self, instance: AIProvider, validated_data: dict[str, Any]) -> AIProvider:
        """Change it; a key is only replaced when one is sent."""
        return self._store(instance, dict(validated_data))


class AIProviderViewSet(ModuleViewSet):
    """``/ai/providers`` – OpenAI-compatible interfaces (ADM-017). Deleting switches off the uses that chose it."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"
    serializer_class = AIProviderSerializer
    queryset = AIProvider.objects.all()

    def perform_destroy(self, instance: AIProvider) -> None:
        """Switch off the uses that chose it, then delete it."""
        ai_settings = AISettings.load()
        for use in (Use.SUMMARY, Use.DRAFT, Use.INVOICE):
            if getattr(ai_settings, f"{use}_provider_id") == instance.pk:
                setattr(ai_settings, f"{use}_source", "off")
                setattr(ai_settings, f"{use}_provider", None)
        ai_settings.save()
        instance.delete()


class AICallListView(ModuleAPIView):
    """``GET /ai/calls`` – the calls to language models, newest first; never their content (ADM-017)."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"

    @extend_schema(responses={200: inline_serializer("AICalls", {"id": serializers.IntegerField()}, many=True)})
    def get(self, request: Request) -> Response:
        """The newest 500 calls."""
        calls = AICall.objects.select_related("user")[:500]
        return Response([call.as_json() for call in calls])


# --- Automatic summaries --------------------------------------------------------------------------


class CustomerAutoSummaryView(ModuleAPIView):
    """``/customers/{id}/ai-summaries`` – no automatic AI summaries for any project of a customer."""

    module = Module.CUSTOMERS
    schema_tag = "ai"

    @extend_schema(responses={200: inline_serializer("CustomerAuto", {"auto_summaries": serializers.BooleanField()})})
    def get(self, request: Request, customer_pk: int) -> Response:
        """Whether the customer's projects get automatic summaries."""
        customer = _customer(customer_pk)
        return Response({"auto_summaries": not AutoSummaryExclusion.objects.filter(customer=customer).exists()})

    @extend_schema(
        request=inline_serializer("CustomerAutoSwitch", {"auto_summaries": serializers.BooleanField()}),
        responses={200: inline_serializer("CustomerAutoSwitched", {"auto_summaries": serializers.BooleanField()})},
    )
    def patch(self, request: Request, customer_pk: int) -> Response:
        """``{"auto_summaries": false}`` excludes the customer's projects; ``true`` takes the exclusion off."""
        customer = _customer(customer_pk)
        value = body_of(request).get("auto_summaries")
        if not isinstance(value, bool):
            raise serializers.ValidationError({"auto_summaries": [_("Send true or false.")]})
        auto.set_exclusion(customer=customer, excluded=not value, user=request.user)
        return Response({"auto_summaries": value})


def _customer(pk: int) -> Any:
    """The customer, or 404."""
    from django.shortcuts import get_object_or_404

    from rentalars.customers.models import Customer

    return get_object_or_404(Customer, pk=pk)


def auto_document() -> dict[str, Any]:
    """``/ai/auto-summaries``: the settings of the automatic summaries, the state of the opt-in and the notice."""
    from rentalars.ai.views import consent_notice

    ai_settings = AISettings.load()
    notice = consent_notice(ai_settings)
    endpoint = notice.get("endpoint")
    return {
        "enabled": ai_settings.auto_enabled,
        "state": auto.consent_state(ai_settings),
        "enabled_at": ai_settings.auto_enabled_at,
        "enabled_by": str(ai_settings.auto_enabled_by) if ai_settings.auto_enabled_by_id else None,
        "window_start": ai_settings.auto_window_start.strftime("%H:%M"),
        "window_end": ai_settings.auto_window_end.strftime("%H:%M"),
        "max_per_run": ai_settings.auto_max_per_run,
        "token_budget": ai_settings.auto_token_budget,
        "project_statuses": ai_settings.auto_project_statuses,
        "case_statuses": ai_settings.auto_case_statuses,
        "min_interval_hours": ai_settings.auto_min_interval_hours,
        "min_mails": ai_settings.auto_min_mails,
        "keep_versions": ai_settings.auto_keep_versions,
        "include_notes": ai_settings.auto_include_notes,
        "include_chat": ai_settings.auto_include_chat,
        "include_locked": ai_settings.auto_include_locked,
        "send_attachment_names": ai_settings.send_attachment_names,
        "remove": ai_settings.privacy_remove,
        "max_input_chars": ai_settings.max_input_chars,
        "manual_per_hour": ai_settings.manual_per_hour,
        "notice": {
            "provider": endpoint.label if endpoint else None,
            "local": endpoint.is_local if endpoint else None,
            "leaves_company": endpoint.leaves_company if endpoint else None,
            "sent": [str(text) for text in notice.get("sent", [])],
            "removed": notice.get("removed", []),
            "never": [str(text) for text in notice.get("never", [])],
            "problem": notice.get("problem", ""),
        },
    }


_BOOLEAN_FIELDS = (
    "auto_include_notes",
    "auto_include_chat",
    "auto_include_locked",
    "send_attachment_names",
)
_LIST_FIELDS = ("auto_project_statuses", "auto_case_statuses", "privacy_remove")
_NUMBER_FIELDS = (
    "auto_max_per_run",
    "auto_token_budget",
    "auto_min_interval_hours",
    "auto_min_mails",
    "auto_keep_versions",
    "max_input_chars",
    "manual_per_hour",
)
#: The name in the API → the field of the form.
_API_NAMES = {
    "enabled": "auto_enabled",
    "window_start": "auto_window_start",
    "window_end": "auto_window_end",
    "max_per_run": "auto_max_per_run",
    "token_budget": "auto_token_budget",
    "project_statuses": "auto_project_statuses",
    "case_statuses": "auto_case_statuses",
    "min_interval_hours": "auto_min_interval_hours",
    "min_mails": "auto_min_mails",
    "keep_versions": "auto_keep_versions",
    "include_notes": "auto_include_notes",
    "include_chat": "auto_include_chat",
    "include_locked": "auto_include_locked",
    "send_attachment_names": "send_attachment_names",
    "remove": "privacy_remove",
    "max_input_chars": "max_input_chars",
    "manual_per_hour": "manual_per_hour",
}


class AutoSummariesView(ModuleAPIView):
    """``/ai/auto-summaries`` – the automatic summaries. Switching on needs ``"consent": true``."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"

    @extend_schema(responses={200: inline_serializer("AutoSummaries", {"enabled": serializers.BooleanField()})})
    def get(self, request: Request) -> Response:
        """The settings and the notice that says which provider gets which data."""
        return Response(auto_document())

    @extend_schema(
        request=inline_serializer("AutoSummariesChange", {"enabled": serializers.BooleanField(required=False)}),
        responses={200: inline_serializer("AutoSummariesChanged", {"enabled": serializers.BooleanField()})},
    )
    def patch(self, request: Request) -> Response:
        """Change settings; the form of the settings page validates (the same rules)."""
        body = body_of(request)
        unknown = sorted(set(body) - set(_API_NAMES) - {"consent"})
        if unknown:
            raise serializers.ValidationError({name: [_("Unknown setting.")] for name in unknown})
        ai_settings = AISettings.load()
        data: dict[str, Any] = {}
        current = auto_document()
        for api_name, field in _API_NAMES.items():
            value = body.get(api_name, current[api_name])
            if field in _LIST_FIELDS:
                data[field] = value if isinstance(value, list) else []
            elif field in _BOOLEAN_FIELDS or field == "auto_enabled":
                if value in (True, "true", "True", "1", 1, "on"):
                    data[field] = "on"
            elif field in ("auto_window_start", "auto_window_end"):
                # (hostile input; R4-2e) A time is a text "HH:MM"; anything else is a 400, never a 500.
                data[field] = str_or_400(value, api_name)
            else:
                data[field] = value
        if body.get("consent") in (True, "true", "True", "1", 1, "on"):
            data["consent"] = "on"
        form = AutoSettingsForm(data, instance=ai_settings, user=request.user)
        if not form.is_valid():
            raise serializers.ValidationError(
                {
                    _API_NAMES_REVERSE.get(name, name): [str(error) for error in errors]
                    for name, errors in form.errors.items()
                }
            )
        form.save()
        return Response(auto_document())


_API_NAMES_REVERSE = {field: name for name, field in _API_NAMES.items()} | {"__all__": "detail"}


class AutoSummaryRunListView(ModuleAPIView):
    """``GET /ai/auto-summaries/runs`` – the runs of the nightly job, newest first, with their errors."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"

    @extend_schema(responses={200: inline_serializer("AutoSummaryRuns", {"id": serializers.IntegerField()}, many=True)})
    def get(self, request: Request) -> Response:
        """The newest 100 runs."""
        return Response([run.as_json() for run in AutoSummaryRun.objects.filter(dry_run=False)[:100]])


class AutoSummaryDryRunView(ModuleAPIView):
    """``POST /ai/auto-summaries/dry-run`` – what the next run would summarise; no model is asked."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"

    @extend_schema(
        request=None, responses={200: inline_serializer("AutoDryRun", {"candidates": serializers.IntegerField()})}
    )
    def post(self, request: Request) -> Response:
        """List the projects and service cases that would get a summary."""
        record = auto.run(dry_run=True, ignore_window=True, user=request.user)
        return Response({"candidates": record.candidates if record else 0, "details": record.details if record else []})


class AutoSummaryRunNowView(ModuleAPIView):
    """``POST /ai/auto-summaries/run`` – start a run now, outside the window; 202, a task."""

    module = Module.ADMINISTRATION
    schema_tag = "ai"

    @extend_schema(
        request=None, responses={202: inline_serializer("AutoRunStarted", {"job": serializers.IntegerField()})}
    )
    def post(self, request: Request) -> Response:
        """Start the run as a background task; the result appears in ``/ai/auto-summaries/runs``."""
        from rentalars.core.jobs import start_job

        if auto.consent_state(AISettings.load()) != "ok":
            raise AIUnavailable(_("Switch the automatic summaries on first, with the provider you agree to."))
        job = start_job("ai_auto_summaries", {"now": True}, user=request.user, title=_("Automatic AI summaries"))
        return Response({"job": job.pk, "status": job.status}, status=status.HTTP_202_ACCEPTED)
