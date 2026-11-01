# SPDX-License-Identifier: GPL-3.0-or-later
"""The dry run shows every row of the file (IMP-011).

The requirement: a preview in the browser – the dry run shows every row (new, changed with old → new, unchanged,
error), filterable, and only then comes the button to import.

* Every row of a material, product, customer or people import gets an
  outcome – in the dry run and in the report of the import: new, changed
  with each field old → new (readable values, labels of the pages),
  unchanged, or error with its messages.
* The material import's second and third pass (installed in, sets bought
  together) change items after they were counted; their rows end up changed.
* Purchase prices, prices and rates are shown only with their right.
* The page lists the rows 200 at a time, filtered by outcome and searched by
  row, ID or name – all in the address. The API returns the rows as well.
"""

from __future__ import annotations

import io
import json
import os
import time
from decimal import Decimal
from typing import Any
from unittest import skipUnless

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, Rights, SpecialRight
from rentalars.core import import_rows
from rentalars.core.import_rows import RowLog
from rentalars.core.models import BackgroundJob
from rentalars.core.tabular import ImportIssue
from rentalars.customers.importer import import_customers
from rentalars.customers.models import Customer
from rentalars.material.importer import import_material, read_table, resolve_mapping, run_import
from rentalars.material.models import MaterialItem
from rentalars.personnel.importer import import_people
from rentalars.personnel.models import Person
from rentalars.products.importer import import_products
from rentalars.products.models import Product
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, job_function, make_customer, make_person, make_product
from tests.ui.base import UiTestCase, form_data

HEAD = "ID;Artikelname;Kategorie"

#: Everything – as the command on the server and an administrator.
ALL_RIGHTS = Rights.everything()


def rights(*special: str, module: str = Module.MATERIAL) -> Rights:
    """Write access to one module with some special rights."""
    return Rights(module_levels={module: Level.DELETE}, special_rights=frozenset(special))


def table(text: str) -> Any:
    """Read CSV text (semicolons) as an import table."""
    return read_table(io.BytesIO(text.encode("utf-8")), "liste.csv")


def material(text: str, *, dry_run: bool = True, rights: Rights | None = None, **overrides: Any) -> Any:
    """Import CSV text as material and return the report."""
    data = table(text)
    return import_material(data, resolve_mapping(data.headers, overrides), dry_run=dry_run, rights=rights)


def mapped(text: str, fields: Any) -> tuple[Any, dict[str, int | None]]:
    """A table and its automatic column mapping."""
    from rentalars.core.tabular import resolve_mapping as resolve

    data = table(text)
    return data, resolve(data.headers, {}, fields)


def rows_of(report: Any) -> dict[int, dict[str, Any]]:
    """The rows of a report by their number, as the API and the page get them."""
    data = report.as_dict()
    json.dumps(data)  # it is kept with the task in the background: plain data only
    return {row["row"]: row for row in data["rows"]}


