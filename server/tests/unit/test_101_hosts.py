# SPDX-License-Identifier: GPL-3.0-or-later
"""ADM-016: after an IP change the server answers to its own addresses; a clear page for other hosts."""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings

from rentalars.config import ConfigurationError, load_config
from rentalars.core import hosts

FIB_TRIE = """Main:
  +-- 0.0.0.0/0 3 0 5
     |-- 0.0.0.0
        /0 universe UNICAST
     +-- 127.0.0.0/8 2 0 2
        +-- 127.0.0.0/31 1 0 0
           |-- 127.0.0.0
              /32 link BROADCAST
           |-- 127.0.0.1
              /32 host LOCAL
        |-- 127.255.255.255
           /32 link BROADCAST
     +-- 192.168.1.0/24 2 0 2
        |-- 192.168.1.0
           /32 link BROADCAST
        |-- 192.168.1.50
           /32 host LOCAL
        |-- 192.168.1.255
           /32 link BROADCAST
"""
IF_INET6 = (
    "00000000000000000000000000000001 01 80 10 80       lo\nfe800000000000000211aafffe223344 02 40 20 80     eth0\n"
)
BASE = "[rentalars]\nsecret_key = s\nurl = https://rentalars.example.de\n{extra}[database]\npassword = p\n"


class ConfigTests(SimpleTestCase):
    """``allowed_hosts`` and ``allow_own_addresses`` of the configuration."""

    def load(self, extra: str):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "rentalars.conf"
        path.write_text(BASE.format(extra=extra), encoding="utf-8")
        return load_config(path)

    def test_default_is_nothing_extra_and_own_addresses_on(self) -> None:
        config = self.load("")
        self.assertEqual(config.allowed_hosts, ())
        self.assertTrue(config.allow_own_addresses)

    def test_entries_are_read_and_lowered(self) -> None:
        config = self.load(
            "allowed_hosts = 192.168.1.50, Rentalars.LAN, .example.de, ::1, [0::2], host.lan.\nallow_own_addresses = no\n"
        )
        # An IPv6 address is written the way a request spells it, in brackets; a trailing dot is dropped.
        self.assertEqual(
            config.allowed_hosts, ("192.168.1.50", "rentalars.lan", ".example.de", "[::1]", "[::2]", "host.lan")
        )
        self.assertFalse(config.allow_own_addresses)

    def test_wrong_entries_stop_the_start(self) -> None:
        for entry in (
            "*",
            "http://192.168.1.50",
            "192.168.1.50:8000",
            "rentalars.lan/path",
            "bad name",
            ".192.168.1.1",
        ):
            with self.subTest(entry=entry), self.assertRaisesRegex(ConfigurationError, "allowed_hosts"):
                self.load(f"allowed_hosts = {entry}\n")


class ReadAddressesTests(SimpleTestCase):
    """The addresses are read from the tables of the kernel."""

    def write(self, name: str, text: str) -> Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / name
        path.write_text(text, encoding="ascii")
        return path

    def test_ipv4_and_ipv6(self) -> None:
        found = hosts.read_addresses(self.write("v4", FIB_TRIE), self.write("v6", IF_INET6))
        self.assertEqual(found, {"127.0.0.1", "192.168.1.50", "::1", "fe80::211:aaff:fe22:3344"})

    def test_unreadable_tables_give_nothing(self) -> None:
        missing = Path("/nonexistent/table")
        self.assertEqual(hosts.read_addresses(missing, missing), frozenset())

    def test_is_own_address(self) -> None:
        hosts.forget_addresses()
        self.addCleanup(hosts.forget_addresses)
        with self.settings():
            original = hosts.read_addresses
            hosts.read_addresses = lambda *a, **k: frozenset({"192.168.1.50", "::1"})  # type: ignore[assignment]
            self.addCleanup(setattr, hosts, "read_addresses", original)
            self.assertTrue(hosts.is_own_address("192.168.1.50"))
            self.assertTrue(hosts.is_own_address("192.168.1.50:8000"))
            self.assertTrue(hosts.is_own_address("[::1]:8000"))
            self.assertFalse(hosts.is_own_address("192.168.1.90"))
            self.assertFalse(hosts.is_own_address("evil.example.com"))  # a name is never accepted this way


