# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "gateway_link": the server's side of the Rentalars Gateway (protocol RGW1).

What is proved: the formats agree with the test vectors of the gateway; a request is checked in the documented
order and nothing is carried out before it passed; the headers of the apps cannot pose as the link's; a login
through a device is for its account only; tokens issued through a device work only through it; the commands.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings
from django.utils import timezone

from rentalars.accounts.models import ApiToken, User
from rentalars.config import ConfigurationError, load_config
from rentalars.gateway_link import binding, protocol, service
from rentalars.gateway_link.models import (
    GatewayDevice,
    GatewayLink,
    GatewayPairing,
    GatewayReplay,
    GatewayTokenBinding,
)
from tests.helpers import PASSWORD, RentalarsTestCase, make_user

VECTORS = json.loads((Path(__file__).parent / "gateway_testvektoren.json").read_text(encoding="utf-8"))
SERVER_URL = "https://localhost"


def scalar_key(hexscalar: str):
    """A private key from the hex scalar of the vectors."""
    return protocol.private_from_scalar(bytes.fromhex(hexscalar))


class VectorTests(RentalarsTestCase):
    """The copy of the protocol module agrees with ``docs/testvektoren.json`` of the gateway (GWT-001)."""

    def test_the_sealed_request_of_the_vectors_is_reproduced_and_opens(self) -> None:
        keys, call = VECTORS["keys"], VECTORS["call"]
        device_id, rid = bytes.fromhex(keys["device_id"]), bytes.fromhex(call["request_id"])
        server = scalar_key(keys["server_e2e_private"])
        sealed = protocol.seal_request(
            server_public=protocol.public_bytes(server),
            id_a=device_id,
            request_id=rid,
            ts=call["ts"],
            frame=bytes.fromhex(call["frame"]),
            ephemeral=scalar_key(call["ephemeral_private"]),
            nonce=bytes.fromhex(call["nonce"]),
        )
        self.assertEqual(sealed.body.hex(), call["sealed_request_body"])
        self.assertEqual(sealed.response_key.hex(), call["response_key"])
        opened = protocol.open_request(
            server_private=server,
            id_a=device_id,
            request_id=rid,
            ts=call["ts"],
            body=bytes.fromhex(call["sealed_request_body"]),
        )
        self.assertEqual(opened.frame.hex(), call["frame"])
        signature = bytes.fromhex(call["signature_deterministic"])
        device_public = bytes.fromhex(keys["device_public"])
        self.assertTrue(
            protocol.verify(
                device_public, signature, protocol.call_signature_input(device_id, rid, call["ts"], sealed.body)
            )
        )

    def test_the_answer_of_the_vectors_opens(self) -> None:
        keys, call, response = VECTORS["keys"], VECTORS["call"], VECTORS["response"]
        opened = protocol.open_response(
            response_key=bytes.fromhex(call["response_key"]),
            id_a=bytes.fromhex(keys["device_id"]),
            request_id=bytes.fromhex(call["request_id"]),
            body=bytes.fromhex(response["sealed_response_body"]),
        )
        self.assertEqual(opened.hex(), response["frame"])

    def test_the_pairing_of_the_vectors_needs_the_secret(self) -> None:
        keys, pairing = VECTORS["keys"], VECTORS["pairing"]
        server = scalar_key(keys["server_e2e_private"])
        arguments = {
            "server_private": server,
            "id_a": bytes.fromhex(pairing["pairing_id"]),
            "request_id": bytes.fromhex(pairing["request_id"]),
            "ts": pairing["ts"],
            "body": bytes.fromhex(pairing["sealed_request_body"]),
            "context": protocol.PAIR,
        }
        opened = protocol.open_request(**arguments, salt=bytes.fromhex(pairing["pairing_secret"]))
        self.assertEqual(opened.frame.hex(), pairing["frame"])
        with self.assertRaises(protocol.ProtocolError):
            protocol.open_request(**arguments)
        offer = protocol.PairingOffer.decode(pairing["offer_text"])
        self.assertEqual(offer.pairing_id.hex(), pairing["pairing_id"])

    def test_the_link_signature_input_of_the_vectors(self) -> None:
        link = VECTORS["link"]
        built = protocol.link_signature_input(
            "PUT", "/v1/server/registry", link["ts"], bytes.fromhex(link["nonce"]), link["body"].encode()
        )
        self.assertEqual(built.hex(), link["signature_input"])


