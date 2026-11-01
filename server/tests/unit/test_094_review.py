# SPDX-License-Identifier: GPL-3.0-or-later
"""What the independent review found (see docs/dev/decisions.md, Part 26).

* Splitting a project keeps the overall discount (PRJ-123): a percentage in every part, an amount shared in proportion.
* The role migration also finds the start roles of an English installation (AUT-036).
* The API changes a project with its overall discount or not at all (PRJ-123).
* The mass inspection survives odd IDs, builds the plan once, shows the test device after an error (MAT-082).
* The after-calculation shares the overall discount over material, personnel and logistics (PRJ-123).
* The packing list shows the spot of the outermost container (MAT-080); a bare number searches IDs, not spots.
* A copy without material, crew and logistics gets no discount (PRJ-123).
"""

from __future__ import annotations

import importlib
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.material import services
from rentalars.material.models import MaterialItem
from rentalars.projects import profitability
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.family_prices import family_prices
from rentalars.projects.split import split_into_subprojects
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_item,
    make_items,
    make_model,
    make_product,
    make_project,
)
from tests.ui.base import UiTestCase
from tests.unit.test_093_dguv import TODAY, setup_dguv

MIGRATION = importlib.import_module("rentalars.accounts.migrations.0009_role_defaults_094")


def two_groups(**fields: object):
    """100,00 in "Bühne A", 50,00 in "Bühne B", flat prices: net 150,00 before any discount."""
    project = make_project(rental_days=1, **fields)
    first, second = add_group(project, "Bühne A"), add_group(project, "Bühne B")
    add_line(project, make_product("L-001", price="100.00", billing_mode="flat"), 1, group=first)
    add_line(project, make_product("L-002", price="50.00", billing_mode="flat"), 1, group=second)
    return project, first, second


class SplitTests(RentalarsTestCase):
    def test_a_percentage_goes_to_every_part_and_no_price_changes(self) -> None:
        project, first, second = two_groups(overall_discount_percent=Decimal("10"))
        before = family_prices(project).totals.net_total
        self.assertEqual(before, Decimal("135.00"))
        parts = split_into_subprojects(project, [first.pk, second.pk]).parts
        project.refresh_from_db()
        self.assertEqual([part.overall_discount_percent for part in parts], [Decimal("10.00"), Decimal("10.00")])
        self.assertEqual(family_prices(project).totals.net_total, before)

    def test_an_amount_is_shared_in_proportion_and_no_price_changes(self) -> None:
        project, first, second = two_groups(overall_discount_amount=Decimal("15"))
        before = family_prices(project).totals.net_total
        self.assertEqual(before, Decimal("135.00"))
        parts = split_into_subprojects(project, [first.pk, second.pk]).parts
        project.refresh_from_db()
        self.assertEqual([part.overall_discount_amount for part in parts], [Decimal("10.00"), Decimal("5.00")])
        self.assertIsNone(project.overall_discount_amount)  # nothing left for the whole project
        self.assertEqual(family_prices(project).totals.net_total, before)

    def test_the_cents_that_do_not_divide_stay_with_the_whole_project(self) -> None:
        project, first, second = two_groups(overall_discount_amount=Decimal("10.00"))
        parts = split_into_subprojects(project, [first.pk, second.pk]).parts
        project.refresh_from_db()
        shared = sum((part.overall_discount_amount or Decimal("0") for part in parts), Decimal("0")) + (
            project.overall_discount_amount or Decimal("0")
        )
        self.assertEqual(shared, Decimal("10.00"))

    def test_no_discount_stays_none(self) -> None:
        project, first, _second = two_groups()
        parts = split_into_subprojects(project, [first.pk]).parts
        self.assertEqual([(p.overall_discount_percent, p.overall_discount_amount) for p in parts], [(None, None)])


