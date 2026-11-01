# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "sync", in the browser: an open packlist page follows what somebody else ticks – a colleague, the
app (UIX-020, PCK-027) –, and the chat shows a second change of a message within the same second (UIX-010) –
and axe-core on both pages, on a wide screen and on a phone."""

from __future__ import annotations

from decimal import Decimal
from unittest import SkipTest

from rentalars.chat import services as chat
from rentalars.packing import offline, services
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import at, make_user


class SyncInBrowserTests(BrowserTestCase):
    """UIX-020, UIX-010 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True
    watch_changes = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def axe_findings(self, within: str = "") -> list[str]:
        """What axe-core finds on the page, or only within the elements a selector names."""
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
        """axe-core in the dark theme and – after switching, on the page's own content – in the light one."""
        findings = self.axe_findings()
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
        findings += [f"light: {finding}" for finding in self.axe_findings("main")]
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        return findings

    def ask_now(self) -> None:
        """The page asks every 20 seconds, and at once when it becomes visible again."""
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")

    def test_the_packlist_follows_the_app(self) -> None:
        """UIX-020, PCK-027: the app ticks a row; the open packlist loads itself again and shows it."""
        packlist = services.get_packlist(self.project)
        row = next(row for row in services.build_overview(packlist).warehouse_rows if row.required > 1)
        # Packing has started: a further tick writes nothing into the change log – only the ticks' stamp moves.
        row = services.set_packed(packlist, row.line.pk, row.product.pk, Decimal(1))
        self.open(f"/projects/{self.project.number}/packlist/")
        self.settle()
        self.assertEqual(self.both_themes(), [])
        change = offline.Change(row.line.pk, row.product.pk, "packed", Decimal(2), at(1, 7), base_version=row.version)
        results = offline.apply_changes(packlist, [change], user=make_user("luka", roles=("Lager",)))
        self.assertEqual(results[0].outcome, "applied", results[0].message)
        with self.page.expect_navigation():
            self.ask_now()
        self.settle()
        self.assertEqual(self.both_themes(), [])

    def test_the_chat_shows_a_second_change_within_the_same_second(self) -> None:
        """UIX-010: the clock stands still – the second change of a message still reaches the open chat."""
        lena = make_user("lena", superuser=True)
        message = chat.post_message(self.project, user=lena, text="Bühne steht um 8")
        chat.edit_message(message, user=lena, text="Bühne steht um 9")
        self.open(f"/projects/{self.project.number}/chat/")
        self.settle()
        self.page.locator(f"#m{message.pk}", has_text="um 9").wait_for()
        self.assertEqual(self.both_themes(), [])
        chat.edit_message(message, user=lena, text="Bühne steht um 10")
        self.ask_now()
        self.page.locator(f"#m{message.pk}", has_text="um 10").wait_for()


class SyncOnAPhoneInBrowserTests(SyncInBrowserTests):
    """The same on a phone."""

    viewport = {"width": 390, "height": 760}
