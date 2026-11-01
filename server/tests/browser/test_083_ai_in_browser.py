# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "ai": EML-040, EML-044, ADM-017.

With the fake model server in place of the local AI, on a desktop and on a phone without horizontal scrolling, and
checked with axe-core (NFA-025):

* Einstellungen → KI with the local AI installed and an interface to a cloud service (EML-040, ADM-017);
* the correspondence of a project: the short overview, "Zusammenfassen", the summary marked as made by AI (EML-040,
  EML-044);
* "Mail schreiben": "Entwurf vorschlagen" and "In den Text übernehmen" (ADM-017).
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import suppress
from pathlib import Path
from unittest import SkipTest

from django.test import override_settings

from rentalars.ai.models import AIProvider, AISettings, Source
from tests.ai_fake import FakeModelServer, write_local_file
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.mailbox import configure_mailbox
from tests.unit.test_083_ai import add_mail

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:  # without Playwright every test of the folder is skipped (tests/browser/base.py)
    PlaywrightTimeout = TimeoutError  # type: ignore[misc,assignment]


class AIInTheBrowserTests(BrowserTestCase):
    """EML-040, EML-044, ADM-017: the pages of the AI, used with mouse and keyboard, with axe-core."""

    bypass_csp = True

    def setUp(self) -> None:
        super().setUp()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        local_file = folder / "ai-local.conf"
        override = override_settings(RENTALARS_AI_LOCAL_FILE=str(local_file))
        override.enable()
        self.addCleanup(override.disable)
        self.fake = FakeModelServer().__enter__()
        self.addCleanup(self.fake.__exit__)
        write_local_file(local_file, self.fake.url)
        ai_settings = AISettings.load()
        ai_settings.summary_source = Source.LOCAL
        ai_settings.draft_source = Source.LOCAL
        ai_settings.save()
        configure_mailbox()
        add_mail(self.project, "Angebot Stadtfest", "Können Sie uns ein Angebot für den 12.06.2027 schicken?")
        add_mail(self.project, "Re: Angebot", "Anbei das Angebot über 2.380,00 €.", incoming=False, days=1)
        self.question = add_mail(self.project, "Re: Angebot", "Passt der Aufbau am Donnerstag?", days=2)

    def check_axe(self, width: int | None = None) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        if width is not None:
            # A part of the page swapped in by htmx may be laid out a moment later on a busy machine.
            with suppress(PlaywrightTimeout):
                self.page.wait_for_function(
                    "(w) => document.scrollingElement.scrollWidth <= w", arg=width, timeout=5000
                )
            scroll = self.page.evaluate("document.scrollingElement.scrollWidth")
            wide = self.page.evaluate(
                "(w) => [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > w)"
                ".slice(0, 5).map(e => e.tagName + '.' + e.className + ' ' + (e.textContent || '').slice(0, 40))",
                width,
            )
            self.assertLessEqual(scroll, width, wide)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def test_summarise_the_correspondence(self) -> None:
        """EML-040, EML-044: overview first, then "Zusammenfassen" – the summary appears, marked as made by AI."""
        self.open(f"/projects/{self.project.pk}/mails/")
        block = self.page.locator("#ai-summary")
        block.get_by_text("Kurzüberblick ohne KI").wait_for()
        # EML-050: the short overview is folded on load – opened by a click.
        block.get_by_text("Kurzüberblick ohne KI").click()
        self.assertIn("Passt der Aufbau am Donnerstag?", block.inner_text())
        block.get_by_role("button", name="Zusammenfassen").click()
        block.get_by_text("von KI erstellt").wait_for()
        self.assertIn("Überblick: Die Kundin fragt nach dem Aufbau am Freitag.", block.inner_text())
        self.assertIn("qwen2.5-1.5b-instruct", block.inner_text())
        self.check_axe()

    def test_the_overview_on_a_phone(self) -> None:
        """EML-044: the block fits a phone."""
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(f"/projects/{self.project.pk}/mails/")
        self.page.locator("#ai-summary").get_by_text("Kurzüberblick ohne KI").wait_for()
        self.check_axe(375)

    def test_suggest_a_draft_and_take_it_over(self) -> None:
        """ADM-017: the draft goes above the quoted mail in the text."""
        self.open(f"/projects/{self.project.pk}/mails/new/?answer={self.question.pk}")
        self.page.get_by_role("button", name="Entwurf vorschlagen").click()
        self.page.get_by_text("Entwurf der KI").first.wait_for()
        self.page.get_by_role("button", name="In den Text übernehmen").click()
        body = self.page.locator("#id_body").input_value()
        self.assertTrue(body.startswith("Hallo Frau Berg,"), body[:80])
        self.assertIn("Passt der Aufbau am Donnerstag?", body)
        self.check_axe()

    def test_the_settings_page(self) -> None:
        """EML-040, ADM-017: installed local AI, the switch, an interface to a cloud service with its warning."""
        AIProvider.objects.create(name="Cloud", base_url="https://api.example.com/v1", model="gpt-x")
        self.open("/administration/ai/")
        self.page.get_by_text("Zusammenfassungen mit lokaler KI ausschalten").wait_for()
        self.assertIn("Cloud – Daten verlassen das Unternehmen", self.page.inner_text("body"))
        self.check_axe()
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open("/administration/ai/")
        self.page.get_by_role("button", name="Geschwindigkeit messen").click()
        self.page.get_by_text("Token pro Sekunde").first.wait_for()
        self.check_axe(375)
