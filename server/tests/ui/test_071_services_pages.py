# SPDX-License-Identifier: GPL-3.0-or-later
"""In the pages, area "services": job functions and their service products (PRD-044, PER-037), incidental
costs (PRD-045), hour tiers per day (PER-035)."""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.personnel import services as personnel
from rentalars.personnel.models import JobFunction, PersonJobFunction
from rentalars.products.models import Product
from rentalars.projects.models import CrewBilling, CrewLine
from tests.helpers import add_line_before_071, at, job_function, make_person, make_product, make_project, plan
from tests.ui.base import UiTestCase, form_data

D = Decimal


class JobFunctionPagesTests(UiTestCase):
    """PRD-044, PER-037: the list links the service product; the form creates it and points to it."""

    def test_the_list_links_the_service_product(self) -> None:
        page = self.assert_ok(self.client.get(reverse("personnel:job_function_list")))
        product = JobFunction.objects.get(name="Lichttechniker").service_product
        self.assertIn(f'href="{reverse("products:detail", args=[product.pk])}"', page)
        self.assertIn("noch kein Preis", page)
        # Personnel planning reads no products: the product is named, not linked.
        planner = self.browser_for("pia", "Personaldisposition")
        page = self.assert_ok(planner.get(reverse("personnel:job_function_list")))
        self.assertIn(product.article_number, page)
        self.assertNotIn(f'href="{reverse("products:detail", args=[product.pk])}"', page)

    def test_a_new_function_with_its_price(self) -> None:
        url = reverse("personnel:job_function_create")
        form = self.client.get(url)
        page = self.assert_ok(form)
        self.assertIn("Preis je Stunde für den Kunden", page)
        self.assertNotIn('name="service_product"', page)
        response = self.client.post(url, form_data(form, name="Pyrotechnik", price="60.00"), follow=True)
        function = JobFunction.objects.get(name="Pyrotechnik")
        self.assertEqual((function.service_product.name, function.service_product.price), ("Pyrotechnik", D("60.00")))
        self.assertIn(
            f"Funktion gespeichert, mit ihrem Dienstleistungsprodukt {function.service_product.article_number} "
            "Pyrotechnik.",
            self.messages_of(response),
        )

    def test_the_form_of_a_function_points_to_its_product(self) -> None:
        function = job_function("Tontechnik", price="45.00")
        url = reverse("personnel:job_function_edit", args=[function.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn(reverse("products:detail", args=[function.service_product_id]), page)
        self.assertIn("45,00", page)
        self.assertNotIn('name="price"', page)  # the price is kept on the product
        response = self.client.post(url, form_data(self.client.get(url), name="Tontechnik FOH"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(pk=function.service_product_id).name, "Tontechnik, Stunde")

    def test_deleting_the_function_deletes_its_product(self) -> None:
        function = personnel.save_job_function(JobFunction(name="Pyrotechnik"))
        self.client.post(reverse("personnel:job_function_delete", args=[function.pk]))
        self.assertFalse(Product.objects.filter(pk=function.service_product_id).exists())

    def test_the_rate_from_the_limit_of_a_person(self) -> None:
        anna = make_person("Anna Becker")
        function = job_function("Tontechnik", price="45.00")
        detail = reverse("personnel:person_detail", args=[anna.pk])
        page = self.client.get(detail)
        self.assertIn("Stundensatz ab der Grenze", self.assert_ok(page))
        self.client.post(
            reverse("personnel:rate_set", args=[anna.pk]),
            form_data(
                page,
                containing="hourly_rate_above_limit",
                job_function=function.pk,
                hourly_rate="35.00",
                hourly_rate_above_limit="42.00",
            ),
        )
        row = PersonJobFunction.objects.get(person=anna, job_function=function)
        self.assertEqual((row.hourly_rate, row.hourly_rate_above_limit), (D("35.00"), D("42.00")))
        self.assertIn("42,00", self.assert_ok(self.client.get(detail)))


class ProductPagesTests(UiTestCase):
    """PRD-044, PRD-045, PER-035 on the product pages."""

    def test_a_service_names_its_function_and_cannot_be_deleted_alone(self) -> None:
        function = JobFunction.objects.get(name="Stagehand")
        detail = reverse("products:detail", args=[function.service_product_id])
        page = self.assert_ok(self.client.get(detail))
        self.assertIn(reverse("personnel:job_function_edit", args=[function.pk]), page)
        response = self.client.post(reverse("products:delete", args=[function.service_product_id]), follow=True)
        self.assertTrue(Product.objects.filter(pk=function.service_product_id).exists())
        self.assertTrue(any("Funktion Stagehand" in text for text in self.messages_of(response)))

    def test_the_form_of_a_service_with_hour_tiers(self) -> None:
        product = JobFunction.objects.get(name="Tontechniker").service_product
        url = reverse("products:edit", args=[product.pk])
        form = self.client.get(url)
        page = self.assert_ok(form)
        self.assertIn('data-show-if="kind=service"', page)
        self.assertIn("gehört zur Funktion Tontechniker", page)
        response = self.client.post(url, form_data(form, price="45.00", hours_limit="10", price_above_limit="55.00"))
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        product.refresh_from_db()
        self.assertEqual((product.hours_limit, product.price_above_limit), (D("10.00"), D("55.00")))
        self.assertIn(
            "ab 10 Std. am Tag: 55,00", self.assert_ok(self.client.get(reverse("products:detail", args=[product.pk])))
        )

    def test_a_new_service_creates_its_function(self) -> None:
        url = reverse("products:create")
        form = self.client.get(url, {"kind": "service"})
        category = JobFunction.objects.get(name="Lager").service_product.category
        data = form_data(form, kind="service", category=category.pk, article_number="D-020", name="Bühnenmeister")
        tax_rate = JobFunction.objects.get(name="Lager").service_product.tax_rate_id
        data.update(price="50.00", billing_mode="hourly", unit=category.default_unit_id, tax_rate=tax_rate)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        self.assertEqual(JobFunction.objects.get(name="Bühnenmeister").service_product.article_number, "D-020")


class PlanningPagesTests(UiTestCase):
    """PRD-044 and PER-035 on the planning page and in the price overview."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.function = job_function("Tontechnik", price="45.00")
        product = self.function.service_product
        product.hours_limit, product.price_above_limit = D("10"), D("55.00")
        product.save()

    def test_the_search_leaves_services_out_and_adding_one_is_refused(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("exclude_kind=service", page)
        response = self.htmx(
            "post",
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": str(self.function.service_product_id), "quantity": "2"},
        )
        self.assertIn("Personal", self.assert_ok(response))
        self.assertFalse(self.project.material_lines.exists())

    def test_an_old_line_of_a_service_has_a_hint(self) -> None:
        add_line_before_071(self.project, self.function.service_product, 2)
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("data-service-line", page)
        self.assertIn("Dienstleistung – unter Personal planen", page)

    def test_the_crew_line_shows_its_product_and_the_hours_beyond_the_limit(self) -> None:
        line = plan(self.project, self.function, start=at(10, 8), end=at(10, 20), billing=CrewBilling.PLAN)
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn(reverse("products:detail", args=[self.function.service_product_id]), page)
        self.assertIn("ab 10 Std. am Tag: 55,00", page)
        self.assertIn("davon 2 Std. über der Grenze", page)
        self.assertIn("560,00", page)
        prices = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        self.assertIn("2 Std. über 10 Std. am Tag zu 55,00", prices)
        # The dialog of the line offers the tiers with the price right.
        dialog = self.assert_ok(self.htmx("get", reverse("projects:crew_edit", args=[self.project.pk, line.pk])))
        for name in ("hours_limit", "unit_price_above_limit", "hourly_rate_above_limit"):
            self.assertIn(f'name="{name}"', dialog)
        self.assertEqual(CrewLine.objects.get(pk=line.pk).hours_limit, D("10"))

    def test_the_offer_splits_the_hours(self) -> None:
        from rentalars.documents.content import priced_sections

        plan(self.project, self.function, start=at(10, 8), end=at(10, 20), billing=CrewBilling.PLAN)
        sections, _prices = priced_sections(self.project)
        crew = next(section for section in sections if section.title == "Personal")
        self.assertIn("davon 2 Std. über 10 Std. am Tag zu 55,00 €", crew.positions[0].details)
        self.assertEqual(crew.positions[0].amount, D("560.00"))

    def test_incidental_costs_are_offered_and_planned(self) -> None:
        transport = make_product("N-001", "Transport Sprinter", price="95.00", kind="incidental", billing_mode="flat")
        response = self.htmx(
            "post",
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": str(transport.pk), "quantity": "1"},
        )
        self.assert_ok(response)
        self.assertEqual(self.project.material_lines.get().product, transport)
