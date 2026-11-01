# SPDX-License-Identifier: GPL-3.0-or-later
"""The API beyond the planning of a part (PRJ-029, PRJ-044, API-014).

* ``POST /projects/{id}/duplicate`` with ``with_subprojects`` and ``as_subproject``;
* ``GET /calendar`` names the whole project of a part.
"""

from __future__ import annotations

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope
from rentalars.projects import services
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, add_line, at, make_customer, make_project, make_stock, make_user


class FamilyApiTestCase(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        customer = make_customer("Stadt Musterstadt")
        self.whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=customer)
        self.market = services.create_subproject(self.whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8))
        self.park = services.create_subproject(self.whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12))
        source = add_line(self.market, make_stock("L-100", 6, "Spot"), 6).line
        services.take_over_line(source, self.park, rights=ALL_RIGHTS)

    def duplicate(self, project: Project, client: object = None, **values: object) -> object:
        return (client or self.admin).post(f"{API}/projects/{project.pk}/duplicate", values, format="json")


class DuplicateApiTests(FamilyApiTestCase):
    """PRJ-029 with PRJ-044 and PRJ-060."""

    def test_a_whole_project_comes_with_its_parts(self) -> None:
        response = self.duplicate(self.whole, start="2028-03-09T12:00:00+01:00", end="2028-03-14T18:00:00+01:00")
        self.assertEqual(response.status_code, 201, response.data)
        copy = Project.objects.get(pk=response.json()["id"])
        self.assertEqual(len(response.json()["subprojects"]), 2)
        park = copy.subprojects.get(name="Bühne Schlosspark")
        self.assertEqual(park.material_lines.get().taken_over_from.project.parent, copy)

    def test_without_the_parts(self) -> None:
        response = self.duplicate(
            self.whole, start="2028-03-09T12:00:00+01:00", end="2028-03-14T18:00:00+01:00", with_subprojects=False
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.json()["subprojects"], [])

    def test_a_part_becomes_a_new_part_or_a_project_of_its_own(self) -> None:
        response = self.duplicate(self.park, name="Bühne Hof", start=at(13, 8).isoformat(), end=at(14, 8).isoformat())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.json()["parent"], self.whole.pk)
        outside = self.duplicate(self.park, start=at(20, 8).isoformat(), end=at(22, 8).isoformat())
        self.assert_error(outside, 400, "validation_error", "start")
        own = self.duplicate(self.park, as_subproject=False, start=at(20, 8).isoformat(), end=at(22, 8).isoformat())
        self.assertEqual(own.status_code, 201, own.data)
        self.assertIsNone(own.json()["parent"])

    def test_a_new_part_needs_the_right_to_edit_the_whole_project(self) -> None:
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        erik = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.park, user=erik, level=ProjectAccessLevel.EDIT)
        client = self.client_of(erik)
        period = {"start": at(13, 8).isoformat(), "end": at(14, 8).isoformat()}
        self.assert_error(self.duplicate(self.park, client, **period), 400, "validation_error", "as_subproject")
        own = self.duplicate(self.park, client, as_subproject=False, **period)
        self.assertEqual(own.status_code, 201, own.data)
        self.assertTrue(ProjectMembership.objects.filter(project_id=own.json()["id"], user=erik).exists())


class CalendarApiTests(FamilyApiTestCase):
    """PRJ-028 with PRJ-044: an entry of the calendar names the whole project of a part."""

    def test_the_parent_of_every_entry(self) -> None:
        rows = self.admin.get(f"{API}/calendar", {"from": "2027-03-08", "weeks": 1}).json()
        parents = {row["id"]: row["parent"] for row in rows}
        self.assertEqual(parents, {self.whole.pk: None, self.market.pk: self.whole.pk, self.park.pk: self.whole.pk})
