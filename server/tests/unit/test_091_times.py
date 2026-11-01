# SPDX-License-Identifier: GPL-3.0-or-later
"""Reminders of the times to approve (ZEI-029), the correction by the approver (ZEI-030), telling the person
(ZEI-031); all people available (VFG-038).

The requirement: authorised people get a notification at defined times (like for open points) when there are times
waiting for approval (Personal → Freigeben); possibly the approver can make the correction themselves instead of only
sending the time back; the person concerned is notified as well on approval, change or sending back.

The requirement: Personal → Verfügbarkeit can also show people who do not have the chosen job function (e.g. an
entry "alle" in the dropdown "Funktion" for everybody available, whatever job functions are assigned).

* Reminders: Einstellungen → Benachrichtigungen, once a day at the time set, first after N days, then every N days;
  only to who may approve, only of what they may approve, not of their own; made up once after a downtime.
* "Korrigieren" on Personal → Freigeben: corrected and approved in one step, the values before in the history – page
  (with and without the page script) and ``POST /time-entries/{id}/correct``.
* The person is told once per action: approved, corrected, sent back with the reason.
* Personal → Verfügbarkeit, "Alle Personen": also people without any job function.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import rights_of
from rentalars.core.history import describe
from rentalars.core.models import AuditLogEntry, NotificationSettings
from rentalars.documents import invoice_reminders
from rentalars.notifications.models import ApprovalNotice, InvoiceNotice, Kind, Notification
from rentalars.personnel.availability import people_availability
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership
from rentalars.timetracking import expenses, services
from rentalars.timetracking.models import ExpenseKind, TimeEntry, TimeEntryStatus
from rentalars.timetracking.reminders import remind_due, run_due_approval_reminders
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)
from tests.ui.base import UiTestCase, form_data
from tests.unit import test_085_invoices as invoices_085


def told(person: object, kind: str = Kind.TIME_DECISION) -> list[Notification]:
    """The notifications of one kind a person (or user) got, oldest first."""
    user = getattr(person, "user", person)
    return list(Notification.objects.filter(user=user, kind=kind).order_by("id"))


class TimesCase(RentalarsTestCase):
    """A project in February, Anna and Tom planned on it, Paula approves (role "Projektleitung")."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Messe", start=at(20, month=2), end=at(28, month=2))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "18.00"})
        self.tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        plan(self.project, "Tontechnik", self.anna)
        plan(self.project, "Tontechnik", self.tom)
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.rights = rights_of(self.paula)

    def times(self, person: object, count: int, *, submit: bool = True) -> list[TimeEntry]:
        """``count`` entries of two hours each, from 20 February on, handed in (on 1 March 08:00)."""
        entries = []
        for number in range(count):
            day, hour = 20 + number // 4, 6 + 3 * (number % 4)
            entries.append(
                record_time(
                    person,
                    self.project,
                    "Tontechnik",
                    at(day, hour, month=2),
                    at(day, hour + 2, month=2),
                    submit=submit,
                )
            )
        return entries


