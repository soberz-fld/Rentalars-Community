# SPDX-License-Identifier: GPL-3.0-or-later
"""Lines of the planning: PRJ-072, PRJ-075, DOK-010, PER-026.

* PRJ-072 – prices of products that changed since the lines took them over;
  the scale hint that left the planning broken.
* PRJ-075 – duplicating a line; optional and alternative lines.
* DOK-010 – the offer.
* PER-026 – the maximum discount of a job function, from every source a
  discount can come from.
"""

from __future__ import annotations

import datetime
import importlib
import xml.etree.ElementTree as ET
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError

from rentalars.accounts.rights import Rights
from rentalars.availability.engine import AvailabilityEngine
from rentalars.core.models import NumberRange
from rentalars.documents import content as builder
from rentalars.documents import services as documents
from rentalars.documents.models import Document, DocumentKind, DocumentTemplate
from rentalars.documents.views import MAKEABLE
from rentalars.documents.xrechnung import NAMESPACES
from rentalars.packing.services import build_overview, get_packlist
from rentalars.products.models import BillingMode, ProductKind
from rentalars.projects import crew
from rentalars.projects.lines import duplicate_line
from rentalars.projects.models import GroupKind, LineVariant, ProjectStatus
from rentalars.projects.planning import build_planning
from rentalars.projects.price_updates import old_prices, take_over_new_prices
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.services import (
    accept_subrental_suggestion,
    change_status,
    default_subrental_product,
    set_surcharge_targets,
    update_group,
    update_line,
)
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    add_line_before_071,
    at,
    job_function,
    make_customer,
    make_internal_project,
    make_item,
    make_model,
    make_person,
    make_product,
    make_project,
    make_stock,
    plan,
    ready_for_invoices,
)

D = Decimal

#: All modules, but no special right: no prices (AUT-019).
NO_PRICES = Rights(module_levels=dict(ALL_RIGHTS.module_levels), special_rights=frozenset())


def flat(article_number: str, price: str, **fields: object) -> object:
    """A product billed as a flat price: its amount is quantity × price, without rental days."""
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT, **fields)


def service(function: object, price: str) -> object:
    """The service product of a job function, billed flat – for personnel planned as a material line (PER-008).

    Every job function has its own service product (PRD-044), and a service can no longer become a
    new material line; lines from before stay, see ``add_line_before_071``.
    """
    product = function.service_product  # type: ignore[attr-defined]
    product.price, product.billing_mode = D(price), BillingMode.FLAT
    product.save()
    return product


# --- PRJ-075: optional and alternative lines -------------------------------------------------


