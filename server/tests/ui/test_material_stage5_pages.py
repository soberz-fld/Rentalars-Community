# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of stage 5 for material: columns, many items, labels, the tabs of an item (MAT, UIX-015)."""

from __future__ import annotations

import datetime
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.core.models import TablePreference
from rentalars.masterdata.models import StorageLocation
from rentalars.material import services
from rentalars.material.models import (
    ConnectionType,
    DefectReport,
    Inspection,
    InspectionType,
    ItemBlock,
    ItemStatus,
    MaterialFile,
    MaterialItem,
)
from rentalars.notifications.models import Kind, Notification
from rentalars.packing.models import Extraction
from tests.helpers import add_line, category, make_items, make_model, make_product, make_project
from tests.ui.base import UiTestCase, form_data


def png_file(name: str = "foto.png") -> SimpleUploadedFile:
    """A tiny real PNG image."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (238, 89, 31)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def pdf_file(name: str = "protokoll.pdf") -> SimpleUploadedFile:
    """A small file that passes as PDF."""
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class ItemListColumnTests(UiTestCase):
    """UIX-015: show more columns, hide some, sort by a click on the heading; IMP-005: CSV."""

    def setUp(self) -> None:
        super().setUp()
        self.cables = make_items(make_model("Cordial CPM 5 FM", make_product("K-005", "XLR-Kabel 5 m")), 3)
        services.set_status(self.cables[1], ItemStatus.BLOCKED, reason="=Inventur")

    def test_default_columns_and_the_chooser(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:item_list")))
        self.assertIn('aria-sort="ascending"', page)
        self.assertIn(reverse("core:table_columns", args=["material_items"]), page)
        self.assertIn("Seriennummer", page)
        self.assertNotIn('<th scope="col" class=""><a href="?sort=created', page)

    def test_save_a_choice_and_go_back_to_the_default(self) -> None:
        url = reverse("core:table_columns", args=["material_items"])
        response = self.client.post(
            url, {"columns": ["status", "location", "nonsense"], "next": "/material/?category=1&page=2&cols=status"}
        )
        self.assertRedirects(response, "/material/?category=1", fetch_redirect_response=False)
        self.assertEqual(TablePreference.columns_of(self.admin_user, "material_items"), ["status", "location"])
        page = self.assert_ok(self.client.get(reverse("material:item_list")))
        self.assertIn("Lagerort", page)
        self.assertNotIn("Seriennummer</a>", page)
        self.client.post(url, {"reset": "1", "next": "/material/"})
        self.assertIsNone(TablePreference.columns_of(self.admin_user, "material_items"))

    def test_foreign_next_address_is_not_followed(self) -> None:
        url = reverse("core:table_columns", args=["material_items"])
        response = self.client.post(url, {"columns": ["status"], "next": "https://example.com/x"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.post("/tables/unknown/columns/", {}).status_code, 404)

    def test_sort_by_a_column(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:item_list"), {"sort": "-id"}))
        self.assertLess(page.index(self.cables[2].display_id), page.index(self.cables[0].display_id))
        self.assertIn('aria-sort="descending"', page)

    def test_csv_of_the_view_and_of_all_columns(self) -> None:
        response = self.client.get(reverse("material:item_list"), {"format": "csv", "cols": "status,status_reason"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        text = response.content.decode("utf-8-sig")
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "ID;Status;Grund für den Status")
        self.assertEqual(len(lines), 4)
        self.assertIn("'=Inventur", text)
        everything = self.client.get(reverse("material:item_list"), {"format": "csv", "cols": "all"})
        self.assertIn("Einkaufspreis", everything.content.decode("utf-8-sig").splitlines()[0])


class ManyItemsPageTests(UiTestCase):
    """MAT-029: tick items, then change them together or print their labels."""

    def setUp(self) -> None:
        super().setUp()
        self.items = make_items(make_model("Cordial CPM 5 FM", make_product("K-005", "XLR-Kabel 5 m")), 3)
        self.hall = StorageLocation.objects.create(name="Halle 2")

    def test_change_location_and_status(self) -> None:
        """MAT-018, MAT-029: the storage location from the tree, for many items at once."""
        page = self.client.get(reverse("material:item_list"))
        data = form_data(
            page, containing="storage_location", status="blocked", reason="Inventur", storage_location=self.hall.pk
        )
        data["items"] = [str(item.pk) for item in self.items[:2]]
        data["action"] = "change"
        response = self.client.post(reverse("material:item_bulk_update"), data, follow=True)
        self.assertIn("2 Exemplare geändert.", self.messages_of(response)[-1])
        changed = MaterialItem.objects.filter(status=ItemStatus.BLOCKED, storage_location=self.hall)
        self.assertEqual(changed.count(), 2)

    def test_defective_without_reason_changes_nothing(self) -> None:
        response = self.client.post(
            reverse("material:item_bulk_update"),
            {"items": [str(self.items[0].pk)], "action": "change", "status": "defective", "next": "/material/"},
            follow=True,
        )
        self.assertTrue(self.messages_of(response))
        self.assertFalse(MaterialItem.objects.filter(status=ItemStatus.DEFECTIVE).exists())

    def test_labels_of_the_chosen_items(self) -> None:
        response = self.client.post(
            reverse("material:item_bulk_update"),
            {"items": [str(item.pk) for item in self.items], "action": "labels"},
        )
        self.assertRedirects(response, "/material/labels/?items=0001,0002,0003", fetch_redirect_response=False)


class LabelPageTests(UiTestCase):
    """MAT-026: choose IDs and sheet, get a PDF."""

    def setUp(self) -> None:
        super().setUp()
        make_items(make_model("Cordial CPM 5 FM", make_product("K-005", "XLR-Kabel 5 m")), 5)

    def test_page_and_pdf(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:labels"), {"items": "0001-0003, 0005"}))
        self.assertIn("4", page)
        response = self.client.get(
            reverse("material:labels"),
            {"items": "0001-0003", "label_format": "a4-65", "code": "barcode", "skip": "2", "pdf": "1"},
        )
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_unknown_ids_are_named(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:labels"), {"items": "0001, 0099", "pdf": "1"}))
        self.assertIn("0099", page)

    def test_the_short_address_of_the_qr_code(self) -> None:
        item = MaterialItem.objects.get(inventory_number=2)
        self.assertRedirects(self.client.get("/m/0002"), reverse("material:item_detail", args=[item.pk]))
        self.assertEqual(self.client.get("/m/9999").status_code, 404)


class ItemTabTests(UiTestCase):
    """The tabs of an item: timeline, inspections, files and defects, history."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Scheinwerfer", make_product("L-010", "PAR 64"), category_code="L")
        self.item = make_items(self.model)[0]

    def test_every_tab_opens(self) -> None:
        for name in ("item_detail", "item_timeline", "item_inspections", "item_files", "item_history"):
            with self.subTest(tab=name):
                self.assert_ok(self.client.get(reverse(f"material:{name}", args=[self.item.pk])))

    def test_timeline_shows_a_project_and_a_block(self) -> None:
        project = make_project("Stadtfest")
        add_line(project, self.item.product, 1)
        services.add_block(
            self.item,
            datetime.datetime(2027, 3, 20, tzinfo=datetime.UTC),
            datetime.datetime(2027, 3, 22, tzinfo=datetime.UTC),
            "Werkstatt",
        )
        page = self.assert_ok(self.client.get(reverse("material:item_timeline", args=[self.item.pk]), {"weeks": "6"}))
        self.assertIn("Stadtfest", page)
        self.assertIn('<option value="6" selected>', page)
        self.assertIn('href="?weeks=6&amp;from=2027-04-12"', page)
        self.assertIn("Werkstatt", page)

    def test_report_a_defect_with_photo(self) -> None:
        url = reverse("material:item_defect", args=[self.item.pk])
        self.assert_ok(self.client.get(url))
        response = self.client.post(url, {"description": "Lampe flackert", "photo": png_file()}, follow=True)
        report = DefectReport.objects.get()
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ItemStatus.DEFECTIVE)
        self.assertIn("Lampe flackert", self.assert_ok(response))
        photo = self.client.get(reverse("material:defect_photo", args=[report.pk]))
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo["Content-Type"], "image/jpeg")  # Made anew

    def test_record_an_inspection_with_protocol(self) -> None:
        """MAT-031: date, inspector, result and protocol; the next due date is calculated."""
        electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        electric.categories.add(category("L"))
        url = reverse("material:item_inspections", args=[self.item.pk])
        page = self.client.get(url)
        self.assertIn("nie geprüft", self.assert_ok(page))
        data = form_data(
            page, containing="inspector", inspection_type=electric.pk, date="2027-02-26", inspector="E. Fachkraft"
        )
        data["protocol"] = pdf_file()
        response = self.client.post(url, data, follow=True)
        self.assertIn("26.02.2028", self.assert_ok(response))
        inspection = Inspection.objects.get()
        protocol = self.client.get(reverse("material:inspection_protocol", args=[inspection.pk]))
        self.assertEqual(protocol.status_code, 200)
        overview = self.assert_ok(self.client.get(reverse("material:inspections"), {"days": "400"}))
        self.assertIn(self.item.display_id, overview)

    def test_files_of_item_and_model(self) -> None:
        url = reverse("material:item_files", args=[self.item.pk])
        self.client.post(url, {"file": pdf_file("anleitung.pdf"), "kind": "manual", "title": "Anleitung"})
        stored = MaterialFile.objects.get()
        self.assertIn("Anleitung", self.assert_ok(self.client.get(url)))
        self.assertEqual(self.client.get(reverse("material:file", args=[stored.pk])).status_code, 200)
        self.client.post(reverse("material:file_delete", args=[stored.pk]), {"next": url})
        self.assertFalse(MaterialFile.objects.exists())
        # MAT-090: a photo is not a file of the tab "Files" but has its own upload on the page of the model.
        model_url = reverse("material:model_files", args=[self.model.pk])
        self.client.post(model_url, {"file": png_file("bild.png"), "kind": "picture"})
        self.assertFalse(MaterialFile.objects.exists())
        self.client.post(reverse("material:model_photos", args=[self.model.pk]), {"photos": png_file("bild.png")})
        self.assertEqual(MaterialFile.objects.get().material_model, self.model)
        self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assert_ok(self.client.get(reverse("material:model_timeline", args=[self.model.pk])))

    def test_block_and_lift_it(self) -> None:
        url = reverse("material:item_block_add", args=[self.item.pk])
        self.client.post(url, {"start": "2027-03-20 08:00", "end": "2027-03-22 18:00", "reason": "Werkstatt"})
        block = ItemBlock.objects.get()
        self.assertIn(
            "Werkstatt", self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.item.pk])))
        )
        self.client.post(reverse("material:item_block_delete", args=[self.item.pk, block.pk]))
        self.assertFalse(ItemBlock.objects.exists())

    def test_warehouse_is_told_of_a_defect(self) -> None:
        warehouse = self.browser_for("luka", "Lager")
        warehouse.post(reverse("material:item_defect", args=[self.item.pk]), {"description": "Kabel ab"})
        self.assertFalse(Notification.objects.filter(user__username="luka", kind=Kind.DEFECT).exists())
        self.assertEqual(DefectReport.objects.get().reported_by.username, "luka")


