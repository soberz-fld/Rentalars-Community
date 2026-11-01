# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "service": people taking part in a service case (PRJ-108), the way to work deducted from trips
(ZEI-027) and the hints at working times switched on and off centrally (ZEI-018).
"""

from __future__ import annotations

import datetime
from decimal import Decimal as D  # noqa: N817

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.core.models import AuditAction, AuditLogEntry, SystemSettings
from rentalars.notifications.models import Kind, Notification
from rentalars.personnel.privacy import anonymise_person, export_person
from rentalars.projects import service_cases
from rentalars.projects.access import ProjectAccess, access_level, access_of_many, visible_projects
from rentalars.projects.models import ServiceCaseParticipant
from rentalars.timetracking import expenses
from rentalars.timetracking.hints import HintLimits, hints_for
from rentalars.timetracking.models import Expense, ExpenseKind
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_project,
    make_user,
    record_time,
)
from tests.unit.test_080_times import ExpenseCase, TimesCase


class ParticipantCase(RentalarsTestCase):
    """A service case of Paula; Kai (crew, assigned projects only) and Lea are technicians."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.case = service_cases.create_case(name="Spot flackert", manager=self.paula, user=self.paula)
        self.kai_user = make_user("kai", roles=("Crew",))
        self.kai = make_person("Kai Kurz", user=self.kai_user)
        self.light = job_function("Lichttechnik")


class ParticipantTests(ParticipantCase):
    """PRJ-108: person, optional job function and note; told when added; in the change log."""

    def test_adding_tells_the_person_and_logs_ids(self) -> None:
        """PRJ-108: "people can be added … they get notified"; the change log keeps references as IDs."""
        participation = service_cases.add_participant(
            self.case, self.kai, job_function=self.light, note="Ersatzlampe mitnehmen", user=self.paula
        )
        self.assertEqual(
            (participation.person, participation.job_function, participation.note, participation.added_by),
            (self.kai, self.light, "Ersatzlampe mitnehmen", self.paula),
        )
        told = Notification.objects.get(user=self.kai_user)
        self.assertEqual(told.kind, Kind.SERVICE_CASE)  # its own kind since the review
        self.assertEqual(told.title, f"Du bist am Servicefall {self.case.number} Spot flackert beteiligt")
        self.assertIn("Als: Lichttechnik", told.body)
        self.assertEqual(told.url, reverse("projects:case_detail", args=[self.case]))
        entry = AuditLogEntry.objects.get(
            action=AuditAction.CREATED, content_type__model="servicecaseparticipant", object_id=str(participation.pk)
        )
        self.assertEqual(entry.changes["person"], [None, self.kai.pk])
        self.assertEqual(entry.changes["job_function"], [None, self.light.pk])
        self.assertEqual(entry.parent_object_id, str(self.case.pk))

    def test_adding_oneself_tells_nobody(self) -> None:
        """PRJ-108: the one who acts is not told about it."""
        service_cases.add_participant(self.case, self.kai, user=self.kai_user)
        self.assertFalse(Notification.objects.filter(user=self.kai_user).exists())

    def test_adding_again_changes_function_and_note(self) -> None:
        """PRJ-108: one place per person; adding again changes function and note, and tells nobody again."""
        service_cases.add_participant(self.case, self.kai, user=self.paula)
        service_cases.add_participant(self.case, self.kai, job_function=self.light, note="Leiter", user=self.paula)
        participation = ServiceCaseParticipant.objects.get()
        self.assertEqual((participation.job_function, participation.note), (self.light, "Leiter"))
        self.assertEqual(Notification.objects.filter(user=self.kai_user).count(), 1)

    def test_only_service_cases_and_active_people(self) -> None:
        """PRJ-108: a project has crew, not participants; a deactivated person cannot be added."""
        project = make_project("Stadtfest")
        with self.assertRaises(ValidationError):
            service_cases.add_participant(project, self.kai)
        self.kai.is_active = False
        self.kai.save()
        with self.assertRaises(ValidationError):
            service_cases.add_participant(self.case, self.kai)

    def test_removing_keeps_the_times(self) -> None:
        """PRJ-108: taking somebody off the case leaves the times on it."""
        participation = service_cases.add_participant(self.case, self.kai, user=self.paula)
        entry = record_time(self.kai, self.case, self.light, at(1, 6), at(1, 7))
        service_cases.remove_participant(participation)
        self.assertFalse(ServiceCaseParticipant.objects.exists())
        entry.refresh_from_db()
        self.assertEqual(entry.project, self.case)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditAction.DELETED, content_type__model="servicecaseparticipant"
            ).exists()
        )

    def test_the_own_cases(self) -> None:
        """PRJ-108: the cases the person takes part in, open and in progress; with the user those they lead."""
        service_cases.add_participant(self.case, self.kai, job_function=self.light, user=self.paula)
        done = service_cases.create_case(name="Kabel tauschen")
        service_cases.add_participant(done, self.kai, user=self.paula)
        service_cases.set_case_status(done, "done")
        own = service_cases.create_case(name="Eigener Fall", manager=self.kai_user)
        found = list(service_cases.cases_of(self.kai, self.kai_user))
        self.assertEqual({case.name for case in found}, {"Spot flackert", "Eigener Fall"})
        case = next(case for case in found if case.pk == self.case.pk)
        self.assertEqual(case.my_participation[0].job_function, self.light)
        self.assertEqual(
            {case.name for case in service_cases.cases_of(self.kai, statuses=["open", "in_progress", "done"])},
            {"Spot flackert", "Kabel tauschen"},
        )
        self.assertNotIn(own.pk, [case.pk for case in service_cases.cases_of(self.kai)])


