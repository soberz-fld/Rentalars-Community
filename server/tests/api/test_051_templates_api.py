# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the project templates (PRJ-076) and of the readable numbers (UIX-024)."""

from __future__ import annotations

from rentalars.projects.models import Project, ProjectTemplate
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, at, make_project, make_stock, plan


class ProjectTemplateApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("T-001", 10, "Lautsprecher")
        self.source = make_project("Stadtfest", start=at(10, 12), end=at(11, 12))
        add_line(self.source, self.speaker, 4)
        plan(self.source, "Tontechnik")

    def test_make_change_and_delete_a_template(self) -> None:
        """POST with ``project`` makes the template; name and description can be changed."""
        response = self.admin.post(
            f"{API}/project-templates", {"project": self.source.pk, "name": "Fest klein", "crew": False}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["source_number"], self.source.number)
        self.assertEqual((body["counts"]["lines"], body["counts"]["crew"]), (1, 0))
        url = f"{API}/project-templates/{body['id']}"
        self.assertEqual(self.admin.get(f"{API}/project-templates").json()["results"][0]["name"], "Fest klein")
        self.assertEqual(self.admin.patch(url, {"description": "Für kleine Feste"}, format="json").status_code, 200)
        self.assertEqual(ProjectTemplate.objects.get().description, "Für kleine Feste")
        self.assertEqual(self.admin.get(url).json()["description"], "Für kleine Feste")
        self.assertEqual(self.admin.delete(url).status_code, 204)

    def test_errors(self) -> None:
        """Without project, with a taken name, or for a project out of reach."""
        self.assert_error(
            self.admin.post(f"{API}/project-templates", {"name": "x"}, format="json"), 400, "validation_error"
        )
        self.admin.post(f"{API}/project-templates", {"project": self.source.pk, "name": "Fest"}, format="json")
        self.assert_error(
            self.admin.post(f"{API}/project-templates", {"project": self.source.pk, "name": "fest"}, format="json"),
            400,
            "validation_error",
            "name",
        )
        self.assertEqual(
            self.admin.post(
                f"{API}/project-templates", {"project": self.source.pk, "name": "fest", "replace": True}, format="json"
            ).status_code,
            201,
        )
        crew = self.client_for("crew", "Crew")
        self.assertIn(
            crew.post(f"{API}/project-templates", {"project": self.source.pk, "name": "y"}, format="json").status_code,
            {403, 404},
        )

    def test_a_project_from_a_template(self) -> None:
        """``template`` when creating a project fills it, with today's prices."""
        template = self.admin.post(
            f"{API}/project-templates", {"project": self.source.pk, "name": "Fest"}, format="json"
        ).json()
        response = self.admin.post(
            f"{API}/projects",
            {
                "name": "Weinfest",
                "customer": self.source.customer_id,
                "start": "2027-04-20T12:00:00+02:00",
                "end": "2027-04-21T12:00:00+02:00",
                "template": template["id"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(name="Weinfest")
        self.assertEqual(project.material_lines.get().quantity, 4)
        self.assertEqual(project.crew_lines.count(), 1)
        self.assertNotIn("template", response.json())


class ReadableNumberApiTests(ApiTestCase):
    def test_the_api_keeps_its_keys(self) -> None:
        """UIX-024 changes the pages only: the API addresses stay with the key."""
        project = make_project()
        self.assertEqual(self.admin.get(f"{API}/projects/{project.pk}").json()["number"], project.number)
