# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the lock of the messages of the correspondence (EML-055) and the tab "Zugriff" with the
crew (AUT-035) – and axe-core on them, on a wide screen and on a phone."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.mail import notes
from rentalars.mail.models import ProjectMail
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import at


class LockInBrowserTests(BrowserTestCase):
    """The lock shown on each message and changed with one click; the access list; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def setUp(self) -> None:
        super().setUp()
        self.secret = ProjectMail.objects.create(
            project=self.project,
            direction="in",
            message_key="lock-092-1",
            message_id="<lock1@x.example>",
            subject="Angebot mit Rabatt",
            sender_name="Max Muster",
            sender_address="max@stadtwerke.example",
            date=at(1, 7),
            text_body="Wir geben 20 % Rabatt.",
        )
        self.open_mail = ProjectMail.objects.create(
            project=self.project,
            direction="in",
            message_key="lock-092-2",
            message_id="<lock2@x.example>",
            subject="Aufbauzeiten",
            sender_name="Max Muster",
            sender_address="max@stadtwerke.example",
            date=at(1, 7, 10),
            text_body="Aufbau ab 8 Uhr.",
            locked=False,
        )
        notes.add_note(self.project, text="Kunde will Rabatt.", subject="Telefonat Preis", user=None, date=at(1, 7, 20))

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

    def both_themes(self, within: str = "") -> list[str]:
        """axe-core in the dark theme and – after switching, on the page's own content – in the light one."""
        findings = self.axe_findings(within)
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
        findings += [f"light: {finding}" for finding in self.axe_findings(within or "main")]
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        return findings

    def test_the_list_and_the_conversation(self) -> None:
        for view in ("list", "conversation"):
            with self.subTest(view):
                self.open(f"/projects/{self.project.pk}/mails/?view={view}")
                self.assertEqual(self.page.locator(".mail-lock .lock-badge").count(), 2)
                self.assertEqual(self.both_themes(), [])
        self.open(f"/projects/{self.project.pk}/mails/?view=list")
        row = self.page.locator("table.mails tbody tr", has_text="Angebot mit Rabatt")
        button = row.locator(".mail-lock button", has_text="Schloss entfernen")
        self.assertIn("Angebot mit Rabatt", button.text_content())  # its name for screen readers
        button.click()
        self.page.locator(".messages", has_text="Das Schloss ist entfernt").wait_for()
        self.secret.refresh_from_db()
        self.assertFalse(self.secret.locked)
        self.assertEqual(self.page.locator(".mail-lock .lock-badge").count(), 1)
        self.assertEqual(self.both_themes(), [])

    def test_the_mail_and_the_form(self) -> None:
        self.open(f"/projects/{self.project.pk}/mails/{self.secret.pk}/")
        self.page.locator(".mail-lock-state", has_text="Mit Schloss:").wait_for()
        self.assertEqual(self.both_themes(), [])
        self.page.locator("button", has_text="Schloss entfernen").click()
        self.page.locator(".mail-lock-state", has_text="Offen:").wait_for()
        self.open(f"/projects/{self.project.pk}/mails/note/")
        self.assertTrue(self.page.locator("input[name=locked]").is_checked())
        self.assertEqual(self.both_themes(), [])

    def test_the_access_tab(self) -> None:
        self.open(f"/projects/{self.project.pk}/members/")
        self.page.locator("h2", has_text="Wer Zugriff hat").wait_for()
        self.assertEqual(self.both_themes(), [])


class LockOnAPhoneTests(LockInBrowserTests):
    """The same on a phone: the table turns into cards, the buttons stay usable."""

    viewport = {"width": 360, "height": 740}
