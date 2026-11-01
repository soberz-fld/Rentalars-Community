# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests for the phases: the kinds (PRJ-092), the calendar with phases outside the rental period, and
projects from the template "Dry Hire" (PRJ-095)."""

from __future__ import annotations

from rentalars.projects import course
from rentalars.projects.defaults import install_dry_hire_template
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_project


class KindsOfPhasesApiTests(ApiTestCase):
    """PRJ-092: the new kinds through the API; "Packen" keeps the value ``loading``."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 12), end=at(12, 12))
        self.base = f"{API}/projects/{self.project.pk}/phases"

    def test_planning_packing_and_follow_up_work(self) -> None:
        for kind, start, end in (
            ("planning", at(3, 10), at(3, 11)),
            ("loading", at(10, 12), at(10, 14)),
            ("aftercare", at(12, 8), at(12, 12)),
        ):
            answer = self.admin.post(self.base, {"kind": kind, "start": start, "end": end}, format="json")
            self.assertEqual(answer.status_code, 201, answer.data)
        labels = [(row["kind"], row["label"]) for row in self.admin.get(self.base).json()]
        self.assertEqual(
            labels,
            [("planning", "Planungen und Besprechungen"), ("loading", "Packen"), ("aftercare", "Nachbereitung")],
        )

    def test_an_unknown_kind_is_refused(self) -> None:
        answer = self.admin.post(self.base, {"kind": "packing", "start": at(10, 12), "end": at(10, 14)}, format="json")
        self.assert_error(answer, 400, "validation_error", "kind")

    def test_the_schema_lists_the_kinds_in_their_order(self) -> None:
        schema = self.admin.get(f"{API}/schema", {"format": "json"})
        if schema.status_code != 200:
            self.skipTest("the schema is not served at this address")
        enum = schema.json()["components"]["schemas"]["PhaseKindEnum"]["enum"]
        self.assertEqual(enum[0], "planning")
        self.assertEqual(enum[-3:], ["aftercare", "cleaning", "other"])


class CalendarWithPhasesApiTests(ApiTestCase):
    """PRJ-092: ``/calendar`` lists a project also for a span that holds only one of its phases."""

    def test_a_planning_meeting_before_the_rental_period(self) -> None:
        project = make_project("Stadtfest", start=at(22, 12), end=at(24, 12))
        course.add_phase(project, kind="planning", title="Ortstermin", start=at(10, 10), end=at(10, 12))
        make_project("Später", start=at(29, 12), end=at(30, 12))
        rows = self.admin.get(f"{API}/calendar", {"from": "2027-03-08", "weeks": 1}).json()
        self.assertEqual([row["id"] for row in rows], [project.pk])
        self.assertEqual([(phase["kind"], phase["label"]) for phase in rows[0]["phases"]], [("planning", "Ortstermin")])


class DryHireApiTests(ApiTestCase):
    """PRJ-095: a project made from the template through the API gets its phases and notes."""

    def test_a_project_from_the_template(self) -> None:
        template = install_dry_hire_template()
        customer = make_project().customer
        answer = self.admin.post(
            f"{API}/projects",
            {
                "name": "Verleih Müller",
                "customer": customer.pk,
                "start": at(20, 12),
                "end": at(22, 12),
                "template": template.pk,
            },
            format="json",
        )
        self.assertEqual(answer.status_code, 201, answer.data)
        project_id = answer.json()["id"]
        phases = self.admin.get(f"{API}/projects/{project_id}/phases").json()
        self.assertEqual([row["kind"] for row in phases], ["loading", "other", "return", "aftercare"])
        self.assertEqual(phases[1]["label"], "Übergabe an den Kunden (Abholung)")
        self.assertEqual(self.admin.get(f"{API}/projects/{project_id}/crew-lines").json(), [])
        listed = self.admin.get(f"{API}/project-templates").json()
        names = [row["name"] for row in (listed["results"] if isinstance(listed, dict) else listed)]
        self.assertIn("Dry Hire (Vermietung ohne Personal)", names)
