# SPDX-License-Identifier: GPL-3.0-or-later
"""Nested groups (PRJ-037): tree, rules, prices, availability, copies, templates, packlists, documents.

The worked example of ``projects.pricing`` is built here as :class:`Lighting`::

    Group "Licht"          lighting desk        450.00
      "Front"              3 × 140.00  420.00   (tax free)
      "Rear"               2 × 155.00  310.00
                           10 % discount - 31.00  279.00
                           together            1149.00
                           5 % discount        - 57.45
    Subtotal "Licht"                           1091.55
    Without group                                50.00
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.availability.engine import AvailabilityEngine
from rentalars.documents import services as documents
from rentalars.documents.content import from_json
from rentalars.documents.models import DocumentKind
from rentalars.documents.xrechnung import NAMESPACES
from rentalars.masterdata.models import TaxRate
from rentalars.packing.services import build_overview, get_packlist
from rentalars.products.models import BillingMode
from rentalars.projects import mvr
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.grouptree import MAX_DEPTH, GroupTree
from rentalars.projects.models import Group, GroupKind, MaterialLine, ProjectTemplate
from rentalars.projects.planning import build_patch, build_planning
from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_pdf
from rentalars.projects.pricing import DaysSource, compute_project_prices
from rentalars.projects.project_templates import CONTENT_VERSION, apply_template, capture, save_as_template
from rentalars.projects.services import (
    copy_group,
    delete_group,
    move_group,
    reorder_groups,
    set_surcharge_targets,
    update_group,
)
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    add_line_before_071,
    at,
    job_function,
    make_product,
    make_project,
    make_stock,
    ready_for_invoices,
)
from tests.unit.test_mvr_import import SKYPANEL, read, sample_plot

D = Decimal


def flat(article_number: str, price: str, **fields: object) -> object:
    """A product billed as a flat price: its amount is quantity × price."""
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT, **fields)


def names(groups: list[Group]) -> list[str]:
    return [group.name for group in groups]


class TreeRuleTests(RentalarsTestCase):
    """PRJ-037: positions among siblings, at most three levels, no cycles."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.light = add_group(self.project, "Licht")
        self.front = add_group(self.project, "Front", parent=self.light)
        self.truss = add_group(self.project, "Traverse 1", parent=self.front)
        self.sound = add_group(self.project, "Ton")

    def tree(self) -> GroupTree:
        return GroupTree(self.project.groups.all())

    def test_positions_count_among_siblings_and_the_tree_reads_like_a_table_of_contents(self) -> None:
        rear = add_group(self.project, "Rear", parent=self.light)
        self.assertEqual(
            [(group.name, group.position) for group in (self.light, self.front, self.truss, self.sound, rear)],
            [("Licht", 1), ("Front", 1), ("Traverse 1", 1), ("Ton", 2), ("Rear", 2)],
        )
        tree = self.tree()
        self.assertEqual(names(tree.ordered), ["Licht", "Front", "Traverse 1", "Rear", "Ton"])
        self.assertEqual([tree.depth[group.pk] for group in tree.ordered], [0, 1, 2, 1, 0])
        truss = tree.by_id[self.truss.pk]
        self.assertEqual(tree.path(truss), "Licht › Front › Traverse 1")
        self.assertEqual(names(tree.ancestors(truss)), ["Front", "Licht"])
        self.assertEqual(names(tree.descendants(tree.by_id[self.light.pk])), ["Front", "Traverse 1", "Rear"])
        self.assertEqual(tree.height(tree.by_id[self.light.pk]), 3)

    def test_walking_up_a_tree_costs_no_query(self) -> None:
        tree = self.tree()
        with self.assertNumQueries(0):
            self.assertEqual(tree.by_id[self.truss.pk].path, "Licht › Front › Traverse 1")
            self.assertEqual(tree.by_id[self.truss.pk].depth, 2)

    def test_at_most_three_levels(self) -> None:
        self.assertEqual(MAX_DEPTH, 3)
        with self.assertRaises(ValidationError) as caught:
            add_group(self.project, "Zu tief", parent=self.truss)
        self.assertIn("parent", caught.exception.message_dict)
        self.assertIn("höchstens 3 Ebenen", caught.exception.message_dict["parent"][0])
        # A group with a subgroup cannot go below a group on the second level either.
        with self.assertRaises(ValidationError):
            move_group(self.light, parent=self.sound)
        with self.assertRaises(ValidationError):
            move_group(self.front, parent=add_group(self.project, "Rear", parent=self.light))
        self.assertEqual(Group.objects.get(pk=self.front.pk).parent, self.light)

    def test_no_group_inside_itself_or_its_own_subgroups(self) -> None:
        for target in (self.light, self.front, self.truss):
            with self.subTest(target=target.name), self.assertRaises(ValidationError) as caught:
                move_group(self.light, parent=target)
            self.assertIn("parent", caught.exception.message_dict)
        self.assertIsNone(Group.objects.get(pk=self.light.pk).parent)

    def test_a_parent_of_another_project_is_refused(self) -> None:
        foreign = add_group(make_project("Anderes"), "Fremd")
        with self.assertRaises(ValidationError) as caught:
            add_group(self.project, "Licht 2", parent=foreign)
        self.assertIn("parent", caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            move_group(self.sound, parent=foreign)

    def test_moving_into_another_group_renumbers_both_sides(self) -> None:
        rear = add_group(self.project, "Rear", parent=self.light)
        side = add_group(self.project, "Seite", parent=self.light)
        move_group(self.sound, parent=self.light, position=2)
        self.assertEqual(
            [(group.name, group.position) for group in self.light.children.order_by("position")],
            [("Front", 1), ("Ton", 2), ("Rear", 3), ("Seite", 4)],
        )
        move_group(rear, parent=None, position=1)
        self.assertEqual(names(self.tree().roots), ["Rear", "Licht"])
        self.assertEqual([group.position for group in self.light.children.order_by("position")], [1, 2, 3])
        move_group(side, parent=self.light, position=99)  # beyond the end: the end
        self.assertEqual(names(self.light.children.order_by("position")), ["Front", "Ton", "Seite"])

    def test_changing_the_parent_like_a_field_moves_the_group_to_the_end(self) -> None:
        update_group(self.sound, rights=ALL_RIGHTS, parent=self.light, name="Ton und Licht")
        self.sound.refresh_from_db()
        self.assertEqual((self.sound.parent, self.sound.position, self.sound.name), (self.light, 2, "Ton und Licht"))
        update_group(self.sound, rights=ALL_RIGHTS, parent=None)
        self.assertEqual(names(self.tree().roots), ["Licht", "Ton und Licht"])

    def test_reordering_keeps_the_parents(self) -> None:
        rear = add_group(self.project, "Rear", parent=self.light)
        reorder_groups(self.project, [self.sound.pk, rear.pk, self.light.pk, self.front.pk])
        tree = self.tree()
        self.assertEqual(names(tree.ordered), ["Ton", "Licht", "Rear", "Front", "Traverse 1"])

    def test_possible_parents_leave_out_what_breaks_a_rule(self) -> None:
        tree = self.tree()
        # "Front" has a subgroup: only a top-level group can take it – its present parent among them.
        self.assertEqual(names(tree.possible_parents(tree.by_id[self.front.pk])), ["Licht", "Ton"])
        self.assertEqual(names(tree.possible_parents(tree.by_id[self.sound.pk])), ["Licht", "Front"])
        self.assertEqual(names(tree.possible_parents(None)), ["Licht", "Front", "Ton"])

    def test_a_cycle_in_the_data_still_shows_every_group(self) -> None:
        """Rentalars never stores one; should the database hold one anyway, no group gets lost."""
        Group.objects.filter(pk=self.light.pk).update(parent=self.truss)
        tree = self.tree()
        self.assertEqual(sorted(names(tree.ordered)), ["Front", "Licht", "Ton", "Traverse 1"])
        self.assertTrue(compute_project_prices(self.project).groups)


class Lighting(RentalarsTestCase):
    """The worked example of the module text, built for several tests."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=1)
        self.tax_free = TaxRate.objects.get(rate=0)
        self.light = add_group(self.project, "Licht", discount_percent=D("5"))
        self.desk = add_line(self.project, flat("L-001", "450.00"), 1, group=self.light).line
        self.front = add_group(self.project, "Front", parent=self.light)
        self.par = add_line(self.project, flat("L-002", "140.00", tax_rate=self.tax_free), 3, group=self.front).line
        self.rear = add_group(self.project, "Rear", parent=self.light, discount_percent=D("10"))
        add_line(self.project, flat("L-003", "155.00"), 2, group=self.rear)
        add_line(self.project, flat("S-001", "50.00"), 1)

    def prices(self) -> object:
        return compute_project_prices(self.project)

    def group(self, prices: object, name: str) -> object:
        return next(group for group in prices.groups if group.group.name == name)  # type: ignore[attr-defined]


class NestedPriceTests(Lighting):
    """PRJ-037: a parent sums its subgroups; the subgroup's rule first, then the parent's."""

    def test_the_worked_example(self) -> None:
        prices = self.prices()
        self.assertEqual([group.group.name for group in prices.groups], ["Licht", "Front", "Rear"])  # type: ignore[attr-defined]
        light = self.group(prices, "Licht")
        self.assertEqual(
            (light.own_lines_total, light.children_total, light.lines_total, light.discount, light.subtotal),  # type: ignore[attr-defined]
            (D("450.00"), D("699.00"), D("1149.00"), D("57.45"), D("1091.55")),
        )
        self.assertEqual(self.group(prices, "Rear").subtotal, D("279.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.groups_total, D("1091.55"))  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("1141.55"))  # type: ignore[attr-defined]
        self.assertEqual(prices.discount_total, D("88.45"))  # type: ignore[attr-defined]  # 31.00 + 57.45

    def test_the_parents_discount_is_spread_over_the_tax_rates_below_it(self) -> None:
        prices = self.prices()
        by_rate = {str(line.tax_rate.rate): line.net for line in prices.tax_lines}  # type: ignore[attr-defined]
        # Front (tax free) 420.00 less 5 %; the rest: (450.00 + 279.00) less 5 % and 50.00 without group.
        self.assertEqual(by_rate, {"19.00": D("742.55"), "0.00": D("399.00")})

    def test_a_flat_price_of_the_parent_replaces_everything_in_it(self) -> None:
        update_group(self.light, rights=ALL_RIGHTS, discount_percent=None, flat_price=D("1000.00"))
        prices = self.prices()
        light = self.group(prices, "Licht")
        self.assertEqual((light.subtotal, light.discount), (D("1000.00"), D("149.00")))  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("1050.00"))  # type: ignore[attr-defined]
        self.assertEqual(sum(line.net for line in prices.tax_lines), D("1050.00"))  # type: ignore[attr-defined]
        # The tax free share keeps its proportion: 420 of 1149 of the flat price.
        tax_free = next(line.net for line in prices.tax_lines if line.tax_rate == self.tax_free)  # type: ignore[attr-defined]
        self.assertEqual(tax_free, D("365.54"))

    def test_a_flat_price_of_an_empty_subgroup_reaches_the_parent(self) -> None:
        add_group(self.project, "Pauschale", parent=self.light, flat_price=D("100.00"))
        prices = self.prices()
        self.assertEqual(self.group(prices, "Licht").lines_total, D("1249.00"))  # type: ignore[attr-defined]
        self.assertEqual(sum(line.net for line in prices.tax_lines), prices.net_total)  # type: ignore[attr-defined]

    def test_an_optional_subgroup_stays_outside_its_parents_sum(self) -> None:
        fog = add_group(self.project, "Nebel", parent=self.light, kind=GroupKind.OPTIONAL)
        add_line(self.project, flat("L-004", "100.00"), 1, group=fog)
        prices = self.prices()
        self.assertEqual(self.group(prices, "Licht").subtotal, D("1091.55"))  # type: ignore[attr-defined]
        self.assertEqual(prices.optional_total, D("100.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("1141.55"))  # type: ignore[attr-defined]

    def test_a_subgroup_of_an_optional_group_is_optional_too(self) -> None:
        effects = add_group(self.project, "Effekte", kind=GroupKind.OPTIONAL)
        add_line(self.project, flat("L-005", "50.00"), 1, group=effects)
        laser = add_group(self.project, "Laser", parent=effects)
        add_line(self.project, flat("L-006", "200.00"), 1, group=laser)
        prices = self.prices()
        self.assertEqual(self.group(prices, "Effekte").subtotal, D("250.00"))  # type: ignore[attr-defined]
        laser_prices = self.group(prices, "Laser")
        self.assertFalse(laser_prices.counts_toward_total)  # type: ignore[attr-defined]
        self.assertTrue(laser_prices.group.kind_is_inherited)  # type: ignore[attr-defined]
        self.assertEqual(laser_prices.group.effective_kind, GroupKind.OPTIONAL)  # type: ignore[attr-defined]
        self.assertEqual(prices.optional_total, D("250.00"))  # type: ignore[attr-defined]
        self.assertEqual(prices.net_total, D("1141.55"))  # type: ignore[attr-defined]

    def test_subgroups_take_the_rental_days_of_the_group_above(self) -> None:
        update_group(self.light, rights=ALL_RIGHTS, rental_days=3)
        lamp = add_line(self.project, make_product("L-010", price="20.00"), 1, group=self.front).line
        price = self.prices().by_line_id[lamp.pk]  # type: ignore[attr-defined]
        self.assertEqual((price.rental_days, price.rental_days_source), (3, DaysSource.GROUP))
        update_group(self.front, rights=ALL_RIGHTS, rental_days=2)
        self.assertEqual(self.prices().by_line_id[lamp.pk].rental_days, 2)  # type: ignore[attr-defined]

    def test_percentage_surcharges_take_their_targets_after_their_own_rules(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        on_rear = add_line(self.project, night, 1).line
        set_surcharge_targets(on_rear, [{"type": "group", "id": self.rear.pk}])
        on_light = add_line(self.project, night, 1).line
        set_surcharge_targets(on_light, [{"type": "group", "id": self.light.pk}])
        on_rear.refresh_from_db()
        on_light.refresh_from_db()
        # PRJ-058: a surcharge on one group stands in it – also in a subgroup.
        self.assertEqual((on_rear.group, on_light.group), (self.rear, self.light))
        prices = self.prices()
        self.assertEqual(prices.by_line_id[on_rear.pk].amount, D("27.90"))  # type: ignore[attr-defined]
        rear = self.group(prices, "Rear")
        self.assertEqual(rear.subtotal, D("306.90"))  # type: ignore[attr-defined]  # 279.00 + 27.90
        light = self.group(prices, "Licht")
        # 450.00 + 420.00 + 306.90 = 1176.90, less 5 % (58.85) = 1118.05, plus its own surcharge on that.
        self.assertEqual(light.base, D("1118.05"))  # type: ignore[attr-defined]
        self.assertEqual(prices.by_line_id[on_light.pk].amount, D("111.81"))  # type: ignore[attr-defined]
        self.assertEqual(light.subtotal, D("1229.86"))  # type: ignore[attr-defined]
        self.assertEqual(sum(line.net for line in prices.tax_lines), prices.net_total)  # type: ignore[attr-defined]

    def test_a_project_surcharge_on_a_subgroup_takes_its_own_amount(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        line = add_line(self.project, night, 1).line
        set_surcharge_targets(line, [{"type": "group", "id": self.front.pk}, {"type": "project"}])
        prices = self.prices()
        # Front 420.00 and the project 1091.55 + 50.00: 10 % of 1561.55.
        self.assertEqual(prices.by_line_id[line.pk].surcharge_base, D("1561.55"))  # type: ignore[attr-defined]


class MaximumDiscountAcrossLevelsTests(RentalarsTestCase):
    """PER-026 holds however many groups above a line give a discount."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        sound = job_function("Tontechnik")
        engineer = sound.service_product  # PRD-044: every job function has its own
        engineer.price, engineer.billing_mode = D("100.00"), BillingMode.FLAT
        engineer.save()
        sound.max_discount_percent = D("5")
        sound.save()
        self.sound = add_group(self.project, "Ton", discount_percent=D("10"))
        self.crew = add_group(self.project, "Personal", parent=self.sound)
        self.engineer = add_line_before_071(self.project, engineer, 1, group=self.crew).line
        self.desks = add_group(self.project, "Technik", parent=self.sound)
        add_line(self.project, flat("T-030", "400.00"), 1, group=self.desks)

    def test_the_parents_discount_takes_only_what_the_maximum_leaves(self) -> None:
        prices = compute_project_prices(self.project)
        sound = prices.by_group_id[self.sound.pk]
        self.assertEqual((sound.discount, sound.cap_excess, sound.subtotal), (D("45.00"), D("5.00"), D("455.00")))
        self.assertTrue(prices.by_line_id[self.engineer.pk].discount_is_capped)
        self.assertEqual(sum(tax.net for tax in prices.tax_lines), D("455.00"))

    def test_discounts_of_two_levels_together_stay_within_the_maximum(self) -> None:
        update_group(self.crew, rights=ALL_RIGHTS, discount_percent=D("3"))
        prices = compute_project_prices(self.project)
        # 97.00 after the 3 % of "Personal"; "Ton" may take 2.00 more, not 9.70.
        self.assertEqual(prices.by_group_id[self.crew.pk].subtotal, D("97.00"))
        sound = prices.by_group_id[self.sound.pk]
        self.assertEqual((sound.lines_total, sound.cap_excess, sound.subtotal), (D("497.00"), D("7.70"), D("455.00")))
        self.assertTrue(prices.by_line_id[self.engineer.pk].discount_is_capped)


class AvailabilityTests(RentalarsTestCase):
    """PRJ-037 with PRJ-040: a subgroup of an optional group reserves softly, at every level."""

    def test_subgroups_of_an_optional_group_reserve_softly(self) -> None:
        lamp = make_stock("L-010", 6)
        project = make_project("Mit Option")
        optional = add_group(project, "Option", kind=GroupKind.OPTIONAL)
        inner = add_group(project, "Front", parent=optional)
        deepest = add_group(project, "Traverse", parent=inner)
        add_line(project, lamp, 2, group=inner)
        add_line(project, lamp, 3, group=deepest)
        # In the project itself the optional lines take nothing from the lines that count.
        self.assertEqual(add_line(project, lamp, 6).availability.shortage_total, 0)
        MaterialLine.objects.filter(project=project, group__isnull=True).delete()
        # Another project sees them as an option: tight, not short.
        answer = AvailabilityEngine().availability([lamp.pk], at(10), at(12))[lamp.pk]
        self.assertEqual((answer.firm, answer.optional), (0, 5))
        verdict = add_line(make_project("Fest"), lamp, 4).availability
        self.assertEqual((verdict.status, verdict.shortage_total), ("tight", 0))

    def test_lines_count_in_the_order_of_the_planning(self) -> None:
        """PRJ-042: the same product in two groups – the group that comes first in the tree gets it."""
        lamp = make_stock("L-010", 6)
        project = make_project()
        first = add_group(project, "Erste")
        second = add_group(project, "Zweite")
        inside = add_group(project, "Drin", parent=first)
        later = add_line(project, lamp, 4, group=second).line
        earlier = add_line(project, lamp, 4, group=inside).line
        verdicts = AvailabilityEngine().project_availability(project, list(project.material_lines.all()))
        self.assertEqual((verdicts[earlier.pk].shortage_total, verdicts[later.pk].shortage_total), (0, 2))
        self.assertEqual(second.position, 2)


class DeleteAndCopyTests(Lighting):
    """PRJ-037: deleting moves what a group holds up one level; copying takes the subgroups along."""

    def test_deleting_moves_lines_and_subgroups_up_into_the_groups_place(self) -> None:
        sound = add_group(self.project, "Ton")
        delete_group(self.light)
        tree = GroupTree(self.project.groups.all())
        self.assertEqual(names(tree.roots), ["Front", "Rear", "Ton"])
        self.desk.refresh_from_db()
        self.assertIsNone(self.desk.group)  # a top-level group's lines go to "without group"
        self.assertEqual(sound.pk, tree.roots[2].pk)

    def test_deleting_a_subgroup_puts_its_lines_into_the_parent(self) -> None:
        truss = add_group(self.project, "Traverse 1", parent=self.front)
        delete_group(self.front)
        self.par.refresh_from_db()
        self.assertEqual(self.par.group, self.light)
        truss.refresh_from_db()
        self.assertEqual((truss.parent, truss.position), (self.light, 1))
        self.assertEqual(names(self.light.children.order_by("position")), ["Traverse 1", "Rear"])

    def test_deleting_with_the_lines_deletes_the_subgroups_too(self) -> None:
        delete_group(self.light, keep_lines=False)
        self.assertEqual(names(self.project.groups.all()), [])
        self.assertEqual(self.project.material_lines.count(), 1)

    def test_copying_takes_the_subgroups_along(self) -> None:
        copy = copy_group(self.light, self.project, rights=ALL_RIGHTS)
        tree = GroupTree(self.project.groups.all())
        self.assertEqual(names(tree.roots), ["Licht", "Licht (Kopie)"])
        self.assertEqual(names(tree.descendants(tree.by_id[copy.pk])), ["Front", "Rear"])
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.by_group_id[copy.pk].subtotal, D("1091.55"))
        # A subgroup copied within the project stays inside the same parent.
        inner = copy_group(self.rear, self.project, rights=ALL_RIGHTS)
        self.assertEqual((inner.parent, inner.name, inner.position), (self.light, "Rear (Kopie)", 3))

    def test_copying_into_another_project_keeps_the_arrangement_and_the_surcharges(self) -> None:
        night = make_product("A-002", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None)
        surcharge = add_line(self.project, night, 1).line
        set_surcharge_targets(surcharge, [{"type": "group", "id": self.rear.pk}])
        target = make_project("Tournee", start=at(20), end=at(22), rental_days=1)
        copy = copy_group(self.light, target, rights=ALL_RIGHTS)
        tree = GroupTree(target.groups.all())
        self.assertEqual([tree.path(group) for group in tree.ordered], ["Licht", "Licht › Front", "Licht › Rear"])
        rear_copy = next(group for group in tree.ordered if group.name == "Rear")
        copied_surcharge = target.material_lines.get(surcharge_percent__isnull=False)
        self.assertEqual(copied_surcharge.group, rear_copy)
        self.assertEqual(copied_surcharge.surcharge_targets.get().target_group, rear_copy)
        self.assertEqual(compute_project_prices(target).by_group_id[copy.pk].subtotal, D("1118.05"))

    def test_duplicating_the_project_keeps_the_arrangement(self) -> None:
        copy = duplicate_project(
            self.project,
            name="Stadtfest 2028",
            start=at(10, year=2028),
            end=at(12, year=2028),
            rights=ALL_RIGHTS,
            user=None,
        )
        tree = GroupTree(copy.groups.all())
        self.assertEqual([tree.path(group) for group in tree.ordered], ["Licht", "Licht › Front", "Licht › Rear"])
        self.assertEqual(compute_project_prices(copy).net_total, D("1141.55"))


