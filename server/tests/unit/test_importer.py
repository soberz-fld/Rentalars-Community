# SPDX-License-Identifier: GPL-3.0-or-later
"""The material import in its details (IMP-002 to IMP-012)."""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from openpyxl import Workbook

from rentalars.masterdata.models import Category, Manufacturer, StorageLocation
from rentalars.material.importer import (
    ImportFileError,
    Table,
    import_material,
    read_table,
    resolve_mapping,
    suggest_mapping,
)
from rentalars.material.models import ConnectionType, MaterialItem, MaterialModel
from tests.helpers import RentalarsTestCase, make_product


def table(text: str) -> Table:
    """Read CSV text (semicolon-separated) as an import table."""
    return read_table(io.BytesIO(text.encode("utf-8")), "material.csv")


def run(text: str, *, dry_run: bool = False, **overrides: Any) -> Any:
    """Import CSV text and return the report."""
    data = table(text)
    return import_material(data, resolve_mapping(data.headers, overrides), dry_run=dry_run, actor="system:test")


HEAD = "ID;Artikelname;Kategorie"


class ReadingTests(RentalarsTestCase):
    """Reading files (IMP-007)."""

    def test_csv_separator_and_encoding_are_detected(self) -> None:
        comma = read_table(io.BytesIO(b"ID,Artikelname,Kategorie\n1,Kabel,Kabel\n"), "a.csv")
        self.assertEqual(comma.headers, ["ID", "Artikelname", "Kategorie"])
        windows = read_table(io.BytesIO("ID;Artikelname;Kategorie\n1;Verlängerung;Kabel\n".encode("cp1252")), "a.csv")
        self.assertEqual(windows.rows[0][1], "Verlängerung")
        with_mark = read_table(io.BytesIO("﻿ID;Artikelname;Kategorie\n1;Kabel;Kabel\n".encode()), "a.csv")
        self.assertEqual(with_mark.headers[0], "ID")

    def test_empty_rows_are_skipped_but_row_numbers_follow_the_file(self) -> None:
        data = table(f"{HEAD}\n1;Kabel;Kabel\n;;\n\n3;Kabel;Kabel\n")
        self.assertEqual(len(data.rows), 2)
        self.assertEqual(data.row_numbers, [2, 5])

    def test_worksheet_can_be_chosen(self) -> None:
        book = Workbook()
        book.active.title = "Notizen"
        book.active.append(["nur Text"])
        sheet = book.create_sheet("Bestand")
        sheet.append(["ID", "Artikelname", "Kategorie"])
        sheet.append([1, "Kabel", "Kabel"])
        stream = io.BytesIO()
        book.save(stream)
        self.assertEqual(read_table(io.BytesIO(stream.getvalue()), "a.xlsx", sheet="Bestand").headers[0], "ID")
        with self.assertRaisesRegex(ImportFileError, "Bestand"):
            read_table(io.BytesIO(stream.getvalue()), "a.xlsx", sheet="Fehlt")

    def test_unreadable_files_are_refused_with_a_reason(self) -> None:
        with self.assertRaises(ImportFileError):
            read_table(io.BytesIO(b"kein Excel"), "a.xlsx")
        with self.assertRaises(ImportFileError):
            read_table(io.BytesIO(b"x"), "a.pdf")
        with self.assertRaises(ImportFileError):
            read_table(io.BytesIO(b"\n\n"), "a.csv")


class RowLimitTests(RentalarsTestCase):
    """A request is ended after two minutes; long lists go through the command on the server (IMP-007)."""

    TEXT = "ID;Artikelname;Kategorie\n" + "".join(f"{number};Kabel;Kabel\n" for number in range(1, 5))

    def test_a_file_with_more_rows_than_allowed_is_refused_with_the_way_out(self) -> None:
        with self.assertRaises(ImportFileError) as refused:
            read_table(io.BytesIO(self.TEXT.encode()), "a.csv", max_rows=3)
        message = str(refused.exception)
        self.assertIn("4", message)
        self.assertIn("3", message)
        self.assertIn("rentalars import_material", message)

    def test_the_heading_row_and_empty_rows_do_not_count(self) -> None:
        text = self.TEXT.replace("2;Kabel;Kabel\n", "2;Kabel;Kabel\n;;\n")
        self.assertEqual(len(read_table(io.BytesIO(text.encode()), "a.csv", max_rows=4).rows), 4)

    def test_without_a_limit_every_length_is_read(self) -> None:
        """What the command on the server does."""
        self.assertEqual(len(read_table(io.BytesIO(self.TEXT.encode()), "a.csv").rows), 4)


