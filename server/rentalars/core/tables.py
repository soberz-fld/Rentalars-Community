# SPDX-License-Identifier: GPL-3.0-or-later
"""Lists as tables whose columns people choose and sort (UIX-015, UIX-004, IMP-005).

A list page describes its table once – the columns it *can* show – and this
module does the rest:

* **Which columns are shown.** Each column is on or off by default. A user
  can switch columns on and off; the choice is remembered per user and list
  (:class:`~rentalars.core.models.TablePreference`). ``?cols=id,name,status``
  in the address overrides it, so a link to a list shows the same columns
  for the colleague who opens it (UIX-004).
* **Sorting.** Every column has a clickable heading; a second click reverses
  the order. The sort order is ``?sort=name`` or ``?sort=-name`` in the
  address, as before. UIX-015: a column sorts by model fields or a
  query expression (a ``Subquery`` for a column of several names); a
  computed column sorts in Python, for lists of at most
  :data:`PYTHON_SORT_MAX_ROWS` rows. Only a column of buttons or tick boxes
  is unsortable, and says why (``Column.unsortable``).
* **Export.** ``?format=csv`` delivers all rows of the filtered view –
  not only the current page – with the shown columns (IMP-005);
  ``?format=csv&cols=all`` with every column the user may see.
* **Groups** (UIX-040). ``?group=status`` puts the rows under a heading per
  value of a column, with the number of rows of the group in the whole
  filtered list. The CSV file is not grouped. UIX-044: every shown
  column is offered under "Group by" – by a database path (``group``) where
  the column shows a field, else in Python by the column's value, for lists
  of at most :data:`PYTHON_SORT_MAX_ROWS` rows. Only a column of buttons or
  tick boxes is not offered, and says why (``Column.unsortable`` or
  ``Column.ungroupable``).
* **Two tables on one page** give one of them a ``prefix``; its parameters
  are then ``runs_sort``, ``runs_cols`` and so on (UIX-040).
* **Entries per page** (UIX-050; UIX-012): a list
  pages with :meth:`TableState.paginate` (or
  :func:`rentalars.core.listing.paginate`) and shows
  ``core/_pagination.html``; it then offers 25, 50, 100, 200 and any number
  from 5 to 1,000 (``?per_page=``), remembered per user and list.

Example::

    ITEMS = TableDefinition(
        "material_items",
        [
            Column("id", _("ID"), cell=lambda item: ..., text=lambda item: item.display_id,
                   sort="inventory_number", fixed=True),
            Column("status", _("Status"), cell=..., sort=("status", "inventory_number")),
            ...
        ],
        default_sort="id",
    )

    table = ITEMS.state(request)
    items = table.order(filtered_queryset)
    if table.wants_csv:
        return table.csv_response(items, "Material")
    page = table.paginate(items)
    ... render with {"table": table, "rows": table.rows(page), "page": page}
    ... and {% include "core/_pagination.html" %} below the table

A cell is HTML made with :func:`~django.utils.html.format_html`, never by
gluing strings, so a name like ``<Bühne>`` arrives as text.
"""

from __future__ import annotations

import csv
import datetime
import html
import io
import itertools
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import FieldDoesNotExist
from django.core.paginator import Page
from django.db.models import Case, Count, IntegerField, OrderBy, QuerySet, Subquery, Value, When
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.functional import Promise, lazy
from django.utils.html import format_html, format_html_join, strip_tags
from django.utils.safestring import SafeData, SafeString, mark_safe
from django.utils.text import slugify
from django.utils.translation import gettext

from rentalars.accounts.rights import Rights, request_rights
from rentalars.core.i18n import FILE_NAMES, local_pattern  # UIX-029
from rentalars.core.money import format_decimal, parse_decimal

#: Marks CSV text as UTF-8 for spreadsheet programs; without it umlauts arrive broken.
BYTE_ORDER_MARK = "﻿"

#: The most rows one CSV export delivers. 20,000 items fit comfortably; a
#: runaway query over some hundred thousand rows does not tie up a worker.
CSV_MAX_ROWS = 100_000

#: Records prepared and written at a time.
CSV_CHUNK_ROWS = 2000

#: UIX-015: the most rows a list sorts in Python by a computed column (the sums of a project, the
#: category-specific value). A longer list stays in its default order and says so (``TableState.sort_notice``).
PYTHON_SORT_MAX_ROWS = 2000

#: The most rows of a page that are chosen and acted on together (the pages hold at most 1,000 rows).
BULK_MAX_ROWS = 1000

