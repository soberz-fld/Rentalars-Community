# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "services": job functions with their service products (PRD-044), incidental costs
(PRD-045), hour tiers per day (PER-035), crew lines by effort (PER-036) (API-014)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.personnel import services as personnel
from rentalars.personnel.models import JobFunction
from rentalars.products.models import Product
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line_before_071, at, job_function, make_person, make_product, make_project, plan

D = Decimal


class JobFunctionApiTests(ApiTestCase):
    """``/job-functions``: the service product comes with the function (PRD-044)."""

    def test_create_with_price_rename_and_delete(self) -> None:
        created = self.admin.post(f"{API}/job-functions", {"name": "Pyrotechnik", "price": "60.00"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        product = Product.objects.get(pk=created.data["service_product"])
        self.assertEqual((product.name, product.price, product.kind), ("Pyrotechnik", D("60.00"), "service"))
        self.assertEqual(created.data["service_product_article_number"], product.article_number)
        self.assertNotIn("price", created.data)  # only sent, never delivered

        url = f"{API}/job-functions/{created.data['id']}"
        renamed = self.admin.patch(url, {"name": "Pyrotechnik und SFX"}, format="json")
        self.assertEqual(renamed.status_code, 200, renamed.data)
        self.assertEqual(Product.objects.get(pk=product.pk).name, "Pyrotechnik und SFX")

        self.assertEqual(self.admin.delete(url).status_code, 204)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_another_service_product_or_a_later_price_is_refused(self) -> None:
        function = JobFunction.objects.get(name="Stagehand")
        other = JobFunction.objects.get(name="Lager").service_product
        url = f"{API}/job-functions/{function.pk}"
        self.assert_error(
            self.admin.patch(url, {"service_product": other.pk}, format="json"),
            400,
            "validation_error",
            "service_product",
        )
        self.assert_error(self.admin.patch(url, {"price": "30.00"}, format="json"), 400, "validation_error", "price")
        same = self.admin.patch(url, {"service_product": function.service_product_id, "is_active": True}, format="json")
        self.assertEqual(same.status_code, 200, same.data)

    def test_the_price_needs_the_price_right_and_the_guide_value_from_the_limit_the_cost_right(self) -> None:
        planner = self.client_for("pia", "Personaldisposition")  # personnel costs, no prices
        refused = planner.post(f"{API}/job-functions", {"name": "Pyrotechnik", "price": "60.00"}, format="json")
        self.assert_error(refused, 400, "validation_error", "price")
        created = planner.post(
            f"{API}/job-functions", {"name": "Pyrotechnik", "guide_cost_rate_above_limit": "40.00"}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["guide_cost_rate_above_limit"], "40.00")
        self.assertIsNone(Product.objects.get(pk=created.data["service_product"]).price)

    def test_a_used_function_is_not_deleted(self) -> None:
        function = job_function("Tontechnik", price="45.00")
        plan(make_project(), function)
        response = self.admin.delete(f"{API}/job-functions/{function.pk}")
        self.assert_error(response, 400, "validation_error")
        self.assertTrue(Product.objects.filter(pk=function.service_product_id).exists())


class ProductApiTests(ApiTestCase):
    """``/products``: services bring their function (PRD-044), incidental costs (PRD-045), hour tiers (PER-035)."""

    def test_a_service_brings_its_function_and_tiers(self) -> None:
        category = Product.objects.get(article_number="D-001").category
        created = self.admin.post(
            f"{API}/products",
            {
                "article_number": "D-020",
                "category": category.pk,
                "name": "Bühnenmeister",
                "unit": category.default_unit_id,
                "tax_rate": Product.objects.get(article_number="D-001").tax_rate_id,
                "kind": "service",
                "billing_mode": "hourly",
                "price": "50.00",
                "hours_limit": "10.00",
                "price_above_limit": "62.50",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        function = JobFunction.objects.get(name="Bühnenmeister")
        self.assertEqual(created.data["job_function"], {"id": function.pk, "name": "Bühnenmeister"})
        self.assertEqual((created.data["hours_limit"], created.data["price_above_limit"]), ("10.00", "62.50"))
        listed = self.admin.get(f"{API}/products", {"kind": "service"}).json()
        self.assertIn("Bühnenmeister", [row["job_function"]["name"] for row in listed["results"]])

    def test_a_service_cannot_be_deleted_without_its_function(self) -> None:
        product = JobFunction.objects.get(name="Stagehand").service_product
        self.assert_error(self.admin.delete(f"{API}/products/{product.pk}"), 400, "validation_error")

    def test_incidental_costs_and_a_limit_only_for_services(self) -> None:
        transport = make_product("N-001", "Transport", price="95.00", kind="incidental", billing_mode="flat")
        response = self.admin.patch(
            f"{API}/products/{transport.pk}", {"hours_limit": "10", "price_above_limit": "1"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "hours_limit")
        self.assertEqual(self.admin.get(f"{API}/products/{transport.pk}").data["job_function"], None)


class MaterialLineApiTests(ApiTestCase):
    """PRD-044: ``/projects/{id}/material-lines`` refuses services; incidental costs are planned like material."""

    def test_a_service_is_refused_incidental_costs_are_planned(self) -> None:
        project = make_project()
        engineer = job_function("Tontechnik", price="45.00").service_product
        url = f"{API}/projects/{project.pk}/material-lines"
        refused = self.admin.post(url, {"product": engineer.pk, "quantity": "2"}, format="json")
        error = self.assert_error(refused, 400, "validation_error", "product")
        self.assertIn("Tontechnik", error["fields"]["product"][0]["message"])
        transport = make_product("N-001", "Transport", price="95.00", kind="incidental", billing_mode="flat")
        added = self.admin.post(url, {"product": transport.pk, "quantity": "1"}, format="json")
        self.assertEqual(added.status_code, 201, added.data)

    def test_an_old_line_of_a_service_cannot_be_duplicated(self) -> None:
        project = make_project()
        line = add_line_before_071(project, job_function("Tontechnik", price="45.00").service_product, 2).line
        response = self.admin.post(f"{API}/projects/{project.pk}/material-lines/{line.pk}/duplicate", {}, format="json")
        self.assert_error(response, 400, "validation_error")


class CrewLineTierApiTests(ApiTestCase):
    """PER-035, PER-036: ``/projects/{id}/crew-lines`` with the hour tiers and billing by effort."""

    def setUp(self) -> None:
        super().setUp()
        self.function = job_function("Tontechnik", price="45.00", guide="30.00")
        product = self.function.service_product
        product.hours_limit, product.price_above_limit = D("10"), D("55.00")
        product.save()
        self.anna = make_person("Anna Becker")
        personnel.set_rate(self.anna, self.function, D("35.00"), hourly_rate_above_limit=D("42.00"))
        self.project = make_project()
        self.base = f"{API}/projects/{self.project.pk}/crew-lines"

    def test_plan_with_the_tiers_of_the_product(self) -> None:
        created = self.admin.post(
            self.base,
            {"job_function": self.function.pk, "person": self.anna.pk, "start": at(10, 8), "end": at(10, 20)},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        line = created.data[0]
        self.assertEqual(line["billing"], "effort")  # PER-036
        self.assertEqual(line["service_product_article_number"], self.function.service_product.article_number)
        self.assertEqual((line["hours_limit"], line["unit_price_above_limit"]), (D("10.00"), D("55.00")))
        self.assertEqual(
            (line["normal_hours"], line["hours_above_limit"], line["amount"]), (D("10"), D("2"), D("560.00"))
        )
        self.assertEqual((line["hourly_rate_above_limit"], line["cost"]), (D("42.00"), D("434.00")))
        self.assertEqual((line["cost_hours_above_limit"], line["cost_rate_above_limit"]), (D("2"), D("42.00")))

        overview = self.admin.get(f"{API}/projects/{self.project.pk}/price-overview").json()
        row = overview["personnel"]["lines"][0]
        self.assertEqual((row["hours_above_limit"], row["unit_price_above_limit"]), ("2.00", "55.00"))

    def test_the_tiers_need_the_price_right_the_rate_the_cost_right(self) -> None:
        planner = self.client_for("pia", "Personaldisposition")
        payload = {"job_function": self.function.pk, "unit_price_above_limit": "60.00"}
        self.assertEqual(planner.post(self.base, payload, format="json").status_code, 400)
        line = plan(self.project, self.function, self.anna)
        response = planner.patch(f"{self.base}/{line.pk}", {"hourly_rate_above_limit": "50.00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("hours_above_limit", response.data)  # prices: not for personnel planning
        self.assertEqual(response.data["hourly_rate_above_limit"], D("50.00"))

    def test_the_rate_from_the_limit_of_a_person(self) -> None:
        url = f"{API}/people/{self.anna.pk}/job-functions"
        response = self.admin.post(
            url,
            {"job_function": self.function.pk, "hourly_rate": "36.00", "hourly_rate_above_limit": "44.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data[0]["hourly_rate_above_limit"], D("44.00"))
