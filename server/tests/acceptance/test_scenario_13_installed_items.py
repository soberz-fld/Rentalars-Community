# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 13 – Verbaute Exemplare (catalogue chapter 11).

The step in which item 0311 is released for the project belongs to MAT-042 (stage 5).
"""

from django.core.exceptions import ValidationError

from rentalars.availability.engine import AvailabilityEngine
from rentalars.availability.stock import stock_of_product
from rentalars.material.models import ConnectionType, ItemStatus
from rentalars.material.services import content_tree, install_item
from rentalars.packing.services import build_overview, extract, get_packlist, issue
from tests.helpers import RentalarsTestCase, add_line, at, make_item, make_model, make_product, make_project


class Scenario13InstalledItems(RentalarsTestCase):
    """MAT-033 to MAT-036, VFG-016, VFG-017, PCK-021."""

    def setUp(self) -> None:
        super().setUp()
        self.rack_product = make_product("T-500", "Funkrack")
        self.rack = make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.case_product = make_product("S-600", "Zubehörcase")
        self.case = make_item(make_model("Case groß", self.case_product), 600)
        self.receiver_product = make_product("T-050", "Funkempfänger")
        receiver_model = make_model("Sennheiser EM 300", self.receiver_product)
        self.r310 = make_item(receiver_model, 310)
        self.r311 = make_item(receiver_model, 311)
        self.r312 = make_item(receiver_model, 312)

    def free_receivers(self, start, end) -> int:
        return AvailabilityEngine().availability([self.receiver_product.pk], start, end)[self.receiver_product.pk].free

    def test_fixed_item_shows_as_content_and_leaves_the_plannable_stock(self) -> None:
        install_item(self.r310, self.rack, connection_type=ConnectionType.FIXED)

        self.assertEqual([item.display_id for _depth, item in content_tree(self.rack).depth_first], ["0310"])
        self.assertEqual(stock_of_product(self.receiver_product.pk).plannable, 2)

    def test_single_rack_is_allocated_by_itself_when_issued(self) -> None:
        install_item(self.r310, self.rack, connection_type=ConnectionType.FIXED)
        project = make_project()
        add_line(project, self.rack_product, 1)

        issue(get_packlist(project))

        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.IN_USE)
        self.assertEqual(self.rack.allocations.count(), 1)

    def test_loose_content_is_occupied_while_its_case_is_planned(self) -> None:
        install_item(self.r310, self.rack, connection_type=ConnectionType.FIXED)
        install_item(self.r311, self.case, connection_type=ConnectionType.LOOSE)
        project = make_project(start=at(10), end=at(12))
        add_line(project, self.case_product, 1)

        self.assertEqual(self.free_receivers(at(10), at(12)), 1)
        self.assertEqual(self.free_receivers(at(8), at(9)), 2)
        self.assertEqual(self.free_receivers(at(13), at(14)), 2)

    def test_taken_out_for_the_project_it_is_free_and_the_packlist_names_it(self) -> None:
        # MAT-042, stage 5
        install_item(self.r310, self.rack, connection_type=ConnectionType.FIXED)
        install_item(self.r311, self.case, connection_type=ConnectionType.LOOSE)
        project = make_project(start=at(10), end=at(12))
        add_line(project, self.case_product, 1)

        extract(project, self.r311)

        self.assertEqual(self.free_receivers(at(10), at(12)), 2)
        overview = build_overview(get_packlist(project), with_contents=True)
        case_row = overview.rows[0]
        self.assertIn("0311 Sennheiser EM 300 bleibt da (aus 0600 herausgelöst)", case_row.hints)
        self.assertEqual(
            [(content.display_id, content.state) for content in case_row.contents], [("0311", "extracted")]
        )

    def test_circular_and_unknown_references_are_rejected(self) -> None:
        install_item(self.r310, self.rack, connection_type=ConnectionType.FIXED)

        with self.assertRaises(ValidationError) as rejected:
            install_item(self.rack, self.r310)
        self.assertIn("installed_in", rejected.exception.message_dict)

    def test_fixed_item_marked_rentable_behaves_like_a_loose_one(self) -> None:
        # MAT-041
        install_item(self.r310, self.rack, connection_type=ConnectionType.FIXED, individually_rentable=True)

        self.assertEqual(stock_of_product(self.receiver_product.pk).plannable, 3)
        project = make_project(start=at(10), end=at(12))
        add_line(project, self.rack_product, 1)
        self.assertEqual(self.free_receivers(at(10), at(12)), 2)
