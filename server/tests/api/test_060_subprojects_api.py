# SPDX-License-Identifier: GPL-3.0-or-later
"""The API for whole projects and their parts (PRJ-044 to PRJ-049, PRJ-060)."""

from __future__ import annotations

from rentalars.projects import services
from rentalars.projects.models import MaterialLine, Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, at, make_customer, make_project, make_stock


class SubprojectApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadt Musterstadt")
        self.whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=self.customer)

    def create_part(self, **values: object) -> object:
        body = {"name": "Bühne Marktplatz", "parent": self.whole.pk, "start": at(10, 8), "end": at(12, 8), **values}
        return self.admin.post(f"{API}/projects", body, format="json")

    def test_create_a_part_with_the_customer_of_the_whole_project(self) -> None:
        other = make_customer("Andere GmbH")
        response = self.create_part(customer=other.pk)
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["parent"], self.whole.pk)
        self.assertEqual(data["customer"], self.customer.pk)
        self.assertEqual(data["number"], f"{self.whole.number}-1")
        whole = self.admin.get(f"{API}/projects/{self.whole.pk}").json()
        self.assertEqual(whole["subprojects"], [data["id"]])
        listed = self.admin.get(f"{API}/projects", {"parent": self.whole.pk}).json()["results"]
        self.assertEqual([row["id"] for row in listed], [data["id"]])

    def test_a_part_outside_the_period_is_refused(self) -> None:
        self.assert_error(self.create_part(start=at(1, 8), end=at(2, 8)), 400, "validation_error", "start")

    def test_a_part_cannot_move_to_another_whole_project(self) -> None:
        part = Project.objects.get(pk=self.create_part().json()["id"])
        other = make_project("Anderes Fest", start=at(1, 12), end=at(20, 12), customer=self.customer)
        response = self.admin.patch(f"{API}/projects/{part.pk}", {"parent": other.pk}, format="json")
        self.assert_error(response, 400, "validation_error", "parent")

    def test_status_with_the_parts(self) -> None:
        part = Project.objects.get(pk=self.create_part().json()["id"])
        response = self.admin.post(
            f"{API}/projects/{self.whole.pk}/status", {"status": "out", "with_subprojects": True}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        part.refresh_from_db()
        self.assertEqual(part.status, ProjectStatus.OUT)

    def test_family_figures(self) -> None:
        part = Project.objects.get(pk=self.create_part().json()["id"])
        add_line(part, make_stock("L-100", 2, "Spot"), 3)
        data = self.admin.get(f"{API}/projects/{part.pk}/family").json()
        self.assertEqual(data["whole"], self.whole.pk)
        self.assertEqual([row["project"] for row in data["parts"]], [self.whole.pk, part.pk])
        self.assertEqual(data["total"]["pieces"], "3.00")
        self.assertEqual(data["total"]["shortage"], 1)
        self.assertIn("net_total", data["total"])
        crew = self.client_for("carla", "Lager")
        self.assertNotIn("net_total", crew.get(f"{API}/projects/{part.pk}/family").json()["total"])

    def test_no_access_only_in_a_part(self) -> None:
        part = Project.objects.get(pk=self.create_part().json()["id"])
        user = self.admin_user
        response = self.admin.post(
            f"{API}/projects/{self.whole.pk}/members", {"user": user.pk, "level": "none"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "level")
        response = self.admin.post(
            f"{API}/projects/{part.pk}/members", {"user": user.pk, "level": "none"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)


class TakeoverApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18))
        self.market = services.create_subproject(whole, name="Marktplatz", start=at(10, 8), end=at(12, 8))
        self.park = services.create_subproject(whole, name="Schlosspark", start=at(12, 12), end=at(14, 12))
        self.spot = make_stock("L-100", 6, "Spot")
        self.source = add_line(self.market, self.spot, 6).line

    def test_a_line_taken_over_through_the_api(self) -> None:
        body = {"product": self.spot.pk, "quantity": "6", "taken_over_from": self.source.pk}
        response = self.admin.post(f"{API}/projects/{self.park.pk}/material-lines", body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["taken_over_from"], self.source.pk)
        self.assertEqual(response.json()["availability"]["status"], "ok")
        self.assertEqual(response.json()["price"]["amount"], "0.00")
        line = MaterialLine.objects.get(project=self.park)
        self.assertEqual(line.taken_over_from, self.source)

    def test_too_many_pieces_are_refused(self) -> None:
        body = {"product": self.spot.pk, "quantity": "7", "taken_over_from": self.source.pk}
        response = self.admin.post(f"{API}/projects/{self.park.pk}/material-lines", body, format="json")
        self.assert_error(response, 400, "validation_error", "quantity")


class ShortagesOfPartsApiTests(ApiTestCase):
    def test_shortages_name_the_whole_project_and_what_other_parts_hold(self) -> None:
        """PRJ-047: the list of all shortages says how much other parts of the whole project hold."""
        whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18))
        market = services.create_subproject(whole, name="Marktplatz", start=at(10, 8), end=at(12, 8))
        park = services.create_subproject(whole, name="Schlosspark", start=at(11, 8), end=at(13, 8))
        for part in (market, park):
            part.status = ProjectStatus.CONFIRMED
            part.save()
        spot = make_stock("L-100", 4, "Spot")
        add_line(market, spot, 4)
        add_line(park, spot, 3)
        rows = self.admin.get(f"{API}/shortages").json()
        row = next(row for row in rows if row["project"] == park.pk)
        self.assertEqual((row["parent"], row["shortage"], row["held_by_other_parts"]), (whole.pk, 3, 3))
