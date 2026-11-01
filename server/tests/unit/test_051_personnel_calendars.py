# SPDX-License-Identifier: GPL-3.0-or-later
"""Availability and calendars of people (PER-021, PER-022, PER-023).

* PER-021: the own availability calendar – colouring periods green, yellow
  or red; the planning warns (PRJ-022) and the overview "who is free"
  (VFG-009, VFG-010) counts red like an absence.
* PER-022: a linked .ics calendar whose busy appointments become red marks.
* PER-023: the deployments as an .ics file and subscription link, and
  written into a CalDAV calendar.

The calendar servers are played by :class:`FakeCalendarServer`, a small HTTP
server in a thread, so that the tests need nothing installed. With
``RENTALARS_TEST_RADICALE=/path/to/radicale`` the CalDAV part also runs
against a real Radicale server (see :class:`RadicaleTests`).
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from typing import Any
from unittest import mock, skipUnless

import icalendar
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.core.crypto import decrypt_secret
from rentalars.notifications.models import Notification
from rentalars.personnel import calendars
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.availability import people_availability, period_text
from rentalars.personnel.calendar_client import CalDAVCalendar, CalendarHttpError, fetch_calendar, normalise_url
from rentalars.personnel.models import (
    AvailabilityMark,
    AvailabilitySource,
    AvailabilityState,
    CalendarPush,
    Person,
)
from rentalars.personnel.privacy import anonymise_person, export_person
from rentalars.projects import crew
from rentalars.projects.models import ProjectStatus, RequestStatus
from tests.helpers import (
    ALL_RIGHTS,
    NOW,
    RentalarsTestCase,
    at,
    clock,
    job_function,
    make_customer,
    make_person,
    make_project,
    plan,
    set_clock,
)

GREEN, YELLOW, RED = AvailabilityState.AVAILABLE, AvailabilityState.LIMITED, AvailabilityState.UNAVAILABLE


# --- A calendar server for the tests ----------------------------------------------------------------------


class _QuietServer(ThreadingHTTPServer):
    """A test server that does not wait for its threads and does not print a client that hung up."""

    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Quiet: the tests of time limits hang up on purpose."""


class FakeCalendarServer:
    """A calendar server on localhost: .ics files to read (PER-022) and CalDAV calendars to write (PER-023).

    It knows enough of RFC 4791 for Rentalars: PROPFIND for the principal,
    the calendar home and the calendars, MKCALENDAR, and GET, PUT and DELETE
    of event files with ETags and the conditions ``If-Match`` and
    ``If-None-Match``. Every request is recorded in :attr:`requests`.
    """

    def __init__(self, *, username: str = "anna", password: str = "geheim") -> None:
        #: path → (status, headers, body) for plain GET requests, e.g. a linked calendar
        self.files: dict[str, tuple[int, dict[str, str], bytes]] = {}
        #: path of an event file → (etag, body)
        self.events: dict[str, tuple[str, bytes]] = {}
        #: path of a calendar → its name
        self.calendars: dict[str, str] = {"/cal/anna/work/": "Arbeit"}
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.credentials = (username, password)
        #: answer every CalDAV request with this status instead
        self.fail_with: int | None = None
        #: seconds to wait before answering
        self.delay = 0.0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                """Quiet."""

            def _body(self) -> bytes:
                length = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(length) if length else b""

            def _send(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body and self.command != "HEAD":
                    self.wfile.write(body)

            def _allowed(self) -> bool:
                expected = base64.b64encode(f"{owner.credentials[0]}:{owner.credentials[1]}".encode()).decode()
                if self.headers.get("Authorization") == f"Basic {expected}":
                    return True
                self._send(401, b"no", {"WWW-Authenticate": 'Basic realm="test"'})
                return False

            def _record(self) -> bytes:
                body = self._body()
                owner.requests.append((self.command, self.path, dict(self.headers.items())))
                if owner.delay:
                    time.sleep(owner.delay)
                return body

            def do_GET(self) -> None:
                self._record()
                if self.path in owner.files:
                    status, headers, body = owner.files[self.path]
                    self._send(status, body, headers)
                    return
                if not self._allowed():
                    return
                if self.path in owner.events:
                    etag, body = owner.events[self.path]
                    self._send(200, body, {"ETag": etag, "Content-Type": "text/calendar"})
                    return
                self._send(404)

            def do_PROPFIND(self) -> None:
                self._record()
                if not self._allowed():
                    return
                if owner.fail_with:
                    self._send(owner.fail_with)
                    return
                depth = self.headers.get("Depth", "0")
                path = self.path
                if path in ("/", "/dav/", "/.well-known/caldav"):
                    parts = [
                        (
                            path,
                            "<d:current-user-principal><d:href>/principals/anna/</d:href></d:current-user-principal>",
                        )
                    ]
                elif path == "/principals/anna/":
                    parts = [(path, "<c:calendar-home-set><d:href>/cal/anna/</d:href></c:calendar-home-set>")]
                elif path == "/cal/anna/":
                    parts = [(path, "<d:resourcetype><d:collection/></d:resourcetype>")]
                    if depth == "1":
                        parts += [
                            (
                                calendar,
                                "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                                f"<d:displayname>{name}</d:displayname>",
                            )
                            for calendar, name in owner.calendars.items()
                        ]
                elif path in owner.calendars:
                    parts = [
                        (
                            path,
                            "<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>"
                            f"<d:displayname>{owner.calendars[path]}</d:displayname>"
                            '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>',
                        )
                    ]
                else:
                    self._send(404)
                    return
                responses = "".join(
                    f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>{props}</d:prop>"
                    "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
                    for href, props in parts
                )
                body = (
                    '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                    f"{responses}</d:multistatus>"
                ).encode()
                self._send(207, body, {"Content-Type": "application/xml"})

            def do_MKCALENDAR(self) -> None:
                body = self._record()
                if not self._allowed():
                    return
                owner.calendars[self.path] = "Rentalars" if b"Rentalars" in body else "?"
                self._send(201)

            def do_PUT(self) -> None:
                body = self._record()
                if not self._allowed():
                    return
                if owner.fail_with:
                    self._send(owner.fail_with)
                    return
                existing = owner.events.get(self.path)
                if self.headers.get("If-None-Match") == "*" and existing:
                    self._send(412)
                    return
                if self.headers.get("If-Match") and (not existing or existing[0] != self.headers["If-Match"]):
                    self._send(412)
                    return
                etag = '"' + hashlib.sha1(body).hexdigest()[:12] + '"'
                owner.events[self.path] = (etag, body)
                self._send(204 if existing else 201, b"", {"ETag": etag})

            def do_DELETE(self) -> None:
                self._record()
                if not self._allowed():
                    return
                existing = owner.events.get(self.path)
                if existing is None:
                    self._send(404)
                    return
                if self.headers.get("If-Match") and existing[0] != self.headers["If-Match"]:
                    self._send(412)
                    return
                del owner.events[self.path]
                self._send(204)

        self.server = _QuietServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        """``http://127.0.0.1:<port>``."""
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self) -> FakeCalendarServer:
        """Start serving; returns itself."""
        self.thread.start()
        return self

    def stop(self) -> None:
        """Stop serving."""
        self.server.shutdown()
        self.server.server_close()

    def methods(self) -> list[str]:
        """The methods of the recorded requests, e.g. ``["PROPFIND", "PUT"]``."""
        return [method for method, _path, _headers in self.requests]

    def event_bodies(self) -> list[icalendar.Event]:
        """The events stored in the calendars."""
        found = []
        for _etag, body in self.events.values():
            found.extend(icalendar.Calendar.from_ical(body).walk("VEVENT"))
        return found


