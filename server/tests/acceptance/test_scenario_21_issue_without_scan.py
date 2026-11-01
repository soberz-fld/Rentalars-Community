# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 21 – Ausgabe ohne Scan (catalogue chapter 11)."""

from decimal import Decimal

from rentalars.material.models import ItemStatus, MaterialItem
from rentalars.packing.models import Allocation, PacklistStatus
from rentalars.packing.services import build_overview, get_packlist, issue, set_packed
from rentalars.projects.models import ProjectStatus
from tests.helpers import RentalarsTestCase, add_line, make_item, make_model, make_product, make_project, make_stock


class Scenario21IssueWithoutScan(RentalarsTestCase):
    """PCK-009, PCK-020, PCK-021, MAT-025."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9, "XLR-Kabel 5 m")
        self.rack_product = make_product("T-500", "Funkrack")
        self.rack = make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.project = make_project()
        self.cable_line = add_line(self.project, self.cable, 3).line
        self.rack_line = add_line(self.project, self.rack_product, 1).line
        self.packlist = get_packlist(self.project)

    def test_three_cables_are_packed_with_one_tick_and_issued(self) -> None:
        row = set_packed(self.packlist, self.cable_line.pk, self.cable.pk, Decimal("3"))
        self.assertTrue(row.is_packed)
        set_packed(self.packlist, self.rack_line.pk, self.rack_product.pk, Decimal("1"))

        issue(self.packlist, only_packed=True)  # PCK-025: "Ausgeben" books what is ticked

        self.packlist.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.packlist.status, PacklistStatus.ISSUED)
        self.assertEqual(self.project.status, ProjectStatus.OUT)
        issued = {row.product.article_number: row.issued for row in build_overview(self.packlist).rows}
        self.assertEqual(issued, {"K-005": Decimal("3"), "T-500": Decimal("1")})

    def test_single_rack_is_allocated_by_itself_and_gets_a_deployment_entry(self) -> None:
        issue(self.packlist)

        allocation = Allocation.objects.get(item=self.rack)
        self.assertEqual(allocation.entry.packlist.project, self.project)
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.IN_USE)

    def test_cables_get_no_item_history_and_nothing_is_blocked(self) -> None:
        issue(self.packlist)

        cable_items = MaterialItem.objects.for_product(self.cable.pk)
        self.assertFalse(Allocation.objects.filter(item__in=cable_items).exists())
        self.assertFalse(cable_items.exclude(status=ItemStatus.AVAILABLE).exists())
