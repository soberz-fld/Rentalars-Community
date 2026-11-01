# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning wishes: month bars, week grid, hour zoom, personnel plan (VFG-020 to VFG-023)."""

from __future__ import annotations

import datetime

from django.test import RequestFactory

from rentalars.personnel.models import Absence, AvailabilityMark, Person
from rentalars.projects.models import Project, ProjectPhase, ProjectStatus
from rentalars.schedule import calendars, services
from rentalars.schedule.services import Scale
from tests.helpers import RentalarsTestCase, at, make_person, make_project, make_user, plan


def _all() -> object:
    return Project.objects.all()


class MonthBarTests(RentalarsTestCase):
    """VFG-020: a project over several days is one bar per week row, stacked in lanes."""

    def test_a_bar_breaks_at_the_end_of_the_week_and_goes_on(self) -> None:
        project = make_project("Messe", start=at(10, 8), end=at(17, 18))  # Wednesday to the next Wednesday
        weeks = calendars.month_weeks(_all(), 2027, 3)
        rows = [(week.days[0].day, segment) for week in weeks for segment in week.segments]
        self.assertEqual([day for day, _segment in rows], [datetime.date(2027, 3, 8), datetime.date(2027, 3, 15)])
        first, second = (segment for _day, segment in rows)
        self.assertEqual((first.first, first.last, first.starts_before, first.ends_after), (3, 7, False, True))
        self.assertEqual((second.first, second.last, second.starts_before, second.ends_after), (1, 3, True, False))
        self.assertEqual(first.style, "grid-column: 3 / 8; grid-row: 2")
        self.assertEqual(first.url, f"/projects/{project.number}/overview/")  # (tab order; PRJ-125) adapted
        self.assertEqual(first.status_label, "Bestätigt")

    def test_a_project_ending_at_midnight_leaves_the_next_day_free(self) -> None:
        make_project("Stadtfest", start=at(10), end=at(12))
        (segment,) = [segment for week in calendars.month_weeks(_all(), 2027, 3) for segment in week.segments]
        self.assertEqual((segment.first, segment.last), (3, 4))  # Wednesday and Thursday

    def test_lanes_stack_overlapping_bars_and_reuse_free_ones(self) -> None:
        make_project("Lang", start=at(8), end=at(13))
        make_project("Mitte", start=at(9), end=at(11))
        make_project("Kurz", start=at(10), end=at(11))
        make_project("Später", start=at(12), end=at(13))
        week = next(week for week in calendars.month_weeks(_all(), 2027, 3) if week.days[0].day.day == 8)
        lanes = {segment.label: segment.lane for segment in week.segments}
        self.assertEqual(lanes, {"Lang": 0, "Mitte": 1, "Kurz": 2, "Später": 1})
        self.assertEqual(week.lanes, 3)
        self.assertEqual(week.rows_style, "grid-template-rows: auto repeat(3, auto) 1fr")
        self.assertEqual(week.extra_row, 5)

    def test_projects_beyond_the_lanes_are_counted_per_day(self) -> None:
        for number in range(calendars.MONTH_LANES + 2):
            make_project(f"Projekt {number}", start=at(10), end=at(11))
        week = next(week for week in calendars.month_weeks(_all(), 2027, 3) if week.days[0].day.day == 8)
        self.assertEqual(sum(segment.shown for segment in week.segments), calendars.MONTH_LANES)
        self.assertEqual(week.hidden, [0, 0, 2, 0, 0, 0, 0])
        self.assertEqual([hidden for _day, _column, hidden in week.cells][2], 2)

    def test_two_queries_whatever_the_number_of_projects(self) -> None:
        for number in range(12):
            project = make_project(f"Projekt {number}", start=at(1 + number), end=at(3 + number))
            ProjectPhase.objects.create(project=project, start=at(1 + number, 8), end=at(1 + number, 12))
        with self.assertNumQueries(2):
            calendars.month_weeks(_all(), 2027, 3)


