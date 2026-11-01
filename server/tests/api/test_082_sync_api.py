# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "sync" (API-014): the offline sync with ``base_version`` and ``change_id``
(PCK-027), the list for the phone that reads only (PCK-026), ``POST …/chat/read`` with ``up_to`` (UIX-010).

What an older app sends – ``line``, ``product``, ``field``, ``quantity``, ``changed_at`` – keeps working and
gets every key; the new keys come in addition.
"""

from __future__ import annotations

from typing import Any

from rentalars.chat import services as chat
from rentalars.chat.models import ChatReadMark
from rentalars.packing.models import PackEntry, Packlist, SyncReceipt
from rentalars.projects.models import Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.api.test_070_packing_api import PacklistApiTestCase
from tests.helpers import at, make_person, make_project, make_user, plan, set_clock

KEYS_OF_081 = {"line", "product", "field", "outcome", "message"}


class SyncWithVersionsApiTests(PacklistApiTestCase):
    """PCK-027: versions, conflicts and change IDs through ``POST …/sync``."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(at(9, 12))

    def cable_row(self) -> dict[str, Any]:
        return self.rows(self.admin.get(self.base).json())["K-005"]

    def test_every_row_carries_its_version(self) -> None:
        self.assertEqual(self.cable_row()["version"], 0)
        self.assertEqual(self.tick("4").status_code, 200)
        self.assertEqual(self.cable_row()["version"], 1)

    def test_the_way_of_the_app_020_is_unchanged(self) -> None:
        answer = self.sync(self.change("packed", "4", "2027-03-09T11:00:00+01:00"))
        self.assertEqual(answer.status_code, 200, answer.content)
        result = answer.json()["results"][0]
        self.assertLessEqual(KEYS_OF_081, set(result))
        self.assertEqual(
            {key: result[key] for key in ("outcome", "change_id", "replayed", "version", "server")},
            {
                "outcome": "applied",
                "change_id": None,
                "replayed": False,
                "version": 1,
                "server": {"quantity": "4.00", "changed_at": "2027-03-09T10:00:00Z"},
            },
        )

    def test_base_version_decides_and_a_conflict_keeps_the_server(self) -> None:
        self.tick("2")
        set_clock(at(9, 12, 5))
        self.tick("3")
        answer = self.sync(
            {**self.change("packed", "7", "2027-03-09T12:00:30+01:00"), "base_version": 1, "change_id": "c-1"},
            {**self.change("packed", "2", "2027-03-09T11:00:00+01:00", line=self.rack_line), "base_version": 0},
        )
        self.assertEqual(answer.status_code, 200, answer.content)
        conflict, applied = answer.json()["results"]
        self.assertEqual(
            {key: conflict[key] for key in ("outcome", "message", "change_id", "version", "server")},
            {
                "outcome": "conflict",
                "message": "Inzwischen auf dem Server geändert; dort steht jetzt 3.",
                "change_id": "c-1",
                "version": 2,
                "server": {"quantity": "3.00", "changed_at": "2027-03-09T11:05:00Z"},
            },
        )
        self.assertEqual((applied["outcome"], applied["message"]), ("refused", "Gebraucht werden nur 1."))
        self.assertEqual(PackEntry.objects.get(line=self.cable_line).packed_quantity, 3)
        self.assertEqual(self.rows(answer.json()["packlist"])["K-005"]["version"], 2)

    def test_sent_again_with_its_change_id(self) -> None:
        change = {**self.change("packed", "5", "2027-03-09T11:00:00+01:00"), "change_id": "6f1c-uuid"}
        first = self.sync(change).json()["results"][0]
        set_clock(at(9, 12, 30))
        self.tick("2")
        again = self.sync(change).json()["results"][0]
        self.assertEqual((first["outcome"], first["replayed"]), ("applied", False))
        self.assertEqual((again["outcome"], again["replayed"], again["server"]["quantity"]), ("applied", True, "2.00"))
        self.assertEqual(PackEntry.objects.get(line=self.cable_line).packed_quantity, 2)
        self.assertEqual(SyncReceipt.objects.count(), 1)
        self.assertIsNone(again["reason"])
        # The same ID with another quantity: refused with its reason, nothing applied.
        reused = self.sync({**change, "quantity": "9"}).json()["results"][0]
        self.assertEqual(
            {key: reused[key] for key in ("outcome", "reason", "replayed", "message")},
            {
                "outcome": "refused",
                "reason": "change_id_reused",
                "replayed": False,
                "message": "Diese Änderungskennung gehört schon zu einer anderen Änderung.",
            },
        )
        self.assertEqual(PackEntry.objects.get(line=self.cable_line).packed_quantity, 2)

    def test_invalid_new_fields_refuse_the_whole_sync(self) -> None:
        good = self.change("packed", "4", "2027-03-09T11:00:00+01:00")
        for change in (
            {**good, "base_version": -1},
            {**good, "base_version": "eins"},
            {**good, "base_version": 2**40},
            {**good, "change_id": "x" * 65},
            {**good, "change_id": ["a"]},
        ):
            self.assert_error(self.sync(good, change), 400, "validation_error")
        self.assertFalse(PackEntry.objects.filter(packed_quantity__gt=0).exists())
        # Empty or null: as without.
        answer = self.sync({**good, "base_version": None, "change_id": ""})
        self.assertEqual(answer.json()["results"][0]["outcome"], "applied")

    def test_described_in_the_api_description(self) -> None:
        description = self.admin.get(f"{API}/schema?format=json").json()
        schemas = description["components"]["schemas"]
        self.assertIn("base_version", schemas["SyncChangeRequest"]["properties"])
        self.assertIn("change_id", schemas["SyncChangeRequest"]["properties"])
        self.assertIn("conflict", str(schemas["OutcomeEnum"]))


