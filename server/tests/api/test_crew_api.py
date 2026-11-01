# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: crew lines, project members, the deployment view (PRJ-019 ff., AUT-016 to AUT-025)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.accounts.models import Role
from rentalars.projects.models import ProjectMembership
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ASSIGNED_READER,
    add_line,
    at,
    job_function,
    make_internal_project,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    record_time,
)


class CrewLineApiTests(ApiTestCase):
    """PRJ-019 to PRJ-023, PRJ-051, PRJ-052, PRJ-061, PER-006, PER-018."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.sound = job_function("Tontechnik", price="45.00", guide="32.00")
        self.hand = job_function("Stagehand", price="28.00", guide="18.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.base = f"{API}/projects/{self.project.pk}/crew-lines"

    def test_plan_a_person_and_read_price_and_cost(self) -> None:
        """Acceptance scenario 15 through the API: 8 hours at 45.00 are 360.00; they cost 280.00."""
        created = self.admin.post(
            self.base,
            {
                "job_function": self.sound.pk,
                "person": self.anna.pk,
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T18:00:00+01:00",
                "planned_hours": "8",
                "meeting_point": "FOH",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        (line,) = created.json()
        self.assertEqual(
            (line["person_name"], line["job_function_name"], line["title"]),
            ("Anna Becker", "Tontechnik", "Tontechnik, Stunde"),
        )
        self.assertEqual(
            (line["unit_price"], line["amount"], line["hourly_rate"], line["cost"]),
            ("45.00", "360.00", "35.00", "280.00"),
        )
        # PER-036: billed by effort – the planned hours stand in as an estimate until times are approved.
        self.assertEqual((line["billing"], line["is_estimate"], line["warnings"]), ("effort", True, []))

        detail = self.admin.get(f"{self.base}/{line['id']}").json()
        self.assertEqual(detail["meeting_point"], "FOH")
        self.assertEqual([row["id"] for row in self.admin.get(self.base).json()], [line["id"]])

    def test_open_places_cost_the_guide_value(self) -> None:
        """PRJ-020, PRJ-052."""
        created = self.admin.post(
            self.base,
            {
                "job_function": self.hand.pk,
                "count": 2,
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T14:00:00+01:00",
            },
            format="json",
        )
        lines = created.json()
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(
                (line["is_vacant"], line["planned_hours"], line["amount"], line["cost"]),
                (True, "6.00", "168.00", "108.00"),
            )
            self.assertTrue(line["cost_is_guide_value"])

    def test_fill_a_place_change_it_and_delete_it(self) -> None:
        place = plan(self.project, self.sound, start=at(10, 8), end=at(10, 18))
        address = f"{self.base}/{place.pk}"
        filled = self.admin.patch(address, {"person": self.anna.pk}, format="json").json()
        self.assertEqual((filled["person"], filled["hourly_rate"]), (self.anna.pk, "35.00"))

        flat = self.admin.patch(
            address, {"cost_flat_rate": "300.00", "billing": "flat", "unit_price": "500.00"}, format="json"
        ).json()
        self.assertEqual((flat["amount"], flat["cost"], flat["charged_hours"]), ("500.00", "300.00", None))

        replaced = self.admin.put(
            address,
            {"job_function": self.sound.pk, "person": None, "billing": "plan", "unit_price": "45.00"},
            format="json",
        ).json()
        self.assertEqual(
            (replaced["is_vacant"], replaced["hourly_rate"], replaced["cost_flat_rate"]), (True, None, None)
        )

        self.assert_error(self.admin.patch(address, {"count": 3}, format="json"), 400, "validation_error", "count")
        self.assertEqual(self.admin.delete(address).status_code, 204)
        self.assertEqual(self.admin.get(self.base).json(), [])

    def test_a_person_is_planned_only_in_their_job_functions(self) -> None:
        """PER-006: refused without the special right, possible – with a warning – with it."""
        Role.objects.create(name="Planung", module_levels={"projects": 2, "personnel": 1})
        body = {"job_function": self.hand.pk, "person": self.anna.pk}
        self.assert_error(
            self.client_for("pia", "Planung").post(self.base, body, format="json"), 400, "validation_error", "person"
        )
        allowed = self.client_for("paula", "Projektleitung").post(self.base, body, format="json")
        self.assertEqual(allowed.status_code, 201, allowed.data)
        self.assertIn("Stagehand", allowed.json()[0]["warnings"][0])

    def test_double_booking_and_absence_are_reported_as_warnings(self) -> None:
        """PRJ-022."""
        other = make_project("Jazznacht")
        plan(other, self.sound, self.anna, start=at(10, 16), end=at(10, 23))
        self.admin.post(
            f"{API}/people/{self.anna.pk}/absences",
            {"kind": "vacation", "start": "2027-03-10T00:00:00+01:00", "end": "2027-03-12T00:00:00+01:00"},
            format="json",
        )
        created = self.admin.post(
            self.base,
            {
                "job_function": self.sound.pk,
                "person": self.anna.pk,
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T18:00:00+01:00",
            },
            format="json",
        )
        warnings = " ".join(created.json()[0]["warnings"])
        self.assertIn(
            f"Projekt {other.number}", warnings
        )  # By number only – the reader may not open the other project (AUT-016)
        self.assertIn("Urlaub", warnings)

    def test_prices_and_costs_follow_the_rights_of_the_caller(self) -> None:
        """AUT-019."""
        plan(self.project, self.sound, self.anna, planned_hours=Decimal("8"))
        Role.objects.create(name="Planung", module_levels={"projects": 2, "personnel": 2})
        planner = self.client_for("pia", "Planung")
        (line,) = planner.get(self.base).json()
        for hidden in ("unit_price", "amount", "hourly_rate", "cost", "cost_flat_rate"):
            self.assertNotIn(hidden, line)
        address = f"{self.base}/{line['id']}"
        self.assert_error(planner.patch(address, {"hourly_rate": "1.00"}, format="json"), 400, "validation_error")
        self.assert_error(planner.patch(address, {"unit_price": "1.00"}, format="json"), 400, "validation_error")
        self.assertEqual(planner.patch(address, {"meeting_point": "Rampe"}, format="json").status_code, 200)

        Role.objects.create(name="Vertrieb", module_levels={"projects": 2}, special_rights=["prices"])
        (line,) = self.client_for("vera", "Vertrieb").get(self.base).json()
        self.assertEqual(line["amount"], "360.00")
        self.assertNotIn("hourly_rate", line)
        self.assertNotIn("cost", line)

    def test_personnel_planning_plans_crew_without_editing_projects(self) -> None:
        """Catalogue chapter 4: the role reads projects and maintains personnel."""
        planner = self.client_for("dora", "Personaldisposition")
        created = planner.post(self.base, {"job_function": self.sound.pk, "person": self.anna.pk}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        line = created.json()[0]
        self.assertEqual(
            planner.patch(f"{self.base}/{line['id']}", {"note": "bringt Funke mit"}, format="json").status_code, 200
        )
        # … but the project itself stays read-only for the role.
        self.assert_error(
            planner.patch(f"{API}/projects/{self.project.pk}", {"venue": "Rathaus"}, format="json"),
            403,
            "permission_denied",
        )
        self.assertEqual(planner.delete(f"{self.base}/{line['id']}").status_code, 204)

    def test_the_warehouse_reads_the_crew_but_does_not_plan_it(self) -> None:
        plan(self.project, self.sound, self.anna)
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(len(warehouse.get(self.base).json()), 1)
        self.assert_error(
            warehouse.post(self.base, {"job_function": self.hand.pk}, format="json"), 403, "permission_denied"
        )

    def test_crew_is_part_of_planning_totals_and_price_overview(self) -> None:
        """PRJ-038: a block of its own with its own subtotal, never inside a group."""
        add_line(self.project, make_product("L-010", "LED-Scheinwerfer", price="20.00"), 5, rental_days=1)
        plan(self.project, self.sound, self.anna, planned_hours=Decimal("8"))
        planning = self.admin.get(f"{API}/projects/{self.project.pk}/planning").json()
        self.assertEqual([row["amount"] for row in planning["crew"]], ["360.00"])
        self.assertEqual(planning["totals"]["personnel_total"], "360.00")
        self.assertEqual(planning["totals"]["net_total"], "460.00")
        self.assertEqual(planning["totals"]["personnel_cost"], "280.00")
        self.assertEqual(self.admin.get(f"{API}/projects/{self.project.pk}/totals").json()["personnel_total"], "360.00")

        overview = self.admin.get(f"{API}/projects/{self.project.pk}/price-overview").json()
        self.assertEqual(overview["personnel"]["subtotal"], "360.00")
        self.assertEqual([row["title"] for row in overview["personnel"]["lines"]], ["Tontechnik, Stunde"])
        # Acceptance scenario 15: the hourly rate of the person does not appear in the price overview.
        self.assertNotIn("35.00", str(overview))
        self.assertNotIn("280.00", str(overview))

    def test_by_effort_the_approved_hours_are_charged(self) -> None:
        """PRJ-061: 9.5 approved hours at 45.00 are 427.50; before, 360.00 stand as an estimate."""
        line = plan(self.project, self.sound, self.anna, planned_hours=Decimal("8"), start=at(10, 8), end=at(10, 20))
        address = f"{self.base}/{line.pk}"
        estimate = self.admin.patch(address, {"billing": "effort"}, format="json").json()
        self.assertEqual((estimate["amount"], estimate["is_estimate"]), ("360.00", True))
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 17, 30), approve=True)
        charged = self.admin.get(address).json()
        self.assertEqual(
            (charged["approved_hours"], charged["amount"], charged["is_estimate"]), ("9.50", "427.50", False)
        )

    def test_times_without_crew_line_are_listed_and_taken_over(self) -> None:
        """ZEI-021."""
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), approve=True)
        kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        record_time(kai, self.project, self.hand, at(10, 8), at(10, 14), approve=True)
        address = f"{self.base}/unassigned-times"
        loose = self.admin.get(address).json()
        self.assertEqual(
            [(row["person_name"], row["hours"]) for row in loose],
            [("Becker, Anna"[8:] + " Becker", "4.00"), ("Kai Kurz", "6.00")],
        )

        # Anna's times become a line of their own, Kai's go onto an open place.
        adopted = self.admin.post(
            address, {"person": self.anna.pk, "job_function": self.sound.pk}, format="json"
        ).json()
        self.assertEqual(
            (adopted["billing"], adopted["approved_hours"], adopted["amount"]), ("effort", "4.00", "180.00")
        )
        place = plan(self.project, self.hand)
        assigned = self.admin.post(
            address, {"person": kai.pk, "job_function": self.hand.pk, "crew_line": place.pk}, format="json"
        ).json()
        self.assertEqual((assigned["id"], assigned["approved_hours"]), (place.pk, "6.00"))
        self.assertEqual(self.admin.get(address).json(), [])
        self.assert_error(
            self.admin.post(address, {"person": kai.pk, "job_function": self.hand.pk}, format="json"),
            400,
            "validation_error",
        )

    def test_planned_against_recorded_hours(self) -> None:
        """PRJ-026."""
        plan(self.project, self.sound, self.anna, planned_hours=Decimal("8"), start=at(10, 8), end=at(10, 20))
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 17), approve=True)
        record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 10), submit=True)
        rows = self.admin.get(f"{self.base}/planned-and-actual").json()
        self.assertEqual(
            [
                (
                    row["job_function_name"],
                    row["person_name"],
                    row["planned_hours"],
                    row["approved_hours"],
                    row["pending_hours"],
                )
                for row in rows
            ],
            [("Tontechnik", "Anna Becker", "8.00", "9.00", "2.00")],
        )

    def test_a_closed_project_takes_no_crew_changes(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        self.admin.post(f"{API}/projects/{self.project.pk}/status", {"status": "cancelled"}, format="json")
        self.assertEqual(self.project.__class__.objects.get(pk=self.project.pk).status, "cancelled")
        self.project.status = "closed"
        self.project.save()
        self.assert_error(
            self.admin.post(self.base, {"job_function": self.hand.pk}, format="json"), 400, "validation_error"
        )
        self.assert_error(self.admin.delete(f"{self.base}/{line.pk}"), 400, "validation_error")


class ProjectAccessApiTests(ApiTestCase):
    """AUT-016 to AUT-018, AUT-023, AUT-025: assigned projects only, in list, search and every address."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", venue="Marktplatz")
        self.foreign = make_project("Jazznacht")
        add_line(self.project, make_product("L-010", "LED-Scheinwerfer", price="23.45"), 4, rental_days=1)
        self.user = make_user("frieda", roles=(ASSIGNED_READER,))  # AUT-036
        self.person = make_person("Frieda Frei", rates={"Stagehand": "20.00"}, user=self.user, phone="0151 1")
        self.line = plan(self.project, "Stagehand", self.person, start=at(10, 8), end=at(10, 14), meeting_point="Rampe")
        self.client_ = self.client_of(self.user)

    def test_list_and_search_show_assigned_projects_only(self) -> None:
        listed = self.client_.get(f"{API}/projects").json()["results"]
        self.assertEqual([row["name"] for row in listed], ["Stadtfest"])
        self.assertEqual(listed[0]["access"], "deployment")
        found = self.client_.get(f"{API}/search", {"q": "nacht"}).json()["results"]
        self.assertEqual(found, [])
        found = self.client_.get(f"{API}/search", {"q": "Stadtfest"}).json()["results"]
        self.assertEqual([hit["id"] for group in found for hit in group["hits"]], [self.project.pk])
        # PRJ-122: the name of the customer shows in every role, so it is found – among the projects the role
        # sees. Which projects a customer has (by its ID) is still no business of the deployment view (AUT-023).
        customer = self.project.customer
        found = self.client_.get(f"{API}/search", {"q": customer.name}).json()["results"]
        self.assertEqual([hit["id"] for group in found for hit in group["hits"]], [self.project.pk])
        listed = self.client_.get(f"{API}/projects", {"q": customer.name}).json()["results"]
        self.assertEqual([row["name"] for row in listed], ["Stadtfest"])
        self.assertEqual(self.client_.get(f"{API}/projects", {"customer": customer.pk}).json()["results"], [])
        self.assertEqual(len(self.admin.get(f"{API}/projects", {"customer": customer.pk}).json()["results"]), 2)

    def test_with_the_deployment_view_the_project_shows_time_and_place_only(self) -> None:
        """AUT-023: no customer record, no notes, no rental days – PRJ-122: but the customer's name."""
        self.project.notes = "Kunde zahlt bar"
        self.project.save()
        data = self.client_.get(f"{API}/projects/{self.project.pk}", {"expand": "manager,customer"}).json()
        self.assertEqual(data["venue"], "Marktplatz")
        for hidden in ("customer", "contact", "notes", "rental_days", "allowed_next_statuses"):
            self.assertNotIn(hidden, data)
        self.assertNotIn("bar", str(data))
        self.assertEqual(data["customer_name"], self.project.customer.name)

    def test_a_foreign_project_does_not_exist_for_the_caller(self) -> None:
        for address in (
            "",
            "/planning",
            "/deployment",
            "/crew-lines",
            "/groups",
            "/material-lines",
            "/members",
            "/packlists",
            "/history",
        ):
            response = self.client_.get(f"{API}/projects/{self.foreign.pk}{address}")
            self.assertEqual(response.status_code, 404, address)
            missing = self.client_.get(f"{API}/projects/999999{address}")
            self.assertEqual(missing.status_code, 404, address)

    def test_the_deployment_view_opens_nothing_of_the_planning(self) -> None:
        for address in ("/planning", "/crew-lines", "/groups", "/material-lines", "/members", "/history", "/shortages"):
            response = self.client_.get(f"{API}/projects/{self.project.pk}{address}")
            self.assert_error(response, 403, "permission_denied")
        for address in ("/totals", "/price-overview"):
            self.assert_error(self.client_.get(f"{API}/projects/{self.project.pk}{address}"), 403, "permission_denied")

    def test_nothing_can_be_changed_or_deleted_through_a_foreign_or_deployment_only_project(self) -> None:
        """AUT-020: every operation asks, deleting included."""
        from tests.helpers import add_group

        for project in (self.project, self.foreign):
            group = add_group(project, "Licht")
            line = add_line(project, make_product(f"K-{project.pk:03d}", price="1.00"), 1, group=group).line
            crew_line = plan(project, "Stagehand")
            base = f"{API}/projects/{project.pk}"
            expected = 403 if project == self.project else 404
            calls = [
                self.client_.delete(f"{base}/groups/{group.pk}"),
                self.client_.delete(f"{base}/material-lines/{line.pk}"),
                self.client_.delete(f"{base}/crew-lines/{crew_line.pk}"),
                self.client_.patch(f"{base}/material-lines/{line.pk}", {"quantity": 5}, format="json"),
                self.client_.post(f"{base}/crew-lines", {"job_function": crew_line.job_function_id}, format="json"),
                self.client_.post(f"{base}/members", {"user": self.user.pk, "level": "edit"}, format="json"),
                self.client_.delete(base),
            ]
            # The role only reads projects, so writing is refused before the project is even looked at.
            self.assertEqual({response.status_code for response in calls} - {403, expected}, set(), project.name)
            self.assertTrue(project.groups.filter(pk=group.pk).exists())
            self.assertTrue(project.material_lines.filter(pk=line.pk).exists())
            self.assertTrue(project.crew_lines.filter(pk=crew_line.pk).exists())

    def test_an_editing_role_for_assigned_projects_cannot_touch_foreign_projects(self) -> None:
        """The same walk for a role that may write – where the module level alone would let it through."""
        from tests.helpers import add_group

        Role.objects.create(
            name="Projektleitung extern", module_levels={"projects": 3, "packing": 2}, project_scope="assigned"
        )
        external = make_user("erik", roles=("Projektleitung extern",))
        client = self.client_of(external)
        group = add_group(self.foreign, "Licht")
        line = add_line(self.foreign, make_product("K-777", price="1.00"), 1, group=group).line
        crew_line = plan(self.foreign, "Stagehand")
        base = f"{API}/projects/{self.foreign.pk}"
        calls = {
            "delete group": client.delete(f"{base}/groups/{group.pk}"),
            "delete line": client.delete(f"{base}/material-lines/{line.pk}"),
            "delete crew line": client.delete(f"{base}/crew-lines/{crew_line.pk}"),
            "change line": client.patch(f"{base}/material-lines/{line.pk}", {"quantity": 5}, format="json"),
            "add line": client.post(
                f"{base}/material-lines", {"product": line.product_id, "quantity": 1}, format="json"
            ),
            "add group": client.post(f"{base}/groups", {"name": "Neu"}, format="json"),
            "copy group": client.post(f"{base}/groups/{group.pk}/copy", {}, format="json"),
            "plan crew": client.post(f"{base}/crew-lines", {"job_function": crew_line.job_function_id}, format="json"),
            "add member": client.post(f"{base}/members", {"user": external.pk, "level": "edit"}, format="json"),
            "status": client.post(f"{base}/status", {"status": "cancelled"}, format="json"),
            "change": client.patch(base, {"name": "Gekapert"}, format="json"),
            "delete": client.delete(base),
            "tick": client.patch(f"{base}/packlists/1/rows", {"rows": []}, format="json"),
        }
        self.assertEqual({name: response.status_code for name, response in calls.items()}, dict.fromkeys(calls, 404))
        self.foreign.refresh_from_db()
        self.assertEqual((self.foreign.name, self.foreign.status), ("Jazznacht", "confirmed"))
        self.assertEqual(self.foreign.groups.count(), 1)
        self.assertEqual(ProjectMembership.objects.count(), 0)

        # A group of an own project cannot be copied into a foreign one either.
        ProjectMembership.objects.create(project=self.project, user=external, level="edit")
        own_group = add_group(self.project, "Ton")
        copied = client.post(
            f"{API}/projects/{self.project.pk}/groups/{own_group.pk}/copy",
            {"target_project": self.foreign.pk},
            format="json",
        )
        self.assertEqual(copied.status_code, 404)
        self.assertEqual(self.foreign.groups.count(), 1)

    def test_deployment_view_shows_time_place_function_and_colleagues(self) -> None:
        """AUT-023, AUT-025, PER-019."""
        anna = make_person(
            "Anna Becker",
            rates={"Tontechnik": "35.00"},
            phone="0170 5550101",
            email="anna@example.de",
            share_phone=True,
        )
        tom = make_person("Tom Richter", rates={"Lichttechnik": "38.00"}, phone="0171 5550102")
        plan(self.project, "Tontechnik", anna, start=at(10, 8), end=at(10, 22))
        plan(self.project, "Lichttechnik", tom, start=at(10, 8), end=at(10, 22))
        plan(self.project, "Stagehand", start=at(10, 8), end=at(10, 14))

        view = self.client_.get(f"{API}/projects/{self.project.pk}/deployment").json()
        self.assertEqual((view["name"], view["venue"], view["can_see_packlist"]), ("Stadtfest", "Marktplatz", True))
        crew = {row["person"]: row for row in view["crew"]}
        self.assertEqual(set(crew), {"Frieda Frei", "Anna Becker", "Tom Richter", None})

        me = crew["Frieda Frei"]
        self.assertTrue(me["is_me"])
        self.assertEqual(
            (me["job_function"], me["meeting_point"], me["planned_hours"], me["hourly_rate"]),
            ("Stagehand", "Rampe", "6.00", "20.00"),
        )
        # Anna released her phone number, not her e-mail address; Tom released nothing.
        self.assertEqual((crew["Anna Becker"]["phone"], crew["Anna Becker"]["email"]), ("0170 5550101", None))
        self.assertEqual((crew["Tom Richter"]["phone"], crew["Tom Richter"]["email"]), (None, None))
        # Nothing about prices, the customer or the rates of others.
        text = str(view)
        for hidden in ("35.00", "38.00", "23.45", "Stadtwerke", "customer", "unit_price"):
            self.assertNotIn(hidden, text)
        self.assertNotIn("hourly_rate", crew["Anna Becker"])

    def test_own_rate_can_be_switched_off(self) -> None:
        """PER-010."""
        changed = self.admin.patch(f"{API}/settings", {"system": {"people_see_own_rates": False}}, format="json")
        self.assertFalse(changed.data["system"]["people_see_own_rates"])
        view = self.client_.get(f"{API}/projects/{self.project.pk}/deployment").json()
        me = next(row for row in view["crew"] if row["is_me"])
        self.assertNotIn("hourly_rate", me)

    def test_project_management_sees_all_contact_data(self) -> None:
        """PER-019: regardless of what the person released."""
        view = self.client_for("paula", "Projektleitung").get(f"{API}/projects/{self.project.pk}/deployment").json()
        self.assertEqual(view["crew"][0]["phone"], "0151 1")

    def test_packlist_is_readable_with_the_deployment_view_but_not_writable(self) -> None:
        base = f"{API}/projects/{self.project.pk}/packlists"
        packlists = self.client_.get(base)
        self.assertEqual(packlists.status_code, 200, packlists.data)
        packlist_id = packlists.json()[0]["id"]
        self.assertEqual(self.client_.get(f"{base}/{packlist_id}").status_code, 200)
        self.assert_error(self.client_.post(f"{base}/{packlist_id}/issue", {}, format="json"), 403, "permission_denied")
        self.assertEqual(self.client_.get(f"{API}/projects/{self.foreign.pk}/packlists").status_code, 404)

    def test_shortage_and_subrental_overviews_leave_out_projects_that_cannot_be_read(self) -> None:
        self.assertEqual(self.client_.get(f"{API}/shortages").json(), [])
        self.assertEqual(self.client_.get(f"{API}/subrentals").json(), [])

    def test_list_of_projects_costs_a_fixed_number_of_queries(self) -> None:
        """NFA-014: the level of each row is not looked up row by row."""
        for number in range(8):
            plan(make_project(f"Projekt {number}"), "Stagehand", self.person)
        self.client_.get(f"{API}/projects")  # warm up: content types, token
        with self.assertNumQueries(self.count_queries(lambda: self.client_.get(f"{API}/projects", {"page_size": 3}))):
            response = self.client_.get(f"{API}/projects")
        self.assertEqual(len(response.json()["results"]), 9)

    def count_queries(self, call: object) -> int:
        """How many queries a call makes – to compare a short list with a long one."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            call()  # type: ignore[operator]
        return len(queries)


class MembershipApiTests(ApiTestCase):
    """AUT-016, AUT-018: explicit assignment of a user to a project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.user = make_user("frieda", roles=(ASSIGNED_READER,))  # AUT-036
        self.base = f"{API}/projects/{self.project.pk}/members"

    def test_add_change_and_remove_a_member(self) -> None:
        client = self.client_of(self.user)
        self.assertEqual(client.get(f"{API}/projects/{self.project.pk}").status_code, 404)

        created = self.admin.post(self.base, {"user": self.user.pk, "level": "read"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["username"], created.data["level"]), ("frieda", "read"))
        self.assertEqual(client.get(f"{API}/projects/{self.project.pk}").json()["access"], "read")
        self.assertEqual(client.get(f"{API}/projects/{self.project.pk}/planning").status_code, 200)

        address = f"{self.base}/{created.data['id']}"
        self.assertEqual(self.admin.get(address).data["level"], "read")
        self.assertEqual(self.admin.patch(address, {"level": "deployment"}, format="json").data["level"], "deployment")
        self.assert_error(client.get(f"{API}/projects/{self.project.pk}/planning"), 403, "permission_denied")
        self.assertEqual([row["username"] for row in self.admin.get(self.base).data], ["frieda"])

        self.assertEqual(self.admin.delete(address).status_code, 204)
        self.assertEqual(client.get(f"{API}/projects/{self.project.pk}").status_code, 404)

    def test_adding_a_member_twice_changes_the_level(self) -> None:
        self.admin.post(self.base, {"user": self.user.pk, "level": "read"}, format="json")
        again = self.admin.post(self.base, {"user": self.user.pk, "level": "deployment"}, format="json")
        self.assertEqual(again.status_code, 201)
        self.assertEqual(
            [(row["username"], row["level"]) for row in self.admin.get(self.base).data], [("frieda", "deployment")]
        )

    def test_a_membership_gives_no_more_than_the_role(self) -> None:
        """AUT-025: "Freie Kraft" reads; a membership "edit" does not make it write."""
        self.admin.post(self.base, {"user": self.user.pk, "level": "edit"}, format="json")
        client = self.client_of(self.user)
        self.assertEqual(client.get(f"{API}/projects/{self.project.pk}").json()["access"], "read")
        self.assert_error(
            client.patch(f"{API}/projects/{self.project.pk}", {"venue": "x"}, format="json"), 403, "permission_denied"
        )
        # No prices either: those come only through the role (AUT-019).
        self.assertNotIn("totals", client.get(f"{API}/projects/{self.project.pk}/planning").json())

    def test_members_are_managed_by_those_who_edit_the_project(self) -> None:
        self.assert_error(
            self.client_for("luka", "Lager").post(self.base, {"user": self.user.pk}, format="json"),
            403,
            "permission_denied",
        )

    def test_creator_with_a_role_for_assigned_projects_becomes_member(self) -> None:
        Role.objects.create(
            name="Projektleitung extern", module_levels={"projects": 2, "customers": 1}, project_scope="assigned"
        )
        external = make_user("erik", roles=("Projektleitung extern",))
        client = self.client_of(external)
        created = client.post(
            f"{API}/projects",
            {
                "name": "Eigenes Projekt",
                "customer": self.project.customer_id,
                "start": "2027-03-20T08:00:00+01:00",
                "end": "2027-03-21T20:00:00+01:00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.json()["access"], "edit")
        self.assertEqual([row["name"] for row in client.get(f"{API}/projects").json()["results"]], ["Eigenes Projekt"])


class InternalProjectApiTests(ApiTestCase):
    """ZEI-010: projects without customer for warehouse, workshop, office."""

    def test_an_internal_project_needs_no_customer(self) -> None:
        created = self.admin.post(
            f"{API}/projects",
            {
                "name": "Lager und Werkstatt",
                "is_internal": True,
                "start": "2027-01-01T00:00:00+01:00",
                "end": "2027-12-31T00:00:00+01:00",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["is_internal"], created.data["customer"]), (True, None))

    def test_any_other_project_needs_one(self) -> None:
        response = self.admin.post(
            f"{API}/projects",
            {"name": "Ohne Kunde", "start": "2027-03-20T08:00:00+01:00", "end": "2027-03-21T20:00:00+01:00"},
            format="json",
        )
        self.assert_error(response, 400, "validation_error", "customer")

    def test_internal_projects_can_be_filtered(self) -> None:
        make_project("Stadtfest")
        make_internal_project("Lager")
        names = [row["name"] for row in self.admin.get(f"{API}/projects", {"is_internal": "true"}).json()["results"]]
        self.assertEqual(names, ["Lager"])