class WeekGridTests(RentalarsTestCase):
    """VFG-021: the week as a time grid with an all-day strip."""

    monday = datetime.date(2027, 3, 8)

    def grid(self) -> calendars.WeekGrid:
        return calendars.week_grid(_all(), self.monday)

    def test_whole_days_and_long_periods_go_into_the_strip(self) -> None:
        self.assertTrue(calendars.lasts_whole_days(at(10), at(11)))
        self.assertTrue(calendars.lasts_whole_days(at(10, 8), at(11, 8)))
        self.assertFalse(calendars.lasts_whole_days(at(10, 8), at(10, 18)))
        self.assertFalse(calendars.lasts_whole_days(at(10, 20), at(11, 2)))
        # 28 March 2027 has 23 hours; from midnight to midnight it is still a whole day.
        self.assertTrue(calendars.lasts_whole_days(at(28), at(29)))

    def test_a_long_project_lies_in_the_strip_with_its_times(self) -> None:
        make_project("Messe", start=at(9, 8), end=at(11, 18))
        grid = self.grid()
        (segment,) = grid.all_day
        self.assertEqual((segment.first, segment.last), (2, 4))
        self.assertEqual((segment.start_note, segment.end_note), ("ab 08:00", "bis 18:00"))
        self.assertEqual(segment.strip_style, "grid-column: 2 / 5; grid-row: 1")
        self.assertEqual([column.blocks for column in grid.columns], [[]] * 7)

    def test_a_short_project_is_a_block_placed_by_its_hours(self) -> None:
        make_project("Vortrag", start=at(10, 8, 30), end=at(10, 12))
        wednesday = self.grid().columns[2]
        (block,) = wednesday.blocks
        self.assertEqual((block.begin, block.end, block.times), (8.5, 12.0, "08:30 – 12:00"))
        self.assertEqual(block.style, "--start: 8.500; --length: 3.500; --lane: 0; --lanes: 1")
        self.assertFalse(block.is_phase)

    def test_a_block_over_midnight_is_split_into_one_piece_per_day(self) -> None:
        make_project("Abiball", start=at(12, 20), end=at(13, 2))
        grid = self.grid()
        friday, saturday = grid.columns[4].blocks, grid.columns[5].blocks
        self.assertEqual([(block.begin, block.end, block.times) for block in friday], [(20.0, 24.0, "ab 20:00")])
        self.assertEqual([(block.begin, block.end, block.times) for block in saturday], [(0.0, 2.0, "bis 02:00")])

    def test_overlapping_blocks_stand_side_by_side(self) -> None:
        make_project("Konzert", start=at(10, 8), end=at(10, 23))
        make_project("Vortrag", start=at(10, 10), end=at(10, 12))
        make_project("Kinderfest", start=at(10, 12), end=at(10, 17))
        make_project("Abend", start=at(10, 23), end=at(10, 23, 30))
        grid = self.grid()
        wednesday = grid.columns[2]
        placed = {block.label: (block.lane, block.lanes) for block in wednesday.blocks}
        # The talk ends when the children's party starts: both share the second lane.
        self.assertEqual(placed["Konzert"], (0, 2))
        self.assertEqual(placed["Vortrag"], (1, 2))
        self.assertEqual(placed["Kinderfest"], (1, 2))
        self.assertEqual(placed["Abend"], (0, 1))
        self.assertEqual(wednesday.lanes, 2)
        tracks = grid.columns_style.split("var(--wk-gutter) ")[1]
        self.assertIn(f"{2 * calendars.LANE_MIN_WIDTH}px", tracks)

    def test_phases_show_with_their_project(self) -> None:
        project = make_project("Messe", start=at(9), end=at(12))
        ProjectPhase.objects.create(project=project, kind="setup", start=at(9, 7), end=at(9, 15))
        grid = self.grid()
        (block,) = grid.columns[1].blocks
        self.assertTrue(block.is_phase)
        self.assertEqual(block.label, "Aufbau · Messe")
        self.assertEqual(block.css, "status-confirmed phase")
        self.assertEqual([segment.label for segment in grid.all_day], ["Messe"])

    def test_the_grid_opens_at_six_or_earlier(self) -> None:
        make_project("Nachtschicht", start=at(7, 22), end=at(8, 4))  # continues into Monday's night
        self.assertEqual(self.grid().scroll_hour, 6)
        make_project("Frühstück", start=at(9, 5, 30), end=at(9, 9))
        self.assertEqual(self.grid().scroll_hour, 5)

    def test_now_is_marked_on_today(self) -> None:
        grid = calendars.week_grid(_all(), datetime.date(2027, 3, 1))  # the tests run on 1 March 2027, 08:00
        self.assertEqual([column.is_today for column in grid.columns], [True] + [False] * 6)
        self.assertEqual(grid.columns[0].now_style, "--at: 8.000")

    def test_the_strip_shows_three_lanes_until_all_are_asked_for(self) -> None:
        for number in range(5):
            make_project(f"Projekt {number}", start=at(9), end=at(11))
        grid = self.grid()
        self.assertTrue(grid.has_hidden)
        self.assertEqual(grid.all_day_lanes, 5)
        self.assertEqual([column.hidden for column in grid.columns], [0, 2, 2, 0, 0, 0, 0])
        self.assertTrue(all(segment.shown for segment in grid.all_day))

    def test_two_queries_whatever_the_number_of_projects(self) -> None:
        for number in range(10):
            project = make_project(f"Projekt {number}", start=at(8 + number % 5, 8), end=at(8 + number % 5, 18))
            ProjectPhase.objects.create(project=project, start=at(8 + number % 5, 8), end=at(8 + number % 5, 10))
        with self.assertNumQueries(2):
            self.grid()


