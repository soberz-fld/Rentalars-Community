# SPDX-License-Identifier: GPL-3.0-or-later
"""Notes in the correspondence, with the time they happened (EML-051).

The requirement: the correspondence can also hold plain notes, with a time stamp so that the chronology is kept.

* A note stands in the chronology at the time chosen – in the list, in the
  conversation, in the overview and in what the AI reads.
* It is no mail: nothing is sent, nothing answered, no "new communication"
  for the rules of the service cases.
* Its writer – or who may edit the project – changes or removes it.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from rentalars.ai.correspondence import entries
from rentalars.ai.overview import overview_of
from rentalars.ai.summary import render_entry
from rentalars.automations.models import Action, Automation, AutomationRun, Trigger
from rentalars.mail import notes
from rentalars.mail.models import Direction, ProjectMail
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, at, make_customer, make_project, make_user
from tests.ui.base import UiTestCase


def mail(project: object, subject: str, when: datetime.datetime, *, direction: str = Direction.INCOMING) -> ProjectMail:
    return ProjectMail.objects.create(
        project=project,
        direction=direction,
        message_key=f"key-{subject}",
        message_id=f"<{subject}@x.example>",
        subject=subject,
        sender_name="Max Muster",
        sender_address="max@stadthalle.example",
        date=when,
        text_body=f"Text {subject}",
    )


class NoteServiceTests(RentalarsTestCase):
    """EML-051: writing, changing, refusing."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.paula.first_name, self.paula.last_name = "Paula", "Plan"
        self.paula.save()
        self.project = make_project("Stadtfest")

    def test_a_note_at_the_time_it_happened(self) -> None:
        when = at(27, 9, 30, month=2)  # earlier than "now" (1 March 2027, 08:00, test clock)
        note = notes.add_note(self.project, text="Anruf: Bühne 2 m breiter.", user=self.paula, date=when)
        self.assertTrue(note.is_note)
        self.assertEqual((note.direction, note.date, note.sent_by), (Direction.NOTE, when, self.paula))
        self.assertEqual(note.sender_name, "Paula Plan")
        self.assertEqual(note.note_title, "Anruf: Bühne 2 m breiter.")
        self.assertEqual(note.display_subject, note.note_title)
        self.assertEqual(note.message_id, "")
        self.assertTrue(note.message_key.startswith("note:"))
        # Without a time: now.
        now_note = notes.add_note(self.project, text="Noch eine", subject="Telefonat", user=self.paula)
        self.assertLess(abs(now_note.date - timezone.now()), datetime.timedelta(seconds=5))
        self.assertEqual(now_note.note_title, "Telefonat")

    def test_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            notes.add_note(self.project, text="  ", user=self.paula)
        self.assertIn("text", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            notes.add_note(
                self.project, text="Morgen", user=self.paula, date=timezone.now() + datetime.timedelta(days=1)
            )
        self.assertIn("date", caught.exception.message_dict)
        received = mail(self.project, "Anfrage", at(1, 8))
        with self.assertRaises(ValidationError):
            notes.update_note(received, text="geändert")

    def test_change(self) -> None:
        note = notes.add_note(self.project, text="Anruf", user=self.paula, date=at(27, 9, month=2))
        notes.update_note(note, text="Anruf von Max", date=at(27, 8, month=2), subject="Telefonat")
        note.refresh_from_db()
        self.assertEqual((note.text_body, note.date, note.subject), ("Anruf von Max", at(27, 8, month=2), "Telefonat"))

    def test_who_may_change(self) -> None:
        note = notes.add_note(self.project, text="Anruf", user=self.paula)
        other = make_user("otto")
        self.assertTrue(notes.may_change(note, self.paula, may_edit_project=False))
        self.assertFalse(notes.may_change(note, other, may_edit_project=False))
        self.assertTrue(notes.may_change(note, other, may_edit_project=True))

    def test_in_the_chronology_of_the_ai_and_the_overview(self) -> None:
        mail(self.project, "Anfrage", at(26, 8, month=2))
        notes.add_note(
            self.project, text="Rückruf: passt so.", subject="Telefonat", user=self.paula, date=at(27, 9, month=2)
        )
        found = entries([self.project.pk])
        self.assertEqual([entry.kind for entry in found], ["mail", "note"])
        self.assertEqual(found[1].writer, "Paula Plan")
        text = render_entry(found[1])
        self.assertIn("--- Note (no mail; e.g. a phone call)", text)
        self.assertIn("Rückruf: passt so.", text)
        overview = overview_of([self.project.pk])
        self.assertEqual((overview.received, overview.sent, overview.notes), (1, 0, 1))
        # The last mail – not the note – decides whether an answer may be due.
        self.assertTrue(overview.last_is_incoming)

    def test_no_new_communication_for_the_service_cases(self) -> None:
        case = service_cases.create_case(name="Spot flackert", customer=make_customer())
        Automation.objects.create(
            name="Wieder öffnen",
            trigger=Trigger.CASE_COMMUNICATION,
            action=Action.CASE_STATUS,
            new_case_status=CaseStatus.IN_PROGRESS,
        )
        with self.captureOnCommitCallbacks(execute=True):
            notes.add_note(case, text="Kunde angerufen", user=self.paula)
        self.assertFalse(AutomationRun.objects.filter(trigger=Trigger.CASE_COMMUNICATION).exists())


class NotePageTests(UiTestCase):
    """EML-051 on the pages: add, list, conversation, change, remove; no answer."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.browser = self.browser_of(self.paula)
        self.project = make_project("Stadtfest")
        self.mails = reverse("mail:project_mails", args=[self.project.pk])

    def test_add_a_note_from_the_correspondence(self) -> None:
        page = self.assert_ok(self.browser.get(self.mails))
        create = reverse("mail:note_create", args=[self.project.pk])
        self.assertIn(create, page)
        self.assertIn("Notiz hinzufügen", page)
        form = self.assert_ok(self.browser.get(create))
        self.assertIn('type="datetime-local"', form)
        self.assertIn("Es wird nichts versendet", form)
        response = self.browser.post(
            create, {"date": "2027-02-27T14:15", "subject": "", "text": "Anruf Max: Aufbau ab 8 Uhr.\nZweite Zeile"}
        )
        self.assertRedirects(response, self.mails)
        note = ProjectMail.objects.get(direction=Direction.NOTE)
        self.assertEqual(timezone.localtime(note.date).strftime("%d.%m.%Y %H:%M"), "27.02.2027 14:15")
        page = self.assert_ok(self.browser.get(self.mails + "?view=list"))
        self.assertIn('<span class="badge is-note">Notiz</span>', page)
        self.assertIn("Anruf Max: Aufbau ab 8 Uhr.", page)
        self.assertIn("notiert von paula", page)
        page = self.assert_ok(self.browser.get(self.mails + "?view=conversation"))
        self.assertIn('<li class="bubble is-note">', page)
        self.assertIn("Zweite Zeile", page)

    def test_a_note_in_the_future_is_refused(self) -> None:
        create = reverse("mail:note_create", args=[self.project.pk])
        page = self.assert_ok(self.browser.post(create, {"date": "2030-01-01T10:00", "text": "später"}))
        self.assertIn("wähle eine Zeit, die vergangen ist", page)
        self.assertFalse(ProjectMail.objects.exists())

    def test_the_note_page_changes_and_removes(self) -> None:
        note = notes.add_note(self.project, text="Anruf", user=self.paula, date=at(27, 9, month=2))
        detail = reverse("mail:detail", args=[self.project.pk, note.pk])
        page = self.assert_ok(self.browser.get(detail))
        self.assertIn("Notiz ändern", page)
        self.assertNotIn("Antworten", page)
        edit = reverse("mail:note_edit", args=[self.project.pk, note.pk])
        response = self.browser.post(edit, {"date": "2027-02-27T08:45", "subject": "Telefonat", "text": "Anruf Max"})
        self.assertRedirects(response, self.mails)
        note.refresh_from_db()
        self.assertEqual((note.subject, note.text_body), ("Telefonat", "Anruf Max"))
        # Reading only: no form, no removing.
        reader = self.browser_for("nora", "Nur-Lesen")
        page = self.assert_ok(reader.get(detail))
        self.assertNotIn("Notiz ändern", page)
        self.assertEqual(reader.post(edit, {"date": "2027-02-27T08:45", "text": "x"}).status_code, 403)
        # The writer removes it.
        response = self.browser.post(reverse("mail:delete", args=[self.project.pk, note.pk]))
        self.assertRedirects(response, self.mails)
        self.assertFalse(ProjectMail.objects.filter(pk=note.pk).exists())

    def test_a_note_is_not_answered(self) -> None:
        note = notes.add_note(self.project, text="Anruf", user=self.paula)
        page = self.assert_ok(self.browser.get(reverse("mail:compose", args=[self.project.pk]) + f"?answer={note.pk}"))
        self.assertNotIn("AW:", page)


class NoteApiTests(ApiTestCase):
    """API-014: notes through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.base = f"{API}/projects/{self.project.pk}/mails"

    def test_write_change_list_remove(self) -> None:
        response = self.admin.post(
            f"{self.base}/notes",
            {"text": "Anruf Max", "subject": "Telefonat", "date": "2027-02-28T10:00:00+01:00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(
            (data["direction"], data["subject"], data["text"], data["reply"]), ("note", "Telefonat", "Anruf Max", None)
        )
        note_id = data["id"]
        listed = self.admin.get(self.base).json()
        self.assertEqual([entry["direction"] for entry in listed], ["note"])
        response = self.admin.patch(f"{self.base}/{note_id}", {"text": "Anruf Max: passt"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["text"], "Anruf Max: passt")
        response = self.admin.post(
            self.base, {"to": "a@b.example", "subject": "x", "body": "y", "answer_to": note_id}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "answer_to")
        self.assertEqual(self.admin.delete(f"{self.base}/{note_id}").status_code, 204)

    def test_refused(self) -> None:
        response = self.admin.post(f"{self.base}/notes", {"text": ""}, format="json")
        self.assert_error(response, 400, "validation_error", "text")
        response = self.admin.post(
            f"{self.base}/notes", {"text": "x", "date": "2031-01-01T10:00:00+01:00"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "date")
        received = mail(self.project, "Anfrage", at(1, 8))
        response = self.admin.patch(f"{self.base}/{received.pk}", {"text": "geändert"}, format="json")
        self.assert_error(response, 400, "validation_error")
        crew = self.client_for("kai", "Crew")
        response = crew.post(f"{self.base}/notes", {"text": "x"}, format="json")
        self.assertIn(response.status_code, (403, 404))