class MappingTests(RentalarsTestCase):
    """Column mapping (IMP-003)."""

    def test_headings_are_recognised_whatever_their_case_and_spacing(self) -> None:
        mapping = suggest_mapping(
            ["  id ", "ARTIKELNAME\n(evtl. gekürzt)", "Kategorie", "Gekauft (Händler)", "Unbekannt"]
        )
        self.assertEqual(
            (mapping["inventory_number"], mapping["name"], mapping["category"], mapping["supplier"]), (0, 1, 2, 3)
        )
        self.assertIsNone(mapping["serial_number"])

    def test_overrides_by_heading_by_number_and_removal(self) -> None:
        headers = ["Inv.-Nr.", "Gerät", "Kategorie", "Notiz"]
        mapping = resolve_mapping(headers, {"inventory_number": "Inv.-Nr.", "name": 1, "note": ""})
        self.assertEqual((mapping["inventory_number"], mapping["name"], mapping["note"]), (0, 1, None))
        with self.assertRaisesRegex(ImportFileError, "Spalte"):
            resolve_mapping(headers, {"name": "Gibt es nicht"})
        with self.assertRaisesRegex(ImportFileError, "nonsense"):
            resolve_mapping(headers, {"nonsense": "Gerät"})

    def test_missing_required_column_is_reported_before_anything_else(self) -> None:
        report = run("ID;Artikelname\n1;Kabel\n")
        self.assertFalse(report.ok)
        self.assertEqual([(issue.row, issue.column) for issue in report.errors], [(None, "Kategorie")])


