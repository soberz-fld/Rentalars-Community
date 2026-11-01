# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "mail".

* EML-047: further addresses (aliases) of a mailbox – which address a mail
  went to, the rule per address for mails without tag (leave, inquiry,
  service case at once), the role "only for service cases" as sender, the
  automations of the trigger "mail without project tag".
* EML-048: no "sent" without a mail server.
* EML-006: assigned mails "only marked as read".
* PRJ-107: taking several waiting mails off the list; the start values of a
  project made from an inquiry.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.test import SimpleTestCase, override_settings

from rentalars.automations.models import Action, AutomationRun, Recipient, RunStatus, Trigger
from rentalars.core import selfcheck
from rentalars.customers.models import Contact
from rentalars.mail.aliases import alias_for, recipient_addresses, save_address, sender_for, untagged_rule
from rentalars.mail.fetching import dismiss_waiting, fetch_mail
from rentalars.mail.imap import ImapMailbox
from rentalars.mail.inquiries import project_initial
from rentalars.mail.mailboxes import has_mail_server, own_addresses
from rentalars.mail.models import (
    AfterAssignment,
    AssignedBy,
    LogResult,
    Mailbox,
    MailboxAddress,
    MailLogEntry,
    ProjectMail,
    UnknownTagMail,
    Untagged,
)
from rentalars.mail.parsing import parse_headers
from rentalars.mail.sending import send_project_mail
from rentalars.notifications.models import Notification
from rentalars.notifications.services import notify
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, Project
from tests.helpers import RentalarsTestCase, make_customer, make_project, make_user
from tests.mailbox import FakeMailbox, add_mailbox, capture_smtp, configure_mailbox, mailboxes, make_mail
from tests.unit.test_080_communication import reply_rule

LOGGING_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"
LOCMEM_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
#: What the configuration does without ``[email] host``: the mails only go into the log of the server.
LOG_ONLY_BACKEND = "django.core.mail.backends.dummy.EmailBackend"


def alias(mailbox: Mailbox, address: str, **fields: Any) -> MailboxAddress:
    """A further address of a mailbox, stored by the rules of its role."""
    entry = MailboxAddress(mailbox=mailbox, address=address, **fields)
    save_address(entry)
    return entry


def headers(**fields: str) -> Any:
    """The headers of a mail as the fetch reads them, e.g. ``headers(To="a@x", **{"Delivered-To": "b@x"})``."""
    lines = [f"{name}: {value}" for name, value in fields.items()]
    return parse_headers(("\r\n".join(["Subject: Frage", "From: kunde@example.org", *lines]) + "\r\n\r\n").encode())


# --- EML-047: which address a mail went to -------------------------------------------------------------


