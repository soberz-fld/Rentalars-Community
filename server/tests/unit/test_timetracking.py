# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: time entries – recording, stopwatch, approval, reports (chapter 5.9)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError

from rentalars.accounts.models import Role, User
from rentalars.accounts.rights import Rights, rights_of
from rentalars.core.models import AuditLogEntry, SystemSettings
from rentalars.personnel import services as personnel
from rentalars.personnel.models import Person
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership, ProjectStatus
from rentalars.timetracking import services
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus, hours_between
from tests.helpers import (
    ALL_RIGHTS,
    LATER,
    NOW,
    RentalarsTestCase,
    at,
    job_function,
    make_internal_project,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)

D = Decimal


class TimeTestCase(RentalarsTestCase):
    """Anna, sound engineer and stagehand, planned on the Stadtfest; Paula manages the project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.hand = job_function("Stagehand", price="28.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"}, user=self.anna_user)
        self.line = plan(self.project, self.sound, self.anna, start=at(10, 8), end=at(10, 20))
        self.manager = make_user("paula", roles=("Projektleitung",))
        # The tests record the hours of 10 March afterwards (ZEI-022).
        set_clock(LATER)

    def record(self, start: datetime.datetime, end: datetime.datetime | None, **options: Any) -> TimeEntry:
        """Record as Anna herself, the way her browser or phone does."""
        values = {"person": self.anna, "project": self.project, "job_function": self.sound, **options}
        return services.create_entry(
            start=start, end=end, rights=rights_of(self.anna_user), user=self.anna_user, **values
        )

    def as_manager(self) -> dict[str, Any]:
        return {"rights": rights_of(self.manager), "user": self.manager}

    def as_anna(self) -> dict[str, Any]:
        return {"rights": rights_of(self.anna_user), "user": self.anna_user}


class HoursTests(RentalarsTestCase):
    """ZEI-004, ZEI-009: start, end, break."""

    def test_hours_are_end_minus_start_minus_break(self) -> None:
        self.assertEqual(hours_between(at(10, 8), at(10, 16, 30), 30), D("8.00"))
        self.assertEqual(hours_between(at(10, 8), at(10, 8, 20)), D("0.33"))

    def test_an_entry_may_run_over_midnight(self) -> None:
        self.assertEqual(hours_between(at(10, 22), at(11, 2, 15)), D("4.25"))


class RecordingTests(TimeTestCase):
    """ZEI-002, ZEI-004, ZEI-007 to ZEI-009."""

    def test_entry_belongs_to_project_and_job_function(self) -> None:
        entry = self.record(at(10, 8), at(10, 16, 30), break_minutes=30, note=" Aufbau FOH ")
        self.assertEqual((entry.person, entry.project, entry.job_function), (self.anna, self.project, self.sound))
        self.assertEqual((entry.hours, entry.note, entry.status), (D("8.00"), "Aufbau FOH", TimeEntryStatus.RECORDED))
        self.assertEqual(entry.crew_line, self.line)

    def test_rate_is_taken_from_person_and_function_and_fixed(self) -> None:
        """ZEI-008: a later change of the person's rate does not reach the entry."""
        as_sound = self.record(at(10, 8), at(10, 12))
        as_hand = self.record(at(10, 13), at(10, 17), job_function=self.hand)
        self.assertEqual((as_sound.hourly_rate, as_hand.hourly_rate), (D("35.00"), D("20.00")))
        self.assertEqual((as_sound.amount, as_hand.amount), (D("140.00"), D("80.00")))

        personnel.set_rate(self.anna, self.sound, D("38.00"), datetime.date(2027, 3, 1))
        as_sound.refresh_from_db()
        self.assertEqual(as_sound.hourly_rate, D("35.00"))
        self.assertEqual(self.record(at(11, 8), at(11, 12)).hourly_rate, D("38.00"))

    def test_rate_is_the_one_valid_on_the_day_worked(self) -> None:
        personnel.set_rate(self.anna, self.sound, D("38.00"), datetime.date(2027, 3, 11))
        self.assertEqual(self.record(at(10, 8), at(10, 12)).hourly_rate, D("35.00"))
        self.assertEqual(self.record(at(11, 8), at(11, 12)).hourly_rate, D("38.00"))

    def test_planned_outside_the_own_functions_the_rate_of_the_line_applies(self) -> None:
        """PER-006 with the special right: the person has no rate for the function, the line has."""
        rigging = job_function("Rigging")
        plan(self.project, rigging, self.anna, start=at(11, 8), end=at(11, 12), hourly_rate=D("30.00"))
        entry = self.record(at(11, 8), at(11, 12), job_function=rigging)
        self.assertEqual(entry.hourly_rate, D("30.00"))

    def test_only_job_functions_of_the_person_or_planned_in_the_project(self) -> None:
        """ZEI-007."""
        self.assertEqual(
            [function.name for function in services.job_functions_for(self.anna, self.project)],
            ["Stagehand", "Tontechnik"],
        )
        with self.assertRaises(ValidationError) as raised:
            self.record(at(10, 8), at(10, 12), job_function=job_function("Rigging"))
        self.assertIn("job_function", raised.exception.message_dict)

    def test_overlapping_entries_are_refused(self) -> None:
        """ZEI-009."""
        self.record(at(10, 8), at(10, 12))
        for start, end in (
            (at(10, 7), at(10, 9)),
            (at(10, 11), at(10, 13)),
            (at(10, 9), at(10, 10)),
            (at(10, 7), at(10, 13)),
        ):
            with self.assertRaises(ValidationError, msg=f"{start:%H:%M}–{end:%H:%M}") as raised:
                self.record(start, end, job_function=self.hand)
            self.assertIn("start", raised.exception.message_dict)
        self.assertEqual(TimeEntry.objects.count(), 1)

    def test_entries_may_touch(self) -> None:
        self.record(at(10, 8), at(10, 12))
        self.record(at(10, 12), at(10, 16))
        self.record(at(10, 6), at(10, 8))
        self.assertEqual(TimeEntry.objects.count(), 3)

    def test_other_people_may_work_at_the_same_time(self) -> None:
        kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        plan(self.project, self.hand, kai)
        self.record(at(10, 8), at(10, 12))
        record_time(kai, self.project, self.hand, at(10, 8), at(10, 12))
        self.assertEqual(TimeEntry.objects.count(), 2)

    def test_end_must_be_after_start(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            self.record(at(10, 12), at(10, 8))
        self.assertIn("end", raised.exception.message_dict)

    def test_over_midnight_is_possible_and_longer_than_a_day_is_not(self) -> None:
        self.assertEqual(self.record(at(10, 22), at(11, 2, 15)).hours, D("4.25"))
        with self.assertRaises(ValidationError):
            self.record(at(11, 8), at(12, 9))

    def test_a_break_as_long_as_the_entry_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            self.record(at(10, 8), at(10, 9), break_minutes=60)
        self.assertIn("break_minutes", raised.exception.message_dict)

    def test_no_times_on_closed_or_cancelled_projects(self) -> None:
        for status in (ProjectStatus.CLOSED, ProjectStatus.CANCELLED):
            Project.objects.filter(pk=self.project.pk).update(status=status)
            self.project.refresh_from_db()
            with self.assertRaises(ValidationError, msg=status) as raised:
                self.record(at(10, 8), at(10, 12))
            self.assertIn("project", raised.exception.message_dict)

    def test_no_times_on_a_project_the_person_is_not_planned_in(self) -> None:
        other = make_project("Jazznacht")
        with self.assertRaises(ValidationError) as raised:
            self.record(at(10, 8), at(10, 12), project=other)
        self.assertIn("project", raised.exception.message_dict)

    def test_internal_projects_take_times_of_everybody(self) -> None:
        """ZEI-010: warehouse, workshop, office."""
        warehouse = make_internal_project()
        entry = self.record(NOW - datetime.timedelta(hours=4), NOW, project=warehouse, job_function=self.hand)
        self.assertIsNone(entry.crew_line)
        self.assertTrue(entry.project.is_internal)

    def test_every_change_is_logged(self) -> None:
        """ZEI-014."""
        entry = self.record(at(10, 8), at(10, 12))
        entry_id = str(entry.pk)
        services.update_entry(entry, end=at(10, 13), **self.as_anna())
        services.delete_entry(entry, **self.as_anna())
        log = AuditLogEntry.objects.filter(object_id=entry_id, content_type__model="timeentry")
        self.assertEqual(sorted(row.action for row in log), ["created", "deleted", "updated"])
        changed = log.get(action="updated")
        self.assertIn("end", changed.changes)
        self.assertIn("hours", changed.changes)
        self.assertEqual({row.actor for row in log}, {None})  # no request: nobody is logged in here


class WhoMayRecordTests(TimeTestCase):
    """ZEI-011, NFA-010."""

    def test_nobody_records_for_somebody_else_without_the_right(self) -> None:
        kai_user = make_user("kai", roles=("Crew",))
        make_person("Kai Kurz", rates={"Stagehand": "18.00"}, user=kai_user)
        with self.assertRaises(PermissionDenied):
            services.create_entry(
                person=self.anna,
                project=self.project,
                job_function=self.sound,
                start=at(10, 8),
                end=at(10, 12),
                rights=rights_of(kai_user),
                user=kai_user,
            )

    def test_with_the_right_times_are_recorded_for_others(self) -> None:
        entry = services.create_entry(
            person=self.anna,
            project=self.project,
            job_function=self.sound,
            start=at(10, 8),
            end=at(10, 12),
            **self.as_manager(),
        )
        self.assertEqual(entry.person, self.anna)

    def test_a_reader_of_time_tracking_records_nothing(self) -> None:
        reader = make_user("rita", roles=("Nur-Lesen",))
        make_person("Rita Reader", rates={"Stagehand": "18.00"}, user=reader)
        self.assertFalse(services.may_record_for(rights_of(reader), reader, reader.person))

    def test_a_deactivated_person_records_nothing(self) -> None:
        personnel.set_person_active(self.anna, active=False)
        with self.assertRaises(ValidationError):
            self.record(at(10, 8), at(10, 12))

    def test_everybody_sees_their_own_entries_only(self) -> None:
        """ZEI-016, NFA-010."""
        kai_user = make_user("kai", roles=("Crew",))
        kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"}, user=kai_user)
        plan(self.project, self.hand, kai)
        self.record(at(10, 8), at(10, 12))
        record_time(kai, self.project, self.hand, at(10, 8), at(10, 12))
        self.assertEqual([entry.person for entry in services.visible_entries(rights_of(kai_user), kai_user)], [kai])
        self.assertEqual(services.visible_entries(rights_of(self.manager), self.manager).count(), 2)

    def test_an_account_without_person_sees_no_entries(self) -> None:
        self.record(at(10, 8), at(10, 12))
        loose = make_user("lose", roles=("Crew",))
        self.assertEqual(services.visible_entries(rights_of(loose), loose).count(), 0)

    def test_without_the_module_nothing_is_visible(self) -> None:
        self.record(at(10, 8), at(10, 12))
        warehouse = make_user("luka", roles=("Lager",))
        self.assertEqual(services.visible_entries(rights_of(warehouse), warehouse).count(), 0)

    def test_an_approver_limited_to_assigned_projects_sees_those_and_the_internal_ones(self) -> None:
        Role.objects.create(
            name="Crewchef",
            module_levels={"projects": 1, "time_tracking": 2},
            special_rights=["approve_times"],
            project_scope="assigned",
        )
        chief = make_user("chris", roles=("Crewchef",))
        other = make_project("Jazznacht")
        plan(other, self.sound, self.anna, start=at(11, 8), end=at(11, 12))
        warehouse = make_internal_project()
        self.record(at(10, 8), at(10, 12))
        self.record(at(11, 8), at(11, 12), project=other)
        self.record(NOW - datetime.timedelta(hours=2), NOW, project=warehouse, job_function=self.hand)
        ProjectMembership.objects.create(project=self.project, user=chief, level=ProjectAccessLevel.READ)

        visible = {entry.project for entry in services.visible_entries(rights_of(chief), chief)}
        self.assertEqual(visible, {self.project, warehouse})
        hidden = TimeEntry.objects.get(project=other)
        hidden.status = TimeEntryStatus.SUBMITTED
        hidden.save()
        with self.assertRaises(PermissionDenied):
            services.approve_entries([hidden], rights=rights_of(chief), user=chief)

    def test_rates_are_shown_to_those_who_may_see_them(self) -> None:
        """AUT-019, PER-010: every rate with the right; one's own unless switched off."""
        kai_user = make_user("kai", roles=("Crew",))
        make_person("Kai Kurz", user=kai_user)
        self.assertTrue(services.may_see_rate_of(rights_of(self.manager), self.manager, self.anna))
        self.assertTrue(services.may_see_rate_of(rights_of(self.anna_user), self.anna_user, self.anna))
        self.assertFalse(services.may_see_rate_of(rights_of(kai_user), kai_user, self.anna))

        settings = SystemSettings.load()
        settings.people_see_own_rates = False
        settings.save()
        self.assertFalse(services.may_see_rate_of(rights_of(self.anna_user), self.anna_user, self.anna))
        self.assertTrue(services.may_see_rate_of(rights_of(self.manager), self.manager, self.anna))


class StopwatchTests(TimeTestCase):
    """ZEI-005: start and stop instead of typing begin and end."""

    def start(self) -> TimeEntry:
        return services.start_timer(person=self.anna, project=self.project, job_function=self.sound, **self.as_anna())

    def test_start_creates_a_running_entry_from_now(self) -> None:
        entry = self.start()
        self.assertTrue(entry.is_running)
        self.assertEqual((entry.start, entry.hours, entry.hourly_rate), (LATER, D("0"), D("35.00")))
        self.assertEqual(services.running_timer(self.anna), entry)

    def test_only_one_stopwatch_runs_at_a_time(self) -> None:
        self.start()
        with self.assertRaises(ValidationError):
            self.start()

    def test_nothing_is_recorded_after_the_start_of_a_running_stopwatch(self) -> None:
        self.start()
        with self.assertRaises(ValidationError):
            self.record(LATER + datetime.timedelta(hours=1), LATER + datetime.timedelta(hours=2))
        # Before its start is fine.
        self.record(LATER - datetime.timedelta(hours=3), LATER - datetime.timedelta(hours=1))

    def test_stop_ends_the_entry_now(self) -> None:
        entry = self.start()
        TimeEntry.objects.filter(pk=entry.pk).update(start=LATER - datetime.timedelta(hours=5, minutes=30))
        stopped = services.stop_timer(person=self.anna, break_minutes=30, submit=True, **self.as_anna())
        self.assertEqual((stopped.end, stopped.hours, stopped.status), (LATER, D("5.00"), TimeEntryStatus.SUBMITTED))
        self.assertIsNone(services.running_timer(self.anna))

    def test_a_stopwatch_stopped_at_once_counts_one_minute(self) -> None:
        self.start()
        stopped = services.stop_timer(person=self.anna, **self.as_anna())
        self.assertEqual(stopped.end - stopped.start, datetime.timedelta(minutes=1))
        self.assertEqual(stopped.status, TimeEntryStatus.RECORDED)

    def test_stopping_without_a_running_stopwatch_is_an_error(self) -> None:
        with self.assertRaises(ValidationError):
            services.stop_timer(person=self.anna, **self.as_anna())

    def test_a_running_stopwatch_is_not_handed_in_and_not_in_the_report(self) -> None:
        entry = self.start()
        self.assertEqual(services.submit_entries([entry], **self.as_anna()), 0)
        report = services.hours_report(TimeEntry.objects.all(), **self.as_anna())
        self.assertEqual(report.entries, [])


class ApprovalTests(TimeTestCase):
    """ZEI-012, ZEI-013: recorded → submitted → approved (locked) or rejected."""

    def test_the_life_of_an_entry(self) -> None:
        entry = self.record(at(10, 8), at(10, 12))
        self.assertEqual(services.submit_entries([entry], **self.as_anna()), 1)
        self.assertEqual((entry.status, entry.submitted_at), (TimeEntryStatus.SUBMITTED, LATER))
        self.assertEqual(services.approve_entries([entry], **self.as_manager()), 1)
        entry.refresh_from_db()
        self.assertEqual(
            (entry.status, entry.decided_by, entry.decided_at), (TimeEntryStatus.APPROVED, self.manager, LATER)
        )
        self.assertTrue(entry.is_locked)

    def test_an_entry_can_be_handed_in_while_recording(self) -> None:
        self.assertEqual(self.record(at(10, 8), at(10, 12), submit=True).status, TimeEntryStatus.SUBMITTED)

    def test_approved_entries_are_locked_for_everybody(self) -> None:
        entry = self.record(at(10, 8), at(10, 12), submit=True)
        services.approve_entries([entry], **self.as_manager())
        entry.refresh_from_db()
        for actor in (self.as_anna(), self.as_manager()):
            with self.assertRaises(ValidationError):
                services.update_entry(entry, end=at(10, 13), **actor)
            with self.assertRaises(ValidationError):
                services.delete_entry(entry, **actor)
        self.assertEqual(TimeEntry.objects.get(pk=entry.pk).end, at(10, 12))

    def test_only_those_with_the_right_approve(self) -> None:
        entry = self.record(at(10, 8), at(10, 12), submit=True)
        with self.assertRaises(PermissionDenied):
            services.approve_entries([entry], **self.as_anna())
        with self.assertRaises(PermissionDenied):
            services.reject_entries([entry], "Nein", **self.as_anna())
        planner = make_user("dora", roles=("Personaldisposition",))
        self.assertEqual(services.approve_entries([entry], rights=rights_of(planner), user=planner), 1)

    def test_many_entries_are_approved_at_once_and_only_the_submitted_ones(self) -> None:
        """ZEI-013: collected per project or period."""
        submitted = [self.record(at(10, hour), at(10, hour + 1), submit=True) for hour in (8, 10, 12)]
        still_open = self.record(at(10, 14), at(10, 15))
        self.assertEqual(services.approve_entries([*submitted, still_open], **self.as_manager()), 3)
        still_open.refresh_from_db()
        self.assertEqual(still_open.status, TimeEntryStatus.RECORDED)
        self.assertEqual(services.approve_entries(submitted, **self.as_manager()), 0)

    def test_rejecting_needs_a_reason_and_sends_the_entry_back(self) -> None:
        entry = self.record(at(10, 8), at(10, 12), submit=True)
        with self.assertRaises(ValidationError) as raised:
            services.reject_entries([entry], "  ", **self.as_manager())
        self.assertIn("reason", raised.exception.message_dict)
        services.reject_entries([entry], "Ende war 11 Uhr", **self.as_manager())
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.rejection_reason), (TimeEntryStatus.REJECTED, "Ende war 11 Uhr"))

        # Correcting it starts anew: recorded, then handed in again without the old reason.
        corrected = services.update_entry(entry, end=at(10, 11), **self.as_anna())
        self.assertEqual(
            (corrected.status, corrected.hours, corrected.decided_by), (TimeEntryStatus.RECORDED, D("3.00"), None)
        )
        services.submit_entries([corrected], **self.as_anna())
        self.assertEqual((corrected.status, corrected.rejection_reason), (TimeEntryStatus.SUBMITTED, ""))

    def test_an_approval_can_be_taken_back_and_that_is_logged(self) -> None:
        entry = self.record(at(10, 8), at(10, 12), submit=True)
        services.approve_entries([entry], **self.as_manager())
        with self.assertRaises(PermissionDenied):
            services.take_back_approval(entry, **self.as_anna())
        services.take_back_approval(entry, **self.as_manager())
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.decided_by), (TimeEntryStatus.SUBMITTED, None))
        self.assertTrue(AuditLogEntry.for_object(entry).filter(event="time_entry.approval_taken_back").exists())
        with self.assertRaises(ValidationError):
            services.take_back_approval(entry, **self.as_manager())

    def test_a_line_planned_after_recording_gets_the_time_at_approval(self) -> None:
        """ZEI-021."""
        entry = self.record(at(11, 8), at(11, 12), job_function=self.hand, submit=True)
        self.assertIsNone(entry.crew_line)
        line = plan(self.project, self.hand, self.anna, start=at(11, 8), end=at(11, 14))
        entry.refresh_from_db()
        services.approve_entries([entry], **self.as_manager())
        entry.refresh_from_db()
        self.assertEqual(entry.crew_line, line)


