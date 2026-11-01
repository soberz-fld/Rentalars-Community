# SPDX-License-Identifier: GPL-3.0-or-later
"""Review: calendar feeds, calendar links for readers, reminders of service cases, bundled shortages.

* H1 (VFG-040, PER-023): the wrong calendar links counted on ``REMOTE_ADDR`` – empty behind NGINX on a socket, so
  every client shared one counter: after 20 wrong links (a calendar program polling a renewed or deactivated link)
  every calendar answered "429" for everybody. Now counted per client address as the login counts it
  (``X-Forwarded-For``, trusted in production only); without a known address nothing is counted; the wrong links
  of one client never block a correct link of another. A wrong token and an unknown record count alike.
* M4 (VFG-040): who may only read a product, model or item learns that a calendar link is active – not its
  address, which works without login and which he could not end. The address (page and API ``url``) only for
  whoever may change the link.
* M2 (DOK-015): the update switches "Auch Servicefälle" on; the reminders would then have come for every
  service case done with work and without invoice, at once and every week. Now service cases are
  reminded of only once done after the setting was switched on (``invoice_cases_since`` – set by the update, the
  page and the API, anew each time it is switched on). Projects stay as they were; the lists ("Rechnung offen",
  "Noch zu schreibende Rechnungen") stay complete.
* L4 (VFG-036): the reminder of several known shortages named them all in its title, cut after 250 characters; now
  a short title with their number and the whole list in the text.
* DOK-015, DOK-016 (as the head of the case): the box of the monthly statements on the page of a service case named
  the number of the monthly invoice to everybody with the price right; now only to whoever may open that invoice
  (its project and every case it bills), otherwise "Abgerechnet mit einer Monatsrechnung (März 2027)".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.test import Client, override_settings
from django.urls import reverse

from rentalars.core.models import AuditLogEntry, NotificationSettings, SystemSettings
from rentalars.documents import invoice_reminders, statements
from rentalars.notifications import services as notification_services
from rentalars.notifications.models import Kind, Notification
from rentalars.personnel import calendars
from rentalars.personnel.calendar_views import FEED_FAILURES_PER_ADDRESS, feed_failures_key
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, Project
from rentalars.schedule import calendar_links
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    RentalarsTestCase,
    add_line,
    at,
    make_customer,
    make_person,
    make_project,
    make_stock,
    make_user,
    record_time,
    set_clock,
)
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_085_invoices import close
from tests.unit.test_090_statements import StatementSetup, invoices_in_rentalars, limited_role
from tests.unit.test_093_calendar_links import CalendarData
from tests.unit.test_093_notifications import MIGRATION

ROOT = Path(settings.BASE_DIR)
#: H1: what NGINX sends in production – the application server listens on a socket, ``REMOTE_ADDR`` stays empty.
PRODUCTION = override_settings(RENTALARS_ENVIRONMENT="production")


def behind_nginx(address: str) -> Client:
    """A client as the application sees it behind NGINX: no ``REMOTE_ADDR``, its address in ``X-Forwarded-For``."""
    return Client(REMOTE_ADDR="", HTTP_X_FORWARDED_FOR=address)


# --- H1: the counter of wrong calendar links, per client ---------------------------------------------------------


class FeedCounterPerClientTests(CalendarData, RentalarsTestCase):
    """VFG-040, PER-023: wrong links count per client; a correct link never waits for the wrong links of others."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()
        anna = make_user("anna", superuser=True)
        self.good = calendar_links.feed_path(calendar_links.create_link(self.product, user=anna)[0])
        old, _renewed = calendar_links.create_link(self.items[0], user=anna)
        self.stale = calendar_links.feed_path(old)
        calendar_links.create_link(self.items[0], user=anna)  # renewed: the old address no longer works
        self.carla = make_person("Carla Wolf")
        self.person_feed = f"/calendar-feed/{self.carla.pk}/{calendars.renew_calendar_token(self.carla)}.ics"

    def test_nginx_sends_the_address_the_application_reads(self) -> None:
        """deploy/nginx: the application on a socket, the client's address in ``X-Forwarded-For`` (overwritten)."""
        site = (ROOT / "deploy/nginx/rentalars.conf").read_text(encoding="utf-8")
        self.assertIn("server unix:/run/rentalars/gunicorn.sock", site)
        self.assertIn("include /etc/nginx/snippets/rentalars-proxy.conf;", site)
        proxy = (ROOT / "deploy/nginx/rentalars-proxy.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", proxy)

    @PRODUCTION
    def test_a_stale_subscriber_blocks_only_itself(self) -> None:
        stale = behind_nginx("198.51.100.7")
        for _poll in range(FEED_FAILURES_PER_ADDRESS):
            self.assertEqual(stale.get(self.stale).status_code, 404)
        # That client waits – for every link, its own correct ones too ...
        self.assertEqual(stale.get(self.stale).status_code, 429)
        self.assertEqual(stale.get(self.good).status_code, 429)
        self.assertEqual(stale.get(self.person_feed).status_code, 429)
        # ... everybody else does not.
        other = behind_nginx("203.0.113.9")
        self.assertEqual(other.get(self.good).status_code, 200)
        self.assertEqual(other.get(self.person_feed).status_code, 200)
        self.assertEqual(behind_nginx("2001:db8::1").get(self.good).status_code, 200)

    @PRODUCTION
    def test_wrong_tokens_and_unknown_records_count_alike(self) -> None:
        guesser = behind_nginx("198.51.100.8")
        wrong = [
            self.good.rsplit("/", 1)[0] + "/wrong.ics",  # a known product, a wrong token
            f"/calendar-feed/item/{self.items[0].pk + 1000}/x.ics",  # an unknown item
            f"/calendar-feed/{self.carla.pk}/wrong.ics",  # the subscription link of a person, a wrong token
            "/calendar-feed/999999/x.ics",  # an unknown person
        ]
        for attempt in range(FEED_FAILURES_PER_ADDRESS):
            self.assertEqual(guesser.get(wrong[attempt % len(wrong)]).status_code, 404)
        self.assertEqual(guesser.get(self.good).status_code, 429)
        self.assertEqual(behind_nginx("198.51.100.9").get(self.good).status_code, 200)

    @PRODUCTION
    def test_without_an_address_nothing_is_counted(self) -> None:
        """No address at all (NGINX not sending it): no shared counter – the correct links keep working."""
        nameless = Client(REMOTE_ADDR="")
        for _poll in range(FEED_FAILURES_PER_ADDRESS + 5):
            self.assertEqual(nameless.get(self.stale).status_code, 404)
        self.assertEqual(nameless.get(self.good).status_code, 200)
        self.assertEqual(Client(REMOTE_ADDR="").get(self.person_feed).status_code, 200)

    def test_outside_production_the_header_is_not_trusted(self) -> None:
        """As the login (``client_ip``): a header made up by the client does not escape the counter."""
        for attempt in range(FEED_FAILURES_PER_ADDRESS):
            Client(REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR=f"192.0.2.{attempt}").get(self.stale)
        self.assertEqual(
            Client(REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="192.0.2.99").get(self.good).status_code, 429
        )
        self.assertEqual(Client(REMOTE_ADDR="10.0.0.6").get(self.good).status_code, 200)
        cache.clear()
        self.assertEqual(Client(REMOTE_ADDR="10.0.0.5").get(self.good).status_code, 200)

    def test_the_key(self) -> None:
        def key(**meta: str) -> str | None:
            request = HttpRequest()
            request.META.update(meta)
            return feed_failures_key(request)

        self.assertEqual(key(REMOTE_ADDR="10.0.0.5"), "rentalars:calendar-feed:failures:10.0.0.5")
        self.assertIsNone(key(REMOTE_ADDR=""))
        self.assertIsNone(key(REMOTE_ADDR="kein Rechner"))
        with PRODUCTION:
            self.assertEqual(
                key(REMOTE_ADDR="", HTTP_X_FORWARDED_FOR="2001:DB8:0:0::1"),
                "rentalars:calendar-feed:failures:2001:db8::1",
            )
            self.assertEqual(
                key(REMOTE_ADDR="", HTTP_X_FORWARDED_FOR="192.0.2.1, 198.51.100.7"),
                "rentalars:calendar-feed:failures:198.51.100.7",  # the last one: what NGINX added
            )
            self.assertIsNone(key(REMOTE_ADDR=""))


