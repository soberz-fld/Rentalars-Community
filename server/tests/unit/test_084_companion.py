# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "companion": when each field of a project changed (PRJ-113, PRJ-114).

The moment is noted in ``Project.save`` whatever way the change takes; these
tests change projects and service cases through the services the browser
and the automations use, and check the update that fills the new column
from the change log.
"""

from __future__ import annotations

import datetime

from rentalars.projects import field_changes, service_cases, services
from rentalars.projects.follow_up import clear_follow_up, set_follow_up
from rentalars.projects.models import CaseStatus, CaseWaitingFor, Project, ProjectStatus
from tests.helpers import ALL_RIGHTS, NOW, RentalarsTestCase, at, make_customer, make_project, make_user, set_clock

HOUR = datetime.timedelta(hours=1)


def times(project: Project) -> dict[str, datetime.datetime]:
    """The moments as stored now."""
    return field_changes.times_of(Project.objects.get(pk=project.pk))


class FieldChangeTimesTests(RentalarsTestCase):
    """PRJ-113: every save notes the moment of the keys whose fields it changes – and only those."""

    def setUp(self) -> None:
        super().setUp()
        self.admin_user = make_user("admin", superuser=True)
        self.project = make_project("Stadtfest", venue="Marktplatz", status=ProjectStatus.INQUIRY)
        set_clock(NOW + HOUR)

    def test_a_new_project_has_its_creation_for_every_key(self) -> None:
        stored = times(self.project)
        self.assertEqual(set(stored), set(field_changes.TRACKED))
        self.assertEqual(set(stored.values()), {NOW})
        self.assertEqual(set(Project.objects.get(pk=self.project.pk).field_changed_at), set(field_changes.TRACKED))

    def test_only_the_keys_of_changed_fields_get_the_moment(self) -> None:
        services.update_project(Project.objects.get(pk=self.project.pk), name="Stadtfest 2027", notes="Bühne")
        stored = times(self.project)
        self.assertEqual((stored["name"], stored["notes"]), (NOW + HOUR, NOW + HOUR))
        self.assertEqual((stored["venue"], stored["start"], stored["status"], stored["follow_up"]), (NOW,) * 4)

    def test_saving_the_same_values_notes_nothing(self) -> None:
        project = Project.objects.get(pk=self.project.pk)
        project.start = at(10)  # the moment stored, written in the time zone of Berlin instead of UTC
        project.name = "Stadtfest"
        project.save()
        self.assertEqual(set(times(self.project).values()), {NOW})

    def test_status_and_follow_up(self) -> None:
        project = Project.objects.get(pk=self.project.pk)
        services.change_status(project, ProjectStatus.OPTION, rights=ALL_RIGHTS)
        set_clock(NOW + 2 * HOUR)
        set_follow_up(project, on=datetime.date(2027, 3, 5), by=self.admin_user)
        stored = times(self.project)
        self.assertEqual((stored["status"], stored["follow_up"], stored["name"]), (NOW + HOUR, NOW + 2 * HOUR, NOW))
        set_clock(NOW + 3 * HOUR)
        clear_follow_up(project)
        self.assertEqual(times(self.project)["follow_up"], NOW + 3 * HOUR)

    def test_a_partial_save_keeps_the_moment_of_a_change_made_in_between(self) -> None:
        """The follow-up writes its fields only; the moment of the name, changed meanwhile, stays."""
        stale = Project.objects.get(pk=self.project.pk)
        services.update_project(Project.objects.get(pk=self.project.pk), name="Neu")
        set_clock(NOW + 2 * HOUR)
        set_follow_up(stale, on=datetime.date(2027, 3, 5), by=self.admin_user)
        stored = times(self.project)
        self.assertEqual((stored["name"], stored["follow_up"]), (NOW + HOUR, NOW + 2 * HOUR))

    def test_a_service_case_and_its_status(self) -> None:
        """PRJ-114: the status of a case with what it waits for – and the follow-up that comes with it."""
        case = service_cases.create_case(name="Spot flackert", customer=make_customer("Theater"))
        set_clock(NOW + 2 * HOUR)
        service_cases.set_case_status(
            case,
            CaseStatus.WAITING,
            waiting_for=CaseWaitingFor.REPLY,
            follow_up={"on": datetime.date(2027, 3, 5)},
            by=self.admin_user,
        )
        stored = times(case)
        self.assertEqual(
            (stored["case_status"], stored["follow_up"], stored["name"]), (NOW + 2 * HOUR,) * 2 + (NOW + HOUR,)
        )
        set_clock(NOW + 3 * HOUR)
        service_cases.set_case_status(
            case,
            CaseStatus.WAITING,
            waiting_for=CaseWaitingFor.ACTION,
            follow_up={"on": datetime.date(2027, 3, 5)},
            by=self.admin_user,
        )
        stored = times(case)
        # What it waits for belongs to the status; the follow-up stayed the same.
        self.assertEqual((stored["case_status"], stored["follow_up"]), (NOW + 3 * HOUR, NOW + 2 * HOUR))
        set_clock(NOW + 4 * HOUR)
        clear_follow_up(Project.objects.get(pk=case.pk))  # PRJ-112: without its follow-up it is open again
        stored = times(case)
        self.assertEqual(Project.objects.get(pk=case.pk).case_status, CaseStatus.OPEN)
        self.assertEqual((stored["case_status"], stored["follow_up"]), (NOW + 4 * HOUR, NOW + 4 * HOUR))

    def test_a_field_loaded_later_does_not_hide_a_change(self) -> None:
        project = Project.objects.only("pk", "name", "created_at").get(pk=self.project.pk)
        project.name = "Neu"
        self.assertEqual(project.notes, "")  # loads a field not loaded before
        project.save()
        self.assertEqual(Project.objects.get(pk=self.project.pk).name, "Neu")
        self.assertEqual((times(self.project)["name"], times(self.project)["venue"]), (NOW + HOUR, NOW))

    def test_a_project_built_by_hand_is_compared_with_the_database(self) -> None:
        stored = Project.objects.get(pk=self.project.pk)
        by_hand = Project(**{field.attname: getattr(stored, field.attname) for field in Project._meta.concrete_fields})
        by_hand._state.adding = False
        by_hand.venue = "Rathaus"
        by_hand.save()
        self.assertEqual((times(self.project)["venue"], times(self.project)["name"]), (NOW + HOUR, NOW))

    def test_a_reload_starts_the_comparison_anew(self) -> None:
        project = Project.objects.get(pk=self.project.pk)
        Project.objects.filter(pk=project.pk).update(name="Anders")  # changed elsewhere, without a moment
        project.refresh_from_db()
        project.save()
        self.assertEqual(times(self.project)["name"], NOW)

    def test_without_a_noted_moment_a_key_counts_from_the_creation(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(field_changed_at={})
        self.assertEqual(set(times(self.project).values()), {NOW})

    def test_a_moment_from_the_phone_is_noted_for_its_keys_only(self) -> None:
        """``changes_at``: the keys sent carry the phone's moment, every other change the server's clock."""
        project = Project.objects.get(pk=self.project.pk)
        phone = NOW + datetime.timedelta(minutes=30)
        with field_changes.changes_at(project, {"name": phone}):
            services.update_project(project, name="Vom Telefon", venue="Rathaus")
        stored = times(self.project)
        self.assertEqual((stored["name"], stored["venue"]), (phone, NOW + HOUR))
        # Never back: an earlier moment for a key changed later on the server keeps the later one.
        with field_changes.changes_at(project, {"venue": NOW + datetime.timedelta(minutes=10)}):
            services.update_project(project, venue="Kirche")
        self.assertEqual(times(self.project)["venue"], NOW + HOUR)


class MomentParsingTests(RentalarsTestCase):
    def test_moments_with_their_time_zone(self) -> None:
        self.assertEqual(field_changes.parse_moment("2027-03-01T09:30:00+01:00"), at(1, 9, 30))
        self.assertEqual(field_changes.parse_moment("2027-03-01T08:30:00Z"), at(1, 9, 30))
        # "+01:00" in an address that was not encoded arrives as " 01:00".
        self.assertEqual(field_changes.parse_moment("2027-03-01T09:30:00 01:00"), at(1, 9, 30))
        self.assertIsNone(field_changes.parse_moment(""))
        self.assertIsNone(field_changes.parse_moment(None))

    def test_no_moment_or_no_time_zone_is_refused(self) -> None:
        from django.core.exceptions import ValidationError

        for wrong in ("2027-03-01T09:30:00", "gestern", "2027-13-01T09:30:00+01:00", 42):
            with self.subTest(value=wrong), self.assertRaises(ValidationError) as caught:
                field_changes.parse_moment(wrong)
            self.assertIn("changed_at", caught.exception.message_dict)
