# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "communication": the chat in the project (UIX-010) and automations with triggers (ADM-013).

UIX-010
    Who reads the chat (everybody who can open the project, the crew with the
    deployment view included), mentions with ``@`` and their notification,
    changing and deleting within 15 minutes, the unread count and the stamp
    of the change polling (UIX-020).
ADM-013
    The four triggers – a mail without project tag, a project status, an
    answer to a deployment request, a due follow-up – and the three actions:
    answer by mail, notify, note an open item. The protection against loops
    of the answer by mail (Auto-Submitted, Precedence, lists, mail systems,
    own addresses, once per sender, rule and day), the outgoing headers, the
    mail log, the runs, the checks of a rule.
"""

from __future__ import annotations

import datetime
from email import message_from_bytes, policy
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import RequestFactory

from rentalars.accounts.models import User
from rentalars.automations import engine
from rentalars.automations.models import Action, Automation, AutomationRun, Recipient, RunStatus, Trigger
from rentalars.chat import services as chat
from rentalars.chat.models import ChatMessage
from rentalars.core.changes import stamps, watch_keys
from rentalars.core.models import CompanyProfile
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.mailboxes import delete_mailbox
from rentalars.mail.models import LogKind, LogResult, MailLogEntry
from rentalars.mail.parsing import automatic_reason, parse_headers
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import crew, services
from rentalars.projects.access import ProjectAccess, access_level
from rentalars.projects.follow_up import notify_due_follow_ups, set_follow_up
from rentalars.projects.models import OpenItem, ProjectAccessLevel, ProjectMembership, ProjectStatus
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, at, make_person, make_project, make_user, plan, set_clock
from tests.mailbox import FakeMailbox, add_mailbox, capture_smtp, configure_mailbox, mailbox, mailboxes, make_mail

# --- UIX-010: the chat ----------------------------------------------------------------------------------


class ChatTestCase(RentalarsTestCase):
    """A project, its manager, a crew member planned in it, and an outsider of the crew."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("lena", roles=("Projektleitung",))
        self.manager.first_name, self.manager.last_name = "Lena", "Krause"
        self.manager.save()
        self.project = make_project(manager=self.manager)
        self.crew_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", user=self.crew_user)
        self.crew_user.refresh_from_db()
        plan(self.project, "Tontechnik", self.anna)
        self.outsider = make_user("otto", roles=("Crew",))
        make_person("Otto Weber", user=self.outsider)
        self.outsider.refresh_from_db()


class ReadersTests(ChatTestCase):
    """UIX-010: everybody who can open the project reads the chat – the same rules as AUT-025."""

    def test_the_same_users_as_the_access_rules(self) -> None:
        member = make_user("mia", roles=("Crew",))
        ProjectMembership.objects.create(project=self.project, user=member, level=ProjectAccessLevel.READ)
        make_user("root", superuser=True)
        gone = make_user("gone", roles=("Projektleitung",))
        gone.is_active = False
        gone.save()
        readers = {user.username: user for user in chat.readers_of(self.project)}
        for user in User.objects.all():
            expected = user.is_active and access_level(user.rights, user, self.project) >= ProjectAccess.DEPLOYMENT
            self.assertEqual(user.username in readers, expected, user.username)
        self.assertEqual(readers["anna"].chat_access, ProjectAccess.DEPLOYMENT)
        # AUT-031 (requirement): the role "Crew" opens the overview only, whatever its membership says.
        # The chat follows access_level, as the loop above checks.
        self.assertEqual(readers["mia"].chat_access, ProjectAccess.DEPLOYMENT)
        self.assertNotIn("otto", readers)

    def test_a_subproject_takes_the_membership_of_its_whole_project(self) -> None:
        member = make_user("mia", roles=("Crew",))
        ProjectMembership.objects.create(project=self.project, user=member, level=ProjectAccessLevel.DEPLOYMENT)
        part = services.create_subproject(self.project, name="Bühne 2")
        self.assertIn("mia", [user.username for user in chat.readers_of(part)])
        # The crew line counts only in its own project.
        self.assertNotIn("anna", [user.username for user in chat.readers_of(part)])

    def test_display_name(self) -> None:
        self.assertEqual(chat.display_name(self.manager), "Lena Krause")
        self.assertEqual(chat.display_name(make_user("bob")), "bob")


