# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading tables for imports: files, column mapping, reports (IMP-001 to IMP-004).

Every import of Rentalars – material, products, customers, people – works on
the same steps, and this module holds the part they share:

1. **Read** an XLSX or CSV file into a plain :class:`Table`. A CSV file may
   be in UTF-8 (with or without byte order mark), UTF-16 or Windows-1252
   (:func:`decode_text`, IMP-013).
2. **Map** the columns of the file to the fields of the import. Headings are
   recognised by their names (:class:`ImportField`); every assignment can be
   overridden (IMP-003).
3. **Report** what happened or would happen: rows created, updated,
   unchanged, and every problem with its row number (:class:`ImportReport`);
   Also the outcome of every single row (``core.import_rows``, IMP-011).

What a row means and how it is written is up to each import (for example
``material.importer`` and ``products.importer``). All of them follow the
rule "all or nothing": if any row has an error, nothing is written, and a
dry run does everything and then rolls back (IMP-009).
"""

from __future__ import annotations

import contextlib
import csv
import datetime
import io
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from rentalars.core.import_rows import RowLog, report_rows


def fold(text: str) -> str:
    """Lower case, umlauts spelt out, accents removed: "Müller" and "MUELLER" both become ``mueller``.

    For comparing names – of imported customers (IMP-013) and of fixture types (PRJ-102).
    """
    text = unicodedata.normalize("NFC", text).casefold()
    for umlaut, spelled in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(umlaut, spelled)
    return "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))


#: UIX-029: the fields of the imports in English. The German label is a heading the import recognises (the files
#: come from German programs), so it stays the label in the code; the page shows this one while English is active.
ENGLISH_LABELS = {
    "Nummer": "Number",
    "Name": "Name",
    "Vorname": "First name",
    "Nachname": "Last name",
    "Anrede": "Salutation",
    "Art": "Kind",
    "Zusatz": "Addition",
    "Straße": "Street",
    "Postleitzahl": "Postal code",
    "Ort": "City",
    "Land": "Country",
    "Lieferadresse": "Delivery address",
    "E-Mail": "E-mail",
    "Telefon": "Phone",
    "USt-IdNr.": "VAT ID",
    "Steuernummer": "Tax number",
    "Zahlungsziel (Tage)": "Payment terms (days)",
    "Standardrabatt %": "Standard discount %",
    "Notiz": "Note",
    "Ansprechperson": "Contact",
    "Ansprechpartner": "Contact",
    "E-Mail der Ansprechperson": "E-mail of the contact",
    "Telefon der Ansprechperson": "Phone of the contact",
    "Aktiv": "Active",
    "Art.-Nr.": "Article no.",
    "Kategorie": "Category",
    "Preis": "Price",
    "Verkaufspreis": "Sale price",
    "Höchstrabatt": "Maximum discount",
    "Einheit": "Unit",
    "Steuerart": "Tax rate",
    "Abrechnungsart": "Billing mode",
    "Beschreibung": "Description",
    "Interne Notiz": "Internal note",
    "Mindestbestand": "Minimum stock",
    "Stück je Produkt": "Pieces per product",  # The items one piece of a product consists of
    "Eigentümer": "Owner",
    # LOG-002, LOG-005, LOG-010: the type, rates and costs of a vehicle.
    "Fahrzeugart": "Vehicle type",
    "Preis je km": "Price per km",
    "Anhängerzuschlag je km": "Trailer surcharge per km",
    "Anhänger abrechnen": "Trailer billed",
    "Interne Kosten je km": "Internal cost per km",
    "Interne Kosten je Tag": "Internal cost per day",
    "Artikelname": "Article name",
    "Kategoriespezifische Angabe": "Category-specific value",
    "Einsatz/Verbindung": "Use/connection",
    "Seriennummer": "Serial number",
    "Rechnungsdatum": "Invoice date",
    "Kaufnotiz": "Purchase note",
    "Kaufpreis": "Purchase price",
    "Gekauft (Händler)": "Bought from (supplier)",
    "Artikelnummer beim Händler": "Supplier's article number",
    "Hersteller": "Manufacturer",
    "Kurzname": "Short name",
    "Menge (Mengenmaterial)": "Quantity (bulk material)",
    "Lagerort": "Storage location",
    "Produkt (Artikelnummer)": "Product (article number)",
    "Rechnungsnummer": "Invoice number",
    "Leistung (W)": "Power (W)",
    "Schutzklasse": "Protection class",  # MAT-077
    "Funktionen": "Job functions",
    "Firma": "Company",
}


def english_label(label: str) -> str:
    """A German label of an import in English: whole, or word by word ("Ansprechpartner 1 Vorname")."""
    if label in ENGLISH_LABELS:
        return ENGLISH_LABELS[label]
    words = label.split(" ")
    for size in range(len(words), 0, -1):
        for start in range(len(words) - size + 1):
            part = " ".join(words[start : start + size])
            if part in ENGLISH_LABELS:
                rest = english_label(" ".join(words[start + size :])) if words[start + size :] else ""
                head = " ".join(words[:start])
                return " ".join(text for text in (head, ENGLISH_LABELS[part], rest.lower() if rest else "") if text)
    return label


@dataclass(frozen=True)
class ImportField:
    """A field an import can fill, with the headings it is recognised by."""

    key: str
    label: str
    required: bool = False
    aliases: tuple[str, ...] = ()

    @property
    def recognised_headings(self) -> list[str]:
        """The headings that are assigned to this field automatically."""
        return [self.label.lower(), *self.aliases]

    @property
    def shown_label(self) -> str:
        """The label as the page shows it: in English while English is active (UIX-029)."""
        from django.utils.translation import get_language

        return english_label(self.label) if (get_language() or "").startswith("en") else self.label


class ImportFileError(Exception):
    """The file cannot be read as a table at all."""


@dataclass
class Table:
    """A spreadsheet reduced to headings and rows of plain values."""

    headers: list[str]
    rows: list[list[Any]]
    #: The number each row has in the file, for error messages. Empty rows
    #: are skipped when reading, so the numbers can have gaps.
    row_numbers: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Number the rows from 2 on if the reader did not supply numbers."""
        if len(self.row_numbers) != len(self.rows):
            self.row_numbers = list(range(2, len(self.rows) + 2))

    def sample(self, count: int = 5) -> list[list[Any]]:
        """The first rows, to show next to the column mapping."""
        return self.rows[:count]

    def numbered_rows(self) -> Iterable[tuple[int, list[Any]]]:
        """``(row number in the file, cells)`` for every row."""
        return zip(self.row_numbers, self.rows, strict=True)


