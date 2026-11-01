# SPDX-License-Identifier: GPL-3.0-or-later
"""The availability calculation in its details (VFG-001 to VFG-018)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from rentalars.availability.engine import AvailabilityEngine, Demand, Firmness, firmness_of, peak_quantity
from rentalars.availability.services import open_shortages
from rentalars.availability.stock import stock_of_products
from rentalars.core.demo import create_demo_data
from rentalars.core.models import SystemSettings
from rentalars.material.models import MaterialItem
from rentalars.products.services import set_kit_components
from rentalars.projects.models import GroupKind, Project
from rentalars.projects.services import accept_subrental_suggestion, change_status
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    category,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
)


def demand(quantity: int, first: tuple[int, int], last: tuple[int, int], firmness: Firmness = Firmness.FIRM) -> Demand:
    """A demand of ``quantity`` pieces from ``(day, hour)`` to ``(day, hour)`` in March 2027."""
    return Demand(product_id=1, quantity=quantity, start=at(*first), end=at(*last), firmness=firmness)


class PeakQuantityTests(RentalarsTestCase):
    """VFG-002: what counts is the highest quantity occupied at the same time."""

    def test_reservations_one_after_the_other_do_not_add_up(self) -> None:
        """The example from the catalogue: 6 until the 12th and 2 from the 12th need 6, not 8."""
        demands = [demand(6, (10, 0), (12, 0)), demand(2, (12, 0), (14, 0))]
        self.assertEqual(peak_quantity(demands, at(10), at(14)), 6)

    def test_overlapping_reservations_add_up_only_while_they_overlap(self) -> None:
        demands = [demand(6, (10, 0), (12, 0)), demand(2, (11, 0), (14, 0)), demand(3, (13, 0), (15, 0))]
        self.assertEqual(peak_quantity(demands, at(10), at(15)), 8)
        self.assertEqual(peak_quantity(demands, at(12, 1), at(15)), 5)
        self.assertEqual(peak_quantity(demands, at(14, 1), at(15)), 3)

    def test_times_count_not_only_dates(self) -> None:
        """VFG-004: back at 10:00 does not block a start at 14:00 on the same day."""
        returned_in_the_morning = [demand(6, (10, 8), (12, 10))]
        self.assertEqual(peak_quantity(returned_in_the_morning, at(12, 14), at(13, 18)), 0)
        self.assertEqual(peak_quantity(returned_in_the_morning, at(12, 9), at(13, 18)), 6)

    def test_return_and_start_at_the_same_moment_do_not_collide(self) -> None:
        demands = [demand(6, (10, 8), (12, 10)), demand(6, (12, 10), (13, 18))]
        self.assertEqual(peak_quantity(demands, at(10), at(14)), 6)

    def test_nothing_reserved(self) -> None:
        self.assertEqual(peak_quantity([], at(10), at(12)), 0)
        self.assertEqual(peak_quantity([demand(0, (10, 0), (12, 0))], at(10), at(12)), 0)


class FirmnessTests(RentalarsTestCase):
    """Which project statuses reserve, and how firmly (PRJ-008, VFG-003)."""

    def test_status_decides(self) -> None:
        self.assertEqual(firmness_of("inquiry"), Firmness.NONE)
        self.assertEqual(firmness_of("option"), Firmness.SOFT)
        for status in ("confirmed_open", "confirmed", "out"):
            self.assertEqual(firmness_of(status), Firmness.FIRM, status)
        for status in ("returned", "closed", "cancelled"):
            self.assertEqual(firmness_of(status), Firmness.NONE, status)

    def test_optional_groups_reserve_softly_even_in_confirmed_projects(self) -> None:
        """PRJ-040."""
        self.assertEqual(firmness_of("confirmed", group_counts=False), Firmness.SOFT)

    def test_free_quantities_by_status(self) -> None:
        cable = make_stock("K-005", 9)
        project = make_project(status="inquiry")
        add_line(project, cable, 6)

        def figures() -> tuple[int, int, int]:
            answer = AvailabilityEngine().availability([cable.pk], at(10), at(12))[cable.pk]
            return answer.firm, answer.optional, answer.free

        self.assertEqual(figures(), (0, 0, 9))
        change_status(project, "option", rights=ALL_RIGHTS)
        self.assertEqual(figures(), (0, 6, 9))  # "9 stock, 0 firm, 6 optional"
        change_status(project, "confirmed", rights=ALL_RIGHTS)
        self.assertEqual(figures(), (6, 0, 3))
        change_status(project, "cancelled", rights=ALL_RIGHTS)
        self.assertEqual(figures(), (0, 0, 9))

    def test_collision_with_an_option_is_tight_not_short(self) -> None:
        cable = make_stock("K-005", 9)
        add_line(make_project("Option", status="option"), cable, 6)
        verdict = add_line(make_project("Fest"), cable, 5).availability
        self.assertEqual(verdict.status, "tight")
        self.assertEqual(verdict.shortage_total, 0)
        self.assertEqual(verdict.main.optional, 6)


class StockRuleTests(RentalarsTestCase):
    """What counts as stock (PRD-006, MAT-021, VFG-006)."""

    def free(self, product: object) -> int:
        return AvailabilityEngine().availability([product.pk], at(10), at(12))[product.pk].free  # type: ignore[attr-defined]

    def test_only_operational_items_count(self) -> None:
        cable = make_stock("K-005", 9)
        for number, status in enumerate(("defective", "in_repair", "blocked", "retired", "sold", "lost"), 1):
            MaterialItem.objects.filter(inventory_number=number).update(status=status)
        self.assertEqual(self.free(cable), 3)
        MaterialItem.objects.filter(inventory_number=7).update(status="in_use")
        self.assertEqual(self.free(cable), 3)

    def test_bulk_rows_count_their_quantity(self) -> None:
        """MAT-005."""
        tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=Decimal("14.90"))
        make_items(make_model("Gaffa schwarz", tape, bulk=True), 1, quantity=40)
        self.assertEqual(self.free(tape), 40)

    def test_items_assigned_individually_to_another_product(self) -> None:
        """PRD-003: the product named on the item wins over the product of its model."""
        cable = make_stock("K-005", 9)
        special = make_product("K-006")
        MaterialItem.objects.filter(inventory_number__in=[1, 2]).update(product_override=special)
        self.assertEqual(self.free(cable), 7)
        self.assertEqual(self.free(special), 2)

    def test_stock_is_counted_with_two_queries_however_many_products_are_asked_for(self) -> None:
        """NFA-014: the same answer for one product, for several and for all – and no query per product."""
        cable = make_stock("K-005", 9)
        special = make_product("K-006")
        lamp = make_stock("L-010", 4)
        without_material = make_product("K-007")
        MaterialItem.objects.filter(inventory_number__in=[1, 2]).update(product_override=special)
        MaterialItem.objects.filter(inventory_number=3).update(status="defective")
        MaterialItem.objects.filter(inventory_number=4).update(status="sold")

        with self.assertNumQueries(2):
            stocks = stock_of_products([cable.pk, special.pk, lamp.pk, without_material.pk])

        self.assertEqual((stocks[cable.pk].total, stocks[cable.pk].operational), (6, 5))
        self.assertEqual(stocks[special.pk].total, 2)
        self.assertEqual(stocks[lamp.pk].plannable, 4)
        self.assertNotIn(without_material.pk, stocks)
        # Asking for one product does not pick up the items that were moved to another one.
        self.assertEqual(stock_of_products([cable.pk]), {cable.pk: stocks[cable.pk]})
        self.assertEqual(stock_of_products([special.pk]), {special.pk: stocks[special.pk]})
        self.assertEqual(stock_of_products(None), stocks)
        with self.assertNumQueries(0):
            self.assertEqual(stock_of_products([]), {})

    def test_products_without_stock_are_not_checked(self) -> None:
        """PRD-030: services, transport and subrentals have nothing to run out of; PRD-045 incidental costs."""
        for article_number, fields in (
            ("N-001", {"kind": "incidental", "billing_mode": "hourly"}),
            ("F-001", {"kind": "incidental", "billing_mode": "flat"}),
            ("E-002", {"kind": "subrental", "billing_mode": "flat"}),
        ):
            product = make_product(article_number, **fields)
            answer = AvailabilityEngine().availability([product.pk], at(10), at(12))[product.pk]
            self.assertFalse(answer.checked, article_number)
            verdict = add_line(make_project(article_number), product, 99).availability
            self.assertEqual(verdict.status, "unchecked", article_number)


class BufferTests(RentalarsTestCase):
    """Buffer times before and after a deployment (VFG-005)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9)
        add_line(make_project(start=at(10, 8), end=at(12, 18)), self.cable, 9)

    def free(self, first: tuple[int, int], last: tuple[int, int]) -> int:
        return AvailabilityEngine().availability([self.cable.pk], at(*first), at(*last))[self.cable.pk].free

    def test_default_is_no_buffer(self) -> None:
        self.assertEqual(self.free((12, 18), (13, 18)), 9)
        self.assertEqual(self.free((9, 8), (10, 8)), 9)

    def test_system_wide_buffer(self) -> None:
        system_settings = SystemSettings.load()
        system_settings.buffer_before_hours = Decimal("2")
        system_settings.buffer_after_hours = Decimal("24")
        system_settings.save()
        self.assertEqual(self.free((12, 18), (13, 17)), 0)
        self.assertEqual(self.free((13, 18), (14, 18)), 9)
        self.assertEqual(self.free((9, 8), (10, 7)), 0)
        self.assertEqual(self.free((9, 8), (10, 6)), 9)

    def test_category_overrides_the_system_and_product_overrides_the_category(self) -> None:
        system_settings = SystemSettings.load()
        system_settings.buffer_after_hours = Decimal("24")
        system_settings.save()
        cables = category("K")
        cables.buffer_after_hours = Decimal("4")
        cables.save()
        self.assertEqual(self.free((12, 22), (13, 18)), 9)
        self.assertEqual(self.free((12, 21), (13, 18)), 0)

        self.cable.buffer_after_hours = Decimal("0")
        self.cable.save()
        self.assertEqual(self.free((12, 18), (13, 18)), 9)


