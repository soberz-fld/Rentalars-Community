# SPDX-License-Identifier: GPL-3.0-or-later
"""The storage spot of an item inside its storage location (MAT-080).

The requirement: besides the storage location, an item gets a storage spot inside that location. It should take
little room, so no long texts; a format such as 1-A-1 (shelf or area 1, shelf place A, height 1), i.e. in principle a
two-digit number, one letter, a one-digit number.

* A short text field on the item; text of the form number-letter-digit is written as ``01-A-1`` however it is typed.
* In the form of an item, of new items, of many items at once, on the item's page, in the list, in the packing list
  next to a chosen item, in the import and export, and in the API.
"""

from __future__ import annotations

import io

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.rights import Rights
from rentalars.core import import_exports
from rentalars.masterdata.models import StorageLocation
from rentalars.material import services
from rentalars.material.importer import import_material, read_table, resolve_mapping
from rentalars.material.models import ConnectionType, MaterialItem
from rentalars.material.spots import normalise_spot
from tests.api.base import API, ApiTestCase
from tests.helpers import make_item, make_items, make_model, make_product
from tests.ui.base import UiTestCase, form_data


class NormaliseTests(UiTestCase):
    """Whatever is typed, the same place is written the same way."""

    def test_the_mark_is_written_one_way(self) -> None:
        for typed in ("1a1", "01-A-1", "1-a-1", "1 A 1", "01.a.1", "1/A/1", " 01 - a - 1 ", "01A1"):
            with self.subTest(typed=typed):
                self.assertEqual(normalise_spot(typed), "01-A-1")
        self.assertEqual(normalise_spot("12b7"), "12-B-7")

    def test_other_short_text_is_kept(self) -> None:
        self.assertEqual(normalise_spot("Kiste  4"), "Kiste 4")
        self.assertEqual(normalise_spot("123-A-1"), "123-A-1")  # three digits: not a mark of this kind
        self.assertEqual(normalise_spot("1-AB-1"), "1-AB-1")
        self.assertEqual(normalise_spot(None), "")
        self.assertEqual(normalise_spot("   "), "")

    def test_the_model_normalises_and_limits(self) -> None:
        item = make_items(make_model("Kabel", make_product("K-005")))[0]
        item.storage_spot = "3c2"
        item.full_clean()
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.storage_spot, "03-C-2")
        item.storage_spot = "x" * 13
        with self.assertRaises(ValidationError) as caught:
            item.full_clean()
        self.assertIn("storage_spot", caught.exception.message_dict)

    def test_an_installed_item_has_the_spot_of_its_container(self) -> None:
        case = make_items(make_model("Case", make_product("S-600")))[0]
        receiver = make_items(make_model("Empfänger", make_product("T-050")))[0]
        case.storage_spot = "02-B-1"
        case.save()
        services.install_item(receiver, case, connection_type=ConnectionType.LOOSE)
        receiver.refresh_from_db()
        self.assertEqual(receiver.effective_storage_spot, "02-B-1")


