# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the mail module: tags, reading mails, fetching, sending, showing (chapter 5.15)."""

from __future__ import annotations

import datetime

from django.test import SimpleTestCase, override_settings

from rentalars.core.crypto import SecretUnreadableError, decrypt_secret, encrypt_secret
from rentalars.core.models import SystemSettings
from rentalars.customers.models import Contact
from rentalars.customers.services import anonymise_customer
from rentalars.mail import tags
from rentalars.mail.display import clean_html, content_security_policy
from rentalars.mail.fetching import fetch_is_due, fetch_mail
from rentalars.mail.models import AfterAssignment, MailKind, MailSettings, ProjectMail, UnknownTagMail, message_key
from rentalars.mail.parsing import parse_mail
from rentalars.mail.sending import reply_subject, send_project_mail, split_addresses
from rentalars.mail.services import delete_old_mails
from rentalars.notifications.models import Notification
from rentalars.projects.models import ProjectStatus
from tests.helpers import NOW, RentalarsTestCase, make_customer, make_project, make_user
from tests.mailbox import FakeMailbox, capture_smtp, configure_mailbox, make_mail


class TagTests(RentalarsTestCase):
    """EML-009 to EML-011: the tag in the subject.

    ADM-014: with a database – a number of today, 2027-0001, may be a former number of another project, which
    ``find_numbers`` asks the database about.
    """

    def test_found_whatever_the_spelling(self) -> None:
        for subject in (
            "[RL#2027-0001] Bühnenplan",
            "AW: WG: Bühnenplan [RL#2027-0001]",
            "Re: Bühnenplan [ rl # 2027-0001 ]",
            "Bühnenplan[RL#2027-0001]und mehr",
        ):
            self.assertEqual(tags.find_numbers(subject, prefix="RL"), ["2027-0001"], subject)

    def test_other_prefixes_and_brackets_do_not_count(self) -> None:
        self.assertEqual(tags.find_numbers("[XY#2027-0001] [RL 2027-0002] RL#2027-0003", prefix="RL"), [])
        self.assertEqual(tags.find_numbers("[XY#2027-0001]", prefix="XY"), ["2027-0001"])

    def test_the_tag_is_added_once(self) -> None:
        self.assertEqual(tags.subject_with_tag("Angebot", "2027-0001", prefix="RL"), "Angebot [RL#2027-0001]")
        self.assertEqual(
            tags.subject_with_tag("AW: Angebot [rl# 2027-0001]", "2027-0001", prefix="RL"),
            "AW: Angebot [rl# 2027-0001]",
        )
        self.assertEqual(
            tags.subject_with_tag("AW: Angebot [rl#prj-2027-0001]", "PRJ-2027-0001", prefix="RL"),
            "AW: Angebot [rl#prj-2027-0001]",
        )
        self.assertEqual(reply_subject("Angebot"), "AW: Angebot")
        self.assertEqual(reply_subject("Re: Angebot"), "Re: Angebot")

    def test_addresses_are_checked(self) -> None:
        self.assertEqual(
            split_addresses("a@x.example, Bea <b@y.example>; c@z.example"),
            ["a@x.example", "Bea <b@y.example>", "c@z.example"],
        )


class TagPrefixTests(RentalarsTestCase):
    """EML-009: the prefix is a system setting."""

    def test_the_prefix_comes_from_the_settings(self) -> None:
        settings = SystemSettings.load()
        settings.mail_tag_prefix = "VL"
        settings.save()
        project = make_project()
        self.assertEqual(project.mail_tag, f"[VL#{project.number}]")
        self.assertEqual(tags.find_numbers(f"Frage [VL#{project.number}]"), [project.number])


class ParsingTests(SimpleTestCase):
    """EML-019, EML-020, EML-030: what is read from a mail."""

    def test_text_html_and_attachments(self) -> None:
        raw = make_mail(
            "Bühnenplan",
            sender="Jörg Müller <joerg@stadtwerke.example>",
            html="<p>Hallo</p>",
            attachments=[("Bühne.pdf", "application/pdf", b"%PDF")],
            message_id="<abc@stadtwerke.example>",
        )
        parsed = parse_mail(raw)
        self.assertEqual((parsed.sender_name, parsed.sender_address), ("Jörg Müller", "joerg@stadtwerke.example"))
        self.assertIn("Bühnenplan", parsed.text)
        self.assertIn("<p>Hallo</p>", parsed.html)
        self.assertEqual([attachment.filename for attachment in parsed.attachments], ["Bühne.pdf"])
        self.assertEqual(parsed.key, message_key("ABC@stadtwerke.example"))

    def test_automatic_replies_and_bounces_are_recognised(self) -> None:
        auto = parse_mail(make_mail("Abwesend", headers={"Auto-Submitted": "auto-replied"}))
        self.assertEqual(auto.kind, MailKind.AUTO_REPLY)
        bounce = parse_mail(make_mail("Undeliverable", sender="MAILER-DAEMON@mx.example"))
        self.assertEqual(bounce.kind, MailKind.BOUNCE)
        self.assertEqual(parse_mail(make_mail("Frage")).kind, MailKind.NORMAL)


