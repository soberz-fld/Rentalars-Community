# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning: the timeline of a project (PRJ-103) and who is in the personnel plan (VFG-023, fix)."""

from __future__ import annotations

from django.http import QueryDict
from django.test import RequestFactory

from rentalars.personnel.models import Absence, Person
from rentalars.projects import course
from rentalars.projects.models import CrewLine, ProjectStatus
from rentalars.schedule import course_timeline, services
from rentalars.schedule.course_timeline import course_rows, course_scale, default_span, short_period
from rentalars.schedule.services import Scale
from tests.helpers import RentalarsTestCase, at, make_person, make_project, make_user, plan


def _get(**params: str) -> object:
    return RequestFactory().get("/projects/1/course/", params)


class DefaultSpanTests(RentalarsTestCase):
    """PRJ-103: the timeline opens on the rental period – days in hours up to ten days, else weeks."""

    def test_a_short_project_in_hours(self) -> None:
        project = make_project(start=at(10, 8), end=at(12, 18))
        self.assertEqual(default_span(project), {"from": "2027-03-10", "days": "3"})

    def test_an_end_at_midnight_does_not_take_the_next_day(self) -> None:
        project = make_project(start=at(10, 8), end=at(12))
        self.assertEqual(default_span(project), {"from": "2027-03-10", "days": "2"})

    def test_a_long_project_in_weeks(self) -> None:
        project = make_project(start=at(1, 8), end=at(20, 18))
        self.assertEqual(default_span(project), {"from": "2027-03-01", "weeks": "3"})
        year = make_project(start=at(1, 8), end=at(1, 8, year=2028))
        self.assertEqual(default_span(year)["weeks"], "12")

    def test_the_scale_follows_the_address_or_the_project(self) -> None:
        project = make_project(start=at(10, 8), end=at(12, 18))
        scale, navigation = course_scale(_get(), project)
        self.assertEqual((navigation["zoom"], navigation["first"].isoformat()), (3, "2027-03-10"))
        self.assertTrue(scale.is_hourly)
        # Two spans before and two after (VFG-033; one each), as on
        # Planung → Zeitstrahl: the bar area scrolls (VFG-022).
        self.assertEqual((scale.days[0].isoformat(), len(scale.days)), ("2027-03-04", 15))
        scale, navigation = course_scale(_get(weeks="2", **{"from": "2027-03-08"}), project)
        self.assertFalse(scale.is_hourly)
        self.assertEqual((len(scale.days), navigation["day_count"]), (14, 3))
        scale, navigation = course_scale(_get(days="1", **{"from": "2027-03-11"}), project)
        self.assertEqual((scale.hours, navigation["first"].isoformat()), (1, "2027-03-11"))

    def test_earlier_and_later_keep_the_columns_of_the_project(self) -> None:
        """An address with ``from`` only – the links "earlier" and "later", the scrolling – stays in hours."""
        short = make_project(start=at(10, 8), end=at(12, 18))
        scale, navigation = course_scale(_get(**{"from": "2027-03-07"}), short)
        self.assertEqual((navigation["zoom"], navigation["first"].isoformat()), (3, "2027-03-07"))
        long = make_project(start=at(1, 8), end=at(20, 18))
        scale, navigation = course_scale(_get(**{"from": "2027-03-22"}), long)
        self.assertEqual((navigation["zoom"], navigation["weeks"], len(scale.days)), (0, 3, 21))

    def test_other_parameters_of_the_address_stay(self) -> None:
        project = make_project(start=at(10, 8), end=at(12, 18))
        request = _get(extend="5")
        course_scale(request, project)
        self.assertEqual(request.GET, QueryDict("extend=5"))


class ShortPeriodTests(RentalarsTestCase):
    def test_texts(self) -> None:
        self.assertEqual(short_period(at(10, 9), at(10, 14)), "09:00–14:00")
        self.assertEqual(short_period(at(10, 18), at(11)), "18:00–24:00")
        self.assertEqual(short_period(at(10, 18), at(11, 2)), "10.03. 18:00 – 11.03. 02:00")
        self.assertEqual(short_period(at(10), at(12)), "10.03.–11.03.")


