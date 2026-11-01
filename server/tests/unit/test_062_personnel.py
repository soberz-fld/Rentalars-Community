# SPDX-License-Identifier: GPL-3.0-or-later
"""Requirements from use for people.

* Job functions without rate and without "valid from"; day rates next to hourly rates (PER-029).
* The week of the availability calendar (PER-030).
* Several linked calendars, one layer of busy times (PER-031).
* The timeline of a person shows the availability that counts (bug, PER-020, PER-027).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError

from rentalars.notifications.models import Notification
from rentalars.personnel import calendars, services
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.availability_week import parse_week, week_calendar
from rentalars.personnel.importer import parse_function_rates
from rentalars.personnel.models import (
    Absence,
    AbsenceKind,
    AvailabilityMark,
    AvailabilitySource,
    AvailabilityState,
    CalendarFeed,
    PersonJobFunction,
)
from rentalars.personnel.privacy import export_person
from rentalars.projects import crew
from rentalars.projects.models import ProjectStatus
from rentalars.schedule.timelines import person_timeline, timeline_document
from rentalars.timetracking.services import _fixed_rate
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    at,
    clock,
    job_function,
    make_person,
    make_project,
    plan,
    set_clock,
)
from tests.unit.test_051_personnel_calendars import FEED, serve

GREEN, YELLOW, RED = AvailabilityState.AVAILABLE, AvailabilityState.LIMITED, AvailabilityState.UNAVAILABLE
OWN, FEED_SOURCE = AvailabilitySource.OWN, AvailabilitySource.FEED
D = Decimal
JANUARY, JULY = datetime.date(2027, 1, 1), datetime.date(2027, 7, 1)


# --- PER-029: job functions without rates, day rates ---------------------------------------------------------


class OptionalRatesTests(RentalarsTestCase):
    """PER-029: assigning needs neither a rate nor a day; the guide values stand in."""

    def setUp(self) -> None:
        super().setUp()
        self.sound = job_function("Tontechnik", guide="30.00")
        self.sound.guide_daily_cost_rate = D("250.00")
        self.sound.save()
        self.anna = make_person("Anna Becker")

    def test_a_function_without_rate_and_day(self) -> None:
        row = services.set_rate(self.anna, self.sound)
        self.assertEqual((row.hourly_rate, row.daily_rate, row.valid_from), (None, None, None))
        self.assertTrue(services.has_job_function(self.anna, self.sound))
        self.assertIsNone(services.rate_on(self.anna, self.sound))  # no own rate …
        rate = services.rate_for(self.anna, self.sound, at(10, 8))  # … the guide values count
        self.assertEqual(
            (rate.hourly, rate.daily, rate.own_hourly, rate.own_daily), (D("30.00"), D("250.00"), None, None)
        )
        self.assertTrue(rate.assigned and rate.hourly_is_guide and rate.daily_is_guide)
        self.assertEqual(str(row), "Anna Becker – Tontechnik (immer)")

    def test_the_row_without_a_date_counts_from_always_and_is_replaced_by_dated_rows(self) -> None:
        services.set_rate(self.anna, self.sound, D("33.00"), daily_rate=D("260.00"))
        services.set_rate(self.anna, self.sound, D("35.00"), JULY)
        on = services.rate_for
        self.assertEqual((on(self.anna, self.sound, datetime.date(2020, 1, 1)).hourly), D("33.00"))
        self.assertEqual(on(self.anna, self.sound, datetime.date(2027, 6, 30)).daily, D("260.00"))
        july = on(self.anna, self.sound, JULY)
        # The dated row applies as a whole: its empty day rate is no own day rate, the guide value counts.
        self.assertEqual(
            (july.hourly, july.own_daily, july.daily, july.valid_from), (D("35.00"), None, D("250.00"), JULY)
        )
        self.assertEqual([row.valid_from for row in services.rate_history(self.anna)], [None, JULY])

    def test_dated_rows_only_keep_the_rule_of_0_6_1(self) -> None:
        """Before PER-029 every row had a day: the latest begun one, else the earliest."""
        services.set_rate(self.anna, self.sound, D("35.00"), JANUARY)
        services.set_rate(self.anna, self.sound, D("38.00"), JULY)
        self.assertEqual(services.rate_on(self.anna, self.sound, datetime.date(2026, 12, 31)), D("35.00"))
        self.assertEqual(services.rate_on(self.anna, self.sound, datetime.date(2027, 6, 30)), D("35.00"))
        self.assertEqual(services.rate_on(self.anna, self.sound, JULY), D("38.00"))
        (current,) = services.current_rates(self.anna, JULY)
        self.assertEqual(current.hourly_rate, D("38.00"))

    def test_the_same_day_corrects_one_row_without_a_date_at_most(self) -> None:
        services.set_rate(self.anna, self.sound, D("33.00"))
        services.set_rate(self.anna, self.sound, None, daily_rate=D("270.00"))
        (row,) = PersonJobFunction.objects.filter(person=self.anna)
        self.assertEqual((row.hourly_rate, row.daily_rate), (None, D("270.00")))
        second = PersonJobFunction(person=self.anna, job_function=self.sound)
        with self.assertRaises(ValidationError) as raised:
            second.full_clean()
        self.assertIn("valid_from", raised.exception.message_dict)
        with self.assertRaises(ValidationError):
            services.set_rate(self.anna, self.sound, D("-1"))

    def test_open_places_and_people_outside_their_functions_get_the_guide_values(self) -> None:
        self.assertEqual(services.rate_for(None, self.sound).hourly, D("30.00"))
        outside = services.rate_for(self.anna, self.sound)
        self.assertEqual((outside.assigned, outside.hourly, outside.daily), (False, D("30.00"), D("250.00")))
        bare = job_function("Rigging")
        self.assertEqual((services.rate_for(self.anna, bare).hourly, services.rate_for(None, bare).daily), (None, None))

    def test_a_rate_book_reads_many_people_with_one_query(self) -> None:
        tom = make_person("Tom Richter", rates={"Tontechnik": "28.00"})
        services.set_rate(self.anna, self.sound, None, daily_rate=D("300.00"))
        with self.assertNumQueries(1):
            book = services.RateBook([self.anna.pk, tom.pk, None])
        with self.assertNumQueries(0):
            anna, tom_rate, place = (book.rate(pk, self.sound, at(10, 8)) for pk in (self.anna.pk, tom.pk, None))
        self.assertEqual((anna.hourly, anna.daily), (D("30.00"), D("300.00")))
        self.assertEqual((tom_rate.hourly, tom_rate.daily), (D("28.00"), D("250.00")))
        self.assertEqual((place.hourly, place.assigned), (D("30.00"), False))

    def test_day_rates_are_personnel_costs_in_the_change_log(self) -> None:
        self.assertIn("daily_rate", PersonJobFunction.audit_sensitive)
        self.assertIn("guide_daily_cost_rate", type(self.sound).audit_sensitive)


class OptionalRatesInCostsTests(RentalarsTestCase):
    """PER-029: where a missing own hourly rate reaches costs, the guide value of the function stands in."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.sound = job_function("Tontechnik", price="45.00", guide="32.00")
        self.anna = make_person("Anna Becker")
        services.set_rate(self.anna, self.sound)  # assigned without a rate

    def test_a_crew_line_of_a_person_without_rate_costs_the_guide_value(self) -> None:
        line = plan(self.project, self.sound, self.anna, planned_hours=D("8"))
        self.assertIsNone(line.hourly_rate)
        price = next(price for price in crew.price_crew_lines(self.project) if price.line == line)
        self.assertEqual((price.amount, price.cost, price.cost_is_guide), (D("360.00"), D("256.00"), True))

    def test_a_time_entry_takes_the_own_rate_else_the_line_else_the_guide_value(self) -> None:
        self.assertEqual(_fixed_rate(self.anna, self.sound, at(10, 8), None), D("32.00"))
        line = plan(self.project, self.sound, self.anna, hourly_rate=D("29.00"))
        self.assertEqual(_fixed_rate(self.anna, self.sound, at(10, 8), line), D("29.00"))
        services.set_rate(self.anna, self.sound, D("35.00"), JANUARY)
        self.assertEqual(_fixed_rate(self.anna, self.sound, at(10, 8), line), D("35.00"))
        self.assertEqual(_fixed_rate(self.anna, job_function("Rigging"), at(10, 8), None), D("0"))

    def test_the_information_for_the_person_has_the_day_rates(self) -> None:
        """Also the rate from the hour limit (PER-035)."""
        services.set_rate(self.anna, self.sound, D("35.00"), JULY, daily_rate=D("280.00"))
        rows = export_person(self.anna)["job_functions"]
        self.assertEqual(
            rows,
            [
                {
                    "job_function": "Tontechnik",
                    "hourly_rate": None,
                    "daily_rate": None,
                    "hourly_rate_above_limit": None,
                    "valid_from": None,
                },
                {
                    "job_function": "Tontechnik",
                    "hourly_rate": "35.00",
                    "daily_rate": "280.00",
                    "hourly_rate_above_limit": None,
                    "valid_from": "2027-07-01",
                },
            ],
        )


