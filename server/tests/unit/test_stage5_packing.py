# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the packing overhaul of stage 5.

PCK-004 (order), PCK-006 (weight), PCK-008 (several packlists), PCK-013 (addendum), PCK-015 (changes),
PCK-017 (defect on return), PCK-018 (issue and return in parts), PCK-022 (chosen items), MAT-032 (overdue
inspections), MAT-037 (contents go along), MAT-042 (what stays behind).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.masterdata.models import StorageLocation
from rentalars.material.models import ConnectionType, InspectionType, ItemStatus, MaterialItem
from rentalars.material.services import install_item
from rentalars.packing import services
from rentalars.packing.models import Allocation, PacklistStatus
from rentalars.projects.models import ProjectStatus
from rentalars.projects.services import change_status, update_line
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    category,
    make_item,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
)


class SeveralPacklistTests(RentalarsTestCase):
    """PCK-008: per truck or trade; the project is out once everything is out (PCK-025)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.cable = add_line(self.project, make_stock("K-005", 10), 6).line
        self.light = add_line(self.project, make_stock("L-010", 4), 2).line
        self.main = services.get_packlist(self.project)
        self.truck = services.create_packlist(self.project, title="LKW 2")

    def test_lines_move_and_are_packed_on_their_own(self) -> None:
        self.assertEqual(services.assign_lines(self.truck, [self.light.pk]), 1)
        self.assertEqual([row.line for row in services.build_overview(self.main).rows], [self.cable])
        self.assertEqual([row.line for row in services.build_overview(self.truck).rows], [self.light])
        services.issue(self.truck)
        self.main.refresh_from_db()
        self.project.refresh_from_db()
        # PCK-025: the cables of the main packlist are still in the warehouse – not everything is out.
        self.assertEqual((self.main.status, self.project.status), (PacklistStatus.OPEN, ProjectStatus.CONFIRMED))
        services.issue(self.main)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.OUT)
        services.return_all(self.truck)
        services.complete_return(self.truck)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.OUT)  # the cables are still out
        services.return_all(self.main)
        services.complete_return(self.main)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.RETURNED)

    def test_rules(self) -> None:
        with self.assertRaises(ValidationError):
            services.create_packlist(self.project, title=" ")
        with self.assertRaises(ValidationError):
            services.delete_packlist(self.main)
        services.assign_lines(self.truck, [self.light.pk])
        services.issue(self.truck)
        with self.assertRaises(ValidationError):
            services.assign_lines(self.main, [self.light.pk])
        with self.assertRaises(ValidationError):
            services.delete_packlist(self.truck)
        other = services.create_packlist(self.project, title="Leer")
        services.delete_packlist(other)
        with self.assertRaises(ValidationError):
            services.assign_lines(self.truck, [add_line(make_project("Anderes"), make_stock("K-010", 1), 1).line.pk])

    def test_moving_back_to_main_drops_the_ticks(self) -> None:
        services.assign_lines(self.truck, [self.light.pk])
        services.set_packed(self.truck, self.light.pk, self.light.product_id, Decimal(2))
        services.assign_lines(self.main, [self.light.pk])
        row = next(row for row in services.build_overview(self.main).rows if row.line == self.light)
        self.assertEqual(row.packed, 0)

    def test_guard_of_the_project_status_looks_at_every_packlist(self) -> None:
        services.assign_lines(self.truck, [self.light.pk])
        services.issue(self.truck)
        services.issue(self.main)
        with self.assertRaises(ValidationError):
            change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        services.return_all(self.truck)
        with self.assertRaises(ValidationError):
            change_status(self.project, ProjectStatus.RETURNED, rights=ALL_RIGHTS)  # the cables are not back
        services.return_all(self.main)
        change_status(self.project, ProjectStatus.RETURNED, rights=ALL_RIGHTS)
        self.truck.refresh_from_db()
        self.main.refresh_from_db()
        self.assertEqual((self.truck.status, self.main.status), (PacklistStatus.RETURNED, PacklistStatus.RETURNED))


class PartialIssueTests(RentalarsTestCase):
    """PCK-018, PCK-025: issue what is ticked, the rest later; returns as soon as something is out."""

    def test_issue_in_two_steps(self) -> None:
        project = make_project()
        line = add_line(project, make_stock("K-005", 10), 6).line
        packlist = services.get_packlist(project)
        services.set_packed(packlist, line.pk, line.product_id, Decimal(4))
        services.issue(packlist, only_packed=True)
        packlist.refresh_from_db()
        self.assertEqual(packlist.status, PacklistStatus.PARTLY_ISSUED)
        row = services.build_overview(packlist).rows[0]
        self.assertEqual((row.issued, row.to_issue), (4, 2))
        with self.assertRaises(ValidationError):
            services.issue(packlist, only_packed=True)  # nothing new is ticked
        services.set_packed(packlist, line.pk, line.product_id, Decimal(1))
        self.assertEqual(services.build_overview(packlist).rows[0].packed, 4)  # issued stays packed
        services.set_returned(packlist, line.pk, line.product_id, Decimal(2))
        services.issue(packlist)
        packlist.refresh_from_db()
        self.assertEqual(packlist.status, PacklistStatus.ISSUED)
        self.assertEqual(services.build_overview(packlist).rows[0].issued, 6)

    def test_complete_after_a_partial_issue(self) -> None:
        project = make_project()
        line = add_line(project, make_stock("K-005", 10), 6).line
        packlist = services.get_packlist(project)
        services.set_packed(packlist, line.pk, line.product_id, Decimal(2))
        services.issue(packlist, only_packed=True)
        services.return_all(packlist)
        services.complete_return(packlist)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.RETURNED)

    def test_undo_a_partial_issue(self) -> None:
        project = make_project()
        line = add_line(project, make_stock("K-005", 10), 6).line
        packlist = services.get_packlist(project)
        services.set_packed(packlist, line.pk, line.product_id, Decimal(2))
        services.issue(packlist, only_packed=True)
        services.undo_issue(packlist)
        project.refresh_from_db()
        self.assertEqual((packlist.status, project.status), (PacklistStatus.IN_PROGRESS, ProjectStatus.CONFIRMED))


class ChosenItemTests(RentalarsTestCase):
    """PCK-022: items chosen where it matters; MAT-032: warned about overdue inspections."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_product("L-010", "PAR 64")
        self.model = make_model("PAR 64", self.product, category_code="L")
        self.items = make_items(self.model, 4)
        self.project = make_project()
        self.line = add_line(self.project, self.product, 2).line
        self.packlist = services.get_packlist(self.project)

    def test_choose_and_issue(self) -> None:
        services.choose_items(self.packlist, self.line.pk, self.product.pk, [self.items[2].pk, self.items[3].pk])
        row = services.build_overview(self.packlist).rows[0]
        self.assertEqual([chosen.display_id for chosen in row.chosen], ["0003", "0004"])
        self.assertEqual(row.allocated_ids, [])
        services.issue(self.packlist)
        self.assertEqual(
            set(MaterialItem.objects.filter(status=ItemStatus.IN_USE).values_list("inventory_number", flat=True)),
            {3, 4},
        )
        self.assertEqual(services.build_overview(self.packlist).rows[0].allocated_ids, ["0003", "0004"])
        services.return_all(self.packlist)
        # PCK-028: the tick books nothing; the items are free once the return is booked.
        self.assertEqual(MaterialItem.objects.filter(status=ItemStatus.IN_USE).count(), 2)
        services.take_back(self.packlist)
        self.assertFalse(MaterialItem.objects.filter(status=ItemStatus.IN_USE).exists())

    def test_rules_of_choosing(self) -> None:
        with self.assertRaises(ValidationError):
            services.choose_items(self.packlist, self.line.pk, self.product.pk, [item.pk for item in self.items[:3]])
        stranger = make_items(make_model("Kabel", make_product("K-005")))[0]
        with self.assertRaises(ValidationError):
            services.choose_items(self.packlist, self.line.pk, self.product.pk, [stranger.pk])
        other = make_project("Anderes")
        other_line = add_line(other, self.product, 1).line
        services.choose_items(services.get_packlist(other), other_line.pk, self.product.pk, [self.items[0].pk])
        with self.assertRaises(ValidationError):
            services.choose_items(self.packlist, self.line.pk, self.product.pk, [self.items[0].pk])
        choices = services.item_choices(self.packlist, services.build_overview(self.packlist).rows[0])
        self.assertEqual(
            [(item.display_id, free) for item, _note, free in choices][:2], [("0001", False), ("0002", True)]
        )

    def test_overdue_inspection(self) -> None:
        electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        electric.categories.add(category("L"))
        row = services.build_overview(self.packlist).rows[0]
        self.assertIn("4 Exemplare im Bestand mit überfälliger Prüfung", row.hints)
        warnings = services.choose_items(self.packlist, self.line.pk, self.product.pk, [self.items[0].pk])
        self.assertEqual(warnings, ["Die Prüfung von 0001 ist überfällig."])
        hints = services.issue(self.packlist)
        self.assertIn("0001 ist ausgegeben, obwohl seine Prüfung überfällig ist.", hints)


