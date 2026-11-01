# SPDX-License-Identifier: GPL-3.0-or-later
"""IMP-010, MAT-020: an item with entries the import cannot take over comes in as "import error"."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from rentalars.material import services
from rentalars.material.forms import BulkEditForm, ItemCreateForm
from rentalars.material.models import ItemStatus, MaterialItem
from tests.helpers import RentalarsTestCase, make_items, make_model, make_product
from tests.unit.test_importer import HEAD, run


def item(number: int) -> MaterialItem:
    """The item with this ID."""
    return MaterialItem.objects.get(inventory_number=number)


class FlaggedImportTests(RentalarsTestCase):
    """What happens to a row with a cell that cannot be taken over."""

    def test_unreadable_values_are_noted_under_the_heading_of_the_file(self) -> None:
        report = run(
            f"{HEAD};Kaufdatum;Kaufpreis;Schutzklasse\n"
            "310;Empfänger;Ton;32.13.2019;neun;V\n"
            "311;Sender;Ton;12.03.2021;499,00;II\n"
        )
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        broken, fine = item(310), item(311)
        self.assertEqual(broken.status, ItemStatus.IMPORT_ERROR)
        self.assertEqual(
            sorted(broken.note.splitlines()), ["Kaufdatum: 32.13.2019", "Kaufpreis: neun", "Schutzklasse: V"]
        )  # the headings of the file
        self.assertIsNone(broken.purchase_price)
        self.assertEqual(fine.status, ItemStatus.AVAILABLE)
        self.assertEqual(fine.purchase_price, Decimal("499.00"))
        self.assertEqual(report.items_flagged, 1)
        self.assertEqual(report.warnings[-1].row, None)  # the summary

    def test_a_flagged_item_is_not_fit_for_rental(self) -> None:
        run(f"{HEAD};Menge\n310;Empfänger;Ton;viele\n")
        flagged = item(310)
        self.assertFalse(flagged.is_operational)
        self.assertNotIn(flagged, MaterialItem.objects.operational())
        self.assertEqual(flagged.status_reason, gettext("taken over from the import with problems"))

    def test_an_unreadable_cell_leaves_the_stored_value_alone(self) -> None:
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;499,00\n")
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n")
        self.assertEqual(item(310).purchase_price, Decimal("499.00"))
        self.assertEqual(item(310).status, ItemStatus.IMPORT_ERROR)

    def test_the_same_list_again_adds_no_second_line(self) -> None:
        text = f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n"
        run(text)
        run(text)
        self.assertEqual(item(310).note, "Kaufpreis: neun")

    def test_a_clean_row_releases_the_item(self) -> None:
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n")
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;9,00\n")
        self.assertEqual(item(310).status, ItemStatus.AVAILABLE)
        self.assertEqual(item(310).purchase_price, Decimal("9.00"))
        self.assertEqual(item(310).note, "Kaufpreis: neun")  # the earlier line stays

    def test_an_item_that_is_not_rentable_anyway_keeps_its_status(self) -> None:
        """A blocked item is not released nor degraded – the problem only goes into the note."""
        run(f"{HEAD};Status;Kaufpreis\n310;Empfänger;Ton;gesperrt;neun\n")
        self.assertEqual(item(310).status, ItemStatus.BLOCKED)
        self.assertEqual(item(310).note.splitlines(), ["Kaufpreis: neun"])
        run(f"{HEAD};Status;Kaufpreis\n310;Empfänger;Ton;gesperrt;9,00\n")
        self.assertEqual(item(310).status, ItemStatus.BLOCKED)  # a clean row does not make it rentable

    def test_the_note_of_the_file_comes_first(self) -> None:
        run(f"{HEAD};Notiz;Kaufpreis\n310;Empfänger;Ton;aus Erstbestand;neun\n")
        self.assertEqual(item(310).note.splitlines(), ["aus Erstbestand", "Kaufpreis: neun"])

    def test_a_file_exported_with_the_status_is_read(self) -> None:
        report = run(f"{HEAD};Status\n310;Empfänger;Ton;Fehler Import\n")
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertEqual(item(310).status, ItemStatus.AVAILABLE)  # only the import sets the status itself

    def test_a_link_that_would_close_a_circle_is_a_hint(self) -> None:
        run(f"{HEAD};Einsatz/Verbindung\n1;A;Rigging;\n2;B;Rigging;1\n")
        report = run(f"{HEAD};Einsatz/Verbindung\n1;A;Rigging;2\n2;B;Rigging;1\n")
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        self.assertEqual(item(1).status, ItemStatus.IMPORT_ERROR)
        self.assertEqual(item(1).note, "Einsatz/Verbindung: 2")
        self.assertEqual(item(2).installed_in.inventory_number, 1)  # the link that existed stays

    def test_the_key_fields_are_still_errors(self) -> None:
        report = run(f"{HEAD}\n;Empfänger;Ton\n310;;Ton\n311;Sender;\n", dry_run=True)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.errors), 3)

    def test_the_quantity_of_a_former_bulk_item_is_not_a_confusing_error(self) -> None:
        """ "quantity: Individual items always have the quantity 1." although "Menge" is not imported."""
        run(f"{HEAD};Menge\n310;Gaffa;Kabel;5\n")
        self.assertEqual(item(310).quantity, 5)
        # The list comes again without a column of quantities and with another article name: an individual item.
        report = run(f"{HEAD}\n310;Gaffa Tape schwarz;Kabel\n")
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        hints = [issue for issue in report.warnings if issue.row and issue.column == "Menge (Mengenmaterial)"]
        self.assertEqual(len(hints), 1)
        # The other article name moves the item to another model – a hint of its own, not a quantity error.
        self.assertEqual(len([i for i in report.warnings if i.row and i.column == "Artikelname"]), 1)
        self.assertEqual(hints[0].column, "Menge (Mengenmaterial)")
        self.assertIn("5", hints[0].message)
        self.assertNotIn("quantity:", hints[0].message)
        self.assertEqual(item(310).quantity, 1)
        self.assertEqual(item(310).note, "Menge (Mengenmaterial): 5")
        self.assertEqual(item(310).status, ItemStatus.IMPORT_ERROR)


class NotSelectableTests(RentalarsTestCase):
    """Nobody chooses "import error"; only the import reaches it."""

    def setUp(self) -> None:
        super().setUp()
        self.item = make_items(make_model("Kabel", make_product("K-005")))[0]

    def test_not_among_the_statuses_to_choose(self) -> None:
        self.assertNotIn(ItemStatus.IMPORT_ERROR, [value for value, _label in self.item.selectable_statuses])
        self.assertNotIn(
            ItemStatus.IMPORT_ERROR, [value for value, _label in ItemCreateForm.base_fields["status"].choices]
        )
        self.assertNotIn(ItemStatus.IMPORT_ERROR, [value for value, _label in BulkEditForm().fields["status"].choices])

    def test_the_services_refuse_it(self) -> None:
        with self.assertRaises(ValidationError):
            services.set_status(self.item, ItemStatus.IMPORT_ERROR)
        self.item.status = ItemStatus.IMPORT_ERROR
        with self.assertRaises(ValidationError):
            self.item.full_clean()

    def test_a_flagged_item_can_be_released_by_hand(self) -> None:
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n")
        flagged = item(310)
        self.assertEqual(
            [value for value, _label in flagged.selectable_statuses if value in ("available", "blocked")],
            ["available", "blocked"],
        )
        services.set_status(flagged, ItemStatus.AVAILABLE)
        self.assertEqual(item(310).status, ItemStatus.AVAILABLE)


class WrongColumnTests(RentalarsTestCase):
    """ "Kategorie: „verfügbar“ hat aus Zeile 10 schon die Kategorie Kabel" – a column of statuses read as names."""

    def test_a_status_as_article_name_is_pointed_out(self) -> None:
        report = run(f"{HEAD}\n310;verfügbar;Kabel\n311;verfügbar;Ton\n", dry_run=True)
        names = [issue for issue in report.warnings if issue.row and issue.column == "Artikelname"]
        self.assertEqual(len(names), 2)
        self.assertIn("Status", names[0].message)

    def test_an_item_moved_to_another_model_is_told(self) -> None:
        run(f"{HEAD}\n310;Global Truss F34 200;Traversen\n")
        report = run(f"{HEAD}\n310;Anderes Ding;Traversen\n", dry_run=True)
        moved = [issue for issue in report.warnings if issue.row == 2]
        self.assertEqual(len(moved), 1)
        self.assertIn("Global Truss F34 200", moved[0].message)
        self.assertIn("Anderes Ding", moved[0].message)

    def test_the_same_name_says_nothing(self) -> None:
        run(f"{HEAD}\n310;Global Truss F34 200;Traversen\n")
        report = run(f"{HEAD}\n310;Global Truss F34 200;Traversen\n", dry_run=True)
        self.assertEqual([issue for issue in report.warnings if issue.row], [])
