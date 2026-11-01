# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, pickers: a phase beyond the rental period (PRJ-100).

The phases tell whether they lie outside the rental period and which rental period would cover them; the API
never extends the rental period by itself – a client does so with ``PATCH /projects/{id}``.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.projects import course, services
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_project


class PhaseOutsideTheRentalPeriodApiTests(ApiTestCase):
    """PRJ-100: ``outside_rental_period`` and ``rental_period_suggestion`` on every phase."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(12, 12), end=at(14, 18))
        self.base = f"{API}/projects/{self.project.pk}/phases"

    def test_a_phase_within_the_rental_period(self) -> None:
        answer = self.admin.post(self.base, {"kind": "setup", "start": at(12, 12), "end": at(12, 20)}, format="json")
        self.assertEqual(answer.status_code, 201, answer.data)
        self.assertIs(answer.json()["outside_rental_period"], False)
        self.assertIsNone(answer.json()["rental_period_suggestion"])

    def test_creating_a_phase_beyond_it_only_tells(self) -> None:
        answer = self.admin.post(self.base, {"kind": "setup", "start": at(11, 14), "end": at(11, 20)}, format="json")
        self.assertEqual(answer.status_code, 201, answer.data)
        data = answer.json()
        self.assertIs(data["outside_rental_period"], True)
        self.assertEqual(
            data["rental_period_suggestion"],
            {"start": "2027-03-11T14:00:00+01:00", "end": "2027-03-14T18:00:00+01:00"},
        )
        self.project.refresh_from_db()
        self.assertEqual((self.project.start, self.project.end), (at(12, 12), at(14, 18)))  # no change by itself

    def test_changing_a_phase_beyond_it(self) -> None:
        phase = course.add_phase(self.project, kind="teardown", start=at(14, 12), end=at(14, 18))
        answer = self.admin.patch(f"{self.base}/{phase.pk}", {"end": at(15, 9)}, format="json")
        self.assertEqual(answer.status_code, 200, answer.data)
        self.assertIs(answer.json()["outside_rental_period"], True)
        self.assertEqual(answer.json()["rental_period_suggestion"]["end"], "2027-03-15T09:00:00+01:00")

    def test_planning_and_meetings_tell_but_suggest_nothing(self) -> None:
        answer = self.admin.post(self.base, {"kind": "planning", "start": at(1, 10), "end": at(1, 12)}, format="json")
        self.assertIs(answer.json()["outside_rental_period"], True)
        self.assertIsNone(answer.json()["rental_period_suggestion"])

    def test_the_client_extends_with_the_project(self) -> None:
        answer = self.admin.post(self.base, {"kind": "setup", "start": at(11, 14), "end": at(11, 20)}, format="json")
        suggestion = answer.json()["rental_period_suggestion"]
        changed = self.admin.patch(f"{API}/projects/{self.project.pk}", suggestion, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        listed = self.admin.get(self.base).json()
        self.assertEqual(
            [(row["outside_rental_period"], row["rental_period_suggestion"]) for row in listed], [(False, None)]
        )

    def test_a_subproject_suggests_what_the_whole_project_must_allow_first(self) -> None:
        part = services.create_subproject(self.project, name="Bühne", start=at(13, 8), end=at(14, 12))
        answer = self.admin.post(
            f"{API}/projects/{part.pk}/phases", {"kind": "setup", "start": at(11, 14), "end": at(11, 20)}, format="json"
        )
        self.assertEqual(answer.json()["rental_period_suggestion"]["start"], "2027-03-11T14:00:00+01:00")
        refused = self.admin.patch(
            f"{API}/projects/{part.pk}", answer.json()["rental_period_suggestion"], format="json"
        )
        self.assertEqual(refused.status_code, 400)

    def test_the_list_costs_no_query_per_phase(self) -> None:
        course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        self.admin.get(self.base)  # the first request of a client asks for more (session, rights)
        with CaptureQueriesContext(connection) as one:
            self.admin.get(self.base)
        for day in (12, 13, 14):
            course.add_phase(self.project, kind="event", start=at(day, 14), end=at(day, 16))
        with CaptureQueriesContext(connection) as four:
            rows = self.admin.get(self.base).json()
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(four), len(one))

    def test_the_schema_describes_the_fields(self) -> None:
        schema = self.admin.get(f"{API}/schema", {"format": "json"})
        if schema.status_code != 200:
            self.skipTest("the schema is not served at this address")
        properties = schema.json()["components"]["schemas"]["Phase"]["properties"]
        self.assertEqual(properties["outside_rental_period"]["type"], "boolean")
        self.assertIn("rental_period_suggestion", properties)
        self.assertTrue(properties["outside_rental_period"].get("readOnly"))
