# SPDX-License-Identifier: GPL-3.0-or-later
"""API of nested groups (PRJ-037): ``parent`` on groups, moving, copying, totals and the planning."""

from __future__ import annotations

from rentalars.projects.models import Group, MaterialLine
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, add_line, make_product, make_project


class NestedGroupApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=1)
        self.base = f"{API}/projects/{self.project.pk}"
        self.lamp = make_product("L-010", "PAR 64", price="100.00", billing_mode="flat")

    def create(self, name: str, **fields: object) -> dict[str, object]:
        response = self.admin.post(f"{self.base}/groups", {"name": name, **fields}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        return response.json()

    def test_parent_is_writable_and_positions_count_among_siblings(self) -> None:
        light = self.create("Licht")
        front = self.create("Front", parent=light["id"])
        rear = self.create("Rear", parent=light["id"], discount_percent="10")
        self.assertEqual((front["parent"], front["position"], rear["position"]), (light["id"], 1, 2))
        sound = self.create("Ton")
        self.assertEqual((sound["parent"], sound["position"]), (None, 2))
        listed = self.admin.get(f"{self.base}/groups").json()
        self.assertEqual([group["name"] for group in listed], ["Licht", "Front", "Rear", "Ton"])

        # Changing the parent moves the group to the end of the other group's subgroups.
        moved = self.admin.patch(f"{self.base}/groups/{sound['id']}", {"parent": light["id"]}, format="json")
        self.assertEqual(moved.status_code, 200, moved.json())
        self.assertEqual((moved.json()["parent"], moved.json()["position"]), (light["id"], 3))
        back = self.admin.patch(f"{self.base}/groups/{sound['id']}", {"parent": None}, format="json")
        self.assertEqual((back.json()["parent"], back.json()["position"]), (None, 2))

    def test_rules_are_answered_in_the_uniform_error_format(self) -> None:
        light = self.create("Licht")
        front = self.create("Front", parent=light["id"])
        truss = self.create("Traverse 1", parent=front["id"])
        too_deep = self.admin.post(f"{self.base}/groups", {"name": "Zu tief", "parent": truss["id"]}, format="json")
        self.assert_error(too_deep, 400, "validation_error", "parent")
        inside_itself = self.admin.patch(f"{self.base}/groups/{light['id']}", {"parent": front["id"]}, format="json")
        self.assert_error(inside_itself, 400, "validation_error", "parent")
        foreign = add_group(make_project("Anderes"), "Fremd")
        other_project = self.admin.post(f"{self.base}/groups", {"name": "X", "parent": foreign.pk}, format="json")
        self.assert_error(other_project, 400, "validation_error", "parent")
        missing = self.admin.post(f"{self.base}/groups/{front['id']}/move", {}, format="json")
        self.assert_error(missing, 400, "validation_error", "parent")
        bad_place = self.admin.post(
            f"{self.base}/groups/{front['id']}/move", {"parent": None, "position": 0}, format="json"
        )
        self.assert_error(bad_place, 400, "validation_error", "position")
        self.assertEqual(Group.objects.get(pk=light["id"]).parent, None)

    def test_moving_with_a_place(self) -> None:
        light = self.create("Licht")
        front = self.create("Front", parent=light["id"])
        sound = self.create("Ton")
        response = self.admin.post(
            f"{self.base}/groups/{sound['id']}/move", {"parent": light["id"], "position": 1}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual((response.json()["parent"], response.json()["position"]), (light["id"], 1))
        self.assertEqual(Group.objects.get(pk=front["id"]).position, 2)
        out = self.admin.post(f"{self.base}/groups/{front['id']}/move", {"parent": None, "position": 1}, format="json")
        self.assertEqual((out.json()["parent"], out.json()["position"]), (None, 1))
        self.assertEqual(
            [group["name"] for group in self.admin.get(f"{self.base}/groups").json()], ["Front", "Licht", "Ton"]
        )

    def test_totals_and_planning_show_the_hierarchy(self) -> None:
        light = self.create("Licht", discount_percent="5")
        front = self.create("Front", parent=light["id"])
        add_line(self.project, self.lamp, 2, group=Group.objects.get(pk=light["id"]))
        add_line(self.project, self.lamp, 3, group=Group.objects.get(pk=front["id"]))
        totals = self.admin.get(f"{self.base}/totals").json()
        by_name = {group["name"]: group for group in totals["groups"]}
        self.assertEqual(
            (by_name["Licht"]["subtotal"], by_name["Licht"]["depth"], by_name["Front"]["parent"]),
            ("475.00", 0, light["id"]),
        )
        self.assertEqual(totals["groups_total"], "475.00")
        planning = self.admin.get(f"{self.base}/planning").json()
        self.assertEqual(
            [(group["name"], group["parent"]) for group in planning["groups"]],
            [("Licht", None), ("Front", light["id"])],
        )
        overview = self.admin.get(f"{API}/projects/{self.project.pk}/price-overview?detail=groups").json()
        self.assertEqual(
            [(group["path"], group["subtotal"]) for group in overview["groups"]],
            [("Licht", "475.00"), ("Licht › Front", "300.00")],
        )

    def test_copy_and_delete_take_the_subgroups_along(self) -> None:
        light = self.create("Licht")
        front = self.create("Front", parent=light["id"])
        add_line(self.project, self.lamp, 1, group=Group.objects.get(pk=front["id"]))
        copied = self.admin.post(f"{self.base}/groups/{light['id']}/copy", {}, format="json")
        self.assertEqual(copied.status_code, 201, copied.json())
        self.assertEqual(Group.objects.get(parent_id=copied.json()["id"]).name, "Front")
        self.assertEqual(self.admin.delete(f"{self.base}/groups/{light['id']}").status_code, 204)
        front_now = Group.objects.get(pk=front["id"])
        self.assertEqual((front_now.parent, front_now.position), (None, 1))
        self.assertEqual(self.admin.delete(f"{self.base}/groups/{copied.json()['id']}?lines=delete").status_code, 204)
        self.assertEqual(Group.objects.filter(project=self.project).count(), 1)
        self.assertEqual(MaterialLine.objects.filter(project=self.project).count(), 1)

    def test_lines_go_into_a_subgroup(self) -> None:
        light = self.create("Licht")
        front = self.create("Front", parent=light["id"])
        response = self.admin.post(
            f"{self.base}/material-lines",
            {"product": self.lamp.pk, "quantity": "2", "group": front["id"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())
        layout = [{"group": light["id"], "lines": [response.json()["id"]]}]
        self.assertEqual(self.admin.post(f"{self.base}/arrange", {"layout": layout}, format="json").status_code, 204)
        self.assertEqual(MaterialLine.objects.get(pk=response.json()["id"]).group_id, light["id"])