def serve(test: Any, **options: Any) -> FakeCalendarServer:
    """Start a :class:`FakeCalendarServer` for the duration of a test."""
    server = FakeCalendarServer(**options).start()
    test.addCleanup(server.stop)
    return server


#: A calendar with busy, free, cancelled and repeating appointments in March 2027 (Berlin time).
FEED = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Kalender//DE
BEGIN:VEVENT
UID:doctor@example.org
DTSTART;TZID=Europe/Berlin:20270310T090000
DTEND;TZID=Europe/Berlin:20270310T120000
SUMMARY:Zahnarzt
END:VEVENT
BEGIN:VEVENT
UID:holiday@example.org
DTSTART;VALUE=DATE:20270312
DTEND;VALUE=DATE:20270314
SUMMARY:Kurzurlaub
END:VEVENT
BEGIN:VEVENT
UID:free@example.org
DTSTART:20270311T080000Z
DTEND:20270311T090000Z
TRANSP:TRANSPARENT
SUMMARY:Nur ein Hinweis
END:VEVENT
BEGIN:VEVENT
UID:cancelled@example.org
DTSTART:20270315T100000Z
DTEND:20270315T110000Z
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:choir@example.org
DTSTART;TZID=Europe/Berlin:20270301T180000
DTEND;TZID=Europe/Berlin:20270301T200000
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=Europe/Berlin:20270308T180000
SUMMARY:Chorprobe
END:VEVENT
BEGIN:VEVENT
UID:long-ago@example.org
DTSTART:20250101T100000Z
DTEND:20250101T110000Z
END:VEVENT
BEGIN:VEVENT
UID:floating@example.org
DTSTART:20270316T100000
DURATION:PT2H
END:VEVENT
END:VCALENDAR
"""


def red(person: Person, start: datetime.datetime, end: datetime.datetime, note: str = "") -> AvailabilityMark:
    """Colour a period red."""
    return availability_marks.mark_period(person, start, end, RED, note)


def own_marks(person: Person) -> list[tuple[datetime.datetime, datetime.datetime, str, str]]:
    """The own marks of a person as ``(start, end, state, note)``."""
    return [
        (mark.start, mark.end, mark.state, mark.note)
        for mark in person.availability_marks.filter(source=AvailabilitySource.OWN).order_by("start")
    ]


# --- PER-021: colouring the availability ---------------------------------------------------------------------


class PaintingTests(RentalarsTestCase):
    """PER-021: a new colour replaces what was entered; the same colour next to it is shown as one (PER-027)."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker")

    def test_a_period_inside_another_splits_it(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(20), GREEN)
        red(self.anna, at(12), at(14), "Hochzeit")
        self.assertEqual(
            own_marks(self.anna),
            [(at(10), at(12), GREEN, ""), (at(12), at(14), RED, "Hochzeit"), (at(14), at(20), GREEN, "")],
        )

    def test_overlapping_marks_are_cut_back_or_replaced(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(13), GREEN)
        availability_marks.mark_period(self.anna, at(15), at(18), YELLOW)
        availability_marks.mark_period(self.anna, at(20), at(21), GREEN)
        red(self.anna, at(12), at(16))
        self.assertEqual(
            own_marks(self.anna),
            [
                (at(10), at(12), GREEN, ""),
                (at(12), at(16), RED, ""),
                (at(16), at(18), YELLOW, ""),
                (at(20), at(21), GREEN, ""),
            ],
        )

    def test_the_same_colour_next_to_it_is_shown_as_one(self) -> None:
        """Each entry keeps its moment of entry (PER-027); the calendar joins them."""
        red(self.anna, at(10), at(11))
        red(self.anna, at(11), at(12))
        red(self.anna, at(9), at(10))
        self.assertEqual(len(own_marks(self.anna)), 3)
        periods = availability_marks.resolve(self.anna.availability_marks.all())
        self.assertEqual([(period.start, period.end, period.state) for period in periods], [(at(9), at(12), RED)])
        self.assertEqual(len(periods[0].mark_ids), 3)
        # Another note is another statement and stays apart.
        red(self.anna, at(12), at(13), "Arzt")
        self.assertEqual(len(availability_marks.resolve(self.anna.availability_marks.all())), 2)

    def test_clearing_removes_only_the_period(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(20), YELLOW, "nur abends")
        self.assertEqual(availability_marks.clear_period(self.anna, at(12), at(14)), 1)
        self.assertEqual(
            own_marks(self.anna), [(at(10), at(12), YELLOW, "nur abends"), (at(14), at(20), YELLOW, "nur abends")]
        )

    def test_busy_times_of_the_linked_calendar_are_never_painted_over(self) -> None:
        busy = AvailabilityMark.objects.create(
            person=self.anna, start=at(10, 9), end=at(10, 12), state=RED, source=AvailabilitySource.FEED
        )
        availability_marks.mark_period(self.anna, at(10), at(11), GREEN)
        availability_marks.clear_period(self.anna, at(9), at(12))
        self.assertTrue(AvailabilityMark.objects.filter(pk=busy.pk).exists())
        with self.assertRaises(availability_marks.ValidationError):
            availability_marks.delete_mark(busy)
        with self.assertRaises(availability_marks.ValidationError):
            availability_marks.change_mark(busy, state=GREEN)

    def test_whole_days_and_daily_times(self) -> None:
        """Without times the days are one period; with times the colour applies on each day."""
        whole = availability_marks.day_periods(datetime.date(2027, 3, 10), datetime.date(2027, 3, 12))
        self.assertEqual(whole, [(at(10), at(13))])
        evenings = availability_marks.day_periods(
            datetime.date(2027, 3, 10), datetime.date(2027, 3, 12), datetime.time(18), datetime.time(23)
        )
        self.assertEqual(evenings, [(at(10, 18), at(10, 23)), (at(11, 18), at(11, 23)), (at(12, 18), at(12, 23))])
        nights = availability_marks.day_periods(
            datetime.date(2027, 3, 10), datetime.date(2027, 3, 10), datetime.time(22), datetime.time(6)
        )
        self.assertEqual(nights, [(at(10, 22), at(11, 6))])

    def test_whole_days_across_the_change_to_summer_time(self) -> None:
        """28 March 2027 has 23 hours; a day is still midnight to midnight."""
        (period,) = availability_marks.day_periods(datetime.date(2027, 3, 28), datetime.date(2027, 3, 28))
        self.assertEqual(period, (at(28), at(29)))
        self.assertEqual(period_text(*period), "28.03.")

    def test_mark_days_colours_and_clears(self) -> None:
        availability_marks.mark_days(
            self.anna, datetime.date(2027, 3, 10), datetime.date(2027, 3, 11), YELLOW,
            note="bis 18 Uhr", start_time=datetime.time(8), end_time=datetime.time(18),
        )  # fmt: skip
        self.assertEqual(len(own_marks(self.anna)), 2)
        availability_marks.mark_days(self.anna, datetime.date(2027, 3, 1), datetime.date(2027, 3, 31), None)
        self.assertEqual(own_marks(self.anna), [])

    def test_invalid_periods_are_refused(self) -> None:
        with self.assertRaises(availability_marks.ValidationError):
            red(self.anna, at(12), at(10))
        with self.assertRaises(availability_marks.ValidationError):
            red(self.anna, at(1), at(1, year=2029))
        with self.assertRaises(availability_marks.ValidationError):
            availability_marks.mark_period(self.anna, at(10), at(11), "purple")
        with self.assertRaises(availability_marks.ValidationError):
            availability_marks.day_periods(datetime.date(2027, 3, 12), datetime.date(2027, 3, 10))
        with self.assertRaises(availability_marks.ValidationError):
            availability_marks.day_periods(datetime.date(2027, 3, 10), datetime.date(2027, 3, 10), datetime.time(8))

    def test_change_mark_paints_it_anew(self) -> None:
        mark = availability_marks.mark_period(self.anna, at(10), at(12), GREEN)
        red(self.anna, at(14), at(15))
        changed = availability_marks.change_mark(mark, end=at(16), state=RED, note="Messe")
        self.assertEqual(own_marks(self.anna), [(at(10), at(16), RED, "Messe")])
        self.assertEqual(changed.end, at(16))


