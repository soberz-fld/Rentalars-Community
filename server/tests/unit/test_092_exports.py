# SPDX-License-Identifier: GPL-3.0-or-later
"""Every import can be exported in its format, and the full export is a part of "Sicherung".

Requirement 1 (IMP-006): the difference between the full export and the backup is explained; if it is small, the full
export lives only under "Sicherung".

Requirement 2 (IMP-017): everything that can be imported under Settings → Import and export can also be exported (at least as
CSV), and in plain text – not like the backups with model=1 – so that one could in theory go on working with the CSV without
Rentalars.

* Material, products, customers and people each have an "Export im Importformat": the columns of the
  import under its headings, in plain text – names and numbers instead of IDs, dates and amounts as the
  import reads them. Exported and imported again, every row is "unverändert".
* Columns of prices, purchase prices and rates only with their right; text that would be a formula gets
  an apostrophe, which the import takes away again; the queries do not grow with the rows.
* The same through the API: ``GET /imports/{kind}/export``.
* The full export of all data (IMP-006) is a section of the page "Sicherung und Verschlüsselung" with the
  difference to a backup, at ``/administration/backup/export/``; "Import und Export" no longer has it.
"""

from __future__ import annotations

import datetime
import io
import time
import zipfile
from decimal import Decimal
from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Rights, rights_of
from rentalars.core import import_exports, imports
from rentalars.core.import_exports import amount, cell
from rentalars.core.models import AccessKind, AccessLogEntry, BackgroundJob
from rentalars.core.tabular import Table, cell_text, read_table, resolve_mapping
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress, CustomerKind
from rentalars.customers.services import anonymise_customer
from rentalars.masterdata.models import (
    Category,
    CategoryField,
    FieldType,
    Manufacturer,
    StorageLocation,
    Supplier,
    Unit,
)
from rentalars.material.models import ConnectionType, ItemStatus, MaterialItem, MaterialModel, TrackingMode
from rentalars.personnel.models import EmploymentKind
from rentalars.personnel.privacy import anonymise_person
from rentalars.personnel.services import current_rates, set_rate
from rentalars.products.models import ProductKind, TrailerBilling, VehicleType
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    RentalarsTestCase,
    category,
    job_function,
    make_customer,
    make_item,
    make_person,
    make_product,
    make_user,
)
from tests.ui.base import UiTestCase

KEYS = ("material", "products", "customers", "people")


# --- Data and helpers ------------------------------------------------------------------------------


def role(name: str, levels: dict[str, int], special: tuple[str, ...] = ()) -> str:
    """A role of its own for a test; returns its name."""
    Role.objects.create(name=name, module_levels=levels, special_rights=list(special))
    return name


def text_of(key: str, user: Any = None, rights: Rights | None = None) -> str:
    """The exported file of an import as text, for the rights of ``user`` (or all)."""
    return import_exports.text_of(import_exports.get(key), rights or (rights_of(user) if user else Rights.everything()))


def table_of(text: str) -> Table:
    """The file read back the way the import reads it."""
    return read_table(io.BytesIO(text.encode("utf-8")), "export.csv")


def records(text: str) -> list[dict[str, Any]]:
    """The rows of a file by heading, with the cells as they are in the file."""
    table = table_of(text)
    return [dict(zip(table.headers, row, strict=True)) for row in table.rows]


def downloaded(response: Any) -> str:
    """The text of a file the browser or the API delivered (written while it is sent)."""
    content = b"".join(response.streaming_content) if response.streaming else response.content
    return content.decode("utf-8")


