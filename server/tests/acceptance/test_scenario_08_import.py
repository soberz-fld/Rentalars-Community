# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 8 – Import (catalogue chapter 11)."""

import io
from typing import Any

from openpyxl import Workbook

from rentalars.material.importer import IMPORT_FIELDS, import_material, read_table, suggest_mapping
from rentalars.material.models import MaterialItem, MaterialModel
from tests.helpers import RentalarsTestCase

#: The 13 column headings of the material list (MAT-011), as the import knows them.
HEADINGS = [import_field.label for import_field in IMPORT_FIELDS[:13]]

#: Eight article types; every 25 rows the article changes: 8 models for 200 rows.
ARTICLES = [
    ("Cordial CPM 5 FM", "Kabel", "XLR m/f", "5"),
    ("Cordial CPM 10 FM", "Kabel", "XLR m/f", "10"),
    ("Schuko 3G1,5 10 m", "Kabel", "H07RN-F", "10"),
    ("Eurolite LED PAR-64", "Lichttechnik", "RGBW", "120"),
    ("Robe Pointe", "Lichttechnik", "Moving Head", "280"),
    ("Yamaha DXR12", "Tontechnik", "Aktivbox 12 Zoll", ""),
    ("K&M 21460", "Stative", "Boxenstativ", ""),
    ("Global Truss F34 200", "Rigging", "4-Punkt 2 m", ""),
]


def material_rows(count: int = 200) -> list[list[Any]]:
    """Rows of a material list with ``count`` items and consecutive IDs."""
    rows = []
    for number in range(1, count + 1):
        name, category_name, specification, specific = ARTICLES[(number - 1) // 25 % len(ARTICLES)]
        rows.append(
            [
                f"{number:04d}",
                name,
                category_name,
                specification,
                specific,
                "",
                f"SN-{number:05d}",
                "",
                "12.04.2023",
                "Erstausstattung",
                "49,90",
                "Musikhaus Nord",
                f"MN-{number % 7}",
            ]
        )
    return rows


def workbook(rows: list[list[Any]]) -> io.BytesIO:
    """An XLSX file with the 13 headings and the given rows."""
    book = Workbook()
    sheet = book.active
    sheet.append(HEADINGS)
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream


class Scenario08Import(RentalarsTestCase):
    """IMP-002, IMP-003, IMP-009."""

    def run_import(self, rows: list[list[Any]], *, dry_run: bool) -> Any:
        """Read the file, recognise its columns and import it."""
        table = read_table(workbook(rows), "material.xlsx")
        return import_material(table, suggest_mapping(table.headers), dry_run=dry_run, actor="system:test")

    def test_all_thirteen_columns_are_recognised_by_their_headings(self) -> None:
        table = read_table(workbook(material_rows(1)), "material.xlsx")
        mapping = suggest_mapping(table.headers)
        recognised = [import_field.key for import_field in IMPORT_FIELDS[:13] if mapping[import_field.key] is not None]
        self.assertEqual(len(recognised), 13)

    def test_dry_run_reports_what_would_happen_and_writes_nothing(self) -> None:
        report = self.run_import(material_rows(), dry_run=True)

        self.assertTrue(report.ok, [str(error) for error in report.errors])
        self.assertEqual(report.rows_read, 200)
        self.assertEqual(report.items_created, 200)
        self.assertEqual(report.models_created, 8)
        self.assertEqual(MaterialItem.objects.count(), 0)
        self.assertEqual(MaterialModel.objects.count(), 0)

    def test_faulty_rows_are_reported_with_row_number_and_reason(self) -> None:
        rows = material_rows()
        rows[16][0] = "12a"  # row 18 of the file: the ID is not a number
        rows[40][8] = "31.02.2023"  # row 42: this day does not exist – a hint, not an error
        rows[99][10] = "viel"  # row 101: not a price – a hint, too
        rows[150][0] = rows[149][0]  # row 152: the same ID as the row above
        rows[180][1] = ""  # row 182: the article name is missing

        report = self.run_import(rows, dry_run=True)

        self.assertFalse(report.ok)
        self.assertEqual(sorted({error.row for error in report.errors}), [18, 152, 182])
        reasons = {error.row: f"{error.column}: {error.message}" for error in report.errors}
        # IMP-010: an entry that cannot be read is a hint, the item comes in as "Fehler Import".
        hints = {issue.row: f"{issue.column}: {issue.message}" for issue in report.warnings if issue.row}
        self.assertIn("ID", reasons[18])
        self.assertIn("Rechnungsdatum", hints[42])  # MAT-050: the column "Tag des Kaufs" fills it
        self.assertIn("Kaufpreis", hints[101])
        self.assertIn("0150", reasons[152])
        self.assertIn("Artikelname", reasons[182])
        self.assertTrue(all(error.message for error in report.errors))

    def test_one_faulty_row_stops_the_whole_import(self) -> None:
        rows = material_rows()
        rows[40][0] = "12a"  # an ID that is no number: no substitute, so no import at all (a date would be a hint)

        report = self.run_import(rows, dry_run=False)

        self.assertFalse(report.ok)
        self.assertEqual(MaterialItem.objects.count(), 0)
        self.assertEqual(MaterialModel.objects.count(), 0)

    def test_an_unreadable_date_does_not_stop_the_import(self) -> None:
        """The item comes in as "Fehler Import" with the cell in its note; the others are taken over."""
        rows = material_rows()
        rows[40][8] = "31.02.2023"

        report = self.run_import(rows, dry_run=False)

        self.assertTrue(report.ok, [str(error) for error in report.errors])
        self.assertEqual(MaterialItem.objects.count(), 200)
        self.assertEqual(MaterialItem.objects.filter(status="import_error").count(), 1)

    def test_after_the_import_the_expected_models_and_200_items_exist(self) -> None:
        dry = self.run_import(material_rows(), dry_run=True)
        real = self.run_import(material_rows(), dry_run=False)

        self.assertTrue(real.ok, [str(error) for error in real.errors])
        self.assertEqual(MaterialItem.objects.count(), 200)
        self.assertEqual(
            sorted(MaterialModel.objects.values_list("name", flat=True)), sorted(article[0] for article in ARTICLES)
        )
        # The dry run promised exactly what the import did (IMP-009).
        self.assertEqual((dry.items_created, dry.models_created), (real.items_created, real.models_created))
        self.assertEqual(dry.categories_created, real.categories_created)

        cable = MaterialItem.objects.select_related("material_model", "supplier").get(inventory_number=7)
        self.assertEqual(cable.material_model.name, "Cordial CPM 5 FM")
        self.assertEqual(cable.material_model.category.name, "Kabel")
        self.assertEqual(cable.material_model.category_specific_display, "5 m")
        self.assertEqual(cable.serial_number, "SN-00007")
        self.assertEqual(str(cable.purchase_date), "2023-04-12")
        self.assertEqual(str(cable.purchase_price), "49.90")
        self.assertEqual(cable.supplier.name, "Musikhaus Nord")
        self.assertEqual(cable.supplier_article_number, "MN-0")
        self.assertEqual(MaterialItem.objects.filter(material_model__name="Robe Pointe").count(), 25)
