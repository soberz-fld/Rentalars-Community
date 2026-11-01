# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages of the correspondence "with lock" or open (EML-055; EML-029, AUT-033).

Requirement: messages of the correspondence can be marked "with lock" (internal and public), which controls whether the crew can
read the message or only those with the finance right. Decided: open for the crew, new messages with a lock.
Correspondence in projects is always confidential, in service cases normally not, because there it is more about fixing faults.

* With lock: who reads the correspondence (as) and sees prices. Open: everybody who reads the
  correspondence, and the crew planned in the project – read only.
* New messages start as the mail settings say – in projects with lock, in service cases open; who may write and sees
  prices chooses and changes it; a writer without the price right writes open messages. Existing messages: those of
  projects get the lock, those of service cases stay open.
* A message one may not read does not exist: lists, pages, attachments, API, search, subrentals, summaries,
  notifications.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, SpecialRight, rights_of
from rentalars.core.models import AuditAction, AuditLogEntry
from rentalars.core.search import global_search
from rentalars.documents import statements
from rentalars.mail import locks, notes
from rentalars.mail.fetching import announce, import_mail
from rentalars.mail.locks import Reach, correspondence_for
from rentalars.mail.models import AssignedBy, ProjectMail
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import service_cases
from tests.api.base import API, ApiTestCase
from tests.helpers import NOW, RentalarsTestCase, at, make_customer, make_person, make_project, make_user, plan
from tests.mailbox import capture_smtp, configure_mailbox, make_mail
from tests.ui.base import UiTestCase, form_data

PDF = b"%PDF-1.4\n%%EOF\n"


def office_role() -> Role:
    """An office role that reads and writes the correspondence of all projects – without the price right."""
    return Role.objects.create(
        name="Büro ohne Preise",
        module_levels={Module.PROJECTS: int(Level.WRITE), Module.EMAIL: int(Level.WRITE)},
        special_rights=[SpecialRight.CORRESPONDENCE_READ, SpecialRight.CORRESPONDENCE_WRITE],
    )


def tabs_of(text: str) -> list[str]:
    """The labels of the tabs of a project page."""
    import re

    start = text.index('<nav class="tabs"')
    return [label.strip() for label in re.findall(r">([^<>]+)</a>", text[start : text.index("</nav>", start)])]


class LockScene:
    """Stadtfest: a mail with lock and an open mail (each with an attachment) and a note with lock.

    paula – Projektleitung (correspondence and prices); lena – office without prices; rita – Nur-Lesen (reads with
    prices); carla – Crew, planned as stagehand; kai – Crew, not planned; and a service case Kai is responsible for.
    """

    def make_scene(self) -> None:
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.paula.first_name, self.paula.last_name = "Paula", "Plan"
        self.paula.save()
        office_role()
        self.lena = make_user("lena", roles=("Büro ohne Preise",))
        self.rita = make_user("rita", roles=("Nur-Lesen",))
        self.carla = make_user("carla", roles=("Crew",))
        self.carla_person = make_person("Carla Crew", user=self.carla)
        self.kai = make_user("kai", roles=("Crew",))
        self.kai_person = make_person("Kai Kurz", user=self.kai)
        self.customer = make_customer()
        self.project = make_project("Stadtfest", customer=self.customer, manager=self.paula)
        # Review: only a confirmed crew line (accepted or firm) reads the open messages – Carla is planned
        # firmly; a line not asked or declined does not count (tests/unit/test_092_review_mail.py).
        plan(self.project, "Stagehand", self.carla_person, start=at(10, 8), end=at(10, 16), firm=True)
        self.secret = import_mail(
            make_mail(
                f"[RL#{self.project.number}] Angebot mit Rabatt",
                text="Wir geben 20 % Rabatt.",
                attachments=[("kalkulation.pdf", "application/pdf", PDF)],
            ),
            self.project,
            assigned_by=AssignedBy.TAG,
        )
        self.open = import_mail(
            make_mail(
                f"[RL#{self.project.number}] Aufbauzeiten",
                text="Aufbau ab 8 Uhr.",
                attachments=[("plan.pdf", "application/pdf", PDF)],
            ),
            self.project,
            assigned_by=AssignedBy.TAG,
        )
        ProjectMail.objects.filter(pk=self.open.pk).update(locked=False)
        self.open.refresh_from_db()
        self.note = notes.add_note(self.project, text="Kunde will Rabatt.", subject="Telefonat Preis", user=self.paula)
        self.case = service_cases.create_case(
            name="Spot flackert", customer=self.customer, manager=self.kai, user=self.paula
        )
        self.case_secret = ProjectMail.objects.create(
            project=self.case,
            direction="in",
            message_key="case-1",
            message_id="<c1@x.example>",
            subject="Reparatur kostet 300 €",
            sender_address="max@stadthalle.example",
            date=at(1, 7),
            text_body="Kosten",
        )
        self.case_open = ProjectMail.objects.create(
            project=self.case,
            direction="in",
            message_key="case-2",
            message_id="<c2@x.example>",
            subject="Spot defekt",
            sender_address="max@stadthalle.example",
            date=at(1, 7, 10),
            text_body="Der Spot flackert.",
            locked=False,
        )


