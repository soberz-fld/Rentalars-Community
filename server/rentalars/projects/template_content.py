# SPDX-License-Identifier: GPL-3.0-or-later
"""Edit the content of a project template (PRJ-135).

A template is *made* ("save as template", PRJ-076) and can be renamed. Its content – the groups, lines,
crew places, vehicle bookings, phases, open items and notes – is a copy that can be changed by changing a
project and saving it again. This module changes the content itself, one entry at a time, for the pages
(``template_content_views``) and the API (``/project-templates/{id}/…``).

The content is the JSON of :func:`rentalars.projects.project_templates.capture`. Entries are addressed by a ``"key"``
(a number that is unique within its section): groups and lines have one, the other sections get theirs when a
template is opened for editing (:func:`ensure_keys`), so that a page that is a little out of date never changes another
entry than the one it shows. The open items are plain texts and are addressed by their place together with their text.

What is kept intact on every change:

* the groups stay in tree order, every parent before its subgroups, at most :data:`MAX_DEPTH` levels (PRJ-037);
* a line names an existing group or none, an alternative names a line or group that exists and is not an alternative
  itself (PRJ-083); a thing that an alternative replaced and that is deleted turns the alternative into an optional one;
* a crew place or vehicle booking names its phase by the phase's place in the list (PRJ-080) – deleting or moving a phase
  moves these numbers along;
* times are relative to the start of the project, or – ``"anchor": "end"`` – to its end (PRJ-095).

Prices (a group's discount or flat price, the price of a free line) are only written by who may see prices; for anybody
else they stay as they are.

Everything is checked as it is written, so that applying the template (``project_templates.apply_template``) never meets
content it cannot read. Products and job functions that are gone or deactivated *later* are still left out then, and named.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.audit import record_event
from rentalars.personnel.models import JobFunction
from rentalars.products.models import Product, ProductKind
from rentalars.projects.grouptree import MAX_DEPTH
from rentalars.projects.models import GroupKind, LineVariant, PhaseKind, ProjectTemplate

GROUPS = "groups"
LINES = "lines"
CREW = "crew"
VEHICLES = "vehicles"
PHASES = "phases"
OPEN_ITEMS = "open_items"

#: The sections whose entries are dictionaries with a ``"key"``.
KEYED = (GROUPS, LINES, CREW, VEHICLES, PHASES)
SECTIONS = (*KEYED, OPEN_ITEMS)

#: The top-level keys of a content (the lists above, notes, rental days and the length of the project it was made from).
TOP_LEVEL = frozenset({"version", "length_seconds", "notes", "rental_days", "next_keys", *SECTIONS})

#: Written into the content; the version of the format (``project_templates.CONTENT_VERSION``).
VERSION = 2

_PRICE_FIELDS = {GROUPS: ("discount_percent", "discount_amount", "flat_price"), LINES: ("unit_price",)}
_MAX_ENTRIES = 500
_HOUR = 3600


# --- Small readers -------------------------------------------------------------------------------------------------


class _Errors:
    """Collects the problems of one entry by field name, then raises them together."""

    def __init__(self) -> None:
        self.found: dict[str, list[str]] = {}

    def add(self, field: str, message: str) -> None:
        self.found.setdefault(field, []).append(str(message))

    def raise_if_any(self) -> None:
        if self.found:
            raise ValidationError(self.found)


def _text(data: dict[str, Any], name: str, errors: _Errors, *, maximum: int, required: bool = False) -> str:
    value = data.get(name, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        errors.add(name, _("Enter text."))
        return ""
    value = value.strip()
    if required and not value:
        errors.add(name, _("This field is required."))
    if len(value) > maximum:
        errors.add(name, _("Use at most %(count)d characters.") % {"count": maximum})
    return value


def _decimal(
    data: dict[str, Any],
    name: str,
    errors: _Errors,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
    places: int = 2,
    required: bool = False,
) -> str | None:
    """A decimal as the string the content keeps; ``None`` if empty."""
    value = data.get(name)
    if value is None or value == "":
        if required:
            errors.add(name, _("This field is required."))
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        errors.add(name, _("Enter a number."))
        return None
    try:
        number = Decimal(str(value).replace(",", ".").strip())
    except InvalidOperation:
        errors.add(name, _("Enter a number."))
        return None
    if not number.is_finite():
        errors.add(name, _("Enter a number."))
        return None
    number = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if minimum is not None and number < minimum:
        errors.add(name, _("The value must be at least %(minimum)s.") % {"minimum": minimum})
    if maximum is not None and number > maximum:
        errors.add(name, _("The value must be at most %(maximum)s.") % {"maximum": maximum})
    return format(number, "f")


def _integer(data: dict[str, Any], name: str, errors: _Errors, *, minimum: int = 1, maximum: int = 999) -> int | None:
    value = data.get(name)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        errors.add(name, _("Enter a whole number."))
        return None
    try:
        number = int(str(value).strip())
    except ValueError:
        errors.add(name, _("Enter a whole number."))
        return None
    if not minimum <= number <= maximum:
        errors.add(
            name, _("Enter a number from %(minimum)d to %(maximum)d.") % {"minimum": minimum, "maximum": maximum}
        )
        return None
    return number


def _flag(data: dict[str, Any], name: str) -> bool:
    value = data.get(name, False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _reference(data: dict[str, Any], name: str, errors: _Errors) -> int | None:
    """An id or a key: a whole number, or ``None``."""
    value = data.get(name)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        errors.add(name, _("Enter a whole number."))
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        errors.add(name, _("Enter a whole number."))
        return None


# --- Times ----------------------------------------------------------------------------------------------------------


def offsets(data: dict[str, Any], errors: _Errors, *, always_own: bool = False) -> dict[str, Any]:
    """The period of an entry: ``{"own_period": False}`` for the project's, else seconds from its start or end."""
    own = True if always_own else _flag(data, "own_period")
    if not own:
        return {"own_period": False}
    anchor = data.get("anchor")
    if anchor not in (None, "", "start", "end"):
        errors.add("anchor", _("Choose the start or the end of the project."))
        anchor = None
    seconds: list[float] = []
    for name in ("start", "end"):
        value = data.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            errors.add(name, _("Enter a number."))
            seconds.append(0)
            continue
        try:
            number = float(str(value).replace(",", "."))
        except ValueError:
            errors.add(name, _("Enter a number."))
            seconds.append(0)
            continue
        if number != number or abs(number) > 3650 * 24 * _HOUR:  # NaN, or more than ten years
            errors.add(name, _("This is too far from the project."))
            number = 0
        seconds.append(int(number) if float(number).is_integer() else number)
    start, end = seconds
    if not errors.found.get("start") and not errors.found.get("end") and end <= start:
        errors.add("end", _("The end must be after the start."))
    result: dict[str, Any] = {"own_period": True, "start": start, "end": end}
    if anchor == "end":
        result["anchor"] = "end"
    return result


