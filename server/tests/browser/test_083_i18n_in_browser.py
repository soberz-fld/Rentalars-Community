# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "i18n", in a real browser: switching to English, the British dates of the pickers and the manual
(UIX-029), with axe-core on a desk and on a phone.
"""

from __future__ import annotations

import re

from rentalars.accounts.models import User
from tests.browser.test_081_ui_in_browser import UiInBrowserCase


class EnglishInBrowserTests(UiInBrowserCase):
    """UIX-029: the own language on "My account"; then everything is English and British."""

    def switch_to_english(self) -> None:
        self.open("/account/")
        self.page.select_option("#id_language-language", "en")
        self.page.locator("#language button[type=submit]").click()
        self.page.wait_for_load_state("networkidle")

    def test_switch_and_axe(self) -> None:
        self.switch_to_english()
        self.assertEqual(self.page.get_attribute("html", "lang"), "en-GB")
        self.assertEqual(self.page.locator("h1").first.inner_text(), "My account")
        self.assertIn("The language was changed.", self.page.inner_text("main"))
        self.assertEqual(User.objects.get(username="anna").language, "en")
        self.axe()

    def test_the_date_picker_writes_day_before_month(self) -> None:
        self.switch_to_english()
        self.open("/projects/new/")
        field = self.page.locator("input[type=datetime-local]").first
        field.fill("2027-03-10T08:00")
        self.page.locator(".dt-wrap:has(input[type=datetime-local]) button.dt-btn").first.click()
        dialog = self.page.locator("dialog.dt-picker[open]")
        dialog.wait_for()
        text = dialog.inner_text()
        self.assertIn("March 2027", text)
        # The days of the calendar are read out the British way: "Wed, 10/03/2027" – day before month.
        self.assertGreater(dialog.locator('[aria-label*="10/03/2027"]').count(), 0)
        self.assertEqual(dialog.locator('[aria-label*="03/10/2027"]').count(), 0)
        self.axe()
        self.page.keyboard.press("Escape")

    def test_the_manual_on_a_phone(self) -> None:
        user = User.objects.get(username="anna")
        user.language = "en"
        user.save()
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.open("/manual/")
        self.assertEqual(self.page.locator("h1").first.inner_text(), "Manual")
        # Manual chapters: the contents page lists the chapters; a chapter has its sections beside it.
        self.assertEqual(self.page.locator(".manual-chapter-link").count(), 18)
        self.page.locator(".manual-chapter-link").nth(3).click()
        self.page.wait_for_url("**/manual/4/")
        self.assertTrue(self.page.locator(".manual-toc a").count() > 10)
        first = self.page.locator(".manual-toc ol ol a").first
        target = first.get_attribute("href")
        first.click()
        self.assertTrue(re.search(r"#.+", self.page.url))
        self.assertTrue(self.page.locator(f'[id="{target[1:]}"]').is_visible())
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.axe()
