# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "security": NFA-071, NFA-072, NFA-073 and the atomic version check of API-010.

* NFA-071: addresses entered in the interface – calendars, webhooks, mail servers of mailboxes – do not
  reach internal addresses unless the operator allows them; the name is resolved once and the connection
  goes to the checked address; redirections are checked again.
* NFA-072: calendar credentials go only to exactly the scheme, host and port they were entered for –
  also on redirections and for addresses the server names – with iCloud's partition hosts as the one
  named exception.
* NFA-073: a production configuration with an http:// address does not start unless ``allow_http = yes``;
  the self-check names the state.
* API-010: comparing ``If-Match`` and writing happen in one transaction that holds a lock row of the
  record; with a database that has row locks, two changes of the same version race and one is refused.
"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models.signals import post_save
from django.test import SimpleTestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import translation
from rest_framework.test import APIClient

from rentalars.accounts.models import ApiToken
from rentalars.api import safeguards, webhooks
from rentalars.api.models import WriteLock
from rentalars.config import ConfigurationError, load_config
from rentalars.core import network, selfcheck
from rentalars.core.defaults import install_defaults
from rentalars.customers.models import Customer
from rentalars.mail.mailboxes import check_connection, smtp_session
from rentalars.material import numbering
from rentalars.personnel import calendar_client, calendars
from rentalars.personnel.calendar_client import CalDAVCalendar, CalendarHttpError, _may_send_credentials
from rentalars.personnel.models import Person
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_customer, make_project, make_user
from tests.mailbox import configure_mailbox
from tests.unit.test_051_personnel_calendars import FEED, serve

NOTHING_ALLOWED = override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())

_REAL_LOOKUP = socket.getaddrinfo


@contextmanager
def fake_dns(names: dict[str, Any]) -> Iterator[list[str]]:
    """Answer DNS questions for invented names; ``names`` maps a name to addresses or to a function giving them.

    Yields the list of names asked, in order.
    """
    asked: list[str] = []

    def lookup(host: Any, port: Any, family: int = 0, kind: int = 0, *args: Any, **kwargs: Any) -> list[Any]:
        name = host.decode() if isinstance(host, bytes) else str(host)
        asked.append(name)
        if name not in names:
            return _REAL_LOOKUP(host, port, family, kind, *args, **kwargs)
        addresses = names[name]() if callable(names[name]) else names[name]
        number = int(port or 0)
        answers = []
        for address in addresses:
            if ":" in address:
                answers.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, number, 0, 0)))
            else:
                answers.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, number)))
        return answers

    with mock.patch("socket.getaddrinfo", lookup):
        yield asked


def without_proxy(test: Any) -> None:
    """The requests of the test go directly, whatever proxy the machine names."""
    environment = {name: value for name, value in os.environ.items() if "proxy" not in name.lower()}
    patcher = mock.patch.dict(os.environ, environment, clear=True)
    patcher.start()
    test.addCleanup(patcher.stop)


