# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "plan": deployments dragged in the personnel plan (VFG-031), exact times, hatching and conflicts in
the plans (VFG-032), hourly lines and a wider scroll range of the timelines (VFG-033). PER-039 (time ranges in the
week of the availability calendar) is a page script over the existing form: see the UI and browser tests."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from rentalars.accounts.rights import rights_of
from rentalars.personnel.models import Absence, AvailabilityMark, Person
from rentalars.projects import course
from rentalars.projects.models import CrewLine, PhaseKind, Project, ProjectStatus, RequestStatus
from rentalars.schedule import moves, services
from rentalars.schedule.moves import CREW, MoveRequest
from rentalars.schedule.services import Scale
from rentalars.schedule.timelines import person_timeline
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, at, make_person, make_project, make_user, plan


def scale_of(**query: str) -> tuple[Scale, dict]:
    return services.scale_from_request(RequestFactory().get("/schedule/personnel/", query))


class ScrollRangeTests(RentalarsTestCase):
    """VFG-033: hour columns hold the chosen span and two more on each side (one)."""

    def test_two_spans_before_and_after(self) -> None:
        scale, navigation = scale_of(days="4", **{"from": "2027-03-10"})
        self.assertEqual((scale.days[0], scale.days[-1]), (datetime.date(2027, 3, 2), datetime.date(2027, 3, 21)))
        self.assertEqual((scale.hours, scale.columns, scale.focus, scale.visible), (3, 160, 64, 32))
        self.assertEqual((scale.spans, scale.span_days), (5, 4))
        self.assertEqual(scale.grid_style, "--cols: 160; --days: 20; --hours: 3; --spans: 5")
        # Earlier and later still move by the chosen span: the page loads the neighbouring span while scrolling.
        self.assertEqual((navigation["earlier"], navigation["later"]), (at(6).date(), at(14).date()))

    def test_weeks_stay_as_they_were(self) -> None:
        scale, _navigation = scale_of(weeks="2", **{"from": "2027-03-08"})
        self.assertEqual((len(scale.days), scale.spans, scale.span_days), (14, 1, 0))
        self.assertIn("--spans: 1", scale.grid_style)

    def test_every_number_of_days(self) -> None:
        for count in range(1, 11):
            with self.subTest(days=count):
                scale, _navigation = scale_of(days=str(count), **{"from": "2027-03-10"})
                self.assertEqual((len(scale.days), scale.spans, scale.span_days), (5 * count, 5, count))
                self.assertEqual(scale.days[scale.focus * scale.hours // 24], datetime.date(2027, 3, 10))


class ExactPeriodTests(RentalarsTestCase):
    """VFG-032: the hover names the exact times – "9:00 Uhr bis 13:30 Uhr"."""

    def test_within_one_day(self) -> None:
        self.assertEqual(services.exact_period(at(10, 9), at(10, 13, 30)), "Mi 10.03., 9:00 Uhr bis 13:30 Uhr")
        self.assertEqual(services.exact_period(at(10, 18), at(11)), "Mi 10.03., 18:00 Uhr bis 24:00 Uhr")

    def test_over_midnight(self) -> None:
        self.assertEqual(
            services.exact_period(at(10, 22), at(11, 2, 15)), "Mi 10.03., 22:00 Uhr bis Do 11.03., 2:15 Uhr"
        )

    def test_whole_days(self) -> None:
        self.assertEqual(services.exact_period(at(10), at(11)), "Mi 10.03., ganztägig")
        self.assertEqual(services.exact_period(at(10), at(13)), "Mi 10.03. bis Fr 12.03.")


class PersonnelPlanTitlesTests(RentalarsTestCase):
    """VFG-032: titles with exact times; "Konflikt" on the bars that take part in a warning."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.line = plan(make_project("Stadtfest"), "Tontechnik", self.anna, start=at(10, 9), end=at(10, 13, 30))
        self.free = plan(make_project("Weinfest"), "Tontechnik", self.anna, start=at(11, 18), end=at(11, 22))
        AvailabilityMark.objects.create(person=self.anna, start=at(10, 12), end=at(10, 16), state="unavailable")
        AvailabilityMark.objects.create(person=self.anna, start=at(11, 8), end=at(11, 12), state="available")
        Absence.objects.create(person=self.anna, kind="vacation", start=at(13), end=at(15), note="Ostsee")

    def rows(self, scale: Scale, **options: object) -> services.PlanRow:
        (row,) = services.personnel_rows(Person.objects.filter(pk=self.anna.pk), scale, **options)  # type: ignore[arg-type]
        return row

    def test_titles_and_conflicts(self) -> None:
        row = self.rows(Scale(days=services.day_range(at(8).date(), 14)))
        conflict, free = row.bars
        self.assertEqual(conflict.css, "crew status-confirmed is-conflict")
        self.assertIn("Mi 10.03., 9:00 Uhr bis 13:30 Uhr · Konflikt", conflict.title)
        self.assertEqual(free.css, "crew status-confirmed")
        self.assertTrue(free.title.endswith("Do 11.03., 18:00 Uhr bis 22:00 Uhr"))
        titles = {bar.label: bar.title for bar in row.availability}
        self.assertEqual(titles["nicht verfügbar"], "Mi 10.03., 12:00 Uhr bis 16:00 Uhr · Konflikt")
        self.assertEqual(titles["verfügbar"], "Do 11.03., 8:00 Uhr bis 12:00 Uhr")
        self.assertEqual(titles["Urlaub"], "Sa 13.03. bis So 14.03. · Ostsee")

    def test_the_queries_stay(self) -> None:
        with self.assertNumQueries(4):
            self.rows(Scale(days=services.day_range(at(8).date(), 14)))

    def test_deployments_movable_for_an_editor_in_hours(self) -> None:
        """VFG-031: in hour columns the deployments of projects the user may change carry what dragging needs."""
        scale, _navigation = scale_of(days="4", **{"from": "2027-03-09"})
        everything = rights_of(make_user("planer", superuser=True))
        row = self.rows(scale, movable=lambda shown: moves.movable_project_ids(everything, None, shown))
        move = row.bars[0].move
        self.assertEqual(move.key, f"crew-{self.line.pk}")
        self.assertEqual(move.url, f"/schedule/move/{self.line.project.number}/?what=crew&line={self.line.pk}")
        self.assertEqual((move.start, move.end), ("2027-03-10T09:00", "2027-03-10T13:30"))
        self.assertEqual(move.name, f"Anna Becker: {self.line.project.number} Tontechnik")
        # In weeks nothing moves; a closed project stays as it is (PRJ-009).
        weeks = self.rows(
            Scale(days=services.day_range(at(8).date(), 14)), movable=lambda shown: {self.line.project_id}
        )
        self.assertIsNone(weeks.bars[0].move)
        Project.objects.filter(pk=self.line.project_id).update(status=ProjectStatus.CLOSED)
        row = self.rows(scale, movable=lambda shown: moves.movable_project_ids(everything, None, shown))
        self.assertIsNone(row.bars[0].move)

    def test_nothing_movable_for_a_reader(self) -> None:
        reader = make_user("rita", roles=("Nur-Lesen",))
        scale, _navigation = scale_of(days="4", **{"from": "2027-03-09"})
        rights = rights_of(reader)
        row = self.rows(scale, movable=lambda shown: moves.movable_project_ids(rights, reader, shown))
        self.assertTrue(all(bar.move is None for bar in row.bars))


class PersonTimelineTests(RentalarsTestCase):
    """VFG-032: a person's timeline marks conflicts and names exact times, as the personnel plan does."""

    def test_conflicts_and_times(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        project = make_project("Stadtfest")
        line = plan(project, "Tontechnik", anna, start=at(10, 9), end=at(10, 13, 30))
        AvailabilityMark.objects.create(person=anna, start=at(10, 12), end=at(10, 16), state="unavailable")
        timeline = person_timeline(anna, services.day_range(at(8).date(), 7), {project.pk})
        (bar,) = timeline.rows[0].bars
        self.assertEqual(bar.css, "crew status-confirmed is-conflict")
        self.assertEqual(bar.title, "Mi 10.03., 9:00 Uhr bis 13:30 Uhr · Konflikt")
        (mark,) = timeline.rows[1].bars
        self.assertEqual(mark.title, "Mi 10.03., 12:00 Uhr bis 16:00 Uhr")
        CrewLine.objects.filter(pk=line.pk).update(start=at(10, 17), end=at(10, 20))
        (bar,) = person_timeline(anna, services.day_range(at(8).date(), 7), {project.pk}).rows[0].bars
        self.assertEqual(bar.css, "crew status-confirmed")


class MoveCrewLineTests(RentalarsTestCase):
    """VFG-031: a deployment dragged to other times – as the crew dialog changes it."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.anna.email = "anna@example.de"
        self.anna.save()
        self.line = plan(self.project, "Stagehand", self.anna, phase=self.phase)
        CrewLine.objects.filter(pk=self.line.pk).update(
            request_status=RequestStatus.ACCEPTED, requested_start=at(10, 14), requested_end=at(10, 20)
        )
        self.line.refresh_from_db()

    def move(self, start: datetime.datetime, end: datetime.datetime, line: CrewLine | None = None) -> MoveRequest:
        return MoveRequest(project=self.project, what=CREW, crew_line=line or self.line, start=start, end=end)

    def test_the_request_names_the_line(self) -> None:
        request = self.move(at(10, 16), at(10, 22))
        self.assertEqual((request.old_start, request.old_end), (at(10, 14), at(10, 20)))
        self.assertEqual(request.key, f"crew-{self.line.pk}")
        self.assertEqual(request.name, "Einsatz von Anna Becker als Stagehand")
        self.assertFalse(request.offers_schedule)

    def test_preview_changes_nothing_and_says_what_follows(self) -> None:
        mail.outbox.clear()
        preview = moves.preview_move(self.move(at(10, 16), at(10, 21)), rights=ALL_RIGHTS)
        self.assertTrue(preview.is_possible)
        outcome = preview.outcome
        self.assertEqual(
            [(change.kind, change.before, change.after) for change in outcome.changes],
            [
                (CREW, "Mi 10.03. 14:00 – 20:00", "Mi 10.03. 16:00 – 21:00"),
            ],
        )
        (crew,) = outcome.crew
        self.assertIsNotNone(crew.asked_again)  # PER-034: accepted for other times
        self.assertEqual((outcome.hours_before, outcome.hours_after), (Decimal("6.00"), Decimal("5.00")))
        self.line.refresh_from_db()
        self.assertEqual((self.line.start, self.line.request_status), (at(10, 14), RequestStatus.ACCEPTED))
        self.assertEqual(mail.outbox, [])

    def test_moving_for_good(self) -> None:
        outcome = moves.perform_move(self.move(at(10, 16), at(10, 22)), rights=ALL_RIGHTS)
        self.line.refresh_from_db()
        self.assertEqual((self.line.start, self.line.end), (at(10, 16), at(10, 22)))
        self.assertEqual(self.line.planned_hours, Decimal("6.00"))  # the same length
        self.assertIsNone(outcome.hours_after)
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)  # PER-034: asked again
        # Only the deployment moves: the phase and the project keep their times.
        self.phase.refresh_from_db()
        self.assertEqual((self.phase.start, self.phase.end), (at(10, 14), at(10, 20)))
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual((project.start, project.end), (at(10, 8), at(12, 18)))

    def test_warnings_at_the_new_times(self) -> None:
        other = make_project("Weinfest", start=at(11, 8), end=at(11, 20))
        plan(other, "Stagehand", self.anna, start=at(11, 9), end=at(11, 12))
        preview = moves.preview_move(self.move(at(11, 10), at(11, 14)), rights=ALL_RIGHTS)
        (crew,) = preview.outcome.crew
        self.assertTrue(
            any(f"Projekt {other.number}" in warning for warning in crew.warnings)
        )  # By number only – the reader may not open the other project (AUT-016)

    def test_rules(self) -> None:
        other_line = plan(make_project("Weinfest"), "Stagehand", self.anna)
        with self.assertRaises(ValidationError):  # a line of another project
            moves.check_move(self.move(at(10, 16), at(10, 22), line=other_line))
        with self.assertRaises(ValidationError):
            moves.check_move(self.move(at(10, 16), at(10, 15)))
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.project.refresh_from_db()
        preview = moves.preview_move(self.move(at(10, 16), at(10, 22)), rights=ALL_RIGHTS)
        self.assertFalse(preview.is_possible)
        self.assertTrue(preview.errors)

    def test_an_open_place_is_named_as_such(self) -> None:
        place = plan(self.project, "Stagehand", None)
        self.assertEqual(self.move(at(10, 9), at(10, 12), line=place).name, "Offener Platz als Stagehand")
