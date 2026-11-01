# SPDX-License-Identifier: GPL-3.0-or-later
"""Exports in the format of the imports (IMP-017; IMP-001, IMP-005, API-002).

The requirement: whatever can be imported under Settings → Import and export can also be exported, at least as CSV, in plain
text (not as the model-and-key format of the backups), so that the CSV could in theory be worked with without Rentalars.

For each import – material, products, customers, people – there is one CSV file whose columns are exactly
the columns of the import, under the same headings and in the same order, and whose values are written the
way the import reads them: names and numbers instead of database IDs (the category as its path, the
supplier, the unit and the tax rate by their names, the storage location by its path, the owner by the
customer number, job functions by name). Exported and imported again, the file changes nothing – the dry run
calls every row "unchanged".

The file
    UTF-8 with byte order mark and semicolons, one row per record, as every list of Rentalars exports
    (IMP-005). Numbers with a decimal comma and without thousands separator (``1234,50``), dates as
    ``31.12.2027``, yes and no as "ja" and "nein", choices by their German names – always in German, like
    the headings of the import, whatever the language of the user (UIX-029): it is a file for the import.
    Text a spreadsheet program would run as a formula gets a leading apostrophe ("CSV injection"); the
    import takes it away again (``core.tabular.cell_text``).

Rights
    The read right on the module of the import. Columns of prices, purchase prices or rates need the
    special right the import and the list ask for; without it the column is left out – and importing such
    a file leaves those values as they are.

Long lists
    The file is written while it is sent, a chunk of :data:`CHUNK_ROWS` records at a time
    (``StreamingHttpResponse``), with a fixed number of queries per chunk – never one per row. 20,000
    items take a few seconds.

Each module describes its export (:class:`ImportFormatExport`) and registers it next to its import in its
``ready()``. Further columns of another module come in through :func:`register_columns`: a column counts
if the import has a field of its key, or – like the custom fields of items, which the material import
finds by their names – if it brings a heading of its own; such columns follow the fields of the import.
"""

from __future__ import annotations

import csv
import datetime
import io
import itertools
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.http import StreamingHttpResponse
from django.utils import timezone, translation
from django.utils.text import slugify
from django.utils.translation import gettext as _

from rentalars.core import imports
from rentalars.core.tables import BYTE_ORDER_MARK
from rentalars.core.tabular import FORMULA_STARTS

#: Records written at a time; the queries of an export grow with the chunks, never with the rows.
CHUNK_ROWS = 2000

#: The language of the files: that of the headings of the imports.
FILE_LANGUAGE = "de"

#: A plain number such as ``-12,50`` or ``+4930123`` is no formula (as in ``core.tables.csv_text``).
_PLAIN_NUMBER = re.compile(r"^[+-]?[\d .,]*\d[\d .,]*$")

#: The first characters of a cell that may need the apostrophe: those of formulas, and the apostrophe itself.
_FIRST_OF_FORMULA = frozenset((*FORMULA_STARTS, "'"))


@dataclass(frozen=True)
class ExportColumn:
    """One column of an export: the field of the import it fills and how its value is read from a row.

    Attributes:
        key: The key of the field of the import (``ImportField.key``); the heading is that field's label.
        value: ``row -> value``: text, a number, a date, yes/no or ``None`` (see :func:`cell`).
        right: The special right the column needs (prices, purchase prices, rates); empty: none.
        heading: For a column the import recognises by its heading rather than as one of its fields – a
            custom field of items, whose name is the heading. Such columns follow the fields of the import.
    """

    key: str
    value: Callable[[Any], Any]
    right: str = ""
    heading: str = ""


@dataclass(frozen=True)
class ColumnSource:
    """Columns another module adds to an export, e.g. custom fields of items (IMP-017, MAT-073).

    Attributes:
        columns: ``rights -> columns`` – those the rights may see; one counts if the import has a field of
            its key, or if it has a heading of its own.
        prepare: Called with every chunk of rows before they are written, to load what the columns need
            for all of them at once (one query per chunk, not per row).
    """

    columns: Callable[[Any], Iterable[ExportColumn]]
    prepare: Callable[[list[Any]], None] | None = None


