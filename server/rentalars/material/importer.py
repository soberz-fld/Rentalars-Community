# SPDX-License-Identifier: GPL-3.0-or-later
"""Import of the material list from a spreadsheet (IMP-002 to IMP-012).

The existing Excel list has one row per item with the 13 columns of MAT-011.
The database separates model and item and refers to categories, suppliers and
other items. This module does the translation:

1. **Read** the file (XLSX or CSV) into a plain table.
2. **Map** the columns of the file to the known fields. Headings are
   recognised automatically; every assignment can be overridden (IMP-003).
3. **Check** every row without touching the database: IDs, dates, prices.
4. **Write** inside one transaction: categories, suppliers, models, items.
   Rows with the same article name become one model (IMP-002). Existing
   items are found by their ID and updated instead of duplicated (IMP-004).
5. **Resolve "installed in"** in a second pass, because the column refers to
   IDs of the same table (IMP-010). Unknown IDs and circles are reported.
6. A **dry run** does all of this and then rolls the transaction back. It
   therefore reports exactly what the real import would do (IMP-009).

If any row has an error, nothing at all is written: all or nothing.

Prices, IDs and sets (IMP-014 to IMP-016):

* Prices may be **gross**: the import is told so for the whole file and
  with which tax rate (default: the default tax rate); every price is then
  divided by 1 + rate and stored net, as MAT-011 wants it.
* A cell ``#0802`` is the ID ``0802`` – in the ID column, in "Einsatz/
  Verbindung" and in the price column.
* A **set bought together** has its price at one item; the others say in
  their price cell which one, e.g. ``#0851`` (MAT-054). They are linked to
  that item ("price included in") in a third pass and get no price of their
  own; a chain ``0853 → #0852 → #0851`` ends at the item with the price.

IMP-011: the report names what becomes of every row: a new
item, a changed one with every changed field old → new – of the item and of
its material model, including what the second and third pass change –, an
unchanged one, or the errors of the row. Purchase prices are shown only to
those who may see them (AUT-019).

MAT-077: the column "Schutzklasse" (I, II, III) is the protection class of the item: a material
model without one takes the class all its rows name, if they agree and none of its items has a class of its
own; a row whose class differs from its model's gives the item a class of its own, an equal or empty cell
none. The class of a model that has one is changed on its page, never by the import.

The command ``manage.py import_material``, the browser import and the API
endpoint all call :func:`import_material` – there is only one import logic.
"""

from __future__ import annotations

import contextlib
import datetime
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, BinaryIO

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import SpecialRight
from rentalars.core import tabular
from rentalars.core.audit import acting_as, record_event
from rentalars.core.import_rows import CHANGED, NEW, UNCHANGED, RowLog, cells_by_number, report_rows, snapshot
from rentalars.core.models import NumberRange, NumberRangeKey, SystemSettings
from rentalars.core.tabular import (
    ImportField,
    ImportFileError,
    ImportIssue,
    Progress,
    Table,
    cell_text,
    messages_of,
    no_progress,
    parse_date,
    parse_decimal,
)
from rentalars.masterdata.models import Category, Manufacturer, StorageLocation, Supplier
from rentalars.material import partial_dates
from rentalars.material import serials as serial_check
from rentalars.material.models import (
    OPERATIONAL_STATUSES,
    ConnectionType,
    ItemStatus,
    MaterialItem,
    MaterialModel,
    TrackingMode,
)
from rentalars.material.numbering import format_inventory_number, parse_inventory_number
from rentalars.material.services import apply_status
from rentalars.material.spots import normalise_spot
from rentalars.products.models import Product

__all__ = [
    "IMPORT_FIELDS",
    "ImportField",
    "ImportFileError",
    "ImportIssue",
    "ImportReport",
    "Table",
    "import_material",
    "read_table",
    "resolve_mapping",
    "suggest_mapping",
]


#: The 13 columns of MAT-011 in their order, followed by optional extras.
IMPORT_FIELDS: tuple[ImportField, ...] = (
    ImportField("inventory_number", "ID", True, ("id", "inventarnummer", "inventar-nr", "nr", "nummer")),
    ImportField("name", "Artikelname", True, ("artikelname", "artikelname (evtl. gekürzt)", "artikel", "name")),
    ImportField("category", "Kategorie", True, ("kategorie",)),
    # MAT-049, MAT-050: the fields are called "Beschreibung" and "Rechnungsdatum" now; the headings of the
    # list of MAT-011 ("Spezifikation", "Tag des Kaufs") are still recognised.
    ImportField("specification", "Beschreibung", False, ("spezifikation", "spec", "beschreibung")),
    ImportField(
        "category_specific",
        "Kategoriespezifische Angabe",
        False,
        ("kategoriespezifische angabe", "kategoriespezifisch", "kat.-spez. angabe"),
    ),
    ImportField(
        "installed_in", "Einsatz/Verbindung", False, ("einsatz/verbindung", "einsatz", "verbindung", "verbaut in")
    ),
    ImportField("serial_number", "Seriennummer", False, ("seriennummer", "serien-nr", "sn", "s/n")),
    ImportField("note", "Notiz", False, ("notiz", "notizen", "bemerkung")),
    ImportField(
        "purchase_date", "Rechnungsdatum", False, ("tag des kaufs", "kaufdatum", "gekauft am", "rechnungsdatum")
    ),
    ImportField("purchase_note", "Kaufnotiz", False, ("kaufnotiz",)),
    ImportField("purchase_price", "Kaufpreis", False, ("kaufpreis", "preis", "ek")),
    ImportField("supplier", "Gekauft (Händler)", False, ("gekauft (händler)", "gekauft", "händler", "haendler")),
    ImportField(
        "supplier_article_number",
        "Artikelnummer beim Händler",
        False,
        ("artikelnummer beim händler", "händler-artikelnummer", "artikelnummer händler", "bestellnummer"),
    ),
    ImportField("manufacturer", "Hersteller", False, ("hersteller",)),
    ImportField("short_name", "Kurzname", False, ("kurzname",)),
    ImportField("quantity", "Menge (Mengenmaterial)", False, ("menge", "anzahl", "stückzahl")),
    ImportField("status", "Status", False, ("status", "zustand")),
    ImportField("storage_location", "Lagerort", False, ("lagerort", "lager")),
    # MAT-080: the place within the location, e.g. "01-A-1".
    ImportField("storage_spot", "Lagerplatz", False, ("lagerplatz", "regalplatz", "platz")),
    ImportField("product", "Produkt (Artikelnummer)", False, ("produkt", "artikelnummer", "artikelnummer (intern)")),
    # The invoice number of an item (MAT-050) and the power of a model (MAT-049).
    ImportField("invoice_number", "Rechnungsnummer", False, ("rechnungsnummer", "rechnungs-nr", "re-nr", "rechnung")),
    ImportField("power", "Leistung (W)", False, ("leistung", "leistung in w", "watt")),
    # MAT-077: the protection class of the item – "I", "II" or "III" (see _Writer.protection_class).
    ImportField("protection_class", "Schutzklasse", False, ("schutzklasse", "schutzkl.", "sk", "protection class")),
)

FIELDS_BY_KEY = {import_field.key: import_field for import_field in IMPORT_FIELDS}

#: How the status "import error" is written in an export; read as "leave the status" (only the import sets it).
IMPORT_ERROR_WORDS = frozenset({"fehler import", "import error"})

#: German and English words accepted in the optional status column.
STATUS_WORDS = {
    "verfügbar": ItemStatus.AVAILABLE,
    "available": ItemStatus.AVAILABLE,
    "ok": ItemStatus.AVAILABLE,
    "im einsatz": ItemStatus.IN_USE,
    "in use": ItemStatus.IN_USE,
    "defekt": ItemStatus.DEFECTIVE,
    "defective": ItemStatus.DEFECTIVE,
    "in reparatur": ItemStatus.IN_REPAIR,
    "reparatur": ItemStatus.IN_REPAIR,
    "in repair": ItemStatus.IN_REPAIR,
    "gesperrt": ItemStatus.BLOCKED,
    "blocked": ItemStatus.BLOCKED,
    "ausgemustert": ItemStatus.RETIRED,
    "retired": ItemStatus.RETIRED,
    "verkauft": ItemStatus.SOLD,
    "sold": ItemStatus.SOLD,
    "verloren": ItemStatus.LOST,
    "lost": ItemStatus.LOST,
}