class MonthCalendarTests(RentalarsTestCase):
    """PER-021: the month calendar shows the strongest colour of each day."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})

    def test_weeks_from_monday_to_sunday(self) -> None:
        calendar = availability_marks.month_calendar(self.anna, datetime.date(2027, 3, 1))
        self.assertEqual(calendar.weeks[0][0].day, datetime.date(2027, 3, 1))  # a Monday
        self.assertEqual(calendar.weeks[-1][-1].day, datetime.date(2027, 4, 4))
        self.assertTrue(all(len(week) == 7 for week in calendar.weeks))
        self.assertEqual((calendar.previous, calendar.next), (datetime.date(2027, 2, 1), datetime.date(2027, 4, 1)))
        self.assertFalse(calendar.weeks[-1][-1].in_month)
        self.assertTrue(calendar.weeks[0][0].is_today)

    def test_colours_parts_of_days_feed_and_deployments(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(12), GREEN)
        availability_marks.mark_period(self.anna, at(11, 18), at(11, 22), YELLOW)
        AvailabilityMark.objects.create(
            person=self.anna, start=at(15, 9), end=at(15, 10), state=RED, source=AvailabilitySource.FEED
        )
        plan(make_project("Stadtfest", start=at(20, 8), end=at(21, 2)), "Tontechnik", self.anna)
        with self.assertNumQueries(2):
            calendar = availability_marks.month_calendar(self.anna, datetime.date(2027, 3, 1))
        days = {entry.day.day: entry for week in calendar.weeks for entry in week if entry.in_month}
        self.assertEqual((days[10].state, days[10].partial), (GREEN, False))
        self.assertEqual((days[11].state, days[11].partial), (YELLOW, True))
        self.assertEqual((days[15].state, days[15].from_feed, days[15].partial), (RED, True, True))
        self.assertEqual(days[12].state, "")
        self.assertTrue(days[20].planned and days[21].planned)
        self.assertFalse(days[22].planned)
        own = [period for period in calendar.month_periods if not period.from_feed]
        self.assertEqual(len(own), 3)  # the evening cut the green period in two
        self.assertEqual(len([period for period in calendar.month_periods if period.from_feed]), 1)

    def test_months_from_the_address(self) -> None:
        self.assertEqual(availability_marks.parse_month("2027-11"), datetime.date(2027, 11, 1))
        self.assertEqual(availability_marks.parse_month("rubbish"), datetime.date(2027, 3, 1))
        self.assertEqual(availability_marks.parse_month("2027-13"), datetime.date(2027, 3, 1))
        self.assertEqual(availability_marks.parse_month("1500-01"), datetime.date(2027, 3, 1))


class PlanningWarningTests(RentalarsTestCase):
    """PER-021, PER-022 with PRJ-022: red warns when planning, yellow hints."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.project = make_project("Stadtfest")  # 10 to 12 March
        self.line = plan(self.project, "Tontechnik", self.anna)

    def warnings(self) -> list[str]:
        return crew.crew_warnings(crew.load_crew_lines(self.project)).get(self.line.pk, [])

    def test_not_available_warns(self) -> None:
        red(self.anna, at(11), at(12), "Familienfeier")
        (warning,) = self.warnings()
        self.assertIn("11.03.", warning)
        self.assertIn("Familienfeier", warning)
        self.assertFalse(getattr(warning, "is_hint", False))

    def test_busy_in_the_linked_calendar_warns_without_the_title(self) -> None:
        AvailabilityMark.objects.create(
            person=self.anna, start=at(10, 9), end=at(10, 12), state=RED, source=AvailabilitySource.FEED
        )
        (warning,) = self.warnings()
        self.assertIn("10.03. 09:00–12:00", warning)

    def test_limits_give_a_quieter_hint_at_the_end(self) -> None:
        availability_marks.mark_period(self.anna, at(10, 18), at(10, 23), YELLOW, "nur bis 23 Uhr")
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, job_function=job_function("Rigging"))
        warnings = self.warnings()
        self.assertEqual(len(warnings), 2)
        self.assertFalse(getattr(warnings[0], "is_hint", False))  # the job function
        self.assertTrue(warnings[-1].is_hint)
        self.assertIn("nur bis 23 Uhr", warnings[-1])

    def test_available_and_other_periods_say_nothing(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(13), GREEN)
        red(self.anna, at(13), at(15))  # touching the end of the deployment is not overlapping
        self.assertEqual(self.warnings(), [])

    def test_many_busy_times_make_one_warning(self) -> None:
        for day in range(10, 12):
            for hour in (8, 10, 12):
                AvailabilityMark.objects.create(
                    person=self.anna,
                    start=at(day, hour),
                    end=at(day, hour + 1),
                    state=RED,
                    source=AvailabilitySource.FEED,
                )
        (warning,) = self.warnings()
        self.assertIn("+3", warning)

    def test_number_of_queries_does_not_grow_with_the_lines(self) -> None:
        """NFA-014: one query more for the marks, whatever the number of lines."""
        for number in range(8):
            person = make_person(f"Person Nr{number}", rates={"Stagehand": "18.00"})
            plan(self.project, "Stagehand", person)
            red(person, at(10), at(11))
        lines = crew.load_crew_lines(self.project)
        with self.assertNumQueries(4):  # other lines, absences, availability marks, job functions
            warnings = crew.crew_warnings(lines)
        self.assertEqual(len(warnings), 8)