class EditingTests(TimeTestCase):
    """ZEI-012: open entries can be corrected."""

    def test_changing_the_job_function_reads_the_rate_again(self) -> None:
        entry = self.record(at(10, 8), at(10, 12))
        changed = services.update_entry(entry, job_function=self.hand, **self.as_anna())
        self.assertEqual((changed.hourly_rate, changed.crew_line), (D("20.00"), None))

    def test_changing_only_the_time_keeps_the_rate(self) -> None:
        entry = self.record(at(10, 8), at(10, 12))
        personnel.set_rate(self.anna, self.sound, D("38.00"), datetime.date(2027, 3, 1))
        changed = services.update_entry(entry, end=at(10, 14), **self.as_anna())
        self.assertEqual((changed.hourly_rate, changed.hours), (D("35.00"), D("6.00")))

    def test_a_correction_must_not_overlap_either(self) -> None:
        self.record(at(10, 8), at(10, 12))
        second = self.record(at(10, 13), at(10, 15))
        with self.assertRaises(ValidationError):
            services.update_entry(second, start=at(10, 11), **self.as_anna())

    def test_person_status_and_rate_cannot_be_set_from_outside(self) -> None:
        entry = self.record(at(10, 8), at(10, 12))
        for change in ({"status": "approved"}, {"hourly_rate": D("99")}, {"person": self.anna}, {"hours": D("20")}):
            with self.assertRaises(ValidationError, msg=change):
                services.update_entry(entry, **change, **self.as_anna())

    def test_somebody_else_changes_nothing(self) -> None:
        entry = self.record(at(10, 8), at(10, 12))
        kai_user = make_user("kai", roles=("Crew",))
        make_person("Kai Kurz", user=kai_user)
        with self.assertRaises(PermissionDenied):
            services.update_entry(entry, note="x", rights=rights_of(kai_user), user=kai_user)
        with self.assertRaises(PermissionDenied):
            services.delete_entry(entry, rights=rights_of(kai_user), user=kai_user)


