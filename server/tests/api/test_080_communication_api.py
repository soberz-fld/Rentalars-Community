# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "communication" (API-014): the chat in the project (UIX-010), automations (ADM-013).

* UIX-010: ``/projects/{id}/chat`` – list and write; ``…/chat/{message}`` – read, change, delete;
  ``…/chat/read`` – unread count, mark as read; ``…/chat/readers`` – who reads along. The crew with the
  deployment view reads and writes; a read-only token only reads; others do not find the chat.
* ADM-013: ``/automations`` and ``/automations/{id}`` – the rules with the checks of the browser;
  ``/automations/runs`` – the runs with filters.
"""

from __future__ import annotations

from rentalars.automations.models import Action, Automation, AutomationRun, RunStatus, Trigger
from rentalars.chat.models import ChatMessage
from rentalars.notifications.models import Kind, Notification
from rentalars.projects.models import ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_project, make_user, plan, set_clock
from tests.mailbox import configure_mailbox


class ChatApiTests(ApiTestCase):
    """UIX-010 through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.crew_user = make_user("anna", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Anna Becker", user=self.crew_user))
        self.crew = self.client_of(self.crew_user)
        self.url = f"{API}/projects/{self.project.pk}/chat"

    def test_write_list_change_delete(self) -> None:
        response = self.admin.post(self.url, {"text": "@Anna Becker Kabel?"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        message = response.json()
        self.assertEqual(message["text"], "@Anna Becker Kabel?")
        self.assertEqual(message["author"], self.admin_user.pk)
        self.assertEqual(message["mentioned"], [self.crew_user.pk])
        self.assertTrue(message["can_change"])
        self.assertTrue(Notification.objects.filter(kind=Kind.CHAT_MENTION, user=self.crew_user).exists())

        response = self.crew.post(self.url, {"text": "Ja"}, format="json")
        self.assertEqual(response.status_code, 201)
        listed = self.crew.get(self.url)
        self.assertEqual([item["text"] for item in listed.json()], ["@Anna Becker Kabel?", "Ja"])
        self.assertEqual(listed["X-Has-Older"], "false")
        self.assertEqual([item["can_change"] for item in listed.json()], [False, True])
        older = self.crew.get(f"{self.url}?before={response.json()['id']}&limit=1")
        self.assertEqual([item["text"] for item in older.json()], ["@Anna Becker Kabel?"])

        detail = f"{self.url}/{message['id']}"
        self.assertEqual(self.crew.get(detail).json()["text"], "@Anna Becker Kabel?")
        response = self.admin.patch(detail, {"text": "Kabel?"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["mentioned"], [])
        self.assertIsNotNone(response.json()["edited_at"])
        response = self.admin.put(detail, {"text": "Kabel!"}, format="json")
        self.assertEqual(response.json()["text"], "Kabel!")
        self.assert_error(self.crew.patch(detail, {"text": "x"}, format="json"), 403, "permission_denied")
        self.assert_error(self.admin.post(self.url, {"text": " "}, format="json"), 400, "validation_error", "text")
        set_clock(at(1, 8, 16))
        self.assert_error(self.admin.delete(detail), 400, "validation_error")
        set_clock(at(1, 8))
        self.assertEqual(self.admin.delete(detail).status_code, 204)
        self.assertEqual(ChatMessage.objects.count(), 1)

    def test_unread_and_readers(self) -> None:
        self.admin.post(self.url, {"text": "Eins"}, format="json")
        self.admin.post(self.url, {"text": "Zwei"}, format="json")
        self.assertEqual(self.crew.get(f"{self.url}/read").json(), {"unread": 2})
        first = ChatMessage.objects.order_by("pk").first()
        self.assertEqual(self.crew.post(f"{self.url}/read", {"up_to": first.pk}, format="json").json(), {"unread": 1})
        self.assertEqual(self.crew.post(f"{self.url}/read", {}, format="json").json(), {"unread": 0})
        readers = {reader["username"]: reader for reader in self.crew.get(f"{self.url}/readers").json()}
        self.assertEqual(
            readers["anna"],
            {"id": self.crew_user.pk, "name": "Anna Becker", "username": "anna", "access": "deployment"},
        )
        self.assertEqual(readers["admin"]["access"], "edit")

    def test_who_may(self) -> None:
        stranger = self.client_for("otto", "Crew")
        self.assert_error(stranger.get(self.url), 404, "not_found")
        self.assert_error(stranger.post(self.url, {"text": "x"}, format="json"), 404, "not_found")
        reader = self.client_of(self.crew_user, read_only=True)
        self.assertEqual(reader.get(self.url).status_code, 200)
        self.assert_error(reader.post(self.url, {"text": "x"}, format="json"), 403, "permission_denied")


class AutomationApiTests(ApiTestCase):
    """ADM-013 through the API."""

    def setUp(self) -> None:
        super().setUp()
        # Without the default rules of the service cases (PRJ-112), which every installation gets.
        Automation.objects.all().delete()

    def test_create_change_delete(self) -> None:
        box = configure_mailbox(process_untagged=True)
        url = f"{API}/automations"
        response = self.admin.post(
            url,
            {
                "name": "Eingangsbestätigung",
                "trigger": "inquiry",
                "mailbox": box.pk,
                "action": "reply",
                "subject": "Eingang: {betreff}",
                "text": "Danke, {name}.",
                "status": "confirmed",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        rule = response.json()
        self.assertEqual((rule["mailbox"], rule["status"], rule["recipient"], rule["user"]), (box.pk, "", "", None))
        self.assertEqual(Automation.objects.get().created_by, self.admin_user)
        self.assertEqual([item["name"] for item in self.admin.get(url).json()], ["Eingangsbestätigung"])
        detail = f"{url}/{rule['id']}"
        self.assertEqual(self.admin.get(detail).json()["text"], "Danke, {name}.")
        error = self.assert_error(
            self.admin.patch(detail, {"trigger": "project_status"}, format="json"), 400, "validation_error"
        )
        self.assertIn("action", error["fields"])
        response = self.admin.patch(detail, {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["is_active"])
        response = self.admin.put(
            detail,
            {
                "name": "Status",
                "trigger": "project_status",
                "status": "confirmed",
                "action": "open_item",
                "text": "Rechnung",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["mailbox"], response.json()["subject"]), (None, ""))
        self.assertEqual(self.admin.delete(detail).status_code, 204)
        self.assertFalse(Automation.objects.exists())

    def test_checks_and_rights(self) -> None:
        url = f"{API}/automations"
        error = self.assert_error(
            self.admin.post(
                url, {"name": "x", "trigger": "follow_up", "action": "notify", "recipient": "user"}, format="json"
            ),
            400,
            "validation_error",
            "user",
        )
        self.assertTrue(error["message"])
        self.assert_error(self.client_for("anna", "Crew").get(url), 403, "permission_denied")

    def test_runs(self) -> None:
        manager = make_user("lena", roles=("Projektleitung",))
        rule = Automation.objects.create(
            name="Bestätigt",
            trigger=Trigger.PROJECT_STATUS,
            status=ProjectStatus.CONFIRMED,
            action=Action.NOTIFY,
            recipient="manager",
        )
        with self.captureOnCommitCallbacks(execute=True):
            make_project(manager=manager)
        response = self.admin.get(f"{API}/automations/runs?automation={rule.pk}&status=done")
        self.assertEqual(response.status_code, 200, response.content)
        runs = response.json()["results"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], RunStatus.DONE)
        self.assertEqual(runs[0]["automation_name"], "Bestätigt")
        self.assertEqual(runs[0]["detail"], "Benachrichtigt: lena")
        self.assertEqual(self.admin.get(f"{API}/automations/runs?status=failed").json()["results"], [])
        self.assertEqual(AutomationRun.objects.count(), 1)