class DisplayTests(SimpleTestCase):
    """EML-027: the HTML of a mail is cleaned and external pictures are held back."""

    def test_scripts_and_handlers_go(self) -> None:
        html, blocked = clean_html(
            '<p onclick="x()">A<script>alert(1)</script><a href="javascript:x()">b</a>'
            '<iframe src="https://x"></iframe><form><input></form></p>',
            allow_external=False,
            cid_url=lambda _cid: None,
        )
        self.assertEqual(blocked, 0)
        for gone in ("script", "onclick", "javascript", "iframe", "<form", "<input"):
            self.assertNotIn(gone, html)

    def test_external_pictures_wait_for_the_reader(self) -> None:
        source = '<img src="https://tracker.example/p.gif"><img src="cid:logo@x">'
        html, blocked = clean_html(source, allow_external=False, cid_url=lambda cid: f"/files/{cid}")
        self.assertEqual(blocked, 1)
        self.assertNotIn(' src="https://', html)
        self.assertIn('src="/files/logo@x"', html)
        html, blocked = clean_html(source, allow_external=True, cid_url=lambda cid: None)
        self.assertIn('src="https://tracker.example/p.gif"', html)
        self.assertIn("img-src 'self' data:;", content_security_policy(allow_external=False) + ";")
        self.assertIn("https:", content_security_policy(allow_external=True))


