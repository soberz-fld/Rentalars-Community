# SPDX-License-Identifier: GPL-3.0-or-later
"""The company in front of the project in mails with a block of facts. (PER-016)

The requirement: mails such as deployment requests show a line with the company name before the project.

The mails Rentalars sends with a block "Project: … / As: … / When: …" are the deployment requests (``mail/email/
crew_request.txt`` and ``.html``, also when asked again for new times, PER-034). Their block starts with the name of the
company of the installation (ADM-001), as the documents and the footer of the mails have it, then the project.
No other mail lists the project like this: the notifications carry the project in their title, the mails of the
correspondence are written by people, and the entries of the calendars (``Project: …`` in the description of an
event) are no mails.
"""

from __future__ import annotations

from django.core import mail as django_mail

from rentalars.core.models import CompanyProfile
from tests.helpers import make_person, make_user, plan
from tests.unit.test_063_crewmail import CrewMailTestCase


class CompanyLineTests(CrewMailTestCase):
    """The block of the request mail, text and HTML, German and English."""

    def setUp(self) -> None:
        super().setUp()
        company = CompanyProfile.load()
        company.name = "Licht & Ton GmbH"
        company.save()

    def mail(self) -> tuple[str, str]:
        self.assertTrue(self.ask())
        message = self.request_message()
        return message.body, message.alternatives[0][0]

    def test_the_text_names_the_company_before_the_project(self) -> None:
        text, _html = self.mail()
        self.assertIn("Firma: Licht & Ton GmbH\nProjekt: ", text)
        self.assertLess(text.index("Firma:"), text.index("Projekt:"))
        self.assertLess(text.index("Projekt:"), text.index("Als:"))

    def test_the_html_names_the_company_before_the_project(self) -> None:
        _text, html = self.mail()
        company = html.index(">Firma</th><td")
        self.assertIn("Licht &amp; Ton GmbH</td>", html[company:])  # escaped, not as markup
        self.assertLess(company, html.index(">Projekt</th>"))
        self.assertLess(html.index(">Projekt</th>"), html.index(">Als</th>"))

    def test_asked_again_for_new_times_has_it_too(self) -> None:
        self.ask()
        self.line.start = self.line.start.replace(hour=9)
        self.line.save()
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            from rentalars.projects import crew

            crew.request_deployment(self.line, user=self.manager)
        text = self.request_message().body
        self.assertIn("Firma: Licht & Ton GmbH\nProjekt: ", text)
        self.assertIn("Neue Zeiten: ", text)

    def test_english(self) -> None:
        user = make_user("ben", roles=("Crew",))
        user.language = "en"
        user.save()
        person = make_person("Ben Meyer", email="ben@crew.example", user=user)
        line = plan(self.project, "Tontechnik", person)
        self.assertTrue(self.ask(line))
        message = self.request_message()
        self.assertIn("Company: Licht & Ton GmbH\nProject: ", message.body)
        html = message.alternatives[0][0]
        self.assertLess(html.index(">Company</th>"), html.index(">Project</th>"))

    def test_without_a_company_name_no_empty_line(self) -> None:
        company = CompanyProfile.load()
        company.name = ""
        company.save()
        text, html = self.mail()
        self.assertNotIn("Firma", text)
        self.assertNotIn(">Firma</th>", html)
        self.assertTrue(text.index("Hallo Anna,") < text.index("Projekt:"))
