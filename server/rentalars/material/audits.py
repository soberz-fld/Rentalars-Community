# SPDX-License-Identifier: GPL-3.0-or-later
"""When is an item due for its audit – and recording audits and to-dos (MAT-067, MAT-068, MAT-069).

The requirement: audits in the material management, with an audit interval set in the settings (default 2 years).
The rules:

* **due date** = day of the last audit + interval (Einstellungen → Audits,
  24 months unless set otherwise) – whatever the audit found: the to-dos it
  noted are followed up as to-dos, not by auditing again;
* an item **never audited** is due once it has been in Rentalars for an
  interval, counted from the day it was created there. A fresh installation
  – or a list of 3,000 items imported today – is therefore not flooded with
  due audits; they come due one interval after the items were entered.
  Unlike an electrical test (``material.inspections``), "not looked at yet"
  is not dangerous, so it does not count as overdue at once;
* **archived** items (retired, sold, lost) and rows of **bulk material**
  (one row for a quantity, MAT-005) are never due – as with inspections.
  Both can still be audited and get to-dos;
* an interval of **0** switches audits off: nothing is due; audits and to-dos
  can still be noted.

Everything is calculated when asked; nothing about due dates is stored. The
lists work on querysets (``with_audit_fields``, ``due_items``), so that the
database filters and sorts thousands of items (NFA-012).
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, DateTimeField, Exists, F, IntegerField, Max, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext as _

from rentalars.material import numbering
from rentalars.material.audit_models import TODO_MAX_LENGTH, AuditResult, AuditSettings, ItemAudit, ItemTodo
from rentalars.material.inspections import add_months
from rentalars.material.models import ARCHIVED_STATUSES, MaterialItem, MaterialModel, TrackingMode

#: The longest note of an audit (``ItemAudit.note``).
NOTE_MAX_LENGTH = 250

#: Why an item has no due date: audits switched off, the item archived, a row of bulk material.
OFF, ARCHIVED, BULK = "off", "archived", "bulk"


def audit_settings() -> AuditSettings:
    """Einstellungen → Audits (read once per request)."""
    return AuditSettings.load()


# --- Due dates ------------------------------------------------------------------------------------


def due_date_for(
    item: MaterialItem, last_audit_at: datetime.datetime | None, settings_row: AuditSettings
) -> datetime.date | None:
    """The day an item is due for its audit; ``None`` if it never is (off, archived, bulk).

    ``last_audit_at`` is the moment of its last audit, ``None`` if it was
    never audited – then the day it was created in Rentalars counts.
    """
    if not settings_row.is_active or item.is_archived or item.material_model.is_bulk:
        return None
    reference = last_audit_at or item.created_at
    return add_months(timezone.localdate(reference), settings_row.interval_months)


def due_before(interval_months: int, today: datetime.date | None = None) -> datetime.datetime:
    """The moment from which an audit (or a creation) is not due yet today.

    An item whose last audit – or, never audited, whose creation – lies
    before this moment is due. Worked out with :func:`add_months` like the
    due date, so that the list and the item's page always agree, also at the
    end of a month (31 January + 1 month = 28 February).
    """
    today = today or timezone.localdate()
    last_due_day = add_months(today, -interval_months)
    while add_months(last_due_day + datetime.timedelta(days=1), interval_months) <= today:
        last_due_day += datetime.timedelta(days=1)
    first_free_day = last_due_day + datetime.timedelta(days=1)
    return timezone.make_aware(datetime.datetime.combine(first_free_day, datetime.time.min))


def with_audit_fields(queryset: QuerySet[MaterialItem]) -> QuerySet[MaterialItem]:
    """Add to each item: ``last_audit_at``, ``open_todo_count`` and ``audit_reference``.

    ``audit_reference`` is the moment the interval is counted from: the last
    audit, or the creation of an item never audited. Each a small subquery
    per item instead of joining all audits to all items (NFA-012) – grouped,
    without ``LIMIT``: MariaDB refuses a ``LIMIT`` in a subquery of ``IN``,
    and the filter ``audit_due`` of ``/material-items`` puts these into one.
    """
    last = (
        ItemAudit.objects.filter(item=OuterRef("pk"))
        .order_by()
        .values("item")
        .annotate(last=Max("audited_at"))
        .values("last")
    )
    todos = (
        ItemTodo.objects.filter(item=OuterRef("pk"), done_at__isnull=True)
        .order_by()
        .values("item")
        .annotate(number=Count("pk"))
        .values("number")
    )
    return queryset.annotate(
        last_audit_at=Subquery(last, output_field=DateTimeField()),
        open_todo_count=Coalesce(Subquery(todos, output_field=IntegerField()), 0),
    ).annotate(audit_reference=Coalesce(F("last_audit_at"), F("created_at"), output_field=DateTimeField()))


def due_items(
    queryset: QuerySet[MaterialItem] | None = None, *, settings_row: AuditSettings | None = None
) -> QuerySet[MaterialItem]:
    """The items whose audit is due, with the fields of :func:`with_audit_fields`; oldest first.

    "Oldest" is the longest time since the last audit (or the creation of an
    item never audited); the ID breaks ties.
    """
    settings_row = settings_row or audit_settings()
    items = with_audit_fields(queryset if queryset is not None else MaterialItem.objects.all())
    if not settings_row.is_active:
        return items.none()
    return (
        items.exclude(status__in=ARCHIVED_STATUSES)
        .exclude(material_model__tracking_mode=TrackingMode.BULK)
        .filter(audit_reference__lt=due_before(settings_row.interval_months))
        .order_by("audit_reference", "inventory_number")
    )


def due_count(*, settings_row: AuditSettings | None = None) -> int:
    """How many items:func:`due_items` lists – counted without a subquery per item (MAT-070).

    The tab "Offene Punkte" shows the sum on every tab of the material management, so the count must be cheap
    with 20,000 items: an item is due exactly when it has no audit since the cut-off and either an earlier
    audit or a creation before it. Two ``EXISTS`` on the index of the audits instead of the last audit of
    every item.
    """
    settings_row = settings_row or audit_settings()
    if not settings_row.is_active:
        return 0
    cutoff = due_before(settings_row.interval_months)
    recent = ItemAudit.objects.filter(item=OuterRef("pk"), audited_at__gte=cutoff)
    earlier = ItemAudit.objects.filter(item=OuterRef("pk"))
    # The few bulk models as a list of ids: excluding through the join made MariaDB test every item (44 ms).
    bulk = MaterialModel.objects.filter(tracking_mode=TrackingMode.BULK).values("pk")
    return (
        MaterialItem.objects.exclude(status__in=ARCHIVED_STATUSES)
        .exclude(material_model_id__in=bulk)
        .filter(~Exists(recent))
        .filter(Q(created_at__lt=cutoff) | Exists(earlier))
        .count()
    )


@dataclass(frozen=True)
class AuditState:
    """Where one item stands with its audits: the last one, the next due date, and why there is none."""

    last: ItemAudit | None
    due_date: datetime.date | None
    #: Why there is no due date: :data:`OFF`, :data:`ARCHIVED`, :data:`BULK` – empty if there is one.
    no_due_reason: str = ""

    @property
    def is_due(self) -> bool:
        """Whether the audit is due today or was due earlier."""
        return self.due_date is not None and self.due_date <= timezone.localdate()

    @property
    def never_audited(self) -> bool:
        """Whether the item was never audited."""
        return self.last is None


def audit_fields(item: MaterialItem, settings_row: AuditSettings | None = None) -> dict[str, Any]:
    """The audit fields of an item in the API: last audit, next due date, whether it is due, open to-dos.

    Read from the annotations of :func:`with_audit_fields` where the item
    has them (lists), else asked for with two small queries.
    """
    known = getattr(item, "_audit_fields", None)
    if known is not None:
        return known
    if hasattr(item, "last_audit_at") and hasattr(item, "open_todo_count"):
        last, count = item.last_audit_at, item.open_todo_count
    else:
        last = item.audits.values_list("audited_at", flat=True).first()
        count = item.todos.filter(done_at__isnull=True).count()
    due = due_date_for(item, last, settings_row or audit_settings())
    fields = {
        "last_audit": last,
        "next_audit": due,
        "audit_due": due is not None and due <= timezone.localdate(),
        "open_todos": count,
    }
    item._audit_fields = fields  # type: ignore[attr-defined]
    return fields


def head_badges(item: MaterialItem) -> dict[str, Any]:
    """For the head of every page of an item: the day its audit was due (if it is) and its open to-dos."""
    last = item.audits.values_list("audited_at", flat=True).first()
    due = due_date_for(item, last, audit_settings())
    return {
        "audit_due_date": due if due is not None and due <= timezone.localdate() else None,
        "open_todo_count": item.todos.filter(done_at__isnull=True).count(),
    }


def state_of(item: MaterialItem, *, settings_row: AuditSettings | None = None) -> AuditState:
    """The last audit of an item and when the next one is due."""
    settings_row = settings_row or audit_settings()
    last = item.audits.select_related("audited_by").first()
    reason = ""
    if not settings_row.is_active:
        reason = OFF
    elif item.is_archived:
        reason = ARCHIVED
    elif item.material_model.is_bulk:
        reason = BULK
    return AuditState(
        last=last,
        due_date=due_date_for(item, last.audited_at if last else None, settings_row),
        no_due_reason=reason,
    )


# --- To-dos ---------------------------------------------------------------------------------------


def open_todos() -> QuerySet[ItemTodo]:
    """The open to-dos of items in use – archived items are left out, as in the list of items (MAT-022)."""
    return ItemTodo.objects.filter(done_at__isnull=True).exclude(item__status__in=ARCHIVED_STATUSES)


def _user(user: Any) -> Any:
    """The user to note, or ``None`` for an anonymous caller or a background task."""
    return user if getattr(user, "is_authenticated", False) else None


def clean_todo_text(text: Any) -> str:
    """The text of a to-do with its spaces evened out.

    Raises:
        ValidationError: The text is longer than a to-do may be.
    """
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) > TODO_MAX_LENGTH:
        raise ValidationError({"text": _("A to-do has at most %(count)d characters.") % {"count": TODO_MAX_LENGTH}})
    return cleaned


def add_todo(item: MaterialItem, text: Any, *, user: Any = None, audit: ItemAudit | None = None) -> ItemTodo:
    """Note a to-do on an item; the same text open on the item already is not noted twice.

    Raises:
        ValidationError: The text is empty or too long.
    """
    cleaned = clean_todo_text(text)
    if not cleaned:
        raise ValidationError({"text": _("Say what is to be done.")})
    for existing in item.todos.filter(done_at__isnull=True):
        if existing.text.casefold() == cleaned.casefold():
            return existing
    todo = ItemTodo(item=item, text=cleaned, audit=audit, created_by=_user(user))
    todo.full_clean()
    todo.save()
    return todo


def complete_todo(todo: ItemTodo, *, user: Any = None) -> bool:
    """Tick a to-do done; returns whether it was open."""
    if not todo.is_open:
        return False
    todo.done_at = timezone.now()
    todo.done_by = _user(user)
    todo.save()
    return True


def complete_todos(todos: Iterable[ItemTodo], *, user: Any = None) -> int:
    """Tick several to-dos done at once; returns how many were open."""
    with transaction.atomic():
        return sum(1 for todo in todos if complete_todo(todo, user=user))


# --- Audits ---------------------------------------------------------------------------------------


def record_audit(
    item: MaterialItem,
    *,
    todos: Iterable[Any] = (),
    done: Iterable[Any] = (),
    note: Any = "",
    user: Any = None,
    audited_at: datetime.datetime | None = None,
) -> ItemAudit:
    """Record an audit of an item: "in order", or with the to-dos it noted (MAT-068, MAT-069).

    Args:
        item: The item looked at.
        todos: Texts of to-dos found; empty texts are skipped, the same text
            only once. With at least one the result is "with to-dos".
        done: IDs of open to-dos of the item that were found done meanwhile.
        note: A short note on the audit.
        user: Who audited.
        audited_at: When – now unless given (an audit of the paper records,
            through the API); never in the future.

    Raises:
        ValidationError: A text or the note is too long, or the moment lies
            in the future.
    """
    texts: list[str] = []
    for text in todos:
        cleaned = clean_todo_text(text)
        if cleaned and cleaned.casefold() not in {known.casefold() for known in texts}:
            texts.append(cleaned)
    note_text = " ".join(str(note or "").split())
    if len(note_text) > NOTE_MAX_LENGTH:
        raise ValidationError({"note": _("The note has at most %(count)d characters.") % {"count": NOTE_MAX_LENGTH}})
    moment = audited_at or timezone.now()
    if moment > timezone.now() + datetime.timedelta(minutes=5):
        raise ValidationError({"audited_at": _("An audit cannot lie in the future.")})
    done_ids = {int(value) for value in done if str(value).isdigit()}
    with transaction.atomic():
        audit = ItemAudit(
            item=item,
            audited_at=moment,
            audited_by=_user(user),
            result=AuditResult.TODOS if texts else AuditResult.OK,
            note=note_text,
        )
        audit.save()
        for text in texts:
            add_todo(item, text, user=user, audit=audit)
        if done_ids:
            complete_todos(item.todos.filter(pk__in=done_ids, done_at__isnull=True), user=user)
    return audit


# --- The audit mode (MAT-068) ------------------------------------------------------------


def parse_scanned_id(text: str) -> int:
    """The ID of an item from what was typed or scanned into the audit mode.

    The forms of the ID field (MAT-063, IMP-015): ``0427``, ``427``,
    ``#0427``. A scanner reading the QR code of a label types its address –
    ``https://…/m/0427`` or the address of Einstellungen → Etiketten with the
    ID at its end; the last part of the address is taken.

    Raises:
        ValidationError: The text holds no valid ID.
    """
    cleaned = text.strip()
    if "/" in cleaned:
        path = cleaned.split("?", 1)[0].split("#", 1)[0]
        parts = [part for part in path.split("/") if part]
        cleaned = parts[-1] if parts else ""
    try:
        return numbering.parse_inventory_number(cleaned)
    except ValidationError:
        raise ValidationError(_("“%(value)s” is not a valid ID.") % {"value": text.strip()}) from None


def audit_item(number: int) -> MaterialItem | None:
    """The item with this ID, with what the audit mode shows of it – its master data too (:func:`master_data`)."""
    return (
        MaterialItem.objects.select_related(
            "material_model__category__parent__parent",
            "material_model__manufacturer",
            "supplier",
            "purchase_price_in",
            "storage_location",
            "installed_in__storage_location",
        )
        .with_category_fields()
        .filter(inventory_number=number)
        .first()
    )


@dataclass(frozen=True)
class MasterDataRow:
    """One line of the master data of an item in the audit mode (MAT-079).

    ``value`` is text, or HTML for the value of a custom field (a web address
    as a link); empty if nothing is documented – the page shows "–" then.
    ``note`` adds a word: "eigen" for an item's own category-specific value,
    "in 0500" for an installed item's place. ``required_missing``: a required
    custom field without value ("Pflichtangabe fehlt").
    """

    label: str
    value: str
    note: str = ""
    required_missing: bool = False

    @property
    def empty(self) -> bool:
        """Whether nothing is documented."""
        return not str(self.value).strip()


def _protection_class_row(item: MaterialItem) -> MasterDataRow | None:
    """The protection class of the item – its own, else its model's (MAT-077); ``None`` without that field.

    Read through the field of the model, so that the overview keeps working
    whatever the electrical inspection adds around it.
    """
    code = getattr(item, "effective_protection_class", None)
    if code is None:
        return None
    field = item.material_model._meta.get_field("protection_class")
    labels = {value: str(label) for value, label in field.flatchoices}
    own = _("own") if getattr(item, "protection_class_override", "") else ""
    return MasterDataRow(capfirst(str(field.verbose_name)), labels.get(code, code) if code else "", own)


def master_data(item: MaterialItem, rights: Any) -> list[MasterDataRow]:
    """The master data of an item at a glance, to check in the audit whether they are documented (MAT-079; MAT-068).

    The requirement: a compact overview of the master data in the audit form, to check whether details such as length
    or purchase date are documented correctly. It lists the ID,
    model, manufacturer, category, serial number, invoice date, supplier,
    purchase price (only with the right to see purchase prices, AUT-019),
    storage location, status, the protection class (MAT-077), the
    category-specific values (MAT-009, MAT-013) and the custom fields of the
    model's fieldset (MAT-073; a sensitive one only with the right to see
    purchase prices). Every field is listed, empty ones too, so that gaps
    stand out.

    A fixed number of queries, however many values: the item comes from
    :func:`audit_item` (category fields prefetched); the storage location
    path, the values and the fieldset of the custom fields take one query
    each.
    """
    from rentalars.accounts.rights import SpecialRight
    from rentalars.core.money import format_money
    from rentalars.customfields import services as custom_fields
    from rentalars.customfields.tables import value_html
    from rentalars.masterdata.models import remember_location_paths

    model = item.material_model
    purchase_date = item.purchase_date_text  # "2015" / "05.2015" when day or month are unknown
    rows = [
        MasterDataRow(_("ID"), item.display_id),
        MasterDataRow(_("Model"), model.name),
        MasterDataRow(_("Manufacturer"), model.manufacturer.name if model.manufacturer_id else ""),
        MasterDataRow(_("Category"), model.category.path),
        MasterDataRow(_("Serial number"), item.serial_number),
        MasterDataRow(_("Invoice date"), purchase_date),
        MasterDataRow(_("Bought from"), item.supplier.name if item.supplier_id else ""),
    ]
    if rights.has(SpecialRight.PURCHASE_PRICES):
        if item.purchase_price_in_id:  # MAT-054: bought as a set, the price is noted at another item
            price = _("included in the price of %(head)s") % {"head": item.purchase_price_in.display_id}
        else:
            price = format_money(item.purchase_price)
        rows.append(MasterDataRow(_("Purchase price (net)"), price))
    location = item.effective_storage_location
    remember_location_paths([location])
    container = _("in %(id)s") % {"id": item.installed_in.display_id} if item.installed_in_id else ""
    spot = item.effective_storage_spot
    place = (f"{location.path} {spot}" if spot else location.path) if location is not None else ""
    rows.append(MasterDataRow(_("Storage location"), place, container))
    rows.append(MasterDataRow(_("Status"), item.get_status_display()))
    protection = _protection_class_row(item)
    if protection is not None:
        rows.append(protection)
    overrides = item.field_value_overrides or {}
    for field in model.category.applicable_fields():
        own = bool(overrides.get(str(field.pk)))
        rows.append(MasterDataRow(field.label, model.field_display(field, overrides), _("own") if own else ""))
    for value_row in custom_fields.value_rows(item, rights):
        rows.append(
            MasterDataRow(
                value_row.field.label_with_unit,
                value_html(value_row.field, value_row.stored),
                required_missing=value_row.missing,
            )
        )
    return rows


# --- Counts of Materialverwaltung → Offene Punkte -------------------------------------------------


def open_point_counts() -> dict[str, int]:
    """How many entries each sub-tab of "Offene Punkte" has: items without product, open to-dos, due audits."""
    return {
        "without_product": MaterialItem.objects.without_product().not_archived().count(),
        "todos": open_todos().count(),
        "audits": due_count(),
    }


# --- History (MAT-025) ----------------------------------------------------------------------------


def history_summary(entry: Any) -> str | None:
    """A readable line for an audit or a to-do in the history of the item; ``None`` for other entries.

    "Audit: in Ordnung", "To-Do notiert: Label fehlt", "To-Do erledigt: Label
    fehlt" – the change log stores field names and raw values.
    """
    from rentalars.core.models import AuditAction

    model = entry.content_type.model_class()
    changes = entry.changes if isinstance(entry.changes, dict) else {}

    def new(name: str) -> Any:
        values = changes.get(name)
        return values[1] if isinstance(values, list) and len(values) == 2 else None

    if model is ItemAudit and entry.action == AuditAction.CREATED:
        result = new("result") or AuditResult.OK
        label = AuditResult(result).label if result in AuditResult.values else result
        note = new("note")
        if note:
            return _("Audit: %(result)s – %(note)s") % {"result": label, "note": note}
        return _("Audit: %(result)s") % {"result": label}
    if model is ItemTodo:
        text = new("text") or entry.object_repr.split(": ", 1)[-1]
        if entry.action == AuditAction.CREATED:
            return _("To-do noted: %(text)s") % {"text": text}
        if entry.action == AuditAction.UPDATED and "done_at" in changes:
            if new("done_at"):
                return _("To-do done: %(text)s") % {"text": text}
            return _("To-do open again: %(text)s") % {"text": text}
        if entry.action == AuditAction.DELETED:
            return _("To-do deleted: %(text)s") % {"text": text}
    return None
