# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the mail wishes (EML-034 to EML-039).

The mailbox and the signature in the settings, writing with CC, BCC and
address suggestions, answering all, the compact mail and the conversation,
and the mail log.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.utils.translation import gettext

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, SpecialRight
from rentalars.core.models import CompanyProfile
from rentalars.customers.models import Contact
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import Direction, LogKind, LogResult, Mailbox, MailLogEntry, MailSettings, ProjectMail
from rentalars.mail.sending import send_project_mail
from tests.helpers import NOW, make_customer, make_person, make_project, make_user
from tests.mailbox import capture_smtp, configure_mailbox, mailbox, make_mail
from tests.ui.base import UiTestCase, form_data

SETTINGS = "/administration/mail/"
SIGNATURE = "/administration/mail/signature/"
PREVIEW = "/administration/mail/signature/preview/"
LOG = "/administration/mail/log/"


def role(name: str, levels: dict[str, int], special: tuple[str, ...] = ()) -> Role:
    """A role of its own for a test about rights."""
    return Role.objects.create(name=name, module_levels=levels, special_rights=list(special))


class MailTestCase(UiTestCase):
    """A company, a mailbox, and an administrator with a full name."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.name = "Firma Muster"
        profile.save()
        make_person("Max Mustermann", user=self.admin_user, position="Leitung Licht", phone="0170 1234567")
        self.admin_user.refresh_from_db()
        configure_mailbox()

    def browser_with(self, username: str, *roles: Role) -> Any:
        user = make_user(username)
        user.roles.set(roles)
        return self.browser_of(user)


class SettingsPageTests(MailTestCase):
    """EML-035: the mailbox lives in the settings and can send with the IMAP access data."""

    def test_the_page_belongs_to_the_settings(self) -> None:
        text = self.assert_ok(self.client.get(SETTINGS))
        self.assertIn('<a href="/administration/" aria-current="page">', text)
        self.assertIn('<div class="breadcrumb"><a href="/administration/">', text)
        # NFA-074: the old address is gone.
        self.assertEqual(self.client.get("/mail/settings/").status_code, 404)
        administration = self.assert_ok(self.client.get("/administration/"))
        self.assertIn(f'<a href="{SETTINGS}">', administration)
        self.assertIn(f'<a href="{LOG}">Mail-Protokoll</a>', administration)

    # The access data belong to each mailbox, changed on a page of its own (EML-041).

    def mailbox_page(self) -> str:
        return f"/administration/mail/mailboxes/{Mailbox.objects.get().pk}/"

    def test_sending_with_the_access_data_of_the_mailbox_or_its_own(self) -> None:
        page = self.client.get(self.mailbox_page())
        text = self.assert_ok(page)
        self.assertIn('data-show-if="smtp_same_login="', text)
        data = form_data(page, "imap_host")
        self.assertEqual(data["smtp_same_login"], "on")

        data.update(smtp_same_login=None, smtp_user="versand@verleih.example", smtp_password="versand-geheim")
        data.pop("smtp_same_login")
        response = self.client.post(self.mailbox_page(), data, follow=True)
        self.assertIn("Das Postfach „Projekte“ wurde gespeichert.", self.messages_of(response))
        stored = Mailbox.objects.get()
        self.assertEqual(
            (stored.smtp_same_login, stored.smtp_login, stored.smtp_password),
            (False, "versand@verleih.example", "versand-geheim"),
        )

        data = form_data(self.client.get(self.mailbox_page()), "imap_host", smtp_same_login="on")
        self.client.post(self.mailbox_page(), data)
        stored = Mailbox.objects.get()
        self.assertEqual((stored.smtp_same_login, stored.smtp_user, stored.smtp_password_encrypted), (True, "", ""))
        self.assertEqual(stored.smtp_login, stored.imap_user)

    def test_an_own_user_without_password_is_refused(self) -> None:
        data = form_data(self.client.get(self.mailbox_page()), "imap_host", smtp_user="versand@verleih.example")
        data.pop("smtp_same_login")
        text = self.assert_ok(self.client.post(self.mailbox_page(), data))
        self.assertIn(gettext("Enter the password for sending."), text)

    def test_mailbox_and_signature_have_their_own_rights(self) -> None:
        manager = self.browser_for("paula", "Projektleitung")
        text = self.assert_ok(manager.get(SETTINGS))
        self.assertIn(f'href="{self.mailbox_page()}"', text)
        self.assertNotIn(f'href="{SIGNATURE}"', text)
        self.assertIn('name="imap_host"', self.assert_ok(manager.get(self.mailbox_page())))

        office = self.browser_with("otto", role("Büro", {"administration": int(Level.WRITE)}))
        text = self.assert_ok(office.get(SETTINGS))
        self.assertNotIn(f'href="{self.mailbox_page()}"', text)
        self.assertIn(f'href="{SIGNATURE}"', text)
        self.assertEqual(office.get(self.mailbox_page()).status_code, 403)
        self.assertEqual(office.post(SETTINGS, {"interval_minutes": "3"}).status_code, 403)

        reader = self.browser_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(SETTINGS).status_code, 403)
        self.assertEqual(reader.get(LOG).status_code, 403)


class SignaturePageTests(MailTestCase):
    """EML-034: one signature for everybody, with placeholders and a preview."""

    def test_write_the_signature(self) -> None:
        page = self.client.get(SIGNATURE)
        text = self.assert_ok(page)
        for token in ("{vorname}", "{nachname}", "{position}", "{email}", "{telefon}", "{firma}"):
            self.assertIn(f'data-insert-placeholder="{token}"', text)
        data = form_data(
            page, "html", html="<p>Gruß<br><b>{vorname} {nachname}</b>, {position}<script>x()</script></p>"
        )
        response = self.client.post(SIGNATURE, data, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], SETTINGS)
        self.assertEqual(MailSettings.load().signature_html, "<p>Gruß<br><b>{vorname} {nachname}</b>, {position}</p>")
        self.assertIn(f'src="{PREVIEW}?text=1"', self.assert_ok(response))

        preview = self.client.get(PREVIEW, {"text": "1"})
        self.assertEqual(preview["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("default-src 'none'", preview["Content-Security-Policy"])
        body = preview.content.decode()
        self.assertIn("<b>Max Mustermann</b>, Leitung Licht", body)
        self.assertIn("Gruß\nMax Mustermann, Leitung Licht", body)

    def test_the_preview_of_a_draft(self) -> None:
        response = self.client.post(PREVIEW, {"html": "Tel. {telefon}\n{firma}", "text": "1"})
        body = response.content.decode()
        self.assertIn("Tel. 0170 1234567<br>", body)
        self.assertIn("Firma Muster", body)

    def test_rights(self) -> None:
        manager = self.browser_for("paula", "Projektleitung")
        self.assertEqual(manager.get(SIGNATURE).status_code, 403)
        self.assertEqual(manager.get(PREVIEW).status_code, 200)
        self.assertEqual(manager.post(PREVIEW, {"html": "x"}).status_code, 403)
        crew = self.browser_for("ben", "Crew")
        self.assertEqual(crew.get(PREVIEW).status_code, 403)
        office = self.browser_with("otto", role("Büro", {"administration": int(Level.WRITE)}))
        self.assertEqual(office.get(SIGNATURE).status_code, 200)


class ComposePageTests(MailTestCase):
    """EML-034, EML-037, EML-038: writing with CC, BCC, suggestions, signature and the writer as sender."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        with mailbox(
            make_mail(
                f"Rider [RL#{self.project.number}]",
                sender="Band <band@band.example>",
                to="projekte@verleih.example, Technik <technik@band.example>",
                headers={"Cc": "manager@band.example"},
                text="Danke!\n\nAm 28.02.2027 schrieb Projekte:\n> Hier der Plan",
            )
        ):
            fetch_mail(force=True)
        self.mail = ProjectMail.objects.get()
        self.base = f"/projects/{self.project.number}/mails"

    def test_the_fields_and_the_sender(self) -> None:
        text = self.assert_ok(self.client.get(f"{self.base}/new/"))
        self.assertIn('<label for="id_cc">CC</label>', text)
        self.assertIn('<label for="id_bcc">BCC</label>', text)
        self.assertNotIn("Kopie an", text)
        self.assertIn('data-address-suggest="/projects/mail-addresses/"', text)
        self.assertIn("Max Mustermann | Firma Muster &lt;projekte@verleih.example&gt;", text)
        self.assertNotIn('name="signature"', text)

    def test_answer_all(self) -> None:
        detail = self.assert_ok(self.client.get(f"{self.base}/{self.mail.pk}/"))
        self.assertIn(f"?answer={self.mail.pk}&amp;all=1", detail)
        page = self.client.get(f"{self.base}/new/", {"answer": self.mail.pk, "all": "1"})
        self.assertIn(gettext("Answer all"), self.assert_ok(page))
        data = form_data(page, "subject")
        self.assertEqual(data["to"], "Band <band@band.example>, Technik <technik@band.example>")
        self.assertEqual(data["cc"], "manager@band.example")
        answer = form_data(self.client.get(f"{self.base}/new/", {"answer": self.mail.pk}), "subject")
        self.assertEqual((answer["to"], answer["cc"]), ("Band <band@band.example>", ""))

    def test_send_with_blind_copy_and_signature(self) -> None:
        mail_settings = MailSettings.load()
        mail_settings.signature_html = "<p>Gruß {vorname}</p>"
        mail_settings.save()
        page = self.client.get(f"{self.base}/new/")
        text = self.assert_ok(page)
        self.assertIn('data-show-if="signature=on"', text)
        # EML-026: the preview names the mailbox of the sender – its own signature, else the common one.
        outgoing = Mailbox.objects.get(is_outgoing=True)
        self.assertIn(f'src="{PREVIEW}?mailbox={outgoing.pk}"', text)
        data = form_data(
            page,
            "subject",
            to="kunde@kunde.example",
            bcc="Archiv <archiv@verleih.example>",
            subject="Angebot",
            body="Hallo",
        )
        self.assertEqual(data["signature"], "on")
        with capture_smtp() as sent:
            self.client.post(f"{self.base}/new/", data)
        stored = ProjectMail.objects.get(direction=Direction.OUTGOING)
        self.assertEqual(stored.bcc_addresses, "Archiv <archiv@verleih.example>")
        self.assertIn("Gruß Max", stored.html_body)
        self.assertEqual(sent[0]["Bcc"], "Archiv <archiv@verleih.example>")

        data.pop("signature")
        with capture_smtp() as sent:
            self.client.post(f"{self.base}/new/", data)
        self.assertEqual(sent[0].get_content_type(), "text/plain")

    def test_a_wrong_blind_copy_address_is_shown_at_its_field(self) -> None:
        data = form_data(
            self.client.get(f"{self.base}/new/"), "subject", to="a@b.example", bcc="kaputt", subject="x", body="x"
        )
        with capture_smtp() as sent:
            text = self.assert_ok(self.client.post(f"{self.base}/new/", data))
        self.assertEqual(sent, [])
        self.assertIn(gettext("An address is not valid."), text)

    def test_address_suggestions(self) -> None:
        customer = make_customer("Stadtwerke Beckstadt")
        Contact.objects.create(customer=customer, name="Bernd Becker", email="b.becker@stadtwerke.example")
        make_person("Anna Becker", email="anna@verleih.example")
        found = self.client.get("/projects/mail-addresses/", {"q": "beck"}).json()
        self.assertEqual(
            [item["label"] for item in found],
            ["Bernd Becker <b.becker@stadtwerke.example>", "Anna Becker <anna@verleih.example>"],
        )
        self.assertEqual(self.client.get("/projects/mail-addresses/", {"q": "be"}).json(), [])
        mail_only = role(
            "Nur Mail",
            {"projects": int(Level.READ)},
            (SpecialRight.CORRESPONDENCE_READ, SpecialRight.CORRESPONDENCE_WRITE),
        )
        self.assertEqual(self.browser_with("mia", mail_only).get("/projects/mail-addresses/", {"q": "beck"}).json(), [])
        self.assertEqual(
            self.browser_for("luka", "Lager").get("/projects/mail-addresses/", {"q": "beck"}).status_code, 403
        )