class ConfigTests(RentalarsTestCase):
    """The section ``[gateway]`` of the configuration file."""

    def load(self, text: str):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rentalars.conf"
            path.write_text("[rentalars]\nenvironment = development\n" + text, encoding="utf-8")
            return load_config(path).gateway

    def test_defaults_without_a_section(self) -> None:
        gateway = self.load("")
        self.assertEqual(
            (gateway.local, gateway.workers, gateway.time_window, gateway.max_response_mib), ("", 4, 180, 12)
        )

    def test_values_are_read_and_kept_within_bounds(self) -> None:
        gateway = self.load(
            "[gateway]\nlocal = /run/rentalars/gunicorn.sock\nworkers = 1\nmax_response_mib = 99\ncall_timeout = 70\n"
        )
        self.assertEqual(
            (gateway.local, gateway.workers, gateway.max_response_mib, gateway.call_timeout),
            ("/run/rentalars/gunicorn.sock", 3, 12, 70),
        )

    def test_a_local_address_that_is_not_local_is_refused(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.load("[gateway]\nlocal = http://evil.example.com:8000\n")
        with self.assertRaises(ConfigurationError):
            self.load("[gateway]\nworkers = many\n")


class LinkTestCase(RentalarsTestCase):
    """A connected link, a device of the account "anna" with its key, and a stand-in for the application."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("anna")
        self.link = GatewayLink()
        self.e2e = protocol.generate_private_key()
        self.link.set_link_key_pem(protocol.private_to_pem(protocol.generate_private_key()))
        self.link.set_e2e_key_pem(protocol.private_to_pem(self.e2e))
        self.link.gateway_url = "https://gateway.example.de:8799"
        self.link.gateway_fingerprint = "ab" * 32
        self.link.enrolled_at = timezone.now()
        self.link.save()
        self.device_key = protocol.generate_private_key()
        self.device_public = protocol.public_bytes(self.device_key)
        self.device_id = protocol.device_id_of(self.device_public)
        self.device = GatewayDevice.objects.create(
            device_id=self.device_id.hex(), public_key=self.device_public.hex(), name="Telefon", user=self.user
        )
        self.calls: list[tuple[str, str, list[tuple[str, str]], bytes, GatewayDevice]] = []
        self.web = Client()
        self.now = float(int(time.time()))
        self.server = service.ServerLink(
            self.link, settings.CONFIG.gateway, self.execute, server_url=SERVER_URL, clock=lambda: self.now
        )
        patcher = mock.patch.object(service.GatewayClient, "push_registry", return_value={})
        self.pushed = patcher.start()
        self.addCleanup(patcher.stop)

    def execute(self, method: str, path: str, headers: list[tuple[str, str]], body: bytes, device: GatewayDevice):
        """Carry the request out against the application, as the link service does over its socket."""
        self.calls.append((method, path, headers, body, device))
        extra = {
            "HTTP_" + name.upper().replace("-", "_"): value for name, value in headers if name.lower() != "content-type"
        }
        extra["HTTP_X_FORWARDED_FOR"] = binding.pseudo_address(bytes.fromhex(device.device_id))
        extra["HTTP_X_RENTALARS_DEVICE"] = binding.device_assertion(device.device_id)
        content_type = next((v for n, v in headers if n.lower() == "content-type"), "application/json")
        answer = self.web.generic(
            method, path, body, content_type=content_type, secure=True, HTTP_HOST="localhost", **extra
        )
        return (
            answer.status_code,
            [(n, v) for n, v in answer.items()] + [("Set-Cookie", c.OutputString()) for c in answer.cookies.values()],
            answer.content,
        )

    # --- what the app does ---------------------------------------------------------------------------------------

    def call_parts(
        self,
        method: str,
        path: str,
        headers: list[tuple[str, str]] | None = None,
        body: bytes = b"",
        *,
        ts: int | None = None,
        rid: bytes | None = None,
    ):
        """(arguments for ``process``, response key) of a request of the device."""
        rid = rid or os.urandom(16)
        ts = int(self.now) if ts is None else ts
        frame = protocol.pack_frame({"method": method, "path": path, "headers": [list(h) for h in headers or []]}, body)
        sealed = protocol.seal_request(
            server_public=protocol.public_bytes(self.e2e), id_a=self.device_id, request_id=rid, ts=ts, frame=frame
        )
        signature = protocol.sign(self.device_key, protocol.call_signature_input(self.device_id, rid, ts, sealed.body))
        return ("call", self.device_id, rid, ts, signature, sealed.body), sealed.response_key, rid

    def ask(self, method: str, path: str, headers: list[tuple[str, str]] | None = None, body: bytes = b"", **options):
        """Send a request through ``process``; returns (status, headers, body, meta) or ``None`` for silence."""
        arguments, key, rid = self.call_parts(method, path, headers, body, **options)
        sealed = self.server.process(*arguments)
        if sealed is None:
            return None
        meta, content = protocol.unpack_frame(
            protocol.open_response(response_key=key, id_a=self.device_id, request_id=rid, body=sealed)
        )
        return meta["status"], meta["headers"], content, meta


class RequestOrderTests(LinkTestCase):
    """GWS-030: the order of the checks, and that nothing is carried out before they passed."""

    def test_a_valid_request_is_carried_out_and_answered_sealed(self) -> None:
        status, _headers, body, meta = self.ask("GET", "/api/v1/me")
        self.assertEqual(status, 401)  # anonymous, but the application answered
        self.assertIn(b"not_authenticated", body)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(meta["time"], int(self.now * 1000))

    def test_an_unknown_device_gets_no_answer(self) -> None:
        self.device.delete()
        self.assertIsNone(self.ask("GET", "/api/v1/me"))
        self.assertEqual(self.calls, [])

    def test_a_bad_signature_gets_no_answer(self) -> None:
        arguments, _key, _rid = self.call_parts("GET", "/api/v1/me")
        forged = (*arguments[:4], protocol.sign(protocol.generate_private_key(), b"x"), arguments[5])
        self.assertIsNone(self.server.process(*forged))
        self.assertEqual(self.calls, [])

    def test_a_changed_body_gets_no_answer(self) -> None:
        arguments, _key, _rid = self.call_parts("GET", "/api/v1/me")
        body = bytearray(arguments[5])
        body[-1] ^= 1
        # the signature no longer fits the bytes ...
        self.assertIsNone(self.server.process(*arguments[:5], bytes(body)))
        # ... and even with a signature over the changed bytes, the sealed box does not open
        signature = protocol.sign(
            self.device_key, protocol.call_signature_input(self.device_id, arguments[2], arguments[3], bytes(body))
        )
        self.assertIsNone(
            self.server.process("call", self.device_id, arguments[2], arguments[3], signature, bytes(body))
        )
        self.assertEqual(self.calls, [])

    def test_a_repeated_request_is_carried_out_once(self) -> None:
        arguments, _key, _rid = self.call_parts("GET", "/api/v1/me")
        self.assertIsNotNone(self.server.process(*arguments))
        self.assertIsNone(self.server.process(*arguments))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(GatewayReplay.objects.count(), 1)

    def test_a_revoked_device_is_told_so_sealed(self) -> None:
        self.device.revoked_at = timezone.now()
        self.device.save()
        status, _headers, _body, meta = self.ask("GET", "/api/v1/me")
        self.assertEqual((status, meta["gw_error"]), (401, "device_revoked"))
        self.assertEqual(self.calls, [])

    def test_a_deactivated_account_locks_its_devices_too(self) -> None:
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        _status, _headers, _body, meta = self.ask("GET", "/api/v1/me")
        self.assertEqual(meta["gw_error"], "device_revoked")
        self.assertEqual(self.calls, [])

    def test_a_wrong_clock_is_answered_sealed_with_the_servers_time(self) -> None:
        status, _headers, _body, meta = self.ask("GET", "/api/v1/me", ts=int(self.now) - 1200)
        self.assertEqual((status, meta["gw_error"], meta["time"]), (401, "time_skew", int(self.now * 1000)))
        self.assertEqual(self.calls, [])

    def test_a_time_probe_is_not_carried_out(self) -> None:
        _arguments, _key, rid = self.call_parts("GET", "/")
        frame = protocol.pack_frame({"op": "time"})
        sealed = protocol.seal_request(
            server_public=protocol.public_bytes(self.e2e),
            id_a=self.device_id,
            request_id=rid,
            ts=int(self.now),
            frame=frame,
        )
        signature = protocol.sign(
            self.device_key, protocol.call_signature_input(self.device_id, rid, int(self.now), sealed.body)
        )
        answer = self.server.process("call", self.device_id, rid, int(self.now), signature, sealed.body)
        meta, _ = protocol.unpack_frame(
            protocol.open_response(
                response_key=sealed.response_key, id_a=self.device_id, request_id=rid, body=answer or b""
            )
        )
        self.assertEqual((meta["status"], meta["time"]), (204, int(self.now * 1000)))
        self.assertEqual(self.calls, [])

    def test_only_the_api_is_reachable(self) -> None:
        for method, path in [
            ("GET", "/"),
            ("GET", "/admin/"),
            ("GET", "/static/css/app.css"),
            ("GET", "/api/schema/"),
            ("GET", "/api/v1/../admin/"),
            ("GET", "/api/v1//me"),
            ("GET", "/api/v1/%2e%2e/admin"),
            ("GET", "/api/v1/me\\x"),
            ("GET", "/api/v1/me#x"),
            ("GET", "/api/v1/mé"),
            ("GET", "/api/v1/ me"),
            ("TRACE", "/api/v1/me"),
            ("GET", "/api/v10/me"),
        ]:
            status, _headers, _body, meta = self.ask(method, path)
            self.assertEqual((status, meta["gw_error"]), (403, "path_forbidden"), (method, path))
        self.assertEqual(self.calls, [])

    def test_a_query_may_hold_dots_and_slashes_but_the_path_may_not(self) -> None:
        """Review: ``?next=https://x`` and ``?q=a..b`` are values, not a way out of ``/api/v1/``."""
        allowed = service.ServerLink.path_allowed
        self.assertTrue(allowed("/api/v1/projects?q=a..b"))
        self.assertTrue(allowed("/api/v1/webhooks?next=https://example.de/x"))
        self.assertFalse(allowed("/api/v1/me?x=%00"))
        self.assertFalse(allowed("/api/v1/me?x=a\\b"))
        self.assertFalse(allowed("/api/v1/me?x=1#y"))
        self.assertFalse(allowed("/api/v1/../admin?x=1"))
        self.assertFalse(allowed("/api/v1//me?x=1"))

    def test_errors_of_the_executor_that_are_not_os_errors_are_answered_too(self) -> None:
        import http.client

        for error in [
            http.client.IncompleteRead(b"x"),
            http.client.BadStatusLine("x"),
            UnicodeEncodeError("latin-1", "é", 0, 1, "x"),
        ]:
            self.server.executor = mock.Mock(side_effect=error)
            status, _headers, _body, meta = self.ask("GET", "/api/v1/me")
            self.assertEqual((status, meta["gw_error"]), (502, "bad_gateway"), type(error).__name__)

    def test_a_failed_poll_is_not_noted_as_a_success(self) -> None:
        # ``close_old_connections`` would close the connection of the test transaction (MariaDB) and leave rows behind
        patcher = mock.patch.object(service, "close_old_connections")
        patcher.start()
        self.addCleanup(patcher.stop)
        for status in (401, 403, 500):
            self.server.client = mock.Mock()
            self.server.client.signed.return_value = service.HttpAnswer(
                status, {}, b'{"error": {"code": "bad_signature", "message": "no\\x1b[31m"}}'
            )
            with self.assertRaises(service.GatewayLinkError) as raised:
                self.server.poll_once()
            self.assertNotIn("\x1b", str(raised.exception))
            self.link.refresh_from_db()
            self.assertIsNone(self.link.last_poll_at)
        self.server.client.signed.return_value = service.HttpAnswer(204, {}, b"")
        self.assertFalse(self.server.poll_once())
        self.link.refresh_from_db()
        self.assertIsNotNone(self.link.last_poll_at)

    def test_headers_of_the_app_cannot_pose_as_the_links(self) -> None:
        headers = [
            ("Authorization", "Bearer rl_x"),
            ("Accept-Language", "de"),
            ("Host", "evil.example"),
            ("Origin", "https://evil.example"),
            ("X-Forwarded-For", "1.2.3.4"),
            ("x-forwarded-proto", "http"),
            ("X-Real-IP", "1.2.3.4"),
            ("Forwarded", "for=1.2.3.4"),
            ("X-Rentalars-Device", "forged"),
            ("Proxy-Authorization", "x"),
            ("Transfer-Encoding", "chunked"),
            ("Content-Length", "99"),
            ("Connection", "upgrade"),
            ("Idempotency-Key", "k1"),
            ("X-Evil", "a\r\nb"),
            ("Bad Name", "x"),
        ]
        self.ask("GET", "/api/v1/me", headers)
        kept = [name.lower() for name, _ in self.calls[0][2]]
        self.assertEqual(kept, ["authorization", "accept-language", "idempotency-key"])

    def test_an_application_that_does_not_answer_becomes_a_sealed_error(self) -> None:
        for error, status, code in [
            (TimeoutError(), 504, "server_timeout"),
            (ConnectionRefusedError(), 502, "bad_gateway"),
        ]:
            self.server.executor = mock.Mock(side_effect=error)
            got, _headers, _body, meta = self.ask("GET", "/api/v1/me")
            self.assertEqual((got, meta["gw_error"]), (status, code))

    def test_an_answer_that_is_too_large_becomes_a_sealed_error(self) -> None:
        self.server.max_sealed = 5000
        self.server.executor = lambda *a: (200, [], b"x" * 6000)
        status, _headers, _body, meta = self.ask("GET", "/api/v1/me")
        self.assertEqual((status, meta["gw_error"]), (502, "too_large"))

    def test_the_announcement_of_a_move_is_attached_to_the_answers(self) -> None:
        _status, _headers, _body, meta = self.ask("GET", "/api/v1/me")
        self.assertNotIn("gateway", meta)
        self.link.move_url, self.link.move_fingerprint, self.link.move_next_fingerprint = (
            "https://new.example.de:8799",
            "cd" * 32,
            "ef" * 32,
        )
        self.link.move_since = timezone.now()
        self.link.save()
        self.server._move_read = 0.0
        _status, _headers, _body, meta = self.ask("GET", "/api/v1/me")
        self.assertEqual(
            (meta["gateway"]["url"], meta["gateway"]["fp"], meta["gateway"]["next"]),
            ("https://new.example.de:8799", "cd" * 32, "ef" * 32),
        )
        _status, _headers, _body, error = self.ask("GET", "/", [])
        self.assertEqual(error["gateway"]["url"], "https://new.example.de:8799")  # also on errors


class AccountAndTokenTests(LinkTestCase):
    """GWS-040, GWS-041: the account of the device, the binding of tokens, the address that is counted."""

    def login(self, name: str, password: str = PASSWORD):
        return self.ask(
            "POST",
            "/api/v1/auth/login",
            [("Content-Type", "application/json")],
            json.dumps({"username": name, "password": password}).encode(),
        )

    def test_login_for_the_account_of_the_device_works_by_name_or_mail(self) -> None:
        self.assertEqual(self.login("anna")[0], 200)
        self.assertEqual(self.login("anna@example.de")[0], 200)

    def test_login_for_another_account_is_refused_and_its_session_ended(self) -> None:
        make_user("berta")
        from django.contrib.sessions.models import Session

        status, _headers, body, _meta = self.login("berta")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "device_user_mismatch")
        self.assertEqual(Session.objects.count(), 0)

    def test_a_token_created_through_the_device_is_bound_to_it(self) -> None:
        self.login("anna")
        cookies = {c.key: c.value for c in self.web.cookies.values()}
        headers = [
            ("Content-Type", "application/json"),
            ("Cookie", f"sessionid={cookies['sessionid']}; csrftoken={cookies['csrftoken']}"),
            ("X-CSRFToken", cookies["csrftoken"]),
        ]
        status, _headers, body, _meta = self.ask("POST", "/api/v1/tokens", headers, b'{"name": "Telefon"}')
        self.assertEqual(status, 201)
        token = ApiToken.objects.get(pk=json.loads(body)["id"])
        self.assertEqual(token.gateway_binding.device, self.device)
        key = json.loads(body)["key"]
        # through the device: works
        status, _headers, _body, _meta = self.ask("GET", "/api/v1/me", [("Authorization", f"Bearer {key}")])
        self.assertEqual(status, 200)
        # the direct way: refused, also with a forged header
        direct = Client()
        self.assertEqual(
            direct.get(
                "/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {key}", HTTP_HOST="localhost", secure=True
            ).status_code,
            401,
        )
        forged = direct.get(
            "/api/v1/me",
            HTTP_AUTHORIZATION=f"Bearer {key}",
            HTTP_X_RENTALARS_DEVICE=f"{self.device.device_id}.{'0' * 64}",
            HTTP_HOST="localhost",
            secure=True,
        )
        self.assertEqual(forged.status_code, 401)
        # another device of the same account: refused
        other = GatewayDevice.objects.create(device_id="11" * 16, public_key="04" + "00" * 64, user=self.user)
        proof = binding.device_assertion(other.device_id)
        self.assertEqual(
            direct.get(
                "/api/v1/me",
                HTTP_AUTHORIZATION=f"Bearer {key}",
                HTTP_X_RENTALARS_DEVICE=proof,
                HTTP_HOST="localhost",
                secure=True,
            ).status_code,
            401,
        )

    def session_headers(self) -> list[tuple[str, str]]:
        self.login("anna")
        cookies = {c.key: c.value for c in self.web.cookies.values()}
        return [
            ("Content-Type", "application/json"),
            ("Cookie", f"sessionid={cookies['sessionid']}; csrftoken={cookies['csrftoken']}"),
            ("X-CSRFToken", cookies["csrftoken"]),
        ]

    def test_the_rules_of_login_and_token_hold_with_a_query_or_a_suffix(self) -> None:
        """Review: ``?x=1`` and ``.json`` reach the same view; the rules must not be skipped by them."""
        from django.contrib.sessions.models import Session

        make_user("berta")
        for path in ("/api/v1/auth/login?x=1", "/api/v1/auth/login.json", "/api/v1/auth/login/?x=1"):
            Session.objects.all().delete()
            status, _headers, body, _meta = self.ask(
                "POST",
                path,
                [("Content-Type", "application/json")],
                json.dumps({"username": "berta", "password": PASSWORD}).encode(),
            )
            self.assertNotEqual(status, 200, path)
            if status == 403:
                self.assertEqual(json.loads(body)["error"]["code"], "device_user_mismatch", path)
            self.assertEqual(Session.objects.count(), 0, path)
        headers = self.session_headers()
        direct = Client()
        for path in ("/api/v1/tokens?x=1", "/api/v1/tokens.json", "/api/v1/tokens/?x=1"):
            status, _headers, body, _meta = self.ask("POST", path, headers, b'{"name": "Telefon"}')
            if status != 201:
                continue  # not a route of the application: nothing was created
            key = json.loads(body)["key"]
            self.assertTrue(GatewayTokenBinding.objects.filter(token_id=json.loads(body)["id"]).exists(), path)
            self.assertEqual(
                direct.get(
                    "/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {key}", HTTP_HOST="localhost", secure=True
                ).status_code,
                401,
                path,
            )
        self.assertTrue(GatewayTokenBinding.objects.exists())  # at least the query form is a route

    def test_a_token_that_cannot_be_bound_is_not_handed_out(self) -> None:
        for body in (b"{}", b"not json", b'{"id": 999999}', b"[]"):
            status, _headers, content = self.server._after(self.device, "POST", "/api/v1/tokens", 201, [], body)
            self.assertEqual(status, 502, body)
            self.assertEqual(json.loads(content)["error"]["code"], "token_not_bound")

    def test_a_foreign_proof_with_other_characters_is_just_refused(self) -> None:
        token, key = ApiToken.create_for_user(self.user, "gebunden")
        GatewayTokenBinding.objects.create(token=token, device=self.device)
        answer = Client().get(
            "/api/v1/me",
            HTTP_AUTHORIZATION=f"Bearer {key}",
            HTTP_X_RENTALARS_DEVICE=f"{self.device.device_id}.é",
            HTTP_HOST="localhost",
            secure=True,
        )
        self.assertEqual(answer.status_code, 401)
        self.assertIsNone(binding.device_of_assertion(f"{'a' * 32}.é"))

    def test_a_token_of_the_direct_way_is_not_touched(self) -> None:
        token, key = ApiToken.create_for_user(self.user, "direkt")
        answer = Client().get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {key}", HTTP_HOST="localhost", secure=True)
        self.assertEqual(answer.status_code, 200)
        self.assertFalse(GatewayTokenBinding.objects.filter(token=token).exists())

    def test_a_token_whose_device_was_deleted_works_nowhere(self) -> None:
        token, key = ApiToken.create_for_user(self.user, "gebunden")
        GatewayTokenBinding.objects.create(token=token, device=self.device)
        self.device.delete()
        answer = Client().get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {key}", HTTP_HOST="localhost", secure=True)
        self.assertEqual(answer.status_code, 401)

    def test_the_address_that_is_counted_belongs_to_the_device(self) -> None:
        one, two = binding.pseudo_address(self.device_id), binding.pseudo_address(os.urandom(16))
        self.assertTrue(one.startswith("fd"))
        self.assertNotEqual(one, two)
        self.assertEqual(one, binding.pseudo_address(self.device_id))
        from rentalars.accounts.services import client_ip

        class Request:
            META = {"HTTP_X_FORWARDED_FOR": one, "REMOTE_ADDR": "127.0.0.1"}

        with override_settings(RENTALARS_ENVIRONMENT="production"):
            self.assertEqual(client_ip(Request()), one)


