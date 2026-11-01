# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the mail wishes (EML-034 to EML-039).

Signature, SMTP with the IMAP access data, sending with BCC and without
signature, the recipients of an answer to all, address suggestions and the
mail log – each with its rights.
"""

from __future__ import annotations

import datetime

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level
from rentalars.core.models import CompanyProfile
from rentalars.customers.models import Contact
from rentalars.mail.models import Direction, LogKind, LogResult, Mailbox, MailLogEntry, MailSettings, ProjectMail
from tests.api.base import API, ApiTestCase
from tests.helpers import NOW, make_customer, make_person, make_project, make_user
from tests.mailbox import PASSWORD, capture_smtp, configure_mailbox, mailbox, make_mail


class MailApiTestCase(ApiTestCase):
    """A company, a mailbox, and an administrator with a full name."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.name = "Firma Muster"
        profile.save()
        make_person("Max Mustermann", user=self.admin_user, position="Leitung Licht")
        configure_mailbox()


class SignatureApiTests(MailApiTestCase):
    """EML-034: the signature is read by who writes mails and changed by administrators."""

    def test_change_and_read(self) -> None:
        response = self.admin.patch(
            f"{API}/mail/signature",
            {"html": '<p onclick="x()">Gruß<br>{vorname} {nachname}, {position}<script>x()</script></p>'},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["html"], "<p>Gruß<br>{vorname} {nachname}, {position}</p>")
        self.assertEqual(data["preview_html"], "<p>Gruß<br>Max Mustermann, Leitung Licht</p>")
        self.assertEqual(data["preview_text"], "Gruß\nMax Mustermann, Leitung Licht")
        self.assertIn({"token": "{telefon}", "label": "Telefon"}, data["placeholders"])

        manager = self.client_for("paula", "Projektleitung")
        read = manager.get(f"{API}/mail/signature").json()
        self.assertEqual(read["html"], data["html"])
        self.assertIn("paula", read["preview_html"])
        self.assert_error(
            manager.patch(f"{API}/mail/signature", {"html": "x"}, format="json"), 403, "permission_denied"
        )
        self.assert_error(self.client_for("ben", "Crew").get(f"{API}/mail/signature"), 403, "permission_denied")

    def test_wrong_input(self) -> None:
        self.assert_error(
            self.admin.patch(f"{API}/mail/signature", {"html": ["x"]}, format="json"), 400, "validation_error", "html"
        )
        self.assert_error(
            self.admin.patch(f"{API}/mail/signature", {"html": "x" * 20001}, format="json"),
            400,
            "validation_error",
            "html",
        )
        self.assertEqual(self.admin.patch(f"{API}/mail/signature", {"html": ""}, format="json").json()["html"], "")


