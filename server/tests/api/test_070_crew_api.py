# SPDX-License-Identifier: GPL-3.0-or-later
"""API: crew requests after changed times (PER-033, PER-034).

* ``GET /projects/{id}/crew-lines`` – each line with its request: status,
  the period asked for and whether the times changed since.
* ``POST …/crew-lines/{line}/request`` – refused (400) for an answered line
  whose times did not change.
* ``PATCH …/crew-lines/{line}`` and ``PATCH …/phases/{phase}`` – new times
  of a line asked for or accepted ask the person again.
* ``GET/PATCH /settings`` – ``system.ask_again_on_new_times``.
"""

from __future__ import annotations

from rentalars.core.models import SystemSettings
from rentalars.projects import course, crew
from rentalars.projects.models import CrewLine, RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_project, plan


class CrewRequestApiTests(ApiTestCase):
    """PER-033 and PER-034 through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10, 8), end=at(12, 20))
        self.line = plan(self.project, "Tontechnik", make_person("Anna Becker"), start=at(10, 8), end=at(10, 18))
        self.lines = f"{API}/projects/{self.project.pk}/crew-lines"
        self.url = f"{self.lines}/{self.line.pk}"
        crew.request_deployment(self.line, user=self.admin_user)
        crew.answer_deployment(self.line, accept=True, user=self.admin_user)

    def test_the_line_names_its_request(self) -> None:
        (document,) = self.admin.get(self.lines).json()
        self.assertEqual(document["request_status"], "accepted")
        self.assertEqual((document["requested_start"], document["requested_end"]), (document["start"], document["end"]))
        self.assertEqual(document["requested_start"], "2027-03-10T07:00:00Z")
        self.assertIs(document["times_changed_since_request"], False)
        self.assertIsNotNone(document["answered_at"])

    def test_asking_again_for_the_same_times_is_refused(self) -> None:
        response = self.admin.post(f"{self.url}/request")
        error = self.assert_error(response, 400, "validation_error")
        self.assertIn("Anna Becker hat für diese Zeiten schon zugesagt.", error["message"])
        self.assertEqual(CrewLine.objects.get(pk=self.line.pk).request_status, RequestStatus.ACCEPTED)

    def test_new_times_ask_again(self) -> None:
        response = self.admin.patch(self.url, {"start": "2027-03-10T10:00:00+01:00"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        document = response.json()
        self.assertEqual(document["request_status"], "requested")
        self.assertEqual(document["requested_start"], document["start"])
        self.assertEqual(CrewLine.objects.get(pk=self.line.pk).requested_start, at(10, 10))
        self.assertIs(document["times_changed_since_request"], False)

    def test_switched_off_the_line_shows_the_change_and_can_be_asked_again(self) -> None:
        settings = self.admin.patch(f"{API}/settings", {"system": {"ask_again_on_new_times": False}}, format="json")
        self.assertEqual(settings.status_code, 200, settings.content)
        self.assertIs(settings.json()["system"]["ask_again_on_new_times"], False)
        self.assertFalse(SystemSettings.load().ask_again_on_new_times)
        document = self.admin.patch(self.url, {"end": "2027-03-10T20:00:00+01:00"}, format="json").json()
        self.assertEqual(document["request_status"], "accepted")
        self.assertIs(document["times_changed_since_request"], True)
        asked = self.admin.post(f"{self.url}/request")
        self.assertEqual(asked.status_code, 200, asked.content)
        self.assertEqual(asked.json()["request_status"], "requested")

    def test_moving_the_phase_asks_again(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(10, 8), end=at(10, 18))
        CrewLine.objects.filter(pk=self.line.pk).update(phase=phase)
        response = self.admin.patch(
            f"{API}/projects/{self.project.pk}/phases/{phase.pk}",
            {"start": "2027-03-10T09:00:00+01:00", "end": "2027-03-10T19:00:00+01:00"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["moved_crew_lines"], [self.line.pk])
        line = CrewLine.objects.get(pk=self.line.pk)
        self.assertEqual((line.request_status, line.requested_start), (RequestStatus.REQUESTED, at(10, 9)))

    def test_the_setting_is_on_by_default(self) -> None:
        self.assertIs(self.admin.get(f"{API}/settings").json()["system"]["ask_again_on_new_times"], True)
