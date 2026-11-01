# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the mail wishes (EML-034 to EML-039).

Signature (EML-034), SMTP with the IMAP access data (EML-035), the compact
text of the conversation (EML-036), answering all, CC, BCC and address
suggestions (EML-037), the sender name (EML-038) and the mail log (EML-039).
"""

from __future__ import annotations

import datetime
import smtplib
from email import message_from_bytes, policy
from typing import Any
from unittest import mock

from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import SimpleTestCase, override_settings
from django.utils.translation import gettext

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, Rights, SpecialRight, rights_of
from rentalars.core.models import CompanyProfile
from rentalars.customers.models import Contact
from rentalars.customers.services import anonymise_customer
from rentalars.mail import log, sending
from rentalars.mail.addresses import suggest_addresses
from rentalars.mail.display import frame_size, html_to_text, split_quoted
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.mailboxes import save_mailbox
from rentalars.mail.models import (
    Direction,
    LogKind,
    LogResult,
    Mailbox,
    MailLogEntry,
    ProjectMail,
)
from rentalars.mail.parsing import format_address
from rentalars.mail.sending import reply_recipients, send_project_mail, split_addresses
from rentalars.mail.services import delete_old_mail_log_entries
from rentalars.mail.signature import clean_signature, render_signature, sender_header, sender_label, sender_name
from tests.helpers import NOW, RentalarsTestCase, make_customer, make_person, make_project, make_user
from tests.mailbox import PASSWORD, FakeMailbox, capture_smtp, configure_mailbox, make_mail

LOGGING_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"
LOCMEM_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

SIGNATURE = (
    "<p>Viele Grüße<br><b>{vorname} {nachname}</b><br>{position}</p>"
    '<p>Tel. {telefon} · <a href="mailto:{email}">{email}</a><br>{firma}</p>'
)


def writer(username: str = "max", **person: Any) -> Any:
    """A user whose person has a full name, position, address and phone."""
    user = make_user(username, roles=("Projektleitung",))
    values = {"position": "Leitung Licht", "phone": "0170 1234567", "email": "max@verleih.example", **person}
    make_person(person.pop("name", "Max Mustermann"), user=user, **values)
    user.refresh_from_db()
    return user


def company(name: str = "Firma Muster") -> None:
    """Give the company a name."""
    profile = CompanyProfile.load()
    profile.name = name
    profile.save()


class RecordingSMTP(smtplib.SMTP):
    """``smtplib.SMTP`` without a network: notes the login and what would be transmitted.

    ``send_message`` of the standard library runs for real – so a test sees
    which header lines leave the house (a ``Bcc`` must not) and which
    addresses the server is told.
    """

    sessions: list[RecordingSMTP] = []

    def __init__(self, host: str = "", port: int = 0, **kwargs: Any) -> None:
        super().__init__()  # without a host nothing is connected
        self.host, self.port = host, port
        self.logged_in: tuple[str, str] | None = None
        self.transmitted: list[tuple[str, list[str], bytes]] = []
        RecordingSMTP.sessions.append(self)

    def starttls(self, *args: Any, **kwargs: Any) -> tuple[int, bytes]:
        return 220, b"ready"

    def ehlo_or_helo_if_needed(self) -> None:
        return None

    def login(self, user: str, password: str, **kwargs: Any) -> tuple[int, bytes]:
        self.logged_in = (user, password)
        return 235, b"ok"

    def sendmail(self, from_addr: str, to_addrs: Any, msg: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.transmitted.append((from_addr, list(to_addrs), msg if isinstance(msg, bytes) else msg.encode()))
        return {}


def recording_smtp() -> Any:
    """Put :class:`RecordingSMTP` in the place of the real client for one test."""
    RecordingSMTP.sessions = []
    return mock.patch.object(smtplib, "SMTP", RecordingSMTP)


class BrokenBackend(BaseEmailBackend):
    """A mail server that refuses everything – silently, if asked to."""

    def send_messages(self, email_messages: Any) -> int:
        if self.fail_silently:
            return 0
        raise smtplib.SMTPException("Server says no")


# --- EML-034: the signature ------------------------------------------------------------------------------


class SignatureCleaningTests(SimpleTestCase):
    """EML-034: the signature is cleaned; plain text keeps its lines."""

    def test_scripts_handlers_and_dangerous_links_go(self) -> None:
        cleaned = clean_signature(
            '<p onclick="x()">Gruß<script>alert(1)</script><a href="javascript:x()">a</a>'
            '<form><input></form><a href="tel:+49170">Telefon</a><img src="https://firma.example/logo.png"></p>'
        )
        for gone in ("script", "onclick", "javascript", "<form", "<input"):
            self.assertNotIn(gone, cleaned)
        self.assertIn('href="tel:+49170"', cleaned)
        self.assertIn('src="https://firma.example/logo.png"', cleaned)

    def test_plain_text_keeps_its_line_breaks(self) -> None:
        self.assertEqual(clean_signature("Viele Grüße\n{vorname} & Co"), "Viele Grüße<br>\n{vorname} &amp; Co")
        self.assertEqual(clean_signature("   "), "")

    def test_text_version_of_html(self) -> None:
        text = html_to_text(
            '<p>Viele Grüße<br><b>Max</b></p><p><a href="mailto:max@x.example">max@x.example</a> · '
            '<a href="https://firma.example">Website</a></p><style>p{}</style>'
        )
        self.assertEqual(text, "Viele Grüße\nMax\n\nmax@x.example · Website <https://firma.example>")


class SignatureTests(RentalarsTestCase):
    """EML-034: placeholders take the data of the writer; mails carry text and HTML."""

    def setUp(self) -> None:
        super().setUp()
        company()
        self.user = writer()

    def test_placeholders_take_the_data_of_the_writer(self) -> None:
        signature = render_signature(self.user, SIGNATURE)
        self.assertIn("<b>Max Mustermann</b>", signature.html)
        self.assertIn('href="mailto:max@verleih.example"', signature.html)
        self.assertIn("Leitung Licht", signature.html)
        self.assertIn("Firma Muster", signature.html)
        self.assertEqual(
            signature.text,
            "Viele Grüße\nMax Mustermann\nLeitung Licht\n\nTel. 0170 1234567 · max@verleih.example\nFirma Muster",
        )

    def test_the_data_of_a_person_cannot_smuggle_markup_in(self) -> None:
        person = self.user.person
        person.last_name = '<script>alert("x")</script>'
        person.phone = "javascript:alert(1)"
        person.save()
        self.user.refresh_from_db()
        signature = render_signature(self.user, '{nachname} <a href="{telefon}">Ruf an</a>')
        self.assertNotIn("<script", signature.html)
        self.assertNotIn("javascript:", signature.html)
        self.assertIn("&lt;script&gt;", signature.html)

    def test_the_stored_signature_goes_into_text_and_html_part(self) -> None:
        configure_mailbox(signature_html=clean_signature(SIGNATURE))
        project = make_project()
        with capture_smtp() as sent:
            stored = send_project_mail(
                project,
                to="kunde@kunde.example",
                subject="Angebot",
                body="Hallo,\nanbei <das> Angebot.",
                user=self.user,
            )
        (message,) = sent
        self.assertEqual(message.get_content_type(), "multipart/alternative")
        text = message.get_body(preferencelist=("plain",)).get_content()
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn("Hallo,\nanbei <das> Angebot.\n\n-- \nViele Grüße\nMax Mustermann", text)
        self.assertIn("anbei &lt;das&gt; Angebot.", html)
        self.assertIn("<b>Max Mustermann</b>", html)
        self.assertIn("Max Mustermann", stored.text_body)
        self.assertIn("<b>Max Mustermann</b>", stored.html_body)

    def test_without_signature_the_mail_is_text_only(self) -> None:
        configure_mailbox(signature_html=clean_signature(SIGNATURE))
        with capture_smtp() as sent:
            stored = send_project_mail(
                make_project(), to="a@b.example", subject="x", body="Nur Text", with_signature=False, user=self.user
            )
        self.assertEqual(sent[0].get_content_type(), "text/plain")
        self.assertEqual((stored.text_body, stored.html_body), ("Nur Text", ""))

    def test_no_signature_stored_means_text_only(self) -> None:
        configure_mailbox()
        with capture_smtp() as sent:
            send_project_mail(make_project(), to="a@b.example", subject="x", body="Text", user=self.user)
        self.assertEqual(sent[0].get_content_type(), "text/plain")

    def test_attachments_keep_both_parts(self) -> None:
        configure_mailbox(signature_html="Gruß {vorname}")
        with capture_smtp() as sent:
            send_project_mail(
                make_project(),
                to="a@b.example",
                subject="x",
                body="Text",
                attachments=[sending.OutgoingAttachment("plan.pdf", "application/pdf", b"%PDF")],
                user=self.user,
            )
        (message,) = sent
        self.assertEqual(message.get_content_type(), "multipart/mixed")
        self.assertIn("Gruß Max", message.get_body(preferencelist=("html",)).get_content())
        self.assertEqual([part.get_filename() for part in message.iter_attachments()], ["plan.pdf"])


# --- EML-035: SMTP with the IMAP access data -------------------------------------------------------------


class SmtpLoginTests(RentalarsTestCase):
    """EML-035: sending with the access data of the mailbox, or with access data of its own."""

    def test_same_access_data_as_imap(self) -> None:
        mail_settings = configure_mailbox(smtp_same_login=True)
        self.assertEqual(
            (mail_settings.smtp_login, mail_settings.smtp_password), ("projekte@verleih.example", PASSWORD)
        )
        with recording_smtp():
            send_project_mail(make_project(), to="a@b.example", subject="x", body="y", user=None)
        self.assertEqual(RecordingSMTP.sessions[0].logged_in, ("projekte@verleih.example", PASSWORD))

    def test_access_data_of_its_own(self) -> None:
        mail_settings = configure_mailbox(smtp_same_login=False, smtp_user="versand@verleih.example")
        mail_settings.set_smtp_password("versand-geheim")
        mail_settings.save()
        with recording_smtp():
            send_project_mail(make_project(), to="a@b.example", subject="x", body="y", user=None)
        self.assertEqual(RecordingSMTP.sessions[0].logged_in, ("versand@verleih.example", "versand-geheim"))

    def test_without_a_user_of_its_own_nothing_logs_in(self) -> None:
        configure_mailbox(smtp_same_login=False, smtp_user="")
        with recording_smtp():
            send_project_mail(make_project(), to="a@b.example", subject="x", body="y", user=None)
        self.assertIsNone(RecordingSMTP.sessions[0].logged_in)

    # The access data belong to each mailbox (EML-041); ``save_mailbox`` keeps the rules of EML-035.
    # The data migration 0003 (keep own SMTP access data) worked on fields that moved into the mailboxes
    # with 0004 and can no longer be run against the current tables; its test went with them.

    def test_same_access_data_removes_the_own_ones(self) -> None:
        mailbox = configure_mailbox(smtp_same_login=False, smtp_user="versand@verleih.example")
        save_mailbox(mailbox, smtp_password="versand-geheim")
        self.assertEqual(Mailbox.objects.get().smtp_password, "versand-geheim")
        mailbox.smtp_same_login = True
        save_mailbox(mailbox, smtp_password="wird-ignoriert")
        stored = Mailbox.objects.get()
        self.assertEqual((stored.smtp_user, stored.smtp_password_encrypted), ("", ""))
        self.assertEqual(stored.smtp_password, PASSWORD)

    def test_an_own_user_needs_an_own_password(self) -> None:
        mailbox = configure_mailbox(smtp_same_login=False, smtp_user="versand@verleih.example")
        with self.assertRaises(ValidationError) as caught:
            save_mailbox(mailbox)
        self.assertIn("smtp_password", caught.exception.message_dict)


# --- EML-036: the conversation -----------------------------------------------------------------------------


class ConversationTextTests(SimpleTestCase):
    """EML-036: what is new in a mail, and the rest folded away."""

    def test_quotes_of_mail_programs_are_found(self) -> None:
        cases = {
            "Danke!\n\nAm 01.03.2027 um 08:30 schrieb Kunde <k@x.example>:\n> Frage": "Am 01.03.2027",
            "Sure.\n\nOn Mon, 1 Mar 2027 at 08:30, Kunde\n<k@x.example> wrote:\n> Frage": "On Mon",
            "Gut.\n\n-----Ursprüngliche Nachricht-----\nVon: A": "-----Urspr",
            "Ok\n\nVon: Kunde\nGesendet: Montag, 1. März 2027\nAn: Projekte": "Von: Kunde",
            "Ok\n________________________________\nFrom: Kunde": "____",
            "Bis bald\n-- \nMax Mustermann": "-- ",
            "Hier:\n> zitiert\nund weiter": "> zitiert",
        }
        for text, rest_starts in cases.items():
            new, rest = split_quoted(text)
            self.assertNotIn(rest_starts.strip(), new, text)
            self.assertTrue(rest.startswith(rest_starts), (text, rest))

    def test_a_mail_without_anything_new_is_shown_whole(self) -> None:
        self.assertEqual(split_quoted("> nur ein Zitat\n> mehr nicht"), ("> nur ein Zitat\n> mehr nicht", ""))
        self.assertEqual(split_quoted("Ein Satz.\nNoch einer."), ("Ein Satz.\nNoch einer.", ""))

    def test_a_one_liner_gets_a_small_frame(self) -> None:
        self.assertEqual(frame_size("<p>Danke!</p>", "Danke!"), "short")
        self.assertEqual(frame_size("<p>x</p>", "\n".join(["Zeile"] * 20)), "medium")
        self.assertEqual(frame_size("<p>x</p>", "\n".join(["Zeile"] * 50)), "")
        self.assertEqual(frame_size('<p>Logo</p><img src="a"><img src="b">', ""), "medium")


# --- EML-037: answer all, CC, BCC, suggestions ------------------------------------------------------------


class AddressTests(SimpleTestCase):
    """EML-037: addresses are kept readable and can be split again."""

    def test_names_keep_umlauts_and_commas_are_quoted(self) -> None:
        self.assertEqual(format_address("Jörg Müller", "j@x.example"), "Jörg Müller <j@x.example>")
        self.assertEqual(format_address("Müller, Hans", "h@x.example"), '"Müller, Hans" <h@x.example>')
        self.assertEqual(format_address("", "h@x.example"), "h@x.example")
        self.assertEqual(
            split_addresses('"Müller, Hans" <h@x.example>; Jörg <j@x.example>'),
            ['"Müller, Hans" <h@x.example>', "Jörg <j@x.example>"],
        )


class ReplyAllTests(RentalarsTestCase):
    """EML-037: an answer to all reaches the sender and every other recipient, never the own mailbox."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.project = make_project()
        fetch_mail(
            force=True,
            opener=FakeMailbox(
                make_mail(
                    f"Frage [RL#{self.project.number}]",
                    sender="Kunde <kunde@stadtwerke.example>",
                    to="Projekte <PROJEKTE@verleih.example>, Technik <technik@stadtwerke.example>",
                    headers={"Cc": '"Müller, Hans" <hans@stadtwerke.example>, kunde@stadtwerke.example'},
                )
            ),
        )
        self.mail = ProjectMail.objects.get()

    def test_answer_goes_to_the_sender(self) -> None:
        self.assertEqual(reply_recipients(self.mail, everyone=False), ("Kunde <kunde@stadtwerke.example>", ""))

    def test_answer_all_adds_the_others_without_the_own_mailbox(self) -> None:
        to, cc = reply_recipients(self.mail, everyone=True)
        self.assertEqual(to, "Kunde <kunde@stadtwerke.example>, Technik <technik@stadtwerke.example>")
        self.assertEqual(cc, '"Müller, Hans" <hans@stadtwerke.example>')

    def test_answer_to_a_sent_mail_goes_to_its_recipients(self) -> None:
        with capture_smtp():
            sent = send_project_mail(
                self.project,
                to="a@b.example",
                cc="c@d.example",
                bcc="geheim@e.example",
                subject="x",
                body="y",
                user=None,
            )
        self.assertEqual(reply_recipients(sent, everyone=False), ("a@b.example", ""))
        self.assertEqual(reply_recipients(sent, everyone=True), ("a@b.example", "c@d.example"))

    def test_blind_copies_reach_their_recipients_unseen(self) -> None:
        with recording_smtp():
            sent = send_project_mail(
                self.project,
                to="a@b.example",
                cc="Chef <chef@b.example>",
                bcc="Archiv <archiv@verleih.example>",
                subject="Angebot",
                body="Text",
                user=None,
            )
        ((_sender, envelope, transmitted),) = RecordingSMTP.sessions[0].transmitted
        self.assertEqual(sorted(envelope), ["a@b.example", "archiv@verleih.example", "chef@b.example"])
        message = message_from_bytes(transmitted, policy=policy.default)
        self.assertIsNone(message["Bcc"])
        self.assertNotIn(b"archiv@", transmitted)
        self.assertEqual(sent.bcc_addresses, "Archiv <archiv@verleih.example>")

    def test_every_address_field_is_checked(self) -> None:
        with capture_smtp(), self.assertRaises(ValidationError) as caught:
            send_project_mail(self.project, to="a@b.example", bcc="kein-mail", subject="x", body="y", user=None)
        self.assertIn("bcc", caught.exception.message_dict)