class TemplateTests(Lighting):
    """PRJ-076 with PRJ-037: templates keep the arrangement; older templates still load."""

    def test_capture_and_apply_keep_the_arrangement(self) -> None:
        content = capture(self.project, rights=ALL_RIGHTS)
        self.assertEqual(content["version"], CONTENT_VERSION)
        self.assertEqual(
            [(group["name"], group["parent"]) for group in content["groups"]],
            [("Licht", None), ("Front", self.light.pk), ("Rear", self.light.pk)],
        )
        template = save_as_template(self.project, name="Licht-Paket", rights=ALL_RIGHTS)
        target = make_project("Neu", rental_days=1)
        add_group(target, "Schon da")
        apply_template(template, target, rights=ALL_RIGHTS)
        tree = GroupTree(target.groups.all())
        self.assertEqual(
            [(tree.path(group), group.position) for group in tree.ordered],
            [("Schon da", 1), ("Licht", 2), ("Licht › Front", 1), ("Licht › Rear", 2)],
        )
        self.assertEqual(target.material_lines.get(product__article_number="L-002").group.name, "Front")

    def test_a_template_of_version_1_loads_with_every_group_at_the_top(self) -> None:
        content = capture(self.project, rights=ALL_RIGHTS)
        content["version"] = 1
        for group in content["groups"]:
            del group["parent"]
        template = ProjectTemplate.objects.create(name="Alt", content=content)
        target = make_project("Neu", rental_days=1)
        apply_template(template, target, rights=ALL_RIGHTS)
        self.assertEqual(
            [(group.name, group.parent, group.position) for group in target.groups.order_by("position")],
            [("Licht", None, 1), ("Front", None, 2), ("Rear", None, 3)],
        )

    def test_children_listed_before_their_parent_still_find_it(self) -> None:
        content = capture(self.project, rights=ALL_RIGHTS)
        content["groups"].reverse()
        template = ProjectTemplate.objects.create(name="Umgedreht", content=content)
        target = make_project("Neu", rental_days=1)
        apply_template(template, target, rights=ALL_RIGHTS)
        tree = GroupTree(target.groups.all())
        self.assertEqual(sorted(tree.path(group) for group in tree.ordered), ["Licht", "Licht › Front", "Licht › Rear"])


