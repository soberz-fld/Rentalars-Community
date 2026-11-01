# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "mail", in the browser: Projekte → Anfragen with the project number suggested while typing, the
trash-can button and several mails off the list (PRJ-107); the further addresses of a mailbox (EML-047) – and
axe-core on all of them, on a wide screen and on a phone."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import MailboxAddress, ProjectMail, UnknownTagMail
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes, make_mail


class MailInBrowserTests(BrowserTestCase):
    """PRJ-107, EML-047 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=True)
        self.raw = make_mail("Angebot Bühne", message_id="<a081@x.example>")
        mails = [self.raw, make_mail("Frage Pult", message_id="<b081@x.example>"), make_mail("Frage Kabel")]
        with mailboxes({self.box.address: FakeMailbox(*mails)}):
            fetch_mail(force=True)

    def axe_findings(self, within: str = "") -> list[str]:
        """What axe-core finds on the page, or only within the elements a selector names."""
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running')")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run(within ? {include: [[within]]} : document,"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )

    def both_themes(self, within: str = "") -> list[str]:
        """axe-core in the dark theme and – after switching, on the page's own content – in the light one."""
        findings = self.axe_findings(within)
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
        findings += [f"light: {finding}" for finding in self.axe_findings(within or "main")]
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        return findings

    def row_of(self, subject: str) -> object:
        return self.page.locator("table.inquiry-list tbody tr", has_text=subject)

    def test_take_over_with_a_suggestion(self) -> None:
        """PRJ-107: typing a part of the name suggests the project; Enter chooses it, "Übernehmen" takes the mail."""
        self.open("/projects/inquiries/")
        self.assertEqual(self.both_themes(), [])
        row = self.row_of("Angebot Bühne")
        field = row.locator("input[data-typeahead-input]")
        field.click()
        field.press_sequentially("Hauptbüh", delay=20)
        option = row.locator("[role=option]").first
        option.wait_for()
        self.assertIn(self.project.number, option.inner_text())
        self.assertEqual(self.axe_findings("table.inquiry-list"), [])
        field.press("Enter")
        self.assertEqual(row.locator("input[name=project_number]").input_value(), self.project.number)
        with mailboxes({self.box.address: FakeMailbox(self.raw)}):
            row.locator("button", has_text="Übernehmen").click()
            self.page.wait_for_load_state("networkidle")
        self.assertEqual(ProjectMail.objects.get().project, self.project)

    def test_trash_can_and_several_off_the_list(self) -> None:
        """PRJ-107: the trash-can button names itself on focus; ticked mails go off the list after a question."""
        self.open("/projects/inquiries/")
        button = self.row_of("Frage Kabel").locator("button.icon-btn")
        button.focus()
        self.page.keyboard.press("Shift+Tab")
        self.page.keyboard.press("Tab")
        self.assertTrue(button.locator(".visually-hidden").is_visible())
        self.assertEqual(self.axe_findings("table.inquiry-list"), [])
        button.click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(UnknownTagMail.objects.filter(resolved_at__isnull=True).count(), 2)
        self.row_of("Angebot Bühne").locator("input[name=items]").check()
        self.row_of("Frage Pult").locator("input[name=items]").check()
        self.assertEqual(self.text_of("[data-chosen-count=items]"), "2")
        self.page.locator("#bulk-form button", has_text="Ausgewählte von der Liste nehmen").click()
        self.confirm()
        self.page.locator(".messages", has_text="2 Mails sind von der Liste genommen.").wait_for()
        self.assertFalse(UnknownTagMail.objects.filter(resolved_at__isnull=True).exists())
        self.assertEqual(self.both_themes(), [])

    def test_the_further_addresses_of_a_mailbox(self) -> None:
        """EML-047: add an address that makes service cases; the responsible person shows only with that choice."""
        self.open(f"/administration/mail/mailboxes/{self.box.pk}/")
        self.assertEqual(self.both_themes("#addresses"), [])
        self.page.locator("#addresses a.btn", has_text="Adresse hinzufügen").click()
        self.page.wait_for_url("**/addresses/new/")
        self.page.fill("#id_address", "support@verleih.example")
        manager = self.page.locator("#id_case_manager")
        self.assertFalse(manager.is_visible())
        self.page.select_option("#id_untagged", "service_case")
        self.assertTrue(manager.is_visible())
        self.page.select_option("#id_case_manager", label="anna")
        self.assertEqual(self.both_themes(), [])
        self.page.locator("form.form button[type=submit]").click()
        self.page.wait_for_url("**/mailboxes/*/#addresses")
        alias = MailboxAddress.objects.get()
        self.assertEqual(
            (alias.address, alias.untagged, alias.case_manager.username),
            ("support@verleih.example", "service_case", "anna"),
        )
        self.assertEqual(self.both_themes("#addresses"), [])


class MailOnAPhoneTests(MailInBrowserTests):
    """The same on a phone: the table turns into cards, the actions stay usable."""

    viewport = {"width": 360, "height": 740}