# --- M4: the address only for whoever may change the link ---------------------------------------------------------


class ReaderSeesNoAddressPageTests(CalendarData, UiTestCase):
    """VFG-040: the box tells a reader that a link is active – the address and the buttons only who may change it."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()
        self.page = f"/products/{self.product.article_number}/"

    def test_reader_and_writer(self) -> None:
        warehouse = self.browser_for("lena", "Lager")  # products: read; material: delete
        text = self.assert_ok(warehouse.get(self.page))
        self.assertIn("Es ist kein Kalender-Link aktiv.", text)
        self.assertNotIn("Kalender-Link erstellen", text)
        link, _renewed = calendar_links.create_link(self.product, user=self.admin_user)
        text = self.assert_ok(warehouse.get(self.page))
        self.assertIn('id="calendar-link"', text)
        self.assertIn("Ein Kalender-Link ist aktiv.", text)
        self.assertIn("Die Adresse sehen nur Benutzer, die den Link ändern dürfen", text)
        self.assertIn("Erstellt am 01.03.2027 08:00 von", text)
        self.assertNotIn(link.token, text)
        self.assertNotIn("/calendar-feed/", text)
        self.assertNotIn("Adresse für Kalenderprogramme", text)
        self.assertNotIn("Neuen Link erstellen", text)
        # The item is hers to change: there she gets the address.
        item_link, _renewed = calendar_links.create_link(self.items[0], user=self.admin_user)
        text = self.assert_ok(warehouse.get(f"/material/items/{self.items[0].pk}/"))
        self.assertIn(f'value="{calendar_links.feed_url(item_link)}"', text)
        self.assertNotIn("Ein Kalender-Link ist aktiv.", text)
        # Who may change the product sees its address as before.
        text = self.assert_ok(self.client.get(self.page))
        self.assertIn(f'data-copy-block="{calendar_links.feed_url(link)}"', text)
        self.assertNotIn("Ein Kalender-Link ist aktiv.", text)


class ReaderSeesNoAddressApiTests(CalendarData, ApiTestCase):
    """VFG-040, API-002: ``GET …/calendar-link`` – ``url`` null for a reader, ``active`` true."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()

    def test_reader_and_writer(self) -> None:
        path = f"{API}/products/{self.product.pk}/calendar-link"
        link = calendar_links.feed_url(calendar_links.create_link(self.product, user=self.admin_user)[0])
        reader = self.client_for("lena", "Lager")
        answer = reader.get(path)
        self.assertEqual(answer.status_code, 200)
        document = answer.json()
        self.assertEqual((document["active"], document["url"]), (True, None))
        self.assertEqual(document["created_by"], str(self.admin_user))
        self.assertNotIn("/calendar-feed/", answer.content.decode())
        self.assertEqual(self.admin.get(path).json()["url"], link)
        # Material is hers to change: the address of the item.
        item = reader.post(f"{API}/material-items/{self.items[0].pk}/calendar-link").json()
        self.assertEqual(
            reader.get(f"{API}/material-items/{self.items[0].pk}/calendar-link").json()["url"], item["url"]
        )
        self.assertIn("/calendar-feed/item/", item["url"])


