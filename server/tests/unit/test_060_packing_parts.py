# SPDX-License-Identifier: GPL-3.0-or-later
"""Packing for subprojects (PRJ-048) and material that goes straight from one part to the next (PRJ-060).

The stages of ``FamilyTestCase``: "Marktplatz" (10th–12th) and "Schlosspark"
(12th–14th). The six spotlights of the Marktplatz – the whole stock – go on
to the Schlosspark; the cables come from the warehouse for each stage.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, rights_of
from rentalars.api import webhook_events, webhooks
from rentalars.api.models import WebhookDelivery
from rentalars.core.models import AuditLogEntry
from rentalars.material.history import item_history
from rentalars.material.models import ItemStatus, MaterialItem
from rentalars.packing import subprojects
from rentalars.packing.models import Allocation, Handover, PackEntry, PacklistStatus
from rentalars.packing.pdf import render_family_html, render_packlist_html
from rentalars.packing.services import (
    build_overview,
    choose_items,
    complete_return,
    get_packlist,
    issue,
    pack_all,
    return_all,
    set_packed,
    set_returned,
    undo_issue,
)
from rentalars.products.services import set_kit_components
from rentalars.projects import services
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership, ProjectStatus
from tests.helpers import ALL_RIGHTS, add_line, make_product, make_stock, make_user
from tests.unit.test_060_subprojects import FamilyTestCase

D = Decimal


class PackingPartsTestCase(FamilyTestCase):
    """Six spots on the Marktplatz go on to the Schlosspark; cables from the warehouse for both."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-100", 6, "Spot")
        self.cable = make_stock("K-005", 20, "XLR-Kabel 5 m")
        self.source = add_line(self.market, self.spot, 6).line
        self.market_cables = add_line(self.market, self.cable, 10).line
        self.taking = services.take_over_line(self.source, self.park, rights=ALL_RIGHTS).line
        self.park_cables = add_line(self.park, self.cable, 4).line
        self.a = get_packlist(self.market)
        self.b = get_packlist(self.park)

    def row(self, packlist: object, line: object, product: object = None) -> object:
        """The row of a line on a packlist, freshly built."""
        packlist.refresh_from_db()  # type: ignore[attr-defined]
        product = product or self.spot
        return next(
            row
            for row in build_overview(packlist).rows  # type: ignore[arg-type]
            if row.line.pk == line.pk and row.product.pk == product.pk  # type: ignore[attr-defined]
        )

    def entry(self, packlist: object, line: object, product: object = None) -> PackEntry:
        """The stored progress of a row."""
        return PackEntry.objects.get(packlist=packlist, line=line, product=product or self.spot)

    def hand_over(self, quantity: int | None = None, **options: object) -> Handover:
        """Book the arrival of spots at the Schlosspark."""
        return subprojects.hand_over(
            self.b, self.taking.pk, self.spot.pk, D(quantity) if quantity is not None else None, **options
        )

    def spot_items(self) -> list[MaterialItem]:
        return list(MaterialItem.objects.for_product(self.spot.pk).order_by("inventory_number"))

    def refresh(self) -> None:
        for thing in (self.a, self.b, self.market, self.park):
            thing.refresh_from_db()


