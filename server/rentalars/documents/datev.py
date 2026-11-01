# SPDX-License-Identifier: GPL-3.0-or-later
"""The invoices of a period for the tax adviser, in the DATEV format (DOK-012).

DATEV Rechnungswesen imports CSV files in the "DATEV-Format" (formerly
"EXTF"; description in the DATEV developer portal, developer.datev.de,
"DATEV-Format"). Each file has

1. a **header line** of 31 fields: "EXTF", header version 700, the data
   category (21 Buchungsstapel, 16 Debitoren/Kreditoren), the format name
   and version (Buchungsstapel 13, Debitoren/Kreditoren 5), when it was
   made, consultant and client number, start of the fiscal year, length of
   the general ledger accounts, the period, a name and the currency;
2. a line with the **names of the columns**;
3. one line per **booking** or account.

Fields are separated by ``;``, texts are put in ``"…"``, amounts have a
decimal comma and no sign, dates of documents are written ``DDMM`` (the year
comes from the period of the header), and the file is in Windows-1252
("ANSI") with CRLF line ends. Characters Windows-1252 does not have lose
their accent ("ő" → "o") or become "?".

The bookings (Buchungsstapel)
-----------------------------
One line per invoice and tax rate: the gross amount of the rate, debit on
the debitor account of the customer, credit on the revenue account of the
rate. The revenue accounts of the charts of accounts – SKR 03 8400 and 8300,
SKR 04 4400 and 4300 – are "automatic accounts": DATEV books the output tax
itself, so no tax key (BU-Schlüssel) is written. The accounts per rate can be
changed in the settings; a rate without account stops the export with a
message.

A cancellation is a document of its own with its own number; its lines are
the reverse bookings of the invoice: the same accounts with "H" (credit on
the debitor) instead of "S". A cancelled invoice and its cancellation are
both in the export of their periods.

The debitor account is the customer number plus an offset (customer 10001 →
debitor 10001 with offset 0), or one collective account for all customers.
DATEV takes as debitors the numbers with one digit more than the general
ledger accounts, from 1… to 6…: 10000 to 69999 with accounts of four digits.

The debitors (Debitoren/Kreditoren)
-----------------------------------
On request a second file with the customers of the invoices of the period as
debitor accounts: name, address, VAT ID, e-mail address, phone, customer
number and payment terms – as they are now in Rentalars.

Neither file is "locked" (Festschreibung 0): the tax adviser checks the
bookings and locks them in DATEV.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.documents.content import ZERO, DocumentContent, eu_vat_id, from_json
from rentalars.documents.models import (
    BOOKABLE_KINDS,
    AccountingSettings,
    ChartOfAccounts,
    DebitorMode,
    Document,
    rate_key,
)

#: Version of the header of the DATEV format.
HEADER_VERSION = 700

#: Who made the file, two letters in the header ("Herkunft").
ORIGIN = "RL"

#: The 125 columns of a Buchungsstapel, format version 13.
BOOKING_COLUMNS: tuple[str, ...] = (
    "Umsatz (ohne Soll/Haben-Kz)",
    "Soll/Haben-Kennzeichen",
    "WKZ Umsatz",
    "Kurs",
    "Basis-Umsatz",
    "WKZ Basis-Umsatz",
    "Konto",
    "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel",
    "Belegdatum",
    "Belegfeld 1",
    "Belegfeld 2",
    "Skonto",
    "Buchungstext",
    "Postensperre",
    "Diverse Adressnummer",
    "Geschäftspartnerbank",
    "Sachverhalt",
    "Zinssperre",
    "Beleglink",
    *(name for number in range(1, 9) for name in (f"Beleginfo – Art {number}", f"Beleginfo – Inhalt {number}")),
    "KOST1 – Kostenstelle",
    "KOST2 – Kostenstelle",
    "Kost-Menge",
    "EU-Land u. UStID (Bestimmung)",
    "EU-Steuersatz (Bestimmung)",
    "Abw. Versteuerungsart",
    "Sachverhalt L+L",
    "Funktionsergänzung L+L",
    "BU 49 Hauptfunktionstyp",
    "BU 49 Hauptfunktionsnummer",
    "BU 49 Funktionsergänzung",
    *(
        name
        for number in range(1, 21)
        for name in (f"Zusatzinformation – Art {number}", f"Zusatzinformation – Inhalt {number}")
    ),
    "Stück",
    "Gewicht",
    "Zahlweise",
    "Forderungsart",
    "Veranlagungsjahr",
    "Zugeordnete Fälligkeit",
    "Skontotyp",
    "Auftragsnummer",
    "Buchungstyp",
    "USt-Schlüssel (Anzahlungen)",
    "EU-Mitgliedstaat (Anzahlungen)",
    "Sachverhalt L+L (Anzahlungen)",
    "EU-Steuersatz (Anzahlungen)",
    "Erlöskonto (Anzahlungen)",
    "Herkunft-Kz",
    "Buchungs GUID",
    "KOST-Datum",
    "SEPA-Mandatsreferenz",
    "Skontosperre",
    "Gesellschaftername",
    "Beteiligtennummer",
    "Identifikationsnummer",
    "Zeichnernummer",
    "Postensperre bis",
    "Bezeichnung SoBil-Sachverhalt",
    "Kennzeichen SoBil-Buchung",
    "Festschreibung",
    "Leistungsdatum",
    "Datum Zuord. Steuerperiode",
    "Fälligkeit",
    "Generalumkehr (GU)",
    "Steuersatz",
    "Land",
    "Abrechnungsreferenz",
    "BVV-Position",
    "EU-Mitgliedstaat u. UStID (Ursprung)",
    "EU-Steuersatz (Ursprung)",
    "Abw. Skontokonto",
)


def _bank_columns(number: int) -> tuple[str, ...]:
    return (
        f"Bankleitzahl {number}",
        f"Bankbezeichnung {number}",
        f"Bankkonto-Nummer {number}",
        f"Länderkennzeichen {number}",
        f"IBAN {number}",
        "Leerfeld",
        f"SWIFT-Code {number}",
        f"Abw. Kontoinhaber {number}",
        f"Kennz. Haupt-Bankverb. {number}",
        f"Bankverb. {number} Gültig von",
        f"Bankverb. {number} Gültig bis",
    )


#: The 254 columns of the debitors and creditors, format version 5.
DEBITOR_COLUMNS: tuple[str, ...] = (
    "Konto",
    "Name (Adressatentyp Unternehmen)",
    "Unternehmensgegenstand",
    "Name (Adressatentyp natürl. Person)",
    "Vorname (Adressatentyp natürl. Person)",
    "Name (Adressatentyp keine Angabe)",
    "Adressatentyp",
    "Kurzbezeichnung",
    "EU-Land",
    "EU-UStID",
    "Anrede",
    "Titel/Akad. Grad",
    "Adelstitel",
    "Namensvorsatz",
    "Adressart",
    "Straße",
    "Postfach",
    "Postleitzahl",
    "Ort",
    "Land",
    "Versandzusatz",
    "Adresszusatz",
    "Abweichende Anrede",
    "Abw. Zustellbezeichnung 1",
    "Abw. Zustellbezeichnung 2",
    "Kennz. Korrespondenzadresse",
    "Adresse Gültig von",
    "Adresse Gültig bis",
    "Telefon",
    "Bemerkung (Telefon)",
    "Telefon GL",
    "Bemerkung (Telefon GL)",
    "E-Mail",
    "Bemerkung (E-Mail)",
    "Internet",
    "Bemerkung (Internet)",
    "Fax",
    "Bemerkung (Fax)",
    "Sonstige",
    "Bemerkung (Sonstige)",
    *(name for number in range(1, 6) for name in _bank_columns(number)),
    "Leerfeld",
    "Briefanrede",
    "Grußformel",
    "Kundennummer",
    "Steuernummer",
    "Sprache",
    "Ansprechpartner",
    "Vertreter",
    "Sachbearbeiter",
    "Diverse-Konto",
    "Ausgabeziel",
    "Währungssteuerung",
    "Kreditlimit (Debitor)",
    "Zahlungsbedingung",
    "Fälligkeit in Tagen (Debitor)",
    "Skonto in Prozent (Debitor)",
    "Kreditoren-Ziel 1 (Tage)",
    "Kreditoren-Skonto 1 (%)",
    "Kreditoren-Ziel 2 (Tage)",
    "Kreditoren-Skonto 2 (%)",
    "Kreditoren-Ziel 3 Brutto (Tage)",
    "Kreditoren-Ziel 4 (Tage)",
    "Kreditoren-Skonto 4 (%)",
    "Kreditoren-Ziel 5 (Tage)",
    "Kreditoren-Skonto 5 (%)",
    "Mahnung",
    "Kontoauszug",
    "Mahntext 1",
    "Mahntext 2",
    "Mahntext 3",
    "Kontoauszugstext",
    "Mahnlimit Betrag",
    "Mahnlimit %",
    "Zinsberechnung",
    "Mahnzinssatz 1",
    "Mahnzinssatz 2",
    "Mahnzinssatz 3",
    "Lastschrift",
    "Verfahren",
    "Mandantenbank",
    "Zahlungsträger",
    *(f"Indiv. Feld {number}" for number in range(1, 16)),
    "Abweichende Anrede (Rechnungsadresse)",
    "Adressart (Rechnungsadresse)",
    "Straße (Rechnungsadresse)",
    "Postfach (Rechnungsadresse)",
    "Postleitzahl (Rechnungsadresse)",
    "Ort (Rechnungsadresse)",
    "Land (Rechnungsadresse)",
    "Versandzusatz (Rechnungsadresse)",
    "Adresszusatz (Rechnungsadresse)",
    "Abw. Zustellbezeichnung 1 (Rechnungsadresse)",
    "Abw. Zustellbezeichnung 2 (Rechnungsadresse)",
    "Adresse Gültig von (Rechnungsadresse)",
    "Adresse Gültig bis (Rechnungsadresse)",
    *(name for number in range(6, 11) for name in _bank_columns(number)),
    "Nummer Fremdsystem",
    "Insolvent",
    *(f"SEPA-Mandatsreferenz {number}" for number in range(1, 11)),
    "Verknüpftes OPOS-Konto",
    "Mahnsperre bis",
    "Lastschriftsperre bis",
    "Zahlungssperre bis",
    "Gebührenberechnung",
    "Mahngebühr 1",
    "Mahngebühr 2",
    "Mahngebühr 3",
    "Pauschalberechnung",
    "Verzugspauschale 1",
    "Verzugspauschale 2",
    "Verzugspauschale 3",
    "Alternativer Suchname",
    "Status",
    "Anschrift manuell geändert (Korrespondenzadresse)",
    "Anschrift individuell (Korrespondenzadresse)",
    "Anschrift manuell geändert (Rechnungsadresse)",
    "Anschrift individuell (Rechnungsadresse)",
    "Fristberechnung bei Debitor",
    "Mahnfrist 1",
    "Mahnfrist 2",
    "Mahnfrist 3",
    "Letzte Frist",
)


@dataclass
class DatevFile:
    """A file of the export: name, content in Windows-1252, and how many lines of data it has."""

    name: str
    content: bytes
    count: int


# --- Writing the format ---------------------------------------------------------------------------


#: Letters that do not fall apart into a base letter and an accent.
_PLAIN_LETTERS = str.maketrans({"Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ħ": "H", "ħ": "h", "ı": "i"})


def _ansi(text: Any) -> str:
    """Text Windows-1252 can hold: accents dropped where needed, quotes and line breaks replaced."""
    result = []
    for character in str(text or "").translate(_PLAIN_LETTERS):
        if character in "\r\n\t":
            result.append(" ")
            continue
        if character == '"':
            result.append("'")
            continue
        try:
            character.encode("cp1252")
        except UnicodeEncodeError:
            plain = "".join(
                part
                for part in unicodedata.normalize("NFKD", character)
                if not unicodedata.combining(part) and part.isascii()
            )
            result.append(plain or "?")
        else:
            result.append(character)
    return "".join(result).strip()


def _text(value: Any, length: int | None = None) -> str:
    """A text field: in quotes, cut to its length."""
    text = _ansi(value)
    if length is not None:
        text = text[:length]
    return f'"{text}"'


def _amount(value: Decimal) -> str:
    """An amount without sign and with decimal comma: 1190,00."""
    return f"{abs(value).quantize(Decimal('0.01')):f}".replace(".", ",")


def _line(fields: list[str]) -> str:
    return ";".join(fields)


def _file(header: list[str], columns: tuple[str, ...], rows: list[list[str]]) -> bytes:
    lines = [_line(header), _line(list(columns)), *(_line(row) for row in rows)]
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


def fiscal_year_start(accounting: AccountingSettings, day: datetime.date) -> datetime.date:
    """The first day of the fiscal year that contains ``day``."""
    month = accounting.datev_fiscal_year_start or 1
    year = day.year if day.month >= month else day.year - 1
    return datetime.date(year, month, 1)


def _exported_by(user: Any) -> str:
    if user is None:
        return "Rentalars"
    return (user.get_full_name() or user.get_username())[:25]


def _header(
    accounting: AccountingSettings,
    *,
    category: int,
    name: str,
    version: int,
    date_from: datetime.date,
    date_to: datetime.date | None,
    title: str,
    user: Any,
) -> list[str]:
    """The 31 fields of the header line (DATEV format, header version 700)."""
    now = timezone.localtime()
    is_bookings = category == 21
    fields = [""] * 31
    fields[0] = '"EXTF"'
    fields[1] = str(HEADER_VERSION)
    fields[2] = str(category)
    fields[3] = _text(name)
    fields[4] = str(version)
    fields[5] = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    fields[7] = _text(ORIGIN)
    fields[8] = _text(_exported_by(user), 25)
    fields[10] = str(accounting.datev_consultant_number)
    fields[11] = str(accounting.datev_client_number)
    fields[12] = fiscal_year_start(accounting, date_from).strftime("%Y%m%d")
    fields[13] = str(accounting.datev_account_length)
    if is_bookings and date_to is not None:
        fields[14] = date_from.strftime("%Y%m%d")
        fields[15] = date_to.strftime("%Y%m%d")
    fields[16] = _text(title, 30)
    if is_bookings:
        fields[18] = "1"  # financial accounting
        fields[19] = "0"  # independent of the purpose of accounting
        fields[20] = "0"  # not locked: the tax adviser checks and locks
        fields[21] = _text("EUR")
        fields[26] = _text("03" if accounting.datev_chart == ChartOfAccounts.SKR03 else "04")
    return fields


# --- What goes in -------------------------------------------------------------------------------------


def documents_in(
    date_from: datetime.date, date_to: datetime.date, *, include_historic: bool = False
) -> QuerySet[Document]:
    """The invoices and cancellations dated in the period, in the order of their dates and numbers.

    Legacy import: invoices taken over from an old system are left out – they were booked there – unless
    ``include_historic`` asks for them.
    """
    found = (
        Document.objects.filter(kind__in=BOOKABLE_KINDS, issued_on__gte=date_from, issued_on__lte=date_to)
        .select_related("project", "project__customer", "customer")
        .order_by("issued_on", "number", "pk")
    )
    return found if include_historic else found.filter(legacy_item__isnull=True)


def check_period(
    accounting: AccountingSettings, date_from: datetime.date | None, date_to: datetime.date | None
) -> None:
    """The period and the settings an export needs (DOK-012).

    DOK-014: while invoices are switched off there is no export at all.

    Raises:
        ValidationError: Invoices are switched off; the period is reversed
            or spans two fiscal years, or the consultant or client number is
            missing.
    """
    from rentalars.documents.services import check_invoices_enabled

    check_invoices_enabled()
    problems = []
    if accounting.datev_consultant_number is None or accounting.datev_client_number is None:
        problems.append(_("Enter the consultant number and the client number under Settings → Accounting first."))
    if date_from is None or date_to is None:
        problems.append(_("Choose the first and the last day of the period."))
    elif date_to < date_from:
        problems.append(_("The period ends before it begins."))
    elif fiscal_year_start(accounting, date_from) != fiscal_year_start(accounting, date_to):
        problems.append(
            _("The period must lie within one fiscal year: DATEV takes one batch per fiscal year (from %(start)s).")
            % {"start": fiscal_year_start(accounting, date_to).strftime(local_pattern("%d.%m.%Y"))}
        )
    if problems:
        raise ValidationError(problems)


def _customer_of(document: Document, content: DocumentContent) -> Any:
    from rentalars.customers.models import Customer

    if content.customer_number:
        customer = Customer.objects.filter(number=content.customer_number).first()
        if customer is not None:
            return customer
    # Free outgoing documents: a document without a project has the customer it was made for.
    return document.customer or (document.project.customer if document.project_id else None)


def debitor_account(accounting: AccountingSettings, customer_number: str, name: str) -> int:
    """The debitor account of a customer (DOK-012).

    Raises:
        ValidationError: The customer number is no number, or the account
            lies outside the debitors.
    """
    if accounting.datev_debitor_mode == DebitorMode.COLLECTIVE:
        if accounting.datev_collective_account is None:
            raise ValidationError(_("Enter the collective debtor account under Settings → Accounting first."))
        return accounting.datev_collective_account
    if not customer_number.isdigit():
        raise ValidationError(
            _(
                "Customer “%(name)s” has the number “%(number)s”, which is not made of digits only; it cannot "
                "become a debtor account. Use a collective debtor account or give the customer a number of digits."
            )
            % {"name": name, "number": customer_number}
        )
    account = int(customer_number) + accounting.datev_debitor_offset
    low, high = accounting.debitor_range
    if not low <= account <= high:
        raise ValidationError(
            _(
                "Customer %(number)s “%(name)s” would get the debtor account %(account)d, but debtor accounts lie "
                "between %(low)d and %(high)d. Change the number added to the customer number."
            )
            % {"number": customer_number, "name": name, "account": account, "low": low, "high": high}
        )
    return account


def _document_number(number: str) -> str:
    """Belegfeld 1: at most 36 characters of a-z, A-Z, 0-9 and $ & % * + - /."""
    return re.sub(r"[^A-Za-z0-9$&%*+\-/]", "-", number)[:36]


_eu_vat_id = eu_vat_id  # The rule moved to ``content`` (the e-invoice needs it as well)


# --- The two files ------------------------------------------------------------------------------------


def bookings_file(
    date_from: datetime.date, date_to: datetime.date, *, user: Any = None, include_historic: bool = False
) -> DatevFile:
    """The Buchungsstapel of the invoices and cancellations of a period (DOK-012).

    Raises:
        ValidationError: Settings missing, the period not within one fiscal
            year, a tax rate without revenue account, or a customer without
            a possible debitor account. Every problem is named.
    """
    accounting = AccountingSettings.load()
    check_period(accounting, date_from, date_to)
    rows: list[list[str]] = []
    problems: list[str] = []
    for document in documents_in(date_from, date_to, include_historic=include_historic):
        content = from_json(document.content)
        name = content.recipient[0] if content.recipient else ""
        try:
            debitor = debitor_account(accounting, content.customer_number, name)
        except ValidationError as error:
            problems.extend(message for message in error.messages if message not in problems)
            continue
        # One line per revenue account: two tax rates of the same percentage share their account.
        gross_by_account: dict[str, Decimal] = {}
        rate_of_account: dict[str, Decimal] = {}
        for share in content.booked_taxes:  # A final invoice books what the advance invoices did not
            account = accounting.revenue_account_for(share.percent)
            if not account:
                message = _("There is no revenue account for the tax rate of %(rate)s %%.") % {
                    "rate": rate_key(share.percent).replace(".", ",")
                }
                if message not in problems:
                    problems.append(message)
                continue
            gross_by_account[account] = gross_by_account.get(account, ZERO) + share.net + share.tax
            rate_of_account[account] = share.percent
        for account, gross in gross_by_account.items():
            if gross == ZERO:
                continue
            row = [""] * len(BOOKING_COLUMNS)
            row[0] = _amount(gross)
            # An invoice: debit on the debitor; a cancellation (negative): credit – the reverse booking.
            row[1] = _text("S" if gross > ZERO else "H")
            row[2] = _text("EUR")
            row[6] = str(debitor)
            row[7] = account
            row[8] = _text("")  # automatic account: DATEV books the tax itself
            row[9] = document.issued_on.strftime("%d%m")
            row[10] = _text(_document_number(document.number))
            row[13] = _text(f"{document.title} {document.number} {name}", 60)
            if rate_of_account[account] == ZERO and _eu_vat_id(content.customer_vat_id):
                row[39] = _text(_eu_vat_id(content.customer_vat_id), 15)
            rows.append(row)
    if problems:
        raise ValidationError(problems)
    title = _("Invoices %(start)s–%(end)s") % {
        "start": date_from.strftime("%d.%m."),
        "end": date_to.strftime("%d.%m.%Y"),
    }
    header = _header(
        accounting,
        category=21,
        name="Buchungsstapel",
        version=13,
        date_from=date_from,
        date_to=date_to,
        title=title,
        user=user,
    )
    name = f"EXTF_Buchungsstapel_{date_from:%Y%m%d}_{date_to:%Y%m%d}.csv"
    return DatevFile(name=name, content=_file(header, BOOKING_COLUMNS, rows), count=len(rows))


def debitors_file(
    date_from: datetime.date, date_to: datetime.date, *, user: Any = None, include_historic: bool = False
) -> DatevFile:
    """The customers of the invoices of a period as debitor accounts (DOK-012).

    Raises:
        ValidationError: As :func:`bookings_file`; also when the customers
            share one collective account.
    """
    from rentalars.customers.models import CustomerKind

    accounting = AccountingSettings.load()
    check_period(accounting, date_from, date_to)
    if accounting.datev_debitor_mode == DebitorMode.COLLECTIVE:
        raise ValidationError(
            _("All customers are booked on one collective debtor account; there are no debtors to export.")
        )
    rows: list[list[str]] = []
    problems: list[str] = []
    seen: set[int] = set()
    for document in documents_in(date_from, date_to, include_historic=include_historic):
        content = from_json(document.content)
        customer = _customer_of(document, content)
        number = customer.number if customer is not None else content.customer_number
        name = customer.name if customer is not None else (content.recipient[0] if content.recipient else "")
        try:
            account = debitor_account(accounting, number, name)
        except ValidationError as error:
            problems.extend(message for message in error.messages if message not in problems)
            continue
        if account in seen or customer is None:
            continue
        seen.add(account)
        rows.append(_debitor_row(account, customer, CustomerKind))
    if problems:
        raise ValidationError(problems)
    header = _header(
        accounting,
        category=16,
        name="Debitoren/Kreditoren",
        version=5,
        date_from=date_from,
        date_to=None,
        title=_("Customers of Rentalars"),
        user=user,
    )
    name = f"EXTF_Debitoren_{date_from:%Y%m%d}_{date_to:%Y%m%d}.csv"
    return DatevFile(name=name, content=_file(header, DEBITOR_COLUMNS, rows), count=len(rows))


def _debitor_row(account: int, customer: Any, kinds: Any) -> list[str]:
    from rentalars.documents.xrechnung import _country_code

    row = [""] * len(DEBITOR_COLUMNS)
    row[0] = str(account)
    if customer.kind == kinds.PRIVATE:
        first, _space, last = customer.name.strip().rpartition(" ")
        row[3] = _text(last or customer.name, 30)
        row[4] = _text(first, 30)
        row[6] = "1"  # natural person
    else:
        row[1] = _text(customer.name, 50)
        row[6] = "2"  # company
    vat_id = "".join((customer.vat_id or "").split()).upper()
    if len(vat_id) > 2 and vat_id[:2].isalpha():
        row[8] = _text(vat_id[:2])
        row[9] = _text(vat_id[2:], 13)
    if customer.street or customer.city:
        row[14] = _text("STR")
        row[15] = _text(customer.street, 36)
        row[17] = _text(customer.postal_code, 10)
        row[18] = _text(customer.city, 30)
        row[19] = _text(_country_code(customer.country))
        if customer.name_addition:
            row[21] = _text(customer.name_addition, 36)
    if customer.phone:
        row[28] = _text(customer.phone, 60)
    if customer.email:
        row[32] = _text(customer.email, 60)
    row[98] = _text(customer.number, 15)
    if customer.tax_number:
        row[99] = _text(customer.tax_number, 20)
    if customer.payment_terms_days is not None:
        row[109] = str(customer.payment_terms_days)
    return row
