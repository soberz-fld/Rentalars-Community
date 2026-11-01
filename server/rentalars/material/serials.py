# SPDX-License-Identifier: GPL-3.0-or-later
"""Serial numbers that exist already: a warning, never an error (duplicate serial numbers; MAT-084,; MAT-004, MAT-050).

A serial number may legitimately occur twice – the same number on the models of two manufacturers –, so nothing
here forbids it and there is no unique constraint. What the module does is look: a serial number that another item
has already (retired and sold items count – the number was in use), or one that occurs twice in the same entry,
gives a warning text. Forms show it before saving and let the user confirm with "create anyway"; the API and the
import add the texts to their answer.

The comparison is case-insensitive and ignores surrounding spaces. The same number at an item of the same model is
the stronger case and says so.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from django.db.models import Q
from django.utils.translation import gettext as _

from rentalars.material.models import ARCHIVED_STATUSES, ItemStatus, MaterialItem

#: How many existing items one warning names; the rest is counted.
ITEMS_NAMED = 3

#: How many serial numbers one query looks for (the query has one alternative per number).
_CHUNK = 100

#: The name of the field the confirmation travels in.
CONFIRM_FIELD = "confirm_serials"


def key_of(serial: str) -> str:
    """The form a serial number is compared in: stripped and case-folded."""
    return str(serial or "").strip().casefold()


@dataclass(frozen=True)
class SerialClash:
    """A serial number an existing item has already.

    Attributes:
        serial: The serial number as typed.
        items: The existing items that have it, the ones of the same model first, then by ID.
        same_model: Whether one of them is an item of the same model – the stronger case.
    """

    serial: str
    items: tuple[MaterialItem, ...]
    same_model: bool

    @property
    def text(self) -> str:
        """The warning for this clash, with the item and its model; "retired", "sold" or "lost" is added."""
        named = [_item_text(item) for item in self.items[:ITEMS_NAMED]]
        rest = len(self.items) - len(named)
        listing = ", ".join(named)
        if rest > 0:
            listing += " " + _("and %(count)d more") % {"count": rest}
        if self.same_model:
            return _("The serial number %(serial)s already exists for the same model: %(items)s.") % {
                "serial": self.serial,
                "items": listing,
            }
        return _("The serial number %(serial)s already exists: %(items)s.") % {"serial": self.serial, "items": listing}


def _item_text(item: MaterialItem) -> str:
    """The item as a warning names it: ID and model; one that is retired, sold or lost says so (it counts all the same)."""
    model = item.material_model.name
    if item.status in ARCHIVED_STATUSES:
        return _("item %(id)s (model %(model)s, %(status)s)") % {
            "id": item.display_id,
            "model": model,
            "status": ItemStatus(item.status).label,
        }
    return _("item %(id)s (model %(model)s)") % {"id": item.display_id, "model": model}


def _existing_by_key(serials: Iterable[str]) -> dict[str, list[MaterialItem]]:
    """The items that have one of these serial numbers, grouped by number (see :func:`key_of`), in ID order.

    The database only fetches candidates: ``iexact`` knows the letters of its collation (MariaDB treats "Muller"
    and "Müller" as the same) or only ASCII (SQLite). So the query is a superset – ``iexact`` of the number and
    the exact spellings of it in lower case, upper case and case-folded – and the decision is made here, with
    one normalisation (:func:`key_of`) on both sides, so that every database answers alike.
    """
    found: dict[str, list[MaterialItem]] = {}
    typed: dict[str, set[str]] = {}
    for serial in serials:
        text = str(serial or "").strip()
        typed.setdefault(key_of(text), set()).update({text, text.upper(), text.lower(), text.casefold()})
    keys = sorted(typed)
    for start in range(0, len(keys), _CHUNK):
        chunk = keys[start : start + _CHUNK]
        spellings: set[str] = set()
        condition = Q()
        for key in chunk:
            spellings.update(typed[key])
            condition |= Q(serial_number__iexact=key)
        condition |= Q(serial_number__in=spellings)
        wanted = set(chunk)
        for item in (
            MaterialItem.objects.filter(condition).select_related("material_model").order_by("inventory_number")
        ):
            found_key = key_of(item.serial_number)
            if found_key in wanted:
                found.setdefault(found_key, []).append(item)
    return found


def _clash(serial: str, model_id: int | None, existing: Sequence[MaterialItem]) -> SerialClash | None:
    """The clash of ``serial`` at a model with the ``existing`` items that have it; the same model's items first."""
    if not existing:
        return None
    same = [item for item in existing if model_id is not None and item.material_model_id == model_id]
    ordered = same + [item for item in existing if item not in same]
    return SerialClash(serial=serial, items=tuple(ordered), same_model=bool(same))


