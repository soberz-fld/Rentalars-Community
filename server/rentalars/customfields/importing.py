# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom values in the material import (MAT-073; IMP-002 ff.).

A column whose heading is the name of a custom field – as the item list's
CSV file writes it – fills that field of the items of its rows. It needs no
assignment in the column mapping: a column assigned to one of the usual
fields stays that field.

For each row the values are checked against the fieldset of the item's
material model, like a value typed in the item's form: a field the fieldset
does not have, a value that does not fit (type, options, pattern) or a
unique value another item has is reported as an error of the row – and, as
with every error, nothing is imported. An empty cell empties the value (the
file is right, as for the other columns); for a field outside the fieldset
it is ignored. Required values are not demanded: the import may create
items without them, as creating several items at once does.

A column of a field visible only with the right to see purchase prices is
left out for who lacks the right, with a warning.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights
from rentalars.core.import_rows import NEW, UNCHANGED
from rentalars.core.tabular import ImportIssue, cell_text, normalise
from rentalars.customfields import services
from rentalars.customfields.models import CustomField


class CustomColumns:
    """The columns of a file that hold custom values, and what writing them did."""

    def __init__(self, headers: list[str], mapping: dict[str, int | None], rights: Rights | None) -> None:
        taken = {index for index in mapping.values() if index is not None}
        by_name = {normalise(field.name): field for field in CustomField.objects.all()}
        self.columns: dict[int, CustomField] = {}
        self.warnings: list[ImportIssue] = []
        for index, heading in enumerate(headers):
            field = by_name.get(normalise(str(heading or "")))
            if field is None or index in taken:
                continue
            if rights is not None and not field.visible_to(rights):
                self.warnings.append(
                    ImportIssue(
                        None,
                        field.name,
                        _(
                            "The column is not imported: the values of this field need the right to see purchase "
                            "prices."
                        ),
                    )
                )
                continue
            self.columns[index] = field
        self.rights = rights

    def __bool__(self) -> bool:
        return bool(self.columns)

    def apply(self, writer: Any, row_number: int, cells: list[Any] | None, item: Any, outcome: str) -> None:
        """Check and store the custom values of one row for its item, after the item was saved.

        Errors go to the report; changes to the row's preview (IMP-011), where
        a row counted as unchanged becomes a changed one.
        """
        if not self.columns or cells is None:
            return
        report = writer.report
        entries = {entry.field_id: entry for entry in services.entries_of(item.material_model)}
        stored = services.stored_values(item)
        values: dict[CustomField, str] = {}
        for index, field in self.columns.items():
            raw = cells[index] if index < len(cells) else None
            if isinstance(raw, str):
                raw = cell_text(raw)
            try:
                text = field.clean_value(raw)
            except ValidationError as error:
                report.errors.append(ImportIssue(row_number, field.name, " ".join(error.messages)))
                continue
            if field.pk not in entries:
                if text and text != stored.get(field.pk, ""):
                    report.errors.append(
                        ImportIssue(
                            row_number,
                            field.name,
                            _("The material model “%(model)s” has no custom field “%(field)s” in its fieldset.")
                            % {"model": item.material_model.name, "field": field.name},
                        )
                    )
                continue
            try:
                services.check_unique(field, text, item=item, rights=self.rights)
            except ValidationError as error:
                report.errors.append(ImportIssue(row_number, field.name, " ".join(error.messages)))
                continue
            values[field] = text
        changes = services.store_values(item, values)
        if not changes or outcome == NEW:
            return
        if outcome == UNCHANGED:
            # The preview turns the row into a changed one with its first change (``RowLog.change``).
            writer.unchanged_items.discard(item.inventory_number)
            report.items_unchanged -= 1
            report.items_updated += 1
        for field, old, new in changes:
            writer.log.change(
                row_number,
                None,
                "value",
                field.display_value(old),
                field.display_value(new),
                key=f"custom.{field.pk}",
                label=_("%(field)s (custom field)") % {"field": field.name},
                sensitive="purchase_prices" if field.is_sensitive else "",
            )
