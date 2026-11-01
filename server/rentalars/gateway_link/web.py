# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → "Gateway": pair an app, list the paired devices, lock one out (GWL-011).

The same work as ``sudo rentalars gateway pair`` / ``devices`` / ``revoke``, for an administrator in the browser – so that
nobody needs a shell on the server to pair a phone. Connecting the server to the gateway (the keys, the service) stays a
command on the server (``rentalars gateway connect``), like the other things that need root.

The pairing code is shown once, in the answer to the POST, and is not stored anywhere but in the offer itself (which
holds the secret encrypted, valid for ten minutes at most and once only). Pairing and locking out are written to the
change log.
"""

from __future__ import annotations

import io
import time
from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.models import User
from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.audit import record_event
from rentalars.core.models import CompanyProfile
from rentalars.gateway_link import service
from rentalars.gateway_link.models import GatewayDevice, GatewayLink, GatewayPairing

#: A link whose last answer is older than this is shown as not connected (as in the self-check).
POLL_MAX_AGE = 90
#: How many devices the page lists (the revoked ones are folded away below the active ones).
LIST_LIMIT = 300


class PairingForm(forms.Form):
    """The account the app is paired for, a name for the device and how long the code is valid (GWL-011)."""

    user = forms.ModelChoiceField(
        label=gettext_lazy("Account"),
        queryset=User.objects.none(),
        help_text=gettext_lazy(
            "The app signs in as this account and has its rights. Whoever scans the code gets this access."
        ),
    )
    device_name = forms.CharField(
        label=gettext_lazy("Name of the device"),
        required=False,
        max_length=64,
        help_text=gettext_lazy("For the list, e.g. “Anna’s phone”. The app can fill it in itself."),
    )
    minutes = forms.TypedChoiceField(
        label=gettext_lazy("Valid for"),
        coerce=int,
        choices=[(1, gettext_lazy("1 minute")), (5, gettext_lazy("5 minutes")), (10, gettext_lazy("10 minutes"))],
        initial=10,
        help_text=gettext_lazy("The code works once only, and only until this time has passed."),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(is_active=True).order_by("username")  # type: ignore[attr-defined]
        self.fields["device_name"].widget.attrs.update({"autocomplete": "off"})


def qr_svg(text: str) -> SafeString:
    """The pairing code as a QR code (SVG, black on white)."""
    import segno

    output = io.BytesIO()
    segno.make(text, error="l").save(output, kind="svg", border=1, xmldecl=False, svgns=True, omitsize=True)
    return mark_safe(output.getvalue().decode("utf-8"))  # noqa: S308 - made by segno from the pairing text


def state_of(link: GatewayLink | None) -> dict[str, Any]:
    """What the page says about the link: connected at all, answering, last error."""
    if link is None or not link.is_connected:
        return {"connected": False}
    age = int((timezone.now() - link.last_poll_at).total_seconds()) if link.last_poll_at else None
    return {
        "connected": True,
        "link": link,
        "age": age,
        "answering": age is not None and age <= POLL_MAX_AGE,
        "no_answer_yet": age is None,
    }


@module_required(Module.ADMINISTRATION)
def gateway_page(request: HttpRequest) -> HttpResponse:
    """The link, the form to pair an app, the paired devices; a POST makes a pairing code (GWL-011)."""
    can_change = request_rights(request).can_delete(Module.ADMINISTRATION)
    link = GatewayLink.current()
    state = state_of(link)
    form = PairingForm(initial={"minutes": 10})
    offer: dict[str, Any] | None = None
    if request.method == "POST":
        if not can_change:
            messages.error(request, _("Only administrators who may delete in the settings can pair an app."))
            return redirect("gateway:page")
        form = PairingForm(request.POST)
        if not state["connected"]:
            messages.error(request, _("No gateway is connected. Connect it on the server first."))
            return redirect("gateway:page")
        if form.is_valid():
            user = form.cleaned_data["user"]
            name = form.cleaned_data["device_name"].strip()
            minutes = form.cleaned_data["minutes"]
            try:
                made = service.create_offer(
                    link,  # type: ignore[arg-type]
                    user,
                    created_by=request.user,
                    device_name=name,
                    lifetime=minutes * 60,
                    organisation=CompanyProfile.load().name,
                )
            except (service.GatewayLinkError, OSError) as error:
                form.add_error(None, _("The code could not be made: %(error)s") % {"error": error})
            else:
                code = made.encode()
                record_event(user, "gateway.pairing_offered", {"device": name or "–", "minutes": minutes})
                offer = {
                    "user": user,
                    "text": code,
                    "qr": qr_svg(code),
                    "minutes": max(1, (made.expires - int(time.time())) // 60),
                }
                form = PairingForm(initial={"minutes": 10})
    devices = list(GatewayDevice.objects.select_related("user", "revoked_by").order_by("-paired_at")[:LIST_LIMIT])
    context = {
        "state": state,
        "form": form,
        "offer": offer,
        "can_change": can_change,
        "devices": [device for device in devices if device.revoked_at is None],
        "revoked": [device for device in devices if device.revoked_at is not None],
        "open_offers": GatewayPairing.objects.filter(expires_at__gt=int(time.time())).count(),
    }
    response = render(request, "gateway_link/page.html", context)
    if offer is not None:
        add_never_cache_headers(response)  # the code is a credential: not into a cache or the history of the browser
    return response


@require_POST
@module_required(Module.ADMINISTRATION)
def revoke(request: HttpRequest, device_id: str) -> HttpResponse:
    """Lock a device out at once (GWL-011); the app's next request ends with a revocation message."""
    if not request_rights(request).can_delete(Module.ADMINISTRATION):
        messages.error(request, _("Only administrators who may delete in the settings can lock a device out."))
        return redirect("gateway:page")
    device = get_object_or_404(GatewayDevice.objects.select_related("user"), device_id=device_id)
    if device.revoked_at is not None:
        return redirect("gateway:page")
    try:
        service.revoke_device(GatewayLink.current(), device, by=request.user)
    except (service.GatewayLinkError, OSError) as error:
        # Locked out here in any case (every request is checked here); only the gateway's own list is not up to date.
        messages.warning(
            request,
            _("%(device)s is locked out here, but the gateway could not be told: %(error)s")
            % {"device": device.name or _("The device"), "error": error},
        )
    else:
        messages.success(
            request,
            _("%(device)s of %(user)s is locked out. Its next request ends with a message that it is no longer paired.")
            % {"device": device.name or _("The device"), "user": device.user},
        )
    record_event(device, "gateway.device_revoked", {"user": str(device.user), "device": device.name or "–"})
    return redirect("gateway:page")
