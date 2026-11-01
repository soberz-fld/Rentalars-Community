# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "ai" (EML-040), checked with axe-core (NFA-025):

* Einstellungen → KI on a phone, for a virtual machine: processor without AVX2/FMA, the Proxmox hint and the
  command for the smaller model;
* the correspondence: the estimate with its warning, then "Zusammenfassen" streaming to the summary.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import override_settings

from rentalars.ai.models import AISettings
from tests.ai_fake import write_local_file
from tests.browser.test_083_ai_in_browser import AIInTheBrowserTests
from tests.unit.test_083_ai import add_mail
from tests.unit.test_084_ai import PROXMOX_CPUINFO


class SpeedInTheBrowserTests(AIInTheBrowserTests):
    """EML-040: the pages with mouse and keyboard, with axe-core."""

    def setUp(self) -> None:
        super().setUp()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "cpuinfo").write_text(PROXMOX_CPUINFO)
        # The model installed by default: Qwen3 4B.
        write_local_file(folder / "ai-local.conf", self.fake.url, model="qwen3-4b")
        override = override_settings(
            RENTALARS_AI_CPUINFO=str(folder / "cpuinfo"), RENTALARS_AI_LOCAL_FILE=str(folder / "ai-local.conf")
        )
        override.enable()
        self.addCleanup(override.disable)
        AISettings.load()
        AISettings.objects.filter(pk=1).update(local_test_prompt_per_second=5, local_test_tokens_per_second=1.5)

    # The other tests run in their own class; here only these.
    test_summarise_the_correspondence = None  # type: ignore[assignment]
    test_the_overview_on_a_phone = None  # type: ignore[assignment]
    test_suggest_a_draft_and_take_it_over = None  # type: ignore[assignment]
    test_the_settings_page = None  # type: ignore[assignment]

    def test_the_settings_on_a_phone(self) -> None:
        """EML-040: processor, speeds, the hint and the command fit a phone."""
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open("/administration/ai/")
        self.page.get_by_text("ohne AVX2, FMA").wait_for()
        body = self.page.inner_text("body")
        self.assertIn("Prozessortyp auf „host“", body)
        self.assertIn("sudo rentalars ai install --model qwen3-1.7b", body)
        self.assertIn("liest 5,0, schreibt 1,5 Token pro Sekunde", body)
        self.check_axe(375)

    def test_the_estimate_then_the_summary(self) -> None:
        """EML-040: the long estimate is shown; the summary still streams in and appears."""
        for day in range(3, 9):
            add_mail(self.project, f"Tag {day}", "Bühne und Licht wie besprochen. " * 30, days=day)
        self.open(f"/projects/{self.project.pk}/mails/")
        block = self.page.locator("#ai-summary")
        block.get_by_text("– lange.").wait_for()
        block.get_by_role("button", name="Zusammenfassen").click()
        block.get_by_text("von KI erstellt").wait_for()
        self.assertTrue(self.fake.chats[-1]["stream"])
        self.check_axe()