# --- The rule ------------------------------------------------------------------------------------------------


class RuleTests(LockScene, RentalarsTestCase):
    """Who reads, writes and locks what – the rights matrix of the wish."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def access(self, user: Any, project: Any = None) -> locks.Correspondence:
        return correspondence_for(rights_of(user), user, project or self.project)

    def new_messages(self, project: Any) -> list[bool]:
        """The lock of a mail that comes in, a mail written, a note and an inquiry noted by hand and taken over."""
        from rentalars.mail.inquiries import create_manual, take_manual_into
        from rentalars.mail.sending import send_project_mail

        configure_mailbox()
        incoming = import_mail(make_mail(f"Frage {project.pk}"), project, assigned_by=AssignedBy.TAG)
        with capture_smtp():
            sent = send_project_mail(project, to="kunde@example.org", subject="Plan", body="x", user=self.paula)
        note = notes.add_note(project, text="Notiz", user=self.paula)
        inquiry = create_manual(user=self.paula, date=at(1, 7), contact_name="Max", phone="0170", note="Anruf")
        taken = take_manual_into(inquiry, project)
        return [incoming.locked, sent.locked, note.locked, taken.locked]

    def test_new_messages_of_projects_have_the_lock_of_cases_not(self) -> None:
        self.assertTrue(self.secret.locked)  # incoming
        self.assertTrue(self.note.locked)  # a note
        self.assertTrue(ProjectMail(project=self.project).locked)  # the default of the field
        self.assertEqual(self.new_messages(self.project), [True, True, True, True])
        self.assertEqual(self.new_messages(self.case), [False, False, False, False])

    def test_the_defaults_are_settings(self) -> None:
        from rentalars.mail.models import MailSettings

        rules = MailSettings.load()
        self.assertEqual((rules.lock_new_in_projects, rules.lock_new_in_cases), (True, False))
        rules.lock_new_in_projects, rules.lock_new_in_cases = False, True
        rules.save()
        self.assertEqual(self.new_messages(self.project), [False, False, False, False])
        self.assertEqual(self.new_messages(self.case), [True, True, True, True])

    def test_a_case_made_from_a_mail_starts_open(self) -> None:
        from rentalars.mail.aliases import save_address
        from rentalars.mail.fetching import fetch_mail
        from rentalars.mail.models import MailboxAddress, Untagged
        from tests.mailbox import FakeMailbox, mailboxes

        box = configure_mailbox()
        save_address(MailboxAddress(mailbox=box, address="support@verleih.example", untagged=Untagged.SERVICE_CASE))
        raw = make_mail("Spot kaputt", to="support@verleih.example")
        with mailboxes({box.address: FakeMailbox(raw)}):
            fetch_mail(force=True)
        mail = ProjectMail.objects.get(subject="Spot kaputt")
        self.assertTrue(mail.project.is_service_case)
        self.assertFalse(mail.locked)

    def test_a_moved_message_keeps_its_state(self) -> None:
        from rentalars.mail.services import reassign

        reassign(self.case_open, self.project, user=self.paula)
        reassign(self.secret, self.case, user=self.paula)
        self.case_open.refresh_from_db()
        self.secret.refresh_from_db()
        self.assertEqual((self.case_open.locked, self.secret.locked), (False, True))

    def test_the_matrix(self) -> None:
        rows = {
            "paula (correspondence + prices)": (self.paula, Reach.ALL, True, True, True),
            "rita (reads, prices)": (self.rita, Reach.ALL, True, False, False),
            "lena (correspondence, no prices)": (self.lena, Reach.OPEN, True, True, False),
            "carla (crew, planned)": (self.carla, Reach.OPEN, False, False, False),
            "kai (crew, not planned)": (self.kai, Reach.NONE, False, False, False),
        }
        for label, (user, reach, basis, writes, may_lock) in rows.items():
            with self.subTest(label):
                found = self.access(user)
                self.assertEqual(
                    (found.reach, found.basis, found.may_write, found.may_lock), (reach, basis, writes, may_lock)
                )
        self.assertTrue(self.access(self.paula).may_read(self.secret))
        self.assertFalse(self.access(self.lena).may_read(self.secret))
        self.assertTrue(self.access(self.lena).may_read(self.open))
        self.assertFalse(self.access(self.carla).may_read(self.note))
        self.assertEqual(list(self.access(self.carla).readable(self.project.mails.all())), [self.open])

    def test_case_work_reads_and_answers_the_open_messages(self) -> None:
        kai = self.access(self.kai, self.case)
        self.assertEqual((kai.reach, kai.basis, kai.may_write, kai.may_lock), (Reach.OPEN, True, True, False))
        self.assertEqual(list(kai.readable(self.case.mails.all())), [self.case_open])
        # With the price right, working on the case reads those with lock as well – the "Finanz-Sicht".
        self.kai.roles.add(Role.objects.get(name="Nur-Lesen"))
        kai_with_prices = type(self.kai).objects.get(pk=self.kai.pk)
        self.assertEqual(self.access(kai_with_prices, self.case).reach, Reach.ALL)

    def test_a_writer_without_the_price_right_writes_open_messages(self) -> None:
        self.assertFalse(self.access(self.lena).new_lock(None, self.project))
        self.assertTrue(self.access(self.paula).new_lock(None, self.project))
        self.assertFalse(self.access(self.paula).new_lock(None, self.case))  # the default of a service case
        self.assertFalse(self.access(self.paula).new_lock(False, self.project))
        self.assertTrue(self.access(self.paula).new_lock(True, self.case))

    def test_firm_rules_of_a_read_only_token_and_inactive_accounts(self) -> None:
        read_only = rights_of(self.paula).restricted(read_only=True, allowed_modules=[])
        found = correspondence_for(read_only, self.paula, self.project)
        self.assertEqual((found.reach, found.may_write, found.may_lock), (Reach.ALL, False, False))
        self.carla.is_active = False
        self.carla.save()
        carla = type(self.carla).objects.get(pk=self.carla.pk)
        self.assertEqual(self.access(carla).reach, Reach.NONE)

    def test_set_lock_is_in_the_history_of_the_project(self) -> None:
        self.assertTrue(locks.set_lock(self.secret, False, user=self.paula))
        self.assertFalse(locks.set_lock(self.secret, False, user=self.paula))  # no change, nothing noted
        entries = AuditLogEntry.objects.filter(
            object_id=str(self.secret.pk), action=AuditAction.UPDATED, changes__has_key="locked"
        )
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.get().changes["locked"], [True, False])


class NotificationTests(LockScene, RentalarsTestCase):
    """New mails are told to those who read them; taking the lock off tells the crew – once."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        Notification.objects.all().delete()

    def told(self, kind: str = Kind.NEW_MAIL) -> set[str]:
        return set(Notification.objects.filter(kind=kind).values_list("user__username", flat=True))

    def test_a_mail_with_lock_goes_only_to_who_reads_it(self) -> None:
        from rentalars.projects.models import ProjectMembership

        ProjectMembership.objects.create(project=self.project, user=self.lena, level="edit")
        announce(self.secret)
        self.assertEqual(self.told(), {"paula"})  # not lena (no prices), not the crew

    def test_an_open_mail_goes_to_the_crew_as_well(self) -> None:
        announce(self.open)
        self.assertEqual(self.told(), {"paula", "carla"})

    def test_taking_the_lock_off_tells_the_crew_once(self) -> None:
        locks.set_lock(self.secret, False, user=self.paula)
        notice = Notification.objects.get(kind=Kind.NEW_MAIL)
        self.assertEqual(notice.user, self.carla)
        self.assertIn("Neue Nachricht für die Crew", notice.title)
        self.assertIn("Angebot mit Rabatt", notice.title)
        self.assertEqual(notice.url, reverse("mail:detail", args=[self.project, self.secret.pk]))
        locks.set_lock(self.secret, True, user=self.paula)
        locks.set_lock(self.secret, False, user=self.paula)
        self.assertEqual(Notification.objects.filter(kind=Kind.NEW_MAIL).count(), 1)