class InternalAddressTests(SimpleTestCase):
    """NFA-071: what counts as internal, and what the operator may allow."""

    def test_kinds_of_internal_addresses(self) -> None:
        """NFA-071: loopback, link-local, private, CGNAT, multicast, reserved – also hidden in IPv6."""
        expected = {
            "127.0.0.1": "loopback",
            "10.1.2.3": "private",
            "172.16.0.1": "private",
            "192.168.1.20": "private",
            "100.64.1.1": "shared",
            "169.254.169.254": "link-local",
            "224.0.0.1": "multicast",
            "240.0.0.1": "reserved",
            "0.0.0.0": "unspecified",
            "::1": "loopback",
            "fe80::1": "link-local",
            "fd00::12": "private",
            "::ffff:10.0.0.1": "private",
            "64:ff9b::a00:1": "private",
            "8.8.8.8": "",
            "2a00:1450:4001::1": "",
        }
        self.assertEqual({address: network.kind_of(address) for address in expected}, expected)

    def test_the_allowance_of_the_operator(self) -> None:
        """NFA-071: networks, single addresses and host names; anything else is a mistake."""
        rules = network.parse_allowance(["192.168.1.0/24", "10.0.0.5", "NAS.local.", " ", "fd00::/8"])
        self.assertEqual(rules.names, frozenset({"nas.local"}))
        self.assertTrue(rules.allows_address(network.ipaddress.ip_address("192.168.1.77")))
        self.assertTrue(rules.allows_address(network.ipaddress.ip_address("::ffff:10.0.0.5")))
        self.assertFalse(rules.allows_address(network.ipaddress.ip_address("10.0.0.6")))
        self.assertTrue(rules.allows_name("nas.local"))
        with self.assertRaises(ValueError):
            network.parse_allowance(["nas local"])

    @NOTHING_ALLOWED
    def test_a_name_that_leads_inside_is_refused_unless_allowed(self) -> None:
        """NFA-071: the DNS answer is checked – a harmless-looking name may point inside."""
        with fake_dns({"nas.example": ["192.168.1.10"]}), self.assertRaises(network.BlockedAddressError) as caught:
            network.checked_addresses("nas.example", 443)
        self.assertEqual((caught.exception.host, caught.exception.address), ("nas.example", "192.168.1.10"))
        for allowance in (("192.168.1.0/24",), ("nas.example",)):
            with (
                self.subTest(allowance=allowance),
                override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=allowance),
                fake_dns({"nas.example": ["192.168.1.10"]}),
            ):
                self.assertEqual(network.checked_addresses("nas.example", 443)[0][4][0], "192.168.1.10")

    @NOTHING_ALLOWED
    def test_only_the_allowed_addresses_of_an_answer_are_kept(self) -> None:
        with fake_dns({"mixed.example": ["10.0.0.1", "93.184.216.34"]}):
            kept = network.checked_addresses("mixed.example", 80)
        self.assertEqual([answer[4][0] for answer in kept], ["93.184.216.34"])

    @NOTHING_ALLOWED
    def test_the_own_addresses_of_the_server_are_refused(self) -> None:
        """NFA-071: a public address of this server reaches services that listen only there."""
        own = frozenset({network.ipaddress.ip_address("93.184.216.34")})
        with (
            mock.patch.object(network, "own_addresses", return_value=own),
            fake_dns({"me.example": ["93.184.216.34"]}),
            self.assertRaises(network.BlockedAddressError),
        ):
            network.checked_addresses("me.example", 443)

    @NOTHING_ALLOWED
    def test_an_entered_ip_address_or_localhost_is_refused_at_once(self) -> None:
        for host in ("127.0.0.1", "localhost", "app.localhost", "10.0.0.1", "[::1]", "0.0.0.0"):
            with self.subTest(host=host), self.assertRaises(network.BlockedAddressError):
                network.check_entered_host(host)
        network.check_entered_host("cloud.example.de")  # a name is checked when it is used
        network.check_entered_host("93.184.216.34")