class ImportWithDayRatesTests(RentalarsTestCase):
    """PER-029 in the import of people: "Tontechnik: 35,00/280,00"."""

    def test_hourly_and_day_rates_after_the_colon(self) -> None:
        self.assertEqual(
            parse_function_rates("Tontechnik: 35,00/280,00, Licht: /250, Rigging"),
            [("Tontechnik", D("35.00"), D("280.00")), ("Licht", None, D("250.00")), ("Rigging", None, None)],
        )

    def test_new_rates_count_from_today_and_keep_what_the_row_does_not_name(self) -> None:
        from rentalars.core.tabular import Table
        from rentalars.personnel.importer import import_people

        sound = job_function("Tontechnik")
        job_function("Licht")
        anna = make_person("Anna Becker")
        services.set_rate(anna, sound, D("35.00"), JANUARY, daily_rate=D("280.00"))

        def run(functions: str) -> Any:
            table = Table(headers=["Name", "Funktionen"], rows=[["Anna Becker", functions]])
            return import_people(table, {"name": 0, "functions": 1}, dry_run=False, rights=ALL_RIGHTS)

        self.assertEqual(run("Tontechnik: 38,00").updated, 1)
        today = services.rate_for(anna, sound)
        self.assertEqual(
            (today.own_hourly, today.own_daily, today.valid_from), (D("38.00"), D("280.00"), clock().date())
        )
        self.assertEqual(run("Tontechnik: 38,00").unchanged, 1)
        self.assertEqual(run("Licht").updated, 1)
        self.assertEqual(services.rate_for(anna, job_function("Licht")).assigned, True)