class WhoIsFreeTests(RentalarsTestCase):
    """PER-021 with VFG-009, VFG-010: red counts like an absence, yellow is a hint, green comes first."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tom = make_person("Tom Richter", rates={"Tontechnik": "38.00"})
        self.lea = make_person("Lea Vogel", rates={"Tontechnik": "25.00"})

    def rows(self) -> dict[str, Any]:
        return {row.person.name: row for row in people_availability(at(10, 9), at(10, 18))}

    def test_red_is_absent_and_yellow_a_hint(self) -> None:
        red(self.anna, at(10), at(11))
        availability_marks.mark_period(self.tom, at(10, 14), at(10, 20), YELLOW, "ab 14 Uhr")
        rows = self.rows()
        self.assertEqual(rows["Anna Becker"].status, "absent")
        self.assertEqual(rows["Tom Richter"].status, "free")
        self.assertEqual(len(rows["Tom Richter"].limited), 1)
        self.assertEqual(rows["Lea Vogel"].status, "free")

    def test_busy_in_the_linked_calendar_is_absent(self) -> None:
        AvailabilityMark.objects.create(
            person=self.lea, start=at(10, 9), end=at(10, 10), state=RED, source=AvailabilitySource.FEED
        )
        self.assertEqual(self.rows()["Lea Vogel"].status, "absent")

    def test_who_said_available_comes_first_and_limits_last(self) -> None:
        availability_marks.mark_period(self.tom, at(10), at(11), GREEN)
        availability_marks.mark_period(self.anna, at(10), at(11), YELLOW)
        names = [row.person.name for row in people_availability(at(10, 9), at(10, 18))]
        self.assertEqual(names, ["Tom Richter", "Lea Vogel", "Anna Becker"])

    def test_number_of_queries_does_not_grow_with_the_people(self) -> None:
        for number in range(6):
            red(make_person(f"Person Nr{number}", rates={"Stagehand": "18.00"}), at(10), at(11))
        with self.assertNumQueries(4):  # people, crew lines, absences, availability marks
            rows = people_availability(at(10, 9), at(10, 18))
        self.assertEqual(len(rows), 9)


# --- PER-022: the linked calendar -------------------------------------------------------------------------------


class FeedParsingTests(RentalarsTestCase):
    """PER-022: which appointments of an .ics calendar are busy."""

    def test_busy_appointments_with_repetitions(self) -> None:
        periods = calendars.busy_periods(FEED)
        found = [(period.start, period.end) for period in periods]
        self.assertEqual(
            found,
            [
                (at(1, 18), at(1, 20)),  # the choir, first evening (8 March is left out)
                (at(10, 9), at(10, 12)),  # the dentist
                (at(12), at(14)),  # two whole days
                (at(15, 18), at(15, 20)),
                (at(16, 10), at(16, 12)),  # without time zone: local time, with a duration
                (at(22, 18), at(22, 20)),
            ],
        )
        self.assertTrue(all(period.uid for period in periods))
        self.assertEqual(len({period.uid for period in periods}), len(periods))

    def test_the_window_is_a_month_back_and_half_a_year_ahead(self) -> None:
        late = FEED.replace(b"20270310T090000", b"20271201T090000").replace(b"20270310T120000", b"20271201T120000")
        starts = [period.start for period in calendars.busy_periods(late)]
        self.assertNotIn(at(1, 9, month=12), starts)
        set_clock(at(1, 8, month=10))
        starts = [period.start for period in calendars.busy_periods(late)]
        self.assertIn(at(1, 9, month=12), starts)

    def test_outlook_free_and_moments_without_length_block_nothing(self) -> None:
        data = (
            b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\n"
            b"BEGIN:VEVENT\r\nUID:o1\r\nDTSTART:20270310T080000Z\r\nDTEND:20270310T100000Z\r\n"
            b"X-MICROSOFT-CDO-BUSYSTATUS:FREE\r\nEND:VEVENT\r\n"
            b"BEGIN:VEVENT\r\nUID:o2\r\nDTSTART:20270310T080000Z\r\nEND:VEVENT\r\n"
            b"BEGIN:VEVENT\r\nUID:o3\r\nDTSTART;VALUE=DATE:20270311\r\nEND:VEVENT\r\n"
            b"END:VCALENDAR\r\n"
        )
        self.assertEqual([(period.start, period.end) for period in calendars.busy_periods(data)], [(at(11), at(12))])

    def test_no_calendar(self) -> None:
        for data in (b"<html>Login</html>", b"", b"BEGIN:VEVENT\r\nEND:VEVENT\r\n"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                calendars.busy_periods(data)


class FeedReadingTests(RentalarsTestCase):
    """PER-022: reading the linked calendar regularly; errors are noted, the last good reading stays."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.server.files["/anna.ics"] = (200, {"Content-Type": "text/calendar"}, FEED)
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        availability_marks.mark_period(self.anna, at(20), at(21), GREEN, "eigene Angabe")
        # One of possibly several linked calendars (PER-031).
        self.feed = calendars.add_feed(self.anna, f"{self.server.url}/anna.ics")

    def feed_marks(self) -> list[tuple[datetime.datetime, datetime.datetime]]:
        return [
            (mark.start, mark.end)
            for mark in self.anna.availability_marks.filter(source=AvailabilitySource.FEED).order_by("start")
        ]

    def test_reading_replaces_the_busy_times_and_keeps_own_marks(self) -> None:
        self.assertTrue(calendars.read_feeds(self.anna))
        self.assertEqual(len(self.feed_marks()), 6)
        self.assertTrue(
            all(mark.state == RED and mark.note == "" for mark in self.anna.availability_marks.filter(source="feed"))
        )
        self.server.files["/anna.ics"] = (
            200,
            {},
            FEED.replace(b"UID:doctor@example.org", b"UID:doctor@example.org\nTRANSP:TRANSPARENT"),
        )
        self.assertTrue(calendars.read_feeds(self.anna, force=True))
        self.assertEqual(len(self.feed_marks()), 5)
        self.assertEqual(own_marks(self.anna), [(at(20), at(21), GREEN, "eigene Angabe")])
        self.feed.refresh_from_db()
        self.assertEqual((self.feed.error, self.feed.checked_at), ("", NOW))

    def test_a_failure_is_noted_and_the_last_reading_stays(self) -> None:
        calendars.read_feeds(self.anna)
        del self.server.files["/anna.ics"]
        self.assertIs(calendars.read_feeds(self.anna, force=True), False)
        self.feed.refresh_from_db()
        self.assertTrue(self.feed.error)
        self.assertNotIn(self.server.url, self.feed.error)
        self.assertEqual(len(self.feed_marks()), 6)
        self.server.files["/anna.ics"] = (200, {}, FEED)
        calendars.read_feeds(self.anna, force=True)
        self.feed.refresh_from_db()
        self.assertEqual((self.feed.error, self.feed.failures), ("", 0))

    def test_what_goes_wrong_is_named_without_the_answer(self) -> None:
        cases = {
            "/login.ics": (200, {"Content-Type": "text/html"}, b"<html>secret page content</html>"),
            "/denied.ics": (403, {}, b"secret reason"),
            "/broken.ics": (500, {}, b"stack trace"),
        }
        self.server.files.update(cases)
        for path in cases:
            with self.subTest(path=path):
                feed = calendars.add_feed(self.anna, f"{self.server.url}{path}")
                self.assertIs(calendars.read_calendar(feed), False)
                feed.refresh_from_db()
                self.assertNotIn("secret", feed.error)
                self.assertNotIn("stack", feed.error)
                self.assertTrue(feed.error)

    def test_size_and_time_limits(self) -> None:
        with mock.patch("rentalars.personnel.calendar_client.MAX_BYTES", 500), self.assertRaises(CalendarHttpError):
            fetch_calendar(f"{self.server.url}/anna.ics")
        self.server.delay = 1.0
        with mock.patch("rentalars.personnel.calendar_client.TIMEOUT", 0.2), self.assertRaises(CalendarHttpError):
            fetch_calendar(f"{self.server.url}/anna.ics")

    def test_only_http_and_https_also_after_a_redirection(self) -> None:
        self.server.files["/moved.ics"] = (302, {"Location": "/anna.ics"}, b"")
        self.assertEqual(fetch_calendar(f"{self.server.url}/moved.ics"), FEED)
        self.server.files["/evil.ics"] = (302, {"Location": "file:///etc/passwd"}, b"")
        with self.assertRaises(CalendarHttpError):
            fetch_calendar(f"{self.server.url}/evil.ics")
        with self.assertRaises(ValidationError):
            calendars.add_feed(self.anna, "file:///etc/passwd")
        self.assertEqual(normalise_url(" webcal://example.org/a.ics "), "https://example.org/a.ics")

    def test_the_periodic_run_reads_every_thirty_minutes(self) -> None:
        calendars.run_due()
        self.assertEqual(self.server.methods(), ["GET"])
        calendars.run_due()
        self.assertEqual(self.server.methods(), ["GET"])
        set_clock(clock() + datetime.timedelta(minutes=31))
        result = calendars.run_due()
        self.assertEqual((self.server.methods(), result.feeds_read), (["GET", "GET"], 1))

    def test_removing_the_link_removes_its_busy_times(self) -> None:
        calendars.read_feeds(self.anna)
        calendars.remove_feed(self.feed)
        self.assertEqual(self.feed_marks(), [])
        self.assertEqual(len(own_marks(self.anna)), 1)

    def test_repeated_failures_are_told_once(self) -> None:
        del self.server.files["/anna.ics"]
        for _attempt in range(calendars.FAILURES_BEFORE_NOTICE + 2):
            calendars.read_feeds(self.anna, force=True)
        notices = Notification.objects.filter(user=self.anna.user)
        self.assertEqual(notices.count(), 1)
        self.assertEqual(notices.get().url, "/me/availability/#calendars")

    def test_the_run_never_raises(self) -> None:
        with (
            mock.patch("rentalars.personnel.calendars.busy_periods", side_effect=RuntimeError("bug")),
            self.assertLogs("rentalars.personnel.calendars", "ERROR"),
        ):
            result = calendars.run_due()
        self.assertEqual(result.feeds_failed, 1)
        with (
            mock.patch("rentalars.personnel.calendars.Person.objects.filter", side_effect=RuntimeError("database")),
            self.assertLogs("rentalars.personnel.calendars", "ERROR"),
        ):
            calendars.run_due()


