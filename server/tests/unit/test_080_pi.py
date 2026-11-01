# SPDX-License-Identifier: GPL-3.0-or-later
"""Rentalars on a Raspberry Pi (NFA-070).

The installation itself cannot run here: there is no Raspberry Pi and no
Raspberry Pi OS in the test environment. What can be tested is tested:

* how the server scripts recognise the system, the device, the packages, the
  memory and the SD card – with made-up files, by ``tests/deploy/test_system.sh``,
  which this module runs;
* the self-check on a Raspberry Pi: the device, a note on too little memory
  and on data on the SD card – and nothing of that on any other computer.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rentalars.core import selfcheck
from tests.helpers import RentalarsTestCase

ROOT = Path(settings.BASE_DIR)


class ServerScriptsTests(SimpleTestCase):
    """NFA-070, NFA-063, NFA-042: the decisions of deploy/lib.sh, with made-up systems."""

    def test_the_system_detection_with_made_up_systems(self) -> None:
        """Ubuntu on x86 as before; Ubuntu and Raspberry Pi OS on a Raspberry Pi; 32 bit and old systems refused."""
        result = subprocess.run(
            ["bash", str(ROOT / "tests/deploy/test_system.sh")], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed.", result.stdout)

    def test_the_operation_manual_describes_the_raspberry_pi(self) -> None:
        """NFA-047, NFA-070: what to prepare, both systems, what is different."""
        manual = (ROOT / "docs/betrieb/installation.md").read_text(encoding="utf-8")
        section = manual[manual.index("## Raspberry Pi") :]
        for words in ("64 Bit", "4 GB", "SSD", "Raspberry Pi OS", "Ubuntu Server", "Debian 13"):
            self.assertIn(words, section)


def fake_block_devices(folder: Path, device_path: str, number: str) -> Path:
    """A made-up ``/sys/dev/block`` in which the device number ``number`` is the device ``device_path``."""
    sys_block = folder / "sys/dev/block"
    sys_block.mkdir(parents=True, exist_ok=True)
    device = folder / "sys/devices" / device_path
    device.mkdir(parents=True, exist_ok=True)
    (sys_block / number).symlink_to(device)
    return sys_block


def device_number(path: Path) -> str:
    """The device number of the file system of a folder, as ``/sys/dev/block`` names it."""
    number = os.stat(path).st_dev
    return f"{os.major(number)}:{os.minor(number)}"


class SdCardTests(SimpleTestCase):
    """NFA-070: whether a folder lies on an SD card."""

    def test_the_sd_card_an_encrypted_volume_on_it_and_an_ssd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            number = device_number(folder)
            cases = (
                ("platform/emmc2bus/mmc0/block/mmcblk0/mmcblk0p2", True),
                ("platform/usb/block/sda/sda2", False),
                ("pci/nvme/block/nvme0n1/nvme0n1p2", False),
            )
            for device_path, expected in cases:
                with self.subTest(device=device_path):
                    sys_block = fake_block_devices(folder / device_path.replace("/", "-"), device_path, number)
                    with mock.patch.object(selfcheck, "SYS_BLOCK", sys_block):
                        self.assertEqual(selfcheck.on_sd_card(folder), expected)
            # An encrypted volume (dm-0) on a partition of the SD card.
            sys_block = fake_block_devices(folder / "encrypted", "virtual/block/dm-0", number)
            card = folder / "encrypted/sys/devices/platform/mmc0/block/mmcblk0/mmcblk0p3"
            card.mkdir(parents=True)
            (folder / "encrypted/sys/devices/virtual/block/dm-0/slaves").mkdir()
            (folder / "encrypted/sys/devices/virtual/block/dm-0/slaves/mmcblk0p3").symlink_to(card)
            with mock.patch.object(selfcheck, "SYS_BLOCK", sys_block):
                self.assertTrue(selfcheck.on_sd_card(folder))
            # A folder that does not exist, an unknown device: cannot tell, so no.
            self.assertFalse(selfcheck.on_sd_card(folder / "missing"))
            with mock.patch.object(selfcheck, "SYS_BLOCK", folder / "nothing"):
                self.assertFalse(selfcheck.on_sd_card(folder))


class RaspberryPiSelfCheckTests(RentalarsTestCase):
    """NFA-070, NFA-037: the self-check names the Raspberry Pi and what lies on its SD card."""

    def setUp(self) -> None:
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.data_dir = self.folder / "data"
        self.data_dir.mkdir()

    def model_file(self, model: str) -> Path:
        """The model file of the device tree; the firmware ends the name with a zero byte."""
        path = self.folder / "model"
        path.write_bytes(model.encode() + b"\0")
        return path

    def findings(self, model_file: Path, device_path: str) -> dict[str, selfcheck.Finding]:
        """Run the self-check with a made-up device whose data folder lies on ``device_path``."""
        sys_block = fake_block_devices(
            Path(tempfile.mkdtemp(dir=self.folder)), device_path, device_number(self.data_dir)
        )
        with (
            override_settings(DATA_DIR=self.data_dir),
            mock.patch.object(selfcheck, "DEVICE_MODEL", model_file),
            mock.patch.object(selfcheck, "SYS_BLOCK", sys_block),
        ):
            report = selfcheck.run_checks()
        return {finding.title: finding for finding in report.findings}

    def test_a_raspberry_pi_with_its_data_on_the_sd_card(self) -> None:
        findings = self.findings(
            self.model_file("Raspberry Pi 5 Model B Rev 1.0"), "platform/mmc0/block/mmcblk0/mmcblk0p2"
        )
        device = findings[pgettext("self-check", "Device")]
        self.assertTrue(device.detail.startswith("Raspberry Pi 5 Model B Rev 1.0"))
        sd_card = findings[_("SD card")]
        self.assertEqual(sd_card.state, selfcheck.NOTE)
        self.assertEqual(sd_card.group, _("Storage"))
        # The data folder, and no backup written yet. With a local MariaDB its folder lies on the same made-up
        # device in this test (the root file system), so the database is named too.
        places = sd_card.detail.split(":", 1)[1].split(".", 1)[0].strip().split(", ")
        self.assertIn(pgettext("on the SD card", "data folder"), places)
        self.assertNotIn(pgettext("on the SD card", "backups"), places)

    def test_a_raspberry_pi_with_an_ssd(self) -> None:
        findings = self.findings(self.model_file("Raspberry Pi 4 Model B Rev 1.5"), "platform/usb/block/sda/sda2")
        self.assertIn(pgettext("self-check", "Device"), findings)
        self.assertNotIn(_("SD card"), findings)

    def test_any_other_computer_shows_nothing_of_it(self) -> None:
        """Nothing changes on an x86 server – not even with a built-in memory card."""
        for model_file in (self.folder / "missing", self.model_file("Pine64 RockPro64 v2.1")):
            with self.subTest(model=model_file.name):
                findings = self.findings(model_file, "platform/mmc0/block/mmcblk0/mmcblk0p2")
                self.assertNotIn(pgettext("self-check", "Device"), findings)
                self.assertNotIn(_("SD card"), findings)

    def test_a_raspberry_pi_with_less_than_4_gb(self) -> None:
        device = pgettext("self-check", "Device")
        for memory, state in (
            (3_884_292 * 1024, selfcheck.OK),
            (1_893_416 * 1024, selfcheck.NOTE),
            (None, selfcheck.OK),
        ):
            with self.subTest(memory=memory):
                report = selfcheck.Report()
                selfcheck._raspberry_pi(report, "Server", "Raspberry Pi 4 Model B Rev 1.5", memory)
                finding = report.findings[0]
                self.assertEqual((finding.title, finding.state), (device, state))
                self.assertEqual("4 GB" in finding.detail, state == selfcheck.NOTE)