class TakeoverRowsTests(PackingPartsTestCase):
    """PRJ-060: the pieces appear on both packlists – once to pack in the warehouse, once to receive."""

    def test_both_packlists_name_the_other_part(self) -> None:
        source = self.row(self.a, self.source)
        self.assertFalse(source.is_takeover)
        self.assertEqual([(passing.project, passing.planned) for passing in source.passes_on], [(self.park, 6)])
        taking = self.row(self.b, self.taking)
        self.assertTrue(taking.is_takeover)
        self.assertEqual(taking.takeover_from, self.source)
        self.assertEqual((taking.required, taking.awaiting_handover, taking.to_issue), (6, 6, 0))

    def test_the_printed_packlists_say_where_the_pieces_come_from_and_go(self) -> None:
        market = render_packlist_html(build_overview(self.a))
        park = render_packlist_html(build_overview(self.b))
        self.assertIn(f"6 gehen weiter an {self.park.number} Bühne Schlosspark", market)
        self.assertIn(f"Übernahme aus {self.market.number} Bühne Marktplatz", park)

    def test_takeovers_are_not_packed_in_the_warehouse(self) -> None:
        overview = build_overview(self.b)
        self.assertEqual((overview.required_total, overview.takeover_total), (4, 6))
        with self.assertRaises(ValidationError):
            set_packed(self.b, self.taking.pk, self.spot.pk, D("6"))
        with self.assertRaises(ValidationError):
            choose_items(self.b, self.taking.pk, self.spot.pk, [self.spot_items()[0].pk])
        pack_all(self.b)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, PacklistStatus.PACKED)
        self.assertEqual(self.row(self.b, self.taking).packed, 0)

    def test_issuing_the_later_part_leaves_the_takeover_alone(self) -> None:
        issue(self.b)
        self.refresh()
        self.assertEqual(self.b.status, PacklistStatus.ISSUED)
        self.assertEqual(self.park.status, ProjectStatus.OUT)
        taking = self.row(self.b, self.taking)
        self.assertEqual((taking.issued, taking.awaiting_handover), (0, 6))
        # No free spot was noted for the Schlosspark: they come from the Marktplatz.
        self.assertFalse(Allocation.objects.filter(entry__packlist=self.b, entry__product=self.spot).exists())
        self.assertEqual({item.status for item in self.spot_items()}, {ItemStatus.AVAILABLE})

    def test_a_packlist_of_takeovers_only_has_nothing_to_issue(self) -> None:
        services.delete_line(self.park_cables)
        with self.assertRaises(ValidationError):
            issue(self.b)

    def test_kits_are_taken_over_component_by_component(self) -> None:
        kit = make_product("L-900", "Spotset", kind="kit", price="50.00")
        set_kit_components(kit, [(self.spot, 2), (self.cable, 2)])
        services.delete_line(self.taking)
        services.delete_line(self.source)
        source = add_line(self.market, kit, 3).line
        taking = services.take_over_line(source, self.park, rights=ALL_RIGHTS, quantity=2).line
        cable_row = self.row(self.a, source, self.cable)
        self.assertEqual([(passing.project, passing.planned) for passing in cable_row.passes_on], [(self.park, 4)])
        self.assertEqual(self.row(self.b, taking, self.spot).required, 4)
        issue(self.a)
        subprojects.hand_over(self.b, taking.pk, self.cable.pk)
        self.assertEqual(self.row(self.b, taking, self.cable).issued, 4)
        self.assertEqual(self.row(self.b, taking, self.spot).awaiting_handover, 4)
        self.assertEqual(self.entry(self.a, source, self.cable).handed_over_quantity, 4)