# --- PER-023: deployments as a calendar ----------------------------------------------------------------


class DeploymentsCalendarTests(RentalarsTestCase):
    """PER-023: the own deployments as .ics – what the person sees anyway, no customer, no prices."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.project = make_project(
            "Stadtfest", customer=make_customer("Geheimkunde AG"), venue="Marktplatz Musterstadt"
        )
        self.line = plan(self.project, "Tontechnik", self.anna, meeting_point="Tor 3", note="Schwarze Kleidung")

    def events(self) -> list[icalendar.Event]:
        body, _etag = calendars.deployments_calendar(self.anna)
        return icalendar.Calendar.from_ical(body).walk("VEVENT")

    def test_one_event_per_deployment(self) -> None:
        (event,) = self.events()
        self.assertEqual(str(event["UID"]), calendars.deployment_uid(self.line.pk))
        self.assertIn(f"rentalars-crewline-{self.line.pk}@", str(event["UID"]))
        self.assertIn("Tontechnik", str(event["SUMMARY"]))
        self.assertIn(self.project.number, str(event["SUMMARY"]))
        self.assertIn("Stadtfest", str(event["SUMMARY"]))
        self.assertEqual(str(event["LOCATION"]), "Marktplatz Musterstadt")
        self.assertIn("Tor 3", str(event["DESCRIPTION"]))
        self.assertIn("Schwarze Kleidung", str(event["DESCRIPTION"]))
        self.assertIn(f"/projects/{self.project.pk}/deployment/", str(event["URL"]))
        self.assertEqual(event.decoded("DTSTART"), at(10))
        self.assertEqual(event.decoded("DTEND"), at(12))
        self.assertEqual(str(event["STATUS"]), "CONFIRMED")
        body, _etag = calendars.deployments_calendar(self.anna)
        self.assertNotIn(b"Geheimkunde", body)  # AUT-023: no customer
        self.assertNotIn(b"35.00", body)  # no hourly rate

    def test_cancelled_declined_and_old_deployments_are_left_out(self) -> None:
        option = make_project("Option", status=ProjectStatus.OPTION, start=at(20), end=at(21))
        plan(option, "Tontechnik", self.anna)
        cancelled = make_project("Abgesagt", start=at(22), end=at(23))
        plan(cancelled, "Tontechnik", self.anna)
        cancelled.status = ProjectStatus.CANCELLED
        cancelled.save()
        declined = plan(make_project("Abgelehnt", start=at(24), end=at(25)), "Tontechnik", self.anna)
        declined.request_status = RequestStatus.DECLINED
        declined.save()
        summaries = {str(event["SUMMARY"]).split(" ", 3)[-1]: str(event["STATUS"]) for event in self.events()}
        self.assertEqual(summaries, {"Stadtfest": "CONFIRMED", "Option": "TENTATIVE"})
        set_clock(at(1, 8, month=7))
        self.assertEqual(self.events(), [])

    def test_the_etag_follows_the_deployments(self) -> None:
        _body, first = calendars.deployments_calendar(self.anna)
        set_clock(clock() + datetime.timedelta(minutes=5))
        _body, again = calendars.deployments_calendar(self.anna)
        self.assertEqual(first, again)
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Tor 4")
        _body, changed = calendars.deployments_calendar(self.anna)
        self.assertNotEqual(first, changed)


class SubscriptionTokenTests(RentalarsTestCase):
    """PER-023: the secret subscription link."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker")

    def test_create_renew_and_revoke(self) -> None:
        self.assertEqual(calendars.subscription_url(self.anna), "")
        first = calendars.renew_calendar_token(self.anna)
        self.assertGreaterEqual(len(first), 40)
        self.assertTrue(calendars.subscription_url(self.anna).endswith(f"/calendar-feed/{self.anna.pk}/{first}.ics"))
        self.assertEqual(calendars.person_for_token(self.anna.pk, first), self.anna)
        second = calendars.renew_calendar_token(self.anna)
        self.assertIsNone(calendars.person_for_token(self.anna.pk, first))
        self.assertEqual(calendars.person_for_token(self.anna.pk, second), self.anna)
        calendars.revoke_calendar_token(self.anna)
        self.assertIsNone(calendars.person_for_token(self.anna.pk, second))
        self.assertIsNone(calendars.person_for_token(self.anna.pk, ""))

    def test_wrong_person_or_deactivated_person(self) -> None:
        token = calendars.renew_calendar_token(self.anna)
        other = make_person("Tom Richter")
        self.assertIsNone(calendars.person_for_token(other.pk, token))
        self.assertIsNone(calendars.person_for_token(999999, token))
        Person.objects.filter(pk=self.anna.pk).update(is_active=False)
        self.assertIsNone(calendars.person_for_token(self.anna.pk, token))

    def test_the_token_never_enters_the_change_log(self) -> None:
        from rentalars.core.models import AuditLogEntry

        calendars.renew_calendar_token(self.anna)
        self.anna.refresh_from_db()
        self.anna.phone = "0170 1"
        self.anna.save()
        for entry in AuditLogEntry.objects.filter(object_id=str(self.anna.pk)):
            self.assertNotIn("calendar_token", entry.changes)


