# SPDX-License-Identifier: GPL-3.0-or-later
"""The link service: fetch requests from the gateway, check and open them, carry them out, seal the answers.

What happens to a request, in this order (``ServerLink._call``); a step that fails ends the processing and
nothing is carried out:

1. the device is known (otherwise: no answer),
2. its signature over the sealed bytes is valid (otherwise: no answer),
3. the body can be opened with the end-to-end key (otherwise: no answer),
4. the device is not revoked and its account is active (otherwise: sealed ``device_revoked``),
5. its clock is within the window (otherwise: sealed ``time_skew`` with the server's time),
6. the request id was not seen before (otherwise: no answer); a time probe ends here with the time,
7. method and path are allowed – ``/api/v1/`` only (otherwise: sealed ``path_forbidden``),
8. the request is carried out against the application on this machine and the answer sealed.

The gateway is not trusted (``docs/sicherheit.md`` of the gateway): everything it hands over is checked here.
"""

from __future__ import annotations

import contextlib
import datetime
import http.client
import json
import logging
import mimetypes
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from rentalars.config import GatewayConfig
from rentalars.gateway_link import protocol
from rentalars.gateway_link.binding import DEVICE_HEADER, device_assertion, pseudo_address
from rentalars.gateway_link.models import GatewayDevice, GatewayLink, GatewayPairing, GatewayReplay, GatewayTokenBinding
from rentalars.gateway_link.transport import GatewayTransport, HttpAnswer, local_connection, read_local_answer

log = logging.getLogger("rentalars.gateway_link")

#: What the gateway accepts in the directory (docs/protokoll.md, chapter 6.2).
MAX_DEVICES = 2000
MAX_PAIRINGS = 100
#: Open pairing offers per account.
MAX_PAIRINGS_PER_USER = 20
#: A pairing offer holds this many seconds (the gateway keeps codes for an hour at most).
PAIRING_LIFETIME = 600

HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
#: Headers of the apps that are never passed on: what the link service sets itself, and what could pose as a proxy.
STRIPPED_FROM_APPS = HOP_BY_HOP | {"content-length", "host", "x-real-ip", "forwarded", "origin"}
STRIPPED_PREFIXES = ("proxy-", "x-forwarded-", "x-rentalars-")
#: Headers of the answer that stay behind: they describe the connection to the application, not the answer.
STRIPPED_FROM_ANSWERS = HOP_BY_HOP | {"content-length", "x-accel-redirect"}
ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
API_PREFIX = "/api/v1/"
FORBIDDEN_IN_PATH = ("..", "\\", "\x00", "//", "%2e", "%2E", "%5c", "%5C", "%00", "#")
#: What is refused in the query string of an address (everything else, such as ``..`` or ``//``, is a value).
QUERY_FORBIDDEN = ("\\", "\x00", "%00", "#")
#: The addresses of the API that tie an account or a token to a device; the router also accepts a format suffix.
_LOGIN_PATH = re.compile(r"/api/v1/auth/login(\.[A-Za-z0-9]+)?/?")
_TOKEN_PATH = re.compile(r"/api/v1/tokens(\.[A-Za-z0-9]+)?/?")
_HEADER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}")
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


class GatewayLinkError(Exception):
    """The link could not do what was asked (not connected, gateway refused, ...); the text is for the operator."""


def error_frame(status: int, code: str, message: str, clock_ms: int, extra: dict[str, Any] | None = None) -> bytes:
    """A refusal of the link itself in the shape of an API error, so that the app needs no special case."""
    body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
    meta: dict[str, Any] = {
        "status": status,
        "headers": [["Content-Type", "application/json"]],
        "time": clock_ms,
        "gw_error": code,
    }
    meta.update(extra or {})
    return protocol.pack_frame(meta, body)


# --- calls to the gateway -------------------------------------------------------------------------------------------


