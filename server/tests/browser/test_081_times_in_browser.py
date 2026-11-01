# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "times": ZEI-025, ZEI-024, ZEI-026.

* ZEI-025: the quick entry divides a period into job functions – the part opens from "Mehrere Funktionen in diesem
  Zeitraum" – and the confirmation names each part.
* ZEI-026: "In Zwischenablage kopieren" at an approved time puts the block with real tabs on the clipboard and says
  "Kopiert" to screen readers – with ``navigator.clipboard`` and, where it is missing, with the fallback.
* ZEI-024: the hint at the companion app goes away with its button and stays away.
* On a phone without horizontal scrolling and checked with axe-core (NFA-025): "My times" with hint, parts and copy
  button, and the quick entry with the parts open.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest import SkipTest

from rentalars.accounts.rights import Rights
from rentalars.timetracking import services
from rentalars.timetracking.models import TimeEntry
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.browser.test_time_in_browser import TimeInBrowserTestCase
from tests.helpers import NOW

ALL = Rights.everything()


class TimesInBrowserCase(TimeInBrowserTestCase):
    """Anna Becker of the sample data is the logged-in administrator, planned as sound engineer on the Jazznacht."""

    def other_function(self, select: str) -> str:
        """A job function of the selection that is neither the one above nor a deployment."""
        main = self.page.input_value("#dialog [name=job_function]")
        values = self.page.eval_on_selector_all(f"{select} option", "options => options.map(option => option.value)")
        return next(value for value in values if value and value != main and not value.startswith("line:"))

    def approved_period(self) -> TimeEntry:
        """Two job functions from 02:00 to 06:00 this morning – 3 hours sound, 1 hour another – approved."""
        start = NOW - datetime.timedelta(hours=6)
        other = next(
            function for function in services.job_functions_for(self.anna, self.show) if function != self.sound
        )
        first = services.create_entry(
            person=self.anna,
            project=self.show,
            job_function=self.sound,
            start=start,
            end=start + datetime.timedelta(hours=4),
            rights=ALL,
            user=None,
            submit=True,
            parts=[services.Part(self.sound, None), services.Part(other, Decimal("1"))],
        )
        services.approve_entries([first], rights=ALL, user=None)
        return first


class DividingInBrowserTests(TimesInBrowserCase):
    """ZEI-025 with scripts running."""

    def test_dividing_a_period_in_the_quick_entry(self) -> None:
        self.open("/times/")
        self.page.locator(".page-head").get_by_role("link", name="Zeit erfassen").click()
        self.dialog().wait_for()
        self.page.select_option("#dialog [name=project]", str(self.show.pk))
        self.settle()
        parts = self.page.locator("#dialog details.time-parts")
        self.assertFalse(self.page.locator("#dialog [name=part_0_hours]").is_visible())
        parts.locator("summary").click()
        self.assertTrue(self.page.locator("#dialog [name=part_0_hours]").is_visible())
        self.page.select_option("#dialog [name=part_0_function]", self.other_function("#dialog [name=part_0_function]"))
        self.page.fill("#dialog [name=part_0_hours]", "0,5")
        self.record("06:00", "08:00")
        text = self.dialog().inner_text()
        self.assertIn("Zeit erfasst", text)
        self.assertIn("1,5 Std. als Tontechniker", text)
        self.assertIn("0,5 Std. als", text)
        divided = TimeEntry.objects.filter(period_key__isnull=False)
        self.assertEqual(sorted(divided.values_list("hours", flat=True)), [Decimal("0.50"), Decimal("1.50")])


class CopyInBrowserTests(TimesInBrowserCase):
    """ZEI-026."""

    bypass_csp = True  # the test waits for the status with a script of its own

    def test_copying_puts_the_blocks_on_the_clipboard(self) -> None:
        self.approved_period()
        self.page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.live_server_url)
        self.open("/times/")
        self.page.get_by_role("button", name="In Zwischenablage kopieren").click()
        self.page.wait_for_function("document.querySelector('[data-copy-status]').textContent === 'Kopiert'")
        copied = self.page.evaluate("navigator.clipboard.readText()")
        self.assertEqual(copied.count("\tDatum: 2027.03.01"), 2)
        self.assertIn(f"\tProjekt: {self.show.number} - Jazznacht\n", copied)

    def test_without_the_clipboard_interface_the_fallback_copies(self) -> None:
        """ZEI-026: plain http has no ``navigator.clipboard``; a hidden text area and execCommand do it."""
        self.approved_period()
        self.open("/times/")
        self.page.evaluate(
            "() => { Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true});"
            " window.copiedText = null;"
            " document.execCommand = (command) => { window.copiedText = document.activeElement.value; return true; }; }"
        )
        self.page.get_by_role("button", name="In Zwischenablage kopieren").click()
        self.page.wait_for_function("document.querySelector('[data-copy-status]').textContent === 'Kopiert'")
        copied = self.page.evaluate("window.copiedText")
        self.assertTrue(copied.startswith("Tontechniker") or "\n\tDatum: 2027.03.01\n" in copied, copied)
        self.assertIn("\tAktivität: ", copied)
        self.assertEqual(self.page.locator("textarea").count(), 0)  # the helper is gone again


class CompanionHintInBrowserTests(TimesInBrowserCase):
    """ZEI-024: put away with one tap, for good."""

    def test_the_hint_goes_away_and_stays_away(self) -> None:
        self.open("/times/")
        hint = self.page.locator("#companion-hint")
        self.assertIn("Rentalars Companion", hint.inner_text())
        hint.get_by_role("button", name="Diesen Hinweis ausblenden").click()
        hint.wait_for(state="detached")
        self.open("/times/")
        self.assertNotIn("Rentalars Companion", self.page.inner_text("main"))


class TimesOnAPhoneTests(TimesInBrowserCase):
    """ZEI-024, ZEI-025, ZEI-026 on a phone, with axe-core (NFA-025)."""

    bypass_csp = True

    def check(self) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def test_my_times_with_hint_parts_pay_and_copy(self) -> None:
        self.approved_period()
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open("/times/")
        self.page.wait_for_load_state("networkidle")
        text = self.page.inner_text("main")
        self.assertIn("Rentalars Companion", text)
        self.assertIn("Teil 2 von 2", text)
        self.assertEqual(self.page.locator("th", has_text="Stundenlohn").count(), 1)
        self.check()

    def test_the_quick_entry_with_the_parts_open(self) -> None:
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open("/times/")
        self.page.locator(".page-head a.btn", has_text="Zeit erfassen").click()
        self.page.locator("dialog#dialog[open]").wait_for()
        self.settle()
        self.page.locator("#dialog details.time-parts summary").click()
        self.check()
