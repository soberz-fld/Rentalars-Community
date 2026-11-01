# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of stage 5 for material: defects, blocks, inspections, files, many items, labels, timelines, jobs."""

from __future__ import annotations

import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.material import labels, services
from rentalars.material.models import ConnectionType, InspectionType, ItemStatus, MaterialFile, MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, category, make_items, make_model, make_product, make_project


def png_file(name: str = "foto.png") -> SimpleUploadedFile:
    """A tiny real PNG image."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (238, 89, 31)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def pdf_file(name: str = "protokoll.pdf") -> SimpleUploadedFile:
    """A small file that passes as PDF."""
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class DefectAndBlockApiTests(ApiTestCase):
    """MAT-023, MAT-024."""

    def setUp(self) -> None:
        super().setUp()
        self.item = make_items(make_model("Kabel", make_product("K-005")))[0]
        self.url = f"{API}/material-items/{self.item.pk}"

    def test_report_a_defect_with_photo(self) -> None:
        response = self.admin.post(
            f"{self.url}/defects", {"description": "Stecker lose", "photo": png_file()}, format="multipart"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["photo_url"])
        self.assertEqual(MaterialItem.objects.get(pk=self.item.pk).status, ItemStatus.DEFECTIVE)
        listed = self.admin.get(f"{self.url}/defects").json()
        self.assertEqual([report["description"] for report in listed], ["Stecker lose"])
        self.assert_error(
            self.admin.post(f"{self.url}/defects", {"description": ""}), 400, "validation_error", "description"
        )

    def test_block_and_lift(self) -> None:
        response = self.admin.post(
            f"{self.url}/blocks",
            {"start": "2027-03-10T08:00:00+01:00", "end": "2027-03-12T18:00:00+01:00", "reason": "Reparatur"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        block = response.json()["id"]
        self.assertEqual(len(self.admin.get(f"{self.url}/blocks").json()), 1)
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.delete(f"{self.url}/blocks/{block}").status_code, 403)
        self.assertEqual(self.admin.delete(f"{self.url}/blocks/{block}").status_code, 204)
        wrong = self.admin.post(
            f"{self.url}/blocks",
            {"start": "2027-03-12T08:00:00+01:00", "end": "2027-03-10T18:00:00+01:00", "reason": "x"},
            format="json",
        )
        self.assert_error(wrong, 400, "validation_error")


class InspectionApiTests(ApiTestCase):
    """MAT-030 to MAT-032."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        self.item = make_items(self.model)[0]

    def test_types_record_and_due(self) -> None:
        created = self.admin.post(
            f"{API}/inspection-types",
            {"name": "Elektrische Prüfung", "interval_months": 12, "categories": [category("L").pk]},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        type_id = created.json()["id"]
        self.assertEqual(len(self.admin.get(f"{API}/inspection-types").json()["results"]), 1)
        self.assertEqual(self.admin.get(f"{API}/inspection-types/{type_id}").json()["interval_months"], 12)
        self.admin.patch(f"{API}/inspection-types/{type_id}", {"interval_months": 24}, format="json")
        full = self.admin.put(
            f"{API}/inspection-types/{type_id}",
            {
                "name": "Elektrische Prüfung",
                "interval_months": 12,
                "categories": [category("L").pk],
                "material_models": [],
            },
            format="json",
        )
        self.assertEqual(full.status_code, 200, full.content)

        due = self.admin.get(f"{API}/inspections/due").json()
        self.assertEqual([(row["display_id"], row["state"]) for row in due], [("0001", "overdue")])

        recorded = self.admin.post(
            f"{API}/material-items/{self.item.pk}/inspections",
            {
                "inspection_type": type_id,
                "date": "2027-02-26",
                "inspector": "E. Fachkraft",
                "result": "passed",
                "protocol": pdf_file(),
            },
            format="multipart",
        )
        self.assertEqual(recorded.status_code, 201, recorded.content)
        self.assertTrue(recorded.json()["protocol_url"])
        state = self.admin.get(f"{API}/material-items/{self.item.pk}/inspections").json()
        self.assertEqual(state["due"][0]["due_date"], "2028-02-26")
        self.assertEqual(len(state["done"]), 1)
        self.assertEqual(self.admin.get(f"{API}/inspections/due").json(), [])

        refused = self.admin.delete(f"{API}/inspection-types/{type_id}")
        self.assert_error(refused, 400, "validation_error")
        spare = InspectionType.objects.create(name="Sichtprüfung", interval_months=3)
        self.assertEqual(self.admin.delete(f"{API}/inspection-types/{spare.pk}").status_code, 204)

    def test_future_date_is_refused(self) -> None:
        electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        electric.categories.add(category("L"))
        response = self.admin.post(
            f"{API}/material-items/{self.item.pk}/inspections",
            {"inspection_type": electric.pk, "date": "2027-04-01", "inspector": "X", "result": "passed"},
            format="json",
        )
        self.assert_error(response, 400, "validation_error", "date")


class FileApiTests(ApiTestCase):
    """MAT-017: pictures and documents of models and items."""

    def test_files_of_model_and_item(self) -> None:
        model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        item = make_items(model)[0]
        for owner in (f"material-models/{model.pk}", f"material-items/{item.pk}"):
            response = self.admin.post(
                f"{API}/{owner}/files", {"file": pdf_file("anleitung.pdf"), "kind": "manual"}, format="multipart"
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(len(self.admin.get(f"{API}/{owner}/files").json()), 1)
        stored = MaterialFile.objects.get(item=item)
        self.assertEqual(self.admin.get(f"{API}/material-files/{stored.pk}").json()["kind"], "manual")
        content = self.admin.get(f"{API}/material-files/{stored.pk}/content")
        self.assertEqual(content.status_code, 200)
        self.assertTrue(b"".join(content.streaming_content).startswith(b"%PDF"))
        self.assertEqual(self.admin.delete(f"{API}/material-files/{stored.pk}").status_code, 204)
        bad = self.admin.post(
            f"{API}/material-items/{item.pk}/files",
            {"file": SimpleUploadedFile("x.exe", b"MZ", "application/octet-stream"), "kind": "other"},
            format="multipart",
        )
        self.assert_error(bad, 400, "validation_error")


class ManyItemsApiTests(ApiTestCase):
    """MAT-029, MAT-043, MAT-010, MAT-013."""

    def test_bulk_update(self) -> None:
        items = make_items(make_model("Kabel", make_product("K-005")), 3)
        response = self.admin.post(
            f"{API}/material-items/bulk-update",
            {"items": [item.pk for item in items], "status": "blocked", "status_reason": "Inventur"},
            format="json",
        )
        self.assertEqual(response.json(), {"changed": 3, "warnings": []})
        self.assertEqual(MaterialItem.objects.filter(status="blocked").count(), 3)
        missing = self.admin.post(
            f"{API}/material-items/bulk-update", {"items": [999], "status": "blocked"}, format="json"
        )
        self.assert_error(missing, 400, "validation_error", "items")

    def test_take_out_and_put_back(self) -> None:
        case = make_items(make_model("Case", make_product("S-600")))[0]
        receiver = make_items(make_model("Empfänger", make_product("T-050")))[0]
        services.install_item(receiver, case, connection_type=ConnectionType.LOOSE)
        out = self.admin.post(f"{API}/material-items/{receiver.pk}/take-out")
        self.assertEqual(out.status_code, 200, out.content)
        self.assertEqual((out.json()["installed_in"], out.json()["taken_out_of"]), (None, case.pk))
        back = self.admin.post(f"{API}/material-items/{receiver.pk}/put-back")
        self.assertEqual(back.json()["installed_in"], case.pk)
        self.assert_error(self.admin.post(f"{API}/material-items/{receiver.pk}/put-back"), 400, "validation_error")

    def test_further_fields(self) -> None:
        cables = category("K")
        length = cables.primary_field
        model = make_model("Kabel", make_product("K-005"))
        response = self.admin.patch(
            f"{API}/material-models/{model.pk}",
            {"field_values": {str(length.pk): "5"}, "weight_kg": "0.4"},
            format="json",
        )
        self.assertEqual(response.json()["category_specific_display"], "5 m")
        item = make_items(model)[0]
        response = self.admin.patch(
            f"{API}/material-items/{item.pk}", {"field_value_overrides": {str(length.pk): "4,5"}}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["field_value_overrides"], {str(length.pk): "4.5"})
        wrong = self.admin.patch(
            f"{API}/material-items/{item.pk}", {"field_value_overrides": {str(length.pk): "lang"}}, format="json"
        )
        self.assert_error(wrong, 400, "validation_error")


class LabelAndJobApiTests(ApiTestCase):
    """MAT-026, NFA-041."""

    def setUp(self) -> None:
        super().setUp()
        self.items = make_items(make_model("Kabel", make_product("K-005")), 3)

    def test_pdf_at_once(self) -> None:
        response = self.admin.post(
            f"{API}/labels", {"items": [item.pk for item in self.items], "code": "barcode"}, format="json"
        )
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_without_a_format_the_sheet_of_0_8_4(self) -> None:
        """Review, finding 2: the new labels of the settings only when named – programs keep their sheet."""
        with mock.patch.object(labels, "render_labels_pdf", return_value=b"%PDF-") as render:
            self.admin.post(f"{API}/labels", {"items": [self.items[0].pk]}, format="json")
            self.assertEqual(render.call_args.kwargs["label_format"], "a4-24")
            self.admin.post(f"{API}/labels", {"items": [self.items[0].pk], "format": "small"}, format="json")
            self.assertEqual(render.call_args.kwargs["label_format"], "small")

    def test_many_labels_in_the_background(self) -> None:
        with mock.patch.object(labels, "MAX_LABELS_DIRECT", 2):
            response = self.admin.post(f"{API}/labels", {"items": [item.pk for item in self.items]}, format="json")
        self.assertEqual(response.status_code, 202)
        job = response.json()["job"]
        state = self.admin.get(f"{API}/jobs/{job}").json()
        self.assertEqual((state["status"], state["result_url"]), ("done", f"/api/v1/jobs/{job}/result"))
        result = self.admin.get(f"{API}/jobs/{job}/result")
        self.assertTrue(b"".join(result.streaming_content).startswith(b"%PDF"))
        other = self.client_for("luka", "Lager")
        self.assertEqual(other.get(f"{API}/jobs/{job}").status_code, 404)


class TimelineApiTests(ApiTestCase):
    """VFG-019."""

    def test_item_and_model_timeline(self) -> None:
        product = make_product("L-010", "PAR 64")
        model = make_model("Scheinwerfer", product)
        item = make_items(model, 2)[0]
        add_line(make_project("Stadtfest"), product, 1)
        services.add_block(item, "2027-03-15T08:00:00+01:00", "2027-03-16T18:00:00+01:00", "Werkstatt")
        timeline = self.admin.get(f"{API}/material-items/{item.pk}/timeline", {"from": "2027-03-08", "weeks": 2}).json()
        self.assertEqual(len(timeline["days"]), 14)
        kinds = {row["kind"] for row in timeline["rows"]}
        self.assertTrue({"blocked", "free"} <= kinds)
        free = next(row for row in timeline["rows"] if row["kind"] == "free")["free"]
        self.assertEqual([day["free"] for day in free[:5]], [2, 2, 1, 1, 2])
        projects = [row for row in timeline["rows"] if "Stadtfest" in row["label"]]
        self.assertEqual(projects[0]["bars"][0]["label"], "1×")
        model_timeline = self.admin.get(f"{API}/material-models/{model.pk}/timeline").json()
        self.assertEqual([row["label"] for row in model_timeline["rows"]][1:], ["0001", "0002"])