class ParticipantAccessTests(ParticipantCase):
    """PRJ-108: with a role for assigned projects only, taking part opens the case for reading."""

    def test_taking_part_opens_the_case(self) -> None:
        """PRJ-108, AUT-016: before taking part Kai does not see the case; afterwards he reads it."""
        rights = self.kai_user.rights
        self.assertEqual(access_level(rights, self.kai_user, self.case), ProjectAccess.NONE)
        self.assertNotIn(self.case, visible_projects(rights, self.kai_user))
        service_cases.add_participant(self.case, self.kai, user=self.paula)
        self.assertEqual(access_level(rights, self.kai_user, self.case), ProjectAccess.READ)
        self.assertIn(self.case, visible_projects(rights, self.kai_user))
        self.assertEqual(access_of_many(rights, self.kai_user, [self.case.pk]), {self.case.pk: ProjectAccess.READ})

    def test_a_crew_line_still_gives_the_deployment_view(self) -> None:
        """AUT-018 unchanged: crew lines and participations come from one query."""
        from tests.helpers import plan

        project = make_project("Stadtfest")
        plan(project, self.light, self.kai)
        service_cases.add_participant(self.case, self.kai, user=self.paula)
        levels = access_of_many(self.kai_user.rights, self.kai_user, [project.pk, self.case.pk])
        self.assertEqual(levels, {project.pk: ProjectAccess.DEPLOYMENT, self.case.pk: ProjectAccess.READ})

    def test_a_converted_case_is_no_longer_opened_by_taking_part(self) -> None:
        """PRJ-108: taking part opens service cases only; a case turned into a project needs crew or membership."""
        service_cases.add_participant(self.case, self.kai, user=self.paula)
        service_cases.convert_to_project(self.case, start=at(10), end=at(11), is_internal=True)
        self.case.refresh_from_db()
        rights = self.kai_user.rights
        self.assertEqual(access_level(rights, self.kai_user, self.case), ProjectAccess.NONE)
        self.assertNotIn(self.case, visible_projects(rights, self.kai_user))
        self.assertEqual(access_of_many(rights, self.kai_user, [self.case.pk]), {self.case.pk: ProjectAccess.NONE})


class ParticipantPrivacyTests(ParticipantCase):
    """NFA-009: the participations are told about a person; the free text of the note is erased."""

    def test_export_and_anonymise(self) -> None:
        """PRJ-108, ZEI-027, NFA-009."""
        self.kai.commute_km = D("14")
        self.kai.save()
        self.kai.refresh_from_db()
        service_cases.add_participant(self.case, self.kai, note="mit Kai Kurz abgesprochen", user=self.paula)
        exported = export_person(self.kai)
        self.assertEqual(exported["person"]["distance_home_company_km"], "14.0")
        self.assertEqual(exported["service_cases"][0]["service_case"], self.case.number)
        anonymise_person(self.kai)
        self.kai.refresh_from_db()
        self.assertIsNone(self.kai.commute_km)
        self.assertEqual(ServiceCaseParticipant.objects.get().note, "")


# --- ZEI-027 -------------------------------------------------------------------------------------------------------


