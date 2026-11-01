# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "settings" (API-014): ADM-015, EML-046, PRJ-105.

* ADM-015: ``/mail/settings`` still reads and changes ``crew_answers`` – the
  browser offers it under Firmendaten und Grundeinstellungen now.
* EML-046: ``DELETE /mail/mailboxes/{id}`` deletes, also a mailbox with mails;
  ``?successor=`` names the mailbox that sends the correspondence afterwards;
  the mail log keeps the name.
* PRJ-105: the follow-up of a project – fields of the project,
  ``PUT``/``DELETE /projects/{id}/follow-up``, the filter ``follow_up``, the
  notification kind ``follow_up``.
"""

from __future__ import annotations

import datetime

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import CrewAnswerMode, Mailbox, MailSettings
from rentalars.projects.follow_up import set_follow_up
from rentalars.projects.models import Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail

MAILBOXES = f"{API}/mail/mailboxes"


class CrewAnswerSettingApiTests(ApiTestCase):
    """ADM-015: the API of the setting is unchanged."""

    def test_read_and_change(self) -> None:
        response = self.admin.get(f"{API}/mail/settings")
        self.assertEqual(response.json()["crew_answers"], CrewAnswerMode.BOTH)
        response = self.admin.patch(f"{API}/mail/settings", {"crew_answers": "link"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.LINK)


class DeleteMailboxApiTests(ApiTestCase):
    """EML-046: ``DELETE`` deletes; mails and log keep the name."""

    def setUp(self) -> None:
        super().setUp()
        self.projects = configure_mailbox()
        self.info = add_mailbox("Info", "info@verleih.example")
        project = make_project()
        with mailboxes(
            {
                "projekte@verleih.example": FakeMailbox(),
                "info@verleih.example": FakeMailbox(make_mail(f"Plan [RL#{project.number}]")),
            }
        ):
            fetch_mail(force=True)

    def test_delete_and_the_log_keeps_the_name(self) -> None:
        self.assertEqual(self.admin.delete(f"{MAILBOXES}/{self.info.pk}").status_code, 204)
        self.assertFalse(Mailbox.objects.filter(pk=self.info.pk).exists())
        entries = self.admin.get(f"{API}/mail/log?q=Info").json()["results"]
        self.assertTrue(entries)
        for entry in entries:
            self.assertEqual((entry["mailbox"], entry["mailbox_name"], entry["mailbox_deleted"]), (None, "Info", True))
        others = [entry for entry in self.admin.get(f"{API}/mail/log").json()["results"] if entry["mailbox"]]
        for entry in others:
            self.assertEqual((entry["mailbox_name"], entry["mailbox_deleted"]), ("Projekte", False))

    def test_the_successor_of_the_mailbox_that_sends(self) -> None:
        buero = add_mailbox("Büro", "buero@verleih.example")
        response = self.admin.delete(f"{MAILBOXES}/{self.projects.pk}")
        self.assert_error(response, 400, "validation_error", "successor")
        self.assertTrue(Mailbox.objects.filter(pk=self.projects.pk).exists())
        response = self.admin.delete(f"{MAILBOXES}/{self.projects.pk}?successor={buero.pk}")
        self.assertEqual(response.status_code, 204, response.content)
        buero.refresh_from_db()
        self.assertTrue(buero.is_outgoing)

    def test_switching_off_is_a_change(self) -> None:
        response = self.admin.patch(f"{MAILBOXES}/{self.info.pk}", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["is_active"])

    def test_needs_the_right_to_delete(self) -> None:
        manager = self.client_for("paula", "Projektleitung")
        self.assertEqual(manager.delete(f"{MAILBOXES}/{self.info.pk}").status_code, 403)
        self.assertTrue(Mailbox.objects.filter(pk=self.info.pk).exists())


class FollowUpApiTests(ApiTestCase):
    """PRJ-105: set, read, filter and finish follow-ups."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)
        self.url = f"{API}/projects/{self.project.pk}/follow-up"

    def test_set_read_and_done(self) -> None:
        response = self.admin.put(
            self.url,
            {"follow_up_on": "2027-03-04", "follow_up_user": self.paula.pk, "follow_up_note": "Angebot nachfassen"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(
            (data["follow_up_on"], data["follow_up_user"], data["follow_up_user_name"], data["follow_up_note"]),
            ("2027-03-04", self.paula.pk, "paula", "Angebot nachfassen"),
        )
        self.assertFalse(data["follow_up_is_due"])
        project = self.admin.get(f"{API}/projects/{self.project.pk}").json()
        self.assertEqual(project["follow_up_on"], "2027-03-04")
        # Not through the project itself: the fields are read-only there.
        self.admin.patch(f"{API}/projects/{self.project.pk}", {"follow_up_note": "anders"}, format="json")
        self.project.refresh_from_db()
        self.assertEqual(self.project.follow_up_note, "Angebot nachfassen")
        response = self.admin.delete(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["follow_up_on"], response.json()["follow_up_user"]), (None, None))

    def test_for_the_caller_by_default(self) -> None:
        response = self.client_of(self.paula).put(self.url, {"follow_up_on": "2027-03-01"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["follow_up_user"], self.paula.pk)
        self.assertTrue(response.json()["follow_up_is_due"])

    def test_refused(self) -> None:
        self.assert_error(self.admin.put(self.url, {}, format="json"), 400, "validation_error", "follow_up_on")
        crew = make_user("carla", roles=("Crew",))
        response = self.admin.put(self.url, {"follow_up_on": "2027-03-04", "follow_up_user": crew.pk}, format="json")
        self.assert_error(response, 400, "validation_error", "follow_up_user")
        reader = self.client_for("nora", "Nur-Lesen")
        self.assertEqual(reader.put(self.url, {"follow_up_on": "2027-03-04"}, format="json").status_code, 403)
        self.assertEqual(reader.delete(self.url).status_code, 403)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.follow_up_on)

    def test_a_closed_project(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        response = self.admin.put(self.url, {"follow_up_on": "2027-04-01"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)

    def test_filter(self) -> None:
        later = make_project("Hochzeit", status=ProjectStatus.OPTION)
        set_follow_up(self.project, on=datetime.date(2027, 3, 1), by=self.paula)
        set_follow_up(later, on=datetime.date(2027, 3, 9), by=self.admin_user)

        def numbers(query: str, client: object = None) -> set[str]:
            response = (client or self.admin).get(f"{API}/projects?{query}")  # type: ignore[attr-defined]
            self.assertEqual(response.status_code, 200, response.content)
            return {row["name"] for row in response.json()["results"]}

        self.assertEqual(numbers("follow_up=due"), {"Firmenfeier"})
        self.assertEqual(numbers("follow_up=any"), {"Firmenfeier", "Hochzeit"})
        self.assertEqual(numbers("follow_up=mine"), {"Hochzeit"})
        self.assertEqual(numbers("follow_up=mine", self.client_of(self.paula)), {"Firmenfeier"})
        response = self.admin.get(f"{API}/projects?follow_up=any&ordering=-follow_up_on")
        self.assertEqual([row["name"] for row in response.json()["results"]], ["Hochzeit", "Firmenfeier"])

    def test_crew_learns_nothing_of_it(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 1), note="Rückruf", by=self.paula)
        carla = make_user("carla", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Carla Crew", user=carla))
        crew = self.client_of(carla)
        document = crew.get(f"{API}/projects/{self.project.pk}").json()
        self.assertNotIn("follow_up_note", document)
        self.assertEqual(crew.get(f"{API}/projects?follow_up=due").json()["results"], [])

    def test_the_notification_kind(self) -> None:
        kinds = {item["kind"]: item for item in self.admin.get(f"{API}/notifications/preferences").json()}
        self.assertEqual(
            (kinds["follow_up"]["label"], kinds["follow_up"]["in_app"], kinds["follow_up"]["by_email"]),
            ("Wiedervorlage eines Projekts", True, True),
        )
