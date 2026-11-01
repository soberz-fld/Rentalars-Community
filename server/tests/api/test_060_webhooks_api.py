# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the webhooks (API-012).

Everything the settings pages offer goes through the API as well: list,
create (with the secret once), change, delete, the events with examples, the
deliveries, a test, the secret and a new one, and sending a failed delivery
again. The receiver is a stand-in for ``webhooks.post``.
"""

from __future__ import annotations

from unittest import mock

from rentalars.accounts.models import Role
from rentalars.api import webhook_events, webhooks
from rentalars.api.models import DeliveryStatus, Webhook, WebhookDelivery
from rentalars.projects.models import ProjectStatus
from rentalars.projects.services import change_status
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, make_project, make_user
from tests.unit.test_060_webhooks import Receiver, make_hook


class WebhookApiTests(ApiTestCase):
    def test_create_read_change_delete(self) -> None:
        created = self.admin.post(
            f"{API}/webhooks",
            {
                "url": "http://erp:8080/rentalars",
                "description": "ERP",
                "events": ["packing.issued", "project.status_changed"],
            },
        )
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        webhook = Webhook.objects.get(pk=body["id"])
        self.assertEqual(body["secret"], webhooks.secret_of(webhook))
        self.assertEqual(body["events"], ["project.status_changed", "packing.issued"])
        self.assertEqual(
            (body["is_active"], body["created_by"], body["failures_in_a_row"]), (True, self.admin_user.pk, 0)
        )

        listed = self.admin.get(f"{API}/webhooks").json()
        self.assertEqual([row["id"] for row in listed["results"]], [webhook.pk])
        read = self.admin.get(f"{API}/webhooks/{webhook.pk}").json()
        self.assertNotIn("secret", read)
        self.assertNotIn(body["secret"], str(read))

        patched = self.admin.patch(f"{API}/webhooks/{webhook.pk}", {"is_active": False})
        self.assertEqual((patched.status_code, patched.json()["is_active"]), (200, False))
        replaced = self.admin.put(
            f"{API}/webhooks/{webhook.pk}",
            {
                "url": "https://erp.example.de/hook",
                "description": "",
                "events": ["time_entry.approved"],
                "is_active": True,
            },
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        webhook.refresh_from_db()
        self.assertEqual(
            (webhook.url, webhook.events, webhook.is_active),
            ("https://erp.example.de/hook", ["time_entry.approved"], True),
        )

        self.assertEqual(self.admin.delete(f"{API}/webhooks/{webhook.pk}").status_code, 204)
        self.assertFalse(Webhook.objects.exists())

    def test_wrong_addresses_and_events_in_the_uniform_error_format(self) -> None:
        response = self.admin.post(f"{API}/webhooks", {"url": "ftp://erp/x", "events": ["project.created"]})
        self.assert_error(response, 400, "validation_error", "url")
        response = self.admin.post(f"{API}/webhooks", {"url": "https://erp/x", "events": ["project.deleted"]})
        self.assert_error(response, 400, "validation_error", "events.0")
        response = self.admin.post(f"{API}/webhooks", {"url": "https://erp/x", "events": []})
        self.assert_error(response, 400, "validation_error", "events")
        self.assertFalse(Webhook.objects.exists())

    def test_the_events_with_their_examples(self) -> None:
        events = self.admin.get(f"{API}/webhooks/events").json()
        self.assertEqual([row["event"] for row in events], list(webhook_events.EVENTS))
        status_changed = next(row for row in events if row["event"] == "project.status_changed")
        self.assertEqual(status_changed["label"], "Projektstatus geändert")
        self.assertEqual(set(status_changed["example"]), {"project", "old_status", "new_status"})

    def test_the_secret_and_a_new_one(self) -> None:
        webhook, secret = make_hook("project.created")
        self.assertEqual(self.admin.get(f"{API}/webhooks/{webhook.pk}/secret").json(), {"secret": secret})
        renewed = self.admin.post(f"{API}/webhooks/{webhook.pk}/secret").json()["secret"]
        self.assertNotEqual(renewed, secret)
        webhook.refresh_from_db()
        self.assertEqual(webhooks.secret_of(webhook), renewed)
        Webhook.objects.filter(pk=webhook.pk).update(secret_encrypted="gAAAAA-kaputt")
        self.assert_error(self.admin.get(f"{API}/webhooks/{webhook.pk}/secret"), 409, "secret_unreadable")

    def test_test_deliveries_and_sending_again(self) -> None:
        webhook, _secret = make_hook("project.status_changed")
        with mock.patch.object(webhooks, "post", Receiver(200)):
            tested = self.admin.post(f"{API}/webhooks/{webhook.pk}/test")
        self.assertEqual(tested.status_code, 201, tested.content)
        ping = tested.json()
        self.assertEqual(
            (ping["event"], ping["status"], ping["attempts"], ping["last_status_code"]), ("ping", "delivered", 1, 200)
        )
        self.assertEqual(ping["payload"]["id"], ping["delivery_id"])
        self.assertEqual(ping["payload"]["data"]["webhook"]["id"], webhook.pk)

        project = make_project(status=ProjectStatus.OPTION)
        change_status(project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        delivery = WebhookDelivery.objects.get(event="project.status_changed")
        listed = self.admin.get(f"{API}/webhooks/{webhook.pk}/deliveries").json()
        self.assertEqual([row["event"] for row in listed["results"]], ["project.status_changed", "ping"])
        waiting = self.admin.get(f"{API}/webhooks/{webhook.pk}/deliveries", {"status": "pending"}).json()["results"]
        self.assertEqual([row["id"] for row in waiting], [delivery.pk])
        self.assertEqual(waiting[0]["payload"]["data"]["new_status"], "confirmed")
        self.assertEqual(waiting[0]["payload"]["version"], 1)
        only_pings = self.admin.get(f"{API}/webhooks/{webhook.pk}/deliveries", {"event": "ping"}).json()["results"]
        self.assertEqual([row["event"] for row in only_pings], ["ping"])

        redeliver = f"{API}/webhooks/{webhook.pk}/deliveries/{delivery.pk}/redeliver"
        self.assert_error(self.admin.post(redeliver), 400, "validation_error")  # still being tried
        WebhookDelivery.objects.filter(pk=delivery.pk).update(
            status=DeliveryStatus.FAILED, attempts=6, next_attempt_at=None
        )
        with mock.patch.object(webhooks, "post", Receiver(500)):
            again = self.admin.post(redeliver)
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(
            (again.json()["status"], again.json()["attempts"], again.json()["last_status_code"]), ("failed", 7, 500)
        )
        self.assertEqual(again.json()["delivery_id"], str(delivery.uuid))
        other, _secret = make_hook("project.created")
        self.assert_error(
            self.admin.post(f"{API}/webhooks/{other.pk}/deliveries/{delivery.pk}/redeliver"), 404, "not_found"
        )


class WebhookRightsApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.webhook, self.secret = make_hook("project.created")
        role = Role.objects.create(name="Einstellungen lesen", module_levels={"administration": 1})
        self.reader = self.client_of(make_user("rita", roles=(role.name,)))

    def test_reading_is_not_seeing_the_secret(self) -> None:
        self.assertEqual(self.reader.get(f"{API}/webhooks").status_code, 200)
        self.assertEqual(self.reader.get(f"{API}/webhooks/{self.webhook.pk}/deliveries").status_code, 200)
        self.assert_error(self.reader.get(f"{API}/webhooks/{self.webhook.pk}/secret"), 403, "permission_denied")
        self.assert_error(self.reader.post(f"{API}/webhooks/{self.webhook.pk}/test"), 403, "permission_denied")
        self.assert_error(self.reader.delete(f"{API}/webhooks/{self.webhook.pk}"), 403, "permission_denied")

    def test_without_the_settings_nothing(self) -> None:
        crew = self.client_for("carla", "Crew")
        self.assert_error(crew.get(f"{API}/webhooks"), 403, "permission_denied")
        self.assert_error(crew.get(f"{API}/webhooks/events"), 403, "permission_denied")