class PairingTests(LinkTestCase):
    """GWS-021, GWS-022: one-off offers, the secret as salt, the proof of the device key."""

    def offer(self, **options):
        return service.create_offer(self.link, self.user, **options)

    def pair_request(
        self, offer, *, key=None, secret: bytes | None = None, ts: int | None = None, proof_for: bytes | None = None
    ):
        key = key or protocol.generate_private_key()
        public = protocol.public_bytes(key)
        rid, ts = os.urandom(16), int(self.now) if ts is None else ts
        one_off = protocol.generate_private_key()
        one_off_public = protocol.public_bytes(one_off)
        proof = protocol.sign(key, protocol.pair_pop_input(proof_for or offer.pairing_id, rid, one_off_public, public))
        frame = protocol.pack_frame(
            {
                "op": "pair",
                "device_pub": protocol.b64e(public),
                "pop": protocol.b64e(proof),
                "device_name": "Neues Telefon",
                "platform": "android",
                "app": "test",
            }
        )
        sealed = protocol.seal_request(
            server_public=offer.server_public,
            id_a=offer.pairing_id,
            request_id=rid,
            ts=ts,
            frame=frame,
            context=protocol.PAIR,
            salt=secret if secret is not None else offer.secret,
            ephemeral=one_off,
        )
        return sealed, rid, public

    def test_a_pairing_creates_the_device_and_uses_the_offer_up(self) -> None:
        offer = self.offer(device_name="Vorschlag")
        self.assertEqual(self.pushed.call_count, 1)  # the gateway knows the offer before it is shown
        sealed, rid, public = self.pair_request(offer)
        answer = self.server.process("pair", offer.pairing_id, rid, int(self.now), b"", sealed.body)
        meta, _ = protocol.unpack_frame(
            protocol.open_response(
                response_key=sealed.response_key,
                id_a=offer.pairing_id,
                request_id=rid,
                body=answer or b"",
                context=protocol.PAIR,
            )
        )
        self.assertEqual((meta["op"], meta["user"], meta["server_url"]), ("paired", "anna", SERVER_URL))
        device = GatewayDevice.objects.get(device_id=protocol.device_id_of(public).hex())
        self.assertEqual((device.name, device.platform, device.user), ("Neues Telefon", "android", self.user))
        self.assertEqual(protocol.b64d(meta["device_id"]), protocol.device_id_of(public))
        self.assertFalse(GatewayPairing.objects.exists())
        self.assertEqual(self.pushed.call_count, 2)  # the directory was renewed before the answer
        # the same offer a second time: no answer
        again, rid2, _ = self.pair_request(offer)
        self.assertIsNone(self.server.process("pair", offer.pairing_id, rid2, int(self.now), b"", again.body))

    def test_pairing_a_device_again_for_another_account_drops_the_old_tokens(self) -> None:
        token, _key = ApiToken.create_for_user(self.user, "alt")
        GatewayTokenBinding.objects.create(token=token, device=self.device)
        other = make_user("berta")
        offer = service.create_offer(self.link, other)
        sealed, rid, _ = self.pair_request(offer, key=self.device_key)
        self.assertIsNotNone(self.server.process("pair", offer.pairing_id, rid, int(self.now), b"", sealed.body))
        self.device.refresh_from_db()
        self.assertEqual(self.device.user, other)
        self.assertFalse(GatewayTokenBinding.objects.filter(token=token).exists())
        token.refresh_from_db()
        self.assertFalse(token.is_usable)

    def test_an_offer_holds_once_even_for_two_workers(self) -> None:
        offer = self.offer()
        sealed, rid, _ = self.pair_request(offer)

        def other_worker_was_faster(*_args):
            GatewayPairing.objects.all().delete()
            return False

        with mock.patch.object(self.server, "_seen", side_effect=other_worker_was_faster):
            self.assertIsNone(self.server.process("pair", offer.pairing_id, rid, int(self.now), b"", sealed.body))
        self.assertFalse(GatewayDevice.objects.filter(name="Neues Telefon").exists())

    def test_a_directory_that_cannot_be_sent_does_not_lose_the_pairing_answer(self) -> None:
        offer = self.offer()
        sealed, rid, _ = self.pair_request(offer)
        self.pushed.side_effect = OSError("gateway away")
        self.assertIsNotNone(self.server.process("pair", offer.pairing_id, rid, int(self.now), b"", sealed.body))
        self.assertFalse(GatewayPairing.objects.exists())

    def test_the_offer_is_in_the_text_the_app_reads(self) -> None:
        offer = self.offer(organisation="Firma")
        text = protocol.PairingOffer.decode(offer.encode())
        self.assertEqual(
            (text.gateway, text.gateway_fingerprint, text.server_url, text.name),
            ("https://gateway.example.de:8799", "ab" * 32, settings.RENTALARS_URL, "Firma"),
        )
        self.assertEqual(text.server_public, protocol.public_bytes(self.e2e))
        self.assertLess(len(offer.encode()), 520)

    def test_without_the_secret_the_request_cannot_be_opened(self) -> None:
        offer = self.offer()
        sealed, rid, _ = self.pair_request(offer, secret=bytes(32))
        self.assertIsNone(self.server.process("pair", offer.pairing_id, rid, int(self.now), b"", sealed.body))
        self.assertFalse(GatewayDevice.objects.filter(name="Neues Telefon").exists())
        self.assertTrue(GatewayPairing.objects.exists())

    def test_an_expired_or_unknown_offer_gets_no_answer(self) -> None:
        offer = self.offer()
        sealed, rid, _ = self.pair_request(offer)
        GatewayPairing.objects.update(expires_at=int(self.now) - 1)
        self.assertIsNone(self.server.process("pair", offer.pairing_id, rid, int(self.now), b"", sealed.body))
        self.assertIsNone(self.server.process("pair", os.urandom(16), rid, int(self.now), b"", sealed.body))

    def test_a_wrong_proof_of_the_device_key_is_answered_sealed(self) -> None:
        offer = self.offer()
        sealed, rid, _ = self.pair_request(offer, proof_for=os.urandom(16))
        answer = self.server.process("pair", offer.pairing_id, rid, int(self.now), b"", sealed.body)
        meta, _ = protocol.unpack_frame(
            protocol.open_response(
                response_key=sealed.response_key,
                id_a=offer.pairing_id,
                request_id=rid,
                body=answer or b"",
                context=protocol.PAIR,
            )
        )
        self.assertEqual(meta["gw_error"], "bad_proof")
        self.assertFalse(GatewayDevice.objects.filter(name="Neues Telefon").exists())

    def test_a_wrong_clock_is_answered_sealed(self) -> None:
        offer = self.offer()
        sealed, rid, _ = self.pair_request(offer, ts=int(self.now) - 1200)
        answer = self.server.process("pair", offer.pairing_id, rid, int(self.now) - 1200, b"", sealed.body)
        meta, _ = protocol.unpack_frame(
            protocol.open_response(
                response_key=sealed.response_key,
                id_a=offer.pairing_id,
                request_id=rid,
                body=answer or b"",
                context=protocol.PAIR,
            )
        )
        self.assertEqual((meta["gw_error"], meta["time"]), ("time_skew", int(self.now * 1000)))

    def test_offers_are_limited(self) -> None:
        for _ in range(service.MAX_PAIRINGS_PER_USER):
            self.offer()
        with self.assertRaises(service.GatewayLinkError):
            self.offer()

    def test_no_offer_for_an_inactive_account(self) -> None:
        user = make_user("gesperrt")
        User.objects.filter(pk=user.pk).update(is_active=False)
        user.refresh_from_db()
        with self.assertRaises(service.GatewayLinkError):
            service.create_offer(self.link, user)

    def test_revoking_and_tidying(self) -> None:
        service.revoke_device(self.link, self.device)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.revoked_at)
        self.assertEqual(self.pushed.call_count, 1)
        GatewayReplay.objects.create(key="aa" * 32, expires_at=1)
        GatewayPairing.objects.create(pairing_id="bb" * 16, secret="x", expires_at=1, user=self.user)
        self.assertEqual(service.clean_up(), 2)


