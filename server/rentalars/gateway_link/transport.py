# SPDX-License-Identifier: GPL-3.0-or-later
"""Blocking HTTP clients: to the gateway (pinned certificate or authority check) and to the application itself."""

from __future__ import annotations

import hashlib
import http.client
import socket
import ssl
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass
class HttpAnswer:
    """What came back: status, headers (lower case names; ``all_headers`` keeps repeated ones) and body."""

    status: int
    headers: dict[str, str]
    body: bytes
    all_headers: list[tuple[str, str]] = field(default_factory=list)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS that accepts exactly one certificate (by SHA-256) and does not look at names or authorities.

    This is how the gateway is trusted when it has a self-made certificate: by the fingerprint that
    ``rentalars-gateway enroll`` printed and that the administrator carried over with the connection text.
    """

    def __init__(self, host: str, port: int, *, fingerprint: str, timeout: float) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(host, port, context=context, timeout=timeout)
        self.fingerprint = fingerprint.lower().replace(":", "")

    def connect(self) -> None:
        """Connect, then compare the certificate with the pinned one; close and fail if it differs."""
        super().connect()
        der = self.sock.getpeercert(binary_form=True)  # type: ignore[union-attr]
        if hashlib.sha256(der or b"").hexdigest() != self.fingerprint:
            self.sock.close()  # type: ignore[union-attr]
            raise ssl.SSLError("The certificate of the gateway does not match the stored fingerprint.")


class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTP over a Unix socket: how the link service reaches the application server on the same machine."""

    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = path

    def connect(self) -> None:
        """Connect to the socket."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def _answer(response: http.client.HTTPResponse, limit: int) -> HttpAnswer:
    pairs = response.getheaders()
    body = response.read(limit + 1)
    return HttpAnswer(response.status, {name.lower(): value for name, value in pairs}, body, pairs)


class GatewayTransport:
    """Calls the gateway. One connection per call keeps it simple; the polls last 25 seconds anyway."""

    def __init__(self, base_url: str, fingerprint: str = "", timeout: float = 70.0) -> None:
        parts = urlsplit(base_url)
        self.scheme = parts.scheme
        self.host = parts.hostname or ""
        self.port = parts.port or (443 if parts.scheme == "https" else 80)
        self.fingerprint = fingerprint
        self.timeout = timeout

    def request(
        self, method: str, target: str, headers: dict[str, str] | None = None, body: bytes | None = None
    ) -> HttpAnswer:
        """One call; the answer is read completely (at most 13 MiB)."""
        connection: http.client.HTTPConnection
        if self.scheme == "https" and self.fingerprint:
            connection = PinnedHTTPSConnection(self.host, self.port, fingerprint=self.fingerprint, timeout=self.timeout)
        elif self.scheme == "https":
            connection = http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout)
        else:
            connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, target, body=body, headers=headers or {})
            return _answer(connection.getresponse(), 13 * 1024 * 1024)
        finally:
            connection.close()


def local_connection(local: str, timeout: float) -> http.client.HTTPConnection:
    """A connection to the application server: its socket (a path) or ``http://127.0.0.1:PORT``."""
    if local.startswith("/"):
        return UnixHTTPConnection(local, timeout)
    parts = urlsplit(local)
    return http.client.HTTPConnection(parts.hostname or "127.0.0.1", parts.port or 80, timeout=timeout)


def read_local_answer(connection: http.client.HTTPConnection, limit: int) -> HttpAnswer:
    """The answer of the application, read completely (a larger one is cut one byte over ``limit``)."""
    return _answer(connection.getresponse(), limit)
