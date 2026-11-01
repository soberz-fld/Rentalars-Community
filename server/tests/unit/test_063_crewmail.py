# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: answering a deployment request by reply mail (PER-032).

* The tag ``[RA-E-<token>-JA|NEIN]`` and the ``mailto:`` links (RFC 6068, umlauts).
* Which mailbox takes the answers, and the setting "link / reply mail / both".
* The request mail instead of the plain mail of the notification.
* The fetch: answers in every mailbox before tags and inquiries, recorded by
  the service of the browser, with note, notifications, history, mail log,
  the mailbox's rule for assigned mails, and a confirmation to the person;
  answers that can no longer be taken over; unknown tokens and automatic
  replies as normal mails.
"""

from __future__ import annotations

import io
import re
from datetime import timedelta
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from rentalars.accounts.rights import Rights
from rentalars.core.models import AuditLogEntry
from rentalars.mail import crew_answers
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import (
    AfterAssignment,
    CrewAnswerMode,
    CrewRequestMail,
    LogResult,
    MailLogEntry,
    MailSettings,
    ProjectMail,
    UnknownTagMail,
)
from rentalars.mail.parsing import parse_mail
from rentalars.notifications.models import Kind, Notification
from rentalars.notifications.services import set_preference
from rentalars.projects import crew
from rentalars.projects import services as project_services
from rentalars.projects.models import CrewLine, ProjectStatus, RequestStatus
from tests.helpers import LATER, RentalarsTestCase, make_person, make_project, make_user, plan, set_clock
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail

ANSWERS = "projekte@verleih.example"


def mailto_links(message: Any) -> dict[str, str]:
    """The two ``mailto:`` links of a request mail, from its HTML part: ``{"Zusagen": …, "Absagen": …}``."""
    html = message.alternatives[0][0]
    return {
        label: href.replace("&amp;", "&")
        for href, label in re.findall(r'<a href="(mailto:[^"]+)"[^>]*>([^<]+)</a>', html)
    }


def split_mailto(link: str) -> tuple[str, str, str]:
    """Address, subject and text of a ``mailto:`` link, decoded."""
    parts = urlsplit(link)
    query = parse_qs(parts.query, keep_blank_values=True)
    return unquote(parts.path), query["subject"][0], query["body"][0]


def answer_mail(
    message: Any, *, accept: bool = True, note: str = "", sender: str = "anna@crew.example", **kwargs: Any
) -> bytes:
    """The mail the person sends by pressing a button of the request mail, with a note typed in."""
    address, subject, body = split_mailto(mailto_links(message)["Zusagen" if accept else "Absagen"])
    if note:
        body = body.replace("Anmerkung: ", f"Anmerkung: {note}", 1)
    return make_mail(subject, sender=f"Anna Becker <{sender}>", to=address, text=body.replace("\r\n", "\n"), **kwargs)


class CrewMailTestCase(RentalarsTestCase):
    """A project with a manager, Anna planned and a mailbox of the correspondence that sends."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("paula", roles=("Projektleitung",))
        self.manager.first_name, self.manager.last_name = "Paula", "Planer"
        self.manager.save()
        self.project = make_project("Stadtfest Müllheim", manager=self.manager)
        self.person = make_person("Anna Becker", email="anna@crew.example")
        self.line = plan(self.project, "Tontechnik", self.person, meeting_point="Bühne Süd")
        self.mailbox = configure_mailbox()

    def ask(self, line: CrewLine | None = None) -> bool:
        """Ask for the line with the commit callbacks run, so that the mails go out."""
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            return crew.request_deployment(line or self.line, user=self.manager)

    def fetch(self, *mails: bytes, box: FakeMailbox | None = None) -> Any:
        """Fetch the answers from the mailbox of the correspondence; the reply mails go out."""
        django_mail.outbox.clear()
        box = box or FakeMailbox(*mails)
        with self.captureOnCommitCallbacks(execute=True), mailboxes({ANSWERS: box}):
            result = fetch_mail(force=True)
        self.box = box
        return result

    def replies(self) -> list[Any]:
        """The mails to Anna – the planner's notification of the answer goes out as well."""
        return [message for message in django_mail.outbox if message.to == ["anna@crew.example"]]

    def request_message(self) -> Any:
        (message,) = django_mail.outbox
        return message