@dataclass(frozen=True)
class ImportFormatExport:
    """The export of one import.

    Attributes:
        key: The key of the import (``material``, ``products``, ``customers``, ``people``).
        name: Names the file, e.g. "Kunden" → ``kunden-importformat-2027-03-01.csv``.
        columns: The columns the module knows, by the keys of the import's fields.
        chunks: ``rights -> chunks of rows``; the rows are whatever the columns read (dicts as a rule).
    """

    key: str
    name: Any
    columns: tuple[ExportColumn, ...]
    chunks: Callable[[Any], Iterator[list[Any]]]

    @property
    def kind(self) -> imports.ImportKind:
        """The import this export belongs to."""
        return imports.get(self.key)

    def columns_for(self, rights: Any) -> list[tuple[str, ExportColumn]]:
        """The columns of the file for these rights as ``(heading, column)``, those without right left out.

        First the fields of the import in its order, under their labels; then the columns of other modules
        that the import recognises by their headings.
        """
        return self._layout(rights)[0]

    def _layout(self, rights: Any) -> tuple[list[tuple[str, ExportColumn]], list[Callable[[list[Any]], None]]]:
        """The columns for these rights, and what prepares the rows for the columns of other modules.

        A module whose columns the rights do not reach (or that has none) loads nothing for the rows.
        """
        known = {column.key: column for column in self.columns}
        extra: list[ExportColumn] = []
        sources: dict[int, ColumnSource] = {}
        for source in _SOURCES.get(self.key, []):
            for column in source.columns(rights):
                if column.heading:
                    extra.append(column)
                else:
                    known[column.key] = column
                sources[id(column)] = source
        result = [(field.label, known[field.key]) for field in self.kind.fields if field.key in known]
        result += [(column.heading, column) for column in extra]
        result = [(heading, column) for heading, column in result if not column.right or rights.has(column.right)]
        preparers = []
        for _heading, column in result:
            origin = sources.get(id(column))
            if origin is not None and origin.prepare is not None and origin.prepare not in preparers:
                preparers.append(origin.prepare)
        return result, preparers

    def file_name(self) -> str:
        """The name the file is saved under, e.g. ``kunden-importformat-2027-03-01.csv``."""
        label = _("import format")  # not inside the f-string: makemessages would not find it there
        words = f"{self.name} {label}"
        return f"{slugify(words)}-{timezone.localdate():%Y-%m-%d}.csv"


_EXPORTS: dict[str, ImportFormatExport] = {}
_SOURCES: dict[str, list[ColumnSource]] = {}


def register(export: ImportFormatExport) -> None:
    """Make the export of an import known; called by the modules in ``ready()`` next to their import."""
    _EXPORTS[export.key] = export


def register_columns(key: str, source: ColumnSource) -> None:
    """Add columns of another module to the export of the import ``key`` (MAT-073, the hook for custom fields)."""
    _SOURCES.setdefault(key, []).append(source)


def get(key: str) -> ImportFormatExport:
    """The export of the import with this key.

    Raises:
        LookupError: There is none.
    """
    try:
        return _EXPORTS[key]
    except KeyError as error:
        raise LookupError(key) from error


def exports() -> list[ImportFormatExport]:
    """Every export, in the order of the imports."""
    return [_EXPORTS[kind.key] for kind in imports.kinds() if kind.key in _EXPORTS]


# --- Values ---------------------------------------------------------------------------------------


def number(value: Decimal | int | None, *, places: int | None = None) -> str | None:
    """A number as the import reads it: decimal comma, no thousands separator – ``1234,5``; ``None`` stays ``None``.

    ``places`` rounds to that many places and keeps them (``12,50``); without, needless zeros go.
    """
    if value is None:
        return None
    decimal = Decimal(value)
    text = format(decimal.quantize(Decimal(1).scaleb(-places)) if places is not None else decimal.normalize(), "f")
    return text.replace(".", ",")


def amount(value: Decimal | int | None) -> str | None:
    """An amount of money with two places: ``1234,50``."""
    return number(value, places=2)


#: The German labels of choices, by (choices, stored value) – looked up once, not for every row.
_LABELS: dict[tuple[Any, str], str] = {}


def label(choices: Any, value: str) -> str:
    """The German label of a stored choice – the language of the files; empty for empty, unknown as it is."""
    if not value:
        return ""
    key = (choices, value)
    if key not in _LABELS:
        try:
            with translation.override(FILE_LANGUAGE):
                _LABELS[key] = str(choices(value).label)
        except ValueError:
            return value
    return _LABELS[key]