class ConnectionTests(RentalarsTestCase):
    """NFA-071: connections go to the checked address; redirections are checked again."""

    def setUp(self) -> None:
        super().setUp()
        without_proxy(self)
        self.server = serve(self)
        self.server.files["/carla.ics"] = (200, {}, FEED)
        self.port = self.server.server.server_address[1]

    def test_the_connection_goes_to_the_address_that_was_checked(self) -> None:
        """NFA-071: one lookup per connection – a second answer (DNS rebinding) never comes into play."""
        answers = iter([["127.0.0.1"]])

        def first_then_inside() -> list[str]:
            return next(answers, ["10.9.9.9"])

        with fake_dns({"rebind.example": first_then_inside}) as asked:
            body = calendar_client.fetch_calendar(f"http://rebind.example:{self.port}/carla.ics")
        self.assertEqual(body, FEED)
        self.assertEqual(asked.count("rebind.example"), 1)

    @NOTHING_ALLOWED
    def test_reading_a_calendar_inside_is_refused_with_a_clear_text(self) -> None:
        with translation.override("de"), self.assertRaises(CalendarHttpError) as caught:
            calendar_client.fetch_calendar(f"{self.server.url}/carla.ics")
        self.assertIn("internes Netz", str(caught.exception))
        self.assertIn("allow_internal", str(caught.exception))
        self.assertNotIn("127.0.0.1", str(caught.exception))
        self.assertEqual(self.server.requests, [])

    def test_a_redirection_into_the_network_is_checked_again(self) -> None:
        """NFA-071: the allowed host may redirect – the target is checked before it is asked."""
        self.server.files["/moved.ics"] = (302, {"Location": f"http://127.0.0.1:{self.port}/carla.ics"}, b"")
        with (
            override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=("cal.example",)),
            fake_dns({"cal.example": ["127.0.0.1"]}),
            self.assertRaises(CalendarHttpError),
        ):
            calendar_client.fetch_calendar(f"http://cal.example:{self.port}/moved.ics")
        self.assertEqual([path for _method, path, _headers in self.server.requests], ["/moved.ics"])

    @NOTHING_ALLOWED
    def test_through_a_proxy_the_name_is_checked_first(self) -> None:
        """NFA-071: with a proxy of the environment the proxy resolves; Rentalars checks its own answer before."""
        with (
            mock.patch.dict(os.environ, {"http_proxy": "http://proxy.invalid:3128"}),
            fake_dns({"cal.example": ["10.0.0.7"]}),
            self.assertRaises(CalendarHttpError) as caught,
        ):
            calendar_client.fetch_calendar("http://cal.example/carla.ics")
        self.assertIn("allow_internal", str(caught.exception))

    @NOTHING_ALLOWED
    def test_entering_an_internal_calendar_address_is_refused(self) -> None:
        person = Person.objects.get(user=make_user("carla", roles=("Crew",)))
        with translation.override("de"):
            with self.assertRaises(ValidationError) as caught:
                calendars.set_caldav(person, url="http://192.168.1.5/dav/", username="carla", password="x")
            self.assertIn("internes Netz", str(caught.exception))
            with self.assertRaises(ValidationError):
                calendars.add_feed(person, "http://localhost:8080/cal.ics")

    @NOTHING_ALLOWED
    def test_a_webhook_to_an_internal_address_is_not_sent(self) -> None:
        with fake_dns({"erp.example": ["127.0.0.1"]}):
            outcome = webhooks.post(f"http://erp.example:{self.port}/hook", b"{}", {})
        self.assertIsNone(outcome.status_code)
        self.assertIn("allow_internal", outcome.error)
        self.assertEqual(self.server.requests, [])

    @NOTHING_ALLOWED
    def test_mail_servers_inside_are_refused(self) -> None:
        """NFA-071: IMAP and SMTP of a mailbox – also the system mailbox – go through the same check."""
        mailbox = configure_mailbox()
        mailbox.imap_host = mailbox.smtp_host = "10.0.0.25"
        mailbox.save()
        with translation.override("de"):
            results = check_connection(mailbox)
            self.assertEqual([(item.part, item.ok) for item in results], [("IMAP", False), ("SMTP", False)])
            self.assertTrue(all("internes Netz" in item.text for item in results), results)
            with self.assertRaises(ValidationError), smtp_session(mailbox):
                pass
        backend = network.GuardedSmtpBackend(host="10.0.0.25", port=587, timeout=2)
        with self.assertRaises(network.BlockedAddressError):
            backend.open()


