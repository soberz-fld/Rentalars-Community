# SPDX-License-Identifier: GPL-3.0-or-later
"""The lists of the master data (Django's administration interface) as tables like every other list (UIX-040).

Django's lists already sort by a click on a heading, search and filter (the
filters fold away, one ``<details>`` per filter). :class:`TableAdminMixin`
adds what the lists of :mod:`rentalars.core.tables` have besides:

* **columns to choose** – ``?cols=name&cols=code`` (the first column, the
  link to the record, always stays);
* **CSV** of the view (filters, search and sort order as shown, all pages)
  with ``?format=csv``, and with every column with ``&cols=all``;
* **groups** – ``?group=<column or filter field>``: the rows sorted by it
  first, a heading above each group with the number of its rows in the whole
  list. UIX-044: every shown column is offered – a field by itself, a
  computed column (the path of a category) by its ``admin_order_field``.
* **entries per page** (UIX-050; UIX-012) –
  ``?per_page=``: 25, 50, 100, 200 or a typed number from 5 to 1,000,
  remembered per user and list like every list of Rentalars; 100 by default,
  as Django has it.

Django would read the three parameters as filters of the list and refuse
them, so the view takes them out of the address before the list is built;
:class:`TableChangeList` puts them back into every link the list makes
(sorting, filters, pages).
"""

from __future__ import annotations

import csv
import datetime
import io
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from django.contrib.admin.utils import display_for_field, label_for_field, lookup_field
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Case, CharField, Count, F, Value, When
from django.db.models.functions import Concat
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify
from django.utils.translation import gettext

from rentalars.core.listing import (
    MAX_PAGE_SIZE,
    MIN_PAGE_SIZE,
    PAGE_SIZE_PARAMETER,
    PAGE_SIZES,
    PageSizeChoice,
    page_size_choice,
)
from rentalars.core.tables import BYTE_ORDER_MARK, csv_text

#: The parameters of the table that Django must not see as filters.
TABLE_PARAMETERS = ("cols", "format", "group", PAGE_SIZE_PARAMETER)

#: Where Django's ``ChangeList`` takes ``list_per_page`` among its arguments after the request.
_PER_PAGE_ARGUMENT = 7

#: UIX-044: the name under which the value of a grouped column that is no field is added to the rows.
GROUP_ALIAS = "table_group_value"


def tree_path_order(levels: int = 6, separator: str = " > ") -> Any:
    """The full name of a record in a tree (``Halle 1 > Regal A > Fach 3``) as the database builds it (UIX-015).

    For sorting a column that shows ``path`` (categories, storage locations): the names of up to ``levels``
    levels from the top, so that every record stands below its parent. Deeper trees sort by their lowest
    ``levels`` levels.
    """
    parts: list[Any] = []
    for level in range(levels - 1, 0, -1):
        above = "__".join(["parent"] * level)
        parts.append(
            Case(
                When(**{f"{above}__isnull": False}, then=Concat(F(f"{above}__name"), Value(separator))),
                default=Value(""),
                output_field=CharField(),
            )
        )
    parts.append(F("name"))
    return Concat(*parts, output_field=CharField())


def _field(model: Any, name: str) -> Any:
    try:
        return model._meta.get_field(name)
    except FieldDoesNotExist:
        return None


def _display(record: Any, name: str) -> str:
    """The value of a field of a record as a heading: the label of a choice, "ja"/"nein", the related record."""
    field = _field(type(record), name)
    value = getattr(record, name, None)
    if field is not None and field.choices:
        return str(dict(field.flatchoices).get(value, value))
    if isinstance(value, bool):
        return gettext("yes") if value else gettext("no")
    if value is None:
        return ""
    if field is not None:
        return strip_tags(str(display_for_field(value, field, "")))  # a date or number as the list shows it
    return str(value)


def _column_text(model_admin: Any, record: Any, name: str) -> str:
    """UIX-044: the text of a column that is no field (a method of the admin or the model)."""
    try:
        _field_found, _attribute, value = lookup_field(name, record, model_admin)
    except (AttributeError, ValueError, FieldDoesNotExist):
        return ""
    return "" if value is None else strip_tags(str(value)).strip()


