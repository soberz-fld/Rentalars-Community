# SPDX-License-Identifier: GPL-3.0-or-later
"""MAT-058: what the items of a material model earned – on the model's page and over the API.

The figures of an item's box "Ertrag" (MAT-053), added up for all items of
the model and listed item by item; an item bought in a set (MAT-054) counts
with its share of the set's price.
"""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.material.models import MaterialItem
from rentalars.projects import profitability
from rentalars.projects.list_sums import _prices_of
from rentalars.projects.models import Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, add_line, make_project, make_stock
from tests.ui.base import UiTestCase


class ModelCase(RentalarsTestCase):
    """Three cables S-100 of one model, all out in the Stadtfest; 0001 bought for 90 € with 0002 in its price."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_stock("S-100", 3)
        self.first, self.second, self.third = MaterialItem.objects.order_by("inventory_number")
        self.model = self.first.material_model
        MaterialItem.objects.filter(pk=self.first.pk).update(purchase_price=Decimal("90.00"))
        MaterialItem.objects.filter(pk=self.second.pk).update(purchase_price_in=self.first)
        MaterialItem.objects.filter(pk=self.third.pk).update(purchase_price=Decimal("30.00"))
        self.project = make_project("Stadtfest")
        add_line(self.project, self.product, 3)
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.project.refresh_from_db()
        self.net = _prices_of([self.project])[self.project.pk][0].net_total


class ModelRevenueTests(ModelCase):
    def test_added_up_and_item_by_item(self) -> None:
        revenue = profitability.model_revenue(self.model)
        self.assertEqual(revenue.total, self.net)
        self.assertEqual(revenue.direct, 0)
        self.assertEqual(revenue.projects, 1)
        self.assertEqual(len(revenue.items), 3)
        # The set of 0001 and 0002 cost 90 € – 45 € each; 0003 cost 30 €.
        prices = {row.item.pk: row.purchase_price for row in revenue.items}
        self.assertEqual(prices, {self.first.pk: Decimal("45.00"), self.second.pk: Decimal("45.00"), self.third.pk: 30})
        self.assertEqual(revenue.purchase_total, Decimal("120.00"))
        self.assertEqual(revenue.share_percent, (self.net * 100 / 120).quantize(Decimal("0.1")))

    def test_without_prices(self) -> None:
        MaterialItem.objects.update(purchase_price=None, purchase_price_in=None)
        revenue = profitability.model_revenue(self.model)
        self.assertIsNone(revenue.purchase_total)
        self.assertIsNone(revenue.share_percent)


class ModelRevenuePageTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        make_stock("S-100", 2)
        self.model = MaterialItem.objects.first().material_model

    def test_the_box_on_the_model_page(self) -> None:
        url = reverse("projects:model_revenue", args=[self.model.pk])
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assertIn(url, detail)
        part = self.assert_ok(self.client.get(url))
        self.assertIn("Kalkuliert mit den Exemplaren dieses Modells eingenommen", part)
        self.assertIn("Kaufpreise zusammen (netto)", part)

    def test_only_for_who_may_see_the_reports(self) -> None:
        Role.objects.create(
            name="Lager mit Preisen",
            module_levels={"material": 1, "projects": 1, "reports": 0},
            special_rights=["prices", "purchase_prices"],
        )
        browser = self.browser_for("luka", "Lager mit Preisen")
        url = reverse("projects:model_revenue", args=[self.model.pk])
        self.assertEqual(browser.get(url).status_code, 403)
        self.assertNotIn(url, self.assert_ok(browser.get(reverse("material:model_detail", args=[self.model.pk]))))


class ModelRevenueApiTests(ApiTestCase):
    def test_get_the_revenue_of_a_model(self) -> None:
        make_stock("S-100", 2)
        model = MaterialItem.objects.first().material_model
        response = self.admin.get(f"{API}/material-models/{model.pk}/revenue")
        self.assertEqual(response.status_code, 200, response.data)
        data = response.json()
        self.assertEqual((data["material_model"], data["total"], len(data["items"])), (model.pk, "0.00", 2))
        self.assertIn("purchase_total", data)
        crew = self.client_for("kai", "Crew")
        self.assertEqual(crew.get(f"{API}/material-models/{model.pk}/revenue").status_code, 403)
