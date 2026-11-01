# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "fixes" (API-014): what the time entry form offers is never without a job function
(ZEI-007) – also for the companion app's token –, and products that are no service have no switch for the surcharges
for night, Sunday and holidays (PER-009, PER-040); crew packs in its own projects, without adding material.
"""

from __future__ import annotations

import datetime
from typing import Any

from rentalars.accounts.models import Role
from rentalars.material.models import MaterialItem
from rentalars.personnel.models import JobFunction
from rentalars.products.models import Product
from rentalars.projects.models import MaterialLine
from rentalars.timetracking.models import TimeEntry
from tests.api.base import API, ApiTestCase
from tests.api.test_070_packing_api import PacklistApiTestCase
from tests.helpers import (
    NOW,
    at,
    job_function,
    make_internal_project,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    set_clock,
)

ENTRIES = f"{API}/time-entries"
#: The modules of the token the companion app makes (packing, projects, time tracking, e-mail).
COMPANION_MODULES = ["packing", "projects", "time_tracking", "email"]


def every_active() -> list[str]:
    return sorted(JobFunction.objects.filter(is_active=True).values_list("name", flat=True), key=str.lower)


class ChoicesApiTests(ApiTestCase):
    """ZEI-007: ``GET /time-entries/choices`` – ``job_functions`` is never empty."""

    def setUp(self) -> None:
        super().setUp()
        # A project running now, without phases and without crew lines.
        self.project = make_project("Messe", start=at(1), end=at(3))
        self.sound = job_function("Tontechnik", price="45.00", guide="30.00")
        self.kai_user = make_user("kai", roles=("Projektleitung",))
        self.kai = make_person("Kai Kurz", user=self.kai_user)  # no job function of his own
        self.kai_client = self.client_of(self.kai_user, allowed_modules=COMPANION_MODULES)

    def choice_of(self, choices: list[dict], project_id: int | None) -> dict:
        return next(choice for choice in choices if choice["project"] == project_id)

    def test_a_project_without_phases_and_crew_offers_every_active_job_function(self) -> None:
        response = self.kai_client.get(f"{ENTRIES}/choices")
        self.assertEqual(response.status_code, 200, response.content)
        choices = response.json()
        messe = self.choice_of(choices, self.project.pk)
        self.assertEqual([function["name"] for function in messe["job_functions"]], every_active())
        self.assertEqual((messe["crew_lines"], messe["suggested_job_function"]), ([], None))
        # Without project (ZEI-023): his own job functions – he has none, so every active one as well.
        self.assertEqual([function["name"] for function in choices[-1]["job_functions"]], every_active())
        # And the time can be recorded with one of them.
        body = {
            "project": self.project.pk,
            "job_function": self.sound.pk,
            "start": (NOW - datetime.timedelta(hours=3)).isoformat(),
            "end": (NOW - datetime.timedelta(hours=1)).isoformat(),
        }
        created = self.kai_client.post(ENTRIES, body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(TimeEntry.objects.get().job_function, self.sound)

    def test_the_crew_functions_of_the_project_come_after_the_own_ones(self) -> None:
        plan(self.project, job_function("Lichttechnik"), make_person("Tom Richter", rates={"Lichttechnik": "30.00"}))
        anna_user = make_user("anna", roles=("Projektleitung",))
        make_person("Anna Becker", rates={"Stagehand": "20.00"}, user=anna_user)
        choices = self.client_of(anna_user, allowed_modules=COMPANION_MODULES).get(f"{ENTRIES}/choices").json()
        messe = self.choice_of(choices, self.project.pk)
        self.assertEqual([function["name"] for function in messe["job_functions"]], ["Stagehand", "Lichttechnik"])
        self.assertEqual([function["name"] for function in choices[-1]["job_functions"]], ["Stagehand"])
        # A job function neither her own nor of the project's crew is still refused.
        body = {
            "project": self.project.pk,
            "job_function": self.sound.pk,
            "start": (NOW - datetime.timedelta(hours=3)).isoformat(),
            "end": (NOW - datetime.timedelta(hours=1)).isoformat(),
        }
        refused = self.client_of(anna_user).post(ENTRIES, body, format="json")
        self.assert_error(refused, 400, "validation_error", "job_function")

    def test_crew_on_an_internal_project_with_the_token_of_the_companion_app(self) -> None:
        """The case from the mobile app: crew without own job functions books on the warehouse project, which has no crew."""
        warehouse = make_internal_project()
        lea_user = make_user("lea", roles=("Crew",))
        make_person("Lea Vogel", user=lea_user)
        app = self.client_of(lea_user, allowed_modules=COMPANION_MODULES)
        choices = app.get(f"{ENTRIES}/choices").json()
        self.assertEqual(
            [function["name"] for function in self.choice_of(choices, warehouse.pk)["job_functions"]], every_active()
        )
        body = {
            "project": warehouse.pk,
            "job_function": self.sound.pk,
            "start": (NOW - datetime.timedelta(hours=2)).isoformat(),
            "end": NOW.isoformat(),
        }
        self.assertEqual(app.post(ENTRIES, body, format="json").status_code, 201)


class ProductSurchargeSwitchApiTests(ApiTestCase):
    """PER-009: ``time_surcharges`` belongs to services; ``null`` for every other product, ignored if sent."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_product("L-100", "Scheinwerfer")
        self.service = job_function("Tontechnik", price="45.00").service_product

    def test_a_rental_product_has_no_switch(self) -> None:
        url = f"{API}/products/{self.spot.pk}"
        self.assertIsNone(self.admin.get(url).json()["time_surcharges"])
        changed = self.admin.patch(url, {"time_surcharges": False, "name": "Spot"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.json()["name"], changed.json()["time_surcharges"]), ("Spot", None))
        self.spot.refresh_from_db()
        self.assertTrue(self.spot.time_surcharges)  # untouched: it means nothing for a rental product
        # A client that sends back what it read (null) is not refused.
        self.assertEqual(self.admin.patch(url, {"time_surcharges": None}, format="json").status_code, 200)
        listed = self.admin.get(f"{API}/products", {"search": "L-100"}).json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertTrue(all(row["time_surcharges"] is None for row in rows if row["kind"] != "service"))

    def test_a_new_product_that_is_no_service(self) -> None:
        created = self.admin.post(
            f"{API}/products",
            {
                "article_number": "L-200",
                "name": "Transport",
                "category": self.spot.category_id,
                "unit": self.spot.unit_id,
                "tax_rate": self.spot.tax_rate_id,
                "kind": "incidental",
                "billing_mode": "flat",
                "price": "80.00",
                "time_surcharges": False,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertIsNone(created.json()["time_surcharges"])

    def test_a_service_keeps_its_switch(self) -> None:
        url = f"{API}/products/{self.service.pk}"
        self.assertIs(self.admin.get(url).json()["time_surcharges"], True)
        self.assertIs(self.admin.patch(url, {"time_surcharges": None}, format="json").json()["time_surcharges"], True)
        changed = self.admin.patch(url, {"time_surcharges": False}, format="json")
        self.assertIs(changed.json()["time_surcharges"], False)
        self.assertFalse(Product.objects.get(pk=self.service.pk).time_surcharges)
        # Without the price right the field is neither shown nor taken, as before (AUT-019).
        warehouse = self.client_for("luka", "Lager")
        self.assertNotIn("time_surcharges", warehouse.get(url).json())

    def test_the_description_of_the_api_says_services_only(self) -> None:
        description = self.admin.get(f"{API}/schema?format=json").data
        field = description["components"]["schemas"]["Product"]["properties"]["time_surcharges"]
        self.assertTrue(field.get("nullable"))
        self.assertTrue(field["description"].startswith("Services only"))
        # The settings of the surcharges are unchanged.
        response = self.admin.get(f"{API}/settings/surcharges")
        self.assertEqual(response.status_code, 200)
        self.assertIn("rules", response.json())


class CrewPacksApiTests(PacklistApiTestCase):
    """Crew packs in its own projects – every step without financial effect; adding material is not one.

    The requirement: everything that implies writing but has no financial effect is allowed; adding material is not.
    The crew keeps strictly to the packing list; extra material must be added by authorised people.
    """

    def setUp(self) -> None:
        super().setUp()
        set_clock(at(9, 12))
        lea = make_user("lea", roles=("Crew",))
        plan(self.project, job_function("Stagehand"), make_person("Lea Vogel", user=lea))
        self.crew = self.client_of(lea, allowed_modules=COMPANION_MODULES)  # the token of the companion app
        self.rack_item = MaterialItem.objects.get(material_model__default_product=self.rack_product)

    def act(self, action: str, client: Any = None, **body: Any) -> Any:
        return (client or self.crew).post(f"{self.base}/{action}", body, format="json")

    def test_a_new_installation_gives_crew_write_on_packing(self) -> None:
        self.assertEqual(Role.objects.get(name="Crew").module_levels["packing"], 2)
        self.assertEqual(Role.objects.get(name="Freie Kraft").module_levels["packing"], 1)  # unchanged

    def test_every_step_without_financial_effect(self) -> None:
        # Tick, choose items, pack everything.
        self.assertEqual(self.tick("4", client=self.crew).status_code, 200)
        body = {"line": self.rack_line.pk, "product": self.rack_product.pk, "items": [self.rack_item.pk]}
        self.assertEqual(self.crew.put(f"{self.base}/items", body, format="json").status_code, 200)
        self.assertEqual(self.act("pack-all").status_code, 200)
        # A further packing list: create, rename, give it a line, delete it with its line (it goes back).
        packlists = f"{API}/projects/{self.project.pk}/packlists"
        created = self.crew.post(packlists, {"title": "LKW 2"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        other = f"{packlists}/{created.json()['id']}"
        self.assertEqual(self.crew.patch(other, {"title": "LKW 3"}, format="json").status_code, 200)
        moved = self.crew.post(f"{other}/lines", {"lines": [self.rack_line.pk]}, format="json")
        self.assertEqual(moved.json(), {"moved": 1})
        self.assertEqual(self.crew.delete(other).status_code, 204)
        self.assertEqual(MaterialLine.objects.filter(project=self.project).count(), 2)  # no material left the project
        # Issue, take it back, issue again.
        self.assertEqual(self.act("pack-all").status_code, 200)
        self.assertEqual(self.act("issue").status_code, 200, self.act("issue").content)
        self.assertEqual(self.act("undo-issue").status_code, 200)
        self.assertEqual(self.act("issue").json()["status"], "issued")
        # The return: two cables are missing; clarify them, report a defect, complete the return.
        self.assertEqual(self.tick("8", field="returned", client=self.crew).status_code, 200)
        returned = self.crew.patch(
            f"{self.base}/rows",
            {"line": self.rack_line.pk, "product": self.rack_product.pk, "returned": 1},
            format="json",
        )
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(self.act("take-back").status_code, 200)
        missing = self.act("resolve-missing", line=self.cable_line.pk, product=self.cable.pk, note="beim Kunden")
        self.assertEqual(missing.status_code, 200, missing.content)
        self.assertIn("hints", missing.json())  # PCK-019: the answer carries the hint, if there is one
        cable_item = MaterialItem.objects.filter(material_model__default_product=self.cable).first()
        defect = self.act("report-defect", item=cable_item.pk, description="Stecker locker")
        self.assertEqual(defect.status_code, 200, defect.content)
        self.assertEqual(self.act("complete-return").json()["status"], "returned")
        self.assertFalse(MaterialLine.objects.filter(project=self.project, is_addendum=True).exists())

    def test_adding_material_needs_the_right_to_change_the_project(self) -> None:
        refused = self.act("add-material", product=self.cable.pk, quantity="2")
        error = self.assert_error(refused, 403, "needs_project_write")
        self.assertEqual(
            error["message"],
            "Material nachtragen dürfen nur Personen, die das Projekt ändern dürfen oder für alle Projekte packen.",
        )
        self.assertFalse(MaterialLine.objects.filter(project=self.project, is_addendum=True).exists())
        # The warehouse packs for all projects, project management may change the project: both still may.
        for username, role in (("luka", "Lager"), ("paula", "Projektleitung")):
            added = self.act("add-material", client=self.client_for(username, role), product=self.cable.pk, quantity=1)
            self.assertEqual(added.status_code, 200, (role, added.content))
        self.assertEqual(MaterialLine.objects.filter(project=self.project, is_addendum=True).count(), 2)

    def test_the_sync_refuses_more_than_the_packing_list_and_takes_the_rest(self) -> None:
        answer = self.sync(
            self.change("packed", "11", "2027-03-09T11:00:00+01:00"),
            self.change("packed", "1", "2027-03-09T11:00:00+01:00", line=self.rack_line),
            client=self.crew,
        )
        self.assertEqual(answer.status_code, 200, answer.content)
        above, rack = answer.json()["results"]
        self.assertEqual((above["outcome"], above["reason"]), ("refused", "needs_project_write"))
        self.assertTrue(above["message"].startswith("Gebraucht werden nur 10. Material nachtragen dürfen nur"))
        self.assertEqual((rack["outcome"], rack["reason"]), ("applied", None))
        # Whoever may add material gets the hint to do that first.
        admin = self.sync(self.change("packed", "11", "2027-03-09T11:05:00+01:00"))
        result = admin.json()["results"][0]
        self.assertEqual(
            (result["outcome"], result["reason"], result["message"]),
            ("refused", "above_packing_list", "Gebraucht werden nur 10."),
        )

    def test_the_list_for_the_phone_says_what_the_caller_may_do(self) -> None:
        def entry_of(client: Any) -> dict[str, Any]:
            projects = client.get(f"{API}/offline/packlists").json()["projects"]
            return next(project for project in projects if project["id"] == self.project.pk)

        crew = entry_of(self.crew)
        self.assertEqual((crew["can_write"], crew["can_add_material"]), (True, False))
        warehouse = entry_of(self.client_for("luka", "Lager", allowed_modules=COMPANION_MODULES))
        self.assertEqual((warehouse["can_write"], warehouse["can_add_material"]), (True, True))

    def test_a_freelancer_still_only_reads(self) -> None:
        fred = make_user("fred", roles=("Freie Kraft",))
        plan(self.project, job_function("Stagehand"), make_person("Fred Frei", user=fred))
        self.assertEqual(self.tick("4", client=self.client_of(fred)).status_code, 403)
