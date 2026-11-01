# SPDX-License-Identifier: GPL-3.0-or-later
"""Search and filters for material items, shared by the list page and the API (MAT-028)."""

from __future__ import annotations

from typing import Any

import django_filters
from django import forms
from django.db.models import Q, QuerySet

from rentalars.masterdata.models import Category, StorageLocation, Supplier
from rentalars.material.models import ARCHIVED_STATUSES, ItemStatus, MaterialItem
from rentalars.products.models import Product


def search_items(queryset: QuerySet[MaterialItem], text: str) -> QuerySet[MaterialItem]:
    """Search by article name, ID and serial number (MAT-028).

    A number is matched against the ID exactly (``42`` and ``0042`` find item
    0042) and against serial numbers that contain it; text is searched in the
    article name, short name, serial number, storage spot and note – and (MAT-073)
    in the custom values, except those visible only with the right to
    see purchase prices.
    """
    from rentalars.customfields.filters import search_condition
    from rentalars.material.spots import normalise_spot

    text = text.strip()
    if not text:
        return queryset
    condition = (
        Q(material_model__name__icontains=text)
        | Q(material_model__short_name__icontains=text)
        | Q(serial_number__icontains=text)
        | Q(note__icontains=text)
        | search_condition(text)
    )
    if text.isdigit():
        condition |= Q(inventory_number=int(text))  # a number alone is an ID, not a spot
    else:
        condition |= Q(storage_spot__icontains=normalise_spot(text))  # MAT-080: "1a1" finds "01-A-1"
    return queryset.filter(condition)


class YesNoWidget(forms.TextInput):
    """Reads a yes/no value from an address: ``true``, ``1``, ``yes`` and ``on`` mean yes.

    Links and bookmarks written by hand use all of these spellings. Reading
    only one of them would silently show the unfiltered list for the others.
    """

    YES = frozenset({"true", "1", "yes", "on"})
    NO = frozenset({"false", "0", "no", "off"})

    def value_from_datadict(self, data: Any, files: Any, name: str) -> bool | None:
        """Return ``True``, ``False`` or ``None`` (filter not used)."""
        text = str(data.get(name, "")).strip().lower()
        if text in self.YES:
            return True
        if text in self.NO:
            return False
        return None


class MaterialItemFilter(django_filters.FilterSet):
    """The filters of MAT-028: category, status, supplier, storage location, product."""

    q = django_filters.CharFilter(method="filter_search", label="Suche")
    category = django_filters.ModelChoiceFilter(queryset=Category.objects.all(), method="filter_category")
    status = django_filters.MultipleChoiceFilter(choices=ItemStatus.choices)
    supplier = django_filters.ModelChoiceFilter(queryset=Supplier.objects.all())
    storage_location = django_filters.ModelChoiceFilter(queryset=StorageLocation.objects.all())
    product = django_filters.ModelChoiceFilter(queryset=Product.objects.all(), method="filter_product")
    without_product = django_filters.BooleanFilter(method="filter_without_product", widget=YesNoWidget)
    material_model = django_filters.NumberFilter(field_name="material_model_id")
    installed_in = django_filters.NumberFilter(field_name="installed_in_id")
    archived = django_filters.BooleanFilter(method="filter_archived", widget=YesNoWidget)
    # MAT-069: items whose audit is due, items with open to-dos.
    audit_due = django_filters.BooleanFilter(method="filter_audit_due", widget=YesNoWidget)
    open_todos = django_filters.BooleanFilter(method="filter_open_todos", widget=YesNoWidget)

    class Meta:
        model = MaterialItem
        fields: list[str] = []

    def filter_queryset(self, queryset: Any) -> Any:
        """The filters above, then (MAT-073) ``cf<id>=text`` for the custom fields marked "in lists"."""
        from rentalars.customfields.filters import filter_items

        return filter_items(super().filter_queryset(queryset), self.data, request=self.request)

    def filter_search(self, queryset: Any, name: str, value: str) -> Any:
        """Free-text search."""
        return search_items(queryset, value)

    def filter_category(self, queryset: Any, name: str, value: Category) -> Any:
        """A category includes all its subcategories (MAT-008)."""
        return queryset.filter(material_model__category_id__in=Category.objects.descendant_ids(value.pk))

    def filter_product(self, queryset: Any, name: str, value: Product) -> Any:
        """Items that belong to a product, through their model or individually (PRD-003)."""
        return queryset.for_product(value.pk)

    def filter_without_product(self, queryset: Any, name: str, value: bool) -> Any:
        """The list "material without product" (PRD-005)."""
        return queryset.without_product() if value else queryset.with_product()

    def filter_audit_due(self, queryset: Any, name: str, value: bool) -> Any:
        """Only items whose audit is due, or only those whose audit is not (MAT-069)."""
        from rentalars.material.audits import due_items

        due = due_items().order_by().values("pk")
        return queryset.filter(pk__in=due) if value else queryset.exclude(pk__in=due)

    def filter_open_todos(self, queryset: Any, name: str, value: bool) -> Any:
        """Only items with open to-dos, or only those without (MAT-069)."""
        from rentalars.material.models import ItemTodo

        with_todos = ItemTodo.objects.filter(done_at__isnull=True).values("item_id")
        return queryset.filter(pk__in=with_todos) if value else queryset.exclude(pk__in=with_todos)

    def filter_archived(self, queryset: Any, name: str, value: bool) -> Any:
        """Show only archived items, or only those that are not (MAT-022)."""
        if value:
            return queryset.filter(status__in=ARCHIVED_STATUSES)
        return queryset.exclude(status__in=ARCHIVED_STATUSES)
