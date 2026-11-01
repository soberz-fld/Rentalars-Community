# SPDX-License-Identifier: GPL-3.0-or-later
"""Calendar links (iCalendar, .ics) of products, material models and items (VFG-040).

The requirement: .ics links can be activated per product, model or item. By default no separate calendar is active;
e.g. when viewing an item, creating the link can be switched on (and off again).

* None by default; on the page of the record "Kalender-Link erstellen", then the address with "Kopieren",
  "Neuen Link erstellen" (the old address stops working) and "Link deaktivieren" (it stops working at once).
* Changing needs write access to the module of the record, seeing that a link is active read access (the address
  itself only who may change it) – and, as the calendar holds what the timeline holds, the right to
  see availability and to read every project. Every change is in the history of the record; the token never is.
* The calendar holds what the timeline shows – bookings with project number and name, status, quantity and period;
  for an item its deployments, wishes, blocks and inspections – no prices, no customers. Stable UIDs, proper
  escaping and folding, a window of 90 days back and two years ahead, a fixed number of queries.
* Unknown or deactivated links, and those of records out of use, are "not found"; the same through the API.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight
from rentalars.core import export
from rentalars.core.history import describe
from rentalars.core.models import AuditLogEntry
from rentalars.material import services as material_services
from rentalars.material.models import InspectionType, ItemStatus, MaterialItem, MaterialModel
from rentalars.packing import services as packing_services
from rentalars.products.models import ProductKind
from rentalars.projects.models import MaterialLine, ProjectStatus
from rentalars.schedule import calendar_links
from rentalars.schedule.models import CalendarLink
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    at,
    make_customer,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
)
from tests.helpers import add_line as plain_add_line
from tests.ui.base import UiTestCase

# --- A minimal reader of iCalendar files (RFC 5545) -------------------------------------------------------------


def physical_lines(body: bytes) -> list[str]:
    """The lines as written, before unfolding; every one ends with CRLF."""
    text = body.decode("utf-8")
    assert text.endswith("\r\n"), "the file must end with CRLF"
    return text[:-2].split("\r\n")


def _unescape(value: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda match: "\n" if match.group(1) in "nN" else match.group(1), value)


def read_ics(body: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The properties of the calendar and of each event: ``{"SUMMARY": "…", "DTSTART;": {"VALUE": "DATE"}}``."""
    lines: list[str] = []
    for line in physical_lines(body):
        if line.startswith((" ", "\t")):
            lines[-1] += line[1:]  # unfolding
        else:
            lines.append(line)
    calendar: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            assert current is not None
            events.append(current)
            current = None
            continue
        head, _colon, value = line.partition(":")
        name, *parameters = head.split(";")
        target = current if current is not None else calendar
        target[name] = _unescape(value)
        target[f"{name};"] = dict(parameter.split("=", 1) for parameter in parameters)
    return calendar, events


def moment(value: str) -> datetime.datetime:
    """A moment in UTC as the calendar writes it: ``20270310T060000Z``."""
    return datetime.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.UTC)


