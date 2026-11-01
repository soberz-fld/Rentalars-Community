# SPDX-License-Identifier: GPL-3.0-or-later
"""The API and the planning changes: no new operation, nothing of the pages' defaults in the API.

* VFG-027 – the timeline of a person names the kind of a deployment bar as the
  pages draw it ("crew status-…").
* VFG-028, VFG-029 – the pages open with four days; the API keeps its
  defaults (weeks), so that existing programs get the same answers.
"""

from __future__ import annotations

from rentalars.projects.models import CrewLine, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, at, make_person, make_project, make_stock, plan


class PlanningApiTests(ApiTestCase):
    def test_the_timeline_of_a_person_names_the_colours(self) -> None:
        anna = make_person("Anna Becker", rates={"Lichttechnik": "35.00"})
        plan(
            make_project("Hochzeit", status=ProjectStatus.INQUIRY, start=at(2, 8), end=at(2, 22)), "Lichttechnik", anna
        )
        line = plan(make_project("Stadtfest", start=at(4, 8), end=at(4, 22)), "Lichttechnik", anna)
        CrewLine.objects.filter(pk=line.pk).update(request_status="requested")
        timeline = self.admin.get(f"{API}/people/{anna.pk}/timeline", {"from": "2027-03-01", "weeks": 1}).json()
        self.assertEqual(
            [bar["kind"] for bar in timeline["rows"][0]["bars"]],
            ["crew status-inquiry", "crew status-confirmed requested"],
        )

    def test_the_spans_of_the_api_stay_weeks(self) -> None:
        spot = make_stock("L-090", 10, "Moving Head Spot")
        add_line(make_project("Vortrag", start=at(10, 8), end=at(10, 12)), spot, 4)
        rows = self.admin.get(f"{API}/utilization", {"product": spot.pk, "from": "2027-03-08"}).json()
        self.assertEqual(len(rows[0]["days"]), 14)  # two weeks, as before
        plan_rows = self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-08"}).json()
        self.assertIsInstance(plan_rows, list)