class AliasForTests(RentalarsTestCase):
    """EML-047: Delivered-To, X-Original-To, To, Cc – in this order; the mailbox's own address last."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=False)
        self.support = alias(self.box, "support@verleih.example", untagged=Untagged.SERVICE_CASE)
        self.projekt = alias(self.box, "projekt@verleih.example", untagged=Untagged.INQUIRY)

    def test_the_order_of_the_headers(self) -> None:
        found = headers(
            **{"Delivered-To": "projekte@verleih.example", "X-Original-To": "support@verleih.example"},
            To="projekt@verleih.example",
        )
        self.assertEqual(
            recipient_addresses(found),
            ["projekte@verleih.example", "support@verleih.example", "projekt@verleih.example"],
        )
        # The mailbox's own address in Delivered-To does not hide the alias the mail was written to.
        self.assertEqual(alias_for(self.box, found), self.support)
        self.assertEqual(alias_for(self.box, headers(To="Projekt <PROJEKT@verleih.example>")), self.projekt)
        self.assertEqual(alias_for(self.box, headers(To="x@y.example", Cc="support@verleih.example")), self.support)

    def test_no_listed_address_follows_the_mailbox(self) -> None:
        mail = headers(To="projekte@verleih.example")
        self.assertIsNone(alias_for(self.box, mail))
        self.assertEqual(untagged_rule(self.box, mail), (Untagged.IGNORE, None))
        self.box.process_untagged = True
        self.assertEqual(untagged_rule(self.box, mail), (Untagged.INQUIRY, None))

    def test_the_own_address_listed_itself(self) -> None:
        own = alias(self.box, "projekte@verleih.example", untagged=Untagged.SERVICE_CASE)
        self.assertEqual(untagged_rule(self.box, headers(To="projekte@verleih.example")), (Untagged.SERVICE_CASE, own))
        # Also for a mail that names no address of the mailbox at all (blind copy).
        self.assertEqual(alias_for(self.box, headers(To="andere@example.org")), own)

    def test_the_addresses_are_own_addresses(self) -> None:
        self.assertTrue({"support@verleih.example", "projekt@verleih.example"} <= own_addresses())

    def test_an_address_once_per_mailbox_in_lower_case(self) -> None:
        self.assertEqual(alias(self.box, "Info@Verleih.Example").address, "info@verleih.example")
        with self.assertRaises(ValidationError):
            alias(self.box, "SUPPORT@verleih.example")

    def test_the_role_for_service_cases_moves(self) -> None:
        self.support.for_service_cases = True
        self.assertEqual(save_address(self.support), [])
        self.projekt.for_service_cases = True
        self.assertEqual(
            save_address(self.projekt), ["support@verleih.example ist nicht mehr die Adresse für Servicefälle."]
        )
        self.support.refresh_from_db()
        self.assertFalse(self.support.for_service_cases)


# --- EML-047: fetching with aliases ---------------------------------------------------------------------


class FetchWithAliasesTests(RentalarsTestCase):
    """EML-047: per address – leave alone, inquiry, or a service case made at once with the mail in it."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=True)
        self.office = make_user("office")
        self.support = alias(
            self.box, "support@verleih.example", untagged=Untagged.SERVICE_CASE, case_manager=self.office
        )
        self.noreply = alias(self.box, "rechnung@verleih.example", untagged=Untagged.IGNORE)

    def fetch(self, *mails: bytes) -> FakeMailbox:
        box = FakeMailbox(*mails)
        with mailboxes({"projekte@verleih.example": box}), self.captureOnCommitCallbacks(execute=True):
            fetch_mail(force=True)
        return box

    def test_an_address_that_leaves_mails_alone(self) -> None:
        box = self.fetch(make_mail("Rechnung 4711", to="rechnung@verleih.example"))
        self.assertEqual(len(box.inbox), 1)
        self.assertFalse(UnknownTagMail.objects.exists())
        entry = MailLogEntry.objects.get()
        self.assertEqual((entry.result, entry.detail), (LogResult.LEFT_IN_INBOX, "rechnung@verleih.example"))

    def test_the_mailbox_itself_still_takes_inquiries(self) -> None:
        self.fetch(make_mail("Angebot Bühne", to="projekte@verleih.example"))
        waiting = UnknownTagMail.objects.get()
        self.assertEqual((waiting.subject, waiting.address), ("Angebot Bühne", "projekte@verleih.example"))

    def test_the_address_a_waiting_mail_went_to(self) -> None:
        """EML-047: noted with every waiting mail, for the column and the groups under Anfragen."""
        alias(self.box, "projekt@verleih.example", untagged=Untagged.INQUIRY)
        self.fetch(make_mail("Hochzeit", to="Projekt <projekt@verleih.example>"), make_mail("[RL#2099-0009] Alt"))
        self.assertEqual(
            dict(UnknownTagMail.objects.values_list("subject", "address")),
            {"Hochzeit": "projekt@verleih.example", "[RL#2099-0009] Alt": "projekte@verleih.example"},
        )

    def test_a_service_case_at_once(self) -> None:
        customer = make_customer("Stadthalle")
        contact = Contact.objects.create(customer=customer, name="Max Muster", email="max@stadthalle.example")
        box = self.fetch(
            make_mail(
                "AW: Beamer flackert",
                sender="Max Muster <max@stadthalle.example>",
                to="Support <support@verleih.example>",
                headers={"Delivered-To": "projekte@verleih.example"},
            )
        )
        case = Project.objects.get()
        self.assertTrue(case.is_service_case)
        self.assertEqual(
            (case.name, case.customer, case.contact, case.manager, case.case_status),
            ("Beamer flackert", customer, contact, self.office, CaseStatus.OPEN),
        )
        mail = ProjectMail.objects.get()
        self.assertEqual((mail.project, mail.assigned_by, mail.mailbox), (case, AssignedBy.NEW_CASE, self.box))
        self.assertEqual(len(box.done), 1)  # filed away as every assigned mail of the mailbox
        self.assertIsNotNone(UnknownTagMail.objects.get().resolved_at)
        entry = MailLogEntry.objects.get()
        self.assertEqual(
            (entry.result, entry.project, entry.detail_text), (LogResult.ASSIGNED, case, "als neuer Servicefall")
        )
        note = Notification.objects.get(user=self.office)
        self.assertEqual(
            note.title,
            f"Neuer Servicefall {case.number} aus einer Mail an support@verleih.example: AW: Beamer flackert",
        )
        # A reply with the tag of the case lands in it as usual.
        self.fetch(make_mail(f"AW: [RL#{case.number}] Beamer flackert", to="support@verleih.example"))
        self.assertEqual(ProjectMail.objects.filter(project=case).count(), 2)
        self.assertEqual(Project.objects.count(), 1)

    def test_a_tagged_mail_to_the_address_goes_to_its_project(self) -> None:
        project = make_project()
        self.fetch(make_mail(f"[RL#{project.number}] Bühnenplan", to="support@verleih.example"))
        self.assertEqual(ProjectMail.objects.get().project, project)
        self.assertFalse(Project.objects.filter(kind="service_case").exists())

    def test_a_case_that_cannot_be_made_leaves_an_inquiry(self) -> None:
        with (
            mock.patch.object(service_cases, "create_case", side_effect=ValidationError("kaputt")),
            self.assertLogs("rentalars.mail.fetching", "WARNING"),
        ):
            box = self.fetch(make_mail("Frage", to="support@verleih.example"))
        self.assertFalse(ProjectMail.objects.exists())
        self.assertEqual(len(box.inbox), 1)
        self.assertIsNone(UnknownTagMail.objects.get().resolved_at)
        self.assertEqual(MailLogEntry.objects.get().result, LogResult.INQUIRY)

    def test_the_automations_run_also_for_a_new_case(self) -> None:
        """ADM-013 still fires; the answer goes out from the address the mail was written to."""
        reply_rule()
        with capture_smtp() as sent:
            self.fetch(make_mail("Frage zum Pult", sender="kunde@example.org", to="support@verleih.example"))
            self.fetch(make_mail("Angebot", sender="kunde2@example.org", to="projekte@verleih.example"))
        runs = list(AutomationRun.objects.order_by("pk"))
        self.assertEqual([run.status for run in runs], [RunStatus.DONE, RunStatus.DONE])
        self.assertEqual(runs[0].project, Project.objects.get(kind="service_case"))
        self.assertIsNone(runs[1].project)
        self.assertEqual(
            [message["From"] for message in sent],
            ["Verleih Projekte <support@verleih.example>", "Verleih Projekte <projekte@verleih.example>"],
        )

    def test_a_notify_rule_names_the_new_case(self) -> None:
        from rentalars.automations.models import Automation

        rule = Automation(
            name="Support",
            trigger=Trigger.INQUIRY,
            action=Action.NOTIFY,
            recipient=Recipient.USER,
            user=self.office,
            subject="Neue Supportmail: {betreff}",
        )
        rule.normalise()
        rule.save()
        self.fetch(make_mail("Frage", to="support@verleih.example"))
        case = Project.objects.get()
        self.assertTrue(
            Notification.objects.filter(user=self.office, title="Neue Supportmail: Frage", project=case).exists()
        )