class ExportData(RentalarsTestCase):
    """Material, products, customers and people with everything their imports take."""

    def setUp(self) -> None:
        super().setUp()
        self.importer = make_user("importer", superuser=True)
        self.material()
        self.products()
        self.customers()
        self.people()

    def material(self) -> None:
        """Items of four models: a set bought together, a cable in a case, bulk material, shelves of one name."""
        self.mics = Category.objects.create(name="Mikrofone", parent=category("T"))
        CategoryField.objects.create(
            category=category("K"), label="Länge", field_type=FieldType.NUMBER, unit="m", position=1
        )
        halle1 = StorageLocation.objects.create(name="Halle 1")
        halle2 = StorageLocation.objects.create(name="Halle 2")
        StorageLocation.objects.create(name="Regal A", parent=halle1)
        self.shelf = StorageLocation.objects.create(name="Regal A", parent=halle2)  # the same name as above
        self.mic_product = make_product("T-100", "Funkmikrofon", category=self.mics, price="10.00")
        sm58 = MaterialModel.objects.create(
            name="SM58",
            category=self.mics,
            manufacturer=Manufacturer.objects.create(name="Shure"),
            short_name="58er",
            specification="Dynamisch\nNiere",
            default_product=self.mic_product,
        )
        par = MaterialModel.objects.create(name="PAR 64", category=category("L"), power_w=Decimal("575.50"))
        cable = MaterialModel(name="XLR 2,5 m", category=category("K"))
        cable.set_category_specific_value("2,5")
        cable.save()
        case = MaterialModel.objects.create(name="Kabelkiste", category=category("K"))
        tape = MaterialModel.objects.create(name="Gaffa-Tape", category=category("V"), tracking_mode=TrackingMode.BULK)
        self.mic = make_item(
            sm58,
            1,
            serial_number="SN-1",
            note='=HYPERLINK("http://example.org")',
            purchase_date=datetime.date(2026, 1, 15),
            purchase_note="Messe",
            purchase_price=Decimal("199.50"),
            supplier=Supplier.objects.create(name="Thomann"),
            supplier_article_number="TH-58",
            invoice_number="RE-7",
            storage_location=self.shelf,
        )
        second = make_item(sm58, 2)
        second.purchase_price_in = self.mic  # MAT-054: bought as a set, the price is noted at 0001
        second.save()
        make_item(par, 3, status=ItemStatus.BLOCKED, note="- Linse fehlt\nzweite Zeile")
        box = make_item(case, 5, storage_location=halle1, note="'=nicht rechnen")
        inner = make_item(cable, 4)
        inner.installed_in, inner.connection_type = box, ConnectionType.LOOSE
        inner.save()
        make_item(tape, 6, quantity=12)

    def products(self) -> None:
        """A rental product with all its fields, a sale product, vehicles and customer material."""
        product = self.mic_product
        product.max_discount_percent, product.gtin = Decimal("12.5"), "4006381333931"
        product.description, product.note, product.minimum_stock = "Zeile 1\nZeile 2", "intern", 2
        product.save()
        make_product(
            "V-010",
            "Gaffa schwarz",
            price=None,
            kind=ProductKind.SALE,
            sale_price=Decimal("8.90"),
            unit=Unit.objects.get(name="Stück (Verkauf)"),
        )
        make_product(
            "S-900",
            "Sprinter",
            price=None,
            kind=ProductKind.VEHICLE,
            vehicle_type=VehicleType.CAR,
            price_per_km=Decimal("0.80"),
            trailer_surcharge_per_km=Decimal("0.20"),
            cost_per_km=Decimal("0.35"),
        )
        make_product(
            "S-901",
            "Planenanhänger",
            price="25.00",
            kind=ProductKind.VEHICLE,
            vehicle_type=VehicleType.TRAILER,
            trailer_billing=TrailerBilling.KM,
            price_per_km=Decimal("0.30"),
            cost_per_day=Decimal("8.00"),
        )
        self.band = make_customer("Die Band")
        make_product(
            "C-001", "Mischpult der Band", price=None, owner=self.band, unit=Unit.objects.get(name="Stück (Miete)")
        )
        make_product("L-010", "Alter Scheinwerfer", is_active=False)

    def customers(self) -> None:
        """A company with three contacts and a delivery address, a private person, an anonymised customer."""
        firm = make_customer("Kultur & Verein e. V.")
        for name, value in {
            "name_addition": "Abteilung Technik",
            "street": "Markt 1",
            "postal_code": "12345",
            "city": "Dorf",
            "country": "Deutschland",
            "email": "info@kv.example",
            "phone": "+49 30 1234",
            "vat_id": "DE123456789",
            "tax_number": "12/345/67890",
            "payment_terms_days": 14,
            "default_discount_percent": Decimal("5.50"),
            "note": "Zeile eins\nZeile zwei",
        }.items():
            setattr(firm, name, value)
        firm.save()
        Contact.objects.create(
            customer=firm, name="Max Muster", salutation="Herr", email="max@kv.example", phone="0170 1", is_primary=True
        )
        Contact.objects.create(customer=firm, name="Erika Beispiel", position="Buchhaltung", email="erika@kv.example")
        Contact.objects.create(customer=firm, name="Hans Dampf", salutation="Herr", phone="0170 3")
        CustomerAddress.objects.create(
            customer=firm, kind=AddressKind.DELIVERY, street="Lagerweg 5", postal_code="12346", city="Dorf-Nord"
        )
        self.firm = firm
        private = make_customer("Eva Privat")
        private.kind, private.email, private.is_active = CustomerKind.PRIVATE, "eva@privat.example", False
        private.save()
        anonymise_customer(make_customer("Ehemals GmbH"))

    def people(self) -> None:
        """A person with rates, a freelancer with a day rate only, an anonymised person."""
        licht, ton = job_function("Licht"), job_function("Tontechnik")
        eva = make_person("Eva Licht", rates={"Licht": "28.00"})
        set_rate(eva, licht, Decimal("28.00"), datetime.date(2027, 1, 1), daily_rate=Decimal("250.00"))
        set_rate(eva, ton, None, None)  # PER-029: the function without own rates
        for name, value in {
            "email": "eva@example.de",
            "phone": "0170 2",
            "company": "Licht & Ton",
            "street": "Weg 2",
            "postal_code": "54321",
            "city": "Stadt",
            "tax_number": "98/765",
            "vat_id": "DE987654321",
            "note": "Nur am Wochenende\nFührerschein C",
        }.items():
            setattr(eva, name, value)
        eva.save()
        self.eva = eva
        tom = make_person("Tom Ton", kind=EmploymentKind.FREELANCER)
        set_rate(tom, ton, None, None, daily_rate=Decimal("280.00"))
        anonymise_person(make_person("Ex Mitarbeiter"))

    def assert_round_trip(self, key: str, text: str, user: Any = None) -> dict[str, Any]:
        """Import the file as a dry run: every column is recognised, and every row is "unchanged"."""
        kind = imports.get(key)
        table = table_of(text)
        mapping = resolve_mapping(table.headers, {}, kind.fields)
        # Every column of a field of the import is assigned to it; columns of custom fields follow them.
        labels = [field.label for field in kind.fields if field.label in table.headers]
        self.assertEqual(
            sorted(index for index in mapping.values() if index is not None), list(range(len(labels))), key
        )
        report = imports.run(kind, table, mapping, dry_run=True, user=user or self.importer).as_dict()
        problems = [row for row in report["rows"] if row["status"] != "unchanged"]
        self.assertTrue(report["ok"], (key, report["errors"], problems))
        self.assertEqual(
            report["row_counts"], {"new": 0, "changed": 0, "unchanged": len(table.rows), "error": 0}, (key, problems)
        )
        return report


