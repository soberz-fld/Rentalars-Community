# SPDX-License-Identifier: GPL-3.0-or-later
"""Price calculation: billing modes, groups, surcharges, tax (PRD-033 ff., PRJ-024, PRJ-039)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.masterdata.models import RentalScale, TaxRate
from rentalars.products.models import Product
from rentalars.projects.models import GroupKind
from rentalars.projects.pricing import (
    DaysSource,
    compute_project_prices,
    resolve_rental_days,
    resolve_rental_days_with_source,
)
from rentalars.projects.services import (
    accept_subrental_suggestion,
    set_surcharge_targets,
    update_group,
    update_line,
    update_project,
)
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_group, add_line, at, make_product, make_project, make_stock

D = Decimal


class BillingModeTests(RentalarsTestCase):
    """How the amount of one line is calculated (PRD-033)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=2)

    def amount(self, line: object) -> Decimal:
        """The calculated net amount of a line."""
        return compute_project_prices(self.project).by_line_id[line.pk].amount  # type: ignore[attr-defined]

    def test_daily_rental_uses_days_and_scale(self) -> None:
        """PRD-014."""
        line = add_line(self.project, make_product("L-010", price="20.00"), 4).line
        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertEqual((price.rental_days, price.scale_factor, price.amount), (2, D("1.500"), D("120.00")))

    def test_days_beyond_the_table_add_the_increment(self) -> None:
        """Default scale (ADM-011): 1 → 1.0, 2 → 1.5 … 7 → 3.5, then +0.3 per further day."""
        line = add_line(self.project, make_product("L-010", price="20.00"), 1, rental_days=9).line
        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertEqual(price.scale_factor, D("4.100"))
        self.assertEqual(price.amount, D("82.00"))

    def test_scale_factor_set_by_hand_wins(self) -> None:
        """PRD-036."""
        line = add_line(self.project, make_product("L-010", price="20.00"), 4, manual_scale_factor=D("1.2")).line
        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertEqual(price.amount, D("96.00"))
        self.assertFalse(price.scale_is_outdated)

    def test_product_without_scale_counts_every_day_fully(self) -> None:
        """ "no scale" means every day counts in full – 2 days of 4 × 20.00 are 160.00, not 80.00."""
        product = make_product("L-010", price="20.00", rental_scale_mode="none")
        line = add_line(self.project, product, 4).line
        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertEqual((price.rental_days, price.scale_factor, price.amount), (2, D("2"), D("160.00")))

    def test_product_with_its_own_scale(self) -> None:
        scale = RentalScale.objects.create(name="Lichtstaffel")
        scale.publish([(1, D("1")), (2, D("1.8"))], extra_day_increment=D("0.8"))
        product = make_product("L-010", price="20.00", rental_scale_mode="custom", rental_scale=scale)
        self.assertEqual(self.amount(add_line(self.project, product, 1).line), D("36.00"))

    def test_kit_is_charged_per_kit_and_day(self) -> None:
        kit = make_product("T-100", kind="kit", billing_mode="daily_kit", price="40.00")
        self.assertEqual(self.amount(add_line(self.project, kit, 2).line), D("120.00"))

    def test_flat_ignores_the_rental_days(self) -> None:
        transport = make_product("F-001", kind="incidental", billing_mode="flat", price="95.00")  # PRD-045
        line = add_line(self.project, transport, 2).line
        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertIsNone(price.rental_days)
        self.assertEqual(price.amount, D("190.00"))

    def test_hourly_multiplies_quantity_hours_and_price(self) -> None:
        technician = make_product("N-001", kind="incidental", billing_mode="hourly", price="45.00")
        self.assertEqual(self.amount(add_line(self.project, technician, 2, hours=D("8")).line), D("720.00"))

    def test_effort_is_an_estimate_until_the_real_quantity_is_entered(self) -> None:
        """PRD-033: billing by effort marks the amount as estimated."""
        kilometres = make_product("F-002", kind="incidental", billing_mode="effort", price="0.80")
        line = add_line(self.project, kilometres, 120).line
        prices = compute_project_prices(self.project)
        self.assertTrue(prices.by_line_id[line.pk].is_estimate)
        self.assertTrue(prices.has_estimates)
        self.assertEqual(prices.net_total, D("96.00"))

        update_line(line, rights=ALL_RIGHTS, quantity=D("134"), quantity_is_estimate=False)
        prices = compute_project_prices(self.project)
        self.assertFalse(prices.has_estimates)
        self.assertEqual(prices.net_total, D("107.20"))

    def test_sale_uses_the_sale_price_without_days(self) -> None:
        """PRD-013."""
        tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=D("14.90"))
        line = add_line(self.project, tape, 3).line
        self.assertTrue(line.is_sale)
        self.assertEqual(self.amount(line), D("44.70"))

    def test_rental_product_sold_before_keeps_its_price(self) -> None:
        """PRD-017: a rental product could be sold as well.

        PRD-047: a rental product has no sale price any more; a line that sold it before
        keeps its price (PRJ-015), a new sale is refused – see tests/unit/test_091_products.py.
        """
        cable = make_product("K-005", price="1.50")
        Product.objects.filter(pk=cable.pk).update(sale_price=D("12.00"))  # as was allowed earlier
        cable.refresh_from_db()
        rented = add_line(self.project, cable, 2).line
        sold = add_line(self.project, cable, 2, is_sale=True).line
        Product.objects.filter(pk=cable.pk).update(sale_price=None)  # products/0009_one_price_091
        sold.refresh_from_db()
        rented.product.refresh_from_db()
        self.assertEqual(self.amount(rented), D("4.50"))
        self.assertEqual(self.amount(sold), D("24.00"))
        with self.assertRaises(ValidationError):
            update_line(rented, rights=ALL_RIGHTS, is_sale=True)

    def test_line_discount(self) -> None:
        line = add_line(self.project, make_product("L-010", price="20.00"), 4, discount_percent=D("12.5")).line
        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertEqual(
            (price.base_amount, price.discount_amount, price.amount), (D("120.00"), D("15.00"), D("105.00"))
        )

    def test_price_is_copied_and_later_product_changes_leave_the_line_alone(self) -> None:
        """PRJ-015."""
        product = make_product("L-010", price="20.00")
        line = add_line(self.project, product, 1).line
        product.price = D("99.00")
        product.save()
        self.assertEqual(self.amount(line), D("30.00"))


