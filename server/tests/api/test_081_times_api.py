# SPDX-License-Identifier: GPL-3.0-or-later
"""Through the API, area "times": ZEI-025 and ZEI-024 (API-014).

No new operations – the companion app keeps using ``/time-entries`` and ``/time-entries/choices`` – but new fields:

* ZEI-025: ``parts`` when recording and changing an entry, ``crew_line`` of an entry and of the stopwatch,
  ``period`` and ``period_hours`` of every entry, ``crew_lines`` with a ``label`` in the choices; approving one part
  approves its period. An entry without parts behaves as before.
* ZEI-024: open service cases in the choices (``is_service_case``, ``takes_part``) with every job function.
"""

from __future__ import annotations

from decimal import Decimal as D  # noqa: N817

from rentalars.projects import service_cases
from rentalars.projects.models import PhaseKind, ProjectPhase
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import LATER, at, job_function, make_person, make_project, make_user, plan, set_clock

ENTRIES = f"{API}/time-entries"


class PeriodApiCase(ApiTestCase):
    """Anna (crew) works light at the setup (08–12) and sound (12–20) of the Stadtfest on 10 March 2027."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.light = job_function("Licht", price="40.00")
        self.sound = job_function("Tontechnik", price="45.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Licht": "30.00", "Tontechnik": "35.00"}, user=self.anna_user)
        setup = ProjectPhase.objects.create(project=self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 12))
        self.light_line = plan(self.project, self.light, self.anna, start=at(10, 8), end=at(10, 12), phase=setup)
        self.sound_line = plan(self.project, self.sound, self.anna, start=at(10, 12), end=at(10, 20))
        self.crew = self.client_of(self.anna_user)
        self.manager = self.client_of(make_user("paula", roles=("Projektleitung",)))

    def divide(self) -> dict:
        created = self.crew.post(
            ENTRIES,
            {
                "project": self.project.pk,
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T16:30:00+01:00",
                "break_minutes": 30,
                "submit": True,
                "parts": [
                    {"job_function": self.light.pk, "crew_line": self.light_line.pk, "hours": "3"},
                    {"job_function": self.sound.pk},
                ],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        return created.json()


class PartsApiTests(PeriodApiCase):
    """ZEI-025."""

    def test_recording_a_divided_period(self) -> None:
        created = self.divide()
        self.assertEqual([part["hours"] for part in created["parts"]], ["3.00", "5.00"])
        self.assertEqual([part["crew_line"] for part in created["parts"]], [self.light_line.pk, self.sound_line.pk])
        self.assertEqual({part["period"] for part in created["parts"]}, {created["period"]})
        self.assertEqual(created["period_hours"], "8.00")
        self.assertEqual(created["id"], created["parts"][0]["id"])
        listed = self.crew.get(ENTRIES).json()["results"]
        self.assertEqual(len(listed), 2)
        self.assertEqual({entry["period"] for entry in listed}, {created["period"]})

    def test_hours_that_do_not_add_up_answer_400(self) -> None:
        refused = self.crew.post(
            ENTRIES,
            {
                "project": self.project.pk,
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T10:00:00+01:00",
                "parts": [{"job_function": self.light.pk, "hours": "1"}, {"job_function": self.sound.pk, "hours": "2"}],
            },
            format="json",
        )
        self.assertEqual(refused.status_code, 400)
        self.assertIn("parts", refused.json()["error"]["fields"])
        self.assertFalse(TimeEntry.objects.exists())

    def test_an_entry_without_parts_is_as_before(self) -> None:
        created = self.crew.post(
            ENTRIES,
            {
                "project": self.project.pk,
                "job_function": self.sound.pk,
                "start": "2027-03-10T12:00:00+01:00",
                "end": "2027-03-10T20:00:00+01:00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        body = created.json()
        self.assertEqual((body["period"], body["period_hours"], body["hours"]), (None, None, "8.00"))
        self.assertNotIn("parts", body)
        self.assertEqual(body["crew_line"], self.sound_line.pk)

    def test_changing_the_parts_and_the_times(self) -> None:
        created = self.divide()
        second = created["parts"][1]["id"]
        changed = self.crew.patch(
            f"{ENTRIES}/{second}",
            {"parts": [{"job_function": self.sound.pk, "hours": "6"}, {"job_function": self.light.pk}]},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(
            [(part["job_function"], part["hours"]) for part in changed.json()["parts"]],
            [(self.sound.pk, "6.00"), (self.light.pk, "2.00")],
        )
        # New times of one part change the period; the shares keep their proportion.
        moved = self.crew.patch(f"{ENTRIES}/{second}", {"end": "2027-03-10T12:30:00+01:00"}, format="json")
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual([part["hours"] for part in moved.json()["parts"]], ["3.00", "1.00"])

    def test_a_crew_line_names_the_deployment(self) -> None:
        created = self.crew.post(
            ENTRIES,
            {
                "project": self.project.pk,
                "crew_line": self.light_line.pk,
                "job_function": self.light.pk,
                "start": "2027-03-10T13:00:00+01:00",
                "end": "2027-03-10T14:00:00+01:00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.json()["crew_line"], self.light_line.pk)  # not the line running at 13:00

    def test_the_stopwatch_with_a_crew_line(self) -> None:
        set_clock(at(10, 9))
        started = self.crew.post(
            f"{ENTRIES}/timer/start", {"crew_line": self.light_line.pk, "project": self.project.pk}
        )
        self.assertEqual(started.status_code, 201, started.data)
        self.assertEqual(
            (started.json()["crew_line"], started.json()["job_function"]), (self.light_line.pk, self.light.pk)
        )

    def test_approving_one_part_approves_the_period(self) -> None:
        created = self.divide()
        answer = self.manager.post(f"{ENTRIES}/approve", {"ids": [created["id"]]}, format="json")
        self.assertEqual(answer.json(), {"changed": 2})
        self.assertEqual(set(TimeEntry.objects.values_list("status", flat=True)), {TimeEntryStatus.APPROVED})

    def test_the_choices_carry_the_deployments(self) -> None:
        choices = self.crew.get(f"{ENTRIES}/choices").json()
        stadtfest = next(choice for choice in choices if choice["project"] == self.project.pk)
        self.assertEqual(
            [(line["id"], line["label"], line["phase"]) for line in stadtfest["crew_lines"]],
            [
                (self.light_line.pk, "Licht – Aufbau, Mi 10.03. 08:00–12:00", "Aufbau"),
                (self.sound_line.pk, "Tontechnik, Mi 10.03. 12:00–20:00", None),
            ],
        )
        self.assertFalse(stadtfest["is_service_case"])
        self.assertEqual(choices[-1]["reason"], "without_project")
        self.assertEqual(choices[-1]["crew_lines"], [])


class ServiceCaseApiTests(PeriodApiCase):
    """ZEI-024."""

    def test_open_cases_in_the_choices_with_every_job_function(self) -> None:
        mine = service_cases.create_case(name="Frage zur Anleitung")
        other = service_cases.create_case(name="Scheinwerfer flackert")
        service_cases.add_participant(mine, self.anna, job_function=self.sound)
        rigging = job_function("Rigging")
        choices = self.crew.get(f"{ENTRIES}/choices").json()
        cases = [choice for choice in choices if choice["is_service_case"]]
        self.assertEqual([choice["project"] for choice in cases], [mine.pk, other.pk])
        self.assertEqual([choice["takes_part"] for choice in cases], [True, False])
        self.assertEqual(cases[0]["suggested_job_function"], self.sound.pk)
        self.assertIn(rigging.pk, [function["id"] for function in cases[1]["job_functions"]])
        created = self.crew.post(
            ENTRIES,
            {
                "project": other.pk,
                "job_function": rigging.pk,
                "start": "2027-03-20T09:00:00+01:00",
                "end": "2027-03-20T10:00:00+01:00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.json()["hours"], "1.00")
        self.assertEqual(D(created.json()["hours"]), D("1"))
