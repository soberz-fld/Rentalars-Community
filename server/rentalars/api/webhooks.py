# SPDX-License-Identifier: GPL-3.0-or-later
"""Webhooks: telling other systems about events by HTTP (API-012).

What a webhook gets is described in :mod:`rentalars.api.webhook_events`.

Recording
---------
Where something happens, the business code calls :func:`record` (packing,
time tracking); creating a project, changing its status and storing a
document are noticed by signals (:func:`connect_signals`), so that every
path counts – also the status "out" and "returned" that packing sets by
itself. :func:`record` writes one :class:`~rentalars.api.models.WebhookDelivery`
per active webhook that wants the event, **in the transaction of the
change**: a change that is rolled back leaves no delivery behind, and the
timer only ever sees committed rows. That is why no ``transaction.on_commit``
is needed – and nothing is lost if the process ends right after the commit.
A problem while recording is logged and never stops the change itself.

Delivering
----------
``manage.py run_jobs`` runs every minute and calls :func:`run_due`. It sends
what is due, oldest first, for at most :data:`RUN_BUDGET_SECONDS` seconds
and :data:`RUN_LIMIT` deliveries, and never raises. When a webhook fails, its
other deliveries wait for the next run, so that one dead receiver cannot use
up the run. A delivery is *claimed* before it is sent (its next attempt is
moved ahead by :data:`CLAIM_SECONDS`), so two runs at the same time never
send it twice.

Every delivery is a ``POST`` with ``Content-Type: application/json`` and the
headers ``X-Rentalars-Event``, ``X-Rentalars-Delivery`` (the delivery ID,
the same on every attempt) and ``X-Rentalars-Signature: sha256=<hex>`` –
the HMAC-SHA256 of the raw body with the webhook's secret as key, like
GitHub's. A receiver computes the same and compares it in constant time.

Any 2xx answer is success. Everything else – an error, no answer within
:data:`TIMEOUT` seconds, a redirection – is a failure, and the delivery is
tried again after 1 minute, 5 minutes, 30 minutes, 2 hours and 12 hours:
:data:`MAX_ATTEMPTS` attempts within about 15 hours. Redirections are never
followed: the address must be the final one. At most
:data:`MAX_RESPONSE_BYTES` of an answer are read; its beginning is kept to
help find out why a receiver refuses. The connection goes through
:mod:`rentalars.core.network` (NFA-071): internal addresses – the
company's own systems, this server – are reached only if the operator
allows them (``[network] allow_internal``), and only the address that was
checked is connected to.

Switching off (decision)
------------------------
When :data:`SWITCH_OFF_AFTER` deliveries in a row have failed for good –
each after all its attempts – the webhook is switched off and the
administrators get a notification. Its waiting deliveries stay; they go out
once it is switched on again. Deliveries of a webhook that is off are not
sent, and no new ones are recorded for it.

By hand
-------
"Send test" (:func:`send_test`) sends a ``ping`` at once and shows the
answer. "Send again" (:func:`redeliver`) sends a failed delivery once more,
with the same delivery ID. Both try exactly once and do not count towards switching
off.

Deliveries are kept for :data:`RETENTION_DAYS` days
(:func:`delete_old_deliveries`, run by the daily maintenance).
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import http.client
import json
import logging
import secrets
import socket
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import F
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars import __version__
from rentalars.api.models import DeliveryStatus, Webhook, WebhookDelivery, validate_webhook_url
from rentalars.api.webhook_events import EVENTS, PING, build
from rentalars.core.crypto import SecretUnreadableError, decrypt_secret, encrypt_secret
from rentalars.core.i18n import LocalText
from rentalars.core.network import BlockedAddressError, open_url

logger = logging.getLogger(__name__)

#: Seconds to wait for the receiver at each step; twice that in total.
TIMEOUT = 10

#: The most of an answer that is read (64 KB); a receiver has nothing to say that is longer.
MAX_RESPONSE_BYTES = 64 * 1024

#: Characters of the answer that are kept with the delivery.
RESPONSE_EXCERPT = 1000

#: Pauses after the 1st, 2nd … failed attempt.
RETRY_DELAYS = (
    datetime.timedelta(minutes=1),
    datetime.timedelta(minutes=5),
    datetime.timedelta(minutes=30),
    datetime.timedelta(hours=2),
    datetime.timedelta(hours=12),
)

#: Attempts of a delivery before it is given up: the first and one after each pause.
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1

#: Deliveries in a row that failed for good before a webhook is switched off.
SWITCH_OFF_AFTER = 10

#: Days a delivery is kept.
RETENTION_DAYS = 30

#: Seconds one run of the timer spends on webhooks at most (a send already begun may take :data:`TIMEOUT` longer).
RUN_BUDGET_SECONDS = 30

#: Deliveries one run looks at, at most.
RUN_LIMIT = 200

#: How far a claimed delivery's next attempt is moved: should a run end while sending, it is tried again then.
CLAIM_SECONDS = 600

USER_AGENT = f"Rentalars/{__version__} (webhook)"


# --- The secret --------------------------------------------------------------------------------------


def new_secret(webhook: Webhook) -> str:
    """Give a webhook a new random secret, stored encrypted; returns it in plain text (not saved yet)."""
    plain = secrets.token_urlsafe(32)
    webhook.secret_encrypted = encrypt_secret(plain)
    webhook.secret_created_at = timezone.now()
    return plain


def secret_of(webhook: Webhook) -> str:
    """The secret of a webhook in plain text, to show it to an administrator.

    Raises:
        SecretUnreadableError: It was encrypted with another ``secret_key``.
    """
    return decrypt_secret(webhook.secret_encrypted)


def signature(secret: str, body: bytes) -> str:
    """The value of ``X-Rentalars-Signature``: ``sha256=`` and the HMAC-SHA256 of the body in hex."""
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# --- Creating and changing ------------------------------------------------------------------------------


def create_webhook(*, user: Any = None, **fields: Any) -> tuple[Webhook, str]:
    """Create a webhook with a new secret; returns it and the secret in plain text (API-012).

    Raises:
        ValidationError: Address or events are not right.
    """
    webhook = Webhook(created_by=user if getattr(user, "is_authenticated", False) else None, **fields)
    plain = new_secret(webhook)
    webhook.full_clean()
    webhook.save()
    return webhook, plain


def update_webhook(webhook: Webhook, **changes: Any) -> Webhook:
    """Change a webhook. Switched on again, it starts afresh: the count of failures is reset.

    Raises:
        ValidationError: Address or events are not right.
    """
    was_active = webhook.is_active
    for name, value in changes.items():
        setattr(webhook, name, value)
    if webhook.is_active and not was_active:
        webhook.failures_in_a_row = 0
        webhook.switched_off_at = None
    webhook.full_clean()
    webhook.save()
    return webhook


def renew_secret(webhook: Webhook) -> str:
    """Replace the secret; from now on deliveries are signed with the new one. Returns it in plain text."""
    plain = new_secret(webhook)
    webhook.save(update_fields=["secret_encrypted", "secret_created_at"])
    return plain


# --- Recording -----------------------------------------------------------------------------------------


def subscribers(event: str) -> list[Webhook]:
    """The active webhooks that want an event."""
    return [
        hook for hook in Webhook.objects.filter(is_active=True).only("id", "events") if event in (hook.events or [])
    ]


def record(event: str, subject: Any, **details: Any) -> int:
    """Note an event about ``subject`` for every webhook that wants it (API-012); returns the number of deliveries.

    Call it inside the transaction of the change. It never raises: a problem
    is logged, and the change goes on.
    """
    return record_each(event, [subject], **details)


def record_each(event: str, subjects: Iterable[Any], **details: Any) -> int:
    """Like :func:`record`, for several objects at once – one query for the webhooks, one insert."""
    try:
        if event not in EVENTS or event == PING:
            raise ValueError(f"Unknown webhook event {event!r}.")
        hooks = subscribers(event)
        if not hooks:
            return 0
        now = timezone.now()
        rows: list[WebhookDelivery] = []
        with translation.override(settings.LANGUAGE_CODE):
            for subject in subjects:
                # Through JSON once: what is stored is exactly what will be sent.
                data = json.loads(json.dumps(build(event, subject, **details), cls=DjangoJSONEncoder))
                rows.extend(
                    WebhookDelivery(webhook=hook, event=event, data=data, created_at=now, next_attempt_at=now)
                    for hook in hooks
                )
        # A savepoint: should the insert fail, the change around it is not affected.
        with transaction.atomic():
            WebhookDelivery.objects.bulk_create(rows)
        return len(rows)
    except Exception:
        logger.exception("The event %s could not be recorded for the webhooks.", event)
        return 0


def _project_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """``project.created`` and ``project.status_changed``, however the project was saved (API-012)."""
    from rentalars.projects.legacy_quiet import is_quiet

    if raw or is_quiet():  # Legacy import: an old project taken over from an invoice is no news
        return
    if created:
        record("project.created", instance)
        return
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "status" not in update_fields:
        return
    # The values before this save, as the change log keeps them (core.audit); None for a hand-built object.
    before = instance._audit_before() if hasattr(instance, "_audit_before") else None
    if not before or "status" not in before or before["status"] == instance.status:
        return
    record("project.status_changed", instance, old_status=before["status"], new_status=instance.status)


def _document_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """``document.created`` when a document is stored for good (API-012)."""
    from rentalars.projects.legacy_quiet import is_quiet

    if created and not raw and not is_quiet():  # Legacy import: a historic invoice is no news
        record("document.created", instance)


def connect_signals() -> None:
    """Connect the signals; called once when the application starts."""
    from django.db.models.signals import post_save

    post_save.connect(_project_saved, sender="projects.Project", dispatch_uid="api.webhooks.project")
    post_save.connect(_document_saved, sender="documents.Document", dispatch_uid="api.webhooks.document")


# --- Sending ---------------------------------------------------------------------------------------


@dataclass
class Outcome:
    """What came of one attempt."""

    status_code: int | None
    #: Empty on success; a short text in the language of the installation otherwise.
    error: str = ""
    response: str = ""
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        """A 2xx answer."""
        return self.status_code is not None and 200 <= self.status_code < 300


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """A redirection comes back as an answer of its own; it is not followed."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Do not follow."""
        return None