class WritingTests(RentalarsTestCase):
    """What the import creates and updates (IMP-002, IMP-004, IMP-008, IMP-010, IMP-012)."""

    def test_categories_are_found_by_name_code_or_path_and_created_when_missing(self) -> None:
        report = run(
            f"{HEAD}\n1;Cordial CPM 5;Kabel\n2;Yamaha DXR12;T\n3;Shure SM58;Ton > Mikrofone\n4;Ender 3;3D-Druck\n5;Prusa MK4;3D-Druck\n"
        )
        self.assertTrue(report.ok, [str(error) for error in report.errors])
        self.assertEqual(MaterialModel.objects.get(name="Cordial CPM 5").category.code, "K")
        self.assertEqual(MaterialModel.objects.get(name="Yamaha DXR12").category.code, "T")
        microphones = MaterialModel.objects.get(name="Shure SM58").category
        self.assertEqual((microphones.name, microphones.parent.code), ("Mikrofone", "T"))
        printing = Category.objects.get(name="3D-Druck")
        # "D" is taken by services, so the code grows by one letter of the name.
        self.assertEqual(printing.code, "DD")
        self.assertEqual(report.categories_created, ["Ton > Mikrofone", "3D-Druck (DD)"])

    def test_a_slash_in_the_name_of_a_main_category(self) -> None:
        # The default categories have names like "Video/Medien" (ADM-011).
        video, _created = Category.objects.get_or_create(name="Video/Medien", parent=None, defaults={"code": "M"})
        report = run(f"{HEAD}\n1;Beamer 1;Video/Medien\n2;Beamer 2;video / medien / Beamer\n3;SM58;Ton/Mikrofone\n")
        self.assertTrue(report.ok, [str(error) for error in report.errors])
        self.assertEqual(MaterialModel.objects.get(name="Beamer 1").category, video)
        projectors = MaterialModel.objects.get(name="Beamer 2").category
        self.assertEqual((projectors.name, projectors.parent), ("Beamer", video))
        self.assertEqual(MaterialModel.objects.get(name="SM58").category.parent.code, "T")
        self.assertEqual(report.categories_created, ["Video/Medien > Beamer", "Ton > Mikrofone"])

    def test_optional_columns(self) -> None:
        product = make_product("K-005")
        report = run(
            "ID;Artikelname;Kategorie;Hersteller;Kurzname;Menge;Status;Lagerort;Produkt\n"
            "1;Cordial CPM 5 FM;Kabel;Cordial;CPM5;;defekt;Halle 1;K-005\n"
            "2;Gaffa schwarz 50 m;Verkauf;;;40;;Halle 1;\n"
            "3;Unbekanntes Teil;Sonstiges;;;;;;Z-999\n"
        )
        self.assertTrue(report.ok, [str(error) for error in report.errors])
        cable = MaterialItem.objects.select_related("material_model").get(inventory_number=1)
        self.assertEqual(cable.material_model.manufacturer, Manufacturer.objects.get(name="Cordial"))
        self.assertEqual(cable.material_model.short_name, "CPM5")
        self.assertEqual(cable.material_model.default_product, product)
        self.assertEqual(cable.status, "defective")
        self.assertEqual(cable.storage_location, StorageLocation.objects.get(name="Halle 1"))
        tape = MaterialItem.objects.select_related("material_model").get(inventory_number=2)
        self.assertTrue(tape.material_model.is_bulk)
        self.assertEqual(tape.quantity, 40)
        self.assertEqual([issue.row for issue in report.warnings], [4])
        self.assertIn("Z-999", report.warnings[0].message)
        self.assertEqual(report.manufacturers_created, ["Cordial"])

    def test_wrong_optional_values_are_hints_with_row_and_column(self) -> None:
        """A cell of an optional field that cannot be read is a hint, not an error: the item is flagged."""
        report = run(
            "ID;Artikelname;Kategorie;Menge;Status;Einsatz/Verbindung\n1;Kabel;Kabel;viele;kaputt;Rack\n", dry_run=True
        )
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertEqual(
            sorted((issue.row, issue.column) for issue in report.warnings if issue.row),
            [(2, "Einsatz/Verbindung"), (2, "Menge (Mengenmaterial)"), (2, "Status")],
        )
        self.assertEqual(report.items_flagged, 1)

    def test_category_specific_value_that_does_not_fit_is_kept_with_a_note(self) -> None:
        report = run(f"{HEAD};Kategoriespezifische Angabe\n1;Cordial CPM 5;Kabel;fünf Meter\n")
        self.assertTrue(report.ok)
        self.assertEqual(len(report.warnings), 1)
        self.assertEqual(MaterialModel.objects.get().field_values["unassigned"], "fünf Meter")

    def test_same_article_name_with_two_categories_is_pointed_out(self) -> None:
        report = run(f"{HEAD}\n1;Cordial CPM 5;Kabel\n2;Cordial CPM 5;Ton\n")
        self.assertTrue(report.ok)
        self.assertEqual(MaterialModel.objects.count(), 1)
        self.assertEqual([issue.row for issue in report.warnings], [3])

    def test_second_run_updates_changed_rows_only(self) -> None:
        """IMP-004: items are found by their ID."""
        first = f"{HEAD};Notiz;Seriennummer\n1;Cordial CPM 5;Kabel;;SN-1\n2;Cordial CPM 5;Kabel;;SN-2\n"
        run(first)
        second = f"{HEAD};Notiz;Seriennummer\n1;Cordial CPM 5;Kabel;Stecker neu;SN-1\n2;Cordial CPM 5;Kabel;;SN-2\n3;Cordial CPM 5;Kabel;;SN-3\n"
        report = run(second)
        self.assertEqual((report.items_created, report.items_updated, report.items_unchanged), (1, 1, 1))
        self.assertEqual((report.models_created, report.models_updated), (0, 0))
        self.assertEqual(MaterialItem.objects.get(inventory_number=1).note, "Stecker neu")
        self.assertEqual(report.next_id, "0004")

    def test_installed_in_becomes_fixed_and_is_listed_for_review(self) -> None:
        """IMP-010."""
        report = run(
            f"{HEAD};Einsatz/Verbindung\n500;Rack 6 HE;Rigging;\n310;Funkempfänger;Ton;500\n311;Funkempfänger;Ton;0500\n"
        )
        self.assertTrue(report.ok, [str(error) for error in report.errors])
        self.assertEqual(report.installed_links, ["0310 → 0500", "0311 → 0500"])
        receiver = MaterialItem.objects.get(inventory_number=310)
        self.assertEqual(
            (receiver.installed_in.inventory_number, receiver.connection_type), (500, ConnectionType.FIXED)
        )

    def test_connection_type_changed_by_hand_survives_the_next_import(self) -> None:
        """IMP-012."""
        text = f"{HEAD};Einsatz/Verbindung\n500;Rack 6 HE;Rigging;\n310;Funkempfänger;Ton;500\n"
        run(text)
        MaterialItem.objects.filter(inventory_number=310).update(connection_type=ConnectionType.LOOSE)
        report = run(text)
        self.assertEqual(report.installed_links, [])
        self.assertEqual(MaterialItem.objects.get(inventory_number=310).connection_type, ConnectionType.LOOSE)

    def test_removed_reference_removes_the_link(self) -> None:
        run(f"{HEAD};Einsatz/Verbindung\n500;Rack 6 HE;Rigging;\n310;Funkempfänger;Ton;500\n")
        run(f"{HEAD};Einsatz/Verbindung\n500;Rack 6 HE;Rigging;\n310;Funkempfänger;Ton;\n")
        self.assertIsNone(MaterialItem.objects.get(inventory_number=310).installed_in)

    def test_references_may_point_to_items_already_in_the_database(self) -> None:
        run(f"{HEAD}\n500;Rack 6 HE;Rigging\n")
        report = run(f"{HEAD};Einsatz/Verbindung\n310;Funkempfänger;Ton;500\n")
        self.assertTrue(report.ok, [str(error) for error in report.errors])
        self.assertEqual(MaterialItem.objects.get(inventory_number=310).installed_in.inventory_number, 500)

    def test_circles_and_self_references_are_flagged_not_linked(self) -> None:
        """A circle or an item in itself is no error: both items come in, flagged, without a link."""
        circle = run(f"{HEAD};Einsatz/Verbindung\n1;Rack A;Rigging;2\n2;Rack B;Rigging;1\n")
        self.assertTrue(circle.ok, [str(issue) for issue in circle.errors])
        self.assertEqual(MaterialItem.objects.filter(installed_in__isnull=False).count(), 0)
        self.assertEqual(set(MaterialItem.objects.values_list("status", flat=True)), {"import_error"})
        MaterialItem.objects.all().delete()
        itself = run(f"{HEAD};Einsatz/Verbindung\n1;Rack A;Rigging;1\n")
        self.assertTrue(itself.ok)
        self.assertEqual([issue.row for issue in itself.warnings if issue.row], [2])
        self.assertEqual(MaterialItem.objects.get().status, "import_error")

    def test_repeated_import_follows_the_file_only_for_the_columns_it_has(self) -> None:
        """IMP-004, IMP-012: the list can be imported again without losing what was added since."""
        run(f"{HEAD};Seriennummer;Kaufpreis;Notiz\n310;Funkempfänger;Ton;SN-1;499,00;aus Erstbestand\n")
        item = MaterialItem.objects.get(inventory_number=310)
        item.status, item.status_reason = "defective", "Antennenbuchse lose"
        item.save()

        # The list comes again without the column of serial numbers, with an emptied note and a new price.
        report = run(f"{HEAD};Kaufpreis;Notiz\n310;Funkempfänger;Ton;520,00;\n")

        self.assertTrue(report.ok)
        self.assertEqual((report.items_created, report.items_updated), (0, 1))
        item.refresh_from_db()
        self.assertEqual(item.serial_number, "SN-1")  # no column: untouched
        self.assertEqual(item.note, "")  # column with an empty cell: emptied
        self.assertEqual(item.purchase_price, Decimal("520.00"))
        self.assertEqual(item.status, "defective")  # maintained in Rentalars, not in the list

        # A column switched off by hand counts as "no column".
        run(f"{HEAD};Kaufpreis;Notiz\n310;Funkempfänger;Ton;;neu\n", purchase_price="")
        item.refresh_from_db()
        self.assertEqual((item.purchase_price, item.note), (Decimal("520.00"), "neu"))

    def test_one_dry_run_lists_every_problem_of_the_file(self) -> None:
        """IMP-009: nobody should have to run the import once per mistake.

        Row 3 has two mistakes of its own *and* points to an ID that does not
        exist; row 4 points nowhere as well. All four problems are reported
        together, in the order of the rows – as hints: the items come in, flagged.
        """
        report = run(
            f"{HEAD};Einsatz/Verbindung;Kaufpreis;Tag des Kaufs\n"
            "500;Rack 6 HE;Rigging;;1250,00;12.03.2021\n"
            "310;Funkempfänger;Ton;9999;neun;32.13.2019\n"
            "311;Funkempfänger;Ton;8888;499,00;2021\n",
            dry_run=True,
        )
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        problems = [(issue.row, issue.column) for issue in report.warnings if issue.row]
        self.assertEqual(
            sorted(problems),
            # MAT-050: the column "Tag des Kaufs" fills the field "Rechnungsdatum".
            [(3, "Einsatz/Verbindung"), (3, "Kaufpreis"), (3, "Rechnungsdatum"), (4, "Einsatz/Verbindung")],
        )
        self.assertEqual(report.items_flagged, 2)
        self.assertEqual(MaterialItem.objects.count(), 0)  # a dry run writes nothing

    def test_import_is_recorded_in_the_change_log_with_the_actor(self) -> None:
        from rentalars.core.models import AuditLogEntry

        run(f"{HEAD}\n1;Kabel;Kabel\n")
        event = AuditLogEntry.objects.get(event="import.material")
        self.assertEqual(event.actor_label, "system:test")
        self.assertEqual(event.changes["created"], 1)
        created = AuditLogEntry.objects.filter(content_type__model="materialitem", action="created").get()
        self.assertEqual(created.actor_label, "system:test")

    def test_dry_run_leaves_no_trace_at_all(self) -> None:
        from rentalars.core.models import AuditLogEntry, NumberRange, NumberRangeKey

        before = (
            AuditLogEntry.objects.count(),
            Category.objects.count(),
            NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value,
        )
        report = run(f"{HEAD};Hersteller\n1650;Ender 3;3D-Druck;Creality\n", dry_run=True)
        self.assertTrue(report.ok)
        self.assertEqual(report.next_id, "1651")
        after = (
            AuditLogEntry.objects.count(),
            Category.objects.count(),
            NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value,
        )
        self.assertEqual(before, after)
        self.assertFalse(Manufacturer.objects.exists())
