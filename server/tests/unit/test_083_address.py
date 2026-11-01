# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "address": server address and certificate from the settings (ADM-016).

Two halves: the application's side (rentalars/core/server_address.py – the name, the uploaded certificate, the
checks, storing, export and record) and the command on the server (deploy/address.py – checking the export
again, the NGINX site, backup, apply and rollback). The command's tests run in temporary folders; NGINX,
systemd, certbot and runuser are replaced by a fake server, openssl and the shell helpers of lib.sh run for real.
"""

from __future__ import annotations

import datetime
import importlib.util
import io
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import TestCase as PlainTestCase
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command

from rentalars.core import server_address
from rentalars.core.address_models import AddressChange, AddressChangeStatus
from rentalars.core.crypto import decrypt_secret
from tests.address_certificates import isolate_server_address, make_chain, make_self_signed
from tests.helpers import RentalarsTestCase, make_user

ROOT = Path(settings.BASE_DIR)


def _load_command() -> Any:
    spec = importlib.util.spec_from_file_location("rentalars_address_command", ROOT / "deploy" / "address.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


address = _load_command()

#: UIX-029: the command speaks the operator's language; the tests read it in German unless they say otherwise.
_GERMAN_OPERATOR = mock.patch.dict(os.environ, {"RENTALARS_LANG": "de"})


def setUpModule() -> None:
    _GERMAN_OPERATOR.start()


def tearDownModule() -> None:
    _GERMAN_OPERATOR.stop()


REAL_NOW = datetime.datetime.now(datetime.UTC)


# --- The application's side ---------------------------------------------------------------------------------


class HostNameTests(PlainTestCase):
    """ADM-016: the name is checked before anything is stored."""

    def test_names_are_normalised(self) -> None:
        self.assertEqual(server_address.normalise_host(" Rentalars.Example.COM "), "rentalars.example.com")
        self.assertEqual(server_address.normalise_host("https://rentalars.example.com/"), "rentalars.example.com")
        self.assertEqual(server_address.normalise_host("verleih.müller.example"), "verleih.xn--mller-kva.example")
        self.assertEqual(server_address.normalise_host("rentalars.firma.lan"), "rentalars.firma.lan")

    def test_wrong_names_are_refused(self) -> None:
        for text in ("", "192.168.1.5", "::1", "host:8443", "a/b", "localhost", "-bad.example.com", "a..b", "x.123"):
            with self.subTest(text=text), self.assertRaises(server_address.AddressError):
                server_address.normalise_host(text)

    def test_lets_encrypt_needs_a_public_name(self) -> None:
        for text in ("rentalars.firma.lan", "rentalars.local", "rentalars"):
            with self.subTest(text=text), self.assertRaises(server_address.AddressError):
                server_address.normalise_host(text, for_letsencrypt=True)

    def test_wildcards_cover_one_label(self) -> None:
        self.assertTrue(server_address.name_matches("a.example.com", ["*.example.com"]))
        self.assertFalse(server_address.name_matches("a.b.example.com", ["*.example.com"]))
        self.assertFalse(server_address.name_matches("example.com", ["*.example.com"]))


class CertificateCheckTests(RentalarsTestCase):
    """ADM-016: an uploaded certificate – key matches, chain, names, expiry."""

    host = "rentalars.example.com"

    def check(self, certificate: bytes, key: bytes, host: str | None = None) -> server_address.CertificateReport:
        return server_address.check_certificate(certificate, key, host or self.host)

    def test_a_good_chain_passes(self) -> None:
        chain = make_chain(self.host)
        report = self.check(chain.leaf_and_intermediate, chain.key)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.info["names"], [self.host])
        self.assertEqual(report.info["issuer"], "Test Intermediate CA")
        self.assertEqual(report.info["chain_length"], 2)
        self.assertTrue(report.chain_pem.startswith(chain.leaf.decode()))
        # Not issued by an authority browsers know: a warning, not an error.
        self.assertTrue(any("Zertifizierungsstelle" in text for text in report.warnings), report.warnings)

    def test_the_order_is_put_right(self) -> None:
        chain = make_chain(self.host)
        report = self.check(chain.intermediate + chain.leaf, chain.key)
        self.assertEqual(report.errors, [])
        self.assertTrue(report.chain_pem.startswith(chain.leaf.decode()))
        self.assertTrue(report.notes)

    def test_a_key_of_another_certificate_is_refused(self) -> None:
        chain = make_chain(self.host)
        report = self.check(chain.leaf_and_intermediate, chain.other_key)
        self.assertIn("Der Schlüssel gehört zu keinem Zertifikat der Datei.", report.errors)

    def test_another_name_is_refused(self) -> None:
        chain = make_chain("other.example.com")
        report = self.check(chain.leaf_and_intermediate, chain.key)
        self.assertTrue(any("other.example.com" in text and self.host in text for text in report.errors), report.errors)

    def test_a_wildcard_certificate_fits(self) -> None:
        chain = make_chain(self.host, names=["*.example.com"])
        self.assertEqual(self.check(chain.leaf_and_intermediate, chain.key).errors, [])

    def test_no_names_is_refused(self) -> None:
        chain = make_chain(self.host, names=[])
        self.assertTrue(self.check(chain.leaf_and_intermediate, chain.key).errors)

    def test_expired_and_expiring(self) -> None:
        expired = make_chain(self.host, days=-2, started_days_ago=30)
        self.assertTrue(
            any("abgelaufen" in text for text in self.check(expired.leaf_and_intermediate, expired.key).errors)
        )
        soon = make_chain(self.host, days=10)
        report = self.check(soon.leaf_and_intermediate, soon.key)
        self.assertEqual(report.errors, [])
        self.assertTrue(
            any("läuft in 9 Tagen ab" in text or "läuft in 10 Tagen ab" in text for text in report.warnings)
        )

    def test_a_key_with_password_is_refused(self) -> None:
        chain = make_chain(self.host, password=b"secret")
        report = self.check(chain.leaf_and_intermediate, chain.key)
        self.assertTrue(any("Passwort" in text for text in report.errors), report.errors)

    def test_swapped_files_are_named(self) -> None:
        chain = make_chain(self.host)
        report = self.check(chain.key, chain.leaf)
        self.assertTrue(any("vertauscht" in text for text in report.errors), report.errors)

    def test_a_certificate_outside_the_chain_is_refused(self) -> None:
        chain = make_chain(self.host)
        stranger = make_chain("stranger.example.com")
        report = self.check(chain.leaf_and_intermediate + stranger.intermediate, chain.key)
        self.assertTrue(report.errors)

    def test_missing_intermediates_get_a_warning(self) -> None:
        chain = make_chain(self.host)
        report = self.check(chain.leaf, chain.key)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("Zwischenzertifikate" in text for text in report.warnings), report.warnings)

    def test_a_self_signed_certificate_gets_a_warning(self) -> None:
        certificate, key = make_self_signed(self.host)
        report = self.check(certificate, key)
        self.assertEqual(report.errors, [])
        self.assertTrue(report.info["self_signed"])
        self.assertTrue(any("selbst signiert" in text for text in report.warnings))

    def test_garbage_is_refused(self) -> None:
        self.assertTrue(self.check(b"hello", b"world").errors)
        self.assertTrue(self.check(b"", b"").errors)


class PrepareTests(RentalarsTestCase):
    """ADM-016: storing a change – model, files in the data folder, the key encrypted, older ones replaced."""

    def setUp(self) -> None:
        super().setUp()
        self.data = isolate_server_address(self, addresses=["203.0.113.10"])
        self.admin = make_user("admin", superuser=True)

    def test_a_self_signed_change(self) -> None:
        change = server_address.prepare(self.admin, host="Neu.Example.com", kind="selfsigned")
        self.assertEqual(change.host, "neu.example.com")
        self.assertEqual(change.status, AddressChangeStatus.PREPARED)
        self.assertEqual(len(change.token), 16)
        self.assertEqual(change.command, f"sudo rentalars address apply {change.token}")
        self.assertEqual(change.previous_url, settings.RENTALARS_URL)
        self.assertTrue(change.redirect_old)
        self.assertEqual(change.prepared_by, self.admin)
        self.assertFalse(server_address.files_dir(change).exists())
        titles = [check["title"] for check in change.checks]
        self.assertIn("DNS von neu.example.com", titles)

    def test_an_own_certificate_is_stored_privately(self) -> None:
        chain = make_chain("neu.example.com")
        change = server_address.prepare(
            self.admin,
            host="neu.example.com",
            kind="own",
            certificate=chain.leaf_and_intermediate,
            private_key=chain.key,
        )
        folder = server_address.files_dir(change)
        self.assertEqual(folder.parent, self.data / "address")
        self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
        for name in (server_address.CERTIFICATE_FILE, server_address.KEY_FILE):
            self.assertEqual(os.stat(folder / name).st_mode & 0o777, 0o600)
        stored_key = (folder / server_address.KEY_FILE).read_text()
        self.assertNotIn("PRIVATE KEY", stored_key)
        self.assertEqual(decrypt_secret(stored_key.strip()), chain.key.decode())
        self.assertEqual(change.certificate_info["names"], ["neu.example.com"])
        self.assertNotIn("key", json.dumps(change.certificate_info).lower().replace("public", ""))

    def test_a_newer_change_replaces_the_older_one(self) -> None:
        chain = make_chain("neu.example.com")
        first = server_address.prepare(
            self.admin,
            host="neu.example.com",
            kind="own",
            certificate=chain.leaf_and_intermediate,
            private_key=chain.key,
        )
        second = server_address.prepare(self.admin, host="neu.example.com", kind="selfsigned")
        first.refresh_from_db()
        self.assertEqual(first.status, AddressChangeStatus.SUPERSEDED)
        self.assertFalse(server_address.files_dir(first).exists())
        self.assertEqual(server_address.latest(), second)

    def test_an_e_mail_address_with_a_leading_hyphen_is_refused(self) -> None:
        """ADM-016: certbot would read "-x@…" as an option."""
        with self.assertRaises(server_address.AddressError) as raised:
            server_address.prepare(self.admin, host="neu.example.com", kind="letsencrypt", email="-x@example.com")
        self.assertIn("email", raised.exception.errors)

    def test_what_cannot_work_is_refused(self) -> None:
        with self.assertRaises(server_address.AddressError) as raised:
            server_address.prepare(self.admin, host="neu.example.com", kind="letsencrypt", email="")
        self.assertIn("email", raised.exception.errors)
        with self.assertRaises(server_address.AddressError) as raised:
            server_address.prepare(self.admin, host="neu.example.com", kind="own")
        self.assertIn("certificate", raised.exception.errors)
        with self.assertRaises(server_address.AddressError) as raised:
            server_address.prepare(self.admin, host=server_address.host_of(settings.RENTALARS_URL), kind="proxy")
        self.assertIn("host", raised.exception.errors)
        with self.assertRaises(server_address.AddressError):
            server_address.prepare(self.admin, host="neu.example.com", kind="magic")
        self.assertFalse(AddressChange.objects.exists())

    def test_the_steps_name_what_happens(self) -> None:
        change = server_address.prepare(self.admin, host="neu.example.com", kind="letsencrypt", email="it@example.com")
        text = " ".join(server_address.steps(change))
        self.assertIn("Let's Encrypt", text)
        self.assertIn("https://neu.example.com", text)
        self.assertIn("leitet die alte adresse", text.lower())


class ChecksTests(RentalarsTestCase):
    """ADM-016: DNS of the new name and the ports – and saying so when Rentalars cannot be sure."""

    def setUp(self) -> None:
        super().setUp()
        isolate_server_address(self)
        self.current = server_address.current_state()

    def states(
        self, host: str, kind: str, resolved: dict[str, list[str]], own: set[str] | None = None
    ) -> dict[str, str]:
        import ipaddress

        with (
            mock.patch("rentalars.core.server_address._resolve", side_effect=lambda name: resolved.get(name, [])),
            mock.patch(
                "rentalars.core.network._interface_addresses",
                return_value={ipaddress.ip_address(a) for a in own or set()},
            ),
        ):
            return {check["title"]: check["state"] for check in server_address.run_checks(host, kind, self.current)}

    def test_a_name_of_this_server(self) -> None:
        states = self.states("neu.example.com", "selfsigned", {"neu.example.com": ["203.0.113.10"]}, {"203.0.113.10"})
        self.assertEqual(states["DNS von neu.example.com"], "ok")

    def test_the_same_address_as_the_current_name(self) -> None:
        self.current.host = "alt.example.com"
        resolved = {"neu.example.com": ["198.51.100.7"], "alt.example.com": ["198.51.100.7"]}
        self.assertEqual(self.states("neu.example.com", "own", resolved)["DNS von neu.example.com"], "ok")

    def test_an_unknown_address_is_a_doubt(self) -> None:
        states = self.states("neu.example.com", "own", {"neu.example.com": ["198.51.100.99"]})
        self.assertEqual(states["DNS von neu.example.com"], "warning")

    def test_no_dns_stops_lets_encrypt(self) -> None:
        self.assertEqual(self.states("neu.example.com", "letsencrypt", {})["DNS von neu.example.com"], "error")
        self.assertEqual(self.states("neu.example.com", "selfsigned", {})["DNS von neu.example.com"], "warning")

    def test_a_private_address_stops_lets_encrypt(self) -> None:
        states = self.states("neu.example.com", "letsencrypt", {"neu.example.com": ["192.168.1.20"]})
        self.assertEqual(states["Let's Encrypt"], "error")

    def test_ports_without_nginx_are_not_checked(self) -> None:
        states = self.states("neu.example.com", "selfsigned", {})
        self.assertEqual(states["Ports"], "note")


class CurrentStateTests(RentalarsTestCase):
    """ADM-016: what the page shows of the address now."""

    def setUp(self) -> None:
        super().setUp()
        self.folder = isolate_server_address(self).parent
        self.site = self.folder / "site"

    def state(self, site_text: str | None, presented: Any = None) -> server_address.CurrentState:
        if site_text is not None:
            self.site.write_text(site_text)
        with mock.patch("rentalars.core.server_address.presented_certificate", return_value=presented):
            return server_address.current_state(site_path=self.site)

    def test_without_nginx(self) -> None:
        state = self.state(None)
        self.assertEqual(state.kind, "proxy")
        self.assertIn("keine NGINX-Konfiguration", state.note)

    def test_lets_encrypt(self) -> None:
        site = render_template("rentalars.example.com", "/etc/letsencrypt/live/rentalars.example.com/fullchain.pem")
        state = self.state(site)
        self.assertEqual(state.kind, "letsencrypt")
        self.assertEqual(state.site.server_names, ["rentalars.example.com"])

    def test_self_signed_and_own(self) -> None:
        from cryptography import x509

        site = render_template("rentalars.example.com", "/etc/rentalars/tls/certificate.pem")
        certificate, _key = make_self_signed("rentalars.example.com")
        state = self.state(site, x509.load_pem_x509_certificate(certificate))
        self.assertEqual(state.kind, "selfsigned")
        self.assertEqual(state.certificate["names"], ["rentalars.example.com"])
        chain = make_chain("rentalars.example.com")
        self.assertEqual(self.state(site, x509.load_pem_x509_certificate(chain.leaf)).kind, "own")
        self.assertEqual(self.state(site, None).kind, "unknown")


class ExportAndRecordTests(RentalarsTestCase):
    """ADM-016: the two ends the command on the server talks to (manage.py address_change)."""

    def setUp(self) -> None:
        super().setUp()
        isolate_server_address(self)
        admin = make_user("admin", superuser=True)
        self.chain = make_chain("neu.example.com")
        self.change = server_address.prepare(
            admin,
            host="neu.example.com",
            kind="own",
            certificate=self.chain.leaf_and_intermediate,
            private_key=self.chain.key,
        )

    def export(self) -> dict[str, Any]:
        out = io.StringIO()
        call_command("address_change", "export", self.change.token, stdout=out)
        return json.loads(out.getvalue())

    def test_export_hands_over_certificate_and_key(self) -> None:
        data = self.export()
        self.assertEqual(data["host"], "neu.example.com")
        self.assertEqual(data["certificate_kind"], "own")
        self.assertEqual(data["private_key"], self.chain.key.decode())
        self.assertTrue(data["certificate"].startswith(self.chain.leaf.decode()))
        self.assertEqual(data["prepared_by"], "admin")
        # What the command accepts.
        change = address.parse_change(json.dumps(data), self.change.token)
        self.assertEqual(change.host, "neu.example.com")

    def test_applied_deletes_the_files(self) -> None:
        call_command(
            "address_change", "record", self.change.token, "--applied", "--by", "kai", "--details", '{"backup": "/x"}',
            stdout=io.StringIO(),
        )  # fmt: skip
        self.change.refresh_from_db()
        self.assertEqual(self.change.status, AddressChangeStatus.APPLIED)
        self.assertEqual(self.change.applied_by, "kai")
        self.assertEqual(self.change.result, {"backup": "/x"})
        self.assertFalse(server_address.files_dir(self.change).exists())
        with self.assertRaises(CommandError):
            self.export()

    def test_the_answer_follows_the_operator_language(self) -> None:
        """UIX-029: lib.sh passes RENTALARS_LANG to the command."""
        for language, text in (("en", "The result is recorded."), ("de", "Das Ergebnis ist vermerkt.")):
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"RENTALARS_LANG": language}):
                call_command("address_change", "record", self.change.token, "--failed", "--by", "kai", stdout=out)
            self.assertIn(text, out.getvalue())
        with (
            mock.patch.dict(os.environ, {"RENTALARS_LANG": "en"}),
            self.assertRaisesMessage(CommandError, "no open change"),
        ):
            call_command("address_change", "export", "0" * 16, stdout=io.StringIO())

    def test_a_failure_keeps_it_open(self) -> None:
        call_command(
            "address_change", "record", self.change.token, "--failed", "--by", "kai", "--message", "nginx -t",
            stdout=io.StringIO(),
        )  # fmt: skip
        self.change.refresh_from_db()
        self.assertEqual(self.change.status, AddressChangeStatus.FAILED)
        self.assertEqual(self.change.result_message, "nginx -t")
        self.assertTrue(self.change.is_open)
        self.assertEqual(self.export()["host"], "neu.example.com")

    def test_unknown_and_discarded_tokens(self) -> None:
        with self.assertRaises(CommandError):
            call_command("address_change", "export", "0" * 16, stdout=io.StringIO())
        server_address.discard(self.change)
        with self.assertRaises(CommandError):
            self.export()


# --- The command on the server (deploy/address.py) -------------------------------------------------------------


def render_template(host: str, certificate: str, key: str | None = None, data_dir: str = "/var/lib/rentalars") -> str:
    """The NGINX site as install.sh writes it (render_nginx_site, without adapting HTTP/2)."""
    key = key or certificate.replace("fullchain.pem", "privkey.pem").replace("certificate.pem", "private-key.pem")
    text = (ROOT / "deploy" / "nginx" / "rentalars.conf").read_text()
    return (
        text.replace("@DOMAIN@", host)
        .replace("@CERTIFICATE@", certificate)
        .replace("@PRIVATE_KEY@", key)
        .replace("@DATA_DIR@", data_dir)
    )


def openssl_self_signed(folder: Path, host: str) -> tuple[Path, Path]:
    """A real certificate made with openssl now (the command checks against the real clock)."""
    certificate, key = folder / "certificate.pem", folder / "private-key.pem"
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes", "-days", "30",
            "-subj", f"/CN={host}", "-addext", f"subjectAltName=DNS:{host}", "-keyout", str(key), "-out", str(certificate),
        ],
        check=True, capture_output=True,
    )  # fmt: skip
    return certificate, key


class ParseChangeTests(PlainTestCase):
    """ADM-016: the command trusts nothing it reads from the application."""

    token = "0123456789abcdef"

    def data(self, **changes: Any) -> str:
        data = {
            "token": self.token,
            "host": "neu.example.com",
            "certificate_kind": "selfsigned",
            "email": "",
            "redirect_old": True,
            "prepared_by": "admin",
            "certificate": "",
            "private_key": "",
        }
        data.update(changes)
        return json.dumps(data)

    def test_a_good_change(self) -> None:
        change = address.parse_change(self.data(), self.token)
        self.assertEqual((change.host, change.kind, change.redirect_old), ("neu.example.com", "selfsigned", True))

    def test_bad_values_are_refused(self) -> None:
        bad = [
            {"token": "fedcba9876543210"},
            {"host": "neu.example.com; rm -rf /"},
            {"host": "../../etc"},
            {"host": "Neu.Example.com"},
            {"host": "10.0.0.1"},
            {"host": 5},
            {"certificate_kind": "shell"},
            {"certificate_kind": "letsencrypt", "email": "x; reboot"},
            {"certificate_kind": "own", "certificate": "nothing", "private_key": "nothing"},
        ]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises(address.AddressFailureError):
                address.parse_change(self.data(**changes), self.token)
        for text in ("[]", "nonsense", "x" * 2_000_000):
            with self.subTest(text=text[:10]), self.assertRaises(address.AddressFailureError):
                address.parse_change(text, self.token)

    def test_only_true_redirects(self) -> None:
        self.assertFalse(address.parse_change(self.data(redirect_old="yes"), self.token).redirect_old)


class EditSiteTests(PlainTestCase):
    """ADM-016: the NGINX site gets the new name, the new certificate and the redirect of the old name."""

    old_certificate = "/etc/rentalars/tls/certificate.pem"

    def setUp(self) -> None:
        self.site = render_template("alt.example.com", self.old_certificate)

    def redirect(self, old: str, new: str, *, https: bool = True) -> str:
        return address.redirect_block(
            old,
            new,
            certificate=self.old_certificate if https else "",
            private_key="/etc/rentalars/tls/private-key.pem" if https else "",
            ipv6=True,
            acme_root=Path("/var/www/rentalars-acme"),
        )

    def test_name_certificate_and_redirect(self) -> None:
        text = address.edit_site(
            self.site,
            old_host="alt.example.com",
            new_host="neu.example.com",
            certificate="/etc/rentalars/tls/neu.example.com/certificate.pem",
            private_key="/etc/rentalars/tls/neu.example.com/private-key.pem",
            redirect=self.redirect("alt.example.com", "neu.example.com"),
        )
        main, section = address.split_site(text)
        self.assertEqual(main.count("server_name neu.example.com;"), 2)
        self.assertNotIn("server_name alt.example.com", main)
        self.assertIn("ssl_certificate     /etc/rentalars/tls/neu.example.com/certificate.pem;", main)
        self.assertIn("ssl_certificate_key /etc/rentalars/tls/neu.example.com/private-key.pem;", main)
        self.assertIn("server_name alt.example.com;", section)
        self.assertEqual(section.count("return 301 https://neu.example.com$request_uri;"), 2)
        self.assertIn(self.old_certificate, section)
        # Everything else of the template stays.
        self.assertIn("ssl_reject_handshake on;", main)
        self.assertIn("limit_req_zone", main)
        site = address.read_site_text(main)
        self.assertEqual(site.certificate, "/etc/rentalars/tls/neu.example.com/certificate.pem")

    def test_a_second_change_points_all_old_names_to_the_newest(self) -> None:
        first = address.edit_site(
            self.site, old_host="alt.example.com", new_host="b.example.com",
            redirect=self.redirect("alt.example.com", "b.example.com"),
        )  # fmt: skip
        second = address.edit_site(
            first, old_host="b.example.com", new_host="c.example.com",
            redirect=self.redirect("b.example.com", "c.example.com", https=False),
        )  # fmt: skip
        _main, section = address.split_site(second)
        self.assertIn("# redirect: alt.example.com", section)
        self.assertIn("# redirect: b.example.com", section)
        self.assertNotIn("https://b.example.com$request_uri", section)
        self.assertEqual(section.count("return 301 https://c.example.com$request_uri;"), 3)
        # Back to the first name: its redirect goes, the others point to it.
        third = address.edit_site(second, old_host="c.example.com", new_host="alt.example.com", redirect=None)
        _main, section = address.split_site(third)
        self.assertNotIn("# redirect: alt.example.com", section)
        self.assertIn("return 301 https://alt.example.com$request_uri;", section)
        self.assertEqual(third.count(address.REDIRECTS_BEGIN), 1)

    def test_a_site_without_the_old_name_is_not_touched(self) -> None:
        with self.assertRaises(address.AddressFailureError):
            address.edit_site(self.site, old_host="other.example.com", new_host="neu.example.com")

    def test_only_the_certificate(self) -> None:
        text = address.edit_site(
            self.site, old_host="alt.example.com", new_host="alt.example.com",
            certificate="/etc/rentalars/tls/alt.example.com/certificate.pem",
            private_key="/etc/rentalars/tls/alt.example.com/private-key.pem",
        )  # fmt: skip
        self.assertIn("server_name alt.example.com;", text)
        self.assertNotIn(address.REDIRECTS_BEGIN, text)
        self.assertIn("/etc/rentalars/tls/alt.example.com/private-key.pem;", text)

    def test_without_ipv6(self) -> None:
        block = address.redirect_block(
            "a.example.com", "b.example.com", certificate="", private_key="", ipv6=False, acme_root=Path("/x")
        )
        self.assertNotIn("[::]", block)
        self.assertNotIn("443", block)


class CertificateFilesTests(PlainTestCase):
    """ADM-016: the command checks certificate and key again with openssl."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)

    def write(self, certificate: bytes, key: bytes) -> tuple[Path, Path]:
        paths = self.folder / "c.pem", self.folder / "k.pem"
        paths[0].write_bytes(certificate)
        paths[1].write_bytes(key)
        return paths

    def test_good_and_bad(self) -> None:
        chain = make_chain("neu.example.com", now=REAL_NOW)
        certificate, key = self.write(chain.leaf_and_intermediate, chain.key)
        self.assertEqual(address.check_certificate_files(certificate, key, "neu.example.com"), [])
        with self.assertRaises(address.AddressFailureError):
            address.check_certificate_files(certificate, key, "other.example.com")
        certificate, key = self.write(chain.leaf_and_intermediate, chain.other_key)
        with self.assertRaises(address.AddressFailureError):
            address.check_certificate_files(certificate, key, "neu.example.com")
        stranger = make_chain("neu.example.com", now=REAL_NOW)
        certificate, key = self.write(chain.leaf + stranger.intermediate, chain.key)
        with self.assertRaises(address.AddressFailureError) as raised:
            address.check_certificate_files(certificate, key, "neu.example.com")
        self.assertIn("Kette", str(raised.exception))
        expired = make_chain("neu.example.com", now=REAL_NOW, days=-1, started_days_ago=10)
        certificate, key = self.write(expired.leaf_and_intermediate, expired.key)
        with self.assertRaises(address.AddressFailureError):
            address.check_certificate_files(certificate, key, "neu.example.com")
        soon = make_chain("neu.example.com", now=REAL_NOW, days=5)
        certificate, key = self.write(soon.leaf_and_intermediate, soon.key)
        self.assertTrue(address.check_certificate_files(certificate, key, "neu.example.com"))