def describe_period(entry: dict[str, Any]) -> str:
    """The period of an entry in words, for the lists: "whole project", "from 2 h to 8 h after the start"."""
    if not entry.get("own_period"):
        return str(_("whole project"))

    def hours(seconds: float) -> str:
        value = (Decimal(str(seconds)) / _HOUR).quantize(Decimal("0.01")).normalize()
        return format(value, "f")

    start, end = entry.get("start", 0), entry.get("end", 0)
    if entry.get("anchor") == "end":
        return str(_("from %(start)s h to %(end)s h before the end") % {"start": hours(-start), "end": hours(-end)})
    return str(_("from %(start)s h to %(end)s h after the start") % {"start": hours(start), "end": hours(end)})


# --- The entries ----------------------------------------------------------------------------------------------------


def _known(
    model: Any, pk: int | None, errors: _Errors, name: str, *, test: Callable[[Any], bool] | None = None
) -> None:
    if pk is None:
        return
    found = model.objects.filter(pk=pk).first()
    if found is None or (test is not None and not test(found)):
        errors.add(name, _("This does not exist."))


def _group(data: dict[str, Any], rights_prices: bool, old: dict[str, Any] | None) -> dict[str, Any]:
    errors = _Errors()
    kind = data.get("kind") or GroupKind.NORMAL.value
    if kind not in GroupKind.values:
        errors.add("kind", _("Choose one of the offered values."))
        kind = GroupKind.NORMAL.value
    entry: dict[str, Any] = {
        "key": data.get("key"),
        "parent": _reference(data, "parent", errors),
        "name": _text(data, "name", errors, maximum=120, required=True),
        "description": _text(data, "description", errors, maximum=5000),
        "kind": kind,
        "alternative_to": _reference(data, "alternative_to", errors),
        "rental_days": _integer(data, "rental_days", errors),
    }
    if rights_prices:
        entry["discount_percent"] = _decimal(
            data, "discount_percent", errors, minimum=Decimal("0"), maximum=Decimal("100")
        )
        entry["discount_amount"] = _decimal(
            data, "discount_amount", errors, minimum=Decimal("0"), maximum=Decimal("99999999")
        )
        entry["flat_price"] = _decimal(data, "flat_price", errors, minimum=Decimal("0"), maximum=Decimal("99999999"))
        if sum(entry[name] is not None for name in _PRICE_FIELDS[GROUPS]) > 1:
            errors.add("flat_price", _("Use only one of: discount in percent, discount as amount, flat price."))
    else:
        for name in _PRICE_FIELDS[GROUPS]:
            entry[name] = old.get(name) if old else None
    if entry["alternative_to"] is not None and kind != GroupKind.ALTERNATIVE.value:
        errors.add("alternative_to", _("Only an alternative group can replace another one."))
    errors.raise_if_any()
    return entry


