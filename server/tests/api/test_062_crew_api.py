# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests for the crew: phases of crew lines (PRJ-080), per day (PER-029), the price overview by phase
and job function (PRJ-088)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.accounts.models import Role
from rentalars.personnel import services as personnel
from rentalars.projects import course
from rentalars.projects.models import CrewLine
from tests.api.base import API, ApiTestCase
from tests.helpers import at, job_function, make_person, make_project, plan

D = Decimal


class CrewLinePhaseAndDayApiTests(ApiTestCase):
    """``/projects/{id}/crew-lines`` with ``phase``, ``days``, ``daily_rate`` and the billing ``day``."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        self.setup = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        self.sound = job_function("Tontechnik", price="40.00", guide="30.00")
        self.anna = make_person("Anna Becker")
        personnel.set_rate(self.anna, self.sound, D("35.00"), daily_rate=D("280.00"))
        self.base = f"{API}/projects/{self.project.pk}/crew-lines"

    def test_plan_for_a_phase_and_per_day(self) -> None:
        created = self.admin.post(
            self.base,
            {
                "job_function": self.sound.pk,
                "person": self.anna.pk,
                "phase": self.setup.pk,
                "billing": "day",
                "unit_price": "400.00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        (line,) = created.json()
        self.assertEqual(
            (line["phase"], line["start"], line["end"], line["planned_hours"]),
            (self.setup.pk, "2027-03-12T07:00:00Z", "2027-03-12T15:00:00Z", "8.00"),
        )
        self.assertEqual(
            (line["billing"], line["days"], line["period_days"], line["charged_days"]), ("day", None, 1, 1)
        )
        self.assertEqual(
            (line["amount"], line["hourly_rate"], line["daily_rate"], line["cost"], line["cost_per_day"]),
            ("400.00", "35.00", "280.00", "280.00", True),
        )

        changed = self.admin.patch(f"{self.base}/{line['id']}", {"days": 2, "daily_rate": "300.00"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(
            (changed.json()["charged_days"], changed.json()["amount"], changed.json()["cost"]), (2, "800.00", "600.00")
        )
        moved = self.admin.patch(
            f"{self.base}/{line['id']}", {"phase": None, "end": "2027-03-12T18:00:00+01:00"}, format="json"
        )
        self.assertEqual((moved.json()["phase"], moved.json()["planned_hours"]), (None, "10.00"))
        listed = self.admin.get(self.base).json()
        self.assertEqual([row["phase"] for row in listed], [None])

    def test_a_phase_of_another_project_is_refused(self) -> None:
        other = make_project("Jazznacht")
        phase = course.add_phase(other, kind="setup", start=at(10, 8), end=at(10, 12))
        response = self.admin.post(self.base, {"job_function": self.sound.pk, "phase": phase.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CrewLine.objects.exists())

    def test_the_day_rate_needs_the_right_for_personnel_costs(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        Role.objects.create(name="Planung", module_levels={"projects": 2, "personnel": 1})
        planner = self.client_for("pia", "Planung")
        response = planner.patch(f"{self.base}/{line.pk}", {"daily_rate": "1.00"}, format="json")
        self.assert_error(response, 400, "validation_error")
        self.assertNotIn("daily_rate", planner.get(f"{self.base}/{line.pk}").json())
        line.refresh_from_db()
        self.assertEqual(line.daily_rate, D("280.00"))


class PhaseMovesCrewApiTests(ApiTestCase):
    """``/projects/{id}/phases`` with ``move_crew`` (PRJ-080)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        self.phase = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        self.whole = plan(self.project, "Stagehand", phase=self.phase)
        self.part = plan(self.project, "Stagehand", phase=self.phase, start=at(12, 12), end=at(12, 14))
        self.url = f"{API}/projects/{self.project.pk}/phases/{self.phase.pk}"

    def test_patch_moves_the_crew_by_default(self) -> None:
        response = self.admin.patch(
            self.url, {"start": "2027-03-12T10:00:00+01:00", "end": "2027-03-12T18:00:00+01:00"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(sorted(response.json()["moved_crew_lines"]), sorted([self.whole.pk, self.part.pk]))
        self.assertEqual(sorted(response.json()["crew_lines"]), sorted([self.whole.pk, self.part.pk]))
        self.part.refresh_from_db()
        self.assertEqual((self.part.start, self.part.end), (at(12, 14), at(12, 16)))

    def test_put_without_moving_the_crew(self) -> None:
        current = self.admin.get(self.url).json()
        current.update(start="2027-03-13T08:00:00+01:00", end="2027-03-13T16:00:00+01:00", move_crew=False)
        current.pop("crew_lines")
        response = self.admin.put(self.url, current, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.json()["moved_crew_lines"], [])
        self.whole.refresh_from_db()
        self.assertEqual((self.whole.start, self.whole.phase_id), (at(12, 8), self.phase.pk))

    def test_deleting_the_phase_keeps_the_crew(self) -> None:
        self.assertEqual(self.admin.delete(self.url).status_code, 204)
        self.whole.refresh_from_db()
        self.assertEqual((self.whole.phase, self.whole.start), (None, at(12, 8)))


class PriceOverviewByPhaseApiTests(ApiTestCase):
    """PRJ-088 through the API: ``personnel.by_phase``, and ``?crew=phases`` for PDF and CSV."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        phase = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        hand = job_function("Stagehand", price="28.00", guide="18.00")
        plan(self.project, hand, phase=phase)
        plan(self.project, hand, phase=phase)
        sound = job_function("Tontechnik", price="40.00")
        plan(self.project, sound, start=at(13, 18), end=at(13, 23), billing="day", unit_price=D("400.00"))
        self.base = f"{API}/projects/{self.project.pk}/price-overview"

    def test_the_breakdown_in_the_document(self) -> None:
        personnel_block = self.admin.get(self.base, {"crew": "phases"}).json()["personnel"]
        setup, without = personnel_block["by_phase"]
        self.assertEqual((setup["label"], setup["subtotal"], setup["cost"]), ("Aufbau", "448.00", "288.00"))
        # Without asking for it the overview names no cost (acceptance scenario 15).
        plain = self.admin.get(self.base).json()["personnel"]["by_phase"][0]
        self.assertEqual((plain["subtotal"], "cost" in plain), ("448.00", False))
        (hands,) = setup["functions"]
        self.assertEqual((hands["name"], hands["places"], hands["hours"], hands["days"]), ("Stagehand", 2, "16.00", 0))
        self.assertEqual((without["phase"], without["functions"][0]["days"]), (None, 1))
        lines = personnel_block["lines"]
        self.assertEqual(
            [(line["unit"], line["quantity"]) for line in lines], [("h", "8.00"), ("h", "8.00"), ("day", "1")]
        )

    def test_pdf_and_csv(self) -> None:
        pdf = self.admin.get(f"{self.base}/pdf", {"crew": "phases"})
        self.assertEqual((pdf.status_code, pdf["Content-Type"]), (200, "application/pdf"))
        csv = self.admin.get(f"{self.base}/csv", {"crew": "phases", "detail": "groups"})
        self.assertIn("Personal › Aufbau;2 × Stagehand, 16 Std.;448", csv.content.decode("utf-8-sig"))
