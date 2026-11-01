# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 17 – Tagesmiete, Staffel und Aufpreis (catalogue chapter 11)."""

from decimal import Decimal

from rentalars.masterdata.models import RentalScale
from rentalars.products.models import BillingMode, ProductKind, SurchargeType
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.services import refresh_scale_versions, set_surcharge_targets, update_line
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    category,
    make_product,
    make_project,
    make_stock,
)


class Scenario17DailyRentalScaleAndSurcharge(RentalarsTestCase):
    """PRD-015, PRD-031, PRD-033 to PRD-039, PRJ-058."""

    def setUp(self) -> None:
        super().setUp()
        # Given: L-010 with a daily price of 20.00; scale 1 day = 1.0, 2 days = 1.5.
        self.spotlight = make_stock("L-010", 12, "LED-Scheinwerfer", price="20.00")
        self.project = make_project(rental_days=1)

    def amount(self, line) -> Decimal:
        return compute_project_prices(self.project).by_line_id[line.pk].amount

    def test_one_and_two_rental_days(self) -> None:
        line = add_line(self.project, self.spotlight, 4).line
        self.assertEqual(self.amount(line), Decimal("80.00"))

        line = update_line(line, rights=ALL_RIGHTS, rental_days=2).line

        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertEqual(price.amount, Decimal("120.00"))
        # The line shows days and factor; the scale is no surcharge line of its own.
        self.assertEqual((price.rental_days, price.scale_factor), (2, Decimal("1.5")))
        self.assertEqual(self.project.material_lines.count(), 1)

    def test_scale_of_the_category_wins_over_the_default(self) -> None:
        light_scale = RentalScale(name="Licht")
        light_scale.save()
        light_scale.publish([(1, Decimal("1.0")), (2, Decimal("1.6"))], extra_day_increment=Decimal("0.5"))
        light = category("L")
        light.rental_scale = light_scale
        light.save()
        self.spotlight.refresh_from_db()  # the product object still held the category without scale

        line = add_line(self.project, self.spotlight, 4, rental_days=2).line

        self.assertEqual(self.amount(line), Decimal("128.00"))

    def test_changing_the_days_recalculates_at_once(self) -> None:
        line = add_line(self.project, self.spotlight, 4, rental_days=2).line

        line = update_line(line, rights=ALL_RIGHTS, rental_days=1).line

        self.assertEqual(self.amount(line), Decimal("80.00"))

    def test_edited_scale_reaches_existing_lines_only_on_request(self) -> None:
        line = add_line(self.project, self.spotlight, 4, rental_days=2).line
        scale = RentalScale.get_default()

        scale.publish([(1, Decimal("1.0")), (2, Decimal("1.8"))], extra_day_increment=Decimal("0.5"))

        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[line.pk].amount, Decimal("120.00"))
        self.assertTrue(prices.by_line_id[line.pk].scale_is_outdated)

        self.assertEqual(refresh_scale_versions(self.project), 1)
        self.assertEqual(self.amount(line), Decimal("144.00"))

    def test_fixed_surcharge_raises_the_group(self) -> None:
        group = add_group(self.project, "Licht")
        add_line(self.project, self.spotlight, 4, group=group, rental_days=2)
        express = make_product("A-001", "Expresszuschlag", price="50.00", kind=ProductKind.SURCHARGE)

        add_line(self.project, express, 1, group=group)

        self.assertEqual(compute_project_prices(self.project).groups[0].subtotal, Decimal("170.00"))

    def test_flat_product_ignores_the_rental_days(self) -> None:
        stage = make_product("S-050", "Bühnenpodest pauschal", price="150.00", billing_mode=BillingMode.FLAT)

        line = add_line(self.project, stage, 1, rental_days=2).line

        self.assertEqual(self.amount(line), Decimal("150.00"))

    def test_percentage_surcharge_on_two_groups(self) -> None:
        flat = {"billing_mode": BillingMode.FLAT}
        front = add_group(self.project, "Front")
        add_line(self.project, make_product("L-020", price="420.00", **flat), 1, group=front)
        rear = add_group(self.project, "Rear")
        rear_line = add_line(self.project, make_product("L-021", price="310.00", **flat), 1, group=rear).line
        night = make_product(
            "A-002",
            "Nachtzuschlag",
            price=None,
            kind=ProductKind.SURCHARGE,
            surcharge_type=SurchargeType.PERCENT,
            surcharge_percent=Decimal("10"),
        )
        surcharge = add_line(self.project, night, 1).line

        set_surcharge_targets(surcharge, [{"type": "group", "id": front.pk}, {"type": "group", "id": rear.pk}])

        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[surcharge.pk].amount, Decimal("73.00"))
        # PRJ-058: it refers to several groups, so it stands in the project's block.
        self.assertEqual([price.line.pk for price in prices.surcharges], [surcharge.pk])
        self.assertEqual(prices.net_total, Decimal("803.00"))

        # If one of the groups changes, the surcharge follows.
        update_line(rear_line, rights=ALL_RIGHTS, unit_price=Decimal("410.00"))
        self.assertEqual(self.amount(surcharge), Decimal("83.00"))
