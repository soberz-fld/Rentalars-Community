# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: crew and customer into "To" with one click (EML-043), and the new mail pages
checked with axe-core (EML-041, EML-042, NFA-025)."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.customers.models import Contact
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import Mailbox
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import make_person, plan
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail


class QuickRecipientsInBrowserTests(BrowserTestCase):
    """EML-043: the buttons add what is not in "To" yet, without loading the page."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.project.contact = Contact.objects.create(
            customer=self.project.customer, name="Anna Muster", email="muster@kunde.example"
        )
        self.project.save()
        plan(self.project, "Tontechnik", make_person("Ben Crew", email="ben@crew.example"))
        plan(self.project, "Licht", make_person("Cleo Crew", email="cleo@crew.example"))

    def test_add_crew_and_customer(self) -> None:
        self.open(f"/projects/{self.project.pk}/mails/new/")
        field = self.page.locator("#id_to")
        status = self.page.locator("[data-recipients-status]")
        # The contact person is in "To" already when the page opens.
        self.assertEqual(field.input_value(), "Anna Muster <muster@kunde.example>")
        self.page.get_by_role("button", name="Kunde hinzufügen").click()
        self.assertEqual(status.inner_text(), "Diese Adressen stehen schon in „An“.")
        self.assertEqual(field.input_value(), "Anna Muster <muster@kunde.example>")

        field.fill("ben@crew.example, ")
        crew = self.page.get_by_role("button", name="Crew hinzufügen")
        crew.click()
        value = field.input_value()
        # The crew of the sample project follows; Ben, typed already, does not come twice.
        self.assertTrue(value.startswith("ben@crew.example, Cleo Crew <cleo@crew.example>, "), value)
        self.assertEqual(value.count("ben@crew.example"), 1)
        self.assertTrue(status.inner_text().startswith("Zu „An“ hinzugefügt: Cleo Crew <cleo@crew.example>"))
        crew.click()
        self.assertEqual((field.input_value(), status.inner_text()), (value, "Diese Adressen stehen schon in „An“."))
        self.page.get_by_role("button", name="Kunde hinzufügen").click()
        self.assertEqual(field.input_value(), f"{value}, Anna Muster <muster@kunde.example>")
        # Nothing was sent or loaded meanwhile.
        self.assertTrue(self.page.url.endswith(f"/projects/{self.project.pk}/mails/new/"))


class MailPagesAccessibilityTests(BrowserTestCase):
    """NFA-025: the pages without a finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def test_mail_pages(self) -> None:
        configure_mailbox()
        add_mailbox("Info", "info@verleih.example", process_untagged=True)
        with mailboxes(
            {
                "projekte@verleih.example": FakeMailbox(make_mail("Frage [RL#2099-0001]")),
                "info@verleih.example": FakeMailbox(make_mail("Anfrage Hochzeit")),
            }
        ):
            fetch_mail(force=True)
        plan(self.project, "Tontechnik", make_person("Ben Crew", email="ben@crew.example"))
        mailbox = Mailbox.objects.get(name="Info")
        findings: list[str] = []
        for path in (
            "/projects/inquiries/",
            "/administration/mail/",
            "/administration/mail/mailboxes/new/",
            f"/administration/mail/mailboxes/{mailbox.pk}/",
            f"/projects/{self.project.pk}/mails/new/",
        ):
            self.open(path)
            self.page.wait_for_load_state("networkidle")
            self.page.add_script_tag(path=str(self.axe))
            result = self.page.evaluate(
                "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
                ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
                WCAG_AA,
            )
            findings += [f"{path}: {finding}" for finding in result]
        self.assertEqual(findings, [], "\n".join(findings))
