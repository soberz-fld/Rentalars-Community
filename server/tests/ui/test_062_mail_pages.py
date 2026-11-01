# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for the mail module.

* EML-041: the mailboxes in the settings – list with roles and state, add,
  change, delete or switch off, check the connection, the rules for all.
* EML-042: the tab "Inquiries" under "Projects" and the navigation without
  the entry "E-mail".
* EML-043: "add crew" and "add customer" next to "To".
"""

from __future__ import annotations

import json
import re
from typing import Any

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.customers.models import Contact
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import AfterAssignment, Mailbox, MailSettings, ProjectMail, UnknownTagMail
from rentalars.projects import services as project_services
from tests.helpers import make_customer, make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, add_mailbox, capture_smtp, configure_mailbox, mailboxes, make_mail
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_051_mail import RecordingSMTP, recording_smtp

SETTINGS = "/administration/mail/"
NEW = "/administration/mail/mailboxes/new/"
INQUIRIES = "/projects/inquiries/"


def page_of(mailbox: Mailbox) -> str:
    return f"/administration/mail/mailboxes/{mailbox.pk}/"


def tabs_of(text: str) -> list[str]:
    """The labels of the tabs of a page."""
    start = text.index('<nav class="tabs"')
    return [label.strip() for label in re.findall(r">([^<>]+)</a>", text[start : text.index("</nav>", start)])]


def navigation_of(text: str) -> list[str]:
    """The labels of the main navigation."""
    start = text.index('<ul class="nav">')
    return [label.strip() for label in re.findall(r"</svg>([^<>]+)</a>", text[start : text.index("</ul>", start)])]


class MailboxListTests(UiTestCase):
    """EML-041: the mailboxes in the settings with their roles and state."""

    def setUp(self) -> None:
        super().setUp()
        self.projects = configure_mailbox()

    def test_the_list_shows_roles_and_state(self) -> None:
        info = add_mailbox("Info", "info@verleih.example", process_untagged=True, after_assignment="keep")
        info.last_error = "Anmeldung abgelehnt"
        info.save()
        add_mailbox("Alt", "alt@verleih.example", is_active=False)
        text = self.assert_ok(self.client.get(SETTINGS))
        table = text[text.index('<table class="table stack mailbox-list">') :]
        rows = {name: table[table.index(f">{name}</a>") :][:1100] for name in ("Projekte", "Info", "Alt")}
        self.assertIn("Korrespondenz", rows["Projekte"])
        self.assertIn("Postausgang", rows["Projekte"])
        self.assertIn("lässt Mails ohne Kennung liegen", rows["Projekte"])
        self.assertIn("<code>Rentalars</code>", rows["Projekte"])
        self.assertNotIn("Postausgang", rows["Info"])
        self.assertIn("übernimmt Mails ohne Kennung · unverändert im Posteingang lassen", rows["Info"])
        self.assertIn('<span class="badge red">Fehler</span> Anmeldung abgelehnt', rows["Info"])
        self.assertIn('<span class="badge">aus</span>', rows["Alt"])
        self.assertIn("Kein Postfach versendet die Systemmails", text)
        self.assertIn(f'href="{NEW}"', text)
        # The box "fetch now" of the old page "E-Mail" lives here (EML-042).
        self.assertIn('action="/administration/mail/fetch/"', text)

    def test_the_rules_for_all_mailboxes(self) -> None:
        data = form_data(self.client.get(SETTINGS), "interval_minutes", interval_minutes="5", retention_days="30")
        response = self.client.post(SETTINGS, data, follow=True)
        self.assertIn("Die Regeln für alle Postfächer wurden gespeichert.", self.messages_of(response))
        rules = MailSettings.load()
        self.assertEqual((rules.interval_minutes, rules.retention_days), (5, 30))

    def test_fetch_now_from_the_settings(self) -> None:
        project = make_project()
        add_mailbox("Info", "info@verleih.example", process_untagged=True)
        boxes = {
            "projekte@verleih.example": FakeMailbox(make_mail(f"Plan [RL#{project.number}]")),
            "info@verleih.example": FakeMailbox(make_mail("Anfrage Hochzeit")),
        }
        with mailboxes(boxes):
            response = self.client.post("/administration/mail/fetch/", {"next": SETTINGS}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], SETTINGS)
        self.assertIn(
            "2 neue Mails angesehen; 1 zugeordnet, 0 mit unbekannter Kennung, 1 Anfragen.",
            self.messages_of(response),
        )

    def test_check_the_connection(self) -> None:
        with mailboxes({"projekte@verleih.example": FakeMailbox()}), recording_smtp():
            response = self.client.post(f"{page_of(self.projects)}check/", {"next": SETTINGS}, follow=True)
        self.assertEqual(
            self.messages_of(response),
            [
                "Projekte – IMAP: Angemeldet; der Ordner „INBOX“ lässt sich öffnen.",
                "Projekte – SMTP: Angemeldet.",
            ],
        )
        self.assertEqual(len(RecordingSMTP.sessions), 1)


class MailboxFormTests(UiTestCase):
    """EML-041: add, change, delete; the roles are checked."""

    def fill(self, url: str, **changes: Any) -> dict[str, Any]:
        defaults = {
            "name": "Info",
            "address": "info@verleih.example",
            "imap_host": "imap.verleih.example",
            "imap_user": "info@verleih.example",
            "imap_password": "info-geheim",
            "smtp_host": "smtp.verleih.example",
        }
        return form_data(self.client.get(url), "imap_host", **{**defaults, **changes})

    def test_the_first_mailbox_fetches_and_sends(self) -> None:
        text = self.assert_ok(self.client.get(NEW))
        data = form_data(self.client.get(NEW), "imap_host")
        self.assertEqual((data.get("for_correspondence"), data.get("is_outgoing")), ("on", "on"))
        self.assertIn('data-show-if="after_assignment=move"', text)
        self.assertIn('data-show-if="for_correspondence=on"', text)
        response = self.client.post(NEW, self.fill(NEW), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], SETTINGS)
        mailbox = Mailbox.objects.get()
        self.assertEqual(
            (mailbox.for_correspondence, mailbox.is_outgoing, mailbox.imap_password), (True, True, "info-geheim")
        )

    def test_a_second_mailbox_takes_the_outgoing_role(self) -> None:
        projects = configure_mailbox()
        data = self.fill(NEW, for_correspondence="on", is_outgoing="on", process_untagged="on")
        self.assertNotIn("is_outgoing", form_data(self.client.get(NEW), "imap_host"))  # not the first one
        response = self.client.post(NEW, data, follow=True)
        self.assertEqual(
            self.messages_of(response),
            ["Das Postfach „Info“ wurde gespeichert.", "Projekte ist nicht mehr Postausgang der Korrespondenz."],
        )
        projects.refresh_from_db()
        info = Mailbox.objects.get(name="Info")
        self.assertEqual((projects.is_outgoing, info.is_outgoing, info.process_untagged), (False, True, True))

    def test_without_a_mailbox_that_sends_the_form_says_so(self) -> None:
        projects = configure_mailbox()
        add_mailbox("Info", "info@verleih.example")
        data = form_data(self.client.get(page_of(projects)), "imap_host")
        data.pop("is_outgoing")
        text = self.assert_ok(self.client.post(page_of(projects), data))
        self.assertIn("Genau ein aktives Postfach der Korrespondenz versendet die Mails", text)
        projects.refresh_from_db()
        self.assertTrue(projects.is_outgoing)

    def test_folder_and_choice_for_assigned_mails(self) -> None:
        projects = configure_mailbox()
        data = form_data(self.client.get(page_of(projects)), "imap_host", after_assignment="move", done_folder="INBOX")
        self.assertIn(
            "Wähle einen anderen Ordner als den Posteingang.", self.assert_ok(self.client.post(page_of(projects), data))
        )
        data.update(after_assignment="delete")
        self.client.post(page_of(projects), data)
        projects.refresh_from_db()
        self.assertEqual(projects.after_assignment, AfterAssignment.DELETE)

    def test_delete_or_switch_off(self) -> None:
        """EML-046: deleting asks first and deletes also a mailbox with mails; switching off stays."""
        projects = configure_mailbox()
        unused = add_mailbox("Alt", "alt@verleih.example")
        response = self.client.post(f"{page_of(unused)}delete/", follow=True)
        self.assertIn("Das Postfach „Alt“ wurde gelöscht.", self.messages_of(response))
        self.assertFalse(Mailbox.objects.filter(name="Alt").exists())

        project = make_project()
        with capture_smtp():
            from rentalars.mail.sending import send_project_mail

            send_project_mail(project, to="a@b.example", subject="x", body="y", user=None)
        self.assertIn(f'href="{page_of(projects)}delete/"', self.assert_ok(self.client.get(page_of(projects))))
        response = self.client.post(f"{page_of(projects)}delete/", {"action": "switch_off"}, follow=True)
        self.assertIn("Das Postfach „Projekte“ wurde ausgeschaltet.", self.messages_of(response))
        projects.refresh_from_db()
        self.assertFalse(projects.is_active)
        response = self.client.post(f"{page_of(projects)}delete/", follow=True)
        self.assertIn("Das Postfach „Projekte“ wurde gelöscht.", self.messages_of(response))
        mail = ProjectMail.objects.get()
        self.assertEqual((mail.mailbox, mail.mailbox_name), (None, "Projekte"))

    def test_rights(self) -> None:
        projects = configure_mailbox()
        manager = self.browser_for("paula", "Projektleitung")  # writes the module E-mail, may not delete
        text = self.assert_ok(manager.get(page_of(projects)))
        self.assertNotIn("/delete/", text)
        self.assertEqual(manager.post(f"{page_of(projects)}delete/").status_code, 403)
        self.assertEqual(self.browser_for("lea", "Nur-Lesen").get(NEW).status_code, 403)
        self.assertEqual(self.browser_for("lea2", "Nur-Lesen").post(f"{page_of(projects)}check/").status_code, 403)
        self.assertNotIn("info-geheim", text)


class InquiriesTabTests(UiTestCase):
    """EML-042: the inquiries are a tab of "Projects"; the entry "E-mail" is gone."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        add_mailbox("Info", "info@verleih.example", process_untagged=True)
        boxes = {
            "projekte@verleih.example": FakeMailbox(make_mail("Frage [RL#2099-0001]", message_id="<u1@x.example>")),
            "info@verleih.example": FakeMailbox(make_mail("Anfrage Hochzeit", message_id="<h@x.example>")),
        }
        with mailboxes(boxes):
            fetch_mail(force=True)

    def test_the_tab_under_projects(self) -> None:
        text = self.assert_ok(self.client.get(INQUIRIES))
        # PRJ-090; "Monatsabrechnung" (DOK-016) is in "Buchhaltung" (tests/unit/test_091_accounting.py).
        self.assertEqual(tabs_of(text), ["Projekte", "Offene Punkte", "Servicefälle", "Anfragen"])
        self.assertIn('<a href="/projects/inquiries/" aria-current="page">Anfragen</a>', text)
        self.assertIn("<h1>Projekte</h1>", text)
        self.assertIn('<a href="/projects/" aria-current="page">', text)  # the entry "Projekte" is marked
        self.assertNotIn('class="back-link', text)  # a tab is a start page
        self.assertNotIn("E-Mail", navigation_of(text))
        # The box "Abruf" went into the settings (EML-042).
        self.assertNotIn("Jetzt abrufen", text)
        self.assertNotIn('action="/administration/mail/fetch/"', text)
        # Both kinds of waiting mails, each with its mailbox.
        self.assertIn("<code>2099-0001</code>", text)
        self.assertIn('<span class="badge accent">ohne Kennung</span>', text)
        self.assertIn("Anfrage Hochzeit", text)
        self.assertIn(">Info</td>", text)
        self.assertIn("und die Mails ohne Kennung", text)

    def test_the_other_tabs_lead_here(self) -> None:
        for url in ("/projects/", "/projects/open-items/"):
            with self.subTest(url=url):
                text = self.assert_ok(self.client.get(url))
                # PRJ-090; DOK-019: "Monatsabrechnung" (DOK-016) is a tab of "Buchhaltung" now.
                self.assertEqual(tabs_of(text), ["Projekte", "Offene Punkte", "Servicefälle", "Anfragen"])
        warehouse = self.browser_for("luka", "Lager")  # projects, but not the module E-mail
        text = self.assert_ok(warehouse.get("/projects/"))
        self.assertEqual(tabs_of(text), ["Projekte", "Offene Punkte", "Servicefälle"])  # PRJ-090
        self.assertEqual(warehouse.get(INQUIRIES).status_code, 403)

    def test_e_mail_without_projects_still_reaches_the_inquiries(self) -> None:
        role = Role.objects.create(
            name="Posteingang", module_levels={Module.EMAIL: int(Level.WRITE)}, special_rights=[]
        )
        user = make_user("mia")
        user.roles.set([role])
        browser = self.browser_of(user)
        text = self.assert_ok(browser.get(INQUIRIES))
        self.assertEqual(tabs_of(text), ["Anfragen"])
        self.assertIn('<a href="/projects/inquiries/" aria-current="page">', text)
        self.assertEqual(navigation_of(text)[0], "Projekte")

    def test_take_over_an_inquiry(self) -> None:
        project = make_project()
        inquiry = UnknownTagMail.objects.get(tag="")
        with mailboxes(
            {
                "projekte@verleih.example": FakeMailbox(),
                "info@verleih.example": FakeMailbox(make_mail("Anfrage Hochzeit", message_id="<h@x.example>")),
            }
        ) as boxes:
            response = self.client.post(
                f"/projects/inquiries/{inquiry.pk}/assign/", {"project_number": project.number}, follow=True
            )
        mail = ProjectMail.objects.get()
        self.assertEqual(response.redirect_chain[-1][0], f"/projects/{project.number}/mails/{mail.pk}/")
        self.assertEqual(boxes["info@verleih.example"].inbox, {})
        self.assertEqual(mail.mailbox.name, "Info")

    def test_the_start_page_counts_and_names_problems(self) -> None:
        Mailbox.objects.filter(name="Info").update(last_error="Anmeldung abgelehnt")
        text = self.assert_ok(self.client.get("/"))
        self.assertIn("2 Anfragen oder Mails mit unbekannter Kennung warten auf ein Projekt.", text)
        self.assertIn("Mails von „Info“ können nicht abgerufen werden: Anmeldung abgelehnt", text)

    def test_the_mail_log_names_the_mailbox(self) -> None:
        text = self.assert_ok(self.client.get("/administration/mail/log/"))
        self.assertIn('data-label="Postfach">Info</td>', text)
        self.assertIn('data-label="Postfach">Projekte</td>', text)
        self.assertIn("Anfrage", text)


