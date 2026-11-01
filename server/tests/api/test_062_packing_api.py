# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the issue per article (PCK-025): ``issue`` books what is ticked unless told otherwise."""

from __future__ import annotations

from rentalars.projects.models import Project
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, make_item, make_model, make_product, make_project, make_stock


class IssuePerArticleApiTests(ApiTestCase):
    """Six cables and a single rack; ``POST …/issue`` with and without ``only_packed``."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9, "XLR-Kabel 5 m")
        self.rack_product = make_product("T-500", "Funkrack")
        make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.project = make_project()
        self.cable_line = add_line(self.project, self.cable, 6).line
        self.rack_line = add_line(self.project, self.rack_product, 1).line
        listing = self.admin.get(f"{API}/projects/{self.project.pk}/packlists").json()
        self.base = f"{API}/projects/{self.project.pk}/packlists/{listing[0]['id']}"

    def tick_cables(self, quantity: str) -> dict:
        body = {"line": self.cable_line.pk, "product": self.cable.pk, "packed": quantity}
        return self.admin.patch(f"{self.base}/rows", body, format="json").json()

    def rows(self, document: dict) -> dict[str, dict]:
        return {row["article_number"]: row for section in document["sections"] for row in section["rows"]}

    def project_status(self) -> str:
        return Project.objects.get(pk=self.project.pk).status

    def test_issue_books_what_is_ticked_by_default(self) -> None:
        ticked = self.tick_cables("4")
        self.assertEqual((ticked["ready_to_issue"], ticked["not_issued"]), ("4.00", "7.00"))
        response = self.admin.post(f"{self.base}/issue")
        self.assertEqual(response.status_code, 200, response.content)
        document = response.json()
        self.assertEqual(document["status"], "partly_issued")
        rows = self.rows(document)
        self.assertEqual((rows["K-005"]["issued"], rows["T-500"]["issued"]), ("4.00", "0.00"))
        self.assertEqual((document["ready_to_issue"], document["not_issued"]), ("0.00", "3.00"))
        self.assertEqual(self.project_status(), "confirmed")
        # Packing goes on: the rest is ticked and issued later; then the project is out.
        self.tick_cables("6")
        self.admin.patch(
            f"{self.base}/rows",
            {"line": self.rack_line.pk, "product": self.rack_product.pk, "packed": "1"},
            format="json",
        )
        self.assertEqual(self.rows(self.admin.get(self.base).json())["K-005"]["ready_to_issue"], "2.00")
        issued = self.admin.post(f"{self.base}/issue", {"only_packed": True}, format="json").json()
        self.assertEqual(issued["status"], "issued")
        self.assertEqual(self.project_status(), "out")

    def test_issue_everything_with_only_packed_false(self) -> None:
        self.tick_cables("2")
        response = self.admin.post(f"{self.base}/issue", {"only_packed": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "issued")
        self.assertEqual(self.rows(response.json())["K-005"]["issued"], "6.00")
        self.assertEqual(self.project_status(), "out")

    def test_only_packed_false_as_a_form_field(self) -> None:
        response = self.admin.post(f"{self.base}/issue", {"only_packed": "false"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "issued")

    def test_nothing_ticked_is_refused(self) -> None:
        response = self.admin.post(f"{self.base}/issue", {}, format="json")
        error = self.assert_error(response, 400, "validation_error")
        self.assertIn("Hake ab, was rausgeht, oder gib alles aus.", error["message"])
        self.assertEqual(self.project_status(), "confirmed")

    def test_the_description_names_the_default(self) -> None:
        description = self.admin.get(f"{API}/schema?format=json").json()
        action = description["components"]["schemas"]["PacklistActionRequest"]["properties"]["only_packed"]
        self.assertEqual(action["default"], True)
        self.assertIn("PCK-025", action["description"])
