# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: people, job functions, hourly rates, absences, availability, privacy (chapter 5.5)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.accounts.models import ApiToken
from rentalars.core.models import AuditLogEntry
from rentalars.personnel import services
from rentalars.personnel.availability import people_availability
from rentalars.personnel.models import Absence, AbsenceKind, EmploymentKind, JobFunction, Person
from rentalars.personnel.privacy import anonymise_person, export_person
from rentalars.projects import crew
from rentalars.projects.models import ProjectStatus
from tests.helpers import (
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    record_time,
)


class JobFunctionTests(RentalarsTestCase):
    """PER-004, PER-008: job functions are master data; the customer price comes from a service product."""

    def test_a_fresh_installation_suggests_the_usual_job_functions(self) -> None:
        """PER-037: the job functions the user asked for, each with its service product."""
        names = set(JobFunction.objects.values_list("name", flat=True))
        self.assertLessEqual(
            {
                "Techniker",
                "Lichttechniker",
                "Tontechniker",
                "Medientechniker",
                "Stagehand",
                "Lager",
                "Projektplanung",
                "Sonstiges",
            },
            names,
        )

    def test_only_a_service_product_can_carry_the_price(self) -> None:
        function = job_function("Tontechnik")
        function.service_product = make_product("K-005", "XLR-Kabel 5 m")
        with self.assertRaises(ValidationError) as raised:
            function.full_clean()
        self.assertIn("service_product", raised.exception.message_dict)

    def test_names_are_unique(self) -> None:
        with self.assertRaises(ValidationError):
            JobFunction(name="Tontechniker").full_clean()