# --- PER-030: the week of the availability calendar ----------------------------------------------------------


class AvailabilityWeekTests(RentalarsTestCase):
    """PER-030: seven columns with hours; the availability that counts and the deployments."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})

    def test_weeks_from_the_address(self) -> None:
        self.assertEqual(parse_week("2027-03-10"), datetime.date(2027, 3, 8))
        self.assertEqual(parse_week("rubbish"), datetime.date(2027, 3, 1))
        self.assertEqual(parse_week(None), datetime.date(2027, 3, 1))
        self.assertEqual(parse_week("1500-01-01"), datetime.date(2027, 3, 1))

    def test_bands_deployments_and_the_heads_of_the_days(self) -> None:
        availability_marks.mark_period(self.anna, at(8), at(9), GREEN)
        availability_marks.mark_period(self.anna, at(10, 18), at(10, 23), RED, "Probe")
        AvailabilityMark.objects.create(
            person=self.anna, start=at(11, 9), end=at(11, 11), state=RED, source=FEED_SOURCE
        )
        AvailabilityMark.objects.create(
            person=self.anna, start=at(11, 10), end=at(11, 12), state=RED, source=FEED_SOURCE
        )
        project = make_project("Stadtfest", start=at(10, 8), end=at(10, 20))
        plan(project, "Tontechnik", self.anna, start=at(10, 16), end=at(10, 20))
        plan(make_project("Messe"), "Tontechnik", self.anna, start=at(10, 16), end=at(10, 17, 30))
        cancelled = make_project("Abgesagt", start=at(12, 8), end=at(12, 18))
        plan(cancelled, "Tontechnik", self.anna)
        cancelled.status = ProjectStatus.CANCELLED
        cancelled.save()
        with self.assertNumQueries(2):
            week = week_calendar(self.anna, datetime.date(2027, 3, 10))
        self.assertEqual(
            (week.monday, week.sunday, week.number), (datetime.date(2027, 3, 8), datetime.date(2027, 3, 14), 10)
        )
        self.assertEqual((week.previous, week.next), (datetime.date(2027, 3, 1), datetime.date(2027, 3, 15)))
        monday, _tuesday, wednesday, thursday, friday = week.days[:5]
        self.assertEqual((monday.day.state, monday.day.partial), (GREEN, False))
        self.assertEqual([(band.begin, band.end, band.times) for band in monday.bands], [(0.0, 24.0, "ganztägig")])
        self.assertEqual([(band.begin, band.end, band.css) for band in wednesday.bands], [(18.0, 23.0, "unavailable")])
        self.assertIn("Probe", wednesday.bands[0].text)
        # Busy times of the linked calendars are one block (PER-027), hatched.
        self.assertEqual(
            [(band.begin, band.end, band.css) for band in thursday.bands], [(9.0, 12.0, "unavailable feed")]
        )
        self.assertTrue(thursday.day.from_feed and thursday.day.partial)
        # Two deployments at once stand side by side; one reaches into the red evening.
        blocks = sorted(wednesday.deployments, key=lambda block: block.lane)
        self.assertEqual(
            [(block.begin, block.end, block.lane, block.lanes) for block in blocks],
            [(16.0, 20.0, 0, 2), (16.0, 17.5, 1, 2)],
        )
        self.assertTrue(blocks[0].clash)
        self.assertFalse(blocks[1].clash)
        self.assertTrue(wednesday.day.planned)
        self.assertEqual(friday.deployments, [])  # cancelled projects are left out
        self.assertEqual(week.scroll_hour, 6)
        self.assertEqual(len(week.periods), 3)

    def test_deployments_name_what_the_reader_may_see(self) -> None:
        project = make_project("Stadtfest", start=at(10, 8), end=at(10, 20))
        plan(project, "Tontechnik", self.anna)
        own = week_calendar(self.anna, datetime.date(2027, 3, 8)).days[2].deployments[0]
        self.assertIn("Stadtfest", own.label)
        self.assertEqual(own.url, f"/projects/{project.number}/deployment/")
        hidden = (
            week_calendar(self.anna, datetime.date(2027, 3, 8), own=False, visible_ids=set()).days[2].deployments[0]
        )
        self.assertEqual((hidden.label, hidden.url), ("Tontechnik · eingeplant", ""))
        shown = week_calendar(self.anna, datetime.date(2027, 3, 8), own=False, visible_ids={project.pk})
        # a project link opens the Überblick – adapted.
        self.assertEqual(shown.days[2].deployments[0].url, f"/projects/{project.number}/overview/")

    def test_an_early_start_opens_the_week_earlier_and_today_has_the_line(self) -> None:
        availability_marks.mark_period(self.anna, at(3, 4, 30), at(3, 7), YELLOW)
        week = week_calendar(self.anna, datetime.date(2027, 3, 1))
        self.assertEqual(week.scroll_hour, 4)
        self.assertEqual(week.days[0].now, 8.0)  # the clock stands at 1 March, 08:00
        self.assertIsNone(week.days[1].now)
        self.assertTrue(week.is_current)

    def test_a_period_over_midnight_is_split_into_the_days(self) -> None:
        availability_marks.mark_period(self.anna, at(9, 22), at(10, 2), RED)
        days = week_calendar(self.anna, datetime.date(2027, 3, 8)).days
        self.assertEqual([(band.begin, band.end) for band in days[1].bands], [(22.0, 24.0)])
        self.assertEqual([(band.begin, band.end) for band in days[2].bands], [(0.0, 2.0)])
        self.assertEqual(days[1].bands[0].times, "ab 22:00")


# --- PER-031: several linked calendars ---------------------------------------------------------------------


BAND = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Band//DE
BEGIN:VEVENT
UID:rehearsal@band.example
DTSTART:20270310T170000Z
DTEND:20270310T210000Z
LAST-MODIFIED:20270201T120000Z
SUMMARY:Probe
END:VEVENT
END:VCALENDAR
"""