class PacklistTests(Lighting):
    """Packlists in the order of the planning, sections named with their path; optional subtrees left out."""

    def test_sections_follow_the_tree(self) -> None:
        for line in self.project.material_lines.all():
            line.delete()
        rear_lamp = make_stock("L-020", 4)
        front_lamp = make_stock("L-010", 4)
        add_line(self.project, rear_lamp, 1, group=self.rear)
        add_line(self.project, front_lamp, 1, group=self.front)
        add_line(self.project, make_stock("L-030", 2), 1, group=self.light)
        effects = add_group(self.project, "Effekte", kind=GroupKind.OPTIONAL)
        add_line(self.project, make_stock("L-040", 2), 1, group=add_group(self.project, "Laser", parent=effects))
        overview = build_overview(get_packlist(self.project))
        self.assertEqual([section.title for section in overview.sections], ["Licht", "Licht › Front", "Licht › Rear"])


class DocumentTests(Lighting):
    """Offer, order confirmation and invoice with nested subtotals; the electronic invoice stays flat."""

    def setUp(self) -> None:
        super().setUp()
        self.project.customer = ready_for_invoices()
        self.project.save()

    def test_sections_open_and_close_around_the_subgroups(self) -> None:
        offer = documents.build_content(
            self.project, DocumentKind.ORDER_CONFIRMATION, number="X", issued_on=at(1).date()
        )
        self.assertEqual(
            [(section.title, section.level, section.part, section.subtotal) for section in offer.sections],
            [
                ("Licht", 0, "opens", D("0")),
                ("Front", 1, "", D("420.00")),
                ("Rear", 1, "", D("279.00")),
                ("Licht", 0, "closes", D("1091.55")),
                ("Ohne Teilgruppe", 0, "", D("50.00")),
            ],
        )
        self.assertEqual([position.number for position in offer.positions], ["1", "2", "3", "4"])
        self.assertEqual(offer.sections[2].adjustment_label, "Rabatt 10 %")
        self.assertEqual(
            (offer.sections[3].adjustment_label, offer.sections[3].adjustment_amount), ("Rabatt 5 %", D("-57.45"))
        )
        # Stored and read again – also an older content without the new fields.
        again = from_json(offer.as_json())
        self.assertEqual([section.part for section in again.sections], ["opens", "", "", "closes", ""])
        old = offer.as_json()
        for section in old["sections"]:
            del section["level"], section["part"]
        self.assertEqual(from_json(old).sections[0].part, "")

    def test_invoice_sums_match_and_the_xrechnung_stays_flat(self) -> None:
        fog = add_group(self.project, "Nebel", parent=self.light, kind=GroupKind.OPTIONAL)
        add_line(self.project, flat("L-004", "100.00"), 1, group=fog)
        invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        self.assertTrue(documents.verify(invoice))
        self.assertEqual((invoice.net_total, invoice.gross_total), (D("1141.55"), D("1282.63")))
        self.assertNotIn("Nebel", [section["title"] for section in invoice.content["sections"]])
        root = ET.fromstring(invoice.xml_file.read())
        cac, cbc = "{" + NAMESPACES["cac"] + "}", "{" + NAMESPACES["cbc"] + "}"
        self.assertEqual(len(root.findall(f"{cac}InvoiceLine")), 4)
        totals = {child.tag.split("}")[1]: D(child.text) for child in root.find(f"{cac}LegalMonetaryTotal")}
        # EN 16931 BR-CO-13: lines less allowances plus charges give the net amount.
        self.assertEqual(totals["LineExtensionAmount"], D("1230.00"))  # 450 + 420 + 310 + 50
        self.assertEqual(
            totals["LineExtensionAmount"]
            - totals.get("AllowanceTotalAmount", D("0"))
            + totals.get("ChargeTotalAmount", D("0")),
            totals["TaxExclusiveAmount"],
        )
        self.assertEqual(totals["TaxExclusiveAmount"], D("1141.55"))
        taxable = sum(D(element.text) for element in root.iter(f"{cbc}TaxableAmount"))
        self.assertEqual(taxable, D("1141.55"))
        self.assertTrue(documents.preview(self.project, DocumentKind.OFFER).startswith(b"%PDF"))