class GatewayClient:
    """Signed calls to ``/v1/server/...`` of the gateway."""

    def __init__(self, url: str, fingerprint: str, link_key: Any, clock: Callable[[], float] = time.time) -> None:
        self.transport = GatewayTransport(url, fingerprint)
        self.link_key = link_key
        self.clock = clock

    @classmethod
    def for_link(cls, link: GatewayLink) -> GatewayClient:
        """The client of a stored link."""
        key = protocol.private_from_pem(link.link_key_pem())
        return cls(link.gateway_url, link.gateway_fingerprint, key)

    def signed(self, method: str, target: str, body: bytes = b"") -> HttpAnswer:
        """One call, signed with the link key (head and digest first, so that the gateway can check before it reads)."""
        ts = int(self.clock())
        nonce = os.urandom(16)
        signature = protocol.sign(self.link_key, protocol.link_signature_input(method, target, ts, nonce, body))
        headers = {
            "X-RGW-Time": str(ts),
            "X-RGW-Nonce": protocol.b64e(nonce),
            "X-RGW-Signature": protocol.b64e(signature),
            "X-RGW-Digest": protocol.b64e(protocol.sha256(body)),
            "Content-Length": str(len(body)),
        }
        return self.transport.request(method, target, headers, body)

    @staticmethod
    def enroll(url: str, fingerprint: str, token: str, link_key: Any) -> dict[str, Any]:
        """Link up with the gateway using the one-off token of ``rentalars-gateway enroll``."""
        document = json.dumps({"token": token, "link_public": protocol.b64e(protocol.public_bytes(link_key))}).encode(
            "ascii"
        )
        headers = {"Content-Type": "application/json", "Content-Length": str(len(document))}
        answer = GatewayTransport(url, fingerprint, timeout=30.0).request("POST", "/v1/enroll", headers, document)
        if answer.status != 200:
            raise GatewayLinkError(f"The gateway refused the setup: {answer.status} {_error_text(answer.body)}")
        result = json.loads(answer.body)
        if not isinstance(result, dict):
            raise GatewayLinkError("The gateway answered unexpectedly.")
        return result

    def info(self) -> dict[str, Any]:
        """The gateway's own numbers (version, devices, queue, time)."""
        answer = self.signed("GET", "/v1/server/info")
        if answer.status != 200:
            raise GatewayLinkError(f"The gateway answered {answer.status} {_error_text(answer.body)}")
        result = json.loads(answer.body)
        return result if isinstance(result, dict) else {}

    def push_registry(self) -> dict[str, Any]:
        """Tell the gateway which devices and which pairing offers exist. Idempotent; the gateway replaces its list."""
        now = int(self.clock())
        devices = [
            {
                "id": protocol.b64e(bytes.fromhex(d.device_id)),
                "pub": protocol.b64e(bytes.fromhex(d.public_key)),
                "name": d.name,
            }
            for d in GatewayDevice.objects.filter(revoked_at__isnull=True, user__is_active=True).order_by("pk")[
                :MAX_DEVICES
            ]
        ]
        pairings = [
            {"id": protocol.b64e(bytes.fromhex(p.pairing_id)), "exp": p.expires_at}
            for p in GatewayPairing.objects.filter(expires_at__gt=now).order_by("pk")[:MAX_PAIRINGS]
        ]
        answer = self.signed(
            "PUT", "/v1/server/registry", json.dumps({"devices": devices, "pairings": pairings}).encode("utf-8")
        )
        if answer.status != 200:
            raise GatewayLinkError(
                f"The gateway did not take the list of devices: {answer.status} {_error_text(answer.body)}"
            )
        result = json.loads(answer.body)
        return result if isinstance(result, dict) else {}


def _printable(text: str, limit: int = 200) -> str:
    """Text from outside, safe for a terminal and the database: no control characters, at most ``limit`` characters."""
    return "".join(ch if ch >= " " and ch != "\x7f" else " " for ch in text)[:limit]


def _error_text(body: bytes) -> str:
    try:
        error = json.loads(body)["error"]
        return _printable(f"{error['code']}: {error.get('message', '')}".strip())
    except (ValueError, KeyError, TypeError, AttributeError):
        return ""


# --- carrying a request out against the application ------------------------------------------------------------------


