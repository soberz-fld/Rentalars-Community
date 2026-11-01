# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "ai" (EML-040): Einstellungen → KI with processor, measured speeds and the recommendation; the
estimate before "Zusammenfassen"; what a running summary or draft is doing."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import override_settings
from django.urls import reverse

from rentalars.ai.models import AISettings, Source
from rentalars.core.models import BackgroundJob, JobStatus
from tests.ai_fake import write_local_file
from tests.mailbox import configure_mailbox
from tests.ui.test_083_ai_pages import AIPagesTestCase
from tests.unit.test_083_ai import add_mail
from tests.unit.test_084_ai import HOST_CPUINFO, PROXMOX_CPUINFO


class CpuFileMixin:
    """A made-up /proc/cpuinfo for the settings page."""

    def cpuinfo(self, text: str) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)  # type: ignore[attr-defined]
        (folder / "cpuinfo").write_text(text)
        override = override_settings(RENTALARS_AI_CPUINFO=str(folder / "cpuinfo"))
        override.enable()
        self.addCleanup(override.disable)  # type: ignore[attr-defined]


def measured(reading: float | None, writing: float, model: str = "") -> None:
    """The local AI as measured: reading and writing in tokens per second."""
    AISettings.load()
    AISettings.objects.filter(pk=1).update(
        local_test_prompt_per_second=reading, local_test_tokens_per_second=writing, local_test_model=model
    )


class SettingsPageTests(CpuFileMixin, AIPagesTestCase):
    """EML-040: processor, speeds, the typical summary and the recommendation on Einstellungen → KI."""

    def test_the_users_virtual_machine(self) -> None:
        """EML-040: no AVX2/FMA in a VM – the Proxmox hint and the command for the smaller model."""
        self.cpuinfo(PROXMOX_CPUINFO)
        write_local_file(self.local_file, self.fake.url, model="qwen3-4b")
        measured(5, 1.5, "qwen3-4b")
        text = self.assert_ok(self.client.get(reverse("ai:settings")))
        self.assertIn("QEMU Virtual CPU version 2.5+", text)
        self.assertIn("4 physische Kerne, 4 logische", text)
        self.assertIn("virtuelle Maschine", text)
        self.assertIn("ohne AVX2, FMA", text)
        self.assertIn("Prozessortyp auf „host“ stellen, z. B. in Proxmox", text)
        self.assertIn("sudo rentalars ai install --model qwen3-1.7b", text)
        self.assertIn("liest 5,0, schreibt 1,5 Token pro Sekunde", text)
        self.assertIn("Eine Zusammenfassung von etwa 20 Mails dauert damit etwa", text)
        self.assertIn("3 Threads – einer je physischem Kern", text)

    def test_a_fast_server_needs_no_advice(self) -> None:
        """EML-040: AVX2 and FMA, fast enough – no recommendation."""
        self.cpuinfo(HOST_CPUINFO)
        self.install_local()
        measured(300, 25)
        text = self.assert_ok(self.client.get(reverse("ai:settings")))
        self.assertIn("AVX2 und FMA", text)
        self.assertIn("4 physische Kerne, 8 logische", text)
        self.assertNotIn("sudo rentalars ai install --model", text)

    def test_the_hint_comes_before_installing(self) -> None:
        """EML-040: the processor is checked before anything is installed."""
        self.cpuinfo(PROXMOX_CPUINFO)
        text = self.assert_ok(self.client.get(reverse("ai:settings")))
        self.assertIn("nicht installiert", text)
        self.assertIn("Prozessortyp auf „host“", text)
        self.assertIn("sudo rentalars ai install --model qwen3-1.7b", text)

    def test_the_speed_test_reports_reading_and_writing(self) -> None:
        """EML-040: the message names both speeds; the page keeps them."""
        self.cpuinfo(HOST_CPUINFO)
        self.install_local()
        response = self.client.post(reverse("ai:local_speed_test"), follow=True)
        self.assertIn("Sie liest 80,0 und schreibt 12,5 Token pro Sekunde.", " ".join(self.messages_of(response)))
        ai_settings = AISettings.load()
        self.assertEqual(
            (ai_settings.local_test_prompt_per_second, ai_settings.local_test_tokens_per_second), (80.0, 12.5)
        )


class SummaryEstimateTests(AIPagesTestCase):
    """EML-040: before "Zusammenfassen" the page says how long it will take."""

    def setUp(self) -> None:
        super().setUp()
        self.install_local()
        self.use("summary", Source.LOCAL)
        self.url = reverse("ai:summary", args=[self.project.pk])

    def test_unknown_before_a_measurement(self) -> None:
        text = self.assert_ok(self.htmx("get", self.url))
        self.assertIn("Wie lange eine Zusammenfassung dauert, ist noch nicht bekannt", text)

    def test_a_short_one(self) -> None:
        measured(300, 25)
        text = self.assert_ok(self.htmx("get", self.url))
        self.assertIn("Die Zusammenfassung dauert etwa 1 Minute.", text)

    def test_a_long_one_is_warned_about(self) -> None:
        """EML-040: a slow virtual machine – several minutes, with the remedy."""
        measured(5, 1.5)
        for day in range(3, 9):
            add_mail(self.project, f"Tag {day}", "Bühne und Licht wie besprochen. " * 30, days=day)
        text = self.assert_ok(self.htmx("get", self.url))
        self.assertIn("– lange. Du kannst inzwischen weiterarbeiten; ein kleineres Modell", text)

    def test_a_running_summary_says_what_it_does(self) -> None:
        """EML-040: "schreibt … 120 Wörter" while it runs."""
        BackgroundJob.objects.create(
            kind="ai_summary",
            title="Zusammenfassung",
            params={"project": self.project.pk},
            status=JobStatus.RUNNING,
            progress=60,
            message="schreibt … 120 Wörter",
            created_by=self.admin_user,
        )
        text = self.assert_ok(self.htmx("get", self.url))
        self.assertIn("schreibt … 120 Wörter", text)
        self.assertNotIn("Die Zusammenfassung dauert etwa", text)


class DraftProgressTests(AIPagesTestCase):
    """EML-040: a running draft says what it does."""

    def test_the_message_of_a_running_draft(self) -> None:
        configure_mailbox()
        self.use("draft", Source.LOCAL)
        job = BackgroundJob.objects.create(
            kind="ai_draft",
            title="Entwurf",
            params={"project": self.project.pk},
            status=JobStatus.RUNNING,
            message="schreibt … 40 Wörter",
            created_by=self.admin_user,
        )
        text = self.assert_ok(self.htmx("get", reverse("ai:draft_job", args=[self.project.pk, job.pk])))
        self.assertIn("schreibt … 40 Wörter", text)
