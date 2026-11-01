# SPDX-License-Identifier: GPL-3.0-or-later
"""NFA-015: a deleted file stays a week in ``media/.deleted`` so that a backup is consistent."""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from rentalars.core.files import TRASH, KeepDeletedStorage, purge_deleted


class KeepDeletedTests(TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        override = override_settings(MEDIA_ROOT=self.root)
        override.enable()
        self.addCleanup(override.disable)

    def test_the_default_storage_keeps_what_is_deleted(self) -> None:
        self.assertIsInstance(default_storage, KeepDeletedStorage)

    def test_a_deleted_file_is_gone_for_the_application_but_kept(self) -> None:
        name = default_storage.save("incoming/2027/rechnung.pdf", ContentFile(b"%PDF original"))
        default_storage.delete(name)
        self.assertFalse(default_storage.exists(name))
        kept = list((self.root / TRASH).rglob("rechnung*.pdf"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_bytes(), b"%PDF original")
        self.assertIn("incoming/2027", kept[0].as_posix())

    def test_the_same_name_deleted_twice_on_a_day_keeps_both(self) -> None:
        for content in (b"eins", b"zwei"):
            default_storage.save("a/datei.txt", ContentFile(content))
            default_storage.delete("a/datei.txt")
        kept = sorted(path.read_bytes() for path in (self.root / TRASH).rglob("datei*"))
        self.assertEqual(kept, [b"eins", b"zwei"])

    def test_a_name_that_is_not_there_does_no_harm(self) -> None:
        default_storage.delete("gibt/es/nicht.pdf")

    def test_purge_removes_only_old_days(self) -> None:
        today = datetime.date(2027, 3, 20)
        for day in ("2027-03-01", "2027-03-15", "2027-03-20"):
            folder = self.root / TRASH / day
            folder.mkdir(parents=True)
            (folder / "x.txt").write_text(day)
        (self.root / TRASH / "keine-datum").mkdir()
        self.assertEqual(purge_deleted(today=today), 1)
        left = sorted(path.name for path in (self.root / TRASH).iterdir())
        self.assertEqual(left, ["2027-03-15", "2027-03-20", "keine-datum"])