class PriceOverviewTests(Lighting):
    """The price overview as CSV and PDF names subgroups with their path."""

    def test_csv_with_and_without_lines(self) -> None:
        rows = [row.split(";") for row in render_price_overview_csv(self.project).lstrip("﻿").splitlines()]
        subtotals = [(row[0], row[2], row[-1]) for row in rows if row[2].startswith("Zwischensumme")]
        self.assertEqual(
            subtotals,
            [
                ("Licht › Front", "Zwischensumme", "420"),
                ("Licht › Rear", "Zwischensumme", "279"),
                ("Licht", "Zwischensumme mit Untergruppen", "1091,55"),
                ("Ohne Teilgruppe", "Zwischensumme", "50"),
            ],
        )
        groups = [
            row.split(";") for row in render_price_overview_csv(self.project, with_lines=False).lstrip("﻿").splitlines()
        ]
        self.assertEqual([row[0] for row in groups[1:4]], ["Licht", "Licht › Front", "Licht › Rear"])
        self.assertEqual(groups[1][2], "1091,55")
        self.assertTrue(render_price_overview_pdf(self.project, with_lines=True).startswith(b"%PDF"))


class MvrTests(RentalarsTestCase):
    """PRJ-077 with PRJ-037: the lines of a light plot go into a subgroup."""

    def test_into_a_subgroup(self) -> None:
        panel = make_product("L-020", "SkyPanel S60", price="60.00")
        project = make_project()
        light = add_group(project, "Licht")
        front = add_group(project, "Front", parent=light)
        plot = read(sample_plot(), "Stadtfest.mvr")
        result = mvr.take_over(
            project, plot, {mvr.type_key(SKYPANEL, "CCT"): mvr.Choice(panel, D("2"))}, rights=ALL_RIGHTS, group=front
        )
        self.assertEqual(result.group, front)
        self.assertEqual(project.material_lines.get().group, front)


