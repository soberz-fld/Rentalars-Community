# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the mail module.

* EML-041: several mailboxes with the roles correspondence (one of them
  sends) and system; per mailbox the mails without tag and what becomes of
  assigned mails; fetching every mailbox; sending through the outgoing and
  the system mailbox; the data migration; the self-check.
* EML-042: mails without tag wait as inquiries.
* EML-043: the addresses behind "add crew" and "add customer".
"""

from __future__ import annotations

import io
import re
from typing import Any
from unittest import mock

from django.apps import apps as django_apps
from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, SpecialRight, rights_of
from rentalars.core import selfcheck
from rentalars.customers.models import Contact
from rentalars.mail.addresses import crew_recipients, customer_recipient
from rentalars.mail.fetching import assign_unknown, fetch_mail
from rentalars.mail.imap import MailboxError
from rentalars.mail.mailboxes import (
    check_connection,
    delete_mailbox,
    outgoing_mailbox,
    save_mailbox,
    system_mailbox,
)
from rentalars.mail.models import (
    AfterAssignment,
    Direction,
    LogKind,
    LogResult,
    Mailbox,
    MailLogEntry,
    ProjectMail,
    UnknownTagMail,
)
from rentalars.mail.sending import reply_recipients, send_project_mail
from rentalars.notifications.models import Notification
from rentalars.projects import services as project_services
from rentalars.projects.access import ProjectAccess
from rentalars.projects.models import RequestStatus
from tests.helpers import RentalarsTestCase, make_customer, make_person, make_project, make_user, plan
from tests.mailbox import (
    PASSWORD,
    FakeMailbox,
    add_mailbox,
    capture_smtp,
    configure_mailbox,
    mailboxes,
    make_mail,
)
from tests.unit.test_051_mail import RecordingSMTP, recording_smtp

LOGGING_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"
LOCMEM_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


def new_mailbox(name: str, address: str, **fields: Any) -> Mailbox:
    """An unsaved mailbox with IMAP and SMTP filled in, for :func:`save_mailbox`."""
    domain = address.split("@")[-1]
    mailbox = Mailbox(
        name=name, address=address, imap_host=f"imap.{domain}", imap_user=address, smtp_host=f"smtp.{domain}"
    )
    for field, value in fields.items():
        setattr(mailbox, field, value)
    return mailbox


# --- EML-041: the rules of the roles -------------------------------------------------------------------


class MailboxRuleTests(RentalarsTestCase):
    """EML-041: exactly one active correspondence mailbox sends; at most one sends the system mails."""

    def setUp(self) -> None:
        super().setUp()
        self.projects = configure_mailbox()

    def test_a_second_mailbox_of_the_correspondence(self) -> None:
        info = new_mailbox("Info", "info@verleih.example", for_correspondence=True)
        self.assertEqual(save_mailbox(info, imap_password="geheim"), [])
        self.assertEqual(outgoing_mailbox(), self.projects)
        self.assertEqual(info.imap_password, "geheim")
        self.assertNotIn("geheim", info.imap_password_encrypted)

    def test_taking_the_outgoing_role_takes_it_from_the_other(self) -> None:
        info = new_mailbox("Info", "info@verleih.example", for_correspondence=True, is_outgoing=True)
        notes = save_mailbox(info, imap_password="geheim")
        self.assertEqual(notes, ["Projekte ist nicht mehr Postausgang der Korrespondenz."])
        self.projects.refresh_from_db()
        self.assertFalse(self.projects.is_outgoing)
        self.assertEqual(outgoing_mailbox(), info)

    def test_one_mailbox_must_send_the_correspondence(self) -> None:
        add_mailbox("Info", "info@verleih.example")
        self.projects.is_outgoing = False
        with self.assertRaises(ValidationError) as caught:
            save_mailbox(self.projects)
        self.assertIn("is_outgoing", caught.exception.message_dict)
        self.projects.refresh_from_db()
        self.assertTrue(self.projects.is_outgoing)

    def test_only_a_correspondence_mailbox_sends_the_correspondence(self) -> None:
        system = new_mailbox("System", "system@verleih.example", is_outgoing=True, for_system=True)
        with self.assertRaises(ValidationError) as caught:
            save_mailbox(system, imap_password="x")
        self.assertIn("is_outgoing", caught.exception.message_dict)

    def test_at_most_one_system_mailbox_and_both_roles_in_one(self) -> None:
        self.projects.for_system = True
        save_mailbox(self.projects)
        self.assertEqual(system_mailbox(), self.projects)
        other = new_mailbox("System", "system@verleih.example", for_system=True)
        notes = save_mailbox(other, imap_password="x")
        self.assertEqual(notes, ["Projekte versendet keine Systemmails mehr."])
        self.assertEqual(system_mailbox(), other)
        self.assertEqual(Mailbox.objects.filter(for_system=True).count(), 1)

    def test_a_mailbox_that_sends_needs_server_and_address(self) -> None:
        system = Mailbox(name="System", for_system=True)
        with self.assertRaises(ValidationError) as caught:
            save_mailbox(system)
        self.assertEqual(set(caught.exception.message_dict), {"smtp_host", "address"})

    def test_a_correspondence_mailbox_needs_its_imap_access(self) -> None:
        info = new_mailbox("Info", "info@verleih.example", for_correspondence=True)
        with self.assertRaises(ValidationError) as caught:
            save_mailbox(info)
        self.assertIn("imap_password", caught.exception.message_dict)
        # Switched off, it may wait half filled in.
        info.is_active = False
        save_mailbox(info)
        self.assertFalse(Mailbox.objects.get(name="Info").is_active)

    def test_moving_needs_a_folder_other_than_the_inbox(self) -> None:
        self.projects.done_folder = "INBOX"
        with self.assertRaises(ValidationError) as caught:
            save_mailbox(self.projects)
        self.assertIn("done_folder", caught.exception.message_dict)
        self.projects.after_assignment = AfterAssignment.KEEP
        save_mailbox(self.projects)

    def test_a_mailbox_never_used_is_deleted(self) -> None:
        info = add_mailbox("Info", "info@verleih.example")
        self.assertEqual(delete_mailbox(info), [])
        self.assertFalse(Mailbox.objects.filter(name="Info").exists())

    def test_a_mailbox_with_mails_is_deleted_too(self) -> None:
        """EML-046: the mail keeps the name of its mailbox."""
        info = add_mailbox("Info", "info@verleih.example")
        project = make_project()
        with mailboxes(
            {
                "projekte@verleih.example": FakeMailbox(),
                "info@verleih.example": FakeMailbox(make_mail(f"Frage [RL#{project.number}]")),
            }
        ):
            fetch_mail(force=True)
        self.assertEqual(delete_mailbox(info), [])
        self.assertFalse(Mailbox.objects.filter(name="Info").exists())
        mail = ProjectMail.objects.get()
        self.assertEqual((mail.mailbox, mail.mailbox_name), (None, "Info"))

    def test_the_role_of_sending_goes_to_the_other_mailbox(self) -> None:
        """EML-046: the only other mailbox that can send takes over sending."""
        info = add_mailbox("Info", "info@verleih.example")
        notes = delete_mailbox(self.projects)
        self.assertEqual(notes, ["„Info“ versendet jetzt die Korrespondenz."])
        info.refresh_from_db()
        self.assertTrue(info.is_outgoing)

    def test_the_mailbox_that_sends_stays_while_no_other_can_send(self) -> None:
        add_mailbox("Info", "info@verleih.example", smtp_host="")
        pk = self.projects.pk
        with self.assertRaises(ValidationError):
            delete_mailbox(self.projects)
        self.assertTrue(Mailbox.objects.filter(pk=pk, is_active=True, is_outgoing=True).exists())


# --- EML-041: fetching every mailbox -------------------------------------------------------------------


class FetchSeveralMailboxesTests(RentalarsTestCase):
    """EML-041: every active correspondence mailbox is fetched; one broken mailbox stops no other."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("paula", roles=("Projektleitung",))
        self.project = make_project(manager=self.manager)
        self.projects = configure_mailbox()
        self.info = add_mailbox("Info", "info@verleih.example", process_untagged=True)

    def test_both_mailboxes_are_fetched_and_named_in_the_log(self) -> None:
        boxes = {
            "projekte@verleih.example": FakeMailbox(make_mail(f"Plan [RL#{self.project.number}]")),
            "info@verleih.example": FakeMailbox(
                make_mail(f"Rider [RL#{self.project.number}]", message_id="<rider@band.example>"),
                make_mail("Anfrage Hochzeit", sender="Brautpaar <paar@example.de>", message_id="<h@example.de>"),
            ),
        }
        with mailboxes(boxes):
            result = fetch_mail(force=True)
        self.assertTrue(result.ok, result.error)
        self.assertEqual((result.looked_at, len(result.imported), len(result.inquiries)), (3, 2, 1))
        # In the order of their names.
        self.assertEqual([part.mailbox for part in result.mailboxes], [self.info, self.projects])
        self.assertEqual(
            {mail.subject: mail.mailbox for mail in ProjectMail.objects.all()},
            {f"Plan [RL#{self.project.number}]": self.projects, f"Rider [RL#{self.project.number}]": self.info},
        )
        inquiry = UnknownTagMail.objects.get()
        self.assertEqual((inquiry.tag, inquiry.is_inquiry, inquiry.mailbox), ("", True, self.info))
        # The inquiry stays in the inbox; assigned mails were moved.
        self.assertEqual(len(boxes["info@verleih.example"].inbox), 1)
        self.assertEqual(
            sorted(MailLogEntry.objects.values_list("result", "mailbox__name")),
            [("assigned", "Info"), ("assigned", "Projekte"), ("inquiry", "Info")],
        )
        for mailbox in (self.projects, self.info):
            mailbox.refresh_from_db()
            self.assertIsNotNone(mailbox.last_success_at)

    def test_without_the_option_mails_without_tag_stay_alone(self) -> None:
        with mailboxes(
            {"projekte@verleih.example": FakeMailbox(make_mail("Newsletter")), "info@verleih.example": FakeMailbox()}
        ):
            result = fetch_mail(force=True)
        self.assertEqual(result.inquiries, [])
        self.assertFalse(UnknownTagMail.objects.exists())
        self.assertEqual(MailLogEntry.objects.get().result, LogResult.LEFT_IN_INBOX)

    def test_a_broken_mailbox_does_not_stop_the_others(self) -> None:
        admin = make_user("admin", superuser=True)
        broken = FakeMailbox()
        broken.fail = "Login refused"
        boxes = {
            "projekte@verleih.example": broken,
            "info@verleih.example": FakeMailbox(make_mail(f"Rider [RL#{self.project.number}]")),
        }
        with mailboxes(boxes), self.assertLogs("rentalars.mail.fetching", "WARNING"):
            result = fetch_mail(force=True)
            fetch_mail(force=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Projekte: Login refused")
        self.assertEqual(len(result.imported), 1)
        self.projects.refresh_from_db()
        self.info.refresh_from_db()
        self.assertEqual((self.projects.last_error, self.info.last_error), ("Login refused", ""))
        notice = Notification.objects.get(kind="mail_problem", user=admin)
        self.assertIn("Projekte", notice.title)

    def test_what_becomes_of_assigned_mails_per_mailbox(self) -> None:
        self.projects.after_assignment = AfterAssignment.KEEP
        self.projects.save()
        self.info.after_assignment = AfterAssignment.DELETE
        self.info.save()
        boxes = {
            "projekte@verleih.example": FakeMailbox(make_mail(f"A [RL#{self.project.number}]")),
            "info@verleih.example": FakeMailbox(make_mail(f"B [RL#{self.project.number}]")),
        }
        with mailboxes(boxes):
            fetch_mail(force=True)
            # Left in the inbox, the mail is not taken over a second time.
            again = fetch_mail(force=True)
        projects, info = boxes["projekte@verleih.example"], boxes["info@verleih.example"]
        self.assertEqual((len(projects.inbox), len(projects.kept), projects.done), (1, 1, []))
        self.assertEqual((info.inbox, len(info.deleted), info.done), ({}, 1, []))
        self.assertEqual((again.looked_at, ProjectMail.objects.count()), (0, 2))

    def test_an_inactive_mailbox_is_not_fetched(self) -> None:
        self.info.is_active = False
        self.info.save()
        boxes = {"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox()}
        with mailboxes(boxes):
            result = fetch_mail(force=True)
        self.assertEqual([part.mailbox for part in result.mailboxes], [self.projects])
        self.assertEqual(boxes["info@verleih.example"].opened, 0)

    def test_an_inquiry_is_taken_over_from_its_own_mailbox(self) -> None:
        boxes = {
            "projekte@verleih.example": FakeMailbox(),
            "info@verleih.example": FakeMailbox(make_mail("Anfrage Hochzeit", message_id="<h@example.de>")),
        }
        with mailboxes(boxes):
            fetch_mail(force=True)
            mail = assign_unknown(UnknownTagMail.objects.get(), self.project)
        self.assertEqual((mail.project, mail.mailbox, mail.assigned_by), (self.project, self.info, "manual"))
        self.assertEqual(boxes["info@verleih.example"].inbox, {})
        self.assertEqual(MailLogEntry.objects.filter(result=LogResult.ASSIGNED).get().mailbox, self.info)

    def test_the_command_reports_per_mailbox(self) -> None:
        output = io.StringIO()
        with mailboxes(
            {"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(make_mail("Anfrage"))}
        ):
            call_command("fetch_mail", "--now", stdout=output)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "Info: 1 neue Mails angesehen; 0 zugeordnet, 0 mit unbekannter Kennung, 1 Anfragen.",
                "Projekte: 0 neue Mails angesehen; 0 zugeordnet, 0 mit unbekannter Kennung, 0 Anfragen.",
            ],
        )


# --- EML-041: sending ------------------------------------------------------------------------------------


class SendingThroughTheOutgoingMailboxTests(RentalarsTestCase):
    """EML-041: mails of projects go out through the outgoing mailbox, with its address."""

    def test_the_outgoing_mailbox_sends(self) -> None:
        configure_mailbox()
        info = new_mailbox("Info", "info@verleih.example", for_correspondence=True, is_outgoing=True)
        save_mailbox(info, imap_password="geheim")
        project = make_project()
        with capture_smtp() as sent:
            mail = send_project_mail(project, to="kunde@kunde.example", subject="Angebot", body="Hallo", user=None)
        self.assertEqual(sent[0].mailbox, info)
        self.assertIn("<info@verleih.example>", sent[0]["From"])
        self.assertEqual((mail.mailbox, mail.sender_address), (info, "info@verleih.example"))
        entry = MailLogEntry.objects.get(direction=Direction.OUTGOING)
        self.assertEqual((entry.mailbox, entry.result), (info, LogResult.SENT))

    def test_an_inactive_outgoing_mailbox_sends_nothing(self) -> None:
        configure_mailbox(is_enabled=False)
        with capture_smtp() as sent, self.assertRaises(ValidationError):
            send_project_mail(make_project(), to="a@b.example", subject="x", body="y", user=None)
        self.assertEqual(sent, [])

    def test_answer_all_leaves_out_every_own_mailbox(self) -> None:
        configure_mailbox()
        add_mailbox("Info", "info@verleih.example")
        project = make_project()
        mail = ProjectMail.objects.create(
            project=project,
            message_key="k" * 64,
            message_id="<q@kunde.example>",
            sender_name="Kunde",
            sender_address="kunde@kunde.example",
            to_addresses="info@verleih.example, kollege@kunde.example",
            cc_addresses="Projekte <projekte@verleih.example>",
        )
        self.assertEqual(
            reply_recipients(mail, everyone=True), ("Kunde <kunde@kunde.example>, kollege@kunde.example", "")
        )


@override_settings(
    EMAIL_BACKEND=LOGGING_BACKEND,
    EMAIL_INNER_BACKEND=LOCMEM_BACKEND,
    DEFAULT_FROM_EMAIL="Rentalars <noreply@verleih.example>",
)
class SystemMailboxTests(RentalarsTestCase):
    """EML-041: with a system mailbox, system mails go out through its SMTP server."""

    def test_without_a_system_mailbox_the_configuration_sends(self) -> None:
        configure_mailbox()
        with recording_smtp():
            send_mail("Einladung", "Hallo", None, ["neu@verleih.example"])
        self.assertEqual(RecordingSMTP.sessions, [])
        self.assertEqual(len(django_mail.outbox), 1)
        entry = MailLogEntry.objects.get(kind=LogKind.SYSTEM)
        self.assertEqual((entry.result, entry.mailbox), (LogResult.SENT, None))

    def test_the_system_mailbox_sends_with_its_address(self) -> None:
        mailbox = configure_mailbox(for_system=True, smtp_same_login=False, smtp_user="system@verleih.example")
        mailbox.set_smtp_password("system-geheim")
        mailbox.save()
        with recording_smtp():
            send_mail("Einladung", "Hallo", None, ["neu@verleih.example"])
        (session,) = RecordingSMTP.sessions
        self.assertEqual((session.host, session.port), ("smtp.verleih.example", 587))
        self.assertEqual(session.logged_in, ("system@verleih.example", "system-geheim"))
        sender, recipients, raw = session.transmitted[0]
        self.assertEqual((sender, recipients), ("Rentalars <projekte@verleih.example>", ["neu@verleih.example"]))
        self.assertIn(b"From: Rentalars <projekte@verleih.example>", raw)
        self.assertEqual(django_mail.outbox, [])
        entry = MailLogEntry.objects.get(kind=LogKind.SYSTEM)
        self.assertEqual(
            (entry.result, entry.mailbox, entry.sender),
            (LogResult.SENT, mailbox, "Rentalars <projekte@verleih.example>"),
        )

    def test_a_switched_off_system_mailbox_leaves_it_to_the_configuration(self) -> None:
        mailbox = configure_mailbox(for_system=True)
        mailbox.is_active = False
        mailbox.save()
        self.assertIsNone(system_mailbox())
        with recording_smtp():
            send_mail("Einladung", "Hallo", None, ["neu@verleih.example"])
        self.assertEqual((RecordingSMTP.sessions, len(django_mail.outbox)), ([], 1))


# --- EML-041: checking the connection ----------------------------------------------------------------------


class ConnectionCheckTests(RentalarsTestCase):
    """EML-041: "check connection" logs in on both sides and changes nothing."""

    def test_both_sides_work(self) -> None:
        mailbox = configure_mailbox()
        box = FakeMailbox(make_mail("Newsletter"))
        with recording_smtp():
            results = check_connection(mailbox, opener=box)
        self.assertEqual([(item.part, item.ok) for item in results], [("IMAP", True), ("SMTP", True)])
        self.assertEqual(RecordingSMTP.sessions[0].logged_in, ("projekte@verleih.example", PASSWORD))
        self.assertEqual((box.fetched, len(box.inbox)), ([], 1))

    def test_problems_are_told(self) -> None:
        mailbox = configure_mailbox()
        box = FakeMailbox()
        box.fail = "Login refused"

        import smtplib

        class Refuse(smtplib.SMTP):
            # A class, not a function: the client class is derived from it (NFA-071, core.network).
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                raise OSError("Connection refused")

        with mock.patch("smtplib.SMTP", Refuse):
            results = check_connection(mailbox, opener=box)
        self.assertEqual([(item.part, item.ok) for item in results], [("IMAP", False), ("SMTP", False)])
        self.assertEqual(results[0].text, "Login refused")
        self.assertIn("Connection refused", results[1].text)

    def test_nothing_to_check(self) -> None:
        results = check_connection(Mailbox(name="Leer"))
        self.assertEqual([(item.part, item.ok) for item in results], [("", False)])


# --- EML-041: the data migration -----------------------------------------------------------------------------


# --- EML-041: the self-check -----------------------------------------------------------------------------------


class SelfCheckTests(RentalarsTestCase):
    """EML-041, EML-032: one line per mailbox; the system mailbox is named."""

    def mail_lines(self) -> dict[str, tuple[str, str]]:
        report = selfcheck.Report()
        selfcheck._mail(report)
        return {finding.title: (finding.state, finding.detail) for finding in report.findings}

    def test_every_mailbox_and_the_system_mailbox(self) -> None:
        projects = configure_mailbox(for_system=True)
        info = add_mailbox("Info", "info@verleih.example")
        info.last_error = "Login refused"
        info.save()
        lines = self.mail_lines()
        self.assertIn("über das Postfach Projekte (smtp.verleih.example:587)", lines["Systemmails"][1])
        self.assertEqual(lines["Postfach „Info“"][0], "error")
        self.assertIn("Login refused", lines["Postfach „Info“"][1])
        self.assertIn(projects.address, lines["Postfach „Projekte“"][1])

    def test_no_mailbox(self) -> None:
        self.assertEqual(self.mail_lines()["Postfächer"][1], "nicht eingerichtet")

    def test_only_a_switched_off_mailbox(self) -> None:
        # As after the update, when fetching was switched off.
        add_mailbox("Projekte", "projekte@verleih.example", is_active=False)
        self.assertEqual(self.mail_lines()["Postfächer"][1], "keines eingeschaltet")


# --- EML-043: crew and customer into "To" ------------------------------------------------------------------------


class QuickRecipientTests(RentalarsTestCase):
    """EML-043: the addresses behind "add crew" and "add customer"."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadtwerke")
        self.customer.email = "info@stadtwerke.example"
        self.customer.save()
        self.project = make_project(customer=self.customer)
        self.project.access = ProjectAccess.EDIT
        self.anna = make_person("Anna Becker", email="anna@crew.example")
        self.tom = make_person("Tom Richter", email="tom@crew.example", share_email=True)
        self.lea = make_person("Lea Sommer", email="lea@crew.example")
        self.admin = make_user("admin", superuser=True)
        self.rights = rights_of(self.admin)

    def test_the_crew_in_the_order_of_the_plan_without_declined_and_twice(self) -> None:
        plan(self.project, "Tontechnik", self.anna)
        plan(self.project, "Licht", self.tom)
        plan(self.project, "Licht", self.anna)
        plan(self.project, "Stagehand")  # an open place
        declined = plan(self.project, "Stagehand", self.lea)
        declined.request_status = RequestStatus.DECLINED
        declined.save()
        self.assertEqual(
            crew_recipients(self.project, rights=self.rights, user=self.admin),
            ["Anna Becker <anna@crew.example>", "Tom Richter <tom@crew.example>"],
        )

    def test_without_edit_access_or_personnel_only_released_addresses(self) -> None:
        """PER-019: as in the deployment view."""
        plan(self.project, "Tontechnik", self.anna)
        plan(self.project, "Licht", self.tom)
        role = Role.objects.create(
            name="Projekte lesen",
            module_levels={Module.PROJECTS: int(Level.READ)},
            special_rights=[SpecialRight.CORRESPONDENCE_READ, SpecialRight.CORRESPONDENCE_WRITE],
        )
        reader = make_user("lea", roles=(role.name,))
        self.project.access = ProjectAccess.READ
        found = crew_recipients(self.project, rights=rights_of(reader), user=reader)
        self.assertEqual(found, ["Tom Richter <tom@crew.example>"])

    def test_inactive_people_are_left_out(self) -> None:
        plan(self.project, "Tontechnik", self.anna)
        self.anna.is_active = False
        self.anna.save()
        self.assertEqual(crew_recipients(self.project, rights=self.rights, user=self.admin), [])

    def test_a_whole_project_brings_the_crew_of_its_parts(self) -> None:
        part = project_services.create_subproject(self.project, name="Bühne 2")
        plan(self.project, "Tontechnik", self.anna)
        plan(part, "Licht", self.tom)
        self.project.refresh_from_db()
        self.project.access = ProjectAccess.EDIT
        self.assertEqual(
            crew_recipients(self.project, rights=self.rights, user=self.admin),
            ["Anna Becker <anna@crew.example>", "Tom Richter <tom@crew.example>"],
        )
        part.access = ProjectAccess.EDIT
        self.assertEqual(crew_recipients(part, rights=self.rights, user=self.admin), ["Tom Richter <tom@crew.example>"])

    def test_the_contact_person_else_the_customer(self) -> None:
        self.assertEqual(customer_recipient(self.project), "Stadtwerke <info@stadtwerke.example>")
        contact = Contact.objects.create(customer=self.customer, name="Anna Muster", email="muster@stadtwerke.example")
        self.project.contact = contact
        self.project.save()
        self.assertEqual(customer_recipient(self.project), "Anna Muster <muster@stadtwerke.example>")
        part = project_services.create_subproject(self.project, name="Bühne 2", contact=None)
        self.assertEqual(customer_recipient(part), "Anna Muster <muster@stadtwerke.example>")
        self.customer.email = ""
        self.customer.save()
        self.project.contact = None
        self.project.save()
        self.assertEqual(customer_recipient(self.project), "")


class FetchWithoutMailboxTests(RentalarsTestCase):
    """EML-041: without any correspondence mailbox nothing is fetched."""

    def test_skipped(self) -> None:
        result = fetch_mail(force=True, opener=FakeMailbox())
        self.assertEqual(result.skipped, "Kein Postfach der Korrespondenz ist eingerichtet und eingeschaltet.")

    def test_a_lost_mailbox_cannot_give_its_mail(self) -> None:
        waiting = UnknownTagMail.objects.create(message_key="k" * 64, message_id="<a@b>", tag="")
        with self.assertRaises(MailboxError):
            assign_unknown(waiting, make_project())


class ExportLeavesOutSecretsTests(SimpleTestCase):
    """NFA-009, EML-041: the full export never contains a password, a key or a token – of any model."""

    def test_every_secret_field_is_left_out(self) -> None:
        from rentalars.core import export

        secret = re.compile(r"(password|_encrypted$|secret|token|key_hash)")
        # Names that only sound like a secret: a rule, a flag, a date, the link to the token a call was made with.
        harmless = {
            "core.systemsettings.password_min_length",
            "accounts.user.must_change_password",
            "api.webhook.secret_created_at",
            "api.apicallcount.token",
            "gateway_link.gatewaytokenbinding.token",  # The link to the token that a device created
            # EML-040, ADM-017: tokens of a language model – sizes of text, not secrets.
            "ai.aiprovider.context_tokens",
            "ai.aisettings.local_test_tokens_per_second",
            "ai.aicall.prompt_tokens",
            "ai.aicall.completion_tokens",
            # EML-056: the budget and the use of tokens of the nightly summaries – counts, not secrets.
            "ai.aisettings.auto_token_budget",
            "ai.autosummaryrun.tokens",
        }
        found = [
            f"{model._meta.label_lower}.{name}"
            for model in django_apps.get_models()
            for name in export._fields(model)
            if secret.search(name) and f"{model._meta.label_lower}.{name}" not in harmless
        ]
        self.assertEqual(found, [])