class HandoverTests(PackingPartsTestCase):
    """PRJ-060: the pieces arrive – for the Marktplatz they are back, for the Schlosspark out."""

    def setUp(self) -> None:
        super().setUp()
        issue(self.a)

    def test_full_handover(self) -> None:
        handover = self.hand_over()
        self.refresh()
        self.assertEqual(handover.quantity, 6)
        self.assertEqual(self.entry(self.a, self.source).handed_over_quantity, 6)
        self.assertEqual(self.entry(self.b, self.taking).issued_quantity, 6)
        source = self.row(self.a, self.source)
        self.assertEqual((source.missing, source.back, source.passes_on[0].handed), (0, 6, 6))
        self.assertEqual(self.row(self.b, self.taking).awaiting_handover, 0)
        # The cables of the Schlosspark are still in the warehouse: its packlist is partly out, and the
        # stage keeps its status until everything is out (PCK-025).
        self.assertEqual(self.b.status, PacklistStatus.PARTLY_ISSUED)
        self.assertEqual(self.park.status, ProjectStatus.CONFIRMED_OPEN)
        self.assertEqual(self.a.status, PacklistStatus.ISSUED)
        events = set(AuditLogEntry.objects.filter(event__startswith="packlist.hand").values_list("event", flat=True))
        self.assertEqual(events, {"packlist.handed_over", "packlist.handed_on"})

    def test_the_items_move_with_the_pieces(self) -> None:
        """MAT-025: the history of an item shows both stages."""
        self.assertEqual(Allocation.objects.filter(entry__packlist=self.a, returned_at__isnull=True).count(), 6)
        handover = self.hand_over()
        moved = Allocation.objects.filter(entry__packlist=self.b, returned_at__isnull=True)
        self.assertEqual(moved.count(), 6)
        self.assertEqual(set(moved.values_list("handover", flat=True)), {handover.pk})
        self.assertFalse(Allocation.objects.filter(entry__packlist=self.a, returned_at__isnull=True).exists())
        self.assertEqual({item.status for item in self.spot_items()}, {ItemStatus.IN_USE})
        history = item_history(self.spot_items()[0], ALL_RIGHTS)
        self.assertEqual(
            {row.project_number for row in history if row.kind == "deployment"}, {self.market.number, self.park.number}
        )
        self.assertEqual(self.row(self.b, self.taking).allocated_ids, [item.display_id for item in self.spot_items()])

    def test_partial_handover_and_the_rest(self) -> None:
        first = self.hand_over(4)
        self.assertEqual(self.row(self.b, self.taking).awaiting_handover, 2)
        self.assertEqual(self.row(self.a, self.source).missing, 2)
        # Which four spots went is not known: the items stay noted at the Marktplatz (PCK-020).
        self.assertFalse(Allocation.objects.filter(entry__packlist=self.b).exists())
        with self.assertRaises(ValidationError):
            self.hand_over(3)  # only two more are expected
        second = self.hand_over()
        self.assertEqual(second.quantity, 2)
        # Now every spot went to the Schlosspark: the items follow.
        self.assertEqual(Allocation.objects.filter(entry__packlist=self.b, handover=second).count(), 6)
        self.assertEqual(
            [booking.handover_id for booking in self.row(self.b, self.taking).handovers], [first.pk, second.pk]
        )
        with self.assertRaises(ValidationError):
            self.hand_over(1)  # nothing is expected any more

    def test_undo_restores_both_sides(self) -> None:
        handover = self.hand_over()
        subprojects.undo_handover(handover)
        self.refresh()
        self.assertFalse(Handover.objects.exists())
        self.assertEqual(self.entry(self.a, self.source).handed_over_quantity, 0)
        self.assertEqual(self.entry(self.b, self.taking).issued_quantity, 0)
        self.assertEqual(Allocation.objects.filter(entry__packlist=self.a, returned_at__isnull=True).count(), 6)
        self.assertFalse(Allocation.objects.filter(entry__packlist=self.b).exists())
        self.assertEqual({item.status for item in self.spot_items()}, {ItemStatus.IN_USE})
        # Nothing of the Schlosspark is out any more: back to packing; the project kept its status (PCK-025).
        self.assertEqual(self.b.status, PacklistStatus.OPEN)
        self.assertEqual(self.park.status, ProjectStatus.CONFIRMED_OPEN)
        self.assertEqual(self.row(self.a, self.source).missing, 6)

    def test_undo_takes_the_latest_booking_first(self) -> None:
        first = self.hand_over(4)
        second = self.hand_over(2)
        with self.assertRaises(ValidationError):
            subprojects.undo_handover(first)
        subprojects.undo_handover(second)
        self.assertEqual(
            Allocation.objects.filter(
                entry__packlist=self.a, entry__product=self.spot, returned_at__isnull=True
            ).count(),
            6,
        )
        self.assertFalse(Allocation.objects.filter(entry__packlist=self.b).exists())
        subprojects.undo_handover(first)
        self.assertEqual(self.entry(self.a, self.source).handed_over_quantity, 0)

    def test_not_before_the_earlier_part_is_out(self) -> None:
        undo_issue(self.a)
        with self.assertRaises(ValidationError):
            self.hand_over()

    def test_not_more_than_is_still_with_the_earlier_part(self) -> None:
        set_returned(self.a, self.source.pk, self.spot.pk, D("4"))
        with self.assertRaises(ValidationError) as caught:
            self.hand_over(3)
        self.assertIn("quantity", caught.exception.message_dict)
        self.assertEqual(self.hand_over().quantity, 2)
        # Four went back to the warehouse: which items went on is not known.
        self.assertFalse(Allocation.objects.filter(entry__packlist=self.b).exists())

    def test_only_rows_that_take_over(self) -> None:
        with self.assertRaises(ValidationError):
            subprojects.hand_over(self.b, self.park_cables.pk, self.cable.pk, D("1"))

    def test_the_earlier_packlist_must_be_writable_too(self) -> None:
        """PRJ-049: whoever works only on the Schlosspark cannot book for the Marktplatz."""
        Role.objects.create(
            name="Bühnencrew",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        crew = make_user("bert", roles=("Bühnencrew",))
        ProjectMembership.objects.create(project=self.park, user=crew, level=ProjectAccessLevel.READ)
        with self.assertRaises(ValidationError):
            self.hand_over(user=crew, rights=rights_of(crew))
        ProjectMembership.objects.create(project=self.market, user=crew, level=ProjectAccessLevel.READ)
        self.assertEqual(self.hand_over(user=crew, rights=rights_of(crew)).quantity, 6)

    def test_a_webhook_hears_of_it(self) -> None:
        """API-012: the new event, with counts in which the pieces handed on are no longer outstanding."""
        webhooks.create_webhook(url="https://erp.example.de/hook", events=["packing.handed_over"], description="ERP")
        handover = self.hand_over()
        subprojects.undo_handover(handover)
        booked, undone = WebhookDelivery.objects.order_by("pk")
        self.assertEqual(
            (booked.event, booked.data["quantity"], booked.data["undone"]), ("packing.handed_over", "6.00", False)
        )
        self.assertEqual(booked.data["from_project"]["id"], self.market.pk)
        self.assertEqual(booked.data["project"]["parent_project"]["id"], self.whole.pk)
        self.assertEqual(booked.data["from_packlist"]["counts"]["outstanding"], "10.00")
        self.assertEqual(booked.data["packlist"]["counts"]["outstanding"], "6.00")
        self.assertTrue(undone.data["undone"])
        self.assertEqual(undone.data["from_packlist"]["counts"]["outstanding"], "16.00")
        self.assertIn("packing.handed_over", webhook_events.SUBSCRIBABLE)


class ReturnTests(PackingPartsTestCase):
    """PRJ-060, PCK-019: pieces handed on count as back for the earlier part; the later part brings them home."""

    def setUp(self) -> None:
        super().setUp()
        issue(self.a)
        issue(self.b)

    def test_the_earlier_part_is_returned_without_the_pieces_handed_on(self) -> None:
        self.hand_over()
        set_returned(self.a, self.market_cables.pk, self.cable.pk, D("10"))
        overview = build_overview(self.a)
        self.assertEqual((overview.returned_total, overview.issued_total, overview.return_percent), (16, 16, 100))
        complete_return(self.a)
        self.refresh()
        self.assertEqual((self.a.status, self.market.status), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        # The spots are still out – with the Schlosspark.
        self.assertEqual({item.status for item in self.spot_items()}, {ItemStatus.IN_USE})

    def test_everything_is_back_leaves_out_what_waits_for_its_handover(self) -> None:
        return_all(self.a)
        self.assertEqual(self.entry(self.a, self.source).returned_quantity, 0)
        self.assertEqual(self.entry(self.a, self.market_cables, self.cable).returned_quantity, 10)
        with self.assertRaises(ValidationError) as caught:
            complete_return(self.a)
        self.assertIn(self.park.number, " ".join(caught.exception.messages))
        with self.assertRaises(ValidationError):
            services.change_status(self.market, ProjectStatus.RETURNED, rights=ALL_RIGHTS)
        self.hand_over()
        services.change_status(self.market, ProjectStatus.RETURNED, rights=ALL_RIGHTS)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, PacklistStatus.RETURNED)

    def test_after_the_earlier_return_nothing_more_is_handed_over_or_taken_back(self) -> None:
        handover = self.hand_over(4)
        set_returned(self.a, self.source.pk, self.spot.pk, D("2"))
        return_all(self.a)
        complete_return(self.a)
        with self.assertRaises(ValidationError):
            self.hand_over(2)
        with self.assertRaises(ValidationError):
            subprojects.undo_handover(handover)

    def test_the_later_part_brings_them_back_to_the_warehouse(self) -> None:
        self.hand_over()
        set_returned(self.b, self.taking.pk, self.spot.pk, D("6"))
        with self.assertRaises(ValidationError):
            subprojects.undo_handover(Handover.objects.get())
        return_all(self.b)
        complete_return(self.b)
        self.refresh()
        self.assertEqual((self.b.status, self.park.status), (PacklistStatus.RETURNED, ProjectStatus.RETURNED))
        self.assertEqual({item.status for item in self.spot_items()}, {ItemStatus.AVAILABLE})
        self.assertFalse(Allocation.objects.filter(returned_at__isnull=True, entry__product=self.spot).exists())

    def test_the_earlier_issue_cannot_be_taken_back_once_pieces_went_on(self) -> None:
        self.hand_over()
        with self.assertRaises(ValidationError):
            undo_issue(self.a)

    def test_taking_back_the_later_issue_keeps_what_was_handed_over(self) -> None:
        self.hand_over()
        undo_issue(self.b)
        self.refresh()
        self.assertEqual(self.b.status, PacklistStatus.PARTLY_ISSUED)
        self.assertEqual(self.park.status, ProjectStatus.OUT)
        self.assertEqual(self.entry(self.b, self.taking).issued_quantity, 6)
        self.assertEqual(self.entry(self.b, self.park_cables, self.cable).issued_quantity, 0)
        self.assertEqual(Allocation.objects.filter(entry__packlist=self.b, returned_at__isnull=True).count(), 6)


class LinesChangingTests(PackingPartsTestCase):
    """PRJ-060: without the takeover, the ordinary rules hold again."""

    def test_a_deleted_takeover_line(self) -> None:
        services.delete_line(self.taking)
        self.assertEqual(self.row(self.a, self.source).passes_on, [])
        issue(self.a)
        return_all(self.a)
        complete_return(self.a)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, PacklistStatus.RETURNED)

    def test_a_cleared_source(self) -> None:
        services.update_line(self.taking, rights=ALL_RIGHTS, taken_over_from=None)
        taking = self.row(self.b, self.taking)
        self.assertFalse(taking.is_takeover)
        set_packed(self.b, self.taking.pk, self.spot.pk, D("6"))
        self.assertEqual(self.row(self.b, self.taking).packed, 6)

    def test_a_line_with_a_handover_cannot_be_deleted(self) -> None:
        issue(self.a)
        self.hand_over()
        with self.assertRaises(ValidationError):
            services.delete_line(self.taking)


