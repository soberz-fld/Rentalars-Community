# SPDX-License-Identifier: GPL-3.0-or-later
"""Review: messages with lock and what is around them (EML-055; API-002, AUT-033, AUT-035, AUT-024, UIX-005).

EML-055: messages can be marked with a lock ("mit Schloss"), which controls whether the crew can read the message or
only those with the right to see finances. A message somebody may not read does not exist for him. The review found where it
still showed, and a few things around it:

* The history of a project (page and API, PRJ-032, API-002) names mails and notes by their subject – now only for
  who may read the message; everybody else reads "Nachricht"/"Notiz" with direction and date. Entries written before
  are covered, as the rule is applied when the history is shown; the queries of a page do not grow with it.
* The automations of service cases (PRJ-112) no longer put the subject of a mail with lock into notifications and
  open items: "Mail von … (mit Schloss)".
* An answer to a message with lock starts with the lock – on the page, in the API and when it comes in.
* Only a confirmed crew line (accepted or firm) makes somebody "the crew" of the correspondence.
* ``next`` of the lock button is checked like everywhere else; the tab "Zugriff" counts an expired account as one
  that cannot log in (AUT-035, AUT-024), as the column "Daten" of the lists of users does.
* The text of a notification keeps "<…>" that is no tag (UIX-005).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from rentalars.accounts import data_access
from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, rights_of
from rentalars.automations.engine import run_pending
from rentalars.automations.models import Action, Automation, AutomationRun, Recipient, Trigger
from rentalars.core.audit import record_event
from rentalars.core.models import AuditLogEntry
from rentalars.mail import locks, notes, services
from rentalars.mail.fetching import announce, fetch_mail, import_mail
from rentalars.mail.locks import Reach, correspondence_for
from rentalars.mail.models import AssignedBy, ProjectMail
from rentalars.notifications.models import Kind, Notification
from rentalars.projects.access import ProjectAccess, access_level
from rentalars.projects.access_rows import access_rows
from rentalars.projects.models import CrewLine, OpenItem, ProjectMembership, RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, at, make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, capture_smtp, configure_mailbox, mailboxes, make_mail
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_092_lock import LockScene

SECRET, OPEN, NOTE = "Angebot mit Rabatt", "Aufbauzeiten", "Telefonat Preis"


def reading_role() -> Role:
    """A role that reads all projects – without any right to the correspondence."""
    return Role.objects.create(name="Projekte lesen", module_levels={Module.PROJECTS: int(Level.READ)})


def rows_of(data: Any) -> list[dict[str, Any]]:
    """The rows of a list of the API, paginated or not."""
    return data["results"] if isinstance(data, dict) else data


# --- H1: the history of a project ----------------------------------------------------------------------------


class HistoryPageTests(LockScene, UiTestCase):
    """The page "Verlauf": subjects only for who reads the message (PRJ-032; EML-055)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.url = reverse("projects:history", args=[self.project])

    def page_of(self, user: Any) -> str:
        return self.assert_ok(self.browser_of(user).get(self.url))

    def test_who_reads_everything_sees_the_subjects(self) -> None:
        page = self.page_of(self.paula)
        for subject in (SECRET, OPEN, NOTE):
            self.assertIn(subject, page)
        self.assertIn(f"Notiz in der Korrespondenz: {NOTE}", page)

    def test_without_the_price_right_the_open_ones_only(self) -> None:
        page = self.page_of(self.lena)
        self.assertIn(OPEN, page)
        self.assertNotIn(SECRET, page)
        self.assertNotIn(NOTE, page)
        self.assertIn("Nachricht, eingegangen am ", page)  # the mail with lock, without its subject
        self.assertIn("Notiz vom 01.03.2027 08:00", page)  # the note with lock
        self.assertIn("Notiz in der Korrespondenz vom 01.03.2027 08:00", page)  # its event

    def test_without_any_correspondence_right_no_subject_at_all(self) -> None:
        reading_role()
        reader = make_user("rolf", roles=("Projekte lesen",))
        self.assertEqual(correspondence_for(rights_of(reader), reader, self.project).reach, Reach.NONE)
        page = self.page_of(reader)
        for subject in (SECRET, OPEN, NOTE):
            self.assertNotIn(subject, page)
        self.assertIn("Nachricht, eingegangen am ", page)

    def test_lock_changes_do_not_name_it(self) -> None:
        locks.set_lock(self.secret, False, user=self.paula)
        locks.set_lock(self.secret, True, user=self.paula)
        page = self.page_of(self.lena)
        self.assertNotIn(SECRET, page)
        self.assertIn("Mit Schloss: <del>ja</del> → nein", page)  # what changed is shown, not the subject
        # Open now: Lena reads the message, so she reads its history as well.
        locks.set_lock(self.secret, False, user=self.paula)
        self.assertIn(SECRET, self.page_of(self.lena))

    def test_a_changed_subject_shows_neither_value(self) -> None:
        notes.update_note(self.note, subject="Telefonat Endpreis")
        page = self.page_of(self.lena)
        self.assertNotIn("Telefonat Endpreis", page)
        self.assertNotIn(NOTE, page)
        self.assertIn("geändert (Einzelheiten nicht sichtbar)", page)
        self.assertIn("Telefonat Endpreis", self.page_of(self.paula))

    def test_removed_and_moved_messages_only_for_who_reads_those_with_lock(self) -> None:
        services.reassign(self.open, self.case, user=self.paula)  # open – but no longer in this project
        services.delete_mail(self.secret)
        page = self.page_of(self.lena)
        self.assertNotIn(SECRET, page)
        self.assertNotIn(OPEN, page)
        self.assertIn(f"Nachricht von {self.project.number} nach {self.case.number} verschoben", page)
        self.assertIn("Nachricht vom 01.03.2027 08:30 aus der Korrespondenz entfernt", page)
        paula = self.page_of(self.paula)
        self.assertIn(f"Mail aus der Korrespondenz entfernt: [RL#{self.project.number}] {SECRET}", paula)
        self.assertIn(
            f"Mail von {self.project.number} nach {self.case.number} verschoben: [RL#{self.project.number}] {OPEN}",
            paula,
        )

    def test_entries_written_before_the_review(self) -> None:
        """Older events name no message: a note is found by time and title."""
        open_note = notes.add_note(
            self.project,
            text="Rückruf",
            subject="Rückruf offen",
            user=self.paula,
            date=at(27, 9, month=2),
            locked=False,
        )
        AuditLogEntry.objects.filter(event="mail.note_added").delete()
        for note in (self.note, open_note):
            record_event(self.project, "mail.note_added", {"subject": note.note_title, "date": note.date.isoformat()})
        record_event(self.project, "mail.reassigned", {"subject": "Alte Verschiebung", "from": "2026-0001", "to": "x"})
        page = self.page_of(self.lena)
        self.assertIn("Notiz in der Korrespondenz: Rückruf offen", page)
        self.assertNotIn(NOTE, page)
        self.assertNotIn("Alte Verschiebung", page)
        self.assertIn("Nachricht von 2026-0001 nach x verschoben", page)
        self.assertIn("Alte Verschiebung", self.page_of(self.paula))

    def test_the_queries_do_not_grow_with_the_page(self) -> None:
        def add(indexes: range) -> None:
            for index in indexes:
                ProjectMail.objects.create(
                    project=self.project,
                    message_key=f"many-{index}",
                    subject=f"Mail {index}",
                    date=at(1, 7),
                    locked=index % 2 == 0,
                )
                notes.add_note(self.project, text=f"Notiz {index}", user=self.paula, locked=index % 2 == 1)

        browser = self.browser_of(self.lena)
        add(range(2))
        browser.get(self.url)  # caches warmed
        with CaptureQueriesContext(connection) as few:
            self.assert_ok(browser.get(self.url))
        add(range(2, 10))
        with CaptureQueriesContext(connection) as many:
            page = self.assert_ok(browser.get(self.url))
        self.assertIn("Mail 9:", page)  # open
        self.assertNotIn("Mail 8:", page)  # with lock
        self.assertIn("Notiz 8", page)  # an open note: its title
        self.assertNotIn("Notiz 9", page)
        self.assertEqual(len(many), len(few))