class VariantPriceTests(RentalarsTestCase):
    """PRJ-075: optional and alternative lines are priced, but enter no sum."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht", discount_percent=D("10"))
        self.counting = add_line(self.project, flat("L-010", "100.00"), 1, group=self.group).line
        self.optional = add_line(
            self.project, flat("L-020", "50.00"), 1, group=self.group, variant=LineVariant.OPTIONAL
        ).line
        self.alternative = add_line(self.project, flat("L-030", "30.00"), 1, variant=LineVariant.ALTERNATIVE).line

    def test_optional_and_alternative_lines_are_priced_but_not_added_up(self) -> None:
        prices = compute_project_prices(self.project)
        group = prices.groups[0]
        # The group: 100.00 less 10 %; the optional 50.00 is neither summed nor discounted.
        self.assertEqual((group.lines_total, group.discount, group.subtotal), (D("100.00"), D("10.00"), D("90.00")))
        self.assertEqual(prices.by_line_id[self.optional.pk].amount, D("50.00"))
        self.assertFalse(prices.by_line_id[self.optional.pk].counts)
        self.assertEqual(prices.ungrouped_total, D("0.00"))
        self.assertEqual(prices.net_total, D("90.00"))
        self.assertEqual(sum(tax.net for tax in prices.tax_lines), D("90.00"))
        self.assertEqual((prices.optional_lines_total, prices.alternative_lines_total), (D("50.00"), D("30.00")))
        self.assertEqual(
            {line_price.line.pk for line_price in prices.variant_lines}, {self.optional.pk, self.alternative.pk}
        )
        self.assertEqual((prices.material_before_discount, prices.discount_total), (D("100.00"), D("10.00")))

    def test_group_summary_names_only_what_counts(self) -> None:
        """PRJ-066 with PRJ-075: "Contains:" of a group without lines does not promise the optional line."""
        self.assertEqual(build_planning(self.project).groups[0].summary, "1 × Produkt L-010")

    def test_a_line_that_becomes_normal_counts_again(self) -> None:
        update_line(self.optional, rights=ALL_RIGHTS, variant=LineVariant.NORMAL)
        self.assertEqual(compute_project_prices(self.project).net_total, D("135.00"))  # (100 + 50) − 10 %

    def test_percentage_surcharge_on_the_project_leaves_optional_lines_out(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        surcharge = add_line(self.project, night).line
        set_surcharge_targets(surcharge, [{"type": "project"}])
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[surcharge.pk].surcharge_base, D("90.00"))
        self.assertEqual(prices.net_total, D("99.00"))

    def test_surcharge_on_an_optional_line_counts_only_if_optional_itself(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        on_alternative = add_line(self.project, night).line
        set_surcharge_targets(on_alternative, [{"type": "line", "id": self.alternative.pk}])
        self.assertEqual(compute_project_prices(self.project).by_line_id[on_alternative.pk].surcharge_base, D("0.00"))
        update_line(on_alternative, rights=ALL_RIGHTS, variant=LineVariant.ALTERNATIVE)
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_line_id[on_alternative.pk].amount, D("3.00"))
        self.assertEqual(prices.alternative_lines_total, D("33.00"))
        self.assertEqual(prices.net_total, D("90.00"))

    def test_flat_price_of_a_group_ignores_its_optional_lines(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=None, flat_price=D("80.00"))
        prices = compute_project_prices(self.project)
        self.assertEqual((prices.groups[0].lines_total, prices.groups[0].subtotal), (D("100.00"), D("80.00")))
        self.assertEqual(sum(tax.net for tax in prices.tax_lines), D("80.00"))


class VariantReservationTests(RentalarsTestCase):
    """PRJ-075: an optional line reserves like an option, and is not packed."""

    def test_optional_line_reserves_softly_in_a_confirmed_project(self) -> None:
        lamp = make_stock("L-010", 6)
        project = make_project()
        add_line(project, lamp, 4, variant=LineVariant.OPTIONAL)
        answer = AvailabilityEngine().availability([lamp.pk], at(10), at(12))[lamp.pk]
        self.assertEqual((answer.firm, answer.optional, answer.free), (0, 4, 6))
        # Another project sees the collision with an option: tight, not short.
        verdict = add_line(make_project("Fest"), lamp, 5).availability
        self.assertEqual((verdict.status, verdict.shortage_total), ("tight", 0))

    def test_optional_line_does_not_take_stock_from_the_lines_that_count(self) -> None:
        lamp = make_stock("L-010", 6)
        project = make_project()
        add_line(project, lamp, 4, variant=LineVariant.ALTERNATIVE)
        counted = add_line(project, lamp, 6).availability
        self.assertEqual(counted.shortage_total, 0)

    def test_packlist_leaves_optional_and_alternative_lines_out(self) -> None:
        project = make_project()
        cable = make_stock("K-005", 10)
        add_line(project, cable, 2)
        add_line(project, make_stock("L-010", 4), 2, variant=LineVariant.OPTIONAL)
        rows = build_overview(get_packlist(project)).rows
        self.assertEqual([(row.product.article_number, row.required) for row in rows], [("K-005", D("2"))])


class DuplicateLineTests(RentalarsTestCase):
    """PRJ-075: a copy of a line directly below it."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.first = add_line(self.project, flat("L-010", "20.00"), 4, group=self.group).line
        self.second = add_line(self.project, flat("L-020", "15.00"), 2, group=self.group).line
        update_line(
            self.first,
            rights=ALL_RIGHTS,
            unit_price=D("18.00"),
            discount_percent=D("5"),
            note="Mit Torblenden",
            start=at(10, 8),
            end=at(11, 18),
        )

    def test_copy_stands_below_with_the_same_values(self) -> None:
        copy = duplicate_line(self.first, rights=ALL_RIGHTS).line
        order = list(self.group.lines.order_by("position").values_list("pk", flat=True))
        self.assertEqual(order, [self.first.pk, copy.pk, self.second.pk])
        for name in ("product_id", "quantity", "start", "end", "unit_price", "discount_percent", "note", "group_id"):
            self.assertEqual(getattr(copy, name), getattr(self.first, name), name)
        self.assertEqual(compute_project_prices(self.project).groups[0].lines_total, D("68.40") * 2 + D("30.00"))

    def test_the_copy_is_a_new_line_with_its_own_history(self) -> None:
        copy = duplicate_line(self.first, rights=ALL_RIGHTS).line
        self.assertNotEqual(copy.pk, self.first.pk)
        update_line(copy, rights=ALL_RIGHTS, variant=LineVariant.OPTIONAL)
        self.first.refresh_from_db()
        self.assertEqual(self.first.variant, LineVariant.NORMAL)

    def test_a_percentage_surcharge_keeps_its_targets(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        surcharge = add_line(self.project, night).line
        set_surcharge_targets(surcharge, [{"type": "group", "id": self.group.pk}])
        surcharge.refresh_from_db()
        copy = duplicate_line(surcharge, rights=ALL_RIGHTS).line
        self.assertEqual(
            [(target.target_type, target.target_group_id) for target in copy.surcharge_targets.all()],
            [("group", self.group.pk)],
        )

    def test_the_wish_for_an_item_is_not_copied_the_model_is(self) -> None:
        lamp = make_product("L-030", price="10.00")
        model = make_model("PAR 64", lamp)
        item = make_item(model, 4711)
        line = add_line(self.project, lamp, 1, preferred_item=item, preferred_model=model).line
        copy = duplicate_line(line, rights=ALL_RIGHTS).line
        self.assertEqual((copy.preferred_model_id, copy.preferred_item_id), (model.pk, None))

    def test_a_covering_subrental_is_not_duplicated(self) -> None:
        lamp = make_stock("L-040", 1)
        short = add_line(self.project, lamp, 3).line
        cover = accept_subrental_suggestion(short, lamp, 2, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            duplicate_line(cover, rights=ALL_RIGHTS)

    def test_closed_projects_are_locked(self) -> None:
        for status in (ProjectStatus.OUT, ProjectStatus.RETURNED, ProjectStatus.CLOSED):
            change_status(self.project, status, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            duplicate_line(self.first, rights=ALL_RIGHTS)


# --- PRJ-072: old prices ----------------------------------------------------------------------


class OldPriceTests(RentalarsTestCase):
    """PRJ-072: products whose price changed since the lines took it over."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(status=ProjectStatus.INQUIRY)
        self.lamp = flat("L-010", "20.00")
        self.line = add_line(self.project, self.lamp, 4, discount_percent=D("10")).line

    def raise_price(self, product: object, price: str) -> None:
        product.price = D(price)  # type: ignore[attr-defined]
        product.save()  # type: ignore[attr-defined]

    def test_line_remembers_the_price_it_took_over(self) -> None:
        self.assertEqual((self.line.unit_price, self.line.list_price), (D("20.00"), D("20.00")))
        self.assertEqual(build_planning(self.project).old_prices, [])

    def test_changed_product_price_is_pointed_out_and_taken_over(self) -> None:
        self.raise_price(self.lamp, "25.00")
        [old] = build_planning(self.project).old_prices
        self.assertEqual(
            (old.key, old.unit_price, old.new_price, old.set_by_hand),
            (f"m{self.line.pk}", D("20.00"), D("25.00"), False),
        )
        result = take_over_new_prices(self.project, rights=ALL_RIGHTS, automatic=True)
        self.assertEqual((result.taken_over, result.kept), (1, 0))
        self.line.refresh_from_db()
        self.assertEqual(
            (self.line.unit_price, self.line.list_price, self.line.discount_percent),
            (D("25.00"), D("25.00"), D("10.00")),
        )
        self.assertEqual(build_planning(self.project).old_prices, [])

    def test_confirmed_projects_keep_their_prices_without_a_hint(self) -> None:
        change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.raise_price(self.lamp, "25.00")
        self.assertEqual(build_planning(self.project).old_prices, [])
        # On request (API) the old prices are still known.
        self.assertEqual(len(old_prices(self.project)), 1)

    def test_option_shows_the_hint_too(self) -> None:
        change_status(self.project, ProjectStatus.OPTION, rights=ALL_RIGHTS)
        self.raise_price(self.lamp, "25.00")
        self.assertEqual(len(build_planning(self.project).old_prices), 1)

    def test_price_set_by_hand_is_left_alone_until_the_planner_decides(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, unit_price=D("17.00"))
        self.assertEqual(build_planning(self.project).old_prices, [])  # the product did not change
        self.raise_price(self.lamp, "25.00")
        [old] = build_planning(self.project).old_prices
        self.assertTrue(old.set_by_hand)
        self.assertEqual(take_over_new_prices(self.project, rights=ALL_RIGHTS, automatic=True).taken_over, 0)
        # Keeping the own price makes the hint go away …
        self.assertEqual(take_over_new_prices(self.project, rights=ALL_RIGHTS, keep=[old.key]).kept, 1)
        self.line.refresh_from_db()
        self.assertEqual((self.line.unit_price, self.line.list_price), (D("17.00"), D("25.00")))
        self.assertEqual(build_planning(self.project).old_prices, [])
        # … until the product's price changes again; then it can be taken over line by line.
        self.raise_price(self.lamp, "26.00")
        [old] = build_planning(self.project).old_prices
        take_over_new_prices(self.project, rights=ALL_RIGHTS, keys=[old.key])
        self.line.refresh_from_db()
        self.assertEqual(self.line.unit_price, D("26.00"))

    def test_everything_takes_over_hand_prices_too(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, unit_price=D("17.00"))
        self.raise_price(self.lamp, "25.00")
        self.assertEqual(take_over_new_prices(self.project, rights=ALL_RIGHTS, everything=True).taken_over, 1)

    def test_sold_lines_compare_with_the_sale_price(self) -> None:
        tape = make_product("V-001", "Gaffa", price=None, sale_price="8.00", kind=ProductKind.SALE)
        sold = add_line(self.project, tape, 3).line
        sold.refresh_from_db()
        self.assertEqual(sold.list_price, D("8.00"))
        tape.sale_price = D("9.50")
        tape.save()
        [old] = old_prices(self.project)
        self.assertEqual((old.line.pk, old.new_price), (sold.pk, D("9.50")))

    def test_crew_lines_follow_the_price_of_the_service_product(self) -> None:
        function = job_function("Stagehand", price="30.00")
        line = plan(self.project, function)
        self.assertEqual(line.list_price, D("30.00"))
        self.raise_price(function.service_product, "32.00")
        [old] = build_planning(self.project).old_prices
        self.assertEqual((old.key, old.is_crew, old.new_price), (f"c{line.pk}", True, D("32.00")))
        take_over_new_prices(self.project, rights=ALL_RIGHTS, keys=[old.key])
        line.refresh_from_db()
        self.assertEqual(line.unit_price, D("32.00"))

    def test_taking_over_needs_the_price_right_and_an_open_project(self) -> None:
        self.raise_price(self.lamp, "25.00")
        with self.assertRaises(ValidationError):
            take_over_new_prices(self.project, rights=NO_PRICES, automatic=True)
        with self.assertRaises(ValidationError):
            take_over_new_prices(self.project, rights=ALL_RIGHTS, keys=["m1"], keep=["m1"])

    def test_percentage_surcharges_and_covering_subrentals_are_not_looked_at(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        add_line(self.project, night)
        rental = default_subrental_product()
        lamp = make_stock("L-040", 1)
        accept_subrental_suggestion(add_line(self.project, lamp, 3).line, lamp, 2, rights=ALL_RIGHTS)
        self.raise_price(rental, "5.00")
        self.assertEqual([old.line.product.article_number for old in old_prices(self.project)], [])


# --- PER-026: maximum discount per job function -----------------------------------------------


class MaximumDiscountTests(RentalarsTestCase):
    """PER-026: no line of a job function gets more off than its maximum – whatever the source."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.sound = job_function("Tontechnik")
        self.engineer = service(self.sound, "100.00")
        self.sound.max_discount_percent = D("5")
        self.sound.save()
        self.group = add_group(self.project, "Ton")
        self.desk = add_line(self.project, flat("T-030", "400.00"), 1, group=self.group).line
        self.person_line = add_line_before_071(self.project, self.engineer, 1, group=self.group).line

    def prices(self) -> object:
        return compute_project_prices(self.project)

    def test_own_discount_of_a_line_is_cut_to_the_maximum(self) -> None:
        update_line(self.person_line, rights=ALL_RIGHTS, discount_percent=D("10"))
        price = self.prices().by_line_id[self.person_line.pk]  # type: ignore[attr-defined]
        self.assertEqual((price.discount_percent, price.discount_amount, price.amount), (D("5"), D("5.00"), D("95.00")))
        self.assertTrue(price.discount_is_capped)
        self.assertEqual(self.prices().capped_discount_lines, 1)  # type: ignore[attr-defined]

    def test_customers_standard_discount_is_cut_too(self) -> None:
        customer = make_customer("Rabattkunde")
        customer.default_discount_percent = D("10")
        customer.save()
        project = make_project("Mit Rabatt", customer=customer)
        line = add_line_before_071(project, self.engineer, 1).line
        self.assertEqual(line.discount_percent, D("10"))  # stored as typed: raising the maximum brings it back
        self.assertEqual(compute_project_prices(project).by_line_id[line.pk].amount, D("95.00"))

    def test_group_discount_in_percent_takes_only_what_the_maximum_leaves(self) -> None:
        """The worked example of ``projects.discounts``: 10 % on 500.00, the engineer may lose 5.00 only."""
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=D("10"))
        prices = self.prices()
        group = prices.groups[0]  # type: ignore[attr-defined]
        self.assertEqual((group.discount, group.cap_excess, group.subtotal), (D("45.00"), D("5.00"), D("455.00")))
        self.assertEqual(prices.by_line_id[self.person_line.pk].group_share, D("95.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("455.00"))  # type: ignore[attr-defined]
        self.assertEqual(sum(tax.net for tax in prices.tax_lines), D("455.00"))  # type: ignore[attr-defined]

    def test_group_discount_as_amount(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, discount_amount=D("100.00"))
        group = self.prices().groups[0]  # type: ignore[attr-defined]
        self.assertEqual((group.discount, group.subtotal), (D("85.00"), D("415.00")))

    def test_flat_price_is_raised_by_what_the_maximum_keeps(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, flat_price=D("400.00"))
        prices = self.prices()
        group = prices.groups[0]  # type: ignore[attr-defined]
        self.assertEqual((group.discount, group.subtotal), (D("85.00"), D("415.00")))
        self.assertEqual(prices.discount_total, D("85.00"))  # type: ignore[attr-defined]
        self.assertEqual(sum(tax.net for tax in prices.tax_lines), D("415.00"))  # type: ignore[attr-defined]

    def test_own_and_group_discount_together_stay_within_the_maximum(self) -> None:
        update_line(self.person_line, rights=ALL_RIGHTS, discount_percent=D("3"))
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=D("10"))
        prices = self.prices()
        # 97.00 after its own 3 %; down to 95.00 at most: the group may take 2.00 of it.
        self.assertEqual(prices.by_line_id[self.person_line.pk].group_share, D("95.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.groups[0].subtotal, D("455.00"))  # type: ignore[attr-defined]

    def test_zero_means_never_discounted_and_empty_means_no_limit(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=D("10"))
        self.sound.max_discount_percent = D("0")
        self.sound.save()
        self.assertEqual(self.prices().groups[0].subtotal, D("460.00"))  # type: ignore[attr-defined]
        self.sound.max_discount_percent = None
        self.sound.save()
        self.assertEqual(self.prices().groups[0].subtotal, D("450.00"))  # type: ignore[attr-defined]

    def test_the_job_function_of_the_service_product_counts(self) -> None:
        """A service product has exactly one job function (PRD-044): no other can take it."""
        other = job_function("Monitortechnik")
        other.service_product = self.engineer
        with self.assertRaises(ValidationError):
            other.full_clean()
        self.sound.max_discount_percent = D("2")
        self.sound.save()
        update_line(self.person_line, rights=ALL_RIGHTS, discount_percent=D("10"))
        self.assertEqual(self.prices().by_line_id[self.person_line.pk].amount, D("98.00"))  # type: ignore[attr-defined]

    def test_crew_line_discount_is_cut_to_the_maximum(self) -> None:
        stagehand = job_function("Stagehand", price="30.00")
        line = plan(self.project, stagehand, planned_hours=D("10"))
        crew.update_crew_line(line, rights=ALL_RIGHTS, discount_percent=D("20"))
        self.assertEqual(crew.price_crew_lines(self.project)[0].amount, D("240.00"))  # no limit: 300 − 20 %
        stagehand.max_discount_percent = D("5")
        stagehand.save()
        price = crew.price_crew_lines(self.project)[0]
        self.assertEqual((price.base_amount, price.discount_percent, price.amount), (D("300.00"), D("5"), D("285.00")))
        self.assertTrue(price.discount_is_capped)
        prices = self.prices()
        self.assertEqual(prices.personnel_total, D("285.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.discount_total, D("15.00"))  # type: ignore[attr-defined]

    def test_crew_lines_do_not_take_over_the_customers_standard_discount(self) -> None:
        """KND-006 stays a discount on material lines; a crew line starts without discount."""
        customer = make_customer("Rabattkunde")
        customer.default_discount_percent = D("10")
        customer.save()
        line = plan(make_project("Mit Rabatt", customer=customer), job_function("Stagehand", price="30.00"))
        self.assertEqual(line.discount_percent, D("0"))

    def test_discount_needs_the_price_right(self) -> None:
        line = plan(self.project, job_function("Stagehand", price="30.00"))
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=NO_PRICES, discount_percent=D("5"))


class MaximumDiscountDocumentTests(RentalarsTestCase):
    """PER-026: documents show the discount as it applies."""

    def setUp(self) -> None:
        super().setUp()
        customer = ready_for_invoices()
        self.project = make_project(customer=customer)
        stagehand = job_function("Stagehand", price="30.00")
        stagehand.max_discount_percent = D("5")
        stagehand.save()
        self.line = plan(self.project, stagehand, planned_hours=D("10"))
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, discount_percent=D("20"))
        add_line(self.project, flat("L-010", "100.00"), 1)

    def test_order_confirmation_shows_the_capped_discount(self) -> None:
        document = documents.create_document(self.project, DocumentKind.ORDER_CONFIRMATION)
        content = builder.from_json(document.content)
        personnel = next(section for section in content.sections if section.title == "Personal")
        position = personnel.positions[0]
        self.assertEqual(
            (position.discount_percent, position.base_amount, position.discount_amount, position.amount),
            (D("5.00"), D("300.00"), D("15.00"), D("285.00")),
        )
        self.assertEqual(document.net_total, D("385.00"))

    def test_invoice_carries_the_crew_discount_as_line_allowance(self) -> None:
        invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        self.assertEqual(invoice.net_total, D("385.00"))
        root = ET.fromstring(invoice.xml_file.read())
        cac, cbc = "{" + NAMESPACES["cac"] + "}", "{" + NAMESPACES["cbc"] + "}"
        allowances = [element.find(f"{cbc}Amount").text for element in root.iter(f"{cac}AllowanceCharge")]
        self.assertIn("15.00", allowances)
        totals = {child.tag.split("}")[1]: child.text for child in root.find(f"{cac}LegalMonetaryTotal")}
        self.assertEqual((totals["LineExtensionAmount"], totals["TaxExclusiveAmount"]), ("385.00", "385.00"))


# --- DOK-010: the offer ---------------------------------------------------------------------------


class OfferTests(RentalarsTestCase):
    """DOK-010: an offer before the order confirmation."""

    def setUp(self) -> None:
        super().setUp()
        customer = ready_for_invoices()
        self.project = make_project(customer=customer, status=ProjectStatus.INQUIRY)
        add_line(self.project, flat("L-010", "100.00"), 2)
        self.optional_group = add_group(self.project, "Nebel", kind=GroupKind.OPTIONAL)
        add_line(self.project, flat("S-010", "40.00"), 1, group=self.optional_group)
        add_line(self.project, flat("L-020", "25.00"), 1, variant=LineVariant.OPTIONAL)

    def test_offer_has_its_own_number_range_and_comes_first(self) -> None:
        self.assertEqual(MAKEABLE[0], DocumentKind.OFFER)
        self.assertEqual(NumberRange.objects.get(key="offer").prefix, "AN-{year}-")
        first = documents.create_document(self.project, DocumentKind.OFFER)
        second = documents.create_document(self.project, DocumentKind.OFFER)  # several offers per project
        self.assertEqual((first.number, second.number), ("AN-2027-0001", "AN-2027-0002"))
        self.assertTrue(first.is_priced)
        self.assertFalse(first.xml_file)  # no XRechnung for an offer

    def test_valid_for_fourteen_days_unless_said_otherwise(self) -> None:
        offer = documents.create_document(self.project, DocumentKind.OFFER)
        self.assertEqual(offer.valid_until, offer.issued_on + datetime.timedelta(days=14))
        self.assertIn(f"gilt bis zum {offer.valid_until:%d.%m.%Y}", offer.content["introduction"])
        chosen = documents.create_document(self.project, DocumentKind.OFFER, valid_until=datetime.date(2027, 4, 30))
        self.assertEqual(chosen.valid_until, datetime.date(2027, 4, 30))
        with self.assertRaises(ValidationError):
            documents.create_document(self.project, DocumentKind.OFFER, valid_until=datetime.date(2027, 2, 1))

    def test_priced_like_the_order_confirmation_with_optional_parts_marked(self) -> None:
        offer = documents.create_document(self.project, DocumentKind.OFFER)
        confirmation = documents.create_document(self.project, DocumentKind.ORDER_CONFIRMATION)
        self.assertEqual((offer.net_total, offer.gross_total), (confirmation.net_total, confirmation.gross_total))
        self.assertEqual(offer.net_total, D("200.00"))
        content = builder.from_json(offer.content)
        self.assertEqual([section.optional for section in content.sections], [True, False])
        variants = [position.variant for section in content.sections for position in section.positions]
        self.assertEqual(variants, ["", "", "optional"])
        self.assertEqual((content.optional_total, content.optional_lines_total), (D("40.00"), D("25.00")))
        self.assertEqual(len(content.positions), 1)  # what counts: neither the optional group nor the optional line

    def test_invoice_leaves_optional_lines_out(self) -> None:
        change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        content = builder.from_json(invoice.content)
        titles = [position.title for section in content.sections for position in section.positions]
        self.assertEqual(titles, ["Produkt L-010"])
        self.assertEqual(invoice.net_total, D("200.00"))

    def test_an_offer_needs_a_customer(self) -> None:
        self.assertTrue(documents.check_can_make(make_internal_project(), "offer"))

    def test_template_and_number_range_come_with_the_migration(self) -> None:
        DocumentTemplate.objects.filter(kind="offer").delete()
        NumberRange.objects.filter(key="offer").delete()
        migration = importlib.import_module("rentalars.documents.migrations.0001_squashed_0006_statements_090")
        migration.add_offer(django_apps, None)
        template = DocumentTemplate.objects.get(kind="offer")
        self.assertEqual(template.title, "Angebot")
        self.assertIn("{valid_until}", template.introduction)
        self.assertEqual(NumberRange.objects.get(key="offer").prefix, "AN-{year}-")
        self.assertEqual(documents.DEFAULT_TEMPLATES[DocumentKind.OFFER]["introduction"], template.introduction)

    def test_preview_stores_nothing(self) -> None:
        pdf = documents.preview(self.project, DocumentKind.OFFER, valid_until=datetime.date(2027, 3, 20))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertFalse(Document.objects.exists())


class PersonOnLineTests(RentalarsTestCase):
    """PER-026 with a planned person: the cost side is untouched by the discount."""

    def test_discount_lowers_the_price_not_the_cost(self) -> None:
        stagehand = job_function("Stagehand", price="30.00")
        person = make_person("Paul Packer", rates={"Stagehand": "18.00"})
        project = make_project()
        line = plan(project, stagehand, person, planned_hours=D("10"))
        crew.update_crew_line(line, rights=ALL_RIGHTS, discount_percent=D("10"))
        price = crew.price_crew_lines(project)[0]
        self.assertEqual((price.amount, price.cost), (D("270.00"), D("180.00")))
