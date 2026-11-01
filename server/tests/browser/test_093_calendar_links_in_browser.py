# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the box "Kalender-Link" on the page of an item – create, copy, deactivate – with axe-core
(VFG-040).

The requirement: .ics links can be activated per product, model or item. By default no separate calendar is active;
on the page of an item, creating the link can be switched on (and off again).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from rentalars.material.models import ItemStatus, MaterialItem
from rentalars.schedule.models import CalendarLink
from tests.browser.base import BrowserTestCase
from tests.browser.test_071_planning_in_browser import AxeMixin


class CalendarLinkInBrowserTests(AxeMixin, BrowserTestCase):
    """None by default; created with one click, copied to the clipboard, read without login, deactivated."""

    def test_create_copy_read_and_deactivate(self) -> None:
        item = MaterialItem.objects.filter(status=ItemStatus.AVAILABLE).order_by("pk").first()
        self.page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.live_server_url)
        self.open(f"/material/items/{item.pk}/")
        box = self.page.locator("#calendar-link")
        self.assertIn("Es ist kein Kalender-Link aktiv.", box.inner_text())
        self.assertEqual(self.axe_findings("#calendar-link"), [])

        with self.page.expect_navigation():
            box.get_by_role("button", name="Kalender-Link erstellen").click()
        self.assertIn("Der Kalender-Link wurde erstellt.", self.text_of("main"))
        address = self.page.get_by_label("Adresse für Kalenderprogramme")
        url = address.input_value()
        self.assertIn(f"/calendar-feed/item/{item.pk}/", url)
        self.assertEqual(self.axe_findings("#calendar-link"), [])

        box.get_by_role("button", name="Kopieren").click()
        self.page.wait_for_function(
            "document.querySelector('#calendar-link [data-copy-status]').textContent === 'Kopiert'"
        )
        self.assertEqual(self.page.evaluate("navigator.clipboard.readText()"), url)

        # Calendar programs read it without login.
        path = urlsplit(url).path
        stranger = self.browser.new_context()
        self.addCleanup(stranger.close)
        answer = stranger.request.get(self.live_server_url + path)
        self.assertEqual(answer.status, 200)
        self.assertTrue(answer.text().startswith("BEGIN:VCALENDAR"))

        box.get_by_role("button", name="Link deaktivieren").click()
        with self.page.expect_navigation():
            self.confirm()
        self.assertIn("Der Kalender-Link ist deaktiviert", self.text_of("main"))
        self.assertIn("Kalender-Link erstellen", self.page.locator("#calendar-link").inner_text())
        self.assertEqual(stranger.request.get(self.live_server_url + path).status, 404)
        self.assertEqual(CalendarLink.objects.exclude(token="").count(), 0)