class RentalDaysTests(RentalarsTestCase):
    """Which rental days apply (PRJ-005, PRD-034)."""

    def test_line_beats_group_beats_project_beats_suggestion(self) -> None:
        project = make_project(
            start=at(10, 8), end=at(14, 18), event_start=at(11, 10), event_end=at(13, 23), rental_days=None
        )
        group = add_group(project, "Licht")
        line = add_line(project, make_product("L-010"), 1, group=group).line
        self.assertEqual(project.suggested_rental_days, 3)
        self.assertEqual(resolve_rental_days(line, group, project), 3)
        project.rental_days = 4
        self.assertEqual(resolve_rental_days(line, group, project), 4)
        group.rental_days = 2
        self.assertEqual(resolve_rental_days(line, group, project), 2)
        line.rental_days = 1
        self.assertEqual(resolve_rental_days(line, group, project), 1)

    def test_without_event_period_the_reservation_period_is_used_for_the_suggestion(self) -> None:
        project = make_project(start=at(10), end=at(12), rental_days=None)
        self.assertEqual(project.effective_rental_days, 2)
        short = make_project("Kurz", start=at(10, 8), end=at(10, 20), rental_days=None)
        self.assertEqual(short.effective_rental_days, 1)

    def test_a_line_with_a_period_of_its_own_is_charged_the_days_of_that_period(self) -> None:
        """PRJ-062: every started 24 hours of the line's own period count as one day."""
        project = make_project(start=at(10, 8), end=at(12, 18), rental_days=2)
        group = add_group(project, "Vorbau", rental_days=5)
        lamp = make_product("L-010", price="20.00")
        line = add_line(project, lamp, 1, group=group).line
        self.assertEqual(resolve_rental_days_with_source(line, group, project), (5, DaysSource.GROUP))

        # One day: 10 March 08:00 to 11 March 08:00.
        line.start, line.end = at(10, 8), at(11, 8)
        self.assertEqual(resolve_rental_days_with_source(line, group, project), (1, DaysSource.PERIOD))
        # One minute more starts the second day.
        line.end = at(11, 8, 1)
        self.assertEqual(resolve_rental_days(line, group, project), 2)
        # Typed in on the line: wins over its period.
        line.rental_days = 4
        self.assertEqual(resolve_rental_days_with_source(line, group, project), (4, DaysSource.LINE))

    def test_lines_that_move_with_the_project_keep_the_days_of_the_project(self) -> None:
        """PRJ-062: only a period that *differs* from the project's counts as the line's own."""
        project = make_project(start=at(10, 8), end=at(12, 18), rental_days=2)
        line = add_line(project, make_product("L-010", price="20.00"), 1).line
        update_project(project, start=at(9, 8), end=at(15, 18))
        line.refresh_from_db()
        self.assertEqual((line.start, line.end), (project.start, project.end))
        self.assertEqual(resolve_rental_days_with_source(line, None, project), (2, DaysSource.PROJECT))

    def test_the_price_follows_the_period_of_the_line(self) -> None:
        """PRJ-062 with the scale of scenario 17: 2 days factor 1.5, 1 day factor 1."""
        project = make_project(start=at(10, 8), end=at(12, 18), rental_days=2)
        scale = RentalScale.objects.create(name="Lichtstaffel kurz")
        scale.publish([(1, D("1")), (2, D("1.5"))], extra_day_increment=D("0.25"))
        lamp = make_product("L-010", price="20.00", rental_scale_mode="custom", rental_scale=scale)
        line = add_line(project, lamp, 4).line
        self.assertEqual(compute_project_prices(project).by_line_id[line.pk].amount, D("120.00"))

        result = update_line(line, rights=ALL_RIGHTS, start=at(10, 8), end=at(11, 8))
        price = compute_project_prices(project).by_line_id[result.line.pk]
        self.assertEqual((price.rental_days, price.rental_days_source, price.amount), (1, "period", D("80.00")))

    def test_rental_days_and_reservation_period_are_independent(self) -> None:
        """The period decides about availability, the days about the price."""
        project = make_project(start=at(1), end=at(20), rental_days=1)
        line = add_line(project, make_product("L-010", price="20.00"), 1).line
        self.assertEqual(compute_project_prices(project).by_line_id[line.pk].amount, D("20.00"))