class EnglishRolesTests(RentalarsTestCase):
    """AUT-036: the start roles of an English installation have English names."""

    def test_the_roles_are_found_by_their_english_names(self) -> None:
        MIGRATION.back_to_093(apps, None)
        Role.objects.filter(name="Lager").update(name="Warehouse")
        Role.objects.filter(name="Projektleitung").update(name="Project management")
        Role.objects.filter(name="Freie Kraft").update(
            name="Freelancer", description="Restricted account: own deployments and times, no prices"
        )
        MIGRATION.update_roles(apps, None)
        warehouse = Role.objects.get(name="Warehouse")
        self.assertEqual(warehouse.module_levels["material"], 2)
        self.assertIn("correspondence_read", warehouse.special_rights)
        self.assertEqual(Role.objects.get(name="Project management").module_levels["projects"], 2)
        freelancer = Role.objects.get(name="Freelancer")
        self.assertEqual((freelancer.special_rights, freelancer.project_scope), ([], "deployment"))
        self.assertEqual(
            freelancer.description, "Only the essentials: own deployments and time recording, no project information"
        )

    def test_going_back_finds_them_too(self) -> None:
        Role.objects.filter(name="Lager").update(name="Warehouse")
        MIGRATION.back_to_093(apps, None)
        self.assertEqual(Role.objects.get(name="Warehouse").module_levels["material"], 3)


