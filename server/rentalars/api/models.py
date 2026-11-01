# SPDX-License-Identifier: GPL-3.0-or-later
"""What the API remembers: counted calls, answers to repeated calls, webhooks (API-010, API-011, API-012)."""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel


class ApiCallCount(models.Model):
    """How many calls one token made in one minute (API-011).

    One row per token and minute, counted up with each call; rows older than
    an hour are removed by the daily maintenance.
    """

    token = models.ForeignKey("accounts.ApiToken", on_delete=models.CASCADE, related_name="call_counts")
    minute = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["token", "minute"], name="api_call_count_per_minute")]

    def __str__(self) -> str:
        return f"{self.token_id} {self.minute:%Y-%m-%d %H:%M}: {self.count}"


class IdempotentCall(models.Model):
    """A changing call sent with an ``Idempotency-Key`` and the answer it got (API-010).

    A client that sends the same call again – because the connection broke
    before the answer arrived – gets the stored answer instead of a second
    execution. Kept for a day.
    """

    #: Whose key: "token:<pk>" for an API token, "user:<pk>" for the session of a user (API-010).
    scope = models.CharField(max_length=80)
    key = models.CharField(max_length=100)
    #: Method, address and body of the call, hashed: the same key for another call is an error.
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    #: Empty while the first call is still running.
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=500, blank=True)
    body = models.BinaryField(blank=True)
    #: Project ID → the level of project access the call relied on; a repetition needs at least that.
    project_access = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope", "key"], name="idempotent_call_per_key")]

    def __str__(self) -> str:
        return f"{self.key} ({self.status_code or '…'})"


class WriteLock(models.Model):
    """The lock row of one record for a change sent with ``If-Match`` (API-010).

    A change with ``If-Match`` takes this row (an ``UPDATE``) at the start
    of its transaction, compares the version and writes – a second change
    of the same record waits for the row until the first is committed and
    then compares against the new state. ``key`` is the SHA-256 of
    ``record:<app.model>:<pk>`` or, where the address names no record,
    ``path:<address>``. Rows older than a day are removed by the daily
    maintenance.
    """

    key = models.CharField(max_length=64, unique=True)
    taken_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.key


# --- Webhooks (API-012) ---------------------------------------------------------------------------


def validate_webhook_url(value: str) -> None:
    """Accept ``http://`` and ``https://`` addresses with a host and nothing else (API-012).

    Internal addresses (``http://erp:8080/…``, ``http://192.168.1.20/…``) are
    reached only if the operator allows them (NFA-071, ``[network]
    allow_internal``): an IP address or ``localhost`` is checked here, a name
    when a delivery is sent (``core.network``). Django's ``URLValidator``
    would refuse a host name without a dot, hence this check.
    Credentials in the address are refused: the signature is the means to
    trust a delivery, and a password in the address would be shown to every
    reader of the settings.
    """
    text = (value or "").strip()
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as error:
        raise ValidationError(_("This is not a valid address."), code="invalid") from error
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValidationError(_("Only addresses beginning with https:// or http:// can be used."), code="invalid")
    if any(character.isspace() for character in text):
        raise ValidationError(_("The address must not contain spaces."), code="invalid")
    if parts.username is not None or parts.password is not None:
        raise ValidationError(
            _("Leave user name and password out of the address. The receiver checks the signature instead."),
            code="invalid",
        )
    if port == 0:
        raise ValidationError(_("This is not a valid address."), code="invalid")
    from rentalars.core.network import BlockedAddressError, check_entered_host

    try:
        check_entered_host(parts.hostname)
    except BlockedAddressError as error:
        raise ValidationError(str(error), code="internal_address") from error