class DirectoryTests(LinkTestCase):
    """GWS-024: what the gateway is told."""

    def test_only_usable_devices_and_open_offers_are_sent(self) -> None:
        mock.patch.stopall()  # the stand-in of push_registry from setUp: here the real one runs
        with mock.patch.object(service.GatewayClient, "signed") as signed:
            signed.return_value = service.HttpAnswer(200, {}, b"{}")
            revoked = GatewayDevice.objects.create(
                device_id="22" * 16, public_key="04" + "11" * 64, user=self.user, revoked_at=timezone.now()
            )
            gone = GatewayDevice.objects.create(device_id="33" * 16, public_key="04" + "22" * 64, user=make_user("weg"))
            User.objects.filter(username="weg").update(is_active=False)
            GatewayPairing.objects.create(
                pairing_id="44" * 16, secret="x", expires_at=int(time.time()) + 500, user=self.user
            )
            GatewayPairing.objects.create(
                pairing_id="55" * 16, secret="x", expires_at=int(time.time()) - 5, user=self.user
            )
            service.GatewayClient.for_link(self.link).push_registry()
        document = json.loads(signed.call_args[0][2])
        self.assertEqual([protocol.b64d(d["id"]).hex() for d in document["devices"]], [self.device.device_id])
        self.assertEqual([protocol.b64d(p["id"]).hex() for p in document["pairings"]], ["44" * 16])
        self.assertEqual(signed.call_args[0][:2], ("PUT", "/v1/server/registry"))
        self.assertNotIn(revoked.device_id, str(document))
        self.assertNotIn(gone.device_id, str(document))