class CompactMailTests(MailTestCase):
    """EML-036: the headers fold away; a one-liner gets a small frame."""

    def test_compact_mail(self) -> None:
        project = make_project()
        with mailbox(make_mail(f"Kurz [RL#{project.number}]", html="<p>Danke!</p>", text="Danke!")):
            fetch_mail(force=True)
        mail = ProjectMail.objects.get()
        text = self.assert_ok(self.client.get(f"/projects/{project.number}/mails/{mail.pk}/"))
        self.assertIn('<details class="mail-meta">', text)
        self.assertIn('class="mail-frame is-short"', text)
        # Only one recipient besides the own mailbox: "answer all" would reach nobody more.
        self.assertNotIn("all=1", text)


class ConversationPageTests(MailTestCase):
    """EML-036: the correspondence as a conversation, received left and sent right."""

    def test_the_conversation(self) -> None:
        project = make_project()
        with mailbox(
            make_mail(
                f"Frage [RL#{project.number}]",
                text="Habt ihr noch Nebel?\n\n-- \nKunde GmbH",
                date=datetime.datetime(2027, 2, 27, 9, 0, tzinfo=datetime.UTC),
            )
        ):
            fetch_mail(force=True)
        question = ProjectMail.objects.get()
        with capture_smtp():
            send_project_mail(
                project,
                to="kunde@stadtwerke.example",
                subject="AW: Frage",
                body="Ja, zwei Stück.\n\nAm 27.02.2027 schrieb Kunde:\n> Habt ihr noch Nebel?",
                answer_to=question,
                user=self.admin_user,
            )
        base = f"/projects/{project.number}/mails/"
        text = self.assert_ok(self.client.get(base, {"view": "conversation"}))
        self.assertLess(text.index('class="bubble is-in"'), text.index('class="bubble is-out"'))
        self.assertLess(text.index("Habt ihr noch Nebel?"), text.index("Ja, zwei Stück."))
        self.assertIn(gettext("Show quoted text and signature"), text)
        self.assertIn("data-scroll-end", text)
        # The choice is remembered, until the list is chosen again.
        self.assertIn('class="conversation"', self.assert_ok(self.client.get(base)))
        self.assertNotIn('class="conversation"', self.assert_ok(self.client.get(base, {"view": "list"})))
        self.assertNotIn('class="conversation"', self.assert_ok(self.client.get(base)))