class CommuteTests(ExpenseCase):
    """ZEI-027: Anna lives 14 km from the company; 28 km a day per project are hers."""

    def setUp(self) -> None:
        super().setUp()
        self.anna.commute_km = D("14")
        self.anna.save()

    def trip(self, kilometres: str, **more) -> Expense:
        return self.spend(ExpenseKind.TRAVEL, amount=None, kilometres=D(kilometres), **more)

    def test_twice_the_distance_is_deducted(self) -> None:
        """ZEI-027: "42 km − 28 km Arbeitsweg = 14 km" at 0.30 € is 4.20 €."""
        trip = self.trip("42")
        self.assertEqual((trip.commute_km, trip.billable_kilometres, trip.amount), (D("28"), D("14"), D("4.20")))
        self.assertEqual(trip.distance_label, "42 km − 28 km Arbeitsweg = 14 km")

    def test_once_per_day_and_project(self) -> None:
        """ZEI-027: a short trip takes up what it can (0 €), the next one the rest; another project or day anew."""
        first = self.trip("20")
        self.assertEqual((first.commute_km, first.amount), (D("20"), D("0.00")))
        self.assertEqual(first.distance_label, "20 km − 20 km Arbeitsweg = 0 km")
        second = self.trip("30")
        self.assertEqual((second.commute_km, second.amount), (D("8"), D("6.60")))
        third = self.trip("30")
        self.assertIsNone(third.commute_km)
        self.assertEqual((third.amount, third.distance_label), (D("9.00"), "30 km"))
        elsewhere = self.trip("30", project=self.warehouse)
        self.assertEqual(elsewhere.commute_km, D("28"))
        next_day = self.trip("30", date=datetime.date(2027, 3, 11))
        self.assertEqual(next_day.commute_km, D("28"))

    def test_changing_the_kilometres_calculates_anew(self) -> None:
        """ZEI-027: a changed trip is calculated without itself; a changed note keeps the deduction."""
        trip = self.trip("42")
        expenses.update_expense(trip, rights=self.crew_rights, user=self.anna_user, kilometres=D("50"))
        self.assertEqual((trip.commute_km, trip.amount), (D("28"), D("6.60")))
        self.anna.commute_km = D("5")
        self.anna.save()
        expenses.update_expense(trip, rights=self.crew_rights, user=self.anna_user, note="Lager – Halle")
        self.assertEqual((trip.commute_km, trip.amount), (D("28"), D("6.60")))
        expenses.update_expense(trip, rights=self.crew_rights, user=self.anna_user, kind=ExpenseKind.PARKING)
        self.assertIsNone(trip.commute_km)

    def test_without_distance_or_switched_off_nothing_is_deducted(self) -> None:
        """ZEI-027: an empty distance deducts nothing; a setting can switch the deduction off."""
        settings = SystemSettings.load()
        settings.expense_deduct_commute = False
        settings.save()
        self.assertIsNone(self.trip("42").commute_km)
        settings.expense_deduct_commute = True
        settings.save()
        self.anna.commute_km = None
        self.anna.save()
        trip = self.trip("42")
        self.assertEqual((trip.commute_km, trip.amount), (None, D("12.60")))

    def test_trips_recorded_before_keep_their_amount(self) -> None:
        """ZEI-027: "existing expenses unchanged" – a trip without deduction keeps it when its note changes."""
        self.anna.commute_km = None
        self.anna.save()
        trip = self.trip("42")
        self.anna.commute_km = D("14")
        self.anna.save()
        expenses.update_expense(trip, rights=self.crew_rights, user=self.anna_user, note="Nachtrag")
        self.assertEqual((trip.commute_km, trip.amount), (None, D("12.60")))

    def test_an_amount_of_zero_only_for_a_trip_taken_up_by_the_way_to_work(self) -> None:
        """ZEI-027: every other expense still needs at least 0.01."""
        with self.assertRaises(ValidationError) as raised:
            self.spend(amount="0")
        self.assertIn("amount", raised.exception.message_dict)
        with self.assertRaises(ValidationError):
            self.spend(ExpenseKind.TRAVEL, amount="0")

    def test_the_csv_names_the_deduction(self) -> None:
        """ZEI-027: the CSV of the expenses has the kilometres of the way to work."""
        self.trip("42", submit=True)
        report = expenses.expense_report(Expense.objects.all())
        rows = expenses.expenses_csv(report).lstrip("﻿").splitlines()
        self.assertIn("Kilometer;Arbeitsweg (km);Satz je Kilometer", rows[0])
        self.assertIn(";Fahrt;42;28;0,30;4,20;", rows[1])


# --- ZEI-018 -------------------------------------------------------------------------------------------------------


class HintSwitchTests(TimesCase):
    """ZEI-018: "Hinweise zu Arbeitszeiten anzeigen" – on by default; off, no hint anywhere."""

    def test_on_by_default_and_off_at_once(self) -> None:
        """ZEI-018: the limits stay; the switch decides."""
        entry = self.work(at(10, 8), at(10, 20), pause=45)
        self.assertTrue(SystemSettings.load().time_hints_enabled)
        self.assertTrue(hints_for([entry]))
        settings = SystemSettings.load()
        settings.time_hints_enabled = False
        settings.save()
        self.assertFalse(HintLimits.load().any)
        self.assertEqual(hints_for([entry]), {})
        self.assertEqual(SystemSettings.load().time_hint_day_hours, D("10"))

    def test_the_csv_of_the_report_has_no_hints(self) -> None:
        """ZEI-018: the column stays, empty."""
        from rentalars.timetracking import services
        from rentalars.timetracking.export import report_csv

        self.work(at(10, 8), at(10, 20), pause=45)
        settings = SystemSettings.load()
        settings.time_hints_enabled = False
        settings.save()
        report = services.hours_report(services.visible_entries(ALL_RIGHTS, None), rights=ALL_RIGHTS, user=None)
        self.assertNotIn("Langer Arbeitstag", report_csv(report, ALL_RIGHTS, None))
