# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "shortages": when, how often and how far ahead shortages are reported (VFG-036).

The tests play in March 2027 (Berlin): Monday 1 March is "now" at 08:00; Good Friday is 26 March. The projects of
the examples begin on 10 March; the stock of "Topteil" is 2 pieces, a project wants 5 – a shortage of 3.
"""

from __future__ import annotations

import datetime
import importlib
import io
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.core.models import AuditLogEntry, NotificationSettings, ShortageInterval
from rentalars.notifications import schedule
from rentalars.notifications.forms import NotificationSettingsForm
from rentalars.notifications.models import Kind, Notification, ShortageNotice
from rentalars.notifications.services import check_shortages, run_due_shortage_check, schedule_changed
from rentalars.projects.models import Project, ProjectStatus
from tests.helpers import RentalarsTestCase, add_line, at, make_project, make_stock, make_user, set_clock

FOUR_FIFTEEN = datetime.time(4, 15)
#: DOK-015: the form also holds the reminders of invoices – their defaults.
INVOICE_DEFAULTS = {
    "invoice_reminders": "on",
    "invoice_time": "09:00",
    "invoice_first_days": "1",
    "invoice_every_days": "7",
    # DOK-015: "Auch Servicefälle" is on by default.
    "invoice_service_cases": "on",
    # ZEI-029: the reminders of the times to approve are part of the same form; their defaults.
    "approval_reminders": "on",
    "approval_time": "08:00",
    "approval_first_days": "1",
    "approval_every_days": "1",
}


def plan(**values: Any) -> SimpleNamespace:
    """A schedule as the settings hold it, without the database."""
    defaults = {"shortage_interval": ShortageInterval.DAILY, "shortage_weekday": 1, "shortage_time": FOUR_FIFTEEN}
    return SimpleNamespace(**(defaults | values))


def configure(*, last_run: datetime.datetime | None = None, **values: Any) -> NotificationSettings:
    """Set the settings of the company and when the schedule counts from."""
    settings = NotificationSettings.load()
    for name, value in values.items():
        setattr(settings, name, value)
    settings.save()
    NotificationSettings.objects.filter(pk=1).update(shortage_last_run=last_run)
    return NotificationSettings.objects.get(pk=1)


class ScheduleTests(RentalarsTestCase):
    """VFG-036: the moments of the checks – every day, on working days, once a week, never."""

    def test_every_day(self) -> None:
        self.assertEqual(schedule.latest_slot(plan(), at(1, 8)), at(1, 4, 15))
        self.assertEqual(schedule.latest_slot(plan(), at(1, 4, 14)), at(28, 4, 15, month=2))
        self.assertEqual(schedule.latest_slot(plan(), at(1, 4, 15)), at(1, 4, 15))
        self.assertEqual(schedule.first_slot_after(plan(), at(1, 4, 15)), at(2, 4, 15))
        self.assertEqual(schedule.first_slot_after(plan(), at(1, 4, 14)), at(1, 4, 15))

    def test_working_days_leave_out_the_weekend_and_the_holidays(self) -> None:
        """Monday to Friday; Good Friday and Easter Monday of the whole of Germany are holidays."""
        workdays = plan(shortage_interval=ShortageInterval.WORKDAYS)
        holidays = schedule.holiday_test()
        self.assertEqual(schedule.latest_slot(workdays, at(7, 12)), at(5, 4, 15))  # Sunday → Friday
        self.assertEqual(schedule.first_slot_after(workdays, at(5, 12)), at(8, 4, 15))  # Friday → Monday
        self.assertEqual(schedule.first_slot_after(workdays, at(25, 12), holidays), at(30, 4, 15))
        self.assertEqual(schedule.latest_slot(workdays, at(29, 12), holidays), at(25, 4, 15))
        # Without the holidays the quick test of the minute timer gives a later moment, never an earlier one.
        self.assertEqual(schedule.latest_slot(workdays, at(29, 12)), at(29, 4, 15))

    def test_own_holidays_count_as_well(self) -> None:
        from rentalars.core.models import OwnHoliday

        OwnHoliday.objects.create(name="Betriebsausflug", kind="once", date=datetime.date(2027, 3, 3))
        workdays = plan(shortage_interval=ShortageInterval.WORKDAYS, shortage_time=datetime.time(9, 0))
        self.assertEqual(schedule.first_slot_after(workdays, at(2, 10), schedule.holiday_test()), at(4, 9))

    def test_once_a_week(self) -> None:
        thursday = plan(shortage_interval=ShortageInterval.WEEKLY, shortage_weekday=4)
        self.assertEqual(schedule.latest_slot(thursday, at(1, 8)), at(25, 4, 15, month=2))
        self.assertEqual(schedule.first_slot_after(thursday, at(1, 8)), at(4, 4, 15))

    def test_switched_off(self) -> None:
        off = plan(shortage_interval=ShortageInterval.OFF)
        self.assertIsNone(schedule.latest_slot(off, at(1, 8)))
        self.assertIsNone(schedule.first_slot_after(off, at(1, 8)))
        self.assertIsNone(schedule.next_run(SimpleNamespace(**vars(off), shortage_last_run=at(1, 4, 15))))

    def test_next_run(self) -> None:
        self.assertEqual(schedule.next_run(plan(shortage_last_run=at(1, 4, 15)), at(1, 8)), at(2, 4, 15))
        # Overdue – the server was off at 4:15: the next minute.
        self.assertEqual(schedule.next_run(plan(shortage_last_run=at(28, 4, 15, month=2)), at(1, 8)), at(1, 8))
        self.assertEqual(schedule.next_run(plan(shortage_last_run=None), at(1, 8)), at(2, 4, 15))


class DefaultsTests(RentalarsTestCase):
    """VFG-036: the defaults are the behaviour as before – with known shortages reported again."""

    def test_defaults(self) -> None:
        settings = NotificationSettings.load()
        self.assertEqual(
            (
                settings.shortage_interval,
                settings.shortage_time,
                settings.shortage_lead_weeks,
                settings.shortage_repeat,
            ),
            # VFG-036 (tests/unit/test_093_notifications.py): "erneut melden" is on by default.
            (ShortageInterval.DAILY, FOUR_FIFTEEN, 4, True),
        )

    def test_after_the_update_the_first_check_is_at_the_next_time(self) -> None:
        """Installed at 08:00, the first check is the next 4:15 – as the nightly job would have done it."""
        migration = importlib.import_module("rentalars.core.migrations.0001_squashed_0021_invoice_085")
        NotificationSettings.objects.all().delete()  # a queryset delete: the row the migration made
        migration.create_settings(apps, None)
        migration.create_settings(apps, None)  # again: nothing changes
        self.assertEqual(NotificationSettings.objects.count(), 1)
        self.assertIsNone(NotificationSettings.objects.get(pk=1).shortage_last_run)
        self.assertIsNone(run_due_shortage_check())  # the first minute of the timer
        settings = NotificationSettings.objects.get(pk=1)
        self.assertEqual((settings.shortage_last_run, settings.shortage_checked_at), (at(1, 8), None))
        self.assertEqual(schedule.next_run(settings), at(2, 4, 15))

    def test_saving_the_settings_keeps_the_bookkeeping_of_the_check(self) -> None:
        """A form loaded before a check must not write back the old time of the last check."""
        settings = configure(last_run=at(1, 4, 15))
        NotificationSettings.objects.filter(pk=1).update(
            shortage_last_run=at(1, 7), shortage_checked_at=at(1, 7), shortage_reported=2
        )
        form = NotificationSettingsForm(
            {
                "shortage_interval": "daily",
                "shortage_weekday": "1",
                "shortage_time": "04:15",
                "shortage_lead_weeks": "6",
                "shortage_repeat": "on",  # VFG-036: on by default – left as it is
            }
            | INVOICE_DEFAULTS,
            instance=settings,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        stored = NotificationSettings.objects.get(pk=1)
        self.assertEqual(
            (stored.shortage_lead_weeks, stored.shortage_last_run, stored.shortage_reported), (6, at(1, 7), 2)
        )
        kind = ContentType.objects.get_for_model(NotificationSettings)
        entry = AuditLogEntry.objects.filter(content_type=kind).latest("pk")
        self.assertEqual(entry.changes, {"shortage_lead_weeks": [4, 6]})

    def test_lead_time_from_1_to_26_weeks(self) -> None:
        data = {"shortage_interval": "weekly", "shortage_weekday": "5", "shortage_time": "07:30"} | INVOICE_DEFAULTS
        self.assertFalse(NotificationSettingsForm(data | {"shortage_lead_weeks": "27"}).is_valid())
        self.assertFalse(NotificationSettingsForm(data | {"shortage_lead_weeks": "0"}).is_valid())
        self.assertTrue(NotificationSettingsForm(data | {"shortage_lead_weeks": "26"}).is_valid())


class ShortageCase(RentalarsTestCase):
    """Paula manages a project from 10 March that lacks 3 × Topteil."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.topteil = make_stock("L-001", 2, "Topteil")
        self.project = make_project(manager=self.paula)
        add_line(self.project, self.topteil, 5)
        # VFG-036: known shortages are reported again by default; these tests are about each shortage once – the
        # default, still there when switched off. The repetition is tested where it is switched on.
        NotificationSettings.objects.filter(pk=1).update(shortage_repeat=False)

    def reported(self) -> list[str]:
        return list(
            Notification.objects.filter(user=self.paula, kind=Kind.SHORTAGE)
            .order_by("pk")
            .values_list("title", flat=True)
        )


