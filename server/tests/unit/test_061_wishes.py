# SPDX-License-Identifier: GPL-3.0-or-later
"""Requirements from the use.

* A customer created in the dialog of the project form is active (bug, PRJ-070).
* One availability at any moment: the newer statement counts; busy times are blocks (PER-027).
* Availability that repeats like an appointment series (PER-028).
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

from rentalars.personnel import calendars
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.availability import people_availability
from rentalars.personnel.models import (
    AvailabilityMark,
    AvailabilityRepeat,
    AvailabilitySeries,
    AvailabilitySource,
    AvailabilityState,
)
from rentalars.projects import crew
from tests.helpers import NOW, RentalarsTestCase, at, make_person, make_project, plan, set_clock

GREEN, YELLOW, RED = AvailabilityState.AVAILABLE, AvailabilityState.LIMITED, AvailabilityState.UNAVAILABLE
OWN, FEED = AvailabilitySource.OWN, AvailabilitySource.FEED


# --- The bug: customers from the dialog were deactivated -----------------------------------------------------


# --- PER-027: one availability at any moment -----------------------------------------------------------------


class OneAvailabilityTests(RentalarsTestCase):
    """PER-027: where an own entry and a busy time meet, the newer statement counts."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})

    def busy(
        self, start: datetime.datetime, end: datetime.datetime, changed: datetime.datetime | None = None
    ) -> AvailabilityMark:
        return AvailabilityMark.objects.create(
            person=self.anna, start=start, end=end, state=RED, source=FEED, entered_at=changed
        )

    def periods(self) -> list[tuple[datetime.datetime, datetime.datetime, str, str]]:
        return [
            (period.start, period.end, period.state, period.source)
            for period in availability_marks.resolve(self.anna.availability_marks.all())
        ]

    def test_an_own_entry_made_after_the_appointment_changed_counts(self) -> None:
        self.busy(at(10, 9), at(10, 12), changed=at(1, 7))
        availability_marks.mark_period(self.anna, at(10), at(11), GREEN)  # entered at 08:00
        self.assertEqual(self.periods(), [(at(10), at(11), GREEN, OWN)])

    def test_an_appointment_changed_later_counts(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(11), GREEN)
        self.busy(at(10, 9), at(10, 12), changed=at(1, 9))
        self.assertEqual(
            self.periods(),
            [(at(10), at(10, 9), GREEN, OWN), (at(10, 9), at(10, 12), RED, FEED), (at(10, 12), at(11), GREEN, OWN)],
        )
        # Entering it again makes the own entry the newer statement.
        set_clock(at(1, 10))
        availability_marks.mark_period(self.anna, at(10), at(11), GREEN)
        self.assertEqual(self.periods(), [(at(10), at(11), GREEN, OWN)])

    def test_without_a_date_of_the_calendar_the_stricter_counts(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(11), GREEN)
        availability_marks.mark_period(self.anna, at(12), at(13), RED, "Arzt")
        self.busy(at(10, 9), at(10, 12))
        self.busy(at(12, 9), at(12, 12))
        periods = availability_marks.resolve(self.anna.availability_marks.all())
        self.assertEqual(
            [(period.start, period.end, period.state, period.source, period.note) for period in periods],
            [
                (at(10), at(10, 9), GREEN, OWN, ""),
                (at(10, 9), at(10, 12), RED, FEED, ""),
                (at(10, 12), at(11), GREEN, OWN, ""),
                # Equally strict: the own entry, which says why.
                (at(12), at(13), RED, OWN, "Arzt"),
            ],
        )

    def test_busy_times_that_overlap_or_touch_are_one_block(self) -> None:
        self.busy(at(10, 9), at(10, 12), changed=at(1, 7))
        self.busy(at(10, 11), at(10, 14), changed=at(1, 6))
        self.busy(at(10, 14), at(10, 15))
        self.busy(at(10, 16), at(10, 17))
        self.assertEqual(self.periods(), [(at(10, 9), at(10, 15), RED, FEED), (at(10, 16), at(10, 17), RED, FEED)])

    def test_a_piece_left_from_cutting_keeps_its_moment_and_series(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(20), GREEN)
        set_clock(at(2, 8))
        availability_marks.mark_period(self.anna, at(12), at(13), RED)
        marks = list(self.anna.availability_marks.order_by("start"))
        self.assertEqual([mark.entered_at for mark in marks], [NOW, at(2, 8), NOW])
        self.assertEqual(len({mark.pk for mark in marks}), 3)

    def test_the_overviews_ask_once_and_leave_out_what_lies_outside(self) -> None:
        tom = make_person("Tom Richter", rates={"Tontechnik": "38.00"})
        availability_marks.mark_period(self.anna, at(1), at(31), GREEN)
        self.busy(at(5, 9), at(5, 12), changed=at(1, 9))  # newer, but before the window
        availability_marks.mark_period(tom, at(10, 8), at(10, 9), YELLOW)
        with self.assertNumQueries(1):
            periods = availability_marks.effective_periods([self.anna.pk, tom.pk], at(10), at(11))
        # The busy time on the 5th lies outside and is not asked for; the period is not cut at the window.
        self.assertEqual([(period.start, period.end) for period in periods[self.anna.pk]], [(at(1), at(31))])
        self.assertEqual([period.state for period in periods[tom.pk]], [YELLOW])

    def test_planning_warns_only_where_the_busy_time_counts(self) -> None:
        project = make_project("Stadtfest")  # 10 to 12 March
        line = plan(project, "Tontechnik", self.anna)
        self.busy(at(10, 9), at(10, 12), changed=at(1, 7))
        availability_marks.mark_period(self.anna, at(10), at(13), GREEN, "passt doch")
        self.assertEqual(crew.crew_warnings(crew.load_crew_lines(project)).get(line.pk, []), [])
        self.assertEqual(people_availability(at(10, 9), at(10, 18))[0].status, "planned")
        self.busy(at(11, 9), at(11, 12), changed=at(1, 9))
        (warning,) = crew.crew_warnings(crew.load_crew_lines(project))[line.pk]
        self.assertIn("11.03. 09:00–12:00", warning)