class SpecialCaseTests(RentalarsTestCase):
    """Sales, overdue projects, kits, subrental (PRD-013, VFG-008, VFG-018)."""

    def test_sold_pieces_stay_occupied_until_they_leave_the_stock(self) -> None:
        tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=Decimal("14.90"))
        make_items(make_model("Gaffa schwarz", tape, bulk=True), 1, quantity=40)
        project = make_project(start=at(10), end=at(12))
        add_line(project, tape, 3)
        later = AvailabilityEngine().availability([tape.pk], at(20), at(22))[tape.pk]
        self.assertEqual(later.free, 37)
        earlier = AvailabilityEngine().availability([tape.pk], at(1), at(2))[tape.pk]
        self.assertEqual(earlier.free, 40)

    def test_overdue_project_keeps_its_material_occupied(self) -> None:
        """Material that is demonstrably still out is not free, whatever the plan said.

        Once it is booked back in, a rental product is in stock again (PRD-019).
        """
        cable = make_stock("K-005", 9)
        now = timezone.now()
        project = make_project(start=now - datetime.timedelta(days=5), end=now - datetime.timedelta(days=2))
        add_line(project, cable, 6)
        Project.objects.filter(pk=project.pk).update(status="out")
        today = AvailabilityEngine().availability(
            [cable.pk], now - datetime.timedelta(hours=1), now + datetime.timedelta(days=1)
        )
        self.assertEqual(today[cable.pk].free, 3)
        # Also for the days to come – nobody knows when it is back, so tomorrow's project must not get it
        later = AvailabilityEngine().availability(
            [cable.pk], now + datetime.timedelta(days=3), now + datetime.timedelta(days=4)
        )
        self.assertEqual(later[cable.pk].free, 3)
        Project.objects.filter(pk=project.pk).update(status="returned")
        today = AvailabilityEngine().availability(
            [cable.pk], now - datetime.timedelta(hours=1), now + datetime.timedelta(days=1)
        )
        self.assertEqual(today[cable.pk].free, 9)

    def test_kit_is_as_available_as_its_scarcest_component(self) -> None:
        """VFG-008."""
        cable = make_stock("K-010", 9)
        speaker = make_stock("T-010", 4)
        kit = make_product("T-100", kind="kit", billing_mode="daily_kit")
        set_kit_components(kit, [(speaker, 1), (cable, 2)])
        add_line(make_project(), cable, 4)
        answer = AvailabilityEngine().availability([kit.pk], at(10), at(12))[kit.pk]
        self.assertEqual(answer.stock.plannable, 4)
        self.assertEqual(answer.free, 2)  # 5 cables left, 2 per kit

    def test_nested_kits_are_resolved_down_to_real_products(self) -> None:
        cable = make_stock("K-010", 20)
        speaker = make_stock("T-010", 4)
        small = make_product("T-100", kind="kit", billing_mode="daily_kit")
        set_kit_components(small, [(speaker, 1), (cable, 2)])
        large = make_product("T-200", kind="kit", billing_mode="daily_kit")
        set_kit_components(large, [(small, 2), (cable, 1)])
        self.assertEqual(AvailabilityEngine().flatten(large.pk), {speaker.pk: 2, cable.pk: 5})
        verdict = add_line(make_project(), large, 3).availability
        self.assertEqual(verdict.status, "short")
        self.assertEqual({detail.product_id: detail.shortage for detail in verdict.shortages}, {speaker.pk: 2})

    def test_covered_quantity_does_not_burden_the_own_stock(self) -> None:
        """VFG-018: other projects and the shortage list reckon with the reduced quantity."""
        cable = make_stock("K-005", 9)
        add_line(make_project("P1", start=at(10), end=at(12)), cable, 6)
        second = make_project("P2", start=at(11), end=at(13))
        line = add_line(second, cable, 4).line
        self.assertEqual(len(open_shortages()), 2)

        accept_subrental_suggestion(line, cable, 1, rights=ALL_RIGHTS)

        self.assertEqual(open_shortages(), [])
        third = AvailabilityEngine().availability([cable.pk], at(11), at(12))[cable.pk]
        self.assertEqual((third.firm, third.free), (9, 0))

    def test_subrental_that_is_no_longer_needed_is_pointed_out(self) -> None:
        """PRJ-056."""
        cable = make_stock("K-005", 9)
        first = make_project("P1", start=at(10), end=at(12))
        blocking = add_line(first, cable, 6).line
        second = make_project("P2", start=at(11), end=at(13))
        line = add_line(second, cable, 4).line
        accept_subrental_suggestion(line, cable, 1, rights=ALL_RIGHTS)
        blocking.delete()

        lines = list(second.material_lines.select_related("product"))
        verdict = AvailabilityEngine().project_availability(second, lines)[line.pk]
        self.assertEqual(verdict.shortage_total, 0)
        self.assertEqual(verdict.excess_cover_total, 1)

    def test_optional_group_does_not_take_stock_from_the_lines_that_count(self) -> None:
        """PRJ-040."""
        lamp = make_stock("L-010", 6)
        project = make_project()
        optional = add_group(project, "Nebel und mehr", kind=GroupKind.OPTIONAL)
        add_line(project, lamp, 4, group=optional)
        counted = add_line(project, lamp, 6).availability
        self.assertEqual(counted.shortage_total, 0)

    def test_typed_candidate_is_checked_against_everything_already_planned(self) -> None:
        """PRJ-012: the answer while typing equals the answer after saving."""
        lamp = make_stock("L-010", 6)
        project = make_project()
        existing = add_line(project, lamp, 4).line
        engine = AvailabilityEngine()
        self.assertEqual(engine.check_candidate(project, lamp, 2, project.start, project.end).status, "ok")
        self.assertEqual(engine.check_candidate(project, lamp, 3, project.start, project.end).shortage_total, 1)
        # Editing the existing line must not count it against itself.
        edited = AvailabilityEngine().check_candidate(
            project, lamp, 6, project.start, project.end, exclude_line_id=existing.pk
        )
        self.assertEqual(edited.status, "ok")
        self.assertEqual(add_line(project, lamp, 3).availability.shortage_total, 1)