class TimerTests(ShortageCase):
    """VFG-036: the minute timer checks at the time set – once per moment."""

    def test_the_first_minute_only_notes_the_time(self) -> None:
        NotificationSettings.load()
        self.assertIsNone(run_due_shortage_check())
        self.assertEqual(NotificationSettings.objects.get(pk=1).shortage_last_run, at(1, 8))
        self.assertEqual(self.reported(), [])

    def test_every_day_at_the_time_set(self) -> None:
        configure(last_run=at(1, 8), shortage_time=datetime.time(9, 30))
        self.assertIsNone(run_due_shortage_check(at(1, 9, 29)))
        self.assertEqual(run_due_shortage_check(at(1, 9, 30)), 1)
        self.assertIsNone(run_due_shortage_check(at(1, 9, 31)))
        self.assertEqual(self.reported(), [f"Fehlbestand in {self.project}: 3 × Topteil fehlen"])
        stored = NotificationSettings.objects.get(pk=1)
        self.assertEqual((stored.shortage_checked_at, stored.shortage_reported), (at(1, 9, 30), 1))
        # The next day: checked, nothing new – once per case, as before.
        self.assertEqual(run_due_shortage_check(at(2, 9, 30)), 0)
        self.assertEqual(NotificationSettings.objects.get(pk=1).shortage_checked_at, at(2, 9, 30))

    def test_a_check_missed_while_the_server_was_off_is_made_up_once(self) -> None:
        configure(last_run=at(26, 4, 15, month=2))
        self.assertEqual(run_due_shortage_check(at(1, 11)), 1)
        self.assertIsNone(run_due_shortage_check(at(1, 11, 1)))

    def test_of_two_runs_at_once_only_one_checks(self) -> None:
        settings = configure(last_run=at(28, 4, 15, month=2))
        NotificationSettings.objects.filter(pk=1).update(shortage_last_run=at(1, 4, 15))  # the other run
        with mock.patch.object(NotificationSettings, "load", return_value=settings):
            self.assertIsNone(run_due_shortage_check(at(1, 4, 15)))
        self.assertEqual(self.reported(), [])

    def test_working_days(self) -> None:
        configure(last_run=at(4, 12), shortage_interval=ShortageInterval.WORKDAYS)
        self.assertEqual(run_due_shortage_check(at(5, 4, 15)), 1)  # Friday
        self.assertIsNone(run_due_shortage_check(at(6, 4, 15)))  # Saturday
        self.assertIsNone(run_due_shortage_check(at(7, 4, 15)))  # Sunday
        self.assertEqual(run_due_shortage_check(at(8, 4, 15)), 0)  # Monday

    def test_no_check_on_a_holiday(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.RETURNED)
        later = make_project("Ostermarkt", start=at(30, 8), end=at(31, 20), manager=self.paula)
        add_line(later, self.topteil, 4)
        configure(last_run=at(25, 12), shortage_interval=ShortageInterval.WORKDAYS)
        set_clock(at(26, 4, 15))
        self.assertIsNone(run_due_shortage_check())  # Good Friday
        set_clock(at(29, 4, 15))
        self.assertIsNone(run_due_shortage_check())  # Easter Monday
        set_clock(at(30, 4, 15))
        self.assertEqual(run_due_shortage_check(), 1)
        self.assertEqual(self.reported(), [f"Fehlbestand in {later}: 2 × Topteil fehlen"])

    def test_once_a_week(self) -> None:
        configure(last_run=at(1, 8), shortage_interval=ShortageInterval.WEEKLY, shortage_weekday=3)
        self.assertIsNone(run_due_shortage_check(at(2, 4, 15)))
        self.assertEqual(run_due_shortage_check(at(3, 4, 15)), 1)  # Wednesday
        self.assertIsNone(run_due_shortage_check(at(4, 4, 15)))

    def test_switched_off(self) -> None:
        configure(last_run=at(1, 4, 15), shortage_interval=ShortageInterval.OFF)
        for day in range(2, 9):
            self.assertIsNone(run_due_shortage_check(at(day, 12)))
        self.assertEqual(self.reported(), [])

    def test_a_new_time_counts_from_its_next_moment(self) -> None:
        """Set at 08:00 to 07:00 – not made up at once; to 09:00 – today at 09:00."""
        configure(last_run=at(1, 4, 15), shortage_time=datetime.time(7, 0))
        schedule_changed()
        self.assertIsNone(run_due_shortage_check(at(1, 8, 1)))
        configure(last_run=at(1, 4, 15), shortage_time=datetime.time(9, 0))
        schedule_changed()
        self.assertIsNone(run_due_shortage_check(at(1, 8, 59)))
        self.assertEqual(run_due_shortage_check(at(1, 9)), 1)

    def test_a_quiet_minute_costs_one_query(self) -> None:
        configure(last_run=at(1, 4, 15), shortage_interval=ShortageInterval.WORKDAYS)
        with CaptureQueriesContext(connection) as queries:
            self.assertIsNone(run_due_shortage_check(at(1, 8)))
        self.assertEqual(len(queries), 1, [query["sql"] for query in queries])

    def test_the_minute_timer_checks_and_the_nightly_job_no_longer(self) -> None:
        configure(last_run=at(1, 4, 15))
        call_command("run_daily_maintenance", stdout=io.StringIO())
        self.assertEqual(self.reported(), [])
        set_clock(at(2, 4, 15))
        with self.captureOnCommitCallbacks(execute=True):
            call_command("run_jobs", stdout=io.StringIO())
        self.assertEqual(len(self.reported()), 1)

    def test_an_error_does_not_stop_the_tasks(self) -> None:
        configure(last_run=at(1, 4, 15))
        set_clock(at(2, 4, 15))
        with (
            mock.patch("rentalars.notifications.services.check_shortages", side_effect=RuntimeError("bug")),
            self.assertLogs("rentalars.core.management.commands.run_jobs", "ERROR"),
        ):
            call_command("run_jobs", stdout=io.StringIO())


