# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of stage 5 for material: blocks, extraction, inspections, defects, many items, labels.

MAT-010, MAT-013, MAT-014, MAT-016, MAT-023, MAT-024, MAT-026, MAT-029 to MAT-032,
MAT-038, MAT-039, MAT-042, MAT-043, PRD-020, PRD-032, NFA-041, and the tables of UIX-015.
"""

from __future__ import annotations

import datetime
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from rentalars.availability.engine import AvailabilityEngine
from rentalars.core.jobs import run_waiting_jobs, start_job
from rentalars.core.models import AuditLogEntry, BackgroundJob, JobStatus, TablePreference
from rentalars.core.tables import csv_text
from rentalars.masterdata.models import (
    CategoryField,
    FieldType,
    StorageLocation,
    location_paths,
    remember_location_paths,
)
from rentalars.material import services
from rentalars.material.inspections import OVERDUE, SOON, InspectionPlan, add_months
from rentalars.material.labels import code128_modules, render_labels_pdf
from rentalars.material.models import (
    ConnectionType,
    InspectionType,
    ItemStatus,
    MaterialItem,
)
from rentalars.material.tables import ITEM_TABLE
from rentalars.notifications.models import Kind, Notification, StockNotice
from rentalars.packing.models import Extraction
from rentalars.packing.services import extract, extraction_choices
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    category,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
)


def png_file(name: str = "foto.png") -> SimpleUploadedFile:
    """A tiny real PNG image."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (238, 89, 31)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class BlockTests(RentalarsTestCase):
    """MAT-024: a blocked item is missing from the free stock for its period only."""

    def test_a_block_reduces_the_free_stock_in_its_period(self) -> None:
        product = make_stock("K-005", 3)
        item = MaterialItem.objects.for_product(product.pk).first()
        services.add_block(item, at(10, 8), at(15, 18), "beim Hersteller")
        engine = AvailabilityEngine()
        during = engine.availability([product.pk], at(11), at(12))[product.pk]
        after = AvailabilityEngine().availability([product.pk], at(16), at(17))[product.pk]
        self.assertEqual((during.free, after.free), (2, 3))
        blocked = [demand for demand in during.occupiers if demand.via == "blocked"]
        self.assertEqual(blocked[0].project_name, "beim Hersteller")

    def test_a_block_of_a_defective_item_takes_nothing_twice(self) -> None:
        product = make_stock("K-005", 3)
        item = MaterialItem.objects.for_product(product.pk).first()
        services.set_status(item, ItemStatus.DEFECTIVE, reason="Stecker")
        services.add_block(item, at(10), at(15), "Reparatur")
        self.assertEqual(AvailabilityEngine().availability([product.pk], at(11), at(12))[product.pk].free, 2)

    def test_end_before_start_and_missing_reason_are_refused(self) -> None:
        item = make_items(make_model("Kabel", make_product("K-005")))[0]
        with self.assertRaises(ValidationError):
            services.add_block(item, at(12), at(10), "falsch herum")
        with self.assertRaises(ValidationError):
            services.add_block(item, at(10), at(12), "  ")

    def test_a_project_short_because_of_a_block(self) -> None:
        product = make_stock("K-005", 2)
        item = MaterialItem.objects.for_product(product.pk).first()
        services.add_block(item, at(9), at(14), "Reparatur")
        line = add_line(make_project(), product, 2).line
        self.assertEqual(AvailabilityEngine().line_availability(line).shortage_total, 1)