class CredentialTests(RentalarsTestCase):
    """NFA-072: credentials only to the server they were entered for."""

    def setUp(self) -> None:
        super().setUp()
        without_proxy(self)

    def test_the_rule(self) -> None:
        send = _may_send_credentials
        self.assertTrue(send("https://cloud.example.de/dav/", "https://cloud.example.de:443/dav/anna/"))
        self.assertTrue(send("http://127.0.0.1:5232/", "http://127.0.0.1:5232/anna/"))
        # Another host of the same domain, another port, http instead of https: not any more.
        self.assertFalse(send("https://cloud.example.de/", "https://files.example.de/"))
        self.assertFalse(send("https://cloud.example.de/", "https://cloud.example.de:8443/"))
        self.assertFalse(send("https://cloud.example.de/", "http://cloud.example.de/"))
        # The one named exception: iCloud's partition hosts, over https only.
        self.assertTrue(send("https://caldav.icloud.com/", "https://p52-caldav.icloud.com/1/calendars/"))
        self.assertTrue(send("https://p07-caldav.icloud.com/", "https://p52-caldav.icloud.com/"))
        self.assertFalse(send("https://caldav.icloud.com/", "https://p52-caldav.icloud.com.evil.example/"))
        self.assertFalse(send("https://caldav.icloud.com/", "http://p52-caldav.icloud.com/"))
        self.assertFalse(send("https://icloud.com.evil.example/", "https://p52-caldav.icloud.com/"))

    def test_a_redirection_to_another_host_loses_the_credentials(self) -> None:
        server = serve(self)
        port = server.server.server_address[1]
        server.files["/go"] = (307, {"Location": f"http://other.example:{port}/cal/anna/work/"}, b"")
        with fake_dns({"cal.example": ["127.0.0.1"], "other.example": ["127.0.0.1"]}):
            calendar_client.request("GET", f"http://cal.example:{port}/go", credentials=("anna", "geheim"))
        sent = [(path, "Authorization" in headers) for _method, path, headers in server.requests]
        self.assertEqual(sent, [("/go", True), ("/cal/anna/work/", False)])

    def test_a_calendar_the_server_names_on_another_host_is_not_taken(self) -> None:
        """NFA-072: the address found is stored and gets the credentials from then on – so never a foreign one."""
        server = serve(self)
        port = server.server.server_address[1]
        original = server.server.RequestHandlerClass.do_PROPFIND

        def foreign_home(handler: Any) -> None:
            if handler.path == "/principals/anna/":
                handler._record()
                body = (
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                    "<d:response><d:href>/principals/anna/</d:href><d:propstat><d:prop><c:calendar-home-set>"
                    f"<d:href>http://evil.example:{port}/cal/anna/</d:href></c:calendar-home-set></d:prop>"
                    "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>"
                ).encode()
                handler._send(207, body, {"Content-Type": "application/xml"})
                return
            original(handler)

        server.server.RequestHandlerClass.do_PROPFIND = foreign_home
        calendar = CalDAVCalendar(f"http://cal.example:{port}/", "anna", "geheim")
        with (
            fake_dns({"cal.example": ["127.0.0.1"], "evil.example": ["127.0.0.1"]}) as asked,
            translation.override("de"),
            self.assertRaises(CalendarHttpError) as caught,
        ):
            calendar.find_collection()
        self.assertIn("anderen Server", str(caught.exception))
        self.assertNotIn("evil.example", asked)
        self.assertEqual([path for _method, path, _headers in server.requests], ["/", "/principals/anna/"])