class MentionTests(ChatTestCase):
    """UIX-010: ``@Name`` or ``@username`` mentions a reader, who is notified once."""

    def test_mention_by_name_and_by_user_name(self) -> None:
        message = chat.post_message(self.project, user=self.manager, text="@Anna Becker bitte Kabel mitbringen")
        self.assertEqual([user.username for user in message.mentioned.all()], ["anna"])
        notification = Notification.objects.get(kind=Kind.CHAT_MENTION)
        self.assertEqual(notification.user, self.crew_user)
        self.assertEqual(notification.title, f"Lena Krause hat dich im Chat von {self.project} erwähnt")
        self.assertEqual(notification.url, f"/projects/{self.project.number}/chat/#m{message.pk}")
        self.assertEqual(notification.body, "@Anna Becker bitte Kabel mitbringen")
        chat.post_message(self.project, user=self.crew_user, text="ok @lena")
        self.assertTrue(Notification.objects.filter(kind=Kind.CHAT_MENTION, user=self.manager).exists())

    def test_a_longer_name_blocks_a_shorter_one_and_mail_addresses_mention_nobody(self) -> None:
        anna_user = make_user("anna2", roles=("Projektleitung",))  # another user, called just "Anna"
        anna_user.first_name = "Anna"
        anna_user.save()
        found = chat.mentioned_in("Hallo @Anna Becker, schreib an info@anna", chat.readers_of(self.project))
        self.assertEqual([user.pk for user in found], [self.crew_user.pk])
        found = chat.mentioned_in("@anna und @Anna Becker", chat.readers_of(self.project))
        self.assertEqual({user.pk for user in found}, {self.crew_user.pk, anna_user.pk})

    def test_nobody_outside_the_project_and_not_oneself(self) -> None:
        chat.post_message(self.project, user=self.manager, text="@Otto Weber @Lena Krause hallo")
        self.assertFalse(Notification.objects.filter(kind=Kind.CHAT_MENTION).exists())

    def test_changing_notifies_only_the_new_ones(self) -> None:
        mia = make_user("mia", roles=("Projektleitung",))
        message = chat.post_message(self.project, user=self.manager, text="@anna Kabel?")
        chat.edit_message(message, user=self.manager, text="@anna Kabel? @mia auch")
        notified = list(Notification.objects.filter(kind=Kind.CHAT_MENTION).values_list("user__username", flat=True))
        self.assertEqual(sorted(notified), ["anna", "mia"])
        self.assertEqual(set(message.mentioned.values_list("pk", flat=True)), {self.crew_user.pk, mia.pk})


class WritingTests(ChatTestCase):
    """UIX-010: own messages can be changed or deleted for 15 minutes; empty and too long ones are refused."""

    def test_change_within_the_minutes(self) -> None:
        message = chat.post_message(self.project, user=self.crew_user, text="Bin um 8 da")
        set_clock(at(1, 8, 15))
        chat.edit_message(message, user=self.crew_user, text="Bin um 9 da")
        message.refresh_from_db()
        self.assertEqual((message.text, message.edited_at), ("Bin um 9 da", at(1, 8, 15)))
        set_clock(at(1, 8, 16))
        self.assertFalse(chat.can_change(message, self.crew_user))
        with self.assertRaises(ValidationError):
            chat.edit_message(message, user=self.crew_user, text="Doch 10")
        with self.assertRaises(ValidationError):
            chat.delete_message(message, user=self.crew_user)

    def test_only_the_author(self) -> None:
        message = chat.post_message(self.project, user=self.crew_user, text="Hallo")
        with self.assertRaises(PermissionDenied):
            chat.edit_message(message, user=self.manager, text="Anders")
        with self.assertRaises(PermissionDenied):
            chat.delete_message(message, user=self.manager)
        chat.delete_message(message, user=self.crew_user)
        self.assertFalse(ChatMessage.objects.exists())

    def test_empty_and_too_long(self) -> None:
        with self.assertRaises(ValidationError):
            chat.post_message(self.project, user=self.manager, text="   \n ")
        with self.assertRaises(ValidationError):
            chat.post_message(self.project, user=self.manager, text="x" * 4001)
        message = chat.post_message(self.project, user=self.manager, text="  Zeile 1\r\nZeile 2  ")
        self.assertEqual(message.text, "Zeile 1\nZeile 2")
        self.assertEqual(message.author_name, "Lena Krause")

    def test_an_anonymised_person_is_not_named_any_more(self) -> None:
        """NFA-009: the chat and the runs of automations forget the name of an anonymised person."""
        from rentalars.personnel.privacy import anonymise_person

        message = chat.post_message(self.project, user=self.crew_user, text="Bin da")
        run = AutomationRun.objects.create(
            automation_name="x",
            trigger=Trigger.CREW_ANSWER,
            action=Action.NOTIFY,
            event_key="k",
            event="2027-0001 Stadtfest: Absage – Anna Becker",
            data={"values": {"person": "Anna Becker"}},
        )
        self.assertEqual(message.author_name, "Anna Becker")
        anonymise_person(self.anna)
        message.refresh_from_db()
        run.refresh_from_db()
        self.assertEqual(message.author_name, f"Anonymisiert ({self.anna.pk})")
        self.assertEqual(run.event, f"2027-0001 Stadtfest: Absage – Anonymisiert ({self.anna.pk})")
        self.assertEqual(run.data, {})

    def test_pages_of_messages(self) -> None:
        for number in range(5):
            chat.post_message(self.project, user=self.manager, text=f"Nachricht {number}")
        page = chat.messages_of(self.project, limit=3)
        self.assertEqual([message.text for message in page.messages], ["Nachricht 2", "Nachricht 3", "Nachricht 4"])
        self.assertTrue(page.has_older)
        older = chat.messages_of(self.project, before=page.messages[0].pk, limit=3)
        self.assertEqual([message.text for message in older.messages], ["Nachricht 0", "Nachricht 1"])
        self.assertFalse(older.has_older)


