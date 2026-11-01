# SPDX-License-Identifier: GPL-3.0-or-later
"""API for customer material: categories marked for it and products with an owner (PRD-043), and such
material in the projects of its owner (PRJ-096)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.masterdata.models import Category, TaxRate, Unit
from rentalars.products.models import BillingMode, Product
from rentalars.projects.models import MaterialLine
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, add_line, make_customer, make_items, make_model, make_product, make_project

D = Decimal


def customer_material_category() -> Category:
    return Category.objects.get(parent__isnull=True, code="C")


class CategoryApiTests(ApiTestCase):
    """PRD-043: ``is_customer_material`` on ``/categories``."""

    def test_read_filter_and_create(self) -> None:
        body = self.admin.get(f"{API}/categories/{customer_material_category().pk}").json()
        self.assertTrue(body["is_customer_material"])
        listed = self.admin.get(f"{API}/categories", {"is_customer_material": "true"}).json()
        self.assertEqual([row["code"] for row in listed["results"]], ["C"])
        created = self.admin.post(
            f"{API}/categories", {"name": "Backline der Kunden", "code": "BK", "is_customer_material": True}
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertTrue(Category.objects.get(code="BK").is_customer_material)

    def test_only_main_categories_with_stock(self) -> None:
        response = self.admin.post(
            f"{API}/categories",
            {"name": "Pulte", "parent": customer_material_category().pk, "is_customer_material": True},
        )
        self.assert_error(response, 400, "validation_error", "is_customer_material")


class ProductApiTests(ApiTestCase):
    """PRD-043: ``owner`` on ``/products`` – required in C, refused elsewhere, never with a price."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")
        self.base = {
            "category": customer_material_category().pk,
            "name": "Mischpult der Band",
            "unit": Unit.objects.get(name="Stück (Miete)").pk,
            "tax_rate": TaxRate.get_default().pk,
            "kind": "rental",
        }

    def test_create_with_owner(self) -> None:
        response = self.admin.post(
            f"{API}/products",
            {**self.base, "article_number": "C-001", "owner": self.band.pk, "billing_mode": "daily_piece"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["owner"], body["price"], body["billing_mode"]), (self.band.pk, None, "flat"))
        self.assertEqual(self.admin.get(f"{API}/products", {"owner": self.band.pk}).json()["count"], 1)

    def test_without_owner_with_price_and_outside_c(self) -> None:
        self.assert_error(
            self.admin.post(f"{API}/products", {**self.base, "article_number": "C-001"}),
            400,
            "validation_error",
            "owner",
        )
        self.assert_error(
            self.admin.post(
                f"{API}/products", {**self.base, "article_number": "C-001", "owner": self.band.pk, "price": "10.00"}
            ),
            400,
            "validation_error",
            "price",
        )
        sound = Category.objects.get(parent__isnull=True, code="T")
        self.assert_error(
            self.admin.post(
                f"{API}/products",
                {**self.base, "category": sound.pk, "article_number": "T-001", "owner": self.band.pk, "price": "1"},
            ),
            400,
            "validation_error",
            "owner",
        )


class LineApiTests(ApiTestCase):
    """PRJ-096: lines of customer material through ``/projects/{id}/material-lines`` and the overviews."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")
        self.desk = make_product("C-001", "Mischpult der Band", price=None, owner=self.band)
        make_items(make_model("Pult", self.desk), 1)
        self.project = make_project("Gig", customer=self.band)
        self.url = f"{API}/projects/{self.project.pk}/material-lines"

    def test_added_in_the_owners_project(self) -> None:
        response = self.admin.post(self.url, {"product": self.desk.pk, "quantity": "1"})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["is_customer_material"], body["unit_price"]), (True, "0.00"))
        self.assertEqual((body["price"]["amount"], body["price"]["is_customer_material"]), ("0.00", True))

    def test_refused_in_a_project_of_somebody_else(self) -> None:
        other = make_project("Stadtfest", customer=make_customer("Stadtwerke"))
        error = self.assert_error(
            self.admin.post(f"{API}/projects/{other.pk}/material-lines", {"product": self.desk.pk}),
            400,
            "validation_error",
            "product",
        )
        self.assertIn("nur in Projekten dieses Kunden", error["fields"]["product"][0]["message"])
        self.assertFalse(MaterialLine.objects.filter(project=other).exists())

    def test_no_price_and_no_option_through_the_api(self) -> None:
        line = add_line(self.project, self.desk).line
        self.assert_error(
            self.admin.patch(f"{self.url}/{line.pk}", {"unit_price": "5.00"}), 400, "validation_error", "unit_price"
        )
        self.assert_error(self.admin.patch(f"{self.url}/{line.pk}", {"variant": "optional"}), 400, "validation_error")

    def test_suggest_only_for_the_owners_projects(self) -> None:
        """The product search of the planning (``/products/suggest/``) with the project named."""
        self.client.force_login(self.admin_user)
        other = make_project("Stadtfest", customer=make_customer("Stadtwerke"))
        own = self.client.get("/products/suggest/", {"q": "Mischpult", "project": self.project.pk}).json()
        self.assertEqual([row["id"] for row in own], [self.desk.pk])
        self.assertTrue(own[0]["hint"].startswith("Kundenmaterial"))
        self.assertEqual(self.client.get("/products/suggest/", {"q": "Mischpult", "project": other.pk}).json(), [])
        self.assertEqual(self.client.get("/products/suggest/", {"q": "Mischpult"}).json(), [])
        with_items = self.client.get("/products/suggest/", {"q": "Pult", "project": other.pk, "with_material": 1})
        self.assertEqual(with_items.json(), [])

    def test_shortage_without_suggestion_and_price_overview(self) -> None:
        group = add_group(self.project, "FOH")
        add_line(self.project, self.desk, 2, group=group)
        add_line(self.project, make_product("L-001", price="50.00", billing_mode=BillingMode.FLAT), 1, group=group)
        rows = self.admin.get(f"{API}/projects/{self.project.pk}/shortages").json()
        shortage = next(row for row in rows if row["product"] == self.desk.pk)
        self.assertEqual((shortage["shortage"], shortage["suggestion"]), (1, None))
        # The light (no stock at all) keeps its suggestion.
        light = next(row for row in rows if row["product"] != self.desk.pk)
        self.assertIsNotNone(light["suggestion"])
        accepted = self.admin.post(
            f"{API}/projects/{self.project.pk}/shortages/accept",
            {"line": shortage["line"], "product": self.desk.pk, "quantity": 1},
        )
        self.assert_error(accepted, 400, "validation_error")
        overview = self.admin.get(f"{API}/projects/{self.project.pk}/price-overview").json()
        lines = overview["groups"][0]["lines"]
        self.assertEqual([line["is_customer_material"] for line in lines], [True, False])
        self.assertEqual(overview["groups"][0]["subtotal"], "50.00")
        self.assertEqual(Product.objects.get(pk=self.desk.pk).owner, self.band)