class ContentsTests(RentalarsTestCase):
    """MAT-037: what is inside the container goes out and comes back with it; MAT-042: except what stays."""

    def setUp(self) -> None:
        super().setUp()
        self.case_product = make_product("S-600", "Funkcase")
        self.case = make_item(make_model("Case", self.case_product), 600)
        receiver_model = make_model("Empfänger", make_product("T-050", "Funkempfänger"))
        self.fixed = make_item(receiver_model, 310)
        self.loose = make_item(receiver_model, 311)
        self.stays = make_item(receiver_model, 312)
        install_item(self.fixed, self.case, connection_type=ConnectionType.FIXED)
        install_item(self.loose, self.case, connection_type=ConnectionType.LOOSE)
        install_item(self.stays, self.case, connection_type=ConnectionType.LOOSE)
        self.project = make_project()
        add_line(self.project, self.case_product, 1)
        services.extract(self.project, self.stays)
        self.packlist = services.get_packlist(self.project)

    def test_contents_listed_and_issued(self) -> None:
        overview = services.build_overview(self.packlist, with_contents=True)
        row = overview.rows[0]
        self.assertEqual(
            [(content.display_id, content.state) for content in row.contents],
            [("0310", "along"), ("0311", "along"), ("0312", "extracted")],
        )
        self.assertIn("0312 Empfänger bleibt da (aus 0600 herausgelöst)", row.hints)
        services.issue(self.packlist)
        out = set(Allocation.objects.filter(returned_at__isnull=True).values_list("item__inventory_number", flat=True))
        self.assertEqual(out, {600, 310, 311})
        services.return_all(self.packlist)
        services.take_back(self.packlist)  # PCK-028: the return is ticked, then booked
        self.assertFalse(Allocation.objects.filter(returned_at__isnull=True).exists())
        self.assertEqual(MaterialItem.objects.filter(status=ItemStatus.IN_USE).count(), 0)