# --- The files --------------------------------------------------------------------------------------


class HeadingTests(ExportData):
    """The columns are exactly those of the import, under its headings and in its order."""

    def test_every_import_has_its_export_with_its_headings(self) -> None:
        self.assertEqual([export.key for export in import_exports.exports()], list(KEYS))
        for key in KEYS:
            text = text_of(key)
            self.assertTrue(text.startswith("﻿"), key)  # UTF-8 with byte order mark, as every list (IMP-005)
            heading = text.lstrip("﻿").split("\r\n", 1)[0]
            self.assertEqual(heading.split(";"), [field.label for field in imports.get(key).fields], key)

    def test_the_file_name(self) -> None:
        self.assertEqual(import_exports.get("customers").file_name(), "kunden-importformat-2027-03-01.csv")
        self.assertEqual(import_exports.get("material").file_name(), "material-importformat-2027-03-01.csv")


class ClearTextTests(ExportData):
    """Names and numbers instead of IDs; dates, amounts and choices as the import reads them."""

    def test_material(self) -> None:
        rows = {row["ID"]: row for row in records(text_of("material"))}
        self.assertEqual(list(rows), ["0001", "0002", "0003", "0004", "0005", "0006"])
        mic = rows["0001"]
        self.assertEqual(
            (mic["Artikelname"], mic["Kategorie"], mic["Hersteller"], mic["Kurzname"], mic["Produkt (Artikelnummer)"]),
            ("SM58", "Ton > Mikrofone", "Shure", "58er", "T-100"),
        )
        self.assertEqual(mic["Beschreibung"], "Dynamisch\nNiere")  # line breaks stay
        self.assertEqual((mic["Rechnungsdatum"], mic["Kaufpreis"]), ("15.01.2026", "199,50"))
        self.assertEqual((mic["Gekauft (Händler)"], mic["Artikelnummer beim Händler"]), ("Thomann", "TH-58"))
        self.assertEqual(
            (mic["Lagerort"], mic["Status"], mic["Rechnungsnummer"]), ("Halle 2 > Regal A", "verfügbar", "RE-7")
        )
        self.assertEqual(rows["0002"]["Kaufpreis"], "#0001")  # MAT-054: the price is noted at 0001
        self.assertEqual((rows["0003"]["Leistung (W)"], rows["0003"]["Status"]), ("575,5", "gesperrt"))
        self.assertEqual(
            (rows["0004"]["Kategoriespezifische Angabe"], rows["0004"]["Einsatz/Verbindung"]), ("2,5 m", "0005")
        )
        self.assertEqual((rows["0005"]["Lagerort"], rows["0006"]["Menge (Mengenmaterial)"]), ("Halle 1", "12"))
        self.assertEqual(rows["0001"]["Menge (Mengenmaterial)"], "")  # an individual item counts 1
        self.assertNotIn(str(self.shelf.pk), {rows["0001"]["Lagerort"], rows["0001"]["Kategorie"]})

    def test_products(self) -> None:
        rows = {row["Art.-Nr."]: row for row in records(text_of("products"))}
        mic = rows["T-100"]
        self.assertEqual(
            (mic["Name"], mic["Kategorie"], mic["Art"], mic["Preis"], mic["Verkaufspreis"], mic["Höchstrabatt"]),
            ("Funkmikrofon", "Ton > Mikrofone", "Mietprodukt", "10,00", "", "12,5"),
        )
        self.assertEqual(
            (mic["Einheit"], mic["Steuerart"]), (self.mic_product.unit.name, self.mic_product.tax_rate.name)
        )
        self.assertEqual(
            (mic["Abrechnungsart"], mic["Mindestbestand"], mic["Aktiv"]), ("Tagesmiete je Stück", "2", "ja")
        )
        self.assertEqual((mic["Beschreibung"], mic["GTIN/EAN"]), ("Zeile 1\nZeile 2", "4006381333931"))
        sale = rows["V-010"]
        self.assertEqual(
            (sale["Art"], sale["Preis"], sale["Verkaufspreis"]), ("Verkaufs- oder Verbrauchsprodukt", "8,90", "8,90")
        )
        trailer = rows["S-901"]
        self.assertEqual(
            (
                trailer["Fahrzeugart"],
                trailer["Anhänger abrechnen"],
                trailer["Preis je km"],
                trailer["Interne Kosten je Tag"],
            ),
            ("Anhänger", "nach Kilometern", "0,30", "8,00"),
        )
        self.assertEqual((rows["S-900"]["Fahrzeugart"], rows["S-900"]["Interne Kosten je km"]), ("KFZ", "0,35"))
        self.assertEqual(rows["C-001"]["Eigentümer"], self.band.number)  # PRD-043: by customer number
        self.assertEqual(rows["L-010"]["Aktiv"], "nein")

    def test_customers(self) -> None:
        rows = {row["Nummer"]: row for row in records(text_of("customers"))}
        self.assertNotIn("Ehemals GmbH", str(rows))  # anonymised customers are left out
        self.assertNotIn(Customer.objects.get(anonymised_at__isnull=False).number, rows)
        firm = rows[self.firm.number]
        self.assertEqual(
            (firm["Name"], firm["Art"], firm["Zusatz"]),
            ("Kultur & Verein e. V.", "Firma oder Organisation", "Abteilung Technik"),
        )
        self.assertEqual(
            (firm["Telefon"], firm["Zahlungsziel (Tage)"], firm["Standardrabatt %"]), ("+49 30 1234", "14", "5,5")
        )
        self.assertEqual(
            (firm["Ansprechperson"], firm["Anrede"], firm["E-Mail der Ansprechperson"]),
            ("Max Muster", "Herr", "max@kv.example"),
        )
        self.assertEqual(
            (firm["Ansprechpartner 1"], firm["Ansprechpartner 1 Vorname"], firm["Ansprechpartner 1 Nachname"]),
            ("Buchhaltung", "Erika", "Beispiel"),
        )
        self.assertEqual((firm["Ansprechpartner 2"], firm["Ansprechpartner 2 Anrede"]), ("Hans Dampf", "Herr"))
        self.assertEqual((firm["Lieferadresse Straße"], firm["Lieferadresse Ort"]), ("Lagerweg 5", "Dorf-Nord"))
        private = next(row for row in rows.values() if row["Name"] == "Eva Privat")
        self.assertEqual((private["Art"], private["Aktiv"]), ("Privatperson", "nein"))

    def test_people(self) -> None:
        rows = {row["Name"]: row for row in records(text_of("people"))}
        self.assertNotIn("Anonymisiert", " ".join(rows))  # anonymised people are left out
        eva = rows["Licht, Eva"]
        self.assertEqual((eva["Vorname"], eva["Nachname"], eva["Art"]), ("Eva", "Licht", "Festangestellte"))
        self.assertEqual(eva["Funktionen"], "Licht: 28,00/250,00, Tontechnik")
        self.assertEqual((eva["Firma"], eva["Notiz"]), ("Licht & Ton", "Nur am Wochenende\nFührerschein C"))
        self.assertEqual(
            (rows["Ton, Tom"]["Art"], rows["Ton, Tom"]["Funktionen"]), ("Freie Kraft", "Tontechnik: /280,00")
        )

    def test_german_also_for_a_user_in_english(self) -> None:
        """UIX-029: the file is a file of the import – headings and values in German, whatever the language."""
        with translation.override("en"):
            text = text_of("products")
        self.assertIn("Mietprodukt", text)
        self.assertIn("10,00", text)