# --- The tag and the links -----------------------------------------------------------------------------


class TagTests(RentalarsTestCase):
    """PER-032: the tag names the request by an unguessable token and the answer."""

    def test_a_token_is_random_and_unguessable(self) -> None:
        tokens = {crew_answers.new_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)
        for token in tokens:
            self.assertRegex(token, r"^[a-z2-7]{24}$")

    def test_the_tag_is_found_wherever_it_stands(self) -> None:
        token = crew_answers.new_token()
        accept = crew_answers.tag_for(token, accept=True)
        self.assertEqual(accept, f"[RA-E-{token}-JA]")
        self.assertEqual(crew_answers.find_tag(f"Zusage: Stadtfest {accept}"), crew_answers.AnswerTag(token, True))
        upper = f"AW: Absage [ ra-e-{token.upper()}-nein ]"
        self.assertEqual(crew_answers.find_tag(upper), crew_answers.AnswerTag(token, False))
        for subject in (
            "Zusage: Stadtfest",
            f"[RA-E-{token}]",  # no answer
            f"[RA-E-{token[:20]}-JA]",  # too short
            f"[RA-E-{token}-VIELLEICHT]",
            f"[RL#{token}]",
        ):
            self.assertIsNone(crew_answers.find_tag(subject), subject)

    def test_mailto_links_are_encoded_as_rfc_6068_asks(self) -> None:
        link = crew_answers.mailto(
            "projekte@verleih.example", "Zusage: Grüße & Bühne [RA-E-x-JA]", "Anmerkung: \n----\nÄnderung?"
        )
        self.assertTrue(link.startswith("mailto:projekte@verleih.example?subject="), link)
        self.assertNotIn(" ", link)
        self.assertNotIn("+", link)
        self.assertIn("Gr%C3%BC%C3%9Fe%20%26%20B%C3%BChne%20%5BRA-E-x-JA%5D", link)
        self.assertIn("&body=Anmerkung%3A%20%0D%0A----%0D%0A%C3%84nderung%3F", link)
        self.assertEqual(
            split_mailto(link),
            ("projekte@verleih.example", "Zusage: Grüße & Bühne [RA-E-x-JA]", "Anmerkung: \r\n----\r\nÄnderung?"),
        )


class AnswerMailboxTests(RentalarsTestCase):
    """PER-032: the answers go to a mailbox that is fetched – the system mailbox if it is one, else the outgoing one."""

    def test_without_a_mailbox_only_the_link(self) -> None:
        self.assertIsNone(crew_answers.answer_mailbox())
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.BOTH)
        self.assertIsNone(crew_answers.answers_by_mail())

    def test_the_outgoing_mailbox_of_the_correspondence(self) -> None:
        projects = configure_mailbox()
        system = add_mailbox("System", "system@verleih.example", for_correspondence=False, for_system=True)
        system.imap_host = ""
        system.save()
        self.assertEqual(crew_answers.answer_mailbox(), projects)

    def test_the_system_mailbox_if_it_is_fetched(self) -> None:
        configure_mailbox()
        system = add_mailbox("System", "system@verleih.example", for_system=True)
        self.assertEqual(crew_answers.answer_mailbox(), system)

    def test_a_mailbox_that_is_not_fetched_takes_no_answers(self) -> None:
        projects = configure_mailbox()
        projects.imap_password_encrypted = ""
        projects.save()
        self.assertIsNone(crew_answers.answer_mailbox())

    def test_the_setting_link_switches_answers_by_mail_off(self) -> None:
        projects = configure_mailbox()
        self.assertEqual(crew_answers.answers_by_mail(), projects)
        rules = MailSettings.load()
        rules.crew_answers = CrewAnswerMode.LINK
        rules.save()
        self.assertIsNone(crew_answers.answers_by_mail())


# --- The request mail ---------------------------------------------------------------------------------


