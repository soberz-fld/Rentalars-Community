# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings → "Serveradresse und Zertifikat" (ADM-016).

The page shows the current address and certificate, prepares a change and
shows the one command that applies it on the server. Everything that needs
root is done by that command (``deploy/address.py``); the page has no button
that changes the server – like the encryption (ADM-009).
"""

from __future__ import annotations

import datetime

from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core import server_address
from rentalars.core.address_models import AddressChange, AddressChangeStatus, CertificateKind

#: The choices of the form, each with what it means.
KIND_HELP = {
    CertificateKind.LETSENCRYPT: gettext_lazy(
        "Free, renewed automatically. The name must be in the public DNS and port 80 reachable from the internet."
    ),
    CertificateKind.SELF_SIGNED: gettext_lazy(
        "Made on the server, for trying things out or a closed network. Browsers warn until it is trusted on every device."
    ),
    CertificateKind.OWN: gettext_lazy(
        "A certificate you have, e.g. from your provider or the certificate authority of your company: upload it "
        "with its chain and the private key."
    ),
    CertificateKind.PROXY: gettext_lazy(
        "Another server in front (a TLS proxy) encrypts; only the name changes here, the certificates stay."
    ),
}


class ServerAddressForm(forms.Form):
    """A new address with the source of its certificate (ADM-016)."""

    host = forms.CharField(
        label=gettext_lazy("New host name"),
        max_length=260,
        help_text=gettext_lazy(
            "The name people will type in the browser, e.g. rentalars.example.com – without https:// and without "
            "a port. It must point to this server in the DNS."
        ),
    )
    certificate_kind = forms.ChoiceField(
        label=pgettext_lazy("TLS", "Certificate"), choices=CertificateKind.choices, widget=forms.RadioSelect
    )
    email = forms.CharField(
        label=gettext_lazy("E-mail address for Let's Encrypt"),
        required=False,
        max_length=254,
        help_text=gettext_lazy("Only for Let's Encrypt: notices about the expiry go here."),
    )
    certificate = forms.FileField(
        label=gettext_lazy("Certificate with its chain (PEM)"),
        required=False,
        help_text=gettext_lazy(
            "Only for your own certificate: the server's certificate first, then the intermediate certificates."
        ),
    )
    private_key = forms.FileField(
        label=gettext_lazy("Private key (PEM, without password)"),
        required=False,
        help_text=gettext_lazy(
            "Only for your own certificate. It is stored encrypted and deleted from Rentalars once the command has installed it."
        ),
    )
    redirect_old = forms.BooleanField(
        label=gettext_lazy("Redirect the old address to the new one"),
        required=False,
        initial=True,
        help_text=gettext_lazy(
            "Links in old e-mails, printed QR codes and bookmarks keep working as long as the old name points to "
            "this server."
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["host"].widget.attrs.update({"autocomplete": "off", "spellcheck": "false", "inputmode": "url"})
        self.fields["email"].widget.attrs.update({"autocomplete": "email", "inputmode": "email"})
        self.fields["certificate"].widget.attrs["accept"] = ".pem,.crt,.cer,application/x-pem-file"
        self.fields["private_key"].widget.attrs["accept"] = ".pem,.key"


def _read_upload(upload: object) -> bytes:
    if not upload:
        return b""
    data = upload.read(server_address.MAX_PEM_BYTES + 1)  # type: ignore[attr-defined]
    return data if isinstance(data, bytes) else b""


@module_required(Module.ADMINISTRATION)
def server_address_page(request: HttpRequest) -> HttpResponse:
    """Show address and certificate; prepare a change (POST, administrators with the delete right)."""
    can_prepare = request_rights(request).can_delete(Module.ADMINISTRATION)
    current = server_address.current_state()
    initial_kind = current.kind if current.kind in CertificateKind.values else CertificateKind.LETSENCRYPT
    form = ServerAddressForm(initial={"certificate_kind": initial_kind, "redirect_old": True})
    if request.method == "POST":
        if not can_prepare:
            messages.error(request, _("Only administrators who may delete in the settings can prepare a change."))
            return redirect("core:server_address")
        form = ServerAddressForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            try:
                change = server_address.prepare(
                    request.user,
                    host=data["host"],
                    kind=data["certificate_kind"],
                    email=data["email"],
                    redirect_old=data["redirect_old"],
                    certificate=_read_upload(data.get("certificate")),
                    private_key=_read_upload(data.get("private_key")),
                    current=current,
                )
            except server_address.AddressError as error:
                for name, texts in error.errors.items():
                    for text in texts:
                        form.add_error(name if name in form.fields else None, text)
            else:
                messages.success(
                    request,
                    _("The change is prepared. Run the command shown on the server – until then nothing changes.")
                    if not server_address.blocking_errors(change)
                    else _("The change is prepared, but a check failed: the command will most likely stop there."),
                )
                return redirect(f"{request.path}#prepared")
    change = server_address.latest()
    certificate = dict(current.certificate) if current.certificate else None
    if certificate:
        certificate["not_after_moment"] = datetime.datetime.fromisoformat(certificate["not_after"])
    earlier = list(AddressChange.objects.select_related("prepared_by").exclude(pk=getattr(change, "pk", None))[:5])
    return render(
        request,
        "core/server_address.html",
        {
            "current": current,
            "certificate": certificate,
            "change": change,
            "steps": server_address.steps(change) if change and change.is_open else [],
            "earlier": earlier,
            "form": form,
            "kind_help": KIND_HELP,
            "can_prepare": can_prepare,
            "statuses": AddressChangeStatus,
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def server_address_discard(request: HttpRequest, token: str) -> HttpResponse:
    """Throw a prepared change away; its command then refuses to run."""
    change = get_object_or_404(AddressChange, token=token)
    if change.is_open:
        server_address.discard(change)
        messages.success(request, _("The prepared change was discarded; its command no longer works."))
    return redirect("core:server_address")
