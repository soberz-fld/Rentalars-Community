# SPDX-License-Identifier: GPL-3.0-or-later
"""What an import does with each row of its file: the preview of the dry run (IMP-011).

The requirement: a preview in the browser. The dry run shows every row – new, changed (old → new), unchanged, error –
filterable; only then "Import now".

Every import – material, products, customers, people – notes here what it
did, or would do, with a row of the file:

* ``new`` – it creates a record;
* ``changed`` – it changes one; every changed field is kept as old → new;
* ``unchanged`` – it finds the record as the file describes it;
* ``error`` – it cannot take the row; the messages say why.

The dry run and the import note the same, so the report of the import shows
what the dry run showed. The report stays plain data, because it is kept
with the task in the background (NFA-041), and it stays small for long
lists: an unchanged row is only its number, a short label and its outcome.

Values are written for reading – dates, amounts, yes or no, the names of
related records instead of their IDs – under the labels the pages use, as
in the change log (``core.history``). A value the user may not see stays
hidden as it does there (``audit_sensitive``, AUT-019): the field is named
as changed, its values are not.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

#: The outcomes of a row (IMP-011).
NEW, CHANGED, UNCHANGED, ERROR = "new", "changed", "unchanged", "error"
OUTCOMES = (NEW, CHANGED, UNCHANGED, ERROR)

#: Fields that hold an amount of money; their values are shown with the currency.
MONEY_FIELDS = frozenset(
    {
        "purchase_price",
        "price",
        "sale_price",
        "hourly_rate",
        "daily_rate",
        # LOG-005, LOG-010: the rates and costs of a vehicle.
        "price_per_km",
        "trailer_surcharge_per_km",
        "cost_per_km",
        "cost_per_day",
    }
)

#: How a missing value is shown, as in the change log.
EMPTY = "–"


@dataclass
class FieldChange:
    """One field a row changes, with its values before and after – as stored and as shown."""

    key: str
    label: str
    old: Any
    new: Any
    old_text: str = ""
    new_text: str = ""
    #: The reader may not see the values (AUT-019); only the field is named.
    hidden: bool = False

    def as_dict(self) -> dict[str, Any]:
        """The change as plain data; a hidden change has no values."""
        if self.hidden:
            return {"field": self.key, "label": self.label, "hidden": True}
        return {"field": self.key, "label": self.label, "old": self.old_text, "new": self.new_text}


@dataclass
class RowRecord:
    """What happened to one row."""

    row: int
    label: str
    outcome: str
    changes: dict[str, FieldChange] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class RowLog:
    """Collects the outcome of every row while an import runs (IMP-011).

    The import calls :meth:`record` once it knows what becomes of a row and
    :meth:`compare` or :meth:`change` for what it changes. A later step may
    change a row again – the material import links items in a second and a
    third pass –; its changes are merged into the row: the old value stays
    the one from before the import, and an unchanged row becomes a changed one.

    ``rights`` are those of the user who imports; ``None`` (the command on
    the server) shows every value.
    """

    def __init__(self, rights: Any = None) -> None:
        self.rights = rights
        self.records: dict[int, RowRecord] = {}
        self._lookup: Any = None
        self._cells: Callable[[int], list[Any] | None] | None = None
        self._label_of: Callable[[list[Any]], str] | None = None

    # --- Recording ------------------------------------------------------------------------------

    def record(self, row: int, label: str, outcome: str, notes: Iterable[str] = ()) -> RowRecord:
        """Note the outcome of a row; a row recorded before keeps its changes and notes."""
        record = self.records.get(row)
        if record is None:
            record = self.records[row] = RowRecord(row, label, outcome)
        else:
            record.label = label or record.label
            record.outcome = outcome
        record.notes.extend(str(note) for note in notes)
        return record

    def outcome_of(self, row: int) -> str | None:
        """The outcome noted for a row so far, or ``None``."""
        record = self.records.get(row)
        return record.outcome if record is not None else None

    def note(self, row: int, text: str) -> None:
        """Add a note to a row that is recorded already."""
        record = self.records.get(row)
        if record is not None:
            record.notes.append(str(text))

    def compare(
        self,
        row: int,
        model: Any,
        before: dict[str, Any],
        after: dict[str, Any],
        *,
        prefix: str = "",
        label_format: str = "",
    ) -> None:
        """Note every field whose value differs between two snapshots of a record.

        Args:
            row: The row of the file.
            model: The model of the record, for labels, readable values and hidden fields.
            before: ``{field name: value}`` before the import touched the record.
            after: The same after it.
            prefix: Put in front of the field names, to tell the fields of two records apart.
            label_format: Text such as ``"%(field)s (material model)"`` the label is put into.
        """
        for name, value in after.items():
            if name in before and before[name] != value:
                self.change(row, model, name, before[name], value, key=prefix + name, label_format=label_format)

    def change(
        self,
        row: int,
        model: Any,
        name: str,
        old: Any,
        new: Any,
        *,
        key: str = "",
        label: str = "",
        label_format: str = "",
        sensitive: str | None = None,
    ) -> None:
        """Note one changed field of a recorded row; a new row has no changes to show.

        Args:
            row: The row of the file.
            model: The model the field belongs to (labels, readable values, ``audit_sensitive``).
            name: The name of the field in the model.
            old: The value before the import.
            new: The value after it.
            key: Tells the change apart from others of the row; default: ``name``.
            label: The label to show instead of the one of the field.
            label_format: Text such as ``"%(field)s (material model)"`` the label is put into.
            sensitive: The special right needed to see the values; default: the model's ``audit_sensitive``.
        """
        record = self.records.get(row)
        if record is None or record.outcome in (NEW, ERROR):
            return
        key = key or name
        existing = record.changes.get(key)
        if existing is not None:
            # A later pass changes the field again: the value before the import stays the old one.
            old = existing.old
        if old == new:
            record.changes.pop(key, None)
            return
        if sensitive is None:
            sensitive = getattr(model, "audit_sensitive", {}).get(name)
        hidden = bool(sensitive) and self.rights is not None and not self.rights.has(sensitive)
        if hidden:
            field_label, old_text, new_text = self._display(model, name, None)[0], "", ""
        else:
            field_label, new_text = self._display(model, name, new)
            old_text = existing.old_text if existing is not None else self._display(model, name, old)[1]
        if not label:
            label = label_format % {"field": field_label} if label_format else field_label
        record.changes[key] = FieldChange(key, label, old, new, old_text, new_text, hidden)
        if record.outcome == UNCHANGED:
            record.outcome = CHANGED

    def use_labels(self, cells: Callable[[int], list[Any] | None], label_of: Callable[[list[Any]], str]) -> None:
        """How to label a row that ended in an error before it was recorded: from its cells.

        Args:
            cells: The cells of a row of the file by its number (``None`` if there is no such row).
            label_of: Makes the short label (ID, name) from the cells.
        """
        self._cells, self._label_of = cells, label_of

    # --- Showing --------------------------------------------------------------------------------

    def _display(self, model: Any, name: str, value: Any) -> tuple[str, str]:
        """Label and readable value of a field, as the change log shows them, with amounts in euros."""
        from rentalars.core.history import _display, _Lookup
        from rentalars.core.money import format_money

        if self._lookup is None:
            self._lookup = _Lookup()
        label, text = _display(model, name, value, self._lookup)
        if value in (None, "") or text == EMPTY:
            return label, EMPTY
        if isinstance(value, dict):
            parts = [str(part) for part in value.values() if part not in (None, "")]
            return label, "; ".join(parts) or EMPTY
        if isinstance(value, list):
            return label, ", ".join(str(part) for part in value) or EMPTY
        if name in MONEY_FIELDS:
            try:
                return label, format_money(Decimal(str(value)))
            except InvalidOperation:
                return label, text
        if name.endswith("_percent"):
            return label, f"{text} %"
        return label, text

    def _fallback_label(self, row: int) -> str:
        """The label of a row known only from an error: made from its cells, if the import said how."""
        if self._cells is None or self._label_of is None:
            return ""
        cells = self._cells(row)
        return self._label_of(cells) if cells is not None else ""

    def as_list(self, errors: Iterable[Any] = (), warnings: Iterable[Any] = ()) -> list[dict[str, Any]]:
        """Every recorded row and every row with an error, in the order of the file, as plain data.

        A row with an error is an error, whatever was recorded for it. The
        notes of the import about a row (``warnings``) are added to its
        notes. An unchanged row is only number, label and outcome (and its
        notes, if it has any), to keep the report of a long list small.

        Args:
            errors: The errors of the report (``ImportIssue``); those without a row concern the file.
            warnings: The notes of the report (``ImportIssue``).
        """
        problems: dict[int, list[str]] = {}
        for issue in errors:
            if issue.row:
                problems.setdefault(issue.row, []).append(_issue_text(issue))
        hints: dict[int, list[str]] = {}
        for issue in warnings:
            if issue.row:
                hints.setdefault(issue.row, []).append(_issue_text(issue))
        rows: list[dict[str, Any]] = []
        for number in sorted(set(self.records) | set(problems)):
            record = self.records.get(number)
            notes = [*(record.notes if record is not None else []), *hints.get(number, [])]
            label = record.label if record is not None else self._fallback_label(number)
            if number in problems:
                rows.append(
                    {
                        "row": number,
                        "label": label,
                        "status": ERROR,
                        "changes": [],
                        "notes": notes,
                        "errors": problems[number],
                    }
                )
                continue
            assert record is not None
            entry: dict[str, Any] = {"row": number, "label": label, "status": record.outcome}
            if record.outcome == UNCHANGED:
                if notes:
                    entry["notes"] = notes
            else:
                entry.update(
                    {
                        "changes": [change.as_dict() for change in record.changes.values()],
                        "notes": notes,
                        "errors": [],
                    }
                )
            rows.append(entry)
        return rows


def _issue_text(issue: Any) -> str:
    """A problem of a row without the row: "Kaufpreis: „neun“ ist keine Zahl."."""
    return f"{issue.column}: {issue.message}" if issue.column else str(issue.message)


def count(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """How many rows have each outcome: ``{"new": 3, "changed": 1, "unchanged": 0, "error": 0}``."""
    counted = Counter(row["status"] for row in rows)
    return {outcome: counted.get(outcome, 0) for outcome in OUTCOMES}


def report_rows(log: RowLog, errors: Iterable[Any], warnings: Iterable[Any]) -> dict[str, Any]:
    """The keys every import report adds for the preview: ``rows`` and ``row_counts`` (IMP-011)."""
    rows = log.as_list(errors, warnings)
    return {"rows": rows, "row_counts": count(rows)}


def cells_by_number(table: Any) -> Callable[[int], list[Any] | None]:
    """The cells of a row of a table by the row's number in the file; the index is built when first needed."""
    index: dict[int, int] = {}

    def cells(number: int) -> list[Any] | None:
        if not index:
            index.update({row_number: position for position, row_number in enumerate(table.row_numbers)})
        position = index.get(number)
        return table.rows[position] if position is not None else None

    return cells


def label_from(mapping: dict[str, int | None], *keys: str) -> Callable[[list[Any]], str]:
    """A label made of the cells of some fields, e.g. ID and name: ``label_from(mapping, "inventory_number", "name")``."""
    from rentalars.core.tabular import cell_text

    def label_of(cells: list[Any]) -> str:
        parts = []
        for key in keys:
            index = mapping.get(key)
            if index is not None and index < len(cells):
                text = cell_text(cells[index])
                if text:
                    parts.append(text)
        return " ".join(parts)

    return label_of


def snapshot(instance: Any, names: Iterable[str]) -> dict[str, Any]:
    """The values of some fields of a record by field name – a foreign key as its ID – to compare and to show."""
    return {name: getattr(instance, instance._meta.get_field(name).attname) for name in names}
