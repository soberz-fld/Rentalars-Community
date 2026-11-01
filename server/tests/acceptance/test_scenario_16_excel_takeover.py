# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 16 – Übernahme der Excel-Tabelle (catalogue chapter 11)."""

import io
import tempfile
from pathlib import Path
from typing import Any

from django.core.management import call_command
from django.core.management.base import CommandError

from rentalars.material.models import ConnectionType, MaterialItem, MaterialModel
from rentalars.material.services import create_items
from tests.acceptance.test_scenario_08_import import material_rows, workbook
from tests.helpers import RentalarsTestCase

#: IDs of receivers and the rack each of them is installed in ("Einsatz/Verbindung").
INSTALLED = {310: 500, 311: 500, 312: 501, 1650: 1649}


def takeover_rows() -> list[list[Any]]:
    """The existing list: IDs 0001 to 1650 with some references between rows."""
    rows = material_rows(1650)
    for item_id, container_id in INSTALLED.items():
        rows[item_id - 1][5] = f"{container_id:04d}"
    return rows


class Scenario16ExcelTakeover(RentalarsTestCase):
    """IMP-004, IMP-007, IMP-009, IMP-010, MAT-003."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.file = Path(cls.directory.name) / "bestand.xlsx"
        cls.file.write_bytes(workbook(takeover_rows()).getvalue())

    def run_command(self, path: Path, *arguments: str) -> str:
        """Run ``manage.py import_material`` and return what it printed."""
        output = io.StringIO()
        call_command("import_material", str(path), *arguments, stdout=output)
        return output.getvalue()

    def test_dry_run_reports_errors_with_row_number_and_writes_nothing(self) -> None:
        rows = takeover_rows()
        rows[41][0] = "12a"  # row 43 of the file: an ID that is no number
        rows[99][5] = "9999"  # row 101 refers to an ID that does not exist
        broken = Path(self.directory.name) / "kaputt.xlsx"
        broken.write_bytes(workbook(rows).getvalue())
        output = io.StringIO()

        with self.assertRaises(CommandError):
            call_command("import_material", str(broken), stdout=output)

        printed = output.getvalue()
        self.assertIn("43", printed)
        self.assertIn("101", printed)
        self.assertIn("9999", printed)
        self.assertEqual(MaterialItem.objects.count(), 0)

    def test_without_commit_nothing_is_written(self) -> None:
        printed = self.run_command(self.file)

        self.assertIn("1650", printed)
        self.assertEqual(MaterialItem.objects.count(), 0)
        self.assertEqual(MaterialModel.objects.count(), 0)

    def test_items_keep_their_ids_references_are_resolved_and_numbering_continues(self) -> None:
        self.run_command(self.file, "--commit")

        ids = list(MaterialItem.objects.order_by("inventory_number").values_list("inventory_number", flat=True))
        self.assertEqual(ids, list(range(1, 1651)))
        self.assertEqual(MaterialItem.objects.get(inventory_number=1).display_id, "0001")
        self.assertEqual(MaterialItem.objects.get(inventory_number=1650).display_id, "1650")

        for item_id, container_id in INSTALLED.items():
            item = MaterialItem.objects.select_related("installed_in").get(inventory_number=item_id)
            self.assertEqual(item.installed_in.inventory_number, container_id)
            self.assertEqual(item.connection_type, ConnectionType.FIXED)
        self.assertEqual(MaterialItem.objects.filter(installed_in__isnull=False).count(), len(INSTALLED))

        new_item = create_items(MaterialModel.objects.first(), 1)[0]
        self.assertEqual(new_item.display_id, "1651")

    def test_second_run_with_the_same_table_creates_no_duplicates(self) -> None:
        self.run_command(self.file, "--commit")
        models_before = MaterialModel.objects.count()

        printed = self.run_command(self.file, "--commit")

        self.assertEqual(MaterialItem.objects.count(), 1650)
        self.assertEqual(MaterialModel.objects.count(), models_before)
        self.assertIn("1650", printed)
        self.assertEqual(create_items(MaterialModel.objects.first(), 1)[0].display_id, "1651")