class ProjectChoiceTests(TimeTestCase):
    """ZEI-006: the project the person is planned in right now comes first, with its job function."""

    def choices(self, moment: datetime.datetime, user: User | None = None) -> list[tuple[str, str, str | None]]:
        user = user or self.anna_user
        person = Person.objects.get(user=user) if user is self.anna_user else self.anna
        return [
            (choice.project.name, choice.reason, choice.job_function.name if choice.job_function else None)
            for choice in services.project_choices(person, rights_of(user), user, at=moment)
        ]

    def test_during_the_deployment_the_project_is_first_with_its_function(self) -> None:
        make_internal_project("Lager")
        self.assertEqual(self.choices(at(10, 9)), [("Stadtfest", "now", "Tontechnik"), ("Lager", "internal", None)])

    def test_before_the_deployment_the_project_is_offered_as_planned(self) -> None:
        make_internal_project("Lager")
        self.assertEqual(self.choices(NOW)[0], ("Stadtfest", "planned", "Tontechnik"))

    def test_a_few_days_after_the_deployment_it_is_still_first(self) -> None:
        """The hours of Saturday night are usually written down on Monday."""
        self.assertEqual(self.choices(at(13, 9))[0][:2], ("Stadtfest", "now"))
        self.assertEqual(self.choices(at(25, 9))[0][:2], ("Stadtfest", "planned"))

    def test_of_two_current_projects_the_one_begun_last_is_first(self) -> None:
        later = make_project("Jazznacht", start=at(11), end=at(12))
        plan(later, self.hand, self.anna, start=at(11, 18), end=at(11, 23))
        self.assertEqual([name for name, *_rest in self.choices(at(11, 19))], ["Jazznacht", "Stadtfest"])
        self.assertEqual(self.choices(at(11, 19))[0][2], "Stagehand")

    def test_cancelled_and_foreign_projects_are_not_offered_to_crew(self) -> None:
        make_project("Hochzeit", start=at(10), end=at(11))
        self.project.status = ProjectStatus.CANCELLED
        self.project.save()
        self.assertEqual(self.choices(at(10, 9)), [])

    def test_a_manager_is_offered_the_running_projects_they_may_see(self) -> None:
        make_person("Paula Planer", rates={"Projektleitung": "45.00"}, user=self.manager)
        make_project("Hochzeit", start=at(20), end=at(21))
        offered = services.project_choices(self.manager.person, rights_of(self.manager), self.manager, at=at(10, 9))
        self.assertEqual([(choice.project.name, choice.reason) for choice in offered], [("Stadtfest", "other")])


