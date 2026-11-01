# SPDX-License-Identifier: GPL-3.0-or-later
"""A prepared change of the server address and its certificate (ADM-016).

The settings page "Serveradresse und Zertifikat" prepares the change; the
operator applies it on the server with ``sudo rentalars address apply TOKEN``
(``deploy/address.py``), which needs root and therefore never runs inside
the application. This model is what both sides share: the page writes it,
the command reads it through ``manage.py address_change export`` and records
its result through ``manage.py address_change record``.

The uploaded certificate and its key are not kept in the database but as
files in the data folder (``<data_dir>/address/<token>/``, mode 0600, the key
encrypted like other stored secrets); see :mod:`rentalars.core.server_address`.

Imported at the end of ``rentalars/core/models.py`` so that Django finds it.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.core.audit import AuditedModel


class AddressChangeStatus(models.TextChoices):
    """Where a prepared change stands (ADM-016)."""

    PREPARED = "prepared", _("prepared")
    APPLIED = "applied", _("applied")
    FAILED = "failed", _("failed")
    SUPERSEDED = "superseded", _("replaced by a newer one")
    DISCARDED = "discarded", _("discarded")


class CertificateKind(models.TextChoices):
    """Where the certificate of the new address comes from (ADM-016, NFA-035)."""

    LETSENCRYPT = "letsencrypt", _("Let's Encrypt")
    SELF_SIGNED = "selfsigned", _("Self-signed certificate")
    OWN = "own", _("Own certificate")
    PROXY = "proxy", _("A server in front encrypts")


class AddressChange(AuditedModel):
    """One prepared change of the address under which Rentalars is reached (ADM-016)."""

    #: What the command names: ``sudo rentalars address apply <token>``.
    token = models.CharField(max_length=32, unique=True, editable=False)
    host = models.CharField(_("host name"), max_length=253)
    certificate_kind = models.CharField(
        pgettext_lazy("TLS", "certificate"), max_length=20, choices=CertificateKind.choices
    )
    #: For Let's Encrypt: where notices about the expiry go.
    email = models.EmailField(_("e-mail address for Let's Encrypt"), blank=True)
    #: Whether the old name keeps working as a redirect to the new one.
    redirect_old = models.BooleanField(_("redirect the old address"), default=True)
    #: The address before the change: ``[rentalars] url`` when it was prepared.
    previous_url = models.CharField(_("previous address"), max_length=300, blank=True)
    #: An uploaded certificate: names, issuer, expiry, fingerprint – never the key.
    certificate_info = models.JSONField(default=dict, blank=True)
    #: What the page could check: ``[{"state": "ok|warning|error|note", "title": …, "detail": …}]``.
    checks = models.JSONField(default=list, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=AddressChangeStatus.choices, default=AddressChangeStatus.PREPARED
    )
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("prepared by"),
    )
    prepared_at = models.DateTimeField(_("prepared"), default=timezone.now)
    #: When the command ran last, and the account on the server that ran it (``SUDO_USER``).
    applied_at = models.DateTimeField(_("applied"), null=True, blank=True)
    applied_by = models.CharField(_("applied by"), max_length=100, blank=True)
    #: The error of a failed run, or a note of a successful one.
    result_message = models.TextField(_("result"), blank=True)
    #: What the command reported: backup folder, certificate expiry, redirect.
    result = models.JSONField(default=dict, blank=True)

    audit_exclude = frozenset({"checks", "certificate_info", "result"})

    class Meta:
        verbose_name = _("change of the server address")
        verbose_name_plural = _("changes of the server address")
        ordering = ["-prepared_at", "-id"]

    def __str__(self) -> str:
        return self.host

    @property
    def url(self) -> str:
        """The new address as it will stand in the configuration file."""
        return f"https://{self.host}"

    @property
    def command(self) -> str:
        """The one command the operator runs on the server."""
        return f"sudo rentalars address apply {self.token}"

    @property
    def is_open(self) -> bool:
        """Whether the command may still apply it (a failed run can be repeated)."""
        return self.status in {AddressChangeStatus.PREPARED, AddressChangeStatus.FAILED}