@dataclass
class ImportReport:
    """What an import (or dry run) did or would do."""

    dry_run: bool
    rows_read: int = 0
    models_created: int = 0
    models_updated: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_unchanged: int = 0
    categories_created: list[str] = field(default_factory=list)
    suppliers_created: list[str] = field(default_factory=list)
    manufacturers_created: list[str] = field(default_factory=list)
    #: IDs of items that were newly linked to a container, as "0310 → 0500".
    installed_links: list[str] = field(default_factory=list)
    #: MAT-054, IMP-016: the sets bought together, as "0851: 0852, 0853" – the item with the price first.
    purchase_sets: list[str] = field(default_factory=list)
    #: IMP-014: how the prices were read, e.g. "gross, 19 %"; empty for net prices.
    prices_gross_rate: str = ""
    highest_id: int = 0
    next_id: str = ""
    errors: list[ImportIssue] = field(default_factory=list)
    warnings: list[ImportIssue] = field(default_factory=list)
    #: The IDs of the items taken over with the status "import error".
    flagged: set[int] = field(default_factory=set, repr=False)
    #: IMP-011: what became of every row – new, changed (old → new), unchanged, error.
    log: RowLog = field(default_factory=RowLog, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        """True if no error was found; only then is anything written."""
        return not self.errors

    @property
    def items_flagged(self) -> int:
        """How many items were taken over with the status "import error"."""
        return len(self.flagged)

    def as_dict(self) -> dict[str, Any]:
        """The report as plain data for the API; ``rows`` holds every row (IMP-011)."""
        return {
            "dry_run": self.dry_run,
            "ok": self.ok,
            "rows_read": self.rows_read,
            "models_created": self.models_created,
            "models_updated": self.models_updated,
            "items_created": self.items_created,
            "items_updated": self.items_updated,
            "items_unchanged": self.items_unchanged,
            "items_flagged": self.items_flagged,
            "categories_created": self.categories_created,
            "suppliers_created": self.suppliers_created,
            "manufacturers_created": self.manufacturers_created,
            "installed_links": self.installed_links,
            "purchase_sets": self.purchase_sets,
            "prices_gross_rate": self.prices_gross_rate,
            "highest_id": self.highest_id,
            "next_id": self.next_id,
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
            **report_rows(self.log, self.errors, self.warnings),
        }


# --- Step 1 and 2: reading the file, mapping columns (``core.tabular``) -------------------


def read_table(
    source: BinaryIO | Path | str,
    filename: str | None = None,
    *,
    sheet: str | None = None,
    max_rows: int | None = None,
) -> Table:
    """Read an XLSX or CSV file; see :func:`rentalars.core.tabular.read_table`."""
    return tabular.read_table(source, filename, sheet=sheet, max_rows=max_rows, command="rentalars import_material")


def suggest_mapping(headers: list[str]) -> dict[str, int | None]:
    """Guess which column of the file belongs to which field of the material list (IMP-003)."""
    return tabular.suggest_mapping(headers, IMPORT_FIELDS)


def resolve_mapping(headers: list[str], overrides: dict[str, Any] | None) -> dict[str, int | None]:
    """Combine the automatic guess with assignments made by the user (IMP-003)."""
    return tabular.resolve_mapping(headers, overrides, IMPORT_FIELDS)


# --- Step 3: checking rows without the database ------------------------------------


@dataclass
class _Row:
    """One row of the file after parsing."""

    number: int
    inventory_number: int
    name: str
    category: str
    values: dict[str, Any]
    #: What of the row could not be taken over, as ``(heading of the column in the file, content of the cell)``.
    #: The item is taken over without it, with the status "import error", and its note names these entries.
    trouble: list[tuple[str, str]] = field(default_factory=list)
    #: The fields whose cell could not be read; the row leaves them as they are in the database.
    keep: set[str] = field(default_factory=set)
    #: The text of every cell by field, for the note.
    raw: dict[str, str] = field(default_factory=dict)
    #: The headings of the columns of the file by field (the same dictionary for all rows).
    headings: dict[str, str] = field(default_factory=dict, repr=False)

    def heading(self, key: str) -> str:
        """The heading of the column of this field in the file; the name of the field if the file has none for it."""
        return self.headings.get(key) or FIELDS_BY_KEY[key].label


_text = cell_text
_parse_date = parse_date


def _parse_purchase_date(value: Any) -> partial_dates.PartialDate | None:
    """Read the purchase date of a row (partial purchase date).

    A date, or "00.00.2015", "00.05.2015", "05.2015", "2015", "2015-00-00". What the file says is kept: a year alone
    is a date known to the year, not "1 January". Other spellings (two-digit years) are those of ``parse_date``.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime.date):  # a date cell of a spreadsheet: a whole date
        return partial_dates.PartialDate(value.date() if isinstance(value, datetime.datetime) else value)
    try:
        return partial_dates.parse(_text(value))
    except ValueError:
        found = _parse_date(value)  # raises the usual "is not a date"
        return partial_dates.PartialDate(found) if found is not None else None


@lru_cache(maxsize=1)
def _status_words() -> frozenset[str]:
    """The names of the statuses in German and English, in lower case – an article name that is one is suspicious."""
    from django.utils import translation

    words = {status.value.replace("_", " ") for status in ItemStatus}
    for language in ("de", "en"):
        with translation.override(language):
            words.update(str(status.label).casefold() for status in ItemStatus)
    return frozenset(words)


class _StatusWords:
    """Looked up lazily: the translations are not there when the module is imported."""

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.casefold() in _status_words()


_STATUS_WORDS = _StatusWords()

#: IMP-016: a price cell that names the item whose price includes this one, e.g. ``#0851``.
_SET_REFERENCE = re.compile(r"^#\s*\d+(\.0)?$")


def _parse_price(value: Any, gross_factor: Decimal | None = None) -> Decimal | None:
    """Accept numbers and texts like ``1.234,56 €``; IMP-014: a gross price is turned into the net one."""
    price = parse_decimal(value, negative=_("The purchase price must not be negative."))
    if price is not None and gross_factor is not None:
        price = (price / gross_factor).quantize(Decimal("0.01"))
    return price


def gross_factor(rate: Any) -> Decimal:
    """IMP-014: what a gross price is divided by – 1.19 for 19 %."""
    return Decimal(1) + Decimal(str(rate)) / Decimal(100)


def _parse_power(value: Any) -> Decimal | None:
    """Accept watts as ``575``, ``575 W`` or ``1200 Watt`` (MAT-049)."""
    if isinstance(value, str):
        value = re.sub(r"\s*(watt|w)\s*$", "", value.strip(), flags=re.IGNORECASE)
    return parse_decimal(value, negative=_("The power must not be negative."))


#: MAT-077: the protection class as a numeral, roman or arabic.
_PROTECTION_CLASSES = {"I": "I", "1": "I", "II": "II", "2": "II", "III": "III", "3": "III"}


def _parse_protection_class(value: Any) -> str:
    """Accept ``II``, ``2``, ``SK II`` or ``Schutzklasse 2`` (MAT-077); empty for an empty cell.

    Raises:
        ValueError: Not a protection class.
    """
    text = _text(value)
    if text.endswith(".0"):
        text = text[:-2]  # a number cell of a spreadsheet: 2.0
    word = re.sub(r"^(schutzklasse|schutzkl\.?|sk|klasse|protection class|class)\s*", "", text, flags=re.IGNORECASE)
    if not word:
        return ""
    found = _PROTECTION_CLASSES.get(word.strip().upper())
    if found is None:
        raise ValueError(_("“%(value)s” is not a protection class. Write I, II or III.") % {"value": text})
    return found


def _parse_rows(
    table: Table, mapping: dict[str, int | None], report: ImportReport, *, gross: Decimal | None = None
) -> list[_Row]:
    """Parse every row and collect errors; nothing is written to the database.

    ``gross``: the factor of gross prices (IMP-014); ``None`` for net prices.
    """

    def cell(row: list[Any], key: str) -> Any:
        index = mapping.get(key)
        return row[index] if index is not None and index < len(row) else None

    parsed: list[_Row] = []
    headings = {
        key: table.headers[index] for key, index in mapping.items() if index is not None and index < len(table.headers)
    }
    seen_ids: dict[int, int] = {}
    #: (row number, ID of the row, ID it is installed in) for every row that names one.
    references: list[tuple[int, int, int]] = []
    #: IMP-016: (row number, ID of the row, ID whose price includes it) for every price cell like ``#0851``.
    set_references: list[tuple[int, int, int]] = []
    for number, row in zip(table.row_numbers, table.rows, strict=True):
        errors_before = len(report.errors)

        def problem(key: str, message: str, number: int = number) -> None:
            report.errors.append(ImportIssue(number, FIELDS_BY_KEY[key].label, message))

        inventory_number = 0
        try:
            inventory_number = parse_inventory_number(cell(row, "inventory_number") or "")
        except ValidationError as error:
            problem("inventory_number", " ".join(error.messages))
        if inventory_number:
            if inventory_number in seen_ids:
                problem(
                    "inventory_number",
                    _("The ID %(id)s already occurs in row %(row)s.")
                    % {"id": format_inventory_number(inventory_number), "row": seen_ids[inventory_number]},
                )
            seen_ids.setdefault(inventory_number, number)

        name = _text(cell(row, "name"))
        if not name:
            problem("name", _("The article name is missing."))
        category = _text(cell(row, "category"))
        if not category:
            problem("category", _("The category is missing."))

        values: dict[str, Any] = {}
        trouble: list[tuple[str, str]] = []
        keep: set[str] = set()
        raw = {key: _text(cell(row, key)) for key in FIELDS_BY_KEY}

        def soft(
            key: str,
            message: str,
            number: int = number,
            trouble: list = trouble,
            keep: set = keep,
            raw: dict = raw,
        ) -> None:
            """A cell that cannot be read is no error: the item is taken over without it, flagged, with the cell in its note."""
            report.warnings.append(ImportIssue(number, FIELDS_BY_KEY[key].label, message))
            trouble.append((headings.get(key) or FIELDS_BY_KEY[key].label, raw[key]))
            keep.add(key)

        for key in (
            "specification",
            "category_specific",
            "serial_number",
            "note",
            "purchase_note",
            "supplier",
            "supplier_article_number",
            "manufacturer",
            "short_name",
            "storage_location",
            "storage_spot",
            "product",
            "invoice_number",
        ):
            values[key] = _text(cell(row, key))
        try:
            values["power"] = _parse_power(cell(row, "power"))
        except ValueError as error:
            values["power"] = None
            soft("power", str(error))
        try:
            values["protection_class"] = _parse_protection_class(cell(row, "protection_class"))
        except ValueError as error:
            values["protection_class"] = ""
            soft("protection_class", str(error))
        try:
            values["purchase_date"] = _parse_purchase_date(cell(row, "purchase_date"))
        except ValueError as error:
            values["purchase_date"] = None
            soft("purchase_date", str(error))
        values["purchase_price_in"] = None
        price_cell = cell(row, "purchase_price")
        if isinstance(price_cell, str) and _SET_REFERENCE.match(price_cell.strip()):
            # IMP-016, MAT-054: "#0851" – bought in a set, the price is noted at 0851.
            values["purchase_price"] = None
            try:
                values["purchase_price_in"] = parse_inventory_number(price_cell.strip())
            except ValidationError:
                soft("purchase_price", _("“%(value)s” is not the ID of an item.") % {"value": price_cell.strip()})
            else:
                set_references.append((number, inventory_number, values["purchase_price_in"]))
        else:
            try:
                values["purchase_price"] = _parse_price(price_cell, gross)
            except ValueError as error:
                values["purchase_price"] = None
                soft("purchase_price", str(error))

        installed_text = raw["installed_in"]
        values["installed_in"] = None
        values["installed_keep"] = False
        if installed_text:
            container, note_text, hint = _read_connection(installed_text)
            if container is not None:
                values["installed_in"] = container
                references.append((number, inventory_number, container))
            elif note_text:
                values["installed_keep"] = True  # what the cell says is not clear enough to change a link
                # IMP-010: text and several IDs are no error. The item is flagged, the cell is in its note.
                soft("installed_in", hint)

        quantity_text = raw["quantity"]
        values["quantity"] = None
        if quantity_text:
            if quantity_text.isdigit():
                values["quantity"] = int(quantity_text)
            else:
                soft("quantity", _("“%(value)s” is not a whole number.") % {"value": quantity_text})

        status_text = raw["status"].lower()
        values["status"] = None
        if status_text:
            if status_text in STATUS_WORDS:
                values["status"] = STATUS_WORDS[status_text]
            elif status_text in IMPORT_ERROR_WORDS:
                values["status"] = None  # a file exported from Rentalars: the status is set by the import itself
            else:
                soft("status", _("Unknown status “%(value)s”.") % {"value": status_text})

        if len(report.errors) == errors_before:
            parsed.append(_Row(number, inventory_number, name, category, values, trouble, keep, raw, headings))

    _check_references(references, set(seen_ids), report, parsed)
    _check_references(set_references, set(seen_ids), report, parsed, key="purchase_price")
    return parsed


#: IMP-010: one entry of "Einsatz/Verbindung" that is an ID – ``#0123``, ``0123`` or ``123.0``.
_CONNECTION_ID = re.compile(r"^#?\s*\d{1,9}(\.0)?$")
#: ``1,5`` is a number with a decimal comma, not two IDs: the hint must not say so.
_DECIMAL_COMMA = re.compile(r"^\d+,\d+$")
#: What separates the entries of "Einsatz/Verbindung": commas, semicolons and line breaks.
_CONNECTION_SEPARATORS = re.compile(r"[,;\n\r]+")


def _read_connection(text: str) -> tuple[int | None, str, str]:
    """IMP-010: what a cell of "Einsatz/Verbindung" says – the container, or what goes to the note.

    An item is installed in one other item at most. So the cell can be **exactly one ID** (``#0123``): the
    container. **Several IDs** (``#0123, #1234``), **text** or an ID with remarks cannot be a link without guessing:
    nothing is linked, a link that exists stays, and the cell goes to the note as it is. The import never stops
    because of this cell; the report has a hint instead.

    Returns:
        ``(container ID or None, text for the note, hint for the report)``; the text is empty if the cell is
        exactly one ID.
    """
    entries = [entry.strip() for entry in _CONNECTION_SEPARATORS.split(text) if entry.strip()]
    if len(entries) == 1 and _CONNECTION_ID.match(entries[0]):
        try:
            return parse_inventory_number(entries[0]), "", ""
        except ValidationError:  # "0": cannot be an ID
            pass
    ids = [entry for entry in entries if _CONNECTION_ID.match(entry)]
    if len(ids) >= 2 and not _DECIMAL_COMMA.match(text.strip()):
        hint = _(
            "An item can be installed in one other item only, but “%(value)s” names several. No link was made; "
            "the entry was taken over into the note."
        ) % {"value": text}
    else:
        hint = _("“%(value)s” is not the ID of an item – taken over into the note, no link was made.") % {"value": text}
    return None, text, hint


def _check_references(
    references: list[tuple[int, int, int]],
    ids_in_file: set[int],
    report: ImportReport,
    parsed: list[_Row],
    *,
    key: str = "installed_in",
) -> None:
    """Find entries in "Einsatz/Verbindung" – or, IMP-016, in the price column – that point nowhere (IMP-010).

    This runs together with the other checks. An ID is known if it is in the file or already in the database.
    Circles are found later, when the links are written, because they can run through items that exist already.
    Such an entry is no error any more: the row is taken over without the link, the item is flagged
    "import error", and the cell is in its note (:func:`_flag_row`).

    Args:
        references: ``(row number, ID of the row, ID it is installed in)``.
        ids_in_file: All IDs the file contains.
        report: Receives the hints.
        parsed: The rows that have no error of their own.
        key: The column the references are in.
    """
    unknown = {target for _number, _own, target in references} - ids_in_file
    if unknown:
        unknown -= set(
            MaterialItem.objects.filter(inventory_number__in=unknown).values_list("inventory_number", flat=True)
        )
    column = FIELDS_BY_KEY[key].label
    rows = {row.number: row for row in parsed}
    for number, own_id, target in references:
        if target == own_id:
            message = (
                _("An item cannot be installed in itself.")
                if key == "installed_in"
                else _("The price of an item cannot be included in its own price.")
            )
        elif target in unknown:
            message = _("The ID %(id)s does not exist.") % {"id": format_inventory_number(target)}
        else:
            continue
        row = rows.get(number)
        if row is None:
            continue  # the row has an error of its own
        if key == "installed_in":
            row.values["installed_in"] = None
            row.values["installed_keep"] = True
        else:
            row.values["purchase_price_in"] = None
        _flag_row(row, report, key, column, message)


def _flag_row(row: _Row, report: ImportReport, key: str, column: str, message: str) -> None:
    """This cell of the row cannot be taken over; the item is flagged and the note names the cell."""
    report.warnings.append(ImportIssue(row.number, column, message))
    row.trouble.append((row.heading(key), row.raw.get(key, "")))
    row.keep.add(key)


# --- Step 4 and 5: writing -----------------------------------------------------------


class _Writer:
    """Creates and updates the database objects for the parsed rows."""

    def __init__(self, report: ImportReport, mapped: set[str]) -> None:
        self.report = report
        #: The fields a column of the file was assigned to. Only these are
        #: written; everything else keeps what is in the database.
        self.mapped = mapped
        self._categories: dict[str, Category] = {}
        self._suppliers: dict[str, Supplier] = {}
        self._manufacturers: dict[str, Manufacturer] = {}
        self._locations: dict[str, StorageLocation] = {}
        #: IMP-017: storage locations by their path, read when a file first names one by its path.
        self._paths: dict[str, int] | None = None
        self._models: dict[str, MaterialModel] = {}
        self._model_rows: dict[str, int] = {}
        #: IMP-011: the outcome of every row.
        self.log = report.log
        #: The items counted as unchanged; a later pass that changes one counts it as changed instead.
        self.unchanged_items: set[int] = set()
        #: What the current row created besides its item (categories, suppliers …), noted with the row.
        self._row_notes: list[str] = []
        #: The material model of the current row, if the row created or changed it: (model, new?, before, after).
        self._model_change: tuple[MaterialModel, bool, dict[str, Any], dict[str, Any]] | None = None
        #: MAT-073: the columns headed with the name of a custom field, and the cells of a row.
        self.custom: Any = None
        self.cells: Any = None
        #: MAT-077: the protection classes the rows of each model name, by lower-case article name.
        self.model_classes: dict[str, set[str]] = {}
        #: Duplicate serial numbers: the rows whose item is new or got another serial number: (row, item).
        self.serial_rows: list[tuple[int, MaterialItem]] = []

    # Reference data ---------------------------------------------------------

    def category(self, text: str) -> Category:
        """Find a category by code, name or path; create what is missing.

        ``Ton > Mikrofone`` (also with ``/``) names a subcategory. A new main
        category gets a code made from the first free letters of its name;
        the report lists it so that the code can be reviewed. A ``/`` that is
        part of the name of a main category stays in it: ``Video/Medien`` is
        the main category of that name (one of the defaults, ADM-011), and
        ``Video/Medien/Beamer`` a subcategory of it.
        """
        key = text.lower()
        if key in self._categories:
            return self._categories[key]
        parts = self._category_parts(text)
        parent: Category | None = None
        category: Category | None = None
        for depth, part in enumerate(parts):
            if depth == 0:
                category = (
                    Category.objects.filter(parent__isnull=True, code__iexact=part).first()
                    or Category.objects.filter(parent__isnull=True, name__iexact=part).first()
                )
                if category is None and len(parts) == 1:
                    # A plain name may also be a subcategory, if it is unambiguous.
                    matches = list(Category.objects.filter(name__iexact=part)[:2])
                    category = matches[0] if len(matches) == 1 else None
            else:
                category = Category.objects.filter(parent=parent, name__iexact=part).first()
            if category is None:
                category = Category(name=part, parent=parent)
                if parent is None:
                    category.code = self._free_code(part)
                category.full_clean()
                category.save()
                self.report.categories_created.append(
                    f"{category.path} ({category.code})" if category.code else category.path
                )
                self._row_notes.append(_("new category “%(name)s”") % {"name": self.report.categories_created[-1]})
            parent = category
        assert category is not None
        self._categories[key] = category
        return category

    @staticmethod
    def _category_parts(text: str) -> list[str]:
        """Split a category path into its names, keeping a ``/`` that belongs to a main category's name."""
        if ">" in text:
            return [part.strip() for part in text.split(">") if part.strip()]
        pieces = [part.strip() for part in text.split("/") if part.strip()]
        if len(pieces) < 2:
            return pieces
        main_names = {
            re.sub(r"\s*/\s*", "/", name).lower(): name
            for name in Category.objects.filter(parent__isnull=True, name__contains="/").values_list("name", flat=True)
        }
        for count in range(len(pieces), 1, -1):
            name = main_names.get("/".join(pieces[:count]).lower())
            if name is not None:
                return [name, *pieces[count:]]
        return pieces

    @staticmethod
    def _free_code(name: str) -> str:
        """Build an unused category code from the letters of a name (PRD-029)."""
        letters = [letter for letter in name.upper() if "A" <= letter <= "Z"] or ["X"]
        taken = set(Category.objects.filter(parent__isnull=True).values_list("code", flat=True))
        for length in range(1, len(letters) + 1):
            code = "".join(letters[:length])[:6]
            if code not in taken:
                return code
        for suffix in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            code = (letters[0] + suffix)[:6]
            if code not in taken:
                return code
        raise ValidationError(_("No free category code could be found for “%(name)s”.") % {"name": name})

    def supplier(self, name: str) -> Supplier | None:
        """Find or create a supplier by name."""
        if not name:
            return None
        key = name.lower()
        if key not in self._suppliers:
            supplier = Supplier.objects.filter(name__iexact=name).first()
            if supplier is None:
                supplier = Supplier(name=name)
                supplier.save()
                self.report.suppliers_created.append(name)
                self._row_notes.append(_("new supplier “%(name)s”") % {"name": name})
            self._suppliers[key] = supplier
        return self._suppliers[key]

    def manufacturer(self, name: str) -> Manufacturer | None:
        """Find or create a manufacturer by name."""
        if not name:
            return None
        key = name.lower()
        if key not in self._manufacturers:
            manufacturer = Manufacturer.objects.filter(name__iexact=name).first()
            if manufacturer is None:
                manufacturer = Manufacturer(name=name)
                manufacturer.save()
                self.report.manufacturers_created.append(name)
                self._row_notes.append(_("new manufacturer “%(name)s”") % {"name": name})
            self._manufacturers[key] = manufacturer
        return self._manufacturers[key]

    def storage_location(self, name: str) -> StorageLocation | None:
        """Find or create a top-level storage location by name.

        IMP-017: a path such as ``Halle 1 > Regal A`` names the location below
        another one – the export writes every location so, because two shelves may have the same name.
        """
        if not name:
            return None
        key = name.lower()
        if key not in self._locations:
            if ">" in name:
                location = self._location_by_path(name) or self._create_path(name)
            else:
                location = StorageLocation.objects.filter(name__iexact=name).first()
                if location is None:
                    location = StorageLocation(name=name)
                    location.save()
            self._locations[key] = location
        return self._locations[key]

    def _create_path(self, text: str) -> StorageLocation | None:
        """Find or create the storage locations of a path one level after the other (IMP-017).

        ``Halle 2 > Regal C`` with an existing "Halle 2" creates "Regal C" below it – never a top-level location
        named after the whole path.
        """
        parent: StorageLocation | None = None
        for part in (part.strip() for part in text.split(">")):
            if not part:
                continue
            location = StorageLocation.objects.filter(parent=parent, name__iexact=part).first()
            if location is None:
                location = StorageLocation(name=part, parent=parent)
                location.save()
            parent = location
        self._paths = None  # the cached paths no longer know the new locations
        return parent

    def _location_by_path(self, text: str) -> StorageLocation | None:
        """The storage location with this path (``Halle 1 > Regal A``, case ignored), or ``None`` (IMP-017)."""
        from rentalars.masterdata.models import location_paths

        def path_key(path: str) -> str:
            return " > ".join(part.strip() for part in path.split(">")).casefold()

        if self._paths is None:
            self._paths = {path_key(path): pk for pk, path in location_paths().items()}
        pk = self._paths.get(path_key(text))
        return StorageLocation.objects.filter(pk=pk).first() if pk is not None else None

    # Models and items -------------------------------------------------------

    def material_model(self, row: _Row) -> MaterialModel:
        """Find or create the model for a row; equal article names share one model (IMP-002).

        It is called first for every row: what it creates or changes is noted
        with the row when :meth:`item` records it (IMP-011).
        """
        self._row_notes, self._model_change = [], None
        key = row.name.lower()
        if key in _STATUS_WORDS:
            # "verfügbar" as an article name is nearly always a column of statuses assigned to "Artikelname".
            self.report.warnings.append(
                ImportIssue(
                    row.number,
                    FIELDS_BY_KEY["name"].label,
                    _(
                        "“%(name)s” is the name of a status. Is the column of the article names assigned correctly? "
                        "The row creates a material model with this name."
                    )
                    % {"name": row.name},
                )
            )
        category = self.category(row.category)
        if key in self._models:
            model = self._models[key]
            if model.category_id != category.pk:
                self.report.warnings.append(
                    ImportIssue(
                        row.number,
                        FIELDS_BY_KEY["category"].label,
                        _("“%(name)s” already has the category %(category)s from row %(row)s; this row differs.")
                        % {"name": row.name, "category": model.category.path, "row": self._model_rows[key]},
                    )
                )
            return model

        model = MaterialModel.objects.filter(name__iexact=row.name).select_related("category").first()
        is_new = model is None
        if model is None:
            model = MaterialModel(name=row.name)
        before = _model_values(model)
        model.category = category
        if row.values["specification"]:
            model.specification = row.values["specification"]
        if row.values.get("power") is not None:
            model.power_w = row.values["power"]
        if row.values["short_name"]:
            model.short_name = row.values["short_name"]
        if "protection_class" in self.mapped and not model.protection_class:
            self._take_protection_class(model, key, is_new)
        manufacturer = self.manufacturer(row.values["manufacturer"])
        if manufacturer is not None:
            model.manufacturer = manufacturer
        if row.values["category_specific"]:
            try:
                model.set_category_specific_value(row.values["category_specific"])
            except ValidationError as error:
                # Keep the text rather than lose it; it shows up for review.
                values = dict(model.field_values or {})
                values["unassigned"] = row.values["category_specific"]
                model.field_values = values
                self.report.warnings.append(
                    ImportIssue(row.number, FIELDS_BY_KEY["category_specific"].label, " ".join(error.messages))
                )
        if row.values["quantity"] is not None and row.values["quantity"] != 1:
            model.tracking_mode = TrackingMode.BULK
        if row.values["product"] and model.default_product_id is None:
            product = Product.objects.filter(article_number__iexact=row.values["product"]).first()
            if product is None:
                self.report.warnings.append(
                    ImportIssue(
                        row.number,
                        FIELDS_BY_KEY["product"].label,
                        _("There is no product %(number)s; the material stays without product.")
                        % {"number": row.values["product"]},
                    )
                )
            else:
                model.default_product = product
        after = _model_values(model)
        if is_new or before != after:
            model.full_clean()
            model.save()
            if is_new:
                self.report.models_created += 1
            else:
                self.report.models_updated += 1
            self._model_change = (model, is_new, before, after)
        self._models[key] = model
        self._model_rows[key] = row.number
        return model

    def _take_protection_class(self, model: MaterialModel, key: str, is_new: bool) -> None:
        """MAT-077: a model without a protection class takes the one all its rows of the file name.

        Only if every row of the model names the same class and none of its items has a class of its own –
        then the class is clearly the model's, and a file exported from Rentalars comes back unchanged
        (IMP-017). Otherwise the rows give their items classes of their own (:meth:`item`). The class of a
        model that has one is never changed by the import.
        """
        classes = self.model_classes.get(key, set())
        if len(classes) != 1 or "" in classes:
            return
        if not is_new and model.items.exclude(protection_class_override="").exists():
            return
        model.protection_class = next(iter(classes))

    def item(self, row: _Row, model: MaterialModel) -> MaterialItem:
        """Create the item of a row or update the one with the same ID (IMP-004, IMP-008)."""
        item = MaterialItem.objects.filter(inventory_number=row.inventory_number).first()
        is_new = item is None
        if item is None:
            item = MaterialItem(inventory_number=row.inventory_number)
        before = item._audit_values() if not is_new else {}

        if not is_new and item.material_model_id is not None and item.material_model_id != model.pk:
            # The material model is not a column of its own – it follows from the article name (and the category).
            # An item that is moved to another model by a row is told, because a wrong column makes this happen silently.
            self.report.warnings.append(
                ImportIssue(
                    row.number,
                    FIELDS_BY_KEY["name"].label,
                    _(
                        "Item %(id)s belongs to the material model “%(old)s” so far; the article name of this row is "
                        "“%(new)s”, so the item is moved to the model “%(new)s”. The material model is not imported as "
                        "a column of its own: it follows from the article name."
                    )
                    % {
                        "id": format_inventory_number(row.inventory_number),
                        "old": item.material_model.name,
                        "new": model.name,
                    },
                )
            )
        item.material_model = model
        # For a column of the file, the file is right – also where its cell
        # is empty. A field without a column is not touched: importing a
        # list without serial numbers must not wipe the ones entered since.
        if "serial_number" in self.mapped:
            item.serial_number = row.values["serial_number"]
        if "note" in self.mapped:
            item.note = row.values["note"]
        if "purchase_date" in self.mapped and "purchase_date" not in row.keep:
            bought = row.values.get("purchase_date")  # A PartialDate – the date and how much of it is known
            item.purchase_date = bought.date if bought is not None else None
            item.purchase_date_precision = bought.precision if bought is not None else partial_dates.DAY
        if "purchase_note" in self.mapped:
            item.purchase_note = row.values["purchase_note"]
        if "purchase_price" in self.mapped and "purchase_price" not in row.keep:
            item.purchase_price = row.values.get("purchase_price")
            if row.values.get("purchase_price_in") is None:
                # A price of its own (or none): no longer part of a set. Members get their set in the third pass.
                item.purchase_price_in = None
        if "supplier" in self.mapped:
            item.supplier = self.supplier(row.values["supplier"])
        if "supplier_article_number" in self.mapped:
            item.supplier_article_number = row.values["supplier_article_number"]
        if "invoice_number" in self.mapped:
            item.invoice_number = row.values["invoice_number"][:60]
        if "protection_class" in self.mapped and "protection_class" not in row.keep:
            # MAT-077: the cell is the class of the item – the same as its model's (or empty) is none of its own.
            value = row.values["protection_class"]
            item.protection_class_override = "" if value == model.protection_class else value
        if row.values["quantity"] is not None:
            item.quantity = row.values["quantity"]
        if row.values["status"] is not None and row.values["status"] != item.status:
            # MAT-044 asks for a reason when an item becomes defective. The
            # list has no column for it; the reason says where the status came from.
            is_defective = row.values["status"] == ItemStatus.DEFECTIVE
            apply_status(
                item, row.values["status"], str(_("taken over from the imported list")) if is_defective else ""
            )
        location = self.storage_location(row.values["storage_location"])
        if location is not None:
            item.storage_location = location
        if row.values["storage_spot"]:
            item.storage_spot = normalise_spot(row.values["storage_spot"])  # "1a1" is "01-A-1" (MAT-080)

        try:
            # "Installed in" is validated in the second pass, when all items exist.
            item.full_clean(exclude=["installed_in"])
        except ValidationError as error:
            self._repair(item, row, error, is_new)  # A field that is not valid is flagged, not an error
        self._flag(item, row)

        if is_new or item._audit_values() != before:
            item.full_clean(exclude=["installed_in"])
            item.save()
            if is_new:
                self.report.items_created += 1
            else:
                self.report.items_updated += 1
            outcome = NEW if is_new else CHANGED
        else:
            self.report.items_unchanged += 1
            self.unchanged_items.add(row.inventory_number)
            outcome = UNCHANGED
        if (
            "serial_number" in self.mapped
            and item.serial_number
            and (is_new or before.get("serial_number") != item.serial_number)
        ):
            self.serial_rows.append((row.number, item))
        self._record(row, item, outcome, before)
        if self.custom:
            # MAT-073: the values of the columns named like a custom field, checked against the fieldset.
            self.custom.apply(self, row.number, self.cells(row.number), item, outcome)
        return item

    #: The fields of an item the file can fill, by the field of the file; a field not valid is reset to what it was.
    _FIELD_KEYS = {
        "serial_number": "serial_number",
        "storage_spot": "storage_spot",
        "invoice_number": "invoice_number",
        "supplier_article_number": "supplier_article_number",
        "purchase_note": "purchase_note",
        "purchase_date": "purchase_date",
        "purchase_price": "purchase_price",
        "protection_class_override": "protection_class",
    }

    def _repair(self, item: MaterialItem, row: _Row, error: ValidationError, is_new: bool) -> None:
        """An entry the model does not accept does not stop the import: the field keeps its old value.

        The cell is named in the note and the item is flagged "import error" (:meth:`_flag`). A field that no cell
        feeds (the article name, the category) stays an error – the exception is raised again.
        """
        problems = error.message_dict if hasattr(error, "message_dict") else {}
        if not problems:
            raise error
        fresh = None if is_new else MaterialItem.objects.get(pk=item.pk)
        for name, messages in problems.items():
            if name == "quantity" and item.material_model is not None and not item.material_model.is_bulk:
                # The item has a quantity from earlier (it was bulk material), but the file names an individual item.
                was = item.quantity
                item.quantity = 1
                row.trouble.append((row.heading("quantity"), str(was)))
                self.report.warnings.append(
                    ImportIssue(
                        row.number,
                        FIELDS_BY_KEY["quantity"].label,
                        _(
                            "The item had the quantity %(quantity)s, but “%(model)s” is an individual item with the "
                            "quantity 1. The quantity was set to 1; the old value is in the note. (The column "
                            "“Menge” is not part of this import, the quantity comes from the stock.)"
                        )
                        % {"quantity": was, "model": item.material_model.name},
                    )
                )
                continue
            key = self._FIELD_KEYS.get(name)
            if key is None:
                raise error
            if fresh is None:
                setattr(item, name, item._meta.get_field(name).get_default())
            else:
                setattr(item, name, getattr(fresh, name))
            row.keep.add(key)
            row.trouble.append((row.heading(key), row.raw.get(key, "")))
            self.report.warnings.append(ImportIssue(row.number, FIELDS_BY_KEY[key].label, " ".join(messages)))

    def _flag(self, item: MaterialItem, row: _Row) -> None:
        """An item with entries that could not be taken over gets the status "import error" and a note.

        The note gets one line per entry, ``<heading of the column in the file>: <content of the cell>``, each only
        once, so that reading the same list again adds nothing; lines of earlier imports stay. The item is not fit
        for rental until someone fills the fields by hand and chooses another status. An item flagged earlier whose
        row has no problems now is released: it takes the status of the file, else "available".
        """
        if not row.trouble:
            if item.status == ItemStatus.IMPORT_ERROR:
                apply_status(item, row.values["status"] or ItemStatus.AVAILABLE, "")
            return
        lines = item.note.splitlines()
        for heading, content in row.trouble:
            line = f"{heading}: {' '.join(str(content).split())}"  # one line, so that reading again finds it
            if line not in lines:
                lines.append(line)
        if row.values["status"] is not None and "status" not in row.keep and _may_flag(item):
            # The status of the file is not lost: it is in the note while the item waits to be completed.
            line = f"{row.heading('status')}: {row.raw.get('status', '')}"
            if line not in lines:
                lines.append(line)
        item.note = "\n".join(lines)
        if not _may_flag(item):
            # Sold, retired, lost, blocked, defective, in repair: not rentable anyway, and the status carries a
            # meaning (and a reason) that an import must not overwrite. The note names the entries.
            self._row_notes.append(_("the note names the entries that could not be taken over (the status is kept)"))
            return
        if item.status != ItemStatus.IMPORT_ERROR:
            item.by_import = True  # stays so until the item is saved (MaterialItem.clean)
            apply_status(item, ItemStatus.IMPORT_ERROR, str(_("taken over from the import with problems")))
        self._row_notes.append(_("status “import error”: the note names the entries that could not be taken over"))
        self.report.flagged.add(row.inventory_number)

    def _record(self, row: _Row, item: MaterialItem, outcome: str, before: dict[str, Any]) -> None:
        """IMP-011: note the outcome of a row – the item's changes and those of its material model."""
        self.log.record(row.number, _row_label(row.inventory_number, row.name), outcome, self._row_notes)
        self._row_notes = []
        if outcome == CHANGED:
            self.log.compare(row.number, MaterialItem, before, item._audit_values())
        if self._model_change is not None:
            model, is_new, model_before, model_after = self._model_change
            if is_new:
                self.log.note(row.number, _("new material model “%(name)s”") % {"name": model.name})
            else:
                self.log.compare(
                    row.number,
                    MaterialModel,
                    model_before,
                    model_after,
                    prefix="model.",
                    label_format=_("%(field)s (material model)"),
                )
            self._model_change = None


#: The fields of a material model the import can change (IMP-002); compared to tell a change (IMP-011).
MODEL_FIELDS = (
    "category",
    "specification",
    "short_name",
    "manufacturer",
    "field_values",
    "tracking_mode",
    "default_product",
    "power_w",
    "protection_class",  # MAT-077
)


def _model_values(model: MaterialModel) -> dict[str, Any]:
    """The values of a model the import can change, by field name; the category-specific values as a copy."""
    values = snapshot(model, MODEL_FIELDS)
    values["field_values"] = dict(values["field_values"] or {})
    return values


def _row_label(inventory_number: int, name: str) -> str:
    """The short label of a row in the preview: ID and article name, e.g. "0310 Funkempfänger" (IMP-011)."""
    return f"{format_inventory_number(inventory_number)} {name}".strip() if inventory_number else name


def _late_change(
    report: ImportReport, unchanged: set[int], row_number: int, item: MaterialItem, before: dict[str, Any]
) -> None:
    """The second or third pass changed an item after it was counted (IMP-011).

    Its row lists what changed, merged with what the first pass changed, and
    an item counted as unchanged is counted as changed instead.
    """
    if item.inventory_number in unchanged:
        unchanged.discard(item.inventory_number)
        report.items_unchanged -= 1
        report.items_updated += 1
    report.log.compare(row_number, MaterialItem, before, item._audit_values())


def _resolve_installations(
    rows: list[_Row], items: dict[int, MaterialItem], report: ImportReport, unchanged: set[int] | None = None
) -> None:
    """Second pass: turn the column "Einsatz/Verbindung" into links between items (IMP-010).

    Every entry becomes "permanently installed"; the report lists the items
    so that individual ones can be switched to "loosely contained" later. A
    link that already exists is left as it is – including a connection type
    that was changed by hand since the last import (IMP-012).

    ``unchanged``: the items the first pass counted as unchanged; one this
    pass changes is counted as changed and its row shows the change (IMP-011).
    """
    # A cell with text or several IDs (``installed_keep``) changes no link, not even removes one.
    wanted = {row.inventory_number: row.values["installed_in"] for row in rows if not row.values["installed_keep"]}
    by_number = {row.inventory_number: row for row in rows}

    known = set(items) | set(
        MaterialItem.objects.filter(inventory_number__in=[target for target in wanted.values() if target]).values_list(
            "inventory_number", flat=True
        )
    )
    for number, target in list(wanted.items()):
        if target and target not in known:
            message = _("The ID %(id)s does not exist.") % {"id": format_inventory_number(target)}
        elif target == number:
            message = _("An item cannot be installed in itself.")
        else:
            continue
        _flag_late(by_number[number], items[number], report, "installed_in", message, unchanged)
        del wanted[number]

    # Circles: follow the chain of containers; meeting the start again is a circle.
    existing_links = dict(
        MaterialItem.objects.filter(installed_in__isnull=False).values_list(
            "inventory_number", "installed_in__inventory_number"
        )
    )
    links = {**existing_links, **wanted}
    for number, target in list(wanted.items()):
        seen = {number}
        current = target
        while current:
            if current in seen:
                message = _("Circular reference: %(id)s would end up installed in itself.") % {
                    "id": format_inventory_number(number)
                }
                _flag_late(by_number[number], items[number], report, "installed_in", message, unchanged)
                del wanted[number]
                break
            seen.add(current)
            current = links.get(current)

    containers = {
        item.inventory_number: item
        for item in MaterialItem.objects.filter(inventory_number__in=[t for t in wanted.values() if t]).select_related(
            "material_model"
        )
    }
    for number, target in wanted.items():
        item = items[number]
        current_target = item.installed_in.inventory_number if item.installed_in_id else None
        if current_target == target:
            continue
        before = item._audit_values()
        old = (item.installed_in, item.connection_type, item.individually_rentable)
        item.installed_in = containers[target] if target else None
        item.connection_type = ConnectionType.FIXED
        item.individually_rentable = False
        try:
            item.full_clean()
        except ValidationError as error:
            item.installed_in, item.connection_type, item.individually_rentable = old
            _flag_late(by_number[number], item, report, "installed_in", " ".join(error.messages), unchanged)
            continue
        item.save()
        _late_change(report, unchanged if unchanged is not None else set(), by_number[number].number, item, before)
        if target:
            report.installed_links.append(f"{format_inventory_number(number)} → {format_inventory_number(target)}")


def _may_flag(item: MaterialItem) -> bool:
    """Whether an item may get the status "import error": one that is rentable (or flagged already).

    An item that is sold, retired, lost, blocked, defective or in repair keeps its status – an import must not make a
    sold item rentable again when it releases the flag later.
    """
    return item.status in OPERATIONAL_STATUSES or item.status == ItemStatus.IMPORT_ERROR


def _flag_late(
    row: _Row, item: MaterialItem, report: ImportReport, key: str, message: str, unchanged: set[int] | None
) -> None:
    """A link or price set that cannot be made is no error: the item is flagged "import error" and the cell noted.

    The same as :meth:`_Writer._flag` for the passes that run once all items exist (second and third pass). The item
    keeps what it had; the entry of the file is in its note under the heading of the column.
    """
    before = item._audit_values()
    report.warnings.append(ImportIssue(row.number, FIELDS_BY_KEY[key].label, message))
    lines = item.note.splitlines()
    line = f"{row.heading(key)}: {' '.join(str(row.raw.get(key, '')).split())}"
    if line not in lines:
        lines.append(line)
    item.note = "\n".join(lines)
    flag = _may_flag(item)
    if flag and item.status != ItemStatus.IMPORT_ERROR:
        item.by_import = True
        apply_status(item, ItemStatus.IMPORT_ERROR, str(_("taken over from the import with problems")))
    item.full_clean()
    item.save()
    if flag:
        report.flagged.add(row.inventory_number)
        report.log.note(row.number, _("status “import error”: the note names the entries that could not be taken over"))
    else:
        report.log.note(row.number, _("the note names the entries that could not be taken over (the status is kept)"))
    _late_change(report, unchanged if unchanged is not None else set(), row.number, item, before)


def _resolve_purchase_sets(
    rows: list[_Row], items: dict[int, MaterialItem], report: ImportReport, unchanged: set[int] | None = None
) -> None:
    """Third pass: link the items of a set bought together to the item with the price (MAT-054, IMP-016).

    A price cell ``#0851`` names the item whose price includes this one. The
    file may name an item that names another one in turn (``#0852`` while
    0852 says ``#0851``); the link always goes to the end of that chain, the
    item with the price – also through items that are not in the file but in
    Rentalars. A chain that runs in a circle has no price at all and is an
    error, as is an item outside the file whose price is included in an item
    the file now puts into another set (it would be a set inside a set).

    ``unchanged``: as for the second pass (IMP-011).
    """
    column = FIELDS_BY_KEY["purchase_price"].label
    wanted = {
        row.inventory_number: row.values["purchase_price_in"] for row in rows if row.values.get("purchase_price_in")
    }
    if not wanted:
        return
    row_numbers = {row.inventory_number: row.number for row in rows}
    in_file = set(row_numbers)
    outside = {
        item.inventory_number: item
        for item in MaterialItem.objects.filter(inventory_number__in=set(wanted.values()) - in_file).select_related(
            "purchase_price_in"
        )
    }

    def head_of(number: int) -> int | None:
        seen = {number}
        current = wanted[number]
        while True:
            if current in seen:
                return None
            seen.add(current)
            if current in wanted:
                current = wanted[current]
            elif current not in in_file and current in outside and outside[current].purchase_price_in_id:
                current = outside[current].purchase_price_in.inventory_number  # type: ignore[union-attr]
            else:
                return current

    by_number = {row.inventory_number: row for row in rows}
    heads: dict[int, int] = {}
    for number in wanted:
        head = head_of(number)
        if head is None:
            # No error: the item is flagged "import error", the cell is in its note, the price stays as it is.
            message = _("Circular reference: the prices of %(id)s and the items it names include each other.") % {
                "id": format_inventory_number(number)
            }
            _flag_late(by_number[number], items[number], report, "purchase_price", message, unchanged)
        else:
            heads[number] = head
    members_elsewhere = (
        MaterialItem.objects.filter(purchase_price_in__inventory_number__in=list(wanted))
        .exclude(inventory_number__in=in_file)
        .select_related("purchase_price_in")
    )
    for other in members_elsewhere:
        target = other.purchase_price_in.inventory_number  # type: ignore[union-attr]
        report.errors.append(
            ImportIssue(
                row_numbers[target],
                column,
                _(
                    "The price of %(other)s is included in %(id)s, which this list puts into another set. "
                    "Add %(other)s to the list with its new price cell."
                )
                % {"other": other.display_id, "id": format_inventory_number(target)},
            )
        )
    if report.errors:
        return
    head_items = {
        item.inventory_number: item
        for item in MaterialItem.objects.filter(inventory_number__in=set(heads.values()) - set(items))
    }
    head_items.update({number: item for number, item in items.items() if number in set(heads.values())})
    sets: dict[int, list[str]] = {}
    for number, head in sorted(heads.items()):
        item = items[number]
        head_item = head_items[head]
        if head_item.purchase_price is None:
            report.warnings.append(
                ImportIssue(
                    row_numbers[number],
                    column,
                    _("The price of %(id)s is included in %(head)s, but %(head)s has no purchase price either.")
                    % {"id": item.display_id, "head": head_item.display_id},
                )
            )
        sets.setdefault(head, []).append(item.display_id)
        if item.purchase_price_in_id == head_item.pk and item.purchase_price is None:
            continue
        before = item._audit_values()
        old = (item.purchase_price_in, item.purchase_price)
        item.purchase_price_in = head_item
        item.purchase_price = None
        try:
            item.full_clean()
        except ValidationError as error:
            item.purchase_price_in, item.purchase_price = old
            _flag_late(by_number[number], item, report, "purchase_price", " ".join(_messages_of(error)), unchanged)
            continue
        item.save()
        _late_change(report, unchanged if unchanged is not None else set(), row_numbers[number], item, before)
    report.purchase_sets = [f"{format_inventory_number(head)}: {', '.join(ids)}" for head, ids in sorted(sets.items())]


#: How many rows get their own warning about a serial number; the rest is counted in one.
MAX_SERIAL_WARNINGS = 100


def _warn_about_serial_numbers(serial_rows: list[tuple[int, MaterialItem]], report: ImportReport) -> None:
    """Warn at every row whose new or changed serial number another item has too (MAT-004, IMP-011).

    A warning, not an error: the same number may be right at another manufacturer's model, and the import goes on.
    It is checked once all rows are written, so that a list that swaps two serial numbers does not warn, and a
    number given twice in the file warns at both rows. Retired and sold items count.
    """
    if not serial_rows:
        return
    clashes = serial_check.clashes_of_items([item for _row, item in serial_rows])
    label = FIELDS_BY_KEY["serial_number"].label
    found = [(number, clashes[item.pk]) for number, item in serial_rows if item.pk in clashes]
    for number, clash in found[:MAX_SERIAL_WARNINGS]:
        report.warnings.append(ImportIssue(number, label, clash.text))
    if len(found) > MAX_SERIAL_WARNINGS:
        report.warnings.append(
            ImportIssue(
                None,
                label,
                _("%(count)d more rows have a serial number that exists already.")
                % {"count": len(found) - MAX_SERIAL_WARNINGS},
            )
        )


def import_material(
    table: Table,
    mapping: dict[str, int | None],
    *,
    dry_run: bool,
    actor: Any = "system:import",
    progress: Progress = no_progress,
    gross_rate: Decimal | None = None,
    rights: Any = None,
) -> ImportReport:
    """Import a material table, or only report what the import would do.

    Args:
        table: The file content from :func:`read_table`.
        mapping: Which column feeds which field, from :func:`resolve_mapping`.
        dry_run: ``True`` checks everything and writes nothing (IMP-003).
        actor: The user (or job name) recorded in the change log.
        progress: Told how far the import got, for a task in the background (NFA-041).
        gross_rate: IMP-014: the prices of the file are gross and include this tax rate in percent;
            ``None``: they are net.
        rights: The rights of the one importing; they decide which values the report shows (IMP-011).
            ``None`` – the command on the server – shows all.

    Returns:
        The report. If ``report.ok`` is false, nothing was written.
    """
    report = ImportReport(dry_run=dry_run, rows_read=len(table.rows))
    report.log.rights = rights
    report.log.use_labels(cells_by_number(table), _label_of_cells(mapping))
    report.errors.extend(tabular.missing_required(mapping, IMPORT_FIELDS))
    if report.errors:
        return report
    if (
        mapping.get("purchase_price") is not None
        and rights is not None
        and not rights.has(SpecialRight.PURCHASE_PRICES)
    ):
        # IMP-011: the import takes the prices over as before; the report does not show them.
        report.warnings.append(
            ImportIssue(
                None,
                FIELDS_BY_KEY["purchase_price"].label,
                _(
                    "The purchase prices of the file are imported. Without the right to see purchase prices "
                    "their values are not shown here."
                ),
            )
        )

    factor = None
    if gross_rate is not None:
        factor = gross_factor(gross_rate)
        report.prices_gross_rate = f"{Decimal(str(gross_rate)).normalize():f}"
    rows = _parse_rows(table, mapping, report, gross=factor)
    if report.errors:
        return report

    # MAT-073: a column headed with the name of a custom field fills it (customfields.importing).
    from rentalars.customfields.importing import CustomColumns

    custom = CustomColumns(table.headers, mapping, rights)
    report.warnings.extend(custom.warnings)

    with acting_as(actor), transaction.atomic():
        writer = _Writer(report, {key for key, index in mapping.items() if index is not None})
        writer.custom, writer.cells = custom, cells_by_number(table)
        for row in rows:  # MAT-077: see _Writer._take_protection_class
            writer.model_classes.setdefault(row.name.lower(), set()).add(row.values.get("protection_class", ""))
        items: dict[int, MaterialItem] = {}
        for position, row in enumerate(rows):
            if position % 50 == 0:
                progress(10 + 80 * position // len(rows))
            try:
                with transaction.atomic():
                    model = writer.material_model(row)
                    items[row.inventory_number] = writer.item(row, model)
            except ValidationError as error:
                for message in _messages_of(error):
                    report.errors.append(ImportIssue(row.number, "", message))
        if not report.errors and mapping.get("installed_in") is not None:
            _resolve_installations(rows, items, report, writer.unchanged_items)
        if not report.errors and mapping.get("purchase_price") is not None:
            _resolve_purchase_sets(rows, items, report, writer.unchanged_items)

        if not report.errors:
            _warn_about_serial_numbers(writer.serial_rows, report)
        if report.flagged and not report.errors:
            report.warnings.append(
                ImportIssue(
                    None,
                    FIELDS_BY_KEY["status"].label,
                    ngettext(
                        "%(count)d item was taken over with the status “import error”: what could not be read "
                        "is in its note, under the heading of its column. Fill in the fields by hand and "
                        "choose another status; until then the item is not fit for rental.",
                        "%(count)d items were taken over with the status “import error”: what could not be read "
                        "is in the note of each, under the heading of its column. Fill in the fields by hand and "
                        "choose another status; until then the items are not fit for rental.",
                        len(report.flagged),
                    )
                    % {"count": len(report.flagged)},
                )
            )
        if rows:
            report.highest_id = max(row.inventory_number for row in rows)
        if not report.errors:
            # IMP-008: new IDs continue behind the highest imported one.
            NumberRange.ensure_next_is_above(NumberRangeKey.MATERIAL_ITEM, report.highest_id)
            next_value = NumberRange.objects.get(key=NumberRangeKey.MATERIAL_ITEM).next_value
            report.next_id = format_inventory_number(next_value)
            if not dry_run:
                record_event(
                    SystemSettings.load(),
                    "import.material",
                    {"created": report.items_created, "updated": report.items_updated, "rows": report.rows_read},
                )
        if dry_run or report.errors:
            # A dry run and a failed import leave no trace in the database.
            transaction.set_rollback(True)
    return report


_messages_of = messages_of


def _label_of_cells(mapping: dict[str, int | None]) -> Any:
    """IMP-011: the label of a row known only from an error – its ID (with leading zeros, if it is one) and name."""

    def label_of(cells: list[Any]) -> str:
        def cell(key: str) -> str:
            index = mapping.get(key)
            return _text(cells[index]) if index is not None and index < len(cells) else ""

        number = cell("inventory_number")
        with contextlib.suppress(ValidationError):
            number = format_inventory_number(parse_inventory_number(number)) if number else ""
        return " ".join(part for part in (number, cell("name")) if part)

    return label_of


#: IMP-014: the values of the choice "prices are …".
PRICES_NET, PRICES_GROSS = "net", "gross"


def tax_rate_choices() -> list[tuple[str, str]]:
    """IMP-014: the active tax rates a gross price may include, as ``("19", "19 %")``."""
    from rentalars.masterdata.models import TaxRate

    rates = sorted({rate.rate for rate in TaxRate.objects.filter(is_active=True)}, reverse=True)
    return [(f"{rate.normalize():f}", f"{rate.normalize():f} %".replace(".", ",")) for rate in rates]


def default_tax_rate() -> str:
    """IMP-014: the rate gross prices are taken to include unless chosen: the default tax rate."""
    from rentalars.masterdata.models import TaxRate

    default = TaxRate.get_default()
    return f"{default.rate.normalize():f}" if default is not None else ""


def run_import(
    table: Table,
    mapping: dict[str, int | None],
    *,
    rights: Any,
    options: dict[str, Any] | None = None,
    **arguments: Any,
) -> ImportReport:
    """The material import as registered in ``core.imports``; the write right was checked by the caller.

    ``options`` are the choices of IMP-014: ``prices`` (net or gross) and
    ``price_tax_rate``, the percentage a gross price includes.
    """
    options = options or {}
    gross_rate = None
    if options.get("prices") == PRICES_GROSS and options.get("price_tax_rate"):
        gross_rate = Decimal(str(options["price_tax_rate"]))
    return import_material(table, mapping, gross_rate=gross_rate, rights=rights, **arguments)
