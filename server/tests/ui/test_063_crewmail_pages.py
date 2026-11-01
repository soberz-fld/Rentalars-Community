# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages: answering a deployment request by reply mail (PER-032).

* Einstellungen → Firmendaten und Grundeinstellungen (ADM-015): the setting "Antwort auf Einsatzanfragen" with its explanation and
  the mailbox the answers go to.
* Asking from the planning page: the request mail with the two ``mailto:``
  links, properly encoded with umlauts.
* An answer by mail in the mail log and in the history of the project.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from django.core import mail as django_mail

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module
from rentalars.mail.models import CrewAnswerMode, CrewRequestMail, MailSettings
from rentalars.projects import crew
from rentalars.projects.models import RequestStatus
from tests.helpers import make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_063_crewmail import answer_mail, mailto_links

#: ADM-015: the setting is under Einstellungen → Firmendaten und Grundeinstellungen.
SETTINGS = "/administration/settings/"
MAIL_SETTINGS = "/administration/mail/"


def crew_answer_block(text: str) -> str:
    """The part of the settings page about answers to deployment requests."""
    start = text.index('id="crew-answers"')
    return text[start : text.index("</fieldset>", start)]


class CrewAnswerSettingTests(UiTestCase):
    """PER-032, ADM-015: the setting under Firmendaten und Grundeinstellungen, with when to choose it."""

    def test_the_setting_with_its_explanation_and_mailbox(self) -> None:
        configure_mailbox()
        block = crew_answer_block(self.assert_ok(self.client.get(SETTINGS)))
        # UIX-051: the group of radio buttons is required and carries the red asterisk at its legend.
        self.assertIn(
            '<legend>Antwort auf Einsatzanfragen <span class="required" aria-hidden="true">*</span></legend>', block
        )
        labels = re.findall(r'<label for="id_system-crew_answers_\d">([^<]+)</label>', block)
        self.assertEqual(labels, ["Über den Link im Browser", "Per Antwort-Mail", "Beides"])
        self.assertRegex(block, r'<input type="radio" name="system-crew_answers" value="both"[^>]*checked')
        self.assertIn("wenn der Server aus dem Internet nicht erreichbar ist", block)
        self.assertIn("Antworten per Mail gehen an projekte@verleih.example – das Postfach „Projekte“", block)

    def test_saving_the_setting(self) -> None:
        configure_mailbox()
        data = form_data(self.client.get(SETTINGS), "system-crew_answers", **{"system-crew_answers": "mail"})
        response = self.client.post(SETTINGS, data, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.MAIL)
        self.assertRegex(
            crew_answer_block(self.assert_ok(response)),
            r'<input type="radio" name="system-crew_answers" value="mail"[^>]*checked',
        )

    def test_an_unknown_choice_is_refused(self) -> None:
        configure_mailbox()
        data = form_data(self.client.get(SETTINGS), "system-crew_answers", **{"system-crew_answers": "fax"})
        response = self.client.post(SETTINGS, data)
        self.assertIn("has-error", crew_answer_block(self.assert_ok(response)))
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.BOTH)

    def test_without_a_mailbox_that_is_fetched_only_the_link(self) -> None:
        block = crew_answer_block(self.assert_ok(self.client.get(SETTINGS)))
        self.assertIn("Noch kann kein Postfach, das Rentalars abruft, die Antworten annehmen", block)

    def test_only_who_may_change_the_settings_changes_it(self) -> None:
        """ADM-015: like every setting of the page, with write access to the settings."""
        configure_mailbox()
        role = Role.objects.create(name="Büro", module_levels={Module.ADMINISTRATION: Level.READ})
        office = make_user("buero")
        office.roles.add(role)
        browser = self.browser_of(office)
        self.assertNotIn("Einstellungen speichern", self.assert_ok(browser.get(SETTINGS)))
        response = browser.post(SETTINGS, {"form": "system", "system-crew_answers": "link"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.BOTH)

    def test_the_mail_page_points_to_it(self) -> None:
        """ADM-015: the page of the mailboxes no longer offers the choice; it names it and links to it."""
        configure_mailbox()
        rules = MailSettings.load()
        rules.crew_answers = CrewAnswerMode.MAIL
        rules.save()
        text = self.assert_ok(self.client.get(MAIL_SETTINGS))
        self.assertNotIn('name="crew_answers"', text)
        self.assertIn("Antwort auf Einsatzanfragen: „Per Antwort-Mail“.", text)
        self.assertIn('href="/administration/settings/#crew-answers"', text)


class RequestMailFromThePlanningTests(UiTestCase):
    """PER-032: asking from the planning page sends the request with the buttons; umlauts encoded in the links."""

    def test_ask_from_the_planning_page(self) -> None:
        configure_mailbox()
        project = make_project("Hoffest Jülich")
        person = make_person("Jörg Müßig", email="joerg@crew.example")
        line = plan(project, "Bühnenbau", person)
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.htmx("post", f"/projects/{project.pk}/crew/{line.pk}/request/")
        self.assertEqual(response.status_code, 200)
        line.refresh_from_db()
        self.assertEqual(line.request_status, RequestStatus.REQUESTED)
        (message,) = django_mail.outbox
        token = CrewRequestMail.objects.get().token
        links = mailto_links(message)
        accept = links["Zusagen"]
        # RFC 6068: UTF-8 percent-encoded, %20 for spaces, nothing left unencoded that a mail program could misread.
        self.assertRegex(
            accept, r"^mailto:projekte@verleih\.example\?subject=[A-Za-z0-9%._~-]+&body=[A-Za-z0-9%._~-]+$"
        )
        self.assertIn("Hoffest%20J%C3%BClich", accept)
        self.assertIn("B%C3%BChnenbau", accept)
        query = parse_qs(urlsplit(accept).query)
        self.assertTrue(query["subject"][0].startswith("Zusage: Hoffest Jülich, Mi 10.03. "))
        self.assertTrue(query["subject"][0].endswith(f"[RA-E-{token}-JA]"))
        self.assertIn("Zusage für: ", query["body"][0])
        self.assertIn("Bühnenbau", query["body"][0])
        self.assertTrue(urlsplit(links["Absagen"]).query.startswith("subject=Absage%3A%20Hoffest%20J%C3%BClich"))
        # In the HTML the link stands as an attribute: "&" escaped, the rest as it is.
        self.assertIn(f"{accept.split('&body=')[0]}&amp;body=", message.alternatives[0][0])
        self.assertIn("Hallo Jörg,", message.body)


class AnswerInLogAndHistoryTests(UiTestCase):
    """PER-032: an answer by mail shows in the mail log with its kind, and in the history of the project."""

    def test_log_and_history(self) -> None:
        mailbox = configure_mailbox()
        manager = make_user("paula", roles=("Projektleitung",))
        project = make_project(manager=manager)
        person = make_person("Anna Becker", email="anna@crew.example")
        line = plan(project, "Tontechnik", person)
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            crew.request_deployment(line, user=manager)
        request: Any = django_mail.outbox[0]
        with (
            self.captureOnCommitCallbacks(execute=True),
            mailboxes({mailbox.address: FakeMailbox(answer_mail(request, accept=False, note="Urlaub"))}),
        ):
            response = self.client.post("/administration/mail/fetch/", {"next": SETTINGS}, follow=True)
        self.assertIn("1 Antwort auf eine Einsatzanfrage per Mail.", self.messages_of(response))
        line.refresh_from_db()
        self.assertEqual((line.request_status, line.answer_note), (RequestStatus.DECLINED, "Urlaub"))

        log = self.assert_ok(self.client.get("/administration/mail/log/?result=crew_answer"))
        self.assertIn("Antwort auf Einsatzanfrage", log)
        self.assertIn("Absage", log)
        self.assertIn(project.number, log)
        self.assertIn('<option value="crew_answer" selected>Antwort auf Einsatzanfrage</option>', log)

        history = self.assert_ok(self.client.get(f"/projects/{project.pk}/history/"))
        self.assertIn("Antwort von Anna Becker kam per Antwort-Mail", history)

    def test_an_answer_not_taken_over_shows_why(self) -> None:
        mailbox = configure_mailbox()
        project = make_project()
        line = plan(project, "Tontechnik", make_person("Anna Becker", email="anna@crew.example"))
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            crew.request_deployment(line, user=None)
        request: Any = django_mail.outbox[0]
        crew.answer_deployment(line, accept=True, user=None)
        with mailboxes({mailbox.address: FakeMailbox(answer_mail(request))}):
            self.client.post("/administration/mail/fetch/", {"next": SETTINGS})
        log = self.assert_ok(self.client.get("/administration/mail/log/"))
        self.assertIn("Zusage – nicht übernommen: schon beantwortet", log)
        self.assertIn('badge yellow">Antwort auf Einsatzanfrage', log)