class FakeServer:
    """NGINX, systemd, certbot and runuser of a server; openssl and bash (lib.sh) run for real."""

    def __init__(self, paths: Any, export: dict[str, Any] | None = None) -> None:
        self.paths = paths
        self.export = export
        self.calls: list[list[str]] = []
        self.nginx_ok = True
        self.answers = True
        self.recorded: list[list[str]] = []

    def __call__(self, args: list[str], *, check: bool = True, input_text: str | None = None) -> Any:
        args = list(args)
        self.calls.append(args)
        program = args[0]
        code, out = 0, ""
        if program == "bash" and "application_answers" in args[2]:
            code = 0 if self.answers else 1
        elif program in ("openssl", "bash"):
            return address.run_command(args, check=check)
        elif program == "nginx":
            code = 0 if self.nginx_ok else 1
        elif program == "certbot":
            host = args[args.index("-d") + 1]
            live = self.paths.letsencrypt_live / host
            certificate, key = openssl_self_signed(live, host)
            certificate.rename(live / "fullchain.pem")
            key.rename(live / "privkey.pem")
        elif program == "runuser":
            if "export" in args:
                out = json.dumps(self.export)
            else:
                self.recorded.append(args)
        result = subprocess.CompletedProcess(args, code, out, "kaputt" if code else "")
        if check and code:
            raise address.AddressFailureError(f"{program} meldet: kaputt")
        return result