# --- EML-047: the sender of mails in service cases ---------------------------------------------------


class ServiceCaseSenderTests(RentalarsTestCase):
    """EML-047: mails written in a service case go out with the address for service cases."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox()
        self.user = make_user("berta")
        self.case = service_cases.create_case(name="Pult defekt")
        self.project = make_project()

    def test_without_the_role_everything_as_before(self) -> None:
        self.assertEqual(sender_for(self.case), (self.box, "projekte@verleih.example"))

    def test_with_the_role(self) -> None:
        alias(self.box, "support@verleih.example", for_service_cases=True)
        self.assertEqual(sender_for(self.case), (self.box, "support@verleih.example"))
        self.assertEqual(sender_for(self.project), (self.box, "projekte@verleih.example"))
        with capture_smtp() as sent:
            mail = send_project_mail(self.case, to="kunde@example.org", subject="Pult", body="Hallo", user=self.user)
            send_project_mail(self.project, to="kunde@example.org", subject="Plan", body="Hallo", user=self.user)
        self.assertIn("<support@verleih.example>", sent[0]["From"])
        self.assertTrue(sent[0]["Message-ID"].endswith("@verleih.example>"))
        self.assertIn("<projekte@verleih.example>", sent[1]["From"])
        self.assertEqual(mail.sender_address, "support@verleih.example")

    def test_through_the_mailbox_of_the_address_when_it_can_send(self) -> None:
        service = add_mailbox("Service", "service@verleih.example")
        alias(service, "hilfe@verleih.example", for_service_cases=True)
        self.assertEqual(sender_for(self.case), (service, "hilfe@verleih.example"))
        service.smtp_host = ""
        service.save()
        self.assertEqual(sender_for(self.case), (self.box, "hilfe@verleih.example"))


# --- EML-006: only mark as read ----------------------------------------------------------------------


class OnlyMarkAsReadTests(RentalarsTestCase):
    """EML-006: "only mark as read" leaves an assigned mail read in the inbox; the default stays "move"."""

    def test_the_default_stays(self) -> None:
        self.assertEqual(Mailbox().after_assignment, AfterAssignment.MOVE)

    def test_fetching(self) -> None:
        box = configure_mailbox(after_assignment=AfterAssignment.READ, done_folder="")
        project = make_project()
        fake = FakeMailbox(make_mail(f"[RL#{project.number}] Plan"))
        with mailboxes({box.address: fake}):
            fetch_mail(force=True)
            fetch_mail(force=True)
        self.assertEqual(ProjectMail.objects.count(), 1)
        self.assertEqual((len(fake.inbox), len(fake.read), fake.done), (1, 1, []))

    def test_imap_marks_as_read_only(self) -> None:
        settings = mock.Mock(after_assignment=AfterAssignment.READ, done_folder="Rentalars")
        connection = ImapMailbox(settings)
        connection.imap = mock.Mock()
        connection.imap.uid.return_value = ("OK", [b""])
        connection.capabilities = {"MOVE", "UIDPLUS"}
        connection.file_away(42)
        self.assertEqual(connection.imap.uid.call_args_list, [mock.call("STORE", "42", "+FLAGS", "(\\Seen)")])


# --- EML-048: no mail server ------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND, EMAIL_INNER_BACKEND=LOG_ONLY_BACKEND)
class NoMailServerTests(RentalarsTestCase):
    """EML-048: without a mail server a system mail is "not sent", not counted, and the self-check says so."""

    def test_not_sent_and_not_counted(self) -> None:
        self.assertFalse(has_mail_server())
        self.assertEqual(send_mail("Dein Zugang", "Hallo", None, ["berta@example.de"]), 0)
        entry = MailLogEntry.objects.get()
        self.assertEqual(
            (entry.result, entry.get_result_display()),
            (LogResult.NOT_SENT, "nicht versendet – kein Mailserver eingerichtet"),
        )

    def test_a_notification_is_not_marked_as_mailed(self) -> None:
        user = make_user("berta")
        with self.captureOnCommitCallbacks(execute=True):
            notify([user], "deployment_request", "Anfrage für Stadtfest")
        self.assertIsNone(Notification.objects.get().emailed_at)
        self.assertEqual(MailLogEntry.objects.get().result, LogResult.NOT_SENT)

    def test_the_self_check_names_the_missing_server(self) -> None:
        report = selfcheck.run_checks()
        texts = [finding.detail for finding in report.findings if finding.title == "Systemmails"]
        self.assertTrue(any(text.startswith("Kein Mailserver eingerichtet") for text in texts), texts)

    def test_a_system_mailbox_is_a_mail_server(self) -> None:
        box = configure_mailbox(for_system=True)
        self.assertTrue(has_mail_server())
        self.assertEqual(box.pk, Mailbox.objects.get(for_system=True).pk)

    @override_settings(EMAIL_INNER_BACKEND=LOCMEM_BACKEND)
    def test_with_a_server_as_before(self) -> None:
        self.assertTrue(has_mail_server())
        self.assertEqual(send_mail("Dein Zugang", "Hallo", None, ["berta@example.de"]), 1)
        self.assertEqual(len(django_mail.outbox), 1)
        self.assertEqual(MailLogEntry.objects.get().result, LogResult.SENT)


class MailServerOfTheConfigurationTests(SimpleTestCase):
    """EML-048: the backends that send nothing."""

    @override_settings(
        EMAIL_BACKEND=LOGGING_BACKEND, EMAIL_INNER_BACKEND="django.core.mail.backends.console.EmailBackend"
    )
    def test_the_console(self) -> None:
        with mock.patch("rentalars.mail.mailboxes.system_mailbox", return_value=None):
            self.assertFalse(has_mail_server())

    @override_settings(EMAIL_BACKEND=LOGGING_BACKEND, EMAIL_INNER_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_smtp(self) -> None:
        with mock.patch("rentalars.mail.mailboxes.system_mailbox", return_value=None):
            self.assertTrue(has_mail_server())


# --- PRJ-107: the list of inquiries ------------------------------------------------------------------


class InquiryListTests(RentalarsTestCase):
    """PRJ-107: several mails off the list at once; a project from an inquiry starts with what the mail says."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=True)
        with mailboxes({self.box.address: FakeMailbox(*(make_mail(f"Frage {number}") for number in range(3)))}):
            fetch_mail(force=True)

    def test_dismissing_several(self) -> None:
        ids = list(UnknownTagMail.objects.values_list("pk", flat=True))
        self.assertEqual(dismiss_waiting(ids[:2]), 2)
        self.assertEqual(dismiss_waiting(ids), 1)  # the two dealt with already stay as they were
        self.assertFalse(UnknownTagMail.objects.filter(resolved_at__isnull=True).exists())

    def test_the_start_values_of_a_project(self) -> None:
        customer = make_customer("Stadthalle")
        contact = Contact.objects.create(customer=customer, name="Max", email="kunde@stadtwerke.example")
        unknown = UnknownTagMail.objects.order_by("pk").first()
        unknown.subject = "AW: Angebot Stadtfest"
        self.assertEqual(
            project_initial(unknown), {"name": "Angebot Stadtfest", "customer": customer, "contact": contact}
        )
        contact.delete()
        self.assertEqual(project_initial(unknown), {"name": "Angebot Stadtfest"})