#: Characters a spreadsheet program treats as the start of a formula.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class Column:
    """One column a list can show.

    Attributes:
        key: Short name used in the address (``?cols=``, ``?sort=``) and in
            the saved preference. Never changes once released.
        label: The heading.
        cell: Returns the content of the cell as HTML.
        text: Returns the value for the CSV file. Without it, the text of the
            cell without its markup is used.
        sort: Model fields (or query expressions, e.g. a ``Subquery`` for a
            multi-valued relation) to sort by. A function ``row -> value``
            sorts a queryset in Python – for computed values, only up to
            :data:`PYTHON_SORT_MAX_ROWS` rows. ``None`` makes the column
            unsortable, which UIX-015 allows only with ``unsortable``.
        unsortable: UIX-015: why a column cannot be sorted – a column of
            buttons or tick boxes. Every other column has a ``sort``; a test
            walks every table and holds it to that.
        sort_prepare: Called with all rows of the list (and the request)
            before they are sorted in Python by ``sort``, to load in one go
            what the sort value needs (the sums of the projects).
        default: Shown unless the user switched it off.
        css: CSS classes of the cells, e.g. ``"num"`` for right-aligned numbers.
        visible_if: A condition on the rights of the user, e.g. the right to
            see prices. A column the user may not see is neither shown nor
            exported nor offered.
        fixed: Always shown; identifies the row (the ID of an item, the
            number of a project).
        group: UIX-040: what the rows are grouped by when the user groups by
            this column (``?group=<key>``). For a queryset the model field
            (lookup path) whose value forms the groups, e.g. ``"status"`` or
            ``"project__number"`` – the database groups. A function
            ``row -> value`` groups in Python. UIX-044: ``None``
            groups in Python by the value the column shows (``text``, else the
            cell without markup). Grouping in Python works on a queryset of at
            most :data:`PYTHON_SORT_MAX_ROWS` rows; a longer list stays
            ungrouped and says so (``TableState.sort_notice``).
        group_value: The value of a row that matches what the database gives
            for ``group`` – needed where ``group`` is a transform such as
            ``"created_at__date"``. Without it the path is followed on the row.
        group_label: The heading of a group, made from its first row. Without
            it the cell of the column.
        ungroupable: UIX-044: why a column is not offered under
            "Group by". A column with ``unsortable`` (buttons, tick boxes) is
            not offered either; every other column is, and a test holds every
            table to that.
        export: ``False`` leaves the column out of CSV files – a column of
            buttons or tick boxes (UIX-040).

    A table over a plain list (not a queryset) sorts in Python: ``sort`` is
    then a function ``row -> value`` or the attribute path(s) to compare.
    """

    key: str
    label: Any
    cell: Callable[[Any], Any]
    text: Callable[[Any], Any] | None = None
    sort: str | tuple[Any, ...] | Callable[[Any], Any] | Any | None = None
    unsortable: str = ""
    sort_prepare: Callable[[list[Any], HttpRequest], None] | None = None
    default: bool = True
    css: str = ""
    visible_if: Callable[[Rights], bool] | None = None
    fixed: bool = False
    group: str | Callable[[Any], Any] | None = None
    group_value: Callable[[Any], Any] | None = None
    group_label: Callable[[Any], Any] | None = None
    ungroupable: str = ""
    export: bool = True

    @property
    def groupable(self) -> bool:
        """UIX-044: whether the column is offered under "Group by" – every column but buttons and tick boxes."""
        return not (self.ungroupable or self.unsortable)

    def html(self, row: Any) -> SafeString:
        """The cell content as safe HTML."""
        value = self.cell(row)
        if value is None:
            return mark_safe("")
        if isinstance(value, SafeString):
            return value
        return format_html("{}", value)

    def csv_value(self, row: Any) -> str:
        """The cell content for a CSV file."""
        # The text of the cell: without markup, and with "&amp;" and the like turned back into "&".
        value = self.text(row) if self.text is not None else html.unescape(strip_tags(str(self.html(row))))
        return csv_text(value)


def csv_text(value: Any) -> str:
    """Write a value the way a German spreadsheet program reads it.

    Dates as ``31.12.2027``, numbers with a decimal comma, nothing for
    ``None``. Text that a spreadsheet would run as a formula (``=HYPERLINK…``)
    gets a leading apostrophe: an exported list must not become a way to
    smuggle a formula onto somebody's desk ("CSV injection").
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        # UIX-029: in the language of the list.
        return gettext("yes") if value else gettext("no")
    if isinstance(value, datetime.datetime):
        return timezone.localtime(value).strftime(local_pattern("%d.%m.%Y %H:%M")) if timezone.is_aware(value) else ""
    if isinstance(value, datetime.date):
        return value.strftime(local_pattern("%d.%m.%Y"))
    if isinstance(value, Decimal | int | float):
        return format_decimal(Decimal(str(value)))
    text = " ".join(str(value).split())
    if text.startswith(_FORMULA_STARTS) and not _looks_like_number(text):
        return "'" + text
    return text


#: A plain number in a file for machines: ``-12.50``, ``+49 30``, ``1.234,50``.
_PLAIN_FILE_NUMBER = re.compile(r"^[+-]?[\d .,]*\d[\d .,]*$")


def formula_safe(value: Any) -> Any:
    """A text for a CSV file that a spreadsheet must not run as a formula (leading apostrophe); everything else as is.

    Numbers – also as text, such as ``-12.50`` – stay what they are, so a file keeps its figures readable.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS) and not _PLAIN_FILE_NUMBER.match(value):
        return "'" + value
    return value


def _looks_like_number(text: str) -> bool:
    """Whether a text is a plain number such as ``-12,50`` (those are no formula)."""
    try:
        parse_decimal(text)  # UIX-029: "-12.50" in English
    except ArithmeticError:
        return False
    return True