def find_clashes(entries: Iterable[tuple[str, int | None]], *, exclude: Iterable[int] = ()) -> list[SerialClash]:
    """The serial numbers of ``entries`` that existing items have already.

    Args:
        entries: ``(serial number, model ID)`` per new or changed item; the model ID is ``None`` for a model
            that does not exist yet (then there can be no clash with the same model).
        exclude: Items that do not count – the item being edited.

    Returns:
        One clash per serial number and model, in the order of the entries; empty serial numbers are skipped.
    """
    wanted = [(str(serial or "").strip(), model_id) for serial, model_id in entries]
    wanted = [(serial, model_id) for serial, model_id in wanted if serial]
    if not wanted:
        return []
    excluded = set(exclude)
    by_key = _existing_by_key(serial for serial, _model in wanted)
    clashes: list[SerialClash] = []
    seen: set[tuple[str, bool]] = set()
    for serial, model_id in wanted:
        existing = [item for item in by_key.get(key_of(serial), []) if item.pk not in excluded]
        clash = _clash(serial, model_id, existing)
        if clash is None or (key_of(serial), clash.same_model) in seen:
            continue
        seen.add((key_of(serial), clash.same_model))
        clashes.append(clash)
    return clashes


def clashes_of_items(items: Sequence[MaterialItem]) -> dict[int, SerialClash]:
    """The clash of each saved item whose serial number another item has too – one query for all (the import).

    Items saved together clash with each other: both name the other.
    """
    with_serial = [item for item in items if item.serial_number]
    by_key = _existing_by_key(item.serial_number for item in with_serial)
    out: dict[int, SerialClash] = {}
    for item in with_serial:
        others = [other for other in by_key.get(key_of(item.serial_number), []) if other.pk != item.pk]
        clash = _clash(item.serial_number, item.material_model_id, others)
        if clash is not None:
            out[item.pk] = clash
    return out


def repeated_serials(serials: Iterable[str]) -> list[str]:
    """The serial numbers that occur more than once in ``serials`` (each named once, as first typed)."""
    first: dict[str, str] = {}
    count: dict[str, int] = {}
    for serial in serials:
        text = str(serial or "").strip()
        if not text:
            continue
        first.setdefault(key_of(text), text)
        count[key_of(text)] = count.get(key_of(text), 0) + 1
    return [first[key] for key, number in count.items() if number > 1]


def entry_warnings(entries: Sequence[tuple[str, int | None]], *, exclude: Iterable[int] = ()) -> list[str]:
    """All warning texts for the serial numbers of one entry: repeated inside it, and existing already.

    Args:
        entries: ``(serial number, model ID)`` per item, in one submission – a form, a purchase, one API call.
        exclude: Items that do not count (the item being edited).
    """
    warnings = [
        _("The serial number %(serial)s occurs more than once in this entry.") % {"serial": serial}
        for serial in repeated_serials(serial for serial, _model in entries)
    ]
    warnings.extend(clash.text for clash in find_clashes(entries, exclude=exclude))
    return warnings


def for_item(item: MaterialItem) -> list[str]:
    """The warning for the serial number of one saved item: other items have it (MAT-004)."""
    if not item.serial_number:
        return []
    return [clash.text for clash in find_clashes([(item.serial_number, item.material_model_id)], exclude=[item.pk])]


def for_items(items: Sequence[MaterialItem]) -> dict[int, list[str]]:
    """The warnings per saved item ID, for items just created together: clashes with others, and among them."""
    return {pk: [clash.text] for pk, clash in clashes_of_items(items).items()}


def token_of(warnings: Sequence[str]) -> str:
    """A short mark of what the user was warned about; the confirmation box carries it (see :func:`confirmed`)."""
    return hashlib.sha1("\n".join(sorted(warnings)).encode(), usedforsecurity=False).hexdigest()[:16]


def confirmed(post: Mapping[str, str], warnings: Sequence[str]) -> bool:
    """Whether the user confirmed exactly these warnings.

    The box carries the mark of the warnings it was shown with; if the serial numbers changed after the
    warning and other ones clash, the old tick does not count.
    """
    return not warnings or post.get(CONFIRM_FIELD, "") == token_of(warnings)