class DecisionNoticeTests(TimesCase):
    """The person is told once per action: approved, sent back with the reason (ZEI-031)."""

    def test_approving_twenty_entries_tells_each_person_once(self) -> None:
        entries = self.times(self.anna, 12) + self.times(self.tom, 8)
        self.assertEqual(services.approve_entries(entries, rights=self.rights, user=self.paula), 20)
        (anna,) = told(self.anna)
        self.assertEqual(anna.title, "12 Zeiteinträge freigegeben (24 Std.)")
        self.assertEqual(anna.body.count("\n"), 10)  # 10 entries named, then "… und 2 weitere"
        self.assertIn("… und 2 weitere", anna.body)
        self.assertIn("Sa 20.02. 06:00–08:00, Tontechnik", anna.body)
        self.assertEqual(anna.url, reverse("timetracking:my_times"))
        (tom,) = told(self.tom)
        self.assertEqual(tom.title, "8 Zeiteinträge freigegeben (16 Std.)")

    def test_sent_back_with_the_reason(self) -> None:
        entries = self.times(self.anna, 2)
        services.reject_entries(entries, "Pause fehlt", rights=self.rights, user=self.paula)
        (anna,) = told(self.anna)
        self.assertEqual(anna.title, "2 Zeiteinträge zurückgegeben (4 Std.)")
        self.assertTrue(anna.body.startswith("Grund: Pause fehlt\n"), anna.body)

    def test_nobody_is_told_about_own_decisions(self) -> None:
        plan(self.project, "Tontechnik", self.paula.person)
        own = self.times(self.paula.person, 1)
        services.approve_entries(own, rights=self.rights, user=self.paula)
        self.assertEqual(told(self.paula), [])

    def test_the_kinds_have_their_categories(self) -> None:
        from rentalars.notifications.categories import Category, category_of
        from rentalars.notifications.services import choice

        self.assertEqual(category_of(Kind.TIME_DECISION), Category.PERSONNEL)
        self.assertEqual(category_of(Kind.TIMES_TO_APPROVE), Category.PERSONNEL)
        self.assertEqual(choice(self.paula, Kind.TIME_DECISION), (True, True, False))


class CorrectionTests(TimesCase):
    """``services.correct_and_approve``: corrected and approved, the values before kept (ZEI-030)."""

    def test_corrected_approved_and_kept_in_the_history(self) -> None:
        (entry,) = self.times(self.anna, 1)
        corrected = services.correct_and_approve(
            entry,
            rights=self.rights,
            user=self.paula,
            end=at(20, 7, 30, month=2),
            break_minutes=15,
            note="Aufbau Halle 2",
        )
        self.assertEqual(corrected.status, TimeEntryStatus.APPROVED)
        self.assertEqual((corrected.hours, corrected.decided_by), (Decimal("1.25"), self.paula))
        changed = AuditLogEntry.objects.filter(object_id=str(entry.pk), action="updated", changes__has_key="end").get()
        self.assertEqual(changed.changes["break_minutes"], [0, 15])
        event = AuditLogEntry.objects.get(object_id=str(entry.pk), event="time_entry.corrected")
        self.assertEqual(event.changes["before"], "Sa 20.02. 06:00–08:00, Tontechnik, " + entry.project_label)
        history = " ".join(item.summary for item in describe(list(AuditLogEntry.for_object(self.anna)), ALL_RIGHTS))
        self.assertIn("Bei der Freigabe korrigiert – vorher: Sa 20.02. 06:00–08:00", history)
        self.assertIn("„Aufbau Halle 2“", history)
        (notice,) = told(self.anna)
        self.assertTrue(
            notice.title.startswith("Deine Zeit wurde korrigiert und freigegeben: Sa 20.02. 06:00–07:30 (−15 min)")
        )
        self.assertEqual(notice.body, "Vorher: Sa 20.02. 06:00–08:00, Tontechnik, " + entry.project_label)

    def test_without_changes_it_is_approved(self) -> None:
        (entry,) = self.times(self.anna, 1)
        services.correct_and_approve(entry, rights=self.rights, user=self.paula, note="")
        entry.refresh_from_db()
        self.assertEqual(entry.status, TimeEntryStatus.APPROVED)
        self.assertFalse(AuditLogEntry.objects.filter(event="time_entry.corrected").exists())
        self.assertEqual(told(self.anna)[0].title, "1 Zeiteintrag freigegeben (2 Std.)")

    def test_refused(self) -> None:
        (entry,) = self.times(self.anna, 1, submit=False)
        with self.assertRaises(ValidationError):  # not handed in
            services.correct_and_approve(entry, rights=self.rights, user=self.paula, break_minutes=15)
        services.submit_entries([entry], rights=ALL_RIGHTS, user=None)
        crew_user = self.anna.user
        crew_user.roles.set(Role.objects.filter(name="Crew"))
        with self.assertRaises(PermissionDenied):  # Anna may not approve, not even her own time
            services.correct_and_approve(entry, rights=rights_of(crew_user), user=crew_user, break_minutes=15)
        with self.assertRaises(ValidationError):  # the rules of recording hold: no overlap
            other = record_time(self.anna, self.project, "Tontechnik", at(27, 8, month=2), at(27, 10, month=2))
            services.correct_and_approve(other, rights=self.rights, user=self.paula, start=at(20, 7, month=2))
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.break_minutes), (TimeEntryStatus.SUBMITTED, 0))
        self.assertEqual(told(self.anna), [])

    def test_the_new_project_must_be_approvable_too(self) -> None:
        Role.objects.create(
            name="Crew-Chef",
            module_levels={"projects": 1, "time_tracking": 2},
            special_rights=["approve_times"],
            project_scope="assigned",
        )
        chief = make_user("chef", roles=("Crew-Chef",))
        ProjectMembership.objects.create(project=self.project, user=chief, level=ProjectAccessLevel.READ)
        other = make_project("Gala", start=at(20, month=2), end=at(28, month=2))
        plan(other, "Tontechnik", self.anna)
        (entry,) = self.times(self.anna, 1)
        with self.assertRaises(PermissionDenied):
            services.correct_and_approve(entry, rights=rights_of(chief), user=chief, project=other)
        entry.refresh_from_db()
        self.assertEqual((entry.project, entry.status), (self.project, TimeEntryStatus.SUBMITTED))

    def test_a_part_of_a_divided_period(self) -> None:
        """ZEI-025: times change for the whole period, which is approved as a whole."""
        first = services.create_entry(
            person=self.anna,
            project=self.project,
            job_function=job_function("Tontechnik"),
            start=at(21, 8, month=2),
            end=at(21, 16, month=2),
            rights=ALL_RIGHTS,
            user=None,
            submit=True,
            parts=[services.Part(job_function("Tontechnik"), Decimal("5")), services.Part(job_function("Stagehand"))],
        )
        second = next(part for part in services.period_of(first) if part.pk != first.pk)
        services.correct_and_approve(second, rights=self.rights, user=self.paula, end=at(21, 17, month=2))
        rows = list(TimeEntry.objects.filter(period_key=first.period_key))
        self.assertEqual({row.status for row in rows}, {TimeEntryStatus.APPROVED})
        self.assertEqual({row.end for row in rows}, {at(21, 17, month=2)})
        self.assertEqual(sum(row.hours for row in rows), Decimal("9"))
        self.assertEqual(len(told(self.anna)), 1)