class ConfigurationTests(SimpleTestCase):
    """NFA-073, NFA-071: the configuration file."""

    def write(self, text: str) -> Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "rentalars.conf"
        path.write_text(text, encoding="utf-8")
        return path

    def test_production_starts_only_with_https_unless_allowed(self) -> None:
        """NFA-073: an http:// address on a production server is refused at start – unless allow_http = yes."""
        base = "[rentalars]\nsecret_key = s\n{extra}[database]\npassword = p\n"
        with self.assertRaisesRegex(ConfigurationError, "https://"):
            load_config(self.write(base.format(extra="url = http://rentalars.example.de\n")))
        with self.assertRaisesRegex(ConfigurationError, "allow_http"):
            load_config(self.write(base.format(extra="")))  # the default address is http://localhost:8000
        allowed = load_config(self.write(base.format(extra="url = http://rentalars.lan\nallow_http = yes\n")))
        self.assertEqual((allowed.url, allowed.allow_http), ("http://rentalars.lan", True))
        secure = load_config(self.write(base.format(extra="url = https://rentalars.example.de\n")))
        self.assertFalse(secure.allow_http)
        development = load_config(self.write("[rentalars]\nenvironment = development\nurl = http://localhost:8000\n"))
        self.assertEqual(development.url, "http://localhost:8000")

    def test_the_network_section(self) -> None:
        """NFA-071: [network] allow_internal – networks, addresses and names, comma-separated."""
        config = load_config(
            self.write(
                "[rentalars]\nenvironment = development\n[network]\nallow_internal = 192.168.1.0/24, nas.local\n"
            )
        )
        self.assertEqual(config.network.allow_internal, ("192.168.1.0/24", "nas.local"))
        self.assertEqual(load_config(self.write("[rentalars]\nenvironment = development\n")).network.allow_internal, ())
        with self.assertRaisesRegex(ConfigurationError, "allow_internal"):
            load_config(self.write("[rentalars]\nenvironment = development\n[network]\nallow_internal = nas local\n"))


class SelfCheckTests(RentalarsTestCase):
    """NFA-071, NFA-073: the self-check names settings that lead inside and the state of HTTPS."""

    def findings(self) -> dict[tuple[str, str], tuple[str, str]]:
        with translation.override("de"):
            report = selfcheck.run_checks()
        return {(item.group, item.title): (item.state, item.detail) for item in report.findings}

    @NOTHING_ALLOWED
    def test_settings_that_lead_inside_are_named_and_kept(self) -> None:
        person = Person.objects.get(user=make_user("carla", roles=("Crew",)))
        Person.objects.filter(pk=person.pk).update(caldav_url="http://192.168.1.5/dav/")
        person.calendar_feeds.create(url="http://localhost:9000/secret-token/cal.ics", label="Band")
        webhooks.create_webhook(url="https://erp.example.de/hook", events=["project.created"], description="ERP")
        with fake_dns({"erp.example.de": ["10.1.1.1"]}):
            state, detail = self.findings()[("Verbindungen zu anderen Servern", "Interne Adressen")]
        self.assertEqual(state, selfcheck.WARNING)
        for part in ("192.168.1.5", "localhost", "Webhook ERP: erp.example.de (10.1.1.1 – privates Netz)"):
            self.assertIn(part, detail)
        self.assertNotIn("secret-token", detail)
        person.refresh_from_db()
        self.assertEqual(person.caldav_url, "http://192.168.1.5/dav/")  # nothing is deleted
        self.assertEqual(person.calendar_feeds.count(), 1)

    def test_nothing_inside(self) -> None:
        with override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=("192.168.1.0/24",)):
            found = self.findings()
        self.assertEqual(found[("Verbindungen zu anderen Servern", "Interne Adressen")][0], selfcheck.OK)
        self.assertEqual(
            found[("Verbindungen zu anderen Servern", "Erlaubte interne Adressen")],
            (selfcheck.NOTE, "192.168.1.0/24"),
        )

    def test_a_proxy_of_the_environment_is_named(self) -> None:
        """NFA-071 (review): through a proxy the guard is weaker – the self-check says so."""
        environment = {name: value for name, value in os.environ.items() if "proxy" not in name.lower()}
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertEqual(self.findings()[("Verbindungen zu anderen Servern", "Proxy")][0], selfcheck.OK)
        with mock.patch.dict(os.environ, {**environment, "https_proxy": "http://user:secret@proxy.example:3128"}):
            state, detail = self.findings()[("Verbindungen zu anderen Servern", "Proxy")]
        self.assertEqual(state, selfcheck.WARNING)
        self.assertIn("schützt dann nur der Proxy", detail)
        self.assertNotIn("secret", detail)

    def test_the_state_of_https(self) -> None:
        """NFA-073: https, http allowed on purpose (warning) – the configuration refuses everything else."""
        with override_settings(RENTALARS_IS_PRODUCTION=True, RENTALARS_URL="https://rentalars.example.de"):
            self.assertEqual(self.findings()[("Sicherheit", "HTTPS")][0], selfcheck.OK)
        with override_settings(
            RENTALARS_IS_PRODUCTION=True, RENTALARS_URL="http://rentalars.lan", RENTALARS_ALLOW_HTTP=True
        ):
            state, detail = self.findings()[("Sicherheit", "HTTPS")]
        self.assertEqual(state, selfcheck.WARNING)
        self.assertIn("allow_http = yes", detail)


