# SPDX-License-Identifier: GPL-3.0-or-later
"""The changes of custom values in the history of an item (MAT-073; MAT-025).

Every value is a record of its own (``CustomFieldValue``) whose change log
entries name the item as their parent. The history of the item shows them
as "Eigenes Feld „Firmware“: 1.2 → 1.3". The value of a field visible only
with the right to see purchase prices is kept in a column the change log
hides from readers without it (``audit_sensitive``, AUT-019): they see that
the field changed, not how.

MAT-071: a field marked sensitive *after* items had values
hides all its values from these readers – also the old ones the log noted
in the open column. What decides is the field's mark now, not the column of
the entry; a value whose field is gone counts as sensitive if it ever was.
The entries written when the mark moved the values from one column to the
other change no value and are shown to nobody.
"""

from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.history import FieldChange
from rentalars.core.models import AuditAction, AuditLogEntry
from rentalars.customfields.models import CustomField, CustomFieldValue

#: The columns of a value in the change log.
_COLUMNS = ("value", "protected_value")


def value_entries(item: Any, *, limit: int = 200) -> list[AuditLogEntry]:
    """The newest change log entries of the item's custom values."""
    content_type = ContentType.objects.get_for_model(CustomFieldValue)
    item_type = ContentType.objects.get_for_model(item, for_concrete_model=True)
    return list(
        AuditLogEntry.objects.filter(
            content_type=content_type, parent_content_type=item_type, parent_object_id=str(item.pk)
        )
        .select_related("actor", "content_type")
        .order_by("-timestamp", "-pk")[:limit]
    )


def _pairs(entry: AuditLogEntry) -> dict[str, list[Any]]:
    """The logged ``[old, new]`` of the value columns of an entry."""
    changes = entry.changes if isinstance(entry.changes, dict) else {}
    return {
        column: values for column in _COLUMNS if isinstance(values := changes.get(column), list) and len(values) == 2
    }


def is_column_move(entry: AuditLogEntry) -> bool:
    """Whether an entry only moved a value to the other column – the field's mark "sensitive" changed (MAT-071)."""
    if entry.action != AuditAction.UPDATED:
        return False
    pairs = _pairs(entry)
    if set(pairs) != set(_COLUMNS):
        return False
    old = pairs["value"][0] or pairs["protected_value"][0] or ""
    new = pairs["value"][1] or pairs["protected_value"][1] or ""
    return old == new


def _texts(entry: AuditLogEntry, rights: Rights, *, hide_all: bool = False) -> tuple[str, str, bool]:
    """Old and new text of an entry, and whether its values are hidden from the reader.

    ``hide_all``: the field is sensitive now and the reader may not see such values – every column is hidden
    (MAT-071).
    """
    sensitive = CustomFieldValue.audit_sensitive
    old = new = ""
    hidden = False
    for column, values in _pairs(entry).items():
        if hide_all or (column in sensitive and not rights.has(sensitive[column])):
            hidden = True
            continue
        old = old or (values[0] or "")
        new = new or (values[1] or "")
    return old, new, hidden


def ever_protected(object_ids: set[str]) -> set[str]:
    """Of these values (IDs as the log stores them), those the log ever noted in the protected column."""
    if not object_ids:
        return set()
    content_type = ContentType.objects.get_for_model(CustomFieldValue)
    found = set()
    for object_id, changes in AuditLogEntry.objects.filter(
        content_type=content_type, object_id__in=sorted(object_ids)
    ).values_list("object_id", "changes"):
        values = changes.get("protected_value") if isinstance(changes, dict) else None
        if isinstance(values, list) and any(values):
            found.add(object_id)
    return found


def value_rows(item: Any, rights: Rights, *, limit: int = 200) -> list[Any]:
    """The changes of the item's custom values as rows of its history (``material.history.ItemHistoryRow``)."""
    from rentalars.core.history import actor_text
    from rentalars.material.history import ItemHistoryRow

    entries = value_entries(item, limit=limit)
    if not entries:
        return []
    ids = {int(entry.object_id) for entry in entries if str(entry.object_id).isdigit()}
    fields_of = {value.pk: value.field for value in CustomFieldValue.objects.filter(pk__in=ids).select_related("field")}
    may_see_sensitive = rights.has(SpecialRight.PURCHASE_PRICES)
    # MAT-071: values whose field is gone count as sensitive if the log ever kept them protected.
    gone = {
        entry.object_id
        for entry in entries
        if not str(entry.object_id).isdigit() or int(entry.object_id) not in fields_of
    }
    protected_once = set() if may_see_sensitive else ever_protected(gone)
    rows = []
    for entry in entries:
        field: CustomField | None = fields_of.get(int(entry.object_id)) if str(entry.object_id).isdigit() else None
        name = field.name if field is not None else _name_from(entry.object_repr, item)
        if is_column_move(entry):
            continue  # only the column moved (the field became sensitive or no longer is) – no value changed
        sensitive_now = field.is_sensitive if field is not None else entry.object_id in protected_once
        old, new, hidden = _texts(entry, rights, hide_all=sensitive_now and not may_see_sensitive)
        if entry.action == AuditAction.DELETED:
            summary = _("Custom field “%(field)s” deleted with its value") % {"field": name}
        elif entry.action == AuditAction.CREATED or (not old and new and not hidden):
            summary = _("Custom field “%(field)s” filled in") % {"field": name}
        elif old and not new and not hidden:
            summary = _("Custom field “%(field)s” emptied") % {"field": name}
        else:
            summary = _("Custom field “%(field)s” changed") % {"field": name}
        changes = []
        if entry.action != AuditAction.DELETED:
            before = "–" if entry.action == AuditAction.CREATED else _shown(old, field, hidden, "…")
            after = _shown(new, field, hidden, _("(not visible)"))
            changes.append(FieldChange(name="value", label=name, old=before, new=after))
        rows.append(
            ItemHistoryRow(
                timestamp=entry.timestamp,
                kind="change",
                summary=summary,
                user=actor_text(entry.actor_label),
                changes=changes,
            )
        )
    return rows


def _shown(text: str, field: CustomField | None, hidden: bool, hidden_text: str) -> str:
    """A value of the history for people; an empty one where part of the change is hidden stands for "not visible"."""
    if not text:
        return hidden_text if hidden else "–"
    return (field.display_value(text) or text) if field is not None else text


def _name_from(object_repr: str, item: Any) -> str:
    """The field's name from the stored name of a deleted value, "0042 Firmware"."""
    prefix = f"{item.display_id} "
    return object_repr[len(prefix) :] if object_repr.startswith(prefix) else object_repr
