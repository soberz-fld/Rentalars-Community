# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: packlist, ticking, issue and return (PCK)."""

from __future__ import annotations

from rentalars.accounts.models import Role
from rentalars.material.models import MaterialItem
from rentalars.projects.models import Project
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, add_line, make_item, make_model, make_product, make_project, make_stock


class PacklistTests(ApiTestCase):
    """The whole way of a packlist: pack, issue, return (PCK-001 to PCK-021)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9, "XLR-Kabel 5 m", price="1.50")
        self.rack_product = make_product("T-500", "Funkrack", price="140.00")
        self.rack = make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.project = make_project()
        sound = add_group(self.project, "Ton FOH")
        self.cable_line = add_line(self.project, self.cable, 3, group=sound, note="Bitte gebündelt").line
        self.rack_line = add_line(self.project, self.rack_product, 1, group=sound).line
        listing = self.admin.get(f"{API}/projects/{self.project.pk}/packlists").json()
        self.base = f"{API}/projects/{self.project.pk}/packlists/{listing[0]['id']}"

    def rows(self, client: object = None) -> dict[str, dict[str, object]]:
        """The rows of the packlist by article number."""
        document = (client or self.admin).get(self.base).json()  # type: ignore[attr-defined]
        return {row["article_number"]: row for section in document["sections"] for row in section["rows"]}

    def test_packlist_follows_the_lines_grouped_and_without_prices(self) -> None:
        """PCK-001, PCK-002, PCK-007."""
        response = self.admin.get(self.base)
        document = response.json()
        self.assertEqual(document["status"], "open")
        self.assertEqual([section["name"] for section in document["sections"]], ["Ton FOH"])
        rows = self.rows()
        self.assertEqual(rows["K-005"]["required"], "3.00")
        self.assertEqual(rows["K-005"]["note"], "Bitte gebündelt")
        text = response.content.decode()
        self.assertNotIn("price", text)
        self.assertNotIn("1.50", text)
        self.assertNotIn("140.00", text)

    def test_packlist_changes_with_the_planning_until_it_is_issued(self) -> None:
        """PCK-001: no separate copy that could get out of date."""
        self.admin.patch(
            f"{API}/projects/{self.project.pk}/material-lines/{self.cable_line.pk}", {"quantity": "5"}, format="json"
        )
        self.assertEqual(self.rows()["K-005"]["required"], "5.00")

    def test_ticking_a_row_needs_no_item_and_no_scan(self) -> None:
        """PCK-009, PCK-020."""
        body = {"line": self.cable_line.pk, "product": self.cable.pk, "packed": "3"}
        response = self.admin.patch(f"{self.base}/rows", body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "in_progress")
        self.assertEqual(response.json()["progress_percent"], 75)
        self.assertEqual(self.rows()["K-005"]["packed"], "3.00")
        # More than planned cannot be packed: the quantity is limited to what the line needs.
        self.admin.patch(f"{self.base}/rows", {**body, "packed": "4"}, format="json")
        self.assertEqual(self.rows()["K-005"]["packed"], "3.00")
        unknown_row = self.admin.patch(
            f"{self.base}/rows", {"line": 999999, "product": self.cable.pk, "packed": "1"}, format="json"
        )
        self.assert_error(unknown_row, 400, "validation_error")

    def test_issue_books_the_material_out_and_allocates_single_items(self) -> None:
        """PCK-014, PCK-021."""
        self.assertEqual(self.admin.post(f"{self.base}/pack-all").json()["status"], "packed")
        issued = self.admin.post(f"{self.base}/issue")
        self.assertEqual(issued.status_code, 200, issued.content)
        self.assertEqual(issued.json()["status"], "issued")
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "out")
        self.assertEqual(self.rows()["T-500"]["allocated_items"], ["0500"])
        self.assertEqual(MaterialItem.objects.get(pk=self.rack.pk).status, "in_use")
        history = self.admin.get(f"{API}/material-items/{self.rack.pk}/history").json()
        self.assertIn(self.project.pk, [row["project"] for row in history])

    def test_issue_of_ticked_rows_only(self) -> None:
        """PCK-014: a partial issue leaves the rest in the warehouse."""
        self.admin.patch(
            f"{self.base}/rows", {"line": self.cable_line.pk, "product": self.cable.pk, "packed": "2"}, format="json"
        )
        self.admin.post(f"{self.base}/issue", {"only_packed": True}, format="json")
        rows = self.rows()
        self.assertEqual(rows["K-005"]["issued"], "2.00")
        self.assertEqual(rows["T-500"]["issued"], "0.00")

    def test_issued_material_blocks_changes_to_its_lines(self) -> None:
        self.admin.post(f"{self.base}/issue", {"only_packed": False}, format="json")  # PCK-025: everything
        response = self.admin.delete(f"{API}/projects/{self.project.pk}/material-lines/{self.cable_line.pk}")
        self.assert_error(response, 400, "validation_error")

    def test_issue_can_be_taken_back_if_nothing_returned_yet(self) -> None:
        self.admin.post(f"{self.base}/issue", {"only_packed": False}, format="json")  # PCK-025: everything
        undone = self.admin.post(f"{self.base}/undo-issue")
        self.assertEqual(undone.status_code, 200, undone.content)
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "confirmed")
        self.assertEqual(MaterialItem.objects.get(pk=self.rack.pk).status, "available")

    def test_return_with_missing_parts_must_be_clarified(self) -> None:
        """PCK-016, PCK-019."""
        self.admin.post(f"{self.base}/issue", {"only_packed": False}, format="json")  # PCK-025: everything
        body = {"line": self.cable_line.pk, "product": self.cable.pk, "returned": "2"}
        self.assertEqual(self.admin.patch(f"{self.base}/rows", body, format="json").status_code, 200)
        self.admin.patch(
            f"{self.base}/rows",
            {"line": self.rack_line.pk, "product": self.rack_product.pk, "returned": "1"},
            format="json",
        )
        self.assertEqual(self.rows()["K-005"]["missing"], "1.00")

        blocked = self.admin.post(f"{self.base}/complete-return")
        self.assert_error(blocked, 400, "validation_error")
        also_blocked = self.admin.post(
            f"{API}/projects/{self.project.pk}/status", {"status": "returned"}, format="json"
        )
        self.assert_error(also_blocked, 400, "validation_error")

        without_note = self.admin.post(
            f"{self.base}/resolve-missing",
            {"line": self.cable_line.pk, "product": self.cable.pk, "note": ""},
            format="json",
        )
        self.assert_error(without_note, 400, "validation_error")
        resolved = self.admin.post(
            f"{self.base}/resolve-missing",
            {
                "line": self.cable_line.pk,
                "product": self.cable.pk,
                "note": "Ein Kabel beim Kunden vergessen, wird nachgeliefert",
            },
            format="json",
        )
        self.assertEqual(resolved.status_code, 200, resolved.content)
        done = self.admin.post(f"{self.base}/complete-return")
        self.assertEqual(done.json()["status"], "returned")
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "returned")
        self.assertEqual(MaterialItem.objects.get(pk=self.rack.pk).status, "available")

    def test_everything_back_with_one_call(self) -> None:
        self.admin.post(f"{self.base}/issue", {"only_packed": False}, format="json")  # PCK-025: everything
        self.assertEqual(self.admin.post(f"{self.base}/return-all").json()["return_percent"], 100)
        self.assertEqual(self.admin.post(f"{self.base}/complete-return").json()["status"], "returned")

    def test_unknown_step_is_rejected(self) -> None:
        self.assert_error(self.admin.post(f"{self.base}/explode"), 400, "validation_error")

    def test_pdf_is_delivered(self) -> None:
        """PCK-003, DOK-001."""
        response = self.admin.get(f"{self.base}/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(self.project.number, response["Content-Disposition"])

    def test_warehouse_packs_without_the_right_to_edit_projects(self) -> None:
        """AUT-013: packing is a module of its own."""
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(warehouse.post(f"{self.base}/pack-all").status_code, 200)
        self.assertEqual(warehouse.post(f"{self.base}/issue").status_code, 200)
        refused = warehouse.patch(f"{API}/projects/{self.project.pk}", {"name": "Umbenannt"}, format="json")
        self.assert_error(refused, 403, "permission_denied")

    def test_reading_the_packlist_does_not_allow_ticking(self) -> None:
        Role.objects.create(name="Fahrer", module_levels={"packing": 1})
        driver = self.client_for("fritz", "Fahrer")
        self.assertEqual(driver.get(self.base).status_code, 200)
        self.assert_error(driver.post(f"{self.base}/pack-all"), 403, "permission_denied")
        self.assert_error(driver.get(f"{API}/projects/{self.project.pk}"), 403, "permission_denied")