class ElsewhereTests(LockScene, RentalarsTestCase):
    """Search, subrentals, the monthly statement and the AI."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def hits(self, user: Any, text: str) -> list[str]:
        groups = global_search(text, rights_of(user), user)
        return [hit.title for group in groups if group.kind == "mails" for hit in group.hits]

    def test_the_search(self) -> None:
        self.assertEqual(self.hits(self.paula, "Angebot"), [self.secret.subject])
        self.assertEqual(self.hits(self.lena, "Angebot"), [])
        self.assertEqual(self.hits(self.lena, "Aufbauzeiten"), [self.open.subject])

    def test_the_subrental_page(self) -> None:
        from rentalars.masterdata.models import Supplier
        from rentalars.projects.subrentals import build_page

        supplier = Supplier.objects.create(name="Lichtverleih Nord", email="kunde@stadtwerke.example")
        ProjectMail.objects.filter(project=self.project).update(supplier=supplier)
        subjects = [mail.subject for mail in build_page(self.project, supplier, rights=rights_of(self.lena)).mails]
        self.assertEqual(subjects, [self.open.subject])
        self.assertEqual(len(build_page(self.project, supplier, rights=rights_of(self.paula)).mails), 3)

    def test_the_monthly_statement_needs_the_price_right_anyway(self) -> None:
        """DOK-016: the activity proposal reads the mails of the month – the statement is for who sees prices."""
        self.assertFalse(statements.may_use(rights_of(self.lena)))
        self.assertTrue(statements.may_use(rights_of(self.paula)))
        proposal = statements.activity_proposal(self.case, datetime.date(2027, 3, 1), [], correspondence=True)
        self.assertIn("Reparatur kostet 300 €", proposal)

    def test_ai_reads_all_messages_only_for_who_reads_them(self) -> None:
        from rentalars.mail.services import may_read_all_mail

        self.assertTrue(may_read_all_mail(rights_of(self.paula)))
        self.assertFalse(may_read_all_mail(rights_of(self.lena)))
        self.assertFalse(may_read_all_mail(rights_of(self.carla)))


# --- The pages -----------------------------------------------------------------------------------------------


class LockPageTests(LockScene, UiTestCase):
    """The correspondence on the pages: what each one sees, the lock shown and changed."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.list_url = reverse("mail:project_mails", args=[self.project])

    def test_paula_sees_everything_with_the_lock_shown_and_the_switch(self) -> None:
        browser = self.browser_of(self.paula)
        for view in ("list", "conversation"):
            with self.subTest(view):
                page = self.assert_ok(browser.get(self.list_url, {"view": view}))
                for subject in ("Angebot mit Rabatt", "Aufbauzeiten", "Telefonat Preis"):
                    self.assertIn(subject, page)
                self.assertEqual(page.count('<span class="visually-hidden">mit Schloss</span>'), 2)
                self.assertIn("offen – auch die Crew liest sie", page)
                self.assertIn("Schloss entfernen", page)
                self.assertIn("Schloss setzen", page)
        page = self.assert_ok(browser.get(self.list_url))
        self.assertIn("Nachrichten mit Schloss liest nur, wer Preise und Kalkulation sehen darf", page)
        self.assertIn('id="ai-summary"', page)  # the summary, for who reads all of them

    def test_lena_without_prices_sees_the_open_ones(self) -> None:
        browser = self.browser_of(self.lena)
        page = self.assert_ok(browser.get(self.list_url))
        self.assertIn("Aufbauzeiten", page)
        self.assertNotIn("Angebot mit Rabatt", page)
        self.assertNotIn("Telefonat Preis", page)
        self.assertIn("Du siehst die offenen Nachrichten", page)
        self.assertNotIn("Schloss entfernen", page)
        self.assertNotIn('id="ai-summary"', page)
        for name, args in (
            ("mail:detail", [self.project, self.secret.pk]),
            ("mail:detail", [self.project, self.note.pk]),
            ("mail:body", [self.project, self.secret.pk]),
            ("mail:attachment", [self.project, self.secret.pk, self.secret.attachments.get().pk]),
        ):
            with self.subTest(name):
                self.assertEqual(browser.get(reverse(name, args=args)).status_code, 404)
        self.assert_ok(browser.get(reverse("mail:detail", args=[self.project, self.open.pk])))
        self.assertEqual(
            browser.get(
                reverse("mail:attachment", args=[self.project, self.open.pk, self.open.attachments.get().pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            browser.get(reverse("mail:compose", args=[self.project]), {"answer": self.secret.pk}).status_code, 404
        )
        refused = browser.post(reverse("mail:lock", args=[self.project, self.open.pk]), {"locked": "1"})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(browser.get(reverse("ai:summary", args=[self.project])).status_code, 403)

    def test_lena_writes_open_messages(self) -> None:
        browser = self.browser_of(self.lena)
        form = self.assert_ok(browser.get(reverse("mail:note_create", args=[self.project])))
        self.assertNotIn('name="locked"', form)
        self.assertIn("ohne Schloss gespeichert", form)
        response = browser.post(
            reverse("mail:note_create", args=[self.project]),
            {"date": "2027-03-01T07:30", "subject": "Rückruf", "text": "Kunde ruft zurück.", "locked": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProjectMail.objects.get(subject="Rückruf").locked)

    def test_crew_reads_the_open_messages_of_its_project(self) -> None:
        browser = self.browser_of(self.carla)
        overview = self.assert_ok(browser.get(reverse("projects:deployment", args=[self.project])))
        self.assertIn("Korrespondenz", tabs_of(overview))
        page = self.assert_ok(browser.get(self.list_url))
        self.assertIn("Aufbauzeiten", page)
        for hidden in ("Angebot mit Rabatt", "Telefonat Preis", "Mail schreiben", "Notiz hinzufügen", "Schloss"):
            self.assertNotIn(hidden, page.replace("Du siehst die offenen Nachrichten. Nachrichten mit Schloss", ""))
        self.assert_ok(browser.get(reverse("mail:detail", args=[self.project, self.open.pk])))
        self.assertEqual(browser.get(reverse("mail:detail", args=[self.project, self.secret.pk])).status_code, 404)
        for name in ("mail:compose", "mail:note_create"):
            self.assertEqual(browser.get(reverse(name, args=[self.project])).status_code, 403, name)
        self.assertEqual(
            browser.post(reverse("mail:lock", args=[self.project, self.open.pk]), {"locked": "1"}).status_code, 403
        )
        # Not planned: the project does not exist for Kai.
        self.assertEqual(self.browser_of(self.kai).get(self.list_url).status_code, 404)

    def test_paula_takes_the_lock_off_and_puts_it_on(self) -> None:
        browser = self.browser_of(self.paula)
        done = browser.post(
            reverse("mail:lock", args=[self.project, self.secret.pk]),
            {"locked": "0", "next": self.list_url},
            follow=True,
        )
        self.assertRedirects(done, self.list_url)
        self.assertIn("Das Schloss ist entfernt", " ".join(self.messages_of(done)))
        self.secret.refresh_from_db()
        self.assertFalse(self.secret.locked)
        self.assertIn("Angebot mit Rabatt", self.assert_ok(self.browser_of(self.carla).get(self.list_url)))
        self.assertTrue(Notification.objects.filter(user=self.carla, kind=Kind.NEW_MAIL).exists())
        detail = self.assert_ok(browser.get(reverse("mail:detail", args=[self.project, self.secret.pk])))
        self.assertIn("Offen:", detail)
        browser.post(
            reverse("mail:lock", args=[self.project, self.secret.pk]), {"locked": "1", "next": "//evil.example"}
        )
        self.secret.refresh_from_db()
        self.assertTrue(self.secret.locked)
        note = self.assert_ok(browser.get(reverse("mail:detail", args=[self.project, self.note.pk])))
        self.assertIn("Mit Schloss:", note)
        self.assertIn("Schloss entfernen", note)

    def test_writing_with_the_choice(self) -> None:
        configure_mailbox()
        browser = self.browser_of(self.paula)
        url = reverse("mail:compose", args=[self.project])
        page = browser.get(url, {"answer": self.open.pk})
        text = self.assert_ok(page)
        self.assertIn('name="locked"', text)
        self.assertIn("Mit Schloss", text)
        data = form_data(page, containing="body", body="Gern.")
        self.assertEqual(data.get("locked"), "on")  # ticked at first
        with capture_smtp():
            browser.post(f"{url}?answer={self.open.pk}", data)
        self.assertTrue(ProjectMail.objects.filter(direction="out").get().locked)
        data.pop("locked")
        with capture_smtp():
            browser.post(f"{url}?answer={self.open.pk}", {**data, "subject": "Zweite Antwort"})
        self.assertFalse(ProjectMail.objects.get(subject__contains="Zweite Antwort").locked)
        note_url = reverse("mail:note_create", args=[self.project])
        form = self.assert_ok(browser.get(note_url))
        self.assertIn('name="locked"', form)
        browser.post(note_url, {"date": "2027-03-01T07:30", "text": "Offen für alle."})
        self.assertFalse(ProjectMail.objects.get(text_body="Offen für alle.").locked)

    def test_the_choice_starts_with_the_default_of_project_or_case(self) -> None:
        configure_mailbox()
        browser = self.browser_of(self.paula)
        project_form = form_data(browser.get(reverse("mail:compose", args=[self.project])), containing="body")
        self.assertEqual(project_form.get("locked"), "on")
        case_form = form_data(browser.get(reverse("mail:compose", args=[self.case])), containing="body")
        self.assertNotIn("locked", case_form)  # offered, not ticked
        self.assertIn('name="locked"', self.assert_ok(browser.get(reverse("mail:compose", args=[self.case]))))
        note_form = form_data(browser.get(reverse("mail:note_create", args=[self.case])), containing="text")
        self.assertNotIn("locked", note_form)

    def test_the_settings_page(self) -> None:
        from rentalars.mail.models import MailSettings

        url = reverse("mail:settings")
        page = self.client.get(url)
        text = self.assert_ok(page)
        self.assertIn("Neue Nachrichten in Projekten: mit Schloss", text)
        self.assertIn("Neue Nachrichten in Servicefällen: mit Schloss", text)
        data = form_data(page, containing="interval_minutes")
        self.assertEqual(data.get("lock_new_in_projects"), "on")
        self.assertNotIn("lock_new_in_cases", data)
        data["lock_new_in_cases"] = "on"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertTrue(MailSettings.load().lock_new_in_cases)

    def test_the_case_page_and_case_work(self) -> None:
        browser = self.browser_of(self.kai)
        page = self.assert_ok(browser.get(reverse("projects:case_detail", args=[self.case])))
        self.assertIn("Spot defekt", page)
        self.assertNotIn("Reparatur kostet", page)
        mails = self.assert_ok(browser.get(reverse("mail:project_mails", args=[self.case])))
        self.assertNotIn("Reparatur kostet", mails)
        compose = reverse("mail:compose", args=[self.case])
        self.assertEqual(browser.get(compose, {"answer": self.case_secret.pk}).status_code, 404)
        self.assert_ok(browser.get(compose, {"answer": self.case_open.pk}))
        self.client.force_login(self.paula)
        self.assertIn(
            "Reparatur kostet", self.assert_ok(self.client.get(reverse("projects:case_detail", args=[self.case])))
        )


# --- The API -------------------------------------------------------------------------------------------------


class LockApiTests(LockScene, ApiTestCase):
    """The same rule in the API – what the companion app syncs (API-002, API-014)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.base = f"{API}/projects/{self.project.pk}/mails"

    def test_lists_carry_locked_and_hold_what_the_caller_reads(self) -> None:
        paula = self.client_of(self.paula).get(self.base).json()
        self.assertEqual({row["subject"]: row["locked"] for row in paula}[self.open.subject], False)
        self.assertEqual(len(paula), 3)
        for user in (self.lena, self.carla):
            with self.subTest(user.username):
                listed = self.client_of(user).get(self.base).json()
                self.assertEqual([row["id"] for row in listed], [self.open.pk])
        crew = self.client_of(self.carla)
        self.assertEqual(crew.get(f"{self.base}/{self.secret.pk}").status_code, 404)
        self.assertEqual(crew.get(f"{self.base}/{self.open.pk}").status_code, 200)
        attachment = self.secret.attachments.get()
        self.assertEqual(crew.get(f"{self.base}/{self.secret.pk}/attachments/{attachment.pk}").status_code, 404)
        self.assertEqual(self.client_of(self.kai).get(self.base).status_code, 404)

    def test_patch_the_lock(self) -> None:
        url = f"{self.base}/{self.secret.pk}/lock"
        changed = self.client_of(self.paula).patch(url, {"locked": False}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertFalse(changed.json()["locked"])
        self.assertTrue(Notification.objects.filter(user=self.carla, kind=Kind.NEW_MAIL).exists())
        self.assert_error(
            self.client_of(self.paula).patch(url, {"locked": "ja"}, format="json"), 400, "validation_error"
        )
        for user in (self.lena, self.carla, self.rita):
            with self.subTest(user.username):
                self.assert_error(
                    self.client_of(user).patch(url, {"locked": True}, format="json"), 403, "permission_denied"
                )
        # Locked again, it is gone for those without the price right.
        self.client_of(self.paula).patch(url, {"locked": True}, format="json")
        self.assertEqual(self.client_of(self.lena).patch(url, {"locked": False}, format="json").status_code, 404)

    def test_notes_and_mails_take_locked(self) -> None:
        paula = self.client_of(self.paula)
        default = paula.post(f"{self.base}/notes", {"text": "Mit Schloss"}, format="json")
        self.assertEqual(default.status_code, 201, default.content)
        self.assertTrue(default.json()["locked"])
        open_note = paula.post(f"{self.base}/notes", {"text": "Offen", "locked": False}, format="json")
        self.assertFalse(open_note.json()["locked"])
        lena = self.client_of(self.lena)
        self.assertFalse(lena.post(f"{self.base}/notes", {"text": "Von Lena"}, format="json").json()["locked"])
        self.assert_error(
            lena.post(f"{self.base}/notes", {"text": "Mit Schloss?", "locked": True}, format="json"),
            403,
            "permission_denied",
        )
        configure_mailbox()
        with capture_smtp():
            sent = paula.post(
                self.base, {"to": "kunde@example.org", "subject": "Plan", "body": "x", "locked": False}, format="json"
            )
        self.assertEqual(sent.status_code, 201, sent.content)
        self.assertFalse(sent.json()["locked"])
        with capture_smtp():
            answer = lena.post(
                self.base,
                {"to": "kunde@example.org", "subject": "Antwort", "body": "x", "answer_to": self.secret.pk},
                format="json",
            )
        self.assertEqual(answer.status_code, 404)  # a mail with lock cannot be answered without reading it

    def test_the_defaults_in_the_mail_settings(self) -> None:
        url = f"{API}/mail/settings"
        found = self.admin.get(url).json()
        self.assertEqual((found["lock_new_in_projects"], found["lock_new_in_cases"]), (True, False))
        changed = self.admin.patch(url, {"lock_new_in_cases": True}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertTrue(changed.json()["lock_new_in_cases"])
        note = self.client_of(self.paula).post(
            f"{API}/projects/{self.case.pk}/mails/notes", {"text": "Mit Schloss im Fall"}, format="json"
        )
        self.assertTrue(note.json()["locked"])

    def test_summaries_and_drafts_for_who_reads_everything(self) -> None:
        url = f"{API}/projects/{self.project.pk}/correspondence-summary"
        self.assertEqual(self.client_of(self.paula).get(url).status_code, 200)
        self.assert_error(self.client_of(self.lena).get(url), 403, "permission_denied")
        self.assert_error(self.client_of(self.carla).get(url), 403, "permission_denied")
        draft = f"{self.base}/reply-draft"
        self.assert_error(self.client_of(self.lena).post(draft, {}, format="json"), 403, "permission_denied")


# --- The update ----------------------------------------------------------------------------------------------


class MigrationTests(TransactionTestCase):
    """The update: messages of projects get the lock, those of service cases stay open."""

    # NFA-077: the old migrations are squashed; mail 0013 is part of this one.
    before = [("mail", "0001_squashed_0013_senders_signatures_inquiries_090")]
    after = [("mail", "0014_locked_092")]

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrate(self, targets: list[tuple[str, str]]) -> Any:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_projects_with_lock_service_cases_open(self) -> None:
        project = make_project("Altprojekt")
        case = service_cases.create_case(name="Altfall")
        old = self.migrate(self.before)
        mails = old.get_model("mail", "ProjectMail").objects
        for index, direction in enumerate(("in", "out", "note")):
            mails.create(project_id=project.pk, direction=direction, message_key=f"p{index}", date=NOW, subject="P")
            mails.create(project_id=case.pk, direction=direction, message_key=f"c{index}", date=NOW, subject="C")
        new = self.migrate(self.after)
        found = new.get_model("mail", "ProjectMail").objects
        self.assertEqual(set(found.filter(project_id=project.pk).values_list("locked", flat=True)), {True})
        self.assertEqual(set(found.filter(project_id=case.pk).values_list("locked", flat=True)), {False})
        rules = new.get_model("mail", "MailSettings")(pk=1)
        self.assertEqual((rules.lock_new_in_projects, rules.lock_new_in_cases), (True, False))
