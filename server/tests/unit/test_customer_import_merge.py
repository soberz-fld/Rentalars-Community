# SPDX-License-Identifier: GPL-3.0-or-later
"""Customer import from a Lexware contact export, merging instead of duplicating (IMP-013)."""

from __future__ import annotations

import io
from typing import Any

from rentalars.core import imports
from rentalars.core.tabular import Table, decode_text, read_table, resolve_mapping
from rentalars.customers.importer import has_legal_form, name_key, same_address
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress, CustomerKind
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, make_customer

#: The heading row of a contact export of Lexware, exactly as a user sent it.
LEXWARE_HEADING_ROW = (
    "Kundennummer;Lieferantennummer;Firmenname;Anrede;Kontakt;Vorname;Nachname;Steuernummer;Umsatzsteuer ID;"
    "Adresszusatz 1;Straße 1;PLZ 1;Ort 1;Land 1;Adresszusatz 2;Straße 2;PLZ 2;Ort 2;Land 2;Telefon 1;Telefon 2;"
    "E-Mail 1;E-Mail 2;Ansprechpartner 1;Ansprechpartner 1 Anrede;Ansprechpartner 1 Vorname;"
    "Ansprechpartner 1 Nachname;Ansprechpartner 1 E-Mail;Ansprechpartner 1 Telefon;Ansprechpartner 2;"
    "Ansprechpartner 2 Anrede;Ansprechpartner 2 Vorname;Ansprechpartner 2 Nachname;Ansprechpartner 2 E-Mail;"
    "Ansprechpartner 2 Telefon"
)
LEXWARE_HEADER = LEXWARE_HEADING_ROW.split(";")


def _column(heading: str) -> str:
    return heading.replace(" ", "_").replace("-", "_").replace("ß", "ss")


def lexware_row(**values: str) -> list[str]:
    """A row of the export; keyword arguments name the columns with "_" for spaces and "ss" for "ß"."""
    unknown = set(values) - {_column(heading) for heading in LEXWARE_HEADER}
    assert not unknown, unknown
    return [values.get(_column(heading), "") for heading in LEXWARE_HEADER]


def lexware_file(*rows: list[str]) -> bytes:
    """The export as Lexware writes it: Windows-1252, semicolons, every value in quotes, CRLF."""
    lines = [";".join(f'"{value}"' for value in row) for row in (LEXWARE_HEADER, *rows)]
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


KULTURVEREIN = lexware_row(
    Kundennummer="20001",
    Lieferantennummer="70001",
    Firmenname="Kulturverein Dorf e. V.",
    Steuernummer="12/345/67890",
    Umsatzsteuer_ID="DE 123 456 789",
    Adresszusatz_1="Bühne im Hof",
    Strasse_1="Hauptstraße 5",
    PLZ_1="12345",
    Ort_1="Dorf",
    Land_1="Deutschland",
    Strasse_2="Lagerweg 2",
    PLZ_2="12345",
    Ort_2="Dorf",
    Telefon_1="0123 4567",
    Telefon_2="0171 9999999",
    E_Mail_1="info@kulturverein-dorf.example",
    E_Mail_2="kasse@kulturverein-dorf.example",
    Ansprechpartner_1="Eva Müller",
    Ansprechpartner_1_Anrede="Frau",
    Ansprechpartner_1_Vorname="Eva",
    Ansprechpartner_1_Nachname="Müller",
    Ansprechpartner_1_E_Mail="eva@kulturverein-dorf.example",
    Ansprechpartner_1_Telefon="0123 45678",
    Ansprechpartner_2="Kasse",
    Ansprechpartner_2_Anrede="Herr",
    Ansprechpartner_2_Vorname="Jörg",
    Ansprechpartner_2_Nachname="Weiß",
)
PRIVATE = lexware_row(
    Kundennummer="20002",
    Anrede="Herr",
    Vorname="Jürgen",
    Nachname="Groß",
    Strasse_1="Am Bach 3",
    PLZ_1="54321",
    Ort_1="Stadt",
    E_Mail_1="juergen.gross@example.de",
)
BUEHNE = lexware_row(
    Kundennummer="20003",
    Firmenname="Mueller Buehnentechnik GmbH",
    Strasse_1="Neuer Weg 9",
    PLZ_1="99999",
    Ort_1="Neustadt",
    Telefon_1="0555 1",
)
STUDIO = lexware_row(Kundennummer="20004", Firmenname="Tonstudio Nord", E_Mail_1="studio@nord.example")