def by_summary(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {event["SUMMARY"]: event for event in events}


def add_line(*args: Any, **kwargs: Any) -> Any:
    """Add a material line; the line itself."""
    return plain_add_line(*args, **kwargs).line


class CalendarData:
    """A product with four items, a confirmed project, an option and a blocked item."""

    def make_data(self) -> None:
        self.customer = make_customer("Stadtwerke Musterstadt")
        self.product = make_stock("L-010", 4, "LED Par")
        self.model = MaterialModel.objects.get(default_product=self.product)
        self.items = list(self.model.items.order_by("inventory_number"))
        self.fest = make_project("Stadtfest", customer=self.customer)  # confirmed, 10 to 12 March 2027
        self.fest_line = add_line(self.fest, self.product, 2)
        self.wedding = make_project(
            "Hochzeit", customer=self.customer, status=ProjectStatus.OPTION, start=at(20, 10), end=at(21, 2)
        )
        self.wedding_line = add_line(self.wedding, self.product, 1)
        self.block = material_services.add_block(self.items[3], at(5), at(7), "Reparatur Lüfter")

    def feed(self, subject: Any, client: Client | None = None, **headers: Any) -> Any:
        link = CalendarLink.objects.get(**{calendar_links._FIELDS[calendar_links.kind_of(subject)]: subject})
        return (client or Client()).get(calendar_links.feed_path(link), **headers)


# --- Creating, renewing, deactivating ---------------------------------------------------------------------------


class LinkServiceTests(CalendarData, RentalarsTestCase):
    """None by default; create, renew, deactivate – each in the history, the token never."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()
        self.anna = make_user("anna", superuser=True)

    def test_none_by_default(self) -> None:
        for subject in (self.product, self.model, self.items[0]):
            self.assertIsNone(calendar_links.link_of(subject))
        self.assertFalse(CalendarLink.objects.exists())

    def test_create_renew_deactivate(self) -> None:
        link, renewed = calendar_links.create_link(self.items[0], user=self.anna)
        self.assertFalse(renewed)
        first = link.token
        self.assertGreaterEqual(len(first), 43)  # 256 random bits
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_-]+", first))
        self.assertEqual(
            calendar_links.feed_url(link), f"{settings.RENTALARS_URL}/calendar-feed/item/{self.items[0].pk}/{first}.ics"
        )
        self.assertEqual((link.created_at, link.created_by), (at(1, 8), self.anna))
        self.assertEqual(calendar_links.link_for_token("item", self.items[0].pk, first), link)

        link, renewed = calendar_links.create_link(self.items[0], user=self.anna)
        self.assertTrue(renewed)
        self.assertNotEqual(link.token, first)
        self.assertIsNone(calendar_links.link_for_token("item", self.items[0].pk, first))
        self.assertEqual(CalendarLink.objects.count(), 1)

        self.assertTrue(calendar_links.deactivate_link(self.items[0]))
        self.assertIsNone(calendar_links.link_of(self.items[0]))
        self.assertIsNone(calendar_links.link_for_token("item", self.items[0].pk, link.token))
        self.assertFalse(calendar_links.deactivate_link(self.items[0]))  # nothing more to end, nothing logged

        entries = list(AuditLogEntry.for_object(self.items[0]).filter(event__startswith="calendar_link."))
        self.assertEqual(
            [entry.event for entry in reversed(entries)],
            ["calendar_link.created", "calendar_link.renewed", "calendar_link.deactivated"],
        )
        self.assertEqual(
            [item.summary for item in describe(entries, ALL_RIGHTS)],
            [
                "Kalender-Link deaktiviert",
                "Neuer Kalender-Link erstellt; die alte Adresse funktioniert nicht mehr",
                "Kalender-Link (iCalendar) erstellt",
            ],
        )
        # The token is nowhere in the change log, nor in the export.
        logged = " ".join(f"{entry.object_repr} {entry.changes}" for entry in AuditLogEntry.objects.all())
        for token in (first, link.token):
            self.assertNotIn(token, logged)
        self.assertNotIn("token", export._fields(CalendarLink))

    def test_wrong_kind_record_or_token(self) -> None:
        link, _renewed = calendar_links.create_link(self.product, user=self.anna)
        self.assertEqual(calendar_links.link_for_token("product", self.product.pk, link.token), link)
        self.assertIsNone(calendar_links.link_for_token("model", self.product.pk, link.token))
        self.assertIsNone(calendar_links.link_for_token("customer", self.product.pk, link.token))
        self.assertIsNone(calendar_links.link_for_token("product", self.product.pk + 1, link.token))
        self.assertIsNone(calendar_links.link_for_token("product", self.product.pk, link.token[:-1] + "x"))
        self.assertIsNone(calendar_links.link_for_token("product", self.product.pk, ""))

    def test_records_out_of_use_end_their_link(self) -> None:
        product_link, _renewed = calendar_links.create_link(self.product, user=self.anna)
        item_link, _renewed = calendar_links.create_link(self.items[1], user=self.anna)
        self.product.is_active = False
        self.product.save()
        material_services.set_status(self.items[1], ItemStatus.RETIRED, reason="Totalschaden")
        for subject, link in ((self.product, product_link), (self.items[1], item_link)):
            link.refresh_from_db()
            self.assertEqual(link.token, "")
            self.assertTrue(AuditLogEntry.for_object(subject).filter(event="calendar_link.ended").exists())
        # Back in use, the old link stays dead; a new one can be made.
        self.product.is_active = True
        self.product.save()
        self.assertIsNone(calendar_links.link_of(self.product))
        calendar_links.create_link(self.product, user=self.anna)
        # Out of use without a save (a mass change): the link answers "not found" all the same.
        link, _renewed = calendar_links.create_link(self.items[2], user=self.anna)
        MaterialItem.objects.filter(pk=self.items[2].pk).update(status=ItemStatus.LOST)
        self.assertIsNone(calendar_links.link_for_token("item", self.items[2].pk, link.token))
        self.items[2].refresh_from_db()
        self.assertIsNone(calendar_links.link_of(self.items[2]))

    def test_no_link_for_records_out_of_use_or_without_stock(self) -> None:
        from django.core.exceptions import ValidationError

        material_services.set_status(self.items[1], ItemStatus.SOLD, reason="an Kunden verkauft")
        with self.assertRaisesMessage(ValidationError, "ausgemustertes, verkauftes oder verlorenes Exemplar"):
            calendar_links.create_link(self.items[1], user=self.anna)
        kit = make_product("L-900", "Set", kind=ProductKind.KIT)
        with self.assertRaisesMessage(ValidationError, "keinen eigenen Bestand"):
            calendar_links.create_link(kit, user=self.anna)
        self.product.is_active = False
        self.product.save()
        with self.assertRaisesMessage(ValidationError, "deaktiviertes Produkt"):
            calendar_links.create_link(self.product, user=self.anna)

    def test_a_deleted_record_takes_its_link_along(self) -> None:
        model = MaterialModel.objects.create(name="Leeres Modell", category=self.model.category)
        link, _renewed = calendar_links.create_link(model, user=self.anna)
        token = link.token
        model.delete()
        self.assertFalse(CalendarLink.objects.filter(pk=link.pk).exists())
        self.assertIsNone(calendar_links.link_for_token("model", model.pk or link.material_model_id, token))


# --- The calendar ------------------------------------------------------------------------------------------------


class FeedTests(CalendarData, RentalarsTestCase):
    """What the calendars hold, how they are written, and what they leave out."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()
        self.anna = make_user("anna", superuser=True)

    def test_the_calendar_of_a_product(self) -> None:
        calendar_links.create_link(self.product, user=self.anna)
        answer = self.feed(self.product)
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer["Content-Type"], "text/calendar; charset=utf-8")
        self.assertEqual(answer["Cache-Control"], "private, max-age=900")
        self.assertEqual((answer["X-Robots-Tag"], answer["Referrer-Policy"]), ("noindex, nofollow", "no-referrer"))
        self.assertTrue(answer["ETag"].startswith('"'))
        calendar, events = read_ics(answer.content)
        self.assertEqual((calendar["BEGIN"], calendar["VERSION"], calendar["METHOD"]), ("VCALENDAR", "2.0", "PUBLISH"))
        self.assertEqual(calendar["X-WR-CALNAME"], "L-010 LED Par")
        self.assertEqual((calendar["REFRESH-INTERVAL"], calendar["X-PUBLISHED-TTL"]), ("PT30M", "PT30M"))
        self.assertIn("Der Kalender zeigt die Buchungen dieses Produkts", calendar["X-WR-CALDESC"])
        events = by_summary(events)
        fest = events[f"2× {self.fest.number} Stadtfest"]
        self.assertEqual(fest["STATUS"], "CONFIRMED")
        # The period of the timeline: the line with the buffers before and after.
        # The period of the timeline: the line, with the buffers before and after (none here). From midnight to
        # midnight it is an appointment over whole days; the option, with times, is one with times.
        self.assertEqual((fest["DTSTART"], fest["DTSTART;"]), ("20270310", {"VALUE": "DATE"}))
        self.assertEqual((fest["DTEND"], fest["DTEND;"]), ("20270312", {"VALUE": "DATE"}))
        self.assertEqual(
            fest["DESCRIPTION"].split("\n")[:3],
            [f"Projekt: {self.fest.number} Stadtfest", "Status: Bestätigt", "Menge: 2"],
        )
        self.assertIn(f"/projects/{self.fest.number}/", fest["URL"])
        wedding = events[f"1× {self.wedding.number} Hochzeit – Option"]
        self.assertEqual(wedding["STATUS"], "TENTATIVE")
        self.assertIn("Status: Option", wedding["DESCRIPTION"])
        self.assertEqual((moment(wedding["DTSTART"]), moment(wedding["DTEND"])), (at(20, 10), at(21, 2)))
        block = events[f"{self.items[3].display_id} gesperrt: Reparatur Lüfter"]
        # A block from midnight to midnight is an appointment over whole days.
        self.assertEqual((block["DTSTART"], block["DTSTART;"]), ("20270305", {"VALUE": "DATE"}))
        self.assertEqual((block["DTEND"], block["DTEND;"]), ("20270307", {"VALUE": "DATE"}))
        self.assertEqual(len(events), 3)
        # Every event has a UID and a time stamp; no customer, no prices, no contact data.
        self.assertTrue(
            all(event["UID"].startswith(f"rentalars-product{self.product.pk}-") for event in events.values())
        )
        self.assertTrue(all("DTSTAMP" in event for event in events.values()))
        text = answer.content.decode()
        for leak in ("Stadtwerke", self.customer.number, "10,00", "10.00", "€", "EUR", "@example.de"):
            self.assertNotIn(leak, text)

    def test_escaping_and_folding(self) -> None:
        self.fest.name = "Stadtfest; Bühne, Markt\\Platz " + "sehr langer Name " * 6
        self.fest.save()
        calendar_links.create_link(self.product, user=self.anna)
        body = self.feed(self.product).content
        for line in physical_lines(body):
            self.assertLessEqual(len(line.encode()), 75, line)
        self.assertIn(b"Stadtfest\\; B\xc3\xbchne\\, Markt\\\\Platz", body.replace(b"\r\n ", b""))
        _calendar, events = read_ics(body)
        self.assertIn(f"2× {self.fest.number} {self.fest.name}", by_summary(events))

    def test_uids_stay_when_a_booking_changes(self) -> None:
        calendar_links.create_link(self.product, user=self.anna)
        first = self.feed(self.product)
        uids = sorted(event["UID"] for event in read_ics(first.content)[1])
        self.assertEqual(self.feed(self.product, HTTP_IF_NONE_MATCH=first["ETag"]).status_code, 304)
        MaterialLine.objects.filter(pk=self.fest_line.pk).update(quantity=3, end=at(13, 18))
        second = self.feed(self.product, HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(second["ETag"], first["ETag"])
        events = read_ics(second.content)[1]
        self.assertEqual(sorted(event["UID"] for event in events), uids)
        self.assertIn(f"3× {self.fest.number} Stadtfest", by_summary(events))

    def test_the_window_is_90_days_back_and_two_years_ahead(self) -> None:
        old = make_project(
            "Alt", customer=self.customer, start=at(20, 10, month=11, year=2026), end=at(21, 2, month=11, year=2026)
        )
        add_line(old, self.product, 1)
        far = make_project(
            "Fern", customer=self.customer, start=at(1, 10, month=4, year=2029), end=at(2, 2, month=4, year=2029)
        )
        add_line(far, self.product, 1)
        soon = make_project(
            "Herbst", customer=self.customer, start=at(1, 10, month=10, year=2028), end=at(2, 2, month=10, year=2028)
        )
        add_line(soon, self.product, 1)
        winter = make_project("Winter", customer=self.customer, start=at(15, 10, month=1), end=at(16, 2, month=1))
        add_line(winter, self.product, 1)
        calendar_links.create_link(self.product, user=self.anna)
        text = "".join(by_summary(read_ics(self.feed(self.product).content)[1]))
        self.assertIn("Herbst", text)  # 19 months ahead
        self.assertIn("Winter", text)  # 45 days ago
        self.assertNotIn("Alt", text)  # 101 days ago
        self.assertNotIn("Fern", text)  # 25 months ahead

    def test_a_sale_is_one_day(self) -> None:
        tape = make_product("V-001", "Gaffa", kind=ProductKind.SALE, price=None, sale_price=Decimal("14.90"))
        make_items(make_model("Gaffa schwarz", tape), 10)
        add_line(self.fest, tape, 3)
        calendar_links.create_link(tape, user=self.anna)
        (event,) = read_ics(self.feed(tape).content)[1]
        self.assertEqual(event["SUMMARY"], f"3× verkauft – {self.fest.number} Stadtfest")
        self.assertEqual((event["DTSTART"], event["DTEND"]), ("20270310", "20270311"))
        self.assertNotIn("14,90", event["DESCRIPTION"])

    def test_the_calendar_of_a_model_names_the_product(self) -> None:
        calendar_links.create_link(self.model, user=self.anna)
        calendar, events = read_ics(self.feed(self.model).content)
        self.assertEqual(calendar["X-WR-CALNAME"], self.model.name)
        events = by_summary(events)
        self.assertEqual(len(events), 3)
        self.assertIn("Produkt: L-010 LED Par", events[f"2× {self.fest.number} Stadtfest"]["DESCRIPTION"])

    def test_the_calendar_of_an_item(self) -> None:
        item = self.items[0]
        packlist = packing_services.get_packlist(self.fest)
        packing_services.choose_items(packlist, self.fest_line.pk, self.product.pk, [item.pk])
        add_line(self.wedding, self.product, 1, preferred_item=item)
        material_services.add_block(item, at(15, 8), at(16, 18), "Beim Hersteller")
        electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        electric.categories.add(self.model.category)
        calendar_links.create_link(item, user=self.anna)
        calendar, events = read_ics(self.feed(item).content)
        self.assertEqual(calendar["X-WR-CALNAME"], f"{item.display_id} {self.model.name}")
        events = by_summary(events)
        self.assertEqual(
            sorted(events),
            sorted(
                [
                    f"Für die Packliste gewählt: {self.fest.number} Stadtfest",
                    f"Gewünscht: {self.wedding.number} Hochzeit",
                    "Gesperrt: Beim Hersteller",
                    "Prüfung überfällig: Elektrische Prüfung",
                ]
            ),
        )
        chosen = events[f"Für die Packliste gewählt: {self.fest.number} Stadtfest"]
        self.assertIn("Status: Bestätigt", chosen["DESCRIPTION"])
        self.assertEqual(events[f"Gewünscht: {self.wedding.number} Hochzeit"]["STATUS"], "TENTATIVE")
        blocked = events["Gesperrt: Beim Hersteller"]
        self.assertEqual((moment(blocked["DTSTART"]), moment(blocked["DTEND"])), (at(15, 8), at(16, 18)))
        # Never inspected: overdue, today, over the whole day.
        inspection = events["Prüfung überfällig: Elektrische Prüfung"]
        self.assertEqual((inspection["DTSTART"], inspection["DTEND"]), ("20270301", "20270302"))
        self.assertEqual(inspection["DESCRIPTION"], "nie geprüft")
        # Issued, the same appointment says so.
        uid = chosen["UID"]
        packing_services.issue(packlist)
        events = by_summary(read_ics(self.feed(item).content)[1])
        out = events[f"Ausgegeben: {self.fest.number} Stadtfest"]
        self.assertEqual(out["UID"], uid)

    def test_not_found(self) -> None:
        anonymous = Client()
        link, _renewed = calendar_links.create_link(self.items[0], user=self.anna)
        good = calendar_links.feed_path(link)
        self.assertEqual(anonymous.get(good).status_code, 200)  # no login needed
        self.assertEqual(anonymous.head(good).status_code, 200)
        for path in (
            good.replace(link.token, "x" * 43),
            good.replace(f"/item/{self.items[0].pk}/", f"/item/{self.items[1].pk}/"),
            good.replace("/item/", "/model/"),
            good.replace("/item/", "/customer/"),
        ):
            answer = anonymous.get(path)
            self.assertEqual((answer.status_code, answer.content.decode()), (404, "Nicht gefunden."), path)
        self.assertEqual(anonymous.post(good).status_code, 405)
        calendar_links.deactivate_link(self.items[0])
        self.assertEqual(anonymous.get(good).status_code, 404)
        # Archived: the link ends.
        link, _renewed = calendar_links.create_link(self.items[0], user=self.anna)
        good = calendar_links.feed_path(link)
        material_services.set_status(self.items[0], ItemStatus.LOST, reason="nicht zurückgekommen")
        self.assertEqual(anonymous.get(good).status_code, 404)

    def test_guessing_waits(self) -> None:
        link, _renewed = calendar_links.create_link(self.product, user=self.anna)
        good = calendar_links.feed_path(link)
        anonymous = Client()
        for attempt in range(20):
            self.assertEqual(anonymous.get(good.replace(link.token, f"wrong{attempt}")).status_code, 404)
        # Counted with the wrong subscription links of people, per address; the right link waits too.
        self.assertEqual(anonymous.get(good).status_code, 429)
        self.assertEqual(anonymous.get("/calendar-feed/1/wrong.ics").status_code, 429)
        cache.clear()
        statuses = {anonymous.get(good).status_code for _ in range(61)}
        self.assertEqual(statuses, {200, 429})


class QueryTests(CalendarData, RentalarsTestCase):
    """A busy product, model or item: the calendar asks the database a fixed number of times."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()
        self.anna = make_user("anna", superuser=True)

    def queries(self, subject: Any) -> int:
        """The queries of one reading of the calendar, after a first one (that reads the system settings)."""
        link = calendar_links.link_of(subject)
        path = calendar_links.feed_path(link)
        cache.clear()
        anonymous = Client()
        anonymous.get(path)
        with CaptureQueriesContext(connection) as captured:
            self.assertEqual(anonymous.get(path).status_code, 200)
        return len(captured)

    def test_hundreds_of_bookings(self) -> None:
        big = make_stock("L-020", 400, "Kabel")
        calendar_links.create_link(big, user=self.anna)
        model = MaterialModel.objects.get(default_product=big)
        calendar_links.create_link(model, user=self.anna)
        first = make_project("Erstes", customer=self.customer, start=at(2, 10), end=at(3, 2))
        add_line(first, big, 1)
        few = (self.queries(big), self.queries(model))
        for day in range(30):
            project = make_project(
                f"Projekt {day}",
                customer=self.customer,
                start=at(1, 10, month=4) + datetime.timedelta(days=day),
                end=at(2, 2, month=4) + datetime.timedelta(days=day),
            )
            for quantity in range(1, 11):
                add_line(project, big, quantity)
        events = read_ics(self.feed(big).content)[1]
        self.assertEqual(len(events), 301)
        self.assertEqual((self.queries(big), self.queries(model)), few)

    def test_a_busy_item(self) -> None:
        item = self.items[0]
        calendar_links.create_link(item, user=self.anna)
        few = self.queries(item)
        for day in range(12):
            project = make_project(
                f"Wunsch {day}",
                customer=self.customer,
                start=at(1, 10, month=5) + datetime.timedelta(days=day),
                end=at(2, 2, month=5) + datetime.timedelta(days=day),
            )
            add_line(project, self.product, 1, preferred_item=item)
            material_services.add_block(
                item,
                at(1, 8, month=6) + datetime.timedelta(days=day),
                at(1, 9, month=6) + datetime.timedelta(days=day),
                "Wartung",
            )
        self.assertEqual(len(read_ics(self.feed(item).content)[1]), 24)
        self.assertEqual(self.queries(item), few)


# --- The box on the pages -------------------------------------------------------------------------------------


def availability_without_all_projects() -> Role:
    """Products and material, availability – but projects only where assigned."""
    return Role.objects.create(
        name="Lager zugewiesen",
        module_levels={
            Module.PROJECTS: int(Level.READ),
            Module.PRODUCTS: int(Level.WRITE),
            Module.MATERIAL: int(Level.WRITE),
        },
        special_rights=[SpecialRight.AVAILABILITY],
        project_scope=ProjectScope.ASSIGNED,
    )


def without_availability() -> Role:
    """Products and material to change, every project – but no availability of material."""
    return Role.objects.create(
        name="Ohne Verfügbarkeit",
        module_levels={
            Module.PROJECTS: int(Level.READ),
            Module.PRODUCTS: int(Level.WRITE),
            Module.MATERIAL: int(Level.WRITE),
        },
    )


class PageTests(CalendarData, UiTestCase):
    """The box "Kalender-Link" on the pages of product, model and item."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()
        self.pages = {
            "product": f"/products/{self.product.article_number}/",
            "model": f"/material/models/{self.model.pk}/",
            "item": f"/material/items/{self.items[0].pk}/",
        }
        self.subjects = {"product": self.product, "model": self.model, "item": self.items[0]}

    def change(self, kind: str, action: str, client: Client | None = None) -> Any:
        return (client or self.client).post(
            f"/schedule/calendar-links/{kind}/{self.subjects[kind].pk}/", {"action": action}, follow=True
        )

    def test_create_copy_renew_deactivate_on_every_page(self) -> None:
        for kind, page in self.pages.items():
            with self.subTest(kind):
                text = self.assert_ok(self.client.get(page))
                self.assertIn('id="calendar-link"', text)
                self.assertIn("Kalender-Link", text)
                self.assertIn("Es ist kein Kalender-Link aktiv.", text)
                self.assertIn("Kalender-Link erstellen", text)
                self.assertIn("Keine Preise, keine Kunden, keine Kontaktdaten.", text)
                answer = self.change(kind, "create")
                self.assertEqual(answer.redirect_chain[-1][0], f"{page}#calendar-link")
                self.assertEqual(self.messages_of(answer), ["Der Kalender-Link wurde erstellt."])
                link = calendar_links.link_of(self.subjects[kind])
                text = self.assert_ok(answer)
                self.assertIn(f'value="{calendar_links.feed_url(link)}"', text)
                self.assertIn(f'data-copy-block="{calendar_links.feed_url(link)}"', text)
                self.assertIn("Kopieren", text)
                self.assertIn("Adresse für Kalenderprogramme", text)
                self.assertIn("Die Adresse funktioniert ohne Anmeldung", text)
                self.assertIn("Behandle sie wie ein Passwort", text)
                self.assertIn("Erstellt am 01.03.2027 08:00 von", text)
                self.assertIn("Neuen Link erstellen", text)
                self.assertIn("Link deaktivieren", text)
                self.assertNotIn("Kalender-Link erstellen<", text)
                answer = self.change(kind, "renew")
                self.assertEqual(
                    self.messages_of(answer),
                    ["Ein neuer Kalender-Link wurde erstellt; die alte Adresse funktioniert nicht mehr."],
                )
                self.assertNotEqual(calendar_links.link_of(self.subjects[kind]).token, link.token)
                answer = self.change(kind, "deactivate")
                self.assertEqual(
                    self.messages_of(answer),
                    ["Der Kalender-Link ist deaktiviert; seine Adresse funktioniert nicht mehr."],
                )
                self.assertIsNone(calendar_links.link_of(self.subjects[kind]))
                self.assertIn("Es ist kein Kalender-Link aktiv.", self.assert_ok(answer))
        # In the history of the product and of the item.
        text = self.assert_ok(self.client.get(self.pages["product"]))
        self.assertIn("Kalender-Link (iCalendar) erstellt", text)
        self.assertIn("Kalender-Link deaktiviert", text)
        text = self.assert_ok(self.client.get(f"/material/items/{self.items[0].pk}/history/"))
        self.assertIn("Kalender-Link (iCalendar) erstellt", text)

    def test_what_the_box_says_it_shows(self) -> None:
        self.assertIn(
            "Der Kalender zeigt die Buchungen dieses Produkts", self.assert_ok(self.client.get(self.pages["product"]))
        )
        self.assertIn(
            "Der Kalender zeigt die Buchungen des Produkts dieses Modells",
            self.assert_ok(self.client.get(self.pages["model"])),
        )
        self.assertIn("Der Kalender zeigt, wann dieses Exemplar", self.assert_ok(self.client.get(self.pages["item"])))

    def test_write_access_changes_read_access_sees(self) -> None:
        calendar_links.create_link(self.product, user=self.admin_user)
        url = calendar_links.feed_url(calendar_links.link_of(self.product))
        warehouse = self.browser_for("lena", "Lager")  # material: delete; products: read
        text = self.assert_ok(warehouse.get(self.pages["product"]))
        # Review (changed on purpose): a reader sees that a link is active, not the address – it works
        # without login and he could not end it (tests/unit/test_093_review_feeds.py).
        self.assertNotIn(url, text)
        self.assertIn("Ein Kalender-Link ist aktiv.", text)
        self.assertNotIn("Neuen Link erstellen", text)
        self.assertNotIn("Link deaktivieren", text)
        self.assertEqual(self.change("product", "deactivate", warehouse).status_code, 403)
        self.assertEqual(self.change("product", "create", warehouse).status_code, 403)
        self.assertIsNotNone(calendar_links.link_of(self.product))
        # The item is hers to change.
        self.assertIn("Kalender-Link erstellen", self.assert_ok(warehouse.get(self.pages["item"])))
        self.assertEqual(
            self.messages_of(self.change("item", "create", warehouse)), ["Der Kalender-Link wurde erstellt."]
        )
        # Changed on purpose, AUT-036: the Projektleitung only reads products now – a role of its own writes them.
        Role.objects.create(
            name="Produktpflege",
            module_levels={"products": 2, "material": 1, "projects": 1},
            special_rights=[SpecialRight.AVAILABILITY],
        )
        lead = self.browser_for("paula", "Produktpflege")  # products: write; material: read
        text = self.assert_ok(lead.get(self.pages["item"]))
        # Review (changed on purpose): reading the item, she learns that a link is active, not its address.
        self.assertNotIn(calendar_links.feed_url(calendar_links.link_of(self.items[0])), text)
        self.assertIn("Ein Kalender-Link ist aktiv.", text)
        self.assertNotIn("Link deaktivieren", text)
        # The product is hers to change: there she gets the address.
        self.assertIn(f'value="{url}"', self.assert_ok(lead.get(self.pages["product"])))
        self.assertEqual(self.change("item", "deactivate", lead).status_code, 403)

    def test_without_availability_or_every_project_no_box(self) -> None:
        calendar_links.create_link(self.product, user=self.admin_user)
        token = calendar_links.link_of(self.product).token
        for role in (without_availability(), availability_without_all_projects()):
            with self.subTest(role.name):
                user = make_user(f"user{role.pk}")
                user.roles.set([role])
                browser = self.browser_of(user)
                for page in self.pages.values():
                    text = self.assert_ok(browser.get(page))
                    self.assertNotIn('id="calendar-link"', text)
                    self.assertNotIn(token, text)
                self.assertEqual(self.change("product", "deactivate", browser).status_code, 403)
        self.assertIsNotNone(calendar_links.link_of(self.product))

    def test_records_out_of_use(self) -> None:
        material_services.set_status(self.items[0], ItemStatus.RETIRED, reason="alt")
        text = self.assert_ok(self.client.get(self.pages["item"]))
        self.assertIn("Ein ausgemustertes, verkauftes oder verlorenes Exemplar hat keinen Kalender-Link.", text)
        self.assertNotIn("Kalender-Link erstellen", text)
        answer = self.change("item", "create")
        self.assertEqual(
            self.messages_of(answer),
            ["Ein ausgemustertes, verkauftes oder verlorenes Exemplar hat keinen Kalender-Link."],
        )
        self.assertFalse(CalendarLink.objects.exclude(token="").exists())
        # A product without stock of its own has no box at all.
        kit = make_product("L-900", "Set", kind=ProductKind.KIT)
        self.assertNotIn('id="calendar-link"', self.assert_ok(self.client.get(f"/products/{kit.article_number}/")))

    def test_create_sent_twice_keeps_the_address(self) -> None:
        self.change("item", "create")
        token = calendar_links.link_of(self.items[0]).token
        answer = self.change("item", "create")
        self.assertEqual(
            self.messages_of(answer), ["Ein Kalender-Link ist schon aktiv; „Neuen Link erstellen“ ersetzt ihn."]
        )
        self.assertEqual(calendar_links.link_of(self.items[0]).token, token)
        self.assertEqual(AuditLogEntry.for_object(self.items[0]).filter(event__startswith="calendar_link.").count(), 1)

    def test_unknown_kind_or_record(self) -> None:
        self.assertEqual(
            self.client.post("/schedule/calendar-links/customer/1/", {"action": "create"}).status_code, 404
        )
        self.assertEqual(
            self.client.post("/schedule/calendar-links/item/999999/", {"action": "create"}).status_code, 404
        )
        self.assertEqual(self.client.get(f"/schedule/calendar-links/item/{self.items[0].pk}/").status_code, 405)


# --- API (API-002, API-014) ----------------------------------------------------------------------------------------


class ApiTests(CalendarData, ApiTestCase):
    """Read, create/renew and deactivate the link of a product, a model and an item."""

    def setUp(self) -> None:
        super().setUp()
        self.make_data()
        self.paths = {
            "product": f"{API}/products/{self.product.pk}/calendar-link",
            "model": f"{API}/material-models/{self.model.pk}/calendar-link",
            "item": f"{API}/material-items/{self.items[0].pk}/calendar-link",
        }

    def test_every_operation(self) -> None:
        anonymous = Client()
        for kind, path in self.paths.items():
            with self.subTest(kind):
                answer = self.admin.get(path)
                self.assertEqual(answer.status_code, 200)
                self.assertEqual(answer.json()["active"], False)
                self.assertIsNone(answer.json()["url"])
                self.assertIn("Der Kalender zeigt", answer.json()["shows"])
                created = self.admin.post(path)
                self.assertEqual(created.status_code, 201)
                document = created.json()
                self.assertTrue(document["active"])
                self.assertIn(f"/calendar-feed/{kind}/", document["url"])
                self.assertEqual(document["created_by"], str(self.admin_user))
                self.assertIsNotNone(document["created_at"])
                feed = document["url"].split("://", 1)[1].split("/", 1)[1]
                self.assertEqual(anonymous.get(f"/{feed}").status_code, 200)
                renewed = self.admin.post(path)
                self.assertEqual(renewed.status_code, 200)
                self.assertNotEqual(renewed.json()["url"], document["url"])
                self.assertEqual(anonymous.get(f"/{feed}").status_code, 404)
                self.assertEqual(self.admin.get(path).json()["url"], renewed.json()["url"])
                self.assertEqual(self.admin.delete(path).status_code, 204)
                self.assertEqual(self.admin.get(path).json()["active"], False)
                self.assertEqual(self.admin.delete(path).status_code, 204)  # nothing to end
                cache.clear()

    def test_rights(self) -> None:
        self.admin.post(self.paths["product"])
        warehouse = self.client_for("lena", "Lager")
        self.assertEqual(warehouse.get(self.paths["product"]).status_code, 200)
        self.assert_error(warehouse.post(self.paths["product"]), 403, "permission_denied")
        self.assert_error(warehouse.delete(self.paths["product"]), 403, "permission_denied")
        self.assertEqual(warehouse.post(self.paths["item"]).status_code, 201)
        nobody = make_user("otto")
        nobody.roles.set([without_availability()])
        client = self.client_of(nobody)
        for path in self.paths.values():
            self.assert_error(client.get(path), 403, "permission_denied")
        self.assert_error(self.client_for("carl", "Crew").get(self.paths["item"]), 403, "permission_denied")
        self.assertTrue(self.admin.get(self.paths["product"]).json()["active"])

    def test_refused_and_unknown(self) -> None:
        material_services.set_status(self.items[0], ItemStatus.RETIRED, reason="alt")
        error = self.assert_error(self.admin.post(self.paths["item"]), 400, "validation_error")
        self.assertIn("ausgemustertes", error["message"])
        self.assert_error(self.admin.get(f"{API}/material-items/999999/calendar-link"), 404, "not_found")
        self.assert_error(self.admin.post(f"{API}/products/999999/calendar-link"), 404, "not_found")