class RequestMailTests(CrewMailTestCase):
    """PER-032: with answers by mail the request goes as a mail with the buttons "Zusagen" and "Absagen"."""

    def test_the_request_mail_with_buttons_and_link(self) -> None:
        self.assertTrue(self.ask())
        message = self.request_message()
        stored = CrewRequestMail.objects.get()
        self.line.refresh_from_db()
        self.assertEqual(
            (stored.line, stored.person, stored.requested_at), (self.line, self.person, self.line.requested_at)
        )
        self.assertEqual(message.to, ["anna@crew.example"])
        self.assertEqual(message.reply_to, [ANSWERS])
        self.assertEqual(message.extra_headers["Auto-Submitted"], "auto-generated")
        self.assertTrue(
            message.subject.startswith(
                f"[Rentalars] Einsatzanfrage: {self.project.number} Stadtfest Müllheim als Tontechnik, Mi 10.03.2027"
            ),
            message.subject,
        )

        links = mailto_links(message)
        self.assertEqual(list(links), ["Zusagen", "Absagen"])
        address, subject, body = split_mailto(links["Zusagen"])
        self.assertEqual(address, ANSWERS)
        self.assertEqual(subject, f"Zusage: Stadtfest Müllheim, Mi 10.03. [RA-E-{stored.token}-JA]")
        self.assertTrue(body.startswith("Anmerkung: \r\n\r\n----\r\nZusage für: "), body)
        self.assertIn("Bitte den Betreff so lassen", body)
        self.assertIn("Stadtfest%20M%C3%BCllheim", links["Zusagen"])  # umlauts as UTF-8, spaces as %20
        self.assertEqual(
            split_mailto(links["Absagen"])[1], f"Absage: Stadtfest Müllheim, Mi 10.03. [RA-E-{stored.token}-NEIN]"
        )

        text = message.body
        self.assertIn("Hallo Anna,", text)
        self.assertIn("Treffpunkt: Bühne Süd", text)
        self.assertIn("Angefragt von: Paula Planer", text)
        self.assertIn(f"<{links['Zusagen']}>", text)
        link = f"{settings.RENTALARS_URL}{reverse('projects:deployment', args=[self.project])}"
        self.assertIn(f"Oder in Rentalars antworten: {link}", text)
        html = message.alternatives[0][0]
        self.assertIn('lang="de"', html)
        self.assertIn("„Zusagen“ und „Absagen“ öffnen je eine vorbereitete Mail an projekte@verleih.example", html)

        # The notification stays in the application; its plain mail is left out.
        notice = Notification.objects.get(user=self.person.user, kind=Kind.DEPLOYMENT_REQUEST)
        self.assertIsNone(notice.emailed_at)

    def test_by_reply_mail_only_no_link(self) -> None:
        rules = MailSettings.load()
        rules.crew_answers = CrewAnswerMode.MAIL
        rules.save()
        self.ask()
        message = self.request_message()
        self.assertNotIn("/deployment/", message.body)
        self.assertNotIn("/deployment/", message.alternatives[0][0])
        self.assertEqual(len(mailto_links(message)), 2)

    def test_by_the_link_as_before(self) -> None:
        rules = MailSettings.load()
        rules.crew_answers = CrewAnswerMode.LINK
        rules.save()
        self.ask()
        message = self.request_message()
        self.assertNotIn("mailto:", message.body)
        self.assertEqual(message.alternatives, [])
        self.assertFalse(CrewRequestMail.objects.exists())

    def test_without_a_mailbox_that_is_fetched_the_link(self) -> None:
        self.mailbox.is_active = False
        self.mailbox.save()
        self.ask()
        self.assertNotIn("mailto:", self.request_message().body)
        self.assertFalse(CrewRequestMail.objects.exists())

    def test_whoever_switched_the_mails_off_gets_none(self) -> None:
        set_preference(self.person.user, Kind.DEPLOYMENT_REQUEST, in_app=True, by_email=False)
        self.assertTrue(self.ask())
        self.assertEqual(django_mail.outbox, [])
        self.assertTrue(Notification.objects.filter(user=self.person.user, kind=Kind.DEPLOYMENT_REQUEST).exists())

    def test_a_person_without_address_gets_no_mail(self) -> None:
        self.person.email = ""
        self.person.save()
        self.ask()
        self.assertEqual(django_mail.outbox, [])
        self.assertFalse(CrewRequestMail.objects.exists())

    def test_a_person_who_cannot_log_in_gets_the_buttons_without_the_hint_on_notifications(self) -> None:
        """Every person has an account (AUT-026); one never invited cannot log in, but can answer by mail."""
        self.assertFalse(self.person.user.has_usable_password())
        self.ask()
        self.assertNotIn("Benachrichtigungen", self.request_message().body)
        self.person.user.set_password("geheim-und-lang-genug")
        self.person.user.save()
        self.ask()
        self.assertIn("„Mein Konto“ → „Benachrichtigungen“", self.request_message().body)

    def test_asking_again_gives_a_new_token(self) -> None:
        self.ask()
        self.ask()
        self.assertEqual(CrewRequestMail.objects.count(), 2)
        self.assertEqual(len(set(CrewRequestMail.objects.values_list("token", flat=True))), 2)