def _line(data: dict[str, Any], rights_prices: bool, old: dict[str, Any] | None) -> dict[str, Any]:
    from rentalars.material.models import MaterialModel
    from rentalars.projects import services

    errors = _Errors()
    product: Product | None = None
    is_text = _flag(data, "is_text")
    product_id = _reference(data, "product", errors)
    entry: dict[str, Any] = {
        "key": data.get("key"),
        "group": _reference(data, "group", errors),
        "product": None if is_text else product_id,
        "title": "",
        "unit_price": None,
        "quantity": "1",
        "is_sale": False,
        "hours": None,
        "quantity_is_estimate": False,
        "rental_days": None,
        "note": _text(data, "note", errors, maximum=5000),
        "variant": "",
        "is_text": is_text,
        "alternative_to": None,
        "preferred_model": None,
        "own_period": False,
    }
    if is_text:
        entry["title"] = _text(data, "title", errors, maximum=200, required=True)
        entry["quantity"] = "1.00"
        errors.raise_if_any()
        return entry
    if product_id is not None:
        found = product = Product.objects.filter(pk=product_id).first()
        if found is None:
            errors.add("product", _("This product does not exist."))
        elif not services.plannable_as_material(found):
            errors.add("product", _("A service or a vehicle is not planned as material."))
        entry["title"] = ""
        entry["is_sale"] = _flag(data, "is_sale")
        if found is not None and entry["is_sale"] and found.sale_price is None:
            errors.add("is_sale", _("This product has no sale price and cannot be sold."))
        elif (
            found is not None
            and not entry["is_sale"]
            and found.price is None
            and not found.is_percent_surcharge
            and found.kind != ProductKind.SALE
        ):
            errors.add("is_sale", _("This product has no rental price and can only be sold."))
    else:
        entry["title"] = _text(data, "title", errors, maximum=200, required=True)
        entry["is_sale"] = False
        if rights_prices:
            entry["unit_price"] = _decimal(
                data, "unit_price", errors, minimum=Decimal("0"), maximum=Decimal("99999999")
            )
        else:
            entry["unit_price"] = old.get("unit_price") if old else None
    entry["quantity"] = (
        _decimal(data, "quantity", errors, minimum=Decimal("0.01"), maximum=Decimal("99999999")) or "1.00"
    )
    whole = Decimal(entry["quantity"]) == Decimal(entry["quantity"]).to_integral_value()
    if (
        product is not None
        and (product.tracks_stock or product.is_kit)
        and not whole
        and "quantity" not in errors.found
    ):
        errors.add("quantity", _("This product is planned in whole pieces."))
    entry["hours"] = _decimal(data, "hours", errors, minimum=Decimal("0"), maximum=Decimal("999999"))
    entry["quantity_is_estimate"] = _flag(data, "quantity_is_estimate")
    entry["rental_days"] = _integer(data, "rental_days", errors)
    variant = data.get("variant") or ""
    if variant not in LineVariant.values:
        errors.add("variant", _("Choose one of the offered values."))
        variant = ""
    entry["variant"] = variant
    entry["alternative_to"] = _reference(data, "alternative_to", errors)
    if entry["alternative_to"] is not None and variant != LineVariant.ALTERNATIVE.value:
        errors.add("alternative_to", _("Only an alternative line can replace another one."))
    entry["preferred_model"] = _reference(data, "preferred_model", errors)
    if entry["preferred_model"] is not None:
        model = MaterialModel.objects.filter(pk=entry["preferred_model"]).first()
        if model is None or product_id is None or model.product_id != product_id:
            errors.add("preferred_model", _("This model does not belong to the product."))
    entry.update(offsets(data, errors))
    errors.raise_if_any()
    return entry


def _crew(data: dict[str, Any], rights_prices: bool, old: dict[str, Any] | None) -> dict[str, Any]:
    errors = _Errors()
    function = _reference(data, "job_function", errors)
    if function is None:
        errors.add("job_function", _("This field is required."))
    else:
        _known(JobFunction, function, errors, "job_function")
    entry: dict[str, Any] = {
        "key": data.get("key"),
        "job_function": function,
        "planned_hours": _decimal(data, "planned_hours", errors, minimum=Decimal("0"), maximum=Decimal("99999.99")),
        "meeting_point": _text(data, "meeting_point", errors, maximum=200),
        "note": _text(data, "note", errors, maximum=5000),
        "phase": _integer(data, "phase", errors, minimum=0, maximum=_MAX_ENTRIES),
    }
    entry.update(offsets(data, errors))
    errors.raise_if_any()
    return entry


