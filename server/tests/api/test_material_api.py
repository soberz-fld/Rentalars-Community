# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: material models, items, "installed in", history and import (MAT, IMP)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from rentalars.accounts.models import Role
from rentalars.masterdata.models import Supplier
from rentalars.material.models import MaterialItem, MaterialModel
from tests.api.base import API, ApiTestCase
from tests.helpers import category, make_item, make_items, make_model, make_product, make_user

CSV = (
    "ID;Artikelname;Kategorie;Spezifikation;Kategoriespezifische Angabe;Einsatz/Verbindung;Seriennummer;"
    "Notiz;Tag des Kaufs;Kaufnotiz;Kaufpreis;Gekauft (Händler);Artikelnummer beim Händler\n"
    "0500;Rack 6 HE;Rack;19 Zoll;;;R-77;;12.04.2023;;249,00;Musikhaus Nord;4711\n"
    "0310;Funkempfänger EW 100;Tontechnik;;;0500;SN-1;;;;399,00;Musikhaus Nord;\n"
    "0311;Funkempfänger EW 100;Tontechnik;;;;SN-2;;;;399,00;Musikhaus Nord;\n"
)


def csv_file(text: str = CSV) -> SimpleUploadedFile:
    """An uploaded CSV file with the 13 columns of the material list."""
    return SimpleUploadedFile("material.csv", text.encode("utf-8"), content_type="text/csv")