class RoundTripTests(ExportData):
    """Exported and imported again: every row is "unverändert"."""

    def test_every_export_comes_back_unchanged(self) -> None:
        for key in KEYS:
            with self.subTest(key):
                self.assert_round_trip(key, text_of(key))

    def test_also_when_imported_in_english(self) -> None:
        """The choices are German in the file; the import knows their German names in every language."""
        for key in KEYS:
            text = text_of(key)
            with self.subTest(key), translation.override("en"):
                self.assert_round_trip(key, text)

    def test_a_changed_cell_changes_only_that(self) -> None:
        text = text_of("material").replace("SN-1", "SN-1b")
        kind = imports.get("material")
        table = table_of(text)
        report = imports.run(
            kind, table, resolve_mapping(table.headers, {}, kind.fields), dry_run=True, user=self.importer
        ).as_dict()
        self.assertEqual(report["row_counts"], {"new": 0, "changed": 1, "unchanged": 5, "error": 0})
        (changed,) = [row for row in report["rows"] if row["status"] == "changed"]
        self.assertEqual([(change["old"], change["new"]) for change in changed["changes"]], [("SN-1", "SN-1b")])

    def test_a_shelf_of_the_same_name_is_found_by_its_path(self) -> None:
        """IMP-017: the import knows a storage location by its path – "Regal A" is twice in the warehouse."""
        self.assert_round_trip("material", text_of("material"))
        text = text_of("material").replace("Halle 2 > Regal A", "Halle 1 > Regal A")
        kind = imports.get("material")
        table = table_of(text)
        imports.run(kind, table, resolve_mapping(table.headers, {}, kind.fields), dry_run=False, user=self.importer)
        self.mic.refresh_from_db()
        self.assertEqual(self.mic.storage_location.path, "Halle 1 > Regal A")
        self.assertEqual(StorageLocation.objects.filter(name__contains=">").count(), 0)

    def test_an_unknown_path_creates_the_locations_level_by_level(self) -> None:
        """IMP-017: "Halle 2 > Regal Neu > Fach 3" creates "Regal Neu" below "Halle 2" and "Fach 3" below it."""
        text = text_of("material").replace("Halle 2 > Regal A", "Halle 2 > Regal Neu > Fach 3")
        kind = imports.get("material")
        table = table_of(text)
        imports.run(kind, table, resolve_mapping(table.headers, {}, kind.fields), dry_run=False, user=self.importer)
        self.mic.refresh_from_db()
        self.assertEqual(self.mic.storage_location.path, "Halle 2 > Regal Neu > Fach 3")
        self.assertEqual(StorageLocation.objects.filter(name__iexact="Halle 2").count(), 1)
        self.assertEqual(StorageLocation.objects.filter(name__contains=">").count(), 0)


