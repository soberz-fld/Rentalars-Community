# SPDX-License-Identifier: GPL-3.0-or-later
"""The sender of a mail chosen by rights (EML-052, EML-003), a signature per mailbox (EML-026), and
inquiries noted by hand (EML-053).

Requirement: the sender can be chosen, always according to the rights. A mailbox is free for everybody who may write e-mail;
further sender addresses need rights ("roles per address"). Inquiries can be created by hand (e.g. when a call comes in, so that
it can be noted at once for the processing in the office).

* The mailbox that sends the correspondence and the project's default address are free for everybody who may
  write correspondence; every further address – another mailbox, an alias – needs one of its roles; superusers
  use all. Browser and API offer the choice and refuse another address.
* An alias goes out through the SMTP server of its mailbox, another mailbox through its own; mail and mail log
  name the real sender.
* A mailbox may have its own signature; empty means the common one; the preview follows the chosen sender.
* An inquiry noted by hand waits under Projekte → Anfragen, is changed and removed by who noted it or who may
  write in "E-mail", and becomes a note in the correspondence when it is taken over – never through IMAP, never
  with the automations of incoming mails.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from rentalars.accounts.models import Role
from rentalars.automations.models import AutomationRun, Trigger
from rentalars.core.changes import stamps
from rentalars.customers.models import Contact
from rentalars.mail import inquiries, senders
from rentalars.mail.aliases import save_address
from rentalars.mail.fetching import assign_unknown
from rentalars.mail.models import (
    Direction,
    InquirySource,
    Mailbox,
    MailboxAddress,
    MailLogEntry,
    ProjectMail,
    UnknownTagMail,
)
from rentalars.mail.sending import send_project_mail
from rentalars.mail.services import delete_mails_of_customer
from rentalars.mail.signature import render_signature, signature_source
from rentalars.projects import service_cases
from rentalars.projects.models import Project
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, at, make_customer, make_project, make_user
from tests.mailbox import add_mailbox, capture_smtp, configure_mailbox
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_080_communication import reply_rule

COMMON = "<p>Viele Grüße<br>{vorname} {nachname}</p>"
SUPPORT_SIGNATURE = "<p>Dein Support-Team</p>"


def alias(mailbox: Mailbox, address: str, **fields: Any) -> MailboxAddress:
    """A further address of a mailbox, stored by the rules of its role."""
    entry = MailboxAddress(mailbox=mailbox, address=address, **fields)
    save_address(entry)
    return entry


def support_role() -> Role:
    """A role of its own that writes correspondence – for the addresses that need a role."""
    role = Role(
        name="Support-Team",
        module_levels={"projects": 3, "email": 2},
        special_rights=["correspondence_read", "correspondence_write"],
    )
    role.full_clean()
    role.save()
    return role


class SenderSetup:
    """Three addresses: the outgoing mailbox (free), a second mailbox and an alias that need the role "Support-Team"."""

    def make_senders(self) -> None:
        self.box = configure_mailbox(signature_html=COMMON)
        self.support = add_mailbox("Support", "support@verleih.example")
        self.billing = alias(self.box, "buchhaltung@verleih.example")
        self.team = support_role()
        self.support.sender_roles.add(self.team)
        self.billing.sender_roles.add(self.team)
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.sven = make_user("sven", roles=("Projektleitung", "Support-Team"))
        self.project = make_project("Stadtfest")

    def keys(self, user: Any, project: Any = None) -> list[str]:
        return [sender.key for sender in senders.allowed_senders(project or self.project, user)]


# --- EML-052: who may send from which address ------------------------------------------------------------------


class SenderChoiceTests(SenderSetup, RentalarsTestCase):
    """EML-052: the outgoing mailbox for everybody, further addresses by role, all for superusers."""

    def setUp(self) -> None:
        super().setUp()
        self.make_senders()

    def test_the_outgoing_mailbox_is_free_further_addresses_need_a_role(self) -> None:
        self.assertEqual(self.keys(self.paula), ["projekte@verleih.example"])
        self.assertEqual(
            self.keys(self.sven),
            ["projekte@verleih.example", "buchhaltung@verleih.example", "support@verleih.example"],
        )
        boss = make_user("chef", superuser=True)
        self.assertEqual(len(self.keys(boss)), 3)
        # The role taken away: the address is gone for sven too.
        self.support.sender_roles.clear()
        self.assertNotIn("support@verleih.example", self.keys(self.sven))
        self.assertIn("support@verleih.example", self.keys(boss))

    def test_the_default_of_a_service_case_stays_allowed(self) -> None:
        alias(self.support, "hilfe@verleih.example", for_service_cases=True)
        case = service_cases.create_case(name="Pult defekt", customer=make_customer())
        self.assertEqual(self.keys(self.paula, case), ["hilfe@verleih.example", "projekte@verleih.example"])
        default = senders.default_choice(senders.allowed_senders(case, self.paula))
        self.assertEqual(
            (default.address, default.mailbox, default.owner), ("hilfe@verleih.example",) + (self.support,) * 2
        )

    def test_only_mailboxes_of_the_correspondence(self) -> None:
        system = add_mailbox("System", "noreply@verleih.example", for_correspondence=False, for_system=True)
        system.sender_roles.add(self.team)
        boss = make_user("chef", superuser=True)
        self.assertNotIn("noreply@verleih.example", self.keys(boss))

    def test_the_default_of_an_answer_is_the_address_the_mail_came_in_through(self) -> None:
        received = ProjectMail.objects.create(
            project=self.project,
            message_key="k1",
            message_id="<k1@x.example>",
            subject="Frage",
            sender_address="kunde@stadtwerke.example",
            to_addresses="Support <support@verleih.example>",
            mailbox=self.support,
        )
        for user, expected in ((self.sven, "support@verleih.example"), (self.paula, "projekte@verleih.example")):
            options = senders.allowed_senders(self.project, user)
            self.assertEqual(senders.default_choice(options, received).address, expected)
        # Not among the recipients (a blind copy): the mailbox it was fetched from.
        received.to_addresses = "jemand@example.org"
        options = senders.allowed_senders(self.project, self.sven)
        self.assertEqual(senders.default_choice(options, received).address, "support@verleih.example")
        # An answer to a sent mail: from the address it was sent from.
        sent = ProjectMail(direction=Direction.OUTGOING, sender_address="buchhaltung@verleih.example")
        self.assertEqual(senders.default_choice(options, sent).address, "buchhaltung@verleih.example")

    def test_refused(self) -> None:
        with self.assertRaises(PermissionDenied) as caught:
            senders.chosen_sender(self.project, self.paula, "Support@verleih.example")
        self.assertIn("Support@verleih.example", str(caught.exception))
        with self.assertRaises(ValidationError) as caught:
            senders.chosen_sender(self.project, self.sven, "fremd@example.org")
        self.assertIn("sender", caught.exception.message_dict)
        self.assertEqual(
            senders.chosen_sender(self.project, self.sven, "SUPPORT@verleih.example").mailbox, self.support
        )
        self.assertEqual(senders.chosen_sender(self.project, self.paula).address, "projekte@verleih.example")


class SendingThroughTests(SenderSetup, RentalarsTestCase):
    """EML-052: the right SMTP mailbox and ``From``; mail and mail log name the real sender."""

    def setUp(self) -> None:
        super().setUp()
        self.make_senders()

    def send(self, address: str) -> tuple[ProjectMail, Any]:
        sender = senders.chosen_sender(self.project, self.sven, address)
        with capture_smtp() as sent:
            mail = send_project_mail(
                self.project, to="kunde@example.org", subject="Plan", body="Hallo", user=self.sven, sender=sender
            )
        return mail, sent[0]

    def test_another_mailbox_through_its_own_server(self) -> None:
        mail, message = self.send("support@verleih.example")
        self.assertIn("<support@verleih.example>", message["From"])
        self.assertEqual(message.mailbox, self.support)
        self.assertEqual((mail.sender_address, mail.mailbox), ("support@verleih.example", self.support))
        entry = MailLogEntry.objects.get(mail=mail)
        self.assertIn("support@verleih.example", entry.sender)
        self.assertEqual(entry.mailbox, self.support)

    def test_an_alias_through_the_server_of_its_mailbox(self) -> None:
        mail, message = self.send("buchhaltung@verleih.example")
        self.assertIn("<buchhaltung@verleih.example>", message["From"])
        self.assertEqual(message.mailbox, self.box)
        self.assertEqual((mail.sender_address, mail.mailbox), ("buchhaltung@verleih.example", self.box))

    def test_an_alias_of_a_mailbox_that_cannot_send_goes_through_the_outgoing_one(self) -> None:
        help_alias = alias(self.support, "hilfe@verleih.example")
        help_alias.sender_roles.add(self.team)
        self.support.smtp_host = ""
        self.support.save()
        mail, message = self.send("hilfe@verleih.example")
        self.assertEqual(mail.sender_address, "hilfe@verleih.example")
        self.assertIn("<hilfe@verleih.example>", message["From"])
        self.assertEqual(message.mailbox, self.box)
        self.assertNotIn("support@verleih.example", self.keys(self.sven))

    def test_without_a_choice_as_before(self) -> None:
        with capture_smtp() as sent:
            mail = send_project_mail(
                self.project, to="kunde@example.org", subject="Plan", body="Hallo", user=self.paula
            )
        self.assertIn("<projekte@verleih.example>", sent[0]["From"])
        self.assertEqual(mail.mailbox, self.box)


# --- EML-026: a signature per mailbox ----------------------------------------------------------------------------


class MailboxSignatureTests(SenderSetup, RentalarsTestCase):
    """EML-026: the mailbox's own signature, else the common one; aliases use their mailbox's."""

    def setUp(self) -> None:
        super().setUp()
        self.make_senders()
        self.sven.first_name = "Sven"
        self.sven.save()
        self.support.signature_html = SUPPORT_SIGNATURE
        self.support.save()

    def test_own_or_common(self) -> None:
        self.assertEqual(signature_source(self.support), SUPPORT_SIGNATURE)
        self.assertEqual(signature_source(self.box), COMMON)
        self.assertEqual(signature_source(None), COMMON)
        self.assertIn("Dein Support-Team", render_signature(self.sven, mailbox=self.support).text)
        self.assertIn("Viele Grüße", render_signature(self.sven, mailbox=self.box).text)

    def test_the_mail_carries_the_signature_of_its_mailbox(self) -> None:
        help_alias = alias(self.support, "hilfe@verleih.example")
        help_alias.sender_roles.add(self.team)
        results = {}
        for address in ("support@verleih.example", "hilfe@verleih.example", "projekte@verleih.example"):
            sender = senders.chosen_sender(self.project, self.sven, address)
            with capture_smtp():
                mail = send_project_mail(
                    self.project, to="kunde@example.org", subject="x", body="Hallo", user=self.sven, sender=sender
                )
            results[address] = mail.html_body
        self.assertIn("Dein Support-Team", results["support@verleih.example"])
        self.assertIn("Dein Support-Team", results["hilfe@verleih.example"])  # an alias: its mailbox's
        self.assertIn("Viele Grüße", results["projekte@verleih.example"])
        self.assertNotIn("Dein Support-Team", results["projekte@verleih.example"])


# --- EML-052, EML-026 on the pages ---------------------------------------------------------------------------------


class ComposePageTests(SenderSetup, UiTestCase):
    """EML-052: the choice when writing, the default of an answer, the refusal; EML-026: the preview follows."""

    def setUp(self) -> None:
        super().setUp()
        self.make_senders()
        self.support.signature_html = SUPPORT_SIGNATURE
        self.support.save()
        self.url = reverse("mail:compose", args=[self.project.pk])

    def test_the_choice_with_name_and_address(self) -> None:
        page = self.assert_ok(self.browser_of(self.sven).get(self.url))
        self.assertIn('name="sender"', page)
        self.assertIn(
            '<option value="projekte@verleih.example" selected>Projekte &lt;projekte@verleih.example&gt;', page
        )
        self.assertIn('<option value="support@verleih.example">Support &lt;support@verleih.example&gt;', page)
        self.assertIn(f'hx-get="{reverse("mail:compose_signature", args=[self.project.pk])}"', page)
        # The preview without scripts: the default's mailbox (no own signature – the common one).
        self.assertIn(f"{reverse('mail:signature_preview')}?mailbox={self.box.pk}", page)
        # Only one address to use: no choice, the sender is named as before.
        page = self.assert_ok(self.browser_of(self.paula).get(self.url))
        self.assertNotIn('name="sender"', page)
        self.assertIn("Gesendet von", page)

    def test_sent_from_the_address_chosen(self) -> None:
        browser = self.browser_of(self.sven)
        data = form_data(
            browser.get(self.url),
            "to",
            to="kunde@example.org",
            subject="Plan",
            body="Hallo",
            sender="support@verleih.example",
        )
        with capture_smtp() as sent:
            response = browser.post(self.url, data)
        mail = ProjectMail.objects.get(direction=Direction.OUTGOING)
        self.assertRedirects(response, reverse("mail:detail", args=[self.project.pk, mail.pk]))
        self.assertEqual((mail.sender_address, mail.mailbox), ("support@verleih.example", self.support))
        self.assertEqual(sent[0].mailbox, self.support)
        self.assertIn("Dein Support-Team", mail.html_body)

    def test_an_address_the_writer_may_not_use_is_refused(self) -> None:
        self.billing.sender_roles.add(Role.objects.get(name="Projektleitung"))  # paula: two addresses, a choice
        browser = self.browser_of(self.paula)
        data = form_data(
            browser.get(self.url),
            "to",
            to="kunde@example.org",
            subject="Plan",
            body="Hallo",
            sender="support@verleih.example",
        )
        with capture_smtp() as sent:
            page = self.assert_ok(browser.post(self.url, data))
        self.assertIn("Von dieser Adresse darfst du nicht senden.", page)
        self.assertEqual(sent, [])
        self.assertFalse(ProjectMail.objects.exists())

    def test_an_answer_from_the_address_the_mail_came_to(self) -> None:
        received = ProjectMail.objects.create(
            project=self.project,
            message_key="k1",
            message_id="<k1@x.example>",
            subject="Frage",
            sender_name="Kunde",
            sender_address="kunde@stadtwerke.example",
            to_addresses="support@verleih.example",
            mailbox=self.support,
        )
        page = self.assert_ok(self.browser_of(self.sven).get(f"{self.url}?answer={received.pk}"))
        self.assertIn('<option value="support@verleih.example" selected>', page)
        self.assertIn(f"?mailbox={self.support.pk}", page)

    def test_the_preview_follows_the_sender(self) -> None:
        url = reverse("mail:compose_signature", args=[self.project.pk])
        frame = self.assert_ok(self.browser_of(self.sven).get(url, {"sender": "support@verleih.example"}))
        self.assertIn('id="signature-frame"', frame)
        self.assertIn(f"?mailbox={self.support.pk}", frame)
        # Not one of paula's addresses: the default's preview.
        frame = self.assert_ok(self.browser_of(self.paula).get(url, {"sender": "support@verleih.example"}))
        self.assertIn(f"?mailbox={self.box.pk}", frame)
        preview = reverse("mail:signature_preview")
        self.assertIn(
            "Dein Support-Team", self.browser_of(self.sven).get(f"{preview}?mailbox={self.support.pk}").content.decode()
        )
        common = self.browser_of(self.sven).get(f"{preview}?mailbox={self.box.pk}").content.decode()
        self.assertIn("Viele Grüße", common)
        reader = self.browser_for("nora", "Lager")
        self.assertEqual(reader.get(url).status_code, 403)


class MailboxSettingsPageTests(SenderSetup, UiTestCase):
    """EML-052: roles per address under Einstellungen → Postfächer; EML-026: the editor of a mailbox's signature."""

    def setUp(self) -> None:
        super().setUp()
        self.make_senders()

    def test_roles_of_a_mailbox_and_of_an_alias(self) -> None:
        url = reverse("mail:mailbox_edit", args=[self.support.pk])
        page = self.client.get(url)
        text = self.assert_ok(page)
        self.assertIn("Als Absender wählbar für", text)
        self.assertIn('name="sender_roles"', text)
        lead = Role.objects.get(name="Projektleitung")
        data = form_data(page, "name", sender_roles=[str(lead.pk)])
        self.assertRedirects(self.client.post(url, data), reverse("mail:settings"))
        self.assertEqual(list(self.support.sender_roles.all()), [lead])
        url = reverse("mail:address_edit", args=[self.box.pk, self.billing.pk])
        page = self.client.get(url)
        data = form_data(page, "address", sender_roles=[str(lead.pk), str(self.team.pk)])
        self.client.post(url, data)
        self.assertEqual(set(self.billing.sender_roles.all()), {lead, self.team})
        listed = self.assert_ok(self.client.get(reverse("mail:mailbox_edit", args=[self.box.pk])))
        self.assertIn("Absender für:", listed)

    def test_the_signature_of_a_mailbox(self) -> None:
        url = reverse("mail:mailbox_signature", args=[self.support.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Signatur von „Support“", page)
        self.assertIn(f'name="mailbox" value="{self.support.pk}"', page)
        response = self.client.post(url, {"html": '<p onclick="x()">Support {vorname}</p><script>x()</script>'})
        self.assertRedirects(response, reverse("mail:settings") + "#signature", fetch_redirect_response=False)
        self.support.refresh_from_db()
        self.assertEqual(self.support.signature_html, "<p>Support {vorname}</p>")
        settings_page = self.assert_ok(self.client.get(reverse("mail:settings")))
        self.assertIn("Signaturen der Postfächer", settings_page)
        self.assertIn("eigene Signatur", settings_page)
        # A draft left empty shows the common signature; saving it empty brings the common one back.
        preview = self.client.post(reverse("mail:signature_preview"), {"html": "", "mailbox": self.support.pk})
        self.assertIn("Viele Grüße", preview.content.decode())
        self.client.post(url, {"html": ""})
        self.support.refresh_from_db()
        self.assertEqual(self.support.signature_html, "")
        # Write access to "E-mail" alone does not change signatures – as for the common one.
        self.assertEqual(self.browser_of(self.paula).get(url).status_code, 403)


# --- EML-052, EML-026 in the API ---------------------------------------------------------------------------------


class SenderApiTests(SenderSetup, ApiTestCase):
    """API-014: ``GET …/mails/senders``, ``sender`` when sending, the fields of mailboxes and addresses."""

    def setUp(self) -> None:
        super().setUp()
        self.make_senders()
        self.base = f"{API}/projects/{self.project.pk}/mails"

    def test_the_senders_of_the_caller(self) -> None:
        response = self.client_of(self.sven).get(f"{self.base}/senders")
        self.assertEqual(response.status_code, 200, response.content)
        listed = response.json()
        self.assertEqual(
            [(entry["address"], entry["is_default"]) for entry in listed],
            [
                ("projekte@verleih.example", True),
                ("buchhaltung@verleih.example", False),
                ("support@verleih.example", False),
            ],
        )
        billing = listed[1]
        self.assertEqual(
            (billing["is_alias"], billing["mailbox"], billing["sends_through"]), (True,) + (self.box.pk,) * 2
        )
        received = ProjectMail.objects.create(
            project=self.project, message_key="k1", message_id="<k1@x>", to_addresses="support@verleih.example"
        )
        listed = self.client_of(self.sven).get(f"{self.base}/senders", {"answer_to": received.pk}).json()
        self.assertEqual([entry["address"] for entry in listed if entry["is_default"]], ["support@verleih.example"])
        self.assertEqual(
            [entry["address"] for entry in self.client_of(self.paula).get(f"{self.base}/senders").json()],
            ["projekte@verleih.example"],
        )
        crew = self.client_for("kai", "Crew")
        self.assertIn(crew.get(f"{self.base}/senders").status_code, (403, 404))

    def test_send_from_a_chosen_address_or_be_refused(self) -> None:
        body = {"to": "kunde@example.org", "subject": "Plan", "body": "Hallo", "sender": "support@verleih.example"}
        with capture_smtp() as sent:
            response = self.client_of(self.sven).post(self.base, body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["sender_address"], "support@verleih.example")
        self.assertEqual(sent[0].mailbox, self.support)
        with capture_smtp() as sent:
            refused = self.client_of(self.paula).post(self.base, body, format="json")
        error = self.assert_error(refused, 403, "permission_denied")
        self.assertEqual(error["message"], "Von support@verleih.example darfst du nicht senden.")
        self.assertEqual(sent, [])
        unknown = self.client_of(self.sven).post(self.base, {**body, "sender": "fremd@example.org"}, format="json")
        self.assert_error(unknown, 400, "validation_error", "sender")

    def test_mailbox_and_address_fields(self) -> None:
        url = f"{API}/mail/mailboxes/{self.support.pk}"
        data = self.admin.get(url).json()
        self.assertEqual((data["sender_roles"], data["signature_html"]), ([self.team.pk], ""))
        response = self.admin.patch(url, {"signature_html": "<b>Support</b><script>x</script>"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["signature_html"], "<b>Support</b>")
        lead = Role.objects.get(name="Projektleitung")
        paula = self.client_of(self.paula)  # write access to "E-mail", not to the settings
        self.assertEqual(paula.patch(url, {"sender_roles": [lead.pk]}, format="json").status_code, 200)
        self.assertEqual(list(self.support.sender_roles.all()), [lead])
        self.assertEqual(paula.patch(url, {"signature_html": "<b>Andere</b>"}, format="json").status_code, 403)
        self.support.refresh_from_db()
        self.assertEqual(self.support.signature_html, "<b>Support</b>")
        created = self.admin.post(
            f"{API}/mail/mailbox-addresses",
            {"mailbox": self.support.pk, "address": "Hilfe@verleih.example", "sender_roles": [lead.pk]},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["sender_roles"], [lead.pk])
        changed = self.admin.patch(
            f"{API}/mail/mailbox-addresses/{created.json()['id']}", {"sender_roles": []}, format="json"
        )
        self.assertEqual(changed.json()["sender_roles"], [])


# --- EML-053: inquiries noted by hand ------------------------------------------------------------------------------


def note_call(user: Any, **values: Any) -> UnknownTagMail:
    """An inquiry noted by hand: Max Muster called at 9:30 on 28 February."""
    defaults = {
        "date": at(28, 9, 30, month=2),
        "contact_name": "Max Muster",
        "phone": "0171 2345678",
        "contact_email": "max@stadthalle.example",
        "subject": "Zwei Lautsprecher für Freitag",
        "note": "Braucht zwei Tops und ein Pult.",
    }
    return inquiries.create_manual(user=user, **{**defaults, **values})


class ManualInquiryTests(RentalarsTestCase):
    """EML-053: noting, checking, changing, who may – and the note it becomes."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.paula.first_name, self.paula.last_name = "Paula", "Plan"
        self.paula.save()
        self.customer = make_customer("Stadthalle")
        self.contact = Contact.objects.create(customer=self.customer, name="Max Muster", email="max@stadthalle.example")

    def test_noted(self) -> None:
        inquiry = note_call(self.paula, customer=self.customer)
        self.assertTrue(inquiry.is_manual and inquiry.is_inquiry)
        self.assertFalse(inquiry.is_defect)
        self.assertEqual(inquiry.source, InquirySource.MANUAL)
        self.assertTrue(inquiry.message_key.startswith("manual:"))
        self.assertIsNone(inquiry.mailbox)
        self.assertEqual(inquiry.sender, "Max Muster <max@stadthalle.example>")
        self.assertEqual((inquiry.created_by, inquiry.date, inquiry.tag), (self.paula, at(28, 9, 30, month=2), ""))
        only_phone = inquiries.create_manual(user=self.paula, phone="0171 1", note="Rückruf")
        self.assertEqual(only_phone.sender, "0171 1")
        self.assertLess(abs(only_phone.date - timezone.now()), datetime.timedelta(seconds=5))

    def test_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            inquiries.create_manual(user=self.paula, note="Wer war das?")
        self.assertIn("contact_name", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            inquiries.create_manual(user=self.paula, contact_name="Max")
        self.assertIn("note", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            note_call(self.paula, date=timezone.now() + datetime.timedelta(days=1))
        self.assertIn("date", caught.exception.message_dict)
        self.assertFalse(UnknownTagMail.objects.exists())

    def test_change_delete_and_who_may(self) -> None:
        from rentalars.accounts.rights import rights_of

        inquiry = note_call(self.paula)
        inquiries.update_manual(inquiry, phone="030 123", customer=self.customer)
        inquiry.refresh_from_db()
        self.assertEqual((inquiry.phone, inquiry.customer, inquiry.version), ("030 123", self.customer, 1))
        office = make_user("otto", roles=("Projektleitung",))  # write access to "E-mail"
        reader = make_user("nora", roles=("Nur-Lesen",))  # read access only
        self.assertTrue(inquiries.may_change(inquiry, self.paula, rights_of(self.paula)))
        self.assertTrue(inquiries.may_change(inquiry, office, rights_of(office)))
        self.assertFalse(inquiries.may_change(inquiry, reader, rights_of(reader)))
        # Who noted it may still change it with read access only.
        inquiry.created_by = reader
        self.assertTrue(inquiries.may_change(inquiry, reader, rights_of(reader)))
        mail_entry = UnknownTagMail.objects.create(message_key="x", subject="Mail", sender="a@b.example")
        self.assertFalse(inquiries.may_change(mail_entry, office, rights_of(office)))
        with self.assertRaises(ValidationError):
            inquiries.update_manual(mail_entry, subject="geändert")
        inquiries.delete_manual(inquiry)
        self.assertFalse(UnknownTagMail.objects.filter(pk=inquiry.pk).exists())

    def test_suggestions(self) -> None:
        suggested = inquiries.project_initial(note_call(self.paula))
        self.assertEqual(
            suggested, {"name": "Zwei Lautsprecher für Freitag", "customer": self.customer, "contact": self.contact}
        )
        stranger = note_call(self.paula, contact_email="", contact_name="Erna", subject="", customer=self.customer)
        suggested = service_cases.suggestions_from_inquiry(stranger)
        self.assertEqual(suggested["name"], "Braucht zwei Tops und ein Pult.")
        self.assertEqual(suggested["customer"], self.customer)
        self.assertEqual(suggested["case_contact"], "Erna, 0171 2345678")

    def test_taken_over_it_becomes_a_note(self) -> None:
        inquiry = note_call(self.paula, customer=self.customer)
        project = make_project("Hoffest", customer=self.customer)
        note = assign_unknown(inquiry, project)  # no mailbox is opened: there is none
        self.assertTrue(note.is_note)
        self.assertEqual((note.project, note.date, note.subject), (project, at(28, 9, 30, month=2), inquiry.subject))
        self.assertEqual(note.sent_by, self.paula)
        self.assertEqual(
            note.text_body,
            "Wer: Max Muster\nTelefon: 0171 2345678\nE-Mail: max@stadthalle.example\nKunde: Stadthalle\n\n"
            "Braucht zwei Tops und ein Pult.",
        )
        inquiry.refresh_from_db()
        self.assertIsNotNone(inquiry.resolved_at)
        with self.assertRaises(ValidationError):
            assign_unknown(inquiry, project)
        self.assertEqual(ProjectMail.objects.count(), 1)

    def test_no_automation_of_incoming_mails(self) -> None:
        reply_rule()
        with self.captureOnCommitCallbacks(execute=True):
            inquiry = note_call(self.paula)
            assign_unknown(inquiry, make_project())
        self.assertFalse(AutomationRun.objects.filter(automation__trigger=Trigger.INQUIRY).exists())

    def test_gone_with_the_customer_and_seen_by_the_change_watch(self) -> None:
        nora = make_user("nora", roles=("Nur-Lesen",))
        before = stamps(["mail:unknown"], nora)["mail:unknown"]
        inquiry = note_call(self.paula)
        noted = stamps(["mail:unknown"], nora)["mail:unknown"]
        self.assertNotEqual(before, noted)
        inquiries.update_manual(inquiry, subject="Drei Lautsprecher")
        self.assertNotEqual(noted, stamps(["mail:unknown"], nora)["mail:unknown"])
        delete_mails_of_customer(self.customer)  # KND-010: the address of its contact
        self.assertFalse(UnknownTagMail.objects.exists())


class ManualInquiryPageTests(UiTestCase):
    """EML-053 on the pages: note, list, change, remove, take over as project, case or into a project."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.browser = self.browser_of(self.paula)
        self.customer = make_customer("Stadthalle")
        self.contact = Contact.objects.create(customer=self.customer, name="Max Muster", email="max@stadthalle.example")
        self.list_url = reverse("mail:unknown_list")

    def test_note_an_inquiry_and_see_it_in_the_list(self) -> None:
        listed = self.assert_ok(self.browser.get(self.list_url))
        create = reverse("mail:inquiry_create")
        self.assertIn(create, listed)
        self.assertIn("Anfrage anlegen", listed)
        form = self.browser.get(create)
        text = self.assert_ok(form)
        self.assertIn('type="datetime-local"', text)
        self.assertIn(reverse("customers:suggest"), text)
        data = form_data(
            form,
            "contact_name",
            date="2027-02-28T09:30",
            contact_name="Max Muster",
            phone="0171 2345678",
            contact_email="max@stadthalle.example",
            customer=str(self.customer.pk),
            subject="Zwei Lautsprecher",
            note="Braucht zwei Tops.",
        )
        self.assertRedirects(self.browser.post(create, data), self.list_url)
        inquiry = UnknownTagMail.objects.get()
        self.assertEqual((inquiry.source, inquiry.created_by, inquiry.customer), ("manual", self.paula, self.customer))
        listed = self.assert_ok(self.browser.get(self.list_url))
        self.assertIn('<span class="badge outline">Notiert</span>', listed)
        self.assertIn("0171 2345678 · max@stadthalle.example · Stadthalle", listed)
        self.assertIn(reverse("mail:inquiry_edit", args=[inquiry.pk]), listed)
        self.assertIn(f"{reverse('projects:create')}?inquiry={inquiry.pk}", listed)
        self.assertIn(f"{reverse('projects:case_create')}?inquiry={inquiry.pk}", listed)
        filtered = self.assert_ok(self.browser.get(self.list_url, {"kind": "manual"}))
        self.assertIn("Zwei Lautsprecher", filtered)
        self.assertNotIn("Zwei Lautsprecher", self.assert_ok(self.browser.get(self.list_url, {"kind": "inquiry"})))
        self.assertIn("Zwei Lautsprecher", self.assert_ok(self.browser.get(self.list_url, {"q": "0171"})))
        # The start page counts it among the waiting ones.
        self.assertEqual(self.browser.get(reverse("core:home")).context["unknown_mail_count"], 1)

    def test_refused_and_rights(self) -> None:
        create = reverse("mail:inquiry_create")
        page = self.assert_ok(
            self.browser.post(create, {"date": "2030-01-01T10:00", "contact_name": "Max", "note": "x"})
        )
        self.assertIn("wähle eine Zeit, die vergangen ist", page)
        page = self.assert_ok(self.browser.post(create, {"date": "2027-02-28T10:00", "note": "x"}))
        self.assertIn("Gib an, von wem die Anfrage ist", page)
        self.assertFalse(UnknownTagMail.objects.exists())
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertNotIn("Anfrage anlegen", self.assert_ok(reader.get(self.list_url)))
        self.assertEqual(reader.get(create).status_code, 403)
        inquiry = note_call(self.paula)
        self.assertEqual(reader.get(reverse("mail:inquiry_edit", args=[inquiry.pk])).status_code, 403)
        self.assertEqual(reader.post(reverse("mail:inquiry_delete", args=[inquiry.pk])).status_code, 403)

    def test_change_and_delete(self) -> None:
        inquiry = note_call(self.paula)
        url = reverse("mail:inquiry_edit", args=[inquiry.pk])
        page = self.browser.get(url)
        text = self.assert_ok(page)
        self.assertIn("Anfrage bearbeiten", text)
        self.assertIn('value="2027-02-28T09:30"', text)
        data = form_data(page, "contact_name", phone="030 123", customer=str(self.customer.pk))
        self.assertRedirects(self.browser.post(url, data), self.list_url)
        inquiry.refresh_from_db()
        self.assertEqual(
            (inquiry.phone, inquiry.customer, inquiry.subject),
            ("030 123", self.customer, "Zwei Lautsprecher für Freitag"),
        )
        # Another with write access to "E-mail" may as well.
        office = self.browser_for("otto", "Projektleitung")
        self.assertEqual(office.get(url).status_code, 200)
        response = office.post(reverse("mail:inquiry_delete", args=[inquiry.pk]), follow=True)
        self.assertIn("Die Anfrage wurde gelöscht.", self.messages_of(response))
        self.assertFalse(UnknownTagMail.objects.exists())

    def test_dismissed_like_the_others(self) -> None:
        inquiry = note_call(self.paula)
        response = self.browser.post(reverse("mail:unknown_dismiss", args=[inquiry.pk]), follow=True)
        self.assertIn("Die Anfrage ist von der Liste genommen.", self.messages_of(response))
        inquiry.refresh_from_db()
        self.assertIsNotNone(inquiry.resolved_at)
        self.assertEqual(self.browser.get(reverse("mail:inquiry_edit", args=[inquiry.pk])).status_code, 404)

    def test_as_a_project(self) -> None:
        inquiry = note_call(self.paula)
        url = f"{reverse('projects:create')}?inquiry={inquiry.pk}"
        page = self.browser.get(url)
        text = self.assert_ok(page)
        self.assertIn("Aus der händisch notierten Anfrage „Zwei Lautsprecher für Freitag“", text)
        data = form_data(page, "name")
        self.assertEqual(
            (data["name"], data["customer"], data["contact"]),
            ("Zwei Lautsprecher für Freitag", str(self.customer.pk), str(self.contact.pk)),
        )
        response = self.browser.post(url, data, follow=True)
        project = Project.objects.get(name="Zwei Lautsprecher für Freitag")
        self.assertIn("Die Anfrage ist jetzt eine Notiz in der Korrespondenz des Projekts.", self.messages_of(response))
        note = ProjectMail.objects.get(project=project)
        self.assertTrue(note.is_note)
        self.assertIn("Telefon: 0171 2345678", note.text_body)
        inquiry.refresh_from_db()
        self.assertIsNotNone(inquiry.resolved_at)

    def test_as_a_service_case(self) -> None:
        inquiry = note_call(self.paula, contact_email="", contact_name="Erna Beispiel", customer=self.customer)
        url = f"{reverse('projects:case_create')}?inquiry={inquiry.pk}"
        page = self.browser.get(url)
        self.assertIn("Aus der händisch notierten Anfrage", self.assert_ok(page))
        data = form_data(page, "name")
        self.assertEqual(
            (data["name"], data["customer"], data["case_contact"]),
            ("Zwei Lautsprecher für Freitag", str(self.customer.pk), "Erna Beispiel, 0171 2345678"),
        )
        response = self.browser.post(url, data, follow=True)
        case = Project.objects.get(name="Zwei Lautsprecher für Freitag")
        self.assertTrue(case.is_service_case)
        self.assertIn(
            "Die Anfrage ist jetzt eine Notiz in der Korrespondenz des Servicefalls.", self.messages_of(response)
        )
        self.assertTrue(ProjectMail.objects.get(project=case).is_note)

    def test_into_an_existing_project(self) -> None:
        inquiry = note_call(self.paula)
        project = make_project("Hoffest", customer=self.customer)
        response = self.browser.post(
            reverse("mail:unknown_assign", args=[inquiry.pk]), {"project_number": project.number}, follow=True
        )
        note = ProjectMail.objects.get(project=project)
        self.assertRedirects(response, reverse("mail:detail", args=[project.pk, note.pk]))
        self.assertIn(
            f"Die Anfrage ist jetzt eine Notiz in der Korrespondenz von {project}.", self.messages_of(response)
        )
        self.assertIn("Braucht zwei Tops und ein Pult.", self.assert_ok(response))


class ManualInquiryApiTests(ApiTestCase):
    """API-014: noting, reading, changing and deleting an inquiry; taking it over into a project or a case."""

    def setUp(self) -> None:
        super().setUp()
        self.paula_user = make_user("paula", roles=("Projektleitung",))
        self.paula = self.client_of(self.paula_user)
        self.customer = make_customer("Stadthalle")

    def note(self, **values: Any) -> dict[str, Any]:
        body = {"contact_name": "Max Muster", "phone": "0171 2345678", "subject": "Lautsprecher", **values}
        response = self.paula.post(f"{API}/mail/unknown", body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_note_read_change_delete(self) -> None:
        data = self.note(customer=self.customer.pk, date="2027-02-28T09:30:00+01:00", note="Zwei Tops")
        self.assertEqual(
            (data["source"], data["sender"], data["phone"], data["customer"], data["customer_name"]),
            ("manual", "Max Muster", "0171 2345678", self.customer.pk, "Stadthalle"),
        )
        # The earlier fields keep their meaning (the companion app reads them).
        self.assertEqual(
            (data["tag"], data["is_inquiry"], data["mailbox"], data["defect_report"]), ("", True, None, None)
        )
        self.assertTrue(data["can_change"])
        listed = self.admin.get(f"{API}/mail/unknown").json()
        self.assertEqual([entry["id"] for entry in listed], [data["id"]])
        detail = f"{API}/mail/unknown/{data['id']}"
        self.assertEqual(self.admin.get(detail).json()["note"], "Zwei Tops")
        changed = self.paula.patch(detail, {"contact_email": "max@stadthalle.example"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["sender"], "Max Muster <max@stadthalle.example>")
        reader = self.client_for("nora", "Nur-Lesen")
        self.assertFalse(reader.get(detail).json()["can_change"])
        self.assertEqual(reader.patch(detail, {"phone": "1"}, format="json").status_code, 403)
        self.assertEqual(reader.delete(detail).status_code, 403)
        self.assertEqual(
            reader.post(f"{API}/mail/unknown", {"contact_name": "x", "note": "y"}, format="json").status_code, 403
        )
        self.assertEqual(self.paula.delete(detail).status_code, 204)
        self.assertFalse(UnknownTagMail.objects.exists())

    def test_refused(self) -> None:
        response = self.paula.post(f"{API}/mail/unknown", {"note": "Wer?"}, format="json")
        self.assert_error(response, 400, "validation_error", "contact_name")
        response = self.paula.post(
            f"{API}/mail/unknown",
            {"contact_name": "Max", "note": "x", "date": "2031-01-01T10:00:00+01:00"},
            format="json",
        )
        self.assert_error(response, 400, "validation_error", "date")
        mail_entry = UnknownTagMail.objects.create(message_key="x", subject="Mail", sender="a@b.example")
        self.assert_error(
            self.paula.patch(f"{API}/mail/unknown/{mail_entry.pk}", {"subject": "y"}, format="json"),
            400,
            "validation_error",
        )
        crew = self.client_for("kai", "Crew")
        self.assertEqual(crew.get(f"{API}/mail/unknown/{mail_entry.pk}").status_code, 403)

    def test_into_a_project_a_case_or_an_existing_project(self) -> None:
        first = self.note(note="Erstes")
        body = {
            "name": "Hoffest",
            "customer": self.customer.pk,
            "start": "2027-03-10T08:00:00+01:00",
            "end": "2027-03-12T18:00:00+01:00",
            "inquiry": first["id"],
        }
        created = self.paula.post(f"{API}/projects", body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        note = ProjectMail.objects.get(project_id=created.json()["id"])
        self.assertTrue(note.is_note)
        self.assertIn("Erstes", note.text_body)
        second = self.note(note="Zweites")
        case = self.paula.post(
            f"{API}/service-cases",
            {"name": "Pult", "customer": self.customer.pk, "inquiry": second["id"]},
            format="json",
        )
        self.assertEqual(case.status_code, 201, case.content)
        self.assertTrue(ProjectMail.objects.get(project_id=case.json()["id"]).is_note)
        third = self.note(note="Drittes")
        project = make_project("Stadtfest", customer=self.customer)
        assigned = self.paula.post(f"{API}/mail/unknown/{third['id']}/assign", {"project": project.pk}, format="json")
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertTrue(ProjectMail.objects.get(pk=assigned.json()["mail"]).is_note)
        self.assertFalse(UnknownTagMail.objects.filter(resolved_at__isnull=True).exists())