class TableChangeList(ChangeList):
    """A list of the administration that keeps columns and grouping in its links and groups its rows."""

    def __init__(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        #: ``{"cols": [...], "group": "..."}`` as taken out of the address by :class:`TableAdminMixin`.
        self.table_wishes = getattr(request, "admin_table", {"cols": [], "group": ""})
        #: One entry per row of the page: ``None`` or ``{"label", "count"}`` above the first row of a group.
        self.group_headings: list[dict[str, Any] | None] = []
        #: UIX-044: for a grouped column that is no field, the value its ``admin_order_field`` gives;
        #: added to the rows as :data:`GROUP_ALIAS`.
        self.group_expression = self.table_wishes.get("expression")
        # UIX-050: as many rows per page as the user chose.
        choice: PageSizeChoice | None = self.table_wishes.get("page_size")
        if choice is not None:
            if len(args) > _PER_PAGE_ARGUMENT:
                args = (*args[:_PER_PAGE_ARGUMENT], choice.size, *args[_PER_PAGE_ARGUMENT + 1 :])
            else:
                kwargs["list_per_page"] = choice.size
        super().__init__(request, *args, **kwargs)

    def get_queryset(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        """UIX-044: the rows with the value of a grouped column that is no field, before they are ordered."""
        if self.group_expression is not None and GROUP_ALIAS not in self.root_queryset.query.annotations:
            self.root_queryset = self.root_queryset.annotate(**{GROUP_ALIAS: self.group_expression})
        return super().get_queryset(request, *args, **kwargs)

    @property
    def group_path(self) -> str:
        """What the rows are grouped by in the database: the field, or :data:`GROUP_ALIAS`."""
        group = self.table_wishes.get("group", "")
        return GROUP_ALIAS if group and self.group_expression is not None else group

    def get_query_string(self, new_params: Any = None, remove: Any = None) -> str:
        """The links of the list – sorting, filters, pages – with the chosen columns and grouping."""
        query = super().get_query_string(new_params, remove)
        extra = [("cols", name) for name in self.table_wishes.get("cols", [])]
        if self.table_wishes.get("group"):
            extra.append(("group", self.table_wishes["group"]))
        if self.table_wishes.get("per_page"):
            extra.append((PAGE_SIZE_PARAMETER, self.table_wishes["per_page"]))
        if not extra:
            return query
        return query + ("&" if query != "?" else "") + urlencode(extra)

    def get_ordering(self, request: HttpRequest, queryset: Any) -> list[Any]:
        """Grouped, the group comes first, so that each group stands together; within it the chosen order."""
        ordering = list(super().get_ordering(request, queryset))
        group = self.group_path
        return [group, *ordering] if group else ordering

    def get_results(self, request: HttpRequest) -> None:
        """The rows of the page, and the headings of their groups with the count in the whole list."""
        super().get_results(request)
        group = self.group_path
        if not group:
            return
        counts = dict(self.queryset.order_by().values(group).annotate(rows=Count("pk")).values_list(group, "rows"))
        field = _field(self.model, group)
        key = field.attname if field is not None and hasattr(field, "attname") else group
        column = self.table_wishes["group"]
        previous: Any = object()
        for record in self.result_list:
            value = getattr(record, key, None)
            if value != previous:
                text = _display(record, group) if field is not None else _column_text(self.model_admin, record, column)
                label = text or gettext("(no entry)")
                self.group_headings.append({"label": label, "count": counts.get(value, 0)})
                previous = value
            else:
                self.group_headings.append(None)


class TableAdminMixin:
    """Columns to choose, CSV and groups for a list of the master data (UIX-040). Put it before ``ModelAdmin``."""

    change_list_template = "admin/table_change_list.html"

    def get_changelist(self, request: HttpRequest, **kwargs: Any) -> type[ChangeList]:
        """The list that keeps columns and grouping in its links and groups its rows."""
        return TableChangeList

    def group_fields(self, request: HttpRequest, *, every_column: bool = False) -> list[str]:
        """The columns and fields the rows can be grouped by.

        UIX-044: every shown column in its order – a field, or a column that sorts by an
        ``admin_order_field`` – then the plain fields among the filters that are no column. With
        ``every_column`` also the columns switched off (a grouping in the address stays valid).
        """
        model = self.model  # type: ignore[attr-defined]
        columns = self.all_columns(request) if every_column else self.get_list_display(request)
        names = [name for name in columns if isinstance(name, str) and self.groups_by(name)]
        filters = [name for name in self.get_list_filter(request) if isinstance(name, str)]  # type: ignore[attr-defined]
        names += [name for name in filters if _field(model, name) is not None]
        return list(dict.fromkeys(names))

    def groups_by(self, name: str) -> bool:
        """Whether a column can group the rows: a field, or a column with an ``admin_order_field`` (UIX-044)."""
        return _field(self.model, name) is not None or self.group_expression(name) is not None  # type: ignore[attr-defined]

    def group_expression(self, name: str) -> Any:
        """For a column that is no field: what it sorts by (``admin_order_field``) as a query expression, else ``None``."""
        model = self.model  # type: ignore[attr-defined]
        if _field(model, name) is not None:
            return None
        attribute = getattr(self, name, None) or getattr(model, name, None)
        order = getattr(attribute, "admin_order_field", None)
        if isinstance(order, str) and order:
            return F(order.lstrip("-"))
        return order if hasattr(order, "resolve_expression") else None

    def all_columns(self, request: HttpRequest) -> list[Any]:
        """Every column the list has – those of ``list_display``."""
        return list(super().get_list_display(request))  # type: ignore[misc]

    def get_list_display(self, request: HttpRequest) -> Any:
        """The chosen columns; the first – the link to the record – always."""
        every = self.all_columns(request)
        wished = getattr(request, "admin_table", {}).get("cols", [])
        if not wished or "all" in wished:
            return every
        chosen = [name for name in every[1:] if isinstance(name, str) and name in wished]
        return [every[0], *chosen]

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        """Take the table's parameters out of the address; answer ``?format=csv`` with the file."""
        wishes = {name: request.GET.getlist(name) for name in TABLE_PARAMETERS}
        columns = [part for value in wishes["cols"] for part in value.split(",") if part]
        group = next((name for name in wishes["group"] if name in self.group_fields(request, every_column=True)), "")
        # UIX-050: read from the address as it came, remembered per user and list.
        size = page_size_choice(request, key=self.page_size_key(), default=self.list_per_page)  # type: ignore[attr-defined]
        if any(wishes.values()):
            query = request.GET.copy()
            for name in TABLE_PARAMETERS:
                query.pop(name, None)
            request.GET = query
        request.admin_table = {  # type: ignore[attr-defined]
            "cols": columns,
            "group": group,
            "expression": self.group_expression(group) if group else None,
            "page_size": size,
            "per_page": str(size.size) if wishes[PAGE_SIZE_PARAMETER] and not size.error else "",
        }
        if "csv" in wishes["format"]:
            changelist = self.get_changelist_instance(request)  # type: ignore[attr-defined]
            return self.csv_response(changelist)
        context = {**(extra_context or {}), "table_tools": self.table_tools(request, columns, group)}
        return super().changelist_view(request, extra_context=context)  # type: ignore[misc]

    def page_size_key(self) -> str:
        """The name under which the number of rows per page of this list is remembered (UIX-050)."""
        meta = self.model._meta  # type: ignore[attr-defined]
        return f"admin:{meta.app_label}.{meta.model_name}"

    def table_tools(self, request: HttpRequest, columns: list[str], group: str) -> dict[str, Any]:
        """What the tools above the list need: the columns, the groups, the kept address, the CSV links."""
        model = self.model  # type: ignore[attr-defined]
        every = self.all_columns(request)
        shown = self.get_list_display(request)
        kept = [(name, value) for name in request.GET for value in request.GET.getlist(name) if name != "p"]
        base = [*kept, *(("cols", name) for name in columns), *([("group", group)] if group else [])]
        size: PageSizeChoice = request.admin_table["page_size"]  # type: ignore[attr-defined]
        return {
            # UIX-050: the numbers to choose, a field for any other; page 1 again.
            "page_size": {
                "links": [
                    (number, "?" + urlencode([*base, (PAGE_SIZE_PARAMETER, number)]), number == size.size)
                    for number in PAGE_SIZES
                ],
                "kept": base,
                "typed": size.refused or ("" if size.size in PAGE_SIZES else str(size.size)),
                "error": size.error,
                "min": MIN_PAGE_SIZE,
                "max": MAX_PAGE_SIZE,
                "param": PAGE_SIZE_PARAMETER,
            },
            "columns": [
                (name, label_for_field(name, model, self), name in shown, index == 0)
                for index, name in enumerate(every)
                if isinstance(name, str)
            ],
            # UIX-044: every shown column in its order, and the chosen one if it was switched off since.
            "groups": [
                (name, label_for_field(name, model, self), name == group)
                for name in dict.fromkeys([*self.group_fields(request), *([group] if group else [])])
            ],
            "kept": kept,
            "cols": columns,
            "group": group,
            "csv_url": "?" + urlencode([*base, ("format", "csv")]),
            "csv_all_url": "?"
            + urlencode([*kept, *([("group", group)] if group else []), ("cols", "all"), ("format", "csv")]),
        }

    def csv_response(self, changelist: ChangeList) -> HttpResponse:
        """Every row of the filtered list – not only the page – with the shown columns, as German spreadsheets read it."""
        model = self.model  # type: ignore[attr-defined]
        names = [name for name in changelist.list_display if isinstance(name, str) and name != "action_checkbox"]
        text = io.StringIO()
        text.write(BYTE_ORDER_MARK)
        writer = csv.writer(text, delimiter=";")
        writer.writerow([strip_tags(str(label_for_field(name, model, self))) for name in names])
        for record in changelist.queryset:
            row = []
            for name in names:
                field = None
                try:
                    field, _attribute, value = lookup_field(name, record, self)
                except (AttributeError, ValueError, FieldDoesNotExist):
                    value = ""
                if field is not None and getattr(field, "choices", None):
                    value = dict(field.flatchoices).get(value, value)
                plain = isinstance(value, bool | int | float | Decimal | datetime.date)
                row.append(csv_text(value if plain else strip_tags(str(value if value is not None else ""))))
            writer.writerow(row)
        response = HttpResponse(text.getvalue(), content_type="text/csv; charset=utf-8")
        name = slugify(str(model._meta.verbose_name_plural)) or "liste"
        response["Content-Disposition"] = f'attachment; filename="{name}-{timezone.localdate():%Y-%m-%d}.csv"'
        return response
