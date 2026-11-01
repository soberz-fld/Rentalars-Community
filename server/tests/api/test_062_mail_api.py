# SPDX-License-Identifier: GPL-3.0-or-later
"""API for the mail module (EML-041, EML-042).

``/mail/mailboxes`` – the mailboxes with their roles, every operation; the
fetch over several mailboxes; inquiries in ``/mail/unknown``; the mailbox in
the mail log; ``/mail/settings`` as it stays for older clients.
"""

from __future__ import annotations

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import Mailbox, MailSettings, ProjectMail
from tests.api.base import API, ApiTestCase
from tests.helpers import make_project
from tests.mailbox import PASSWORD, FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail
from tests.unit.test_051_mail import RecordingSMTP, recording_smtp

MAILBOXES = f"{API}/mail/mailboxes"

NEW_MAILBOX = {
    "name": "Info",
    "address": "info@verleih.example",
    "for_correspondence": True,
    "process_untagged": True,
    "after_assignment": "keep",
    "imap_host": "imap.verleih.example",
    "imap_user": "info@verleih.example",
    "imap_password": "info-geheim",
    "smtp_host": "smtp.verleih.example",
}


class MailboxResourceTests(ApiTestCase):
    """EML-041: list, create, read, change, delete, check – passwords are written, never read."""

    def setUp(self) -> None:
        super().setUp()
        self.projects = configure_mailbox()

    def test_list_and_read(self) -> None:
        listed = self.admin.get(MAILBOXES)
        self.assertEqual(listed.status_code, 200, listed.content)
        (row,) = listed.json()["results"]
        self.assertEqual(
            (row["name"], row["for_correspondence"], row["is_outgoing"], row["for_system"], row["has_imap_password"]),
            ("Projekte", True, True, False, True),
        )
        self.assertNotIn("imap_password", row)
        self.assertNotIn(PASSWORD, listed.content.decode())
        detail = self.admin.get(f"{MAILBOXES}/{self.projects.pk}").json()
        self.assertEqual((detail["after_assignment"], detail["done_folder"]), ("move", "Rentalars"))

    def test_create_change_and_replace(self) -> None:
        created = self.admin.post(MAILBOXES, NEW_MAILBOX, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        data = created.json()
        self.assertNotIn("info-geheim", created.content.decode())
        info = Mailbox.objects.get(pk=data["id"])
        self.assertEqual(
            (info.imap_password, info.process_untagged, info.after_assignment), ("info-geheim", True, "keep")
        )

        # Taking the outgoing role takes it from the other mailbox.
        changed = self.admin.patch(f"{MAILBOXES}/{info.pk}", {"is_outgoing": True}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.projects.refresh_from_db()
        self.assertEqual((changed.json()["is_outgoing"], self.projects.is_outgoing), (True, False))
        self.assertEqual(Mailbox.objects.get(pk=info.pk).imap_password, "info-geheim")  # kept without a new one

        replaced = self.admin.put(
            f"{MAILBOXES}/{info.pk}",
            {**NEW_MAILBOX, "name": "Anfragen", "is_outgoing": True, "imap_password": ""},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        info.refresh_from_db()
        self.assertEqual((info.name, info.imap_password), ("Anfragen", "info-geheim"))

    def test_the_rules_of_the_roles_are_kept(self) -> None:
        add_mailbox("Info", "info@verleih.example")
        response = self.admin.patch(f"{MAILBOXES}/{self.projects.pk}", {"is_outgoing": False}, format="json")
        self.assert_error(response, 400, "validation_error", "is_outgoing")
        response = self.admin.post(MAILBOXES, {**NEW_MAILBOX, "imap_password": ""}, format="json")
        self.assert_error(response, 400, "validation_error", "imap_password")
        response = self.admin.post(
            MAILBOXES, {"name": "System", "for_system": True, "is_outgoing": True}, format="json"
        )
        self.assert_error(response, 400, "validation_error")

    def test_delete_or_switch_off(self) -> None:
        unused = add_mailbox("Alt", "alt@verleih.example")
        self.assertEqual(self.admin.delete(f"{MAILBOXES}/{unused.pk}").status_code, 204)
        self.assertFalse(Mailbox.objects.filter(pk=unused.pk).exists())

        info = add_mailbox("Info", "info@verleih.example")
        project = make_project()
        with mailboxes(
            {
                "projekte@verleih.example": FakeMailbox(),
                "info@verleih.example": FakeMailbox(make_mail(f"Plan [RL#{project.number}]")),
            }
        ):
            fetch_mail(force=True)
        # EML-046: deleted as well; the mail keeps the name.
        response = self.admin.delete(f"{MAILBOXES}/{info.pk}")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Mailbox.objects.filter(pk=info.pk).exists())
        mail = ProjectMail.objects.get()
        self.assertEqual((mail.mailbox_id, mail.mailbox_name), (None, "Info"))

    def test_check_the_connection(self) -> None:
        with mailboxes({"projekte@verleih.example": FakeMailbox()}), recording_smtp():
            response = self.admin.post(f"{MAILBOXES}/{self.projects.pk}/check")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([(item["part"], item["ok"]) for item in response.json()], [("IMAP", True), ("SMTP", True)])
        self.assertEqual(len(RecordingSMTP.sessions), 1)

    def test_rights(self) -> None:
        reader = self.client_for("lea", "Nur-Lesen")
        self.assert_error(reader.get(MAILBOXES), 403, "permission_denied")
        self.assert_error(reader.post(f"{MAILBOXES}/{self.projects.pk}/check"), 403, "permission_denied")
        manager = self.client_for("paula", "Projektleitung")  # writes the module E-mail, may not delete
        self.assertEqual(manager.get(MAILBOXES).status_code, 200)
        self.assert_error(manager.delete(f"{MAILBOXES}/{self.projects.pk}"), 403, "permission_denied")


class FetchAndInquiriesApiTests(ApiTestCase):
    """EML-041, EML-042: the fetch tells per mailbox; inquiries and the log name their mailbox."""

    def test_fetch_inquiries_and_log(self) -> None:
        configure_mailbox()
        info = add_mailbox("Info", "info@verleih.example", process_untagged=True)
        project = make_project()
        boxes = {
            "projekte@verleih.example": FakeMailbox(make_mail(f"Plan [RL#{project.number}]")),
            "info@verleih.example": FakeMailbox(make_mail("Anfrage Hochzeit")),
        }
        with mailboxes(boxes):
            result = self.admin.post(f"{API}/mail/fetch").json()
        self.assertEqual((result["ok"], len(result["assigned"]), len(result["inquiries"])), (True, 1, 1))
        self.assertEqual(
            [(part["name"], part["looked_at"], len(part["inquiries"])) for part in result["mailboxes"]],
            [("Info", 1, 1), ("Projekte", 1, 0)],
        )
        (waiting,) = self.admin.get(f"{API}/mail/unknown").json()
        self.assertEqual(
            (waiting["tag"], waiting["is_inquiry"], waiting["mailbox"], waiting["mailbox_name"]),
            ("", True, info.pk, "Info"),
        )
        log = self.admin.get(f"{API}/mail/log", {"q": "Info"}).json()
        self.assertEqual([(row["result"], row["mailbox_name"]) for row in log["results"]], [("inquiry", "Info")])


class LegacySettingsApiTests(ApiTestCase):
    """``/mail/settings``: the rules for all mailboxes, and the mailbox fields of older clients."""

    def test_the_rules_and_the_mailbox_that_sends(self) -> None:
        configure_mailbox()
        add_mailbox("Info", "info@verleih.example")
        response = self.admin.patch(
            f"{API}/mail/settings",
            {"retention_days": 30, "delete_after_import": True, "done_folder": "Archiv"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(
            (data["retention_days"], data["delete_after_import"], data["address"], data["is_enabled"]),
            (30, True, "projekte@verleih.example", True),
        )
        self.assertEqual(MailSettings.load().retention_days, 30)
        projects = Mailbox.objects.get(name="Projekte")
        self.assertEqual((projects.after_assignment, projects.done_folder), ("delete", "Archiv"))
        self.assertEqual(Mailbox.objects.get(name="Info").after_assignment, "move")

    def test_without_any_mailbox(self) -> None:
        data = self.admin.get(f"{API}/mail/settings").json()
        self.assertEqual((data["is_enabled"], data["address"], data["interval_minutes"]), (False, "", 2))
