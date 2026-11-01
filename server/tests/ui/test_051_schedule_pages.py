# SPDX-License-Identifier: GPL-3.0-or-later
"""The planning pages: month bars, week grid, hour zoom, personnel plan (VFG-020 to VFG-023).

Besides what the pages show, every new view goes through the structural
accessibility check (NFA-025) and keeps a fixed number of queries (NFA-012).
"""

from __future__ import annotations

import re

from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.personnel.models import Absence, AvailabilityMark
from rentalars.projects.models import ProjectPhase, ProjectStatus
from rentalars.schedule import calendars
from tests.helpers import at, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase
from tests.ui.test_accessibility import problems_of


class MonthTests(UiTestCase):
    """VFG-020: bars over the days of a week, a legend of the colours."""

    def test_bars_over_the_days_with_status_in_words_and_a_legend(self) -> None:
        project = make_project("Messe", start=at(10, 8), end=at(17, 18), status=ProjectStatus.OPTION)
        page = self.assert_ok(self.client.get("/schedule/", {"view": "month", "month": "2027-03"}))
        bars = re.findall(r'<a class="month-bar ([^"]*)" style="([^"]*)" href="([^"]*)"', page)
        self.assertEqual(
            bars,
            [
                # (tab order; PRJ-125) adapted: a bar opens the project on its overview, not on the planning.
                ("status-option goes-on", "grid-column: 3 / 8; grid-row: 2", f"/projects/{project.number}/overview/"),
                (
                    "status-option from-before",
                    "grid-column: 1 / 4; grid-row: 2",
                    f"/projects/{project.number}/overview/",
                ),
            ],
        )
        self.assertIn('<span class="visually-hidden">, Option, 10.03. 08:00 – 17.03. 18:00</span>', page)
        legend = page[page.index('class="cal-legend"') : page.index("</aside>")]
        for status in (
            "Anfrage",
            "Option",
            "Bestätigt – Preise und Einzelheiten offen / Bestätigt",
            "Unterwegs",
            "Wieder im Lager",
        ):
            self.assertIn(status, legend)
        self.assertNotIn("Storniert", legend)
        self.assertIn("Storniert", self.assert_ok(self.client.get("/schedule/", {"view": "month", "all": "1"})))

    def test_more_projects_than_lanes_are_counted_and_lead_to_the_week(self) -> None:
        for number in range(calendars.MONTH_LANES + 3):
            make_project(f"Projekt {number}", start=at(10), end=at(11))
        page = self.assert_ok(self.client.get("/schedule/", {"view": "month", "month": "2027-03"}))
        self.assertEqual(page.count('class="month-bar '), calendars.MONTH_LANES)
        self.assertIn('href="?view=week&amp;week=2027-03-10" title="Diese Woche öffnen">+3', page)
        self.assertIn('+3<span class="visually-hidden"> weitere Projekte am 10.03.</span>', page)


class WeekTests(UiTestCase):
    """VFG-021: a time grid with an all-day strip; blocks link to the project."""

    def test_time_grid_with_all_day_strip_blocks_and_now(self) -> None:
        fair = make_project("Messe", start=at(1, 8), end=at(3, 18))
        ProjectPhase.objects.create(project=fair, kind="setup", start=at(1, 7), end=at(1, 12))
        talk = make_project("Vortrag", start=at(2, 10), end=at(2, 12), status=ProjectStatus.INQUIRY)
        make_project("Kinderfest", start=at(2, 11), end=at(2, 17))
        page = self.assert_ok(self.client.get("/schedule/", {"view": "week", "week": "2027-03-01"}))
        self.assertIn("data-week-grid", page)
        self.assertIn('data-scroll-hour="6"', page)
        self.assertIn("ganztägig", page)
        strip = page[page.index("data-all-day>") : page.index('class="wk-hours"')]
        self.assertIn("ab 08:00", strip)
        self.assertIn("bis 18:00", strip)
        self.assertIn(">Messe<", strip)
        self.assertIn(
            f'<a class="wk-event status-inquiry" style="--start: 10.000; --length: 2.000; --lane: 0; --lanes: 2" '
            f'href="/projects/{talk.number}/overview/"',  # (tab order; PRJ-125) adapted
            page,
        )
        self.assertIn('style="--start: 11.000; --length: 6.000; --lane: 1; --lanes: 2"', page)
        self.assertIn('<a class="wk-event status-confirmed phase" style="--start: 7.000; --length: 5.000', page)
        self.assertIn("Aufbau · Messe", page)
        self.assertIn('<div class="wk-now" style="--at: 8.000" data-now aria-hidden="true"></div>', page)
        self.assertIn('data-day="2027-03-01" role="group" aria-label="Montag, 1. März"', page)

    def test_many_all_day_entries_wait_behind_a_button(self) -> None:
        for number in range(calendars.WEEK_ALL_DAY_LANES + 2):
            make_project(f"Projekt {number}", start=at(2), end=at(4))
        page = self.assert_ok(self.client.get("/schedule/", {"view": "week", "week": "2027-03-01"}))
        self.assertEqual(page.count(" is-extra"), 2)
        self.assertIn('data-all-day-toggle aria-expanded="false"', page)
        self.assertIn('+2<span class="visually-hidden"> weitere ganztägige Einträge am 02.03., alle zeigen', page)
        self.assertIn("Weniger zeigen", page)