class BusyTimesWithTheirDateTests(RentalarsTestCase):
    """PER-027: the linked calendar says when an appointment changed."""

    CALENDAR = (
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\n"
        b"BEGIN:VEVENT\r\nUID:a\r\nDTSTART:20270310T080000Z\r\nDTEND:20270310T100000Z\r\n"
        b"DTSTAMP:20270301T070000Z\r\nCREATED:20270201T090000Z\r\nLAST-MODIFIED:20270215T090000Z\r\nEND:VEVENT\r\n"
        b"BEGIN:VEVENT\r\nUID:b\r\nDTSTART:20270311T080000Z\r\nDTEND:20270311T100000Z\r\n"
        b"CREATED:20270202T090000Z\r\nEND:VEVENT\r\n"
        b"BEGIN:VEVENT\r\nUID:c\r\nDTSTART:20270312T080000Z\r\nDTEND:20270312T100000Z\r\n"
        b"DTSTAMP:20270301T070000Z\r\nEND:VEVENT\r\n"
        b"BEGIN:VEVENT\r\nUID:d\r\nDTSTART:20270313T080000Z\r\nDTEND:20270313T100000Z\r\n"
        b"LAST-MODIFIED:20991231T000000Z\r\nEND:VEVENT\r\n"
        b"END:VCALENDAR\r\n"
    )

    def test_last_modified_else_created_never_the_stamp_and_never_later_than_now(self) -> None:
        changed = [period.changed for period in calendars.busy_periods(self.CALENDAR)]
        utc = datetime.UTC
        self.assertEqual(
            changed,
            [
                datetime.datetime(2027, 2, 15, 9, tzinfo=utc),
                datetime.datetime(2027, 2, 2, 9, tzinfo=utc),
                None,
                NOW,
            ],
        )


# --- PER-028: series -----------------------------------------------------------------------------------------


