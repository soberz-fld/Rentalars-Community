# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the project mailbox (chapter 5.15) and acceptance scenario 12.

The mailbox is :class:`tests.mailbox.FakeMailbox`; sending is caught before
it reaches a server.
"""

from __future__ import annotations

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.mail.models import Mailbox, ProjectMail, UnknownTagMail
from rentalars.masterdata.models import DocumentType
from rentalars.notifications.models import Notification
from rentalars.projects.models import ProjectMembership
from tests.api.base import API, ApiTestCase
from tests.helpers import make_project, make_user
from tests.mailbox import PASSWORD, capture_smtp, configure_mailbox, mailbox, make_mail

PDF = b"%PDF-1.4\n%%EOF\n"


class MailboxSettingsApiTests(ApiTestCase):
    """EML-001, EML-002: the mailbox is set up by administrators; passwords are never shown.

    The mailbox fields of ``/mail/settings`` mean the mailbox that sends the
    correspondence; the first change creates it (EML-041).
    """

    def test_read_and_change_the_settings(self) -> None:
        response = self.admin.patch(
            f"{API}/mail/settings",
            {
                "is_enabled": True,
                "address": "projekte@verleih.example",
                "imap_host": "imap.verleih.example",
                "imap_user": "projekte@verleih.example",
                "imap_password": "geheim-1",
                "smtp_host": "smtp.verleih.example",
                "interval_minutes": 5,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        data = response.json()
        self.assertTrue(data["has_imap_password"])
        self.assertNotIn("imap_password", data)
        self.assertNotIn("geheim-1", str(data))
        mailbox = Mailbox.objects.get()
        self.assertEqual(
            (mailbox.imap_password, mailbox.for_correspondence, mailbox.is_outgoing), ("geheim-1", True, True)
        )
        self.assertNotIn("geheim-1", mailbox.imap_password_encrypted)

        read = self.admin.get(f"{API}/mail/settings").json()
        self.assertEqual(read["interval_minutes"], 5)
        # Sending without a new password keeps the stored one.
        self.admin.patch(f"{API}/mail/settings", {"sender_name": "Verleih", "imap_port": 993}, format="json")
        self.assertEqual(Mailbox.objects.get().imap_password, "geheim-1")

    def test_switching_on_needs_a_password(self) -> None:
        response = self.admin.patch(
            f"{API}/mail/settings",
            {"is_enabled": True, "imap_host": "imap.example", "imap_user": "x"},
            format="json",
        )
        self.assert_error(response, 400, "validation_error", "imap_password")

    def test_only_writers_of_the_module_see_the_settings(self) -> None:
        self.assert_error(self.client_for("paula", "Nur-Lesen").get(f"{API}/mail/settings"), 403, "permission_denied")


class ScenarioTwelveMailAssignmentTests(ApiTestCase):
    """Acceptance scenario 12: mails are assigned by the tag in the subject."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.manager = make_user("paula", roles=("Projektleitung",))
        self.project = make_project(manager=self.manager)
        self.tag = f"[RL#{self.project.number}]"

    def test_scenario_12(self) -> None:
        tagged = make_mail(
            f"AW: Bühnenplan {self.tag.lower().replace('#', '# ')}",
            attachments=[("buehne.pdf", "application/pdf", PDF), ("setup.exe", "application/octet-stream", b"MZ")],
            message_id="<m1@stadtwerke.example>",
        )
        unknown = make_mail("Frage zu [RL#2099-0999]", message_id="<m2@stadtwerke.example>")
        foreign = make_mail("Newsletter März", message_id="<m3@werbung.example>")
        with mailbox(tagged, unknown, foreign) as box:
            fetched = self.admin.post(f"{API}/mail/fetch")
            self.assertEqual(fetched.status_code, 200, fetched.data)
            result = fetched.json()
            self.assertEqual((result["ok"], result["looked_at"], len(result["assigned"])), (True, 3, 1))
            # Assigned mails are moved away; the others stay where they are (EML-006, EML-013, EML-014).
            self.assertEqual(len(box.done), 1)
            self.assertEqual(len(box.inbox), 2)

            # Fetching again stores nothing twice (EML-007).
            again = self.admin.post(f"{API}/mail/fetch").json()
            self.assertEqual(again["assigned"], [])

        manager = self.client_of(self.manager)
        mails = manager.get(f"{API}/projects/{self.project.pk}/mails").json()
        self.assertEqual(len(mails), 1)
        mail = mails[0]
        self.assertEqual(mail["assigned_by"], "tag")
        self.assertEqual([item["filename"] for item in mail["attachments"]], ["buehne.pdf"])
        self.assertIn("setup.exe", mail["attachments_left_out"])
        # The project manager is told (EML-023).
        self.assertTrue(Notification.objects.filter(user=self.manager, kind="new_mail").exists())

        detail = manager.get(f"{API}/projects/{self.project.pk}/mails/{mail['id']}").json()
        self.assertIn("Bühnenplan", detail["text"])
        attachment = mail["attachments"][0]
        content = manager.get(f"{API}/projects/{self.project.pk}/mails/{mail['id']}/attachments/{attachment['id']}")
        self.assertEqual(b"".join(content.streaming_content), PDF)

        # The mail with the unknown tag is listed for assigning by hand.
        listed = self.admin.get(f"{API}/mail/unknown").json()
        self.assertEqual([row["tag"] for row in listed], ["2099-0999"])

    def test_assign_an_unknown_tag_by_hand(self) -> None:
        unknown = make_mail("Frage zu [RL#2099-0999]", message_id="<m2@stadtwerke.example>")
        with mailbox(unknown) as box:
            self.admin.post(f"{API}/mail/fetch")
            entry = UnknownTagMail.objects.get()
            response = self.admin.post(
                f"{API}/mail/unknown/{entry.pk}/assign", {"project_number": self.project.number}, format="json"
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(box.inbox, {})
        mail = ProjectMail.objects.get(pk=response.json()["mail"])
        self.assertEqual((mail.project, mail.assigned_by), (self.project, "manual"))
        self.assertEqual(self.admin.get(f"{API}/mail/unknown").json(), [])

    def test_dismiss_an_unknown_tag(self) -> None:
        with mailbox(make_mail("Frage zu [RL#2099-0999]")):
            self.admin.post(f"{API}/mail/fetch")
        entry = UnknownTagMail.objects.get()
        self.assertEqual(self.admin.post(f"{API}/mail/unknown/{entry.pk}/dismiss").status_code, 204)
        self.assertEqual(self.admin.get(f"{API}/mail/unknown").json(), [])

    def test_a_mail_that_is_gone_cannot_be_assigned(self) -> None:
        with mailbox(make_mail("Frage zu [RL#2099-0999]", message_id="<gone@x.example>")) as box:
            self.admin.post(f"{API}/mail/fetch")
            box.inbox.clear()
            entry = UnknownTagMail.objects.get()
            response = self.admin.post(
                f"{API}/mail/unknown/{entry.pk}/assign", {"project": self.project.pk}, format="json"
            )
        self.assert_error(response, 400, "validation_error")

    def test_answers_without_tag_follow_the_conversation(self) -> None:
        """EML-012: an answer whose tag was removed still finds its project."""
        with mailbox(make_mail(f"Anfrage {self.tag}", message_id="<first@kunde.example>")):
            self.admin.post(f"{API}/mail/fetch")
        with mailbox(
            make_mail("AW: Anfrage", message_id="<second@kunde.example>", in_reply_to="<first@kunde.example>")
        ):
            self.admin.post(f"{API}/mail/fetch")
        assigned = ProjectMail.objects.order_by("date", "id").values_list("assigned_by", flat=True)
        self.assertEqual(list(assigned), ["tag", "reference"])

    def test_a_failing_mailbox_is_reported(self) -> None:
        """EML-032: the error is shown and the operators are told once."""
        with mailbox() as box, self.assertLogs("rentalars.mail.fetching", "WARNING"):
            box.fail = "Login refused"
            result = self.admin.post(f"{API}/mail/fetch").json()
            self.assertFalse(result["ok"])
            self.admin.post(f"{API}/mail/fetch")
        self.assertIn("Login refused", Mailbox.objects.get().last_error)
        self.assertEqual(Notification.objects.filter(kind="mail_problem", user=self.admin_user).count(), 1)


class CorrespondenceApiTests(ApiTestCase):
    """EML-015, EML-021, EML-024, EML-025, EML-029 through the API."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.project = make_project()
        self.other = make_project("Weinfest")
        with mailbox(
            make_mail(
                f"Rider [RL#{self.project.number}]",
                attachments=[("rider.pdf", "application/pdf", PDF)],
                message_id="<rider@band.example>",
            )
        ):
            self.admin.post(f"{API}/mail/fetch")
        self.mail = ProjectMail.objects.get()
        self.base = f"{API}/projects/{self.project.pk}/mails"

    def test_send_an_answer_with_the_tag_and_a_document(self) -> None:
        with capture_smtp() as sent:
            response = self.admin.post(
                self.base,
                {
                    "to": "Band <band@band.example>",
                    "subject": "AW: Rider",
                    "body": "Danke, passt.",
                    "answer_to": self.mail.pk,
                    "documents": ["prices"],
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        (message,) = sent
        self.assertIn(f"[RL#{self.project.number}]", message["Subject"])
        self.assertEqual(message["In-Reply-To"], "<rider@band.example>")
        self.assertEqual(
            [part.get_filename() for part in message.iter_attachments()], [f"Preisuebersicht-{self.project.number}.pdf"]
        )
        stored = ProjectMail.objects.get(pk=response.json()["id"])
        self.assertEqual((stored.direction, stored.sent_by), ("out", self.admin_user))

    def test_sending_with_an_upload(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        with capture_smtp() as sent:
            response = self.admin.post(
                self.base,
                {
                    "to": "band@band.example",
                    "subject": "Plan",
                    "body": "Anbei.",
                    "uploads": SimpleUploadedFile("plan.pdf", PDF, content_type="application/pdf"),
                },
                format="multipart",
            )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([part.get_filename() for part in sent[0].iter_attachments()], ["plan.pdf"])

    def test_an_invalid_address_is_refused(self) -> None:
        with capture_smtp() as sent:
            response = self.admin.post(self.base, {"to": "nobody", "subject": "x", "body": "y"}, format="json")
        self.assert_error(response, 400, "validation_error", "to")
        self.assertEqual(sent, [])

    def test_take_an_attachment_into_the_files(self) -> None:
        attachment = self.mail.attachments.get()
        response = self.admin.post(
            f"{self.base}/{self.mail.pk}/attachments/{attachment.pk}/to-files",
            {"document_type": DocumentType.objects.get(name="Rider").pk, "title": "Rider der Band"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        files = self.admin.get(f"{API}/projects/{self.project.pk}/files").json()
        self.assertEqual([(row["title"], row["from_mail"]) for row in files], [("Rider der Band", self.mail.pk)])

    def test_move_to_another_project_and_delete(self) -> None:
        response = self.admin.post(
            f"{self.base}/{self.mail.pk}/assign", {"project_number": self.other.number}, format="json"
        )
        self.assertEqual(response.json()["project"], self.other.pk)
        self.assertEqual(self.admin.get(self.base).json(), [])
        other_base = f"{API}/projects/{self.other.pk}/mails"
        self.assertEqual(self.admin.delete(f"{other_base}/{self.mail.pk}").status_code, 204)
        self.assertFalse(ProjectMail.objects.exists())

    def test_correspondence_needs_its_own_right(self) -> None:
        """EML-029: project rights alone do not show the mails."""
        role = Role.objects.create(
            name="Projekte ohne Post", module_levels={Module.PROJECTS: Level.WRITE}, special_rights=[]
        )
        client = self.client_of(make_user("olaf", roles=(role.name,)))
        self.assert_error(client.get(self.base), 403, "permission_denied")
        role.special_rights = [SpecialRight.CORRESPONDENCE_READ]
        role.save()
        # EML-055: the mail has the lock (as every mail that comes in) – it needs the price right as well.
        self.assertEqual(client.get(self.base).json(), [])
        role.special_rights = [SpecialRight.CORRESPONDENCE_READ, SpecialRight.PRICES]
        role.save()
        self.assertEqual(len(client.get(self.base).json()), 1)
        with capture_smtp():
            response = client.post(self.base, {"to": "a@b.example", "subject": "x", "body": "y"}, format="json")
        self.assert_error(response, 403, "permission_denied")

    def test_mails_of_projects_one_may_not_see_are_not_found(self) -> None:
        """AUT-016, AUT-023: a project one may not see is "not found"; the deployment view shows no mails."""
        ben = make_user("ben", roles=("Crew",))
        client = self.client_of(ben)
        self.assert_error(client.get(self.base), 404, "not_found")
        ProjectMembership.objects.create(project=self.project, user=ben, level="deployment")
        self.assert_error(client.get(self.base), 403, "permission_denied")

    def test_the_html_part_is_cleaned(self) -> None:
        """EML-027: no scripts, no external pictures."""
        with mailbox(
            make_mail(
                f"Bild [RL#{self.project.number}]",
                html='<p>Hallo<script>alert(1)</script><img src="https://tracker.example/p.gif"></p>',
            )
        ):
            self.admin.post(f"{API}/mail/fetch")
        mail = ProjectMail.objects.get(subject__startswith="Bild")
        html = self.admin.get(f"{self.base}/{mail.pk}").json()["html"]
        self.assertNotIn("script", html)
        self.assertNotRegex(html, r"\ssrc=\"https?://")  # the picture is not loaded
        self.assertIn("Hallo", html)


class MailboxPasswordTests(ApiTestCase):
    """The stored password stays readable for the fetch, but never leaves the server."""

    def test_password_is_not_in_any_answer(self) -> None:
        configure_mailbox()
        self.assertNotIn(PASSWORD, str(self.admin.get(f"{API}/mail/settings").content))
