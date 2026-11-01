# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the material wishes (API-014): power of a model (MAT-049), new items from a start ID with serial
numbers and invoice number (MAT-050), a product made from a model (MAT-051), the default storage location (MAT-052),
and a model assigned to a product (PRD-046)."""

from __future__ import annotations

from rentalars.accounts.models import Role
from rentalars.masterdata.models import StorageLocation
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.products.models import Product
from tests.api.base import API, ApiTestCase
from tests.helpers import category, make_item, make_model, make_product


class PowerTests(ApiTestCase):
    """MAT-049."""

    def test_the_power_of_a_model(self) -> None:
        response = self.admin.post(
            f"{API}/material-models",
            {"name": "Robe Pointe", "category": category("L").pk, "power_w": "470", "weight_kg": "15.5"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["power_w"], response.data["weight_kg"]), ("470.00", "15.50"))
        negative = self.admin.patch(f"{API}/material-models/{response.data['id']}", {"power_w": "-1"}, format="json")
        self.assert_error(negative, 400, "validation_error", "power_w")


class NewItemsTests(ApiTestCase):
    """MAT-050: ``POST /material-models/{id}/items`` with a start ID, serial numbers and the invoice."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Shure SM58", make_product("T-010"), category_code="T")
        self.url = f"{API}/material-models/{self.model.pk}/items"

    def test_start_id_serial_numbers_and_invoice(self) -> None:
        make_item(self.model, 43)
        response = self.admin.post(
            self.url,
            {
                "count": 3,
                "start_number": 42,
                "serial_numbers": ["SN-1", "", "SN-3"],
                "invoice_number": "RE-118",
                "purchase_date": "2026-10-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([row["inventory_number"] for row in response.data], [42, 44, 45])
        self.assertEqual([row["serial_number"] for row in response.data], ["SN-1", "", "SN-3"])
        self.assertEqual({row["invoice_number"] for row in response.data}, {"RE-118"})

    def test_too_many_serial_numbers_and_a_taken_start_id(self) -> None:
        too_many = self.admin.post(self.url, {"count": 1, "serial_numbers": ["A", "B"]}, format="json")
        self.assert_error(too_many, 400, "validation_error", "serial_numbers")
        make_item(self.model, 42)
        taken = self.admin.post(self.url, {"count": 2, "start_number": 42}, format="json")
        self.assert_error(taken, 400, "validation_error", "start_number")
        self.assertEqual(MaterialItem.objects.count(), 1)

    def test_the_invoice_number_of_one_item(self) -> None:
        item = make_item(self.model, 7)
        response = self.admin.patch(f"{API}/material-items/{item.pk}", {"invoice_number": "RE-9"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.admin.get(f"{API}/material-items/{item.pk}").data["invoice_number"], "RE-9")


class ProductFromModelTests(ApiTestCase):
    """MAT-051: ``POST /material-models/{id}/create-product``."""

    def test_the_product_is_created_and_the_model_assigned(self) -> None:
        model = make_model("Robe Pointe", category_code="L")
        response = self.admin.post(f"{API}/material-models/{model.pk}/create-product")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["article_number"], response.data["name"]), ("L-001", "Robe Pointe"))
        model.refresh_from_db()
        self.assertEqual(model.default_product_id, response.data["id"])
        again = self.admin.post(f"{API}/material-models/{model.pk}/create-product")
        self.assert_error(again, 400, "validation_error")

    def test_write_access_to_products_is_needed(self) -> None:
        Role.objects.create(name="Werkstatt", module_levels={"material": 2, "products": 1})
        workshop = self.client_for("willi", "Werkstatt")
        model = make_model("Leiter 3-teilig", category_code="R")
        response = workshop.post(f"{API}/material-models/{model.pk}/create-product")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Product.objects.filter(name="Leiter 3-teilig").exists())


class AssignModelTests(ApiTestCase):
    """PRD-046: a model is given to a product by setting its ``default_product``."""

    def test_assigning_a_model_without_product(self) -> None:
        product = make_product("K-005")
        model = make_model("Cordial CPM 5 FM", category_code="K")
        response = self.admin.patch(f"{API}/material-models/{model.pk}", {"default_product": product.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(MaterialModel.objects.get(pk=model.pk).default_product, product)


class DefaultLocationTests(ApiTestCase):
    """MAT-052: ``is_default`` of the storage locations."""

    def test_reading_and_choosing_the_default(self) -> None:
        rows = self.admin.get(f"{API}/storage-locations").data["results"]
        self.assertEqual([row["name"] for row in rows if row["is_default"]], ["Hauptlager"])
        created = self.admin.post(f"{API}/storage-locations", {"name": "Halle 2", "is_default": True}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(StorageLocation.get_default().name, "Halle 2")
        self.assertEqual(StorageLocation.objects.filter(is_default=True).count(), 1)
        inactive = self.admin.post(
            f"{API}/storage-locations", {"name": "Halle 3", "is_default": True, "is_active": False}, format="json"
        )
        self.assert_error(inactive, 400, "validation_error", "is_default")