class ApprovalPageTests(UiTestCase):
    """Personal → Freigeben: "Korrigieren" – with and without the page script; telling once per action.

    ZEI-030 (correction by the approver), ZEI-031 (telling the person).
    """

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Messe", start=at(20, month=2), end=at(28, month=2))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        plan(self.project, "Tontechnik", self.anna)
        plan(self.project, "Tontechnik", self.tom)
        self.entry = record_time(
            self.anna, self.project, "Tontechnik", at(20, 8, month=2), at(20, 16, month=2), submit=True
        )
        self.url = reverse("timetracking:entry_correct", args=[self.entry.pk])
        self.approval = reverse("timetracking:approval")

    def test_the_link_in_every_row(self) -> None:
        page = self.assert_ok(self.client.get(self.approval, {"person": self.anna.pk}))
        self.assertIn(f'href="{self.url}?next=', page)
        self.assertIn(f'hx-get="{self.url}?next=', page)
        self.assertIn("Korrigieren und freigeben: Anna Becker, Sa 20.02.", page)

    def test_with_the_page_script(self) -> None:
        dialog = self.htmx("get", self.url)
        text = self.assert_ok(dialog)
        self.assertIn("Speichern und freigeben", text)
        self.assertIn("Eingereicht von Anna Becker:", text)
        self.assertNotIn("assign later", text)
        self.assertNotIn("später zuordnen", text)
        data = form_data(dialog, "day", end="15:30", break_minutes="30")
        response = self.htmx("post", self.url, data)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Trigger"], "timesChanged, closeDialog")
        self.entry.refresh_from_db()
        self.assertEqual(
            (self.entry.status, self.entry.end, self.entry.break_minutes), ("approved", at(20, 15, 30, month=2), 30)
        )
        self.assertEqual(len(told(self.anna)), 1)

    def test_without_the_page_script(self) -> None:
        back = f"{self.approval}?person={self.anna.pk}"
        page = self.assert_ok(self.client.get(self.url, {"next": back}))
        self.assertIn("<h1>Korrigieren und freigeben</h1>", page)
        data = form_data(self.client.get(self.url, {"next": back}), "day", note="korrigiert")
        response = self.client.post(self.url, data)
        self.assertRedirects(response, back, fetch_redirect_response=False)
        page = self.client.get(back)
        self.assertIn("Die Zeit von Anna Becker wurde korrigiert und freigegeben.", self.messages_of(page))
        # Approved: no longer to be corrected here.
        response = self.client.get(self.url)
        self.assertRedirects(response, self.approval, fetch_redirect_response=False)
        response = self.htmx("get", self.url)
        self.assertEqual((response.status_code, response["HX-Redirect"]), (204, self.approval))

    def test_rights(self) -> None:
        crew = self.browser_of(self.anna.user)
        self.anna.user.roles.set(Role.objects.filter(name="Crew"))
        self.assertEqual(crew.get(self.url).status_code, 403)
        self.assertEqual(crew.post(self.url, {"note": "x"}).status_code, 403)
        self.assertEqual(self.browser_for("nora", "Nur-Lesen").get(self.url).status_code, 403)

    def test_approving_on_the_page_tells_each_person_once(self) -> None:
        more = [
            record_time(self.anna, self.project, "Tontechnik", at(21, 8, month=2), at(21, 16, month=2), submit=True),
            record_time(self.tom, self.project, "Tontechnik", at(21, 8, month=2), at(21, 16, month=2), submit=True),
        ]
        ids = [self.entry.pk, *(entry.pk for entry in more)]
        self.client.post(reverse("timetracking:decide"), {"entry": ids, "decision": "approve"})
        self.assertEqual([notice.title for notice in told(self.anna)], ["2 Zeiteinträge freigegeben (16 Std.)"])
        self.assertEqual(len(told(self.tom)), 1)


