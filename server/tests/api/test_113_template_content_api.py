# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the content of a project template (PRJ-136)."""

from __future__ import annotations

from rentalars.accounts.models import Role
from rentalars.projects.models import OpenItem
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, add_line, at, job_function, make_project, make_stock, plan

PHASE = {"kind": "setup", "own_period": True, "start": 0, "end": 3600}


class TemplateContentApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("T-001", 10, "Lautsprecher", price="20.00")
        self.source = make_project("Stadtfest", start=at(10, 12), end=at(11, 12))
        self.stage = add_group(self.source, "Bühne")
        add_line(self.source, self.speaker, 4, group=self.stage)
        self.tech = job_function("Tontechnik", price="40.00")
        plan(self.source, self.tech)
        OpenItem.objects.create(project=self.source, text="Strom klären")
        created = self.admin.post(
            f"{API}/project-templates", {"project": self.source.pk, "name": "Fest"}, format="json"
        )
        self.base = f"{API}/project-templates/{created.json()['id']}/content"

    def content(self) -> dict:
        return self.admin.get(self.base).json()

    def test_read_the_content_with_keys(self) -> None:
        body = self.content()
        for section in ("groups", "lines", "crew", "vehicles", "phases"):
            self.assertTrue(all("key" in entry for entry in body[section]), section)
        self.assertEqual(body["open_items"], ["Strom klären"])

    def test_add_change_move_and_delete_entries(self) -> None:
        cable = make_stock("K-001", 50, "Kabel", price="2.00")
        response = self.admin.post(
            f"{self.base}/lines",
            {"product": cable.pk, "quantity": 20, "group": self.content()["groups"][0]["key"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        key = response.json()["key"]
        line = f"{self.base}/lines/{key}"
        # Only what is sent is changed.
        self.assertEqual(self.admin.patch(line, {"quantity": 30}, format="json").status_code, 200)
        entry = next(e for e in self.content()["lines"] if e["key"] == key)
        self.assertEqual((entry["quantity"], entry["product"]), ("30.00", cable.pk))
        self.assertEqual(self.admin.post(f"{line}/move", {"direction": "up"}, format="json").status_code, 200)
        self.assertEqual(self.content()["lines"][0]["key"], key)
        self.assertEqual(self.admin.delete(line).status_code, 204)
        self.assertNotIn(key, [e["key"] for e in self.content()["lines"]])
        self.assert_error(self.admin.delete(line), 404, "not_found")

    def test_groups_and_phases(self) -> None:
        group = self.admin.post(
            f"{self.base}/groups", {"name": "Licht", "parent": self.content()["groups"][0]["key"]}, format="json"
        )
        self.assertEqual(group.status_code, 201, group.content)
        phase = self.admin.post(
            f"{self.base}/phases", {"kind": "setup", "own_period": True, "start": 0, "end": 3600}, format="json"
        )
        self.assertEqual(phase.status_code, 201, phase.content)
        crew = self.content()["crew"][0]["key"]
        self.assertEqual(self.admin.patch(f"{self.base}/crew/{crew}", {"phase": 0}, format="json").status_code, 200)
        self.assertEqual(self.content()["crew"][0]["phase"], 0)
        self.admin.delete(f"{self.base}/phases/{phase.json()['key']}")
        self.assertIsNone(self.content()["crew"][0]["phase"])
        # A group holding a line: its content moves up, or goes with it.
        stage = self.content()["groups"][0]["key"]
        self.admin.delete(f"{self.base}/groups/{stage}")
        self.assertIsNone(self.content()["lines"][0]["group"])

    def test_delete_a_group_with_its_content(self) -> None:
        stage = self.content()["groups"][0]["key"]
        self.admin.delete(f"{self.base}/groups/{stage}?with_content=true")
        body = self.content()
        self.assertEqual((body["groups"], body["lines"]), ([], []))

    def test_open_items_are_guarded_by_their_text(self) -> None:
        self.assertEqual(
            self.admin.post(f"{self.base}/open_items", {"text": "Hotel"}, format="json").json(), {"key": 1}
        )
        self.assert_error(
            self.admin.patch(f"{self.base}/open_items/0", {"text": "x", "expect": "anderer Text"}, format="json"),
            404,
            "not_found",
        )
        self.assertEqual(
            self.admin.patch(
                f"{self.base}/open_items/0", {"text": "Strom bestellen", "expect": "Strom klären"}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(self.content()["open_items"], ["Strom bestellen", "Hotel"])
        self.assertEqual(self.admin.delete(f"{self.base}/open_items/1?expect=Hotel").status_code, 204)
        self.assertEqual(self.content()["open_items"], ["Strom bestellen"])

    def test_notes(self) -> None:
        response = self.admin.put(f"{self.base}/notes", {"notes": "Bitte prüfen", "rental_days": 3}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["notes"], response.json()["rental_days"]), ("Bitte prüfen", 3))

    def test_replace_everything(self) -> None:
        body = self.content()
        body["open_items"] = ["Neu"]
        body["lines"] = []
        self.assertEqual(self.admin.put(self.base, body, format="json").status_code, 200)
        self.assertEqual((self.content()["open_items"], self.content()["lines"]), (["Neu"], []))
        body["groups"][0]["parent"] = 999
        self.assert_error(self.admin.put(self.base, body, format="json"), 400, "validation_error")
        self.assertEqual(self.content()["open_items"], ["Neu"])

    def test_errors(self) -> None:
        self.assert_error(
            self.admin.post(f"{self.base}/lines", {"quantity": 1}, format="json"), 400, "validation_error"
        )
        self.assert_error(
            self.admin.post(f"{self.base}/crew", {"job_function": 99999}, format="json"), 400, "validation_error"
        )
        self.assertEqual(self.admin.post(f"{self.base}/things", {}, format="json").status_code, 404)
        self.assert_error(self.admin.patch(f"{self.base}/groups/999", {"name": "x"}, format="json"), 404, "not_found")
        key = self.content()["groups"][0]["key"]
        self.assert_error(
            self.admin.post(f"{self.base}/groups/{key}/move", {"direction": "sideways"}, format="json"),
            400,
            "validation_error",
        )
        self.assert_error(
            self.admin.post(f"{self.base}/groups/999/move", {"direction": "up"}, format="json"), 404, "not_found"
        )

    def test_rights(self) -> None:
        reader = self.client_for("leser", "Nur Projekte")
        self.assertIn(reader.get(self.base).status_code, {200, 403})
        crew = self.client_for("crew", "Crew")
        self.assertEqual(crew.post(f"{self.base}/open_items", {"text": "x"}, format="json").status_code, 403)
        self.assertEqual(self.content()["open_items"], ["Strom klären"])

    def test_the_template_itself_is_changed_with_patch_only(self) -> None:
        url = self.base.removesuffix("/content")
        self.assertEqual(self.admin.put(url, {"name": "x"}, format="json").status_code, 405)
        self.assertEqual(self.admin.patch(url, {"name": "Fest 2"}, format="json").status_code, 200)

    def planner(self, with_prices: bool):
        Role.objects.create(
            name="Planer mit Preisen" if with_prices else "Planer ohne Preise",
            module_levels={"projects": 2, "material": 1},
            special_rights=["prices"] if with_prices else [],
        )
        return self.client_for("planer", "Planer mit Preisen" if with_prices else "Planer ohne Preise")

    def test_prices_are_read_only_by_who_may_see_prices(self) -> None:
        free = self.admin.post(
            f"{self.base}/lines", {"title": "Pauschale", "quantity": 1, "unit_price": "99.00"}, format="json"
        )
        self.assertEqual(free.status_code, 201, free.content)
        group_key = self.content()["groups"][0]["key"]
        self.admin.patch(f"{self.base}/groups/{group_key}", {"flat_price": "500.00"}, format="json")
        self.assertIn("99.00", str(self.content()))
        template_url = self.base.removesuffix("/content")
        blind = self.planner(with_prices=False)
        for response in (blind.get(self.base), blind.get(template_url), blind.get(f"{API}/project-templates")):
            self.assertEqual(response.status_code, 200, response.content)
            self.assertNotIn("99.00", response.content.decode())
            self.assertNotIn("500.00", response.content.decode())
        # What they write does not touch the prices, and their answers do not show them either.
        changed = blind.put(self.base, blind.get(self.base).json(), format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertNotIn("99.00", changed.content.decode())
        self.assertIn("99.00", str(self.content()))
        self.assertIn("500.00", str(self.content()))

    def test_the_planned_hours_fit_into_the_field_of_the_project(self) -> None:
        crew = self.content()["crew"][0]["key"]
        too_many = self.admin.patch(f"{self.base}/crew/{crew}", {"planned_hours": "100000"}, format="json")
        self.assert_error(too_many, 400, "validation_error")
        self.assertEqual(
            self.admin.patch(f"{self.base}/crew/{crew}", {"planned_hours": "99999.99"}, format="json").status_code, 200
        )

    def test_a_key_is_not_given_twice(self) -> None:
        added = self.admin.post(f"{self.base}/phases", PHASE, format="json").json()["key"]
        self.assertEqual(self.admin.delete(f"{self.base}/phases/{added}").status_code, 204)
        again = self.admin.post(f"{self.base}/phases", PHASE, format="json").json()["key"]
        self.assertGreater(again, added)
        # A page that still shows the deleted entry changes nothing now.
        self.assert_error(
            self.admin.patch(f"{self.base}/phases/{added}", {"title": "x"}, format="json"), 404, "not_found"
        )
        # The counter survives a replacement of the whole content.
        body = self.content()
        body["phases"] = []
        self.admin.put(self.base, body, format="json")
        after = self.admin.post(f"{self.base}/phases", PHASE, format="json").json()["key"]
        self.assertGreater(after, again)

    def test_two_changes_of_different_fields_do_not_undo_each_other(self) -> None:
        key = self.content()["lines"][0]["key"]
        self.admin.patch(f"{self.base}/lines/{key}", {"quantity": 7}, format="json")
        self.admin.patch(f"{self.base}/lines/{key}", {"note": "Hinten links"}, format="json")
        entry = next(e for e in self.content()["lines"] if e["key"] == key)
        self.assertEqual((entry["quantity"], entry["note"]), ("7.00", "Hinten links"))
