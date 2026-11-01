# SPDX-License-Identifier: GPL-3.0-or-later
"""What the link to the gateway keeps in the database.

``GatewayLink``     the one link to a gateway, with the two key pairs of this installation
``GatewayDevice``   a paired app (phone, tablet): its public key and the account it was paired for
``GatewayPairing``  an open, one-off pairing offer (the text and QR code that an administrator shows)
``GatewayReplay``   request ids already seen, so that a repeated request is not carried out twice
``GatewayTokenBinding``  an API token issued through a device works only through that device

The private keys are stored encrypted with a key derived from ``secret_key`` of the configuration file, like the
other secrets of the application (``core.crypto``). They are therefore part of every backup, and a restore on
another server (with the configuration file of the backup) brings them back.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from rentalars.core.crypto import decrypt_secret, encrypt_secret


class GatewayLink(models.Model):
    """The link of this installation to its gateway (one row). Created by ``rentalars gateway connect``."""

    #: Where the gateway is reached, e.g. ``https://gateway.example.de:8799``; empty while not connected.
    gateway_url = models.CharField(max_length=300, blank=True)
    #: SHA-256 of the gateway's TLS certificate (hex, lower case); empty for a certificate of a public authority.
    gateway_fingerprint = models.CharField(max_length=64, blank=True)
    gateway_id = models.CharField(max_length=100, blank=True)
    #: ECDSA key that signs every call to the gateway (stored encrypted, PKCS#8 PEM).
    link_key = models.TextField(blank=True)
    #: ECDH key that opens the requests of the apps (stored encrypted, PKCS#8 PEM).
    e2e_key = models.TextField(blank=True)
    enrolled_at = models.DateTimeField(null=True, blank=True)
    #: The last time the polling service got an answer from the gateway (for ``rentalars gateway status``).
    last_poll_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    #: Announcement of a new gateway address or certificate (move), attached to every sealed answer while set.
    move_url = models.CharField(max_length=300, blank=True)
    move_fingerprint = models.CharField(max_length=64, blank=True)
    move_next_fingerprint = models.CharField(max_length=64, blank=True)
    move_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Gateway link"

    def __str__(self) -> str:
        return self.gateway_url or "(not connected)"

    @classmethod
    def current(cls) -> GatewayLink | None:
        """The link, or ``None`` if there is none yet."""
        return cls.objects.order_by("pk").first()

    @property
    def is_connected(self) -> bool:
        """Whether a gateway is configured (enrolled)."""
        return bool(self.gateway_url and self.link_key and self.enrolled_at)

    def set_link_key_pem(self, pem: bytes) -> None:
        """Store the private link key (encrypted)."""
        self.link_key = encrypt_secret(pem.decode("ascii"))

    def link_key_pem(self) -> bytes:
        """The private link key as PEM."""
        return decrypt_secret(self.link_key).encode("ascii")

    def set_e2e_key_pem(self, pem: bytes) -> None:
        """Store the private end-to-end key (encrypted)."""
        self.e2e_key = encrypt_secret(pem.decode("ascii"))

    def e2e_key_pem(self) -> bytes:
        """The private end-to-end key as PEM."""
        return decrypt_secret(self.e2e_key).encode("ascii")


class GatewayDevice(models.Model):
    """A paired app. The id is derived from the public key (the first 16 bytes of its SHA-256), nobody chooses it."""

    device_id = models.CharField(max_length=32, unique=True, help_text="16 bytes in hex")
    public_key = models.CharField(max_length=130, help_text="65 bytes in hex (uncompressed P-256 point)")
    name = models.CharField(max_length=64, blank=True)
    platform = models.CharField(max_length=20, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gateway_devices")
    paired_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-paired_at"]

    def __str__(self) -> str:
        return f"{self.name or 'device'} ({self.device_id[:8]})"

    @property
    def is_usable(self) -> bool:
        """Not revoked, and the account it was paired for may still log in."""
        return self.revoked_at is None and self.user.is_active


class GatewayPairing(models.Model):
    """An open pairing offer. It holds once, for ten minutes at most; the secret is the salt of the key derivation."""

    pairing_id = models.CharField(max_length=32, unique=True, help_text="16 bytes in hex")
    secret = models.TextField(help_text="32 bytes, stored encrypted")
    expires_at = models.BigIntegerField(db_index=True, help_text="seconds since 1970")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gateway_pairings")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    device_name = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"pairing {self.pairing_id[:8]} for {self.user_id}"

    def set_secret(self, secret: bytes) -> None:
        """Store the 32 secret bytes (encrypted)."""
        self.secret = encrypt_secret(secret.hex())

    def secret_bytes(self) -> bytes:
        """The 32 secret bytes."""
        return bytes.fromhex(decrypt_secret(self.secret))


class GatewayReplay(models.Model):
    """A request id (device and request) that was seen; remembered until the request could no longer be accepted."""

    key = models.CharField(max_length=64, unique=True, help_text="device id and request id, 32 bytes in hex")
    expires_at = models.BigIntegerField(db_index=True, help_text="seconds since 1970")

    def __str__(self) -> str:
        return self.key[:8]


class GatewayTokenBinding(models.Model):
    """An API token that was issued through a device. It works only through that device (GWS-041)."""

    token = models.OneToOneField("accounts.ApiToken", on_delete=models.CASCADE, related_name="gateway_binding")
    #: ``None`` once the device was deleted: the token then works nowhere (it is not freed for the direct way).
    device = models.ForeignKey(GatewayDevice, null=True, on_delete=models.SET_NULL, related_name="bound_tokens")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"token {self.token_id} -> device {self.device_id}"
