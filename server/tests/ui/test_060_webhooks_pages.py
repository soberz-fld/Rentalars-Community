# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of the webhooks in the settings (API-012).

The list, creating and changing a webhook, its secret (shown once, later on
request, or replaced), "Send test", the deliveries with "Send again", and
who may do what. The receiver is a stand-in for ``webhooks.post``.
"""

from __future__ import annotations

from unittest import mock

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.api import webhooks
from rentalars.api.models import DeliveryStatus, Webhook, WebhookDelivery
from rentalars.projects.models import ProjectStatus
from rentalars.projects.services import change_status
from tests.helpers import ALL_RIGHTS, make_project, make_user
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_060_webhooks import Receiver, make_hook


def settings_user(username: str, level: int) -> object:
    """A user with this level in the settings: 1 read, 2 change, 3 delete."""
    role = Role.objects.create(name=f"Einstellungen {level}", module_levels={"administration": level})
    return make_user(username, roles=(role.name,))


class WebhookListTests(UiTestCase):
    def test_the_settings_lead_to_the_webhooks(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(f'href="{reverse("webhooks:list")}">Webhooks</a>', page)

    def test_an_empty_list_explains_what_a_webhook_is(self) -> None:
        page = self.assert_ok(self.client.get(reverse("webhooks:list")))
        self.assertIn("Noch keine Webhooks.", page)
        self.assertIn(reverse("webhooks:create"), page)

    def test_the_list_shows_state_and_deliveries(self) -> None:
        hook, _secret = make_hook("project.status_changed")
        off, _secret = make_hook("project.created", active=False, url="http://n8n:5678/webhook/x")
        Webhook.objects.filter(pk=off.pk).update(switched_off_at=hook.created_at)
        WebhookDelivery.objects.create(webhook=hook, event="ping", status=DeliveryStatus.FAILED)
        WebhookDelivery.objects.create(webhook=hook, event="ping")
        page = self.assert_ok(self.client.get(reverse("webhooks:list")))
        self.assertIn("Projektstatus geändert", page)
        self.assertIn("1 fehlgeschlagen", page)
        self.assertIn("1 wartet", page)
        self.assertIn("automatisch abgeschaltet", page)
        self.assertIn("http://n8n:5678/webhook/x", page)


class WebhookFormTests(UiTestCase):
    def test_creating_shows_the_secret_once(self) -> None:
        page = self.client.get(reverse("webhooks:create"))
        self.assert_ok(page)
        data = form_data(
            page,
            "url",
            url="http://erp:8080/rentalars",
            description="ERP",
            events=["project.status_changed", "packing.issued", "packing.returned", "time_entry.approved"],
        )
        response = self.client.post(reverse("webhooks:create"), data, follow=True)
        text = self.assert_ok(response)
        webhook = Webhook.objects.get()
        self.assertEqual(response.redirect_chain[-1][0], reverse("webhooks:detail", args=[webhook.pk]))
        self.assertEqual(
            (webhook.url, webhook.is_active, webhook.created_by), ("http://erp:8080/rentalars", True, self.admin_user)
        )
        self.assertEqual(
            webhook.events, ["project.status_changed", "packing.issued", "packing.returned", "time_entry.approved"]
        )
        secret = webhooks.secret_of(webhook)
        self.assertIn(f'data-copy="{secret}"', text)
        self.assertIn("kopiere es jetzt", text)
        again = self.assert_ok(self.client.get(reverse("webhooks:detail", args=[webhook.pk])))
        self.assertNotIn(secret, again)
        self.assertIn("Geheimnis anzeigen", again)

    def test_mistakes_are_shown_at_the_fields(self) -> None:
        page = self.client.get(reverse("webhooks:create"))
        data = form_data(page, "url", url="ftp://erp/x")
        data.pop("events", None)
        text = self.assert_ok(self.client.post(reverse("webhooks:create"), data))
        self.assertIn("https:// oder http://", text)
        self.assertIn("Dieses Feld ist zwingend erforderlich.", text)
        self.assertFalse(Webhook.objects.exists())

    def test_switching_on_again_starts_afresh(self) -> None:
        webhook, _secret = make_hook("project.created", active=False)
        Webhook.objects.filter(pk=webhook.pk).update(failures_in_a_row=10, switched_off_at=webhook.created_at)
        detail = self.assert_ok(self.client.get(reverse("webhooks:detail", args=[webhook.pk])))
        self.assertIn("automatisch abgeschaltet", detail)
        page = self.client.get(reverse("webhooks:edit", args=[webhook.pk]))
        self.assertEqual(form_data(page, "url")["events"], "project.created")
        data = form_data(page, "url", is_active="on", events=["project.created", "document.created"])
        response = self.client.post(reverse("webhooks:edit", args=[webhook.pk]), data)
        self.assertRedirects(response, reverse("webhooks:detail", args=[webhook.pk]))
        webhook.refresh_from_db()
        self.assertEqual((webhook.is_active, webhook.failures_in_a_row, webhook.switched_off_at), (True, 0, None))
        self.assertEqual(webhook.events, ["project.created", "document.created"])


class WebhookDetailTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.webhook, self.secret = make_hook("project.status_changed")
        self.url = reverse("webhooks:detail", args=[self.webhook.pk])

    def test_the_secret_on_request_and_a_new_one(self) -> None:
        fragment = self.htmx("post", reverse("webhooks:secret", args=[self.webhook.pk]))
        self.assertEqual(fragment.status_code, 200)
        self.assertIn(f'data-copy="{self.secret}"', fragment.content.decode())
        self.assertNotIn("<html", fragment.content.decode())
        # Without scripts the whole page comes back, with the secret.
        page = self.assert_ok(self.client.post(reverse("webhooks:secret", args=[self.webhook.pk])))
        self.assertIn(f'data-copy="{self.secret}"', page)
        self.assertIn("<h1>ERP</h1>", page)

        renewed = self.htmx("post", reverse("webhooks:secret", args=[self.webhook.pk]), {"renew": "1"})
        self.webhook.refresh_from_db()
        new = webhooks.secret_of(self.webhook)
        self.assertNotEqual(new, self.secret)
        self.assertIn(f'data-copy="{new}"', renewed.content.decode())
        self.assertIn("es gilt ab sofort", renewed.content.decode())

    def test_an_unreadable_secret_says_what_to_do(self) -> None:
        Webhook.objects.filter(pk=self.webhook.pk).update(secret_encrypted="gAAAAA-kaputt")
        fragment = self.htmx("post", reverse("webhooks:secret", args=[self.webhook.pk])).content.decode()
        self.assertIn("nicht mehr lesbar", fragment)
        self.assertIn("Geheimnis neu erzeugen", fragment)

    def test_send_test_tells_how_it_went(self) -> None:
        with mock.patch.object(webhooks, "post", Receiver(200)):
            response = self.client.post(reverse("webhooks:test", args=[self.webhook.pk]), follow=True)
        self.assertIn(
            "Der Test ist angekommen: Das empfangende System antwortete nach 12 ms mit 200.", self.messages_of(response)
        )
        page = self.assert_ok(response)
        self.assertIn("ping", page)
        self.assertIn("zugestellt", page)
        with mock.patch.object(webhooks, "post", Receiver(None)):
            response = self.client.post(reverse("webhooks:test", args=[self.webhook.pk]), follow=True)
        self.assertIn("Der Test ist fehlgeschlagen: Der Server ist nicht erreichbar.", self.messages_of(response))

    def test_the_deliveries_show_what_was_sent_and_a_failed_one_can_be_sent_again(self) -> None:
        project = make_project(status=ProjectStatus.OPTION)
        change_status(project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        delivery = WebhookDelivery.objects.get()
        WebhookDelivery.objects.filter(pk=delivery.pk).update(
            status=DeliveryStatus.FAILED,
            attempts=6,
            next_attempt_at=None,
            last_status_code=503,
            last_error="Fehler 503",
        )
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn(str(delivery.uuid), page)
        self.assertIn("&quot;new_status&quot;: &quot;confirmed&quot;", page)
        self.assertIn("Fehler 503", page)
        redeliver = reverse("webhooks:redeliver", args=[self.webhook.pk, delivery.pk])
        self.assertIn(redeliver, page)
        self.assertNotIn("Fehler 503", self.assert_ok(self.client.get(self.url, {"status": "delivered"})))

        with mock.patch.object(webhooks, "post", Receiver(202)):
            response = self.client.post(redeliver, follow=True)
        self.assertIn(
            "Erneut gesendet: Das empfangende System antwortete nach 12 ms mit 202.", self.messages_of(response)
        )
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempts), ("delivered", 7))
        self.assertNotIn(redeliver, self.assert_ok(response))
        response = self.client.post(redeliver, follow=True)
        self.assertIn("Nur fehlgeschlagene Zustellungen lassen sich erneut senden.", self.messages_of(response))

    def test_deleting(self) -> None:
        response = self.client.post(reverse("webhooks:delete", args=[self.webhook.pk]))
        self.assertRedirects(response, reverse("webhooks:list"))
        self.assertFalse(Webhook.objects.exists())


class WebhookRightsTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.webhook, self.secret = make_hook("project.created")

    def test_reading_shows_neither_the_secret_nor_buttons(self) -> None:
        reader = self.browser_of(settings_user("rita", 1))
        self.assert_ok(reader.get(reverse("webhooks:list")))
        page = self.assert_ok(reader.get(reverse("webhooks:detail", args=[self.webhook.pk])))
        self.assertIn("Das Geheimnis sieht nur, wer Webhooks ändern darf.", page)
        self.assertNotIn(reverse("webhooks:secret", args=[self.webhook.pk]), page)
        self.assertNotIn(reverse("webhooks:test", args=[self.webhook.pk]), page)
        for address in (
            reverse("webhooks:secret", args=[self.webhook.pk]),
            reverse("webhooks:test", args=[self.webhook.pk]),
            reverse("webhooks:create"),
            reverse("webhooks:delete", args=[self.webhook.pk]),
        ):
            with self.subTest(address=address):
                self.assertEqual(reader.post(address).status_code, 403)
        self.assertEqual(reader.get(reverse("webhooks:edit", args=[self.webhook.pk])).status_code, 403)

    def test_changing_is_not_deleting(self) -> None:
        editor = self.browser_of(settings_user("eddi", 2))
        page = self.assert_ok(editor.get(reverse("webhooks:detail", args=[self.webhook.pk])))
        self.assertIn(reverse("webhooks:secret", args=[self.webhook.pk]), page)
        self.assertNotIn(reverse("webhooks:delete", args=[self.webhook.pk]), page)
        self.assertEqual(editor.post(reverse("webhooks:delete", args=[self.webhook.pk])).status_code, 403)

    def test_without_the_settings_nothing(self) -> None:
        crew = self.browser_for("carla", "Crew")
        self.assertEqual(crew.get(reverse("webhooks:list")).status_code, 403)
        self.assertEqual(crew.get(reverse("webhooks:detail", args=[self.webhook.pk])).status_code, 403)