def run_file(data: bytes, *, dry_run: bool = False) -> Any:
    kind = imports.get("customers")
    table = read_table(io.BytesIO(data), "kontakte.csv")
    return kind.run(table, resolve_mapping(table.headers, {}, kind.fields), dry_run=dry_run, rights=ALL_RIGHTS)


def run_rows(rows: list[list[Any]], *, dry_run: bool = False) -> Any:
    kind = imports.get("customers")
    table = Table(headers=[str(cell) for cell in rows[0]], rows=[list(row) for row in rows[1:]])
    return kind.run(table, resolve_mapping(table.headers, {}, kind.fields), rights=ALL_RIGHTS, dry_run=dry_run)


def messages(report: Any) -> str:
    return " ".join(issue.message for issue in report.warnings)


class ReadingTests(RentalarsTestCase):
    """IMP-013 (a): the encoding of a CSV file is recognised by itself."""

    def test_encodings(self) -> None:
        text = "Name;Straße\nMüller;Hauptstraße 5 – Hof\n"
        self.assertEqual(decode_text(text.encode("cp1252")), text)
        self.assertEqual(decode_text(text.encode("utf-8")), text)
        self.assertEqual(decode_text(b"\xef\xbb\xbf" + text.encode("utf-8")), text)
        self.assertEqual(decode_text(text.encode("utf-16")), text)
        # ISO-8859-1 for the bytes Windows-1252 does not define.
        self.assertEqual(decode_text("Grüße".encode("latin-1") + b"\x81"), "Grüße\x81")
        for data in (text.encode("cp1252"), b"\xef\xbb\xbf" + text.encode("utf-8"), text.encode("utf-8")):
            table = read_table(io.BytesIO(data), "liste.csv")
            self.assertEqual((table.headers, table.rows), (["Name", "Straße"], [["Müller", "Hauptstraße 5 – Hof"]]))

    def test_lexware_headings_are_recognised(self) -> None:
        table = read_table(io.BytesIO(lexware_file(KULTURVEREIN)), "kontakte.csv")
        self.assertEqual(table.headers[10], "Straße 1")
        mapping = resolve_mapping(table.headers, {}, imports.get("customers").fields)
        column = {key: table.headers[index] for key, index in mapping.items() if index is not None}
        self.assertEqual(
            [column[key] for key in ("number", "name", "salutation", "contact_name", "first_name", "last_name")],
            ["Kundennummer", "Firmenname", "Anrede", "Kontakt", "Vorname", "Nachname"],
        )
        self.assertEqual(
            [column[key] for key in ("tax_number", "vat_id", "name_addition", "street", "postal_code", "city")],
            ["Steuernummer", "Umsatzsteuer ID", "Adresszusatz 1", "Straße 1", "PLZ 1", "Ort 1"],
        )
        self.assertEqual(
            [column[f"delivery_{key}"] for key in ("name_addition", "street", "postal_code", "city", "country")],
            ["Adresszusatz 2", "Straße 2", "PLZ 2", "Ort 2", "Land 2"],
        )
        self.assertEqual(
            [column[key] for key in ("phone", "phone_2", "email", "email_2")],
            ["Telefon 1", "Telefon 2", "E-Mail 1", "E-Mail 2"],
        )
        for number, first in ((1, 23), (2, 29)):
            parts = ("name", "salutation", "first_name", "last_name", "email", "phone")
            self.assertEqual([column[f"contact{number}_{part}"] for part in parts], LEXWARE_HEADER[first : first + 6])
        self.assertNotIn("Lieferantennummer", column.values())

    def test_comparing_names_and_addresses(self) -> None:
        self.assertEqual(name_key("Müller GmbH"), name_key("MUELLER  gmbh"))
        self.assertEqual(name_key("Kulturverein Dorf e. V."), name_key("kulturverein dorf"))
        self.assertNotEqual(name_key("Müller Licht GmbH"), name_key("Müller Ton GmbH"))
        self.assertEqual(name_key("AB"), "")
        self.assertTrue(has_legal_form("Müller GmbH & Co. KG"))
        self.assertTrue(has_legal_form("Kulturverein e. V."))
        self.assertFalse(has_legal_form("Jürgen Groß"))
        self.assertTrue(same_address(("Hauptstr. 5", "12345", "Dorf"), ("Hauptstraße 5", "12345", "DORF")))
        self.assertTrue(same_address(("Lagerweg 2", "", "Dorf"), ("Lagerweg 2", "12345", "Dorf")))
        self.assertFalse(same_address(("Lagerweg 2", "12346", "Dorf"), ("Lagerweg 2", "12345", "Dorf")))
        self.assertFalse(same_address(("Lagerweg 3", "12345", "Dorf"), ("Lagerweg 2", "12345", "Dorf")))


