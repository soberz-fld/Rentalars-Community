# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "settings": the follow-up of a project (PRJ-105), deleting a mailbox (EML-046).

* The dialog "Wiedervorlage" from the head of the project: set, shown in the head, done – the dialog closes
  and the page shows the result without a page of its own.
* On a phone without horizontal scrolling and checked with axe-core (NFA-025): the project with its follow-up
  and the open dialog, the start page with the follow-ups, the confirmation for deleting a mailbox.

The setting "Antwort auf Einsatzanfragen" under Firmendaten und Grundeinstellungen (ADM-015) is checked in
``tests/browser/test_063_crewmail_in_browser.py``.
"""

from __future__ import annotations

import datetime
from unittest import SkipTest

from rentalars.accounts.models import User
from rentalars.projects.follow_up import set_follow_up
from rentalars.projects.models import Project
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.mailbox import add_mailbox, configure_mailbox


class FollowUpInBrowserTests(BrowserTestCase):
    """PRJ-105: set, show and finish a follow-up from the head of the project."""

    def test_set_and_done(self) -> None:
        self.open_planning()
        self.page.locator(".project-actions a", has_text="Wiedervorlage").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        self.assertEqual(dialog.locator("select[name=follow_up_user] option:checked").inner_text(), "anna")
        dialog.locator("input[name=follow_up_on]").fill("2027-03-01")
        dialog.locator("input[name=follow_up_note]").fill("Angebot nachfassen")
        with self.page.expect_navigation():
            dialog.get_by_role("button", name="Wiedervorlage speichern").click()
        note = self.page.locator(".follow-up-note")
        note.wait_for()
        text = " ".join(note.inner_text().split())
        self.assertIn("Wiedervorlage am Mo 01.03.2027 für anna fällig – Angebot nachfassen", text)
        self.project.refresh_from_db()
        self.assertEqual(self.project.follow_up_on, datetime.date(2027, 3, 1))

        with self.page.expect_navigation():
            note.get_by_role("button", name="Erledigt").click()
        self.page.locator(".project-actions a", has_text="Wiedervorlage").wait_for()
        self.assertEqual(self.page.locator(".follow-up-note").count(), 0)
        self.assertIsNone(Project.objects.get(pk=self.project.pk).follow_up_on)

    def test_change_in_the_dialog(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 5), note="Rückruf", by=User.objects.get(username="anna"))
        self.open_planning()
        self.page.locator(".follow-up-note a", has_text="Ändern").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        self.assertEqual(dialog.locator("input[name=follow_up_note]").input_value(), "Rückruf")
        dialog.locator("input[name=follow_up_on]").fill("2027-03-08")
        with self.page.expect_navigation():
            dialog.get_by_role("button", name="Wiedervorlage speichern").click()
        self.page.locator(".follow-up-note").wait_for()
        self.assertIn("Mo 08.03.2027", self.text_of(".follow-up-note"))


class SettingsOnAPhoneTests(BrowserTestCase):
    """PRJ-105, EML-046: the new pages and parts on a phone, with axe-core."""

    bypass_csp = True

    def check(self, path: str, *, then: str = "") -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        if then:
            self.page.locator(then).first.click()
            self.page.locator("dialog#dialog[open]").wait_for()
            self.settle()
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375, path)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def follow_up(self) -> None:
        anna = User.objects.get(username="anna")
        set_follow_up(self.project, on=datetime.date(2027, 2, 26), note="Angebot nachfassen", by=anna)

    def test_project_with_follow_up(self) -> None:
        self.follow_up()
        self.check(f"/projects/{self.project.pk}/")

    def test_dialog(self) -> None:
        self.follow_up()
        self.check(f"/projects/{self.project.pk}/", then=".follow-up-note a")

    def test_start_page(self) -> None:
        self.follow_up()
        self.check("/")
        self.assertIn("Deine Wiedervorlagen", self.page.inner_text("main"))

    def test_project_list(self) -> None:
        self.follow_up()
        self.check("/projects/?follow_up=any")

    def test_delete_mailbox(self) -> None:
        configure_mailbox()
        info = add_mailbox("Info", "info@verleih.example")
        add_mailbox("Büro", "buero@verleih.example")
        self.check(f"/administration/mail/mailboxes/{info.pk}/delete/")
        projects = info.__class__.objects.get(name="Projekte")
        self.check(f"/administration/mail/mailboxes/{projects.pk}/delete/")
        self.assertTrue(self.page.locator("select#id_successor").is_visible())