class MaterialModelAndItemTests(ApiTestCase):
    """Models, items and their IDs (MAT-001 to MAT-012)."""

    def test_model_with_category_specific_value(self) -> None:
        """MAT-009: cables carry their length in metres."""
        response = self.admin.post(
            f"{API}/material-models",
            {"name": "Cordial CPM 5 FM", "category": category("K").pk, "category_specific_value": "5"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["category_specific_display"], "5 m")
        wrong = self.admin.post(
            f"{API}/material-models",
            {"name": "Cordial CPM 10 FM", "category": category("K").pk, "category_specific_value": "lang"},
            format="json",
        )
        self.assert_error(wrong, 400, "validation_error")

    def test_items_get_consecutive_ids_with_leading_zeros(self) -> None:
        """MAT-002, MAT-003, MAT-006: several items are created in one step."""
        model = make_model("Cordial CPM 5 FM", category_code="K")
        response = self.admin.post(
            f"{API}/material-models/{model.pk}/items", {"count": 3, "purchase_note": "Sammelkauf"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([row["display_id"] for row in response.data], ["0001", "0002", "0003"])
        single = self.admin.post(f"{API}/material-items", {"material_model": model.pk}, format="json")
        self.assertEqual(single.data["display_id"], "0004")

    def test_an_id_is_never_given_twice(self) -> None:
        """MAT-001."""
        model = make_model("Rack 6 HE", category_code="R")
        make_item(model, 500)
        response = self.admin.post(
            f"{API}/material-items", {"material_model": model.pk, "inventory_number": 500}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "inventory_number")

    def test_item_row_carries_the_thirteen_fields_of_the_material_list(self) -> None:
        """MAT-011, MAT-012: model fields and item fields in one row."""
        supplier = Supplier.objects.create(name="Musikhaus Nord")
        model = make_model("Cordial CPM 5 FM", category_code="K")
        model.specification = "XLR m/f"
        model.set_category_specific_value("5")
        model.save()
        item = make_item(model, 17, serial_number="SN-17", supplier=supplier, purchase_price="12.50")
        row = self.admin.get(f"{API}/material-items/{item.pk}").data
        self.assertEqual(row["display_id"], "0017")
        self.assertEqual(row["name"], "Cordial CPM 5 FM")
        self.assertEqual(row["category_name"], category("K").name)
        self.assertEqual(row["specification"], "XLR m/f")
        self.assertEqual(row["category_specific"], "5 m")
        self.assertEqual(row["serial_number"], "SN-17")
        self.assertEqual(row["purchase_price"], "12.50")
        expanded = self.admin.get(f"{API}/material-items/{item.pk}", {"expand": "supplier"}).data
        self.assertEqual(expanded["supplier"]["name"], "Musikhaus Nord")

    def test_purchase_price_needs_its_own_right(self) -> None:
        """AUT-019: without the right the field is neither delivered nor accepted."""
        item = make_item(make_model("Rack 6 HE", category_code="R"), 500, purchase_price="249.00")
        Role.objects.create(name="Werkstatt", module_levels={"material": 2})
        workshop = self.client_for("willi", "Werkstatt")
        self.assertNotIn("purchase_price", workshop.get(f"{API}/material-items/{item.pk}").data)
        refused = workshop.patch(f"{API}/material-items/{item.pk}", {"purchase_price": "1.00"}, format="json")
        self.assert_error(refused, 400, "validation_error", "purchase_price")
        self.assertIn("purchase_price", self.client_for("luka", "Lager").get(f"{API}/material-items/{item.pk}").data)

    def test_duplicate_serial_number_warns_but_does_not_block(self) -> None:
        """MAT-004."""
        model = make_model("Funkempfänger", category_code="T")
        make_item(model, 310, serial_number="SN-1")
        response = self.admin.post(
            f"{API}/material-items", {"material_model": model.pk, "serial_number": "SN-1"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["warnings"]), 1)
        self.assertIn("0310", response.data["warnings"][0])

    def test_filters_and_search(self) -> None:
        """MAT-028."""
        cable = make_model("Cordial CPM 5 FM", make_product("K-005"), category_code="K")
        rack = make_model("Rack 6 HE", category_code="R")
        make_items(cable, 3)
        make_item(rack, 500, serial_number="R-77")
        MaterialItem.objects.filter(inventory_number=2).update(status="defective")

        def ids(**params: object) -> list[str]:
            return [row["display_id"] for row in self.admin.get(f"{API}/material-items", params).data["results"]]

        self.assertEqual(ids(category=category("K").pk), ["0001", "0002", "0003"])
        self.assertEqual(ids(status="defective"), ["0002"])
        self.assertEqual(ids(q="R-77"), ["0500"])
        self.assertEqual(ids(q="0003"), ["0003"])
        self.assertEqual(ids(without_product="true"), ["0500"])
        self.assertEqual(ids(ordering="-inventory_number")[0], "0500")

    def test_lookup_by_id_or_serial_number(self) -> None:
        """MAT-027: the entry point for a later scan."""
        make_item(make_model("Rack 6 HE", category_code="R"), 500, serial_number="R-77")
        self.assertEqual(self.admin.get(f"{API}/material-items/lookup", {"code": "500"}).data["display_id"], "0500")
        self.assertEqual(self.admin.get(f"{API}/material-items/lookup", {"code": "r-77"}).data["display_id"], "0500")
        self.assert_error(self.admin.get(f"{API}/material-items/lookup", {"code": "9999"}), 404, "not_found")

    def test_status_change_appears_in_the_history(self) -> None:
        """MAT-020, MAT-025."""
        item = make_item(make_model("Rack 6 HE", category_code="R"), 500)
        response = self.admin.patch(
            f"{API}/material-items/{item.pk}",
            {"status": "defective", "status_reason": "Griff abgerissen"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status_reason"], "Griff abgerissen")
        history = self.admin.get(f"{API}/material-items/{item.pk}/history").data
        changed = [row for row in history if any(change["field"] == "status" for change in row["changes"])]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["user"], "admin")
        self.assertIn("status_reason", [change["field"] for change in changed[0]["changes"]])

    def test_defective_needs_a_reason_and_leads_only_to_repair_or_out_of_the_stock(self) -> None:
        """MAT-044, MAT-045 – the same rules as on the item page."""
        item = make_item(make_model("Rack 6 HE", category_code="R"), 500)
        url = f"{API}/material-items/{item.pk}"
        self.assert_error(
            self.admin.patch(url, {"status": "defective"}, format="json"), 400, "validation_error", "status_reason"
        )
        self.admin.patch(url, {"status": "defective", "status_reason": "Griff abgerissen"}, format="json")

        self.assert_error(
            self.admin.patch(url, {"status": "available"}, format="json"), 400, "validation_error", "status"
        )
        repaired = self.admin.patch(url, {"status": "in_repair"}, format="json")
        self.assertEqual((repaired.data["status"], repaired.data["status_reason"]), ("in_repair", ""))
        self.assertEqual(self.admin.patch(url, {"status": "available"}, format="json").status_code, 200)
        # A reason alone can be added or corrected without changing the status.
        noted = self.admin.patch(url, {"status_reason": "frisch gewartet"}, format="json")
        self.assertEqual((noted.data["status"], noted.data["status_reason"]), ("available", "frisch gewartet"))

    def test_warehouse_may_write_material_but_read_only_users_may_not(self) -> None:
        model = make_model("Rack 6 HE", category_code="R")
        self.assertEqual(
            self.client_for("luka", "Lager")
            .post(f"{API}/material-items", {"material_model": model.pk}, format="json")
            .status_code,
            201,
        )
        self.assert_error(
            self.client_for("nora", "Nur-Lesen").post(
                f"{API}/material-items", {"material_model": model.pk}, format="json"
            ),
            403,
            "permission_denied",
        )
        self.assert_error(
            self.client_for("karl", "Personaldisposition").get(f"{API}/material-items"), 403, "permission_denied"
        )


class InstalledInTests(ApiTestCase):
    """Items inside other items (MAT-033 to MAT-041)."""

    def setUp(self) -> None:
        super().setUp()
        self.rack = make_item(make_model("Rack 6 HE", category_code="R"), 500)
        receiver_model = make_model("Funkempfänger EW 100", make_product("T-050"), category_code="T")
        self.receiver = make_item(receiver_model, 310)

    def test_installing_shows_the_content_and_the_container(self) -> None:
        response = self.admin.patch(
            f"{API}/material-items/{self.receiver.pk}",
            {"installed_in": self.rack.pk, "connection_type": "fixed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        rack = self.admin.get(f"{API}/material-items/{self.rack.pk}/contents").data
        self.assertEqual([(row["depth"], row["display_id"]) for row in rack["contents"]], [(1, "0310")])
        receiver = self.admin.get(f"{API}/material-items/{self.receiver.pk}/contents").data
        self.assertEqual([row["display_id"] for row in receiver["installed_in"]], ["0500"])

    def test_circle_is_rejected(self) -> None:
        """MAT-038."""
        self.admin.patch(f"{API}/material-items/{self.receiver.pk}", {"installed_in": self.rack.pk}, format="json")
        response = self.admin.patch(
            f"{API}/material-items/{self.rack.pk}", {"installed_in": self.receiver.pk}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "installed_in")

    def test_unknown_container_is_rejected(self) -> None:
        response = self.admin.patch(f"{API}/material-items/{self.receiver.pk}", {"installed_in": 999999}, format="json")
        self.assert_error(response, 400, "validation_error", "installed_in")

    def test_contents_are_added_and_removed_from_the_side_of_the_container(self) -> None:
        """MAT-046: ``POST`` and ``DELETE`` on ``/material-items/{id}/contents``."""
        url = f"{API}/material-items/{self.rack.pk}/contents"
        added = self.admin.post(url, {"item": self.receiver.pk, "connection_type": "loose"}, format="json")
        self.assertEqual(added.status_code, 200, added.data)
        self.assertEqual([(row["depth"], row["display_id"]) for row in added.data["contents"]], [(1, "0310")])
        self.receiver.refresh_from_db()
        self.assertEqual((self.receiver.installed_in, self.receiver.connection_type), (self.rack, "loose"))

        # No loops (MAT-034): the rack cannot go into the receiver it contains, nor into itself.
        circle = self.admin.post(
            f"{API}/material-items/{self.receiver.pk}/contents", {"item": self.rack.pk}, format="json"
        )
        self.assert_error(circle, 400, "validation_error", "installed_in")
        itself = self.admin.post(url, {"item": self.rack.pk}, format="json")
        self.assert_error(itself, 400, "validation_error", "installed_in")
        self.assert_error(self.admin.post(url, {"item": 999999}, format="json"), 404, "not_found")
        self.assert_error(
            self.admin.post(url, {"item": self.receiver.pk, "connection_type": "glued"}, format="json"),
            400,
            "validation_error",
            "connection_type",
        )

        removed = self.admin.delete(f"{url}/{self.receiver.pk}")
        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertEqual(removed.data["contents"], [])
        self.assert_error(self.admin.delete(f"{url}/{self.receiver.pk}"), 400, "validation_error")

    def test_an_item_in_another_container_is_not_moved_from_the_container_side(self) -> None:
        """MAT-046."""
        other = make_item(self.rack.material_model, 501)
        self.admin.patch(f"{API}/material-items/{self.receiver.pk}", {"installed_in": other.pk}, format="json")
        response = self.admin.post(
            f"{API}/material-items/{self.rack.pk}/contents", {"item": self.receiver.pk}, format="json"
        )
        self.assert_error(response, 400, "validation_error")
        self.receiver.refresh_from_db()
        self.assertEqual(self.receiver.installed_in, other)

    def test_taking_content_out_needs_write_access_not_delete_access(self) -> None:
        self.admin.post(f"{API}/material-items/{self.rack.pk}/contents", {"item": self.receiver.pk}, format="json")
        role = Role.objects.create(name="Material schreiben", module_levels={"material": 2})
        writer = make_user("schreiber")
        writer.roles.set([role])
        client = self.client_of(writer)
        self.assertEqual(
            client.delete(f"{API}/material-items/{self.rack.pk}/contents/{self.receiver.pk}").status_code, 200
        )
        self.assertEqual(client.delete(f"{API}/material-items/{self.receiver.pk}").status_code, 403)
        reader = self.client_for("leser", "Nur-Lesen")
        self.assertEqual(
            reader.post(
                f"{API}/material-items/{self.rack.pk}/contents", {"item": self.receiver.pk}, format="json"
            ).status_code,
            403,
        )

    def test_item_with_content_cannot_be_archived(self) -> None:
        """MAT-040: remove the content first."""
        self.admin.patch(f"{API}/material-items/{self.receiver.pk}", {"installed_in": self.rack.pk}, format="json")
        response = self.admin.patch(f"{API}/material-items/{self.rack.pk}", {"status": "retired"}, format="json")
        self.assert_error(response, 400, "validation_error", "status")


class ImportApiTests(ApiTestCase):
    """The material import through the API (IMP-002 to IMP-010)."""

    def test_fields_and_recognised_headings_are_listed(self) -> None:
        fields = self.admin.get(f"{API}/imports/material").data
        self.assertEqual([field["key"] for field in fields][:3], ["inventory_number", "name", "category"])
        self.assertTrue(fields[0]["required"])

    def test_dry_run_is_the_default_and_writes_nothing(self) -> None:
        """IMP-009."""
        response = self.admin.post(f"{API}/imports/material", {"file": csv_file()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["dry_run"])
        self.assertEqual(response.data["items_created"], 3)
        self.assertEqual(response.data["models_created"], 2)
        self.assertEqual(response.data["mapping"]["inventory_number"], "ID")
        self.assertEqual(MaterialItem.objects.count(), 0)
        self.assertEqual(MaterialModel.objects.count(), 0)

    def test_import_creates_models_items_and_links(self) -> None:
        """IMP-002, IMP-010: rows with the same article name share one model."""
        response = self.admin.post(
            f"{API}/imports/material", {"file": csv_file(), "dry_run": "false"}, format="multipart"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(MaterialModel.objects.count(), 2)
        self.assertEqual(sorted(MaterialItem.objects.values_list("inventory_number", flat=True)), [310, 311, 500])
        receiver = MaterialItem.objects.get(inventory_number=310)
        self.assertEqual(receiver.installed_in.inventory_number, 500)
        self.assertEqual(response.data["next_id"], "0501")

    def test_errors_carry_the_row_number_and_nothing_is_written(self) -> None:
        broken = CSV + "abc;Kaputt;Rack;;;;;;31.02.2023;;;;\n"
        response = self.admin.post(
            f"{API}/imports/material", {"file": csv_file(broken), "dry_run": "false"}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["ok"])
        self.assertEqual({error["row"] for error in response.data["errors"]}, {5})
        self.assertEqual(MaterialItem.objects.count(), 0)

    def test_columns_can_be_assigned_by_hand(self) -> None:
        """IMP-003."""
        text = CSV.replace("Artikelname", "Gerät")
        unmapped = self.admin.post(f"{API}/imports/material", {"file": csv_file(text)}, format="multipart")
        self.assertEqual(unmapped.status_code, 400)
        mapped = self.admin.post(
            f"{API}/imports/material", {"file": csv_file(text), "mapping": '{"name": "Gerät"}'}, format="multipart"
        )
        self.assertEqual(mapped.status_code, 200, mapped.data)
        self.assertEqual(mapped.data["items_created"], 3)

    @override_settings(MAX_IMPORT_ROWS_PER_REQUEST=2)
    def test_a_list_too_long_for_one_request_is_refused(self) -> None:
        """IMP-007: longer lists go through the command on the server."""
        response = self.admin.post(f"{API}/imports/material", {"file": csv_file()}, format="multipart")
        self.assert_error(response, 400, "validation_error")
        self.assertIn("rentalars import_material", str(response.data))
        self.assertEqual(MaterialItem.objects.count(), 0)

    def test_other_file_types_are_refused(self) -> None:
        """NFA-042: uploads are checked by type."""
        upload = SimpleUploadedFile("material.exe", b"MZ\x90\x00", content_type="application/octet-stream")
        response = self.admin.post(f"{API}/imports/material", {"file": upload}, format="multipart")
        self.assert_error(response, 400, "validation_error")

    def test_import_needs_write_access_to_material(self) -> None:
        reader = self.client_for("nora", "Nur-Lesen")
        self.assert_error(
            reader.post(f"{API}/imports/material", {"file": csv_file()}, format="multipart"), 403, "permission_denied"
        )
