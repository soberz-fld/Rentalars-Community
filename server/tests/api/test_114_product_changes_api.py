# SPDX-License-Identifier: GPL-3.0-or-later
"""API: what products changed in projects that are not confirmed yet (PRJ-072, PRJ-137, PRJ-139)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.accounts.models import Role
from rentalars.projects.models import ProjectStatus
from rentalars.projects.services import update_line
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, add_line, make_project

D = Decimal


class ProjectProductChangesApiTests(ApiTestCase):
    """``/projects/{id}/product-changes``."""

    def setUp(self) -> None:
        super().setUp()
        from tests.unit.test_051_lines import flat

        self.project = make_project(status=ProjectStatus.OPTION)
        self.lamp = flat("L-010", "20.00", name="Lampe")
        self.line = add_line(self.project, self.lamp, 4).line
        self.hand = add_line(self.project, flat("L-020", "10.00", name="Kabel"), 1).line
        update_line(self.hand, rights=ALL_RIGHTS, title="Kabel für die Bühne")
        self.lamp.name = "Lampe LED"
        self.lamp.price = D("25.00")
        self.lamp.save()
        self.hand.product.name = "Kabel 5 m"
        self.hand.product.save()
        self.url = f"{API}/projects/{self.project.pk}/product-changes"

    def test_list_names_old_and_new_values(self) -> None:
        listing = self.admin.get(self.url).json()
        self.assertTrue(listing["shows_hint"])
        rows = {row["key"]: row for row in listing["lines"]}
        self.assertEqual(
            rows[f"m{self.line.pk}"],
            {
                "key": f"m{self.line.pk}",
                "kind": "material",
                "line": self.line.pk,
                "article_number": "L-010",
                "title": "Lampe",
                "set_by_hand": False,
                "changes": [{"field": "name", "old": "Lampe", "new": "Lampe LED", "by_hand": False}],
                "price": {"unit_price": "20.00", "list_price": "20.00", "new_price": "25.00", "set_by_hand": False},
            },
        )
        self.assertTrue(rows[f"m{self.hand.pk}"]["set_by_hand"])
        self.assertIsNone(rows[f"m{self.hand.pk}"]["price"])

    def test_take_over_automatic_keep_and_all(self) -> None:
        result = self.admin.post(self.url, {"take_over_all": "automatic"}, format="json").json()
        self.assertEqual((result["taken_over"], result["kept"]), (1, 0))
        self.assertEqual([row["key"] for row in result["lines"]], [f"m{self.hand.pk}"])
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe LED", D("25.00")))
        result = self.admin.post(self.url, {"keep": [f"m{self.hand.pk}"]}, format="json").json()
        self.assertEqual((result["kept"], result["lines"]), (1, []))
        self.hand.refresh_from_db()
        self.assertEqual(self.hand.title, "Kabel für die Bühne")
        self.hand.product.name = "Kabel 10 m"
        self.hand.product.save()
        result = self.admin.post(self.url, {"take_over_all": "all"}, format="json").json()
        self.assertEqual((result["taken_over"], result["lines"]), (1, []))
        self.hand.refresh_from_db()
        self.assertEqual(self.hand.title, "Kabel 10 m")

    def test_a_line_cannot_take_over_and_keep(self) -> None:
        key = f"m{self.line.pk}"
        response = self.admin.post(self.url, {"take_over": [key], "keep": [key]}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_confirmed_project_answers_on_request(self) -> None:
        self.project.status = ProjectStatus.CONFIRMED
        self.project.save()
        listing = self.admin.get(self.url).json()
        self.assertFalse(listing["shows_hint"])
        self.assertEqual(len(listing["lines"]), 2)

    def test_a_confirmed_project_keeps_what_was_agreed(self) -> None:
        """PRJ-015: the API does not take over new values or prices into a confirmed project."""
        self.project.status = ProjectStatus.CONFIRMED
        self.project.save()
        for body in ({"take_over_all": "all"}, {"take_over_all": "automatic"}, {"keep": [f"m{self.line.pk}"]}):
            self.assertEqual(self.admin.post(self.url, body, format="json").status_code, 400)
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe", D("20.00")))
        prices = self.admin.post(
            f"{API}/projects/{self.project.pk}/old-prices", {"take_over_all": "all"}, format="json"
        )
        self.assertEqual(prices.status_code, 400)
        self.line.refresh_from_db()
        self.assertEqual(self.line.unit_price, D("20.00"))

    def test_prices_only_with_the_price_right(self) -> None:
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.client_for("paul", "Planung ohne Preise")
        rows = {row["key"]: row for row in planner.get(self.url).json()["lines"]}
        self.assertIsNone(rows[f"m{self.line.pk}"]["price"])
        self.assertEqual(planner.post(self.url, {"take_over_all": "automatic"}, format="json").status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe LED", D("20.00")))

    def test_reading_is_not_enough_to_take_over(self) -> None:
        Role.objects.create(name="Nur lesen", module_levels={"projects": 1})
        reader = self.client_for("rita", "Nur lesen")
        self.assertEqual(reader.get(self.url).status_code, 200)
        self.assert_error(reader.post(self.url, {"take_over_all": "all"}, format="json"), 403, "permission_denied")


class ProductUnconfirmedProjectsApiTests(ApiTestCase):
    """``/products/{id}/unconfirmed-projects``."""

    def setUp(self) -> None:
        super().setUp()
        from tests.unit.test_051_lines import flat

        self.lamp = flat("L-010", "20.00", name="Lampe")
        self.first = make_project(status=ProjectStatus.INQUIRY)
        self.second = make_project("Zweites", status=ProjectStatus.OPTION)
        self.done = make_project("Bestätigt", status=ProjectStatus.CONFIRMED)
        self.lines = [add_line(project, self.lamp, 1).line for project in (self.first, self.second, self.done)]
        self.lamp.name = "Lampe LED"
        self.lamp.save()
        self.url = f"{API}/products/{self.lamp.pk}/unconfirmed-projects"

    def test_list_names_the_projects_not_confirmed_yet(self) -> None:
        listing = self.admin.get(self.url).json()
        self.assertEqual([entry["project"] for entry in listing["projects"]], [self.first.pk, self.second.pk])
        entry = listing["projects"][0]
        self.assertEqual((entry["number"], entry["status"], entry["can_edit"]), (self.first.number, "inquiry", True))
        self.assertEqual(entry["lines"][0]["changes"][0]["new"], "Lampe LED")

    def test_take_over_in_named_projects_or_in_all(self) -> None:
        result = self.admin.post(self.url, {"projects": [self.first.pk]}, format="json").json()
        self.assertEqual(result, {"lines": 1, "projects": 1})
        self.lines[0].refresh_from_db()
        self.lines[1].refresh_from_db()
        self.assertEqual((self.lines[0].title, self.lines[1].title), ("Lampe LED", "Lampe"))
        self.assertEqual(self.admin.post(self.url, {}, format="json").json(), {"lines": 1, "projects": 1})
        self.assertEqual(self.admin.get(self.url).json(), {"projects": []})
        self.lines[2].refresh_from_db()
        self.assertEqual(self.lines[2].title, "Lampe")  # confirmed: untouched

    def test_projects_the_caller_may_not_read_are_not_named(self) -> None:
        Role.objects.create(name="Nur Produkte", module_levels={"products": 2})
        clerk = self.client_for("petra", "Nur Produkte")
        self.assertEqual(clerk.get(self.url).json(), {"projects": []})
        self.assertEqual(clerk.post(self.url, {}, format="json").json(), {"lines": 0, "projects": 0})

    def test_reading_products_is_enough_to_look_but_not_to_take_over(self) -> None:
        Role.objects.create(name="Produkte lesen", module_levels={"products": 1, "projects": 2})
        reader = self.client_for("rita", "Produkte lesen")
        self.assertEqual(len(reader.get(self.url).json()["projects"]), 2)
        self.assert_error(reader.post(self.url, {}, format="json"), 403, "permission_denied")

    def test_a_project_known_only_by_its_overview_is_not_named(self) -> None:
        from rentalars.accounts.rights import ProjectScope
        from rentalars.projects.models import ProjectAccessLevel, ProjectMembership
        from tests.helpers import make_user

        Role.objects.create(
            name="Crew mit Produkten",
            module_levels={"projects": 1, "products": 2},
            special_rights=["prices"],
            project_scope=ProjectScope.DEPLOYMENT,
        )
        crew = make_user("carla", roles=("Crew mit Produkten",))
        ProjectMembership.objects.create(project=self.first, user=crew, level=ProjectAccessLevel.READ)
        client = self.client_of(crew)
        self.assertEqual(client.get(self.url).json(), {"projects": []})

    def test_unknown_product(self) -> None:
        self.assertEqual(self.admin.get(f"{API}/products/99999/unconfirmed-projects").status_code, 404)