class LexwareImportTests(RentalarsTestCase):
    """IMP-013 (b): a Lexware export creates customers with contacts and both addresses."""

    def test_new_customers_from_the_export(self) -> None:
        report = run_file(lexware_file(KULTURVEREIN, PRIVATE))
        self.assertTrue(report.ok, report.errors)
        self.assertEqual((report.created, report.updated, report.unchanged), (2, 0, 0))
        self.assertEqual(report.notes, ["Die Spalte „Lieferantennummer“ wird nicht übernommen."])
        self.assertEqual([row.text for row in report.rows], ["neu", "neu"])

        verein = Customer.objects.get(number="20001")
        self.assertEqual(
            (verein.name, verein.kind, verein.name_addition, verein.street, verein.city, verein.country),
            ("Kulturverein Dorf e. V.", CustomerKind.COMPANY, "Bühne im Hof", "Hauptstraße 5", "Dorf", "Deutschland"),
        )
        self.assertEqual((verein.vat_id, verein.tax_number), ("DE123456789", "12/345/67890"))
        self.assertEqual((verein.email, verein.phone), ("info@kulturverein-dorf.example", "0123 4567"))
        self.assertEqual(
            verein.note, "Weitere E-Mail: kasse@kulturverein-dorf.example\nWeitere Telefonnummer: 0171 9999999"
        )
        self.assertEqual(
            [(c.salutation, c.name, c.position, c.email, c.is_primary) for c in verein.contacts.all()],
            [
                ("Frau", "Eva Müller", "", "eva@kulturverein-dorf.example", True),
                ("Herr", "Jörg Weiß", "Kasse", "", False),
            ],
        )
        delivery = verein.addresses.get()
        self.assertEqual(
            (delivery.kind, delivery.street, delivery.postal_code, delivery.city, delivery.is_default),
            (AddressKind.DELIVERY, "Lagerweg 2", "12345", "Dorf", True),
        )
        person = Customer.objects.get(number="20002")
        self.assertEqual((person.name, person.kind, person.street), ("Jürgen Groß", CustomerKind.PRIVATE, "Am Bach 3"))
        self.assertFalse(person.contacts.exists())

        again = run_file(lexware_file(KULTURVEREIN, PRIVATE))
        self.assertEqual((again.created, again.updated, again.unchanged), (0, 0, 2))
        self.assertEqual([row.text for row in again.rows], ["unverändert", "unverändert"])
        self.assertEqual((Contact.objects.count(), CustomerAddress.objects.count()), (2, 1))