class TakeOutAndExtractionPageTests(UiTestCase):
    """MAT-043 and MAT-042 from the item's page."""

    def setUp(self) -> None:
        super().setUp()
        self.case_product = make_product("S-600", "Funkcase")
        self.case = make_items(make_model("Case", self.case_product))[0]
        self.receiver = make_items(make_model("Empfänger", make_product("T-050", "Funkempfänger")))[0]
        services.install_item(self.receiver, self.case, connection_type=ConnectionType.LOOSE)

    def test_take_out_and_put_back(self) -> None:
        self.client.post(reverse("material:item_take_out", args=[self.receiver.pk]))
        self.receiver.refresh_from_db()
        self.assertIsNone(self.receiver.installed_in_id)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.receiver.pk])))
        self.assertIn(reverse("material:item_put_back", args=[self.receiver.pk]), page)
        self.client.post(reverse("material:item_put_back", args=[self.receiver.pk]))
        self.receiver.refresh_from_db()
        self.assertEqual(self.receiver.installed_in_id, self.case.pk)

    def test_leave_behind_for_a_project(self) -> None:
        project = make_project("Mit Case")
        add_line(project, self.case_product, 1)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.receiver.pk])))
        self.assertIn(project.number, page)
        self.client.post(reverse("packing:extract", args=[self.receiver.pk]), {"project": project.pk})
        extraction = Extraction.objects.get()
        self.assertIn(
            "Mit Case", self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.receiver.pk])))
        )
        self.client.post(reverse("packing:extraction_cancel", args=[extraction.pk]))
        self.assertFalse(Extraction.objects.exists())