class UnreadTests(ChatTestCase):
    """UIX-010: messages of others after the mark are unread; the change polling carries the count."""

    def test_unread_and_read(self) -> None:
        chat.post_message(self.project, user=self.manager, text="Eins")
        chat.post_message(self.project, user=self.manager, text="Zwei")
        self.assertEqual(chat.unread_count(self.project, self.crew_user), 2)
        self.assertEqual(chat.unread_count(self.project, self.manager), 0)
        chat.mark_read(self.project, self.crew_user)
        self.assertEqual(chat.unread_count(self.project, self.crew_user), 0)
        # Writing oneself reads the chat up to one's own message.
        third = chat.post_message(self.project, user=self.manager, text="Drei")
        chat.post_message(self.project, user=self.crew_user, text="Gelesen")
        self.assertEqual(chat.unread_count(self.project, self.crew_user), 0)
        self.assertEqual(chat.unread_count(self.project, self.manager), 1)
        # An older mark never moves back.
        self.assertEqual(chat.mark_read(self.project, self.manager, up_to=1), third.pk)
        self.assertEqual(chat.unread_count(self.project, self.manager), 1)

    def test_stamp_of_the_change_polling(self) -> None:
        empty = chat.stamp(self.project.pk, self.crew_user)
        self.assertEqual(empty, "0-0-0~0")
        message = chat.post_message(self.project, user=self.manager, text="Eins")
        first = chat.stamp(self.project.pk, self.crew_user)
        self.assertEqual(first, f"{message.pk}-1-0~1")
        set_clock(at(1, 8, 5))
        chat.edit_message(message, user=self.manager, text="Eins!")
        changed = chat.stamp(self.project.pk, self.crew_user)
        self.assertNotEqual(changed.split("~")[0], first.split("~")[0])
        self.assertTrue(changed.endswith("~1"))

    def test_the_key_on_every_project_page_and_its_rights(self) -> None:
        request = RequestFactory().get(f"/projects/{self.project.number}/deployment/")
        from django.urls import resolve

        request.resolver_match = resolve(request.path)
        self.assertEqual(
            watch_keys(request), ["notifications", f"project:{self.project.pk}", f"chat:{self.project.pk}"]
        )
        request = RequestFactory().get(f"/projects/{self.project.number}/chat/")
        request.resolver_match = resolve(request.path)
        self.assertIn(f"project:{self.project.pk}", watch_keys(request))
        chat.post_message(self.project, user=self.manager, text="Eins")
        key = f"chat:{self.project.pk}"
        self.assertTrue(stamps([key], self.crew_user)[key].endswith("~1"))
        self.assertEqual(stamps([key], self.outsider)[key], "")

    def test_a_message_does_not_reload_the_other_pages(self) -> None:
        key = f"project:{self.project.pk}"
        before = stamps([key], self.crew_user)[key]
        chat.post_message(self.project, user=self.manager, text="Eins")
        self.assertEqual(stamps([key], self.crew_user)[key], before)


# --- ADM-013: automations ------------------------------------------------------------------------------


