# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the setting "Antwort auf Einsatzanfragen" (PER-032).

Under Einstellungen → Firmendaten und Grundeinstellungen (ADM-015).

Chosen and saved like a person would, on a phone without horizontal scrolling, and checked with axe-core
(NFA-025).
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.mail.models import CrewAnswerMode, MailSettings
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.mailbox import configure_mailbox

SETTINGS = "/administration/settings/"


class CrewAnswerSettingInBrowserTests(BrowserTestCase):
    """PER-032, ADM-015: the three choices with their explanation; saved with the other settings."""

    bypass_csp = True

    def test_choose_and_save(self) -> None:
        configure_mailbox()
        self.open(SETTINGS)
        group = self.page.get_by_role("group", name="Antwort auf Einsatzanfragen")
        self.assertTrue(group.get_by_role("radio", name="Beides").is_checked())
        self.assertIn("Antworten per Mail gehen an projekte@verleih.example", group.inner_text())
        group.get_by_role("radio", name="Per Antwort-Mail").check()
        # The page has more than one form with this button (the accounting box has its own); take that of the group.
        self.page.locator("form", has=group).get_by_role("button", name="Einstellungen speichern").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.MAIL)
        group = self.page.get_by_role("group", name="Antwort auf Einsatzanfragen")
        self.assertTrue(group.get_by_role("radio", name="Per Antwort-Mail").is_checked())

    def test_on_a_phone_and_with_axe(self) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(SETTINGS)
        self.page.wait_for_load_state("networkidle")
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))