@override_settings(RENTALARS_URL="https://rentalars.example.de")
class MiddlewareTests(TestCase):
    """The request to an address of the server is answered; every other host gets the clear 400 page."""

    def setUp(self) -> None:
        super().setUp()
        self.addresses = {"192.168.1.50"}
        names = override_settings(
            ALLOWED_HOSTS=hosts.AllowedHosts(["rentalars.example.de", "testserver"]),
            RENTALARS_FIXED_HOSTS=("rentalars.example.de", "testserver"),
        )
        names.enable()
        self.addCleanup(names.disable)
        hosts.forget_addresses()
        self.addCleanup(hosts.forget_addresses)
        original = hosts.read_addresses
        hosts.read_addresses = lambda *a, **k: frozenset(self.addresses)  # type: ignore[assignment]
        self.addCleanup(setattr, hosts, "read_addresses", original)

    def test_own_address_is_answered_and_said_once(self) -> None:
        with self.assertLogs("rentalars.core.hosts", "INFO") as logged:
            first = Client(HTTP_HOST="192.168.1.50").get("/health/")
            second = Client(HTTP_HOST="192.168.1.50:8000").get("/health/")
        self.assertNotEqual((first.status_code, second.status_code), (400, 400))
        self.assertEqual(len(logged.records), 1)

    def test_an_address_that_is_no_longer_the_servers_is_refused_again(self) -> None:
        self.assertNotEqual(Client(HTTP_HOST="192.168.1.50").get("/health/").status_code, 400)
        self.addresses.discard("192.168.1.50")
        self.addresses.add("192.168.1.90")
        hosts.forget_addresses()  # (the addresses are read again after half a minute)
        with self.assertLogs("django.security.DisallowedHost", "WARNING"):
            self.assertEqual(Client(HTTP_HOST="192.168.1.50").get("/health/").status_code, 400)
        self.assertNotEqual(Client(HTTP_HOST="192.168.1.90").get("/health/").status_code, 400)

    def test_only_the_canonical_spelling_of_an_ipv6_address_counts(self) -> None:
        self.addresses.add("::1")
        hosts.forget_addresses()
        self.assertNotEqual(Client(HTTP_HOST="[::1]:8000").get("/health/").status_code, 400)
        for spelling in ("[0::1]", "[00::1]", "[0000:0:0:0:0:0:0:1]", "[::0001]"):
            with self.subTest(spelling=spelling), self.assertLogs("django.security.DisallowedHost", "WARNING"):
                self.assertEqual(Client(HTTP_HOST=spelling).get("/health/").status_code, 400)
        self.assertEqual(len(list(settings.ALLOWED_HOSTS)), 4)  # two names, 192.168.1.50 and [::1]: nothing grows

    @override_settings(RENTALARS_ALLOW_OWN_ADDRESSES=False)
    def test_switched_off(self) -> None:
        with self.assertLogs("django.security.DisallowedHost", "WARNING"):
            response = Client(HTTP_HOST="192.168.1.50").get("/health/")
        self.assertEqual(response.status_code, 400)

    def test_foreign_address_gets_the_clear_page_and_no_error_record(self) -> None:
        from rentalars.core.models import ErrorRecord

        with self.assertLogs("django.security.DisallowedHost", "WARNING"):
            response = Client(HTTP_HOST="192.168.1.90").get("/")
        self.assertEqual(response.status_code, 400)
        text = response.content.decode()
        self.assertIn("192.168.1.90", text)
        self.assertIn("allowed_hosts", text)
        self.assertIn("https://rentalars.example.de", text)
        self.assertEqual(ErrorRecord.objects.count(), 0)

    def test_the_log_entry_is_a_one_line_warning(self) -> None:
        import logging

        records: list[logging.LogRecord] = []

        class Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        logger = logging.getLogger("django.security.DisallowedHost")
        handler = Collect()
        handler.addFilter(hosts.DisallowedHostHint())
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        Client(HTTP_HOST="192.168.1.90").get("/")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIsNone(records[0].exc_info)
        self.assertIn("192.168.1.90", records[0].getMessage())

    def test_the_host_is_escaped(self) -> None:
        with self.assertLogs("django.security.DisallowedHost", "WARNING"):
            response = Client(HTTP_HOST="<script>alert(1)</script>.evil").get("/")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("<script>alert(1)", response.content.decode())

    def test_a_name_in_the_list_is_answered(self) -> None:
        response = Client(HTTP_HOST="rentalars.example.de").get("/health/")
        self.assertNotEqual(response.status_code, 400)