def reply_rule(**fields: object) -> Automation:
    """A confirmation of receipt for every inquiry."""
    values = {
        "name": "Eingangsbestätigung",
        "trigger": Trigger.INQUIRY,
        "action": Action.REPLY,
        "subject": "Eingangsbestätigung: {betreff}",
        "text": "Hallo {name},\n\ndanke für deine Mail an {postfach}.\n\n{firma}",
        **fields,
    }
    rule = Automation(**values)
    rule.normalise()
    assert not rule.problems(), rule.problems()
    rule.save()
    return rule


class InquiryAnswerTests(RentalarsTestCase):
    """ADM-013: an inquiry gets a confirmation of receipt – marked as automatic, noted in the mail log."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.name, profile.email = "Licht & Ton GmbH", "info@licht-ton.example"
        profile.save()
        self.box = configure_mailbox(process_untagged=True)
        self.rule = reply_rule()

    def fetch(self, *mails: bytes) -> list:
        with mailbox(*mails), capture_smtp() as sent, self.captureOnCommitCallbacks(execute=True):
            fetch_mail(force=True)
        return sent

    def test_the_answer(self) -> None:
        sent = self.fetch(
            make_mail(
                "Anfrage Stadtfest",
                sender="Kunde Müller <kunde@stadtwerke.example>",
                message_id="<abc@stadtwerke.example>",
            )
        )
        self.assertEqual(len(sent), 1)
        answer = sent[0]
        self.assertEqual(answer.mailbox, self.box)
        self.assertEqual(answer["To"], "Kunde Müller <kunde@stadtwerke.example>")
        self.assertEqual(answer["From"], "Verleih Projekte <projekte@verleih.example>")
        self.assertEqual(answer["Subject"], "Eingangsbestätigung: Anfrage Stadtfest")
        self.assertEqual(answer["Auto-Submitted"], "auto-replied")
        self.assertEqual(answer["X-Auto-Response-Suppress"], "All")
        self.assertEqual(answer["In-Reply-To"], "<abc@stadtwerke.example>")
        self.assertEqual(answer["References"], "<abc@stadtwerke.example>")
        body = answer.get_content()
        self.assertIn("Hallo Kunde Müller,\n\ndanke für deine Mail an Projekte.\n\nLicht & Ton GmbH", body)
        self.assertIn("-- \nDiese Nachricht wurde automatisch von Rentalars für Licht & Ton GmbH versendet", body)
        run = AutomationRun.objects.get()
        self.assertEqual((run.status, run.recipient), (RunStatus.DONE, "kunde@stadtwerke.example"))
        self.assertEqual(run.event, "Mail von kunde@stadtwerke.example: Anfrage Stadtfest")
        self.assertEqual(run.detail, "Beantwortet über das Postfach „Projekte“.")
        entry = MailLogEntry.objects.get(kind=LogKind.AUTOMATIC)
        self.assertEqual(
            (entry.result, entry.mailbox, entry.recipients), (LogResult.SENT, self.box, "kunde@stadtwerke.example")
        )
        self.assertEqual(entry.detail, "Eingangsbestätigung")
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.INQUIRY).subject, "Anfrage Stadtfest")

    def test_reply_to_wins_and_an_empty_subject_is_aw(self) -> None:
        self.rule.subject = ""
        self.rule.save()
        sent = self.fetch(
            make_mail("Kontaktformular", sender="formular@web.example", headers={"Reply-To": "Bea <bea@x.example>"})
        )
        self.assertEqual(sent[0]["To"], "Bea <bea@x.example>")
        self.assertEqual(sent[0]["Subject"], "AW: Kontaktformular")

    def test_never_an_answer_to_automatic_mails(self) -> None:
        cases = {
            "Auto-Submitted": ("Abwesend", "kunde1@x.example", {"Auto-Submitted": "auto-replied"}),
            "Precedence": ("Newsletter", "kunde2@x.example", {"Precedence": "bulk"}),
            "List-Id": ("Liste", "kunde3@x.example", {"List-Id": "<info.lists.example>"}),
            "Suppress": ("Outlook", "kunde4@x.example", {"X-Auto-Response-Suppress": "OOF, AutoReply"}),
            "mailer-daemon": ("Unzustellbar", "MAILER-DAEMON@x.example", {}),
            "no-reply": ("Bestellung", "no-reply@shop.example", {}),
            "own mailbox": ("Schleife", "projekte@verleih.example", {}),
            "own company": ("Firma", "info@licht-ton.example", {}),
        }
        mails = [make_mail(subject, sender=sender, headers=headers) for subject, sender, headers in cases.values()]
        self.assertEqual(self.fetch(*mails), [])
        runs = {run.event.split(": ", 1)[1]: run for run in AutomationRun.objects.all()}
        self.assertEqual(len(runs), len(cases))
        for subject, _sender, _headers in cases.values():
            with self.subTest(subject):
                self.assertEqual(runs[subject].status, RunStatus.SKIPPED)
        self.assertIn("Auto-Submitted: auto-replied", runs["Abwesend"].detail)
        self.assertIn("Precedence: bulk", runs["Newsletter"].detail)
        self.assertIn("mailer-daemon@x.example ist ein Mailsystem", runs["Unzustellbar"].detail)
        self.assertIn("eine Adresse von Rentalars selbst", runs["Firma"].detail)
        self.assertFalse(MailLogEntry.objects.filter(kind=LogKind.AUTOMATIC).exists())

    def test_once_per_sender_rule_and_day(self) -> None:
        self.assertEqual(len(self.fetch(make_mail("Erste"), make_mail("Zweite"))), 1)
        second = AutomationRun.objects.get(event__endswith="Zweite")
        self.assertEqual(second.status, RunStatus.SKIPPED)
        self.assertEqual(
            second.detail, "kunde@stadtwerke.example hat heute schon eine Antwort dieser Automation bekommen."
        )
        # Another rule may answer the same sender; the next day the first one again.
        reply_rule(name="Zweite Regel", subject="Danke")
        self.assertEqual([mail["Subject"] for mail in self.fetch(make_mail("Dritte"))], ["Danke"])
        set_clock(at(2, 7))
        self.assertEqual(len(self.fetch(make_mail("Vierte"))), 2)

    def test_the_same_mail_in_two_mailboxes_is_one_event(self) -> None:
        add_mailbox("Info", "info@verleih.example", process_untagged=True)
        raw = make_mail("Anfrage", message_id="<one@x.example>")
        with (
            mailboxes({"projekte@verleih.example": FakeMailbox(raw), "info@verleih.example": FakeMailbox(raw)}),
            capture_smtp() as sent,
            self.captureOnCommitCallbacks(execute=True),
        ):
            fetch_mail(force=True)
        self.assertEqual(len(sent), 1)
        self.assertEqual(AutomationRun.objects.count(), 1)

    def test_only_the_chosen_mailbox_and_its_own_smtp(self) -> None:
        info = add_mailbox("Info", "info@verleih.example", process_untagged=True)
        self.rule.mailbox = info
        self.rule.save()
        with (
            mailboxes(
                {
                    "projekte@verleih.example": FakeMailbox(make_mail("In Projekte")),
                    "info@verleih.example": FakeMailbox(make_mail("In Info")),
                }
            ),
            capture_smtp() as sent,
            self.captureOnCommitCallbacks(execute=True),
        ):
            fetch_mail(force=True)
        self.assertEqual([mail["Subject"] for mail in sent], ["Eingangsbestätigung: In Info"])
        self.assertEqual(sent[0].mailbox, info)
        self.assertEqual(sent[0]["From"], "Verleih Projekte <info@verleih.example>")

    def test_a_mailbox_without_smtp_answers_through_the_one_that_sends(self) -> None:
        info = add_mailbox("Info", "info@verleih.example", process_untagged=True, smtp_host="")
        with (
            mailboxes(
                {"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(make_mail("Hallo"))}
            ),
            capture_smtp() as sent,
            self.captureOnCommitCallbacks(execute=True),
        ):
            fetch_mail(force=True)
        self.assertEqual(sent[0].mailbox, self.box)
        self.assertNotEqual(sent[0].mailbox, info)

    def test_a_failure_is_noted(self) -> None:
        def refuse(mailbox: object, message: object) -> None:
            raise ValidationError("Der Mailserver hat die Anmeldung zum Senden abgelehnt.")

        with (
            mailbox(make_mail("Anfrage")),
            mock.patch("rentalars.mail.sending._send", refuse),
            self.captureOnCommitCallbacks(execute=True),
        ):
            fetch_mail(force=True)
        run = AutomationRun.objects.get()
        self.assertEqual(
            (run.status, run.detail), (RunStatus.FAILED, "Der Mailserver hat die Anmeldung zum Senden abgelehnt.")
        )
        entry = MailLogEntry.objects.get(kind=LogKind.AUTOMATIC)
        self.assertEqual(entry.result, LogResult.FAILED)

    def test_switched_off_and_mailboxes_that_leave_mails_alone(self) -> None:
        self.rule.is_active = False
        self.rule.save()
        self.assertEqual(self.fetch(make_mail("Anfrage")), [])
        self.assertFalse(AutomationRun.objects.exists())
        self.rule.is_active = True
        self.rule.save()
        self.box.process_untagged = False
        self.box.save()
        self.assertEqual(self.fetch(make_mail("Noch eine")), [])
        self.assertFalse(AutomationRun.objects.exists())


class AutomaticHeaderTests(RentalarsTestCase):
    """ADM-013: which headers mark a mail as sent automatically (RFC 3834)."""

    def reason(self, **headers: str) -> str:
        return automatic_reason(message_from_bytes(make_mail("Test", headers=headers), policy=policy.default))

    def test_reasons(self) -> None:
        self.assertEqual(self.reason(), "")
        self.assertEqual(self.reason(**{"Auto-Submitted": "no"}), "")
        self.assertEqual(self.reason(**{"Auto-Submitted": "auto-generated"}), "Auto-Submitted: auto-generated")
        self.assertEqual(self.reason(Precedence="junk"), "Precedence: junk")
        self.assertEqual(self.reason(Precedence="first-class"), "")
        self.assertEqual(self.reason(**{"List-Unsubscribe": "<mailto:x@y>"}), "List-Unsubscribe: <mailto:x@y>")
        self.assertEqual(self.reason(**{"X-Autoreply": "yes"}), "X-Autoreply: yes")
        self.assertEqual(self.reason(**{"Return-Path": "<>"}), "Return-Path: <>")
        self.assertEqual(self.reason(**{"X-Auto-Response-Suppress": "DR"}), "")

    def test_the_fetch_asks_for_these_headers(self) -> None:
        from rentalars.mail.imap import HEADER_FIELDS

        for name in ("REPLY-TO", "AUTO-SUBMITTED", "PRECEDENCE", "LIST-ID", "RETURN-PATH", "X-AUTO-RESPONSE-SUPPRESS"):
            self.assertIn(name, HEADER_FIELDS.split())
        headers = parse_headers(make_mail("Test", headers={"Reply-To": "a@b.example", "Precedence": "list"}))
        self.assertEqual((headers.reply_to, headers.automatic), ("a@b.example", "Precedence: list"))


class ProjectTriggerTests(RentalarsTestCase):
    """ADM-013: a status, an answer, a follow-up – notify and note an open item."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("lena", roles=("Projektleitung",))
        self.office = make_user("bea", roles=("Projektleitung",))
        self.project = make_project(status=ProjectStatus.OPTION, manager=self.manager)

    def rule(self, trigger: str, action: str, **fields: object) -> Automation:
        rule = Automation(name=f"{trigger} {action}", trigger=trigger, action=action, **fields)
        rule.normalise()
        self.assertEqual(rule.problems(), {})
        rule.save()
        return rule

    def test_status_notifies_and_notes(self) -> None:
        self.rule(
            Trigger.PROJECT_STATUS,
            Action.NOTIFY,
            status=ProjectStatus.CONFIRMED,
            recipient=Recipient.USER,
            user=self.office,
            subject="{projekt} ist {status}",
            text="Lager vorbereiten. {link}",
        )
        self.rule(
            Trigger.PROJECT_STATUS,
            Action.OPEN_ITEM,
            status=ProjectStatus.CONFIRMED,
            text="Rechnungsadresse prüfen ({projektleitung})",
        )
        self.rule(Trigger.PROJECT_STATUS, Action.NOTIFY, status=ProjectStatus.CANCELLED, recipient=Recipient.MANAGER)
        with self.captureOnCommitCallbacks(execute=True):
            services.change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        notification = Notification.objects.get(kind=Kind.AUTOMATION)
        self.assertEqual(notification.user, self.office)
        self.assertEqual(notification.title, f"{self.project.number} Stadtfest ist Bestätigt")
        self.assertIn(f"/projects/{self.project.number}/", notification.body)
        # the notification opens the Überblick – adapted.
        self.assertEqual(notification.url, f"/projects/{self.project.number}/overview/")
        item = OpenItem.objects.get(project=self.project)
        self.assertEqual(item.text, "Rechnungsadresse prüfen (lena)")
        runs = AutomationRun.objects.order_by("pk")
        self.assertEqual([run.status for run in runs], [RunStatus.DONE, RunStatus.DONE])
        self.assertEqual(runs[0].event, f"{self.project.number} Stadtfest: Option → Bestätigt")
        # The change log says who noted the open item.
        from rentalars.core.models import AuditLogEntry

        entry = AuditLogEntry.objects.filter(object_repr=item.text).get()
        self.assertEqual(entry.actor_label, "Automation „project_status open_item“")

    def test_a_new_project_reaches_its_status_and_a_save_without_change_does_nothing(self) -> None:
        self.rule(Trigger.PROJECT_STATUS, Action.NOTIFY, status=ProjectStatus.INQUIRY, recipient=Recipient.MANAGER)
        with self.captureOnCommitCallbacks(execute=True):
            project = make_project("Neu", status=ProjectStatus.INQUIRY, manager=self.manager)
            project.name = "Neu 2"
            project.save()
        self.assertEqual(Notification.objects.filter(kind=Kind.AUTOMATION, user=self.manager).count(), 1)

    def test_a_closed_project_gets_no_open_item(self) -> None:
        self.project.status = ProjectStatus.RETURNED
        self.project.save()
        self.rule(Trigger.PROJECT_STATUS, Action.OPEN_ITEM, status=ProjectStatus.CLOSED, text="Nachkalkulation")
        with self.captureOnCommitCallbacks(execute=True):
            self.project.status = ProjectStatus.CLOSED
            self.project.save()
        run = AutomationRun.objects.get()
        self.assertEqual(run.status, RunStatus.SKIPPED)
        self.assertFalse(OpenItem.objects.exists())

    def test_crew_answer(self) -> None:
        self.rule(
            Trigger.CREW_ANSWER, Action.OPEN_ITEM, answer="declined", text="Ersatz für {person} ({funktion}) suchen"
        )
        self.rule(Trigger.CREW_ANSWER, Action.NOTIFY, recipient=Recipient.ASKED_BY, subject="{antwort} von {person}")
        person = make_person("Anna Becker")
        line = plan(self.project, "Tontechnik", person)
        with self.captureOnCommitCallbacks(execute=True):
            crew.request_deployment(line, user=self.office)
        line.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            crew.answer_deployment(line, accept=False, note="Krank", user=None)
        self.assertEqual(OpenItem.objects.get().text, "Ersatz für Anna Becker (Tontechnik) suchen")
        notification = Notification.objects.get(kind=Kind.AUTOMATION)
        self.assertEqual((notification.user, notification.title), (self.office, "Absage von Anna Becker"))
        # An acceptance: only the rule for both.
        line.refresh_from_db()
        line.request_status = "requested"
        line.save()
        with self.captureOnCommitCallbacks(execute=True):
            crew.answer_deployment(line, accept=True, user=None)
        self.assertEqual(OpenItem.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(kind=Kind.AUTOMATION).count(), 2)

    def test_follow_up(self) -> None:
        self.rule(
            Trigger.FOLLOW_UP,
            Action.NOTIFY,
            recipient=Recipient.FOLLOW_UP_USER,
            subject="Wiedervorlage {projekt}: {notiz}",
        )
        self.rule(Trigger.FOLLOW_UP, Action.OPEN_ITEM, text="Nachfassen ({wiedervorlage})")
        set_follow_up(
            self.project, on=datetime.date(2027, 3, 1), note="Angebot nachfassen", user=self.office, by=self.manager
        )
        with self.captureOnCommitCallbacks(execute=True):
            notify_due_follow_ups()
            notify_due_follow_ups()
        notification = Notification.objects.get(kind=Kind.AUTOMATION)
        self.assertEqual(notification.user, self.office)
        self.assertEqual(notification.title, f"Wiedervorlage {self.project.number} Stadtfest: Angebot nachfassen")
        self.assertEqual(OpenItem.objects.get().text, "Nachfassen (Mo 01.03.2027)")

    def test_nobody_to_notify(self) -> None:
        self.rule(
            Trigger.PROJECT_STATUS,
            Action.NOTIFY,
            status=ProjectStatus.CONFIRMED,
            recipient=Recipient.USER,
            user=self.office,
        )
        self.office.is_active = False
        self.office.save()
        with self.captureOnCommitCallbacks(execute=True):
            services.change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.assertEqual(AutomationRun.objects.get().status, RunStatus.SKIPPED)