class MergeTests(RentalarsTestCase):
    """IMP-013 (c): existing customers are found and completed, never duplicated or emptied."""

    def setUp(self) -> None:
        super().setUp()
        self.by_vat = make_customer("KV Dorf")
        self.by_vat.vat_id, self.by_vat.phone = "DE123456789", "0999 1"
        self.by_vat.street, self.by_vat.postal_code, self.by_vat.city = "Hauptstr. 5", "12345", "Dorf"
        self.by_vat.save()
        Contact.objects.create(customer=self.by_vat, name="E. Müller", email="EVA@kulturverein-dorf.example")
        CustomerAddress.objects.create(
            customer=self.by_vat, kind=AddressKind.DELIVERY, street="Lagerweg 2", city="Dorf"
        )
        self.by_email = make_customer("J. Groß")
        self.by_email.kind, self.by_email.email = CustomerKind.PRIVATE, "juergen.gross@example.de"
        self.by_email.save()
        self.by_name = make_customer("MÜLLER Bühnentechnik GmbH")
        self.by_name.street, self.by_name.city, self.by_name.email = "Alter Weg 1", "Altstadt", "alt@buehne.example"
        self.by_name.save()
        self.by_contact = make_customer("Studio Nord Tontechnik")
        Contact.objects.create(customer=self.by_contact, name="Studio", email="studio@nord.example")

    def test_found_by_vat_id_email_and_name(self) -> None:
        data = lexware_file(KULTURVEREIN, PRIVATE, BUEHNE, STUDIO)
        dry = run_file(data, dry_run=True)
        self.assertTrue(dry.ok, dry.errors)
        self.assertEqual((dry.created, dry.updated, dry.unchanged), (0, 4, 0))
        self.assertEqual(
            [row.text for row in dry.rows],
            [
                f"zusammengeführt mit {self.by_vat.number} „KV Dorf“ (gefunden über die USt-IdNr.)",
                f"zusammengeführt mit {self.by_email.number} „J. Groß“ (gefunden über die E-Mail-Adresse)",
                f"zusammengeführt mit {self.by_name.number} „MÜLLER Bühnentechnik GmbH“ (gefunden über den Namen)",
                f"zusammengeführt mit {self.by_contact.number} „Studio Nord Tontechnik“ "
                "(gefunden über die E-Mail-Adresse)",
            ],
        )
        self.assertIn(
            f"Die Datei nennt die Nummer 20001; der Kunde behält seine Nummer {self.by_vat.number}.",
            dry.rows[0].notes,
        )
        self.assertEqual(Customer.objects.count(), 4)
        self.assertEqual(Customer.objects.get(pk=self.by_vat.pk).name, "KV Dorf")  # the dry run wrote nothing

        report = run_file(data)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(Customer.objects.count(), 4)
        verein = Customer.objects.get(pk=self.by_vat.pk)
        self.assertEqual(
            (verein.number, verein.name, verein.tax_number),
            (self.by_vat.number, "Kulturverein Dorf e. V.", "12/345/67890"),
        )
        # Telefon 1 of the file wins. "Hauptstr. 5" is "Hauptstraße 5": no move, no old address kept.
        self.assertEqual((verein.phone, verein.street), ("0123 4567", "Hauptstraße 5"))
        # The contact with the same e-mail address is completed, not duplicated.
        self.assertEqual(
            [(c.salutation, c.name, c.phone) for c in verein.contacts.all()],
            [("Frau", "E. Müller", "0123 45678"), ("Herr", "Jörg Weiß", "")],
        )
        # The delivery address existed without postal code; it is completed, not added again.
        self.assertEqual([(a.street, a.postal_code) for a in verein.addresses.all()], [("Lagerweg 2", "12345")])

        person = Customer.objects.get(pk=self.by_email.pk)
        self.assertEqual((person.name, person.street, person.kind), ("Jürgen Groß", "Am Bach 3", CustomerKind.PRIVATE))

        buehne = Customer.objects.get(pk=self.by_name.pk)
        # Only the spelling differs: Rentalars keeps its own. Empty cells keep what is there.
        self.assertEqual(
            (buehne.name, buehne.email, buehne.street, buehne.phone),
            ("MÜLLER Bühnentechnik GmbH", "alt@buehne.example", "Neuer Weg 9", "0555 1"),
        )
        old = buehne.addresses.get()
        self.assertEqual((old.kind, old.street, old.city), (AddressKind.BILLING, "Alter Weg 1", "Altstadt"))
        self.assertIn("Die bisherige Adresse bleibt als weitere Rechnungsadresse erhalten.", report.rows[2].notes)

        studio = Customer.objects.get(pk=self.by_contact.pk)
        self.assertEqual((studio.name, studio.email), ("Tonstudio Nord", "studio@nord.example"))

        again = run_file(data)
        self.assertEqual((again.created, again.updated, again.unchanged), (0, 0, 4))
        self.assertEqual((Contact.objects.count(), CustomerAddress.objects.count()), (3, 2))

    def test_number_of_the_file_and_of_rentalars(self) -> None:
        rows = [["Kundennummer", "Firmenname", "Telefon 1", "E-Mail 1"], [self.by_vat.number, "KV Dorf e. V.", "", ""]]
        report = run_rows(rows)
        self.assertEqual(
            report.rows[0].text,
            f"zusammengeführt mit {self.by_vat.number} „KV Dorf“ (gefunden über die Kundennummer)",
        )
        self.assertEqual(report.rows[0].notes, [])
        self.assertEqual(Customer.objects.get(pk=self.by_vat.pk).phone, "0999 1")
        self.assertEqual(run_rows(rows).rows[0].text, "unverändert")
        self.assertEqual(report.warnings, [])
        # The number of another program meets a different customer: the dry run warns.
        foreign = run_rows([["Kundennummer", "Firmenname"], [self.by_name.number, "Ganz anderer Verein"]], dry_run=True)
        self.assertEqual(foreign.rows[0].found_by, "number")
        self.assertIn(
            f"In Rentalars ist {self.by_name.number} „MÜLLER Bühnentechnik GmbH“ und hat sonst nichts mit dieser Zeile",
            messages(foreign),
        )

    def test_conservative_where_it_is_not_clear(self) -> None:
        company = make_customer("Jürgen Groß GmbH")
        Contact.objects.create(customer=company, name="Jürgen", email="chef@gross-gmbh.example")
        first, second = make_customer("Stadtwerke Nord"), make_customer("Stadtwerke Süd")
        for customer in (first, second):
            customer.vat_id = "DE111111111"
            customer.save()
        rows = [
            ["Firmenname", "Vorname", "Nachname", "Umsatzsteuer ID", "E-Mail 1"],
            ["", "Jürgen", "Groß", "", "chef@gross-gmbh.example"],
            ["Stadtwerke Musterstadt", "", "", "DE111111111", ""],
            ["Stadtwerke Nord", "", "", "DE111111111", ""],
            ["STADTWERKE NORD", "", "", "", ""],
        ]
        report = run_rows(rows)
        self.assertTrue(report.ok, report.errors)
        # A private person is neither the company whose contact has its e-mail address,
        # nor the company with the same name and a legal form.
        self.assertEqual(report.rows[0].outcome, "created")
        self.assertEqual(Customer.objects.get(number=report.rows[0].customer).kind, CustomerKind.PRIVATE)
        # Two customers with the VAT ID and none with the name: a new customer and a note naming both.
        self.assertEqual(report.rows[1].outcome, "created")
        self.assertIn(f"Mehrere Kunden passen ({first.number}, {second.number})", messages(report))
        # The name narrows the two down.
        self.assertEqual((report.rows[2].customer, report.rows[2].found_by), (first.number, "vat_id"))
        # A customer is found by one row only; the next row like it becomes a new customer with a note.
        self.assertEqual(report.rows[3].outcome, "created")
        self.assertIn(f"{first.number} Stadtwerke Nord", messages(report))

    def test_existing_rules_stay(self) -> None:
        """IMP-013 (d): errors stop everything, numbers occur once, a name is needed."""
        rows = [
            ["Kundennummer", "Firmenname", "E-Mail 1"],
            [self.by_vat.number, "KV Dorf", "keine-adresse"],
            ["", "Sportverein", ""],
            [self.by_vat.number, "KV Dorf", ""],
        ]
        report = run_rows(rows)
        self.assertEqual([issue.row for issue in report.errors], [2, 4])
        self.assertFalse(Customer.objects.filter(name="Sportverein").exists())
        unnamed = run_rows([["Firmenname", "Vorname"], ["", ""]])
        self.assertEqual([str(issue) for issue in unnamed.errors], ["Zeile 2, Name: Der Name fehlt."])
        self.assertEqual(run_rows([["Ort"], ["Dorf"]]).errors[0].column, "Name")