def rights_with(*, customers: bool = False, personnel: bool = False) -> Rights:
    """Rights of somebody who writes mails and may read customers and/or personnel."""
    levels = {}
    if customers:
        levels[Module.CUSTOMERS.value] = int(Level.READ)
    if personnel:
        levels[Module.PERSONNEL.value] = int(Level.READ)
    return Rights(
        module_levels=levels,
        special_rights=frozenset({SpecialRight.CORRESPONDENCE_READ, SpecialRight.CORRESPONDENCE_WRITE}),
    )


class AddressSuggestionTests(RentalarsTestCase):
    """EML-037: suggestions from customers, contacts and personnel – within the rights."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadtwerke Beckstadt")
        self.customer.email = "info@stadtwerke-beckstadt.example"
        self.customer.save()
        Contact.objects.create(
            customer=self.customer, name="Bernd Becker", email="b.becker@stadtwerke-beckstadt.example"
        )
        Contact.objects.create(customer=self.customer, name="Ohne Adresse Becker", email="")
        make_person("Anna Becker", email="anna.becker@verleih.example", position="Ton")

    def addresses(self, rights: Rights, text: str) -> list[str]:
        return [suggestion.address for suggestion in suggest_addresses(rights, text)]

    def test_three_characters_are_needed(self) -> None:
        everything = rights_with(customers=True, personnel=True)
        self.assertEqual(self.addresses(everything, "Be"), [])
        self.assertEqual(
            self.addresses(everything, "Beck"),
            [
                "b.becker@stadtwerke-beckstadt.example",
                "info@stadtwerke-beckstadt.example",
                "anna.becker@verleih.example",
            ],
        )

    def test_the_rights_decide_the_sources(self) -> None:
        self.assertEqual(self.addresses(rights_with(personnel=True), "Beck"), ["anna.becker@verleih.example"])
        self.assertEqual(
            self.addresses(rights_with(customers=True), "Beck"),
            ["b.becker@stadtwerke-beckstadt.example", "info@stadtwerke-beckstadt.example"],
        )
        self.assertEqual(self.addresses(rights_with(), "Beck"), [])

    def test_several_words_and_the_form_of_a_suggestion(self) -> None:
        (found,) = suggest_addresses(rights_with(customers=True, personnel=True), "anna beck")
        self.assertEqual(found.as_json()["label"], "Anna Becker <anna.becker@verleih.example>")
        self.assertEqual((found.source, found.detail), (gettext("Personnel"), "Ton"))
        (contact,) = suggest_addresses(rights_with(customers=True), "bernd")
        self.assertEqual((contact.source, contact.detail), (gettext("Contact"), "Stadtwerke Beckstadt"))

    def test_anonymised_customers_are_not_suggested(self) -> None:
        anonymise_customer(self.customer)
        self.assertEqual(self.addresses(rights_with(customers=True), "Beck"), [])


# --- EML-038: the sender ---------------------------------------------------------------------------------


class SenderNameTests(RentalarsTestCase):
    """EML-038: the sender is the writer with the company; the address stays the mailbox."""

    def test_name_and_company(self) -> None:
        company("Firma Muster")
        user = writer()
        self.assertEqual(sender_name(user), "Max Mustermann | Firma Muster")
        self.assertEqual(
            sender_label(user, "projekte@verleih.example"), "Max Mustermann | Firma Muster <projekte@verleih.example>"
        )
        self.assertIn("<projekte@verleih.example>", sender_header(user, "projekte@verleih.example"))

    def test_without_company_or_writer(self) -> None:
        company("")
        self.assertEqual(sender_name(writer()), "Max Mustermann")
        company("Firma Muster")
        self.assertEqual(sender_name(None, "Verleih Projekte"), "Verleih Projekte")
        self.assertEqual(sender_name(None), "Firma Muster")

    def test_a_sent_mail_names_the_writer(self) -> None:
        company("Licht & Ton GmbH")
        configure_mailbox()
        with capture_smtp() as sent:
            stored = send_project_mail(make_project(), to="a@b.example", subject="x", body="y", user=writer())
        self.assertEqual(sent[0]["From"].addresses[0].display_name, "Max Mustermann | Licht & Ton GmbH")
        self.assertEqual(sent[0]["From"].addresses[0].addr_spec, "projekte@verleih.example")
        self.assertEqual(stored.sender_name, "Max Mustermann | Licht & Ton GmbH")


# --- EML-039: the mail log -------------------------------------------------------------------------------


class MailLogFetchTests(RentalarsTestCase):
    """EML-039: every mail the fetch looks at is noted with its result."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.project = make_project()

    def test_assigned_unknown_and_left_in_the_inbox(self) -> None:
        box = FakeMailbox(
            make_mail(f"Frage [RL#{self.project.number}]", message_id="<a@x.example>"),
            make_mail("Frage [RL#1999-0001]", message_id="<b@x.example>"),
            make_mail("Newsletter", message_id="<c@x.example>", to="projekte@verleih.example, alle@x.example"),
        )
        fetch_mail(force=True, opener=box)
        entries = {entry.subject: entry for entry in MailLogEntry.objects.all()}
        assigned = entries[f"Frage [RL#{self.project.number}]"]
        self.assertEqual(
            (assigned.result, assigned.project, assigned.kind), (LogResult.ASSIGNED, self.project, "project")
        )
        self.assertEqual(assigned.mail, ProjectMail.objects.get())
        self.assertEqual(assigned.detail_text, gettext("by the tag in the subject"))
        self.assertEqual(
            (entries["Frage [RL#1999-0001]"].result, entries["Frage [RL#1999-0001]"].detail),
            ("unknown_tag", "1999-0001"),
        )
        left = entries["Newsletter"]
        self.assertEqual((left.result, left.direction), (LogResult.LEFT_IN_INBOX, Direction.INCOMING))
        self.assertEqual(left.recipients, "projekte@verleih.example, alle@x.example")
        self.assertEqual(left.sender, "Kunde <kunde@stadtwerke.example>")

        # The server renumbers its inbox: everything is looked at again, nothing is noted twice.
        box.validity = 99
        box.add(make_mail("Newsletter", message_id="<c@x.example>"))
        fetch_mail(force=True, opener=box)
        self.assertEqual(MailLogEntry.objects.filter(subject="Newsletter").count(), 1)

    def test_a_mail_that_cannot_be_read_is_noted_once(self) -> None:
        class Failing(FakeMailbox):
            def fetch(self, uid: int, *, limit: int | None = None) -> bytes:
                from rentalars.mail.imap import MailboxError

                raise MailboxError("Zeitüberschreitung")

        box = Failing(make_mail(f"Frage [RL#{self.project.number}]", message_id="<f@x.example>"))
        with self.assertLogs("rentalars.mail.fetching", "WARNING"):
            fetch_mail(force=True, opener=box)
            fetch_mail(force=True, opener=box)
        (entry,) = MailLogEntry.objects.all()
        self.assertEqual((entry.result, entry.detail), (LogResult.FAILED, "Zeitüberschreitung"))


