# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 4 – Stundensatz je Funktion (catalogue chapter 11).

Told through the API, the way another program would do it; the rules
themselves are tested in ``tests/unit/test_crew.py`` and
``tests/unit/test_timetracking.py``.
"""

from tests.api.base import API, ApiTestCase
from tests.helpers import LATER, job_function, make_person, make_project, make_user, set_clock


class Scenario04HourlyRatePerJobFunction(ApiTestCase):
    """PER-005, PER-007, PRJ-021, ZEI-008."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)  # the hours of 10 March are recorded afterwards (ZEI-022)
        self.sound = job_function("Tontechnik", price="45.00")
        self.hand = job_function("Stagehand", price="28.00")
        # Given: person A with the job functions Tontechnik at 35.00 and Stagehand at 20.00.
        self.user = make_user("anna", roles=("Crew",))
        self.person = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"}, user=self.user)
        self.project = make_project("Stadtfest")
        self.crew = f"{API}/projects/{self.project.pk}/crew-lines"

    def plan_as_sound_engineer(self) -> dict:
        response = self.admin.post(
            self.crew,
            {
                "job_function": self.sound.pk,
                "person": self.person.pk,
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T18:00:00+01:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.json()[0]

    def record_as_stagehand(self) -> dict:
        response = self.client_of(self.user).post(
            f"{API}/time-entries",
            {
                "project": self.project.pk,
                "job_function": self.hand.pk,
                "start": "2027-03-10T18:00:00+01:00",
                "end": "2027-03-10T22:00:00+01:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.json()

    def test_planned_as_sound_engineer_the_line_carries_35(self) -> None:
        self.assertEqual(self.plan_as_sound_engineer()["hourly_rate"], "35.00")

    def test_four_hours_as_stagehand_in_the_same_project_are_valued_at_20(self) -> None:
        self.plan_as_sound_engineer()
        entry = self.record_as_stagehand()
        self.assertEqual((entry["hours"], entry["hourly_rate"], entry["amount"]), ("4.00", "20.00", "80.00"))

    def test_raising_the_rate_later_leaves_existing_lines_and_entries_unchanged(self) -> None:
        line = self.plan_as_sound_engineer()
        entry = self.record_as_stagehand()
        own = (
            self.client_of(self.user)
            .post(
                f"{API}/time-entries",
                {
                    "project": self.project.pk,
                    "job_function": self.sound.pk,
                    "start": "2027-03-10T08:00:00+01:00",
                    "end": "2027-03-10T12:00:00+01:00",
                },
                format="json",
            )
            .json()
        )
        self.assertEqual(own["hourly_rate"], "35.00")

        # The rate for Tontechnik is raised to 38.00, valid from today.
        raised = self.admin.post(
            f"{API}/people/{self.person.pk}/job-functions",
            {"job_function": self.sound.pk, "hourly_rate": "38.00", "valid_from": "2027-03-01"},
            format="json",
        )
        self.assertEqual(raised.status_code, 200, raised.data)

        self.assertEqual(self.admin.get(f"{self.crew}/{line['id']}").json()["hourly_rate"], "35.00")
        self.assertEqual(self.admin.get(f"{API}/time-entries/{own['id']}").json()["hourly_rate"], "35.00")
        self.assertEqual(self.admin.get(f"{API}/time-entries/{entry['id']}").json()["hourly_rate"], "20.00")

        # Only what is planned and recorded from now on carries the new rate.
        new_line = self.admin.post(
            self.crew,
            {
                "job_function": self.sound.pk,
                "person": self.person.pk,
                "start": "2027-03-11T08:00:00+01:00",
                "end": "2027-03-11T18:00:00+01:00",
            },
            format="json",
        ).json()[0]
        self.assertEqual(new_line["hourly_rate"], "38.00")
