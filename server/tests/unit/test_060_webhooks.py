# SPDX-License-Identifier: GPL-3.0-or-later
"""Webhooks: events are noted with the change and delivered in the background (API-012).

* Recording – which changes become events, for which webhooks, with what
  content; nothing for a change that is rolled back.
* Delivering – signature and headers, retries with growing pauses, giving
  up, switching a webhook off, the bounded run of the timer.
* By hand – "Send test" and "Send again".
* The HTTP client itself, against a small server on this machine.

Except for the last group, the receiver is a stand-in for ``webhooks.post``:
no request leaves the test.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import socket
import threading
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from typing import Any
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.test import SimpleTestCase

from rentalars.api import webhook_events, webhooks
from rentalars.api.models import DeliveryStatus, Webhook, WebhookDelivery, validate_webhook_url
from rentalars.core import export
from rentalars.core.models import AuditLogEntry
from rentalars.documents import services as documents
from rentalars.documents.models import DocumentKind
from rentalars.notifications.models import Kind, Notification
from rentalars.packing import subprojects
from rentalars.packing.services import (
    complete_return,
    get_packlist,
    issue,
    return_all,
    set_packed,
    set_returned,
    undo_issue,
)
from rentalars.projects.models import Project, ProjectStatus
from rentalars.projects.services import change_status, create_subproject, take_over_line, update_project
from rentalars.timetracking import services as time_services
from tests.helpers import (
    ALL_RIGHTS,
    NOW,
    RentalarsTestCase,
    add_line,
    at,
    clock,
    make_customer,
    make_internal_project,
    make_items,
    make_model,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    ready_for_invoices,
    record_time,
    set_clock,
)

D = Decimal

#: Words that must never appear as a key of an event: prices, costs, rates (API-012, AUT-019).
PRICE_WORDS = ("price", "rate", "amount", "cost", "total", "net", "gross", "discount")


class Receiver:
    """Stands in for ``webhooks.post``: notes every request and answers with the given status codes in turn.

    ``None`` plays a receiver that cannot be reached. The last status repeats.
    """

    def __init__(self, *statuses: int | None) -> None:
        self.statuses = list(statuses) or [200]
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    def __call__(self, url: str, body: bytes, headers: dict[str, str]) -> webhooks.Outcome:
        self.calls.append((url, body, headers))
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if status is None:
            return webhooks.Outcome(None, "Der Server ist nicht erreichbar.", duration_ms=3)
        error = "" if 200 <= status < 300 else f"Fehler {status}"
        return webhooks.Outcome(status, error, "danke" if not error else "kaputt", 12)

    @property
    def events(self) -> list[str]:
        return [headers["X-Rentalars-Event"] for _url, _body, headers in self.calls]


def make_hook(*events: str, active: bool = True, url: str = "https://erp.example.de/hook") -> tuple[Webhook, str]:
    """A webhook for the events; returns it with its secret."""
    return webhooks.create_webhook(url=url, events=list(events), is_active=active, description="ERP")


def keys_of(value: Any, prefix: str = "") -> set[str]:
    """All keys of a nested document, as dotted paths (lists are looked into)."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(prefix + key)
            found |= keys_of(inner, prefix + key + ".")
    elif isinstance(value, list):
        for inner in value:
            found |= keys_of(inner, prefix)
    return found


def keys_of_example(value: Any, prefix: str = "") -> set[str]:
    """Like :func:`keys_of`; a ``None`` in the example may stand for an object."""
    return keys_of(value, prefix)


