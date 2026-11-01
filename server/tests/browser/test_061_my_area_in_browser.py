# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: entering a series on "My area" (PER-028) and "Back" on the phone (UIX-027)."""

from __future__ import annotations

import datetime

from rentalars.accounts.models import User
from rentalars.personnel.models import AvailabilitySeries
from tests.browser.base import BrowserTestCase


class SeriesInBrowserTests(BrowserTestCase):
    def test_enter_a_series_by_tapping_days(self) -> None:
        self.open("/me/availability/?month=2027-03")
        # The details of a repetition show only with one, the weekdays only for "weekly".
        self.page.locator("details.avail-repeat-toggle summary").click()
        self.assertFalse(self.page.locator("[data-repeat-weekdays]").is_visible())
        self.assertFalse(self.page.locator("input[name=until]").is_visible())
        self.page.locator('[data-avail-day="2027-03-02"]').click()
        self.page.locator('[data-avail-day="2027-03-02"]').click()
        self.page.check("input[name=with_times]")
        self.page.fill("input[name=start_time]", "18:00")
        self.page.fill("input[name=end_time]", "22:00")
        self.page.select_option("select[name=repeat]", "weekly")
        self.assertTrue(self.page.locator("[data-repeat-weekdays]").is_visible())
        self.assertEqual(self.page.locator(".unit-weekly").inner_text(), "Wochen")
        self.page.locator("label.weekday-box", has_text="Di").click()
        self.page.locator("label.weekday-box", has_text="Do").click()
        self.page.fill("input[name=count]", "4")
        self.page.click("button[name=state][value=unavailable]")
        self.page.wait_for_load_state("networkidle")
        self.assertIn("Serie eingetragen: 4 Termine.", self.page.locator(".messages").inner_text())
        series = AvailabilitySeries.objects.get(person=User.objects.get(username="anna").person)
        self.assertEqual((series.weekdays, series.count, series.start_time), ("1,3", 4, datetime.time(18)))
        self.assertEqual(self.page.locator(".series-row").count(), 1)
        self.assertEqual(self.page.locator(".avail-day.unavailable").count(), 4)


class BackOnThePhoneTests(BrowserTestCase):
    viewport = {"width": 360, "height": 740}

    def test_back_at_the_top_goes_where_one_came_from(self) -> None:
        self.open("/customers/")
        self.page.locator("nav.tabs a", has_text="Veranstaltungsorte").click()
        self.page.wait_for_url(f"{self.live_server_url}/customers/venues/")
        self.assertEqual(self.page.locator("a.back-link").count(), 0)  # a tab is a start page
        back = self.page.locator("a.topbar-back")
        self.assertTrue(back.is_visible())
        back.click()
        self.page.wait_for_url(f"{self.live_server_url}/customers/")
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        # The name next to the logo makes room, but stays for screen readers.
        self.assertEqual(self.page.locator(".topbar .brand").get_attribute("href"), "/")
        self.assertEqual(self.page.locator(".topbar .brand").inner_text().strip(), "Rentalars")