class ReportTests(TimeTestCase):
    """ZEI-015 to ZEI-017: sums by person, project, job function and day."""

    def setUp(self) -> None:
        super().setUp()
        self.kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        plan(self.project, self.hand, self.kai)
        self.warehouse = make_internal_project("Lager")
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 16), approve=True)
        record_time(self.anna, self.project, self.hand, at(11, 8), at(11, 12), submit=True)
        record_time(self.kai, self.project, self.hand, at(10, 8), at(10, 14), approve=True)
        record_time(self.kai, self.warehouse, self.hand, NOW - datetime.timedelta(hours=3), NOW)

    def report(
        self, group_by: str, rights: Rights = ALL_RIGHTS, user: Any = None, **filters: Any
    ) -> services.HoursReport:
        return services.hours_report(TimeEntry.objects.filter(**filters), group_by=group_by, rights=rights, user=user)

    def test_by_person(self) -> None:
        report = self.report("person")
        self.assertEqual(
            [(row.label, row.hours, row.amount) for row in report.rows],
            [("Becker, Anna", D("12.00"), D("360.00")), ("Kurz, Kai", D("9.00"), D("162.00"))],
        )
        self.assertEqual((report.total_hours, report.total_amount), (D("21.00"), D("522.00")))

    def test_by_project(self) -> None:
        rows = {row.label: row.hours for row in self.report("project").rows}
        self.assertEqual(rows, {str(self.project): D("18.00"), str(self.warehouse): D("3.00")})

    def test_by_job_function(self) -> None:
        rows = [(row.label, row.hours) for row in self.report("job_function").rows]
        self.assertEqual(rows, [("Stagehand", D("13.00")), ("Tontechnik", D("8.00"))])

    def test_by_day_in_order_of_time(self) -> None:
        rows = [(row.label, row.hours) for row in self.report("day").rows]
        self.assertEqual(rows, [("01.03.2027", D("3.00")), ("10.03.2027", D("14.00")), ("11.03.2027", D("4.00"))])

    def test_filtered_by_person_and_period(self) -> None:
        report = self.report("day", person=self.anna, start__gte=at(11))
        self.assertEqual((report.total_hours, len(report.entries)), (D("4.00"), 1))

    def test_an_unknown_grouping_falls_back_to_person(self) -> None:
        self.assertEqual(self.report("colour").group_by, "person")

    def test_without_the_cost_right_amounts_of_others_are_left_out(self) -> None:
        """AUT-019, PER-010: a sum that would include a hidden amount is not shown too small – it is not shown."""
        rights = rights_of(self.anna_user)
        own = services.hours_report(
            services.visible_entries(rights, self.anna_user), group_by="person", rights=rights, user=self.anna_user
        )
        self.assertEqual((own.total_hours, own.total_amount), (D("12.00"), D("360.00")))

        Role.objects.create(
            name="Freigabe ohne Kosten",
            module_levels={"projects": 1, "time_tracking": 2},
            special_rights=["approve_times"],
        )
        approver = make_user("fred", roles=("Freigabe ohne Kosten",))
        report = self.report("project", rights_of(approver), approver)
        self.assertEqual(report.total_hours, D("21.00"))
        self.assertIsNone(report.total_amount)
        self.assertTrue(all(row.amount is None for row in report.rows))

    def test_week_of_a_day(self) -> None:
        self.assertEqual(
            services.week_of(datetime.date(2027, 3, 10)), (datetime.date(2027, 3, 8), datetime.date(2027, 3, 14))
        )
        self.assertEqual(services.week_of(datetime.date(2027, 3, 8))[0], datetime.date(2027, 3, 8))