class QuickLineCheckTests(RentalarsTestCase):
    """The quick check of a single line gives the same verdict as the check of the whole project."""

    def test_same_verdict_for_every_line_of_the_sample_data(self) -> None:
        from rentalars.core.demo import create_demo_data
        from rentalars.projects.models import Project as ProjectModel

        create_demo_data()
        compared = 0
        for project in ProjectModel.objects.all():
            lines = list(project.material_lines.select_related("product"))
            full = AvailabilityEngine().project_availability(project, lines)
            for line in lines:
                quick = AvailabilityEngine().line_availability(line)
                self.assertEqual(quick, full[line.pk], f"{project.number}: {line.title}")
                compared += 1
        self.assertGreater(compared, 15)

    def test_same_verdict_with_kits_containers_subrentals_and_optional_groups(self) -> None:
        from rentalars.material.models import ConnectionType
        from rentalars.material.services import install_item

        cable = make_stock("K-010", 9)
        speaker = make_stock("T-010", 4)
        kit = make_product("T-100", kind="kit", billing_mode="daily_kit")
        set_kit_components(kit, [(speaker, 1), (cable, 1)])
        case_product = make_product("S-600")
        case = make_items(make_model("Case", case_product), 1)[0]
        receiver = make_stock("T-050", 3)
        loose = MaterialItem.objects.for_product(receiver.pk).first()
        install_item(loose, case, connection_type=ConnectionType.LOOSE)

        other = make_project("Anderes Projekt", start=at(11), end=at(13))
        add_line(other, cable, 3)
        project = make_project("Großes Projekt", start=at(10), end=at(12))
        optional = add_group(project, "Optional", kind=GroupKind.OPTIONAL)
        first = add_line(project, kit, 3).line
        add_line(project, cable, 5)
        add_line(project, kit, 2, group=optional)
        add_line(project, case_product, 1)
        add_line(project, receiver, 3)
        add_line(project, speaker, 2)
        accept_subrental_suggestion(first, speaker, 1, rights=ALL_RIGHTS)

        lines = list(project.material_lines.select_related("product"))
        full = AvailabilityEngine().project_availability(project, lines)
        self.assertTrue(any(verdict.shortage_total for verdict in full.values()))
        for line in lines:
            self.assertEqual(AvailabilityEngine().line_availability(line), full[line.pk], line.title)