class RunTests(RentalarsTestCase):
    """ADM-013: runs are carried out once – after the commit or by the timer – and every one is noted."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("lena", roles=("Projektleitung",))
        self.project = make_project(status=ProjectStatus.OPTION, manager=self.manager)
        self.rule = Automation.objects.create(
            name="Bestätigt",
            trigger=Trigger.PROJECT_STATUS,
            status=ProjectStatus.CONFIRMED,
            action=Action.NOTIFY,
            recipient=Recipient.MANAGER,
        )

    def test_rolled_back_runs_nothing_and_the_timer_takes_what_waits(self) -> None:
        services.change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        run = AutomationRun.objects.get()
        self.assertEqual(run.status, RunStatus.PENDING)
        call_command("run_jobs", verbosity=0)
        run.refresh_from_db()
        self.assertEqual(run.status, RunStatus.DONE)
        self.assertEqual(engine.run_pending(), 0)
        self.assertEqual(Notification.objects.filter(kind=Kind.AUTOMATION).count(), 1)

    def test_switched_off_meanwhile_and_interrupted(self) -> None:
        services.change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.rule.is_active = False
        self.rule.save()
        engine.run_pending()
        run = AutomationRun.objects.get()
        self.assertEqual(run.status, RunStatus.SKIPPED)
        stuck = AutomationRun.objects.create(
            automation=None,
            automation_name="x",
            trigger=Trigger.INQUIRY,
            action=Action.REPLY,
            event_key="k",
            status=RunStatus.RUNNING,
        )
        set_clock(at(1, 8, 11))
        engine.run_pending()
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, RunStatus.FAILED)
        self.assertIn("Nicht wiederholt", stuck.detail)

    def test_deleted_rule_keeps_its_runs_and_old_runs_go(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            services.change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.rule.delete()
        run = AutomationRun.objects.get()
        self.assertEqual((run.automation, run.automation_name), (None, "Bestätigt"))
        set_clock(at(1, 8, year=2028) + datetime.timedelta(days=2))
        self.assertEqual(engine.delete_old_runs(), 1)

    def test_placeholders(self) -> None:
        self.assertEqual(
            engine.fill("{Name}, {betreff} {unbekannt}", {"name": "Bea", "betreff": "X"}), "Bea, X {unbekannt}"
        )
        tokens = [token for token, _label in engine.placeholders_of(Trigger.INQUIRY)]
        # KND-004: {anrede} (the greeting of the sender) joined the placeholders – adapted.
        self.assertEqual(tokens, ["{name}", "{absender}", "{betreff}", "{postfach}", "{anrede}", "{firma}", "{datum}"])
        self.assertIn("{person}", [token for token, _label in engine.placeholders_of(Trigger.CREW_ANSWER)])
        self.assertIn("{projekt}", [token for token, _label in engine.placeholders_of(Trigger.FOLLOW_UP)])


class RuleCheckTests(RentalarsTestCase):
    """ADM-013: what fits together; what does not belong is emptied."""

    def test_problems(self) -> None:
        rule = Automation(name="x", trigger=Trigger.PROJECT_STATUS, action=Action.REPLY, text="Hallo")
        self.assertIn("action", rule.problems())
        rule = Automation(name="x", trigger=Trigger.PROJECT_STATUS, action=Action.NOTIFY, recipient=Recipient.USER)
        self.assertEqual(set(rule.problems()), {"status", "user"})
        rule = Automation(name="x", trigger=Trigger.INQUIRY, action=Action.NOTIFY, recipient=Recipient.MANAGER)
        self.assertIn("recipient", rule.problems())
        rule = Automation(name="x", trigger=Trigger.INQUIRY, action=Action.REPLY, text=" ")
        self.assertIn("text", rule.problems())
        rule = Automation(name="x", trigger=Trigger.FOLLOW_UP, action=Action.OPEN_ITEM, text="x" * 251)
        self.assertIn("text", rule.problems())
        box = configure_mailbox()
        rule = Automation(name="x", trigger=Trigger.INQUIRY, action=Action.REPLY, text="Danke", mailbox=box)
        self.assertIn("mailbox", rule.problems())

    def test_normalise(self) -> None:
        box = configure_mailbox(process_untagged=True)
        user = make_user("bea")
        rule = Automation(
            name="x",
            trigger=Trigger.CREW_ANSWER,
            action=Action.OPEN_ITEM,
            mailbox=box,
            status="confirmed",
            answer="declined",
            recipient=Recipient.USER,
            user=user,
            subject="weg",
            text="Ersatz",
        )
        rule.normalise()
        self.assertEqual(
            (rule.mailbox, rule.status, rule.answer, rule.recipient, rule.user, rule.subject),
            (None, "", "declined", "", None, ""),
        )

    def test_deleting_the_mailbox_switches_its_rules_off(self) -> None:
        configure_mailbox(process_untagged=True)
        info = add_mailbox("Info", "info@verleih.example", process_untagged=True)
        rule = reply_rule(mailbox=info)
        delete_mailbox(info)
        rule.refresh_from_db()
        self.assertEqual((rule.is_active, rule.mailbox), (False, None))
