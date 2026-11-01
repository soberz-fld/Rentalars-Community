# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the page of a contact – own greeting only on demand, the preview follows the typing, and
the page passes axe-core (KND-004, NFA-025)."""

from __future__ import annotations

from unittest import SkipTest

from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class ContactGreetingInBrowserTests(BrowserTestCase):
    """KND-004: salutation, first and last name, and the greeting of mails with its preview."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def test_the_preview_follows_the_form(self) -> None:
        self.open(f"/customers/{self.project.customer_id}/contacts/new/")
        text = self.page.locator("#id_greeting_text")
        preview = self.page.locator("#greeting-preview")
        self.assertFalse(text.is_visible())  # only for "Eigene Anrede"
        self.page.locator("#id_salutation").fill("Frau")
        self.page.locator("#id_last_name").fill("Berg")
        self.page.wait_for_function("document.querySelector('#greeting-preview').innerText.includes('Berg')")
        self.assertEqual(preview.inner_text(), "Vorschau: Sehr geehrte Frau Berg,")
        self.page.locator("#id_first_name").fill("Anna")
        self.page.locator("#id_greeting_style").select_option("personal")
        self.page.wait_for_function("document.querySelector('#greeting-preview').innerText.includes('Hallo')")
        self.assertEqual(preview.inner_text(), "Vorschau: Hallo Anna,")
        self.page.locator("#id_greeting_style").select_option("custom")
        self.assertTrue(text.is_visible())
        text.fill("Liebe Anna,")
        self.page.wait_for_function("document.querySelector('#greeting-preview').innerText.includes('Liebe')")
        self.assertEqual(preview.inner_text(), "Vorschau: Liebe Anna,")
        self.page.get_by_role("button", name="Ansprechpartner speichern").click()
        self.page.wait_for_url(f"**/customers/{self.project.customer_id}/")
        self.assertIn("Anna Berg", self.page.content())
        self.assertIn("Liebe Anna,", self.page.content())

    def test_the_page_passes_axe(self) -> None:
        self.open(f"/customers/{self.project.customer_id}/contacts/new/")
        self.page.wait_for_load_state("networkidle")
        self.page.add_script_tag(path=str(self.axe))
        result = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(result, [], "\n".join(result))