class ProtectedFileTests(RentalarsTestCase):
    """The link does what NGINX does for ``X-Accel-Redirect`` (the application hands files over that way on a server)."""

    def setUp(self) -> None:
        super().setUp()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        media = Path(self.folder.name) / "media"
        (media / "docs").mkdir(parents=True)
        (media / "docs" / "a.pdf").write_bytes(bytes(range(256)) * 4)
        (Path(self.folder.name) / "secret.txt").write_text("not for the app")
        self.override = override_settings(MEDIA_ROOT=media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.executor = service.LocalExecutor("/nonexistent.sock", SERVER_URL, 5, 12 * 1024 * 1024)
        self.answer = service.HttpAnswer(
            200,
            {},
            b"",
            [
                ("Content-Disposition", 'attachment; filename="a.pdf"'),
                ("Content-Length", "0"),
                ("X-Accel-Redirect", "/protected-media/docs/a.pdf"),
            ],
        )

    def deliver(self, redirect: str, range_header: str = ""):
        return self.executor._protected_file(self.answer, redirect, range_header)

    def test_the_file_comes_with_its_type_and_the_headers_of_the_application(self) -> None:
        status, headers, body = self.deliver("/protected-media/docs/a.pdf")
        names = {n.lower(): v for n, v in headers}
        self.assertEqual((status, len(body)), (200, 1024))
        self.assertEqual(
            (names["content-type"], names["accept-ranges"], names["content-disposition"]),
            ("application/pdf", "bytes", 'attachment; filename="a.pdf"'),
        )
        self.assertNotIn("x-accel-redirect", names)

    def test_a_range_gets_a_part(self) -> None:
        status, headers, body = self.deliver("/protected-media/docs/a.pdf", "bytes=10-19")
        self.assertEqual((status, body), (206, bytes(range(10, 20))))
        self.assertIn(("Content-Range", "bytes 10-19/1024"), headers)
        self.assertEqual(self.deliver("/protected-media/docs/a.pdf", "bytes=-4")[2], bytes([252, 253, 254, 255]))
        self.assertEqual(self.deliver("/protected-media/docs/a.pdf", "bytes=2000-")[0], 416)

    def test_a_part_of_a_large_file_is_delivered_though_the_whole_file_is_over_the_limit(self) -> None:
        self.executor.max_bytes = 100
        status, _headers, body = self.deliver("/protected-media/docs/a.pdf", "bytes=0-49")
        self.assertEqual((status, len(body)), (206, 50))
        self.assertEqual(
            self.deliver("/protected-media/docs/a.pdf", "bytes=0-499")[0], 502
        )  # the part itself is too large
        self.assertEqual(self.deliver("/protected-media/docs/a.pdf")[0], 502)

    def test_nothing_outside_the_media_folder_is_delivered(self) -> None:
        for redirect in [
            "/protected-media/../secret.txt",
            "/protected-media/docs/missing.pdf",
            "/etc/passwd",
            "/protected-media//etc/passwd",
        ]:
            self.assertEqual(self.deliver(redirect)[0], 404, redirect)

    def test_a_file_over_the_limit_is_not_read(self) -> None:
        self.executor.max_bytes = 100
        self.assertEqual(self.deliver("/protected-media/docs/a.pdf")[0], 502)


class CommandTests(LinkTestCase):
    """``rentalars gateway …``."""

    def run_command(self, *arguments: str) -> str:
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"RENTALARS_LANG": "en"}):
            call_command("gateway", *arguments, stdout=out)
        return out.getvalue()

    def test_pair_prints_the_text_and_registers_the_offer(self) -> None:
        text = self.run_command("pair", "anna", "--no-qr", "--name", "Tablet")
        code = next(line for line in text.splitlines() if line.startswith("RGW1:"))
        offer = protocol.PairingOffer.decode(code)
        pairing = GatewayPairing.objects.get(pairing_id=offer.pairing_id.hex())
        self.assertEqual(
            (pairing.user, pairing.device_name, pairing.secret_bytes()), (self.user, "Tablet", offer.secret)
        )
        self.assertNotIn(offer.secret.hex(), pairing.secret)  # stored encrypted
        self.assertIn("█", self.run_command("pair", "anna"))  # the QR code

    def test_pair_for_an_unknown_account_or_without_a_link_fails(self) -> None:
        with self.assertRaises(CommandError):
            self.run_command("pair", "nobody")
        GatewayLink.objects.all().delete()
        with self.assertRaises(CommandError):
            self.run_command("pair", "anna")

    def test_devices_and_revoke(self) -> None:
        self.assertIn("Telefon", self.run_command("devices"))
        self.assertIn("Revoked", self.run_command("revoke", self.device.device_id[:6]))
        self.assertIn("No devices", self.run_command("devices"))
        self.assertIn("revoked", self.run_command("devices", "--all"))
        with self.assertRaises(CommandError):
            self.run_command("revoke", "zz")
        with self.assertRaises(CommandError):
            self.run_command("revoke", "abcdef12")

    def test_connect_links_up_and_keeps_the_keys(self) -> None:
        GatewayLink.objects.all().delete()
        text = protocol.LinkText("https://gateway.example.de:8799", "ab" * 32, "token", "gw1").encode()
        with mock.patch.object(
            service.GatewayClient, "enroll", return_value={"gateway_id": "gw1", "version": "0.1.0"}
        ) as enroll:
            output = self.run_command("connect", text)
        self.assertIn("Connected to https://gateway.example.de:8799", output)
        link = GatewayLink.current()
        self.assertTrue(link.is_connected)
        self.assertEqual(enroll.call_args[0][:3], ("https://gateway.example.de:8799", "ab" * 32, "token"))
        self.assertNotIn("BEGIN", link.link_key + link.e2e_key)  # stored encrypted
        keys = (link.link_key_pem(), link.e2e_key_pem())
        with mock.patch.object(service.GatewayClient, "enroll", return_value={"gateway_id": "gw2", "version": "0.1.0"}):
            self.run_command("connect", text)
        self.assertEqual((GatewayLink.current().link_key_pem(), GatewayLink.current().e2e_key_pem()), keys)

    def test_connect_refuses_bad_texts_and_plain_http(self) -> None:
        with self.assertRaises(CommandError):
            self.run_command("connect", "RGW1:xyz")
        with self.assertRaises(CommandError):
            self.run_command("connect", protocol.LinkText("http://gateway.example.de", "", "token", "gw1").encode())

    def test_disconnect_keeps_keys_and_devices(self) -> None:
        self.run_command("disconnect")
        link = GatewayLink.current()
        self.assertFalse(link.is_connected)
        self.assertTrue(link.link_key and link.e2e_key)
        self.assertTrue(GatewayDevice.objects.filter(pk=self.device.pk).exists())
        self.assertIn("No gateway connected", self.run_command("status"))

    def test_announce_and_clear_a_move(self) -> None:
        with self.assertRaises(CommandError):
            self.run_command("announce-move", "--url", "http://x", "--fingerprint", "ab" * 32)
        with self.assertRaises(CommandError):
            self.run_command("announce-move", "--url", "https://x.example.de", "--fingerprint", "xyz")
        self.run_command("announce-move", "--url", "https://x.example.de/", "--fingerprint", ":".join(["AB"] * 32))
        link = GatewayLink.current()
        self.assertEqual((link.move_url, link.move_fingerprint), ("https://x.example.de", "ab" * 32))
        self.run_command("announce-clear")
        self.assertEqual(GatewayLink.current().move_url, "")

    def test_rekey_needs_confirmation_and_ends_every_pairing(self) -> None:
        token, _key = ApiToken.create_for_user(self.user, "gebunden")
        GatewayTokenBinding.objects.create(token=token, device=self.device)
        before = GatewayLink.current().e2e_key_pem()
        with self.assertRaises(CommandError):
            self.run_command("rekey")
        self.assertTrue(GatewayDevice.objects.exists())
        self.run_command("rekey", "--yes")
        self.assertNotEqual(GatewayLink.current().e2e_key_pem(), before)
        self.assertFalse(GatewayDevice.objects.exists())
        token.refresh_from_db()
        self.assertIsNotNone(token.revoked_at)  # not freed for the direct way

    def test_is_configured_is_the_condition_of_the_service(self) -> None:
        self.run_command("is-configured")
        self.run_command("disconnect")
        with self.assertRaises(SystemExit) as stop:
            self.run_command("is-configured")
        self.assertEqual(stop.exception.code, 1)

    def test_is_configured_cannot_tell_when_the_database_is_away(self) -> None:
        """Exit 1 would make systemd skip the unit for good; 255 makes it fail and try again (review)."""
        from django.db import OperationalError

        with (
            mock.patch.object(GatewayLink, "current", side_effect=OperationalError("away")),
            self.assertRaises(SystemExit) as stop,
        ):
            self.run_command("is-configured")
        self.assertEqual(stop.exception.code, 255)

    def test_status_names_the_state(self) -> None:
        with mock.patch.object(service.GatewayClient, "info", return_value={"version": "0.1.0", "server_online": True}):
            output = self.run_command("status")
        self.assertIn("https://gateway.example.de:8799", output)
        self.assertIn("1 paired", output)
        self.assertIn("no poll yet", output)
        self.assertNotIn(self.link.e2e_key, output)