class CalDAVPushTests(RentalarsTestCase):
    """PER-023: writing the deployments into a CalDAV calendar, only what changed."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.project = make_project("Stadtfest")
        self.line = plan(self.project, "Tontechnik", self.anna)
        calendars.set_caldav(self.anna, url=f"{self.server.url}/", username="anna", password="geheim")

    def push(self) -> calendars.PushResult:
        result = calendars.push_deployments(self.anna, force=True)
        assert result is not None
        self.anna.refresh_from_db()
        return result

    def test_the_password_is_stored_encrypted(self) -> None:
        self.anna.refresh_from_db()
        self.assertNotIn("geheim", self.anna.caldav_password_encrypted)
        self.assertEqual(decrypt_secret(self.anna.caldav_password_encrypted), "geheim")

    def test_first_write_finds_or_creates_the_calendar_rentalars(self) -> None:
        result = self.push()
        self.assertEqual((result.written, result.error), (1, ""))
        self.assertEqual(self.server.methods(), ["PROPFIND", "PROPFIND", "PROPFIND", "MKCALENDAR", "PUT"])
        self.assertRegex(self.anna.caldav_url, r"/cal/anna/rentalars-[0-9a-f]{8}/$")
        put = self.server.requests[-1]
        self.assertEqual(put[2].get("If-None-Match"), "*")
        self.assertIn("Basic ", put[2]["Authorization"])
        (event,) = self.server.event_bodies()
        self.assertEqual(str(event["UID"]), calendars.deployment_uid(self.line.pk))
        self.assertIsNotNone(self.anna.caldav_synced_at)
        # An existing calendar named "Rentalars" is used instead of creating another.
        other = make_person("Tom Richter")
        self.server.calendars = {"/cal/anna/work/": "Arbeit", "/cal/anna/mine/": "rentalars"}
        calendars.set_caldav(other, url=f"{self.server.url}/dav/", username="anna", password="geheim")
        calendars.push_deployments(other, force=True)
        other.refresh_from_db()
        self.assertTrue(other.caldav_url.endswith("/cal/anna/mine/"))

    def test_a_calendar_address_is_used_as_it_is(self) -> None:
        calendars.set_caldav(self.anna, url=f"{self.server.url}/cal/anna/work", username="anna", password="geheim")
        self.push()
        self.assertEqual(self.server.methods(), ["PROPFIND", "PUT"])
        self.assertEqual(self.anna.caldav_url, f"{self.server.url}/cal/anna/work/")

    def test_only_what_changed_is_written(self) -> None:
        self.push()
        before = len(self.server.requests)
        result = self.push()
        self.assertEqual((result.written, result.unchanged, len(self.server.requests)), (0, 1, before))
        etag = CalendarPush.objects.get(person=self.anna).etag
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Tor 3")
        result = self.push()
        self.assertEqual(result.written, 1)
        method, _path, headers = self.server.requests[-1]
        self.assertEqual((method, headers.get("If-Match")), ("PUT", etag))
        self.assertNotEqual(CalendarPush.objects.get(person=self.anna).etag, etag)
        self.assertIn("Tor 3", str(self.server.event_bodies()[0]["DESCRIPTION"]))

    def test_a_change_on_the_phone_is_written_over(self) -> None:
        self.push()
        path = next(iter(self.server.events))
        self.server.events[path] = ('"changed-on-phone"', self.server.events[path][1])
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Halle 2")
        result = self.push()
        self.assertEqual((result.written, result.error), (1, ""))
        self.assertEqual(self.server.methods()[-2:], ["PUT", "PUT"])
        self.assertIn("Halle 2", str(self.server.event_bodies()[0]["DESCRIPTION"]))

    def test_gone_deployments_are_deleted_old_ones_stay(self) -> None:
        second = plan(make_project("Messe", start=at(20), end=at(21)), "Tontechnik", self.anna)
        self.push()
        self.assertEqual(len(self.server.events), 2)
        crew.delete_crew_line(second)
        result = self.push()
        self.assertEqual((result.deleted, len(self.server.events)), (1, 1))
        self.assertEqual(self.server.requests[-1][0], "DELETE")
        self.assertTrue(self.server.requests[-1][2].get("If-Match"))
        # Months later the Stadtfest is history: it stays in the calendar, Rentalars just forgets it.
        set_clock(at(1, 8, month=7))
        result = self.push()
        self.assertEqual((result.deleted, len(self.server.events)), (0, 1))
        self.assertFalse(CalendarPush.objects.filter(person=self.anna).exists())

    def test_cancelled_projects_disappear(self) -> None:
        self.push()
        self.project.status = ProjectStatus.CANCELLED
        self.project.save()
        self.assertEqual(self.push().deleted, 1)
        self.assertEqual(self.server.events, {})

    def test_refused_login_is_noted_and_told_once(self) -> None:
        self.server.credentials = ("anna", "anders")
        result = self.push()
        self.assertTrue(result.error)
        self.assertEqual((self.anna.caldav_error, self.anna.caldav_failures), (result.error, 1))
        for _attempt in range(calendars.FAILURES_BEFORE_NOTICE + 1):
            self.push()
        self.assertEqual(Notification.objects.filter(user=self.anna.user).count(), 1)
        self.server.credentials = ("anna", "geheim")
        self.assertEqual(self.push().error, "")
        self.assertEqual((self.anna.caldav_error, self.anna.caldav_failures), ("", 0))

    def test_a_changed_crew_line_makes_the_person_due(self) -> None:
        tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        self.push()
        Person.objects.filter(pk=self.anna.pk).update(caldav_dirty=False)
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, person=tom)
        self.anna.refresh_from_db()
        tom.refresh_from_db()
        self.assertTrue(self.anna.caldav_dirty)  # the person taken off the line
        self.assertFalse(tom.caldav_dirty)  # no CalDAV calendar, nothing to do
        calendars.run_due()
        self.anna.refresh_from_db()
        self.assertFalse(self.anna.caldav_dirty)
        self.assertEqual(self.server.events, {})
        # Deleting a line makes due as well.
        line = plan(self.project, "Tontechnik", self.anna)
        Person.objects.filter(pk=self.anna.pk).update(caldav_dirty=False)
        crew.delete_crew_line(line)
        self.anna.refresh_from_db()
        self.assertTrue(self.anna.caldav_dirty)

    def test_the_periodic_run_writes_what_is_due(self) -> None:
        result = calendars.run_due()
        self.assertEqual(result.calendars_written, 1)
        requests = len(self.server.requests)
        calendars.run_due()  # nothing due
        self.assertEqual(len(self.server.requests), requests)
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, note="Neu")
        calendars.run_due()  # due because of the change, within a minute
        self.assertEqual(self.server.methods()[-1], "PUT")

    def test_another_calendar_starts_afresh(self) -> None:
        self.push()
        self.assertEqual(CalendarPush.objects.filter(person=self.anna).count(), 1)
        calendars.set_caldav(self.anna, url=f"{self.server.url}/cal/anna/work/", username="anna", password=None)
        self.assertEqual(CalendarPush.objects.filter(person=self.anna).count(), 0)
        self.anna.refresh_from_db()
        self.assertEqual(decrypt_secret(self.anna.caldav_password_encrypted), "geheim")
        calendars.set_caldav(self.anna, url="", username="", password=None)
        self.anna.refresh_from_db()
        self.assertEqual((self.anna.caldav_url, self.anna.caldav_password_encrypted), ("", ""))
        self.assertIsNone(calendars.push_deployments(self.anna, force=True))

    def test_the_client_refuses_foreign_credentials_after_a_redirection(self) -> None:
        from rentalars.personnel.calendar_client import _may_send_credentials

        self.assertTrue(
            _may_send_credentials("https://caldav.icloud.com/", "https://p52-caldav.icloud.com/1/calendars/")
        )
        self.assertFalse(_may_send_credentials("https://caldav.icloud.com/", "https://evil.example.org/"))
        self.assertFalse(_may_send_credentials("https://cloud.example.de/", "http://cloud.example.de/"))
        self.assertTrue(_may_send_credentials("http://127.0.0.1:5232/", "http://127.0.0.1:5232/anna/"))

    def test_server_errors(self) -> None:
        self.push()
        self.server.fail_with = 507
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, note="voll")
        self.assertTrue(self.push().error)
        calendar = CalDAVCalendar(f"{self.server.url}/nowhere/", "anna", "geheim")
        self.server.fail_with = None
        with self.assertRaises(CalendarHttpError):
            calendar.find_collection()


class PrivacyTests(RentalarsTestCase):
    """NFA-009 with PER-021 to PER-023: information and erasure include availability and calendars."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", email="anna@example.de")
        red(self.anna, at(10), at(11), "privat")
        calendars.add_feed(self.anna, "https://calendar.example.org/private/abc.ics")
        calendars.set_caldav(self.anna, url="https://cloud.example.org/dav/", username="anna", password="geheim")
        calendars.renew_calendar_token(self.anna)
        CalendarPush.objects.create(person=self.anna, uid="x", href="x.ics", digest="d")

    def test_export_tells_everything_but_the_password(self) -> None:
        document = export_person(self.anna)
        self.assertEqual(document["availability"][0]["note"], "privat")
        # Every linked calendar (PER-031).
        self.assertEqual(
            [feed["address"] for feed in document["calendars"]["linked_calendars"]],
            ["https://calendar.example.org/private/abc.ics"],
        )
        self.assertTrue(document["calendars"]["subscription_link_active"])
        self.assertNotIn("geheim", str(document))

    def test_anonymising_erases_marks_links_and_secrets(self) -> None:
        anonymise_person(self.anna)
        self.anna.refresh_from_db()
        self.assertFalse(AvailabilityMark.objects.filter(person=self.anna).exists())
        self.assertFalse(CalendarPush.objects.filter(person=self.anna).exists())
        self.assertFalse(self.anna.calendar_feeds.exists())  # PER-031: the linked calendars with their addresses
        for name in (
            "calendar_token",
            "caldav_url",
            "caldav_username",
            "caldav_password_encrypted",
        ):
            self.assertEqual(getattr(self.anna, name), "", name)


