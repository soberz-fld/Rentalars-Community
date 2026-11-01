# SPDX-License-Identifier: GPL-3.0-or-later
"""Tokens issued through a device work only through that device (GWS-041).

The link service tells the application which device a request came from in the header ``X-Rentalars-Device``.
A browser or an app on the direct way could send that header too, so it carries a proof that only this installation
can make: ``<device id>.<HMAC>`` with a key derived from ``secret_key``. The application trusts the header only with
a valid proof.

The binding itself is a row (``GatewayTokenBinding``). The link service creates it when a device creates a token
(``POST /api/v1/tokens``); the authentication of the API (``accounts.authentication``) asks :func:`check_token`.
A token without a binding – every token issued on the direct way – is not touched at all.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from functools import cache
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

#: The header with which the link service names the device of a request.
DEVICE_HEADER = "X-Rentalars-Device"
#: How the application sees that header in ``request.META``.
DEVICE_META = "HTTP_X_RENTALARS_DEVICE"


@cache
def _key(secret_key: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"rentalars gateway device assertion v1").derive(
        secret_key.encode("utf-8")
    )


def device_assertion(device_id: str) -> str:
    """The value of the header for a device: its id (hex) and the proof."""
    proof = hmac.new(_key(settings.SECRET_KEY), device_id.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{device_id}.{proof}"


def device_of_assertion(value: str) -> str | None:
    """The device id (hex) of a header value with a valid proof, otherwise ``None``."""
    device_id, _dot, proof = value.partition(".")
    if len(device_id) != 32 or not proof:
        return None
    expected = hmac.new(_key(settings.SECRET_KEY), device_id.encode("ascii", "ignore"), hashlib.sha256).hexdigest()
    # Compared as bytes: ``compare_digest`` refuses a text with non-ASCII characters (a header the client controls).
    return device_id if hmac.compare_digest(expected.encode("ascii"), proof.encode("utf-8")) else None


def pseudo_address(device_id: bytes) -> str:
    """An address derived from the device id (``fd00::/8``), used where the application counts per address (GWS-040).

    Every request through the gateway reaches the application from the same local process. If the lock-out after
    failed logins and the limits hung on that address, one device could lock out all the others. With this address
    each device only locks itself.
    """
    return str(ipaddress.IPv6Address(b"\xfd" + device_id[:8] + bytes(7)))


def check_token(request: Any, token: Any) -> bool:
    """Whether ``token`` may be used for ``request``: unbound tokens always, bound ones only through their device."""
    try:
        binding = token.gateway_binding
    except ObjectDoesNotExist:  # no binding: the common case
        return True
    if binding.device is None:  # the device is gone: the token works nowhere any more
        return False
    return device_of_assertion(request.META.get(DEVICE_META, "")) == binding.device.device_id