class LongBufferTests(RentalarsTestCase):
    """VFG-005 meets PRD-013: buffers of a day or more next to material that never comes back."""

    def test_a_sale_line_and_a_day_of_buffer_do_not_break_the_calculation(self) -> None:
        """A sale has no end. Adding the buffer to "no end" once produced a date that does not exist."""
        system_settings = SystemSettings.load()
        system_settings.buffer_before_hours = Decimal("24")
        system_settings.buffer_after_hours = Decimal("48")
        system_settings.save()
        tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=Decimal("14.90"))
        make_items(make_model("Gaffa schwarz", tape, bulk=True), 1, quantity=40)
        cable = make_stock("K-005", 9)
        project = make_project(start=at(10), end=at(12))
        add_line(project, cable, 6)

        verdict = add_line(project, tape, 50).availability

        self.assertEqual(verdict.shortage_total, 10)
        self.assertEqual([entry.quantity for entry in open_shortages()], [10])
        # Sold is sold: weeks later the 50 rolls are still gone – ten more than there are.
        self.assertEqual(AvailabilityEngine().availability([tape.pk], at(20), at(22))[tape.pk].free, -10)


class ShortageOverviewTests(RentalarsTestCase):
    """The list of all open shortages (PRJ-057) and the quick test in front of it (NFA-012)."""

    def shortages_by_judging_every_project(self) -> set[tuple[str, int, str, int]]:
        """The slow, obviously right way: the exact calculation for every single project."""
        engine = AvailabilityEngine()
        found = set()
        for project in Project.objects.all():
            lines = list(project.material_lines.select_related("product"))
            for line in lines:
                for detail in engine.project_availability(project, lines)[line.pk].shortages:
                    found.add((project.name, line.pk, detail.product_id, detail.shortage))
        return found

    def shortages_of_the_overview(self) -> set[tuple[str, int, str, int]]:
        return {(entry.project.name, entry.line.pk, entry.product.pk, entry.quantity) for entry in open_shortages()}

    def test_overview_finds_exactly_what_judging_every_project_finds(self) -> None:
        cable = make_stock("K-010", 9)
        speaker = make_stock("T-010", 4)
        lamp = make_stock("L-010", 6)
        kit = make_product("T-100", kind="kit", billing_mode="daily_kit")
        set_kit_components(kit, [(speaker, 1), (cable, 2)])
        tape = make_product("V-001", kind="sale", billing_mode="flat", price=None, sale_price=Decimal("14.90"))
        make_items(make_model("Gaffa schwarz", tape, bulk=True), 1, quantity=40)

        # Two confirmed projects overlap: both show the shortage (cables 6 + 4 > 9).
        add_line(make_project("Fest A", start=at(10), end=at(12)), cable, 6)
        add_line(make_project("Fest B", start=at(11), end=at(13)), cable, 4)
        # Options do not push each other out, an inquiry is short on its own account.
        add_line(make_project("Option A", start=at(20), end=at(21), status="option"), lamp, 4)
        add_line(make_project("Option B", start=at(20), end=at(21), status="option"), lamp, 4)
        add_line(make_project("Anfrage", start=at(25), end=at(26), status="inquiry"), lamp, 8)
        # A kit is short of one component only; a subrental covers a part of it.
        kit_project = make_project("Sets", start=at(15), end=at(16))
        kit_line = add_line(kit_project, kit, 5).line
        accept_subrental_suggestion(kit_line, cable, 1, rights=ALL_RIGHTS)
        # An optional group, a sale that outlasts its project, and a project without any shortage.
        mixed = make_project("Gemischt", start=at(17), end=at(18))
        add_line(mixed, speaker, 3)
        add_line(mixed, speaker, 3, group=add_group(mixed, "Zugabe", kind=GroupKind.OPTIONAL))
        add_line(mixed, tape, 45)
        add_line(make_project("Entspannt", start=at(28), end=at(29)), cable, 2)
        # Overdue: out since February and not back, so the project that started this morning runs short.
        overdue = make_project("Überfällig", start=at(20, month=2), end=at(25, month=2))
        add_line(overdue, lamp, 5)
        Project.objects.filter(pk=overdue.pk).update(status="out")
        add_line(make_project("Heute", start=at(1, 7), end=at(2)), lamp, 3)
        # Finished projects are no longer looked at.
        done = make_project("Vorbei", start=at(10), end=at(12))
        add_line(done, cable, 9)
        Project.objects.filter(pk=done.pk).update(status="cancelled")

        expected = self.shortages_by_judging_every_project()

        self.assertEqual(self.shortages_of_the_overview(), expected)
        self.assertEqual(
            {name for name, _line, _product, _quantity in expected},
            # The overdue lamps stay occupied, so the two options of later days run short as well
            {"Fest A", "Fest B", "Anfrage", "Sets", "Gemischt", "Heute", "Option A", "Option B"},
        )

    def test_sample_data(self) -> None:
        create_demo_data()
        self.assertEqual(self.shortages_of_the_overview(), self.shortages_by_judging_every_project())

    def test_quick_test_names_only_the_projects_that_can_be_short(self) -> None:
        """The example from the description of ``projects_that_may_be_short``."""
        cable = make_stock("K-010", 50)
        first = make_project("A", start=at(10), end=at(12))
        second = make_project("B", start=at(11), end=at(13))
        third = make_project("C", start=at(10, month=4), end=at(12, month=4))
        for project, quantity in ((first, 30), (second, 30), (third, 10)):
            add_line(project, cable, quantity)

        candidates = AvailabilityEngine().projects_that_may_be_short([first, second, third])

        self.assertEqual(candidates, {first.pk, second.pk})

        # As an inquiry B reserves nothing: A has all it needs, B would still be short.
        Project.objects.filter(pk=second.pk).update(status="inquiry")
        second.refresh_from_db()
        self.assertEqual(AvailabilityEngine().projects_that_may_be_short([first, second, third]), {second.pk})
        self.assertEqual({entry.project.name for entry in open_shortages()}, {"B"})

    def test_number_of_queries_does_not_grow_with_the_number_of_projects(self) -> None:
        """NFA-012: a thousand projects without shortage must not cost a thousand calculations."""
        cable = make_stock("K-010", 50)
        lamp = make_stock("L-010", 50)

        def add_projects(count: int, first_day: int) -> None:
            for index in range(count):
                project = make_project(
                    f"Projekt {first_day + index}", start=at(first_day + index), end=at(first_day + index + 2)
                )
                add_line(project, cable, 3)
                add_line(project, lamp, 2)

        add_projects(3, 2)
        with CaptureQueriesContext(connection) as few:
            self.assertEqual(open_shortages(), [])
        add_projects(15, 8)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(open_shortages(), [])

        self.assertEqual(len(many), len(few))
        self.assertLess(len(many), 20)