class HistoryApiTests(LockScene, ApiTestCase):
    """``GET /projects/{id}/history`` – the same rule as the page (API-002)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.url = f"{API}/projects/{self.project.pk}/history"

    def test_the_rows(self) -> None:
        locks.set_lock(self.secret, False, user=self.paula)
        locks.set_lock(self.secret, True, user=self.paula)
        notes.update_note(self.note, subject="Telefonat Endpreis")
        response = self.client_of(self.lena).get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        text = response.content.decode()
        for hidden in (SECRET, NOTE, "Telefonat Endpreis"):
            self.assertNotIn(hidden, text)
        rows = rows_of(response.json())
        self.assertIn(f"[RL#{self.project.number}] {OPEN}", [row["object"] for row in rows])
        lock_rows = [row for row in rows if any(change["field"] == "locked" for change in row["changes"])]
        self.assertEqual(len(lock_rows), 2)
        self.assertTrue(all(row["object"].startswith("Nachricht, eingegangen am ") for row in lock_rows))
        note_rows = [row for row in rows if row["summary"].startswith("Notiz in der Korrespondenz")]
        self.assertEqual([row["summary"] for row in note_rows], ["Notiz in der Korrespondenz vom 01.03.2027 08:00"])
        changed = [row for row in rows if row["summary"] == "geändert (Einzelheiten nicht sichtbar)"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["changes"], [])
        paula = self.client_of(self.paula).get(self.url).content.decode()
        for shown in (SECRET, NOTE, "Telefonat Endpreis"):
            self.assertIn(shown, paula)


# --- M1: automations of service cases ------------------------------------------------------------------------


class AutomationTests(LockScene, RentalarsTestCase):
    """PRJ-112: "new communication" – a mail with lock without its subject (EML-055)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        Notification.objects.all().delete()

    def case_mail(self, subject: str, *, locked: bool) -> ProjectMail:
        mail = ProjectMail.objects.create(
            project=self.case,
            direction="in",
            message_key=f"auto-{subject}",
            message_id=f"<{subject.replace(' ', '')}@x.example>",
            subject=subject,
            sender_address="max@stadthalle.example",
            date=at(1, 7),
            text_body="x",
            locked=locked,
        )
        run_pending()
        return mail

    def test_the_notification(self) -> None:
        Automation.objects.create(
            name="Fall-Kommunikation",
            trigger=Trigger.CASE_COMMUNICATION,
            action=Action.NOTIFY,
            recipient=Recipient.MANAGER,
        )
        self.case_mail("Geheimer Preis 999", locked=True)
        notice = Notification.objects.get(user=self.kai, kind=Kind.AUTOMATION)
        self.assertIn("Mail von max@stadthalle.example (mit Schloss)", notice.title)
        self.assertNotIn("Geheimer Preis", notice.title + notice.body)
        run = AutomationRun.objects.get()
        self.assertNotIn("Geheimer Preis", run.event + str(run.data))
        # An open mail: as before, with its subject.
        self.case_mail("Spot geht wieder", locked=False)
        titles = list(Notification.objects.filter(user=self.kai, kind=Kind.AUTOMATION).values_list("title", flat=True))
        self.assertTrue(any("Mail von max@stadthalle.example: Spot geht wieder" in title for title in titles), titles)

    def test_an_open_item(self) -> None:
        Automation.objects.create(
            name="Offener Punkt",
            trigger=Trigger.CASE_COMMUNICATION,
            action=Action.OPEN_ITEM,
            text="Prüfen: {kommunikation}",
        )
        self.case_mail("Geheimer Preis 999", locked=True)
        self.case_mail("Spot geht wieder", locked=False)
        texts = sorted(OpenItem.objects.filter(project=self.case).values_list("text", flat=True))
        self.assertEqual(
            texts,
            [
                "Prüfen: Mail von max@stadthalle.example (mit Schloss)",
                "Prüfen: Mail von max@stadthalle.example: Spot geht wieder",
            ],
        )


