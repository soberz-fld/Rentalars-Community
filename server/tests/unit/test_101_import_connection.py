# SPDX-License-Identifier: GPL-3.0-or-later
"""IMP-010: "Einsatz/Verbindung" with several IDs or with text – no error, the text goes to the note."""

from __future__ import annotations

from rentalars.material.models import MaterialItem
from tests.helpers import RentalarsTestCase
from tests.unit.test_importer import HEAD, run

RACKS = f"{HEAD};Einsatz/Verbindung\n500;Rack A;Rigging;\n600;Rack B;Rigging;\n"


def item(number: int) -> MaterialItem:
    """The item with this ID."""
    return MaterialItem.objects.get(inventory_number=number)


class ConnectionCellTests(RentalarsTestCase):
    """What a cell of "Einsatz/Verbindung" may hold."""

    def test_one_id_is_still_the_container(self) -> None:
        for cell in ("500", "#0500", "# 500", "500.0"):
            with self.subTest(cell=cell):
                MaterialItem.objects.update(installed_in=None)
                MaterialItem.objects.all().delete()
                report = run(f"{RACKS}310;Empfänger;Ton;{cell}\n")
                self.assertTrue(report.ok, [str(issue) for issue in report.errors])
                self.assertEqual(item(310).installed_in.inventory_number, 500)
                self.assertEqual(report.warnings, [])
                self.assertEqual(item(310).note, "")

    def test_several_ids_are_no_link_but_the_note_and_a_hint(self) -> None:
        report = run(f'{RACKS}310;Netzkabel;Kabel;"#0500, #0600"\n')
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        cable = item(310)
        self.assertIsNone(cable.installed_in)
        self.assertEqual(cable.note, "Einsatz/Verbindung: #0500, #0600")
        hints = [issue for issue in report.warnings if issue.row == 4]
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].column, "Einsatz/Verbindung")
        self.assertIn("#0500, #0600", hints[0].message)
        self.assertEqual(report.installed_links, [])

    def test_text_only_is_no_error_the_note_and_a_hint(self) -> None:
        report = run(f"{RACKS}310;Netzkabel;Kabel;Regal 4 im Lager\n")
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertEqual(item(310).note, "Einsatz/Verbindung: Regal 4 im Lager")
        self.assertIsNone(item(310).installed_in)
        self.assertEqual([issue.row for issue in report.warnings if issue.row], [4])

    def test_an_id_with_remarks_is_not_guessed_at(self) -> None:
        report = run(f"{RACKS}310;Netzkabel;Kabel;#0500, linke Seite\n")
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertIsNone(item(310).installed_in)
        self.assertEqual(item(310).note, "Einsatz/Verbindung: #0500, linke Seite")
        self.assertEqual(report.installed_links, [])
        self.assertEqual(len([issue for issue in report.warnings if issue.row]), 1)

    def test_an_unknown_single_id_is_a_hint_too_since_0_10_2(self) -> None:
        report = run(f"{RACKS}310;Netzkabel;Kabel;#0999\n")
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertIn("0999", next(issue for issue in report.warnings if issue.row).message)
        self.assertEqual(item(310).status, "import_error")
        self.assertEqual(item(310).note, "Einsatz/Verbindung: #0999")

    def test_a_dry_run_says_the_same_and_writes_nothing(self) -> None:
        text = f'{RACKS}310;Netzkabel;Kabel;"#0500, #0600"\n'
        dry = run(text, dry_run=True)
        self.assertEqual(MaterialItem.objects.count(), 0)
        real = run(text)
        self.assertEqual([issue.message for issue in dry.warnings], [issue.message for issue in real.warnings])
        self.assertEqual(real.items_created, 3)

    def test_the_note_is_added_after_the_note_of_the_file_and_only_once(self) -> None:
        text = f"{HEAD};Einsatz/Verbindung;Notiz\n500;Rack A;Rigging;;\n310;Netzkabel;Kabel;Regal 4;Stecker neu\n"
        run(text)
        self.assertEqual(item(310).note, "Stecker neu\nEinsatz/Verbindung: Regal 4")
        again = run(text)
        self.assertEqual(item(310).note, "Stecker neu\nEinsatz/Verbindung: Regal 4")
        self.assertEqual(again.items_unchanged, 2)

    def test_without_a_note_column_the_note_of_the_database_stays_and_grows_once(self) -> None:
        run(f"{HEAD}\n310;Netzkabel;Kabel\n")
        MaterialItem.objects.filter(inventory_number=310).update(note="Eigene Notiz")
        text = f"{HEAD};Einsatz/Verbindung\n310;Netzkabel;Kabel;Regal 4\n"
        run(text)
        self.assertEqual(item(310).note, "Eigene Notiz\nEinsatz/Verbindung: Regal 4")
        run(text)
        self.assertEqual(item(310).note, "Eigene Notiz\nEinsatz/Verbindung: Regal 4")

    def test_a_link_that_exists_stays_when_the_cell_is_unclear(self) -> None:
        run(f"{RACKS}310;Netzkabel;Kabel;500\n")
        run(f'{RACKS}310;Netzkabel;Kabel;"#0500, #0600"\n')
        self.assertEqual(item(310).installed_in.inventory_number, 500)
        run(f"{RACKS}310;Netzkabel;Kabel;\n")  # an empty cell removes it, as before
        self.assertIsNone(item(310).installed_in)

    def test_the_semicolon_and_line_break_separate_too(self) -> None:
        report = run(f'{RACKS}310;Netzkabel;Kabel;"#0500\n#0600"\n')
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertIsNone(item(310).installed_in)
        self.assertIn("#0500", item(310).note)

    def test_a_decimal_comma_is_no_pair_of_ids_that_breaks_anything(self) -> None:
        report = run(f'{RACKS}310;Netzkabel;Kabel;"1,5 m"\n')
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertIsNone(item(310).installed_in)
        self.assertEqual(item(310).note, "Einsatz/Verbindung: 1,5 m")

    def test_a_huge_number_is_text_not_a_crash(self) -> None:
        report = run(f"{RACKS}310;Empfänger;Ton;99999999999999999999999999999\n")
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertIsNone(item(310).installed_in)
        self.assertIn("99999999999999999999999999999", item(310).note)

    def test_a_decimal_comma_does_not_claim_to_name_several_items(self) -> None:
        report = run(f'{RACKS}310;Empfänger;Ton;"1,5"\n')
        hints = [issue for issue in report.warnings if issue.row]
        self.assertEqual(len(hints), 1)
        self.assertNotIn("names several", hints[0].message)

    def test_a_changed_text_is_a_new_line_and_a_prefix_is_not_taken_for_the_same(self) -> None:
        run(f"{RACKS}310;Empfänger;Ton;Regal 41\n")
        run(f"{RACKS}310;Empfänger;Ton;Regal 4\n")
        self.assertEqual(item(310).note.splitlines(), ["Einsatz/Verbindung: Regal 41", "Einsatz/Verbindung: Regal 4"])
        run(f"{RACKS}310;Empfänger;Ton;Regal 4\n")
        self.assertEqual(len(item(310).note.splitlines()), 2)
