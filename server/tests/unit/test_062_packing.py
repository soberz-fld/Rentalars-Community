# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the issue per article (PCK-025, changes PCK-018).

"Issue" books only what is ticked; the packlist is then *partly issued* and
packed further. The project becomes "out" only once everything is out, and
material that is out counts as out for the availability whatever the
project's status says.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from rentalars.api.models import WebhookDelivery
from rentalars.availability.engine import AvailabilityEngine
from rentalars.material.models import ItemStatus, MaterialItem
from rentalars.packing import services, subprojects
from rentalars.packing.models import Allocation, Packlist, PacklistStatus, material_out
from rentalars.projects.models import MaterialLine, Project, ProjectStatus
from rentalars.projects.services import change_status, create_subproject, take_over_line
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    make_item,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
)
from tests.unit.test_060_webhooks import make_hook

D = Decimal


class IssuePerArticleTestCase(RentalarsTestCase):
    """Six cables, a single rack and three rolls of tape for sale on one packlist."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 10, "XLR-Kabel 5 m")
        self.rack_product = make_product("T-500", "Funkrack")
        self.rack = make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.tape = make_product("V-001", "Gaffa", kind="sale", billing_mode="flat", price=None, sale_price=D("14.90"))
        make_items(make_model("Gaffa schwarz", self.tape, bulk=True), 1, quantity=40)
        self.project = make_project()
        self.cable_line = add_line(self.project, self.cable, 6).line
        self.rack_line = add_line(self.project, self.rack_product, 1).line
        self.tape_line = add_line(self.project, self.tape, 3).line
        self.packlist = services.get_packlist(self.project)

    def tick(self, line: MaterialLine, quantity: int, packlist: Packlist | None = None) -> None:
        services.set_packed(packlist or self.packlist, line.pk, line.product_id, D(quantity))

    def rows(self, packlist: Packlist | None = None) -> dict[str, services.PackRow]:
        packlist = packlist or self.packlist
        packlist.refresh_from_db()
        return {row.product.article_number: row for row in services.build_overview(packlist).rows}

    def statuses(self) -> tuple[str, str]:
        self.packlist.refresh_from_db()
        self.project.refresh_from_db()
        return self.packlist.status, self.project.status


class IssueTickedTests(IssuePerArticleTestCase):
    """PCK-025: "issue" books what is ticked; the rest is packed and issued later."""

    def test_issue_books_only_the_ticked_quantities(self) -> None:
        self.tick(self.cable_line, 4)
        self.tick(self.rack_line, 1)
        overview = services.build_overview(self.packlist)
        self.assertEqual(overview.ready_total, 5)
        services.issue(self.packlist, only_packed=True)
        rows = self.rows()
        self.assertEqual({number: row.issued for number, row in rows.items()}, {"K-005": 4, "T-500": 1, "V-001": 0})
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.CONFIRMED))
        self.assertTrue(rows["T-500"].is_issued_in_full)
        self.assertFalse(rows["K-005"].is_issued_in_full)
        self.assertEqual((rows["K-005"].to_issue, rows["K-005"].ready_to_issue), (2, 0))
        # Issued material is out all the same: the single rack is noted and in use (PCK-021).
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.IN_USE)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).filter(material_out()).exists())

    def test_packing_goes_on_and_the_rest_makes_the_project_out(self) -> None:
        self.tick(self.cable_line, 4)
        services.issue(self.packlist, only_packed=True)
        self.assertTrue(self.packlist.can_be_packed)
        self.tick(self.cable_line, 6)
        self.tick(self.tape_line, 3)
        self.assertEqual(services.build_overview(self.packlist).ready_total, 5)
        services.issue(self.packlist, only_packed=True)
        # The rack is not ticked yet: the packlist stays partly issued, the project keeps its status.
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.CONFIRMED))
        self.assertEqual(self.rows()["V-001"].issued, 3)
        self.tick(self.rack_line, 1)
        services.issue(self.packlist, only_packed=True)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_nothing_new_ticked_is_refused_with_a_hint(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            services.issue(self.packlist, only_packed=True)
        self.assertIn("oder gib alles aus", " ".join(caught.exception.messages))
        self.assertEqual(self.statuses(), (PacklistStatus.OPEN, ProjectStatus.CONFIRMED))
        self.assertFalse(self.packlist.entries.filter(issued_quantity__gt=0).exists())

    def test_issue_everything_books_every_row_in_full(self) -> None:
        self.tick(self.cable_line, 2)
        services.issue(self.packlist, only_packed=False)
        self.assertEqual(
            {number: row.issued for number, row in self.rows().items()}, {"K-005": 6, "T-500": 1, "V-001": 3}
        )
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_issue_everything_after_a_partial_issue_books_the_rest(self) -> None:
        self.tick(self.cable_line, 4)
        services.issue(self.packlist, only_packed=True)
        services.issue(self.packlist, only_packed=False)
        self.assertEqual(self.rows()["K-005"].issued, 6)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_an_option_partly_issued_keeps_its_status(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.OPTION)
        self.tick(self.cable_line, 6)
        services.issue(self.packlist, only_packed=True)
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.OPTION))
        services.issue(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))


class ReturnAndUndoTests(IssuePerArticleTestCase):
    """PCK-025, PCK-016, PCK-019: returns and taking back work with a partly issued packlist."""

    def test_partly_issued_partly_returned_then_the_rest(self) -> None:
        self.tick(self.cable_line, 4)
        self.tick(self.rack_line, 1)
        services.issue(self.packlist, only_packed=True)
        services.set_returned(self.packlist, self.cable_line.pk, self.cable.pk, D(2))
        self.assertEqual(self.rows()["K-005"].return_state, "partial")
        # The return cannot be taken back, and the rest still goes out.
        with self.assertRaises(ValidationError):
            services.undo_issue(self.packlist)
        self.tick(self.cable_line, 6)
        self.tick(self.tape_line, 3)
        services.issue(self.packlist, only_packed=True)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        row = self.rows()["K-005"]
        self.assertEqual((row.issued, row.returned, row.missing), (6, 2, 4))
        services.return_all(self.packlist)
        services.complete_return(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.AVAILABLE)

    def test_completing_the_return_of_a_partial_issue_leaves_the_rest_in_the_warehouse(self) -> None:
        self.tick(self.cable_line, 4)
        services.issue(self.packlist, only_packed=True)
        services.return_all(self.packlist)
        services.complete_return(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        with self.assertRaises(ValidationError):
            services.issue(self.packlist)

    def test_undo_takes_back_every_partial_issue(self) -> None:
        self.tick(self.cable_line, 2)
        services.issue(self.packlist, only_packed=True)
        self.tick(self.cable_line, 5)
        self.tick(self.rack_line, 1)
        services.issue(self.packlist, only_packed=True)
        services.undo_issue(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.IN_PROGRESS, ProjectStatus.CONFIRMED))
        rows = self.rows()
        self.assertEqual((rows["K-005"].issued, rows["K-005"].packed), (0, 5))
        self.assertFalse(Allocation.objects.exists())
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.AVAILABLE)

    def test_undo_of_a_complete_issue_makes_the_project_confirmed_again(self) -> None:
        MaterialLine.objects.filter(pk=self.tape_line.pk).delete()  # sold stock booked out cannot be taken back
        services.pack_all(self.packlist)
        services.issue(self.packlist, only_packed=True)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        services.undo_issue(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.PACKED, ProjectStatus.CONFIRMED))


class SeveralPacklistsTests(IssuePerArticleTestCase):
    """PCK-025, PCK-008: the project is "out" once every packlist with material from the warehouse is issued."""

    def setUp(self) -> None:
        super().setUp()
        self.truck = services.create_packlist(self.project, title="LKW 2")
        services.assign_lines(self.truck, [self.rack_line.pk])

    def test_one_issued_packlist_is_not_everything(self) -> None:
        services.pack_all(self.truck)
        services.issue(self.truck, only_packed=True)
        self.truck.refresh_from_db()
        self.assertEqual(self.truck.status, PacklistStatus.ISSUED)
        self.assertEqual(self.statuses(), (PacklistStatus.OPEN, ProjectStatus.CONFIRMED))
        services.pack_all(self.packlist)
        services.issue(self.packlist, only_packed=True)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_an_empty_packlist_does_not_hold_the_project_back(self) -> None:
        services.create_packlist(self.project, title="Leer")
        services.issue(self.packlist)
        services.issue(self.truck)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_one_packlist_back_before_the_other_went_out(self) -> None:
        services.issue(self.truck)
        services.return_all(self.truck)
        services.complete_return(self.truck)
        # The main packlist still waits: the project is not "returned".
        self.assertEqual(self.statuses(), (PacklistStatus.OPEN, ProjectStatus.CONFIRMED))
        services.issue(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        services.return_all(self.packlist)
        services.complete_return(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))

    def test_taking_back_one_issue_of_an_out_project(self) -> None:
        MaterialLine.objects.filter(pk=self.tape_line.pk).delete()
        services.issue(self.packlist)
        services.issue(self.truck)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        services.undo_issue(self.truck)
        # Material is still out with the main packlist: the project stays "out".
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        services.undo_issue(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.PACKED, ProjectStatus.CONFIRMED))


class ChangesAfterTheIssueTests(IssuePerArticleTestCase):
    """PCK-015, PCK-025: acknowledged changes of the planning settle whether something is left to issue."""

    def test_a_rest_no_longer_needed_completes_the_issue(self) -> None:
        self.tick(self.cable_line, 4)
        self.tick(self.rack_line, 1)
        self.tick(self.tape_line, 3)
        services.issue(self.packlist, only_packed=True)
        MaterialLine.objects.filter(pk=self.cable_line.pk).update(quantity=4)
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.CONFIRMED))
        services.acknowledge_changes(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_a_new_line_after_the_issue_can_be_packed_and_issued(self) -> None:
        services.issue(self.packlist)
        extra = add_line(self.project, self.cable, 2).line
        services.acknowledge_changes(self.packlist)
        # The project stays "out"; the packlist has a rest again.
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.OUT))
        self.tick(extra, 2)
        services.issue(self.packlist, only_packed=True)
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))


class ProjectStatusByHandTests(IssuePerArticleTestCase):
    """PCK-025, PCK-019: what can be set by hand while material is only partly out."""

    def setUp(self) -> None:
        super().setUp()
        self.tick(self.cable_line, 4)
        services.issue(self.packlist, only_packed=True)
        self.project.refresh_from_db()

    def test_partly_out_can_be_set_out_by_hand(self) -> None:
        change_status(self.project, ProjectStatus.CONFIRMED_OPEN, rights=ALL_RIGHTS)
        change_status(self.project, ProjectStatus.OUT, rights=ALL_RIGHTS)
        # More issued later does not change it; the rest can still go out.
        self.tick(self.rack_line, 1)
        services.issue(self.packlist, only_packed=True)
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.OUT))
        services.return_all(self.packlist)
        services.complete_return(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))

    def test_partly_out_cannot_go_back_or_be_cancelled(self) -> None:
        for status in (ProjectStatus.OPTION, ProjectStatus.CANCELLED):
            with self.assertRaises(ValidationError):
                change_status(self.project, status, rights=ALL_RIGHTS)
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.CONFIRMED))

    def test_a_whole_project_with_a_part_partly_out_cannot_be_cancelled(self) -> None:
        whole = make_project("Festival")
        part = create_subproject(whole, name="Bühne 1")
        line = add_line(part, self.cable, 2).line
        packlist = services.get_packlist(part)
        services.set_packed(packlist, line.pk, self.cable.pk, D(1))
        services.issue(packlist, only_packed=True)
        with self.assertRaises(ValidationError) as caught:
            change_status(whole, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        self.assertIn(part.number, " ".join(caught.exception.messages))
        whole.refresh_from_db()
        self.assertEqual(whole.status, ProjectStatus.CONFIRMED)


class TakeoverTests(RentalarsTestCase):
    """PRJ-060, PCK-025: pieces taken over from another subproject do not hold the project back."""

    def setUp(self) -> None:
        super().setUp()
        whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18))
        self.market = create_subproject(whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8))
        self.park = create_subproject(whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12))
        self.spot = make_stock("L-100", 6, "Spot")
        self.cable = make_stock("K-005", 20, "XLR-Kabel 5 m")
        self.source = add_line(self.market, self.spot, 6).line
        self.taking = take_over_line(self.source, self.park, rights=ALL_RIGHTS).line
        self.park_cables = add_line(self.park, self.cable, 4).line
        services.issue(services.get_packlist(self.market))
        self.b = services.get_packlist(self.park)
        self.assertEqual(self.park.status, ProjectStatus.CONFIRMED_OPEN)  # as a new part of a confirmed project

    def test_the_handover_alone_is_not_everything(self) -> None:
        subprojects.hand_over(self.b, self.taking.pk, self.spot.pk)
        self.b.refresh_from_db()
        self.park.refresh_from_db()
        self.assertEqual(
            (self.b.status, self.park.status), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.CONFIRMED_OPEN)
        )
        services.set_packed(self.b, self.park_cables.pk, self.cable.pk, D(4))
        services.issue(self.b, only_packed=True)
        self.b.refresh_from_db()
        self.park.refresh_from_db()
        self.assertEqual((self.b.status, self.park.status), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_pieces_still_to_arrive_do_not_hold_the_project_back(self) -> None:
        services.set_packed(self.b, self.park_cables.pk, self.cable.pk, D(4))
        services.issue(self.b, only_packed=True)
        self.b.refresh_from_db()
        self.park.refresh_from_db()
        self.assertEqual((self.b.status, self.park.status), (PacklistStatus.ISSUED, ProjectStatus.OUT))


class AvailabilityTests(RentalarsTestCase):
    """PCK-025: issued material is out whatever the status of its project says."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9)

    def partly_issue(self, project: Project, line: MaterialLine, quantity: int) -> None:
        packlist = services.get_packlist(project)
        services.set_packed(packlist, line.pk, line.product_id, D(quantity))
        services.issue(packlist, only_packed=True)

    def test_an_option_partly_out_reserves_firmly(self) -> None:
        project = make_project(status=ProjectStatus.OPTION)
        line = add_line(project, self.cable, 6).line
        before = AvailabilityEngine().availability([self.cable.pk], at(10), at(12))[self.cable.pk]
        self.assertEqual((before.firm, before.optional), (0, 6))
        self.partly_issue(project, line, 2)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.OPTION)
        after = AvailabilityEngine().availability([self.cable.pk], at(10), at(12))[self.cable.pk]
        self.assertEqual((after.firm, after.optional), (6, 0))

    def test_an_overdue_project_partly_out_keeps_its_material_occupied(self) -> None:
        now = timezone.now()
        project = make_project(start=now - datetime.timedelta(days=5), end=now - datetime.timedelta(days=2))
        line = add_line(project, self.cable, 6).line
        self.partly_issue(project, line, 4)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.CONFIRMED)
        window = (now - datetime.timedelta(hours=1), now + datetime.timedelta(days=1))
        self.assertEqual(AvailabilityEngine().availability([self.cable.pk], *window)[self.cable.pk].free, 3)
        # The quick check for the list of shortages sees it the same way.
        other = make_project("Messe", start=window[0], end=window[1])
        add_line(other, self.cable, 6)
        self.assertIn(other.pk, AvailabilityEngine().projects_that_may_be_short([project, other]))

    def test_items_issued_are_in_use_whatever_the_project_status(self) -> None:
        rack_product = make_product("T-500", "Funkrack")
        rack = make_item(make_model("Funkrack 4 HE", rack_product), 500)
        project = make_project()
        line = add_line(project, rack_product, 1).line
        add_line(project, self.cable, 2)
        self.partly_issue(project, line, 1)
        self.assertEqual(MaterialItem.objects.get(pk=rack.pk).status, ItemStatus.IN_USE)
        self.assertEqual(Allocation.objects.get(item=rack).entry.packlist.project, project)


class WebhookTests(IssuePerArticleTestCase):
    """API-012, PCK-025: every issue is an event; the project's status changes once everything is out."""

    def setUp(self) -> None:
        super().setUp()
        make_hook("project.status_changed", "packing.issued")

    def events(self) -> list[tuple[str, dict]]:
        return [(delivery.event, delivery.data) for delivery in WebhookDelivery.objects.order_by("pk")]

    def test_status_change_comes_with_the_last_issue(self) -> None:
        self.tick(self.cable_line, 6)
        services.issue(self.packlist, only_packed=True)
        [(event, data)] = self.events()
        self.assertEqual((event, data["complete"], data["project"]["status"]), ("packing.issued", False, "confirmed"))
        services.pack_all(self.packlist)
        services.issue(self.packlist, only_packed=True)
        (status_event, status_data), (event, data) = self.events()[1:]
        self.assertEqual((status_event, status_data["new_status"]), ("project.status_changed", "out"))
        self.assertEqual((event, data["complete"], data["project"]["status"]), ("packing.issued", True, "out"))