class AddressAndModelTests(RentalarsTestCase):
    def test_internal_addresses_are_allowed(self) -> None:
        """The company's own systems are often internal: a name without a dot, an IP address, a port.

        NFA-071: an internal IP address only if the operator allows it (``[network] allow_internal``);
        a name is checked when a delivery is sent.
        """
        urls = (
            "http://erp:8080/hook",
            "http://192.168.1.20/rentalars",
            "https://[fd00::12]:8443/x",
            "http://localhost:5678/webhook/abc",
            "https://n8n.example.de/webhook/3f2b?x=1",
        )
        with self.settings(RENTALARS_NETWORK_ALLOW_INTERNAL=("192.168.1.0/24", "fd00::/8", "127.0.0.1")):
            for url in urls:
                validate_webhook_url(url)
        with self.settings(RENTALARS_NETWORK_ALLOW_INTERNAL=()):
            for url in urls[1:4]:
                with self.subTest(url=url), self.assertRaises(ValidationError):
                    validate_webhook_url(url)
            validate_webhook_url(urls[0])
            validate_webhook_url(urls[4])

    def test_other_addresses_are_refused(self) -> None:
        for url in (
            "ftp://erp/x",
            "erp/hook",
            "http://",
            "https://user:secret@erp/x",
            "http://erp/a b",
            "javascript:alert(1)",
            "http://erp:99999/x",
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_webhook_url(url)

    def test_events_must_be_known_and_at_least_one(self) -> None:
        for events in ([], ["ping"], ["project.deleted"]):
            with self.subTest(events=events), self.assertRaises(ValidationError) as caught:
                make_hook(*events)
            self.assertIn("events", caught.exception.message_dict)
        webhook, _secret = make_hook("packing.returned", "project.created", "project.created")
        self.assertEqual(webhook.events, ["project.created", "packing.returned"])

    def test_the_secret_is_stored_encrypted_and_never_logged(self) -> None:
        webhook, secret = make_hook("project.created")
        self.assertGreaterEqual(len(secret), 40)
        self.assertNotIn(secret, webhook.secret_encrypted)
        self.assertEqual(webhooks.secret_of(webhook), secret)
        self.assertEqual(webhook.secret_created_at, NOW)
        logged = json.dumps(list(AuditLogEntry.objects.values_list("changes", flat=True)))
        self.assertNotIn(webhook.secret_encrypted, logged)
        self.assertNotIn("secret_encrypted", logged)

    def test_a_new_secret_replaces_the_old_one_and_shows_in_the_change_log(self) -> None:
        webhook, old = make_hook("project.created")
        set_clock(NOW + datetime.timedelta(hours=1))
        new = webhooks.renew_secret(webhook)
        webhook.refresh_from_db()
        self.assertNotEqual(new, old)
        self.assertEqual(webhooks.secret_of(webhook), new)
        entry = AuditLogEntry.objects.filter(object_id=str(webhook.pk), action="updated").latest("pk")
        self.assertIn("secret_created_at", entry.changes)

    def test_the_full_export_leaves_webhooks_out(self) -> None:
        """The address may be a secret link, and the secret is one (IMP-006)."""
        exported = {model._meta.label_lower for model in export.exported_models()}
        self.assertNotIn("api.webhook", exported)
        self.assertNotIn("api.webhookdelivery", exported)
        self.assertIn("projects.project", exported)


class RecordingTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.webhook, _secret = make_hook("project.created", "project.status_changed")
        self.off, _secret = make_hook("project.created", "project.status_changed", active=False)
        self.other, _secret = make_hook("packing.issued")

    def deliveries(self, event: str) -> list[WebhookDelivery]:
        return list(WebhookDelivery.objects.filter(event=event).order_by("pk"))

    def test_a_status_change_is_noted_for_the_webhooks_that_want_it(self) -> None:
        project = make_project(status=ProjectStatus.OPTION)
        change_status(project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        [delivery] = self.deliveries("project.status_changed")
        self.assertEqual((delivery.webhook, delivery.status, delivery.attempts), (self.webhook, "pending", 0))
        self.assertEqual(delivery.next_attempt_at, NOW)
        self.assertEqual((delivery.data["old_status"], delivery.data["new_status"]), ("option", "confirmed"))
        block = delivery.data["project"]
        self.assertEqual((block["id"], block["number"], block["status"]), (project.pk, project.number, "confirmed"))
        self.assertEqual(block["customer"], {"id": project.customer_id, "number": project.customer.number})
        self.assertIsNone(block["parent_project"])
        self.assertEqual(block["start"], "2027-03-10T00:00:00+01:00")
        self.assertEqual(block["api_url"], f"{settings.RENTALARS_URL}/api/v1/projects/{project.pk}")

    def test_a_new_project_is_an_event_and_its_first_status_is_no_change(self) -> None:
        project = make_project()
        [delivery] = self.deliveries("project.created")
        self.assertEqual(delivery.data["project"]["id"], project.pk)
        self.assertEqual(self.deliveries("project.status_changed"), [])

    def test_saving_without_a_new_status_is_no_event(self) -> None:
        project = make_project()
        update_project(project, name="Stadtfest 2027")
        Project.objects.get(pk=project.pk).save()
        self.assertEqual(self.deliveries("project.status_changed"), [])

    def test_saving_other_fields_only_is_no_status_change(self) -> None:
        project = make_project()
        project.status = ProjectStatus.OPTION  # changed, but not saved
        project.name = "Stadtfest 2027"
        project.save(update_fields=["name"])
        self.assertEqual(self.deliveries("project.status_changed"), [])

    def test_a_subproject_names_its_main_project_and_an_internal_project_no_customer(self) -> None:
        main = make_project("Festival")
        part = make_project("Festival – Bühne 2", parent=main)
        internal = make_internal_project()
        data = {
            delivery.data["project"]["id"]: delivery.data["project"] for delivery in self.deliveries("project.created")
        }
        self.assertEqual(data[part.pk]["parent_project"], {"id": main.pk, "number": main.number})
        self.assertIsNone(data[internal.pk]["customer"])
        self.assertTrue(data[internal.pk]["is_internal"])

    def test_a_change_that_is_rolled_back_leaves_nothing_to_send(self) -> None:
        project = make_project(status=ProjectStatus.OPTION)
        with self.assertRaises(RuntimeError), transaction.atomic():
            change_status(project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
            self.assertEqual(len(self.deliveries("project.status_changed")), 1)
            raise RuntimeError("the change fails afterwards")
        self.assertEqual(self.deliveries("project.status_changed"), [])

    def test_a_problem_while_noting_does_not_stop_the_change(self) -> None:
        project = make_project(status=ProjectStatus.OPTION)
        with (
            mock.patch.dict(
                webhook_events.EVENTS,
                {
                    "project.status_changed": webhook_events.EventType(
                        "project.status_changed", "x", "x", mock.Mock(side_effect=RuntimeError("bug"))
                    )
                },
            ),
            self.assertLogs("rentalars.api.webhooks", "ERROR"),
        ):
            change_status(project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.assertEqual(Project.objects.get(pk=project.pk).status, "confirmed")
        self.assertEqual(self.deliveries("project.status_changed"), [])

    def test_without_webhooks_one_small_query(self) -> None:
        Webhook.objects.all().delete()
        project = make_project(status=ProjectStatus.OPTION)
        project.status = ProjectStatus.CONFIRMED
        with self.assertNumQueries(1):
            self.assertEqual(
                webhooks.record("project.status_changed", project, old_status="option", new_status="confirmed"), 0
            )


class PackingEventTests(RentalarsTestCase):
    """PCK-014 ff.: material out and back."""

    def setUp(self) -> None:
        super().setUp()
        self.webhook, _secret = make_hook(
            "project.status_changed", "packing.issued", "packing.issue_undone", "packing.returned"
        )
        self.cable = make_stock("K-001", 10)
        self.tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=D("14.90"))
        make_items(make_model("Gaffa schwarz", self.tape, bulk=True), 1, quantity=40)
        self.project = make_project()
        self.cable_line = add_line(self.project, self.cable, 4).line
        add_line(self.project, self.tape, 3)
        self.packlist = get_packlist(self.project)

    def events(self) -> list[tuple[str, dict[str, Any]]]:
        return [(delivery.event, delivery.data) for delivery in WebhookDelivery.objects.order_by("pk")]

    def test_issue_and_return_are_events_with_counts(self) -> None:
        issue(self.packlist)
        (status_event, status_data), (event, data) = self.events()
        self.assertEqual(
            (status_event, status_data["old_status"], status_data["new_status"]),
            ("project.status_changed", "confirmed", "out"),
        )
        self.assertEqual(event, "packing.issued")
        self.assertTrue(data["complete"])
        self.assertEqual((data["packlist"]["id"], data["packlist"]["status"]), (self.packlist.pk, "issued"))
        self.assertEqual(data["project"]["status"], "out")
        self.assertEqual(
            data["packlist"]["counts"],
            {"rows": 2, "issued": "7.00", "returned": "0.00", "sold": "3.00", "outstanding": "4.00"},
        )

        set_returned(self.packlist, self.cable_line.pk, self.cable.pk, D("3"))
        event, data = self.events()[-1]
        self.assertEqual((event, data["complete"]), ("packing.returned", False))
        self.assertEqual(
            (data["packlist"]["counts"]["returned"], data["packlist"]["counts"]["outstanding"]), ("3.00", "1.00")
        )

        count = len(self.events())
        set_returned(self.packlist, self.cable_line.pk, self.cable.pk, D("2"))  # a correction downwards
        self.assertEqual(len(self.events()), count)

        return_all(self.packlist)
        event, data = self.events()[-1]
        self.assertEqual(
            (event, data["complete"], data["packlist"]["counts"]["outstanding"]), ("packing.returned", False, "0.00")
        )
        count = len(self.events())
        return_all(self.packlist)  # nothing new came back
        self.assertEqual(len(self.events()), count)

        complete_return(self.packlist)
        (status_event, status_data), (event, data) = self.events()[-2:]
        self.assertEqual((status_event, status_data["new_status"]), ("project.status_changed", "returned"))
        self.assertEqual((event, data["complete"], data["packlist"]["status"]), ("packing.returned", True, "returned"))
        self.assertIsNotNone(data["packlist"]["returned_at"])

    def test_issuing_what_is_ticked_is_not_complete(self) -> None:
        set_packed(self.packlist, self.cable_line.pk, self.cable.pk, D("2"))
        issue(self.packlist, only_packed=True)
        event, data = self.events()[-1]
        self.assertEqual(
            (event, data["complete"], data["packlist"]["status"]), ("packing.issued", False, "partly_issued")
        )
        self.assertEqual(data["packlist"]["counts"]["issued"], "2.00")

    def test_taking_back_an_issue_is_an_event(self) -> None:
        project = make_project("Messe")  # without sold material: that cannot be taken back
        add_line(project, self.cable, 2)
        packlist = get_packlist(project)
        issue(packlist)
        undo_issue(packlist)
        (status_event, status_data), (event, data) = self.events()[-2:]
        self.assertEqual((status_event, status_data["new_status"]), ("project.status_changed", "confirmed"))
        self.assertEqual((event, data["packlist"]["status"]), ("packing.issue_undone", "packed"))
        self.assertEqual(data["packlist"]["counts"]["issued"], "0.00")
        self.assertNotIn("complete", data)


class TimeEntryEventTests(RentalarsTestCase):
    """ZEI-012: approving and taking back an approval."""

    def setUp(self) -> None:
        super().setUp()
        self.webhook, _secret = make_hook("time_entry.approved", "time_entry.approval_withdrawn")
        self.project = make_project()
        self.person = make_person("Carla Crew", rates={"Lichttechnik": "30.00"})
        self.first = record_time(self.person, self.project, "Lichttechnik", at(10, 8), at(10, 18), submit=True)
        self.second = record_time(self.person, self.project, "Lichttechnik", at(11, 8), at(11, 12), submit=True)

    def test_one_event_per_approved_entry_and_one_for_taking_it_back(self) -> None:
        set_clock(at(28, 18))
        approved = time_services.approve_entries([self.first, self.second], rights=ALL_RIGHTS, user=None)
        self.assertEqual(approved, 2)
        deliveries = list(WebhookDelivery.objects.filter(event="time_entry.approved").order_by("pk"))
        self.assertEqual(
            [delivery.data["time_entry"]["id"] for delivery in deliveries], [self.first.pk, self.second.pk]
        )
        entry = deliveries[0].data["time_entry"]
        self.assertEqual(entry["person"], {"id": self.person.pk, "name": self.person.name})
        self.assertEqual(
            (entry["hours"], entry["status"], entry["break_minutes"]), (str(self.first.hours), "approved", 0)
        )
        self.assertNotIn("hourly_rate", entry)
        self.assertNotIn("30.00", json.dumps(deliveries[0].data))
        self.assertEqual(deliveries[0].data["project"]["id"], self.project.pk)

        self.first.refresh_from_db()
        time_services.take_back_approval(self.first, rights=ALL_RIGHTS, user=None)
        [withdrawn] = WebhookDelivery.objects.filter(event="time_entry.approval_withdrawn")
        self.assertEqual(
            (withdrawn.data["time_entry"]["status"], withdrawn.data["time_entry"]["decided_at"]), ("submitted", None)
        )

    def test_entries_that_were_not_waiting_are_no_event(self) -> None:
        set_clock(at(28, 18))
        time_services.approve_entries([self.first], rights=ALL_RIGHTS, user=None)
        self.first.refresh_from_db()
        time_services.approve_entries([self.first], rights=ALL_RIGHTS, user=None)
        self.assertEqual(WebhookDelivery.objects.filter(event="time_entry.approved").count(), 1)


class DocumentEventTests(RentalarsTestCase):
    """DOK-003 ff.: a stored document – without its amounts."""

    def test_an_invoice_and_its_cancellation(self) -> None:
        make_hook("document.created")
        project = make_project(customer=ready_for_invoices())
        add_line(project, make_stock("L-010", 6, "PAR 64", price="20.00"), 4)
        invoice = documents.create_document(project, DocumentKind.INVOICE)
        cancellation = documents.cancel_invoice(invoice)
        first, second = WebhookDelivery.objects.filter(event="document.created").order_by("pk")
        self.assertEqual(
            {key: first.data["document"][key] for key in ("id", "kind", "number", "cancels")},
            {"id": invoice.pk, "kind": "invoice", "number": invoice.number, "cancels": None},
        )
        self.assertEqual(first.data["document"]["due_on"], invoice.due_on.isoformat())
        self.assertEqual(
            first.data["document"]["pdf_url"], f"{settings.RENTALARS_URL}/api/v1/documents/{invoice.pk}/pdf"
        )
        self.assertEqual(second.data["document"]["kind"], "cancellation")
        self.assertEqual(second.data["document"]["cancels"], {"id": invoice.pk, "number": invoice.number})
        self.assertEqual(second.data["document"]["id"], cancellation.pk)
        self.assertEqual(first.data["project"]["id"], project.pk)


class PayloadRuleTests(RentalarsTestCase):
    """What every event may contain, and that the documented examples match what is sent."""

    def setUp(self) -> None:
        super().setUp()
        # PRJ-060: spots that go from one stage straight on to the next. Prepared before the webhook exists:
        # the events of subprojects name their whole project, which the examples of the other events do not show.
        whole = make_project("Festival", start=at(9, 12), end=at(14, 18), customer=make_customer("Festival GmbH"))
        stage_1 = create_subproject(whole, name="Bühne 1", start=at(10, 8), end=at(12, 8))
        stage_2 = create_subproject(whole, name="Bühne 2", start=at(12, 12), end=at(14, 12))
        spot = make_stock("L-100", 2)
        source = add_line(stage_1, spot, 2).line
        taking = take_over_line(source, stage_2, rights=ALL_RIGHTS).line
        add_line(stage_2, make_stock("K-002", 2), 1)
        issue(get_packlist(stage_1))
        issue(get_packlist(stage_2))
        make_hook(*webhook_events.SUBSCRIBABLE)
        subprojects.undo_handover(subprojects.hand_over(get_packlist(stage_2), taking.pk, spot.pk))
        project = make_project(customer=ready_for_invoices(), status=ProjectStatus.OPTION)
        change_status(project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        cable = make_stock("K-001", 10, price="12.50")
        line = add_line(project, cable, 4, unit_price=D("12.50")).line
        packlist = get_packlist(project)
        issue(packlist)
        undo_issue(packlist)
        issue(packlist)
        set_returned(packlist, line.pk, cable.pk, D("1"))
        return_all(packlist)
        complete_return(packlist)
        person = make_person("Carla Crew", rates={"Lichttechnik": "30.00"})
        entry = record_time(person, project, "Lichttechnik", at(10, 8), at(10, 18), submit=True)
        set_clock(at(28, 18))
        time_services.approve_entries([entry], rights=ALL_RIGHTS, user=None)
        entry.refresh_from_db()
        time_services.take_back_approval(entry, rights=ALL_RIGHTS, user=None)
        documents.create_document(project, DocumentKind.INVOICE)
        self.deliveries = list(WebhookDelivery.objects.order_by("pk"))

    def test_every_event_was_produced(self) -> None:
        self.assertEqual({delivery.event for delivery in self.deliveries}, set(webhook_events.SUBSCRIBABLE))

    def test_no_event_carries_prices_costs_or_rates(self) -> None:
        for delivery in self.deliveries:
            for key in keys_of(delivery.data):
                last = key.rsplit(".", 1)[-1]
                with self.subTest(event=delivery.event, key=key):
                    self.assertFalse(any(word in last for word in PRICE_WORDS))
            self.assertNotIn("12.50", json.dumps(delivery.data))

    def test_the_documented_example_of_every_event_has_the_keys_that_are_sent(self) -> None:
        for delivery in self.deliveries:
            with self.subTest(event=delivery.event):
                self.assertEqual(keys_of(delivery.data), keys_of_example(webhook_events.EVENTS[delivery.event].example))


class DeliveryTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.webhook, self.secret = make_hook("project.status_changed")
        self.project = make_project(status=ProjectStatus.OPTION)
        change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.delivery = WebhookDelivery.objects.get()

    def run_with(self, receiver: Receiver, **options: Any) -> webhooks.RunResult:
        with mock.patch.object(webhooks, "post", receiver):
            return webhooks.run_due(**options)

    def test_a_due_delivery_is_signed_and_sent(self) -> None:
        receiver = Receiver(200)
        result = self.run_with(receiver)
        self.assertEqual((result.delivered, result.failed), (1, 0))
        [(url, body, headers)] = receiver.calls
        self.assertEqual(url, "https://erp.example.de/hook")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["X-Rentalars-Event"], "project.status_changed")
        self.assertEqual(headers["X-Rentalars-Delivery"], str(self.delivery.uuid))
        self.assertTrue(headers["User-Agent"].startswith("Rentalars/"))
        expected = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-Rentalars-Signature"], f"sha256={expected}")
        document = json.loads(body)
        self.assertEqual(
            (document["version"], document["id"], document["event"], document["timestamp"]),
            (1, str(self.delivery.uuid), "project.status_changed", "2027-03-01T08:00:00+01:00"),
        )
        self.assertEqual(document["data"]["new_status"], "confirmed")
        self.delivery.refresh_from_db()
        self.assertEqual((self.delivery.status, self.delivery.attempts), ("delivered", 1))
        self.assertEqual((self.delivery.last_status_code, self.delivery.last_response), (200, "danke"))
        self.assertEqual((self.delivery.delivered_at, self.delivery.next_attempt_at), (NOW, None))
        self.assertEqual(self.run_with(receiver).delivered, 0)  # nothing left

    def test_a_failed_delivery_is_tried_again_after_growing_pauses_and_then_given_up(self) -> None:
        receiver = Receiver(500)
        pauses = []
        for _attempt in range(webhooks.MAX_ATTEMPTS):
            self.assertEqual(self.run_with(receiver).failed, 1)
            self.delivery.refresh_from_db()
            if self.delivery.next_attempt_at is not None:
                pauses.append(self.delivery.next_attempt_at - clock())
                self.assertEqual(self.run_with(receiver).failed, 0)  # not due yet
                set_clock(self.delivery.next_attempt_at)
        self.assertEqual(
            pauses,
            [
                datetime.timedelta(minutes=1),
                datetime.timedelta(minutes=5),
                datetime.timedelta(minutes=30),
                datetime.timedelta(hours=2),
                datetime.timedelta(hours=12),
            ],
        )
        self.assertEqual((self.delivery.status, self.delivery.attempts), ("failed", 6))
        self.assertEqual((self.delivery.last_status_code, self.delivery.last_error), (500, "Fehler 500"))
        self.assertEqual(len({body for _url, body, _headers in receiver.calls}), 1, "the same body every time")
        self.webhook.refresh_from_db()
        self.assertEqual((self.webhook.failures_in_a_row, self.webhook.is_active), (1, True))

    def test_a_success_starts_the_count_of_failures_afresh(self) -> None:
        Webhook.objects.filter(pk=self.webhook.pk).update(failures_in_a_row=4)
        self.run_with(Receiver(204))
        self.webhook.refresh_from_db()
        self.assertEqual(self.webhook.failures_in_a_row, 0)

    def test_after_ten_deliveries_that_failed_for_good_the_webhook_is_switched_off(self) -> None:
        admin = make_user("admin", superuser=True)
        Webhook.objects.filter(pk=self.webhook.pk).update(failures_in_a_row=webhooks.SWITCH_OFF_AFTER - 1)
        WebhookDelivery.objects.filter(pk=self.delivery.pk).update(attempts=webhooks.MAX_ATTEMPTS - 1)
        with mock.patch("rentalars.notifications.services._send_email"):
            self.run_with(Receiver(None))
        self.webhook.refresh_from_db()
        self.assertFalse(self.webhook.is_active)
        self.assertEqual((self.webhook.switched_off_at, self.webhook.failures_in_a_row), (NOW, 10))
        [notification] = Notification.objects.filter(user=admin)
        self.assertEqual(notification.kind, Kind.SYSTEM_ERROR)
        self.assertEqual(notification.title, "Webhook abgeschaltet: ERP")
        self.assertIn("Der Server ist nicht erreichbar.", notification.body)
        self.assertEqual(notification.url, f"/administration/webhooks/{self.webhook.pk}/")
        entry = AuditLogEntry.objects.filter(object_id=str(self.webhook.pk), action="updated").latest("pk")
        self.assertEqual((entry.changes["is_active"], entry.actor_label), ([True, False], "system"))

        # Off, nothing more is noted or sent; switched on again, it starts afresh.
        change_status(self.project, ProjectStatus.OPTION, rights=ALL_RIGHTS)
        self.assertEqual(WebhookDelivery.objects.count(), 1)
        webhooks.update_webhook(self.webhook, is_active=True)
        self.assertEqual((self.webhook.failures_in_a_row, self.webhook.switched_off_at), (0, None))

    def test_deliveries_of_a_webhook_that_is_off_wait_until_it_is_on_again(self) -> None:
        webhooks.update_webhook(self.webhook, is_active=False)
        receiver = Receiver(200)
        self.assertEqual(self.run_with(receiver).delivered, 0)
        webhooks.update_webhook(self.webhook, is_active=True)
        self.assertEqual(self.run_with(receiver).delivered, 1)

    def test_a_failing_receiver_gets_one_attempt_per_run(self) -> None:
        good, _secret = make_hook("project.status_changed", url="https://good.example.de/")
        for status in (ProjectStatus.OPTION, ProjectStatus.CONFIRMED):
            change_status(self.project, status, rights=ALL_RIGHTS)

        def answer(url: str, body: bytes, headers: dict[str, str]) -> webhooks.Outcome:
            calls.append(url)
            return webhooks.Outcome(200 if "good" in url else 503, "" if "good" in url else "Fehler 503")

        calls: list[str] = []
        with mock.patch.object(webhooks, "post", answer):
            result = webhooks.run_due()
        self.assertEqual(calls.count("https://erp.example.de/hook"), 1)
        self.assertEqual(calls.count("https://good.example.de/"), 2)
        self.assertEqual((result.delivered, result.failed), (2, 1))
        self.assertEqual(WebhookDelivery.objects.filter(webhook=good, status="delivered").count(), 2)

    def test_the_run_ends_when_its_time_is_up(self) -> None:
        receiver = Receiver(200)
        self.assertEqual(self.run_with(receiver, budget_seconds=-1).delivered, 0)
        self.assertEqual(receiver.calls, [])

    def test_a_delivery_taken_by_another_run_is_not_sent_twice(self) -> None:
        stale = WebhookDelivery.objects.get(pk=self.delivery.pk)
        self.assertTrue(webhooks._claim(self.delivery))
        self.assertFalse(webhooks._claim(stale))
        self.assertEqual(
            WebhookDelivery.objects.get(pk=self.delivery.pk).next_attempt_at, NOW + datetime.timedelta(minutes=10)
        )

    def test_an_unreadable_secret_is_a_failure_that_says_what_to_do(self) -> None:
        Webhook.objects.filter(pk=self.webhook.pk).update(secret_encrypted="gAAAAA-not-a-secret")
        receiver = Receiver(200)
        self.assertEqual(self.run_with(receiver).failed, 1)
        self.assertEqual(receiver.calls, [])
        self.delivery.refresh_from_db()
        self.assertIn("Geheimnis", self.delivery.last_error)
        self.assertEqual(self.delivery.status, "pending")

    def test_a_mistake_while_sending_is_noted_and_the_delivery_tried_again(self) -> None:
        with self.assertLogs("rentalars.api.webhooks", "ERROR"):
            self.run_with(mock.Mock(side_effect=RuntimeError("bug")))
        self.delivery.refresh_from_db()
        self.assertEqual((self.delivery.status, self.delivery.attempts), ("pending", 1))
        self.assertIn("Interner Fehler", self.delivery.last_error)

    def test_a_webhook_deleted_while_its_delivery_is_on_the_way(self) -> None:
        def answer(url: str, body: bytes, headers: dict[str, str]) -> webhooks.Outcome:
            Webhook.objects.all().delete()
            return webhooks.Outcome(500, "Fehler 500")

        WebhookDelivery.objects.filter(pk=self.delivery.pk).update(attempts=webhooks.MAX_ATTEMPTS - 1)
        with mock.patch.object(webhooks, "post", answer):
            result = webhooks.run_due()
        self.assertEqual((result.delivered, result.failed), (0, 1))
        self.assertFalse(WebhookDelivery.objects.exists())

    def test_the_run_never_raises(self) -> None:
        with (
            mock.patch.object(WebhookDelivery.objects, "filter", side_effect=RuntimeError("database gone")),
            self.assertLogs("rentalars.api.webhooks", "ERROR"),
        ):
            result = webhooks.run_due()
        self.assertEqual((result.delivered, result.failed), (0, 0))

    def test_the_timer_of_every_minute_delivers(self) -> None:
        receiver = Receiver(200)
        with mock.patch.object(webhooks, "post", receiver):
            call_command("run_jobs", verbosity=0)
        self.assertEqual(receiver.events, ["project.status_changed"])
        with (
            mock.patch("rentalars.api.webhooks.run_due", side_effect=RuntimeError("bug")),
            self.assertLogs("rentalars.core.management.commands.run_jobs", "ERROR"),
        ):
            call_command("run_jobs", verbosity=0)


class ByHandTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.webhook, self.secret = make_hook("project.created")

    def test_a_test_is_sent_at_once_and_tried_only_once(self) -> None:
        receiver = Receiver(200)
        with mock.patch.object(webhooks, "post", receiver):
            delivery = webhooks.send_test(self.webhook)
        self.assertEqual((delivery.event, delivery.status, delivery.attempts), ("ping", "delivered", 1))
        self.assertEqual(delivery.data["webhook"], {"id": self.webhook.pk, "events": ["project.created"]})
        self.assertEqual(receiver.events, ["ping"])

        with mock.patch.object(webhooks, "post", Receiver(404)):
            failed = webhooks.send_test(self.webhook)
        self.assertEqual((failed.status, failed.next_attempt_at, failed.last_status_code), ("failed", None, 404))
        self.webhook.refresh_from_db()
        self.assertEqual(self.webhook.failures_in_a_row, 0, "a test does not count towards switching off")

    def test_a_webhook_that_is_off_can_be_tested(self) -> None:
        webhooks.update_webhook(self.webhook, is_active=False)
        with mock.patch.object(webhooks, "post", Receiver(200)):
            self.assertEqual(webhooks.send_test(self.webhook).status, "delivered")

    def test_a_failed_delivery_is_sent_again_with_the_same_id(self) -> None:
        make_project()
        delivery = WebhookDelivery.objects.get(event="project.created")
        WebhookDelivery.objects.filter(pk=delivery.pk).update(
            status=DeliveryStatus.FAILED, attempts=6, next_attempt_at=None
        )
        delivery.refresh_from_db()
        receiver = Receiver(200)
        with mock.patch.object(webhooks, "post", receiver):
            webhooks.redeliver(delivery)
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempts), ("delivered", 7))
        self.assertEqual(receiver.calls[0][2]["X-Rentalars-Delivery"], str(delivery.uuid))
        with self.assertRaises(ValidationError):
            webhooks.redeliver(delivery)  # it arrived


class RetentionTests(RentalarsTestCase):
    def test_deliveries_are_kept_for_thirty_days(self) -> None:
        webhook, _secret = make_hook("project.created")
        old = WebhookDelivery.objects.create(
            webhook=webhook, event="ping", created_at=NOW - datetime.timedelta(days=31)
        )
        young = WebhookDelivery.objects.create(
            webhook=webhook, event="ping", created_at=NOW - datetime.timedelta(days=29)
        )
        output = StringIO()
        call_command("run_daily_maintenance", stdout=output)
        self.assertIn("Deleted 1 webhook deliveries past their retention (API-012).", output.getvalue())
        self.assertFalse(WebhookDelivery.objects.filter(pk=old.pk).exists())
        self.assertTrue(WebhookDelivery.objects.filter(pk=young.pk).exists())


# --- The HTTP client, against a server on this machine -----------------------------------------------------


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        """A client that hung up (the timeout test) is no error worth printing."""


class _Handler(BaseHTTPRequestHandler):
    server: Any

    def log_message(self, *args: Any) -> None:
        """Quiet."""

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.server.requests.append((self.path, dict(self.headers), self.rfile.read(length)))
        if self.path == "/slow":
            time.sleep(1.5)
        status, body, extra = {
            "/ok": (200, b"danke", {}),
            "/redirect": (302, b"", {"Location": "/ok"}),
            "/error": (500, ("x" * 5000).encode(), {}),
            "/slow": (200, b"spaet", {}),
        }.get(self.path, (404, b"unbekannt", {}))
        self.send_response(status)
        for name, value in extra.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class HttpClientTests(SimpleTestCase):
    """The rules of ``webhooks.post`` (API-012): no redirections, a limited answer, a time limit."""

    def setUp(self) -> None:
        self.server = _QuietServer(("127.0.0.1", 0), _Handler)
        self.server.requests = []
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def test_the_body_and_the_headers_arrive(self) -> None:
        outcome = webhooks.post(
            self.base + "/ok", b'{"a":1}', {"Content-Type": "application/json", "X-Rentalars-Event": "ping"}
        )
        self.assertTrue(outcome.ok)
        self.assertEqual((outcome.status_code, outcome.error, outcome.response), (200, "", "danke"))
        [(path, headers, body)] = self.server.requests
        self.assertEqual((path, body, headers["X-Rentalars-Event"]), ("/ok", b'{"a":1}', "ping"))

    def test_a_redirection_is_not_followed(self) -> None:
        outcome = webhooks.post(self.base + "/redirect", b"{}", {})
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.status_code, 302)
        self.assertIn("leitet", outcome.error)
        self.assertEqual([path for path, _headers, _body in self.server.requests], ["/redirect"])

    def test_an_error_keeps_only_the_beginning_of_the_answer(self) -> None:
        outcome = webhooks.post(self.base + "/error", b"{}", {})
        self.assertEqual(outcome.status_code, 500)
        self.assertEqual(outcome.error, "Das empfangende System antwortete mit Fehler 500.")
        self.assertEqual(len(outcome.response), webhooks.RESPONSE_EXCERPT)

    def test_no_answer_in_time(self) -> None:
        with mock.patch.object(webhooks, "TIMEOUT", 0.3):
            outcome = webhooks.post(self.base + "/slow", b"{}", {})
        self.assertIsNone(outcome.status_code)
        self.assertIn("Keine Antwort", outcome.error)

    def test_a_server_that_does_not_listen(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        outcome = webhooks.post(f"http://127.0.0.1:{port}/", b"{}", {})
        self.assertIsNone(outcome.status_code)
        self.assertEqual(outcome.error, "Die Verbindung wurde abgelehnt.")

    def test_only_http_addresses_are_asked(self) -> None:
        outcome = webhooks.post("file:///etc/passwd", b"{}", {})
        self.assertIsNone(outcome.status_code)
        self.assertTrue(outcome.error)
        self.assertEqual(self.server.requests, [])