class ExtractionTests(RentalarsTestCase):
    """MAT-042: a loose item taken out for a project is free for others meanwhile."""

    def setUp(self) -> None:
        super().setUp()
        self.case_product = make_product("S-600", "Funkcase")
        self.case = make_items(make_model("Case", self.case_product), 1)[0]
        self.receiver = make_stock("T-050", 1, "Funkempfänger")
        self.loose = MaterialItem.objects.for_product(self.receiver.pk).first()
        services.install_item(self.loose, self.case, connection_type=ConnectionType.LOOSE)
        self.project = make_project("Mit Case")
        add_line(self.project, self.case_product, 1)

    def free_receivers(self) -> int:
        return AvailabilityEngine().availability([self.receiver.pk], at(10, 12), at(11))[self.receiver.pk].free

    def test_the_container_takes_its_content_until_it_is_taken_out(self) -> None:
        self.assertEqual(self.free_receivers(), 0)
        self.assertEqual(extraction_choices(self.loose, ALL_RIGHTS, None), [self.project])
        extract(self.project, self.loose)
        self.assertEqual(self.free_receivers(), 1)
        self.assertEqual(extraction_choices(self.loose, ALL_RIGHTS, None), [])
        history = AuditLogEntry.for_object(self.project, include_children=False)
        self.assertTrue(history.filter(event="project.content_extracted").exists())

    def test_only_loose_contents_and_only_projects_with_the_container(self) -> None:
        with self.assertRaises(ValidationError):
            extract(make_project("Ohne Case"), self.loose)
        extract(self.project, self.loose)
        with self.assertRaises(ValidationError):
            extract(self.project, self.loose)
        fixed = make_items(make_model("Blende", make_product("S-601")))[0]
        services.install_item(fixed, self.case, connection_type=ConnectionType.FIXED)
        with self.assertRaises(ValidationError):
            extract(self.project, fixed)
        self.assertEqual(Extraction.objects.count(), 1)


