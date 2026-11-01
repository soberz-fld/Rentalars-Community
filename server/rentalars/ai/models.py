# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings, providers, summaries and the call log of the AI (EML-040, EML-044, ADM-017).

* :class:`AISettings` – which provider serves which use: the summary of the
  correspondence ("local AI" or a provider; off until an administrator
  switches it on), the reply draft (off, no provider) and (MAT-062)
  reading invoices for "Kauf einpflegen" (off). Template suggestions
  (PRJ-091) are only listed as "later".
* :class:`AIProvider` – an OpenAI-compatible interface: base URL, model,
  API key (stored encrypted, like the mailbox passwords), timeout and the
  size of the model's context. Local servers (Ollama, LM Studio, vLLM) and
  cloud services alike.
* :class:`AISummary` – the summary of a project's correspondence, one per
  project, with the newest mail it covers (to say when it is out of date),
  the model and the date.
* :class:`AICall` – one call to a language model: use, provider, model,
  duration and sizes – never the content.

The local AI itself is not a row here: the operator installs it and the
command writes where it listens into a file next to the configuration file
(:mod:`rentalars.ai.local`).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel
from rentalars.core.crypto import SecretUnreadableError, decrypt_secret, encrypt_secret
from rentalars.core.models import SingletonModel


def address_origin(url: str) -> tuple[str, str, int | None]:
    """Scheme, host and port of an address – the server a key belongs to (ports filled in for http and https)."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit((url or "").strip())
        scheme = parts.scheme.lower()
        port = parts.port or {"http": 80, "https": 443}.get(scheme)
        return scheme, (parts.hostname or "").lower().rstrip("."), port
    except ValueError:
        return "", url, None


def default_project_statuses() -> list[str]:
    """The statuses of projects that get automatic summaries – the open ones, not closed or cancelled."""
    return ["inquiry", "option", "confirmed_open", "confirmed", "out", "returned"]


def default_case_statuses() -> list[str]:
    """The statuses of service cases that get automatic summaries – open, in progress, waiting, closing."""
    return ["open", "in_progress", "waiting", "closing"]


def default_remove() -> list[str]:
    """The classes of data taken out of texts before they go to a model (``rentalars.ai.privacy``)."""
    return ["iban", "card", "secret", "email", "phone"]


def window_start() -> datetime.time:
    """The night begins at 1:00."""
    return datetime.time(1, 0)


def window_end() -> datetime.time:
    """And ends at 5:00."""
    return datetime.time(5, 0)


class Use(models.TextChoices):
    """What a language model is used for (EML-040, ADM-017)."""

    SUMMARY = "summary", _("Summary of the correspondence")
    DRAFT = "draft", _("Reply draft for mails")
    # MAT-062 (MAT-019): supplier, number, date and positions from an uploaded invoice.
    INVOICE = "invoice", _("Reading invoices")
    TEST = "test", _("Test")


class Source(models.TextChoices):
    """Who serves a use: nobody, the local AI on this machine, or a provider of the list."""

    OFF = "off", _("Off")
    LOCAL = "local", _("Local AI")
    PROVIDER = "provider", _("Provider")


class AIProvider(AuditedModel):
    """An OpenAI-compatible interface for language models (ADM-017).

    The base URL ends before ``/chat/completions``, e.g.
    ``https://api.example.com/v1`` or ``http://192.168.1.30:11434/v1`` for
    Ollama on another computer of the company. Calls go through the network
    guard (NFA-071): an internal address needs ``[network] allow_internal``.
    """

    name = models.CharField(_("name"), max_length=100, unique=True)
    base_url = models.CharField(
        _("base URL"),
        max_length=300,
        help_text=_("The address the interface answers at, ending in /v1 for most servers."),
    )
    model = models.CharField(_("model"), max_length=200, help_text=_("The name of the model as the server knows it."))
    api_key_encrypted = models.TextField(_("API key"), blank=True, editable=False)
    timeout_seconds = models.PositiveSmallIntegerField(
        _("timeout in seconds"),
        default=120,
        validators=[MinValueValidator(5), MaxValueValidator(900)],
        # EML-040: the answer streams in; the limit is a silence, not the whole answer.
        help_text=_("How long Rentalars waits when the server sends nothing – the answer itself may take longer."),
    )
    context_tokens = models.PositiveIntegerField(
        _("context size in tokens"),
        default=8192,
        validators=[MinValueValidator(2048), MaxValueValidator(2_000_000)],
        help_text=_("How much text the model takes at once; long correspondence is summarised in parts."),
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    audit_exclude = frozenset({"api_key_encrypted", "created_at"})

    class Meta:
        verbose_name = _("AI provider")
        verbose_name_plural = _("AI providers")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def api_key(self) -> str:
        """The API key in plain text; empty if none is stored.

        Raises:
            SecretUnreadableError: The key was stored with another ``secret_key``.
        """
        return decrypt_secret(self.api_key_encrypted)

    @api_key.setter
    def api_key(self, value: str) -> None:
        self.api_key_encrypted = encrypt_secret(value)

    @property
    def has_api_key(self) -> bool:
        """Whether a key is stored (it is never shown again)."""
        return bool(self.api_key_encrypted)

    @property
    def api_key_readable(self) -> bool:
        """Whether the stored key can still be decrypted (``secret_key`` unchanged)."""
        try:
            self.api_key  # noqa: B018 - decrypting is the check
        except SecretUnreadableError:
            return False
        return True

    def take_address(self, new_url: str, *, new_key: str | None) -> bool:
        """Set a new base URL; the stored key does not follow it to another server (ADM-017, NFA-072).

        When scheme, host or port change and no new key comes with the
        change, the stored key is removed: it was given for the old server
        and must never be sent to another one. Returns whether it was removed.
        """
        moved = bool(self.pk) and address_origin(self.base_url) != address_origin(new_url)
        self.base_url = new_url
        if new_key is not None:
            self.api_key = new_key
            return False
        if moved and self.has_api_key:
            self.api_key = ""
            return True
        return False

    @property
    def leaves_company(self) -> bool:
        """Whether texts sent here leave the company's network – a cloud service (ADM-017).

        Internal addresses are reached only when the operator allows them
        (NFA-071); whatever he did not allow is therefore on the internet.
        """
        from rentalars.ai.client import address_leaves_company

        return address_leaves_company(self.base_url)


class AISettings(SingletonModel):
    """Which provider serves which use (EML-040, EML-044, ADM-017). Everything is off at first."""

    summary_source = models.CharField(
        _("summary of the correspondence"), max_length=10, choices=Source.choices, default=Source.OFF
    )
    summary_provider = models.ForeignKey(
        AIProvider,
        verbose_name=_("provider of the summaries"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    draft_source = models.CharField(_("reply draft"), max_length=10, choices=Source.choices, default=Source.OFF)
    draft_provider = models.ForeignKey(
        AIProvider,
        verbose_name=_("provider of the reply drafts"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # MAT-062: reading an uploaded invoice for "Kauf einpflegen" – off until an administrator chooses.
    invoice_source = models.CharField(_("reading invoices"), max_length=10, choices=Source.choices, default=Source.OFF)
    invoice_provider = models.ForeignKey(
        AIProvider,
        verbose_name=_("provider for reading invoices"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    #: The last speed test of the local AI (EML-040): when, how many tokens per second, how long in all.
    local_test_at = models.DateTimeField(null=True, blank=True, editable=False)
    #: Generation: tokens written per second; reading: tokens of the prompt per second.
    #: Set by the speed test and kept up to date by every call of the local AI that reports its timings.
    local_test_tokens_per_second = models.FloatField(null=True, blank=True, editable=False)
    local_test_prompt_per_second = models.FloatField(null=True, blank=True, editable=False)
    local_test_seconds = models.FloatField(null=True, blank=True, editable=False)
    local_test_model = models.CharField(max_length=200, blank=True, editable=False)

    # --- Information security of the summaries (data classes, caps) -----------------------------------
    #: The classes of data taken out of every text before it goes to a model (``rentalars.ai.privacy.CLASSES``).
    privacy_remove = models.JSONField(_("taken out of texts"), default=default_remove, blank=True)
    #: Whether the names of attached files go to the model (they can say more than the summary needs).
    send_attachment_names = models.BooleanField(_("names of attached files"), default=True)
    #: The most characters of correspondence one summary reads; older mails are left out (a cap on the cost).
    max_input_chars = models.PositiveIntegerField(
        _("longest text per summary"),
        default=150_000,
        validators=[MinValueValidator(2000), MaxValueValidator(2_000_000)],
        help_text=_("Characters of correspondence one summary reads. If there is more, the oldest mails are left out."),
    )
    #: How many summaries one user may start by hand in an hour (a cap on the cost and a brake on misuse).
    manual_per_hour = models.PositiveSmallIntegerField(
        _("summaries by hand per user and hour"),
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
    )

    # --- Automatic summaries (the nightly job; off until an administrator opts in) --------------------
    auto_enabled = models.BooleanField(_("automatic summaries"), default=False)
    #: Which provider the operator agreed to when switching on: the summaries stop if the provider is another one.
    auto_consent_key = models.CharField(max_length=300, blank=True, editable=False)
    auto_enabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    auto_enabled_at = models.DateTimeField(null=True, blank=True, editable=False)
    auto_window_start = models.TimeField(_("window from"), default=window_start)
    auto_window_end = models.TimeField(_("window until"), default=window_end)
    auto_max_per_run = models.PositiveSmallIntegerField(
        _("most summaries per night"),
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
    )
    auto_token_budget = models.PositiveIntegerField(
        _("token budget per night"),
        default=200_000,
        validators=[MaxValueValidator(100_000_000)],
        help_text=_("Tokens read and written in one night; the job stops when it is reached. 0: no limit."),
    )
    auto_project_statuses = models.JSONField(_("statuses of projects"), default=default_project_statuses, blank=True)
    auto_case_statuses = models.JSONField(_("statuses of service cases"), default=default_case_statuses, blank=True)
    auto_min_interval_hours = models.PositiveSmallIntegerField(
        _("least time between two summaries in hours"),
        default=20,
        validators=[MaxValueValidator(720)],
    )
    auto_min_mails = models.PositiveSmallIntegerField(
        _("least number of mails"), default=2, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    auto_keep_versions = models.PositiveSmallIntegerField(
        _("earlier summaries kept"), default=5, validators=[MaxValueValidator(50)]
    )
    auto_include_notes = models.BooleanField(_("notes"), default=True)
    auto_include_chat = models.BooleanField(_("chat"), default=False)
    #: Default on: in projects every message starts with the lock (EML-055), so the job would read nothing there; the
    #: summary shows only to who reads all messages anyway, and the notice of the opt-in names the data class.
    auto_include_locked = models.BooleanField(_("messages with lock"), default=True)
    #: The night (the day its window began) of the last complete run; the minute timer starts one run per night.
    auto_last_night = models.DateField(null=True, blank=True, editable=False)

    audit_exclude = frozenset(
        {
            "auto_last_night",
            "local_test_at",
            "local_test_tokens_per_second",
            "local_test_prompt_per_second",
            "local_test_seconds",
            "local_test_model",
        }
    )

    class Meta:
        verbose_name = _("AI settings")
        verbose_name_plural = _("AI settings")

    def __str__(self) -> str:
        return str(_("AI settings"))

    def source_of(self, use: str) -> tuple[str, AIProvider | None]:
        """Who serves a use: ``(source, provider)``; a provider that is gone counts as off."""
        if use == Use.SUMMARY:
            source, provider = self.summary_source, self.summary_provider
        elif use == Use.DRAFT:
            source, provider = self.draft_source, self.draft_provider
        elif use == Use.INVOICE:
            source, provider = self.invoice_source, self.invoice_provider
        else:
            return Source.OFF, None
        if source == Source.PROVIDER and provider is None:
            return Source.OFF, None
        return source, provider if source == Source.PROVIDER else None


class AISummary(models.Model):
    """The AI summary of a project's correspondence (EML-040, EML-044).

    One per project; a new summary replaces the old one. It covers the mails
    of :attr:`covered_projects` up to :attr:`newest_mail_id` – a newer mail
    makes it out of date ("veraltet"). It is shown only to those who may read
    the correspondence of every project it covers. Deleting a mail it covers
    deletes it (:mod:`rentalars.ai.signals`): its text came from that mail.
    """

    project = models.OneToOneField(
        "projects.Project", verbose_name=_("project"), on_delete=models.CASCADE, related_name="ai_summary"
    )
    text = models.TextField(_("summary"))
    model = models.CharField(_("model"), max_length=200)
    provider_label = models.CharField(_("provider"), max_length=120)
    is_local = models.BooleanField(_("local AI"), default=True)
    language = models.CharField(_("language"), max_length=10, default="de")
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    mail_count = models.PositiveIntegerField(_("number of mails"), default=0)
    newest_mail_id = models.PositiveIntegerField(default=0)
    newest_mail_date = models.DateTimeField(null=True, blank=True)
    include_chat = models.BooleanField(_("with the chat"), default=False)
    newest_chat_id = models.PositiveIntegerField(default=0)
    #: The projects whose mails it covers: the project and the parts its author could read (PRJ-044).
    covered_projects = models.JSONField(default=list)
    #: How many parts the correspondence was cut into for the model, and how long it all took.
    parts = models.PositiveSmallIntegerField(default=1)
    duration_seconds = models.FloatField(default=0)
    #: Made by the nightly job, not by somebody pressing "Zusammenfassen".
    is_automatic = models.BooleanField(_("created automatically"), default=False)
    #: SHA-256 of the texts that were sent (after removing data classes) with the scope – the same input
    #: needs no new summary.
    input_hash = models.CharField(max_length=64, blank=True)
    #: Whether messages with lock were read; the nightly job leaves them out unless an administrator allows them.
    covers_locked = models.BooleanField(_("with messages with lock"), default=True)
    #: Older mails left out because the text was longer than the cap (``AISettings.max_input_chars``).
    dropped_entries = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("AI summary")
        verbose_name_plural = _("AI summaries")

    def __str__(self) -> str:
        return f"{self.project_id}: {self.created_at:%Y-%m-%d %H:%M}"


class AISummaryVersion(models.Model):
    """An earlier summary of a project, kept when a new one replaced it (``AISettings.auto_keep_versions``).

    The same rights as the summary itself; deleted with the project, with the mails it covers and when the
    customer's personal data are erased (:mod:`rentalars.ai.signals`, :func:`rentalars.ai.auto.forget_customer`).
    """

    project = models.ForeignKey(
        "projects.Project", verbose_name=_("project"), on_delete=models.CASCADE, related_name="ai_summary_versions"
    )
    text = models.TextField(_("summary"))
    model = models.CharField(_("model"), max_length=200)
    provider_label = models.CharField(_("provider"), max_length=120)
    is_local = models.BooleanField(_("local AI"), default=True)
    language = models.CharField(_("language"), max_length=10, default="de")
    created_at = models.DateTimeField(_("created"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_automatic = models.BooleanField(_("created automatically"), default=False)
    input_hash = models.CharField(max_length=64, blank=True)
    covers_locked = models.BooleanField(default=True)
    mail_count = models.PositiveIntegerField(default=0)
    newest_mail_id = models.PositiveIntegerField(default=0)
    include_chat = models.BooleanField(default=False)
    covered_projects = models.JSONField(default=list)
    replaced_at = models.DateTimeField(_("replaced"), default=timezone.now)

    class Meta:
        verbose_name = _("earlier AI summary")
        verbose_name_plural = _("earlier AI summaries")
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["project", "-created_at"], name="ai_version_project_idx")]

    def __str__(self) -> str:
        return f"{self.project_id}: {self.created_at:%Y-%m-%d %H:%M}"


class RunState(models.TextChoices):
    """How a night of automatic summaries ended."""

    RUNNING = "running", _("running")
    DONE = "done", _("done")
    STOPPED = "stopped", _("stopped early")
    FAILED = "failed", _("failed")
    ABORTED = "aborted", _("interrupted")
    DRY_RUN = "dry_run", _("dry run")


class AutoSummaryRun(models.Model):
    """One run of the nightly job – what it did, what it left out and why, and the errors (for administrators).

    ``lock`` is 1 while the run is under way and empty afterwards; a unique constraint on it keeps two runs from
    overlapping, on SQLite and MariaDB alike. A run that stopped reporting for longer than
    :data:`rentalars.ai.auto.LOCK_SECONDS` counts as interrupted and no longer blocks.
    """

    started_at = models.DateTimeField(_("started"), default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(_("finished"), null=True, blank=True)
    heartbeat_at = models.DateTimeField(default=timezone.now)
    state = models.CharField(_("state"), max_length=10, choices=RunState.choices, default=RunState.RUNNING)
    #: Why it ended early: ``budget``, ``limit``, ``window``, ``provider`` (it kept failing), ``off``, ``consent``.
    reason = models.CharField(_("reason"), max_length=20, blank=True)
    night = models.DateField(_("night"), null=True, blank=True)
    candidates = models.PositiveIntegerField(default=0)
    summarised = models.PositiveIntegerField(default=0)
    unchanged = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    tokens = models.PositiveIntegerField(default=0)
    dry_run = models.BooleanField(default=False)
    lock = models.PositiveSmallIntegerField(null=True, blank=True, editable=False)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: One entry per project looked at: ``{"project": id, "number": "...", "outcome": "...", "error": "..."}``.
    details = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = _("run of automatic summaries")
        verbose_name_plural = _("runs of automatic summaries")
        ordering = ["-started_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["lock"], name="ai_auto_run_one_at_a_time")]

    def __str__(self) -> str:
        return f"{self.started_at:%Y-%m-%d %H:%M} {self.state}"

    def as_json(self) -> dict[str, Any]:
        """The run for the API."""
        return {
            "id": self.pk,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "state": self.state,
            "reason": self.reason,
            "night": self.night,
            "candidates": self.candidates,
            "summarised": self.summarised,
            "unchanged": self.unchanged,
            "failed": self.failed,
            "tokens": self.tokens,
            "dry_run": self.dry_run,
            "details": self.details,
        }


class AutoSummaryExclusion(AuditedModel):
    """Exclusion from the automatic AI summaries for one project – or for all projects of one customer.

    Exactly one of ``project`` and ``customer`` is set. The summary by hand stays possible.
    """

    project = models.OneToOneField(
        "projects.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="ai_exclusion"
    )
    customer = models.OneToOneField(
        "customers.Customer", null=True, blank=True, on_delete=models.CASCADE, related_name="ai_exclusion"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    audit_exclude = frozenset({"created_at"})

    class Meta:
        verbose_name = _("exclusion from automatic summaries")
        verbose_name_plural = _("exclusions from automatic summaries")
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(project__isnull=False, customer__isnull=True))
                | (models.Q(project__isnull=True, customer__isnull=False)),
                name="ai_exclusion_one_target",
            )
        ]

    def __str__(self) -> str:
        return f"{self.project or self.customer}"

    def audit_parent(self) -> models.Model | None:
        """The project or customer, so that the switch shows in its history."""
        return self.project or self.customer


class AICall(models.Model):
    """One call to a language model, for the administrator (ADM-017). Never the content."""

    timestamp = models.DateTimeField(_("time"), default=timezone.now, db_index=True)
    use = models.CharField(_("use"), max_length=10, choices=Use.choices)
    provider_label = models.CharField(_("provider"), max_length=120)
    is_local = models.BooleanField(_("local AI"), default=False)
    model = models.CharField(_("model"), max_length=200, blank=True)
    duration_ms = models.PositiveIntegerField(_("duration in ms"), default=0)
    request_chars = models.PositiveIntegerField(_("characters sent"), default=0)
    response_chars = models.PositiveIntegerField(_("characters received"), default=0)
    prompt_tokens = models.PositiveIntegerField(_("tokens sent"), null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(_("tokens received"), null=True, blank=True)
    #: EML-040: how fast the server read the prompt and wrote the answer, as it reported.
    prompt_per_second = models.FloatField(_("read per second"), null=True, blank=True)
    generation_per_second = models.FloatField(_("written per second"), null=True, blank=True)
    ok = models.BooleanField(_("successful"), default=True)
    error = models.CharField(_("error"), max_length=300, blank=True)
    #: Made by a job (the nightly summaries), not on somebody's request; ``user`` is empty then.
    automatic = models.BooleanField(_("automatic"), default=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    project = models.ForeignKey(
        "projects.Project",
        verbose_name=_("project"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("AI call")
        verbose_name_plural = _("AI calls")
        ordering = ["-timestamp", "-id"]

    def __str__(self) -> str:
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.use} {self.provider_label}"

    def as_json(self) -> dict[str, Any]:
        """The entry for the API."""
        return {
            "id": self.pk,
            "timestamp": self.timestamp,
            "use": self.use,
            "provider": self.provider_label,
            "is_local": self.is_local,
            "model": self.model,
            "duration_ms": self.duration_ms,
            "request_chars": self.request_chars,
            "response_chars": self.response_chars,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "prompt_per_second": self.prompt_per_second,
            "generation_per_second": self.generation_per_second,
            "ok": self.ok,
            "error": self.error,
            "automatic": self.automatic,
            "user": str(self.user) if self.user_id else None,
            "project": self.project_id,
        }