class RightsTests(ExportData):
    """Columns of prices, purchase prices and rates only with their right – and the import keeps those values."""

    def test_material_without_purchase_prices(self) -> None:
        viewer = make_user("mona", roles=(role("Materialsicht", {"material": 1}),))
        text = text_of("material", viewer)
        self.assertNotIn("Kaufpreis", text)
        self.assertNotIn("199,50", text)
        self.assertIn("Kaufpreis", text_of("material", make_user("luka", roles=("Lager",))))
        self.assert_round_trip("material", text)
        self.mic.refresh_from_db()
        self.assertEqual(self.mic.purchase_price, Decimal("199.50"))

    def test_products_without_prices(self) -> None:
        warehouse = make_user("luka", roles=("Lager",))  # products read, purchase prices, no prices
        heading = text_of("products", warehouse).lstrip("﻿").split("\r\n", 1)[0].split(";")
        for column in ("Preis", "Verkaufspreis", "Höchstrabatt", "Preis je km", "Anhängerzuschlag je km"):
            self.assertNotIn(column, heading)
        self.assertIn("Interne Kosten je km", heading)
        no_costs = make_user("otto", roles=(role("Produktsicht", {"products": 1}),))
        self.assertNotIn("Interne Kosten je Tag", text_of("products", no_costs))
        self.assert_round_trip("products", text_of("products", no_costs))

    def test_customers_without_prices(self) -> None:
        viewer = make_user("kai", roles=(role("Kundensicht", {"customers": 1}),))
        text = text_of("customers", viewer)
        self.assertNotIn("Standardrabatt", text)
        self.assert_round_trip("customers", text)

    def test_people_without_personnel_costs(self) -> None:
        viewer = make_user("pia", roles=(role("Personalsicht", {"personnel": 1}),))
        rows = {row["Name"]: row for row in records(text_of("people", viewer))}
        self.assertEqual(rows["Licht, Eva"]["Funktionen"], "Licht, Tontechnik")
        self.assertNotIn("28,00", text_of("people", viewer))
        self.assert_round_trip("people", text_of("people", viewer))
        rates = {rate.job_function.name: rate.hourly_rate for rate in current_rates(self.eva)}
        self.assertEqual(rates["Licht"], Decimal("28.00"))


