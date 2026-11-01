# SPDX-License-Identifier: GPL-3.0-or-later
"""Several users do the same thing at the same moment (VFG-007, ZEI-009, NFA-051).

The tests that race two requests against each other need a database with
real row locks and therefore only run on MariaDB (``RENTALARS_CONFIG``
pointing to a MariaDB test configuration). On SQLite they are skipped:
there, writes are processed one after the other anyway.
"""

from __future__ import annotations

import threading
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import LiveServerTestCase, TransactionTestCase, skipUnlessDBFeature

from rentalars.accounts.rights import Rights
from rentalars.core.defaults import install_defaults
from rentalars.material import numbering
from rentalars.projects.models import MaterialLine, Project
from rentalars.projects.services import add_line
from rentalars.timetracking import services as times
from rentalars.timetracking.loadtest import PREFIX, measure_concurrent_recording
from rentalars.timetracking.models import TimeEntry
from tests.helpers import (
    LATER,
    at,
    job_function,
    make_internal_project,
    make_person,
    make_project,
    make_stock,
    set_clock,
    stop_the_clock,
)

#: How often the race is repeated. Without the lock it is lost within a few rounds.
ROUNDS = 8


@skipUnlessDBFeature("has_select_for_update")
class SimultaneousBookingTests(TransactionTestCase):
    """Check and save are one protected step: an overbooking never goes unnoticed."""

    def setUp(self) -> None:
        super().setUp()
        # A TransactionTestCase empties all tables after each test, including the start data.
        install_defaults()
        numbering.reset_cache()

    def test_of_two_simultaneous_bookings_at_least_one_is_told_about_the_shortage(self) -> None:
        cable = make_stock("K-005", 9)
        rights = Rights.everything()

        for round_number in range(ROUNDS):
            projects = [
                make_project(f"Runde {round_number} A", start=at(10), end=at(12)),
                make_project(f"Runde {round_number} B", start=at(10), end=at(12)),
            ]
            start_together = threading.Barrier(2)
            shortages: list[int] = []
            errors: list[BaseException] = []

            def book(
                project_id: int,
                start_together: threading.Barrier = start_together,
                shortages: list[int] = shortages,
                errors: list[BaseException] = errors,
            ) -> None:
                try:
                    project = Project.objects.get(pk=project_id)
                    start_together.wait(timeout=10)
                    result = add_line(project, rights=rights, product=cable, quantity=Decimal("5"))
                    shortages.append(result.availability.shortage_total)
                except BaseException as error:
                    errors.append(error)
                finally:
                    connection.close()

            threads = [threading.Thread(target=book, args=(project.pk,)) for project in projects]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

            self.assertEqual(errors, [])
            # 5 + 5 pieces of 9: whoever saved second must have seen the first booking.
            self.assertEqual(sorted(shortages), [0, 1], f"round {round_number}")
            MaterialLine.objects.filter(project__in=projects).delete()