class GroupPriceTests(RentalarsTestCase):
    """Discount, flat price and kinds of groups (PRJ-039, PRJ-040)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=1)
        self.group = add_group(self.project, "Licht")
        flat = {"billing_mode": "flat"}
        add_line(self.project, make_product("L-001", price="100.00", **flat), 2, group=self.group)
        add_line(self.project, make_product("L-002", price="110.00", **flat), 1, group=self.group)

    def test_discount_as_amount_never_goes_below_zero(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, discount_amount=D("60.00"))
        prices = compute_project_prices(self.project)
        self.assertEqual((prices.groups[0].discount, prices.groups[0].subtotal), (D("60.00"), D("250.00")))
        update_group(self.group, rights=ALL_RIGHTS, discount_amount=D("999.00"))
        prices = compute_project_prices(self.project)
        self.assertEqual((prices.groups[0].discount, prices.groups[0].subtotal), (D("310.00"), D("0.00")))

    def test_flat_price_replaces_the_sum_of_the_lines(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, flat_price=D("250.00"))
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.groups[0].lines_total, D("310.00"))
        self.assertEqual(prices.groups[0].subtotal, D("250.00"))
        self.assertEqual(prices.groups[0].discount, D("60.00"))
        self.assertEqual(prices.net_total, D("250.00"))
        self.assertEqual(prices.discount_total, D("60.00"))

    def test_flat_price_above_the_lines_is_no_discount(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, flat_price=D("400.00"))
        prices = compute_project_prices(self.project)
        self.assertEqual((prices.groups[0].subtotal, prices.groups[0].discount), (D("400.00"), D("0.00")))

    def test_flat_priced_group_without_lines_is_taxed_at_the_default_rate(self) -> None:
        empty = add_group(self.project, "Pauschale Technik", flat_price=D("500.00"))
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id, prices.by_line_id)
        self.assertEqual(prices.groups[1].group, empty)
        self.assertEqual(prices.net_total, D("810.00"))
        self.assertEqual(prices.tax_total, D("153.90"))

    def test_alternative_group_is_priced_but_not_added(self) -> None:
        alternative = add_group(self.project, "Alternative: LED statt Halogen", kind=GroupKind.ALTERNATIVE)
        add_line(self.project, make_product("L-003", price="180.00", billing_mode="flat"), 1, group=alternative)
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.groups[1].subtotal, D("180.00"))
        self.assertEqual(prices.optional_total, D("180.00"))
        self.assertEqual(prices.net_total, D("310.00"))

    def test_fixed_surcharge_inside_a_group_raises_its_subtotal(self) -> None:
        """Scenario 17: A-001 "Expresszuschlag" lifts 310.00 to 360.00."""
        express = make_product("A-001", "Expresszuschlag", kind="surcharge", billing_mode="flat", price="50.00")
        add_line(self.project, express, 1, group=self.group)
        prices = compute_project_prices(self.project)
        self.assertEqual(
            (prices.groups[0].lines_total, prices.groups[0].surcharges_total, prices.groups[0].subtotal),
            (D("310.00"), D("50.00"), D("360.00")),
        )

    def test_group_discount_does_not_reduce_surcharges_in_the_group(self) -> None:
        express = make_product("A-001", kind="surcharge", billing_mode="flat", price="50.00")
        add_line(self.project, express, 1, group=self.group)
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=D("10"))
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.groups[0].subtotal, D("329.00"))  # 310 − 31 + 50


class PercentSurchargeTests(RentalarsTestCase):
    """Percentage surcharges and what they refer to (PRD-031, PRD-039, PRJ-058)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=1)
        flat = {"billing_mode": "flat"}
        self.front = add_group(self.project, "Front")
        self.front_line = add_line(
            self.project, make_product("L-001", price="420.00", **flat), 1, group=self.front
        ).line
        self.rear = add_group(self.project, "Rear")
        add_line(self.project, make_product("L-002", price="310.00", **flat), 1, group=self.rear)
        self.loose = add_line(self.project, make_product("S-001", price="50.00", **flat), 1).line
        self.night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )

    def surcharge(self, *targets: dict[str, object]) -> object:
        """Add the 10 % surcharge with the given targets."""
        line = add_line(self.project, self.night, 1).line
        set_surcharge_targets(line, list(targets))
        return line

    def test_on_two_groups_stands_in_the_project_block(self) -> None:
        """Scenario 17: 10 % of 420.00 + 310.00 = 73.00."""
        line = self.surcharge({"type": "group", "id": self.front.pk}, {"type": "group", "id": self.rear.pk})
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[line.pk].amount, D("73.00"))  # type: ignore[attr-defined]
        self.assertEqual([price.line.pk for price in prices.surcharges], [line.pk])  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("853.00"))

    def test_on_one_group_moves_into_that_group(self) -> None:
        """PRJ-058: a surcharge on a single group belongs to its subtotal."""
        line = self.surcharge({"type": "group", "id": self.front.pk})
        line.refresh_from_db()  # type: ignore[attr-defined]
        self.assertEqual(line.group, self.front)  # type: ignore[attr-defined]
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.groups[0].subtotal, D("462.00"))
        self.assertEqual(prices.surcharges, [])

    def test_follows_its_base_after_discounts(self) -> None:
        """PRD-039: the percentage is taken after discounts."""
        line = self.surcharge({"type": "group", "id": self.front.pk}, {"type": "group", "id": self.rear.pk})
        update_group(self.rear, rights=ALL_RIGHTS, discount_percent=D("10"))
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[line.pk].surcharge_base, D("699.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.by_line_id[line.pk].amount, D("69.90"))  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("818.90"))

    def test_on_the_whole_project_never_counts_other_surcharges(self) -> None:
        express = make_product("A-001", kind="surcharge", billing_mode="flat", price="100.00")
        add_line(self.project, express, 1)
        line = self.surcharge({"type": "project"})
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[line.pk].surcharge_base, D("780.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("958.00"))  # 780 + 100 + 78

    def test_on_a_single_line_in_a_discounted_group_takes_the_reduced_amount(self) -> None:
        update_group(self.front, rights=ALL_RIGHTS, discount_percent=D("50"))
        line = self.surcharge({"type": "line", "id": self.front_line.pk})
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[line.pk].surcharge_base, D("210.00"))  # type: ignore[attr-defined]

    def test_optional_group_adds_nothing_to_a_project_level_surcharge(self) -> None:
        fog = add_group(self.project, "Nebel", kind=GroupKind.OPTIONAL)
        add_line(self.project, make_product("S-002", price="80.00", billing_mode="flat"), 1, group=fog)
        line = self.surcharge({"type": "group", "id": self.front.pk}, {"type": "group", "id": fog.pk})
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[line.pk].amount, D("42.00"))  # type: ignore[attr-defined]

    def test_without_target_the_surcharge_is_zero_and_says_so(self) -> None:
        line = add_line(self.project, self.night, 1).line
        price = compute_project_prices(self.project).by_line_id[line.pk]
        self.assertEqual(price.amount, D("0.00"))
        self.assertEqual(price.surcharge_target_labels, [])

    def test_own_percentage_on_the_line(self) -> None:
        line = add_line(self.project, self.night, 1, surcharge_percent=D("25")).line
        set_surcharge_targets(line, [{"type": "line", "id": self.loose.pk}])
        self.assertEqual(compute_project_prices(self.project).by_line_id[line.pk].amount, D("12.50"))