class VersionCheckIsOneStepTests(ApiTestCase):
    """API-010: comparing ``If-Match`` and writing happen in one transaction that holds the lock of the record."""

    def test_lock_compare_and_write_in_one_transaction(self) -> None:
        customer = make_customer("Kulturverein")
        url = f"{API}/customers/{customer.pk}"
        tag = self.admin.get(url)["ETag"]
        events: list[tuple[str, Any]] = []
        take_lock = safeguards._take_lock
        check_version = safeguards.ApiSafeguardMiddleware._check_version

        def recording_lock(name: str) -> None:
            take_lock(name)
            events.append(("lock", (name, connection.savepoint_ids[-1] if connection.savepoint_ids else None)))

        def recording_check(middleware: Any, request: Any) -> Any:
            events.append(("compare", None))
            return check_version(middleware, request)

        def written(sender: Any, instance: Customer, **kwargs: Any) -> None:
            events.append(("write", list(connection.savepoint_ids)))

        post_save.connect(written, sender=Customer)
        self.addCleanup(post_save.disconnect, written, sender=Customer)
        with (
            mock.patch.object(safeguards, "_take_lock", recording_lock),
            mock.patch.object(safeguards.ApiSafeguardMiddleware, "_check_version", recording_check),
        ):
            changed = self.admin.patch(url, {"city": "Dorf"}, format="json", HTTP_IF_MATCH=tag)
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual([name for name, _value in events], ["lock", "compare", "write"])
        lock_name, savepoint = events[0][1]
        self.assertEqual(lock_name, f"record:customers.customer:{customer.pk}")
        # The transaction in which the lock was taken is still open when the record is written.
        self.assertIn(savepoint, events[2][1])
        self.assertEqual(WriteLock.objects.count(), 1)

    def test_a_change_of_an_address_without_a_record_locks_the_address(self) -> None:
        events: list[str] = []
        take_lock = safeguards._take_lock

        def recording_lock(name: str) -> None:
            events.append(name)
            take_lock(name)

        with mock.patch.object(safeguards, "_take_lock", recording_lock):
            answer = self.admin.post(f"{API}/customers", {"name": "Neu"}, format="json", HTTP_IF_MATCH="*")
        self.assertEqual(answer.status_code, 201, answer.content)
        self.assertEqual(events, [f"path:{API}/customers"])

    def test_old_lock_rows_are_removed(self) -> None:
        import datetime

        from django.utils import timezone

        WriteLock.objects.create(key="a" * 64, taken_at=timezone.now() - datetime.timedelta(days=2))
        WriteLock.objects.create(key="b" * 64)
        safeguards.delete_old_call_counts()
        self.assertEqual(list(WriteLock.objects.values_list("key", flat=True)), ["b" * 64])


#: How often the race is repeated; without the lock both changes go through every time.
ROUNDS = 3