class NothingInTheFutureTests(TimeTestCase):
    """ZEI-022: hours are written down after they were worked, never before."""

    def test_an_end_after_now_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            self.record(LATER - datetime.timedelta(hours=2), LATER + datetime.timedelta(minutes=1))
        self.assertEqual(set(raised.exception.message_dict), {"end"})
        self.assertIn("28.03. 18:00", raised.exception.message_dict["end"][0])
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_a_begin_after_now_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            self.record(LATER + datetime.timedelta(hours=1), LATER + datetime.timedelta(hours=3))
        self.assertEqual(set(raised.exception.message_dict), {"start", "end"})

    def test_ending_right_now_is_allowed(self) -> None:
        entry = self.record(LATER - datetime.timedelta(hours=2), LATER)
        self.assertEqual(entry.hours, D("2.00"))

    def test_a_correction_into_the_future_is_refused(self) -> None:
        entry = self.record(at(10, 8), at(10, 12))
        with self.assertRaises(ValidationError):
            services.update_entry(entry, end=LATER + datetime.timedelta(hours=1), **self.as_anna())
        entry.refresh_from_db()
        self.assertEqual(entry.end, at(10, 12))

    def test_nobody_may_record_future_hours_for_others_either(self) -> None:
        with self.assertRaises(ValidationError):
            services.create_entry(
                person=self.anna,
                project=self.project,
                job_function=self.sound,
                start=LATER + datetime.timedelta(days=1),
                end=LATER + datetime.timedelta(days=1, hours=4),
                **self.as_manager(),
            )

    def test_the_stopwatch_begins_now_and_is_therefore_never_in_the_future(self) -> None:
        entry = services.start_timer(person=self.anna, project=self.project, job_function=self.sound, **self.as_anna())
        self.assertEqual(entry.start, LATER)


