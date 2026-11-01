# SPDX-License-Identifier: GPL-3.0-or-later
"""core.tables: groups, tables over computed rows, two tables on one page (UIX-040).

The pages are tested in ``tests/ui/test_081_ui_pages.py``; here the rules of the module itself.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.utils.html import format_html

from rentalars.core.listing import paginate
from rentalars.core.tables import Column, TableDefinition, _value_at
from rentalars.projects.models import Project, ProjectStatus
from tests.helpers import RentalarsTestCase, make_customer, make_project


@dataclass
class Row:
    """A computed row, as the open items or the inspections have them."""

    name: str
    kind: str
    amount: int
    day: datetime.date | None = None


ROWS = TableDefinition(
    "test_081_rows",
    [
        Column("name", "Name", cell=lambda row: row.name, sort="name", fixed=True),
        Column("kind", "Art", cell=lambda row: row.kind, sort=lambda row: row.kind, group=lambda row: row.kind),
        Column("amount", "Betrag", cell=lambda row: row.amount, sort="amount", css="num"),
        Column(
            "buttons",
            format_html('<span class="visually-hidden">{}</span>', "Aktionen"),
            cell=lambda row: format_html("<button>{}</button>", row.name),
            export=False,
            unsortable="buttons",  # UIX-044: neither sorted nor offered under "Group by"
        ),
    ],
    default_sort="name",
)

PROJECTS = TableDefinition(
    "test_081_projects",
    [
        Column("number", "Nummer", cell=lambda project: project.number, sort="number", fixed=True),
        Column("status", "Status", cell=lambda project: project.get_status_display(), sort="status", group="status"),
        Column(
            "customer",
            "Kunde",
            cell=lambda project: project.customer.name if project.customer_id else "",
            sort=("customer__name", "number"),
            group="customer",
        ),
    ],
    default_sort="number",
    prefix="p_",
)


class TablesTestCase(RentalarsTestCase):
    def request(self, **query: Any) -> Any:
        request = RequestFactory().get("/list/", query)
        request.user = AnonymousUser()
        return request


class ComputedRowsTests(TablesTestCase):
    """UIX-040: a table over a list sorts and groups in Python."""

    rows = [Row("Bühne", "Holz", 3), Row("anker", "Stahl", 1), Row("Cable", "Holz", 2), Row("Dübel", "", 5)]

    def test_sorted_by_a_column_ignoring_case(self) -> None:
        table = ROWS.state(self.request(sort="name"))
        self.assertEqual([row.name for row in table.order(self.rows)], ["anker", "Bühne", "Cable", "Dübel"])
        table = ROWS.state(self.request(sort="-amount"))
        self.assertEqual([row.amount for row in table.order(self.rows)], [5, 3, 2, 1])

    def test_grouped_with_counts_and_an_empty_group_named(self) -> None:
        table = ROWS.state(self.request(group="kind", sort="amount"))
        ordered = table.order(self.rows)
        # Empty values last; within a group by the chosen column.
        self.assertEqual([row.name for row in ordered], ["Cable", "Bühne", "anker", "Dübel"])
        rows = table.rows(ordered)
        headings = [(str(row.group.label), row.group.count, row.group.span) for row in rows if row.group]
        self.assertEqual(headings[:2], [("Holz", 2, 4), ("Stahl", 1, 4)])
        self.assertIn("(ohne Angabe)", headings[2][0])
        self.assertIsNone(rows[1].group)

    def test_the_counts_cover_the_whole_list_not_the_page(self) -> None:
        many = [Row(f"R{number:02d}", "A" if number < 30 else "B", number) for number in range(40)]
        request = self.request(group="kind", per_page="25", page="2")
        table = ROWS.state(request)
        page = paginate(request, table.order(many))
        rows = table.rows(page)
        self.assertEqual([(str(row.group.label), row.group.count) for row in rows if row.group], [("A", 30), ("B", 10)])

    def test_buttons_are_left_out_of_the_csv_and_their_heading_out_of_the_cards(self) -> None:
        table = ROWS.state(self.request())
        text = table.csv_text(self.rows)
        self.assertEqual(text.lstrip("﻿").splitlines()[0], "Name;Art;Betrag")
        self.assertNotIn("button", text)
        cells = table.rows(self.rows)[0].cells
        self.assertEqual(cells[1].label, "Art")
        self.assertEqual(cells[3].label, "")  # a heading only for screen readers shows no label in a card

    def test_every_column_but_the_buttons_can_be_chosen(self) -> None:
        """UIX-044: a column without ``group`` groups by what it shows."""
        self.assertEqual(ROWS.state(self.request(group="amount")).group.key, "amount")
        self.assertIsNone(ROWS.state(self.request(group="buttons")).group)
        choices = [column.key for column, _chosen in ROWS.state(self.request()).group_choices()]
        self.assertEqual(choices, ["name", "kind", "amount"])

    def test_the_value_of_a_path(self) -> None:
        customer = make_customer("Stadtwerke")
        project = make_project("Stadtfest", customer=customer)
        self.assertEqual(_value_at(project, "customer"), customer.pk)  # the key, as values() gives it
        self.assertEqual(_value_at(project, "customer__name"), "Stadtwerke")
        self.assertIsNone(_value_at(project, "parent__number"))
        self.assertEqual(_value_at(project, "status"), project.status)


class QuerysetGroupTests(TablesTestCase):
    """UIX-040: grouped in the database – in the order of the choices or the names; with a prefix."""

    def setUp(self) -> None:
        super().setUp()
        zeta, alpha = make_customer("Zeta GmbH"), make_customer("Alpha AG")
        make_project("A", status=ProjectStatus.CONFIRMED, customer=zeta)
        make_project("B", status=ProjectStatus.INQUIRY, customer=alpha)
        make_project("C", status=ProjectStatus.CONFIRMED, customer=alpha)

    def group(self, **query: Any) -> list[tuple[str, int]]:
        request = self.request(**query)
        table = PROJECTS.state(request)
        page = paginate(request, table.order(Project.objects.all()))
        return [(str(row.group.label), row.group.count) for row in table.rows(page) if row.group]

    def test_the_parameters_carry_the_prefix(self) -> None:
        self.assertEqual(self.group(group="status"), [])  # without the prefix: another table's choice
        self.assertEqual(self.group(p_group="status"), [("Anfrage", 1), ("Bestätigt", 2)])
        table = PROJECTS.state(self.request(p_sort="-number"))
        self.assertEqual(table.sort, "-number")
        self.assertIn("p_format=csv", table.csv_url())
        self.assertIn("p_cols=all", table.csv_url_all)
        self.assertEqual(table.group_param, "p_group")

    def test_choices_in_their_order_reversed_with_the_column(self) -> None:
        self.assertEqual(self.group(p_group="status", p_sort="-status"), [("Bestätigt", 2), ("Anfrage", 1)])

    def test_a_relation_in_the_order_of_its_names(self) -> None:
        self.assertEqual(self.group(p_group="customer"), [("Alpha AG", 2), ("Zeta GmbH", 1)])

    def test_the_csv_ignores_the_grouping(self) -> None:
        grouped = PROJECTS.state(self.request(p_group="status", p_format="csv"))
        plain = PROJECTS.state(self.request(p_format="csv"))
        self.assertTrue(grouped.wants_csv)
        self.assertEqual(
            grouped.csv_text(grouped.order(Project.objects.all())), plain.csv_text(plain.order(Project.objects.all()))
        )

    def test_the_chooser_keeps_the_other_parameters(self) -> None:
        table = PROJECTS.state(self.request(q="x", p_group="status", page="3", p_sort="number"))
        self.assertEqual(sorted(table.kept_parameters()), [("p_sort", "number"), ("q", "x")])