class InspectionTests(RentalarsTestCase):
    """MAT-030 to MAT-032: due dates follow from type, interval and the last result."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        self.item = make_items(self.model)[0]
        self.electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        self.electric.categories.add(category("L"))

    def dues(self) -> list:
        return InspectionPlan().dues_for([self.item])[self.item.pk]

    def test_never_inspected_is_overdue(self) -> None:
        (due,) = self.dues()
        self.assertEqual((due.state, due.never_inspected), (OVERDUE, True))

    def test_passed_is_due_after_the_interval(self) -> None:
        services.record_inspection(
            self.item, self.electric, date=datetime.date(2026, 3, 20), inspector="E. Fachkraft", result="passed"
        )
        (due,) = self.dues()
        self.assertEqual((due.due_date, due.state), (datetime.date(2027, 3, 20), SOON))

    def test_failed_is_due_at_once_and_sets_defective(self) -> None:
        services.record_inspection(
            self.item, self.electric, date=datetime.date(2027, 2, 20), inspector="E. Fachkraft", result="failed"
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ItemStatus.DEFECTIVE)
        self.assertIn("nicht bestanden", self.item.status_reason)
        (due,) = self.dues()
        self.assertEqual((due.state, due.last_passed), (OVERDUE, False))

    def test_wrong_input_is_refused(self) -> None:
        other = InspectionType.objects.create(name="Rigging", interval_months=6)
        cases = [
            {"inspection_type": other, "date": datetime.date(2027, 2, 1), "inspector": "X", "result": "passed"},
            {"inspection_type": self.electric, "date": datetime.date(2027, 5, 1), "inspector": "X", "result": "passed"},
            {"inspection_type": self.electric, "date": datetime.date(2027, 2, 1), "inspector": "", "result": "passed"},
            {"inspection_type": self.electric, "date": datetime.date(2027, 2, 1), "inspector": "X", "result": "maybe"},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValidationError):
                services.record_inspection(self.item, case.pop("inspection_type"), **case)

    def test_a_model_rule_and_the_overview(self) -> None:
        cable_model = make_model("Kabel", make_product("K-005"))
        cable = make_items(cable_model)[0]
        visual = InspectionType.objects.create(name="Sichtprüfung", interval_months=3)
        visual.material_models.add(cable_model)
        services.record_inspection(cable, visual, date=datetime.date(2027, 2, 15), inspector="Luka", result="passed")
        rows = InspectionPlan().due_items(within_days=30)
        self.assertEqual(
            [(item.pk, due.inspection_type.name) for item, due in rows], [(self.item.pk, "Elektrische Prüfung")]
        )
        rows = InspectionPlan().due_items(within_days=120)
        self.assertEqual(len(rows), 2)
        self.assertEqual(InspectionPlan().overdue_ids([self.item.pk, cable.pk]), {self.item.pk})

    def test_the_packlist_rule_is_the_rule_of_the_item_page(self) -> None:
        """``overdue_ids`` (packlists, on plain values) agrees with ``dues_for`` in every case."""
        items = make_items(self.model, 5)
        cases = [
            (items[0], []),
            (items[1], [(datetime.date(2027, 1, 10), "passed")]),
            (items[2], [(datetime.date(2025, 6, 1), "passed")]),
            (items[3], [(datetime.date(2027, 1, 10), "passed"), (datetime.date(2027, 2, 1), "failed")]),
            (items[4], [(datetime.date(2027, 1, 10), "failed"), (datetime.date(2027, 2, 1), "passed")]),
        ]
        for item, inspections in cases:
            for date, result in inspections:
                services.record_inspection(item, self.electric, date=date, inspector="E. Fachkraft", result=result)
        plan = InspectionPlan()
        by_page = {
            item_id
            for item_id, dues in plan.dues_for(MaterialItem.objects.filter(pk__in=[i.pk for i in items])).items()
            if any(due.state == OVERDUE for due in dues)
        }
        self.assertEqual(plan.overdue_ids([item.pk for item in items]), by_page)
        self.assertEqual(by_page, {items[0].pk, items[2].pk, items[3].pk})

    def test_months_are_added_like_a_calendar(self) -> None:
        self.assertEqual(add_months(datetime.date(2027, 1, 31), 1), datetime.date(2027, 2, 28))
        self.assertEqual(add_months(datetime.date(2027, 11, 15), 3), datetime.date(2028, 2, 15))


class DefectTests(RentalarsTestCase):
    """MAT-023: a defect report with photo sets the status and tells the warehouse."""

    def test_report_with_photo(self) -> None:
        warehouse = make_user("luka", roles=("Lager",))
        item = make_items(make_model("Kabel", make_product("K-005")))[0]
        report = services.report_defect(item, "Stecker lose", photo=png_file(), context="Rücknahme 2027-0001")
        item.refresh_from_db()
        self.assertEqual((item.status, item.status_reason), (ItemStatus.DEFECTIVE, "Stecker lose"))
        self.assertTrue(report.photo.name.endswith(".jpg"))  # Made anew (NFA-084)
        self.assertTrue(Notification.objects.filter(user=warehouse, kind=Kind.DEFECT).exists())
        services.report_defect(item, "Mantel eingerissen")
        self.assertEqual(item.defect_reports.count(), 2)

    def test_no_description_and_no_image_are_refused(self) -> None:
        item = make_items(make_model("Kabel", make_product("K-005")))[0]
        with self.assertRaises(ValidationError):
            services.report_defect(item, " ")
        with self.assertRaises(ValidationError):
            services.report_defect(item, "kaputt", photo=SimpleUploadedFile("x.png", b"<html>", "image/png"))


class ManyItemsTests(RentalarsTestCase):
    """MAT-029: all or nothing; hints for installed items and other main categories (MAT-038, PRD-032)."""

    def test_change_status_and_location(self) -> None:
        items = make_items(make_model("Kabel", make_product("K-005")), 3)
        hall = StorageLocation.objects.create(name="Halle 2")
        services.bulk_update(items, status=ItemStatus.BLOCKED, reason="Inventur", storage_location=hall)
        self.assertEqual(
            set(MaterialItem.objects.values_list("status", "status_reason", "storage_location_id")),
            {("blocked", "Inventur", hall.pk)},
        )

    def test_one_broken_rule_changes_nothing(self) -> None:
        first, second = make_items(make_model("Kabel", make_product("K-005")), 2)
        services.set_status(first, ItemStatus.DEFECTIVE, reason="Stecker")
        with self.assertRaises(ValidationError) as caught:
            services.bulk_update([first, second], status=ItemStatus.AVAILABLE)
        self.assertIn(first.display_id, str(caught.exception))
        second.refresh_from_db()
        self.assertEqual(second.status, ItemStatus.AVAILABLE)

    def test_hints(self) -> None:
        case = make_items(make_model("Case", make_product("S-600")))[0]
        cable = make_items(make_model("Kabel", make_product("K-005")))[0]
        services.install_item(cable, case, connection_type=ConnectionType.LOOSE)
        light = make_product("L-001", "Scheinwerfer")
        hints = services.bulk_update([cable], storage_location=StorageLocation.objects.create(name="A"), product=light)
        self.assertEqual(len(hints), 2)
        self.assertIn("Hauptkategorie", hints[0])


class TakeOutTests(RentalarsTestCase):
    """MAT-043, MAT-039: in one step, noted for both items; MAT-038: the location follows the case."""

    def test_take_out_and_put_back(self) -> None:
        hall = StorageLocation.objects.create(name="Halle 1")
        case = make_items(make_model("Case", make_product("S-600")), storage_location=hall)[0]
        cable = make_items(make_model("Kabel", make_product("K-005")))[0]
        services.install_item(cable, case, connection_type=ConnectionType.LOOSE)
        self.assertEqual(MaterialItem.objects.get(pk=cable.pk).effective_storage_location, hall)
        services.take_out(cable)
        self.assertIsNone(cable.installed_in_id)
        self.assertEqual(cable.taken_out_of, case)
        services.put_back(cable)
        cable.refresh_from_db()
        self.assertEqual((cable.installed_in_id, cable.taken_out_of_id), (case.pk, None))
        events = set(AuditLogEntry.objects.exclude(event="").values_list("event", flat=True))
        self.assertTrue({"item.taken_out", "item.put_back", "item.content_added", "item.content_removed"} <= events)
        with self.assertRaises(ValidationError):
            services.put_back(cable)

    def test_fixed_items_are_not_taken_out_by_a_tap(self) -> None:
        rack = make_items(make_model("Rack", make_product("S-500")))[0]
        panel = make_items(make_model("Blende", make_product("S-501")))[0]
        services.install_item(panel, rack, connection_type=ConnectionType.FIXED)
        with self.assertRaises(ValidationError):
            services.take_out(panel)


class FieldTests(RentalarsTestCase):
    """MAT-010, MAT-013, MAT-014, MAT-016."""

    def test_further_fields_and_own_values(self) -> None:
        cables = category("K")
        length = cables.primary_field  # "Länge" in m comes with the installation
        plug = CategoryField.objects.create(
            category=cables, label="Stecker", field_type=FieldType.CHOICE, choices=["XLR", "Speakon"], position=9
        )
        model = make_model("Kabel", make_product("K-005"))
        model.set_field_value(length, "5")
        model.set_field_value(plug, "XLR")
        with self.assertRaises(ValidationError):
            model.set_field_value(plug, "Klinke")
        model.save()
        item = make_items(model)[0]
        item.set_field_override(length, "4,5")
        item.save()
        rows = {field.label: (value, own) for field, value, own in item.field_rows()}
        self.assertEqual(rows, {"Länge": ("4,5 m", True), "Stecker": ("XLR", False)})
        self.assertEqual(item.category_specific_display, "4,5 m")

    def test_weight_volume_and_suggested_supplier(self) -> None:
        from rentalars.masterdata.models import Supplier

        model = make_model("Case", make_product("S-600"))
        model.weight_kg, model.length_cm, model.width_cm, model.height_cm = (
            Decimal("12.5"),
            Decimal("60"),
            Decimal("40"),
            Decimal("35"),
        )
        self.assertEqual((model.volume_litres, model.dimensions_display), (Decimal("84.0"), "60 × 40 × 35 cm"))
        self.assertEqual(services.suggested_purchase_fields(model), {})
        dealer = Supplier.objects.create(name="Thomann")
        make_items(model, supplier=dealer, supplier_article_number="123")
        self.assertEqual(
            services.suggested_purchase_fields(model), {"supplier": dealer.pk, "supplier_article_number": "123"}
        )


class LowStockTests(RentalarsTestCase):
    """PRD-020: below the minimum the warehouse is told – once, until the stock recovers."""

    def test_reported_once(self) -> None:
        warehouse = make_user("luka", roles=("Lager",))
        # PRD-047: a sale product has its sale price only – no price besides it.
        tape = make_product("V-001", "Gaffa", kind="sale", price=None, sale_price=Decimal("8.50"))
        model = make_model("Gaffa schwarz", tape, bulk=True)
        row = make_items(model, quantity=4)[0]
        tape.minimum_stock = 10
        tape.save()
        self.assertEqual(services.check_low_stock(), 1)
        self.assertEqual(services.check_low_stock(), 0)
        self.assertEqual(Notification.objects.filter(user=warehouse, kind=Kind.LOW_STOCK).count(), 1)
        row.quantity = 20
        row.save()
        self.assertEqual(services.check_low_stock(), 0)
        self.assertFalse(StockNotice.objects.exists())


class LabelTests(RentalarsTestCase):
    """MAT-026: Code 128 as hand scanners read it, and the PDF."""

    def test_code_128(self) -> None:
        # Reference patterns, checked against an independent implementation.
        self.assertEqual(code128_modules("0042"), "110100111001101100110010110111000111101001001100011101011")
        self.assertEqual(
            code128_modules("10000"),
            "1101001110011001000100110110011001011110111010011101100100001011001100011101011",
        )

    def test_pdf_with_qr_codes_and_barcodes(self) -> None:
        items = make_items(make_model("Kabel", make_product("K-005")), 3)
        for code in ("qr", "barcode"):
            for sheet in ("a4-24", "a4-65", "roll-62x29"):
                with self.subTest(code=code, sheet=sheet):
                    self.assertTrue(render_labels_pdf(items, label_format=sheet, code=code, skip=2).startswith(b"%PDF"))


class JobTests(RentalarsTestCase):
    """NFA-041: tasks in the background, here run at once."""

    def test_labels_in_the_background(self) -> None:
        user = make_user("luka")
        items = make_items(make_model("Kabel", make_product("K-005")), 2)
        job = start_job("labels", {"numbers": [item.inventory_number for item in items]}, user=user, title="Etiketten")
        self.assertEqual(job.status, JobStatus.DONE)
        self.assertTrue(job.result_file.read().startswith(b"%PDF"))
        self.assertTrue(Notification.objects.filter(user=user, kind=Kind.JOB_FINISHED).exists())

    def test_lost_and_waiting_tasks(self) -> None:
        from django.utils import timezone

        stale = BackgroundJob.objects.create(
            kind="labels",
            title="alt",
            status=JobStatus.RUNNING,
            started_at=timezone.now() - datetime.timedelta(hours=3),
            params={"numbers": []},
        )
        given_up = BackgroundJob.objects.create(
            kind="labels",
            title="zweimal",
            status=JobStatus.RUNNING,
            started_at=timezone.now() - datetime.timedelta(hours=3),
            params={"numbers": [], "attempts": 1},
        )
        waiting = BackgroundJob.objects.create(kind="labels", title="neu", params={"numbers": []})
        # The lost task is started once more; the one lost a second time fails.
        self.assertEqual(run_waiting_jobs(), 2)
        for job in (stale, given_up, waiting):
            job.refresh_from_db()
        self.assertEqual(
            (stale.status, given_up.status, waiting.status), (JobStatus.DONE, JobStatus.FAILED, JobStatus.DONE)
        )


class TableTests(RentalarsTestCase):
    """UIX-015, IMP-005: columns from the address, from the saved choice, or the default."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_user("anna", superuser=True)

    def request(self, query: str = "", user: object = None) -> object:
        request = RequestFactory().get(f"/material/{query}")
        request.user = user or self.anna
        return request

    def test_columns_and_sort(self) -> None:
        state = ITEM_TABLE.state(self.request())
        # V1: the purchase and supplier columns are off until switched on (8 of 14 are shown).
        self.assertEqual(len(state.columns), 8)
        self.assertTrue(state.is_default)
        state = ITEM_TABLE.state(self.request("?cols=status,serial&sort=-serial"))
        self.assertEqual([column.key for column in state.columns], ["id", "status", "serial"])
        self.assertEqual((state.sort_key, state.descending), ("serial", True))
        # UIX-015: the category-specific value sorts too (in Python); an unknown column falls back.
        state = ITEM_TABLE.state(self.request("?sort=category_specific"))
        self.assertEqual(state.sort, "category_specific")
        state = ITEM_TABLE.state(self.request("?sort=no_such_column"))
        self.assertEqual(state.sort, "id")

    def test_saved_choice_and_rights(self) -> None:
        user = make_user("tom", roles=("Crew",))
        TablePreference.save_columns(user, "material_items", ["status", "purchase_price", "location"])
        state = ITEM_TABLE.state(self.request(user=user))
        # The crew may not see purchase prices (AUT-019): the column is left out.
        self.assertEqual([column.key for column in state.columns], ["id", "status", "location"])

    def test_csv_values(self) -> None:
        self.assertEqual(csv_text("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(csv_text("-12,50"), "-12,50")
        self.assertEqual(csv_text(Decimal("1234.50")), "1234,5")
        self.assertEqual(csv_text(datetime.date(2027, 3, 1)), "01.03.2027")
        self.assertEqual(csv_text(None), "")


class LocationPathTests(RentalarsTestCase):
    """MAT-018, NFA-012: a list shows the full place of every item without asking per row and level."""

    def setUp(self) -> None:
        super().setUp()
        hall = StorageLocation.objects.create(name="Halle 1")
        shelf = StorageLocation.objects.create(name="Regal A", parent=hall)
        self.places = [StorageLocation.objects.create(name=f"Fach {number}", parent=shelf) for number in range(1, 6)]
        self.items = make_items(make_model("Scheinwerfer", make_product("L-010")), 5)
        for item, place in zip(self.items, self.places, strict=True):
            item.storage_location = place
            item.save()

    def test_paths_from_one_query(self) -> None:
        with self.assertNumQueries(1):
            paths = location_paths()
        self.assertEqual(paths[self.places[0].pk], "Halle 1 > Regal A > Fach 1")
        locations = [StorageLocation.objects.get(pk=place.pk) for place in reversed(self.places)]
        with self.assertNumQueries(1):
            ordered = remember_location_paths([None, *locations])
            self.assertEqual(
                [location.path for location in ordered][:2],
                ["Halle 1 > Regal A > Fach 1", "Halle 1 > Regal A > Fach 2"],
            )

    def test_the_item_list_asks_once_for_all_places(self) -> None:
        request = RequestFactory().get("/material/?cols=id,location")
        request.user = make_user("anna", superuser=True)
        state = ITEM_TABLE.state(request)
        items = list(MaterialItem.objects.select_related("storage_location", "installed_in__storage_location"))
        with self.assertNumQueries(1):
            rows = state.rows(items)
        with self.assertNumQueries(1):
            csv = state.csv_text(items)
        self.assertIn("Halle 1 &gt; Regal A &gt; Fach 5", str(rows[4].cells[1].html))
        self.assertIn("Halle 1 > Regal A > Fach 5", csv)