@dataclass
class Cell:
    """One cell: its CSS classes, its content and – for the narrow layout – the column's label."""

    css: str
    html: SafeString
    label: Any


@dataclass
class GroupHeading:
    """UIX-040: the heading above the first row of a group – its value and how many rows it holds."""

    label: SafeString
    count: int
    #: The number of shown columns, for ``colspan``.
    span: int


@dataclass
class TableRow:
    """One row as the template needs it: the record's key (for a tick box), its cells, its CSS classes."""

    pk: Any
    cells: list[Cell]
    css: str = ""
    #: UIX-040: set on the first row of a group (and on the first row of a page) when the table is grouped.
    group: GroupHeading | None = None


@dataclass
class HeaderCell:
    """A column heading as the template needs it."""

    column: Column
    url: str
    is_active: bool
    descending: bool

    @property
    def sortable(self) -> bool:
        """Whether the heading is a link that sorts."""
        return self.column.sort is not None


#: Every table by its key, for the view that saves a column choice.
REGISTRY: dict[str, TableDefinition] = {}


class TableDefinition:
    """The columns a list can show and its default sort order."""

    def __init__(
        self,
        key: str,
        columns: Sequence[Column],
        *,
        default_sort: str,
        row_css: Callable[[Any], str] | None = None,
        prepare: Callable[[list[Any]], None] | None = None,
        prefix: str = "",
        ungroupable: str = "",
    ) -> None:
        keys = [column.key for column in columns]
        if len(set(keys)) != len(keys):
            raise ValueError(f"Duplicate column keys in table {key}")
        if default_sort.lstrip("-") not in keys:
            raise ValueError(f"Default sort {default_sort} of table {key} is no column")
        if key in REGISTRY:
            raise ValueError(f"Two tables with the key {key}")
        self.key = key
        self.columns = list(columns)
        self.default_sort = default_sort
        #: CSS classes of a row, e.g. ``is-muted`` for a deactivated record.
        self.row_css = row_css
        #: Called with the records of a page or a CSV file before their cells
        #: are written, to load in one go what the cells of every row need.
        self.prepare = prepare
        #: UIX-040: put before the names in the address (``runs_sort``, ``runs_cols`` …) where a page shows
        #: two tables, so that sorting one does not sort the other.
        self.prefix = prefix
        #: UIX-044: why a table offers no "Group by" at all – a page that groups its rows itself.
        self.ungroupable = ungroupable
        #: MAT-073: functions giving columns known only when a page is shown, see
        #: :meth:`add_column_source`.
        self.column_sources: list[Callable[[], Sequence[Column]]] = []
        REGISTRY[key] = self

    def add_column_source(
        self, source: Callable[[], Sequence[Column]], *, prepare: Callable[[list[Any]], None] | None = None
    ) -> None:
        """Add columns that come from the database, e.g. the custom fields of the item list (MAT-073).

        ``source`` is asked for its columns whenever a page works out what it
        shows; their keys must differ from the table's own. ``prepare`` is
        called with the rows after the table's own ``prepare``, to load what
        the cells of these columns need in one go.
        """
        self.column_sources.append(source)
        if prepare is not None:
            before = self.prepare

            def prepare_both(records: list[Any]) -> None:
                if before is not None:
                    before(records)
                prepare(records)

            self.prepare = prepare_both

    def all_columns(self) -> list[Column]:
        """The table's own columns, then those of its column sources (MAT-073)."""
        if not self.column_sources:
            return self.columns
        own = {column.key for column in self.columns}
        extra = [column for source in self.column_sources for column in source() if column.key not in own]
        return [*self.columns, *extra]

    def param(self, name: str) -> str:
        """The name of a parameter of this table in the address: ``sort``, or ``runs_sort`` with a prefix."""
        return f"{self.prefix}{name}"

    def available(self, rights: Rights) -> list[Column]:
        """The columns this user may see."""
        return [column for column in self.all_columns() if column.visible_if is None or column.visible_if(rights)]

    def default_keys(self, rights: Rights) -> list[str]:
        """The columns shown when nothing was chosen."""
        return [column.key for column in self.available(rights) if column.default or column.fixed]

    def state(self, request: HttpRequest) -> TableState:
        """Work out what this request shows: columns and sort order."""
        rights = request_rights(request)
        available = self.available(rights)
        by_key = {column.key: column for column in available}
        chosen = self._chosen_keys(request, rights, by_key)
        shown = [column for column in available if column.key in chosen or column.fixed]
        sort = request.GET.get(self.param("sort"), self.default_sort)
        key = sort.lstrip("-")
        column = by_key.get(key)
        if column is None or column.sort is None:
            sort = self.default_sort
        # UIX-040: ``?group=status`` – only a column the user may see and that can group (UIX-044: all but buttons).
        group = by_key.get(request.GET.get(self.param("group"), ""))
        if group is not None and (self.ungroupable or not group.groupable):
            group = None
        return TableState(definition=self, request=request, available=available, columns=shown, sort=sort, group=group)

    def _chosen_keys(self, request: HttpRequest, rights: Rights, by_key: dict[str, Column]) -> set[str]:
        """The keys asked for in the address, saved by the user, or the default."""
        asked = request.GET.get(self.param("cols"), "")
        if asked == "all":
            return set(by_key)
        if asked:
            keys = {key for key in asked.split(",") if key in by_key}
            if keys:
                return keys
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            from rentalars.core.models import TablePreference

            saved = TablePreference.columns_of(user, self.key)
            if saved is not None:
                keys = {key for key in saved if key in by_key}
                if keys:
                    return keys
        return set(self.default_keys(rights))


