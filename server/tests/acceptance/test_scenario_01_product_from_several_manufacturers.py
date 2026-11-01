# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 1 – Produkt aus mehreren Herstellern (catalogue chapter 11)."""

from rentalars.availability.stock import stock_of_product
from rentalars.material.models import ItemStatus
from rentalars.material.services import set_status
from tests.helpers import RentalarsTestCase, make_items, make_model, make_product


class Scenario01ProductFromSeveralManufacturers(RentalarsTestCase):
    """PRD-002, PRD-006, MAT-021: one product, material of two manufacturers."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_product("K-005", "XLR-Kabel 5 m")
        cordial = make_model("Cordial CPM 5 FM", self.product, manufacturer="Cordial")
        sommer = make_model("Sommer Cable Stage 22 5 m", self.product, manufacturer="Sommer Cable")
        self.items = make_items(cordial, 4) + make_items(sommer, 5)

    def test_stock_is_the_sum_over_all_models(self) -> None:
        self.assertEqual(stock_of_product(self.product.pk).total, 9)

    def test_defective_item_reduces_the_operational_stock(self) -> None:
        set_status(self.items[0], ItemStatus.DEFECTIVE, reason="Stecker abgerissen")

        stock = stock_of_product(self.product.pk)

        self.assertEqual(stock.total, 9)
        self.assertEqual(stock.operational, 8)
        self.assertEqual(stock.plannable, 8)