class ChangeTests(RentalarsTestCase):
    """PCK-015: changes after packing started are marked until acknowledged; PCK-013: addendum."""

    def test_changed_new_and_removed_rows(self) -> None:
        project = make_project()
        cable = add_line(project, make_stock("K-005", 10), 6).line
        light = add_line(project, make_stock("L-010", 4), 2).line
        packlist = services.get_packlist(project)
        services.set_packed(packlist, light.pk, light.product_id, Decimal(2))
        self.assertFalse(services.build_overview(packlist).has_changes)
        update_line(cable, rights=ALL_RIGHTS, quantity=Decimal(8))
        light.delete()
        stand = add_line(project, make_stock("S-020", 4), 2).line
        overview = services.build_overview(packlist)
        changes = {row.line.pk: (row.change, row.was_required) for row in overview.rows}
        self.assertEqual(changes, {cable.pk: ("changed", Decimal("6.00")), stand.pk: ("new", None)})
        self.assertEqual([(removed.article_number, removed.packed) for removed in overview.removed], [("L-010", 2)])
        services.acknowledge_changes(packlist)
        self.assertFalse(services.build_overview(packlist).has_changes)

    def test_addendum(self) -> None:
        project = make_project()
        add_line(project, make_stock("K-005", 10), 6)
        truck = services.create_packlist(project, title="LKW 2")
        tape = make_stock("V-001", 3, "Gaffa")
        warnings = services.add_material(truck, tape, Decimal(5), user=make_user("luka"), rights=ALL_RIGHTS)
        self.assertEqual(warnings, ["Fehlmenge: 2 × V-001 sind im Zeitraum nicht frei."])
        row = services.build_overview(truck).rows[0]
        self.assertTrue(row.line.is_addendum)
        self.assertEqual((row.required, row.packed, row.change), (5, 5, ""))


class ReturnDefectTests(RentalarsTestCase):
    """PCK-017: a defect per item on return."""

    def test_report(self) -> None:
        project = make_project()
        product = make_stock("K-005", 3)
        add_line(project, product, 2)
        packlist = services.get_packlist(project)
        item = MaterialItem.objects.for_product(product.pk).first()
        with self.assertRaises(ValidationError):
            services.report_return_defect(packlist, item, "Stecker ab")
        services.issue(packlist)
        report = services.report_return_defect(packlist, item, "Stecker ab", user=make_user("luka"))
        self.assertIn(project.number, report.context)
        item.refresh_from_db()
        self.assertEqual(item.status, ItemStatus.DEFECTIVE)
        foreign = make_items(make_model("Fremd", make_product("L-010")))[0]
        with self.assertRaises(ValidationError):
            services.report_return_defect(packlist, foreign, "kaputt")


class OrderAndWeightTests(RentalarsTestCase):
    """PCK-004: by category or storage location; PCK-006: weight and volume."""

    def test_order_and_sums(self) -> None:
        project = make_project()
        hall = StorageLocation.objects.create(name="Halle 1")
        shelf = StorageLocation.objects.create(name="Regal A", parent=hall)
        light_model = make_model("PAR 64", make_product("L-010"), category_code="L")
        light_model.weight_kg, light_model.length_cm, light_model.width_cm, light_model.height_cm = (
            Decimal("5"),
            Decimal("30"),
            Decimal("30"),
            Decimal("40"),
        )
        light_model.save()
        make_items(light_model, 4, storage_location=shelf)
        cable = make_stock("K-005", 10)
        group = add_group(project, "Bühne")
        add_line(project, cable, 6, group=group)
        add_line(project, light_model.default_product, 3)
        packlist = services.get_packlist(project)
        by_category = services.build_overview(packlist, order="category")
        self.assertEqual([section.title for section in by_category.sections], ["Kabel", "Licht"])
        by_location = services.build_overview(packlist, order="location")
        self.assertEqual([section.title for section in by_location.sections], ["Halle 1 > Regal A", "Ohne Lagerort"])
        self.assertEqual((by_location.weight_kg, by_location.volume_litres), (Decimal("15"), Decimal("108.0")))
        self.assertEqual(by_location.rows_without_weight, 1)
        self.assertTrue(datetime.date.today())