class SeveralLinkedCalendarsTests(RentalarsTestCase):
    """PER-031: every calendar is read on its own; together they are one layer of busy times."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.server.files["/private.ics"] = (200, {}, FEED)
        self.server.files["/band.ics"] = (200, {}, BAND)
        self.anna = make_person("Anna Becker")
        self.private = calendars.add_feed(self.anna, f"{self.server.url}/private.ics")
        self.band = calendars.add_feed(self.anna, f"{self.server.url}/band.ics", "  Band  ")

    def busy(self, feed: CalendarFeed | None = None) -> int:
        marks = AvailabilityMark.objects.filter(person=self.anna, source=FEED_SOURCE)
        return (marks.filter(feed=feed) if feed is not None else marks).count()

    def test_each_calendar_brings_its_busy_times_into_one_layer(self) -> None:
        self.assertIs(calendars.read_feeds(self.anna), True)
        self.assertEqual((self.busy(self.private), self.busy(self.band), self.busy()), (6, 1, 7))
        uids = list(AvailabilityMark.objects.filter(feed=self.band).values_list("feed_uid", flat=True))
        self.assertEqual(uids, [f"{self.band.pk}:rehearsal@band.example#2027-03-10T17:00:00+00:00"])
        self.assertEqual((self.band.label, self.band.name, self.private.name), ("Band", "Band", "127.0.0.1"))
        periods = availability_marks.effective_periods([self.anna.pk], at(10), at(11))[self.anna.pk]
        self.assertTrue(all(period.from_feed for period in periods))

    def test_a_failing_calendar_keeps_its_busy_times_and_leaves_the_others_alone(self) -> None:
        calendars.read_feeds(self.anna)
        del self.server.files["/band.ics"]
        self.server.files["/private.ics"] = (
            200,
            {},
            FEED.replace(b"UID:doctor@example.org", b"UID:doctor@example.org\nTRANSP:TRANSPARENT"),
        )
        self.assertIs(calendars.read_feeds(self.anna, force=True), False)
        self.private.refresh_from_db()
        self.band.refresh_from_db()
        self.assertEqual((self.private.error, self.private.failures), ("", 0))
        self.assertTrue(self.band.error)
        self.assertEqual(self.band.failures, 1)
        self.assertEqual((self.busy(self.private), self.busy(self.band)), (5, 1))

    def test_removing_a_calendar_removes_only_its_busy_times(self) -> None:
        calendars.read_feeds(self.anna)
        calendars.remove_feed(self.band)
        self.assertEqual((self.busy(), self.busy(self.private)), (6, 6))

    def test_the_same_address_once_and_at_most_ten(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            calendars.add_feed(self.anna, f"{self.server.url}/band.ics")
        self.assertIn("schon verknüpft", str(raised.exception))
        with self.assertRaises(ValidationError):
            calendars.add_feed(self.anna, "")
        for number in range(CalendarFeed.MAX_PER_PERSON - 2):
            calendars.add_feed(self.anna, f"{self.server.url}/more{number}.ics")
        with self.assertRaises(ValidationError) as raised:
            calendars.add_feed(self.anna, f"{self.server.url}/one-too-many.ics")
        self.assertIn("höchstens 10", str(raised.exception))
        # Another person may link the same address.
        calendars.add_feed(make_person("Tom Richter"), f"{self.server.url}/band.ics")

    def test_the_periodic_run_reads_each_calendar_every_thirty_minutes(self) -> None:
        result = calendars.run_due()
        self.assertEqual((result.feeds_read, len(self.server.methods())), (2, 2))
        set_clock(clock() + datetime.timedelta(minutes=10))
        late = calendars.add_feed(self.anna, f"{self.server.url}/late.ics")
        self.server.files["/late.ics"] = (200, {}, BAND.replace(b"rehearsal", b"gig"))
        self.assertEqual(calendars.run_due().feeds_read, 1)  # only the new one is due
        set_clock(clock() + datetime.timedelta(minutes=21))
        self.assertEqual(calendars.run_due().feeds_read, 2)  # the first two, not the new one
        late.refresh_from_db()
        self.assertEqual(self.busy(late), 1)

    def test_a_calendar_that_keeps_failing_is_told_once_with_its_name(self) -> None:
        del self.server.files["/band.ics"]
        for _attempt in range(calendars.FAILURES_BEFORE_NOTICE + 2):
            calendars.read_calendar(self.band, force=True)
        (notice,) = Notification.objects.filter(user=self.anna.user)
        self.assertEqual(notice.url, "/me/availability/#calendars")
        self.assertIn("„Band“", notice.title)

    def test_the_addresses_stay_out_of_the_change_log_and_the_data_export(self) -> None:
        from rentalars.core.export import _fields

        self.assertNotIn("url", _fields(CalendarFeed))
        self.assertIn("label", _fields(CalendarFeed))

    def test_busy_times_from_before_0_6_2_go_with_the_next_reading(self) -> None:
        AvailabilityMark.objects.create(person=self.anna, start=at(20), end=at(21), state=RED, source=FEED_SOURCE)
        calendars.read_calendar(self.band)
        self.assertFalse(
            AvailabilityMark.objects.filter(person=self.anna, source=FEED_SOURCE, feed__isnull=True).exists()
        )

    def test_a_reading_does_not_fail_others_when_the_run_breaks(self) -> None:
        with (
            mock.patch("rentalars.personnel.calendars.busy_periods", side_effect=RuntimeError("bug")),
            self.assertLogs("rentalars.personnel.calendars", "ERROR"),
        ):
            result = calendars.run_due()
        self.assertEqual(result.feeds_failed, 2)


# --- The bug: the timeline of a person did not show the availability ----------------------------------------


class PersonTimelineAvailabilityTests(RentalarsTestCase):
    """PER-020 with PER-021, PER-022, PER-027: the timeline shows what the personnel plan shows."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.days = [datetime.date(2027, 3, day) for day in range(1, 15)]

    def availability_row(self) -> Any:
        rows = [row for row in person_timeline(self.anna, self.days, set()).rows if row.css == "availability"]
        self.assertEqual(len(rows), 1, "the timeline has one row with the availability")
        return rows[0]

    def test_own_entries_busy_times_and_absences_in_one_row(self) -> None:
        availability_marks.mark_period(self.anna, at(2), at(4), GREEN, "gern")
        availability_marks.mark_period(self.anna, at(5, 18), at(5, 23), YELLOW)
        AvailabilityMark.objects.create(person=self.anna, start=at(8, 9), end=at(8, 11), state=RED, source=FEED_SOURCE)
        AvailabilityMark.objects.create(person=self.anna, start=at(8, 10), end=at(8, 12), state=RED, source=FEED_SOURCE)
        Absence.objects.create(person=self.anna, kind=AbsenceKind.VACATION, start=at(11), end=at(13))
        row = self.availability_row()
        bars = sorted(row.bars, key=lambda bar: bar.first)
        self.assertEqual([(bar.first, bar.last) for bar in bars], [(2, 3), (5, 5), (8, 8), (11, 12)])
        self.assertEqual(
            [bar.css for bar in bars],
            [
                "availability is-available",
                "availability is-limited",
                "availability is-unavailable from-feed",
                "absence",
            ],
        )
        self.assertIn("gern", bars[0].title)
        self.assertIn("18:00", bars[1].title)  # a part of the day says when
        self.assertIn("verknüpften Kalender", bars[2].title)
        # The two busy times are one block (PER-027), from 09:00 to 12:00 – VFG-032: as the
        # hover of the personnel plan says it.
        self.assertIn("9:00 Uhr bis 12:00 Uhr", bars[2].title)

    def test_the_newer_statement_counts(self) -> None:
        """PER-027: an own entry made after the appointment changed covers the busy time."""
        AvailabilityMark.objects.create(
            person=self.anna, start=at(3, 9), end=at(3, 17), state=RED, source=FEED_SOURCE, entered_at=at(1, 7)
        )
        availability_marks.mark_period(self.anna, at(3), at(4), GREEN)  # entered at 08:00, later
        bars = self.availability_row().bars
        self.assertEqual([bar.css for bar in bars], ["availability is-available"])

    def test_deployments_stay_the_first_row_and_the_document_has_the_availability(self) -> None:
        project = make_project("Stadtfest", start=at(6, 8), end=at(6, 18))
        plan(project, "Tontechnik", self.anna)
        availability_marks.mark_period(self.anna, at(6), at(7), RED)
        timeline = person_timeline(self.anna, self.days, {project.pk})
        self.assertEqual(timeline.rows[0].bars[0].label, f"{project.number} Stadtfest · Tontechnik")
        document = timeline_document(timeline)
        availability = next(row for row in document["rows"] if row["kind"] == "availability")
        self.assertEqual(availability["bars"][0]["kind"], "availability is-unavailable")
        self.assertEqual(availability["bars"][0]["from"], datetime.date(2027, 3, 6))
