# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the planning wishes: spans of up to ten days (VFG-024), maximum discount of products (PRD-041)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.accounts.models import Role
from rentalars.masterdata.models import RentalScale, Unit
from rentalars.products.models import Product
from rentalars.projects.pricing import compute_project_prices
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, at, category, make_person, make_product, make_project, plan


class SpanOfDaysTests(ApiTestCase):
    """VFG-024: ``days`` gives the 1 to 10 days of the pages – and up to 84 days, as 12 weeks."""

    def test_calendar_and_personnel_plan_of_seven_and_ten_days(self) -> None:
        make_project("Vortrag", start=at(10, 8), end=at(10, 12))
        make_project("Messe", start=at(17, 8), end=at(19, 18))
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project("Kinderfest", start=at(19, 8), end=at(19, 18)), "Tontechnik", anna)
        seven = self.admin.get(f"{API}/calendar", {"from": "2027-03-10", "days": 7}).json()
        self.assertEqual([row["name"] for row in seven], ["Vortrag"])
        ten = self.admin.get(f"{API}/calendar", {"from": "2027-03-10", "days": 10}).json()
        self.assertEqual([row["name"] for row in ten], ["Vortrag", "Messe", "Kinderfest"])
        # Every active person is listed (VFG-023): Anna's row among those of the accounts.
        (row,) = [
            row
            for row in self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-10", "days": 10}).json()
            if row["person"] == anna.pk
        ]
        self.assertEqual([entry["type"] for entry in row["entries"]], ["deployment"])
        (row,) = [
            row
            for row in self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-10", "days": 9}).json()
            if row["person"] == anna.pk
        ]
        self.assertEqual(len(row["entries"]), 0)

    def test_eighty_four_days_stay_the_longest_span(self) -> None:
        make_project("Sommerfest", start=at(1, month=6), end=at(2, month=6))  # 1 June is day 84 from 10 March
        make_project("Hafenfest", start=at(2, 12, month=6), end=at(3, month=6))  # day 85
        rows = self.admin.get(f"{API}/calendar", {"from": "2027-03-10", "days": 84}).json()
        self.assertEqual([row["name"] for row in rows], ["Sommerfest"])
        rows = self.admin.get(f"{API}/calendar", {"from": "2027-03-10", "days": 200}).json()
        self.assertEqual([row["name"] for row in rows], ["Sommerfest"])


class ProductMaximumDiscountTests(ApiTestCase):
    """PRD-041: ``max_discount_percent`` of a product – ``null`` no limit, 0 never discounted; needs the price right."""

    def test_read_create_and_change(self) -> None:
        product = make_product("L-050", "Nebelmaschine", price="100.00", max_discount_percent=Decimal("5"))
        self.assertEqual(self.admin.get(f"{API}/products/{product.pk}").json()["max_discount_percent"], "5.00")
        body = {
            "article_number": "L-051",
            "name": "Hazer",
            "category": category("L").pk,
            "unit": Unit.objects.get(name="Stück (Miete)").pk,
            "tax_rate": product.tax_rate_id,
            "kind": "rental",
            "billing_mode": "daily_piece",
            "price": "40.00",
            "max_discount_percent": "0",
        }
        created = self.admin.post(f"{API}/products", body, format="json")
        self.assertEqual(created.status_code, 201, created.json())
        self.assertEqual(created.json()["max_discount_percent"], "0.00")
        changed = self.admin.patch(f"{API}/products/{product.pk}", {"max_discount_percent": None}, format="json")
        self.assertIsNone(changed.json()["max_discount_percent"])
        self.assertIsNone(Product.objects.get(pk=product.pk).max_discount_percent)

    def test_out_of_range_is_refused(self) -> None:
        product = make_product("L-050", price="100.00")
        refused = self.admin.patch(f"{API}/products/{product.pk}", {"max_discount_percent": "101"}, format="json")
        self.assert_error(refused, 400, "validation_error", "max_discount_percent")

    def test_needs_the_price_right(self) -> None:
        product = make_product("L-050", price="100.00", max_discount_percent=Decimal("5"))
        Role.objects.create(name="Werkstatt", module_levels={"products": 2})
        workshop = self.client_for("willi", "Werkstatt")
        self.assertNotIn("max_discount_percent", workshop.get(f"{API}/products/{product.pk}").json())
        refused = workshop.patch(f"{API}/products/{product.pk}", {"max_discount_percent": "50"}, format="json")
        self.assert_error(refused, 400, "validation_error", "max_discount_percent")
        self.assertEqual(Product.objects.get(pk=product.pk).max_discount_percent, Decimal("5.00"))

    def test_lines_of_the_product_show_the_cut_discount(self) -> None:
        project = make_project()
        hazer = make_product("L-050", price="100.00", billing_mode="flat", max_discount_percent=Decimal("5"))
        line = add_line(project, hazer, 1, discount_percent=Decimal("10")).line
        self.assertEqual(compute_project_prices(project).by_line_id[line.pk].amount, Decimal("95.00"))
        listed = self.admin.get(f"{API}/projects/{project.pk}/material-lines").json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        (data,) = [row for row in rows if row["id"] == line.pk]
        self.assertEqual(
            (data["price"]["max_discount_percent"], data["price"]["discount_is_capped"], data["price"]["amount"]),
            ("5.00", True, "95.00"),
        )


class StartDataTests(ApiTestCase):
    """ADM-011: the start data as the API lists it."""

    def test_units_and_scale(self) -> None:
        names = {row["name"] for row in self.admin.get(f"{API}/units").json()["results"]}
        self.assertTrue({"Stück (Miete)", "Stück (Verkauf)", "Angefangenes Kilogramm"} <= names)
        scale = RentalScale.objects.get(name="Standardstaffel")
        rows = self.admin.get(f"{API}/rental-scales/{scale.pk}").json()["current_version"]["rows"]
        self.assertEqual(
            [row["factor"] for row in rows], ["1.000", "1.500", "1.750", "2.000", "2.400", "2.750", "3.500"]
        )