@dataclass
class ImportIssue:
    """A problem found in the file."""

    row: int | None
    column: str
    message: str

    def __str__(self) -> str:
        position = _("Row %(row)s") % {"row": self.row} if self.row else _("File")
        column = f", {self.column}" if self.column else ""
        return f"{position}{column}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        """The issue as plain data, for the API and for background tasks."""
        return {"row": self.row, "column": self.column, "message": self.message, "text": str(self)}


@dataclass
class ImportReport:
    """What an import of products, customers or people did or would do.

    The material import has a report of its own with models and items
    (``material.importer.ImportReport``); both offer ``ok``, ``errors``,
    ``warnings`` and ``as_dict``.
    """

    dry_run: bool
    rows_read: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    #: Further things the import created or did, e.g. "Category Licht created".
    notes: list[str] = field(default_factory=list)
    errors: list[ImportIssue] = field(default_factory=list)
    warnings: list[ImportIssue] = field(default_factory=list)
    #: IMP-011: what became of every row – new, changed (old → new), unchanged, error.
    log: RowLog = field(default_factory=RowLog, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        """True if no error was found; only then is anything written."""
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        """The report as plain data for the API and for background tasks; ``rows`` holds every row (IMP-011)."""
        return {
            "dry_run": self.dry_run,
            "ok": self.ok,
            "rows_read": self.rows_read,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "notes": self.notes,
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
            **report_rows(self.log, self.errors, self.warnings),
        }


#: Called with a percentage while an import runs (for tasks in the background).
Progress = Callable[[int], None]


def no_progress(_percent: int) -> None:
    """The default: nobody is watching."""


# --- Reading the file -------------------------------------------------------------


#: What one table may hold – a file of a million rows (a few kilobytes as a ZIP) would fill the memory.
MAX_TABLE_ROWS = 100_000
MAX_TABLE_CELLS = 3_000_000
#: S7: empty rows are not counted as rows – but reading them costs time, and Excel writes formatted rows that
#: are empty (a million of them, each as wide as the sheet: up to column XFD). So no more than this many rows of any
#: kind are looked at, and an XLSX sheet is read only up to this many columns (a heading beyond is refused). A file
#: that has more is refused with the advice to delete the empty rows – not read in part, which would lose data
#: without a word.
MAX_SCANNED_ROWS = 3 * MAX_TABLE_ROWS
MAX_COLUMNS = 200
#: What an XLSX file may be once unpacked (a ZIP bomb is small and unpacks to gigabytes).
MAX_UNPACKED_BYTES = 200 * 1024 * 1024


def read_table(
    source: BinaryIO | Path | str,
    filename: str | None = None,
    *,
    sheet: str | None = None,
    max_rows: int | None = None,
    command: str = "",
) -> Table:
    """Read an XLSX or CSV file into a :class:`Table`.

    The first non-empty row is taken as the heading row. Completely empty
    rows are skipped, but row numbers in messages still refer to the file.

    Args:
        source: An open binary file or a path.
        filename: The file name, used to tell XLSX from CSV. Defaults to the
            name of ``source``.
        sheet: For XLSX: the name of the worksheet; default is the first.
        max_rows: Refuse files with more rows. The API passes
            ``settings.MAX_IMPORT_ROWS_PER_REQUEST`` when it imports within the
            request, because a request is ended after two minutes; imports in
            the background and the commands on the server pass nothing.
        command: The command on the server named in the message about too
            many rows, e.g. ``rentalars import_material``.

    Raises:
        ImportFileError: Unknown file type, unreadable file, no heading row,
            or more rows than ``max_rows``.
    """
    if isinstance(source, str | Path):
        path = Path(source)
        filename = filename or path.name
        with path.open("rb") as handle:
            return read_table(io.BytesIO(handle.read()), filename, sheet=sheet, max_rows=max_rows, command=command)

    extension = Path(filename or getattr(source, "name", "")).suffix.lower()
    if extension == ".xlsx":
        raw_rows = _read_xlsx(source, sheet)
    elif extension == ".csv":
        raw_rows = _read_csv(source)
    else:
        raise ImportFileError(_("Only XLSX and CSV files can be imported."))

    # Row by row, so that a file with a million rows is refused when it is too big, not after it filled the memory
    # . The limits are those of a table that can still be shown and imported on a small server.
    numbered: list[tuple[int, list[Any], Any]] = []
    counted = cells = 0
    with contextlib.closing(raw_rows):  # also when the loop stops early: the workbook is closed
        for number, row in enumerate(raw_rows, start=1):
            if number > MAX_SCANNED_ROWS:
                raise ImportFileError(
                    _(
                        "The file is too big: it has more than %(rows)s rows, empty ones included. Delete the empty "
                        "rows below the data, or split the file into several files."
                    )
                    % {"rows": MAX_SCANNED_ROWS}
                )
            if not any(cell_text(cell) for cell in row):
                continue
            counted += 1
            # Cells after the last filled one are formatting, not data: Excel writes a row up to column XFD when the
            # whole column was formatted. They are neither counted nor kept.
            fill = None  # what a missing cell was before: "" in a CSV file, None in a workbook
            while row and not cell_text(row[-1]):
                fill = row[-1]
                row = row[:-1]
            cells += len(row)
            if counted - 1 > MAX_TABLE_ROWS or cells > MAX_TABLE_CELLS:
                raise ImportFileError(
                    _(
                        "The file is too big: at most %(rows)s rows and %(cells)s cells can be read. Split it into "
                        "several files."
                    )
                    % {"rows": MAX_TABLE_ROWS, "cells": MAX_TABLE_CELLS}
                )
            if max_rows is None or counted - 1 <= max_rows:
                numbered.append((number, row, fill))  # beyond the limit of a request the rows are only counted
    if not numbered:
        raise ImportFileError(_("The file contains no rows."))
    if max_rows is not None and counted - 1 > max_rows:
        raise ImportFileError(
            _(
                "The file has %(rows)s rows. In one request at most %(limit)s rows can be imported. "
                "Send it with “background” to import it as a task in the background, or import it on the "
                "server with the command “%(command)s”; the import guide (docs/betrieb/import.md) explains how."
            )
            % {"rows": counted - 1, "limit": max_rows, "command": command or "rentalars import_data"}
        )
    _header_number, header_row, _fill = numbered[0]
    headers = [cell_text(cell) for cell in header_row]
    while headers and not headers[-1]:
        headers.pop()
    if len(headers) >= MAX_COLUMNS:
        raise ImportFileError(
            _("The file has more than %(columns)s columns. Only files with fewer columns can be read.")
            % {"columns": MAX_COLUMNS - 1}
        )
    width = len(headers)
    rows = []
    for _number, row, fill in numbered[1:]:
        cells = list(row[:width]) + [fill] * (width - len(row))
        rows.append(cells)
    return Table(headers=headers, rows=rows, row_numbers=[number for number, _row, _fill in numbered[1:]])


def _read_xlsx(source: BinaryIO, sheet: str | None) -> Iterator[list[Any]]:
    """Read all rows of one worksheet; formulas are delivered as their last values."""
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        with zipfile.ZipFile(source) as archive:
            unpacked = sum(item.file_size for item in archive.infolist())
    except (zipfile.BadZipFile, OSError) as error:
        raise ImportFileError(_("The file is not a readable XLSX file.")) from error
    if unpacked > MAX_UNPACKED_BYTES:
        raise ImportFileError(_("The file is too big once it is unpacked. Split it into several files."))
    source.seek(0)
    try:
        workbook = load_workbook(source, read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, OSError, KeyError, ValueError) as error:
        # An XLSX file is a ZIP archive; a renamed file of another kind fails here.
        raise ImportFileError(_("The file is not a readable XLSX file.")) from error
    try:
        if sheet:
            if sheet not in workbook.sheetnames:
                raise ImportFileError(
                    _("The file has no worksheet “%(sheet)s”. It has: %(names)s")
                    % {"sheet": sheet, "names": ", ".join(workbook.sheetnames)}
                )
            worksheet = workbook[sheet]
        else:
            worksheet = workbook.worksheets[0]
        for row in worksheet.iter_rows(values_only=True, max_col=MAX_COLUMNS):
            yield list(row)
    finally:
        workbook.close()


def _read_csv(source: BinaryIO) -> Iterator[list[Any]]:
    """Read a CSV file; separator and encoding are detected."""
    text = decode_text(source.read())
    first_line = text.split("\n", 1)[0]
    delimiter = max((";", ",", "\t"), key=first_line.count)
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        yield list(row)


#: Byte order marks and the encodings they announce; UTF-8 with BOM is what Excel writes as "CSV UTF-8".
_BYTE_ORDER_MARKS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def decode_text(raw: bytes) -> str:
    """Turn the bytes of a text file into text, whatever the program that wrote it used (IMP-013).

    The order matters:

    1. A byte order mark names the encoding: UTF-8 (Excel's "CSV UTF-8") or
       UTF-16 (Excel's "Unicode text").
    2. UTF-8 without mark. A file in Windows-1252 or ISO-8859-1 that contains
       umlauts is practically never valid UTF-8, so this test is safe.
    3. Windows-1252, as written by Lexware, DATEV and older versions of Excel
       on Windows ("Straße" is the byte ``0xDF``, which UTF-8 would show as
       "Stra�e").
    4. ISO-8859-1 for the five bytes Windows-1252 leaves undefined; it can
       decode every byte, so reading never fails.
    """
    for mark, encoding in _BYTE_ORDER_MARKS:
        if raw.startswith(mark):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                break
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


# --- Mapping columns ------------------------------------------------------------------


def normalise(heading: str) -> str:
    """Compare headings without regard to case, spacing and line breaks."""
    return re.sub(r"\s+", " ", heading.replace("\n", " ")).strip().lower()


def suggest_mapping(headers: list[str], fields: Iterable[ImportField]) -> dict[str, int | None]:
    """Guess which column of the file belongs to which field (IMP-003).

    Returns:
        ``{field key: column index or None}``. The guess is a starting point;
        the caller can replace any assignment.
    """
    normalised = [normalise(header) for header in headers]
    mapping: dict[str, int | None] = {}
    taken: set[int] = set()
    for import_field in fields:
        names = (normalise(import_field.label), *import_field.aliases)
        index = next(
            (position for position, header in enumerate(normalised) if header in names and position not in taken),
            None,
        )
        mapping[import_field.key] = index
        if index is not None:
            taken.add(index)
    return mapping


def resolve_mapping(
    headers: list[str], overrides: dict[str, Any] | None, fields: Iterable[ImportField]
) -> dict[str, int | None]:
    """Combine the automatic guess with assignments made by the user.

    Args:
        headers: The headings of the file.
        overrides: ``{field key: heading text, column index, or ""}``. An
            empty value means "do not import this field".
        fields: The fields of the import.

    Raises:
        ImportFileError: An override names an unknown field or column.
    """
    fields = tuple(fields)
    keys = {import_field.key for import_field in fields}
    mapping = suggest_mapping(headers, fields)
    normalised = [normalise(header) for header in headers]
    for key, value in (overrides or {}).items():
        if key not in keys:
            raise ImportFileError(_("Unknown field in the column mapping: %(field)s") % {"field": key})
        if value in (None, "", -1, "-1"):
            mapping[key] = None
        elif isinstance(value, int) or (isinstance(value, str) and value.isdigit() and int(value) < len(headers)):
            if int(value) >= len(headers):
                raise ImportFileError(_("The file has no column number %(number)s.") % {"number": value})
            mapping[key] = int(value)
        elif normalise(str(value)) in normalised:
            mapping[key] = normalised.index(normalise(str(value)))
        else:
            raise ImportFileError(_("The file has no column “%(column)s”.") % {"column": value})
    return mapping


def missing_required(mapping: dict[str, int | None], fields: Iterable[ImportField]) -> list[ImportIssue]:
    """An issue for every required field no column is assigned to."""
    return [
        ImportIssue(None, import_field.shown_label, _("No column of the file is assigned to this required field."))
        for import_field in fields
        if import_field.required and mapping.get(import_field.key) is None
    ]


# --- Reading cells ------------------------------------------------------------------------


#: Characters a spreadsheet program takes for the start of a formula; an exported cell starting with one of them
#: gets a leading apostrophe (``core.tables.csv_text``, ``core.import_exports``).
FORMULA_STARTS = ("=", "+", "-", "@")


def cell_text(value: Any) -> str:
    """Turn a cell into trimmed text; whole numbers lose their ``.0``.

    IMP-017: the apostrophe an export puts in front of text that would start a
    formula ("'=Summe", "'- defekt") is taken away again, so that an exported file comes back unchanged.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    text = str(value).strip()
    if text[:1] == "'" and (
        text[1:2] in FORMULA_STARTS or (text[1:2] == "'" and text[2:3] in FORMULA_STARTS)  # "''=…" was "'=…"
    ):
        return text[1:]
    return text


DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%Y", "%Y")


def parse_date(value: Any) -> datetime.date | None:
    """Accept spreadsheet dates and the usual German and ISO spellings."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = cell_text(value)
    if "T" in text:
        text = text.split("T", 1)[0]
    for date_format in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ValueError(_("“%(value)s” is not a date.") % {"value": text})


def parse_decimal(value: Any, *, places: str = "0.01", negative: str = "") -> Decimal | None:
    """Accept numbers and texts like ``1.234,56 €`` or ``19 %``.

    Args:
        value: The cell.
        places: The precision the result is rounded to.
        negative: The message for a negative number; empty: negative numbers are fine.
    """
    if value in (None, ""):
        return None
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        number = Decimal(str(value)).quantize(Decimal(places))
    else:
        text = cell_text(value)
        for noise in ("€", "EUR", "%", " ", " "):
            text = text.replace(noise, "")
        if "," in text:
            # German notation: the dot groups thousands, the comma is the decimal sign.
            text = text.replace(".", "").replace(",", ".")
        try:
            number = Decimal(text).quantize(Decimal(places))
        except InvalidOperation as error:
            raise ValueError(_("“%(value)s” is not a number.") % {"value": value}) from error
    if negative and number < 0:
        raise ValueError(negative)
    return number


TRUE_WORDS = frozenset({"1", "ja", "j", "yes", "y", "true", "wahr", "x", "aktiv", "active"})
FALSE_WORDS = frozenset({"0", "nein", "n", "no", "false", "falsch", "inaktiv", "inactive", "-"})


def parse_bool(value: Any) -> bool | None:
    """``ja``/``nein``, ``1``/``0``, ``x`` and the like; empty: ``None``."""
    text = cell_text(value).lower()
    if not text:
        return None
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    raise ValueError(_("“%(value)s” is neither yes nor no.") % {"value": value})


def choice_of(value: Any, words: dict[str, str], choices: Iterable[tuple[str, Any]]) -> str | None:
    """Find a choice by its stored value, its label or one of ``words``; empty: ``None``.

    IMP-017: the German label counts in every language – the exported files
    name choices in German, like their headings, and come back unchanged also for a user working in English.

    Raises:
        ValueError: The text matches nothing.
    """
    from django.utils import translation

    text = cell_text(value)
    if not text:
        return None
    wanted = normalise(text)
    choices = list(choices)
    with translation.override("de"):
        german = [str(label) for _stored, label in choices]
    for (stored, label), german_label in zip(choices, german, strict=True):
        if wanted in {normalise(str(stored)), normalise(str(label)), normalise(german_label)}:
            return str(stored)
    if wanted in words:
        return words[wanted]
    raise ValueError(_("“%(value)s” is not a known value.") % {"value": text})


def messages_of(error: ValidationError, labels: dict[str, str] | None = None) -> list[str]:
    """Flatten a validation error into readable messages with field labels."""
    if hasattr(error, "error_dict"):
        messages = []
        for name, errors in error.error_dict.items():
            for single in errors:
                for message in single.messages:
                    label = (labels or {}).get(name, name)
                    messages.append(message if name == "__all__" else f"{label}: {message}")
        return messages
    return list(error.messages)
