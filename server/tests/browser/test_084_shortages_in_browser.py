# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "shortages": Einstellungen → Benachrichtigungen (VFG-036).

The day of the week appears only for "Einmal in der Woche"; saving keeps the values; axe-core finds nothing in the
dark and the light theme, and on a phone the page fits without horizontal scrolling (NFA-025).
"""

from __future__ import annotations

import datetime
from unittest import SkipTest

from rentalars.core.models import NotificationSettings, ShortageInterval
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path

URL = "/administration/notifications/"


class ShortageSettingsInBrowserTests(BrowserTestCase):
    """VFG-036: Anna of the sample data, an administrator, sets the shortage notifications."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def axe_findings(self, within: str = "") -> list[str]:
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

    def both_themes(self) -> list[str]:
        """The whole page in the dark theme; after switching, the page's own content in the light one."""
        findings = self.axe_findings()
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
        findings += [f"light: {finding}" for finding in self.axe_findings("main")]
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        return findings

    def test_once_a_week_on_friday(self) -> None:
        self.open(URL)
        form = self.page.locator("form#notification-settings")
        weekday = form.locator("select[name=shortage_weekday]")
        self.assertFalse(weekday.is_visible())
        self.assertEqual(self.both_themes(), [])
        form.locator("select[name=shortage_interval]").select_option(label="Einmal in der Woche")
        weekday.wait_for(state="visible")
        weekday.select_option(label="Freitag")
        form.locator("input[name=shortage_time]").fill("07:30")
        form.locator("input[name=shortage_lead_weeks]").fill("8")
        form.get_by_label("Bekannte Fehlbestände bei jeder Prüfung erneut melden").check()
        with self.page.expect_navigation():
            form.get_by_role("button", name="Einstellungen speichern").click()
        self.assertIn("Einstellungen gespeichert.", self.text_of("main"))
        self.assertIn("Fr 05.03.2027 07:30", self.text_of("#shortage-check-times"))
        self.assertTrue(self.page.locator("select[name=shortage_weekday]").is_visible())
        settings = NotificationSettings.objects.get(pk=1)
        self.assertEqual(
            (
                settings.shortage_interval,
                settings.shortage_weekday,
                settings.shortage_time,
                settings.shortage_lead_weeks,
                settings.shortage_repeat,
            ),
            (ShortageInterval.WEEKLY, 5, datetime.time(7, 30), 8, True),
        )
        # Back to every day: the day of the week goes away again.
        self.page.locator("select[name=shortage_interval]").select_option(label="Jeden Tag")
        self.page.locator("select[name=shortage_weekday]").wait_for(state="hidden")
        self.assertEqual(self.both_themes(), [])

    def test_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 375, "height": 800})
        try:
            self.open(URL)
            self.page.wait_for_load_state("networkidle")
            self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 375)
            self.assertEqual(self.axe_findings(), [])
        finally:
            self.page.set_viewport_size(self.viewport)
