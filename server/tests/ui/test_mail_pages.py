# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the project mailbox (chapter 5.15): settings, correspondence, writing, unknown tags."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import Mailbox, ProjectMail, UnknownTagMail
from rentalars.masterdata.models import DocumentType
from rentalars.projects.models import ProjectFile
from tests.helpers import make_project, make_user
from tests.mailbox import capture_smtp, configure_mailbox, mailbox, make_mail
from tests.ui.base import UiTestCase, form_data

PDF = b"%PDF-1.4\n%%EOF\n"


class MailboxSettingsPageTests(UiTestCase):
    """EML-001, EML-002, EML-005; the page lives in the settings (EML-035).

    Each mailbox has a page of its own (EML-041).
    """

    def test_set_up_the_mailbox(self) -> None:
        page = self.client.get("/administration/mail/mailboxes/new/")
        data = form_data(
            page,
            "imap_host",
            name="Projekte",
            is_active="on",
            address="projekte@verleih.example",
            imap_host="imap.verleih.example",
            imap_user="projekte@verleih.example",
            imap_password="geheim-1",
            smtp_host="smtp.verleih.example",
        )
        response = self.client.post("/administration/mail/mailboxes/new/", data, follow=True)
        self.assertIn("Das Postfach „Projekte“ wurde gespeichert.", self.messages_of(response))
        self.assertNotIn("geheim-1", response.content.decode())
        mailbox = Mailbox.objects.get()
        self.assertEqual(mailbox.imap_password, "geheim-1")
        # The first mailbox is offered for the correspondence and for sending it.
        self.assertEqual((mailbox.for_correspondence, mailbox.is_outgoing), (True, True))

        # Saving again without a password keeps the stored one (EML-002).
        url = f"/administration/mail/mailboxes/{mailbox.pk}/"
        self.client.post(url, form_data(self.client.get(url), "imap_host", imap_port="143", imap_security="starttls"))
        mailbox.refresh_from_db()
        self.assertEqual((mailbox.imap_password, mailbox.imap_port), ("geheim-1", 143))

    def test_fetch_now_and_the_list_of_unknown_tags(self) -> None:
        configure_mailbox()
        with mailbox(make_mail("Frage [RL#2099-0001]", message_id="<u1@x.example>")):
            response = self.client.post("/administration/mail/fetch/", {"next": "/projects/inquiries/"}, follow=True)
        self.assertIn("1 mit unbekannter Kennung", " ".join(self.messages_of(response)))
        self.assertIn("2099-0001", self.assert_ok(response))

        project = make_project()
        entry = UnknownTagMail.objects.get()
        with mailbox(make_mail("Frage [RL#2099-0002]", message_id="<u2@x.example>")) as box:
            box.add(make_mail("Frage [RL#2099-0001]", message_id="<u1@x.example>"))
            response = self.client.post(
                f"/projects/inquiries/{entry.pk}/assign/", {"project_number": project.number}, follow=True
            )
        mail = ProjectMail.objects.get()
        self.assertEqual(response.redirect_chain[-1][0], f"/projects/{project.number}/mails/{mail.pk}/")

    def test_dismiss_and_wrong_numbers(self) -> None:
        configure_mailbox()
        with mailbox(make_mail("Frage [RL#2099-0001]")):
            fetch_mail(force=True)
        entry = UnknownTagMail.objects.get()
        response = self.client.post(
            f"/projects/inquiries/{entry.pk}/assign/", {"project_number": "1999-0001"}, follow=True
        )
        self.assertIn("Ein Projekt mit dieser Nummer", " ".join(self.messages_of(response)))
        self.client.post(f"/projects/inquiries/{entry.pk}/dismiss/")
        entry.refresh_from_db()
        self.assertIsNotNone(entry.resolved_at)

    def test_the_module_needs_its_rights(self) -> None:
        crew = self.browser_for("ben", "Crew")
        self.assertEqual(crew.get("/projects/inquiries/").status_code, 403)
        reader = self.browser_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get("/projects/inquiries/").status_code, 200)
        self.assertEqual(reader.get("/administration/mail/").status_code, 403)