class PatchTests(Lighting):
    """NFA-013 with PRJ-037: a change in a subgroup sends the subtotals of the groups above it."""

    def test_a_change_in_a_subgroup_sends_the_totals_above(self) -> None:
        truss = add_group(self.project, "Traverse", parent=self.front)
        _planning, patch = build_patch(self.project, AvailabilityEngine(), product_ids=[], group_ids=[truss.pk])
        self.assertEqual([group.group.name for group in patch.groups], ["Traverse"])
        self.assertEqual([group.group.name for group in patch.totals], ["Licht", "Front"])

    def test_with_a_maximum_discount_below_a_rule_the_family_goes_along(self) -> None:
        sound = job_function("Tontechnik")
        engineer = sound.service_product  # PRD-044: every job function has its own
        engineer.price, engineer.billing_mode = D("100.00"), BillingMode.FLAT
        engineer.save()
        sound.max_discount_percent = D("5")
        sound.save()
        add_line_before_071(self.project, engineer, 1, group=self.rear)
        _planning, patch = build_patch(self.project, AvailabilityEngine(), product_ids=[], group_ids=[self.front.pk])
        self.assertEqual([group.group.name for group in patch.groups], ["Licht", "Front", "Rear"])

    def test_the_planning_links_parents_and_subgroups(self) -> None:
        planning = build_planning(self.project)
        self.assertEqual([group.group.name for group in planning.root_groups], ["Licht"])
        front = planning.groups[1]
        self.assertEqual(
            (front.path, front.depth, front.heading_level, front.parent.group.name), ("Licht › Front", 1, 4, "Licht")
        )
        self.assertEqual(
            planning.groups[0].delete_question,
            "Diese Teilgruppe löschen? Ihre Positionen wandern nach „ohne Teilgruppe“, ihre Untergruppen auf die oberste Ebene.",
        )
        self.assertIn("„Licht“", front.delete_question)
