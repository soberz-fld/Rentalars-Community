# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, helper "packing".

PCK-028: the return works like the issue – ticked, then booked – also while
only part of the material is out; per piece, what came back is done for the
project. PCK-029: the bar of a packlist. PCK-027: every change of a ticked
quantity notes its moment, on whatever way; the sync from the app keeps the
later change.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from rentalars.api.models import WebhookDelivery
from rentalars.availability.engine import AvailabilityEngine
from rentalars.material.models import ItemStatus
from rentalars.packing import offline, services, subprojects
from rentalars.packing.models import Allocation, PackEntry, PacklistStatus, material_out
from rentalars.projects.models import MaterialLine, Project, ProjectStatus
from rentalars.projects.services import create_subproject, take_over_line
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
    set_clock,
)
from tests.unit.test_060_webhooks import make_hook

D = Decimal


class PackingTestCase(RentalarsTestCase):
    """Ten cables and a single rack on one packlist of a confirmed project, 10 to 12 March."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 12, "XLR-Kabel 5 m")
        self.rack_product = make_product("T-500", "Funkrack")
        self.rack = make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.project = make_project()
        self.cable_line = add_line(self.project, self.cable, 10).line
        self.rack_line = add_line(self.project, self.rack_product, 1).line
        self.packlist = services.get_packlist(self.project)

    def tick(self, line: MaterialLine, quantity: int | str) -> None:
        services.set_packed(self.packlist, line.pk, line.product_id, D(quantity))

    def tick_back(self, line: MaterialLine, quantity: int | str) -> None:
        services.set_returned(self.packlist, line.pk, line.product_id, D(quantity))

    def issue_ticked(self) -> None:
        services.issue(self.packlist, only_packed=True)

    def row(self, article_number: str = "K-005") -> services.PackRow:
        self.packlist.refresh_from_db()
        return next(
            row for row in services.build_overview(self.packlist).rows if row.product.article_number == article_number
        )

    def statuses(self) -> tuple[str, str]:
        self.packlist.refresh_from_db()
        self.project.refresh_from_db()
        return self.packlist.status, self.project.status

    def is_out(self) -> bool:
        return Project.objects.filter(pk=self.project.pk).filter(material_out()).exists()


class PartialReturnTests(PackingTestCase):
    """PCK-028: tick what came back, book it; per piece – what came back does not go out again here."""

    def test_the_example_of_the_decision(self) -> None:
        """10 planned, 6 out, 4 back: those 4 are done, the other 4 can still go out, 2 of the 6 are still out."""
        self.tick(self.cable_line, 6)
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        self.tick_back(self.cable_line, 4)
        self.assertEqual(services.take_back(self.packlist), 4)
        row = self.row()
        self.assertEqual((row.issued, row.taken_back, row.still_out, row.to_issue), (6, 4, 2, 4))
        # The packed tick cannot go below what went out; the 4 taken back are not packed again.
        self.tick(self.cable_line, 0)
        self.assertEqual(self.row().packed, 6)
        self.tick(self.cable_line, 10)
        self.issue_ticked()
        row = self.row()
        self.assertEqual((row.issued, row.taken_back, row.still_out, row.to_issue), (10, 4, 6, 0))
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))

    def test_return_while_partly_issued_then_issue_and_return_again(self) -> None:
        self.tick(self.cable_line, 6)
        self.issue_ticked()
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.CONFIRMED))
        self.tick_back(self.cable_line, 6)
        services.take_back(self.packlist)
        # Nothing out any more, but the rest waits for its issue: neither "out" nor "returned".
        self.assertFalse(self.is_out())
        self.assertEqual(self.statuses(), (PacklistStatus.PARTLY_ISSUED, ProjectStatus.CONFIRMED))
        self.tick(self.cable_line, 10)
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        self.assertTrue(self.is_out())
        self.assertEqual(self.statuses(), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        self.tick_back(self.cable_line, 10)
        self.tick_back(self.rack_line, 1)
        services.take_back(self.packlist)
        # Nothing out and nothing waits: booking the return completed it.
        self.assertEqual(self.statuses(), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        self.assertIsNotNone(self.packlist.returned_at)

    def test_the_tick_books_nothing(self) -> None:
        self.tick(self.rack_line, 1)
        self.tick(self.cable_line, 10)
        self.issue_ticked()
        self.tick_back(self.rack_line, 1)
        self.tick_back(self.cable_line, 3)
        row = self.row()
        self.assertEqual((row.returned, row.taken_back, row.ready_to_take_back, row.still_out), (3, 0, 3, 10))
        self.assertEqual(row.missing, 7)  # ticked as back is physically back
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.IN_USE)
        overview = services.build_overview(self.packlist)
        self.assertEqual((overview.ready_back_total, overview.taken_back_total), (4, 0))

    def test_what_is_taken_back_cannot_be_unticked(self) -> None:
        self.tick(self.cable_line, 10)
        self.issue_ticked()
        self.tick_back(self.cable_line, 4)
        services.take_back(self.packlist)
        self.tick_back(self.cable_line, 1)
        self.assertEqual(self.row().returned, 4)
        self.assertEqual(services.return_limits(self.row()), (4, 10))
        self.tick_back(self.cable_line, 20)
        self.assertEqual(self.row().returned, 10)

    def test_nothing_ticked_is_not_booked(self) -> None:
        with self.assertRaises(ValidationError):
            services.take_back(self.packlist)  # nothing is out
        self.tick(self.cable_line, 10)
        self.issue_ticked()
        with self.assertRaises(ValidationError) as caught:
            services.take_back(self.packlist)
        self.assertIn("Hake ab, was zurückgekommen ist.", " ".join(caught.exception.messages))

    def test_a_taken_back_item_is_available_at_once_and_not_issued_again_here(self) -> None:
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.IN_USE)
        self.tick_back(self.rack_line, 1)
        services.take_back(self.packlist)
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.AVAILABLE)
        self.assertFalse(Allocation.objects.filter(item=self.rack, returned_at__isnull=True).exists())
        # A second rack line of the same project (a later phase): the rack is done here.
        second = add_line(self.project, self.rack_product, 1, start=at(11), end=at(12)).line
        row = next(row for row in services.build_overview(self.packlist).rows if row.line.pk == second.pk)
        choices = services.item_choices(self.packlist, row)
        self.assertEqual(
            [(item.pk, note, free) for item, note, free in choices],
            [(self.rack.pk, "aus diesem Projekt zurückgekommen", False)],
        )
        with self.assertRaises(ValidationError) as caught:
            services.choose_items(self.packlist, second.pk, self.rack_product.pk, [self.rack.pk])
        self.assertIn("werden darin nicht noch einmal ausgegeben", " ".join(caught.exception.messages))
        services.set_packed(self.packlist, second.pk, self.rack_product.pk, D(1))
        self.issue_ticked()
        self.assertFalse(Allocation.objects.filter(item=self.rack, returned_at__isnull=True).exists())
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.status, ItemStatus.AVAILABLE)
        # Another project may take it.
        other = make_project("Weinfest", start=at(11), end=at(13))
        other_line = add_line(other, self.rack_product, 1).line
        services.set_packed(services.get_packlist(other), other_line.pk, self.rack_product.pk, D(1))
        services.issue(services.get_packlist(other), only_packed=True)
        self.assertTrue(Allocation.objects.filter(item=self.rack, returned_at__isnull=True).exists())

    def test_items_of_a_row_back_in_part_stay_out_until_the_row_is_back(self) -> None:
        """PCK-020: which of two allocated items came back is not known until both are back."""
        spot = make_product("L-100", "Spot")
        first, second = make_items(make_model("Spot", spot), 2)
        line = add_line(self.project, spot, 2).line
        services.set_packed(self.packlist, line.pk, spot.pk, D(2))
        self.issue_ticked()
        self.assertEqual(Allocation.objects.filter(entry__line=line, returned_at__isnull=True).count(), 2)
        services.set_returned(self.packlist, line.pk, spot.pk, D(1))
        services.take_back(self.packlist)
        self.assertEqual(Allocation.objects.filter(entry__line=line, returned_at__isnull=True).count(), 2)
        services.set_returned(self.packlist, line.pk, spot.pk, D(2))
        services.take_back(self.packlist)
        self.assertFalse(Allocation.objects.filter(entry__line=line, returned_at__isnull=True).exists())
        for item in (first, second):
            item.refresh_from_db()
            self.assertEqual(item.status, ItemStatus.AVAILABLE)

    def test_completing_books_what_is_ticked_and_missing_parts_are_clarified(self) -> None:
        """PCK-016, PCK-019, PCK-023 keep working with the booking."""
        self.tick(self.cable_line, 10)
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        self.tick_back(self.cable_line, 8)
        self.tick_back(self.rack_line, 1)
        with self.assertRaises(ValidationError):
            services.complete_return(self.packlist)
        self.assertEqual(self.row().taken_back, 0)  # refused as a whole
        self.assertEqual(self.row().return_state, "partial")
        services.resolve_missing(self.packlist, self.cable_line.pk, self.cable.pk, "2 Kabel verloren")
        services.complete_return(self.packlist)
        self.assertEqual(self.statuses(), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        self.assertEqual((self.row().taken_back, self.row("T-500").taken_back), (8, 1))

    def test_an_item_that_did_not_come_back_is_blocked_not_available(self) -> None:
        """A row clarified as "lost" must not give the missing item back to the stock of the next project."""
        spot = make_product("L-100", "Spot")
        first, second = make_items(make_model("Spot", spot), 2)
        line = add_line(self.project, spot, 2).line
        services.set_packed(self.packlist, line.pk, spot.pk, D(2))
        self.issue_ticked()
        services.set_returned(self.packlist, line.pk, spot.pk, D(1))
        services.resolve_missing(self.packlist, line.pk, spot.pk, "einer ist verloren")
        services.complete_return(self.packlist)
        first.refresh_from_db()
        second.refresh_from_db()
        statuses = sorted([first.status, second.status])
        self.assertEqual(statuses, [ItemStatus.AVAILABLE, ItemStatus.BLOCKED])
        blocked = first if first.status == ItemStatus.BLOCKED else second
        self.assertIn("einer ist verloren", blocked.status_reason)

    def test_taking_back_an_issue_leaves_an_option_an_option(self) -> None:
        """The project has the status it had before the issue – it does not become "confirmed"."""
        self.project.status = ProjectStatus.OPTION
        self.project.save()
        self.packlist = services.get_packlist(Project.objects.get(pk=self.project.pk))
        self.tick(self.cable_line, 10)
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        self.assertEqual(self.statuses()[1], ProjectStatus.OUT)
        services.undo_issue(self.packlist)
        self.assertEqual(self.statuses()[1], ProjectStatus.OPTION)

    def test_a_defect_can_be_reported_on_return(self) -> None:
        """PCK-017 with a partial return."""
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        self.tick_back(self.rack_line, 1)
        services.take_back(self.packlist)
        report = services.report_return_defect(self.packlist, self.rack, "Lüfter defekt")
        self.assertEqual(report.item, self.rack)

    def test_setting_the_status_by_hand_books_the_ticks(self) -> None:
        from rentalars.projects.services import change_status

        self.tick(self.cable_line, 10)
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        services.return_all(self.packlist)
        change_status(self.project, ProjectStatus.RETURNED, rights=ALL_RIGHTS)
        self.assertEqual(self.statuses(), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        self.assertEqual(self.row().taken_back, 10)

    def test_ticks_are_events_and_the_completion_too(self) -> None:
        """API-012: more ticked as back is an event, as before; the booking that completes the return as well."""
        make_hook("packing.returned")
        self.tick(self.cable_line, 10)
        self.tick(self.rack_line, 1)
        self.issue_ticked()
        services.return_all(self.packlist)
        self.assertEqual(WebhookDelivery.objects.filter(event="packing.returned").count(), 1)
        services.take_back(self.packlist)
        last = WebhookDelivery.objects.filter(event="packing.returned").order_by("pk").last()
        self.assertTrue(last.data["complete"])


class AvailabilityAfterPartialReturnTests(PackingTestCase):
    """PCK-028: pieces taken back are free for others at once; what is out stays occupied."""

    def free_cables(self, start: datetime.datetime, end: datetime.datetime) -> int:
        return AvailabilityEngine().availability([self.cable.pk], start, end)[self.cable.pk].free

    def test_taken_back_pieces_are_free_from_their_return(self) -> None:
        self.tick(self.cable_line, 10)
        self.issue_ticked()
        set_clock(at(10, 12))
        self.assertEqual(self.free_cables(at(11), at(12)), 2)
        self.tick_back(self.cable_line, 4)
        self.assertEqual(self.free_cables(at(11), at(12)), 2)  # ticked only
        services.take_back(self.packlist)
        self.assertEqual(self.free_cables(at(11), at(12)), 6)
        # Before they came back they were out: the morning of the 10th still shows them.
        self.assertEqual(self.free_cables(at(10, 8), at(10, 9)), 2)

    def test_a_kit_frees_its_components(self) -> None:
        from rentalars.products.services import set_kit_components

        kit = make_product("T-900", "Kabel-Set", kind="kit", billing_mode="daily_kit")
        set_kit_components(kit, [(self.cable, 2)])
        kit_line = add_line(self.project, kit, 1).line
        services.set_packed(self.packlist, kit_line.pk, self.cable.pk, D(2))
        self.tick(self.cable_line, 10)
        self.issue_ticked()
        set_clock(at(10, 12))
        self.assertEqual(self.free_cables(at(11), at(12)), 0)
        services.set_returned(self.packlist, kit_line.pk, self.cable.pk, D(2))
        services.take_back(self.packlist)
        self.assertEqual(self.free_cables(at(11), at(12)), 2)


class BarTests(PackingTestCase):
    """PCK-029: grey in the warehouse, green hatched packed, green issued, orange hatched ticked back, orange back."""

    def test_the_five_states(self) -> None:
        self.tick(self.cable_line, 8)
        self.tick(self.rack_line, 1)
        self.issue_ticked()  # 8 cables and the rack out
        self.tick(self.cable_line, 9)  # one more packed
        self.tick_back(self.cable_line, 5)
        services.take_back(self.packlist)  # 5 back
        self.tick_back(self.cable_line, 7)  # 2 more ticked as back
        bar = services.build_overview(self.packlist).bar
        self.assertEqual((bar.back, bar.ticked_back, bar.out, bar.packed, bar.in_stock), (5, 2, 2, 1, 1))
        self.assertEqual(bar.total, 11)
        self.assertEqual(
            [(segment.name, segment.width, segment.label) for segment in bar.segments],
            [
                ("back", "45.45", "zurückgenommen"),
                ("ticked_back", "18.18", "zurück abgehakt"),
                ("out", "18.18", "ausgegeben"),
                ("packed", "9.09", "gepackt"),
                ("in_stock", "9.09", "im Lager"),
            ],
        )
        self.assertEqual(bar.summary, "5 zurückgenommen, 2 zurück abgehakt, 2 ausgegeben, 1 gepackt, 1 im Lager")

    def test_states_without_pieces_are_left_out(self) -> None:
        bar = services.build_overview(self.packlist).bar
        self.assertEqual([segment.name for segment in bar.segments], ["in_stock"])
        empty = make_project("Leer")
        self.assertEqual(services.build_overview(services.get_packlist(empty)).bar.segments, [])


class HandoverAndPartialReturnTests(RentalarsTestCase):
    """PCK-028 with PRJ-060: pieces go on from stage 1 to stage 2; each part takes back what it has."""

    def setUp(self) -> None:
        super().setUp()
        whole = make_project("Festival", start=at(9), end=at(14))
        self.first = create_subproject(whole, name="Bühne 1", start=at(10), end=at(11))
        self.later = create_subproject(whole, name="Bühne 2", start=at(12), end=at(13))
        self.spot = make_product("L-100", "Spot")
        make_items(make_model("Spot", self.spot), 6)
        self.source = add_line(self.first, self.spot, 6).line
        self.taking = take_over_line(self.source, self.later, rights=ALL_RIGHTS).line
        self.a = services.get_packlist(self.first)
        self.b = services.get_packlist(self.later)
        services.issue(self.a)

    def statuses(self, packlist: Any) -> tuple[str, str]:
        packlist.refresh_from_db()
        return packlist.status, packlist.project.status

    def test_each_part_takes_back_its_pieces(self) -> None:
        subprojects.hand_over(self.b, self.taking.pk, self.spot.pk, D(4))
        # Two pieces come back to the warehouse instead of going on: stage 1 is back completely.
        services.set_returned(self.a, self.source.pk, self.spot.pk, D(2))
        services.take_back(self.a)
        self.assertEqual(self.statuses(self.a), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        with self.assertRaises(ValidationError):
            subprojects.hand_over(self.b, self.taking.pk, self.spot.pk, D(2))
        # Stage 2 takes back in two steps.
        services.set_returned(self.b, self.taking.pk, self.spot.pk, D(3))
        services.take_back(self.b)
        self.assertTrue(Project.objects.filter(pk=self.later.pk).filter(material_out()).exists())
        services.set_returned(self.b, self.taking.pk, self.spot.pk, D(4))
        services.take_back(self.b)
        self.assertFalse(Project.objects.filter(pk=self.later.pk).filter(material_out()).exists())
        # Two pieces were still expected from stage 1: the return is completed by hand.
        self.assertEqual(self.statuses(self.b), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        services.complete_return(self.b)
        self.assertEqual(self.statuses(self.b), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        self.assertFalse(Allocation.objects.filter(entry__product=self.spot, returned_at__isnull=True).exists())

    def test_pieces_handed_over_count_as_back(self) -> None:
        subprojects.hand_over(self.b, self.taking.pk, self.spot.pk)
        row = next(row for row in services.build_overview(self.a).rows if row.line.pk == self.source.pk)
        self.assertEqual((row.still_out, row.bar.back, row.ready_to_take_back), (0, 6, 0))
        self.assertEqual(services.return_limits(row), (0, 0))


class ChangeTimeTests(PackingTestCase):
    """PCK-027: every change of the packed or the returned quantity notes its moment; no change, no new moment."""

    def entry(self, line: MaterialLine | None = None) -> PackEntry:
        line = line or self.cable_line
        return PackEntry.objects.get(packlist=self.packlist, line=line, product_id=line.product_id)

    def test_ticking_and_ticking_the_same_again(self) -> None:
        set_clock(at(9, 8))
        self.tick(self.cable_line, 4)
        self.assertEqual(self.entry().packed_changed_at, at(9, 8))
        self.assertIsNone(self.entry().returned_changed_at)
        self.assertIsNone(self.entry(self.rack_line).packed_changed_at)  # noted when packing started, not ticked
        set_clock(at(9, 9))
        self.tick(self.cable_line, 4)
        self.assertEqual(self.entry().packed_changed_at, at(9, 8))
        self.tick(self.cable_line, 5)
        self.assertEqual(self.entry().packed_changed_at, at(9, 9))

    def test_every_way(self) -> None:
        set_clock(at(9, 8))
        services.pack_all(self.packlist)
        self.assertEqual(self.entry(self.rack_line).packed_changed_at, at(9, 8))
        set_clock(at(9, 9))
        self.tick(self.cable_line, 6)
        set_clock(at(9, 10))
        services.issue(self.packlist, only_packed=False)  # "issue everything" packs the rest
        self.assertEqual(
            (self.entry().packed_changed_at, self.entry(self.rack_line).packed_changed_at), (at(9, 10), at(9, 8))
        )
        set_clock(at(12, 10))
        services.return_all(self.packlist)
        self.assertEqual(self.entry().returned_changed_at, at(12, 10))
        set_clock(at(12, 11))
        services.take_back(self.packlist)  # booking changes neither tick
        self.assertEqual(self.entry().returned_changed_at, at(12, 10))

    def test_changes_dealt_with(self) -> None:
        self.tick(self.cable_line, 10)
        MaterialLine.objects.filter(pk=self.cable_line.pk).update(quantity=D(6))
        set_clock(at(9, 12))
        services.acknowledge_changes(self.packlist)
        self.assertEqual((self.entry().packed_quantity, self.entry().packed_changed_at), (6, at(9, 12)))

    def test_the_handover_ticks_the_later_part(self) -> None:
        whole = make_project("Festival", start=at(9), end=at(14))
        first = create_subproject(whole, name="Bühne 1", start=at(10), end=at(11))
        later = create_subproject(whole, name="Bühne 2", start=at(12), end=at(13))
        spot = make_stock("L-100", 6, "Spot")
        source = add_line(first, spot, 6).line
        taking = take_over_line(source, later, rights=ALL_RIGHTS).line
        services.issue(services.get_packlist(first))
        set_clock(at(11, 18))
        subprojects.hand_over(services.get_packlist(later), taking.pk, spot.pk, D(4))
        entry = PackEntry.objects.get(line=taking)
        self.assertEqual((entry.packed_quantity, entry.packed_changed_at), (4, at(11, 18)))


class SyncTests(PackingTestCase):
    """PCK-027: the later change counts; at the same moment the server; the future counts as now."""

    def change(self, field: str, quantity: int, moment: datetime.datetime, line: MaterialLine | None = None) -> Any:
        line = line or self.cable_line
        return offline.Change(line.pk, line.product_id, field, D(quantity), moment)

    def entry(self) -> PackEntry:
        return PackEntry.objects.get(packlist=self.packlist, line=self.cable_line, product=self.cable)

    def test_the_later_change_counts(self) -> None:
        set_clock(at(9, 10))
        self.tick(self.cable_line, 5)
        set_clock(at(9, 12))
        results = offline.apply_changes(
            self.packlist,
            [
                self.change("packed", 7, at(9, 11)),
                self.change("packed", 2, at(9, 9)),
                self.change("packed", 3, at(9, 10)),
            ],
        )
        # The phone's 9:11 is later than the server's 9:10; 9:09 and 9:10 (a tie) are not – in the order sent.
        self.assertEqual([result.outcome for result in results], ["applied", "older", "older"])
        self.assertEqual((self.entry().packed_quantity, self.entry().packed_changed_at), (7, at(9, 11)))
        self.assertEqual(results[1].message, "Auf dem Server gilt eine spätere Änderung.")

    def test_of_several_changes_the_latest_remains(self) -> None:
        set_clock(at(9, 12))
        results = offline.apply_changes(
            self.packlist, [self.change("packed", 8, at(9, 11)), self.change("packed", 4, at(9, 10))]
        )
        # Taken in the order of their moments: 4 at 9:10, then 8 at 9:11.
        self.assertEqual([result.outcome for result in results], ["applied", "applied"])
        self.assertEqual((self.entry().packed_quantity, self.entry().packed_changed_at), (8, at(9, 11)))

    def test_the_future_counts_as_now(self) -> None:
        set_clock(at(9, 12))
        offline.apply_changes(self.packlist, [self.change("packed", 4, at(20, 12))])
        self.assertEqual(self.entry().packed_changed_at, at(9, 12))
        # A server change a minute later wins against what the phone claimed.
        set_clock(at(9, 12, 1))
        self.tick(self.cable_line, 2)
        self.assertEqual(self.entry().packed_quantity, 2)

    def test_limits_as_in_the_browser(self) -> None:
        set_clock(at(9, 12))
        results = offline.apply_changes(
            self.packlist,
            [
                self.change("packed", 11, at(9, 10)),
                self.change("returned", 1, at(9, 10)),
                offline.Change(999999, self.cable.pk, "packed", D(1), at(9, 10)),
            ],
        )
        self.assertEqual([result.outcome for result in results], ["refused"] * 3)
        self.assertEqual(results[0].message, "Gebraucht werden nur 10.")
        self.assertEqual(results[1].message, "Rücknahmen lassen sich nur buchen, solange das Material unterwegs ist.")
        self.tick(self.cable_line, 6)
        self.issue_ticked()
        self.tick_back(self.cable_line, 3)
        services.take_back(self.packlist)
        set_clock(at(11, 12))
        results = offline.apply_changes(
            self.packlist,
            [
                self.change("packed", 5, at(11, 10)),
                self.change("returned", 2, at(11, 10)),
                self.change("returned", 7, at(11, 10)),
                self.change("returned", 5, at(11, 11)),
            ],
        )
        self.assertEqual([result.outcome for result in results], ["refused", "refused", "refused", "applied"])
        self.assertEqual(
            [result.message for result in results[:3]],
            ["Davon sind schon 6 ausgegeben.", "Davon sind schon 3 zurückgenommen.", "Davon sind nur 6 unterwegs."],
        )
        self.assertEqual((self.entry().returned_quantity, self.entry().taken_back_quantity), (5, 3))

    def test_the_first_packed_tick_starts_packing(self) -> None:
        set_clock(at(9, 12))
        offline.apply_changes(self.packlist, [self.change("packed", 10, at(9, 11))])
        self.packlist.refresh_from_db()
        self.assertIsNotNone(self.packlist.packing_started_at)
        self.assertEqual(self.packlist.status, PacklistStatus.IN_PROGRESS)
        rack = PackEntry.objects.get(line=self.rack_line)
        self.assertEqual(rack.required_snapshot, 1)  # noted when packing started (PCK-015), not overwritten
        self.assertEqual(self.entry().required_snapshot, 10)


class OfflineProjectsTests(PackingTestCase):
    """PCK-026: the confirmed projects that are not finished, with the rule of opening a packlist."""

    def test_statuses(self) -> None:
        option = make_project("Option", status=ProjectStatus.OPTION)
        out = make_project("Unterwegs")
        Project.objects.filter(pk=out.pk).update(status=ProjectStatus.OUT)
        found = {entry.project.pk for entry in offline.offline_projects(ALL_RIGHTS, None)}
        self.assertIn(self.project.pk, found)
        self.assertIn(out.pk, found)
        self.assertNotIn(option.pk, found)


class MaterialOutTests(PackingTestCase):
    """PCK-028: material is out by the books – issued, neither taken back nor handed over; sold pieces never."""

    def test_sold_pieces_do_not_keep_the_project_out(self) -> None:
        tape = make_product("V-001", "Gaffa", kind="sale", billing_mode="flat", price=None, sale_price=D("14.90"))
        make_items(make_model("Gaffa", tape, bulk=True), 1, quantity=40)
        sold = make_project("Verkauf")
        line = add_line(sold, tape, 3).line
        packlist = services.get_packlist(sold)
        services.set_packed(packlist, line.pk, tape.pk, D(3))
        services.issue(packlist, only_packed=True)
        self.assertFalse(Project.objects.filter(pk=sold.pk).filter(material_out()).exists())