class QuickRecipientsPageTests(UiTestCase):
    """EML-043: "add crew" and "add customer" next to "To"."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        customer = make_customer("Stadtwerke")
        customer.email = "info@stadtwerke.example"
        customer.save()
        self.project = make_project(customer=customer)
        self.anna = make_person("Anna Becker", email="anna@crew.example")
        self.tom = make_person("Tom Richter", email="tom@crew.example", share_email=True)
        plan(self.project, "Tontechnik", self.anna)
        plan(self.project, "Licht", self.tom)

    def buttons(self, text: str) -> dict[str, list[str]]:
        found = re.findall(
            r'<button type="button"[^>]*data-add-recipients="([^"]*)"[^>]*>.*?</svg>([^<]+)</button>', text
        )
        return {
            label: json.loads(data.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
            for data, label in found
        }

    def test_both_buttons_with_their_addresses(self) -> None:
        text = self.assert_ok(self.client.get(f"/projects/{self.project.pk}/mails/new/"))
        self.assertIn('data-quick-recipients="id_to"', text)
        self.assertIn('role="status"', text)
        self.assertIn('aria-controls="id_to"', text)
        self.assertEqual(
            self.buttons(text),
            {
                "Crew hinzufügen": ["Anna Becker <anna@crew.example>", "Tom Richter <tom@crew.example>"],
                "Kunde hinzufügen": ["Stadtwerke <info@stadtwerke.example>"],
            },
        )
        self.assertIn('data-text-added="Zu „An“ hinzugefügt:"', text)

    def test_the_contact_person_and_the_privacy_of_the_crew(self) -> None:
        contact = Contact.objects.create(
            customer=self.project.customer, name="Anna Muster", email="muster@stadtwerke.example"
        )
        self.project.contact = contact
        self.project.save()
        role = Role.objects.create(
            name="Schreibt Projekte an",
            module_levels={Module.PROJECTS: int(Level.READ)},
            special_rights=[SpecialRight.CORRESPONDENCE_READ, SpecialRight.CORRESPONDENCE_WRITE],
        )
        user = make_user("olaf")
        user.roles.set([role])
        text = self.assert_ok(self.browser_of(user).get(f"/projects/{self.project.pk}/mails/new/"))
        self.assertEqual(
            self.buttons(text),
            {
                # PER-019: without edit access or the personnel only who released the address.
                "Crew hinzufügen": ["Tom Richter <tom@crew.example>"],
                "Kunde hinzufügen": ["Anna Muster <muster@stadtwerke.example>"],
            },
        )

    def test_a_whole_project_and_its_part(self) -> None:
        part = project_services.create_subproject(self.project, name="Bühne 2")
        lea = make_person("Lea Sommer", email="lea@crew.example")
        plan(part, "Licht", lea)
        whole = self.buttons(self.assert_ok(self.client.get(f"/projects/{self.project.pk}/mails/new/")))
        self.assertIn("Lea Sommer <lea@crew.example>", whole["Crew hinzufügen"])
        only_part = self.buttons(self.assert_ok(self.client.get(f"/projects/{part.pk}/mails/new/")))
        self.assertEqual(only_part["Crew hinzufügen"], ["Lea Sommer <lea@crew.example>"])

    def test_no_buttons_without_addresses(self) -> None:
        empty = make_project("Leer", customer=make_customer("Ohne Adresse"))
        text = self.assert_ok(self.client.get(f"/projects/{empty.pk}/mails/new/"))
        self.assertNotIn("data-quick-recipients", text)