class ZoomTests(UiTestCase):
    """VFG-022: timeline and personnel plan in one, two or three days of hours; weeks as before."""

    def test_timeline_of_one_day_in_hours(self) -> None:
        make_project("Vortrag", start=at(10, 8), end=at(10, 12))
        page = self.assert_ok(self.client.get("/schedule/timeline/", {"days": "1", "from": "2027-03-10"}))
        self.assertIn("is-hourly", page)
        # VFG-033: two days before and two after the chosen one.
        self.assertIn('data-tl-zoom data-focus="48" data-shift="24" data-columns="120"', page)
        self.assertIn('data-earlier-url="?days=1&amp;from=2027-03-09"', page)
        self.assertIn('data-later-url="?days=1&amp;from=2027-03-11"', page)
        make_project("Heute", start=at(1, 8), end=at(1, 12))
        self.assertIn('<div class="tl-dayname today', self.assert_ok(self.client.get("/schedule/timeline/?days=1")))
        self.assertIn('title="Mi 10.03., 08:00–09:00">08</div>', page)
        self.assertIn('style="grid-column: 57 / 61"', page)
        self.assertIn("Mi 10.03.2027", page)
        # VFG-024: "Days" with the number of days chosen in a field, 1 to 10; the way back to weeks keeps the day.
        self.assertIn('href="?days=1&amp;from=2027-03-10" aria-current="true">Tage</a>', page)
        self.assertIn('<option value="1" selected>1</option>', page)
        self.assertIn('<option value="10">10</option>', page)
        # VFG-028: the way back to weeks names the weeks, since an address without them shows days.
        self.assertIn('href="?from=2027-03-08&amp;weeks=4">Wochen</a>', page)

    def test_two_and_three_days_and_the_week_modes(self) -> None:
        make_project("Vortrag", start=at(10, 8), end=at(10, 12))
        two = self.assert_ok(self.client.get("/schedule/timeline/", {"days": "2", "from": "2027-03-10"}))
        self.assertIn('data-focus="48" data-shift="24" data-columns="120"', two)  # VFG-033: five spans
        self.assertIn("Mi 10.03.2027 – Do 11.03.2027", two)
        three = self.assert_ok(self.client.get("/schedule/timeline/", {"days": "3", "from": "2027-03-10"}))
        self.assertIn('data-focus="72" data-shift="36" data-columns="180"', three)
        # Old addresses with weeks keep working, with day columns.
        weeks = self.assert_ok(self.client.get("/schedule/timeline/", {"from": "2027-03-08", "weeks": "2"}))
        self.assertNotIn("data-tl-zoom", weeks)
        self.assertIn('<div class="tl-day"><span>Mi</span>10.3.</div>', weeks)
        self.assertIn('<option value="2" selected>2</option>', weeks)
        self.assertIn("Vortrag", weeks)

    def test_personnel_plan_in_hours(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest"), "Tontechnik", anna, start=at(10, 8), end=at(10, 18))
        page = self.assert_ok(self.client.get("/schedule/personnel/", {"days": "2", "from": "2027-03-10"}))
        self.assertIn('data-tl-zoom data-focus="48"', page)  # VFG-033: two spans before
        self.assertIn('<input type="hidden" name="days" value="2">', page)
        self.assertIn('style="grid-column: 53 / 58"', page)  # 08:00 to 18:00 in two-hour columns


class PersonnelPlanTests(UiTestCase):
    """VFG-023: availability on top, a warning that stands out, only people who can be planned."""

    def test_availability_above_deployments_and_a_conspicuous_warning(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest"), "Tontechnik", anna, start=at(10, 8), end=at(10, 18))
        plan(make_project("Weinfest"), "Tontechnik", anna, start=at(10, 14), end=at(10, 22))
        AvailabilityMark.objects.create(person=anna, start=at(8), end=at(10), state="available")
        page = self.assert_ok(self.client.get("/schedule/personnel/", {"from": "2027-03-08", "weeks": "1"}))
        # Every active person is in the plan (VFG-023); the row of Anna starts with her label.
        name = page.index(">Anna Becker</a>")
        following = page.find('<div class="tl-label person', name)
        row = page[page.rindex('<div class="tl-label person', 0, name) : following if following != -1 else None]
        self.assertIn('<span class="plan-warning" title="Einsätze überschneiden sich">', row)
        self.assertIn('<span class="visually-hidden">Warnung: Einsätze überschneiden sich.</span>', row)
        availability, deployments = row.index('class="tl-row tl-avail"'), row.index('class="tl-row tl-deploy"')
        self.assertLess(availability, deployments)
        self.assertIn("availability is-available", row[availability:deployments])
        self.assertIn(">verfügbar<", row[availability:deployments])
        # Only the bars, not the legend that follows the last row (it shows a conflict, VFG-032).
        bars = row[deployments:].split('class="tl-bar legend', 1)[0]
        self.assertEqual(bars.count("is-conflict"), 2)

    def test_absence_and_not_available_are_warnings_too(self) -> None:
        ben = make_person("Ben Schmidt", rates={"Stagehand": "20.00"})
        plan(make_project("Stadtfest"), "Stagehand", ben, start=at(10, 8), end=at(10, 18))
        AvailabilityMark.objects.create(person=ben, start=at(10), end=at(11), state="unavailable")
        Absence.objects.create(person=ben, kind="sick", start=at(10, 12), end=at(11))
        page = self.assert_ok(self.client.get("/schedule/personnel/", {"from": "2027-03-08", "weeks": "1"}))
        self.assertIn(
            "Warnung: Eingeplant während einer Abwesenheit; Eingeplant, obwohl als nicht verfügbar markiert.", page
        )
        self.assertIn(">krank<", page)

    def test_office_accounts_show_unless_only_the_busy_are_asked_for(self) -> None:
        """VFG-023, fix: unticked, every active person shows, office accounts included."""
        make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        office = make_user("buero").person
        page = self.assert_ok(self.client.get("/schedule/personnel/", {"from": "2027-03-08"}))
        self.assertIn("Anna Becker", page)
        self.assertIn(f"/personnel/people/{office.pk}/", page)
        busy = self.assert_ok(self.client.get("/schedule/personnel/", {"from": "2027-03-08", "busy": "1"}))
        self.assertIn("Niemand anzuzeigen.", busy)


class AccessibilityAndQueryTests(UiTestCase):
    """NFA-025 and NFA-012 for the new views."""

    def fill(self, count: int) -> None:
        for number in range(count):
            project = make_project(
                f"Projekt {number}", start=at(1 + number % 6, 8), end=at(2 + number % 6 + number % 3, 18)
            )
            ProjectPhase.objects.create(project=project, start=at(1 + number % 6, 8), end=at(1 + number % 6, 12))
            person = make_person(f"Person{number} Test", rates={"Stagehand": "20.00"})
            plan(project, "Stagehand", person, start=at(1 + number % 6, 8), end=at(1 + number % 6, 18))
            AvailabilityMark.objects.create(person=person, start=at(1), end=at(3), state="limited")
            Absence.objects.create(person=person, start=at(4), end=at(5))

    PATHS = (
        "/schedule/?view=month&month=2027-03",
        "/schedule/?view=week&week=2027-03-01",
        "/schedule/timeline/?days=1&from=2027-03-02",
        "/schedule/timeline/?days=3&from=2027-03-02",
        "/schedule/timeline/?weeks=4&from=2027-03-01",
        "/schedule/personnel/?days=2&from=2027-03-02",
        "/schedule/personnel/?weeks=2&from=2027-03-01",
    )

    def test_no_findings_on_the_new_views(self) -> None:
        self.fill(8)
        found = []
        for path in self.PATHS:
            found += [f"{path}: {problem}" for problem in problems_of(self.assert_ok(self.client.get(path)))]
        self.assertEqual(found, [], "\n".join(found))

    def test_queries_do_not_grow_with_projects_and_people(self) -> None:
        def counts() -> list[int]:
            result = []
            for path in self.PATHS:
                with CaptureQueriesContext(connection) as queries:
                    self.assert_ok(self.client.get(path))
                result.append(len(queries))
            return result

        self.fill(3)
        few = counts()
        self.fill(12)
        self.assertEqual(counts(), few)
