# SPDX-License-Identifier: GPL-3.0-or-later
"""PRJ-116: the period a new phase starts with – on one day, after the latest phase.

The bug: in a project from Monday 08:00 to Tuesday 20:00 the
dialog "Neue Phase …" from the vehicle form started with the whole rental
period. Whoever changed only the times got "Anfahrt Mo 08:15 – Di 09:00" and
"Aufbau Mo 09:00 – Di 10:00"; the vehicles took over these periods, were booked
twice at the same time, and the trailers were charged for two days.
"""

from __future__ import annotations

import datetime
import re

from django.urls import reverse

from rentalars.projects import course, logistics
from rentalars.projects.models import PhaseKind, ProjectPhase, VehicleLine
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, at, make_project
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_090_logistics import make_fleet

HOUR = datetime.timedelta(hours=1)


class FirstGuessTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(13, 20))

    def test_over_several_days_the_guess_lasts_eight_hours_on_the_first_day(self) -> None:
        # (phase length; PRJ-124) adapted: eight hours from the start of the rental period.
        self.assertEqual(course.first_guess(self.project), (at(12, 8), at(12, 16)))

    def test_on_one_day_it_is_the_rental_period_up_to_eight_hours(self) -> None:
        # (phase length; PRJ-124) adapted.
        day = make_project("Jazznacht", start=at(20, 12), end=at(20, 23))
        self.assertEqual(course.first_guess(day), (at(20, 12), at(20, 20)))
        short = make_project("Soundcheck", start=at(21, 12), end=at(21, 15))
        self.assertEqual(course.first_guess(short), (at(21, 12), at(21, 15)))

    def test_it_begins_where_the_latest_phase_ends(self) -> None:
        course.add_phase(self.project, kind=PhaseKind.LOADING, start=at(12, 7), end=at(12, 8))
        course.add_phase(self.project, kind=PhaseKind.TRAVEL, start=at(12, 8, 15), end=at(12, 9))
        self.assertEqual(course.first_guess(self.project), (at(12, 9), at(12, 17)))  # eight hours, was one

    def test_a_latest_phase_outside_the_rental_period_does_not_count(self) -> None:
        course.add_phase(self.project, kind=PhaseKind.AFTERCARE, start=at(13, 20), end=at(14, 10))
        self.assertEqual(course.first_guess(self.project), (at(12, 8), at(12, 16)))  # eight hours, was one
        before = make_project("Messe", start=at(20, 8), end=at(21, 20))
        course.add_phase(before, kind=PhaseKind.PLANNING, start=at(2, 10), end=at(2, 11))
        self.assertEqual(course.first_guess(before), (at(20, 8), at(20, 16)))

    def test_a_typed_period_counts_unless_it_is_the_rental_period(self) -> None:
        self.assertEqual(course.first_guess(self.project, at(13, 9), at(13, 17)), (at(13, 9), at(13, 17)))
        # The form's untouched rental period is no typed period: after the latest phase, as without one.
        course.add_phase(self.project, kind=PhaseKind.LOADING, start=at(12, 7), end=at(12, 8))
        self.assertEqual(course.first_guess(self.project, at(12, 8), at(13, 20)), (at(12, 8), at(12, 16)))
        # Typed over two days: one hour from its start (a typed period is no default: the eight hours do not cut it).
        self.assertEqual(course.first_guess(self.project, at(12, 14), at(13, 2)), (at(12, 14), at(12, 15)))
        # Nonsense is no period.
        self.assertEqual(course.first_guess(self.project, at(13, 9), at(13, 8)), (at(12, 8), at(12, 16)))


class GuessOnThePagesTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(13, 20))
        self.dialog = reverse("projects:phase_dialog", args=[self.project.pk])

    @staticmethod
    def period(page: str) -> tuple[str, str]:
        start = re.search(
            r'<input[^>]*name="start"[^>]*value="([^"]+)"|<input[^>]*value="([^"]+)"[^>]*name="start"', page
        )
        end = re.search(r'<input[^>]*name="end"[^>]*value="([^"]+)"|<input[^>]*value="([^"]+)"[^>]*name="end"', page)
        assert start and end
        return (start.group(1) or start.group(2), end.group(1) or end.group(2))

    def test_the_page_zeitplanung_follows_the_latest_phase(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:phase_create", args=[self.project.pk])))
        # (phase length; PRJ-124) adapted: eight hours instead of one.
        self.assertEqual(self.period(page), ("2027-03-12T08:00", "2027-03-12T16:00"))
        course.add_phase(self.project, kind=PhaseKind.LOADING, start=at(12, 7), end=at(12, 8, 30))
        page = self.assert_ok(self.client.get(reverse("projects:phase_create", args=[self.project.pk])))
        self.assertEqual(self.period(page), ("2027-03-12T08:30", "2027-03-12T16:30"))

    def test_the_dialog_from_the_vehicle_form_with_the_untouched_rental_period(self) -> None:
        course.add_phase(self.project, kind=PhaseKind.LOADING, start=at(12, 7), end=at(12, 8))
        page = self.assert_ok(self.htmx("get", self.dialog, {"start": "2027-03-12T08:00", "end": "2027-03-13T20:00"}))
        self.assertEqual(self.period(page), ("2027-03-12T08:00", "2027-03-12T16:00"))  # eight hours, was one

    def test_changing_only_the_times_gives_a_phase_on_that_day_and_the_van_follows(self) -> None:
        """The steps of the report: "Anfahrt" 08:15–09:00, "Aufbau" 09:00–10:00, the van on both."""
        fleet = make_fleet()
        for kind, start, end in (("travel", "08:15", "09:00"), ("setup", "09:00", "10:00")):
            page = self.htmx("get", self.dialog, {"start": "2027-03-12T08:00", "end": "2027-03-13T20:00"})
            day = self.period(self.assert_ok(page))[0][:10]
            data = form_data(page, kind=kind, start=f"{day}T{start}", end=f"{day}T{end}")
            self.assertEqual(self.htmx("post", self.dialog, data).status_code, 204)
        travel, setup = ProjectPhase.objects.filter(project=self.project).order_by("start")
        self.assertEqual((travel.start, travel.end), (at(12, 8, 15), at(12, 9)))
        self.assertEqual((setup.start, setup.end), (at(12, 9), at(12, 10)))
        for phase in (travel, setup):
            logistics.add_vehicle_line(
                self.project, rights=ALL_RIGHTS, product=fleet["car"], item=fleet["van"], phase=phase,
                start=phase.start, end=phase.end,
            )  # fmt: skip
        lines = list(VehicleLine.objects.filter(project=self.project).select_related("item", "item__vehicle"))
        self.assertTrue(all(line.end - line.start <= HOUR for line in lines))
        warnings = logistics.logistics_warnings(self.project, lines, [], [])
        self.assertFalse(
            [text for texts in warnings.values() for text in texts if "doppelt" in text or "twice" in text], warnings
        )
