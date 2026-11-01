# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 14 – Set und Einzelvermietung (catalogue chapter 11)."""

from rentalars.availability.engine import AvailabilityEngine
from rentalars.packing.services import build_overview, get_packlist
from rentalars.products.models import ProductKind
from rentalars.products.services import set_kit_components
from tests.helpers import RentalarsTestCase, add_line, at, make_product, make_project, make_stock


class Scenario14KitAndSingleRental(RentalarsTestCase):
    """PRD-004, PRD-022, VFG-008, PCK-005."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-010", 9, "XLR-Kabel 10 m")
        self.speaker = make_stock("T-010", 4, "Aktivbox")
        self.stand = make_stock("S-020", 6, "Boxenstativ")
        self.kit = make_product("T-100", "Aktivbox-Set", kind=ProductKind.KIT)
        set_kit_components(self.kit, [(self.speaker, 1), (self.stand, 1), (self.cable, 1)])
        self.project = make_project(start=at(10), end=at(12))
        add_line(self.project, self.kit, 3)
        add_line(self.project, self.cable, 5)

    def availability(self, *products):
        answers = AvailabilityEngine().availability([product.pk for product in products], at(10), at(12))
        return [answers[product.pk] for product in products]

    def test_kit_and_single_bookings_add_up(self) -> None:
        cable, speaker = self.availability(self.cable, self.speaker)

        self.assertEqual((cable.firm, cable.free), (8, 1))
        self.assertEqual(speaker.free, 1)

    def test_a_fourth_kit_fits(self) -> None:
        result = add_line(self.project, self.kit, 1)

        self.assertEqual(result.availability.status, "ok")

    def test_a_fifth_kit_is_short_of_one_speaker_and_one_cable(self) -> None:
        add_line(self.project, self.kit, 1)

        result = add_line(self.project, self.kit, 1)

        shortages = {detail.product_id: detail.shortage for detail in result.availability.shortages}
        self.assertEqual(shortages, {self.speaker.pk: 1, self.cable.pk: 1})

    def test_packlist_resolves_kits_into_components(self) -> None:
        rows = build_overview(get_packlist(self.project)).rows

        packed = sorted((row.product.article_number, int(row.required)) for row in rows)
        self.assertEqual(packed, [("K-010", 3), ("K-010", 5), ("S-020", 3), ("T-010", 3)])
        self.assertTrue(all(row.kit_title for row in rows if int(row.required) == 3))

    def test_kit_availability_follows_the_scarcest_component(self) -> None:
        (kit,) = self.availability(self.kit)

        self.assertEqual(kit.free, 1)