class TaxAndCostTests(RentalarsTestCase):
    """Tax per rate and the contribution margin (PRJ-024, PRJ-025)."""

    def test_net_is_split_by_tax_rate(self) -> None:
        project = make_project(rental_days=1)
        tax_free = TaxRate.objects.get(rate=0)
        add_line(project, make_product("L-001", price="100.00", billing_mode="flat"), 1)
        add_line(
            project,
            make_product(
                "V-001", kind="sale", billing_mode="flat", price=None, sale_price=D("10.00"), tax_rate=tax_free
            ),
            3,
        )
        prices = compute_project_prices(project)
        by_rate = {str(line.tax_rate.rate): (line.net, line.tax) for line in prices.tax_lines}
        self.assertEqual(by_rate, {"19.00": (D("100.00"), D("19.00")), "0.00": (D("30.00"), D("0.00"))})
        self.assertEqual(
            (prices.net_total, prices.tax_total, prices.gross_total), (D("130.00"), D("19.00"), D("149.00"))
        )

    def test_group_discount_is_spread_over_the_tax_rates(self) -> None:
        project = make_project(rental_days=1)
        tax_free = TaxRate.objects.get(rate=0)
        group = add_group(project, "Gemischt", discount_percent=D("10"))
        add_line(project, make_product("L-001", price="100.00", billing_mode="flat"), 1, group=group)
        add_line(project, make_product("L-002", price="50.00", billing_mode="flat", tax_rate=tax_free), 1, group=group)
        prices = compute_project_prices(project)
        by_rate = {str(line.tax_rate.rate): line.net for line in prices.tax_lines}
        self.assertEqual(by_rate, {"19.00": D("90.00"), "0.00": D("45.00")})
        self.assertEqual(sum(by_rate.values()), prices.net_total)

    def test_rounding_never_loses_a_cent(self) -> None:
        """The parts per tax rate always add up to the net total exactly."""
        project = make_project(rental_days=1)
        tax_free = TaxRate.objects.get(rate=0)
        group = add_group(project, "Pauschal", flat_price=D("100.00"))
        for number, rate in enumerate([None, None, tax_free], 1):
            fields = {"tax_rate": rate} if rate else {}
            add_line(
                project, make_product(f"L-00{number}", price="33.33", billing_mode="flat", **fields), 1, group=group
            )
        prices = compute_project_prices(project)
        self.assertEqual(sum((line.net for line in prices.tax_lines), D("0")), D("100.00"))

    def test_subrental_costs_and_contribution_margin(self) -> None:
        """PRJ-055, PRJ-025: the customer price stays, the cost is internal."""
        cable = make_stock("K-005", 2, price="10.00")
        project = make_project(rental_days=1)
        line = add_line(project, cable, 5).line
        before = compute_project_prices(project).net_total
        accept_subrental_suggestion(line, cable, 3, rights=ALL_RIGHTS, purchase_price=D("4.00"))
        prices = compute_project_prices(project)
        self.assertEqual(prices.net_total, before)
        self.assertEqual(prices.subrental_cost, D("12.00"))
        self.assertEqual(prices.contribution_margin, D("38.00"))

    def test_subrental_planned_for_the_customer_is_charged_normally(self) -> None:
        """PRJ-018: foreign material that the customer pays for."""
        project = make_project(rental_days=1)
        subrental = make_product("E-002", "Zumietung LED-Wand", kind="subrental", billing_mode="flat", price="0.00")
        add_line(project, subrental, 1, title="LED-Wand 3 × 2 m", unit_price=D("900.00"), purchase_price=D("650.00"))
        prices = compute_project_prices(project)
        self.assertEqual(
            (prices.net_total, prices.subrental_cost, prices.contribution_margin),
            (D("900.00"), D("650.00"), D("250.00")),
        )