class FamilyPacklistTests(PackingPartsTestCase):
    """PRJ-048: the packlist of the whole project, part by part and per article."""

    def setUp(self) -> None:
        super().setUp()
        self.power = make_stock("S-100", 1, "Stromverteiler")
        add_line(self.whole, self.power, 1)

    def test_every_part_with_its_progress(self) -> None:
        issue(self.a)
        self.hand_over(4)
        family = subprojects.build_family_packlist(self.park, rights=ALL_RIGHTS, user=None)
        self.assertEqual(family.whole, self.whole)
        self.assertEqual([part.project for part in family.parts], [self.whole, self.market, self.park])
        self.assertEqual(family.hidden, 0)
        whole, market, park = (part.figures for part in family.parts)
        self.assertEqual((whole.required, whole.packed, whole.issued), (1, 0, 0))
        self.assertEqual(
            (market.required, market.packed, market.issued, market.passing_on, market.handed_on), (16, 16, 16, 6, 4)
        )
        self.assertEqual((park.required, park.taken_over, park.handed_in, park.out), (4, 6, 4, 4))
        self.assertEqual((family.figures.required, family.figures.issued), (21, 16))

    def test_summed_up_per_article(self) -> None:
        articles = {
            article.product.article_number: article
            for article in subprojects.build_family_packlist(self.whole, rights=ALL_RIGHTS, user=None).articles
        }
        self.assertEqual(list(articles), ["K-005", "L-100", "S-100"])
        self.assertEqual((articles["K-005"].from_warehouse, articles["K-005"].taken_over), (14, 0))
        spot = articles["L-100"]
        self.assertEqual((spot.from_warehouse, spot.taken_over), (6, 6))
        self.assertEqual(
            [(share.project, share.quantity, share.is_takeover) for share in spot.shares],
            [(self.market, 6, False), (self.park, 6, True)],
        )

    def test_a_part_the_user_may_not_see_is_left_out(self) -> None:
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.READ)},
            project_scope=ProjectScope.ASSIGNED,
        )
        external = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=external, level=ProjectAccessLevel.READ)
        ProjectMembership.objects.create(project=self.park, user=external, level=ProjectAccessLevel.NONE)
        family = subprojects.build_family_packlist(self.whole, rights=rights_of(external), user=external)
        self.assertEqual([part.project for part in family.parts], [self.whole, self.market])
        self.assertEqual(family.hidden, 1)
        self.assertEqual({article.product.article_number for article in family.articles}, {"K-005", "L-100", "S-100"})
        self.assertEqual(family.figures.required, 17)

    def test_printed_part_by_part_and_per_article(self) -> None:
        family = subprojects.build_family_packlist(self.whole, rights=ALL_RIGHTS, user=None)
        by_part = render_family_html(family, view=subprojects.VIEW_PARTS)
        self.assertIn("Bühne Schlosspark", by_part)
        self.assertIn(f"Übernahme aus {self.market.number} Bühne Marktplatz", by_part)
        per_article = render_family_html(family, view=subprojects.VIEW_ARTICLES)
        self.assertIn("Stromverteiler", per_article)
        self.assertIn("6 zusätzlich als Übernahme zwischen Teilprojekten", per_article)
        self.assertNotIn("10,00", per_article)  # no prices (PCK-007)
