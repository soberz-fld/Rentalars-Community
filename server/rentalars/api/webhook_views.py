# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the settings for webhooks (API-012).

* the list of webhooks with how their deliveries stand;
* creating and changing a webhook – address, events, on/off;
* one webhook: its secret (shown once after creating it, later on request,
  or replaced by a new one), "Send test", and its deliveries with what was
  sent and what came back; a failed one can be sent again.

Rights: module "Administration" – read to see, write to change, test, send
again and see the secret, delete to delete (AUT-015).
"""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.api import webhook_events, webhooks
from rentalars.api.models import DeliveryStatus, Webhook, WebhookDelivery, validate_webhook_url
from rentalars.api.webhook_tables import WEBHOOK_TABLE
from rentalars.core.crypto import SecretUnreadableError
from rentalars.core.forms import StyledForm
from rentalars.core.listing import paginate

#: Where the secret of a webhook just created waits for the page after the redirect – read once, then gone.
SESSION_KEY_NEW_SECRET = "webhooks.new_secret"  # noqa: S105 - the name of a session entry


class WebhookForm(StyledForm):
    """Address, events and state of a webhook (API-012)."""

    url = forms.CharField(
        label=gettext_lazy("Address (URL)"),
        max_length=500,
        validators=[validate_webhook_url],
        widget=forms.TextInput(attrs={"inputmode": "url", "spellcheck": "false", "autocomplete": "off"}),
        help_text=gettext_lazy(
            "Where the events are sent to, beginning with https:// or http://. Internal addresses only if the "
            "operator allows them in the configuration file."
        ),
    )
    description = forms.CharField(
        label=gettext_lazy("Description"),
        max_length=200,
        required=False,
        help_text=gettext_lazy("Which system receives the events, e.g. “ERP” or “n8n: warehouse”."),
    )
    events = forms.MultipleChoiceField(
        label=gettext_lazy("Events"),
        choices=webhook_events.choices,
        widget=forms.CheckboxSelectMultiple,
    )
    is_active = forms.BooleanField(
        label=gettext_lazy("Active"),
        required=False,
        initial=True,
        help_text=gettext_lazy("Switched off, nothing is sent and no events are noted for it."),
    )

    def save(self, webhook: Webhook | None, user: Any) -> tuple[Webhook, str] | None:
        """Create or change the webhook; returns it and – for a new one – its secret, or ``None`` on errors."""
        values = {name: self.cleaned_data[name] for name in ("url", "description", "events", "is_active")}
        try:
            if webhook is None:
                return webhooks.create_webhook(user=user, **values)
            return webhooks.update_webhook(webhook, **values), ""
        except ValidationError as error:
            self.add_error(None, error)
            return None


def _rights(request: HttpRequest) -> dict[str, bool]:
    rights = request_rights(request)
    return {
        "can_edit": rights.has_level(Module.ADMINISTRATION, Level.WRITE),
        "can_delete": rights.has_level(Module.ADMINISTRATION, Level.DELETE),
    }


@module_required(Module.ADMINISTRATION)
def webhook_list(request: HttpRequest) -> HttpResponse:
    """All webhooks, with what is waiting and what failed (API-012)."""
    hooks = Webhook.objects.annotate(
        waiting=Count("deliveries", filter=Q(deliveries__status=DeliveryStatus.PENDING)),
        failed=Count("deliveries", filter=Q(deliveries__status=DeliveryStatus.FAILED)),
        last_delivered=Max("deliveries__delivered_at"),
    )
    # UIX-040: a table of core.tables – columns, sorting, groups, CSV.
    table = WEBHOOK_TABLE.state(request)
    hooks = table.order(hooks)
    if table.wants_csv:
        return table.csv_response(hooks, _("Webhooks"))
    page = table.paginate(hooks)  # UIX-050 (UIX-012)
    return render(
        request,
        "webhooks/list.html",
        {
            "table": table,
            "rows": table.rows(page),
            "page": page,
            "retention_days": webhooks.RETENTION_DAYS,
            **_rights(request),
        },
    )


@module_required(Module.ADMINISTRATION, Level.WRITE)
def webhook_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create a webhook, or change one (API-012)."""
    webhook = get_object_or_404(Webhook, pk=pk) if pk else None
    initial = (
        {name: getattr(webhook, name) for name in ("url", "description", "events", "is_active")}
        if webhook
        else {"is_active": True}
    )
    form = WebhookForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        saved = form.save(webhook, request.user)
        if saved is not None:
            hook, secret = saved
            if secret:
                request.session[SESSION_KEY_NEW_SECRET] = {"pk": hook.pk, "secret": secret}
                messages.success(request, _("The webhook was created. Copy its secret into the receiving system."))
            else:
                messages.success(request, _("The webhook was saved."))
            return redirect("webhooks:detail", pk=hook.pk)
    return render(request, "webhooks/form.html", {"form": form, "webhook": webhook})


