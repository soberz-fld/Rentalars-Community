# SPDX-License-Identifier: GPL-3.0-or-later
"""Rules of projects, groups and lines that the scenarios do not reach (PRJ)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.accounts.rights import Level, Module, Rights, SpecialRight
from rentalars.masterdata.models import Supplier
from rentalars.projects.models import Group, MaterialLine, Project, SurchargeTarget
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.services import (
    accept_subrental_suggestion,
    add_group,
    arrange_lines,
    change_status,
    copy_group,
    delete_group,
    reorder_groups,
    set_surcharge_targets,
    update_group,
    update_line,
    update_project,
)
from rentalars.projects.services import (
    add_line as add_line_service,
)
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    make_customer,
    make_product,
    make_project,
    make_stock,
)
from tests.helpers import add_group as make_group

D = Decimal
PLANNER = Rights(module_levels={Module.PROJECTS: Level.WRITE})
SALES = Rights(module_levels={Module.PROJECTS: Level.WRITE}, special_rights=frozenset({SpecialRight.PRICES}))


class ProjectRuleTests(RentalarsTestCase):
    """Project master data and status (PRJ-001 to PRJ-009)."""

    def test_moving_the_project_period_moves_the_lines_that_followed_it(self) -> None:
        """PRJ-011: lines with a period of their own keep it."""
        project = make_project(start=at(10, 8), end=at(12, 18))
        lamp = make_product("L-010")
        following = add_line(project, lamp, 1).line
        own = add_line(project, lamp, 1, start=at(11, 8), end=at(11, 20)).line

        update_project(project, start=at(17, 8), end=at(19, 18))

        following.refresh_from_db()
        own.refresh_from_db()
        self.assertEqual((following.start, following.end), (at(17, 8), at(19, 18)))
        self.assertEqual((own.start, own.end), (at(11, 8), at(11, 20)))

    def test_contact_must_belong_to_the_customer(self) -> None:
        from rentalars.customers.models import Contact

        project = make_project()
        stranger = Contact.objects.create(customer=make_customer("Anderer Kunde"), name="Fremd")
        with self.assertRaises(ValidationError):
            update_project(project, contact=stranger)

    def test_event_period_must_be_complete_and_in_order(self) -> None:
        project = make_project()
        with self.assertRaises(ValidationError):
            update_project(project, event_start=at(11, 10), event_end=None)
        with self.assertRaises(ValidationError):
            update_project(project, event_start=at(11, 10), event_end=at(11, 9))

    def test_subprojects_have_one_level(self) -> None:
        """PRJ-043: the data model is prepared; deeper nesting is refused."""
        parent = make_project("Tournee")
        child = make_project("Tournee Tag 1", parent=parent)
        self.assertEqual(child.parent, parent)
        with self.assertRaises(ValidationError):
            make_project("Tournee Tag 1 Bühne B", parent=child)
        with self.assertRaises(ValidationError):
            update_project(parent, parent=parent)

    def test_closed_project_is_locked_for_lines_groups_and_master_data(self) -> None:
        """PRJ-009."""
        project = make_project()
        lamp = make_product("L-010")
        line = add_line(project, lamp, 1).line
        group = make_group(project, "Licht")
        Project.objects.filter(pk=project.pk).update(status="closed")
        project.refresh_from_db()
        line.project = project
        group.project = project
        for attempt in (
            lambda: update_project(project, name="Neu"),
            lambda: add_line(project, lamp, 1),
            lambda: update_line(line, rights=ALL_RIGHTS, quantity=D("2")),
            lambda: add_group(project, rights=ALL_RIGHTS, name="Ton"),
            lambda: update_group(group, rights=ALL_RIGHTS, name="Anders"),
            lambda: delete_group(group),
            lambda: arrange_lines(project, [(None, [line.pk])]),
        ):
            with self.assertRaises(ValidationError):
                attempt()
        with self.assertRaises(ValidationError):
            change_status(project, "returned", rights=SALES)
        change_status(project, "returned", rights=ALL_RIGHTS)
        update_project(project, name="Wieder offen")


class LineRuleTests(RentalarsTestCase):
    """Lines: price rights, quantities, fields (PRJ-010 to PRJ-018)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.lamp = make_stock("L-010", 6, price="20.00")

    def test_prices_and_purchase_prices_need_their_rights(self) -> None:
        """AUT-019."""
        line = add_line(self.project, self.lamp, 1).line
        for field, value in (("unit_price", D("1")), ("discount_percent", D("50")), ("manual_scale_factor", D("0.1"))):
            with self.assertRaises(ValidationError, msg=field):
                update_line(line, rights=PLANNER, **{field: value})
            with self.assertRaises(ValidationError, msg=field):
                add_line_service(self.project, rights=PLANNER, product=self.lamp, **{field: value})
        with self.assertRaises(ValidationError):
            update_line(line, rights=SALES, purchase_price=D("5"))
        update_line(line, rights=SALES, unit_price=D("25.00"))
        update_line(line, rights=PLANNER, quantity=D("3"), note="Planung darf das")
        line.refresh_from_db()
        self.assertEqual((line.unit_price, line.quantity), (D("25.00"), D("3")))

    def test_fields_that_are_not_meant_to_be_edited_are_refused(self) -> None:
        line = add_line(self.project, self.lamp, 1).line
        for field in ("project", "product", "position", "scale_version", "covers_line", "stock_removed_quantity"):
            with self.assertRaises(ValidationError, msg=field):
                update_line(line, rights=ALL_RIGHTS, **{field: None})

    def test_stock_products_are_planned_in_whole_pieces(self) -> None:
        with self.assertRaises(ValidationError):
            add_line(self.project, self.lamp, "1.5")
        with self.assertRaises(ValidationError):
            add_line(self.project, self.lamp, -1)
        transport = make_product("F-002", kind="incidental", billing_mode="effort", price="0.80")  # PRD-045
        self.assertEqual(add_line(self.project, transport, "12.5").line.quantity, D("12.5"))

    def test_line_period_must_be_in_order(self) -> None:
        with self.assertRaises(ValidationError):
            add_line(self.project, self.lamp, 1, start=at(12), end=at(11))

    def test_product_without_sale_price_cannot_be_sold_and_vice_versa(self) -> None:
        with self.assertRaises(ValidationError):
            add_line(self.project, self.lamp, 1, is_sale=True)
        tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=D("14.90"))
        line = add_line(self.project, tape, 1).line
        with self.assertRaises(ValidationError):
            update_line(line, rights=ALL_RIGHTS, is_sale=False)

    def test_subrental_needs_a_positive_quantity_and_an_active_subrental_product(self) -> None:
        """PRD-040."""
        from rentalars.products.models import Product

        line = add_line(self.project, self.lamp, 8).line
        with self.assertRaises(ValidationError):
            accept_subrental_suggestion(line, self.lamp, 0, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            accept_subrental_suggestion(line, self.lamp, 2, rights=SALES, purchase_price=D("5"))
        Product.objects.filter(kind="subrental").update(is_active=False)
        with self.assertRaises(ValidationError):
            accept_subrental_suggestion(line, self.lamp, 2, rights=ALL_RIGHTS)

    def test_subrental_line_sits_directly_below_the_line_it_covers(self) -> None:
        first = add_line(self.project, self.lamp, 8).line
        last = add_line(self.project, make_product("K-005"), 1).line
        subrental = accept_subrental_suggestion(
            first, self.lamp, 2, rights=ALL_RIGHTS, supplier=Supplier.objects.create(name="Verleih Nord")
        )
        order = list(
            MaterialLine.objects.filter(project=self.project).order_by("position", "id").values_list("pk", flat=True)
        )
        self.assertEqual(order, [first.pk, subrental.pk, last.pk])
        self.assertEqual((subrental.title, subrental.start, subrental.end), (first.title, first.start, first.end))

    def test_deleting_a_line_keeps_the_subrental_that_was_ordered_for_it(self) -> None:
        from rentalars.projects.services import delete_line

        line = add_line(self.project, self.lamp, 8).line
        subrental = accept_subrental_suggestion(line, self.lamp, 2, rights=ALL_RIGHTS)
        delete_line(line)
        subrental.refresh_from_db()
        self.assertIsNone(subrental.covers_line)
        self.assertFalse(subrental.is_covering_subrental)


class GroupRuleTests(RentalarsTestCase):
    """Groups: order, copy, delete (PRJ-014, PRJ-039 to PRJ-041)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=1)
        self.lamp = make_stock("L-010", 6, price="20.00")
        self.front = make_group(self.project, "Front", discount_percent=D("10"))
        self.line = add_line(self.project, self.lamp, 2, group=self.front, note="mit Torblende").line

    def test_group_discounts_need_the_price_right(self) -> None:
        with self.assertRaises(ValidationError):
            update_group(self.front, rights=PLANNER, discount_percent=D("90"))
        with self.assertRaises(ValidationError):
            add_group(self.project, rights=PLANNER, name="Billig", flat_price=D("1"))
        update_group(self.front, rights=PLANNER, name="Front-Traverse")

    def test_copy_within_the_project(self) -> None:
        copy = copy_group(self.front, self.project, rights=ALL_RIGHTS)
        self.assertEqual(copy.name, "Front (Kopie)")
        self.assertEqual(copy.discount_percent, D("10"))
        copied_line = copy.lines.get()
        self.assertEqual(
            (copied_line.quantity, copied_line.note, copied_line.unit_price), (D("2"), "mit Torblende", D("20.00"))
        )
        self.assertEqual(Group.objects.filter(project=self.project).count(), 2)

    def test_copy_into_another_project_takes_its_period_and_leaves_out_covering_subrentals(self) -> None:
        big = add_line(self.project, self.lamp, 9, group=self.front).line
        accept_subrental_suggestion(big, self.lamp, 5, rights=ALL_RIGHTS)
        target = make_project("Jazznacht", start=at(20, 8), end=at(21, 18))

        copy = copy_group(self.front, target, rights=ALL_RIGHTS)

        self.assertEqual(copy.name, "Front")
        lines = list(copy.lines.order_by("position", "id"))
        self.assertEqual([line.quantity for line in lines], [D("2"), D("9")])
        self.assertTrue(all((line.start, line.end) == (at(20, 8), at(21, 18)) for line in lines))
        self.assertFalse(any(line.is_covering_subrental for line in lines))

    def test_copy_without_price_right_does_not_carry_the_discount(self) -> None:
        copy = copy_group(self.front, self.project, rights=PLANNER)
        self.assertIsNone(copy.discount_percent)

    def test_surcharge_in_a_copied_group_refers_to_the_copy(self) -> None:
        night = make_product("A-002", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None)
        surcharge = add_line(self.project, night, 1).line
        set_surcharge_targets(surcharge, [{"type": "group", "id": self.front.pk}])
        copy = copy_group(self.front, self.project, rights=ALL_RIGHTS)
        copied_surcharge = copy.lines.get(product=night)
        target = SurchargeTarget.objects.get(surcharge_line=copied_surcharge)
        self.assertEqual(target.target_group, copy)
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.groups[0].subtotal, prices.groups[1].subtotal)

    def test_reordering_only_touches_the_groups_of_the_project(self) -> None:
        rear = make_group(self.project, "Rear")
        foreign = make_group(make_project("Anderes"), "Fremd")
        reorder_groups(self.project, [foreign.pk, rear.pk, self.front.pk, 999999])
        self.assertEqual(list(self.project.groups.values_list("name", flat=True)), ["Rear", "Front"])
        foreign.refresh_from_db()
        self.assertEqual(foreign.position, 1)

    def test_arranging_never_reaches_into_another_project(self) -> None:
        other = make_project("Anderes")
        foreign_line = add_line(other, self.lamp, 1).line
        foreign_group = make_group(other, "Fremd")
        # IDs of lines that do not belong to the project are ignored …
        arrange_lines(self.project, [(self.front.pk, [foreign_line.pk, self.line.pk])])
        foreign_line.refresh_from_db()
        self.assertEqual((foreign_line.project, foreign_line.group), (other, None))
        # … and a group of another project is refused.
        with self.assertRaises(ValidationError):
            arrange_lines(self.project, [(foreign_group.pk, [self.line.pk])])
        self.line.refresh_from_db()
        self.assertEqual(self.line.group, self.front)

    def test_deleting_a_group_with_its_lines(self) -> None:
        delete_group(self.front, keep_lines=False)
        self.assertFalse(MaterialLine.objects.filter(project=self.project).exists())

    def test_surcharge_targets_are_validated(self) -> None:
        night = make_product("A-002", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None)
        surcharge = add_line(self.project, night, 1).line
        other_project_group = make_group(make_project("Anderes"), "Fremd")
        for targets in (
            [{"type": "group", "id": other_project_group.pk}],
            [{"type": "line", "id": 999999}],
            [{"type": "line", "id": surcharge.pk}],
            [{"type": "nonsense"}],
        ):
            with self.assertRaises(ValidationError, msg=str(targets)):
                set_surcharge_targets(surcharge, targets)
        with self.assertRaises(ValidationError):
            set_surcharge_targets(self.line, [{"type": "project"}])
        set_surcharge_targets(surcharge, [{"type": "project"}])
        set_surcharge_targets(surcharge, [])
        self.assertFalse(SurchargeTarget.objects.filter(surcharge_line=surcharge).exists())