class HourlyRateTests(RentalarsTestCase):
    """PER-005, PER-007: a rate per person and job function, valid from a day on."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"})
        self.sound = job_function("Tontechnik")

    def test_each_job_function_has_its_own_rate(self) -> None:
        self.assertEqual(services.rate_on(self.anna, self.sound), Decimal("35.00"))
        self.assertEqual(services.rate_on(self.anna, job_function("Stagehand")), Decimal("20.00"))
        self.assertEqual(
            [function.name for function in services.job_functions_of(self.anna)], ["Stagehand", "Tontechnik"]
        )

    def test_a_function_the_person_does_not_have_has_no_rate(self) -> None:
        self.assertIsNone(services.rate_on(self.anna, job_function("Rigging")))
        self.assertFalse(services.has_job_function(self.anna, job_function("Rigging")))

    def test_a_new_rate_applies_from_its_day_and_keeps_the_old_one(self) -> None:
        """The example of the model description: 35.00 from January, 38.00 from July."""
        services.set_rate(self.anna, self.sound, Decimal("38.00"), datetime.date(2027, 7, 1))
        self.assertEqual(services.rate_on(self.anna, self.sound, datetime.date(2027, 6, 30)), Decimal("35.00"))
        self.assertEqual(services.rate_on(self.anna, self.sound, datetime.date(2027, 7, 1)), Decimal("38.00"))
        self.assertEqual(self.anna.rates.filter(job_function=self.sound).count(), 2)
        # Today (1 March) the old rate still applies.
        current = {row.job_function.name: row.hourly_rate for row in services.current_rates(self.anna)}
        self.assertEqual(current, {"Stagehand": Decimal("20.00"), "Tontechnik": Decimal("35.00")})

    def test_a_rate_for_the_same_day_corrects_the_typo(self) -> None:
        services.set_rate(self.anna, self.sound, Decimal("36.00"), datetime.date(2027, 1, 1))
        self.assertEqual(self.anna.rates.filter(job_function=self.sound).count(), 1)
        self.assertEqual(services.rate_on(self.anna, self.sound), Decimal("36.00"))

    def test_before_the_first_rate_the_first_rate_applies(self) -> None:
        """Somebody whose first rate begins next month still has a rate for a job tomorrow."""
        kai = make_person("Kai Kurz")
        services.set_rate(kai, self.sound, Decimal("30.00"), datetime.date(2027, 4, 1))
        self.assertEqual(services.rate_on(kai, self.sound, datetime.date(2027, 3, 2)), Decimal("30.00"))

    def test_taking_a_function_away_removes_all_its_rates(self) -> None:
        services.set_rate(self.anna, self.sound, Decimal("38.00"), datetime.date(2027, 7, 1))
        services.remove_job_function(self.anna, self.sound)
        self.assertFalse(services.has_job_function(self.anna, self.sound))
        self.assertTrue(services.has_job_function(self.anna, job_function("Stagehand")))

    def test_rate_changes_are_logged_with_the_person(self) -> None:
        services.set_rate(self.anna, self.sound, Decimal("38.00"), datetime.date(2027, 7, 1))
        history = AuditLogEntry.for_object(self.anna)
        self.assertTrue(any("hourly_rate" in entry.changes for entry in history))


class PersonTests(RentalarsTestCase):
    """PER-001, PER-002, PER-003, AUT-012."""

    def test_person_with_the_master_data_of_a_freelancer(self) -> None:
        tom = make_person(
            "Tom Richter",
            kind=EmploymentKind.FREELANCER,
            email="Tom@Richter-Licht.example.de",
            company="Richter Lichtdesign",
            street="Am Hafen 3",
            postal_code="12345",
            city="Musterstadt",
            tax_number="12/345/67890",
            vat_id="DE123456789",
        )
        self.assertTrue(tom.is_freelancer)
        self.assertEqual(tom.email, "tom@richter-licht.example.de")
        self.assertEqual((tom.name, tom.sort_name), ("Tom Richter", "Richter, Tom"))

    def test_contact_data_are_hidden_from_colleagues_unless_released(self) -> None:
        """PER-019: the default is "not visible"."""
        anna = make_person("Anna Becker", phone="0170 5550101")
        self.assertFalse(anna.share_phone)
        self.assertFalse(anna.share_email)

    def test_an_account_belongs_to_one_person_only(self) -> None:
        """AUT-026: account and person come together; a second person for the same account is impossible."""
        from django.db import IntegrityError, transaction

        user = make_user("anna")
        make_person("Anna Becker", user=user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Person.objects.bulk_create([Person(first_name="Zweite", last_name="Anna", user=user)])
        self.assertEqual(Person.objects.get(user=user).name, "Anna Becker")

    def test_unused_person_can_be_deleted(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        services.delete_person(anna)
        self.assertFalse(Person.objects.exists())

    def test_planned_person_is_deactivated_instead_of_deleted(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project(), "Tontechnik", anna)
        with self.assertRaises(ValidationError):
            services.delete_person(anna)
        services.set_person_active(anna, active=False)
        self.assertFalse(Person.objects.get(pk=anna.pk).is_active)


class AbsenceTests(RentalarsTestCase):
    """PER-011: absences with a period."""

    def test_absence_needs_an_end_after_its_start(self) -> None:
        anna = make_person()
        with self.assertRaises(ValidationError) as raised:
            services.save_absence(Absence(person=anna, kind=AbsenceKind.VACATION, start=at(12), end=at(10)))
        self.assertIn("end", raised.exception.message_dict)

    def test_absence_that_hits_a_deployment_is_saved_with_a_warning(self) -> None:
        """PRJ-022: the absence is a fact; the planner must know."""
        anna = make_person(rates={"Tontechnik": "35.00"})
        project = make_project("Stadtfest")
        plan(project, "Tontechnik", anna)
        warnings = services.save_absence(Absence(person=anna, kind=AbsenceKind.SICK, start=at(11), end=at(14)))
        self.assertEqual(len(warnings), 1)
        self.assertIn("Stadtfest", warnings[0])
        self.assertIn("Tontechnik", warnings[0])
        self.assertEqual(anna.absences.count(), 1)

    def test_cancelled_projects_do_not_warn(self) -> None:
        anna = make_person(rates={"Tontechnik": "35.00"})
        project = make_project("Stadtfest")
        plan(project, "Tontechnik", anna)
        project.status = ProjectStatus.CANCELLED
        project.save()
        self.assertEqual(services.save_absence(Absence(person=anna, start=at(11), end=at(14))), [])


class AvailabilityOfPeopleTests(RentalarsTestCase):
    """VFG-009, VFG-010: free, planned or absent – for every person and period."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tom = make_person("Tom Richter", rates={"Lichttechnik": "38.00"})
        self.lea = make_person("Lea Vogel", rates={"Stagehand": "16.00", "Tontechnik": "25.00"})
        self.project = make_project("Stadtfest")
        plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 22))
        services.save_absence(Absence(person=self.lea, kind=AbsenceKind.VACATION, start=at(9), end=at(16)))

    def statuses(self, start: datetime.datetime, end: datetime.datetime, **options: object) -> dict[str, str]:
        return {row.person.name: row.status for row in people_availability(start, end, **options)}

    def test_three_states(self) -> None:
        self.assertEqual(
            self.statuses(at(10, 9), at(10, 18)),
            {"Tom Richter": "free", "Anna Becker": "planned", "Lea Vogel": "absent"},
        )

    def test_free_people_come_first(self) -> None:
        names = [row.person.name for row in people_availability(at(10, 9), at(10, 18))]
        self.assertEqual(names, ["Tom Richter", "Anna Becker", "Lea Vogel"])

    def test_a_period_next_to_the_deployment_is_free(self) -> None:
        """Touching is not overlapping: 22:00 to midnight after a deployment that ends at 22:00."""
        self.assertEqual(self.statuses(at(10, 22), at(11))["Anna Becker"], "free")
        self.assertEqual(self.statuses(at(10, 21), at(11))["Anna Becker"], "planned")

    def test_search_by_job_function(self) -> None:
        """VFG-010: who is free and can do sound?"""
        self.assertEqual(
            self.statuses(at(10, 9), at(10, 18), job_function=job_function("Tontechnik")),
            {"Anna Becker": "planned", "Lea Vogel": "absent"},
        )
        self.assertEqual(
            self.statuses(at(20), at(21), job_function=job_function("Tontechnik")),
            {"Anna Becker": "free", "Lea Vogel": "free"},
        )

    def test_absence_outranks_a_deployment(self) -> None:
        plan(self.project, "Stagehand", self.lea, start=at(10, 8), end=at(10, 14))
        row = next(row for row in people_availability(at(10, 9), at(10, 18)) if row.person == self.lea)
        self.assertEqual(row.status, "absent")
        self.assertEqual(len(row.deployments), 1)

    def test_cancelled_projects_and_deactivated_people_are_left_out(self) -> None:
        self.project.status = ProjectStatus.CANCELLED
        self.project.save()
        services.set_person_active(self.tom, active=False)
        self.assertEqual(self.statuses(at(10, 9), at(10, 18)), {"Anna Becker": "free", "Lea Vogel": "absent"})

    def test_number_of_queries_does_not_grow_with_the_people(self) -> None:
        """NFA-014."""
        for number in range(12):
            person = make_person(f"Person Nr{number}", rates={"Stagehand": "18.00"})
            plan(self.project, "Stagehand", person)
        with self.assertNumQueries(4):  # people, crew lines, absences, availability marks (PER-021)
            rows = people_availability(at(10, 9), at(10, 18))
        self.assertEqual(len(rows), 15)