# --- M2: reminders of service cases since the setting was switched on ------------------------------------------


class ServiceCaseCutOffTests(RentalarsTestCase):
    """DOK-015: after the update only service cases done from then on are reminded of; projects as before."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        SystemSettings.objects.filter(pk=1).update(defaults_installed=True)
        # As left: reminders since the update, service cases off.
        NotificationSettings.objects.filter(pk=1).update(
            invoice_reminders_since=at(1, 0, month=6, year=2026),
            invoice_last_run=at(28, 9, month=2),
            invoice_service_cases=False,
            invoice_cases_since=None,
        )
        self.old_cases = [self.done_case(f"Fall {month}", at(10, 9, month=month, year=2026)) for month in (7, 9, 11)]
        set_clock(at(10, 9, month=11, year=2026))
        self.old_project = make_project(
            "Herbstfest",
            manager=self.paula,
            start=at(1, 10, month=11, year=2026),
            end=at(2, 2, month=11, year=2026),
        )
        add_line(self.old_project, make_stock("S-100", 2), 2)
        self.old_project = close(self.old_project)
        set_clock(at(1, 8))

    def done_case(self, name: str, when: Any) -> Project:
        """A service case with two hours of work, done at ``when``."""
        set_clock(when)
        case = service_cases.create_case(name=name, customer=make_customer(f"Kunde {name}"), manager=self.paula)
        record_time(make_person(f"Tom {name}"), case, "Techniker", when, when.replace(hour=when.hour + 2))
        service_cases.set_case_status(case, CaseStatus.DONE, by=self.paula)
        set_clock(at(1, 8))
        return Project.objects.get(pk=case.pk)

    def due(self, when: Any) -> list[Project]:
        return invoice_reminders.due_projects(when)

    def test_the_update_reminds_only_of_cases_done_after_it(self) -> None:
        MIGRATION.switch_on(apps, None)
        stored = NotificationSettings.objects.get(pk=1)
        self.assertTrue(stored.invoice_service_cases)
        self.assertEqual(stored.invoice_cases_since, at(1, 8))
        # A bookkeeping value: not in the change log of the update.
        entry = AuditLogEntry.objects.get(actor_label="Aktualisierung 0.9.3")
        self.assertEqual(entry.changes, {"invoice_service_cases": [False, True]})
        due = self.due(at(1, 9))
        self.assertEqual([case for case in due if case in self.old_cases], [])
        self.assertIn(self.old_project, due)  # projects as before: closed ones
        # The lists stay complete: an open invoice is still open.
        open_ids = set(invoice_reminders.open_projects().values_list("pk", flat=True))
        self.assertTrue({case.pk for case in self.old_cases} <= open_ids)
        self.assertEqual(invoice_reminders.state_of(self.old_cases[0]), invoice_reminders.InvoiceState.OPEN)
        # A case done after the update is reminded of.
        new = self.done_case("Neu", at(2, 10))
        self.assertIn(new, self.due(at(3, 9)))
        # The check itself: the new case and the project, none of the old cases.
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(3, 9, 1)), 2)
        titles = set(Notification.objects.filter(kind=Kind.INVOICE_REMINDER).values_list("title", flat=True))
        self.assertEqual(
            titles,
            {
                f"Rechnung noch zu schreiben: {new.number} {new.name}",
                f"Rechnung noch zu schreiben: {self.old_project.number} {self.old_project.name}",
            },
        )

    def test_a_fresh_database_gets_no_cut_off(self) -> None:
        SystemSettings.objects.filter(pk=1).update(defaults_installed=False)
        MIGRATION.switch_on(apps, None)
        self.assertIsNone(NotificationSettings.objects.get(pk=1).invoice_cases_since)

    def test_switched_on_before_the_update_stays_as_it_was(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(invoice_service_cases=True)
        MIGRATION.switch_on(apps, None)
        self.assertIsNone(NotificationSettings.objects.get(pk=1).invoice_cases_since)
        self.assertTrue(set(self.old_cases[1:]) <= set(self.due(at(1, 9))))

    def test_switched_off_and_on_again_the_cut_off_moves(self) -> None:
        """Decided: each time it is switched on – the cases done while it was off are listed, not reminded of."""
        row = NotificationSettings.load()
        row.invoice_service_cases = True
        row.save()
        self.assertEqual(NotificationSettings.objects.get(pk=1).invoice_cases_since, at(1, 8))
        between = self.done_case("Dazwischen", at(1, 9))
        self.assertIn(between, self.due(at(3, 9)))
        set_clock(at(1, 10))
        row = NotificationSettings.load()
        row.save()  # saved again, still on: the cut-off stays
        self.assertEqual(NotificationSettings.objects.get(pk=1).invoice_cases_since, at(1, 8))
        row.invoice_service_cases = False
        row.save()
        off = self.done_case("Ausgeschaltet", at(4, 9))
        set_clock(at(5, 12))
        row = NotificationSettings.load()
        row.invoice_service_cases = True
        row.save()
        self.assertEqual(NotificationSettings.objects.get(pk=1).invoice_cases_since, at(5, 12))
        due = self.due(at(8, 9))
        self.assertNotIn(between, due)
        self.assertNotIn(off, due)
        self.assertIn(off, invoice_reminders.open_projects())
        # Never in the change log of the settings.
        for entry in AuditLogEntry.for_object(NotificationSettings.load()):
            self.assertNotIn("invoice_cases_since", entry.changes or {})


class ServiceCaseCutOffPageTests(UiTestCase):
    """DOK-015: Einstellungen → Benachrichtigungen – switching "Auch Servicefälle" on sets the cut-off and shows it."""

    def test_switched_on_on_the_page(self) -> None:
        url = reverse("notifications:company_settings")
        NotificationSettings.objects.filter(pk=1).update(invoice_service_cases=False, invoice_cases_since=None)
        text = self.assert_ok(self.client.get(url))
        self.assertIn("seit dem Einschalten erledigt wurden", text)
        self.assertNotIn("Servicefälle erledigt seit", text)
        data = form_data(self.client.get(url), "shortage_interval")
        data["invoice_service_cases"] = "on"
        self.assertEqual(self.messages_of(self.client.post(url, data, follow=True)), ["Einstellungen gespeichert."])
        self.assertEqual(NotificationSettings.objects.get(pk=1).invoice_cases_since, at(1, 8))
        self.assertIn(
            "<dt>Servicefälle erledigt seit</dt><dd>01.03.2027 08:00</dd>", self.assert_ok(self.client.get(url))
        )


class ServiceCaseCutOffApiTests(ApiTestCase):
    """DOK-015, API-002: ``PATCH /settings/notifications`` sets the cut-off, ``invoice_cases_since`` reads it."""

    def test_switched_on_through_the_api(self) -> None:
        path = f"{API}/settings/notifications"
        NotificationSettings.objects.filter(pk=1).update(invoice_service_cases=False, invoice_cases_since=None)
        self.assertIsNone(self.admin.get(path).json()["invoice_cases_since"])
        changed = self.admin.patch(path, {"invoice_service_cases": True}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["invoice_cases_since"], "2027-03-01T08:00:00+01:00")
        # Read only: a value sent is ignored.
        self.admin.patch(path, {"invoice_cases_since": "2020-01-01T00:00:00+01:00"}, format="json")
        self.assertEqual(NotificationSettings.objects.get(pk=1).invoice_cases_since, at(1, 8))


# --- L4: a short title, the whole list in the text ------------------------------------------------------------------


class ShortageReminderListTests(RentalarsTestCase):
    """VFG-036: the known shortages of a project in one reminder – however many, none lost."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project(manager=self.paula)
        self.names = [f"Sehr lange Produktbezeichnung eines Scheinwerfers Nummer {number:02d}" for number in range(12)]
        for number, name in enumerate(self.names):
            add_line(self.project, make_stock(f"L-{100 + number}", 1, name), 1 + number % 3 + 1)

    def reminder(self) -> Notification:
        notification_services.check_shortages(repeat=True)  # new: one by one
        notification_services.check_shortages(repeat=True)  # known: one reminder
        return Notification.objects.filter(user=self.paula, kind=Kind.SHORTAGE).latest("pk")

    def test_many_products(self) -> None:
        notice = self.reminder()
        self.assertEqual(notice.title, f"Weiterhin Fehlbestände in {self.project}: 12 Produkte")
        lines = notice.body.split("\n")
        self.assertEqual(len(lines), 13)
        for number, name in enumerate(self.names):
            self.assertIn(f"{number % 3 + 1} × {name} fehlen", lines)
        self.assertEqual(lines[-1], "Ab 10.03.2027 00:00. Liste: Planung → Fehlbestände.")

    def test_in_the_language_of_the_recipient(self) -> None:
        self.paula.language = "en"
        self.paula.save()
        notice = self.reminder()
        self.assertEqual(notice.title, f"Still shortages in {self.project}: 12 products")
        self.assertIn(f"1 × {self.names[0]} missing", notice.body.split("\n"))
        self.assertTrue(notice.body.endswith("Shortage list: Planning → Shortages."))


