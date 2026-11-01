# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "mail".

* PRJ-107: Projekte → Anfragen as a table (columns, sorting, CSV, filters),
  the project number with suggestions, "Als Projekt anlegen", the trash-can
  button and taking several mails off the list after a confirmation.
* EML-047: the further addresses of a mailbox in Einstellungen → Postfächer.
* EML-006: "nur als gelesen markieren" among the choices for assigned mails.
* EML-048: without a mail server the places that send say "nicht versendet".
"""

from __future__ import annotations

import json

from django.test import override_settings
from django.urls import reverse

from rentalars.customers.models import Contact
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import MailboxAddress, MailLogEntry, ProjectMail, UnknownTagMail, Untagged
from rentalars.projects.models import Project
from tests.helpers import make_customer, make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes, make_mail
from tests.ui.base import UiTestCase, form_data

INQUIRIES = "/projects/inquiries/"
LOGGING_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"
LOG_ONLY_BACKEND = "django.core.mail.backends.dummy.EmailBackend"


class InquiryPageTests(UiTestCase):
    """PRJ-107: the list of waiting mails as a table, with the actions of each row and for several rows."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=True)
        self.project = make_project("Stadtfest Musterstadt")
        self.raw = make_mail("AW: Angebot Bühne", message_id="<a@x.example>", sender="Max <max@stadthalle.example>")
        mails = [self.raw, make_mail("Frage Pult", message_id="<b@x.example>"), make_mail("[RL#2099-0001] Tippfehler")]
        with mailboxes({self.box.address: FakeMailbox(*mails)}):
            fetch_mail(force=True)
        self.inquiry = UnknownTagMail.objects.get(subject="AW: Angebot Bühne")

    def test_the_table(self) -> None:
        text = self.assert_ok(self.client.get(INQUIRIES))
        self.assertIn('<table class="table stack inquiry-list">', text)
        for heading in ("Betreff", "Absender", "Datum", "Kennung", "Postfach"):
            self.assertIn(f">{heading}<", text)
        self.assertIn('href="?format=csv"', text)
        self.assertIn("CSV mit allen Spalten", text)
        # Sorting by a click on a heading.
        self.assertIn('href="?sort=subject"', text)
        sorted_text = self.assert_ok(self.client.get(INQUIRIES, {"sort": "subject"}))
        self.assertLess(sorted_text.index("AW: Angebot Bühne"), sorted_text.index("Frage Pult"))
        self.assertIn('aria-sort="ascending"', sorted_text)
        only_tag = self.assert_ok(self.client.get(INQUIRIES, {"kind": "unknown_tag"}))
        self.assertIn("2099-0001", only_tag)
        self.assertNotIn("Frage Pult", only_tag)
        self.assertIn("Keine Mail passt zu den Filtern.", self.assert_ok(self.client.get(INQUIRIES, {"q": "nichts"})))

    def test_grouped(self) -> None:
        """UIX-040: "Gruppieren nach" – a heading row per value with its number of mails, over the whole width."""
        text = self.assert_ok(self.client.get(INQUIRIES))
        self.assertIn("Gruppieren nach", text)
        # UIX-044: the shown columns are offered – the address (off by default) once it is shown.
        for value in ("subject", "sender", "date", "tag", "mailbox"):
            self.assertIn(f'<option value="{value}"', text)
        self.assertNotIn('<option value="address"', text)
        shown = self.assert_ok(self.client.get(INQUIRIES, {"cols": "all"}))
        self.assertIn('<option value="address"', shown)
        grouped = self.assert_ok(self.client.get(INQUIRIES, {"group": "tag"}))
        headings = grouped.count('<tr class="table-group">')
        self.assertEqual(headings, 2)
        self.assertIn('<th colspan="7" scope="colgroup"><span class="badge accent">ohne Kennung</span>', grouped)
        self.assertIn("2 Einträge", grouped)
        self.assertLess(grouped.index("ohne Kennung</span> <span"), grouped.index("<code>2099-0001</code> <span"))
        by_day = self.assert_ok(self.client.get(INQUIRIES, {"group": "date"}))
        self.assertIn('01.03.2027 <span class="table-group-count">3 Einträge</span>', by_day)
        by_address = self.assert_ok(self.client.get(INQUIRIES, {"group": "address"}))
        self.assertIn('projekte@verleih.example <span class="table-group-count">3 Einträge</span>', by_address)
        # The CSV file is not grouped.
        csv = self.client.get(INQUIRIES, {"group": "tag", "format": "csv"}).content.decode("utf-8-sig")
        self.assertEqual(len(csv.strip().splitlines()), 4)

    def test_the_csv(self) -> None:
        response = self.client.get(INQUIRIES, {"format": "csv", "cols": "all"})
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8-sig")
        self.assertTrue(text.startswith("Betreff;Absender;Datum;Kennung;Postfach;Empfangsadresse;gefunden"), text[:80])
        self.assertIn("AW: Angebot Bühne;Max <max@stadthalle.example>", text)
        self.assertIn("ohne Kennung", text)

    def test_the_actions_of_a_row(self) -> None:
        text = self.assert_ok(self.client.get(INQUIRIES))
        row = text[text.index(f'value="{self.inquiry.pk}" form="bulk-form"') :]
        row = row[: row.index("</tr>")]
        self.assertIn(f'data-url="{reverse("mail:project_suggestions")}"', row)
        self.assertIn('aria-label="Projektnummer"', row)
        self.assertIn(f'href="{reverse("projects:create")}?inquiry={self.inquiry.pk}"', row)
        self.assertIn("Als Projekt anlegen", row)
        self.assertIn("Als Servicefall anlegen", row)
        # "von der Liste nehmen" is a small trash-can button that names itself to screen readers and on focus.
        self.assertIn('<button class="icon-btn" type="submit" title="von der Liste nehmen">', row)
        self.assertIn('<span class="visually-hidden">von der Liste nehmen</span>', row)
        self.assertNotIn('class="link-btn"', row)
        # A mail with an unknown tag becomes neither a project nor a case.
        unknown = UnknownTagMail.objects.get(tag="2099-0001")
        other = text[text.index(f'value="{unknown.pk}" form="bulk-form"') :]
        self.assertNotIn("Als Projekt anlegen", other[: other.index("</tr>")])

    def test_several_off_the_list_after_a_confirmation(self) -> None:
        text = self.assert_ok(self.client.get(INQUIRIES))
        self.assertIn('id="bulk-form"', text)
        self.assertIn('data-check-all="items"', text)
        self.assertIn('data-confirm="Die ausgewählten Mails von der Liste nehmen? Sie bleiben im Posteingang."', text)
        self.assertIn("Ausgewählte von der Liste nehmen", text)
        ids = [str(pk) for pk in UnknownTagMail.objects.exclude(pk=self.inquiry.pk).values_list("pk", flat=True)]
        response = self.client.post(
            reverse("mail:unknown_dismiss_many"), {"items": ids, "next": INQUIRIES}, follow=True
        )
        self.assertIn(
            "2 Mails sind von der Liste genommen. Sie liegen weiter im Posteingang.", self.messages_of(response)
        )
        self.assertEqual(list(UnknownTagMail.objects.filter(resolved_at__isnull=True)), [self.inquiry])
        nothing = self.client.post(reverse("mail:unknown_dismiss_many"), {}, follow=True)
        self.assertIn("Hake zuerst die Mails an, die von der Liste sollen.", self.messages_of(nothing))

    def test_one_off_the_list_back_to_the_same_view(self) -> None:
        response = self.client.post(
            reverse("mail:unknown_dismiss", args=[self.inquiry.pk]), {"next": "/projects/inquiries/?sort=subject"}
        )
        self.assertRedirects(response, "/projects/inquiries/?sort=subject", fetch_redirect_response=False)

    def test_suggestions_while_typing(self) -> None:
        make_project("Hoffest")
        found = json.loads(self.client.get(reverse("mail:project_suggestions"), {"q": "musterst"}).content)
        self.assertEqual(
            found,
            [
                {
                    "id": self.project.number,
                    "label": f"{self.project.number} Stadtfest Musterstadt",
                    "hint": self.project.customer.name,
                }
            ],
        )
        by_number = json.loads(self.client.get(reverse("mail:project_suggestions"), {"q": self.project.number}).content)
        self.assertEqual([item["id"] for item in by_number], [self.project.number])
        self.assertEqual(json.loads(self.client.get(reverse("mail:project_suggestions")).content), [])
        crew = self.browser_for("ben", "Crew")
        self.assertEqual(crew.get(reverse("mail:project_suggestions"), {"q": "Stadt"}).status_code, 403)

    def test_taking_over_with_the_suggestion_or_the_typed_text(self) -> None:
        url = reverse("mail:unknown_assign", args=[self.inquiry.pk])
        with mailboxes({self.box.address: FakeMailbox(self.raw)}):
            # Without scripts only the typed text arrives: "2026-0001 Stadtfest" names the project by its first word.
            response = self.client.post(url, {"project_text": f"{self.project.number} Stadtfest", "project_number": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProjectMail.objects.get().project, self.project)


class ProjectFromInquiryPageTests(UiTestCase):
    """PRJ-107: "Als Projekt anlegen" – the project form from the mail; saving takes the mail along."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=True)
        self.customer = make_customer("Stadthalle")
        self.contact = Contact.objects.create(customer=self.customer, name="Max Muster", email="max@stadthalle.example")
        self.raw = make_mail(
            "AW: Angebot Hoffest", message_id="<h@x.example>", sender="Max Muster <max@stadthalle.example>"
        )
        with mailboxes({self.box.address: FakeMailbox(self.raw)}):
            fetch_mail(force=True)
        self.inquiry = UnknownTagMail.objects.get()
        self.url = f"{reverse('projects:create')}?inquiry={self.inquiry.pk}"

    def test_from_the_inquiry_to_the_project(self) -> None:
        page = self.client.get(self.url)
        text = self.assert_ok(page)
        self.assertIn("Aus der Mail „AW: Angebot Hoffest“ von Max Muster &lt;max@stadthalle.example&gt;.", text)
        self.assertIn(f'<input type="hidden" name="inquiry" value="{self.inquiry.pk}">', text)
        data = form_data(page, "name")
        self.assertEqual(
            (data["name"], data["customer"], data["contact"]),
            ("Angebot Hoffest", str(self.customer.pk), str(self.contact.pk)),
        )
        with mailboxes({self.box.address: FakeMailbox(self.raw)}):
            response = self.client.post(self.url, data, follow=True)
        project = Project.objects.get(name="Angebot Hoffest")
        self.assertFalse(project.is_service_case)
        self.assertIn("Die Mail liegt jetzt im Projekt.", self.messages_of(response))
        self.assertEqual(ProjectMail.objects.get().project, project)
        self.inquiry.refresh_from_db()
        self.assertIsNotNone(self.inquiry.resolved_at)

    def test_a_mail_gone_from_the_inbox_creates_no_project(self) -> None:
        data = form_data(self.client.get(self.url), "name")
        with mailboxes({self.box.address: FakeMailbox()}):
            text = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("nicht mehr im Posteingang", text)
        self.assertFalse(Project.objects.filter(name="Angebot Hoffest").exists())

    def test_it_needs_the_right_to_take_mails_over(self) -> None:
        reader = self.browser_for("lea", "Nur-Lesen")
        self.assertIn(reader.get(self.url).status_code, (403, 404))
        self.assertEqual(self.client.get(f"{reverse('projects:create')}?inquiry=999999").status_code, 404)


class MailboxAddressPageTests(UiTestCase):
    """EML-047: the further addresses of a mailbox – list, add, change, remove; EML-006: "only mark as read"."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox()
        self.page = f"/administration/mail/mailboxes/{self.box.pk}/"

    def test_add_change_and_remove(self) -> None:
        text = self.assert_ok(self.client.get(self.page))
        self.assertIn("Weitere Adressen (Aliasse)", text)
        self.assertIn("Keine weiteren Adressen. Alle Mails folgen der Einstellung des Postfachs.", text)
        new = reverse("mail:address_create", args=[self.box.pk])
        self.assertIn(f'href="{new}"', text)
        form = self.assert_ok(self.client.get(new))
        for option in ("nicht übernehmen", "als Anfrage", "gleich als Servicefall anlegen"):
            self.assertIn(option, form)
        self.assertIn('data-show-if="untagged=service_case"', form)
        office = make_user("office")
        data = form_data(
            self.client.get(new),
            "address",
            address="Support@Verleih.example",
            untagged=Untagged.SERVICE_CASE,
            for_service_cases="on",
            case_manager=str(office.pk),
        )
        response = self.client.post(new, data, follow=True)
        self.assertIn("Die Adresse support@verleih.example ist gespeichert.", self.messages_of(response))
        alias = MailboxAddress.objects.get()
        self.assertEqual(
            (alias.address, alias.untagged, alias.for_service_cases, alias.case_manager),
            ("support@verleih.example", "service_case", True, office),
        )
        listed = self.assert_ok(response)
        self.assertIn('Gleich als Servicefall anlegen<div class="muted small">verantwortlich: office</div>', listed)
        self.assertIn("nur für Servicefälle", listed)
        settings_page = self.assert_ok(self.client.get("/administration/mail/"))
        # EML-049: with the moment from which its mails without tag are taken in.
        self.assertIn(
            "support@verleih.example: gleich als Servicefall anlegen ab 01.03.2027 08:00 · nur für Servicefälle",
            settings_page,
        )
        # The same address twice is refused.
        again = self.client.post(new, dict(data, address="support@verleih.example"))
        self.assertIn("Diese Adresse steht schon beim Postfach.", self.assert_ok(again))
        # Changing: as an inquiry; nobody is responsible for cases it no longer makes.
        edit = reverse("mail:address_edit", args=[self.box.pk, alias.pk])
        self.client.post(edit, dict(data, untagged=Untagged.INQUIRY, for_service_cases=""))
        alias.refresh_from_db()
        self.assertEqual((alias.untagged, alias.case_manager, alias.for_service_cases), ("inquiry", None, False))
        delete = reverse("mail:address_delete", args=[self.box.pk, alias.pk])
        self.assertIn(f'action="{delete}"', self.assert_ok(self.client.get(self.page)))
        response = self.client.post(delete, follow=True)
        self.assertIn("Die Adresse support@verleih.example ist nicht mehr in der Liste.", self.messages_of(response))
        self.assertFalse(MailboxAddress.objects.exists())

    def test_only_with_the_right_to_change_mailboxes(self) -> None:
        reader = self.browser_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(reverse("mail:address_create", args=[self.box.pk])).status_code, 403)

    def test_only_mark_as_read(self) -> None:
        text = self.assert_ok(self.client.get(self.page))
        self.assertIn('<option value="read">nur als gelesen markieren</option>', text)
        self.assertIn(
            '<option value="move" selected>als gelesen markieren und in einen Ordner verschieben</option>', text
        )
        data = form_data(self.client.get(self.page), "after_assignment", after_assignment="read", done_folder="")
        self.client.post(self.page, data)
        self.box.refresh_from_db()
        self.assertEqual(self.box.after_assignment, "read")
        self.assertIn("nur als gelesen markieren", self.assert_ok(self.client.get("/administration/mail/")))


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND, EMAIL_INNER_BACKEND=LOG_ONLY_BACKEND)
class NoMailServerPageTests(UiTestCase):
    """EML-048: without a mail server nothing is "gesendet"; the place that sends says so and where to help."""

    def test_the_test_mail_of_the_self_check(self) -> None:
        response = self.client.post("/administration/self-check/", {"action": "test_mail"}, follow=True)
        messages = self.messages_of(response)
        self.assertTrue(
            any(text.startswith("Nicht versendet – kein Mailserver eingerichtet.") for text in messages), messages
        )
        self.assertIn(
            '<a href="/administration/mail/">Einstellungen → Postfächer und Signatur</a>', self.assert_ok(response)
        )
        self.assertEqual(
            MailLogEntry.objects.get().get_result_display(), "nicht versendet – kein Mailserver eingerichtet"
        )
        self.assertIn("Kein Mailserver eingerichtet", self.assert_ok(response))

    def test_an_invitation(self) -> None:
        user = make_user("berta")
        response = self.client.post(reverse("accounts:user_send_invitation", args=[user.pk]), follow=True)
        messages = self.messages_of(response)
        self.assertTrue(any(text.startswith("Nicht versendet") for text in messages), messages)
        self.assertFalse(any("Die Einladung wurde" in text for text in messages), messages)

    def test_settings_and_mail_log_warn(self) -> None:
        self.assertIn(
            "Kein Mailserver eingerichtet: Einladungen, Passwort-Links",
            self.assert_ok(self.client.get("/administration/mail/")),
        )
        log = self.assert_ok(self.client.get("/administration/mail/log/"))
        self.assertIn("Nicht versendet – kein Mailserver eingerichtet.", log)

    def test_a_deployment_request_by_mail(self) -> None:
        """The request mail (PER-032) went nowhere: the planning says so; without a mail due it stays quiet."""
        configure_mailbox()
        project = make_project("Hoffest")
        line = plan(project, "Bühnenbau", make_person("Jörg Müßig", email="joerg@crew.example"))
        url = reverse("projects:crew_request", args=[project.pk, line.pk])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, follow=True)
        messages = self.messages_of(response)
        self.assertIn("Jörg Müßig wurde angefragt.", messages)
        self.assertTrue(
            any(text.startswith("Nicht versendet – kein Mailserver eingerichtet.") for text in messages), messages
        )
        self.assertEqual(MailLogEntry.objects.get().result, "not_sent")
        self.client.get("/")  # the messages of the first request are shown and gone
        quiet = plan(project, "Bühnenbau", make_person("Ida Ohnemail"))
        messages = self.messages_of(
            self.client.post(reverse("projects:crew_request", args=[project.pk, quiet.pk]), follow=True)
        )
        self.assertFalse(any(text.startswith("Nicht versendet") for text in messages), messages)

    @override_settings(EMAIL_INNER_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_with_a_server_no_warning(self) -> None:
        self.assertNotIn("Kein Mailserver eingerichtet", self.assert_ok(self.client.get("/administration/mail/")))
        response = self.client.post("/administration/self-check/", {"action": "test_mail"}, follow=True)
        self.assertIn("Eine Testmail ging an admin@example.de.", self.messages_of(response))
