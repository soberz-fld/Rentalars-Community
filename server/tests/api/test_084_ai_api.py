# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "ai" (EML-040): the estimate of a summary, the processor, speeds and recommendation in
the settings, reading and writing speed of the speed test and of every call (changed operations, API-014)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import override_settings

from rentalars.ai.models import AICall, AISettings, Source
from tests.ai_fake import write_local_file
from tests.api.base import API
from tests.api.test_083_ai_api import AIApiTestCase
from tests.unit.test_084_ai import PROXMOX_CPUINFO


class EstimateApiTests(AIApiTestCase):
    """EML-040: ``GET /projects/{id}/correspondence-summary`` – ``estimate``."""

    def test_the_estimate(self) -> None:
        url = f"{API}/projects/{self.project.pk}/correspondence-summary"
        self.assertIsNone(self.admin.get(url).json()["estimate"])  # switched off
        self.switch("summary", Source.LOCAL)
        self.assertIsNone(self.admin.get(url).json()["estimate"])  # not measured yet
        AISettings.load()
        AISettings.objects.filter(pk=1).update(local_test_prompt_per_second=5, local_test_tokens_per_second=1.5)
        estimate = self.admin.get(url).json()["estimate"]
        self.assertGreater(estimate["seconds"], 60)
        self.assertGreaterEqual(estimate["limit_seconds"], 3 * estimate["upper_seconds"])
        self.assertEqual(estimate["calls"], 1)
        started = self.admin.post(url, {}, format="json")
        self.assertEqual(started.status_code, 202, started.content)


class SettingsApiTests(AIApiTestCase):
    """EML-040: ``/ai/settings`` with processor, speeds and recommendation; the speed test; the call log."""

    def setUp(self) -> None:
        super().setUp()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "cpuinfo").write_text(PROXMOX_CPUINFO)
        override = override_settings(RENTALARS_AI_CPUINFO=str(folder / "cpuinfo"))
        override.enable()
        self.addCleanup(override.disable)

    def test_settings_name_the_processor_and_the_advice(self) -> None:
        write_local_file(self.local_file, self.fake.url, model="qwen3-4b")
        data = self.admin.get(f"{API}/ai/settings").json()["local"]
        self.assertEqual(data["cpu"]["missing"], ["AVX2", "FMA"])
        self.assertEqual((data["cpu"]["physical_cores"], data["cpu"]["virtual_machine"]), (4, True))
        self.assertIn("Proxmox", data["advice"]["texts"][0])
        self.assertEqual(data["advice"]["command"], "sudo rentalars ai install --model qwen3-1.7b")
        self.assertIsNone(data["typical_summary"])
        changed = self.admin.patch(f"{API}/ai/settings", {"summary": "local"}, format="json")
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["local"]["cpu"]["missing"], ["AVX2", "FMA"])

    def test_speed_test_reads_and_writes(self) -> None:
        response = self.admin.post(f"{API}/ai/local/speed-test")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            (response.json()["prompt_tokens_per_second"], response.json()["tokens_per_second"]), (80.0, 12.5)
        )
        local = self.admin.get(f"{API}/ai/settings").json()["local"]
        self.assertEqual(local["speed_test"]["prompt_tokens_per_second"], 80.0)
        self.assertGreater(local["typical_summary"]["seconds"], 0)
        calls = self.admin.get(f"{API}/ai/calls").json()
        self.assertEqual((calls[0]["prompt_per_second"], calls[0]["generation_per_second"]), (80.0, 12.5))
        self.assertTrue(AICall.objects.filter(use="test").exists())
