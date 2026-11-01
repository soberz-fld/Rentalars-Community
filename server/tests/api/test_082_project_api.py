# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "project" (API-014): trips changed, removed, reset and added (PRJ-111); the customer of a
service case required (PRJ-090).

``GET /projects/{id}/trips`` (with ``?removed=true``), ``POST /projects/{id}/trips``,
``PATCH`` and ``DELETE /projects/{id}/trips/{key}``, ``POST /projects/{id}/trips/{key}/reset``;
``POST``, ``PATCH`` and ``PUT /service-cases``.
"""

from __future__ import annotations

from rentalars.core.models import CompanyProfile
from rentalars.projects import course, service_cases
from rentalars.projects.models import PhaseKind, Project, ProjectStatus, TripAdjustment
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_customer, make_person, make_project, plan

WAREHOUSE = "Hafenstraße 1, 12345 Musterstadt"


class TripApiTests(ApiTestCase):
    """PRJ-111 through the API."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.warehouse_address = WAREHOUSE
        profile.save()
        self.project = make_project(start=at(10, 8), end=at(12, 20), venue="Stadthalle, Marktplatz 1")
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16))
        self.url = f"{API}/projects/{self.project.pk}/trips"
        self.key = f"to_venue-{self.setup.pk}"

    def test_change_and_reset(self) -> None:
        """PRJ-111, API-014: PATCH keeps what is left out; reset brings the determined trip back."""
        trips = self.admin.get(self.url).json()
        self.assertEqual([trip["key"] for trip in trips], [self.key, f"from_venue-{self.setup.pk}"])
        self.assertEqual((trips[0]["is_changed"], trips[0]["is_removed"], trips[0]["note"]), (False, False, ""))
        changed = self.admin.patch(
            f"{self.url}/{self.key}",
            {"destination": "Stadthalle, Lieferzufahrt Nord", "stops": ["Baumarkt"], "note": "Rampe"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        trip = changed.json()
        self.assertEqual((trip["is_changed"], trip["note"]), (True, "Rampe"))
        self.assertEqual(trip["destination"]["address"], "Stadthalle, Lieferzufahrt Nord")
        self.assertEqual(trip["origin"]["address"], WAREHOUSE)
        self.assertIn("waypoints=Baumarkt", trip["route_url"])
        adjustment = TripAdjustment.objects.get()
        self.assertEqual((adjustment.origin, adjustment.start), ("", None))  # unchanged: not stored
        reset = self.admin.post(f"{self.url}/{self.key}/reset")
        self.assertEqual(reset.status_code, 200, reset.content)
        self.assertEqual(
            (reset.json()["is_changed"], reset.json()["destination"]["address"]), (False, "Stadthalle, Marktplatz 1")
        )
        self.assertFalse(TripAdjustment.objects.exists())

    def test_remove_list_removed_and_bring_back(self) -> None:
        self.assertEqual(self.admin.delete(f"{self.url}/{self.key}").status_code, 204)
        self.assertEqual([trip["key"] for trip in self.admin.get(self.url).json()], [f"from_venue-{self.setup.pk}"])
        everything = self.admin.get(self.url, {"removed": "true"}).json()
        self.assertEqual(next((trip["key"], trip["is_removed"]) for trip in everything), (self.key, True))
        self.assertEqual(self.admin.post(f"{self.url}/{self.key}/reset").status_code, 200)
        self.assertEqual(len(self.admin.get(self.url).json()), 2)

    def test_a_trip_of_ones_own(self) -> None:
        body = {"start": "2027-03-11T09:00+01:00", "origin": WAREHOUSE, "destination": "Stadthalle", "title": "Kabel"}
        created = self.admin.post(self.url, body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        trip = created.json()
        self.assertEqual((trip["kind"], trip["title"]), ("own", "Kabel"))
        self.assertTrue(trip["key"].startswith("own-"))
        self.assert_error(self.admin.post(f"{self.url}/{trip['key']}/reset"), 400, "validation_error")
        self.assertEqual(self.admin.delete(f"{self.url}/{trip['key']}").status_code, 204)
        self.assertFalse(TripAdjustment.objects.exists())
        self.assert_error(
            self.admin.post(self.url, {"title": "ohne alles"}, format="json"), 400, "validation_error", "start"
        )

    def test_unknown_trips_rights_and_closed_projects(self) -> None:
        self.assertEqual(self.admin.patch(f"{self.url}/to_venue-999", {"note": "x"}, format="json").status_code, 404)
        self.assertEqual(self.admin.delete(f"{self.url}/pickup").status_code, 404)
        reader = self.client_for("luka", "Lager")
        self.assertEqual(reader.get(self.url).status_code, 200)
        self.assertEqual(reader.patch(f"{self.url}/{self.key}", {"note": "x"}, format="json").status_code, 403)
        self.assertEqual(reader.delete(f"{self.url}/{self.key}").status_code, 403)
        # A planned driver reads the trips of the project but changes nothing.
        crew_user = self.client_for("kai", "Crew")
        from rentalars.accounts.models import User

        plan(self.project, "Stagehand", make_person("Kai Kurz", user=User.objects.get(username="kai")))
        self.assertEqual(crew_user.get(self.url).status_code, 200)
        self.assertEqual(crew_user.get(self.url, {"removed": "true"}).json()[0]["is_removed"], False)
        self.assertIn(crew_user.delete(f"{self.url}/{self.key}").status_code, (403, 404))
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.assert_error(self.admin.delete(f"{self.url}/{self.key}"), 400, "validation_error")
        self.assertFalse(TripAdjustment.objects.exists())

    def test_the_description_names_the_new_operations(self) -> None:
        schema = self.admin.get(f"{API}/schema").content.decode()
        for path in ("/projects/{project_pk}/trips/{key}", "/projects/{project_pk}/trips/{key}/reset"):
            self.assertIn(path, schema)


class ServiceCaseCustomerApiTests(ApiTestCase):
    """PRJ-090: a new case needs a customer; an older one asks for it at the first change."""

    url = f"{API}/service-cases"

    def test_create_needs_a_customer(self) -> None:
        self.assert_error(
            self.admin.post(self.url, {"name": "Spot flackert"}, format="json"), 400, "validation_error", "customer"
        )
        created = self.admin.post(self.url, {"name": "Spot flackert", "customer": make_customer().pk}, format="json")
        self.assertEqual(created.status_code, 201, created.content)

    def test_an_older_case_without_customer(self) -> None:
        old = service_cases.create_case(name="Kabel defekt")
        detail = f"{self.url}/{old.pk}"
        self.assertEqual(self.admin.get(detail).json()["customer"], None)
        self.assertEqual(self.admin.patch(detail, {"case_status": "in_progress"}, format="json").status_code, 200)
        self.assert_error(self.admin.patch(detail, {"notes": "x"}, format="json"), 400, "validation_error", "customer")
        changed = self.admin.patch(detail, {"notes": "x", "customer": make_customer().pk}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