class PagesTests(UiTestCase):
    """The forms, the page and the list."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Shure SM58", make_product("T-010"), category_code="T")
        self.hall = StorageLocation.objects.create(name="Halle 2")

    def test_editing_an_item(self) -> None:
        item = make_items(self.model)[0]
        edit = reverse("material:item_edit", args=[item.pk])
        page = self.client.get(edit)
        self.assertIn("Lagerplatz", self.assert_ok(page))
        self.client.post(edit, form_data(page, storage_location=self.hall.pk, storage_spot="4d2"))
        item.refresh_from_db()
        self.assertEqual((item.storage_location, item.storage_spot), (self.hall, "04-D-2"))
        detail = self.assert_ok(self.client.get(reverse("material:item_detail", args=[item.pk])))
        self.assertIn('<span class="storage-spot">04-D-2</span>', detail)
        self.assertIn("Halle 2", detail)

    def test_new_items_get_the_spot(self) -> None:
        url = reverse("material:item_create", args=[self.model.pk])
        page = self.client.get(url)
        self.assertIn("Lagerplatz", self.assert_ok(page))
        data = form_data(page, count=2, storage_location=self.hall.pk, storage_spot="1a1")
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:300])
        self.assertEqual(list(MaterialItem.objects.values_list("storage_spot", flat=True)), ["01-A-1", "01-A-1"])

    def test_many_items_at_once(self) -> None:
        items = make_items(self.model, 3)
        for item in items:
            item.storage_location = StorageLocation.get_default()
            item.storage_spot = "09-Z-9"
            item.save()
        page = self.client.get(reverse("material:item_list"))
        self.assertIn("Lagerplatz", self.assert_ok(page))

        def change(*pks: int, **fields: object) -> None:
            data = form_data(page, containing="storage_location", **fields)
            data["items"] = [str(pk) for pk in pks]
            data["action"] = "change"
            self.client.post(reverse("material:item_bulk_update"), data, follow=True)

        change(items[0].pk, storage_spot="2b3")
        self.assertEqual(MaterialItem.objects.get(pk=items[0].pk).storage_spot, "02-B-3")
        # Another location without a new spot: the old spot meant a place in the old location.
        change(items[1].pk, storage_location=self.hall.pk)
        moved = MaterialItem.objects.get(pk=items[1].pk)
        self.assertEqual((moved.storage_location, moved.storage_spot), (self.hall, ""))
        # With a spot: both.
        change(items[2].pk, storage_location=self.hall.pk, storage_spot="1c1")
        both = MaterialItem.objects.get(pk=items[2].pk)
        self.assertEqual((both.storage_location, both.storage_spot), (self.hall, "01-C-1"))

    def test_the_list_shows_and_finds_the_spot(self) -> None:
        item = make_item(self.model, 7, storage_location=self.hall, storage_spot="03-A-2")
        make_item(self.model, 8, storage_location=self.hall, storage_spot="03-B-2")
        found = services_search("3a2")
        self.assertEqual(list(found), [item])
        page = self.assert_ok(self.client.get(reverse("material:item_list") + "?q=3a2&cols=id,location"))
        self.assertIn("Halle 2 03-A-2", page)
        self.assertNotIn("03-B-2", page)


def services_search(text: str) -> list[MaterialItem]:
    from rentalars.material.filters import search_items

    return list(search_items(MaterialItem.objects.all(), text))


class ImportExportTests(UiTestCase):
    """Import column "Lagerplatz" and the same column in the export."""

    def test_import_and_export(self) -> None:
        data = read_table(
            io.BytesIO(b"ID;Artikelname;Kategorie;Lagerort;Lagerplatz\n1;Cordial CPM 5 FM;Kabel;Halle 1;2a3\n"),
            "material.csv",
        )
        report = import_material(data, resolve_mapping(data.headers, {}), dry_run=False, actor="system:test")
        self.assertTrue(report.ok, [str(error) for error in report.errors])
        self.assertEqual(MaterialItem.objects.get(inventory_number=1).storage_spot, "02-A-3")
        text = import_exports.text_of(import_exports.get("material"), Rights.everything())
        self.assertIn("Lagerplatz", text.splitlines()[0])
        self.assertIn("02-A-3", text)


class ApiTests(ApiTestCase):
    """The API (API-002): the field, normalised, and in the bulk update."""

    def test_field_and_bulk_update(self) -> None:
        model = make_model("Kabel", make_product("K-005"))
        hall = StorageLocation.objects.create(name="Halle 2")
        created = self.admin.post(
            f"{API}/material-models/{model.pk}/items",
            {"storage_location": hall.pk, "storage_spot": "5e6"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()[0]
        self.assertEqual((body["storage_spot"], body["effective_storage_spot"]), ("05-E-6", "05-E-6"))
        patched = self.admin.patch(f"{API}/material-items/{body['id']}", {"storage_spot": "1b1"}, format="json")
        self.assertEqual(patched.json()["storage_spot"], "01-B-1")
        too_long = self.admin.patch(f"{API}/material-items/{body['id']}", {"storage_spot": "x" * 13}, format="json")
        self.assert_error(too_long, 400, "validation_error", "storage_spot")
        bulk = self.admin.post(
            f"{API}/material-items/bulk-update",
            {"items": [body["id"]], "storage_spot": "7g7"},
            format="json",
        )
        self.assertEqual(bulk.status_code, 200, bulk.content)
        self.assertEqual(MaterialItem.objects.get(pk=body["id"]).storage_spot, "07-G-7")
        moved = self.admin.post(
            f"{API}/material-items/bulk-update", {"items": [body["id"]], "storage_location": None}, format="json"
        )
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(MaterialItem.objects.get(pk=body["id"]).storage_spot, "")


class PacklistSpotTests(UiTestCase):
    """MAT-078: the packing list shows where a chosen item is to be taken from."""

    def test_a_chosen_item_shows_its_spot(self) -> None:
        from rentalars.packing import services as packing
        from tests.helpers import add_line, make_project

        product = make_product("L-010", "PAR 64")
        items = make_items(make_model("PAR 64", product, category_code="L"), 2)
        items[0].storage_spot = "2a3"
        items[0].full_clean()
        items[0].save()
        project = make_project()
        line = add_line(project, product, 1).line
        packlist = packing.get_packlist(project)
        packing.choose_items(packlist, line.pk, product.pk, [items[0].pk])
        row = packing.build_overview(packlist).rows[0]
        self.assertEqual([chosen.spot for chosen in row.chosen], ["02-A-3"])