class FormulaTests(ExportData):
    """Text that would be a formula gets an apostrophe; the import takes it away again ("CSV injection")."""

    def test_cells(self) -> None:
        self.assertEqual(cell('=HYPERLINK("x")'), '\'=HYPERLINK("x")')
        self.assertEqual(cell("@SUMME(A1)"), "'@SUMME(A1)")
        self.assertEqual(cell("- defekt"), "'- defekt")
        self.assertEqual(cell("'=x"), "''=x")
        self.assertEqual(cell("+49 30 1234"), "+49 30 1234")  # a number, no formula
        self.assertEqual(cell("-12,50"), "-12,50")
        self.assertEqual((cell(None), cell(True), cell(False)), ("", "ja", "nein"))
        self.assertEqual(
            (cell(datetime.date(2027, 3, 1)), cell(Decimal("1234.50")), amount(Decimal("3"))),
            ("01.03.2027", "1234,5", "3,00"),
        )
        self.assertEqual((cell_text("'=x"), cell_text("''=x"), cell_text("'Hallo")), ("=x", "'=x", "'Hallo"))

    def test_in_the_file_and_back(self) -> None:
        rows = {row["ID"]: row for row in records(text_of("material"))}
        self.assertEqual(rows["0001"]["Notiz"], '\'=HYPERLINK("http://example.org")')
        self.assertEqual(rows["0003"]["Notiz"], "'- Linse fehlt\nzweite Zeile")
        self.assertEqual(rows["0005"]["Notiz"], "''=nicht rechnen")
        self.assert_round_trip("material", text_of("material"))


class CustomFieldTests(ExportData):
    """MAT-073: a column per custom field, headed with its name, as the material import reads it."""

    def setUp(self) -> None:
        super().setUp()
        from rentalars.customfields import services
        from rentalars.customfields.models import CustomField, Fieldset, FieldsetEntry
        from rentalars.customfields.models import FieldType as CustomType

        self.length = CustomField.objects.create(name="Kabellänge", field_type=CustomType.NUMBER, unit="m")
        checked = CustomField.objects.create(name="Geprüft am", field_type=CustomType.DATE)
        wireless = CustomField.objects.create(name="Funk", field_type=CustomType.BOOLEAN)
        insurance = CustomField.objects.create(name="Versicherungswert", field_type=CustomType.TEXT, is_sensitive=True)
        # "EK" is a heading of the purchase price: without that column in the file the import would take it.
        cost = CustomField.objects.create(name="EK", field_type=CustomType.TEXT)
        fieldset = Fieldset.objects.create(name="Mikrofone")
        for position, field in enumerate((self.length, checked, wireless, insurance, cost), start=1):
            FieldsetEntry.objects.create(fieldset=fieldset, field=field, position=position)
        services.assign_fieldset(self.mic.material_model, fieldset)
        services.store_values(
            self.mic, {self.length: "12.5", checked: "2027-02-01", wireless: "yes", insurance: "=500 EUR", cost: "A7"}
        )

    def test_the_columns_and_values(self) -> None:
        text = text_of("material")
        heading = table_of(text).headers
        labels = [field.label for field in imports.get("material").fields]
        self.assertEqual(heading, [*labels, "EK", "Funk", "Geprüft am", "Kabellänge", "Versicherungswert"])
        mic = records(text)[0]
        self.assertEqual(
            (mic["Kabellänge"], mic["Geprüft am"], mic["Funk"], mic["Versicherungswert"], mic["EK"]),
            ("12,5 m", "01.02.2027", "ja", "'=500 EUR", "A7"),
        )
        self.assertEqual(records(text)[1]["Kabellänge"], "")
        self.assert_round_trip("material", text)

    def test_without_purchase_prices(self) -> None:
        viewer = make_user("mona", roles=(role("Materialsicht", {"material": 1}),))
        text = text_of("material", viewer)
        heading = table_of(text).headers
        self.assertNotIn("Versicherungswert", heading)  # visible only with the right to see purchase prices
        self.assertNotIn("EK", heading)  # without the column "Kaufpreis" the import would read it as the price
        self.assertIn("Kabellänge", heading)
        self.assert_round_trip("material", text)

    def test_a_changed_value(self) -> None:
        text = text_of("material").replace("12,5 m", "15 m")
        kind = imports.get("material")
        table = table_of(text)
        imports.run(kind, table, resolve_mapping(table.headers, {}, kind.fields), dry_run=False, user=self.importer)
        from rentalars.customfields.services import forget_values, stored_values

        forget_values(self.mic)
        self.assertEqual(stored_values(self.mic)[self.length.pk], "15")