def _vehicle(data: dict[str, Any], rights_prices: bool, old: dict[str, Any] | None) -> dict[str, Any]:
    errors = _Errors()
    product = _reference(data, "product", errors)
    if product is None:
        errors.add("product", _("This field is required."))
    else:
        _known(Product, product, errors, "product", test=lambda found: found.is_vehicle)
    entry: dict[str, Any] = {
        "key": data.get("key"),
        "product": product,
        "title": _text(data, "title", errors, maximum=200),
        "note": _text(data, "note", errors, maximum=5000),
        "only_trip_days": _flag(data, "only_trip_days"),
        "phase": _integer(data, "phase", errors, minimum=0, maximum=_MAX_ENTRIES),
    }
    entry.update(offsets(data, errors))
    errors.raise_if_any()
    return entry


def _phase(data: dict[str, Any], rights_prices: bool, old: dict[str, Any] | None) -> dict[str, Any]:
    from rentalars.customers.models import Venue

    errors = _Errors()
    kind = data.get("kind") or PhaseKind.SETUP.value
    if kind not in PhaseKind.values:
        errors.add("kind", _("Choose one of the offered values."))
        kind = PhaseKind.SETUP.value
    site = _reference(data, "venue_site", errors)
    _known(Venue, site, errors, "venue_site")
    entry: dict[str, Any] = {
        "key": data.get("key"),
        "kind": kind,
        "title": _text(data, "title", errors, maximum=120),
        "location": _text(data, "location", errors, maximum=250),
        "notes": _text(data, "notes", errors, maximum=5000),
        "venue_site": site,
    }
    entry.update(offsets(data, errors, always_own=True))
    errors.raise_if_any()
    return entry


_NORMALIZE: dict[str, Callable[[dict[str, Any], bool, dict[str, Any] | None], dict[str, Any]]] = {
    GROUPS: _group,
    LINES: _line,
    CREW: _crew,
    VEHICLES: _vehicle,
    PHASES: _phase,
}