class CorrespondencePageTests(UiTestCase):
    """EML-015, EML-019 to EML-021, EML-024, EML-025, EML-027."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.project = make_project()
        self.other = make_project("Weinfest")
        with mailbox(
            make_mail(
                f"Rider [RL#{self.project.number}]",
                html='<p>Siehe <b>Anhang</b><img src="https://tracker.example/p.gif"><script>x()</script></p>',
                attachments=[("rider.pdf", "application/pdf", PDF)],
                message_id="<rider@band.example>",
            )
        ):
            fetch_mail(force=True)
        self.mail = ProjectMail.objects.get()
        self.base = f"/projects/{self.project.pk}/mails"

    def test_list_detail_and_the_cleaned_text(self) -> None:
        text = self.assert_ok(self.client.get(f"{self.base}/"))
        self.assertIn("Rider", text)
        detail = self.assert_ok(self.client.get(f"{self.base}/{self.mail.pk}/"))
        self.assertIn("rider.pdf", detail)
        self.assertIn("1 Bild von einem anderen Server wurde zurückgehalten.", detail)

        body = self.client.get(f"{self.base}/{self.mail.pk}/body/")
        self.assertIn("default-src 'none'", body["Content-Security-Policy"])
        self.assertNotIn("<script", body.content.decode())
        self.assertNotIn(' src="https://tracker', body.content.decode())
        shown = self.client.get(f"{self.base}/{self.mail.pk}/body/", {"external": "1"})
        self.assertIn('src="https://tracker.example/p.gif"', shown.content.decode())

        attachment = self.mail.attachments.get()
        download = self.client.get(f"{self.base}/{self.mail.pk}/attachments/{attachment.pk}/")
        self.assertEqual(b"".join(download.streaming_content), PDF)

    def test_take_an_attachment_into_the_files(self) -> None:
        attachment = self.mail.attachments.get()
        rider = DocumentType.objects.get(name="Rider")
        response = self.client.post(
            f"{self.base}/{self.mail.pk}/attachments/{attachment.pk}/to-files/",
            {"document_type": rider.pk},
            follow=True,
        )
        self.assertIn("„rider.pdf“ liegt jetzt bei den Dateien des Projekts.", self.messages_of(response))
        self.assertEqual(ProjectFile.objects.get().source_attachment, attachment)

    def test_answer_with_a_project_file_and_an_upload(self) -> None:
        self.client.post(
            f"/projects/{self.project.pk}/files/", {"file": SimpleUploadedFile("plan.pdf", PDF), "title": "Plan"}
        )
        page = self.client.get(f"{self.base}/new/", {"answer": self.mail.pk})
        data = form_data(page, "subject")
        self.assertEqual(data["subject"], f"AW: Rider [RL#{self.project.number}]")
        self.assertIn("> ", data["body"])
        data.update(
            body="Danke!\n" + data["body"],
            files=[str(ProjectFile.objects.get().pk)],
            uploads=SimpleUploadedFile("extra.pdf", PDF, content_type="application/pdf"),
        )
        with capture_smtp() as sent:
            response = self.client.post(f"{self.base}/new/?answer={self.mail.pk}", data, follow=True)
        self.assertIn("Die Mail wurde gesendet und beim Projekt abgelegt.", self.messages_of(response))
        (message,) = sent
        self.assertEqual(message["Subject"].count("[RL#"), 1)
        self.assertEqual(sorted(part.get_filename() for part in message.iter_attachments()), ["extra.pdf", "plan.pdf"])
        self.assertEqual(ProjectMail.objects.filter(direction="out").count(), 1)

    def test_writing_needs_the_right(self) -> None:
        reader = self.browser_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(f"{self.base}/").status_code, 200)
        self.assertEqual(reader.get(f"{self.base}/new/").status_code, 403)

    def test_move_and_remove(self) -> None:
        response = self.client.post(
            f"{self.base}/{self.mail.pk}/assign/", {"project_number": self.other.number}, follow=True
        )
        self.assertEqual(response.redirect_chain[-1][0], f"/projects/{self.other.number}/mails/{self.mail.pk}/")
        self.client.post(f"/projects/{self.other.pk}/mails/{self.mail.pk}/delete/")
        self.assertFalse(ProjectMail.objects.exists())

    def test_crew_never_sees_mails(self) -> None:
        ben = make_user("ben", roles=("Crew",))
        browser = self.browser_of(ben)
        self.assertEqual(browser.get(f"{self.base}/").status_code, 404)