class QueryTests(ExportData):
    """The queries of an export do not grow with its rows (no query per row)."""

    def queries(self, key: str) -> int:
        text_of(key)  # what is kept in memory (the width of IDs) is read before
        with CaptureQueriesContext(connection) as captured:
            text_of(key)
        return len(captured)

    def test_constant_queries(self) -> None:
        before = {key: self.queries(key) for key in KEYS}
        for number in range(10):
            model = MaterialModel.objects.create(name=f"Modell {number}", category=self.mics)
            make_item(model, 100 + number, storage_location=self.shelf, supplier=Supplier.objects.first())
            make_product(f"T-2{number:02d}", f"Produkt {number}", category=self.mics)
            customer = make_customer(f"Kunde {number}")
            Contact.objects.create(customer=customer, name=f"Kontakt {number}")
            make_person(f"Person{number} Neu", rates={"Licht": "20.00"})
        after = {key: self.queries(key) for key in KEYS}
        self.assertEqual(after, before)
        self.assertLessEqual(max(after.values()), 7)


class LargeExportTests(RentalarsTestCase):
    """20,000 items in well under ten seconds; a few queries per chunk of 2,000 rows, none per row (NFA-041)."""

    def test_twenty_thousand_items(self) -> None:
        location = StorageLocation.objects.create(name="Halle 1")
        models = MaterialModel.objects.bulk_create(
            MaterialModel(name=f"Modell {number}", category=category("L"), power_w=Decimal("100"))
            for number in range(200)
        )
        MaterialItem.objects.bulk_create(
            MaterialItem(
                inventory_number=number,
                material_model=models[number % 200],
                serial_number=f"SN-{number}",
                purchase_price=Decimal("99.90"),
                purchase_date=datetime.date(2026, 5, 1),
                storage_location=location,
            )
            for number in range(1, 20_001)
        )
        text_of("material")
        with CaptureQueriesContext(connection) as captured:
            started = time.monotonic()
            text = text_of("material")
            seconds = time.monotonic() - started
        self.assertEqual(text.count("\r\n"), 20_001)
        self.assertLess(seconds, 10, f"{seconds:.1f} s")
        # Six queries, and one more (the custom values) per chunk of 2,000 items.
        self.assertLessEqual(len(captured), 6 + 20_000 // import_exports.CHUNK_ROWS)


# --- Pages and API ---------------------------------------------------------------------------------


class ExportPageTests(UiTestCase):
    """Next to each import under Einstellungen → Import und Export, and on the import page."""

    def test_the_settings_offer_each_export(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        for key, name in (
            ("material", "Material"),
            ("products", "Produkte"),
            ("customers", "Kunden"),
            ("people", "Personen"),
        ):
            url = reverse("core:import_export", args=[key])
            self.assertIn(f'href="{url}"', page)
            self.assertIn(f'Export im Importformat<span class="visually-hidden"> – {name}</span>', page)
        self.assertIn("Der Export im Importformat ist eine CSV-Datei mit den Spalten des Imports", page)
        self.assertNotIn(reverse("core:full_export"), page)  # IMP-006: the full export is under "Sicherung"
        self.assertIn("die letzte nächtliche Sicherung; der lesbare Export aller Daten", page)
        self.assertIn(f'href="{reverse("core:backup")}#export">Sicherung → Lesbarer Export aller Daten</a>', page)

    def test_who_may_read_a_list_may_export_it(self) -> None:
        reader = self.browser_for("rita", role("Einsicht", {"administration": 1, "material": 1}))
        page = self.assert_ok(reader.get(reverse("core:administration")))
        self.assertIn(reverse("core:import_export", args=["material"]), page)
        self.assertNotIn(reverse("material:import"), page)
        self.assertNotIn(reverse("core:import_export", args=["customers"]), page)
        response = reader.get(reverse("core:import_export", args=["material"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reader.get(reverse("core:import_export", args=["customers"])).status_code, 403)

    def test_the_download(self) -> None:
        make_customer("Kulturverein")
        response = self.client.get(reverse("core:import_export", args=["customers"]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)  # written while it is sent
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="kunden-importformat-2027-03-01.csv"', response["Content-Disposition"])
        self.assertIn("Kulturverein", downloaded(response))
        # AUT-028: who exported customers is in the access log, as for the CSV file of the list.
        entry = AccessLogEntry.objects.get(object_type=AccessKind.LIST)
        self.assertEqual((entry.action, entry.label), ("export", "kunden-importformat-2027-03-01.csv"))

    def test_the_import_page_offers_the_export(self) -> None:
        for key, url in (("material", reverse("material:import")), ("people", reverse("core:import", args=["people"]))):
            page = self.assert_ok(self.client.get(url))
            self.assertIn(f'href="{reverse("core:import_export", args=[key])}"', page)
            self.assertIn("Was Rentalars jetzt hat, in den Spalten dieses Imports", page)

    def test_refused(self) -> None:
        crew = self.browser_for("chris", "Crew")
        self.assertEqual(crew.get(reverse("core:import_export", args=["material"])).status_code, 403)
        self.assertEqual(self.client.get("/import/nothing/export/").status_code, 404)
        self.client.logout()
        response = self.client.get(reverse("core:import_export", args=["material"]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])


class ExportApiTests(ApiTestCase):
    """API-002, API-014: ``GET /imports/{kind}/export`` for every import."""

    def test_every_export_through_the_api(self) -> None:
        make_customer("Kulturverein")
        make_person("Eva Licht", rates={"Licht": "28.00"})
        for key in KEYS:
            response = self.admin.get(f"{API}/imports/{key}/export")
            self.assertEqual(response.status_code, 200, key)
            self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
            text = downloaded(response)
            self.assertEqual(table_of(text).headers, [field.label for field in imports.get(key).fields], key)
            # Sent back to the import, it changes nothing.
            upload = io.BytesIO(text.encode("utf-8"))
            upload.name = f"{key}.csv"
            report = self.admin.post(f"{API}/imports/{key}", {"file": upload, "dry_run": "true"}, format="multipart")
            self.assertEqual(report.status_code, 200, report.content[:300])
            counts = report.json()["row_counts"]
            self.assertEqual((counts["new"], counts["changed"], counts["error"]), (0, 0, 0), key)

    def test_rights_and_unknown_lists(self) -> None:
        make_product("T-100", "Funkmikrofon")
        warehouse = self.client_for("luka", "Lager")
        heading = table_of(downloaded(warehouse.get(f"{API}/imports/products/export"))).headers
        self.assertNotIn("Preis", heading)
        self.assertIn("Art.-Nr.", heading)
        self.assertEqual(self.client_for("chris", "Crew").get(f"{API}/imports/material/export").status_code, 403)
        self.assertEqual(self.admin.get(f"{API}/imports/nothing/export").status_code, 404)


# --- Requirement 1: the full export under "Sicherung" ----------------------------------------------------------


class FullExportUnderBackupTests(UiTestCase):
    """IMP-006: a section of the page "Sicherung und Verschlüsselung", with the difference to a backup."""

    def test_the_section_explains_the_difference(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        self.assertIn('<h2 id="export-title">Lesbarer Export aller Daten</h2>', page)
        self.assertIn("Eine Sicherung dient dazu, Rentalars wiederherzustellen", page)
        self.assertIn("ohne Passwörter, Schlüssel und andere Geheimnisse", page)
        self.assertIn("nicht zum Wiederherstellen von Rentalars", page)
        self.assertIn("Die Sicherungen von Datenbank und Dateien, ihre Verschlüsselung und der lesbare Export", page)
        self.assertIn("Die ZIP-Datei ist nicht verschlüsselt", page)
        self.assertIn(f'action="{reverse("core:full_export")}"', page)
        self.assertIn("Vollständigen Export erstellen", page)
        self.assertIn(
            f'href="{reverse("core:administration")}#settings-import">Einstellungen → Import und Export</a>', page
        )

    def test_the_address_belongs_to_the_backup(self) -> None:
        """NFA-074: the page lives under /administration/backup/.

        It was the target of a form only (POST), so there is no bookmark to forward.
        """
        self.assertEqual(reverse("core:full_export"), "/administration/backup/export/")
        self.assertEqual(self.client.post("/administration/export/").status_code, 404)

    def test_making_the_export(self) -> None:
        make_customer("Kulturverein")
        response = self.client.post(reverse("core:full_export"), follow=True)
        job = BackgroundJob.objects.get(kind="export")
        self.assertRedirects(response, reverse("core:job", args=[job.pk]))
        self.assertEqual(job.status, "done", job.message)
        content = b"".join(self.client.get(reverse("core:job_result", args=[job.pk])).streaming_content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertIn("Kulturverein", archive.read("csv/customers.customer.csv").decode("utf-8-sig"))

    def test_rights_as_before(self) -> None:
        """Those who may delete in the settings, as for a backup; others read why there is no button."""
        reader = self.browser_for("dana", role("Datenschutz", {"administration": 1}))
        page = self.assert_ok(reader.get(reverse("core:backup")))
        self.assertIn("Den vollständigen Export erstellt, wer in den Einstellungen löschen darf.", page)
        self.assertNotIn(f'action="{reverse("core:full_export")}"', page)
        self.assertEqual(reader.post(reverse("core:full_export")).status_code, 403)
        self.assertFalse(BackgroundJob.objects.filter(kind="export").exists())