class ScaleTests(RentalarsTestCase):
    """VFG-022: hour columns for one to three days; the week modes stay as they were."""

    def scale(self, **query: str) -> tuple[Scale, dict]:
        return services.scale_from_request(RequestFactory().get("/schedule/timeline/", query))

    def test_one_day_in_hours_with_a_day_before_and_after(self) -> None:
        """VFG-033: two days before and two after, to scroll into (one each)."""
        scale, navigation = self.scale(days="1", **{"from": "2027-03-10"})
        self.assertEqual(scale.days, [datetime.date(2027, 3, day) for day in (8, 9, 10, 11, 12)])
        self.assertEqual((scale.hours, scale.columns, scale.focus, scale.visible), (1, 120, 48, 24))
        self.assertEqual((navigation["earlier"], navigation["later"]), (datetime.date(2027, 3, 9), at(11).date()))
        self.assertEqual((navigation["first"], navigation["last"], navigation["zoom"]), (at(10).date(),) * 2 + (1,))
        bar = scale.bar(at(10, 8), at(10, 10, 30), label="x")
        self.assertEqual((bar.first, bar.last), (57, 59))  # 08, 09 and 10 o'clock of the middle day
        self.assertIsNone(scale.bar(at(13, 8), at(13, 9), label="x"))
        whole = scale.bar(at(1), at(20), label="x")
        self.assertEqual((whole.first, whole.last), (1, 120))

    def test_two_and_three_days_in_two_hour_columns(self) -> None:
        scale, navigation = self.scale(days="2", **{"from": "2027-03-10"})
        # VFG-033: two spans before and after the chosen one.
        self.assertEqual((scale.hours, scale.columns, scale.focus, scale.visible), (2, 120, 48, 24))
        self.assertEqual(scale.days[0], datetime.date(2027, 3, 6))
        bar = scale.bar(at(10, 9), at(10, 11), label="x")
        self.assertEqual((bar.first, bar.last), (53, 54))
        self.assertEqual(navigation["later"], datetime.date(2027, 3, 12))
        scale, _navigation = self.scale(days="3", **{"from": "2027-03-10"})
        self.assertEqual((scale.hours, scale.columns, scale.focus, len(scale.days)), (2, 180, 72, 15))
        heads = scale.hour_heads
        self.assertEqual([head.label for head in heads[:3]], ["00", "02", "04"])
        self.assertEqual(heads[0].css, "day-start")
        self.assertEqual(heads[0].title, "Do 04.03., 00:00–02:00")

    def test_the_day_the_clocks_change_has_24_columns_as_well(self) -> None:
        scale, _navigation = self.scale(days="1", **{"from": "2027-03-28"})
        self.assertEqual(len(scale.hour_heads), 120)  # VFG-033: five days of 24 columns
        bar = scale.bar(at(28, 1), at(28, 4), label="x")
        self.assertEqual((bar.first, bar.last), (50, 52))  # 01, 02 and 03 o'clock on the wall clock

    def test_week_modes_and_their_addresses_stay(self) -> None:
        scale, navigation = self.scale(weeks="2", **{"from": "2027-03-08"})
        self.assertFalse(scale.is_hourly)
        self.assertEqual((scale.columns, scale.focus, scale.visible, navigation["zoom"]), (14, 0, 14, 0))
        self.assertEqual(scale.row_style, "grid-template-columns: repeat(14, minmax(28px, 1fr))")
        bar = scale.bar(at(10, 8), at(11, 12), label="x")
        self.assertEqual((bar.first, bar.last), (3, 4))
        for wrong in ("11", "0", "abc"):  # VFG-024: 1 to 10 days are hour columns
            with self.subTest(days=wrong):
                scale, navigation = self.scale(days=wrong, weeks="1")
                self.assertEqual((scale.hours, len(scale.days), navigation["zoom"]), (24, 7, 0))

    def test_project_timeline_in_hours(self) -> None:
        project = make_project("Vortrag", start=at(10, 8), end=at(10, 12))
        ProjectPhase.objects.create(project=project, kind="setup", start=at(10, 7), end=at(10, 8))
        scale, _navigation = self.scale(days="1", **{"from": "2027-03-10"})
        ((shown, bars),) = services.project_timeline(_all(), scale)
        self.assertEqual(shown, project)
        self.assertEqual(
            [(bar.first, bar.last, bar.css) for bar in bars], [(57, 60, "status-confirmed"), (56, 56, "phase")]
        )
        # A plain list of days still means day columns.
        ((_shown, day_bars),) = services.project_timeline(_all(), services.day_range(at(8).date(), 7))
        self.assertEqual((day_bars[0].first, day_bars[0].last), (3, 3))