class SmtpLoginApiTests(MailApiTestCase):
    """EML-035: the option "same access data as IMAP" through the API."""

    def test_switch_between_same_and_own_access_data(self) -> None:
        response = self.admin.patch(
            f"{API}/mail/settings",
            {"smtp_same_login": False, "smtp_user": "versand@verleih.example", "smtp_password": "versand-geheim"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["smtp_same_login"], response.json()["has_smtp_password"]), (False, True))
        self.assertEqual(Mailbox.objects.get().smtp_login, "versand@verleih.example")

        data = self.admin.patch(f"{API}/mail/settings", {"smtp_same_login": True}, format="json").json()
        self.assertEqual((data["smtp_user"], data["has_smtp_password"]), ("", False))
        self.assertEqual(Mailbox.objects.get().smtp_password, PASSWORD)

    def test_an_own_user_needs_a_password(self) -> None:
        response = self.admin.patch(
            f"{API}/mail/settings", {"smtp_same_login": False, "smtp_user": "versand@verleih.example"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "smtp_password")


class SendingApiTests(MailApiTestCase):
    """EML-034, EML-037, EML-038: BCC, the signature as a choice, the writer as sender, answer all."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        settings = MailSettings.load()
        settings.signature_html = "<p>Gruß {vorname}</p>"
        settings.save()

    def test_send_with_blind_copy(self) -> None:
        with capture_smtp() as sent:
            response = self.admin.post(
                f"{API}/projects/{self.project.pk}/mails",
                {"to": "kunde@kunde.example", "bcc": "archiv@verleih.example", "subject": "Angebot", "body": "Hallo"},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["bcc"], "archiv@verleih.example")
        self.assertEqual(data["sender_name"], "Max Mustermann | Firma Muster")
        self.assertIn("Gruß Max", data["html"])
        self.assertEqual(sent[0].get_content_type(), "multipart/alternative")

    def test_send_without_signature(self) -> None:
        with capture_smtp() as sent:
            response = self.admin.post(
                f"{API}/projects/{self.project.pk}/mails",
                {"to": "kunde@kunde.example", "subject": "Kurz", "body": "Ok", "signature": False},
                format="json",
            )
        self.assertEqual(response.json()["text"], "Ok")
        self.assertEqual(sent[0].get_content_type(), "text/plain")

    def test_a_wrong_blind_copy_address(self) -> None:
        with capture_smtp():
            response = self.admin.post(
                f"{API}/projects/{self.project.pk}/mails",
                {"to": "kunde@kunde.example", "bcc": "kaputt", "subject": "x", "body": "y"},
                format="json",
            )
        self.assert_error(response, 400, "validation_error", "bcc")

    def test_who_an_answer_goes_to(self) -> None:
        with mailbox(
            make_mail(
                f"Frage [RL#{self.project.number}]",
                sender="Band <band@band.example>",
                to="projekte@verleih.example, technik@band.example",
                headers={"Cc": "manager@band.example"},
            )
        ):
            self.admin.post(f"{API}/mail/fetch")
        mail = ProjectMail.objects.get()
        data = self.admin.get(f"{API}/projects/{self.project.pk}/mails/{mail.pk}").json()
        self.assertEqual(data["reply"], {"to": "Band <band@band.example>", "cc": ""})
        self.assertEqual(
            data["reply_all"], {"to": "Band <band@band.example>, technik@band.example", "cc": "manager@band.example"}
        )


class AddressSuggestionApiTests(MailApiTestCase):
    """EML-037: suggestions for the recipient fields, within the rights."""

    def test_suggestions(self) -> None:
        customer = make_customer("Stadtwerke")
        Contact.objects.create(customer=customer, name="Bernd Becker", email="b.becker@stadtwerke.example")
        make_person("Anna Becker", email="anna@verleih.example")
        found = self.admin.get(f"{API}/mail/address-suggestions", {"q": "Becker"}).json()
        self.assertEqual(
            [(item["name"], item["address"]) for item in found],
            [("Bernd Becker", "b.becker@stadtwerke.example"), ("Anna Becker", "anna@verleih.example")],
        )
        self.assertEqual(self.admin.get(f"{API}/mail/address-suggestions", {"q": "Be"}).json(), [])
        staff_only = Role.objects.create(
            name="Personal und Mail",
            module_levels={"personnel": int(Level.READ), "projects": int(Level.READ)},
            special_rights=["correspondence_read", "correspondence_write"],
        )
        user = make_user("pia")
        user.roles.set([staff_only])
        found = self.client_of(user).get(f"{API}/mail/address-suggestions", {"q": "Becker"}).json()
        self.assertEqual([item["address"] for item in found], ["anna@verleih.example"])
        self.assert_error(
            self.client_for("luka", "Lager").get(f"{API}/mail/address-suggestions", {"q": "Becker"}),
            403,
            "permission_denied",
        )


class MailLogApiTests(MailApiTestCase):
    """EML-039: the mail log, read-only, for who may read the administration."""

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
                project=self.project if subject == "Angebot" else None,
                detail="Anmeldung abgelehnt" if result == LogResult.FAILED else "",
            )

    def subjects(self, **filters: str) -> list[str]:
        response = self.admin.get(f"{API}/mail/log", filters)
        self.assertEqual(response.status_code, 200, response.content)
        return [entry["subject"] for entry in response.json()["results"]]

    def test_the_log_and_its_filters(self) -> None:
        data = self.admin.get(f"{API}/mail/log").json()
        self.assertEqual(data["count"], 3)
        failed = data["results"][2]
        self.assertEqual(
            (failed["result"], failed["detail"], failed["project_number"]),
            ("failed", "Anmeldung abgelehnt", self.project.number),
        )
        self.assertEqual(self.subjects(direction="in"), ["Newsletter"])
        self.assertEqual(self.subjects(kind="system"), ["Einladung"])
        self.assertEqual(self.subjects(result="failed", q="Angebot"), ["Angebot"])
        self.assertEqual(self.subjects(since="2027-02-27"), ["Einladung", "Newsletter"])
        self.assertEqual(self.subjects(since="2027-02-27T12:00:00+00:00"), ["Einladung"])
        self.assertEqual(self.subjects(until="2027-02-20"), ["Angebot"])
        self.assert_error(self.admin.get(f"{API}/mail/log", {"since": "gestern"}), 400, "validation_error")

    def test_only_for_the_administration(self) -> None:
        self.assert_error(self.client_for("lea", "Nur-Lesen").get(f"{API}/mail/log"), 403, "permission_denied")
        reader = Role.objects.create(name="Verwaltung lesen", module_levels={"administration": int(Level.READ)})
        user = make_user("vera")
        user.roles.set([reader])
        self.assertEqual(self.client_of(user).get(f"{API}/mail/log").status_code, 200)
        self.assertEqual(self.client_of(user).post(f"{API}/mail/log").status_code, 403)