class MigrationOfNothingTests(RentalarsTestCase):
    """GWY-001: without a gateway nothing changes for the apps' direct way."""

    def test_direct_login_and_token_work_as_before_without_any_link(self) -> None:
        user = make_user("anna")
        self.assertFalse(GatewayLink.objects.exists())
        _token, key = ApiToken.create_for_user(user, "app")
        self.assertEqual(self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {key}").status_code, 200)
        answer = self.client.post(
            "/api/v1/auth/login", {"username": "anna", "password": PASSWORD}, content_type="application/json"
        )
        self.assertEqual(answer.status_code, 200)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.client.get("/api/v1/me").status_code, 200)


ROOT = Path(__file__).resolve().parents[2]


class DeploymentTests(RentalarsTestCase):
    """The unit, the script and the command around the link service."""

    def test_the_unit_is_skipped_without_a_gateway_and_belongs_to_the_application(self) -> None:
        unit = (ROOT / "deploy" / "systemd" / "rentalars-gateway-link.service").read_text(encoding="utf-8")
        self.assertIn(
            "ExecCondition=/opt/rentalars/venv/bin/python /opt/rentalars/app/manage.py gateway is-configured", unit
        )
        self.assertIn("ExecStart=/opt/rentalars/venv/bin/python /opt/rentalars/app/manage.py gateway serve", unit)
        self.assertIn("PartOf=rentalars.service", unit)
        self.assertIn("WantedBy=rentalars.service", unit)  # not multi-user.target: nothing starts it by itself
        self.assertIn("User=rentalars", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertNotIn("ReadWritePaths", unit)

    def test_the_command_passes_gateway_on_to_the_script(self) -> None:
        command = (ROOT / "deploy" / "rentalars").read_text(encoding="utf-8")
        self.assertIn('gateway)       exec bash "${APP_DIR}/deploy/gateway.sh" "$@"', command)

    def test_the_scripts_are_valid_bash(self) -> None:
        import subprocess

        for name in ("gateway.sh", "rentalars"):
            done = subprocess.run(
                ["bash", "-n", str(ROOT / "deploy" / name)], capture_output=True, text=True, timeout=30
            )
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_script_switches_the_unit_on_and_off(self) -> None:
        script = (ROOT / "deploy" / "gateway.sh").read_text(encoding="utf-8")
        self.assertIn('systemctl enable "${LINK_UNIT}"', script)
        self.assertIn('systemctl disable --now "${LINK_UNIT}"', script)
        self.assertIn('systemctl restart "${LINK_UNIT}"', script)
