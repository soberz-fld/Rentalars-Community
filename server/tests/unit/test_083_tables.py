# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "tables": every shown column can be chosen under "Gruppieren nach" (UIX-044).

The pages – grouping every list by each of its columns, the master-data lists – are tested in
``tests/ui/test_083_tables_pages.py``, the grouped tables in a browser in
``tests/browser/test_083_tables_in_browser.py``.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from rentalars.core.admin_tables import TableAdminMixin
from rentalars.core.tables import REGISTRY, Column, TableDefinition, grouped_by_day
from rentalars.masterdata.models import Category
from rentalars.projects.models import Project
from tests.helpers import RentalarsTestCase, make_project, make_user
from tests.unit.test_082_cleanup import every_table


class EveryColumnGroupsTests(SimpleTestCase):
    """UIX-044: every column of every table groups, or says why not – buttons and tick boxes only."""

    def test_every_column_of_every_table_groups_or_says_why_not(self) -> None:
        tables = every_table()
        self.assertGreater(len(tables), 30)
        excluded = []
        for key, table in tables.items():
            if key.startswith("test_"):
                continue  # tables made up by tests
            if table.ungroupable:
                excluded.append(f"{key} (table)")
                continue
            for column in table.columns:
                with self.subTest(table=key, column=column.key):
                    if column.groupable:
                        continue
                    self.assertTrue(column.ungroupable or column.unsortable, f"{key}.{column.key} needs a reason")
                    # Only buttons and fields are no data – they are left out of the CSV file as well.
                    self.assertFalse(column.export, f"{key}.{column.key}")
                    excluded.append(f"{key}.{column.key}")
        # The approval of times (one form per project) and the sums of the hours report group themselves.
        self.assertIn("time_approval (table)", excluded)
        self.assertIn("hours_report_sums (table)", excluded)
        self.assertLessEqual(len(excluded), 12, excluded)

    def test_grouped_by_day_names_the_day(self) -> None:
        arguments = grouped_by_day("created_at")
        self.assertEqual(arguments["group"], "created_at__date")
        moment = timezone.make_aware(datetime.datetime(2027, 3, 1, 23, 30))
        row = SimpleNamespace(created_at=moment)
        self.assertEqual(arguments["group_value"](row), datetime.date(2027, 3, 1))
        self.assertEqual(arguments["group_label"](row), "01.03.2027")
        self.assertEqual(arguments["group_label"](SimpleNamespace(created_at=None)), "")


class GroupChoiceTests(RentalarsTestCase):
    """UIX-044: "Gruppieren nach" lists the shown columns in their order – not the buttons."""

    def state(self, key: str, **parameters: str) -> Any:
        request = RequestFactory().get("/", parameters)
        request.user = make_user("chef", superuser=True)
        return REGISTRY[key].state(request)

    def test_the_choice_lists_the_shown_columns_in_their_order(self) -> None:
        state = self.state("projects", cols="status,name,customer")
        keys = [column.key for column, _chosen in state.group_choices()]
        self.assertEqual(keys, [column.key for column in state.columns])
        self.assertEqual(keys, ["number", "name", "customer", "status"])  # the fixed number, then the table's order

    def test_a_column_of_buttons_is_not_offered(self) -> None:
        state = self.state("automation_rules", cols="all", group="actions")
        self.assertIsNone(state.group)
        keys = [column.key for column, _chosen in state.group_choices()]
        self.assertNotIn("actions", keys)
        self.assertIn("runs", keys)  # a counted column groups by what it shows


class PythonGroupTests(RentalarsTestCase):
    """UIX-044: a column without a database path groups in Python – up to a length, else the list says so."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("chef", superuser=True)
        self.table = TableDefinition(
            "test_083_python_group",
            [
                Column("number", "Nummer", cell=lambda project: project.number, sort="number"),
                Column("name", "Name", cell=lambda project: project.name, sort="name"),
                # No ``group``: grouped by the value shown – the length of the name as a word.
                Column(
                    "size",
                    "Größe",
                    cell=lambda project: "kurz" if len(project.name) < 8 else "lang",
                    sort=lambda project: len(project.name) >= 8,
                ),
            ],
            default_sort="number",
        )
        self.addCleanup(REGISTRY.pop, "test_083_python_group")
        for name in ("Stadtfest groß", "Kurz", "Messe", "Ein sehr langes Projekt"):
            make_project(name)

    def state(self, **parameters: str) -> Any:
        request = RequestFactory().get("/", parameters)
        request.user = self.user
        return self.table.state(request)

    def test_the_rows_of_a_group_stand_together_with_its_count(self) -> None:
        state = self.state(group="size", sort="-name")
        records = state.order(Project.objects.all())
        self.assertIsInstance(records, list)
        # "kurz" before "lang" (the order of the column), within each group by the chosen sort.
        self.assertEqual(
            [project.name for project in records], ["Messe", "Kurz", "Stadtfest groß", "Ein sehr langes Projekt"]
        )
        rows = state.rows(records)
        headings = [(str(row.group.label), row.group.count) for row in rows if row.group is not None]
        self.assertEqual(headings, [("kurz", 2), ("lang", 2)])
        self.assertEqual(state.sort_notice, "")

    def test_grouped_by_the_column_itself_descending(self) -> None:
        records = self.state(group="size", sort="-size").order(Project.objects.all())
        self.assertEqual({project.name for project in records[:2]}, {"Stadtfest groß", "Ein sehr langes Projekt"})

    def test_a_long_list_is_not_grouped_and_says_why(self) -> None:
        state = self.state(group="size")
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 2):
            records = state.order(Project.objects.all())
        self.assertIsNone(state.group)
        self.assertIn("„Größe“", state.sort_notice)
        self.assertIn("höchstens 2", state.sort_notice)
        self.assertEqual(list(records), list(Project.objects.order_by("number")))
        self.assertTrue(all(row.group is None for row in state.rows(records)))

    def test_a_field_groups_in_the_database_however_long_the_list(self) -> None:
        self.table.columns[1] = Column("name", "Name", cell=lambda project: project.name, sort="name", group="name")
        state = self.state(group="name")
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 2):
            records = state.order(Project.objects.all())
        self.assertEqual(state.group.key, "name")
        self.assertEqual(state.sort_notice, "")
        self.assertTrue(hasattr(records, "query"))  # still a queryset: the database grouped

    def test_the_csv_file_is_not_grouped(self) -> None:
        state = self.state(group="size", format="csv")
        records = state.order(Project.objects.all())
        self.assertEqual(records[0].name, "Stadtfest groß")  # by number: as created


class MasterDataGroupTests(SimpleTestCase):
    """UIX-044 in the lists of the master data (Django's administration): every shown column groups."""

    def test_every_shown_column_is_offered_in_its_order(self) -> None:
        for model, model_admin in admin.site._registry.items():
            if not isinstance(model_admin, TableAdminMixin):
                continue
            request = RequestFactory().get("/")
            request.admin_table = {"cols": [], "group": ""}
            columns = [name for name in model_admin.get_list_display(request) if isinstance(name, str)]
            with self.subTest(model=model._meta.label):
                offered = model_admin.group_fields(request)
                self.assertEqual(offered[: len(columns)], columns)

    def test_the_path_of_a_category_groups_by_what_it_sorts_by(self) -> None:
        model_admin = admin.site._registry[Category]
        self.assertIsNone(model_admin.group_expression("code"))
        self.assertTrue(hasattr(model_admin.group_expression("path"), "resolve_expression"))