class Webhook(AuditedModel):
    """An address of another system that is told about events by an HTTP POST (API-012).

    Which events it wants is a list of event names (see
    :mod:`rentalars.api.webhook_events`). Every delivery is signed with the
    webhook's secret (HMAC-SHA256); the secret is stored encrypted like the
    other secrets Rentalars has to read again (:mod:`rentalars.core.crypto`).

    ``failures_in_a_row`` counts deliveries that failed for good – after all
    their attempts – since the last successful one. At
    :data:`rentalars.api.webhooks.SWITCH_OFF_AFTER` the webhook is switched
    off and the administrators are told; ``switched_off_at`` says so.
    """

    url = models.CharField(
        _("address"),
        max_length=500,
        validators=[validate_webhook_url],
        help_text=_(
            "Where the events are sent to, beginning with https:// or http://. Internal addresses only if the "
            "operator allows them in the configuration file."
        ),
    )
    description = models.CharField(_("description"), max_length=200, blank=True)
    events = models.JSONField(_("events"), default=list)
    is_active = models.BooleanField(_("active"), default=True)
    secret_encrypted = models.TextField(_("secret (encrypted)"), blank=True, editable=False)
    #: When the secret was made; a new secret shows in the change log by this date.
    secret_created_at = models.DateTimeField(_("secret created"), null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    failures_in_a_row = models.PositiveIntegerField(_("failed deliveries in a row"), default=0, editable=False)
    switched_off_at = models.DateTimeField(_("switched off automatically"), null=True, blank=True, editable=False)

    #: The secret never goes into the change log; the counter would only add noise.
    audit_exclude: ClassVar[frozenset[str]] = frozenset({"secret_encrypted", "failures_in_a_row"})

    class Meta:
        verbose_name = _("webhook")
        verbose_name_plural = _("webhooks")
        ordering = ["url", "id"]

    def __str__(self) -> str:
        return self.description or self.url

    def clean(self) -> None:
        """Tidy the address and check the events (API-012)."""
        from rentalars.api.webhook_events import SUBSCRIBABLE

        super().clean()
        self.url = (self.url or "").strip()
        events = self.events if isinstance(self.events, list) else []
        unknown = sorted({str(name) for name in events} - set(SUBSCRIBABLE))
        if unknown:
            raise ValidationError({"events": _("Unknown events: %(names)s.") % {"names": ", ".join(unknown)}})
        if not events:
            raise ValidationError({"events": _("Choose at least one event.")})
        # Kept in the order of the catalogue, without duplicates.
        self.events = [name for name in SUBSCRIBABLE if name in events]


class DeliveryStatus(models.TextChoices):
    """Where a delivery stands (API-012)."""

    PENDING = "pending", _("waiting")
    DELIVERED = "delivered", _("delivered")
    FAILED = "failed", _("failed")


class WebhookDelivery(models.Model):
    """One event for one webhook, with the outcome of its attempts (API-012).

    The row is written in the same transaction as the change it reports: a
    change that is rolled back leaves no delivery behind. The background
    timer sends it (``manage.py run_jobs``) and tries again with growing
    pauses until the receiver answers with 2xx or the attempts are used up.

    ``data`` is the event-specific part; the body that is sent wraps it with
    version, delivery ID, event name and time (see :meth:`body`). Kept for
    :data:`rentalars.api.webhooks.RETENTION_DAYS` days.
    """

    webhook = models.ForeignKey(Webhook, verbose_name=_("webhook"), on_delete=models.CASCADE, related_name="deliveries")
    #: Sent as ``X-Rentalars-Delivery`` and as ``id`` in the body; the same on every attempt.
    uuid = models.UUIDField(_("delivery ID"), default=uuid4, unique=True, editable=False)
    event = models.CharField(_("event"), max_length=60)
    data = models.JSONField(_("content"), default=dict)
    status = models.CharField(
        _("status"), max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    #: Empty once delivered or given up, and for a test that is sent at once.
    next_attempt_at = models.DateTimeField(_("next attempt"), null=True, blank=True)
    last_attempt_at = models.DateTimeField(_("last attempt"), null=True, blank=True)
    last_status_code = models.PositiveSmallIntegerField(_("last answer"), null=True, blank=True)
    last_error = models.CharField(_("last error"), max_length=300, blank=True)
    #: The beginning of the last answer, for finding out why a receiver refuses.
    last_response = models.TextField(_("beginning of the last answer"), blank=True)
    last_duration_ms = models.PositiveIntegerField(_("duration (ms)"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("delivered"), null=True, blank=True)

    class Meta:
        verbose_name = _("webhook delivery")
        verbose_name_plural = _("webhook deliveries")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="webhook_delivery_due_idx"),
            models.Index(fields=["webhook", "-created_at"], name="webhook_delivery_list_idx"),
            models.Index(fields=["created_at"], name="webhook_delivery_age_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event} {self.uuid}"

    def envelope(self) -> dict[str, Any]:
        """The whole document that is sent (API-012): version, ID, event, time and the event's data."""
        from rest_framework.fields import DateTimeField

        return {
            "version": 1,
            "id": str(self.uuid),
            "event": self.event,
            "timestamp": DateTimeField().to_representation(self.created_at),
            "data": self.data,
        }

    def body(self) -> bytes:
        """The exact bytes that are sent and signed."""
        import json

        return json.dumps(self.envelope(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @property
    def is_redeliverable(self) -> bool:
        """Only a delivery that failed for good is sent again by hand."""
        return self.status == DeliveryStatus.FAILED