class MailLogPageTests(MailTestCase):
    """EML-039: the mail log with its filters and the CSV file."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        for subject, direction, kind, result, days in (
            ("Einladung", Direction.OUTGOING, LogKind.SYSTEM, LogResult.SENT, 1),
            ("Newsletter", Direction.INCOMING, LogKind.PROJECT, LogResult.LEFT_IN_INBOX, 2),
            ("Angebot", Direction.OUTGOING, LogKind.PROJECT, LogResult.FAILED, 10),
        ):
            MailLogEntry.objects.create(
                timestamp=NOW - datetime.timedelta(days=days),
                subject=subject,
                direction=direction,
                kind=kind,
                result=result,
                sender="projekte@verleih.example",
                recipients="kunde@stadtwerke.example",
                project=self.project if subject == "Angebot" else None,
                detail="Anmeldung abgelehnt" if result == LogResult.FAILED else "",
            )

    def subjects(self, **filters: str) -> list[str]:
        response = self.client.get(LOG, filters)
        self.assert_ok(response)
        return [MailLogEntry.objects.get(pk=row.pk).subject for row in response.context["rows"]]

    def test_the_log_and_its_filters(self) -> None:
        text = self.assert_ok(self.client.get(LOG))
        self.assertIn('<div class="breadcrumb"><a href="/administration/">', text)
        self.assertIn("Anmeldung abgelehnt", text)
        # the project link opens the Überblick – adapted.
        self.assertIn(f'href="/projects/{self.project.number}/overview/"', text)
        self.assertEqual(self.subjects(), ["Einladung", "Newsletter", "Angebot"])
        self.assertEqual(self.subjects(direction="in"), ["Newsletter"])
        self.assertEqual(self.subjects(kind="system"), ["Einladung"])
        self.assertEqual(self.subjects(result="failed"), ["Angebot"])
        self.assertEqual(self.subjects(q=self.project.number), ["Angebot"])
        self.assertEqual(self.subjects(since="2027-02-27"), ["Einladung", "Newsletter"])
        self.assertEqual(self.subjects(until="2027-02-20"), ["Angebot"])

    def test_csv_export(self) -> None:
        response = self.client.get(LOG, {"format": "csv", "kind": "project"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        text = response.content.decode("utf-8-sig")
        self.assertIn("Zeitpunkt;Richtung;Art;Von;An;Betreff;Projekt;Ergebnis", text.splitlines()[0])
        self.assertIn("fehlgeschlagen: Anmeldung abgelehnt", text)
        self.assertNotIn("Einladung", text)

    def test_fetching_and_sending_fill_the_log(self) -> None:
        MailLogEntry.objects.all().delete()
        with mailbox(make_mail(f"Frage [RL#{self.project.number}]"), make_mail("Werbung")):
            self.client.post("/administration/mail/fetch/", {"next": "/projects/inquiries/"})
        text = self.assert_ok(self.client.get(LOG))
        self.assertIn("Werbung", text)
        self.assertIn(gettext("left in the inbox"), text)
        self.assertIn(gettext("assigned"), text)