class CourseRowsTests(RentalarsTestCase):
    """PRJ-103: rental period, event, phases, crew by person, open places – with the colours of VFG-027."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18), event_start=at(11, 18), event_end=at(11, 23))
        self.setup_phase = course.add_phase(self.project, kind="setup", start=at(10, 12), end=at(10, 19))
        self.visit = course.add_phase(
            self.project, kind="planning", title="Ortsbegehung", start=at(1, 10), end=at(1, 11), location="Markt"
        )
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"})
        self.ben = make_person("Ben Schmidt", rates={"Stagehand": "20.00"})
        self.sound = plan(self.project, "Tontechnik", self.anna, start=at(11, 16), end=at(11, 23))
        self.hand = plan(self.project, "Stagehand", self.anna, start=at(10, 12), end=at(10, 19))
        self.asked = plan(self.project, "Stagehand", self.ben, start=at(10, 8), end=at(10, 12))
        self.open_place = plan(self.project, "Stagehand", start=at(10, 12), end=at(10, 19))
        CrewLine.objects.filter(pk=self.asked.pk).update(request_status="requested")
        self.scale = Scale(days=services.day_range(at(10).date(), 3), hours=3)

    def rows(self, **options: bool) -> list[course_timeline.CourseRow]:
        phases = list(self.project.phases.all())
        lines = list(self.project.crew_lines.select_related("job_function", "person"))
        return course_rows(self.project, phases, lines, self.scale, **options)

    def test_the_rows_in_their_order(self) -> None:
        rows = self.rows()
        self.assertEqual(
            [(row.kind, row.label) for row in rows],
            [
                ("period", "Mietzeitraum"),
                ("event", "Veranstaltung"),
                ("phase", "Ortsbegehung"),
                ("phase", "Aufbau"),
                ("person", "Ben Schmidt"),
                ("person", "Anna Becker"),
                ("open", "Stagehand"),
            ],
        )
        self.assertEqual([row.starts_group for row in rows], [False, False, True, False, True, False, False])
        period, event, visit, setup, ben, anna, open_place = rows
        self.assertEqual(period.bars[0].css, "status-confirmed")
        self.assertEqual(period.bars[0].label, "10.03. 08:00 – 12.03. 18:00")
        self.assertIn("Bestätigt", period.bars[0].title)
        self.assertEqual(event.bars[0].label, "18:00–23:00")
        # The site visit lies before the shown days: its row stays, without a bar.
        self.assertEqual((visit.bars, visit.sublabel), ([], "Planungen und Besprechungen · Markt"))
        self.assertEqual((setup.bars[0].label, setup.bars[0].css), ("12:00–19:00", "phase"))
        # The bar is cut to its exact times: 12:00 to 19:00 in columns of three hours.
        self.assertEqual((setup.bars[0].first, setup.bars[0].last), (5, 7))
        self.assertEqual([bar.label for bar in anna.bars], ["Stagehand", "Tontechnik"])
        self.assertEqual(anna.bars[0].css, "crew status-confirmed")
        self.assertEqual(ben.bars[0].css, "crew status-confirmed requested")
        # VFG-035: the exact times, as in the personnel plan.
        self.assertEqual(ben.bars[0].title, "Ben Schmidt · Stagehand · Mi 10.03., 8:00 Uhr bis 12:00 Uhr · angefragt")
        self.assertEqual((open_place.sublabel, open_place.bars[0].css), ("offen", "crew open-place"))
        self.assertEqual(open_place.bars[0].title, "Stagehand · Mi 10.03., 12:00 Uhr bis 19:00 Uhr · offen")
        self.assertEqual(anna.url, "")

    def test_declined_and_the_colours_of_the_project(self) -> None:
        CrewLine.objects.filter(pk=self.sound.pk).update(request_status="declined")
        type(self.project).objects.filter(pk=self.project.pk).update(status=ProjectStatus.OPTION)
        self.project.refresh_from_db()
        rows = self.rows(link_people=True)
        anna = next(row for row in rows if row.label == "Anna Becker")
        self.assertEqual(anna.bars[1].css, "crew status-option declined")
        self.assertIn("abgesagt", anna.bars[1].title)
        self.assertEqual(anna.url, f"/personnel/people/{self.anna.pk}/")
        self.assertEqual(rows[0].bars[0].css, "status-option")
        self.assertEqual(
            course_timeline.crew_legend(self.project),
            # VFG-035: the legend of the personnel plan, then declined (in the colour of the project) and open.
            [
                ("crew status-confirmed", "fest"),
                ("crew status-option", "Option"),
                ("crew status-inquiry", "Projekt-Anfrage"),
                ("crew status-confirmed requested", "angefragt"),
                ("crew status-confirmed is-conflict", "Konflikt"),
                ("crew status-option declined", "abgesagt"),
                ("crew open-place", "offen"),
            ],
        )

    def test_without_event_phases_and_crew_only_the_rental_period(self) -> None:
        bare = make_project("Leer", start=at(10, 8), end=at(12, 18))
        rows = course_rows(bare, [], [], self.scale)
        self.assertEqual([row.kind for row in rows], ["period"])

    def test_no_query(self) -> None:
        phases = list(self.project.phases.all())
        lines = list(self.project.crew_lines.select_related("job_function", "person"))
        with self.assertNumQueries(0):
            course_rows(self.project, phases, lines, self.scale, link_people=True)


class PeopleInThePlanTests(RentalarsTestCase):
    """VFG-023, fix: unticked, the personnel plan shows every active person."""

    def test_everybody_active_unless_only_the_busy(self) -> None:
        crew = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        office = make_user("buero").person
        away = make_person("Carla Wolf")
        Absence.objects.create(person=away, start=at(9), end=at(10))
        gone = make_person("Dora Klein")
        Person.objects.filter(pk=gone.pk).update(is_active=False)
        start, end = services.bounds(services.day_range(at(8).date(), 7))
        everybody = set(services.people_in_plan(Person.objects.filter(is_active=True), start, end))
        self.assertTrue({crew, office, away} <= everybody)
        self.assertNotIn(gone, everybody)
        busy = set(services.people_in_plan(Person.objects.filter(is_active=True), start, end, busy_only=True))
        self.assertEqual(busy, {away})
