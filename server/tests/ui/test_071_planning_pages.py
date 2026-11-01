# SPDX-License-Identifier: GPL-3.0-or-later
"""In the pages: the tab "Zeitplanung" without the venue box (PRJ-102) and with a timeline of the project
(PRJ-103), the order of the project tabs and "Überblick" (PRJ-104), every active person in the personnel plan
(VFG-023, fix)."""

from __future__ import annotations

import re

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.customers.models import Venue
from rentalars.projects import course
from rentalars.projects.models import CrewLine, RequestStatus
from tests.helpers import at, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase
from tests.ui.test_accessibility import problems_of


def _project_tabs(page: str) -> list[str]:
    nav = page[page.index('<nav class="tabs" aria-label="Projekt">') :]
    return [
        re.sub(r"<[^>]+>|\s+", " ", label).split()[0]
        for label in re.findall(r"<a [^>]*>(.*?)</a>", nav[: nav.index("</nav>")], flags=re.S)
    ]


def _timeline(page: str) -> str:
    start = page.index('<section class="course-timeline"')
    return page[start : page.index("</section>", start)]


class CourseTimelineTests(UiTestCase):
    """PRJ-102, PRJ-103 on the tab "Zeitplanung"."""

    def setUp(self) -> None:
        super().setUp()
        self.venue = Venue.objects.create(name="Stadthalle", access_notes="Tor 3, Höhe 3,80 m")
        self.project = make_project(
            start=at(10, 8), end=at(12, 18), venue_site=self.venue, event_start=at(11, 18), event_end=at(11, 23)
        )
        self.setup_phase = course.add_phase(self.project, kind="setup", start=at(10, 12), end=at(10, 19))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, start=at(10, 12), end=at(10, 19))
        plan(self.project, "Stagehand", start=at(10, 12), end=at(10, 19))
        self.url = reverse("projects:course", args=[self.project.pk])

    def test_no_venue_box_but_the_timeline(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertNotIn("<h2>Veranstaltungsort</h2>", page)
        self.assertNotIn("Tor 3", page)
        self.assertIn("Stadthalle", page)  # in the head of the project
        timeline = _timeline(page)
        self.assertIn('<h2 id="course-timeline-title" class="course-timeline-title">Zeitstrahl</h2>', timeline)
        self.assertIn('aria-label="Zeitstrahl des Projekts"', timeline)
        for label in ("Mietzeitraum", "Veranstaltung", "Aufbau", "Anna Becker", "offen"):
            self.assertIn(label, timeline)
        # Opened on the rental period: three days in columns of two hours, two spans before and after to scroll to
        # (VFG-033); earlier and later keep the days.
        self.assertIn('data-tl-zoom data-focus="72" data-shift="36" data-columns="180"', timeline)
        self.assertIn('data-earlier-url="?from=2027-03-07"', timeline)
        earlier = _timeline(self.assert_ok(self.client.get(self.url, {"from": "2027-03-07"})))
        self.assertIn('data-tl-zoom data-focus="72"', earlier)
        self.assertIn("So 07.03.2027 – Di 09.03.2027", earlier)
        self.assertIn("Mi 10.03.2027 – Fr 12.03.2027", timeline)
        # VFG-035: the exact times, as in the personnel plan.
        # PRJ-121: the crew bar can be dragged now – a link to its dialog, the title unchanged.
        self.assertIn('title="Anna Becker · Stagehand · Mi 10.03., 12:00 Uhr bis 19:00 Uhr" data-tl-dialog', timeline)
        self.assertIn(f'href="/personnel/people/{self.anna.pk}/"', timeline)
        self.assertIn('class="tl-bar crew open-place"', timeline)
        # The open items stay above, the phases below.
        self.assertLess(page.index('id="open-items"'), page.index('class="course-timeline"'))
        self.assertLess(page.index('class="course-timeline"'), page.index("<h2>Phasen</h2>"))
        self.assertEqual(problems_of(page), [])

    def test_weeks_and_days_as_on_the_planning_pages(self) -> None:
        weeks = self.assert_ok(self.client.get(self.url, {"weeks": "2", "from": "2027-03-08"}))
        self.assertIn("Mo 08.03.2027 – So 21.03.2027", weeks)
        self.assertNotIn("data-tl-zoom", weeks)
        # "Days" offers as many days as the project has.
        self.assertIn('href="?weeks=2&amp;from=2027-03-08&amp;days=3">Tage</a>', weeks)
        day = self.assert_ok(self.client.get(self.url, {"days": "1", "from": "2027-03-11"}))
        self.assertIn('data-columns="120"', day)  # one day in hours, two before and two after (VFG-033)
        self.assertIn("Do 11.03.2027", day)

    def test_a_request_and_a_refusal_in_their_colours(self) -> None:
        CrewLine.objects.filter(pk=self.line.pk).update(request_status="declined")
        ben = make_person("Ben Schmidt", rates={"Stagehand": "20.00"})
        asked = plan(self.project, "Stagehand", ben, start=at(10, 8), end=at(10, 12))
        CrewLine.objects.filter(pk=asked.pk).update(request_status="requested")
        timeline = _timeline(self.assert_ok(self.client.get(self.url)))
        self.assertIn('class="tl-bar crew status-confirmed declined"', timeline)
        self.assertIn('class="tl-bar crew status-confirmed requested"', timeline)
        self.assertIn("· abgesagt", timeline)

    def test_who_may_not_read_the_personnel_sees_names_without_links(self) -> None:
        warehouse = self.browser_for("luka", "Lager")
        timeline = _timeline(self.assert_ok(warehouse.get(self.url)))
        self.assertIn("Anna Becker", timeline)
        self.assertNotIn("/personnel/people/", timeline)

    def test_the_queries_do_not_grow_with_the_crew(self) -> None:
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as few:
            self.assert_ok(self.client.get(self.url))
        for number in range(12):
            person = make_person(f"Person {number}", rates={"Stagehand": "20.00"})
            plan(self.project, "Stagehand", person, start=at(10, 8 + number % 6), end=at(10, 16))
            course.add_phase(self.project, kind="other", title=f"Phase {number}", start=at(11, 8), end=at(11, 9))
        with CaptureQueriesContext(connection) as many:
            self.assert_ok(self.client.get(self.url))
        self.assertEqual(len(many), len(few))


class ProjectTabsTests(UiTestCase):
    """PRJ-104: the order of the tabs; "Einsatz" is now "Überblick", the PDF stays "Einsatzübersicht"."""

    def test_the_tabs_in_their_order(self) -> None:
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        self.assertEqual(
            _project_tabs(page),
            [
                "Überblick",  # (tab order; PRJ-125) adapted: the first tab, as of a service case; was after "Chat"
                "Planung",
                "Preisübersicht",
                "Dokumente",
                "Zeitplanung",
                "Packliste",
                "Korrespondenz",
                "Chat",  # UIX-010
                "Zugriff",
                "Verlauf",
            ],
        )

    def test_the_overview_of_the_crew(self) -> None:
        project = make_project()
        user = make_user("carla", roles=("Crew",))
        line = plan(project, "Stagehand", make_person("Carla Crew", rates={"Stagehand": "20.00"}, user=user))
        page = self.assert_ok(self.browser_of(user).get(reverse("projects:deployment", args=[project.pk])))
        self.assertIn(f"<title>Überblick {project.number} – Rentalars</title>", page)
        # UIX-010: the chat is open to the crew as well. EML-055: the correspondence only once the
        # request is accepted or the person is planned firmly – not while it is not asked or not answered.
        # (tab order; PRJ-125) adapted: "Überblick" first.
        self.assertEqual(_project_tabs(page), ["Überblick", "Packliste", "Chat"])
        self.assertIn(reverse("documents:deployment_pdf", args=[project.pk]), page)
        CrewLine.objects.filter(pk=line.pk).update(request_status=RequestStatus.ACCEPTED)
        page = self.assert_ok(self.browser_of(user).get(reverse("projects:deployment", args=[project.pk])))
        self.assertEqual(_project_tabs(page), ["Überblick", "Packliste", "Korrespondenz", "Chat"])


class PersonnelPlanTests(UiTestCase):
    """VFG-023, fix: without the tick every active person is in the plan."""

    def test_every_active_person_without_the_tick(self) -> None:
        make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        office = make_user("buero").person
        page = self.assert_ok(self.client.get("/schedule/personnel/", {"from": "2027-03-08"}))
        self.assertIn(f'<a href="/personnel/people/{office.pk}/">', page)
        self.assertIn("Anna Becker", page)
        busy = self.assert_ok(self.client.get("/schedule/personnel/", {"from": "2027-03-08", "busy": "1"}))
        self.assertNotIn(f'<a href="/personnel/people/{office.pk}/">', busy)