@dataclass
class TableState:
    """A table as one request shows it."""

    definition: TableDefinition
    request: HttpRequest
    available: list[Column]
    columns: list[Column]
    sort: str
    #: UIX-040: the column the rows are grouped by, or ``None``.
    group: Column | None = None
    #: UIX-015: set when a computed column could not sort a list this long; the list keeps its default order.
    #: UIX-044: also when a list is too long to be grouped in Python; it is then not grouped.
    sort_notice: str = ""
    #: Whether every row of the shown page is a record with a key – only then can rows be ticked (``rows``).
    bulk_rows: bool = False

    @property
    def key(self) -> str:
        """The key of the table, for the form that saves the choice."""
        return self.definition.key

    @property
    def bulk_name(self) -> str:
        """The name of the tick boxes of the rows – and of the group of boxes the page script counts."""
        return f"sel_{self.definition.key}"

    @property
    def bulk_form(self) -> str:
        """The id of the bar with the actions for the ticked rows."""
        return f"bulk-{self.definition.key}"

    @property
    def selected_ids(self) -> set[int] | None:
        """The keys named by ``?only=`` (also ``?only=1,2,3``) – the rows a CSV file is limited to; else ``None``."""
        name = self.definition.param("only")
        if name not in self.request.GET:
            return None
        found: set[int] = set()
        for value in self.request.GET.getlist(name):
            if value.startswith("t:"):  # a long selection waits in the session (core.bulk.keep_selection)
                from rentalars.core.bulk import kept_selection

                found.update(kept_selection(self.request, value[2:]))
                continue
            for part in value.split(","):
                part = part.strip()
                if part.isascii() and part.isdigit() and len(part) < 12:
                    found.add(int(part))
                if len(found) >= BULK_MAX_ROWS:
                    return found
        return found

    @property
    def descending(self) -> bool:
        """Whether the order is reversed."""
        return self.sort.startswith("-")

    @property
    def sort_key(self) -> str:
        """The column the list is sorted by."""
        return self.sort.lstrip("-")

    @property
    def wants_csv(self) -> bool:
        """Whether the address asks for the CSV file instead of the page (IMP-005)."""
        return self.request.GET.get(self.definition.param("format")) == "csv"

    @property
    def shown_keys(self) -> set[str]:
        """The keys of the shown columns."""
        return {column.key for column in self.columns}

    @property
    def is_default(self) -> bool:
        """Whether the shown columns are the default ones."""
        return self.shown_keys == set(self.definition.default_keys(request_rights(self.request)))

    def order(self, queryset: Any) -> Any:
        """Sort a queryset by the chosen column, the primary key breaking ties.

        UIX-040: grouped, the rows are sorted by the group first, so that each
        group stands together, and by the chosen column within it. The CSV file
        is not grouped. A plain list (a table over computed rows) is sorted in
        Python and returned as a new list.

        UIX-044: a column without a database path groups in Python –
        a queryset of at most :data:`PYTHON_SORT_MAX_ROWS` rows becomes a
        list; a longer one stays ungrouped and :attr:`sort_notice` says why.
        """
        column = next(column for column in self.available if column.key == self.sort_key)
        group = None if self.wants_csv else self.group
        if not hasattr(queryset, "order_by"):
            return self._order_list(list(queryset), column, group)
        if group is not None and not isinstance(group.group, str):
            if queryset.order_by().count() > PYTHON_SORT_MAX_ROWS:
                self._add_notice(
                    gettext(
                        "Grouping by “%(column)s” needs a shorter list (at most %(count)s rows): narrow it down "
                        "with the filters. The list is shown without groups."
                    )
                    % {"column": strip_tags(str(group.label)), "count": PYTHON_SORT_MAX_ROWS}
                )
                self.group = None
                return self.order(queryset)
            records = list(self._order_queryset(queryset, column, None))
            return self._group_in_python(records, column, group, queryset)
        return self._order_queryset(queryset, column, group)

    def _order_queryset(self, queryset: Any, column: Column, group: Column | None) -> Any:
        """Sort a queryset by the chosen column – first by a group the database forms (UIX-040)."""
        if callable(column.sort) and not _is_expression(column.sort):
            return self._order_in_python(queryset, column, group)
        fields = column.sort if isinstance(column.sort, tuple) else (column.sort,)
        ordering = [_directed(name, descending=self.descending) for name in fields if name is not None and name != ""]
        if group is not None and isinstance(group.group, str):
            # The groups in the order of their column (customers by name, not by ID), each one together;
            # a field with choices in the order of its choices ("offen", "in Arbeit", "erledigt").
            # A day of a moment (``created_at__date``) is ordered by the moment itself: the days come in the
            # same order, and MariaDB without time zone tables gives no day at all (CONVERT_TZ is NULL).
            lead: list[Any] = [_moment_of_day(group.group) or group.group]
            choices = _choice_order(queryset.model, group.group)
            if choices is not None:
                lead.insert(0, choices)
            elif isinstance(group.sort, str | tuple):
                first = group.sort[0] if isinstance(group.sort, tuple) else group.sort
                if isinstance(first, str) and first and first.lstrip("-") != group.group:
                    lead.insert(0, first)
            if group is column and self.descending:
                lead = [name.desc() if hasattr(name, "desc") else _reversed(name) for name in lead]
            ordering = [*lead, *ordering]
        return queryset.order_by(*ordering, "pk")

    def _order_in_python(self, queryset: Any, column: Column, group: Column | None) -> Any:
        """UIX-015: sort a queryset by a computed column – as a list, if it is not too long.

        A longer list keeps the default order of the table and sets :attr:`sort_notice`, so that the
        page says why; filtering it shorter makes the column sort again.
        """
        if queryset.order_by().count() > PYTHON_SORT_MAX_ROWS:
            self._add_notice(
                gettext(
                    "Sorting by “%(column)s” needs a shorter list (at most %(count)s rows): narrow it down with the "
                    "filters. The list is shown in its usual order."
                )
                % {"column": strip_tags(str(column.label)), "count": PYTHON_SORT_MAX_ROWS}
            )
            self.sort = self.definition.default_sort
            fallback = next(each for each in self.available if each.key == self.sort_key)
            if callable(fallback.sort) and not _is_expression(fallback.sort):
                raise ValueError(f"The default sort of table {self.key} must be done by the database")
            return self.order(queryset)
        default = next(each for each in self.definition.columns if each.key == self.definition.default_sort.lstrip("-"))
        fields = default.sort if isinstance(default.sort, tuple) else (default.sort,)
        if callable(default.sort) and not _is_expression(default.sort):
            fields = ()
        # Equal values keep the default order of the table: Python's sort is stable.
        backwards = self.definition.default_sort.startswith("-")
        ordering = [_directed(name, descending=backwards) for name in fields if name is not None and name != ""]
        records = list(queryset.order_by(*ordering, "pk"))
        if column.sort_prepare is not None:
            column.sort_prepare(records, self.request)
        return self._order_list(records, column, group)

    def _order_list(self, records: list[Any], column: Column, group: Column | None) -> list[Any]:
        """Sort computed rows by the chosen column – and first by the group (UIX-040)."""
        ordered = sorted(records, key=_list_sort_key(column.sort), reverse=self.descending)
        if group is not None:
            return self._group_in_python(ordered, column, group, None)
        return ordered

    def _group_in_python(
        self, records: list[Any], column: Column, group: Column, queryset: QuerySet[Any] | None
    ) -> list[Any]:
        """UIX-040, UIX-044: put the rows of each group together, the groups in the order of their column.

        ``records`` come in the chosen order and keep it within each group (Python's sort is stable). A
        group stands where the first of its rows stands when the list is sorted by the group's column –
        by the database for a column it sorts (``queryset``), else in Python.
        """
        if group.sort_prepare is not None:
            group.sort_prepare(records, self.request)
        if group.group is None and group.group_value is None and self.definition.prepare is not None:
            self.definition.prepare(records)  # the cells – and so the values grouped by – may need it
        place: dict[Any, int] = {}
        for record in self._in_order_of(records, group, queryset):
            place.setdefault(self.group_key(record), len(place))
        return sorted(
            records, key=lambda record: place[self.group_key(record)], reverse=group is column and self.descending
        )

    def _in_order_of(self, records: list[Any], group: Column, queryset: QuerySet[Any] | None) -> list[Any]:
        """The records in the order of the group's column, its value breaking ties (UIX-044)."""
        if queryset is not None and group.sort is not None and (_is_expression(group.sort) or not callable(group.sort)):
            fields = group.sort if isinstance(group.sort, tuple) else (group.sort,)
            ordering = [_directed(name, descending=False) for name in fields if name is not None and name != ""]
            places = {
                pk: index for index, pk in enumerate(queryset.order_by(*ordering, "pk").values_list("pk", flat=True))
            }
            return sorted(records, key=lambda record: places.get(record.pk, len(places)))
        by_column = _list_sort_key(group.sort) if group.sort is not None else (lambda row: ())
        return sorted(records, key=lambda row: (by_column(row), _comparable(self.group_key(row))))

    def _add_notice(self, text: str) -> None:
        """Say above the list why a sort or a grouping was not done (UIX-015, UIX-044)."""
        self.sort_notice = f"{self.sort_notice} {text}" if self.sort_notice else text

    # --- Groups (UIX-040) ---------------------------------------------------------------------

    @property
    def group_param(self) -> str:
        """The name of the choice "Group by" in the address."""
        return self.definition.param("group")

    def group_choices(self) -> list[tuple[Column, bool]]:
        """The columns the rows can be grouped by, with whether it is the chosen one.

        UIX-044: every shown column in its order – and the chosen one, if it was switched off since –
        except buttons and tick boxes.
        """
        if self.definition.ungroupable:
            return []
        chosen = self.group.key if self.group is not None else ""
        shown = self.shown_keys | {chosen}
        return [(column, column.key == chosen) for column in self.available if column.key in shown and column.groupable]

    def kept_parameters(self) -> list[tuple[str, str]]:
        """What the address holds besides the grouping – for the small form that chooses it."""
        dropped = {self.group_param, "page", self.definition.param("page"), self.definition.param("format")}
        return [
            (name, value)
            for name in self.request.GET
            for value in self.request.GET.getlist(name)
            if name not in dropped
        ]

    def group_key(self, record: Any) -> Any:
        """The value a record is grouped by."""
        column = self.group
        if column is None:
            return None
        if column.group_value is not None:
            return column.group_value(record)
        if callable(column.group):
            return column.group(record)
        if column.group is None:
            return _shown_value(column, record)  # UIX-044
        return _value_at(record, column.group)

    def _group_heading(self, record: Any) -> SafeString:
        column = self.group
        assert column is not None
        label = column.group_label(record) if column.group_label is not None else column.html(record)
        if label is None or not strip_tags(str(label)).strip():
            return format_html('<span class="muted">{}</span>', gettext("(no entry)"))
        return label if isinstance(label, SafeString) else format_html("{}", label)

    def _group_counts(self, records: Any) -> dict[Any, int]:
        """How many rows each group holds in the whole filtered list – not only on this page."""
        source = records.paginator.object_list if isinstance(records, Page) else records
        column = self.group
        assert column is not None
        if isinstance(source, QuerySet) and isinstance(column.group, str):
            path = column.group
            moment = _moment_of_day(path)
            if moment is not None:
                # The day in the local time zone, worked out here rather than by the database (see ``order``).
                moments = source.model._base_manager.filter(pk__in=source.order_by().values("pk")).values_list(
                    moment, flat=True
                )
                return dict(Counter(timezone.localdate(value) if value else None for value in moments))
            counted = (
                source.model._base_manager.filter(pk__in=source.order_by().values("pk"))
                .order_by()
                .values(path)
                .annotate(rows=Count("pk"))
                .values_list(path, "rows")
            )
            return dict(counted)
        return dict(Counter(self.group_key(record) for record in source))

    def headers(self) -> list[HeaderCell]:
        """The headings of the shown columns with their sort links."""
        cells = []
        for column in self.columns:
            is_active = column.key == self.sort_key
            next_sort = f"-{column.key}" if is_active and not self.descending else column.key
            parameters = self.request.GET.copy()
            parameters[self.definition.param("sort")] = next_sort
            parameters.pop("page", None)
            parameters.pop(self.definition.param("page"), None)  # UIX-050: the page of a table with a prefix
            cells.append(
                HeaderCell(
                    column=column,
                    url=f"?{parameters.urlencode()}",
                    is_active=is_active,
                    descending=is_active and self.descending,
                )
            )
        return cells

    def rows(self, records: Iterable[Any]) -> list[TableRow]:
        """The cells of the shown columns for each record.

        On a phone the table turns into cards (``stack``); every cell but the
        first then shows its column label in front of the value.
        """
        row_css = self.definition.row_css
        counts = self._group_counts(records) if self.group is not None else None
        records = list(records)
        if self.definition.prepare is not None:
            self.definition.prepare(records)
        rows = [
            TableRow(
                pk=getattr(record, "pk", None),
                cells=[
                    # A label with markup (a heading only for screen readers, over buttons) shows no label in a card.
                    Cell(column.css, column.html(record), column.label if index and not _has_markup(column) else "")
                    for index, column in enumerate(self.columns)
                ],
                css=row_css(record) if row_css else "",
            )
            for record in records
        ]
        self.bulk_rows = bool(rows) and all(row.pk is not None for row in rows)
        if counts is not None:
            # UIX-040: a heading above the first row of each group, and above the first row of the page.
            previous: Any = object()
            for record, row in zip(records, rows, strict=True):
                value = self.group_key(record)
                if value != previous:
                    row.group = GroupHeading(self._group_heading(record), counts.get(value, 0), len(self.columns))
                    previous = value
        return rows

    def paginate(self, records: Any, *, default: int | None = None) -> Page[Any]:
        """One page of the ordered rows, as many as the user chose (UIX-050; UIX-012).

        25, 50, 100, 200 or a typed number from 5 to 1,000 (``?per_page=``, with the prefix of the table),
        remembered per user and list; ``core/_pagination.html`` shows the choice under the table.
        """
        from rentalars.core.listing import DEFAULT_PAGE_SIZE, paginate

        return paginate(self.request, records, prefix=self.definition.prefix, default=default or DEFAULT_PAGE_SIZE)

    def chooser(self) -> list[tuple[Column, bool]]:
        """The columns to offer in the chooser, with whether each is shown."""
        shown = self.shown_keys
        return [(column, column.key in shown) for column in self.available]

    def csv_url(self, *, every_column: bool = False) -> str:
        """The address of the CSV file of this view."""
        parameters = self.request.GET.copy()
        parameters[self.definition.param("format")] = "csv"
        parameters.pop("page", None)
        parameters.pop(self.definition.param("page"), None)
        if every_column:
            parameters[self.definition.param("cols")] = "all"
        return f"?{parameters.urlencode()}"

    @property
    def csv_url_all(self) -> str:
        """The address of the CSV file with every column the user may see."""
        return self.csv_url(every_column=True)

    def csv_text(self, records: Iterable[Any]) -> str:
        """All records as CSV text with the shown columns (IMP-005).

        Semicolons and decimal commas, as German spreadsheet programs expect.
        """
        text = io.StringIO()
        text.write(BYTE_ORDER_MARK)
        writer = csv.writer(text, delimiter=";")
        # UIX-040: columns of buttons or tick boxes are no data.
        columns = [column for column in self.columns if column.export]
        writer.writerow([strip_tags(str(column.label)) for column in columns])
        chosen = self.selected_ids
        if chosen is not None:
            records = _only(records, chosen)  # "Auswahl als CSV" – the view's own rows, limited to the ticked
        remaining = iter(itertools.islice(records, CSV_MAX_ROWS))
        # In parts, so that a long list never sits in memory as a whole.
        while chunk := list(itertools.islice(remaining, CSV_CHUNK_ROWS)):
            if self.definition.prepare is not None:
                self.definition.prepare(chunk)
            for record in chunk:
                writer.writerow([column.csv_value(record) for column in columns])
        return text.getvalue()

    def csv_response(self, records: Iterable[Any], name: str) -> HttpResponse:
        """The CSV file as a download named after the list and the day."""
        response = HttpResponse(self.csv_text(records), content_type="text/csv; charset=utf-8")
        filename = f"{slugify(name) or FILE_NAMES['list']}-{timezone.localdate():%Y-%m-%d}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