def normalize_entry(
    section: str, data: dict[str, Any], *, prices: bool, old: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The entry of ``section`` in the form the content keeps, or a ``ValidationError`` naming the fields.

    Args:
        section: One of :data:`KEYED`.
        data: What was entered (strings from a form or JSON values).
        prices: Whether whoever writes may see prices; if not, price fields are taken from ``old``.
        old: The entry that is changed, if any.
    """
    if not isinstance(data, dict):
        raise ValidationError(_("An entry is a set of fields."))
    key = data.get("key")
    if key is not None and (isinstance(key, bool) or not isinstance(key, int) or key < 1):
        raise ValidationError({"key": [str(_("Enter a whole number."))]})
    return _NORMALIZE[section](data, prices, old)


def _open_item(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({"text": [str(_("This field is required."))]})
    text = value.strip()
    if len(text) > 250:
        raise ValidationError({"text": [str(_("Use at most %(count)d characters.") % {"count": 250})]})
    return text


# --- Keys and references --------------------------------------------------------------------------------------------


def _take_key(content: dict[str, Any], section: str) -> int:
    """The next key of a section.

    Keys are never given twice, not even after the last entry was deleted: a page that still shows the deleted entry must
    not change a new one.
    """
    counters = content.setdefault("next_keys", {})
    used = (entry["key"] for entry in content[section] if isinstance(entry.get("key"), int))
    key = max(counters.get(section, 1), max(used, default=0) + 1)
    counters[section] = key + 1
    return key


def ensure_keys(content: dict[str, Any]) -> bool:
    """Give every entry of every section a key (and every section a list); ``True`` if something was added."""
    changed = False
    for section in SECTIONS:
        if not isinstance(content.get(section), list):
            content[section] = []
            changed = True
    content.setdefault("version", VERSION)
    for section in KEYED:
        entries = content[section]
        used: set[int] = set()
        for entry in entries:
            key = entry.get("key")
            if isinstance(key, int) and key not in used:
                used.add(key)
            else:
                entry["key"] = None
        counters = content.get("next_keys")
        if not isinstance(counters, dict):
            counters = content["next_keys"] = {}
            changed = True
        before = counters.get(section)
        nxt = max(max(used, default=0) + 1, before if isinstance(before, int) and not isinstance(before, bool) else 1)
        for entry in entries:
            if entry["key"] is None:
                entry["key"] = nxt
                nxt += 1
                changed = True
        if before != nxt:
            counters[section] = nxt
            changed = True
    return changed


def index_of(content: dict[str, Any], section: str, key: int) -> int:
    """The place of the entry with ``key`` in its section.

    Raises:
        KeyError: There is no such entry (it was deleted meanwhile).
    """
    for index, entry in enumerate(content.get(section, [])):
        if entry.get("key") == key:
            return index
    raise KeyError(key)


def _group_depth(groups: dict[int, dict[str, Any]], key: int) -> int:
    depth, seen = 0, set()
    parent = groups[key].get("parent")
    while parent is not None and parent in groups and parent not in seen:
        seen.add(parent)
        depth += 1
        parent = groups[parent].get("parent")
    return depth


def tree_order(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The groups with every parent directly before its subgroups (depth first), siblings in their list order.

    A group whose parent does not exist, and the members of a circle, are kept as they are at the end – nothing is
    dropped or re-parented here; :func:`check_references` names them.
    """
    by_parent: dict[Any, list[dict[str, Any]]] = {}
    for entry in groups:
        by_parent.setdefault(entry.get("parent"), []).append(entry)
    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(parent: Any) -> None:
        for entry in by_parent.get(parent, []):
            if id(entry) not in seen:
                seen.add(id(entry))
                ordered.append(entry)
                walk(entry["key"])

    walk(None)
    for entry in groups:
        if id(entry) not in seen:
            seen.add(id(entry))
            ordered.append(entry)
    return ordered


def check_references(content: dict[str, Any]) -> None:
    """Every reference of the content points at something that is there.

    Raises:
        ValidationError: A group or line names a missing or impossible group, parent, alternative or phase.
    """
    errors = _Errors()
    groups = {entry["key"]: entry for entry in content[GROUPS]}
    lines = {entry["key"]: entry for entry in content[LINES]}
    for entry in content[GROUPS]:
        parent = entry.get("parent")
        if parent is not None and parent not in groups:
            errors.add("parent", _("The parent group does not exist."))
        elif parent == entry["key"]:
            errors.add("parent", _("A group cannot be its own parent."))
    for key in groups:
        seen: set[int] = set()
        walk: int | None = key
        while walk is not None and walk in groups:
            if walk in seen:
                errors.add("parent", _("The groups lead into a circle."))
                break
            seen.add(walk)
            walk = groups[walk].get("parent")
    if not errors.found:
        for key in groups:
            if _group_depth(groups, key) + 1 > MAX_DEPTH:
                errors.add("parent", _("Groups can be nested up to %(levels)d levels.") % {"levels": MAX_DEPTH})
                break
    for entry in content[GROUPS]:
        target = entry.get("alternative_to")
        if target is not None:
            if target not in groups or target == entry["key"]:
                errors.add("alternative_to", _("The group to replace does not exist."))
            elif groups[target].get("kind") == GroupKind.ALTERNATIVE.value:
                errors.add("alternative_to", _("An alternative cannot replace another alternative."))
    for entry in content[LINES]:
        group = entry.get("group")
        if group is not None and group not in groups:
            errors.add("group", _("The group does not exist."))
        target = entry.get("alternative_to")
        if target is not None:
            if target not in lines or target == entry["key"]:
                errors.add("alternative_to", _("The line to replace does not exist."))
            elif lines[target].get("variant") == LineVariant.ALTERNATIVE.value:
                errors.add("alternative_to", _("An alternative cannot replace another alternative."))
    count = len(content[PHASES])
    for section in (CREW, VEHICLES):
        for entry in content[section]:
            phase = entry.get("phase")
            if phase is not None and not 0 <= phase < count:
                errors.add("phase", _("The phase does not exist."))
    for section in SECTIONS:
        if len(content[section]) > _MAX_ENTRIES:
            errors.add(section, _("A template holds at most %(count)d entries per section.") % {"count": _MAX_ENTRIES})
    errors.raise_if_any()


# --- Whole content --------------------------------------------------------------------------------------------------


def normalize_content(raw: Any, *, prices: bool, old: dict[str, Any] | None = None) -> dict[str, Any]:
    """The content in its canonical form, checked as a whole (the API writes a template this way).

    Unknown top-level keys are refused, entries are read field by field (:func:`normalize_entry`), keys are kept or given,
    the groups are put in tree order, and all references are checked. Price fields are those of ``old`` (matched by key)
    unless ``prices``.

    Raises:
        ValidationError: By section and entry – ``{"lines": ["Entry 3: …"]}``.
    """
    if not isinstance(raw, dict):
        raise ValidationError({"content": [str(_("The content is a set of sections."))]})
    unknown = sorted(set(raw) - TOP_LEVEL)
    if unknown:
        raise ValidationError(
            {"content": [str(_("Unknown sections: %(names)s.") % {"names": ", ".join(map(str, unknown))})]}
        )
    problems: dict[str, list[str]] = {}
    out: dict[str, Any] = {"version": VERSION}
    notes = raw.get("notes", "")
    out["notes"] = notes.strip("\r\n ") if isinstance(notes, str) else ""
    if not isinstance(notes, str) and notes is not None:
        problems.setdefault("notes", []).append(str(_("Enter text.")))
    errors = _Errors()
    out["rental_days"] = _integer(raw, "rental_days", errors)
    length = raw.get("length_seconds", old.get("length_seconds") if old else 0)
    out["length_seconds"] = (
        length if isinstance(length, (int, float)) and not isinstance(length, bool) and length >= 0 else 0
    )
    for name, messages in errors.found.items():
        problems.setdefault(name, []).extend(messages)
    out["next_keys"] = {}
    for source in (old, raw):
        counters = source.get("next_keys") if isinstance(source, dict) else None
        for section, value in counters.items() if isinstance(counters, dict) else ():
            if section in KEYED and isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 10**9:
                out["next_keys"][section] = max(out["next_keys"].get(section, 1), value)
    old_by_key = {
        section: {entry.get("key"): entry for entry in (old or {}).get(section, []) if isinstance(entry, dict)}
        for section in KEYED
    }
    for section in KEYED:
        entries = raw.get(section, [])
        if not isinstance(entries, list):
            problems.setdefault(section, []).append(str(_("A section is a list.")))
            out[section] = []
            continue
        made: list[dict[str, Any]] = []
        for number, data in enumerate(entries, start=1):
            previous = old_by_key[section].get(data.get("key")) if isinstance(data, dict) else None
            try:
                made.append(normalize_entry(section, data, prices=prices, old=previous))
            except ValidationError as error:
                for field, messages in (
                    error.message_dict if hasattr(error, "error_dict") else {"": error.messages}
                ).items():
                    for message in messages:
                        problems.setdefault(section, []).append(
                            _("Entry %(number)d, %(field)s: %(message)s")
                            % {"number": number, "field": field or "–", "message": message}
                        )
        out[section] = made
    items = raw.get(OPEN_ITEMS, [])
    out[OPEN_ITEMS] = []
    if not isinstance(items, list):
        problems.setdefault(OPEN_ITEMS, []).append(str(_("A section is a list.")))
    else:
        for number, value in enumerate(items, start=1):
            try:
                out[OPEN_ITEMS].append(_open_item(value))
            except ValidationError as error:
                problems.setdefault(OPEN_ITEMS, []).append(
                    _("Entry %(number)d: %(message)s") % {"number": number, "message": " ".join(error.messages)}
                )
    if problems:
        raise ValidationError(problems)
    for section in KEYED:
        keys = [entry["key"] for entry in out[section] if entry.get("key") is not None]
        if len(keys) != len(set(keys)):
            raise ValidationError({section: [str(_("Keys must be unique within a section."))]})
    ensure_keys(out)
    out[GROUPS] = tree_order(out[GROUPS])
    try:
        check_references(out)
    except ValidationError as error:
        raise ValidationError({"content": error.messages}) from error
    return out


# --- Changing a template --------------------------------------------------------------------------------------------


def _locked(template: ProjectTemplate) -> ProjectTemplate:
    return ProjectTemplate.objects.select_for_update().get(pk=template.pk)


def _store(template: ProjectTemplate, content: dict[str, Any], event: str, details: dict[str, Any], user: Any) -> None:
    template.content = content
    template.save(update_fields=["content"])
    record_event(template, event, details)


def open_for_editing(template: ProjectTemplate) -> dict[str, Any]:
    """The content with every section and every key in place; written back once if it had to be completed."""
    with transaction.atomic():
        fresh = _locked(template)
        content = copy.deepcopy(fresh.content or {})
        if ensure_keys(content):
            content[GROUPS] = tree_order(content[GROUPS])
            fresh.content = content
            fresh.save(update_fields=["content"])
            template.content = content
        return content


def _mutate(
    template: ProjectTemplate, user: Any, event: str, details: dict[str, Any], change: Callable[[dict[str, Any]], Any]
) -> Any:
    """Run ``change`` on a locked, completed copy of the content; check it as a whole; write it."""
    with transaction.atomic():
        fresh = _locked(template)
        content = copy.deepcopy(fresh.content or {})
        ensure_keys(content)
        result = change(content)
        content[GROUPS] = tree_order(content[GROUPS])
        content["version"] = VERSION
        check_references(content)
        _store(fresh, content, event, details, user)
        template.content = content
        return result


def set_notes(template: ProjectTemplate, *, notes: str, rental_days: Any, user: Any = None) -> None:
    """The notes that go into a new project, and the default rental days (top level of the content)."""
    errors = _Errors()
    text = _text({"notes": notes}, "notes", errors, maximum=20000)
    days = _integer({"rental_days": rental_days}, "rental_days", errors)
    errors.raise_if_any()

    def change(content: dict[str, Any]) -> None:
        content["notes"] = text
        content["rental_days"] = days

    _mutate(template, user, "project_template.content_changed", {"section": "notes"}, change)


def add_entry(
    template: ProjectTemplate, section: str, data: dict[str, Any], *, rights: Rights, user: Any = None
) -> int:
    """Add an entry at the end of its section (a group below its parent); returns its key (an open item: its place)."""
    prices = rights.has(SpecialRight.PRICES)

    def change(content: dict[str, Any]) -> int:
        if section == OPEN_ITEMS:
            content[OPEN_ITEMS].append(_open_item(data.get("text") if isinstance(data, dict) else data))
            return len(content[OPEN_ITEMS]) - 1
        entry = normalize_entry(section, {**data, "key": None}, prices=prices)
        entry["key"] = _take_key(content, section)
        content[section].append(entry)
        return entry["key"]

    return _mutate(template, user, "project_template.content_changed", {"section": section, "change": "added"}, change)


def update_entry(
    template: ProjectTemplate,
    section: str,
    key: int,
    data: dict[str, Any],
    *,
    rights: Rights,
    user: Any = None,
    expect: str | None = None,
    merge: bool = False,
) -> None:
    """Change an entry. Raises ``KeyError`` if it is gone; ``expect`` (open items only) is the text it had on the page.

    ``merge``: ``data`` holds only the fields to change; the others are those the entry has *now* (read under the lock, so
    two callers that change different fields of the same entry do not undo each other).
    """
    prices = rights.has(SpecialRight.PRICES)

    def change(content: dict[str, Any]) -> None:
        if section == OPEN_ITEMS:
            if key >= len(content[OPEN_ITEMS]) or (expect is not None and content[OPEN_ITEMS][key] != expect):
                raise KeyError(key)
            content[OPEN_ITEMS][key] = _open_item(data.get("text") if isinstance(data, dict) else data)
            return
        index = index_of(content, section, key)
        old = content[section][index]
        given = {**old, **data} if merge else data
        entry = normalize_entry(section, {**given, "key": key}, prices=prices, old=old)
        content[section][index] = entry
        if section == GROUPS:
            _after_group_change(content, entry, old)
        elif section == LINES and entry["variant"] != LineVariant.ALTERNATIVE.value:
            entry["alternative_to"] = None

    _mutate(template, user, "project_template.content_changed", {"section": section, "change": "changed"}, change)


def _after_group_change(content: dict[str, Any], entry: dict[str, Any], old: dict[str, Any]) -> None:
    """An alternative group that became normal replaces nothing; a group that is replaced and became an alternative is not."""
    if entry["kind"] != GroupKind.ALTERNATIVE.value:
        entry["alternative_to"] = None
    else:
        for other in content[GROUPS]:
            if other.get("alternative_to") == entry["key"]:
                other["alternative_to"] = None
                other["kind"] = GroupKind.OPTIONAL.value


def _clear_alternatives(content: dict[str, Any], section: str, key: int) -> None:
    """What replaced the deleted thing is optional now (as when a line is deleted from a project, PRJ-083)."""
    for entry in content[section]:
        if entry.get("alternative_to") == key:
            entry["alternative_to"] = None
            if section == GROUPS:
                entry["kind"] = GroupKind.OPTIONAL.value
            else:
                entry["variant"] = LineVariant.OPTIONAL.value


def delete_entry(
    template: ProjectTemplate,
    section: str,
    key: int,
    *,
    user: Any = None,
    with_content: bool = False,
    expect: str | None = None,
) -> None:
    """Delete an entry.

    Args:
        template: The template.
        section: The section of the entry.
        key: Its key (an open item: its place).
        user: Who does it.
        with_content: For a group: delete its lines and subgroups too; otherwise they move up to the group's parent.
        expect: Open items only – the text it had on the page.

    Raises:
        KeyError: It is gone already.
    """

    def change(content: dict[str, Any]) -> None:
        if section == OPEN_ITEMS:
            if key >= len(content[OPEN_ITEMS]) or (expect is not None and content[OPEN_ITEMS][key] != expect):
                raise KeyError(key)
            del content[OPEN_ITEMS][key]
            return
        index = index_of(content, section, key)
        entry = content[section].pop(index)
        if section == GROUPS:
            _delete_group(content, entry, with_content)
        elif section == LINES:
            _clear_alternatives(content, LINES, key)
        elif section == PHASES:
            for other in (*content[CREW], *content[VEHICLES]):
                phase = other.get("phase")
                if phase == index:
                    other["phase"] = None
                elif phase is not None and phase > index:
                    other["phase"] = phase - 1

    _mutate(template, user, "project_template.content_changed", {"section": section, "change": "deleted"}, change)


def _delete_group(content: dict[str, Any], group: dict[str, Any], with_content: bool) -> None:
    key, parent = group["key"], group.get("parent")
    if with_content:
        doomed = {key}
        grew = True
        while grew:
            grew = False
            for entry in content[GROUPS]:
                if entry.get("parent") in doomed and entry["key"] not in doomed:
                    doomed.add(entry["key"])
                    grew = True
        removed_lines = {line["key"] for line in content[LINES] if line.get("group") in doomed}
        content[GROUPS] = [entry for entry in content[GROUPS] if entry["key"] not in doomed]
        content[LINES] = [line for line in content[LINES] if line["key"] not in removed_lines]
        for gone in doomed:
            _clear_alternatives(content, GROUPS, gone)
        for gone in removed_lines:
            _clear_alternatives(content, LINES, gone)
        return
    for entry in content[GROUPS]:
        if entry.get("parent") == key:
            entry["parent"] = parent
    for line in content[LINES]:
        if line.get("group") == key:
            line["group"] = parent
    _clear_alternatives(content, GROUPS, key)


def move_entry(
    template: ProjectTemplate, section: str, key: int, direction: int, *, user: Any = None, expect: str | None = None
) -> None:
    """Move an entry one place up (``direction`` < 0) or down.

    A group moves among the groups of the same parent (with its subgroups), a line among the lines of the same group, a
    phase takes the crew places and bookings that name it along. At the end of the row nothing happens.
    """
    step = -1 if direction < 0 else 1

    def change(content: dict[str, Any]) -> None:
        if section == OPEN_ITEMS:
            items = content[OPEN_ITEMS]
            if key >= len(items) or (expect is not None and items[key] != expect):
                raise KeyError(key)
            other = key + step
            if 0 <= other < len(items):
                items[key], items[other] = items[other], items[key]
            return
        entries = content[section]
        index = index_of(content, section, key)
        if section == GROUPS:
            _move_group(content, index, step)
        elif section == LINES:
            group = entries[index].get("group")
            neighbours = [i for i, line in enumerate(entries) if line.get("group") == group]
            place = neighbours.index(index) + step
            if 0 <= place < len(neighbours):
                other = neighbours[place]
                entries[index], entries[other] = entries[other], entries[index]
        else:
            other = index + step
            if not 0 <= other < len(entries):
                return
            entries[index], entries[other] = entries[other], entries[index]
            if section == PHASES:
                for booking in (*content[CREW], *content[VEHICLES]):
                    if booking.get("phase") == index:
                        booking["phase"] = other
                    elif booking.get("phase") == other:
                        booking["phase"] = index

    _mutate(template, user, "project_template.content_changed", {"section": section, "change": "moved"}, change)


def _subtree(groups: list[dict[str, Any]], index: int) -> int:
    """The number of entries from ``index`` on that belong to the group there (itself and its descendants)."""
    members = {groups[index]["key"]}
    count = 1
    for entry in groups[index + 1 :]:
        if entry.get("parent") in members:
            members.add(entry["key"])
            count += 1
        else:
            break
    return count


def _move_group(content: dict[str, Any], index: int, step: int) -> None:
    groups = content[GROUPS]
    parent = groups[index].get("parent")
    siblings = [i for i, entry in enumerate(groups) if entry.get("parent") == parent]
    place = siblings.index(index) + step
    if not 0 <= place < len(siblings):
        return
    first, second = sorted((index, siblings[place]))
    size_first = _subtree(groups, first)
    size_second = _subtree(groups, second)
    block_first = groups[first : first + size_first]
    block_second = groups[second : second + size_second]
    groups[first : second + size_second] = [*block_second, *groups[first + size_first : second], *block_first]


def replace_content(template: ProjectTemplate, raw: Any, *, rights: Rights, user: Any = None) -> dict[str, Any]:
    """Replace the whole content (the API): checked and put in canonical form first.

    Raises:
        ValidationError: By section; the template is not changed.
    """
    prices = rights.has(SpecialRight.PRICES)
    with transaction.atomic():
        fresh = _locked(template)
        content = normalize_content(raw, prices=prices, old=fresh.content or {})
        if not prices:
            _keep_prices(content, fresh.content or {})
        _store(
            fresh,
            content,
            "project_template.content_replaced",
            {"counts": {s: len(content[s]) for s in SECTIONS}},
            user,
        )
        template.content = content
        return content


def without_prices(content: dict[str, Any]) -> dict[str, Any]:
    """A copy of the content without prices – for who may not see prices (PRJ-135)."""
    out = copy.deepcopy(content)
    for section, names in _PRICE_FIELDS.items():
        for entry in out.get(section, []):
            if isinstance(entry, dict):
                for name in names:
                    entry.pop(name, None)
    return out


def _keep_prices(content: dict[str, Any], old: dict[str, Any]) -> None:
    """Without the right to see prices a new entry has none and a kept entry keeps its own."""
    for section, names in _PRICE_FIELDS.items():
        before = {entry.get("key"): entry for entry in old.get(section, []) if isinstance(entry, dict)}
        for entry in content[section]:
            previous = before.get(entry["key"], {})
            for name in names:
                entry[name] = previous.get(name)


# --- For the pages: what the content looks like ---------------------------------------------------------------------


def outline(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Groups and lines as one list of rows, in the order of a project.

    Lines without a group come first, then every group in tree order, each followed by its lines. A row is
    ``{"type": "group" | "line", "depth": n, "entry": {...}}``.
    """
    rows: list[dict[str, Any]] = []
    lines = content.get(LINES, [])
    for line in lines:
        if line.get("group") is None:
            rows.append({"type": "line", "depth": 0, "entry": line})
    groups = content.get(GROUPS, [])
    by_key = {entry["key"]: entry for entry in groups}
    for group in groups:
        depth = _group_depth(by_key, group["key"])
        rows.append({"type": "group", "depth": depth, "entry": group})
        for line in lines:
            if line.get("group") == group["key"]:
                rows.append({"type": "line", "depth": depth + 1, "entry": line})
    return rows