class CommandTests(RentalarsTestCase):
    """PER-022, PER-023: by hand with ``sync_calendars``, every minute with ``run_jobs``."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.server.files["/anna.ics"] = (200, {}, FEED)
        self.anna = make_person("Anna Becker")
        calendars.add_feed(self.anna, f"{self.server.url}/anna.ics")

    def test_sync_calendars(self) -> None:
        output = StringIO()
        call_command("sync_calendars", stdout=output)
        self.assertIn("1 read", output.getvalue())
        output = StringIO()
        call_command("sync_calendars", person=self.anna.pk, stdout=output)
        self.assertIn("Linked calendar 127.0.0.1: read", output.getvalue())  # One line per calendar
        self.assertEqual(self.server.methods(), ["GET", "GET"])

    def test_run_jobs_reads_due_calendars_and_survives_their_errors(self) -> None:
        call_command("run_jobs", verbosity=0)
        self.assertEqual(self.server.methods(), ["GET"])
        with (
            mock.patch("rentalars.personnel.calendars.run_due", side_effect=RuntimeError("bug")),
            self.assertLogs("rentalars.core.management.commands.run_jobs", "ERROR"),
        ):
            call_command("run_jobs", verbosity=0)

    def test_the_query_count_of_an_idle_run_is_small(self) -> None:
        calendars.run_due()
        with CaptureQueriesContext(connection) as queries:
            calendars.run_due()
        self.assertLessEqual(len(queries), 2)


# --- A real CalDAV server, if one is at hand ---------------------------------------------------------------


RADICALE = os.environ.get("RENTALARS_TEST_RADICALE", "")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@skipUnless(RADICALE and shutil.which(RADICALE), "set RENTALARS_TEST_RADICALE to the radicale program to run these")
class RadicaleTests(RentalarsTestCase):
    """PER-023 against Radicale: discovery, creating the calendar, writing, changing and deleting.

    Radicale is installed in an environment of its own, never in the one of
    Rentalars, e.g. ``python -m venv /tmp/radicale && /tmp/radicale/bin/pip
    install radicale``, then ``RENTALARS_TEST_RADICALE=/tmp/radicale/bin/radicale``.
    """

    def setUp(self) -> None:
        super().setUp()
        folder = tempfile.mkdtemp(prefix="radicale-")
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        port = _free_port()
        with open(os.path.join(folder, "users"), "w", encoding="utf-8") as users:
            users.write("anna:geheim\n")
        with open(os.path.join(folder, "config"), "w", encoding="utf-8") as config:
            config.write(
                f"[server]\nhosts = 127.0.0.1:{port}\n[auth]\ntype = htpasswd\n"
                f"htpasswd_filename = {folder}/users\nhtpasswd_encryption = plain\n"
                f"[storage]\nfilesystem_folder = {folder}/collections\n[logging]\nlevel = warning\n"
            )
        process = subprocess.Popen(
            [RADICALE, "--config", os.path.join(folder, "config")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.addCleanup(process.wait, 10)
        self.addCleanup(process.terminate)
        self.url = f"http://127.0.0.1:{port}/"
        for _attempt in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.project = make_project("Stadtfest")
        self.line = plan(self.project, "Tontechnik", self.anna, meeting_point="Tor 3")

    def test_write_change_and_delete(self) -> None:
        from rentalars.personnel.calendar_client import request

        calendars.set_caldav(self.anna, url=self.url, username="anna", password="geheim")
        result = calendars.push_deployments(self.anna, force=True)
        self.anna.refresh_from_db()
        self.assertEqual((result.written, result.error), (1, ""))
        self.assertRegex(self.anna.caldav_url, r"/anna/rentalars-[0-9a-f]{8}/$")
        push = CalendarPush.objects.get(person=self.anna)
        stored = request("GET", self.anna.caldav_url + push.href, credentials=("anna", "geheim"))
        self.assertEqual(stored.status, 200)
        self.assertIn(b"Tor 3", stored.body)
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, meeting_point="Tor 4")
        self.assertEqual(calendars.push_deployments(self.anna, force=True).written, 1)
        stored = request("GET", self.anna.caldav_url + push.href, credentials=("anna", "geheim"))
        self.assertIn(b"Tor 4", stored.body)
        crew.delete_crew_line(self.line)
        self.assertEqual(calendars.push_deployments(self.anna, force=True).deleted, 1)
        gone = request("GET", self.anna.caldav_url + push.href, credentials=("anna", "geheim"))
        self.assertEqual(gone.status, 404)
        # A second person finds the calendar "Rentalars" that is there now.
        tom = make_person("Tom Richter")
        calendars.set_caldav(tom, url=self.url, username="anna", password="geheim")
        calendars.push_deployments(tom, force=True)
        tom.refresh_from_db()
        self.assertEqual(tom.caldav_url, self.anna.caldav_url)
