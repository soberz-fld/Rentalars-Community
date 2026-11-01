# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: people, job functions, hourly rates, absences, availability, privacy (chapter 5.5)."""

from __future__ import annotations

from rentalars.accounts.models import User
from rentalars.core.models import AuditLogEntry
from rentalars.personnel.models import JobFunction, Person
from tests.api.base import API, ApiTestCase
from tests.helpers import at, job_function, make_person, make_project, make_user, plan, record_time


class JobFunctionApiTests(ApiTestCase):
    """PER-004, PER-008."""

    def test_life_cycle(self) -> None:
        created = self.admin.post(
            f"{API}/job-functions", {"name": "Pyrotechnik", "guide_cost_rate": "40.00"}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        address = f"{API}/job-functions/{created.data['id']}"
        self.assertEqual(self.admin.get(address).data["name"], "Pyrotechnik")

        replaced = self.admin.put(address, {"name": "Pyrotechnik und SFX", "guide_cost_rate": "42.00"}, format="json")
        self.assertEqual(replaced.data["guide_cost_rate"], "42.00")
        self.assertFalse(self.admin.patch(address, {"is_active": False}, format="json").data["is_active"])
        self.assertEqual(self.admin.delete(address).status_code, 204)
        self.assertFalse(JobFunction.objects.filter(name__startswith="Pyro").exists())

    def test_list_is_readable_for_everybody_but_not_the_guide_values(self) -> None:
        """Forms need the list; what an hour costs the company is not everybody's business (AUT-019)."""
        job_function("Tontechnik", price="45.00", guide="32.00")
        crew = self.client_for("carla", "Crew").get(f"{API}/job-functions")
        self.assertEqual(crew.status_code, 200)
        sound = next(row for row in crew.data if row["name"] == "Tontechnik")
        self.assertNotIn("guide_cost_rate", sound)
        self.assertIsNotNone(sound["service_product"])
        with_costs = next(row for row in self.admin.get(f"{API}/job-functions").data if row["name"] == "Tontechnik")
        self.assertEqual(with_costs["guide_cost_rate"], "32.00")

    def test_changing_needs_write_access_to_personnel(self) -> None:
        client = self.client_for("paula", "Projektleitung")
        self.assert_error(client.post(f"{API}/job-functions", {"name": "Neu"}, format="json"), 403, "permission_denied")

    def test_used_job_function_cannot_be_deleted(self) -> None:
        make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        function = job_function("Tontechnik")
        self.assert_error(self.admin.delete(f"{API}/job-functions/{function.pk}"), 400, "validation_error")

    def test_only_service_products_can_be_linked(self) -> None:
        from tests.helpers import make_product

        cable = make_product("K-005", "XLR-Kabel 5 m")
        function = job_function("Tontechnik")
        response = self.admin.patch(f"{API}/job-functions/{function.pk}", {"service_product": cable.pk}, format="json")
        self.assert_error(response, 400, "validation_error", "service_product")


class PersonApiTests(ApiTestCase):
    """PER-001 to PER-003, AUT-012."""

    def test_life_cycle(self) -> None:
        """AUT-026: the person comes with an account of its own; it is not chosen."""
        created = self.admin.post(
            f"{API}/people",
            {
                "first_name": "Tom",
                "last_name": "Richter",
                "kind": "freelancer",
                "email": "tom@example.de",
                "company": "Richter Lichtdesign",
                "vat_id": "DE123456789",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["name"], created.data["job_functions"]), ("Tom Richter", []))
        self.assertEqual(created.data["username"], "tom.richter")
        self.assertFalse(created.data["share_phone"])  # PER-019: off by default
        address = f"{API}/people/{created.data['id']}"
        account = created.data["user"]

        self.assertEqual(self.admin.get(address).data["company"], "Richter Lichtdesign")
        replaced = self.admin.put(
            address,
            {"first_name": "Thomas", "last_name": "Richter", "kind": "freelancer", "company": "", "user": None},
            format="json",
        )
        self.assertEqual(
            (replaced.data["name"], replaced.data["company"], replaced.data["user"]), ("Thomas Richter", "", account)
        )
        self.assertEqual(User.objects.get(pk=account).first_name, "Thomas")
        self.assertFalse(self.admin.patch(address, {"is_active": False}, format="json").data["is_active"])
        self.assertEqual(self.admin.delete(address).status_code, 204)
        self.assertFalse(Person.objects.filter(pk=created.data["id"]).exists())
        self.assertFalse(User.objects.filter(pk=account).exists())

    def test_list_with_search_and_filters(self) -> None:
        make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        make_person("Tom Richter", rates={"Lichttechnik": "38.00"}, kind="freelancer")
        names = lambda response: [row["name"] for row in response.data["results"]]  # noqa: E731
        # AUT-026: the administrator's account is a person too (where "admin" sorts depends on the database).
        self.assertEqual(sorted(names(self.admin.get(f"{API}/people"))), ["Anna Becker", "Tom Richter", "admin"])
        self.assertEqual(names(self.admin.get(f"{API}/people", {"search": "rich"})), ["Tom Richter"])
        self.assertEqual(names(self.admin.get(f"{API}/people", {"kind": "freelancer"})), ["Tom Richter"])
        sound = job_function("Tontechnik")
        self.assertEqual(names(self.admin.get(f"{API}/people", {"job_function": sound.pk})), ["Anna Becker"])

    def test_personnel_data_are_only_for_those_with_the_right(self) -> None:
        """NFA-010, acceptance scenario 6."""
        anna = make_person("Anna Becker")
        for role in ("Lager", "Crew", "Freie Kraft"):
            client = self.client_for(role.lower().replace(" ", ""), role)
            self.assert_error(client.get(f"{API}/people"), 403, "permission_denied")
            self.assert_error(client.get(f"{API}/people/{anna.pk}"), 403, "permission_denied")
            self.assert_error(
                client.get(f"{API}/people/availability", {"from": "2027-03-10", "to": "2027-03-11"}),
                403,
                "permission_denied",
            )
        reader = self.client_for("paula", "Projektleitung")
        self.assertEqual(reader.get(f"{API}/people/{anna.pk}").status_code, 200)
        self.assert_error(
            reader.patch(f"{API}/people/{anna.pk}", {"phone": "1"}, format="json"), 403, "permission_denied"
        )

    def test_an_account_belongs_to_one_person(self) -> None:
        """AUT-026: ``user`` is read only – a new person always gets a new account."""
        user = make_user("anna")
        response = self.admin.post(f"{API}/people", {"last_name": "Doppelt", "user": user.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotEqual(response.data["user"], user.pk)
        self.assertEqual(Person.objects.get(user=user).last_name, "anna")

    def test_planned_person_cannot_be_deleted(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project(), "Tontechnik", anna)
        self.assert_error(self.admin.delete(f"{API}/people/{anna.pk}"), 400, "validation_error")
        self.assertTrue(Person.objects.filter(pk=anna.pk).exists())

    def test_own_profile_names_the_linked_person(self) -> None:
        """AUT-012."""
        user = make_user("anna", roles=("Crew",))
        anna = make_person("Anna Becker", user=user)
        profile = self.client_of(user).get(f"{API}/me").data
        self.assertEqual(profile["person"], {"id": anna.pk, "name": "Anna Becker"})
        self.assertEqual(profile["module_levels"]["projects"], 1)
        self.assertEqual(profile["module_levels_everywhere"]["projects"], 0)
        admin_person = Person.objects.get(user=self.admin_user)
        self.assertEqual(self.admin.get(f"{API}/me").data["person"], {"id": admin_person.pk, "name": "admin"})


class RateApiTests(ApiTestCase):
    """PER-005, PER-007, PER-010."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.address = f"{API}/people/{self.anna.pk}/job-functions"
        self.sound = job_function("Tontechnik")

    def test_assign_a_function_and_raise_a_rate_later(self) -> None:
        hand = job_function("Stagehand")
        response = self.admin.post(self.address, {"job_function": hand.pk, "hourly_rate": "20.00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["name"] for row in response.data], ["Stagehand", "Tontechnik"])

        raised = self.admin.post(
            self.address,
            {"job_function": self.sound.pk, "hourly_rate": "38.00", "valid_from": "2027-07-01"},
            format="json",
        )
        sound = next(row for row in raised.json() if row["name"] == "Tontechnik")
        self.assertEqual(sound["hourly_rate"], "35.00")  # today the old rate still applies
        self.assertEqual([step["hourly_rate"] for step in sound["history"]], ["35.00", "38.00"])
        self.assertEqual(
            self.admin.get(f"{API}/people/{self.anna.pk}").data["job_functions"], sorted([hand.pk, self.sound.pk])
        )

    def test_rates_are_hidden_without_the_cost_right(self) -> None:
        """AUT-019: personnel can be maintained without seeing what people earn."""
        from rentalars.accounts.models import Role

        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        client = self.client_for("pit", "Personal ohne Kosten")
        rows = client.get(self.address).data
        self.assertEqual(rows, [{"job_function": self.sound.pk, "name": "Tontechnik"}])
        self.assert_error(
            client.post(self.address, {"job_function": self.sound.pk, "hourly_rate": "1.00"}, format="json"),
            403,
            "permission_denied",
        )
        self.assert_error(client.delete(f"{self.address}/{self.sound.pk}"), 403, "permission_denied")

    def test_take_a_function_away(self) -> None:
        self.assertEqual(self.admin.delete(f"{self.address}/{self.sound.pk}").status_code, 204)
        self.assertEqual(self.admin.get(self.address).data, [])

    def test_invalid_rate_is_refused(self) -> None:
        response = self.admin.post(self.address, {"job_function": self.sound.pk, "hourly_rate": "-5"}, format="json")
        self.assert_error(response, 400, "validation_error", "hourly_rate")


class AbsenceAndAvailabilityApiTests(ApiTestCase):
    """PER-011, VFG-009, VFG-010."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tom = make_person("Tom Richter", rates={"Lichttechnik": "38.00"})
        self.project = make_project("Stadtfest")
        plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 22))
        self.absences = f"{API}/people/{self.tom.pk}/absences"

    def test_enter_list_and_delete_an_absence(self) -> None:
        created = self.admin.post(
            self.absences,
            {"kind": "vacation", "start": "2027-03-09T00:00:00+01:00", "end": "2027-03-16T00:00:00+01:00"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["warnings"], [])
        listed = self.admin.get(self.absences).data
        self.assertEqual([row["kind"] for row in listed], ["vacation"])
        self.assertEqual(self.admin.delete(f"{self.absences}/{listed[0]['id']}").status_code, 204)
        self.assertEqual(self.admin.get(self.absences).data, [])

    def test_absence_during_a_deployment_is_saved_with_a_warning(self) -> None:
        """PRJ-022."""
        response = self.admin.post(
            f"{API}/people/{self.anna.pk}/absences",
            {"kind": "sick", "start": "2027-03-10T00:00:00+01:00", "end": "2027-03-11T00:00:00+01:00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("Stadtfest", response.data["warnings"][0])

    def test_absence_with_reversed_period_is_refused(self) -> None:
        response = self.admin.post(
            self.absences, {"start": "2027-03-16T00:00:00+01:00", "end": "2027-03-09T00:00:00+01:00"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "end")

    def test_who_is_free_planned_or_absent(self) -> None:
        self.admin.post(
            self.absences,
            {"kind": "vacation", "start": "2027-03-09T00:00:00+01:00", "end": "2027-03-16T00:00:00+01:00"},
            format="json",
        )
        lea = make_person("Lea Vogel", rates={"Tontechnik": "25.00"})
        rows = self.admin.get(f"{API}/people/availability", {"from": "2027-03-10T09:00", "to": "2027-03-10T18:00"}).data
        # VFG-038: without a job function every active person – also the administrator's
        # account, a person without job function (AUT-026).
        self.assertEqual(
            [(row["name"], row["status"]) for row in rows],
            [("admin", "free"), ("Lea Vogel", "free"), ("Anna Becker", "planned"), ("Tom Richter", "absent")],
        )
        planned = next(row for row in rows if row["person"] == self.anna.pk)
        self.assertEqual(planned["deployments"][0]["project_number"], self.project.number)

        # VFG-010: who is free and can do sound?
        sound = job_function("Tontechnik")
        rows = self.admin.get(
            f"{API}/people/availability", {"from": "2027-03-10", "to": "2027-03-11", "job_function": sound.pk}
        ).data
        self.assertEqual(
            [(row["person"], row["status"]) for row in rows], [(lea.pk, "free"), (self.anna.pk, "planned")]
        )

    def test_projects_the_caller_may_not_see_are_counted_but_not_named(self) -> None:
        """AUT-016: the planner learns that Anna is busy, not where."""
        from rentalars.accounts.models import Role

        Role.objects.create(
            name="Disposition extern", module_levels={"personnel": 1, "projects": 1}, project_scope="assigned"
        )
        rows = (
            self.client_for("dana", "Disposition extern")
            .get(f"{API}/people/availability", {"from": "2027-03-10", "to": "2027-03-11"})
            .data
        )
        planned = next(row for row in rows if row["person"] == self.anna.pk)
        self.assertEqual(planned["status"], "planned")
        self.assertEqual(planned["deployments"][0]["project"], None)
        self.assertEqual(planned["deployments"][0]["project_number"], None)

    def test_period_must_be_given_and_in_order(self) -> None:
        self.assert_error(self.admin.get(f"{API}/people/availability"), 400, "validation_error", "from")
        self.assert_error(
            self.admin.get(f"{API}/people/availability", {"from": "2027-03-11", "to": "2027-03-10"}),
            400,
            "validation_error",
            "to",
        )
        self.assert_error(
            self.admin.get(f"{API}/people/availability", {"from": "morgen", "to": "2027-03-10"}),
            400,
            "validation_error",
            "from",
        )


class PrivacyApiTests(ApiTestCase):
    """NFA-009: export and anonymisation for people and customers."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, email="anna@example.de")
        self.project = make_project("Stadtfest")
        plan(self.project, "Tontechnik", self.anna)
        record_time(self.anna, self.project, "Tontechnik", at(10, 8), at(10, 16), approve=True)

    def test_export_of_a_person(self) -> None:
        document = self.admin.get(f"{API}/people/{self.anna.pk}/export").data
        self.assertEqual(document["person"]["email"], "anna@example.de")
        self.assertEqual(len(document["deployments"]), 1)
        self.assertEqual(document["time_entries"][0]["hourly_rate"], "35.00")

    def test_export_needs_the_highest_level_and_the_cost_right(self) -> None:
        self.assert_error(
            self.client_for("paula", "Projektleitung").get(f"{API}/people/{self.anna.pk}/export"),
            403,
            "permission_denied",
        )
        self.assertEqual(
            self.client_for("dora", "Personaldisposition").get(f"{API}/people/{self.anna.pk}/export").status_code, 200
        )

    def test_anonymise_a_person(self) -> None:
        response = self.admin.post(f"{API}/people/{self.anna.pk}/anonymise")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["name"], f"Anonymisiert ({self.anna.pk})")
        self.assertEqual(response.data["email"], "")
        self.assertIsNotNone(response.data["anonymised_at"])
        self.assertTrue(AuditLogEntry.objects.filter(event="person.anonymised").exists())
        # The work stays in the project.
        crew = self.admin.get(f"{API}/projects/{self.project.pk}/crew-lines").json()
        self.assertEqual(crew[0]["approved_hours"], "8.00")
        self.assertEqual(crew[0]["person_name"], f"Anonymisiert ({self.anna.pk})")

    def test_export_of_a_customer(self) -> None:
        customer = self.project.customer
        document = self.admin.get(f"{API}/customers/{customer.pk}/export").data
        self.assertEqual(document["customer"]["name"], customer.name)
        self.assertEqual([row["number"] for row in document["projects"]], [self.project.number])
        self.assert_error(
            self.client_for("paula", "Projektleitung").get(f"{API}/customers/{customer.pk}/export"),
            403,
            "permission_denied",
        )