# --- DOK-015, DOK-016: the number of a monthly invoice on the page of a case ----------------------------------------


class StatementHintNumberTests(StatementSetup, UiTestCase):
    """DOK-016: "Abgerechnet mit der Monatsrechnung RE-…" only for who may open it – the rule of the head of the case."""

    def test_the_number_only_for_who_may_open_the_invoice(self) -> None:
        from rentalars.projects.models import ProjectAccessLevel, ProjectMembership

        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 12))
        self.work(self.mixer, at(4, 9), at(4, 10))
        invoice = statements.create_invoice(self.statement(), user=self.paula)
        page = reverse("projects:case_detail", args=[self.spot.pk])
        self.assertIn(
            f"Abgerechnet mit der Monatsrechnung {invoice.number} (März 2027)", self.assert_ok(self.client.get(page))
        )
        # A member of the first case only: the invoice also bills the second one.
        erik = make_user("erik", roles=(limited_role(),))
        ProjectMembership.objects.create(project=self.spot, user=erik, level=ProjectAccessLevel.EDIT)
        text = self.assert_ok(self.browser_of(erik).get(page))
        self.assertIn("Abgerechnet mit einer Monatsrechnung (März 2027)", text)
        self.assertNotIn(invoice.number, text)
        # Member of both cases: the number.
        ProjectMembership.objects.create(project=self.mixer, user=erik, level=ProjectAccessLevel.READ)
        text = self.assert_ok(self.browser_of(erik).get(page))
        self.assertIn(f"Abgerechnet mit der Monatsrechnung {invoice.number} (März 2027)", text)