class MailLogSendingTests(RentalarsTestCase):
    """EML-039: mails sent from a project are noted, sent or failed."""

    def test_sent_and_failed(self) -> None:
        configure_mailbox()
        project = make_project()
        user = writer()
        with capture_smtp():
            stored = send_project_mail(
                project, to="a@b.example", bcc="c@d.example", subject="Angebot", body="y", user=user
            )
        entry = MailLogEntry.objects.get()
        self.assertEqual(
            (entry.direction, entry.kind, entry.result, entry.project, entry.mail, entry.user),
            (Direction.OUTGOING, LogKind.PROJECT, LogResult.SENT, project, stored, user),
        )
        self.assertEqual(entry.recipients, "a@b.example, c@d.example")
        self.assertIn(f"Angebot [RL#{project.number}]", entry.subject)

        def refuse(mail_settings: Any, message: Any) -> None:
            raise ValidationError("Der Mailserver hat die Anmeldung abgelehnt.")

        with mock.patch("rentalars.mail.sending._send", refuse), self.assertRaises(ValidationError):
            send_project_mail(project, to="a@b.example", subject="Zweiter Versuch", body="y", user=user)
        failed = MailLogEntry.objects.get(result=LogResult.FAILED)
        self.assertEqual(failed.detail, "Der Mailserver hat die Anmeldung abgelehnt.")
        self.assertEqual(ProjectMail.objects.count(), 1)

    def test_writing_the_log_never_stops_a_mail(self) -> None:
        with (
            mock.patch.object(MailLogEntry.objects, "create", side_effect=RuntimeError("disk full")),
            self.assertLogs("rentalars.mail.log", "ERROR"),
        ):
            self.assertIsNone(
                log.record(direction=Direction.OUTGOING, kind=LogKind.SYSTEM, result=LogResult.SENT, subject="x")
            )


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND, EMAIL_INNER_BACKEND=LOCMEM_BACKEND)
class SystemMailLogTests(RentalarsTestCase):
    """EML-039: every mail Django sends – invitations, password links, notifications – is noted."""

    def test_the_settings_wrap_the_configured_backend(self) -> None:
        from rentalars import settings as configured

        self.assertEqual(configured.EMAIL_BACKEND, LOGGING_BACKEND)
        self.assertTrue(configured.EMAIL_INNER_BACKEND.startswith("django.core.mail.backends."))

    def test_a_system_mail_is_sent_and_noted(self) -> None:
        send_mail("Dein Zugang", "Hallo", "rentalars@verleih.example", ["berta@example.de"])
        self.assertEqual(len(django_mail.outbox), 1)
        entry = MailLogEntry.objects.get()
        self.assertEqual(
            (entry.direction, entry.kind, entry.result, entry.sender, entry.recipients, entry.subject),
            (
                Direction.OUTGOING,
                LogKind.SYSTEM,
                LogResult.SENT,
                "rentalars@verleih.example",
                "berta@example.de",
                "Dein Zugang",
            ),
        )

    def test_an_invitation_is_noted(self) -> None:
        from rentalars.accounts.services import send_invitation

        send_invitation(make_user("berta"))
        entry = MailLogEntry.objects.get()
        self.assertEqual((entry.kind, entry.recipients), (LogKind.SYSTEM, "berta@example.de"))

    @override_settings(EMAIL_INNER_BACKEND="tests.unit.test_051_mail.BrokenBackend")
    def test_a_failure_is_noted_and_still_raised(self) -> None:
        with self.assertRaises(smtplib.SMTPException):
            send_mail("Test", "Text", None, ["a@example.de"])
        self.assertEqual(send_mail("Leise", "Text", None, ["b@example.de"], fail_silently=True), 0)
        results = dict(MailLogEntry.objects.values_list("subject", "result"))
        self.assertEqual(results, {"Test": LogResult.FAILED, "Leise": LogResult.FAILED})
        self.assertEqual(MailLogEntry.objects.get(subject="Test").detail, "Server says no")

    @override_settings(EMAIL_INNER_BACKEND=LOGGING_BACKEND)
    def test_the_wrapper_never_wraps_itself(self) -> None:
        from rentalars.mail.backends import LoggingEmailBackend

        self.assertNotIsInstance(LoggingEmailBackend().inner, LoggingEmailBackend)