def _only(records: Any, keys: set[int]) -> Any:
    """The records with these keys – a queryset narrowed in the database, any other sequence in Python."""
    if isinstance(records, QuerySet) and not records.query.is_sliced:
        return records.filter(pk__in=keys)
    return (record for record in records if getattr(record, "pk", None) in keys)


def _reversed(field_name: str) -> str:
    """``name`` → ``-name`` and ``-name`` → ``name``: a column may sort descending by default."""
    return field_name[1:] if field_name.startswith("-") else f"-{field_name}"


def _is_expression(value: Any) -> bool:
    """Whether a sort entry is a query expression (``Subquery``, ``F() * F()`` …) rather than a function."""
    return hasattr(value, "resolve_expression")


def _directed(entry: Any, *, descending: bool) -> Any:
    """A sort entry of a column in the wanted direction: a field name or a query expression (UIX-015)."""
    if isinstance(entry, str):
        return _reversed(entry) if descending else entry
    if isinstance(entry, OrderBy):
        if not descending:
            return entry
        return OrderBy(entry.expression, descending=not entry.descending)
    return entry.desc() if descending else entry.asc()


def natural_key(value: Any) -> Any:
    """A sort key for text with numbers in it: ``5 m`` before ``10 m``, ``M8`` before ``M10`` (UIX-015)."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return value
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
        for part in re.split(r"(\d+)", value.strip())
        if part
    )


def first_value(queryset: QuerySet[Any], field: str) -> Subquery:
    """The smallest value of ``field`` among related rows – to sort by a multi-valued column (UIX-015).

    ``queryset`` is filtered with ``OuterRef``, e.g. the functions of a person; a column of several names
    sorts by the first of them in the alphabet.
    """
    return Subquery(queryset.order_by(field).values(field)[:1])


def grouped_by_day(path: str) -> dict[str, Any]:
    """UIX-044: the arguments of a column of moments that groups its rows by the local day.

    ``Column("time", ..., sort="timestamp", **grouped_by_day("timestamp"))``: the database forms the groups
    (``timestamp__date``), the heading is the day.
    """

    def day(record: Any) -> datetime.date | None:
        moment = _value_at(record, path)
        return timezone.localdate(moment) if moment else None

    return {"group": f"{path}__date", "group_value": day, "group_label": lambda record: date_text(day(record))}


def _moment_of_day(path: str) -> str | None:
    """UIX-040: ``"created_at"`` for a grouping path ``"created_at__date"``, else ``None``."""
    return path[: -len("__date")] if path.endswith("__date") else None


def _choice_order(model: Any, path: str) -> Any:
    """For a field with choices: an expression giving each value its place among the choices, else ``None``."""
    try:
        field = None
        for part in path.split("__"):
            field = model._meta.get_field(part)
            model = field.related_model
    except (FieldDoesNotExist, AttributeError):
        return None
    if field is None or field.is_relation or not field.choices:
        return None
    return Case(
        *(When(**{path: value}, then=Value(index)) for index, (value, _label) in enumerate(field.flatchoices)),
        default=Value(len(field.flatchoices)),
        output_field=IntegerField(),
    )


def _has_markup(column: Column) -> bool:
    """Whether a column's heading is HTML, e.g. ``<span class="visually-hidden">Aktionen</span>`` (UIX-040).

    A ``hidden_label`` counts too: a lazy text whose result is HTML (UIX-029).
    """
    return isinstance(column.label, SafeString) or hasattr(column.label, "__html__")


def _hidden_label(text: Any) -> SafeString:
    return format_html('<span class="visually-hidden">{}</span>', text)


#: UIX-029: a heading only screen readers say – over tick boxes and buttons. Lazy, so a table defined
#: at import time speaks the language of whoever reads it: ``hidden_label(_("Actions"))``.
hidden_label = lazy(_hidden_label, SafeString)


def _value_at(record: Any, path: str) -> Any:
    """Follow ``project__number`` on a record; a relation at the end gives its key, as ``values()`` does."""
    parts = path.split("__")
    target = record
    for part in parts[:-1]:
        target = getattr(target, part, None)
        if target is None:
            return None
    last = parts[-1]
    meta = getattr(target, "_meta", None)
    if meta is not None:
        try:
            field = meta.get_field(last)
        except FieldDoesNotExist:  # not a field: an attribute or a property
            field = None
        if field is not None and field.is_relation and getattr(field, "attname", None):
            return getattr(target, field.attname)
    return getattr(target, last, None)


def _shown_value(column: Column, record: Any) -> Any:
    """UIX-044: the value a column shows for a row – what it is grouped by without a ``group`` of its own.

    The value of the CSV column (``text``: a date stays a date) or the cell's text without markup; text with its
    spaces evened out, nothing for an empty cell.
    """
    value = column.text(record) if column.text is not None else html.unescape(strip_tags(str(column.html(record))))
    if isinstance(value, str | Promise):
        return " ".join(str(value).split()) or None
    try:
        hash(value)
    except TypeError:
        return str(value)
    return value


def _comparable(value: Any) -> tuple[bool, Any]:
    """A sort key that puts empty values last and ignores the case of text."""
    if value is None or value == "":
        return (True, "")
    if isinstance(value, str):
        return (False, value.lower())
    return (False, value)


def _list_sort_key(sort: Any) -> Callable[[Any], Any]:
    """The key function for sorting computed rows by a column (UIX-040)."""
    if callable(sort) and not _is_expression(sort):
        return lambda row: _comparable(sort(row))
    # Query expressions cannot be followed on a row; the field names of the column still sort the groups.
    paths = [
        name.lstrip("-") for name in (sort if isinstance(sort, tuple) else (sort,)) if isinstance(name, str) and name
    ]
    return lambda row: tuple(_comparable(_value_at(row, path)) for path in paths)


# --- Small helpers for cells ---------------------------------------------------------------------


def link(url: str, text: Any, css: str = "") -> SafeString:
    """A link as cell content."""
    if css:
        return format_html('<a class="{}" href="{}">{}</a>', css, url, text)
    return format_html('<a href="{}">{}</a>', url, text)


def badge(text: Any, colour: str = "") -> SafeString:
    """A coloured label, e.g. for a status."""
    return format_html('<span class="badge {}">{}</span>', colour, text)


#: UIX-005: what counts as markup in a stored text – a tag of a known HTML element whose attributes
#: all have a value, and comments. "Von Max <max@example.org>" or "a<b und c>d" are text, not tags.
_ELEMENTS = (
    "a|abbr|b|blockquote|body|br|caption|center|cite|code|col|colgroup|dd|del|div|dl|dt|em|figcaption|figure|font|"
    "footer|h[1-6]|head|header|hr|html|i|img|ins|kbd|li|link|mark|meta|nav|ol|p|pre|q|s|samp|script|section|small|"
    "span|strike|strong|style|sub|sup|table|tbody|td|tfoot|th|thead|title|tr|tt|u|ul|var|wbr"
)
_MARKUP = re.compile(
    r"<!--.*?-->|</?(?:" + _ELEMENTS + r")"
    r"(?:\s+[a-zA-Z_:][-\w:.]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))*\s*/?>",
    re.IGNORECASE | re.DOTALL,
)


def plain_text(value: Any) -> str:
    """A text without markup: tags left out, ``&amp;`` and the like turned back, no spaces at the ends (UIX-005).

    The tags are taken out first, the entities turned back afterwards – never the other way round, which would take
    an escaped "&lt;max@example.org&gt;" for a tag. Markup made by Rentalars (a safe string) is HTML through and
    through; a stored text, such as the text of a notification, is plain text that may hold a few tags: there only
    real tags go (:data:`_MARKUP`) – a "<" of the text stays, with what follows it.
    """
    text = str(value or "")
    text = strip_tags(text) if isinstance(value, SafeData) else _MARKUP.sub("", text)
    return html.unescape(text).strip()


def text_lines(value: Any) -> SafeString:
    """A text of several lines as cell content: plain text with its line breaks (UIX-005).

    Never wrapped in ``<p>`` – handed to :func:`~django.utils.html.format_html`, the paragraphs of
    ``linebreaks`` arrived escaped, as ``<p>…</p>`` to read.
    """
    return format_html_join(mark_safe("<br>"), "{}", ((line,) for line in plain_text(value).splitlines()))


def date_text(value: datetime.date | datetime.datetime | None) -> str:
    """A date as ``31.12.2027``; a moment in local time with the time of day."""
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return timezone.localtime(value).strftime(local_pattern("%d.%m.%Y %H:%M"))  # UIX-029
    return value.strftime(local_pattern("%d.%m.%Y"))