@skipUnlessDBFeature("has_select_for_update")
class SimultaneousVersionCheckTests(TransactionTestCase):
    """API-010: two changes sent with the same ``ETag`` at the same moment – one is refused (MariaDB only).

    The comparison is slowed down, so that without the lock both would pass it before either writes.
    """

    def setUp(self) -> None:
        super().setUp()
        install_defaults()
        numbering.reset_cache()

    def test_of_two_changes_on_the_same_version_one_is_refused(self) -> None:
        from rentalars.core.models import SystemSettings

        SystemSettings.objects.update(setup_completed=True)
        user = make_user("admin", superuser=True)
        keys = [ApiToken.create_for_user(user, f"test {number}")[1] for number in range(2)]
        check_version: Callable[..., Any] = safeguards.ApiSafeguardMiddleware._check_version

        def slow_check(middleware: Any, request: Any) -> Any:
            result = check_version(middleware, request)
            time.sleep(0.3)
            return result

        for round_number in range(ROUNDS):
            customer = make_customer(f"Runde {round_number}")
            url = f"{API}/customers/{customer.pk}"
            reader = APIClient()
            reader.credentials(HTTP_AUTHORIZATION=f"Bearer {keys[0]}")
            tag = reader.get(url)["ETag"]
            start_together = threading.Barrier(2)
            answers: dict[str, int] = {}
            errors: list[BaseException] = []

            def change(
                key: str,
                city: str,
                start_together: threading.Barrier = start_together,
                url: str = url,
                tag: str = tag,
                answers: dict[str, int] = answers,
                errors: list[BaseException] = errors,
            ) -> None:
                try:
                    client = APIClient()
                    client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
                    start_together.wait(timeout=10)
                    answers[city] = client.patch(url, {"city": city}, format="json", HTTP_IF_MATCH=tag).status_code
                except BaseException as error:
                    errors.append(error)
                finally:
                    connection.close()

            with mock.patch.object(safeguards.ApiSafeguardMiddleware, "_check_version", slow_check):
                threads = [
                    threading.Thread(target=change, args=(key, city))
                    for key, city in zip(keys, ("Dorf", "Stadt"), strict=True)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=60)
            self.assertEqual(errors, [])
            self.assertEqual(sorted(answers.values()), [200, 412], answers)
            customer.refresh_from_db()
            self.assertEqual(answers[customer.city], 200)


class ReplayCoversEveryProjectAddressTests(RentalarsTestCase):
    """API-010 (review): every changing API address with a project in its path names it to the check."""

    def test_every_write_route_with_a_project_in_its_path_is_covered(self) -> None:
        from django.test import RequestFactory
        from django.urls import get_resolver
        from django.urls.resolvers import RegexPattern, RoutePattern

        project = make_project("Stadtfest")
        admin = make_user("admin", superuser=True)

        def names_of(pattern: Any) -> list[str]:
            if isinstance(pattern, RoutePattern):
                return list(pattern.converters)
            if isinstance(pattern, RegexPattern):
                return list(pattern.regex.groupindex)
            return []

        def walk(patterns: Any, prefix: str = "", names: tuple[str, ...] = ()) -> Iterator[tuple[str, Any, tuple]]:
            for entry in patterns:
                here = (*names, *names_of(entry.pattern))
                if hasattr(entry, "url_patterns"):
                    yield from walk(entry.url_patterns, prefix + str(entry.pattern), here)
                else:
                    yield prefix + str(entry.pattern), entry.callback, here

        checked, uncovered = 0, []
        for path, callback, names in walk(get_resolver().url_patterns):
            view_class = getattr(callback, "cls", None)
            if not path.startswith("api/") or view_class is None or "format" in names:
                continue
            actions = getattr(callback, "actions", None) or {}
            methods = [
                m
                for m in ("post", "put", "patch", "delete")
                if m in actions or (not actions and hasattr(view_class, m))
            ]
            names_a_project = "project_pk" in names or (
                "pk" in names and (path.startswith(("api/v1/^projects/", "api/v1/^service-cases/")))
            )
            if not methods or not names_a_project:
                continue
            kwargs = {name: project.pk if name in ("project_pk", "pk") else 1 for name in names}
            if "key" in kwargs:
                kwargs["key"] = "own-1"
            request = RequestFactory().generic(methods[0].upper(), "/api/v1/x")
            request.user = admin
            probe = safeguards._ViewProbe.for_view(request, callback, (), kwargs)
            checked += 1
            if probe is None or project.pk not in probe.projects_in_address():
                uncovered.append(path)
        self.assertGreater(checked, 40)
        self.assertEqual(uncovered, [])