class CorrectionApiTests(ApiTestCase):
    """``POST /time-entries/{id}/correct`` (ZEI-030)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Messe", start=at(20, month=2), end=at(28, month=2))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(self.project, "Tontechnik", self.anna)
        self.entry = record_time(
            self.anna, self.project, "Tontechnik", at(20, 8, month=2), at(20, 16, month=2), submit=True
        )
        self.url = f"{API}/time-entries/{self.entry.pk}/correct"

    def test_correct(self) -> None:
        response = self.admin.post(self.url, {"break_minutes": 45, "note": "Pause nachgetragen"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual((data["status"], data["break_minutes"], data["hours"]), ("approved", 45, "7.25"))
        self.assertEqual(len(told(self.anna)), 1)
        # Approved now: nothing more to correct.
        self.assert_error(self.admin.post(self.url, {"break_minutes": 30}, format="json"), 400, "validation_error")

    def test_refused(self) -> None:
        crew = self.client_of(self.anna.user)
        self.anna.user.roles.set(Role.objects.filter(name="Crew"))
        self.assert_error(crew.post(self.url, {"break_minutes": 30}, format="json"), 403, "permission_denied")
        self.assert_error(
            self.admin.post(self.url, {"person": self.anna.pk}, format="json"), 400, "validation_error", "person"
        )
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, TimeEntryStatus.SUBMITTED)


class ReminderTests(TimesCase):
    """When and whom the times waiting are reminded of (Einstellungen → Benachrichtigungen, ZEI-029)."""

    def setUp(self) -> None:
        super().setUp()
        self.times(self.anna, 2)  # handed in on 1 March, 08:00
        expenses.create_expense(
            person=self.tom,
            project=self.project,
            kind=ExpenseKind.MEALS,
            date=datetime.date(2027, 2, 27),
            amount=Decimal("12.50"),
            rights=ALL_RIGHTS,
            user=None,
            submit=True,
        )
        self.assertIsNone(run_due_approval_reminders(at(1, 8)))  # the first minute after the update notes its time

    def reminders(self, user: object) -> list[Notification]:
        return told(user, Kind.TIMES_TO_APPROVE)

    def test_the_next_morning_once_with_the_count(self) -> None:
        self.assertIsNone(run_due_approval_reminders(at(1, 9)))
        self.assertIsNone(run_due_approval_reminders(at(2, 7, 59)))
        self.assertEqual(run_due_approval_reminders(at(2, 8)), 1)
        (reminder,) = self.reminders(self.paula)
        self.assertEqual(reminder.title, "Warten auf deine Freigabe: 2 Zeiteinträge, 1 Spesenposten")
        self.assertIn("Der älteste wurde am Mo 01.03.2027 eingereicht.", reminder.body)
        self.assertEqual(reminder.url, reverse("timetracking:approval"))
        self.assertIsNone(run_due_approval_reminders(at(2, 8, 1)))  # claimed: of two runs only one reminds
        self.assertIsNone(run_due_approval_reminders(at(2, 18)))
        self.assertEqual(run_due_approval_reminders(at(3, 8)), 1)  # every day while something waits
        self.assertEqual(len(self.reminders(self.paula)), 2)
        settings_row = NotificationSettings.load()
        self.assertEqual((settings_row.approval_checked_at, settings_row.approval_reminded), (at(3, 8), 1))

    def test_after_a_downtime_once(self) -> None:
        self.assertEqual(run_due_approval_reminders(at(2, 8)), 1)
        # The server is off from the 2nd at noon until the 5th at 10:00: one reminder, not three.
        self.assertEqual(run_due_approval_reminders(at(5, 10)), 1)
        self.assertIsNone(run_due_approval_reminders(at(5, 10, 1)))
        self.assertEqual(len(self.reminders(self.paula)), 2)

    def test_first_after_and_then_every(self) -> None:
        settings_row = NotificationSettings.load()
        settings_row.approval_first_days, settings_row.approval_every_days = 2, 3
        settings_row.save()
        self.assertEqual(run_due_approval_reminders(at(2, 8)), 0)  # handed in yesterday: not yet
        self.assertEqual(run_due_approval_reminders(at(3, 8)), 1)
        self.assertEqual(run_due_approval_reminders(at(4, 8)), 0)
        self.assertEqual(run_due_approval_reminders(at(5, 8)), 0)
        self.assertEqual(run_due_approval_reminders(at(6, 8)), 1)
        self.assertEqual(ApprovalNotice.objects.get(user=self.paula).count, 2)

    def test_only_who_may_approve_only_what_they_may_approve_not_their_own(self) -> None:
        Role.objects.create(
            name="Crew-Chef",
            module_levels={"projects": 1, "time_tracking": 2},
            special_rights=["approve_times"],
            project_scope="assigned",
        )
        chief = make_user("chef", roles=("Crew-Chef",))
        other = make_project("Gala", start=at(20, month=2), end=at(28, month=2))
        ProjectMembership.objects.create(project=other, user=chief, level=ProjectAccessLevel.READ)
        plan(other, "Tontechnik", self.paula.person)
        record_time(self.paula.person, other, "Tontechnik", at(20, 8, month=2), at(20, 10, month=2), submit=True)
        make_user("nora", roles=("Nur-Lesen",))
        self.assertEqual(run_due_approval_reminders(at(2, 8)), 2)
        self.assertEqual(
            self.reminders(self.paula)[0].title, "Warten auf deine Freigabe: 2 Zeiteinträge, 1 Spesenposten"
        )
        self.assertEqual(self.reminders(chief)[0].title, "Warten auf deine Freigabe: 1 Zeiteintrag")
        self.assertEqual(Notification.objects.filter(kind=Kind.TIMES_TO_APPROVE).count(), 2)

    def test_nothing_waiting_starts_anew_and_switched_off_is_quiet(self) -> None:
        self.assertEqual(run_due_approval_reminders(at(2, 8)), 1)
        waiting = list(TimeEntry.objects.filter(status=TimeEntryStatus.SUBMITTED))
        services.approve_entries(waiting, rights=self.rights, user=self.paula)
        expenses.approve_expenses(list(expenses.Expense.objects.all()), rights=self.rights, user=self.paula)
        self.assertEqual(run_due_approval_reminders(at(3, 8)), 0)
        self.assertFalse(ApprovalNotice.objects.exists())
        settings_row = NotificationSettings.load()
        settings_row.approval_reminders = False
        settings_row.save()
        self.times(self.tom, 1)
        self.assertIsNone(run_due_approval_reminders(at(5, 8)))
        self.assertEqual(len(self.reminders(self.paula)), 1)

    def test_on_the_minute_timer(self) -> None:
        set_clock(at(2, 8))
        call_command("run_jobs", verbosity=0)
        self.assertEqual(len(self.reminders(self.paula)), 1)


class ReminderSettingsTests(UiTestCase):
    """Einstellungen → Benachrichtigungen, and ``/settings/notifications`` (ZEI-029)."""

    def test_the_page(self) -> None:
        url = reverse("notifications:company_settings")
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Zeiten zur Freigabe", page)
        self.assertIn("An Zeiten zur Freigabe erinnern", page)
        self.assertIn('id="approval-check-times"', page)
        data = form_data(self.client.get(url), "approval_time", approval_time="07:30", approval_every_days="2")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        settings_row = NotificationSettings.load()
        self.assertEqual((settings_row.approval_time, settings_row.approval_every_days), (datetime.time(7, 30), 2))


class ReminderSettingsApiTests(ApiTestCase):
    """The settings through the API (ZEI-029)."""

    def test_read_and_change(self) -> None:
        url = f"{API}/settings/notifications"
        data = self.admin.get(url).json()
        self.assertEqual((data["approval_reminders"], data["approval_time"]), (True, "08:00:00"))
        self.assertEqual((data["approval_first_days"], data["approval_every_days"]), (1, 1))
        self.assertIn("approval_next_check", data)
        data = self.admin.patch(url, {"approval_first_days": 0, "approval_reminders": False}, format="json").json()
        self.assertEqual((data["approval_first_days"], data["approval_next_check"]), (0, None))
        self.assert_error(self.admin.patch(url, {"approval_every_days": 0}, format="json"), 400, "validation_error")


class AvailabilityOfAllTests(UiTestCase):
    """Personal → Verfügbarkeit: "Alle Personen" – also without job function; the filter as before (VFG-038)."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.olga = make_person("Olga Office")  # no job function at all

    def test_all_people_whatever_their_job_functions(self) -> None:
        names = [row.person.name for row in people_availability(at(10, 9), at(10, 18))]
        self.assertIn("Olga Office", names)
        self.assertIn("Anna Becker", names)
        names = [
            row.person.name
            for row in people_availability(at(10, 9), at(10, 18), job_function=job_function("Tontechnik"))
        ]
        self.assertEqual(names, ["Anna Becker"])
        page = self.assert_ok(
            self.client.get(reverse("personnel:availability"), {"start": "2027-03-10T09:00", "end": "2027-03-10T18:00"})
        )
        self.assertIn("Alle Personen, unabhängig von der Funktion", page)
        self.assertIn("Office, Olga", page)
        page = self.assert_ok(
            self.client.get(
                reverse("personnel:availability"),
                {"start": "2027-03-10T09:00", "end": "2027-03-10T18:00", "job_function": job_function("Tontechnik").pk},
            )
        )
        self.assertNotIn("Office, Olga", page)


