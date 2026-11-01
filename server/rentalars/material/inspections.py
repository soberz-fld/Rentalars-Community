# SPDX-License-Identifier: GPL-3.0-or-later
"""When is which item due for which inspection (MAT-030 to MAT-032)?

An inspection type applies to the items of its models and of the models in
its categories, subcategories included. For every item and type:

* **due date** = date of the last *passed* inspection + interval;
* a **failed** inspection makes the item due at once (it is repaired and
  inspected again);
* an item that was **never** inspected counts as overdue. Electrical tests
  exist so that nothing untested goes out; "we don't know" is not "fine".
  *Assumption* (catalogue 12.2): a new inspection type therefore makes all
  its items overdue until they are inspected – or until somebody records
  the last inspection known from the paper records.

Everything is calculated when asked; nothing about due dates is stored.

States, in the order of urgency:

=========  =======================================================
overdue    due date passed, failed, or never inspected
soon       due within :data:`SOON_DAYS`
ok         due later
=========  =======================================================
"""

from __future__ import annotations

import calendar
import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.db.models import Max
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.i18n import LazyCall, LocalText, format_date
from rentalars.masterdata.models import Category
from rentalars.material.models import (
    ARCHIVED_STATUSES,
    Inspection,
    InspectionResult,
    InspectionType,
    MaterialItem,
)

#: Inspections due within this many days are "soon".
SOON_DAYS = 30

OVERDUE, SOON, OK = "overdue", "soon", "ok"

STATE_LABELS = {OVERDUE: _("overdue"), SOON: _("due soon"), OK: _("ok")}