class PrivacyTests(RentalarsTestCase):
    """NFA-009: information and erasure."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("anna", roles=("Crew",))
        self.anna = make_person(
            "Anna Becker",
            rates={"Tontechnik": "35.00"},
            user=self.user,
            email="anna@example.de",
            phone="0170 5550101",
            note="Allergie: Nüsse",
        )
        self.project = make_project("Stadtfest")
        self.line = plan(self.project, "Tontechnik", self.anna, note="Anna fährt den Sprinter", meeting_point="Lager")
        self.entry = record_time(
            self.anna, self.project, "Tontechnik", at(10, 8), at(10, 16), note="Aufbau mit Anna", approve=True
        )
        services.save_absence(Absence(person=self.anna, kind=AbsenceKind.SICK, start=at(20), end=at(22)))

    def test_export_contains_everything_stored_about_the_person(self) -> None:
        document = export_person(self.anna)
        self.assertEqual(document["person"]["last_name"], "Becker")
        self.assertEqual(document["person"]["user_account"], "anna")
        self.assertEqual(document["job_functions"][0]["hourly_rate"], "35.00")
        self.assertEqual(len(document["absences"]), 1)
        self.assertEqual(document["deployments"][0]["project"], self.project.number)
        self.assertEqual(document["time_entries"][0]["hours"], "8.00")

    def test_anonymising_erases_the_person_and_keeps_the_work(self) -> None:
        anonymise_person(self.anna)
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.name, f"Anonymisiert ({self.anna.pk})")
        self.assertEqual((self.anna.email, self.anna.phone, self.anna.note), ("", "", ""))
        self.assertFalse(self.anna.is_active)
        self.assertIsNotNone(self.anna.anonymised_at)
        # AUT-026: the account stays with the person, closed and without a name (next test).
        self.assertEqual(self.anna.user.username, f"anonym-{self.user.pk}")
        self.assertEqual(self.anna.absences.count(), 0)

        # The work stays: hours and rates still count in the project.
        self.line.refresh_from_db()
        self.entry.refresh_from_db()
        self.assertEqual((self.line.note, self.line.meeting_point, self.entry.note), ("", "", ""))
        self.assertEqual(self.entry.hours, Decimal("8.00"))
        self.assertEqual(self.entry.hourly_rate, Decimal("35.00"))
        self.assertEqual(crew.price_crew_lines(self.project)[0].approved_hours, Decimal("8.00"))

    def test_anonymising_closes_the_account_and_erases_its_name(self) -> None:
        """The account says who it was, too: name and address go, the tokens stop working."""
        token, _key = ApiToken.create_for_user(self.user, "Handy")
        anonymise_person(self.anna)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.username, f"anonym-{self.user.pk}")
        self.assertNotIn("anna", self.user.email)
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(self.user.roles.count(), 0)
        token.refresh_from_db()
        self.assertFalse(token.is_usable)

    def test_the_change_log_no_longer_names_the_person(self) -> None:
        # An event whose details carry the name: times moved to a line.
        loose = record_time(self.anna, self.project, "Tontechnik", at(11, 8), at(11, 10), approve=True)
        loose.crew_line = None
        loose.save()
        crew.assign_times(self.project, self.anna, job_function("Tontechnik"), self.line)

        anonymise_person(self.anna)
        log = " ".join(f"{entry.object_repr} {entry.changes}" for entry in AuditLogEntry.objects.all())
        log += " ".join(entry.actor_label for entry in AuditLogEntry.objects.all())
        for trace in ("Becker", "anna", "Anna", "0170 5550101", "Nüsse", "Sprinter"):
            self.assertNotIn(trace, log)
        self.assertTrue(AuditLogEntry.for_object(self.anna).filter(event="person.anonymised").exists())

    def test_an_administrator_account_is_not_anonymised(self) -> None:
        """Erasing the personnel data of the boss must not lock the company out: the right goes first."""
        boss = make_user("chef", superuser=True)
        person = make_person("Carl Chef", user=boss)
        with self.assertRaises(ValidationError):
            anonymise_person(person)
        boss.refresh_from_db()
        self.assertTrue(boss.is_active)
        self.assertEqual(Person.objects.get(user=boss).name, "Carl Chef")
