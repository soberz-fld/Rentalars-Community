# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 9 – Teilgruppen mit Preisen (catalogue chapter 11).

The parts of the scenario about the browser view and about users without the
price right are tested in ``tests/test_project_views.py`` and
``tests/api/test_projects_api.py``.
"""

from decimal import Decimal

from rentalars.projects.models import GroupKind
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.services import update_group
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_group, add_line, make_product, make_project, make_stock


class Scenario09GroupsWithPrices(RentalarsTestCase):
    """PRJ-033, PRJ-034, PRJ-039, PRJ-040, PRJ-042."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest 2027")
        flat = {"billing_mode": "flat"}
        self.front = add_group(self.project, "Licht Front-Traverse")
        add_line(self.project, make_product("L-001", price="100.00", **flat), 2, group=self.front)
        add_line(self.project, make_product("L-002", price="60.00", **flat), 2, group=self.front)
        add_line(self.project, make_product("L-003", price="100.00", **flat), 1, group=self.front)
        self.rear = add_group(self.project, "Licht Rear-Traverse")
        add_line(self.project, make_product("L-004", price="150.00", **flat), 1, group=self.rear)
        add_line(self.project, make_product("L-005", price="80.00", **flat), 2, group=self.rear)
        add_line(self.project, make_product("S-001", price="50.00", **flat), 1)

    def test_subtotals_and_project_total(self) -> None:
        prices = compute_project_prices(self.project)

        self.assertEqual([group.subtotal for group in prices.groups], [Decimal("420.00"), Decimal("310.00")])
        self.assertEqual(prices.ungrouped_total, Decimal("50.00"))
        self.assertEqual(prices.net_total, Decimal("780.00"))

    def test_ten_percent_discount_on_one_group(self) -> None:
        update_group(self.rear, rights=ALL_RIGHTS, discount_percent=Decimal("10"))

        prices = compute_project_prices(self.project)

        self.assertEqual(prices.groups[1].subtotal, Decimal("279.00"))
        self.assertEqual(prices.net_total, Decimal("749.00"))

    def test_optional_group_is_priced_but_not_added_to_the_total(self) -> None:
        fog = add_group(self.project, "Nebel", kind=GroupKind.OPTIONAL)
        add_line(self.project, make_product("S-002", price="80.00", billing_mode="flat"), 1, group=fog)

        prices = compute_project_prices(self.project)

        self.assertEqual(prices.groups[2].subtotal, Decimal("80.00"))
        self.assertEqual(prices.optional_total, Decimal("80.00"))
        self.assertEqual(prices.net_total, Decimal("780.00"))

    def test_same_product_in_two_groups_is_checked_together(self) -> None:
        spotlight = make_stock("L-010", 6, "LED-Scheinwerfer")

        first = add_line(self.project, spotlight, 4, group=self.front)
        second = add_line(self.project, spotlight, 4, group=self.rear)

        self.assertEqual(first.availability.shortage_total, 0)
        self.assertEqual(second.availability.shortage_total, 2)

    def test_tax_and_gross_total(self) -> None:
        prices = compute_project_prices(self.project)

        self.assertEqual(len(prices.tax_lines), 1)
        self.assertEqual(prices.tax_lines[0].net, Decimal("780.00"))
        self.assertEqual(prices.tax_total, Decimal("148.20"))
        self.assertEqual(prices.gross_total, Decimal("928.20"))