class PersonnelPlanTests(RentalarsTestCase):
    """VFG-023: availability on top, conspicuous warnings, only people who can be planned."""

    def test_warnings_compare_real_times(self) -> None:
        def period(start: datetime.datetime, end: datetime.datetime) -> Absence:
            return Absence(start=start, end=end)

        morning, evening = period(at(10, 8), at(10, 12)), period(at(10, 18), at(10, 22))
        self.assertEqual(services.find_warnings([morning, evening], [], []), ([], set()))
        touching = period(at(10, 12), at(10, 14))
        self.assertEqual(services.find_warnings([morning, touching], [], [])[0], [])
        overlapping = period(at(10, 11), at(10, 13))
        codes, involved = services.find_warnings([morning, overlapping, evening], [], [])
        self.assertEqual(codes, ["double_booking"])
        self.assertEqual(involved, {id(morning), id(overlapping)})
        away, blocked = period(at(10, 20), at(11)), period(at(10), at(10, 9))
        codes, involved = services.find_warnings([morning, evening], [away], [blocked])
        self.assertEqual(codes, ["absence", "unavailable"])
        self.assertEqual(involved, {id(morning), id(evening), id(away), id(blocked)})

    def test_rows_with_availability_deployments_and_warnings(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest"), "Tontechnik", anna, start=at(10, 8), end=at(10, 18))
        plan(make_project("Weinfest"), "Tontechnik", anna, start=at(11, 9), end=at(11, 12))
        AvailabilityMark.objects.create(person=anna, start=at(8), end=at(10), state="available")
        AvailabilityMark.objects.create(person=anna, start=at(11), end=at(12), state="unavailable", source="feed")
        AvailabilityMark.objects.create(person=anna, start=at(12), end=at(13), state="limited", note="nur abends")
        Absence.objects.create(person=anna, kind="vacation", start=at(13), end=at(15))
        days = services.day_range(at(8).date(), 7)
        with self.assertNumQueries(4):
            (row,) = services.personnel_rows(Person.objects.filter(pk=anna.pk), Scale(days=days))
        # VFG-027: "crew" gives the bars the colours of the legend of the deployments.
        self.assertEqual([bar.css for bar in row.bars], ["crew status-confirmed", "crew status-confirmed is-conflict"])
        self.assertEqual(
            [(bar.label, bar.css) for bar in row.availability],
            [
                ("verfügbar", "availability is-available"),
                ("nicht verfügbar", "availability is-unavailable from-feed is-conflict"),
                ("eingeschränkt verfügbar", "availability is-limited"),
                ("Urlaub", "absence"),
            ],
        )
        # VFG-032: the title names the exact times, and "conflict" where the bar takes part.
        self.assertEqual(row.availability[1].title, "Do 11.03., ganztägig · aus dem verknüpften Kalender · Konflikt")
        self.assertEqual(row.availability[2].title, "Fr 12.03., ganztägig · nur abends")
        self.assertEqual(row.warnings, ["unavailable"])
        self.assertTrue(row.conflict)
        self.assertEqual(row.warning_text, "Eingeplant, obwohl als nicht verfügbar markiert")

    def test_every_active_person_is_in_the_plan(self) -> None:
        """VFG-023, fix: without "only people with deployments or absences" everybody is in the plan."""
        crew = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        office = make_user("buero").person  # every account is a person (AUT-026), without a job function
        deployed = make_person("Ben Schmidt")  # planned outside any job function, with the right to do so
        plan(make_project("Stadtfest"), "Stagehand", deployed, start=at(10, 8), end=at(10, 18))
        elsewhere = make_person("Carla Wolf")
        plan(make_project("Sommerfest", start=at(10, month=7), end=at(11, month=7)), "Stagehand", elsewhere)
        cancelled = make_person("Dora Klein")
        plan(make_project("Abgesagt", status=ProjectStatus.CANCELLED), "Stagehand", cancelled)
        start, end = services.bounds(services.day_range(at(8).date(), 14))
        shown = set(services.people_in_plan(Person.objects.all(), start, end))
        self.assertTrue({crew, office, deployed, elsewhere, cancelled} <= shown)
        busy = set(services.people_in_plan(Person.objects.all(), start, end, busy_only=True))
        self.assertIn(deployed, busy)
        self.assertNotIn(office, busy)
        self.assertNotIn(elsewhere, busy)

    def test_rows_in_hour_columns(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest"), "Tontechnik", anna, start=at(10, 8), end=at(10, 18))
        plan(make_project("Weinfest"), "Tontechnik", anna, start=at(10, 18), end=at(10, 22))
        scale = Scale(days=services.day_range(at(9).date(), 3), hours=1, focus=24, visible=24)
        (row,) = services.personnel_rows(Person.objects.filter(pk=anna.pk), scale)
        self.assertEqual([(bar.first, bar.last) for bar in row.bars], [(33, 42), (43, 46)])
        self.assertFalse(row.conflict)  # one ends when the other begins