class MailLogRetentionTests(RentalarsTestCase):
    """EML-039: entries go with the mails' retention, or after a year if mails are kept."""

    def entry(self, days_ago: int, **fields: Any) -> MailLogEntry:
        return MailLogEntry.objects.create(
            timestamp=NOW - datetime.timedelta(days=days_ago),
            direction=Direction.OUTGOING,
            kind=LogKind.SYSTEM,
            result=LogResult.SENT,
            **fields,
        )

    def test_a_year_while_mails_are_kept(self) -> None:
        configure_mailbox(retention_days=0)
        self.entry(400)
        self.entry(300)
        self.assertEqual(delete_old_mail_log_entries(), 1)
        self.assertEqual(MailLogEntry.objects.count(), 1)

    def test_the_retention_of_the_mails(self) -> None:
        configure_mailbox(retention_days=30)
        self.entry(31)
        self.entry(29)
        self.assertEqual(log.delete_old_entries(), 1)

    def test_an_anonymised_customer_leaves_no_trace(self) -> None:
        configure_mailbox()
        customer = make_customer("Firma Muster")
        Contact.objects.create(customer=customer, name="Frau Muster", email="muster@firma.example")
        self.entry(1, sender="Frau Muster <muster@firma.example>")
        self.entry(1, recipients="a@b.example, MUSTER@firma.example")
        self.entry(1, recipients="andere@b.example")
        anonymise_customer(customer)
        self.assertEqual(list(MailLogEntry.objects.values_list("recipients", flat=True)), ["andere@b.example"])


class RightsTests(RentalarsTestCase):
    """EML-034, EML-039: who may change the signature, see it, and read the log."""

    def test_rights(self) -> None:
        from rentalars.mail import services

        admin_only = Role.objects.create(name="Nur Verwaltung", module_levels={"administration": int(Level.WRITE)})
        office = make_user("office")
        office.roles.set([admin_only])
        manager = make_user("paula", roles=("Projektleitung",))
        reader = make_user("lea", roles=("Nur-Lesen",))
        self.assertTrue(services.may_edit_signature(rights_of(office)))
        self.assertFalse(services.may_edit_signature(rights_of(manager)))
        self.assertTrue(services.may_see_signature(rights_of(manager)))
        self.assertFalse(services.may_see_signature(rights_of(reader)))
        self.assertTrue(services.may_open_mail_settings(rights_of(manager)))
        self.assertTrue(services.may_open_mail_settings(rights_of(office)))
        self.assertFalse(services.may_open_mail_settings(rights_of(reader)))