def add_months(day: datetime.date, months: int) -> datetime.date:
    """The same day ``months`` later; the 31st becomes the last day of a shorter month."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return datetime.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class InspectionDue:
    """Where one item stands with one inspection type."""

    inspection_type: InspectionType
    last_date: datetime.date | None
    last_passed: bool
    due_date: datetime.date | None

    @property
    def state(self) -> str:
        """``overdue``, ``soon`` or ``ok``."""
        today = timezone.localdate()
        if self.due_date is None or self.due_date < today:
            return OVERDUE
        if self.due_date <= today + datetime.timedelta(days=SOON_DAYS):
            return SOON
        return OK

    @property
    def state_label(self) -> str:
        """The state in words."""
        return str(STATE_LABELS[self.state])

    @property
    def never_inspected(self) -> bool:
        """Whether no inspection of this type was ever recorded."""
        return self.last_date is None

    @property
    def sort_key(self) -> datetime.date:
        """For ordering by urgency: never inspected first."""
        return self.due_date or datetime.date.min


#: The date of the last passed inspection, and the last inspection of any result, per item and type.
_Latest = tuple[dict[tuple[int, int], datetime.date], dict[tuple[int, int], tuple[datetime.date, str]]]


class InspectionPlan:
    """Answers "what is due?" for many items with a fixed number of queries.

    Built once per request: the types with their categories and models,
    the category tree, and the latest inspections of the items asked about.
    """

    def __init__(self) -> None:
        self.types = list(
            InspectionType.objects.filter(is_active=True).prefetch_related("categories", "material_models")
        )
        parents = dict(Category.objects.values_list("pk", "parent_id"))
        self._by_model: dict[int, list[InspectionType]] = defaultdict(list)
        self._by_category: dict[int, list[InspectionType]] = defaultdict(list)
        for inspection_type in self.types:
            for model in inspection_type.material_models.all():
                self._by_model[model.pk].append(inspection_type)
            for category in inspection_type.categories.all():
                self._by_category[category.pk].append(inspection_type)
        self._parents = parents
        self._latest: dict[frozenset[int], _Latest] = {}

    def _latest_of(self, item_ids: list[int]) -> _Latest:
        """The latest inspections of these items, asked for once per plan (a page may ask twice)."""
        key = frozenset(item_ids)
        if key not in self._latest:
            self._latest[key] = _latest_inspections(item_ids)
        return self._latest[key]

    @property
    def is_empty(self) -> bool:
        """Whether no inspection type exists; then nothing is ever due."""
        return not self.types

    def types_for(self, model_id: int, category_id: int) -> list[InspectionType]:
        """The inspection types that apply to the items of a model."""
        found: dict[int, InspectionType] = {t.pk: t for t in self._by_model.get(model_id, [])}
        current: int | None = category_id
        seen: set[int] = set()
        while current is not None and current not in seen:
            seen.add(current)
            for inspection_type in self._by_category.get(current, []):
                found.setdefault(inspection_type.pk, inspection_type)
            current = self._parents.get(current)
        return sorted(found.values(), key=lambda inspection_type: inspection_type.name)

    def model_ids_with_types(self) -> set[int]:
        """The models to whose items at least one inspection type applies."""
        from rentalars.material.models import MaterialModel

        category_ids = set(self._by_category)
        if category_ids:
            expanded: set[int] = set()
            for category_id in category_ids:
                expanded |= Category.objects.descendant_ids(category_id)
            category_ids = expanded
        by_category = set(MaterialModel.objects.filter(category_id__in=category_ids).values_list("pk", flat=True))
        return by_category | set(self._by_model)

    def dues_for(self, items: Iterable[MaterialItem]) -> dict[int, list[InspectionDue]]:
        """For each item, its applicable inspections with due dates, most urgent first."""
        items = [item for item in items if not item.material_model.is_bulk]
        if self.is_empty or not items:
            return {}
        latest = self._latest_of([item.pk for item in items])
        result: dict[int, list[InspectionDue]] = {}
        for item in items:
            types = self.types_for(item.material_model_id, item.material_model.category_id)
            if types:
                dues = [self._due(item.pk, inspection_type, latest) for inspection_type in types]
                result[item.pk] = sorted(dues, key=lambda due: due.sort_key)
        return result

    @staticmethod
    def _due_date(item_id: int, inspection_type: InspectionType, latest: _Latest) -> datetime.date | None:
        """When an item is due for an inspection type – the one rule for every page (MAT-031).

        ``interval`` after the last passed inspection; never inspected: at
        once (``None``). The latest inspection decides: if it failed, the item
        is due again from that day.
        """
        latest_passed, latest_any = latest
        last = latest_any.get((item_id, inspection_type.pk))
        if last is not None and last[1] == InspectionResult.FAILED:
            return last[0]
        passed = latest_passed.get((item_id, inspection_type.pk))
        return add_months(passed, inspection_type.interval_months) if passed is not None else None

    @classmethod
    def _due(cls, item_id: int, inspection_type: InspectionType, latest: _Latest) -> InspectionDue:
        """Where one item stands with one inspection type."""
        last = latest[1].get((item_id, inspection_type.pk))
        last_date, last_result = last if last else (None, None)
        return InspectionDue(
            inspection_type=inspection_type,
            last_date=last_date,
            last_passed=last_result == InspectionResult.PASSED,
            due_date=cls._due_date(item_id, inspection_type, latest),
        )

    def _item_values(self, items: Any) -> list[tuple[int, int, int, int]]:
        """ID, inventory number, model and category of the items with inspections, as plain values."""
        from rentalars.material.models import TrackingMode

        return list(
            items.exclude(material_model__tracking_mode=TrackingMode.BULK).values_list(
                "pk", "inventory_number", "material_model_id", "material_model__category_id"
            )
        )

    def _types_memo(self) -> Any:
        """``types_for``, asked once per model and category."""
        known: dict[tuple[int, int], list[InspectionType]] = {}

        def types(model_id: int, category_id: int) -> list[InspectionType]:
            key = (model_id, category_id)
            if key not in known:
                known[key] = self.types_for(model_id, category_id)
            return known[key]

        return types

    def due_rows(self, *, within_days: int = SOON_DAYS, type_id: int | None = None) -> list[tuple[int, InspectionDue]]:
        """What :meth:`due_items` returns, with item IDs instead of items.

        Works on plain values: with inspections for thousands of items the
        overview must not load every one of them (NFA-012). Load the items of
        the rows shown with :meth:`with_items`.
        """
        model_ids = self.model_ids_with_types()
        if not model_ids:
            return []
        values = self._item_values(
            MaterialItem.objects.filter(material_model_id__in=model_ids).exclude(status__in=ARCHIVED_STATUSES)
        )
        latest = self._latest_of([item_id for item_id, _number, _model, _category in values])
        types = self._types_memo()
        limit = timezone.localdate() + datetime.timedelta(days=within_days)
        found = []
        for item_id, number, model_id, category_id in values:
            for inspection_type in types(model_id, category_id):
                if type_id is not None and inspection_type.pk != type_id:
                    continue
                due_date = self._due_date(item_id, inspection_type, latest)
                if due_date is None or due_date <= limit:
                    due = self._due(item_id, inspection_type, latest)
                    found.append((due.sort_key, number, item_id, due))
        found.sort(key=lambda row: (row[0], row[1]))
        return [(item_id, due) for _key, _number, item_id, due in found]

    @staticmethod
    def with_items(rows: list[tuple[int, InspectionDue]]) -> list[tuple[MaterialItem, InspectionDue]]:
        """The rows of :meth:`due_rows` with their items, ready to show."""
        items = MaterialItem.objects.select_related(
            "material_model__category", "storage_location", "installed_in__storage_location"
        ).in_bulk([item_id for item_id, _due in rows])
        return [(items[item_id], due) for item_id, due in rows if item_id in items]

    def due_items(
        self, *, within_days: int = SOON_DAYS, type_id: int | None = None
    ) -> list[tuple[MaterialItem, InspectionDue]]:
        """Every item whose inspection is overdue or due within ``within_days`` (MAT-032).

        One row per item and inspection type, most urgent first. Archived
        items are left out; defective items are kept – they are often
        exactly the ones waiting for their inspection after a repair.
        """
        return self.with_items(self.due_rows(within_days=within_days, type_id=type_id))

    def overdue_ids(self, item_ids: Iterable[int]) -> set[int]:
        """Which of the given items have an overdue inspection (MAT-032, for packlists).

        The rule of :meth:`dues_for`, on plain values: a packlist of a big
        project asks about thousands of items at once (NFA-012).
        """
        if self.is_empty:
            return set()
        values = self._item_values(MaterialItem.objects.filter(pk__in=list(item_ids)))
        if not values:
            return set()
        latest = self._latest_of([item_id for item_id, _number, _model, _category in values])
        types = self._types_memo()
        today = timezone.localdate()
        overdue = set()
        for item_id, _number, model_id, category_id in values:
            for inspection_type in types(model_id, category_id):
                due_date = self._due_date(item_id, inspection_type, latest)
                # The same as InspectionDue.state == OVERDUE.
                if due_date is None or due_date < today:
                    overdue.add(item_id)
                    break
        return overdue


def _latest_inspections(
    item_ids: list[int],
) -> tuple[dict[tuple[int, int], datetime.date], dict[tuple[int, int], tuple[datetime.date, str]]]:
    """The date of the last passed inspection and the last inspection of any result, per item and type."""
    inspections = Inspection.objects.all()
    if len(item_ids) <= 2000:
        inspections = inspections.filter(item_id__in=item_ids)
    wanted = set(item_ids)
    passed: dict[tuple[int, int], datetime.date] = {}
    for row in (
        inspections.filter(result=InspectionResult.PASSED)
        .order_by()
        .values("item_id", "inspection_type_id")
        .annotate(last=Max("date"))
    ):
        if row["item_id"] in wanted:
            passed[(row["item_id"], row["inspection_type_id"])] = row["last"]
    latest: dict[tuple[int, int], tuple[datetime.date, str]] = {}
    # The latest inspection of any result: ordered by date and ID, the last one wins.
    for item_id, type_id, date, result in inspections.order_by("date", "id").values_list(
        "item_id", "inspection_type_id", "date", "result"
    ):
        if item_id in wanted:
            latest[(item_id, type_id)] = (date, result)
    return passed, latest


def report_due_inspections() -> int:
    """Tell the warehouse once about inspections that became due (MAT-032).

    Run by the daily maintenance. "Due" is overdue or due within
    :data:`SOON_DAYS`. Each item, type and due date is reported once, in one
    notification per run that names the first few and leads to the
    overview – a new inspection type for 300 cables is one message, not 300.
    Returns how many inspections were reported now.
    """
    from django.utils.translation import gettext as _
    from django.utils.translation import ngettext_lazy

    from rentalars.notifications.models import DueNotice, Kind
    from rentalars.notifications.services import notify, warehouse_staff

    rows = InspectionPlan().due_items(within_days=SOON_DAYS)
    keys = {
        f"inspection:{item.pk}:{due.inspection_type.pk}:{due.due_date.isoformat() if due.due_date else 'never'}": (
            item,
            due,
        )
        for item, due in rows
    }
    known = set(DueNotice.objects.filter(key__startswith="inspection:").values_list("key", flat=True))
    stale = [key for key in known if key not in keys]
    for start in range(0, len(stale), 500):
        DueNotice.objects.filter(key__in=stale[start : start + 500]).delete()
    new = [key for key in keys if key not in known]
    if not new:
        return 0
    DueNotice.objects.bulk_create([DueNotice(key=key) for key in new], ignore_conflicts=True)
    overdue = sum(1 for key in new if keys[key][1].state == OVERDUE)
    # UIX-029: written for each recipient in his language.
    title = LocalText(
        ngettext_lazy(
            "%(count)d inspection due (%(overdue)d overdue)",
            "%(count)d inspections due (%(overdue)d overdue)",
            len(new),
        ),
        count=len(new),
        overdue=overdue,
    )

    def due_lines() -> str:
        lines = [
            f"{keys[key][0].display_id} {keys[key][0].material_model.name}: {keys[key][1].inspection_type.name}, "
            + (format_date(keys[key][1].due_date) if keys[key][1].due_date else str(_("never inspected")))
            for key in new[:10]
        ]
        if len(new) > 10:
            lines.append(_("and %(count)d more") % {"count": len(new) - 10})
        return "\n".join(lines)

    notify(
        warehouse_staff(),
        Kind.INSPECTION_DUE,
        title,
        body=LocalText(LazyCall(due_lines)),
        url=reverse("material:inspections"),
    )
    return len(new)