class FetchTests(RentalarsTestCase):
    """EML-005 to EML-008, EML-012 to EML-014, EML-018, EML-023, EML-028, EML-032."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("paula", roles=("Projektleitung",))
        self.project = make_project(manager=self.manager)
        self.mail_settings = configure_mailbox()

    def fetch(self, box: FakeMailbox) -> object:
        return fetch_mail(force=True, opener=box)

    def test_nothing_happens_without_a_mailbox(self) -> None:
        self.mail_settings.is_active = False
        self.mail_settings.save()
        self.assertTrue(fetch_mail(force=True, opener=FakeMailbox()).skipped)

    def test_the_interval_is_kept(self) -> None:
        # The interval holds for all mailboxes; each mailbox keeps the time of its last fetch (EML-041).
        rules = MailSettings.load()
        rules.interval_minutes = 5
        rules.save()
        self.mail_settings.last_fetch_at = NOW - datetime.timedelta(minutes=3)
        self.assertFalse(fetch_is_due(self.mail_settings))
        self.mail_settings.save()
        self.assertTrue(fetch_mail(opener=FakeMailbox()).skipped)
        self.mail_settings.last_fetch_at = NOW - datetime.timedelta(minutes=5)
        self.assertTrue(fetch_is_due(self.mail_settings))

    def test_only_new_mails_are_looked_at(self) -> None:
        box = FakeMailbox(make_mail("Newsletter"))
        self.assertEqual(self.fetch(box).looked_at, 1)
        newsletter = next(iter(box.inbox))
        uid = box.add(make_mail(f"Frage [RL#{self.project.number}]"))
        result = self.fetch(box)
        self.assertEqual((result.looked_at, len(result.imported)), (1, 1))
        # Only the assigned mail was read completely; the newsletter stays untouched in the inbox (EML-013).
        self.assertEqual((box.fetched, list(box.inbox)), ([uid], [newsletter]))

    def test_a_new_uid_validity_starts_over(self) -> None:
        """When the server renumbers the inbox, everything is looked at again – nothing is stored twice."""
        raw = make_mail(f"Frage [RL#{self.project.number}]", message_id="<once@x.example>")
        box = FakeMailbox(raw)
        self.fetch(box)
        box.validity = 99
        box.add(raw)  # the same mail, still there because moving failed
        result = self.fetch(box)
        self.assertEqual(result.imported, [])
        self.assertEqual(ProjectMail.objects.count(), 1)
        self.assertEqual(box.inbox, {})  # filed away this time

    def test_deleting_instead_of_moving(self) -> None:
        """EML-006; a choice per mailbox (EML-041)."""
        self.mail_settings.after_assignment = AfterAssignment.DELETE
        self.mail_settings.save()
        box = FakeMailbox(make_mail(f"Frage [RL#{self.project.number}]"))
        self.fetch(box)
        self.assertEqual((len(box.deleted), box.done), (1, []))

    def test_mails_of_finished_projects_are_marked(self) -> None:
        """EML-018: the mail is stored, and the project manager is told that the project is finished."""
        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        self.fetch(FakeMailbox(make_mail(f"Nachtrag [RL#{self.project.number}]")))
        mail = ProjectMail.objects.get()
        self.assertTrue(mail.project_was_finished)
        notice = Notification.objects.get(user=self.manager)
        self.assertIn("(abgeschlossen)", notice.title)

    def test_large_mails_leave_their_attachments(self) -> None:
        """EML-028; the limit holds for all mailboxes."""
        rules = MailSettings.load()
        rules.max_message_mb = 1
        rules.save()
        big = make_mail(
            f"Video [RL#{self.project.number}]",
            attachments=[("film.pdf", "application/pdf", b"0" * (2 * 1024 * 1024))],
        )
        self.fetch(FakeMailbox(big))
        mail = ProjectMail.objects.get()
        self.assertEqual(mail.attachments.count(), 0)
        self.assertIn("größer als 1 MB", mail.attachments_note)

    def test_several_tags_the_first_counts_and_unknown_ones_are_listed(self) -> None:
        other = make_project("Weinfest")
        self.fetch(FakeMailbox(make_mail(f"[RL#{other.number}] und [RL#{self.project.number}]")))
        self.assertEqual(ProjectMail.objects.get().project, other)
        self.fetch(FakeMailbox(make_mail("[RL#1999-0001] alt")))
        self.assertEqual(UnknownTagMail.objects.get().tag, "1999-0001")

    def test_errors_are_reported_once_until_it_works_again(self) -> None:
        admin = make_user("admin", superuser=True)
        box = FakeMailbox()
        box.fail = "Connection refused"
        with self.assertLogs("rentalars.mail.fetching", "WARNING"):
            self.fetch(box)
            self.fetch(box)
        self.assertEqual(Notification.objects.filter(kind="mail_problem", user=admin).count(), 1)
        box.fail = ""
        self.fetch(box)
        # The state of the fetch is kept per mailbox (EML-041).
        self.mail_settings.refresh_from_db()
        self.assertEqual((self.mail_settings.last_error, self.mail_settings.error_reported), ("", False))


class SendingTests(RentalarsTestCase):
    """EML-011, EML-012, EML-024: sending from a project."""

    def test_an_answer_refers_to_the_mail_and_comes_back(self) -> None:
        configure_mailbox()
        project = make_project()
        box = FakeMailbox(make_mail(f"Frage [RL#{project.number}]", message_id="<q@kunde.example>"))
        fetch_mail(force=True, opener=box)
        question = ProjectMail.objects.get()
        with capture_smtp() as sent:
            answer = send_project_mail(
                project, to="kunde@kunde.example", subject="AW: Frage", body="Antwort", answer_to=question, user=None
            )
        self.assertEqual(sent[0]["References"], "<q@kunde.example>")
        # The customer answers without the tag; it still finds its project (EML-012).
        box.add(make_mail("AW: AW: Frage", in_reply_to=answer.message_id))
        result = fetch_mail(force=True, opener=box)
        self.assertEqual(result.imported[0].project, project)

    def test_nothing_is_sent_without_a_mailbox(self) -> None:
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            send_project_mail(make_project(), to="a@b.example", subject="x", body="y", user=None)


class RetentionTests(RentalarsTestCase):
    """EML-031, NFA-011: mails are deleted after the retention period and with an anonymised customer."""

    def test_old_mails_go(self) -> None:
        configure_mailbox(retention_days=30)
        project = make_project()
        fetch_mail(
            force=True,
            opener=FakeMailbox(
                make_mail(f"alt [RL#{project.number}]", date=datetime.datetime(2026, 12, 1, tzinfo=datetime.UTC)),
                make_mail(f"neu [RL#{project.number}]", date=datetime.datetime(2027, 2, 25, tzinfo=datetime.UTC)),
            ),
        )
        self.assertEqual(delete_old_mails(), 1)
        self.assertEqual(list(ProjectMail.objects.values_list("subject", flat=True)), [f"neu [RL#{project.number}]"])
        settings = MailSettings.load()
        settings.retention_days = 0
        settings.save()
        self.assertEqual(delete_old_mails(), 0)

    def test_mails_of_an_anonymised_customer_go(self) -> None:
        configure_mailbox()
        customer = make_customer("Firma Muster")
        Contact.objects.create(customer=customer, name="Frau Muster", email="muster@firma.example")
        project = make_project(customer=customer)
        other = make_project("Fremd", customer=make_customer("Andere"))
        fetch_mail(
            force=True,
            opener=FakeMailbox(
                make_mail(f"Projekt [RL#{project.number}]"),
                make_mail(f"Weitergeleitet [RL#{other.number}]", sender="muster@firma.example"),
                make_mail(f"Ohne Bezug [RL#{other.number}]"),
            ),
        )
        anonymise_customer(customer)
        self.assertEqual(
            list(ProjectMail.objects.values_list("subject", flat=True)), [f"Ohne Bezug [RL#{other.number}]"]
        )


class CryptoTests(SimpleTestCase):
    """EML-002: stored passwords are encrypted and need the secret key."""

    def test_round_trip_and_another_key(self) -> None:
        token = encrypt_secret("geheim")
        self.assertNotIn("geheim", token)
        self.assertEqual(decrypt_secret(token), "geheim")
        self.assertEqual((encrypt_secret(""), decrypt_secret("")), ("", ""))
        with override_settings(SECRET_KEY="ein-ganz-anderer-schluessel-" * 3), self.assertRaises(SecretUnreadableError):
            decrypt_secret(token)
