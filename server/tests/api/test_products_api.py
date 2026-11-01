# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: products, kits and the availability query (PRD, VFG, API-009)."""

from __future__ import annotations

from rentalars.accounts.models import Role
from rentalars.masterdata.models import TaxRate, Unit
from rentalars.material.models import MaterialItem
from rentalars.products.models import Product
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, at, category, make_items, make_model, make_product, make_project, make_stock


def product_body(article_number: str, **fields: object) -> dict[str, object]:
    """The smallest valid body for a rental product."""
    code = article_number.split("-")[0]
    body: dict[str, object] = {
        "article_number": article_number,
        "name": f"Produkt {article_number}",
        "category": category(code).pk,
        "unit": Unit.objects.get(name="Stück (Miete)").pk,  # ADM-011
        "tax_rate": TaxRate.get_default().pk,
        "kind": "rental",
        "billing_mode": "daily_piece",
        "price": "10.00",
    }
    body.update(fields)
    return body


class ProductTests(ApiTestCase):
    """Products and their article numbers (PRD-007 to PRD-025)."""

    def test_create_read_change(self) -> None:
        """PRD-012."""
        created = self.admin.post(f"{API}/products", product_body("K-005", name="XLR-Kabel 5 m"), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["stock"], {"total": 0, "operational": 0, "plannable": 0})
        changed = self.admin.patch(f"{API}/products/{created.data['id']}", {"price": "1.50"}, format="json")
        self.assertEqual(changed.data["price"], "1.50")
        self.assertEqual(self.admin.get(f"{API}/products/{created.data['id']}").data["name"], "XLR-Kabel 5 m")

    def test_article_number_must_match_the_category(self) -> None:
        """PRD-008, PRD-009."""
        wrong_code = product_body("K-005", category=category("L").pk)
        self.assert_error(
            self.admin.post(f"{API}/products", wrong_code, format="json"), 400, "validation_error", "article_number"
        )
        malformed = {**product_body("K-005"), "article_number": "K005"}
        self.assert_error(
            self.admin.post(f"{API}/products", malformed, format="json"), 400, "validation_error", "article_number"
        )

    def test_article_number_is_unique(self) -> None:
        make_product("K-005")
        response = self.admin.post(f"{API}/products", product_body("K-005"), format="json")
        self.assert_error(response, 400, "validation_error", "article_number")

    def test_next_free_article_number_and_presets_are_suggested(self) -> None:
        """PRD-010, PRD-030."""
        make_product("K-005")
        make_product("K-007")
        suggestion = self.admin.get(f"{API}/products/suggest-article-number", {"category": category("K").pk}).data
        self.assertEqual(suggestion["article_number"], "K-008")
        self.assertEqual(suggestion["kind"], "rental")
        self.assert_error(
            self.admin.get(f"{API}/products/suggest-article-number", {"category": 0}),
            400,
            "validation_error",
            "category",
        )

    def test_used_article_number_is_protected_by_a_special_right(self) -> None:
        """PRD-011."""
        product = make_product("K-005")
        add_line(make_project(), product, 1)
        # AUT-036: the Projektleitung only reads products now – a role of its own writes them.
        Role.objects.create(name="Produktpflege", module_levels={"products": 2, "projects": 2})
        manager = self.client_for("paula", "Produktpflege")
        refused = manager.patch(f"{API}/products/{product.pk}", {"article_number": "K-006"}, format="json")
        self.assert_error(refused, 400, "validation_error", "article_number")
        allowed = self.admin.patch(f"{API}/products/{product.pk}", {"article_number": "K-006"}, format="json")
        self.assertEqual(allowed.status_code, 200, allowed.data)

    def test_stock_is_counted_from_the_assigned_material(self) -> None:
        """PRD-006: the product has no stock field of its own."""
        product = make_stock("K-005", 9)
        MaterialItem.objects.filter(inventory_number=1).update(status="defective")
        self.assertEqual(
            self.admin.get(f"{API}/products/{product.pk}").data["stock"], {"total": 9, "operational": 8, "plannable": 8}
        )
        listed = self.admin.get(f"{API}/products", {"search": "K-005"}).data["results"][0]
        self.assertEqual(listed["stock"]["total"], 9)
        materials = self.admin.get(f"{API}/products/{product.pk}/materials").data
        self.assertEqual(len(materials["models"]), 1)
        self.assertEqual(len(materials["items"]), 9)

    def test_prices_are_hidden_without_the_price_right(self) -> None:
        """AUT-019."""
        product = make_product("K-005", price="1.50")
        Role.objects.create(name="Werkstatt", module_levels={"products": 2})
        workshop = self.client_for("willi", "Werkstatt")
        data = workshop.get(f"{API}/products/{product.pk}").data
        self.assertNotIn("price", data)
        self.assertNotIn("sale_price", data)
        self.assertNotIn("calculation_note", data)
        refused = workshop.patch(f"{API}/products/{product.pk}", {"price": "0.01"}, format="json")
        self.assert_error(refused, 400, "validation_error", "price")
        self.assertEqual(str(Product.objects.get(pk=product.pk).price), "1.50")

    def test_product_in_use_is_deactivated_instead_of_deleted(self) -> None:
        """PRD-024."""
        product = make_product("K-005")
        add_line(make_project(), product, 1)
        self.assert_error(self.admin.delete(f"{API}/products/{product.pk}"), 400, "validation_error")
        self.assertEqual(
            self.admin.patch(f"{API}/products/{product.pk}", {"is_active": False}, format="json").status_code, 200
        )
        unused = make_product("K-006")
        self.assertEqual(self.admin.delete(f"{API}/products/{unused.pk}").status_code, 204)

    def test_category_filter_includes_subcategories(self) -> None:
        cables = category("K")
        audio = self.admin.post(f"{API}/categories", {"name": "Audiokabel", "parent": cables.pk}, format="json").data
        make_product("K-005", category=type(cables).objects.get(pk=audio["id"]))
        make_product("L-010")
        numbers = [
            row["article_number"] for row in self.admin.get(f"{API}/products", {"category": cables.pk}).data["results"]
        ]
        self.assertEqual(numbers, ["K-005"])