@module_required(Module.ADMINISTRATION)
def webhook_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One webhook: settings, secret, test, and its deliveries (API-012).

    Right after creating it, the page shows the secret once.
    """
    webhook = get_object_or_404(Webhook, pk=pk)
    secret_context: dict[str, Any] = {}
    waiting = request.session.get(SESSION_KEY_NEW_SECRET)
    if isinstance(waiting, dict) and waiting.get("pk") == webhook.pk:
        del request.session[SESSION_KEY_NEW_SECRET]
        if _rights(request)["can_edit"]:
            secret_context = {"secret": waiting.get("secret", ""), "is_new": True}
    return _detail_page(request, webhook, secret_context)


def _detail_page(request: HttpRequest, webhook: Webhook, secret_context: dict[str, Any]) -> HttpResponse:
    rights = _rights(request)
    deliveries = webhook.deliveries.all()
    chosen_status = request.GET.get("status", "")
    if chosen_status in DeliveryStatus.values:
        deliveries = deliveries.filter(status=chosen_status)
    page = paginate(request, deliveries)
    labels = {name: event.label for name, event in webhook_events.EVENTS.items()}
    rows = [
        (
            delivery,
            labels.get(delivery.event, delivery.event),
            json.dumps(delivery.envelope(), ensure_ascii=False, indent=2),
        )
        for delivery in page
    ]
    return render(
        request,
        "webhooks/detail.html",
        {
            "webhook": webhook,
            "event_labels": [(name, labels.get(name, name)) for name in webhook.events or []],
            "page": page,
            "rows": rows,
            "statuses": DeliveryStatus.choices,
            "chosen_status": chosen_status,
            "retention_days": webhooks.RETENTION_DAYS,
            "max_attempts": webhooks.MAX_ATTEMPTS,
            "switch_off_after": webhooks.SWITCH_OFF_AFTER,
            **rights,
            **secret_context,
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def webhook_secret(request: HttpRequest, pk: int) -> HttpResponse:
    """Show the secret ("Show secret"), or replace it ("Create a new one") (API-012)."""
    webhook = get_object_or_404(Webhook, pk=pk)
    context: dict[str, Any] = {"secret_error": ""}
    if request.POST.get("renew"):
        context.update(secret=webhooks.renew_secret(webhook), is_renewed=True)
    else:
        try:
            context["secret"] = webhooks.secret_of(webhook)
        except SecretUnreadableError:
            context["secret_error"] = _(
                "The secret cannot be read any more (was the key of the installation changed?). Create a new one."
            )
    if request.headers.get("HX-Request"):
        return render(request, "webhooks/_secret.html", {"webhook": webhook, "can_edit": True, **context})
    return _detail_page(request, webhook, context)


def _report(request: HttpRequest, delivery: WebhookDelivery, *, arrived: str, failed: str) -> None:
    """Say how a delivery sent by hand went."""
    if delivery.status == DeliveryStatus.DELIVERED:
        messages.success(
            request,
            arrived % {"status": delivery.last_status_code, "milliseconds": delivery.last_duration_ms or 0},
        )
    else:
        messages.error(request, failed % {"error": delivery.last_error})


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def webhook_test(request: HttpRequest, pk: int) -> HttpResponse:
    """Send a ``ping`` now and say what came back (API-012)."""
    webhook = get_object_or_404(Webhook, pk=pk)
    delivery = webhooks.send_test(webhook)
    _report(
        request,
        delivery,
        arrived=_("The test arrived: the receiver answered %(status)s after %(milliseconds)d ms."),
        failed=_("The test failed: %(error)s"),
    )
    return redirect("webhooks:detail", pk=webhook.pk)


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def webhook_redeliver(request: HttpRequest, pk: int, delivery_pk: int) -> HttpResponse:
    """Send a failed delivery again, now (API-012)."""
    webhook = get_object_or_404(Webhook, pk=pk)
    delivery = get_object_or_404(webhook.deliveries.select_related("webhook"), pk=delivery_pk)
    try:
        webhooks.redeliver(delivery)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        _report(
            request,
            delivery,
            arrived=_("Sent again: the receiver answered %(status)s after %(milliseconds)d ms."),
            failed=_("Sending again failed: %(error)s"),
        )
    return redirect("webhooks:detail", pk=webhook.pk)


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def webhook_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a webhook with its deliveries (API-012)."""
    webhook = get_object_or_404(Webhook, pk=pk)
    webhook.delete()
    messages.success(request, _("The webhook was deleted."))
    return redirect("webhooks:list")