class WithoutProjectTests(TimeTestCase):
    """ZEI-023: a time can be recorded without project; it is approved once a project is assigned."""

    def record_without(self, **options: Any) -> TimeEntry:
        return self.record(at(10, 8), at(10, 12), project=None, **options)

    def test_recorded_with_one_of_the_own_job_functions(self) -> None:
        entry = self.record_without(submit=True)
        self.assertIsNone(entry.project)
        self.assertIsNone(entry.crew_line)
        self.assertEqual((entry.hourly_rate, entry.status), (D("35.00"), TimeEntryStatus.SUBMITTED))
        self.assertEqual(entry.project_label, "ohne Projekt")

    def test_a_function_the_person_does_not_have_needs_a_project(self) -> None:
        """A function planned only in a project needs that project."""
        rigging = job_function("Rigging")
        plan(self.project, rigging, self.anna, start=at(11, 8), end=at(11, 12), hourly_rate=D("30.00"))
        with self.assertRaises(ValidationError) as raised:
            self.record(at(11, 8), at(11, 12), project=None, job_function=rigging)
        self.assertIn("job_function", raised.exception.message_dict)

    def test_without_project_it_cannot_be_approved(self) -> None:
        entry = self.record_without(submit=True)
        with self.assertRaises(ValidationError) as raised:
            services.approve_entries([entry], **self.as_manager())
        self.assertIn("project", raised.exception.message_dict)
        entry.refresh_from_db()
        self.assertEqual(entry.status, TimeEntryStatus.SUBMITTED)

    def test_the_person_assigns_the_project_and_it_counts_from_approval_on(self) -> None:
        entry = self.record_without(submit=True)
        services.assign_project(entry, self.project, **self.as_anna())
        entry.refresh_from_db()
        self.assertEqual(
            (entry.project, entry.crew_line, entry.status), (self.project, self.line, TimeEntryStatus.SUBMITTED)
        )
        self.assertEqual(services.approve_entries([entry], **self.as_manager()), 1)
        from rentalars.projects import crew

        self.assertEqual(crew.price_crew_lines(self.project)[0].approved_hours, D("4.00"))

    def test_an_approver_assigns_the_project_and_approves(self) -> None:
        entry = self.record_without(submit=True)
        services.assign_project(entry, self.project, **self.as_manager())
        entry.refresh_from_db()
        self.assertEqual(services.approve_entries([entry], **self.as_manager()), 1)

    def test_a_project_the_person_is_not_planned_in_is_refused(self) -> None:
        other = make_project("Jazznacht")
        entry = self.record_without()
        with self.assertRaises(ValidationError):
            services.assign_project(entry, other, **self.as_anna())

    def test_it_can_be_sent_back_without_project(self) -> None:
        entry = self.record_without(submit=True)
        self.assertEqual(services.reject_entries([entry], "Welches Projekt?", **self.as_manager()), 1)

    def test_seen_by_the_person_and_by_approvers_for_all_projects_only(self) -> None:
        entry = self.record_without(submit=True)
        self.assertIn(entry, services.visible_entries(rights_of(self.anna_user), self.anna_user))
        self.assertIn(entry, services.visible_entries(rights_of(self.manager), self.manager))
        Role.objects.create(
            name="Crewchef",
            module_levels={"projects": 1, "time_tracking": 2},
            special_rights=["approve_times"],
            project_scope="assigned",
        )
        chief = make_user("chris", roles=("Crewchef",))
        self.assertNotIn(entry, services.visible_entries(rights_of(chief), chief))
        with self.assertRaises(PermissionDenied):
            services.reject_entries([entry], "nein", rights=rights_of(chief), user=chief)

    def test_the_stopwatch_runs_without_project_too(self) -> None:
        entry = services.start_timer(person=self.anna, project=None, job_function=self.sound, **self.as_anna())
        self.assertIsNone(entry.project)

    def test_the_report_lists_it_as_without_project(self) -> None:
        self.record_without()
        self.record(at(11, 8), at(11, 10))
        report = services.hours_report(TimeEntry.objects.all(), group_by="project", **self.as_manager())
        self.assertEqual(
            sorted((row.label, row.hours) for row in report.rows),
            # ADM-014: "2027-0001 …" sorts before "Ohne Projekt" again.
            sorted([(str(self.project), D("2.00")), ("Ohne Projekt", D("4.00"))]),
        )
