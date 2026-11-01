# SPDX-License-Identifier: GPL-3.0-or-later
"""Corrections found when trying the update with many data (MAT-086)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.masterdata.models import StorageLocation
from rentalars.material.models import AssetKind
from tests.api.base import API, ApiTestCase
from tests.helpers import make_item, make_model
from tests.ui.base import UiTestCase


class AssetRegisterQueriesTests(UiTestCase):
    """(update test; MAT-086) The register asks the database the same number of times for 3 or 60 items."""

    def count_queries(self) -> int:
        with CaptureQueriesContext(connection) as queries:
            self.assert_ok(self.client.get(reverse("material:asset_register")))
        return len(queries)

    def add_items(self, how_many: int, offset: int) -> None:
        model = make_model(f"Pult {offset}", category_code="T")
        for number in range(how_many):
            hall = StorageLocation.objects.create(name=f"Halle {offset}-{number}")
            shelf = StorageLocation.objects.create(name=f"Regal {number}", parent=hall)
            spot = StorageLocation.objects.create(name=f"Fach {number}", parent=shelf)
            item = make_item(
                model,
                offset + number,
                purchase_date=datetime.date(2026, 3, 17),
                purchase_price=Decimal("100.00"),
                asset_kind=AssetKind.FIXED_ASSET,
                useful_life_months=36,
                acquisition_cost_net=Decimal("100.00"),
            )
            item.storage_location = spot
            item.save()

    def test_the_paths_of_the_storage_locations_come_from_one_query(self) -> None:
        self.add_items(3, 1000)
        few = self.count_queries()
        self.add_items(57, 2000)
        many = self.count_queries()
        self.assertLessEqual(many, few + 1, f"{few} queries for 3 items, {many} for 60")


class PlanningApiQueriesTests(ApiTestCase):
    """(update test; PRD-052, PRJ-064, NFA-014) The planning of the API asks for the wished items once."""

    def plan(self, project, how_many: int, offset: int, *, wishing: bool) -> None:
        from rentalars.projects import services
        from tests.helpers import ALL_RIGHTS, add_line, make_product

        for number in range(how_many):
            product = make_product(f"T-{number + offset:03d}", price="10.00")
            model = make_model(f"Modell W{offset + number}", product, category_code="T")
            items = [make_item(model, 5000 + (offset + number) * 10 + step) for step in range(3)]
            result = add_line(project, product, 3)
            if wishing:
                services.update_line(result.line, rights=ALL_RIGHTS, preferred_items=items)

    def count(self, project) -> int:
        with CaptureQueriesContext(connection) as queries:
            response = self.admin.get(f"{API}/projects/{project.pk}/planning")
        self.assertEqual(response.status_code, 200)
        return len(queries)

    def test_the_queries_do_not_grow_with_the_lines(self) -> None:
        from tests.helpers import make_project

        project = make_project("Stadtfest")
        self.plan(project, 3, 501, wishing=True)
        few = self.count(project)
        self.plan(project, 12, 601, wishing=False)
        self.plan(project, 12, 701, wishing=True)
        many = self.count(project)
        self.assertLessEqual(many, few + 2, f"{few} queries for 3 lines, {many} for 27")