class SeriesTests(RentalarsTestCase):
    """PER-028: daily, weekly on weekdays, monthly; until a day or n times; at most a year ahead."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})

    def series(self, **values: object) -> AvailabilitySeries:
        defaults: dict[str, object] = {
            "state": RED,
            "first_day": datetime.date(2027, 3, 2),  # a Tuesday
            "last_day": datetime.date(2027, 3, 2),
            "repeat": AvailabilityRepeat.WEEKLY,
            "count": 4,
        }
        return availability_marks.create_series(self.anna, **{**defaults, **values})

    def starts(self) -> list[datetime.datetime]:
        return [mark.start for mark in self.anna.availability_marks.order_by("start")]

    def test_weekly_on_two_weekdays_in_the_evening(self) -> None:
        series = self.series(
            weekdays=[1, 3], start_time=datetime.time(18), end_time=datetime.time(23), note="Probe", count=None,
            until=datetime.date(2027, 3, 14),
        )  # fmt: skip
        marks = list(self.anna.availability_marks.order_by("start"))
        self.assertEqual(
            [(mark.start, mark.end) for mark in marks],
            [(at(day, 18), at(day, 23)) for day in (2, 4, 9, 11)],
        )
        self.assertTrue(all(mark.series == series and mark.note == "Probe" for mark in marks))
        self.assertEqual(
            availability_marks.describe_series(series),
            "wöchentlich am Di, Do, 18:00–23:00, ab 02.03.2027, bis 14.03.2027",
        )

    def test_every_second_week_and_n_times(self) -> None:
        self.series(interval=2, count=3)
        self.assertEqual(self.starts(), [at(2), at(16), at(30)])

    def test_daily_and_several_days_long(self) -> None:
        self.series(repeat=AvailabilityRepeat.DAILY, interval=3, count=3, last_day=datetime.date(2027, 3, 3))
        self.assertEqual(
            [(mark.start, mark.end) for mark in self.anna.availability_marks.order_by("start")],
            [(at(2), at(4)), (at(5), at(7)), (at(8), at(10))],
        )

    def test_monthly_skips_months_without_the_day(self) -> None:
        self.series(
            repeat=AvailabilityRepeat.MONTHLY, first_day=datetime.date(2027, 1, 31),
            last_day=datetime.date(2027, 1, 31), count=None, until=datetime.date(2027, 5, 31),
        )  # fmt: skip
        self.assertEqual(
            [timezone.localtime(mark.start).date() for mark in self.anna.availability_marks.order_by("start")],
            [datetime.date(2027, 1, 31), datetime.date(2027, 3, 31), datetime.date(2027, 5, 31)],
        )

    def test_at_most_a_year_ahead(self) -> None:
        series = self.series(repeat=AvailabilityRepeat.DAILY, count=None, until=datetime.date(2030, 1, 1))
        self.assertEqual(len(availability_marks.series_occurrences(series)), 367)
        self.assertEqual(self.starts()[-1], at(2, year=2028))

    def test_the_rule_is_checked(self) -> None:
        for values in (
            {"count": None},
            {"count": 2, "until": datetime.date(2027, 3, 1)},
            {"interval": 53},
            {"start_time": datetime.time(18)},
            {"weekdays": "1,9"},
            {"last_day": datetime.date(2027, 3, 1)},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.series(**values)
        self.assertFalse(AvailabilitySeries.objects.exists())

    def test_an_occurrence_replaces_what_was_entered_and_a_later_entry_replaces_it(self) -> None:
        availability_marks.mark_period(self.anna, at(9), at(10), GREEN)
        self.series(count=2)  # 2 and 9 March
        set_clock(at(1, 9))
        availability_marks.mark_period(self.anna, at(2, 12), at(2, 14), YELLOW)
        periods = availability_marks.resolve(self.anna.availability_marks.all())
        self.assertEqual(
            [(period.start, period.end, period.state) for period in periods],
            [(at(2), at(2, 12), RED), (at(2, 12), at(2, 14), YELLOW), (at(2, 14), at(3), RED), (at(9), at(10), RED)],
        )

    def test_remove_from_a_day_on_or_all(self) -> None:
        series = self.series(count=4)  # 2, 9, 16, 23 March
        availability_marks.remove_series(series, from_day=datetime.date(2027, 3, 16))
        self.assertEqual(self.starts(), [at(2), at(9)])
        series.refresh_from_db()
        self.assertEqual((series.until, series.count), (datetime.date(2027, 3, 15), None))
        availability_marks.remove_series(series)
        self.assertEqual(self.starts(), [])
        self.assertFalse(AvailabilitySeries.objects.exists())

    def test_a_change_counts_from_a_day_on(self) -> None:
        series = self.series(count=4)  # 2, 9, 16, 23 March, red
        changed = availability_marks.change_series(
            series, from_day=datetime.date(2027, 3, 10), state=YELLOW, weekdays=[0], note="nur vormittags"
        )
        marks = list(self.anna.availability_marks.order_by("start"))
        # The changed rule: Mondays, four times from the first day on (8, 15, 22, 29 March); the 8th lies before the change.
        self.assertEqual(
            [(timezone.localtime(mark.start).day, mark.state) for mark in marks],
            [(2, RED), (9, RED), (15, YELLOW), (22, YELLOW), (29, YELLOW)],
        )
        self.assertTrue(all(mark.series_id == changed.pk == series.pk for mark in marks))

    def test_editing_an_occurrence_takes_it_out_of_the_series(self) -> None:
        self.series(count=2)
        mark = self.anna.availability_marks.order_by("start").first()
        changed = availability_marks.change_mark(mark, state=YELLOW)
        self.assertIsNone(changed.series_id)