class ApiUpdateTests(ApiTestCase):
    def test_a_refused_discount_leaves_the_rest_unchanged(self) -> None:
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2}, special_rights=[])
        client = self.client_for("pp", "Planung ohne Preise")
        project = make_project(name="Alt")
        response = client.patch(
            f"{API}/projects/{project.pk}", {"name": "Neu", "overall_discount_percent": "5"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        project.refresh_from_db()
        self.assertEqual(project.name, "Alt")

    def test_both_kinds_at_once_change_nothing(self) -> None:
        project = make_project(name="Alt")
        response = self.admin.patch(
            f"{API}/projects/{project.pk}",
            {"name": "Neu", "overall_discount_percent": "5", "overall_discount_amount": "10"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        project.refresh_from_db()
        self.assertEqual(project.name, "Alt")

    def test_the_discount_is_judged_by_changed_at(self) -> None:
        from rentalars.projects.field_changes import KEY_OF

        self.assertEqual(KEY_OF["overall_discount_percent"], KEY_OF["overall_discount_amount"])


class BatchRobustnessTests(ApiTestCase):
    def body(self, **changes: object) -> dict[str, object]:
        body = {
            "inspection_type": self.visual.pk,
            "date": TODAY.isoformat(),
            "inspector": "E",
            "items": [{"item": self.cable.pk, "result": "passed"}],
        }
        body.update(changes)
        return body

    def test_ids_beyond_the_database_are_a_400_not_a_500(self) -> None:
        setup_dguv(self)
        url = f"{API}/material-items/inspections/batch"
        for body in (
            self.body(items=[{"item": 2**70, "result": "passed"}]),
            self.body(inspection_type=2**70),
            self.body(items=[{"item": 0, "result": "passed"}]),
        ):
            self.assertEqual(self.admin.post(url, body, format="json").status_code, 400)

    def test_too_many_items_are_refused_before_anything_is_looked_up(self) -> None:
        setup_dguv(self)
        items = [{"item": 1 + i, "result": "passed"} for i in range(services.MAX_BULK_ITEMS + 1)]
        response = self.admin.post(f"{API}/material-items/inspections/batch", self.body(items=items), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("items", str(response.json()))


class BatchPageTests(UiTestCase):
    def test_odd_digits_and_huge_numbers_are_ignored(self) -> None:
        setup_dguv(self)
        url = reverse("material:inspection_batch")
        response = self.client.post(url, {"items": ["²", "9" * 30, str(self.cable.pk)]})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url, {"items": ["²", "9" * 30]})
        self.assertEqual(response.status_code, 302)  # nothing valid chosen: back to the list

    def test_the_plan_is_built_once_for_the_whole_batch(self) -> None:
        setup_dguv(self)
        items = [self.cable] + [make_item(self.cable_model, 100 + i) for i in range(20)]
        entries = [services.BatchEntry(item=item, result="passed") for item in items]
        with CaptureQueriesContext(connection) as queries:
            services.record_inspections(entries, self.visual, date=TODAY, inspector="E")
        self.assertLess(len(queries) / len(items), 8)

    def test_the_test_device_stays_visible_after_an_error(self) -> None:
        setup_dguv(self)
        response = self.client.post(
            reverse("material:inspection_batch"),
            {
                "items": [str(self.cable.pk)],
                "save": "1",
                "inspection_type": str(self.electric.pk),
                "date": TODAY.isoformat(),
                "inspector": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].preselected_electrical)


class ProfitabilityTests(RentalarsTestCase):
    def test_the_overall_discount_is_shared_over_the_three_kinds(self) -> None:
        project = make_project()
        prices = SimpleNamespace(
            net_total=Decimal("480.00"),
            net_before_overall_discount=Decimal("600.00"),
            overall_discount=Decimal("120.00"),
            personnel_total=Decimal("500.00"),
            logistics_total=Decimal("0.00"),
            subrental_cost=Decimal("0"),
            personnel_cost=Decimal("0"),
            expenses_cost=Decimal("0"),
            logistics_cost=Decimal("0"),
        )
        with mock.patch.object(profitability, "_calculate", return_value={project.pk: prices}):
            figures = profitability.figures_of([project])[project.pk]
        self.assertEqual(figures.personnel_revenue, Decimal("400.00"))
        self.assertEqual(figures.material_revenue, Decimal("80.00"))
        self.assertEqual(figures.material_revenue + figures.personnel_revenue, Decimal("480.00"))


class SpotTests(UiTestCase):
    def test_the_packing_list_shows_the_spot_of_the_container(self) -> None:
        from rentalars.packing import services as packing

        product = make_product("L-010", "PAR 64")
        items = make_items(make_model("PAR 64", product, category_code="L"), 2)
        container = make_item(make_model("Case", make_product("L-020", "Case"), category_code="L"), 50)
        MaterialItem.objects.filter(pk=container.pk).update(storage_spot="04-B-2")
        project = make_project()
        line = add_line(project, product, 1).line
        packlist = packing.get_packlist(project)
        packing.choose_items(packlist, line.pk, product.pk, [items[0].pk])
        MaterialItem.objects.filter(pk=items[0].pk).update(installed_in=container.pk, storage_spot="01-A-1")
        row = packing.build_overview(packlist).rows[0]
        self.assertEqual([chosen.spot for chosen in row.chosen], ["04-B-2"])

    def test_a_number_alone_finds_the_item_not_a_spot(self) -> None:
        from rentalars.material.filters import search_items

        model = make_model("PAR 64", make_product("L-010", "PAR 64"), category_code="L")
        first, second = make_item(model, 1), make_item(model, 42)
        MaterialItem.objects.filter(pk=first.pk).update(storage_spot="42-B-3")
        self.assertEqual(list(search_items(MaterialItem.objects.all(), "42")), [second])

    def test_a_spot_with_letters_is_still_found(self) -> None:
        from rentalars.material.filters import search_items

        model = make_model("PAR 64", make_product("L-010", "PAR 64"), category_code="L")
        item = make_item(model, 3)
        MaterialItem.objects.filter(pk=item.pk).update(storage_spot="03-A-2")
        self.assertEqual(list(search_items(MaterialItem.objects.all(), "3a2")), [item])


class DuplicateTests(RentalarsTestCase):
    def test_a_copy_without_anything_to_sum_up_has_no_discount(self) -> None:
        source, _first, _second = two_groups(overall_discount_percent=Decimal("10"))
        copy = duplicate_project(
            source,
            start=at(20),
            end=at(22),
            name="Leer",
            rights=ALL_RIGHTS,
            user=None,
            with_material=False,
            with_crew=False,
            with_logistics=False,
        )
        self.assertIsNone(copy.overall_discount_percent)