class LeadTimeAndRepetitionTests(ShortageCase):
    """VFG-036: how far ahead, and whether known shortages are reported again."""

    def setUp(self) -> None:
        super().setUp()
        # Begins in five weeks: beyond the four weeks.
        self.far = make_project("Sommerfest", start=at(5, 8, month=4), end=at(6, 22, month=4), manager=self.paula)
        add_line(self.far, self.topteil, 6)

    def test_the_lead_time_decides_which_projects(self) -> None:
        configure(last_run=at(1, 4, 15))
        self.assertEqual(run_due_shortage_check(at(2, 4, 15)), 1)
        self.assertNotIn(str(self.far), " ".join(self.reported()))
        configure(last_run=at(2, 4, 15), shortage_lead_weeks=6)
        self.assertEqual(run_due_shortage_check(at(3, 4, 15)), 1)
        self.assertIn(f"Fehlbestand in {self.far}: 4 × Topteil fehlen", self.reported())

    def test_a_shorter_lead_time_does_not_forget_what_was_reported(self) -> None:
        self.assertEqual(check_shortages(horizon_days=42), 2)
        self.assertEqual(check_shortages(horizon_days=28), 0)
        self.assertEqual(ShortageNotice.objects.count(), 2)  # the far one stays known
        self.assertEqual(check_shortages(horizon_days=42), 0)
        self.assertEqual(len(self.reported()), 2)

    def test_a_resolved_shortage_is_forgotten(self) -> None:
        self.assertEqual(check_shortages(), 1)
        self.project.material_lines.update(quantity=2)
        self.assertEqual(check_shortages(), 0)
        self.assertEqual(ShortageNotice.objects.count(), 0)

    def test_report_again_at_every_check(self) -> None:
        configure(last_run=at(1, 4, 15), shortage_repeat=True)
        self.assertEqual(run_due_shortage_check(at(2, 4, 15)), 1)
        self.assertEqual(run_due_shortage_check(at(3, 4, 15)), 1)
        self.assertEqual(
            self.reported(),
            [
                f"Fehlbestand in {self.project}: 3 × Topteil fehlen",
                f"Weiterhin Fehlbestand in {self.project}: 3 × Topteil fehlen",
            ],
        )

    def test_without_repetition_a_grown_shortage_is_reported(self) -> None:
        self.assertEqual(check_shortages(), 1)
        self.project.material_lines.update(quantity=7)
        self.assertEqual(check_shortages(), 1)
        self.assertEqual(self.reported()[-1], f"Fehlbestand in {self.project}: 5 × Topteil fehlen")