class ApplyTests(PlainTestCase):
    """ADM-016: backup, apply, rollback – in temporary folders instead of /etc."""

    token = "0123456789abcdef"

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        etc = self.folder / "etc"
        (etc / "tls").mkdir(parents=True)
        self.paths = address.Paths(
            config_file=etc / "rentalars.conf",
            config_dir=etc,
            nginx_site=self.folder / "site",
            acme_root=self.folder / "acme",
            letsencrypt_live=self.folder / "live",
            app_dir=ROOT,
            lock_file=self.folder / "lock",
        )
        self.config = "[rentalars]\nurl = https://alt.example.com\nsecret_key = x\n"
        self.paths.config_file.write_text(self.config)
        openssl_self_signed(etc / "tls", "alt.example.com")
        self.site = render_template(
            "alt.example.com", str(etc / "tls" / "certificate.pem"), str(etc / "tls" / "private-key.pem")
        )
        self.paths.nginx_site.write_text(self.site)

    def change(self, kind: str = "selfsigned", **values: Any) -> Any:
        data = {
            "host": "neu.example.com", "kind": kind, "email": "", "redirect_old": True, "prepared_by": "admin",
            "certificate": "", "private_key": "",
        }  # fmt: skip
        data.update(values)
        return address.Change(token=self.token, **data)

    def applier(self, change: Any, server: FakeServer) -> Any:
        applier = address.Applier(change, self.paths, server, "kai", services=True)
        applier.read_current()
        return applier

    def test_self_signed(self) -> None:
        server = FakeServer(self.paths)
        applier = self.applier(self.change(), server)
        with mock.patch.object(address, "https_check", return_value="") as https, redirect_stdout(io.StringIO()):
            applier.apply()
        https.assert_called()
        self.assertIn("url = https://neu.example.com", self.paths.config_file.read_text())
        self.assertIn("secret_key = x", self.paths.config_file.read_text())
        site = self.paths.nginx_site.read_text()
        self.assertIn("server_name neu.example.com;", site)
        new = self.paths.tls_dir / "neu.example.com"
        self.assertIn(f"ssl_certificate     {new / 'certificate.pem'};", site)
        self.assertEqual(os.stat(new / "private-key.pem").st_mode & 0o777, 0o600)
        self.assertIn("# redirect: alt.example.com", site)
        self.assertTrue(applier.redirect_https)
        self.assertTrue((applier.backup_dir / "rentalars.conf").is_file())
        self.assertTrue((applier.backup_dir / "tls" / "certificate.pem").is_file())
        programs = [call[0] if call[0] != "systemctl" else " ".join(call[:3]) for call in server.calls]
        self.assertIn("nginx", programs)
        self.assertLess(
            programs.index("systemctl reload-or-restart nginx"), programs.index("systemctl restart rentalars")
        )

    def test_a_refused_nginx_configuration_is_rolled_back(self) -> None:
        server = FakeServer(self.paths)
        server.nginx_ok = False
        applier = self.applier(self.change(), server)
        with (
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
            self.assertRaises(address.AddressFailureError) as raised,
        ):
            applier.apply()
        self.assertIn("zurückgesetzt", str(raised.exception))
        self.assertEqual(self.paths.config_file.read_text(), self.config)
        self.assertEqual(self.paths.nginx_site.read_text(), self.site)
        self.assertFalse((self.paths.tls_dir / "neu.example.com").exists())

    def test_a_new_address_that_does_not_answer_is_rolled_back(self) -> None:
        server = FakeServer(self.paths)
        applier = self.applier(self.change(), server)
        with (
            mock.patch.object(address, "https_check", return_value="NGINX zeigt nicht das neue Zertifikat."),
            mock.patch.object(address.time, "sleep"),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
            self.assertRaises(address.AddressFailureError),
        ):
            applier.apply()
        self.assertEqual(self.paths.config_file.read_text(), self.config)
        self.assertEqual(self.paths.nginx_site.read_text(), self.site)
        restarts = [call for call in server.calls if call[:2] == ["systemctl", "restart"]]
        self.assertEqual(len(restarts), 2)  # after the change, and after putting it back

    def test_own_certificate(self) -> None:
        chain = make_chain("neu.example.com", now=REAL_NOW)
        change = self.change("own", certificate=chain.leaf_and_intermediate.decode(), private_key=chain.key.decode())
        applier = self.applier(change, FakeServer(self.paths))
        with mock.patch.object(address, "https_check", return_value=""), redirect_stdout(io.StringIO()):
            applier.apply()
        folder = self.paths.tls_dir / "neu.example.com"
        self.assertEqual((folder / "certificate.pem").read_bytes(), chain.leaf_and_intermediate)
        self.assertEqual(os.stat(folder / "private-key.pem").st_mode & 0o777, 0o600)

    def test_lets_encrypt(self) -> None:
        server = FakeServer(self.paths)
        applier = self.applier(self.change("letsencrypt", email="it@example.com"), server)
        with (
            mock.patch.object(address.shutil, "which", return_value="/usr/bin/certbot"),
            mock.patch.object(address, "https_check", return_value=""),
            redirect_stdout(io.StringIO()),
        ):
            applier.apply()
        programs = [" ".join(call[:2]) for call in server.calls]
        # NGINX answers for the new name before certbot asks.
        self.assertLess(programs.index("systemctl reload-or-restart"), programs.index("certbot certonly"))
        certbot = next(call for call in server.calls if call[0] == "certbot")
        self.assertIn("--webroot", certbot)
        self.assertIn("--email=it@example.com", certbot)  # one argument: an address cannot become an option
        site = self.paths.nginx_site.read_text()
        self.assertIn(f"{self.paths.letsencrypt_live / 'neu.example.com' / 'fullchain.pem'};", site)

    def test_behind_a_proxy_only_the_name(self) -> None:
        applier = self.applier(self.change("proxy", redirect_old=False), FakeServer(self.paths))
        with mock.patch.object(address, "https_check", return_value=""), redirect_stdout(io.StringIO()):
            applier.apply()
        site = self.paths.nginx_site.read_text()
        self.assertIn("server_name neu.example.com;", site)
        self.assertIn(f"{self.paths.tls_dir / 'certificate.pem'};", site)
        self.assertNotIn(address.REDIRECTS_BEGIN, site)

    def test_without_systemd_nothing_is_restarted(self) -> None:
        server = FakeServer(self.paths)
        applier = address.Applier(self.change(), self.paths, server, "kai", services=False)
        applier.read_current()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            applier.apply()
        self.assertFalse([call for call in server.calls if call[0] == "systemctl"])
        self.assertIn("url = https://neu.example.com", self.paths.config_file.read_text())