# --- The answer ---------------------------------------------------------------------------------------------


class AnswerByMailTests(CrewMailTestCase):
    """PER-032: the fetch records an answer by mail as the browser does."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.request = self.request_message()
        self.token = CrewRequestMail.objects.get().token

    def test_an_acceptance_with_a_note(self) -> None:
        result = self.fetch(answer_mail(self.request, note="Bin dabei, komme mit dem Bus.\nBis dann!"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual((result.crew_answers, len(result.imported), len(result.inquiries)), (1, 0, 0))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)
        self.assertEqual(self.line.answer_note, "Bin dabei, komme mit dem Bus. Bis dann!")
        self.assertIsNotNone(CrewRequestMail.objects.get().answered_at)

        # The planner hears of it, as with an answer in the browser; the person does not.
        notice = Notification.objects.get(user=self.manager, kind=Kind.DEPLOYMENT_ANSWER)
        self.assertIn("Anna Becker hat zugesagt", notice.title)
        self.assertFalse(Notification.objects.filter(user=self.person.user, kind=Kind.DEPLOYMENT_ANSWER).exists())

        # The history: the change of the line by the person, and that it came by mail.
        entries = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(CrewLine), object_id=str(self.line.pk)
        )
        change = entries.filter(action="updated").latest("id")
        self.assertEqual(
            (change.actor, change.changes["request_status"]), (self.person.user, ["requested", "accepted"])
        )
        event = entries.get(action="event")
        self.assertEqual((event.event, event.actor), ("crew_line.answered_by_mail", self.person.user))

        # Dealt with as the mailbox deals with assigned mails: moved away.
        self.assertEqual((self.box.inbox, len(self.box.done)), ({}, 1))
        self.assertFalse(ProjectMail.objects.exists())
        entry = MailLogEntry.objects.get(result=LogResult.CREW_ANSWER)
        self.assertEqual((entry.detail, entry.project, entry.mailbox), ("accepted", self.project, self.mailbox))
        self.assertEqual(entry.detail_text, "Zusage")

        # The confirmation goes to the person.
        (reply,) = self.replies()
        self.assertEqual(reply.to, ["anna@crew.example"])
        self.assertEqual(reply.subject, "[Rentalars] Deine Zusage ist angekommen: Stadtfest Müllheim, Mi 10.03.")
        self.assertIn("deine Zusage für", reply.body)
        self.assertIn("an Paula Planer weitergegeben", reply.body)
        self.assertIn("Deine Anmerkung: „Bin dabei, komme mit dem Bus. Bis dann!“", reply.body)
        self.assertNotIn("RA-E-", reply.subject + reply.body)
        self.assertEqual(reply.extra_headers["Auto-Submitted"], "auto-replied")

    def test_the_command_tells_the_answers(self) -> None:
        output = io.StringIO()
        with self.captureOnCommitCallbacks(execute=True), mailboxes({ANSWERS: FakeMailbox(answer_mail(self.request))}):
            call_command("fetch_mail", "--now", stdout=output)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "Projekte: 1 neue Mails angesehen; 0 zugeordnet, 0 mit unbekannter Kennung, 0 Anfragen.",
                "1 Antwort auf eine Einsatzanfrage per Mail.",
            ],
        )

    def test_a_refusal_from_a_mail_program_that_sends_html_only(self) -> None:
        _address, subject, body = split_mailto(mailto_links(self.request)["Absagen"])
        html = "<p>" + body.replace("\r\n", "<br>").replace("Anmerkung: ", "Anmerkung: <b>Krank</b>", 1) + "</p>"
        message = make_mail(subject, sender="Anna Becker <anna@crew.example>", text="")
        raw = message.replace(b"Content-Type: text/plain", b"Content-Type: text/html").replace(
            b"\n\n\n", f"\n\n{html}\n".encode()
        )
        parsed = parse_mail(raw)
        self.assertEqual(crew_answers.note_of(parsed), "Krank")
        self.fetch(raw)
        self.line.refresh_from_db()
        self.assertEqual((self.line.request_status, self.line.answer_note), (RequestStatus.DECLINED, "Krank"))
        self.assertIn("Deine Absage ist angekommen", self.replies()[0].subject)

    def test_in_every_mailbox_whatever_it_does_with_mails_without_tag(self) -> None:
        info = add_mailbox(
            "Info", "info@verleih.example", process_untagged=True, after_assignment=AfterAssignment.DELETE
        )
        boxes = {ANSWERS: FakeMailbox(), "info@verleih.example": FakeMailbox(answer_mail(self.request, accept=False))}
        with self.captureOnCommitCallbacks(execute=True), mailboxes(boxes):
            result = fetch_mail(force=True)
        self.assertEqual((result.crew_answers, result.inquiries), (1, []))
        self.assertFalse(UnknownTagMail.objects.exists())
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.DECLINED)
        self.assertEqual(len(boxes["info@verleih.example"].deleted), 1)
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.CREW_ANSWER).mailbox, info)

    def test_a_mailbox_that_leaves_mails_keeps_it_and_it_counts_once(self) -> None:
        self.mailbox.after_assignment = AfterAssignment.KEEP
        self.mailbox.save()
        box = FakeMailbox(answer_mail(self.request))
        self.fetch(box=box)
        self.assertEqual((len(box.inbox), len(box.kept)), (1, 1))
        # The server renumbered its inbox: the mail is looked at again, but not answered twice.
        self.mailbox.refresh_from_db()
        self.mailbox.uid_validity = 99
        self.mailbox.save()
        result = self.fetch(box=box)
        self.assertEqual(result.crew_answers, 1)
        self.assertEqual(django_mail.outbox, [])
        self.assertEqual(MailLogEntry.objects.filter(result=LogResult.CREW_ANSWER).count(), 1)

    def test_a_forwarded_request_cannot_be_answered_by_its_new_holder(self) -> None:
        """PER-046: the token alone is not enough – the mail must come from the address asked."""
        self.fetch(answer_mail(self.request, sender="kollege@example.org"))
        self.line.refresh_from_db()
        self.assertEqual((self.line.request_status, self.line.answer_note), (RequestStatus.REQUESTED, ""))
        self.assertFalse(AuditLogEntry.objects.filter(event__startswith="crew_line.answered_by_mail").exists())
        self.assertIsNone(CrewRequestMail.objects.get().answered_at)
        entry = MailLogEntry.objects.get(result=LogResult.CREW_ANSWER)
        self.assertEqual(entry.detail, "accepted:sender")
        self.assertEqual(entry.detail_text, "Zusage – nicht übernommen: nicht von der Adresse, an die die Anfrage ging")
        (reply,) = self.replies()
        self.assertEqual(reply.to, ["anna@crew.example"])
        self.assertIn(
            "Die Antwort kam nicht von der Adresse, an die diese Anfrage ging, sondern von kollege@example.org",
            reply.body,
        )
        self.assertIn("Es wurde nichts geändert.", reply.body)
        self.assertEqual(self.box.inbox, {})
        # The person can still answer from the address asked, with the same mail.
        self.fetch(answer_mail(self.request))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def test_the_address_asked_is_the_one_the_mail_went_to_not_the_one_of_today(self) -> None:
        """PER-046: if the address of the person changes afterwards, the old request still wants the old address."""
        self.assertEqual(CrewRequestMail.objects.get().sent_to, "anna@crew.example")
        self.person.email = "anna@neu.example"
        self.person.save()
        self.fetch(answer_mail(self.request, sender="anna@neu.example"))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.fetch(answer_mail(self.request, sender="Anna@Crew.Example"))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def test_a_request_of_before_0_11_5_wants_the_address_of_the_person(self) -> None:
        CrewRequestMail.objects.update(sent_to="")
        self.fetch(answer_mail(self.request, sender="kollege@example.org"))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.fetch(answer_mail(self.request))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def test_a_second_from_header_is_a_trick_and_answers_nothing(self) -> None:
        """PER-046: a receiver may check the last From while Rentalars reads the first one – so two are refused."""
        raw = answer_mail(self.request)
        tricked = b"From: kollege@example.org\r\n" + raw
        self.assertEqual(parse_mail(tricked).from_count, 2)
        self.fetch(
            raw.replace(
                b"From: Anna Becker <anna@crew.example>",
                b"From: Anna Becker <anna@crew.example>\nFrom: kollege@example.org",
                1,
            )
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.CREW_ANSWER).detail, "accepted:sender")

    def test_an_address_in_idn_form_counts_as_the_same(self) -> None:
        """PER-046: ``müller.example`` and ``xn--mller-kva.example`` are one domain."""
        CrewRequestMail.objects.update(sent_to="anna@müller.example")
        self.fetch(answer_mail(self.request, sender="anna@xn--mller-kva.example"))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def test_a_full_width_look_alike_of_the_domain_is_not_the_domain(self) -> None:
        """PER-046: ``ｇｍａｉｌ.com`` in full-width letters is another domain than ``gmail.com`` – the server checked that one."""
        CrewRequestMail.objects.update(sent_to="anna@mail.example")
        self.fetch(answer_mail(self.request, sender="anna@\uff47\uff4d\uff41\uff49\uff4c.com"))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.CREW_ANSWER).detail, "accepted:sender")

    def test_the_warning_comes_once_an_hour_for_the_same_refusal(self) -> None:
        """PER-046: whoever has the token cannot flood the person with warnings."""
        self.fetch(answer_mail(self.request, sender="a@x.example"), answer_mail(self.request, sender="b@x.example"))
        self.assertEqual(MailLogEntry.objects.filter(result=LogResult.CREW_ANSWER, detail="accepted:sender").count(), 2)
        self.assertEqual(len(self.replies()), 1)
        # An hour later the person is told again.
        MailLogEntry.objects.update(timestamp=timezone.now() - timedelta(hours=2))
        self.fetch(answer_mail(self.request, sender="c@x.example"))
        self.assertEqual(len(self.replies()), 1)

    def test_only_a_plain_address_is_named_in_the_warning(self) -> None:
        """PER-046: a display string posing as the address (a link, a request) is not repeated in a mail from us."""
        text = "Dein Konto ist gesperrt, bestaetigen unter http://evil.example/login"
        self.fetch(answer_mail(self.request, sender=f'"{text}"@x.example'))
        (reply,) = self.replies()
        self.assertNotIn("evil.example", reply.body)
        self.assertIn("sondern von –", reply.body)

    def test_a_mail_without_sender_address_answers_nothing(self) -> None:
        address, subject, body = split_mailto(mailto_links(self.request)["Zusagen"])
        self.fetch(make_mail(subject, sender="", to=address, text=body.replace("\r\n", "\n")))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)

    def test_a_forged_sender_is_refused_when_the_mail_server_says_so(self) -> None:
        """PER-046: the right address, but the receiving server wrote ``dmarc=fail``: somebody forged the From."""
        forged = answer_mail(
            self.request,
            headers={"Authentication-Results": "mx.verleih.example; spf=pass; dkim=none; dmarc=fail (p=reject)"},
        )
        self.fetch(forged)
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.CREW_ANSWER).detail, "accepted:forged")
        (reply,) = self.replies()
        self.assertIn("Prüfung des Absenders", reply.body)

    def test_a_good_or_missing_verdict_of_the_mail_server_does_not_hinder(self) -> None:
        good = answer_mail(
            self.request, headers={"Authentication-Results": "mx.verleih.example; spf=fail; dkim=pass; dmarc=pass"}
        )
        self.fetch(good)
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def test_without_the_label_there_is_no_note(self) -> None:
        _address, subject, _body = split_mailto(mailto_links(self.request)["Zusagen"])
        quoted = "Passt!\n\nAm 01.03.2027 schrieb Rentalars:\n> Anmerkung: alt\n"
        self.fetch(make_mail(subject, sender="anna@crew.example", text=quoted))
        self.line.refresh_from_db()
        self.assertEqual((self.line.request_status, self.line.answer_note), (RequestStatus.ACCEPTED, ""))

    def test_a_long_note_is_cut(self) -> None:
        self.fetch(answer_mail(self.request, note="x" * 400))
        self.line.refresh_from_db()
        self.assertEqual(len(self.line.answer_note), 250)

    def test_an_unknown_token_is_a_normal_mail(self) -> None:
        self.mailbox.process_untagged = True
        self.mailbox.save()
        other = crew_answers.tag_for(crew_answers.new_token(), accept=True)
        result = self.fetch(make_mail(f"Zusage {other}", sender="anna@crew.example"))
        self.assertEqual((result.crew_answers, len(result.inquiries)), (0, 1))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(django_mail.outbox, [])

    def test_an_automatic_reply_answers_nothing(self) -> None:
        result = self.fetch(answer_mail(self.request, headers={"Auto-Submitted": "auto-replied"}))
        self.assertEqual(result.crew_answers, 0)
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(django_mail.outbox, [])
        self.assertEqual(MailLogEntry.objects.get().result, LogResult.LEFT_IN_INBOX)


class AnswerNotTakenOverTests(CrewMailTestCase):
    """PER-032: answered already, over, withdrawn, replaced or cancelled – nothing changes, the person is told."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.request = self.request_message()

    def assert_refused(self, raw: bytes, reason: str, sentence: str) -> Any:
        before = CrewLine.objects.filter(pk=self.line.pk).values("request_status", "answer_note").first()
        result = self.fetch(raw)
        self.assertEqual(result.crew_answers, 1)
        self.assertEqual(
            CrewLine.objects.filter(pk=self.line.pk).values("request_status", "answer_note").first(), before
        )
        entry = MailLogEntry.objects.get(result=LogResult.CREW_ANSWER)
        self.assertEqual(entry.detail.split(":")[1], reason)
        (reply,) = self.replies()
        self.assertEqual(reply.to, ["anna@crew.example"])
        self.assertTrue(reply.subject.startswith("[Rentalars] Deine Antwort wurde nicht übernommen"), reply.subject)
        self.assertIn(sentence, reply.body)
        self.assertIn("Es wurde nichts geändert.", reply.body)
        self.assertEqual(self.box.inbox, {})
        return entry

    def test_answered_already(self) -> None:
        crew.answer_deployment(self.line, accept=True, user=self.person.user)
        entry = self.assert_refused(
            answer_mail(self.request, accept=False), "answered", "Diese Anfrage ist schon beantwortet: Zusage."
        )
        self.assertEqual(entry.detail_text, "Absage – nicht übernommen: schon beantwortet")

    def test_the_deployment_is_over(self) -> None:
        set_clock(LATER)
        self.assert_refused(answer_mail(self.request), "expired", "Der Einsatz ist schon vorbei.")

    def test_replaced_by_a_newer_request(self) -> None:
        self.ask()
        self.assert_refused(answer_mail(self.request), "replaced", "Für diesen Einsatz gibt es eine neuere Anfrage.")

    def test_somebody_else_is_planned_now(self) -> None:
        other = make_person("Ben Schmidt", email="ben@crew.example")
        crew.update_crew_line(self.line, rights=Rights.everything(), person=other)
        self.assert_refused(answer_mail(self.request), "withdrawn", "Die Anfrage gilt nicht mehr")

    def test_a_refusal_of_the_service_does_not_block_the_fetch(self) -> None:
        with mock.patch.object(crew, "answer_deployment", side_effect=ValidationError("Nein")):
            result = self.fetch(answer_mail(self.request))
        self.assertTrue(result.ok, result.error)
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.CREW_ANSWER).detail, "accepted:withdrawn")
        self.assertFalse(AuditLogEntry.objects.filter(event__startswith="crew_line.answered_by_mail").exists())
        self.assertEqual(self.box.inbox, {})

    def test_the_line_was_deleted(self) -> None:
        crew.delete_crew_line(self.line)
        result = self.fetch(answer_mail(self.request))
        self.assertEqual(result.crew_answers, 1)
        (reply,) = self.replies()
        self.assertEqual(reply.subject, "[Rentalars] Deine Antwort auf eine Einsatzanfrage wurde nicht übernommen")
        entry = MailLogEntry.objects.get(result=LogResult.CREW_ANSWER)
        self.assertEqual((entry.detail, entry.project), ("accepted:withdrawn", None))

    def test_the_project_was_cancelled(self) -> None:
        project_services.change_status(self.project, ProjectStatus.CANCELLED, rights=Rights.everything())
        self.assert_refused(answer_mail(self.request), "cancelled", "Das Projekt wurde abgesagt oder abgeschlossen.")