def cell(value: Any) -> str:
    """One cell as the import reads it back unchanged (see the module text).

    Text keeps its line breaks – the import keeps them as well – and only loses spaces at its ends, which
    the import drops too. Text that would start a formula gets an apostrophe in front; so does text that
    starts with one followed by such a character, which the import would otherwise take for that mark.
    """
    if type(value) is str:  # the common case first: tens of thousands of cells
        text = value.strip()
        if text[:1] not in _FIRST_OF_FORMULA:
            return text
    elif value is None:
        return ""
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, datetime.datetime):
        value = timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, Decimal | int):
        return number(value) or ""
    text = str(value).strip()
    formula = text[:1] in FORMULA_STARTS and not _PLAIN_NUMBER.match(text)
    if formula or (text[:1] == "'" and text[1:2] in FORMULA_STARTS):
        return "'" + text
    return text


# --- The file -------------------------------------------------------------------------------------


def stream(export: ImportFormatExport, rights: Any) -> Iterator[str]:
    """The file as pieces of text: the heading row, then one piece per chunk of rows.

    Each chunk is written under the language of the files; between the pieces nothing of it stays active.
    """
    columns, preparers = export._layout(rights)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    buffer.write(BYTE_ORDER_MARK)
    writer.writerow([heading for heading, _column in columns])
    yield _drain(buffer)
    for chunk in export.chunks(rights):
        with translation.override(FILE_LANGUAGE):
            for prepare in preparers:
                prepare(chunk)
            for row in chunk:
                writer.writerow([cell(column.value(row)) for _heading, column in columns])
        yield _drain(buffer)


def _drain(buffer: io.StringIO) -> str:
    """What was written into the buffer so far; the buffer is emptied."""
    text = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate()
    return text


def text_of(export: ImportFormatExport, rights: Any) -> str:
    """The whole file as one text – for programs on the server and the tests."""
    return "".join(stream(export, rights))


def response(export: ImportFormatExport, rights: Any) -> StreamingHttpResponse:
    """The file as a download, written while it is sent (browser and API)."""
    answer = StreamingHttpResponse(stream(export, rights), content_type="text/csv; charset=utf-8")
    answer["Content-Disposition"] = f'attachment; filename="{export.file_name()}"'
    return answer


def chunked(rows: Iterable[Any], size: int = CHUNK_ROWS) -> Iterator[list[Any]]:
    """Rows in lists of ``size``."""
    iterator = iter(rows)
    while chunk := list(itertools.islice(iterator, size)):
        yield chunk


# --- Categories, shared by material and products ----------------------------------------------------


class CategoryIndex:
    """Every category with its path and its first category-specific field – from two queries (MAT-009, PRD-009)."""

    def __init__(self) -> None:
        from rentalars.masterdata.models import Category, CategoryField

        self._rows = {
            pk: (name, parent) for pk, name, parent in Category.objects.values_list("pk", "name", "parent_id")
        }
        self._fields: dict[int, list[Any]] = {}
        for field in CategoryField.objects.order_by("category_id", "position", "id"):
            self._fields.setdefault(field.category_id, []).append(field)
        self._paths: dict[int, str] = {}
        self._primary: dict[int, Any] = {}

    def chain(self, pk: int) -> list[int]:
        """The categories from the main category down to this one."""
        chain: list[int] = []
        current: int | None = pk
        while current is not None and current not in chain and current in self._rows:
            chain.append(current)
            current = self._rows[current][1]
        return list(reversed(chain))

    def path(self, pk: int | None) -> str:
        """``Ton > Mikrofone``; a main category is its name."""
        if pk is None:
            return ""
        if pk not in self._paths:
            self._paths[pk] = " > ".join(self._rows[part][0] for part in self.chain(pk))
        return self._paths[pk]

    def primary_field(self, pk: int) -> Any:
        """The first field of the category, or of the nearest parent with fields (``Category.primary_field``)."""
        if pk not in self._primary:
            fields = next((self._fields[part] for part in reversed(self.chain(pk)) if self._fields.get(part)), [])
            self._primary[pk] = fields[0] if fields else None
        return self._primary[pk]