def _network_problem(error: BaseException) -> str:
    """Name the kind of network problem, without the address."""
    reason: Any = getattr(error, "reason", error)
    if isinstance(reason, BlockedAddressError):
        return str(reason)  # NFA-071
    if isinstance(reason, TimeoutError | socket.timeout):
        return _("No answer within %(seconds)d seconds.") % {"seconds": TIMEOUT}
    if isinstance(reason, socket.gaierror):
        return _("The server name is unknown.")
    if isinstance(reason, ConnectionRefusedError):
        return _("The connection was refused.")
    if isinstance(reason, ssl.SSLError | ssl.CertificateError):
        return _("The secure connection failed (certificate).")
    return _("The connection failed.")


def _read(response: Any, deadline: float) -> bytes:
    """Read the beginning of an answer: at most :data:`MAX_RESPONSE_BYTES`, and only until the deadline."""
    chunks: list[bytes] = []
    size = 0
    while size < MAX_RESPONSE_BYTES and time.monotonic() < deadline:
        chunk = response.read(min(65536, MAX_RESPONSE_BYTES - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def post(url: str, body: bytes, headers: dict[str, str]) -> Outcome:
    """Send one ``POST`` under the rules of the module description; never raises."""
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        validate_webhook_url(url)
    except ValidationError as error:
        return Outcome(None, " ".join(error.messages))
    prepared = urllib.request.Request(url, data=body, method="POST")  # noqa: S310 - scheme checked above
    for name, value in headers.items():
        prepared.add_header(name, value)
    deadline = started + 2 * TIMEOUT
    try:
        # NFA-071: only to a checked address; a redirection comes back as an answer.
        with open_url(prepared, timeout=TIMEOUT, handlers=[_NoRedirects]) as response:
            status = response.status
            try:
                data = _read(response, deadline)
            except (OSError, http.client.HTTPException):
                data = b""  # the status is known; an answer cut short does not change it
    except urllib.error.HTTPError as error:
        status = error.code
        try:
            data = _read(error, deadline)
        except (OSError, http.client.HTTPException):
            data = b""
        finally:
            error.close()
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as error:
        return Outcome(None, _network_problem(error), duration_ms=elapsed())
    text = data.decode("utf-8", errors="replace")[:RESPONSE_EXCERPT]
    if 200 <= status < 300:
        problem = ""
    elif 300 <= status < 400:
        problem = _(
            "The receiver redirects to another address (%(status)d). Redirections are not followed: enter the final "
            "address."
        ) % {"status": status}
    else:
        problem = _("The receiver answered with error %(status)d.") % {"status": status}
    return Outcome(status, problem, text, elapsed())


def _send(delivery: WebhookDelivery) -> Outcome:
    """Sign and send a delivery to the current address of its webhook."""
    webhook = delivery.webhook
    try:
        secret = decrypt_secret(webhook.secret_encrypted)
    except SecretUnreadableError:
        secret = ""
    if not secret:
        return Outcome(
            None,
            _(
                "The secret of the webhook cannot be read (was the key of the installation changed?). Create a new secret."
            ),
        )
    body = delivery.body()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Rentalars-Event": delivery.event,
        "X-Rentalars-Delivery": str(delivery.uuid),
        "X-Rentalars-Signature": signature(secret, body),
    }
    return post(webhook.url, body, headers)


def attempt(delivery: WebhookDelivery, *, by_hand: bool = False) -> bool:
    """Try a delivery once and note the outcome; returns whether it arrived.

    Sent by the timer, a failed delivery waits for its next attempt or – the
    attempts used up – is given up and counts towards switching off the
    webhook. Sent by hand, there is no second attempt and nothing is counted.
    """
    now = timezone.now()
    with translation.override(settings.LANGUAGE_CODE):
        try:
            outcome = _send(delivery)
        except Exception:  # a mistake of ours must not leave the delivery claimed for ever
            logger.exception("Webhook delivery %s could not be sent.", delivery.pk)
            outcome = Outcome(None, _("Internal error while sending; details are in the log of the server."))
    delivery.attempts += 1
    delivery.last_attempt_at = now
    delivery.last_status_code = outcome.status_code
    delivery.last_error = outcome.error[:300]
    delivery.last_response = outcome.response
    delivery.last_duration_ms = outcome.duration_ms
    if outcome.ok:
        delivery.status = DeliveryStatus.DELIVERED
        delivery.delivered_at = timezone.now()
        delivery.next_attempt_at = None
    elif by_hand or delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = DeliveryStatus.FAILED
        delivery.next_attempt_at = None
    else:
        delivery.status = DeliveryStatus.PENDING
        delivery.next_attempt_at = now + RETRY_DELAYS[delivery.attempts - 1]
    # An update, not save(): a webhook deleted while its delivery was on the way leaves nothing to update.
    WebhookDelivery.objects.filter(pk=delivery.pk).update(
        attempts=delivery.attempts,
        last_attempt_at=delivery.last_attempt_at,
        last_status_code=delivery.last_status_code,
        last_error=delivery.last_error,
        last_response=delivery.last_response,
        last_duration_ms=delivery.last_duration_ms,
        status=delivery.status,
        delivered_at=delivery.delivered_at,
        next_attempt_at=delivery.next_attempt_at,
    )
    if outcome.ok:
        Webhook.objects.filter(pk=delivery.webhook_id, failures_in_a_row__gt=0).update(failures_in_a_row=0)
    elif delivery.status == DeliveryStatus.FAILED and not by_hand:
        _count_failure(delivery)
    return outcome.ok


def _count_failure(delivery: WebhookDelivery) -> None:
    """One more delivery failed for good; switch the webhook off at :data:`SWITCH_OFF_AFTER` (API-012)."""
    Webhook.objects.filter(pk=delivery.webhook_id).update(failures_in_a_row=F("failures_in_a_row") + 1)
    webhook = Webhook.objects.filter(pk=delivery.webhook_id).first()
    if webhook is None or not webhook.is_active or webhook.failures_in_a_row < SWITCH_OFF_AFTER:
        return
    webhook.is_active = False
    webhook.switched_off_at = timezone.now()
    webhook.save(update_fields=["is_active", "switched_off_at"])  # in the change log, by "system:jobs"
    try:
        _tell_administrators(webhook, delivery)
    except Exception:  # a notification must not break the run
        logger.exception("Telling the administrators about webhook %s failed.", webhook.pk)


def _tell_administrators(webhook: Webhook, delivery: WebhookDelivery) -> None:
    from django.urls import reverse

    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify, operators

    # UIX-029: each administrator reads it in his language.
    title = LocalText(gettext_lazy("Webhook switched off: %(webhook)s"), webhook=webhook)
    body = LocalText(
        gettext_lazy(
            "%(count)d deliveries in a row failed after all their attempts. The last error: %(error)s\n"
            "Check the receiving system, switch the webhook on again and send the failed deliveries again."
        ),
        count=webhook.failures_in_a_row,
        error=delivery.last_error or "–",
    )
    # There is no kind of its own: a new kind would change the notifications' table (API-012).
    notify(operators(), Kind.SYSTEM_ERROR, title, body=body, url=reverse("webhooks:detail", args=[webhook.pk]))


# --- The run of the timer ----------------------------------------------------------------------------


@dataclass
class RunResult:
    """What one run did."""

    delivered: int = 0
    failed: int = 0


def _claim(delivery: WebhookDelivery) -> bool:
    """Take a due delivery for this run; ``False`` if another run took it first."""
    until = timezone.now() + datetime.timedelta(seconds=CLAIM_SECONDS)
    taken = WebhookDelivery.objects.filter(
        pk=delivery.pk, status=DeliveryStatus.PENDING, next_attempt_at=delivery.next_attempt_at
    ).update(next_attempt_at=until)
    if taken:
        delivery.next_attempt_at = until
    return bool(taken)


def run_due(*, budget_seconds: float = RUN_BUDGET_SECONDS, limit: int = RUN_LIMIT) -> RunResult:
    """Send the deliveries that are due (API-012).

    Called every minute by the background timer. Never raises; bounded by
    ``budget_seconds`` and ``limit``.
    """
    result = RunResult()
    try:
        deadline = time.monotonic() + budget_seconds
        due = list(
            WebhookDelivery.objects.filter(
                status=DeliveryStatus.PENDING, next_attempt_at__lte=timezone.now(), webhook__is_active=True
            )
            .select_related("webhook")
            .order_by("next_attempt_at", "pk")[:limit]
        )
        failing: set[int] = set()
        for delivery in due:
            if time.monotonic() > deadline:
                break
            if delivery.webhook_id in failing or not _claim(delivery):
                continue
            try:
                arrived = attempt(delivery)
            except Exception:  # noting the outcome failed; the claim runs out and the delivery is tried again
                logger.exception("Webhook delivery %s: the outcome could not be noted.", delivery.pk)
                arrived = False
            if arrived:
                result.delivered += 1
            else:
                result.failed += 1
                failing.add(delivery.webhook_id)
    except Exception:
        logger.exception("The periodic run of the webhooks failed.")
    return result


# --- By hand ---------------------------------------------------------------------------------------


def send_test(webhook: Webhook) -> WebhookDelivery:
    """Send a ``ping`` now and return the delivery with the answer (API-012).

    Works for a webhook that is switched off too: it is the way to check a
    receiver before switching it on again.
    """
    with translation.override(settings.LANGUAGE_CODE):
        data = build(PING, webhook)
    delivery = WebhookDelivery.objects.create(webhook=webhook, event=PING, data=data, next_attempt_at=None)
    delivery.webhook = webhook
    attempt(delivery, by_hand=True)
    return delivery


def redeliver(delivery: WebhookDelivery) -> WebhookDelivery:
    """Send a failed delivery once more, now; returns it with the new outcome (API-012).

    Raises:
        ValidationError: The delivery has not failed – it arrived, or it is
            still being tried.
    """
    if not delivery.is_redeliverable:
        raise ValidationError(_("Only deliveries that failed can be sent again."))
    attempt(delivery, by_hand=True)
    return delivery


# --- Retention -----------------------------------------------------------------------------------


def delete_old_deliveries() -> int:
    """Delete deliveries older than :data:`RETENTION_DAYS` days; run by the daily maintenance (API-012)."""
    limit = timezone.now() - datetime.timedelta(days=RETENTION_DAYS)
    deleted, _per_model = WebhookDelivery.objects.filter(created_at__lt=limit).delete()
    return deleted
