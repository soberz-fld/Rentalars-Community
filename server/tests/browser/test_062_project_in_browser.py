# SPDX-License-Identifier: GPL-3.0-or-later
"""The head of a project in a real browser (PRJ-078) and the tab "Documents" with the files (PRJ-079)."""

from __future__ import annotations

from rentalars.projects.models import ProjectStatus
from tests.browser.base import BrowserTestCase


class HeadActionsInBrowserTests(BrowserTestCase):
    """PRJ-078: the status as a list, the next document with the others behind the arrow."""

    def test_the_status_is_chosen_from_a_list_and_the_tab_stays(self) -> None:
        self.open(f"/projects/{self.project.pk}/documents/")
        button = self.page.locator(".status-form button[type=submit]")
        self.assertTrue(button.is_disabled())  # nothing chosen yet
        self.page.select_option("#status-choice", ProjectStatus.OPTION)
        self.assertFalse(button.is_disabled())
        button.click()
        self.page.wait_for_load_state()
        self.assertIn("/documents/", self.page.url)
        self.assertIn("Status geändert auf „Option“.", self.text_of(".messages"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.OPTION)

    def test_cancelling_asks_first(self) -> None:
        self.open_planning()
        self.page.select_option("#status-choice", ProjectStatus.CANCELLED)
        self.page.click(".status-form button[type=submit]")
        question = self.page.locator("dialog.confirm[open]")
        question.wait_for()
        self.assertIn("stornieren", question.inner_text())
        question.locator(".dialog-foot button").first.click()  # no
        question.wait_for(state="detached")
        self.project.refresh_from_db()
        self.assertNotEqual(self.project.status, ProjectStatus.CANCELLED)

    def test_the_other_documents_behind_the_arrow(self) -> None:
        self.open_planning()
        # "Teilprojekt anlegen" has an arrow of its own (PRJ-050); this is the one of the documents.
        button = self.page.locator(".split-button").filter(has_text="Angebot")
        menu = button.locator(".menu-list")
        self.assertFalse(menu.is_visible())
        button.locator("summary").click()
        self.assertTrue(menu.is_visible())
        self.page.keyboard.press("Escape")
        self.assertFalse(menu.is_visible())
        button.locator("summary").click()
        self.page.click("h1")  # somewhere else
        self.assertFalse(menu.is_visible())
        button.locator("summary").click()
        menu.get_by_text("Lieferschein").click()
        self.page.wait_for_url("**/documents/?kind=delivery_note#make-document")
        self.assertEqual(self.page.input_value("#id_kind"), "delivery_note")
        self.assertTrue(self.page.is_visible("#make-document"))
        self.assertTrue(self.page.is_visible("#files"))


class HeadOnPhoneTests(BrowserTestCase):
    """The row of actions wraps on a phone; nothing sticks out to the side."""

    viewport = {"width": 360, "height": 740}

    def test_no_sideways_scrolling(self) -> None:
        for path in (f"/projects/{self.project.pk}/", f"/projects/{self.project.pk}/documents/"):
            with self.subTest(path=path):
                self.open(path)
                self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
                self.page.click(".split-button summary")
                self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