class ReminderCalendarDayTests(TimesCase):
    """ZEI-029: "then again every N days" counts days of the local calendar, not hours – no day is
    skipped by the change to summer time, by a reminder made up after a downtime or by a run that started late."""

    def setUp(self) -> None:
        super().setUp()
        self.times(self.anna, 2)  # handed in on 1 March, 08:00
        self.assertIsNone(run_due_approval_reminders(at(1, 8)))  # the first minute after the update notes its time

    def count(self) -> int:
        """How often Paula was reminded."""
        return ApprovalNotice.objects.get(user=self.paula).count

    def test_the_day_of_the_change_to_summer_time(self) -> None:
        """Reminded on Saturday 27 March 08:00 (CET); 08:00 on Sunday (CEST) is only 23 hours later."""
        self.assertEqual(run_due_approval_reminders(at(27, 8)), 1)
        self.assertEqual(run_due_approval_reminders(at(28, 8)), 1)
        self.assertIsNone(run_due_approval_reminders(at(28, 8, 1)))  # of two runs only one reminds
        self.assertEqual(run_due_approval_reminders(at(29, 8)), 1)
        self.assertEqual(self.count(), 3)

    def test_made_up_after_a_downtime_then_the_next_morning(self) -> None:
        self.assertEqual(run_due_approval_reminders(at(2, 8)), 1)
        self.assertEqual(run_due_approval_reminders(at(3, 10)), 1)  # the server was off at 08:00: made up once
        self.assertIsNone(run_due_approval_reminders(at(3, 10, 1)))
        self.assertEqual(run_due_approval_reminders(at(4, 8)), 1)  # 22 hours later, but the next day
        self.assertEqual(self.count(), 3)

    def test_a_run_that_started_twenty_minutes_late(self) -> None:
        self.assertEqual(run_due_approval_reminders(at(2, 8, 20)), 1)
        self.assertEqual(run_due_approval_reminders(at(3, 8)), 1)
        self.assertEqual(remind_due(at(3, 18)), 0)  # once a day at most, however often it is asked
        self.assertEqual(self.count(), 2)

    def test_every_two_days(self) -> None:
        settings_row = NotificationSettings.load()
        settings_row.approval_every_days = 2
        settings_row.save()
        self.assertEqual(run_due_approval_reminders(at(2, 8, 20)), 1)
        self.assertEqual(run_due_approval_reminders(at(3, 8)), 0)
        self.assertEqual(run_due_approval_reminders(at(4, 8)), 1)
        self.assertEqual(run_due_approval_reminders(at(5, 8)), 0)
        self.assertEqual(run_due_approval_reminders(at(6, 10)), 1)  # made up late
        self.assertEqual(run_due_approval_reminders(at(7, 8)), 0)
        self.assertEqual(run_due_approval_reminders(at(8, 8)), 1)
        self.assertEqual(self.count(), 4)


class InvoiceReminderCalendarDayTests(invoices_085.InvoiceCase):
    """DOK-015 (as ZEI-029): the reminders of invoices had the same flaw – "every 7 days" in hours."""

    def test_the_week_across_the_change_to_summer_time(self) -> None:
        invoices_085.invoices_in_rentalars(False)
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(21, 9)), 1)  # made up: the first reminder
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(27, 9)), 0)
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(28, 9)), 1)  # 7 days, 167 hours
        self.assertEqual(InvoiceNotice.objects.get(project=self.project).count, 2)

    def test_a_check_that_started_late(self) -> None:
        invoices_085.invoices_in_rentalars(False)
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(2, 9, 20)), 1)
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(8, 9)), 0)
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(9, 9)), 1)
        self.assertEqual(InvoiceNotice.objects.get(project=self.project).count, 2)