class OfflineListReadsOnlyApiTests(PacklistApiTestCase):
    """Line 29, PCK-026: ``GET /offline/packlists`` creates nothing."""

    def test_a_project_without_packlist(self) -> None:
        bare = make_project("Ohne Packliste")
        Packlist.objects.filter(project=bare).delete()
        Project.objects.filter(pk=bare.pk).update(status=ProjectStatus.OUT)
        count = Packlist.objects.count()
        answer = self.admin.get(f"{API}/offline/packlists")
        self.assertEqual(answer.status_code, 200)
        listed = {project["id"]: project for project in answer.json()["projects"]}
        self.assertEqual(listed[bare.pk]["packlists"], [])
        self.assertEqual(len(listed[self.project.pk]["packlists"]), 1)
        self.assertEqual(Packlist.objects.count(), count)

    def test_a_project_confirmed_through_the_api_has_its_packlist(self) -> None:
        option = make_project("Option", status=ProjectStatus.OPTION)
        answer = self.admin.post(f"{API}/projects/{option.pk}/status", {"status": "confirmed"}, format="json")
        self.assertEqual(answer.status_code, 200, answer.content)
        listed = {project["id"]: project for project in self.admin.get(f"{API}/offline/packlists").json()["projects"]}
        self.assertEqual(len(listed[option.pk]["packlists"]), 1)


class ChatReadApiTests(ApiTestCase):
    """Line 27, UIX-010: ``up_to`` counts up to the newest message of the chat, never further."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.crew_user = make_user("anna", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Anna Becker", user=self.crew_user))
        self.crew = self.client_of(self.crew_user)
        self.url = f"{API}/projects/{self.project.pk}/chat/read"

    def test_beyond_the_newest_message(self) -> None:
        first = chat.post_message(self.project, user=self.admin_user, text="Eins")
        answer = self.crew.post(self.url, {"up_to": first.pk + 10**9}, format="json")
        self.assertEqual(answer.json(), {"unread": 0})
        self.assertEqual(ChatReadMark.objects.get(user=self.crew_user).last_read_id, first.pk)
        chat.post_message(self.project, user=self.admin_user, text="Zwei")
        self.assertEqual(self.crew.get(self.url).json(), {"unread": 1})

    def test_up_to_as_before_and_invalid(self) -> None:
        first = chat.post_message(self.project, user=self.admin_user, text="Eins")
        chat.post_message(self.project, user=self.admin_user, text="Zwei")
        self.assertEqual(self.crew.post(self.url, {"up_to": str(first.pk)}, format="json").json(), {"unread": 1})
        for value in ("abc", -1, [1]):
            self.assert_error(self.crew.post(self.url, {"up_to": value}, format="json"), 400, "validation_error")
        self.assertEqual(self.crew.post(self.url, {}, format="json").json(), {"unread": 0})