class KitTests(ApiTestCase):
    """Kits and their components (PRD-020 to PRD-023)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_product("K-010")
        self.speaker = make_product("T-010")
        self.kit = make_product("T-100", kind="kit", billing_mode="daily_kit")

    def test_components_are_replaced_as_a_whole(self) -> None:
        body = [{"component": self.cable.pk, "quantity": 2}, {"component": self.speaker.pk, "quantity": 1}]
        response = self.admin.put(f"{API}/products/{self.kit.pk}/components", body, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [(row["article_number"], row["quantity"]) for row in response.data], [("K-010", 2), ("T-010", 1)]
        )
        self.assertEqual(len(self.admin.get(f"{API}/products/{self.kit.pk}").data["components"]), 2)

    def test_a_kit_cannot_contain_itself(self) -> None:
        body = [{"component": self.kit.pk, "quantity": 1}]
        self.assert_error(
            self.admin.put(f"{API}/products/{self.kit.pk}/components", body, format="json"), 400, "validation_error"
        )

    def test_only_kits_have_components(self) -> None:
        body = [{"component": self.cable.pk, "quantity": 1}]
        self.assert_error(
            self.admin.put(f"{API}/products/{self.speaker.pk}/components", body, format="json"), 400, "validation_error"
        )


class AvailabilityQueryTests(ApiTestCase):
    """The availability endpoints (VFG-001, VFG-003, VFG-011, API-009)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        add_line(self.project, self.cable, 6)

    def test_free_quantity_in_a_period(self) -> None:
        response = self.admin.get(
            f"{API}/products/{self.cable.pk}/availability", {"from": at(11).isoformat(), "to": at(13).isoformat()}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["stock"], 9)
        self.assertEqual(response.data["firm"], 6)
        self.assertEqual(response.data["free"], 3)
        occupier = response.data["occupied_by"][0]
        self.assertEqual(occupier["project_number"], self.project.number)
        self.assertEqual(occupier["quantity"], 6)
        self.assertTrue(occupier["firm"])

    def test_several_products_in_one_query(self) -> None:
        lamp = make_stock("L-010", 4)
        response = self.admin.get(
            f"{API}/availability",
            {"from": at(11).isoformat(), "to": at(13).isoformat(), "products": f"{self.cable.pk},{lamp.pk}"},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({row["product"]: row["free"] for row in response.data}, {self.cable.pk: 3, lamp.pk: 4})

    def test_own_project_can_be_left_out(self) -> None:
        response = self.admin.get(
            f"{API}/products/{self.cable.pk}/availability",
            {"from": at(11).isoformat(), "to": at(13).isoformat(), "exclude_project": self.project.pk},
        )
        self.assertEqual(response.data["free"], 9)

    def test_period_must_be_complete_and_in_order(self) -> None:
        url = f"{API}/products/{self.cable.pk}/availability"
        self.assert_error(self.admin.get(url, {"from": at(11).isoformat()}), 400, "validation_error", "to")
        self.assert_error(
            self.admin.get(url, {"from": "2027-03-11T08:00:00", "to": at(13).isoformat()}),
            400,
            "validation_error",
            "from",
        )
        self.assert_error(
            self.admin.get(url, {"from": at(13).isoformat(), "to": at(11).isoformat()}), 400, "validation_error", "to"
        )

    def test_project_planners_may_query_availability_without_product_rights(self) -> None:
        # AUT-032: with the special right to see availability (test_091_rights refuses it without).
        Role.objects.create(name="Planung", module_levels={"projects": 2}, special_rights=["availability"])
        planner = self.client_for("pia", "Planung")
        response = planner.get(
            f"{API}/availability",
            {"from": at(11).isoformat(), "to": at(13).isoformat(), "products": str(self.cable.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assert_error(planner.get(f"{API}/products"), 403, "permission_denied")

    def test_service_products_are_not_checked(self) -> None:
        """PRD-021."""
        transport = make_product("F-001", kind="service", billing_mode="flat")
        response = self.admin.get(
            f"{API}/products/{transport.pk}/availability", {"from": at(11).isoformat(), "to": at(13).isoformat()}
        )
        self.assertFalse(response.data["checked"])

    def test_material_of_a_new_model_raises_the_stock_at_once(self) -> None:
        model = make_model("Sommer Stage 22 5 m", self.cable)
        make_items(model, 5)
        response = self.admin.get(
            f"{API}/products/{self.cable.pk}/availability", {"from": at(11).isoformat(), "to": at(13).isoformat()}
        )
        self.assertEqual(response.data["free"], 8)
