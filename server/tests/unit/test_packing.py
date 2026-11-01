# SPDX-License-Identifier: GPL-3.0-or-later
"""Packlist rules that the scenarios do not reach: sales, subrentals, allocation, guards (PCK)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.material.models import MaterialItem
from rentalars.packing.models import Allocation, PacklistStatus
from rentalars.packing.services import (
    build_overview,
    complete_return,
    get_packlist,
    issue,
    pack_all,
    resolve_missing,
    return_all,
    set_packed,
    set_returned,
    undo_issue,
)
from rentalars.projects.models import GroupKind, Project
from rentalars.projects.services import accept_subrental_suggestion, change_status
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_item,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
)

D = Decimal


class PacklistContentTests(RentalarsTestCase):
    """What appears on a packlist (PCK-002, PCK-005, PRJ-018, PRJ-040)."""

    def test_only_physical_things_are_packed(self) -> None:
        project = make_project()
        add_line(project, make_stock("K-005", 9, "XLR-Kabel 5 m"), 3)
        add_line(project, make_product("N-001", "Transport", kind="incidental", billing_mode="flat"), 1)  # PRD-045
        add_line(project, make_product("A-001", "Expresszuschlag", kind="surcharge", billing_mode="flat"), 1)
        add_line(project, None, 1, title="Sonderbau", unit_price=D("100"))
        rows = build_overview(get_packlist(project)).rows
        self.assertEqual([row.product.article_number for row in rows], ["K-005"])

    def test_optional_groups_are_left_out(self) -> None:
        project = make_project()
        optional = add_group(project, "Nebel", kind=GroupKind.OPTIONAL)
        add_line(project, make_stock("S-002", 2, "Nebelmaschine"), 1, group=optional)
        self.assertEqual(build_overview(get_packlist(project)).rows, [])

    def test_covered_part_appears_as_the_row_of_the_subrental(self) -> None:
        """Three cables from the shelf, two from the supplier – two rows, the second one marked."""
        cable = make_stock("K-005", 3, "XLR-Kabel 5 m")
        project = make_project()
        line = add_line(project, cable, 5).line
        accept_subrental_suggestion(line, cable, 2, rights=ALL_RIGHTS)
        rows = build_overview(get_packlist(project)).rows
        self.assertEqual(
            [(row.product.article_number, row.required, row.is_subrental) for row in rows],
            [("K-005", D("3"), False), ("E-001", D("2"), True)],
        )
        self.assertEqual(rows[1].title, "XLR-Kabel 5 m")

    def test_fully_covered_line_only_shows_the_subrental(self) -> None:
        cable = make_product("K-005")  # a product without any material: stock 0
        project = make_project()
        line = add_line(project, cable, 2).line
        accept_subrental_suggestion(line, cable, 2, rights=ALL_RIGHTS)
        rows = build_overview(get_packlist(project)).rows
        self.assertEqual([row.is_subrental for row in rows], [True])

    def test_progress_in_percent(self) -> None:
        project = make_project()
        cable = make_stock("K-005", 9)
        line = add_line(project, cable, 4).line
        packlist = get_packlist(project)
        self.assertEqual(build_overview(packlist).progress_percent, 0)
        set_packed(packlist, line.pk, cable.pk, D("1"))
        self.assertEqual(build_overview(packlist).progress_percent, 25)
        self.assertEqual(packlist.status, PacklistStatus.IN_PROGRESS)
        set_packed(packlist, line.pk, cable.pk, D("0"))
        packlist.refresh_from_db()
        self.assertEqual(packlist.status, PacklistStatus.OPEN)


class IssueTests(RentalarsTestCase):
    """Issue: status, allocation of items, sold material (PCK-014, PCK-020, PCK-021, PRD-013)."""

    def test_whole_stock_issued_means_every_item_is_known(self) -> None:
        """PCK-021: if all four speakers go out, it is beyond doubt which ones."""
        speaker = make_stock("T-010", 4)
        project = make_project()
        add_line(project, speaker, 4)
        issue(get_packlist(project))
        self.assertEqual(Allocation.objects.count(), 4)
        self.assertEqual(set(MaterialItem.objects.values_list("status", flat=True)), {"in_use"})

    def test_part_of_the_stock_issued_allocates_nothing(self) -> None:
        speaker = make_stock("T-010", 4)
        project = make_project()
        add_line(project, speaker, 3)
        issue(get_packlist(project))
        self.assertEqual(Allocation.objects.count(), 0)
        self.assertEqual(set(MaterialItem.objects.values_list("status", flat=True)), {"available"})

    def test_an_item_is_never_out_with_two_projects_at_once(self) -> None:
        rack_product = make_product("T-500")
        rack = make_item(make_model("Funkrack", rack_product), 500)
        first = make_project("Erstes", start=at(10), end=at(12))
        add_line(first, rack_product, 1)
        issue(get_packlist(first))
        second = make_project("Zweites", start=at(11), end=at(13))
        add_line(second, rack_product, 1)
        issue(get_packlist(second))
        self.assertEqual(Allocation.objects.filter(item=rack, returned_at__isnull=True).count(), 1)

    def test_sold_bulk_material_leaves_the_stock_at_issue(self) -> None:
        tape = make_product("V-001", "Gaffa", kind="sale", billing_mode="flat", price=None, sale_price=D("14.90"))
        roll = make_items(make_model("Gaffa schwarz", tape, bulk=True), 1, quantity=40)[0]
        project = make_project()
        line = add_line(project, tape, 3).line
        hints = issue(get_packlist(project))
        roll.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(hints, [])
        self.assertEqual(roll.quantity, 37)
        self.assertEqual(line.stock_removed_quantity, 3)

    def test_sold_single_item_is_marked_sold_when_it_is_beyond_doubt(self) -> None:
        # PRD-047: what is sold is a sale product.
        mixer = make_product("T-030", kind="sale", billing_mode="flat", price=None, sale_price=D("900.00"))
        item = make_item(make_model("Mischpult", mixer), 30)
        project = make_project()
        add_line(project, mixer, 1)
        self.assertEqual(issue(get_packlist(project)), [])
        item.refresh_from_db()
        self.assertEqual(item.status, "sold")

    def test_sold_items_that_cannot_be_told_apart_are_pointed_out(self) -> None:
        # PRD-047: what is sold is a sale product.
        cable = make_product("K-005", kind="sale", billing_mode="flat", price=None, sale_price=D("12.00"))
        make_items(make_model("Cordial", cable), 9)
        project = make_project()
        add_line(project, cable, 2)
        hints = issue(get_packlist(project))
        self.assertEqual(len(hints), 1)
        self.assertIn("K-005", hints[0])
        self.assertEqual(MaterialItem.objects.filter(status="sold").count(), 0)

    def test_sold_rows_do_not_come_back(self) -> None:
        tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=D("14.90"))
        make_items(make_model("Gaffa schwarz", tape, bulk=True), 1, quantity=40)
        project = make_project()
        line = add_line(project, tape, 3).line
        packlist = get_packlist(project)
        issue(packlist)
        with self.assertRaises(ValidationError):
            set_returned(packlist, line.pk, tape.pk, D("3"))
        return_all(packlist)
        complete_return(packlist)
        self.assertEqual(Project.objects.get(pk=project.pk).status, "returned")
        with self.assertRaises(ValidationError):
            undo_issue(packlist)

    def test_issue_is_refused_twice_and_for_finished_or_empty_projects(self) -> None:
        cable = make_stock("K-005", 9)
        project = make_project()
        add_line(project, cable, 1)
        packlist = get_packlist(project)
        issue(packlist)
        with self.assertRaises(ValidationError):
            issue(packlist)
        with self.assertRaises(ValidationError):
            pack_all(packlist)
        empty = make_project("Leer")
        with self.assertRaises(ValidationError):
            issue(get_packlist(empty))
        cancelled = make_project("Abgesagt", status="inquiry")
        add_line(cancelled, cable, 1)
        change_status(cancelled, "cancelled", rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            issue(get_packlist(cancelled))

    def test_inquiry_becomes_out_when_its_material_is_issued(self) -> None:
        cable = make_stock("K-005", 9)
        project = make_project(status="option")
        add_line(project, cable, 1)
        issue(get_packlist(project))
        self.assertEqual(Project.objects.get(pk=project.pk).status, "out")


class ReturnTests(RentalarsTestCase):
    """Return and the link to the project status (PCK-016, PCK-019)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9)
        self.project = make_project()
        self.line = add_line(self.project, self.cable, 3).line
        self.packlist = get_packlist(self.project)
        issue(self.packlist)

    def test_status_cannot_leave_out_while_material_is_out(self) -> None:
        self.project.refresh_from_db()
        with self.assertRaises(ValidationError):
            change_status(self.project, "confirmed", rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            change_status(self.project, "returned", rights=ALL_RIGHTS)

    def test_setting_the_status_by_hand_completes_the_return_once_everything_is_back(self) -> None:
        return_all(self.packlist)
        self.project.refresh_from_db()
        change_status(self.project, "returned", rights=ALL_RIGHTS)
        self.packlist.refresh_from_db()
        self.assertEqual(self.packlist.status, PacklistStatus.RETURNED)

    def test_missing_part_needs_a_note(self) -> None:
        set_returned(self.packlist, self.line.pk, self.cable.pk, D("2"))
        row = build_overview(self.packlist).rows[0]
        self.assertEqual(row.missing, D("1"))
        with self.assertRaises(ValidationError):
            resolve_missing(self.packlist, self.line.pk, self.cable.pk, "  ")
        with self.assertRaises(ValidationError):
            complete_return(self.packlist)
        resolve_missing(self.packlist, self.line.pk, self.cable.pk, "liegt beim Kunden")
        complete_return(self.packlist)
        row = build_overview(self.packlist).rows[0]
        self.assertTrue(row.missing_resolved)
        self.assertEqual(row.missing_note, "liegt beim Kunden")

    def test_returned_quantity_is_limited_to_what_went_out(self) -> None:
        set_returned(self.packlist, self.line.pk, self.cable.pk, D("99"))
        self.assertEqual(build_overview(self.packlist).rows[0].returned, D("3"))

    def test_return_is_only_possible_while_material_is_out(self) -> None:
        return_all(self.packlist)
        complete_return(self.packlist)
        with self.assertRaises(ValidationError):
            set_returned(self.packlist, self.line.pk, self.cable.pk, D("1"))
        with self.assertRaises(ValidationError):
            complete_return(self.packlist)
        with self.assertRaises(ValidationError):
            undo_issue(self.packlist)

    def test_undo_is_refused_once_something_came_back(self) -> None:
        set_returned(self.packlist, self.line.pk, self.cable.pk, D("1"))
        with self.assertRaises(ValidationError):
            undo_issue(self.packlist)

    def test_rows_that_vanished_from_the_planning_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            set_returned(self.packlist, 999999, self.cable.pk, D("1"))