def changes_of(row: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """The changes of a row as ``{label: (old, new)}``."""
    return {change["label"]: (change.get("old"), change.get("new")) for change in row["changes"]}


class MaterialRowTests(RentalarsTestCase):
    """Material: items and their models, row by row."""

    FIRST = (
        f"{HEAD};Seriennummer;Kaufpreis;Tag des Kaufs;Gekauft (Händler);Status\n"
        "1;Funkempfänger;Ton;SN-1;499,00;12.03.2021;Thomann;verfügbar\n"
        "2;Funkempfänger;Ton;SN-2;499,00;12.03.2021;Thomann;verfügbar\n"
    )

    def test_new_changed_unchanged_with_old_and_new_values(self) -> None:
        material(self.FIRST, dry_run=False)
        report = material(
            f"{HEAD};Seriennummer;Kaufpreis;Tag des Kaufs;Gekauft (Händler);Status\n"
            "1;Funkempfänger;Ton;SN-9;520,00;01.04.2021;Musikhaus Kirstein;defekt\n"
            "2;Funkempfänger;Ton;SN-2;499,00;12.03.2021;Thomann;verfügbar\n"
            "3;Funkempfänger;Ton;SN-3;499,00;12.03.2021;Thomann;verfügbar\n",
            rights=ALL_RIGHTS,
        )
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        rows = rows_of(report)
        self.assertEqual(
            {number: row["status"] for number, row in rows.items()}, {2: "changed", 3: "unchanged", 4: "new"}
        )
        self.assertEqual(rows[2]["label"], "0001 Funkempfänger")
        changes = changes_of(rows[2])
        self.assertEqual(changes["Seriennummer"], ("SN-1", "SN-9"))
        self.assertEqual(changes["Kaufpreis (netto)"], ("499,00 €", "520,00 €"))
        self.assertEqual(changes["Rechnungsdatum"], ("12.03.2021", "01.04.2021"))
        self.assertEqual(changes["Gekauft bei"], ("Thomann", "Musikhaus Kirstein"))  # by name, not ID
        self.assertEqual(changes["Status"], ("verfügbar", "defekt"))
        self.assertIn("neuer Händler „Musikhaus Kirstein“", rows[2]["notes"])
        # An unchanged row is only number, label and outcome – a list of 20,000 rows stays small.
        self.assertEqual(rows[3], {"row": 3, "label": "0002 Funkempfänger", "status": "unchanged"})
        self.assertEqual((rows[4]["label"], rows[4]["changes"]), ("0003 Funkempfänger", []))
        self.assertEqual(report.as_dict()["row_counts"], {"new": 1, "changed": 1, "unchanged": 1, "error": 0})
        self.assertEqual(MaterialItem.objects.get(inventory_number=1).serial_number, "SN-1")  # a dry run

    def test_a_changed_model_makes_its_row_changed(self) -> None:
        material(f"{HEAD}\n1;Funkempfänger;Ton\n", dry_run=False)
        report = material(f"{HEAD};Beschreibung;Hersteller\n1;Funkempfänger;Ton;UHF, 1 Kanal;Sennheiser\n")
        row = rows_of(report)[2]
        self.assertEqual(row["status"], "changed")
        self.assertEqual(changes_of(row)["Beschreibung (Materialmodell)"], ("–", "UHF, 1 Kanal"))
        self.assertEqual(changes_of(row)["Hersteller (Materialmodell)"], ("–", "Sennheiser"))
        self.assertIn("neuer Hersteller „Sennheiser“", row["notes"])
        # The counts of models and items stay what they were: the item itself is unchanged.
        self.assertEqual((report.models_updated, report.items_unchanged), (1, 1))

    def test_new_models_and_categories_are_noted_with_their_row(self) -> None:
        report = material(f"{HEAD}\n1;Ender 3;3D-Druck\n2;Ender 3;3D-Druck\n")
        rows = rows_of(report)
        self.assertEqual([rows[2]["status"], rows[3]["status"]], ["new", "new"])
        self.assertIn("neues Materialmodell „Ender 3“", rows[2]["notes"])
        self.assertTrue(any(note.startswith("neue Kategorie „3D-Druck") for note in rows[2]["notes"]))
        self.assertEqual(rows[3]["notes"], [])

    def test_second_and_third_pass_change_rows_after_they_were_counted(self) -> None:
        """IMP-010, IMP-016: "installed in" and sets bought together are written after all items exist."""
        head = f"{HEAD};Einsatz/Verbindung;Kaufpreis"
        material(
            f"{head}\n500;Rack 6 HE;Rigging;;\n310;Funkempfänger;Ton;;\n851;Mikrofon;Ton;;300,00\n852;Mikrofon;Ton;;120,00\n",
            dry_run=False,
        )
        text = f"{head}\n500;Rack 6 HE;Rigging;;\n310;Funkempfänger;Ton;500;\n851;Mikrofon;Ton;;300,00\n852;Mikrofon;Ton;;#0851\n"
        dry = material(text, rights=ALL_RIGHTS)
        rows = rows_of(dry)
        self.assertEqual(
            [rows[number]["status"] for number in (2, 3, 4, 5)], ["unchanged", "changed", "unchanged", "changed"]
        )
        self.assertEqual(changes_of(rows[3])["Verbaut in"], ("–", "0500 Rack 6 HE"))
        self.assertEqual(changes_of(rows[5])["Kaufpreis (netto)"], ("120,00 €", "–"))
        self.assertEqual(changes_of(rows[5])["Preis enthalten in"], ("–", "0851 Mikrofon"))
        # The counts follow: two items changed in the later passes, two stay unchanged.
        self.assertEqual((dry.items_created, dry.items_updated, dry.items_unchanged), (0, 2, 2))

        done = material(text, dry_run=False, rights=ALL_RIGHTS)
        self.assertEqual(done.as_dict()["rows"], dry.as_dict()["rows"])  # the import does what the dry run showed
        self.assertEqual((done.items_updated, done.items_unchanged), (2, 2))
        self.assertEqual(MaterialItem.objects.get(inventory_number=310).installed_in.inventory_number, 500)

    def test_a_row_changed_by_the_first_and_the_second_pass_lists_both(self) -> None:
        head = f"{HEAD};Einsatz/Verbindung;Notiz"
        material(f"{head}\n500;Rack;Rigging;;\n310;Empfänger;Ton;;alt\n", dry_run=False)
        report = material(f"{head}\n500;Rack;Rigging;;\n310;Empfänger;Ton;500;neu\n")
        changes = changes_of(rows_of(report)[3])
        self.assertEqual((changes["Notiz"], changes["Verbaut in"]), (("alt", "neu"), ("–", "0500 Rack")))
        self.assertEqual((report.items_updated, report.items_unchanged), (1, 1))

    def test_errors_are_rows_and_a_file_error_has_no_rows(self) -> None:
        report = material(f"{HEAD};Kaufpreis\n310;Funkempfänger;Ton;499,00\n311;;Ton;1,00\n312;Funkempfänger;;2,00\n")
        rows = rows_of(report)
        self.assertEqual(rows[3]["status"], "error")
        self.assertEqual(rows[3]["label"], "0311")
        self.assertEqual((rows[4]["status"], rows[4]["label"]), ("error", "0312 Funkempfänger"))
        self.assertTrue(rows[3]["errors"])
        # With a hard error in the file nothing is written, and the other rows are checked once it is corrected.
        self.assertNotIn(2, rows)
        # A single unreadable value is no hard error: the item is taken over with the status “import error”.
        soft = rows_of(material(f"{HEAD};Kaufpreis\n310;Funkempfänger;Ton;neun\n"))
        self.assertEqual(soft[2]["status"], "new")
        self.assertEqual(soft[2]["errors"], [])
        missing = material("ID;Kategorie\n1;Ton\n")
        self.assertEqual(missing.as_dict()["rows"], [])
        self.assertIsNone(missing.errors[0].row)

    def test_purchase_prices_only_with_their_right(self) -> None:
        """AUT-019: the preview must not show purchase prices; the import writes them as before."""
        material(f"{HEAD};Kaufpreis\n1;Funkempfänger;Ton;499,00\n", dry_run=False)
        text = f"{HEAD};Kaufpreis;Seriennummer\n1;Funkempfänger;Ton;520,00;SN-1\n"
        data = table(text)
        mapping = resolve_mapping(data.headers, {})
        without = run_import(data, mapping, rights=rights(), dry_run=True, actor="system:test")
        row = rows_of(without)[2]
        self.assertEqual(row["status"], "changed")
        price = next(change for change in row["changes"] if change["field"] == "purchase_price")
        self.assertEqual(price, {"field": "purchase_price", "label": "Kaufpreis (netto)", "hidden": True})
        stored = json.dumps(without.as_dict())
        self.assertNotIn("499", stored)
        self.assertNotIn("520,00", stored)
        self.assertIn("Ohne das Recht, Einkaufspreise zu sehen", " ".join(str(issue) for issue in without.warnings))

        with_right = run_import(data, mapping, rights=rights(SpecialRight.PURCHASE_PRICES), dry_run=True)
        self.assertEqual(changes_of(rows_of(with_right)[2])["Kaufpreis (netto)"], ("499,00 €", "520,00 €"))
        self.assertEqual(with_right.warnings, [])
        # The import itself takes the price over.
        run_import(data, mapping, rights=rights(), dry_run=False)
        self.assertEqual(MaterialItem.objects.get(inventory_number=1).purchase_price, Decimal("520.00"))


class ProductRowTests(RentalarsTestCase):
    """Products: by article number."""

    def test_rows_of_a_product_import(self) -> None:
        from rentalars.products.importer import IMPORT_FIELDS

        make_product("L-010", "PAR 64", price="12.00")
        make_product("K-005", "XLR-Kabel 5 m", price="2.50")
        data, mapping = mapped(
            "Art.-Nr.;Name;Preis;Aktiv\nL-010;PAR 64 LED;14,00;nein\nK-005;XLR-Kabel 5 m;2,50;ja\n"
            "L-011;Fresnel;20,00;ja\nfalsch;Etwas;1,00;ja\n",
            IMPORT_FIELDS,
        )
        report = import_products(data, mapping, dry_run=True, rights=ALL_RIGHTS)
        rows = rows_of(report)
        statuses = {number: row["status"] for number, row in rows.items()}
        self.assertEqual(statuses, {2: "changed", 3: "unchanged", 4: "new", 5: "error"})
        changes = changes_of(rows[2])
        self.assertEqual(rows[2]["label"], "L-010 PAR 64 LED")
        self.assertEqual(changes["Name"], ("PAR 64", "PAR 64 LED"))
        self.assertEqual(changes["Preis (netto)"], ("12,00 €", "14,00 €"))
        self.assertEqual(changes["Aktiv"], ("ja", "nein"))
        self.assertEqual(rows[5]["label"], "falsch Etwas")
        self.assertIn("ist keine Artikelnummer", rows[5]["errors"][0])
        self.assertEqual(Product.objects.get(article_number="L-010").name, "PAR 64")

    def test_prices_only_with_the_price_right(self) -> None:
        """AUT-019: without the price right a price column is refused (as before); the log hides prices anyway."""
        log = RowLog(rights(module=Module.PRODUCTS))
        log.record(2, "L-010 PAR 64", import_rows.UNCHANGED)
        log.change(2, Product, "price", Decimal("12.00"), Decimal("14.00"))
        log.change(2, Product, "name", "PAR 64", "PAR 64 LED")
        row = log.as_list()[0]
        self.assertEqual(row["status"], "changed")
        self.assertEqual(row["changes"][0], {"field": "price", "label": "Preis (netto)", "hidden": True})
        self.assertEqual(row["changes"][1]["new"], "PAR 64 LED")
        priced = RowLog(rights(SpecialRight.PRICES, module=Module.PRODUCTS))
        priced.record(2, "L-010", import_rows.UNCHANGED)
        priced.change(2, Product, "price", Decimal("12.00"), Decimal("14.00"))
        self.assertEqual(priced.as_list()[0]["changes"][0]["new"], "14,00 €")


class CustomerRowTests(RentalarsTestCase):
    """Customers: merged rows name what they change."""

    def test_rows_of_a_customer_import(self) -> None:
        from rentalars.customers.importer import IMPORT_FIELDS

        known = make_customer("Kulturverein")
        known.city, known.email = "Dorf", "k@v.example"
        known.save()
        same = make_customer("Sportverein")
        data, mapping = mapped(
            f"Nummer;Name;Ort;Ansprechperson;Art\n{known.number};Kulturverein;Stadt;Eva Müller;\n"
            f"{same.number};Sportverein;;;\n;Theater;Dorf;;\n;Musikschule;;;Verein?\n",
            IMPORT_FIELDS,
        )
        report = import_customers(data, mapping, dry_run=True, rights=ALL_RIGHTS)
        rows = rows_of(report)
        self.assertEqual(
            [(rows[n]["status"], rows[n]["outcome"]) for n in (2, 3, 4, 5)],
            [("changed", "merged"), ("unchanged", "unchanged"), ("new", "created"), ("error", "error")],
        )
        self.assertEqual(rows[2]["label"], f"{known.number} Kulturverein")
        self.assertEqual(changes_of(rows[2])["Ort"], ("Dorf", "Stadt"))
        self.assertIn("Ansprechperson Eva Müller hinzugefügt", rows[2]["notes"])
        self.assertIn("gefunden über die Kundennummer", rows[2]["text"])  # the customer import's own words stay
        self.assertEqual(rows[5]["label"], "Musikschule")
        self.assertIn("Verein?", rows[5]["errors"][0])
        self.assertEqual(Customer.objects.get(pk=known.pk).city, "Dorf")

    def test_the_discount_only_with_the_price_right(self) -> None:
        log = RowLog(rights(module=Module.CUSTOMERS))
        log.record(2, "10001 Kulturverein", import_rows.UNCHANGED)
        log.change(2, Customer, "default_discount_percent", Decimal("5.00"), Decimal("10.00"))
        self.assertTrue(log.as_list()[0]["changes"][0]["hidden"])
        priced = RowLog(rights(SpecialRight.PRICES, module=Module.CUSTOMERS))
        priced.record(2, "10001 Kulturverein", import_rows.UNCHANGED)
        priced.change(2, Customer, "default_discount_percent", Decimal("5.00"), Decimal("10.00"))
        self.assertEqual(priced.as_list()[0]["changes"][0]["new"], "10,00 %")


class PeopleRowTests(RentalarsTestCase):
    """People: fields, job functions and rates."""

    def test_rows_of_a_people_import(self) -> None:
        from rentalars.personnel.importer import IMPORT_FIELDS

        job_function("Licht", guide="25.00")
        job_function("Ton", guide="25.00")
        eva = make_person("Eva Licht", rates={"Licht": "28.00"})
        eva.phone = "0123"
        eva.save()
        make_person("Max Ton")
        data, mapping = mapped(
            "Vorname;Nachname;Telefon;Funktionen\nEva;Licht;0456;Licht: 30,00, Ton\nMax;Ton;;\n"
            "Ida;Neu;;Ton\nOla;Fehler;;Ballett\n",
            IMPORT_FIELDS,
        )
        costs = rights(SpecialRight.PERSONNEL_COSTS, module=Module.PERSONNEL)
        report = import_people(data, mapping, dry_run=True, rights=costs)
        rows = rows_of(report)
        statuses = {number: row["status"] for number, row in rows.items()}
        self.assertEqual(statuses, {2: "changed", 3: "unchanged", 4: "new", 5: "error"})
        changes = changes_of(rows[2])
        self.assertEqual(rows[2]["label"], "Eva Licht")
        self.assertEqual(changes["Telefon"], ("0123", "0456"))
        self.assertEqual(changes["Funktionen"], ("Licht", "Licht, Ton"))
        self.assertEqual(changes["Stundensatz (Licht)"], ("28,00 €", "30,00 €"))
        self.assertEqual(rows[5]["errors"], ["Funktionen: Eine Funktion „Ballett“ gibt es nicht."])
        self.assertEqual(rows[5]["label"], "Ola Fehler")
        self.assertEqual(Person.objects.get(pk=eva.pk).phone, "0123")

    def test_rates_only_with_the_right_to_see_personnel_costs(self) -> None:
        from rentalars.personnel.models import PersonJobFunction

        log = RowLog(rights(module=Module.PERSONNEL))
        log.record(2, "Eva Licht", import_rows.UNCHANGED)
        log.change(2, PersonJobFunction, "hourly_rate", Decimal("28.00"), Decimal("30.00"), key="hourly_rate.1")
        self.assertTrue(log.as_list()[0]["changes"][0]["hidden"])


class CommandTests(RentalarsTestCase):
    """``import_material --changes`` lists the changed rows of the dry run."""

    def test_changed_rows_on_the_command_line(self) -> None:
        import tempfile
        from pathlib import Path

        from django.core.management import call_command

        material(f"{HEAD};Seriennummer;Kaufpreis\n1;Kabel;Kabel;SN-1;10,00\n2;Kabel;Kabel;SN-2;10,00\n", dry_run=False)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bestand.csv"
            path.write_text(f"{HEAD};Seriennummer;Kaufpreis\n1;Kabel;Kabel;SN-9;12,00\n2;Kabel;Kabel;SN-2;10,00\n")
            out = io.StringIO()
            call_command("import_material", str(path), "--changes", stdout=out)
        text = out.getvalue()
        self.assertIn("Geänderte Zeilen: 1", text)
        self.assertIn("Zeile 2, 0001 Kabel: Seriennummer: SN-1 → SN-9; Kaufpreis (netto): 10,00 € → 12,00 €", text)
        self.assertNotIn("0002 Kabel:", text)


class RowLogTests(RentalarsTestCase):
    """The parts all imports share."""

    def test_a_later_change_keeps_the_old_value_and_a_change_back_is_none(self) -> None:
        log = RowLog()
        log.record(7, "0001 Kabel", import_rows.UNCHANGED)
        log.change(7, MaterialItem, "note", "alt", "mittel")
        log.change(7, MaterialItem, "note", "mittel", "neu")
        self.assertEqual(log.as_list()[0]["changes"], [{"field": "note", "label": "Notiz", "old": "alt", "new": "neu"}])
        log.change(7, MaterialItem, "note", "neu", "alt")
        self.assertEqual(log.as_list()[0]["changes"], [])

    def test_a_new_row_has_no_changes_and_notes_of_the_import_join_the_row(self) -> None:
        log = RowLog()
        log.record(2, "0001 Kabel", import_rows.NEW)
        log.change(2, MaterialItem, "note", "", "neu")
        row = log.as_list(warnings=[ImportIssue(2, "Kategorie", "Bitte prüfen."), ImportIssue(None, "", "Datei")])[0]
        self.assertEqual((row["changes"], row["notes"]), ([], ["Kategorie: Bitte prüfen."]))


def material_file(count: int, *, start: int = 1) -> SimpleUploadedFile:
    """A material list of ``count`` rows as CSV."""
    lines = [f"{HEAD};Seriennummer"]
    lines += [f"{number};Kabel {number % 7};Kabel;SN-{number}" for number in range(start, start + count)]
    return SimpleUploadedFile("bestand.csv", "\n".join(lines).encode("utf-8"), content_type="text/csv")


class PreviewPageTests(UiTestCase):
    """The page: the rows below the result, filter, search, 200 to a page, then "Import now"."""

    def dry_run(self, upload: SimpleUploadedFile, url: str | None = None) -> tuple[str, dict[str, Any], str]:
        url = url or reverse("material:import")
        self.client.post(url, {"step": "upload", "file": upload})
        data = form_data(self.client.get(url), containing="map_inventory_number")
        page = self.assert_ok(self.client.post(url, {**data, "step": "check"}, follow=True))
        return url, data, page

    def test_rows_filter_search_and_pages(self) -> None:
        material(f"{HEAD};Seriennummer\n1;Kabel 1;Kabel;SN-1\n2;Kabel 2;Kabel;SN-2\n", dry_run=False)
        url, data, page = self.dry_run(material_file(205))  # 0001 and 0002 exist as the file has them
        self.assertIn("Zeilen der Datei", page)
        # First everything but the unchanged rows: 203 new ones, 200 to a page.
        self.assertIn("Alle außer unveränderten (203)", page)
        self.assertIn("Unverändert (2)", page)
        self.assertIn("Seite 1 von 2", page)
        self.assertIn('<th scope="col" class="num">Zeile</th>', page)
        self.assertIn("<caption", page)
        self.assertIn('form="import-form" name="step" value="import"', page)
        self.assertNotIn("0001 Kabel 1</td>", page)  # unchanged: not in the first view

        unchanged = self.assert_ok(self.client.get(url, {"show": "unchanged"}))
        self.assertIn("0001 Kabel 1", unchanged)
        self.assertNotIn("Seite 1 von 2", unchanged)
        second = self.assert_ok(self.client.get(url, {"show": "all", "page": 2}))
        self.assertIn("0205 Kabel 2", second)
        self.assertIn("Seite 2 von 2", second)
        self.assertIn("show=all", second)  # the links keep the filter
        found = self.assert_ok(self.client.get(url, {"show": "all", "q": "0150"}))
        self.assertIn("0150 Kabel 3", found)
        self.assertNotIn("0151 Kabel", found)
        self.assertIn('value="0150"', found)
        by_row = self.assert_ok(self.client.get(url, {"q": "17"}))
        self.assertIn("0016 Kabel 2", by_row)  # row 17 of the file holds ID 0016
        self.assertIn("Keine Zeile passt zum Filter.", self.assert_ok(self.client.get(url, {"q": "nichts"})))
        self.assertFalse(MaterialItem.objects.filter(inventory_number=3).exists())

        done = self.assert_ok(self.client.post(url, {**data, "step": "import"}, follow=True))
        self.assertIn("Der Import ist abgeschlossen.", done)
        self.assertIn("Importierte Zeilen", done)
        job = BackgroundJob.objects.filter(kind="import").latest("pk")
        again = self.assert_ok(self.client.get(url, {"job": job.pk, "show": "all", "page": 2}))
        self.assertIn("Der Import ist abgeschlossen.", again)
        self.assertIn("0205 Kabel 2", again)
        self.assertIn(f'name="job" value="{job.pk}"', again)
        self.assertEqual(MaterialItem.objects.count(), 205)
        # Somebody else's import is not shown; the page starts anew.
        other = self.browser_for("luka", "Lager")
        self.assertIn('name="file"', self.assert_ok(other.get(url, {"job": job.pk})))

    def test_changed_rows_show_field_previously_and_new(self) -> None:
        material(f"{HEAD};Seriennummer;Kaufpreis\n1;Kabel 1;Kabel;SN-1;10,00\n", dry_run=False)
        upload = SimpleUploadedFile("b.csv", f"{HEAD};Seriennummer;Kaufpreis\n1;Kabel 1;Kabel;SN-9;12,00\n".encode())
        _url, _data, page = self.dry_run(upload)
        self.assertIn('<th scope="col">Feld</th><th scope="col">bisher</th><th scope="col">neu</th>', page)
        self.assertIn('<th scope="row">Seriennummer</th><td><del>SN-1</del></td><td>SN-9</td>', page)
        self.assertIn("<td><del>10,00 €</del></td><td>12,00 €</td>", page)

        # A warehouse role without the right to see purchase prices: the field is named, its values are not.
        Role.objects.create(name="Lager ohne Preise", module_levels={"material": 3}, special_rights=[])
        browser = self.browser_for("lena", "Lager ohne Preise")
        url = reverse("material:import")
        upload.seek(0)
        browser.post(url, {"step": "upload", "file": upload})
        data = form_data(browser.get(url), containing="map_inventory_number")
        page = self.assert_ok(browser.post(url, {**data, "step": "check"}, follow=True))
        self.assertIn('<th scope="row">Kaufpreis (netto)</th><td colspan="2" class="muted">nicht sichtbar</td>', page)
        self.assertNotIn("10,00", page)
        self.assertNotIn("12,00 €", page)
        job = BackgroundJob.objects.filter(created_by__username="lena").latest("pk")
        self.assertNotIn("10,00", json.dumps(job.result))

    def test_errors_and_the_other_imports(self) -> None:
        url = reverse("core:import", args=["people"])
        job_function("Licht")
        self.client.post(
            url,
            {
                "step": "upload",
                "file": SimpleUploadedFile("l.csv", b"Name;Funktionen\nEva Licht;Ballett\nMax Ton;Licht\n"),
            },
        )
        data = form_data(self.client.get(url), containing="map_name")
        page = self.assert_ok(self.client.post(url, {**data, "step": "check"}, follow=True))
        self.assertIn("Fehler (1)", page)
        self.assertIn("Funktionen: Eine Funktion „Ballett“ gibt es nicht.", page)
        self.assertNotIn("Jetzt importieren", page)
        errors = self.assert_ok(self.client.get(url, {"show": "error"}))
        self.assertNotIn('data-label="Datensatz">Max Ton<', errors)
        self.assertIn('data-label="Datensatz">Max Ton<', page)

    def test_a_material_list_with_errors_lists_the_rows_with_errors(self) -> None:
        upload = SimpleUploadedFile("b.csv", f"{HEAD};Kaufpreis\n1;;Kabel;3,00\n2;Kabel;Kabel;1,00\n".encode())
        _url, _data, page = self.dry_run(upload)
        self.assertIn("Aufgeführt sind nur die Zeilen mit Fehlern.", page)
        self.assertIn("Fehler (1)", page)

    def test_an_unknown_filter_falls_back_and_a_report_without_rows_still_shows(self) -> None:
        url, _data, _page = self.dry_run(material_file(3))
        self.assertIn("Alle (3)", self.assert_ok(self.client.get(url, {"show": "kaputt", "page": "x"})))
        # An older dry run kept no rows: its result is shown as before, without the list.
        job = BackgroundJob.objects.filter(kind="import").latest("pk")
        job.result = {"report": {key: value for key, value in job.result["report"].items() if key != "rows"}}
        job.save()
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Ergebnis des Probelaufs", page)
        self.assertNotIn("Zeilen der Datei", page)


class PreviewApiTests(ApiTestCase):
    """API: the rows in the answer of a dry run and an import, and in the result of a task."""

    def test_rows_in_the_answer(self) -> None:
        make_product("L-010", "PAR 64", price="12.00")
        upload = SimpleUploadedFile("p.csv", b"Art.-Nr.;Name;Preis\nL-010;PAR 64;14,00\nL-011;Fresnel;20,00\n")
        response = self.admin.post(f"{API}/imports/products", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["row_counts"], {"new": 1, "changed": 1, "unchanged": 0, "error": 0})
        self.assertEqual(
            body["rows"][0],
            {
                "row": 2,
                "label": "L-010 PAR 64",
                "status": "changed",
                "changes": [{"field": "price", "label": "Preis (netto)", "old": "12,00 €", "new": "14,00 €"}],
                "notes": [],
                "errors": [],
            },
        )
        self.assertEqual(body["created"], 1)  # the fields of before stay

    def test_rows_of_errors_and_of_a_task_in_the_background(self) -> None:
        upload = SimpleUploadedFile("m.csv", f"{HEAD};Kaufpreis\n1;;Kabel;3,00\n2;Kabel;Kabel;1,00\n".encode())
        refused = self.admin.post(f"{API}/imports/material", {"file": upload}, format="multipart")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["rows"][0]["status"], "error")

        upload = SimpleUploadedFile("m.csv", f"{HEAD}\n1;Kabel;Kabel\n".encode())
        started = self.admin.post(f"{API}/imports/material", {"file": upload, "background": "true"}, format="multipart")
        self.assertEqual(started.status_code, 202, started.content)
        job = self.admin.get(f"{API}/jobs/{started.json()['id']}").json()
        row = job["result"]["report"]["rows"][0]
        self.assertEqual((row["row"], row["label"], row["status"]), (2, "0001 Kabel", "new"))
        self.assertIn("neues Materialmodell „Kabel“", row["notes"])

    def test_the_schema_describes_the_rows(self) -> None:
        schema = self.admin.get(f"{API}/schema?format=json").data
        report = schema["components"]["schemas"]["ImportReport"]["properties"]
        self.assertIn("rows", report)
        self.assertIn("row_counts", report)
        row = schema["components"]["schemas"]["ImportRow"]["properties"]
        self.assertTrue({"row", "label", "status", "changes", "notes", "errors"} <= set(row))


