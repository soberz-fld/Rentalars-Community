# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "plan" (API-014): moving a deployment (VFG-031).

``POST /projects/{id}/reschedule/preview`` and ``POST /projects/{id}/reschedule`` take ``what=crew`` with
``crew_line`` – the move the personnel plan drags –, and the answer names the planned hours before and after.
"""

from __future__ import annotations

from rentalars.projects import course
from rentalars.projects.models import CrewLine, PhaseKind, Project, ProjectStatus, RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_project, plan


class RescheduleACrewLineApiTests(ApiTestCase):
    """VFG-031 through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, phase=self.phase)
        CrewLine.objects.filter(pk=self.line.pk).update(
            request_status=RequestStatus.ACCEPTED, requested_start=at(10, 14), requested_end=at(10, 20)
        )
        self.url = f"{API}/projects/{self.project.pk}/reschedule"
        self.body = {
            "what": "crew",
            "crew_line": self.line.pk,
            "start": "2027-03-10T16:00+01:00",
            "end": "2027-03-10T21:00+01:00",
        }

    def test_preview_changes_nothing(self) -> None:
        response = self.admin.post(f"{self.url}/preview", self.body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["possible"])
        self.assertFalse(data["offers_with_schedule"])
        outcome = data["outcome"]
        self.assertEqual(outcome["changes"][0]["kind"], "crew")
        self.assertEqual(outcome["changes"][0]["label"], "Einsatz von Anna Becker als Stagehand")
        self.assertEqual((outcome["planned_hours_before"], outcome["planned_hours_after"]), ("6.00", "5.00"))
        (crew,) = outcome["crew_lines"]
        self.assertEqual((crew["crew_line"], crew["new_start"]), (self.line.pk, "2027-03-10T16:00:00+01:00"))
        self.assertIsNotNone(crew["asked_again"])
        self.assertEqual(crew["warnings"], [])
        line = CrewLine.objects.get(pk=self.line.pk)
        self.assertEqual((line.start, line.request_status), (at(10, 14), RequestStatus.ACCEPTED))

    def test_move(self) -> None:
        response = self.admin.post(self.url, self.body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["planned_hours_after"], "5.00")
        line = CrewLine.objects.get(pk=self.line.pk)
        self.assertEqual((line.start, line.end, line.request_status), (at(10, 16), at(10, 21), RequestStatus.REQUESTED))
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 14))

    def test_refusals_and_rights(self) -> None:
        self.assert_error(
            self.admin.post(self.url, {**self.body, "crew_line": None}, format="json"), 400, "validation_error"
        )
        other = plan(make_project("Weinfest"), "Stagehand", self.anna)
        self.assert_error(
            self.admin.post(self.url, {**self.body, "crew_line": other.pk}, format="json"), 404, "not_found"
        )
        reader = self.client_for("rita", "Nur-Lesen")
        self.assert_error(reader.post(self.url, self.body, format="json"), 403, "permission_denied")
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.assert_error(self.admin.post(self.url, self.body, format="json"), 400, "validation_error")