class LocalExecutor:
    """Carries a request out against the application on this machine (its socket, or an address on 127.0.0.1)."""

    def __init__(self, local: str, server_url: str, timeout: float, max_bytes: int) -> None:
        self.local = local
        parts = urlsplit(server_url)
        self.scheme = parts.scheme or "https"
        self.netloc = parts.netloc
        self.origin = f"{self.scheme}://{self.netloc}"
        self.timeout = timeout
        self.max_bytes = max_bytes

    def __call__(
        self, method: str, path: str, headers: list[tuple[str, str]], body: bytes, device: GatewayDevice
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        """Send the request; returns status, headers and body. Raises ``TimeoutError`` or ``OSError``."""
        sent = [*headers]
        sent += [
            ("Host", self.netloc),
            ("Origin", self.origin),
            ("X-Forwarded-Proto", self.scheme),
            ("X-Forwarded-For", pseudo_address(bytes.fromhex(device.device_id))),
            (DEVICE_HEADER, device_assertion(device.device_id)),
        ]
        if body or method in {"POST", "PUT", "PATCH"}:
            sent.append(("Content-Length", str(len(body))))
        connection = local_connection(self.local, self.timeout)
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for name, value in sent:
                connection.putheader(name, value)
            connection.endheaders(body or None)
            answer = read_local_answer(connection, self.max_bytes)
        finally:
            connection.close()
        range_header = next((value for name, value in headers if name.lower() == "range"), "")
        redirected = answer.headers.get("x-accel-redirect", "")
        if redirected:
            return self._protected_file(answer, redirected, range_header)
        return (
            answer.status,
            [(n, v) for n, v in answer.all_headers if n.lower() not in STRIPPED_FROM_ANSWERS],
            answer.body,
        )

    def _protected_file(
        self, answer: HttpAnswer, redirect: str, range_header: str
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        """Do what NGINX does for ``X-Accel-Redirect: /protected-media/…``: deliver the file, with a ``Range`` if asked."""
        kept = [(n, v) for n, v in answer.all_headers if n.lower() not in STRIPPED_FROM_ANSWERS | {"content-type"}]
        prefix = "/protected-media/"
        media_root = Path(settings.MEDIA_ROOT).resolve()
        full = (media_root / redirect.removeprefix(prefix)).resolve() if redirect.startswith(prefix) else None
        if full is None or media_root not in full.parents or not full.is_file():
            return 404, [("Content-Type", "application/json")], b'{"error":{"code":"not_found","message":"Not found."}}'
        size = full.stat().st_size
        too_large = (
            502,
            [("Content-Type", "application/json")],
            b'{"error":{"code":"too_large","message":"Too large."}}',
        )
        content_type = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
        kept += [
            ("Content-Type", content_type),
            ("Accept-Ranges", "bytes"),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"),
        ]
        wanted = _RANGE.fullmatch(range_header.strip()) if range_header else None
        if wanted and (wanted.group(1) or wanted.group(2)):
            first = int(wanted.group(1)) if wanted.group(1) else max(size - int(wanted.group(2)), 0)
            last = min(int(wanted.group(2)), size - 1) if wanted.group(1) and wanted.group(2) else size - 1
            if first > last or first >= size:
                return 416, [*kept, ("Content-Range", f"bytes */{size}")], b""
            if last - first + 1 > self.max_bytes:  # a part of a large file is fine as long as the part fits
                return too_large
            with full.open("rb") as handle:
                handle.seek(first)
                data = handle.read(last - first + 1)
            return 206, [*kept, ("Content-Range", f"bytes {first}-{last}/{size}")], data
        if size > self.max_bytes:
            return too_large
        return answer.status, kept, full.read_bytes()


# --- the service ------------------------------------------------------------------------------------------------------


class ServerLink:
    """This installation's connection to its gateway: poll, check, open, carry out, seal, answer."""

    def __init__(
        self,
        link: GatewayLink,
        config: GatewayConfig,
        executor: Callable[..., tuple[int, list[tuple[str, str]], bytes]],
        *,
        server_url: str,
        organisation: str = "",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.link_id = link.pk
        self.client = GatewayClient.for_link(link)
        self.client.clock = clock
        self.gateway_url = link.gateway_url
        self.gateway_fingerprint = link.gateway_fingerprint
        self.e2e_key = protocol.private_from_pem(link.e2e_key_pem())
        self.e2e_public = protocol.public_bytes(self.e2e_key)
        self.config = config
        self.executor = executor
        self.server_url = server_url
        self.organisation = organisation
        self.clock = clock
        self.max_sealed = config.max_response_mib * 1024 * 1024
        self.stats = {"answered": 0, "dropped": 0, "refused": 0}
        self._noted = 0.0
        self._move: dict[str, Any] | None = None
        self._move_read = 0.0

    # --- the announcement of a move (GWS-015) --------------------------------------------------------------------

    def _gateway_meta(self) -> dict[str, Any] | None:
        """The ``gateway`` field for sealed answers while a move is announced; read from the database every 30 s."""
        now = time.monotonic()
        if now - self._move_read > 30:
            self._move_read = now
            link = GatewayLink.objects.filter(pk=self.link_id).first()
            if link is not None and link.move_url and link.move_fingerprint:
                announcement: dict[str, Any] = {
                    "url": link.move_url,
                    "fp": link.move_fingerprint,
                    "since": int(link.move_since.timestamp()) if link.move_since else int(self.clock()),
                }
                if link.move_next_fingerprint:
                    announcement["next"] = link.move_next_fingerprint
                self._move = announcement
            else:
                self._move = None
        return self._move

    def _now_ms(self) -> int:
        return int(self.clock() * 1000)

    def _frame(self, meta: dict[str, Any], body: bytes = b"") -> bytes:
        document = dict(meta)
        announcement = self._gateway_meta()
        if announcement is not None:
            document["gateway"] = announcement
        return protocol.pack_frame(document, body)

    def _error(self, status: int, code: str, message: str) -> bytes:
        announcement = self._gateway_meta()
        return error_frame(status, code, message, self._now_ms(), {"gateway": announcement} if announcement else None)

    # --- the loop ------------------------------------------------------------------------------------------------

    def poll_once(self, wait: int = 25) -> bool:
        """Fetch one request, deal with it, answer it. True if there was one."""
        answer = self.client.signed("POST", f"/v1/server/poll?wait={wait}")
        if answer.status in {200, 204}:
            self._note_success()
        if answer.status == 204:
            return False
        if answer.status != 200:
            raise GatewayLinkError(f"poll: {answer.status} {_error_text(answer.body)}")
        headers = answer.headers
        kind = headers.get("x-rgw-kind", "")
        try:
            rid = protocol.b64d(headers["x-rgw-request"], length=protocol.ID_LEN)
            ts = int(headers["x-rgw-time"])
            ident = protocol.b64d(
                headers["x-rgw-device" if kind == "call" else "x-rgw-pairing"], length=protocol.ID_LEN
            )
            signature = protocol.b64d(headers.get("x-rgw-signature", ""), max_length=128) if kind == "call" else b""
        except (KeyError, ValueError, protocol.ProtocolError):
            self.stats["dropped"] += 1
            return True
        close_old_connections()
        try:
            sealed = self.process(kind, ident, rid, ts, signature, answer.body)
        finally:
            close_old_connections()
        if sealed is None:
            self.stats["dropped"] += 1
            return True
        reply = self.client.signed("POST", f"/v1/server/respond/{protocol.b64e(rid)}", sealed)
        if reply.status == 204:
            self.stats["answered"] += 1
        else:
            log.warning("The gateway did not take an answer: %s", reply.status)
        return True

    def _note_success(self) -> None:
        """Remember in the database, at most every 10 seconds, that the gateway answers."""
        now = time.monotonic()
        if now - self._noted < 10:
            return
        self._noted = now
        close_old_connections()
        GatewayLink.objects.filter(pk=self.link_id).update(
            last_poll_at=timezone.now(), last_error="", last_error_at=None
        )

    def note_failure(self, error: Exception) -> None:
        """Remember what went wrong (a short text, never a secret)."""
        text = _printable(f"{type(error).__name__}: {error}", 290)
        with contextlib.suppress(Exception):
            close_old_connections()
            GatewayLink.objects.filter(pk=self.link_id).update(last_error=text, last_error_at=timezone.now())

    def serve(self, stop: threading.Event) -> list[threading.Thread]:
        """Start the polling threads; they end when ``stop`` is set."""

        def loop() -> None:
            delay = 1.0
            while not stop.is_set():
                try:
                    self.poll_once()
                    delay = 1.0
                except Exception as error:
                    log.warning("The gateway does not answer: %s", error)
                    self.note_failure(error)
                    stop.wait(delay)
                    delay = min(delay * 2, 30.0)

        threads = [
            threading.Thread(target=loop, name=f"gateway-poll-{number}", daemon=True)
            for number in range(self.config.workers)
        ]
        for thread in threads:
            thread.start()
        return threads

    # --- one request ---------------------------------------------------------------------------------------------

    def process(self, kind: str, ident: bytes, rid: bytes, ts: int, signature: bytes, body: bytes) -> bytes | None:
        """Check, open and carry out one request; returns the sealed answer, or ``None`` to stay silent."""
        try:
            if kind == protocol.PAIR:
                return self._pair(ident, rid, ts, body)
            if kind == protocol.CALL:
                return self._call(ident, rid, ts, signature, body)
        except protocol.ProtocolError as error:
            log.warning("Request dropped (%s): %s", kind, error)
        except Exception:  # whatever a hostile frame provokes (deep nesting, odd numbers): drop it, keep serving
            log.exception("Request dropped (%s): unexpected error", kind)
        return None

    def _seen(self, key: bytes, until: int) -> bool:
        """True if the request id was seen; otherwise remember it until ``until`` (seconds since 1970)."""
        try:
            with transaction.atomic():
                GatewayReplay.objects.create(key=key.hex(), expires_at=until)
        except IntegrityError:
            return True
        return False

    def _call(self, device_id: bytes, rid: bytes, ts: int, signature: bytes, body: bytes) -> bytes | None:
        device = GatewayDevice.objects.select_related("user").filter(device_id=device_id.hex()).first()
        if device is None:
            log.warning("Request of an unknown device %s", device_id[:4].hex())
            return None
        if not protocol.verify(
            bytes.fromhex(device.public_key), signature, protocol.call_signature_input(device_id, rid, ts, body)
        ):
            log.warning("Bad signature of device %s", device_id[:4].hex())
            return None
        opened = protocol.open_request(server_private=self.e2e_key, id_a=device_id, request_id=rid, ts=ts, body=body)

        def answer(frame: bytes) -> bytes:
            return protocol.seal_response(response_key=opened.response_key, id_a=device_id, request_id=rid, frame=frame)

        if not device.is_usable:
            return answer(self._error(401, "device_revoked", "This device was removed."))
        if abs(self.clock() - ts) > self.config.time_window:
            return answer(self._error(401, "time_skew", "The clock of the device is too far off."))
        if self._seen(device_id + rid, ts + self.config.time_window + 10):
            log.warning("Repeated request of device %s", device_id[:4].hex())
            return None
        self._touch(device)

        meta, request_body = protocol.unpack_frame(opened.frame)
        if meta.get("op") == "time":
            # A time probe (docs/protokoll.md of the gateway, chapter 9): nothing is carried out, the answer tells the time.
            return answer(self._frame({"status": 204, "headers": [], "time": self._now_ms()}))
        method = str(meta.get("method", ""))
        path = str(meta.get("path", ""))
        if method not in ALLOWED_METHODS or not self.path_allowed(path):
            self.stats["refused"] += 1
            return answer(self._error(403, "path_forbidden", "This address is not available through the gateway."))
        headers = self.clean_headers(meta.get("headers", []))
        try:
            status, response_headers, response_body = self.executor(method, path, headers, request_body, device)
        except TimeoutError:
            log.warning("The application did not answer in time.")
            return answer(self._error(504, "server_timeout", "The server took too long."))
        except (OSError, http.client.HTTPException, UnicodeError) as error:
            log.warning("The application does not answer: %s", type(error).__name__)
            return answer(self._error(502, "bad_gateway", "The application does not answer."))
        status, response_headers, response_body = self._after(
            device, method, path, status, response_headers, response_body
        )
        sealed = answer(
            self._frame(
                {"status": status, "headers": [[n, v] for n, v in response_headers], "time": self._now_ms()},
                response_body,
            )
        )
        if len(sealed) > self.max_sealed:
            return answer(self._error(502, "too_large", "The answer is too large for the gateway."))
        return sealed

    def _touch(self, device: GatewayDevice) -> None:
        """Note the time of the last request, at most once a minute per device."""
        now = timezone.now()
        stale = Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=now - datetime.timedelta(minutes=1))
        GatewayDevice.objects.filter(stale, pk=device.pk).update(last_seen_at=now)

    @staticmethod
    def path_allowed(path: str) -> bool:
        """``/api/v1/…`` only, written plainly: no ``..``, ``//``, backslash, encoded dot, spaces, control or non-ASCII characters."""
        if not path.startswith(API_PREFIX) or len(path) > 2048:
            return False
        bare, _mark, query = path.partition("?")
        # In the path itself nothing that could lead out of /api/v1/; the query may hold ``..`` or ``//`` (a URL as a value).
        if any(bad in bare for bad in FORBIDDEN_IN_PATH) or any(bad in query for bad in QUERY_FORBIDDEN):
            return False
        return path.isascii() and all(ch > " " and ch != "\x7f" for ch in path)

    @staticmethod
    def clean_headers(raw: Any) -> list[tuple[str, str]]:
        """The headers of the app without the ones that only the link service may set (GWS-033)."""
        cleaned: list[tuple[str, str]] = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, list) and len(item) == 2 and all(isinstance(part, str) for part in item):
                name, value = item
                lower = name.lower()
                if (
                    _HEADER_NAME.fullmatch(name)
                    and lower not in STRIPPED_FROM_APPS
                    and not lower.startswith(STRIPPED_PREFIXES)
                    and not any(ch in value for ch in "\r\n\x00")
                ):
                    cleaned.append((name, value))
        return cleaned

    # --- what the link adds around a request -----------------------------------------------------------------------

    def _after(
        self, device: GatewayDevice, method: str, path: str, status: int, headers: list[tuple[str, str]], body: bytes
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        """Two rules that tie an account and its tokens to the device (GWS-041).

        * A login through a device is for the account the device was paired for. Another account is refused, and
          the session that the login just started is ended again.
        * A token created through a device (``POST /tokens``) is bound to it.
        """
        if method != "POST" or status not in {200, 201}:
            return status, headers, body
        bare = path.partition("?")[0]  # the application routes without the query, and so must these rules
        if _LOGIN_PATH.fullmatch(bare):
            # The profile in the answer names the account that was logged in, whatever the user typed (name, mail address).
            try:
                username = str(json.loads(body).get("username", ""))
            except (ValueError, AttributeError):
                username = ""  # not understood: refused, to be safe
            if username.lower() != device.user.username.lower():
                self._end_sessions(headers)
                text = "This device is paired for another account."
                log.warning("Login of another account through device %s refused", device.device_id[:8])
                error = json.dumps({"error": {"code": "device_user_mismatch", "message": text}}).encode("utf-8")
                return 403, [("Content-Type", "application/json")], error
        elif _TOKEN_PATH.fullmatch(bare):
            from rentalars.accounts.models import ApiToken

            try:
                token_id = int(json.loads(body)["id"])
                if not ApiToken.objects.filter(pk=token_id, user=device.user).exists():
                    raise KeyError(token_id)
            except (ValueError, KeyError, TypeError, AttributeError):
                # A token that cannot be tied to the device must not reach the app: its key would work on the direct way.
                log.warning(
                    "A token created through device %s could not be bound; the answer is withheld", device.device_id[:8]
                )
                error = json.dumps(
                    {"error": {"code": "token_not_bound", "message": "The token could not be tied to this device."}}
                ).encode("utf-8")
                return 502, [("Content-Type", "application/json")], error
            GatewayTokenBinding.objects.get_or_create(token_id=token_id, defaults={"device": device})
        return status, headers, body

    @staticmethod
    def _drop_bindings(device: GatewayDevice) -> None:
        """Revoke the tokens that were tied to ``device`` and forget the ties: a device that is paired anew starts clean."""
        from rentalars.accounts.models import ApiToken

        for token in ApiToken.objects.filter(gateway_binding__device=device):
            token.revoke()
        GatewayTokenBinding.objects.filter(device=device).delete()

    @staticmethod
    def _end_sessions(headers: list[tuple[str, str]]) -> None:
        """End the browser session that a refused login started: its key is in the ``Set-Cookie`` of the answer."""
        from django.contrib.sessions.models import Session

        from rentalars.accounts.models import UserSession

        for name, value in headers:
            if name.lower() == "set-cookie":
                match = re.match(rf"{re.escape(settings.SESSION_COOKIE_NAME)}=([A-Za-z0-9]+)", value)
                if match:
                    Session.objects.filter(session_key=match.group(1)).delete()
                    UserSession.objects.filter(session_key=match.group(1)).delete()

    # --- pairing -----------------------------------------------------------------------------------------------

    def _pair(self, pairing_id: bytes, rid: bytes, ts: int, body: bytes) -> bytes | None:
        offer = GatewayPairing.objects.select_related("user").filter(pairing_id=pairing_id.hex()).first()
        now = int(self.clock())
        if offer is None or offer.expires_at <= now:
            return None
        try:
            opened = protocol.open_request(
                server_private=self.e2e_key, id_a=pairing_id, request_id=rid, ts=ts, body=body,
                context=protocol.PAIR, salt=offer.secret_bytes(),
            )  # fmt: skip
        except protocol.ProtocolError:
            log.warning("Pairing request without the secret (pairing %s)", pairing_id[:4].hex())
            return None

        def answer(frame: bytes) -> bytes:
            return protocol.seal_response(
                response_key=opened.response_key, id_a=pairing_id, request_id=rid, frame=frame, context=protocol.PAIR
            )

        if abs(self.clock() - ts) > self.config.time_window:
            return answer(self._error(401, "time_skew", "The clock of the device is too far off."))
        meta, _ = protocol.unpack_frame(opened.frame)
        try:
            device_public = protocol.b64d(meta["device_pub"], length=protocol.POINT_LEN)
            protocol.load_public(device_public)
            proof = protocol.b64d(meta["pop"], max_length=128)
        except (KeyError, protocol.ProtocolError):
            return answer(self._error(400, "bad_request", "The pairing request is incomplete."))
        if not protocol.verify(
            device_public, proof, protocol.pair_pop_input(pairing_id, rid, body[: protocol.POINT_LEN], device_public)
        ):
            return answer(self._error(400, "bad_proof", "The device key could not be verified."))
        if self._seen(pairing_id + rid, ts + self.config.time_window + 10):
            return None
        device_id = protocol.device_id_of(device_public)
        if (
            GatewayDevice.objects.exclude(device_id=device_id.hex()).filter(revoked_at__isnull=True).count()
            >= MAX_DEVICES
        ):
            return answer(self._error(400, "too_many_devices", "No more devices can be paired."))

        name = str(meta.get("device_name", ""))[:64] or offer.device_name or "device"
        platform = str(meta.get("platform", ""))[:20]
        if not GatewayPairing.objects.filter(pk=offer.pk).delete()[0]:
            return None  # another worker used the offer up in the meantime: it holds once
        previous = GatewayDevice.objects.filter(device_id=device_id.hex()).first()
        if previous is not None and (previous.user_id != offer.user_id or previous.revoked_at is not None):
            self._drop_bindings(previous)  # tokens of the old account must not come alive through this device
        GatewayDevice.objects.update_or_create(
            device_id=device_id.hex(),
            defaults={
                "public_key": device_public.hex(),
                "name": name,
                "platform": platform,
                "user": offer.user,
                "revoked_at": None,
                "revoked_by": None,
            },
        )
        try:
            self.client.push_registry()  # the gateway must know the device before the app's first call arrives
        except Exception as error:  # the registry thread catches up; the app must still hear that it is paired
            log.warning("The list of devices could not be sent right away: %s", error)
        document = {
            "op": "paired",
            "device_id": protocol.b64e(device_id),
            "user": offer.user.username,
            "time": self._now_ms(),
            "server_url": self.server_url,
        }
        return answer(self._frame(document))


# --- what the administrator triggers ----------------------------------------------------------------------------------


def create_offer(
    link: GatewayLink,
    user: Any,
    *,
    created_by: Any = None,
    device_name: str = "",
    lifetime: int = PAIRING_LIFETIME,
    organisation: str = "",
) -> protocol.PairingOffer:
    """A one-off, short-lived pairing offer for ``user``; registered at the gateway before it is returned."""
    if not link.is_connected:
        raise GatewayLinkError("No gateway is connected (rentalars gateway connect).")
    if not user.is_active:
        raise GatewayLinkError("This account is not active.")
    now = int(time.time())
    GatewayPairing.objects.filter(expires_at__lte=now).delete()
    if GatewayPairing.objects.count() >= MAX_PAIRINGS:
        raise GatewayLinkError(f"There are already {MAX_PAIRINGS} open pairing offers.")
    if GatewayPairing.objects.filter(user=user).count() >= MAX_PAIRINGS_PER_USER:
        raise GatewayLinkError(f"This account already has {MAX_PAIRINGS_PER_USER} open pairing offers.")
    lifetime = max(60, min(lifetime, PAIRING_LIFETIME))
    pairing_id = os.urandom(protocol.ID_LEN)
    secret = os.urandom(protocol.SECRET_LEN)
    record = GatewayPairing(
        pairing_id=pairing_id.hex(),
        expires_at=now + lifetime,
        user=user,
        created_by=created_by,
        device_name=device_name[:64],
    )
    record.set_secret(secret)
    record.save()
    try:
        GatewayClient.for_link(link).push_registry()
    except Exception:
        record.delete()
        raise
    e2e_public = protocol.public_bytes(protocol.private_from_pem(link.e2e_key_pem()))
    return protocol.PairingOffer(
        gateway=link.gateway_url,
        gateway_fingerprint=link.gateway_fingerprint,
        server_url=settings.RENTALARS_URL,
        server_public=e2e_public,
        pairing_id=pairing_id,
        secret=secret,
        expires=record.expires_at,
        name=organisation,
    )


def revoke_device(link: GatewayLink | None, device: GatewayDevice, by: Any = None) -> None:
    """Lock a device out: first here (every request is checked here), then the gateway's list."""
    device.revoked_at = timezone.now()
    device.revoked_by = by
    device.save(update_fields=["revoked_at", "revoked_by"])
    if link is not None and link.is_connected:
        GatewayClient.for_link(link).push_registry()


def clean_up() -> int:
    """Remove request ids and pairing offers that no longer matter; returns how many rows went."""
    now = int(time.time())
    deleted_replays, _ = GatewayReplay.objects.filter(expires_at__lt=now).delete()
    deleted_offers, _ = GatewayPairing.objects.filter(expires_at__lt=now).delete()
    return deleted_replays + deleted_offers


def build_executor(config: GatewayConfig) -> LocalExecutor:
    """The executor for this installation: its socket on a server, ``127.0.0.1:8000`` in development."""
    local = config.local or (
        "/run/rentalars/gunicorn.sock" if settings.RENTALARS_ENVIRONMENT == "production" else "http://127.0.0.1:8000"
    )
    return LocalExecutor(
        local, settings.RENTALARS_URL, float(config.call_timeout), config.max_response_mib * 1024 * 1024
    )


def hold_registry(link_id: int, stop: threading.Event, interval: float = 300.0) -> threading.Thread:
    """Start the thread that sends the directory at the start and every five minutes, and tidies up the database.

    A new or replaced gateway thus learns the devices without anybody doing anything (GWS-024).
    """

    def loop() -> None:
        while not stop.is_set():
            try:
                close_old_connections()
                link = GatewayLink.objects.filter(pk=link_id).first()
                if link is not None and link.is_connected:
                    GatewayClient.for_link(link).push_registry()
                clean_up()
            except Exception as error:
                log.warning("The list of devices could not be sent: %s", error)
            finally:
                close_old_connections()
            stop.wait(interval)

    thread = threading.Thread(target=loop, name="gateway-registry", daemon=True)
    thread.start()
    return thread


__all__ = [
    "GatewayClient",
    "GatewayLinkError",
    "LocalExecutor",
    "ServerLink",
    "build_executor",
    "clean_up",
    "create_offer",
    "hold_registry",
    "revoke_device",
]
