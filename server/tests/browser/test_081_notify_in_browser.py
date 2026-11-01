# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "notify": UIX-039, PRJ-109, VFG-034.

* PRJ-109: the dialog of the follow-up takes a time; the head of the project shows it.
* VFG-034: Planung → Wiedervorlagen – "Verschieben" opens the dialog over the table and comes back to it,
  "Erledigt" removes the row.
* On a phone without horizontal scrolling and checked with axe-core (NFA-025): the notification settings
  grouped by category with the column "In der App" (UIX-039), the list of notifications with the category
  filter, the tab "Wiedervorlagen" and the dialog with its time field.
"""

from __future__ import annotations

import datetime
from unittest import SkipTest

from rentalars.accounts.models import User
from rentalars.notifications import services as notifications
from rentalars.notifications.models import Kind
from rentalars.projects import service_cases
from rentalars.projects.follow_up import set_follow_up
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class FollowUpInBrowserTests(BrowserTestCase):
    """PRJ-109, VFG-034: the time in the dialog; moving and finishing from the table."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = User.objects.get(username="anna")

    def test_set_a_time_in_the_dialog(self) -> None:
        self.open_planning()
        self.page.locator(".project-actions a", has_text="Wiedervorlage").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        dialog.locator("input[name=follow_up_on]").fill("2027-03-04")
        dialog.locator("input[name=follow_up_at]").fill("14:30")
        dialog.locator("input[name=follow_up_note]").fill("Rückruf Technik")
        with self.page.expect_navigation():
            dialog.get_by_role("button", name="Wiedervorlage speichern").click()
        note = self.page.locator(".follow-up-note")
        note.wait_for()
        self.assertIn("Wiedervorlage am Do 04.03.2027 um 14:30", " ".join(note.inner_text().split()))
        self.project.refresh_from_db()
        self.assertEqual(self.project.follow_up_at, datetime.time(14, 30))

    def test_move_and_done_from_the_table(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 4), at=datetime.time(9, 0), note="Angebot", by=self.anna)
        case = service_cases.create_case(name="Reparatur Mischpult", manager=self.anna)
        set_follow_up(case, on=datetime.date(2027, 3, 2), note="Rückruf", by=self.anna)
        self.open("/schedule/follow-ups/")
        row = self.page.locator("tr", has_text="Stadtfest Hauptbühne")
        row.get_by_role("link", name=f"Wiedervorlage von {self.project.number} verschieben").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        dialog.locator("input[name=follow_up_at]").fill("16:15")
        with self.page.expect_navigation():
            dialog.get_by_role("button", name="Wiedervorlage speichern").click()
        self.assertEqual(self.page.url, f"{self.live_server_url}/schedule/follow-ups/")
        self.page.locator("tr", has_text="Stadtfest Hauptbühne").locator("td", has_text="16:15").wait_for()
        with self.page.expect_navigation():
            self.page.locator("tr", has_text="Reparatur Mischpult").get_by_role(
                "button", name=f"Wiedervorlage von {case.number} erledigt"
            ).click()
        self.assertEqual(self.page.locator("tr", has_text="Reparatur Mischpult").count(), 0)
        case.refresh_from_db()
        self.assertIsNone(case.follow_up_on)


class NotifyOnAPhoneTests(BrowserTestCase):
    """UIX-039, PRJ-109, VFG-034: the pages on a phone, with axe-core."""

    bypass_csp = True

    def check(self, path: str, *, then: object = None) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        if callable(then):
            then()
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375, path)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def test_notification_settings(self) -> None:
        self.check("/account/notifications/")
        self.assertEqual(self.page.locator("th[scope=rowgroup]").first.inner_text(), "Projekt")

    def test_notification_list(self) -> None:
        anna = User.objects.get(username="anna")
        notifications.notify([anna], Kind.FOLLOW_UP, "Wiedervorlage: Stadtfest Hauptbühne", body="Angebot nachfassen")
        notifications.notify([anna], Kind.MAIL_PROBLEM, "Postfach nicht erreichbar")
        self.check("/notifications/?category=project")

    def test_follow_ups_tab_and_dialog(self) -> None:
        anna = User.objects.get(username="anna")
        set_follow_up(self.project, on=datetime.date(2027, 2, 26), at=datetime.time(9, 0), note="Angebot", by=anna)
        case = service_cases.create_case(name="Reparatur Mischpult", manager=anna)
        set_follow_up(case, on=datetime.date(2027, 3, 2), note="Rückruf beim Kunden", by=anna)
        self.check("/schedule/follow-ups/?group=user")

        def open_dialog() -> None:
            self.page.get_by_role("link", name=f"Wiedervorlage von {self.project.number} verschieben").click()
            self.page.locator("#dialog input[name=follow_up_at]").wait_for()

        self.check("/schedule/follow-ups/", then=open_dialog)