# --- M2: answers inherit the lock ----------------------------------------------------------------------------


class AnswerPageTests(LockScene, UiTestCase):
    """The page "Mail schreiben": an answer to a message with lock starts with it – in a service case, too."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        configure_mailbox()
        self.url = reverse("mail:compose", args=[self.case])

    def test_the_choice_starts_with_the_lock_of_the_message_answered(self) -> None:
        browser = self.browser_of(self.paula)
        answer_secret = form_data(browser.get(self.url, {"answer": self.case_secret.pk}), containing="body")
        self.assertEqual(answer_secret.get("locked"), "on")
        answer_open = form_data(browser.get(self.url, {"answer": self.case_open.pk}), containing="body")
        self.assertNotIn("locked", answer_open)  # the default of a service case: open
        with capture_smtp():
            browser.post(f"{self.url}?answer={self.case_secret.pk}", answer_secret)
        self.assertTrue(ProjectMail.objects.get(direction="out").locked)
        # Who may set the lock takes it off on purpose.
        answer_secret.pop("locked")
        with capture_smtp():
            browser.post(f"{self.url}?answer={self.case_secret.pk}", {**answer_secret, "subject": "Ohne Schloss"})
        self.assertFalse(ProjectMail.objects.get(subject__contains="Ohne Schloss").locked)


class AnswerApiTests(LockScene, ApiTestCase):
    """``POST /projects/{id}/mails`` with ``answer_to`` – ``locked`` left out (EML-055, API-002)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        configure_mailbox()

    def send(self, **body: Any) -> dict[str, Any]:
        with capture_smtp():
            response = self.client_of(self.paula).post(
                f"{API}/projects/{self.case.pk}/mails",
                {"to": "kunde@example.org", "subject": "Antwort", "body": "x", **body},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_the_default_of_an_answer(self) -> None:
        self.assertTrue(self.send(answer_to=self.case_secret.pk)["locked"])
        self.assertFalse(self.send(answer_to=self.case_secret.pk, locked=False)["locked"])
        self.assertFalse(self.send(answer_to=self.case_open.pk)["locked"])
        self.assertFalse(self.send()["locked"])  # a new mail of a service case


class IncomingAnswerTests(LockScene, RentalarsTestCase):
    """A mail that comes in as an answer to a message with lock of the same project is stored with the lock."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        asked = import_mail(
            make_mail("Preisfrage", message_id="<preis@x.example>"), self.case, assigned_by=AssignedBy.TAG
        )
        ProjectMail.objects.filter(pk=asked.pk).update(locked=True)
        import_mail(make_mail("Frage offen", message_id="<offen@x.example>"), self.case, assigned_by=AssignedBy.TAG)

    def test_answers(self) -> None:
        to_locked = import_mail(
            make_mail("AW: Preisfrage", in_reply_to="<preis@x.example>"), self.case, assigned_by=AssignedBy.REFERENCE
        )
        to_open = import_mail(
            make_mail("AW: Frage offen", in_reply_to="<offen@x.example>"), self.case, assigned_by=AssignedBy.REFERENCE
        )
        self.assertEqual((to_locked.locked, to_open.locked), (True, False))
        # A message with lock of another project counts for nothing here.
        elsewhere = import_mail(
            make_mail("AW: Angebot", in_reply_to=self.secret.message_id), self.case, assigned_by=AssignedBy.TAG
        )
        self.assertFalse(elsewhere.locked)

    def test_fetched_and_found_by_the_reference(self) -> None:
        box = configure_mailbox()
        raw = make_mail("AW: Preisfrage (ohne Kennung)", in_reply_to="<preis@x.example>")
        with mailboxes({box.address: FakeMailbox(raw)}):
            fetch_mail(force=True)
        answer = ProjectMail.objects.get(subject="AW: Preisfrage (ohne Kennung)")
        self.assertEqual((answer.project, answer.assigned_by, answer.locked), (self.case, AssignedBy.REFERENCE, True))


# --- L2: only a confirmed crew line --------------------------------------------------------------------------


class CrewLineTests(LockScene, UiTestCase):
    """The crew of the correspondence: an accepted or firm line; asked, not answered or declined is not."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.line = CrewLine.objects.get(project=self.project, person=self.carla_person)
        Notification.objects.all().delete()

    def answer(self, status: str) -> Any:
        CrewLine.objects.filter(pk=self.line.pk).update(request_status=status)
        return type(self.carla).objects.get(pk=self.carla.pk)

    def test_the_status_of_the_line(self) -> None:
        for status, reach in (
            (RequestStatus.NONE, Reach.NONE),
            (RequestStatus.REQUESTED, Reach.NONE),
            (RequestStatus.DECLINED, Reach.NONE),
            (RequestStatus.ACCEPTED, Reach.OPEN),
            (RequestStatus.FIRM, Reach.OPEN),
        ):
            with self.subTest(status):
                carla = self.answer(status)
                self.assertEqual(correspondence_for(rights_of(carla), carla, self.project).reach, reach)
                self.assertEqual(carla in locks.crew_of(self.project), reach == Reach.OPEN)
                # Who opens the project does not change.
                self.assertEqual(access_level(rights_of(carla), carla, self.project), ProjectAccess.DEPLOYMENT)

    def test_declined_reads_nothing_and_is_told_nothing(self) -> None:
        self.answer(RequestStatus.DECLINED)
        browser = self.browser_of(self.carla)
        overview = self.assert_ok(browser.get(reverse("projects:deployment", args=[self.project])))
        self.assertNotIn(reverse("mail:project_mails", args=[self.project]), overview)  # no tab "Korrespondenz"
        # As for every reader of the deployment view without the correspondence: not hers (403).
        self.assertEqual(browser.get(reverse("mail:project_mails", args=[self.project])).status_code, 403)
        self.assertEqual(browser.get(reverse("mail:detail", args=[self.project, self.open.pk])).status_code, 403)
        announce(self.open)
        locks.set_lock(self.secret, False, user=self.paula)
        self.assertFalse(Notification.objects.filter(user=self.carla, kind=Kind.NEW_MAIL).exists())
        self.answer(RequestStatus.ACCEPTED)
        announce(self.open)
        self.assertTrue(Notification.objects.filter(user=self.carla, kind=Kind.NEW_MAIL).exists())


# --- L7: back after the lock button --------------------------------------------------------------------------


class LockNextTests(LockScene, UiTestCase):
    """``next`` leads only to a page of Rentalars (as ``projects.relation_views``)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def test_next(self) -> None:
        browser = self.browser_of(self.paula)
        url = reverse("mail:lock", args=[self.project, self.open.pk])
        detail = reverse("mail:detail", args=[self.project, self.open.pk])
        list_url = reverse("mail:project_mails", args=[self.project])
        for target, expected in (
            ("/\\evil.example/", detail),
            ("https://evil.example/", detail),
            ("//evil.example", detail),
            (list_url, list_url),
        ):
            with self.subTest(target):
                response = browser.post(url, {"locked": "1", "next": target})
                self.assertEqual((response.status_code, response["Location"]), (302, expected))


# --- L9: the tab "Zugriff" and an expired account ------------------------------------------------------------


class ExpiredAccountTests(UiTestCase):
    """AUT-035, AUT-024: an account past its "valid until" cannot log in – on the tab and in the column "Daten"."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.eva = make_user("eva", roles=("Projektleitung",))
        plan(self.project, "Stagehand", make_person("Eva Ende", user=self.eva), start=at(10, 8), end=at(10, 16))
        ProjectMembership.objects.create(project=self.project, user=self.eva, level="edit")
        # The nightly job has not run yet: the account is still switched on.
        self.eva.valid_until = timezone.localdate() - datetime.timedelta(days=1)
        self.eva.save()

    def test_the_row_and_the_data_column_agree(self) -> None:
        row = {row.user.username: row for row in access_rows(self.project)}["eva"]
        self.assertFalse(row.can_log_in)
        self.assertEqual(row.access, ProjectAccess.NONE)
        self.assertEqual(data_access.of_user(self.eva), data_access.NONE_AT_ALL)
        self.assertFalse(data_access.can_log_in(self.eva))
        page = self.assert_ok(self.client.get(reverse("projects:members", args=[self.project])))
        self.assertIn("kein Zugang – kann sich nicht anmelden", page)
        self.eva.valid_until = timezone.localdate()  # valid today
        self.eva.save()
        self.assertTrue({row.user.username: row for row in access_rows(self.project)}["eva"].can_log_in)
        self.assertNotEqual(data_access.of_user(self.eva), data_access.NONE_AT_ALL)


class ExpiredAccountApiTests(ApiTestCase):
    """``GET /projects/{id}/access`` – the same (API-002)."""

    def test_the_row(self) -> None:
        project = make_project("Stadtfest")
        eva = make_user("eva", roles=("Crew",))
        plan(project, "Stagehand", make_person("Eva Ende", user=eva), start=at(10, 8), end=at(10, 16))
        eva.valid_until = timezone.localdate() - datetime.timedelta(days=1)
        eva.save()
        rows = {row["username"]: row for row in self.admin.get(f"{API}/projects/{project.pk}/access").json()}
        self.assertEqual((rows["eva"]["can_log_in"], rows["eva"]["access"]), (False, "none"))


# --- L4: the text of a notification ----------------------------------------------------------------------------


class NotificationTextTests(UiTestCase):
    """UIX-005: "<…>" that is no tag stays – in the table and in the CSV file."""

    TEXTS = ("Von Max Mustermann <max@example.org>", "a<b und c>d")

    def setUp(self) -> None:
        super().setUp()
        for index, body in enumerate(self.TEXTS):
            Notification.objects.create(user=self.admin_user, kind=Kind.NEW_MAIL, title=f"Neue Mail {index}", body=body)

    def test_in_the_table(self) -> None:
        page = self.assert_ok(self.client.get(reverse("notifications:list")))
        self.assertIn('<div class="muted small">Von Max Mustermann &lt;max@example.org&gt;</div>', page)
        self.assertIn('<div class="muted small">a&lt;b und c&gt;d</div>', page)

    def test_in_the_csv_file(self) -> None:
        response = self.client.get(reverse("notifications:list"), {"format": "csv", "cols": "all"})
        text = response.content.decode("utf-8")
        self.assertIn("Neue Mail 0;Von Max Mustermann <max@example.org>;", text)
        self.assertIn("Neue Mail 1;a<b und c>d;", text)

    def test_as_a_new_mail_tells_it(self) -> None:
        """The text as Rentalars stores it: the sender of a mail, unescaped."""
        project = make_project("Stadtfest", manager=self.admin_user)
        mail = import_mail(
            make_mail(f"[RL#{project.number}] Frage", sender="Max Mustermann <max@example.org>"),
            project,
            assigned_by=AssignedBy.TAG,
        )
        announce(mail)
        stored = Notification.objects.filter(user=self.admin_user, project=project).get()
        self.assertEqual(stored.body, "Von Max Mustermann <max@example.org>")
        page = self.assert_ok(self.client.get(reverse("notifications:list")))
        self.assertEqual(page.count("Von Max Mustermann &lt;max@example.org&gt;"), 2)
