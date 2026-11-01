# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the packlists of stage 5 (PCK-008, PCK-013, PCK-015, PCK-017, PCK-018, PCK-022, MAT-042)."""

from __future__ import annotations

from rentalars.material.models import ConnectionType, MaterialItem
from rentalars.material.services import install_item
from rentalars.packing import services
from rentalars.projects.models import MaterialLine
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, make_item, make_model, make_product, make_project, make_stock


class PacklistApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.cables = make_stock("K-005", 10)
        self.lights = make_stock("L-010", 4)
        self.cable_line = add_line(self.project, self.cables, 6).line
        self.light_line = add_line(self.project, self.lights, 2).line
        self.url = f"{API}/projects/{self.project.pk}/packlists"

    def test_several_packlists(self) -> None:
        created = self.admin.post(self.url, {"title": "LKW 2", "note": "Rampe 2"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        truck = created.json()["id"]
        listed = self.admin.get(self.url).json()
        self.assertEqual([(entry["is_main"], entry["title"]) for entry in listed], [(True, ""), (False, "LKW 2")])
        moved = self.admin.post(f"{self.url}/{truck}/lines", {"lines": [self.light_line.pk]}, format="json")
        self.assertEqual(moved.json(), {"moved": 1})
        detail = self.admin.get(f"{self.url}/{truck}", {"order": "category"}).json()
        self.assertEqual(detail["sections"][0]["rows"][0]["article_number"], "L-010")
        self.assertEqual(
            self.admin.patch(f"{self.url}/{truck}", {"title": "LKW 3"}, format="json").json()["title"], "LKW 3"
        )
        self.assert_error(
            self.admin.post(f"{self.url}/{truck}/lines", {"lines": "x"}, format="json"), 400, "validation_error"
        )
        main = listed[0]["id"]
        self.admin.post(f"{self.url}/{main}/lines", {"lines": [self.light_line.pk]}, format="json")
        self.assertEqual(self.admin.delete(f"{self.url}/{truck}").status_code, 204)
        self.assert_error(self.admin.delete(f"{self.url}/{main}"), 400, "validation_error")

    def test_items_partial_issue_changes_addendum_defect(self) -> None:
        main = services.get_packlist(self.project).pk
        choices = self.admin.get(
            f"{self.url}/{main}/items", {"line": self.light_line.pk, "product": self.lights.pk}
        ).json()
        self.assertEqual(len(choices), 4)
        chosen = self.admin.put(
            f"{self.url}/{main}/items",
            {"line": self.light_line.pk, "product": self.lights.pk, "items": [choices[0]["id"]]},
            format="json",
        ).json()
        light_row = next(row for row in chosen["sections"][0]["rows"] if row["product"] == self.lights.pk)
        self.assertEqual(light_row["chosen_items"][0]["issued"], False)

        self.admin.patch(
            f"{self.url}/{main}/rows",
            {"line": self.cable_line.pk, "product": self.cables.pk, "packed": 3},
            format="json",
        )
        issued = self.admin.post(f"{self.url}/{main}/issue", {"only_packed": True}, format="json").json()
        self.assertEqual(issued["status"], "partly_issued")

        MaterialLine.objects.filter(pk=self.cable_line.pk).update(quantity=7)
        self.assertTrue(self.admin.get(f"{self.url}/{main}").json()["has_changes"])
        acknowledged = self.admin.post(f"{self.url}/{main}/acknowledge-changes", {}, format="json").json()
        self.assertFalse(acknowledged["has_changes"])

        tape = make_stock("V-001", 20, "Gaffa")
        added = self.admin.post(f"{self.url}/{main}/add-material", {"product": tape.pk, "quantity": 2}, format="json")
        self.assertEqual(added.status_code, 200, added.content)
        self.assertTrue(MaterialLine.objects.get(product=tape).is_addendum)

        item = MaterialItem.objects.for_product(self.cables.pk).first()
        defect = self.admin.post(
            f"{self.url}/{main}/report-defect", {"item": item.pk, "description": "Stecker ab"}, format="json"
        )
        self.assertEqual(defect.status_code, 200, defect.content)


class ExtractionApiTests(ApiTestCase):
    """MAT-042 through the API."""

    def test_take_out_and_cancel(self) -> None:
        case_product = make_product("S-600", "Funkcase")
        case = make_item(make_model("Case", case_product), 600)
        receiver = make_item(make_model("Empfänger", make_product("T-050")), 311)
        install_item(receiver, case, connection_type=ConnectionType.LOOSE)
        project = make_project()
        add_line(project, case_product, 1)
        url = f"{API}/projects/{project.pk}/extractions"
        created = self.admin.post(url, {"item": receiver.pk}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["container_display_id"], "0600")
        self.assertEqual(len(self.admin.get(url).json()), 1)
        self.assert_error(self.admin.post(url, {"item": receiver.pk}, format="json"), 400, "validation_error")
        self.assertEqual(self.admin.delete(f"{url}/{created.json()['id']}").status_code, 204)