@skipUnlessDBFeature("has_select_for_update")
class SimultaneousTimeEntryTests(TransactionTestCase):
    """ZEI-009 under load: check and save of a time entry are one protected step."""

    def setUp(self) -> None:
        super().setUp()
        # The hours of February 2027 are recorded afterwards (ZEI-022), whatever the real date.
        stop_the_clock(self)
        set_clock(LATER)
        install_defaults()
        numbering.reset_cache()

    def test_a_double_tap_saves_the_entry_once(self) -> None:
        """Two identical entries sent at the same moment: one is saved, the other refused as overlapping."""
        project = make_internal_project()
        person = make_person("Anna Becker", rates={"Lager": "20.00"})
        function = job_function("Lager")
        rights = Rights.everything()

        for round_number in range(ROUNDS):
            start_together = threading.Barrier(2)
            outcomes: list[str] = []
            errors: list[BaseException] = []
            start = at(1 + round_number, 6, month=2)

            def record(
                start_together: threading.Barrier = start_together,
                outcomes: list[str] = outcomes,
                errors: list[BaseException] = errors,
                start: object = start,
            ) -> None:
                try:
                    start_together.wait(timeout=10)
                    times.create_entry(
                        person=person,
                        project=project,
                        job_function=function,
                        start=start,
                        end=start.replace(hour=8),  # type: ignore[attr-defined]
                        rights=rights,
                        user=None,
                    )
                    outcomes.append("saved")
                except ValidationError:
                    outcomes.append("refused")
                except BaseException as error:
                    errors.append(error)
                finally:
                    connection.close()

            threads = [threading.Thread(target=record) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

            self.assertEqual(errors, [])
            self.assertEqual(sorted(outcomes), ["refused", "saved"], f"round {round_number}")
        self.assertEqual(TimeEntry.objects.count(), ROUNDS)

    def test_ten_people_record_at_the_same_moment_and_nothing_is_lost(self) -> None:
        """NFA-051: the crew writes down its hours after the job."""
        project = make_internal_project()
        function = job_function("Lager")
        people = [make_person(f"Person Nr{number}", rates={"Lager": "20.00"}) for number in range(10)]
        rights = Rights.everything()
        start_together = threading.Barrier(len(people))
        errors: list[BaseException] = []

        def record(person_id: int) -> None:
            try:
                person = type(people[0]).objects.get(pk=person_id)
                start_together.wait(timeout=10)
                for hour in (6, 8, 10):
                    times.create_entry(
                        person=person,
                        project=project,
                        job_function=function,
                        start=at(1, hour, month=2),
                        end=at(1, hour + 1, month=2),
                        rights=rights,
                        user=None,
                        submit=True,
                    )
            except BaseException as error:
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=record, args=(person.pk,)) for person in people]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertEqual(errors, [])
        self.assertEqual(TimeEntry.objects.count(), 30)


class MeasureConcurrencyTests(LiveServerTestCase):
    """The measurement of NFA-051 itself: it records through the running server and tidies up.

    How fast the answers are is a question for the reference system (see
    ``docs/betrieb/betrieb.md``); here the mechanics are checked. On SQLite
    with one person only: the test server shares a single database
    connection among its threads there, which real simultaneous requests
    would trip over.
    """

    def setUp(self) -> None:
        super().setUp()
        install_defaults()
        numbering.reset_cache()
        from rentalars.core.middleware import SetupRequiredMiddleware
        from rentalars.core.models import SystemSettings

        system_settings = SystemSettings.load()
        system_settings.setup_completed = True
        system_settings.save()
        SetupRequiredMiddleware.reset()

    def assert_nothing_stays_behind(self) -> None:
        from rentalars.accounts.models import User
        from rentalars.personnel.models import Person

        self.assertFalse(User.objects.filter(username__startswith=PREFIX).exists())
        self.assertFalse(Person.objects.filter(last_name__startswith=PREFIX).exists())
        self.assertFalse(Project.objects.filter(name__startswith=PREFIX).exists())
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_every_entry_arrives_and_the_test_accounts_are_removed_again(self) -> None:
        result = measure_concurrent_recording(self.live_server_url, users=1, rounds=3)
        self.assertEqual(result.errors, [])
        self.assertEqual((result.entries_saved, result.entries_expected), (3, 3))
        self.assertEqual((len(result.seconds["record"]), len(result.seconds["read"])), (3, 3))
        self.assertTrue(result.ok)
        self.assertGreater(result.slowest("record"), 0)
        self.assertLessEqual(result.median("record"), result.slowest("record"))
        self.assert_nothing_stays_behind()

    @skipUnlessDBFeature("has_select_for_update")
    def test_ten_people_at_once_through_the_server(self) -> None:
        result = measure_concurrent_recording(self.live_server_url, users=10, rounds=2)
        self.assertEqual(result.errors, [])
        self.assertEqual((result.entries_saved, result.entries_expected), (20, 20))
        self.assert_nothing_stays_behind()

    def test_the_command_reports_and_fails_when_the_server_cannot_be_reached(self) -> None:
        from io import StringIO

        from django.core.management.base import CommandError

        output = StringIO()
        call_command("measure_concurrency", url=self.live_server_url, users=1, rounds=2, stdout=output)
        text = output.getvalue()
        self.assertIn("1 people at the same moment", text)
        self.assertIn("entries saved: 2 of 2", text)
        self.assertIn("Stayed usable.", text)

        with self.assertRaises(CommandError):
            call_command("measure_concurrency", url="http://127.0.0.1:9", users=1, rounds=1, stdout=StringIO())
        self.assert_nothing_stays_behind()