class MainTests(ApplyTests):
    """ADM-016: the command as the operator runs it – dry run, apply, recording the result."""

    def export(self, **values: Any) -> dict[str, Any]:
        data = {
            "token": self.token, "host": "neu.example.com", "certificate_kind": "selfsigned", "email": "",
            "redirect_old": True, "prepared_by": "admin", "certificate": "", "private_key": "",
        }  # fmt: skip
        data.update(values)
        return data

    def main(self, server: FakeServer, *arguments: str) -> tuple[int, str]:
        out = io.StringIO()
        with (
            mock.patch.object(address.os, "geteuid", return_value=0),
            mock.patch.object(address, "systemd_running", return_value=True),
            mock.patch.object(address, "https_check", return_value=""),
            redirect_stdout(out),
            redirect_stderr(out),
        ):
            code = address.main(["apply", self.token, *arguments], self.paths, server)
        return code, out.getvalue()

    def test_dry_run_changes_nothing(self) -> None:
        server = FakeServer(self.paths, self.export())
        code, out = self.main(server, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("Probelauf", out)
        self.assertIn("https://alt.example.com  →  https://neu.example.com", out)
        self.assertIn("+    server_name neu.example.com;", out)
        self.assertEqual(self.paths.config_file.read_text(), self.config)
        self.assertEqual(self.paths.nginx_site.read_text(), self.site)
        self.assertEqual(server.recorded, [])
        self.assertFalse(self.paths.backup_root.exists())

    def test_apply_records_the_result(self) -> None:
        server = FakeServer(self.paths, self.export())
        with mock.patch.dict(os.environ, {"SUDO_USER": "kai"}):
            code, out = self.main(server, "--yes")
        self.assertEqual(code, 0, out)
        self.assertIn("url = https://neu.example.com", self.paths.config_file.read_text())
        (recorded,) = server.recorded
        self.assertIn("--applied", recorded)
        self.assertEqual(recorded[recorded.index("--by") + 1], "kai")

    def test_a_failure_is_recorded(self) -> None:
        server = FakeServer(self.paths, self.export())
        server.nginx_ok = False
        code, out = self.main(server, "--yes")
        self.assertEqual(code, 1)
        self.assertIn("zurückgesetzt", out)
        (recorded,) = server.recorded
        self.assertIn("--failed", recorded)

    def test_wrong_calls(self) -> None:
        server = FakeServer(self.paths, self.export())
        self.assertEqual(self.main(server, "--now")[0], 2)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            self.assertEqual(address.main(["apply", "NOT-A-TOKEN"], self.paths, server), 2)
            self.assertEqual(address.main(["--help"], self.paths, server), 0)
        self.assertEqual(server.calls, [])

    def test_an_own_certificate_is_checked_again(self) -> None:
        chain = make_chain("other.example.com", now=REAL_NOW)
        export = self.export(
            certificate_kind="own", certificate=chain.leaf_and_intermediate.decode(), private_key=chain.key.decode()
        )
        code, out = self.main(FakeServer(self.paths, export), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("gilt nicht für neu.example.com", out)


class EnglishOperatorTests(MainTests):
    """UIX-029, ADM-016: with an English locale the command, its plan and its errors are English."""

    def test_dry_run_in_english(self) -> None:
        server = FakeServer(self.paths, self.export())
        with mock.patch.dict(
            os.environ, {"RENTALARS_LANG": "", "LC_ALL": "", "LC_MESSAGES": "", "LANG": "en_GB.UTF-8"}
        ):
            code, out = self.main(server, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("dry run, nothing is changed", out)
        self.assertIn("Address:      https://alt.example.com  →  https://neu.example.com", out)
        self.assertIn("Certificate:  self-signed certificate", out)
        self.assertNotIn("Probelauf", out)
        export = next(call for call in server.calls if call[0] == "runuser")
        self.assertIn("RENTALARS_LANG=en", export)

    def test_errors_in_english(self) -> None:
        server = FakeServer(self.paths, self.export())
        server.nginx_ok = False
        with mock.patch.dict(os.environ, {"RENTALARS_LANG": "en"}):
            code, out = self.main(server, "--yes")
            refused = io.StringIO()
            with redirect_stderr(refused):
                self.assertEqual(address.main(["apply", "NOT-A-TOKEN"], self.paths, server), 2)
        self.assertIn("This is not a valid TOKEN", refused.getvalue())
        self.assertEqual(code, 1)
        self.assertIn("Error:", out)
        self.assertIn("everything was put back", out)
        self.assertNotIn("zurückgesetzt", out)

    def test_german_from_the_locale(self) -> None:
        with mock.patch.dict(
            os.environ, {"RENTALARS_LANG": "", "LC_ALL": "", "LC_MESSAGES": "de_DE.UTF-8", "LANG": "C"}
        ):
            self.assertEqual(address.operator_language(), "de")
        with mock.patch.dict(os.environ, {"RENTALARS_LANG": "en", "LANG": "de_DE.UTF-8"}):
            self.assertEqual(address.operator_language(), "en")


class HardeningTests(MainTests):
    """ADM-016: what the review found – line breaks, control characters, the lock file, e-mail options."""

    def test_a_trailing_line_break_is_refused(self) -> None:
        self.assertFalse(address.valid_host("example.com\n"))
        self.assertFalse(server_address.valid_label("com\n"))
        self.assertTrue(server_address.valid_label("com"))
        parse = ParseChangeTests()
        for changes in (
            {"host": "neu.example.com\n"},
            {"certificate_kind": "letsencrypt", "email": "it@example.com\n"},
        ):
            with self.subTest(changes=changes), self.assertRaises(address.AddressFailureError):
                address.parse_change(parse.data(**changes), parse.token)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            self.assertEqual(address.main(["apply", self.token + "\n"], self.paths, FakeServer(self.paths)), 2)

    def test_control_characters_do_not_reach_the_terminal(self) -> None:
        parse = ParseChangeTests()
        with self.assertRaises(address.AddressFailureError) as raised:
            address.parse_change(parse.data(host="evil\x1b]0;owned\x07.example.com"), parse.token)
        self.assertNotIn("\x1b", str(raised.exception))
        self.assertIn("\\x1b", str(raised.exception))
        with self.assertRaises(address.AddressFailureError) as raised:
            address.parse_change(parse.data(certificate_kind="own\x9b2J"), parse.token)
        self.assertNotIn("\x9b", str(raised.exception))

        def refusing(args: list[str], **_options: Any) -> Any:
            return subprocess.CompletedProcess(args, 1, "", "CommandError: \x1b[2Jgone\x1b]0;title\x07")

        with self.assertRaises(address.AddressFailureError) as raised:
            address.load_change(self.paths, refusing, self.token)
        self.assertNotIn("\x1b", str(raised.exception))
        self.assertNotIn("\x07", str(raised.exception))
        self.assertIn("gone", str(raised.exception))

    def test_the_lock_file_never_follows_a_link(self) -> None:
        self.assertEqual(address.Paths().lock_file, Path("/run/rentalars-address.lock"))
        target = self.folder / "victim"
        target.write_text("keep")
        self.paths.lock_file.symlink_to(target)
        with self.assertRaises(address.AddressFailureError), address.locked(self.paths.lock_file):
            pass
        self.assertEqual(target.read_text(), "keep")
        self.paths.lock_file.unlink()
        with address.locked(self.paths.lock_file):
            self.assertEqual(os.stat(self.paths.lock_file).st_mode & 0o777, 0o600)

    def test_an_e_mail_address_cannot_be_an_option(self) -> None:
        parse = ParseChangeTests()
        with self.assertRaises(address.AddressFailureError):
            address.parse_change(parse.data(certificate_kind="letsencrypt", email="-x@example.com"), parse.token)


class HttpsCheckTests(PlainTestCase):
    """ADM-016: after the restart the command asks NGINX for the login page and compares the certificate."""

    def test_answer_and_certificate(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        certificate, key = openssl_self_signed(folder, "neu.example.com")
        other, _other_key = openssl_self_signed(folder / "other", "neu.example.com")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        listener = socket.create_server(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        self.addCleanup(listener.close)

        def serve() -> None:
            for _ in range(2):
                connection, _address = listener.accept()
                with context.wrap_socket(connection, server_side=True) as tls:
                    tls.recv(1000)
                    tls.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.assertEqual(address.https_check("neu.example.com", certificate.read_text(), port=port), "")
        self.assertIn("nicht das neue Zertifikat", address.https_check("neu.example.com", other.read_text(), port=port))
        thread.join(5)
        listener.close()
        self.assertIn("antwortet", address.https_check("neu.example.com", "", port=port))