@skipUnless(os.environ.get("RENTALARS_TEST_IMPORT_LOAD"), "set RENTALARS_TEST_IMPORT_LOAD=1 to measure 20,000 rows")
class LargeFileTests(UiTestCase):
    """A material list of 20,000 rows (XLSX): dry run, size of the stored report, pages of the list (< 1 s).

    First the list is imported as new items, then a dry run of the same list with every 20th row changed:
    1,000 changed rows with their fields, 19,000 unchanged rows of a few bytes each.
    """

    def workbook(self, serial: str) -> SimpleUploadedFile:
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.append(["ID", "Artikelname", "Kategorie", "Seriennummer", "Kaufpreis", "Notiz"])
        for n in range(1, 20001):
            sheet.append([n, f"Kabel {n % 50}", "Kabel", f"{serial if n % 20 == 0 else 'SN-'}{n}", n % 90 + 0.5, "x"])
        buffer = io.BytesIO()
        book.save(buffer)
        return SimpleUploadedFile("bestand.xlsx", buffer.getvalue())

    def test_twenty_thousand_rows(self) -> None:
        url = reverse("material:import")
        measured: dict[str, Any] = {}
        for step, serial in (("new", "SN-"), ("changed", "NEU-")):
            self.client.post(url, {"step": "upload", "file": self.workbook(serial)})
            data = form_data(self.client.get(url), containing="map_inventory_number")
            started = time.perf_counter()
            self.client.post(url, {**data, "step": "check"})
            measured[f"dry run {step}"] = round(time.perf_counter() - started, 1)
            job = BackgroundJob.objects.latest("pk")
            measured[f"report {step} (MB)"] = round(len(json.dumps(job.result)) / 1e6, 2)
            for name, query in (("first", {}), ("all p.50", {"show": "all", "page": 50}), ("search", {"q": "1999"})):
                started = time.perf_counter()
                self.assert_ok(self.client.get(url, query))
                measured[f"page {step} {name}"] = round(time.perf_counter() - started, 2)
            if step == "new":
                self.client.post(url, {**data, "step": "import"})
                self.assertEqual(MaterialItem.objects.count(), 20000)
        print(f"\n20,000 rows: {measured}")
        self.assertEqual(job.result["report"]["row_counts"]["changed"], 1000)
        self.assertLess(max(value for key, value in measured.items() if key.startswith("page")), 1.0)
