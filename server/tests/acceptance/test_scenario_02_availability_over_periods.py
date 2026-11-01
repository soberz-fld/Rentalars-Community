# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 2 – Verfügbarkeit über Zeiträume (catalogue chapter 11)."""

from decimal import Decimal

from rentalars.availability.engine import AvailabilityEngine
from rentalars.availability.services import open_shortages
from rentalars.core.models import SystemSettings
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.services import accept_subrental_suggestion
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_line, at, make_project, make_stock


def days(first: int, last: int):
    """Return start and end for whole days, e.g. ``days(10, 12)`` = 10th 00:00 to 13th 00:00."""
    return at(first), at(last + 1)


class Scenario02AvailabilityOverPeriods(RentalarsTestCase):
    """VFG-002, VFG-004, VFG-005, VFG-018, PRJ-013, PRJ-054, PRJ-055."""

    def setUp(self) -> None:
        super().setUp()
        # Given: stock 9. Project P1 (confirmed) books 6 pieces from the 10th to the 12th.
        self.cable = make_stock("K-005", 9, "XLR-Kabel 5 m")
        start, end = days(10, 12)
        self.p1 = make_project("P1", start=start, end=end)
        add_line(self.p1, self.cable, 6)
        start, end = days(11, 13)
        self.p2 = make_project("P2", start=start, end=end)

    def free(self, start, end, *, exclude=None) -> int:
        answer = AvailabilityEngine().availability(
            [self.cable.pk], start, end, exclude_project_id=exclude.pk if exclude else None
        )
        return answer[self.cable.pk].free

    def test_overlapping_request_sees_three_free(self) -> None:
        self.assertEqual(self.free(*days(11, 13), exclude=self.p2), 3)

    def test_overbooking_is_saved_and_marked_as_shortage(self) -> None:
        result = add_line(self.p2, self.cable, 4)

        self.assertIsNotNone(result.line.pk, "the line is saved despite the shortage (PRJ-013)")
        self.assertEqual(result.availability.status, "short")
        self.assertEqual(result.availability.shortage_total, 1)

    def test_accepted_subrental_covers_the_shortage_without_raising_the_price(self) -> None:
        result = add_line(self.p2, self.cable, 4)
        price_before = compute_project_prices(self.p2).net_total

        subrental = accept_subrental_suggestion(result.line, self.cable, 1, rights=ALL_RIGHTS)

        self.assertEqual(subrental.product.category.effective_code, "E")
        self.assertEqual(subrental.covers_line, result.line)
        self.assertEqual((subrental.start, subrental.end), days(11, 13))
        self.assertEqual(subrental.quantity, Decimal("1"))
        self.assertEqual(compute_project_prices(self.p2).net_total, price_before)

    def test_covered_quantity_does_not_burden_the_own_stock(self) -> None:
        result = add_line(self.p2, self.cable, 4)
        accept_subrental_suggestion(result.line, self.cable, 1, rights=ALL_RIGHTS)

        # P2 now takes only 3 from the own stock: 6 + 3 = 9, so a third
        # project in the same period sees 0 free – not minus 1.
        self.assertEqual(self.free(*days(11, 12)), 0)
        self.assertEqual(open_shortages(), [])

    def test_without_buffer_the_material_is_free_right_after_the_return(self) -> None:
        # Default: no buffer. If P2 only starts on the 13th, all 9 are free.
        self.assertEqual(self.free(*days(13, 13)), 9)

    def test_with_one_day_of_buffer_the_material_is_blocked_a_day_longer(self) -> None:
        system_settings = SystemSettings.load()
        system_settings.buffer_after_hours = Decimal("24")
        system_settings.save()

        self.assertEqual(self.free(*days(13, 13)), 3)
        self.assertEqual(self.free(*days(14, 14)), 9)

    def test_times_are_compared_to_the_hour(self) -> None:
        # VFG-004: back at 10:00 does not block a project that starts at 14:00.
        morning = make_project("Vormittag", start=at(20, 6), end=at(20, 10))
        add_line(morning, self.cable, 9)

        self.assertEqual(self.free(at(20, 14), at(20, 22)), 9)
        self.assertEqual(self.free(at(20, 9), at(20, 22)), 0)
