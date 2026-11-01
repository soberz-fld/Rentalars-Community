# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 11 – Leistung auf dem Referenzsystem (catalogue chapter 11).

The scenario is proven in two ways:

* This test runs with every test run. It uses the project of the scenario in
  full size (500 lines in 20 groups) inside a smaller installation, and
  checks the two limits – and, more robust than any stopwatch, that the
  number of database queries does not grow with the number of lines. The
  stopwatch takes the fastest of three runs: the test is to notice code that
  has become slow, not a machine that was busy for a moment.
* On the reference system the full amount of data (100 users, 20,000 items,
  1,000 projects) is created with ``manage.py create_load_test_data`` and
  measured with ``manage.py measure_performance`` against MariaDB – or both
  in one step with ``measure_performance --create-test-data`` (NFA-044). The
  measured values are recorded in ``docs/betrieb/betrieb.md``.

The memory limit of the scenario (under 4 GB) concerns the whole server and
is checked on the reference system; here only the test process is watched.
"""

import gc
import itertools
import resource
import sys

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.accounts.models import User
from rentalars.core.loadtest import (
    BIG_PROJECT_NAME,
    FAMILY_PAGES,
    FESTIVAL_NUMBER,
    INSPECTED_CATEGORY_CODES,
    OWN_PAGES,
    USUAL_PAGES,
    LoadTestSize,
    create_load_test_data,
    measure,
    page_path,
)
from rentalars.core.warmup import set_startup_objects_aside, warm_up
from rentalars.material.inspections import InspectionPlan
from rentalars.material.models import MaterialItem
from rentalars.personnel.models import Person
from rentalars.projects.models import CrewLine, MaterialLine, Project
from rentalars.projects.planning import build_planning
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus
from tests.helpers import RentalarsTestCase, make_customer, make_user

#: The big project in full size; the rest of the installation reduced to keep the test short.
SIZE = LoadTestSize(users=10, items=4_000, projects=100, time_entries=2_000)


class Scenario11Performance(RentalarsTestCase):
    """NFA-012 to NFA-014 on the amount of data of catalogue 3.2.

    NFA-039 ties these limits to the reference system (4 cores, 8 GB, two
    users at the same time). No test run can prove that for another machine;
    what was measured where is recorded in ``docs/betrieb/betrieb.md``.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.created = create_load_test_data(SIZE)
        cls.project = Project.objects.get(name=BIG_PROJECT_NAME)
        cls.admin_user = make_user("admin", superuser=True)
        # Prepare this process the way the application server prepares itself
        # (rentalars/wsgi.py). Without it the stopwatch would now and then
        # catch Python looking through everything the test run has loaded so
        # far – a pause of a tenth of a second and more that a server does
        # not have (see rentalars/core/warmup.py).
        warm_up()
        set_startup_objects_aside()
        cls.addClassCleanup(gc.unfreeze)

    def test_test_data_has_the_size_of_the_scenario(self) -> None:
        self.assertEqual(MaterialLine.objects.filter(project=self.project).count(), 500)
        self.assertEqual(self.project.groups.count(), 20)
        self.assertEqual(MaterialItem.objects.count(), SIZE.items)
        # Stage 6: and a festival – a whole project with three stages (PRJ-044).
        self.assertEqual(Project.objects.count(), SIZE.projects + 1 + 4)
        festival = Project.objects.get(number=FESTIVAL_NUMBER)
        self.assertEqual(festival.subprojects.count(), 3)
        self.assertEqual(
            MaterialLine.objects.filter(project__parent=festival, taken_over_from__isnull=False).count(), 60
        )
        full = LoadTestSize()
        self.assertEqual((full.users, full.items, full.projects), (100, 20_000, 1_000))
        self.assertEqual((full.big_project_lines, full.big_project_groups), (500, 20))
        # Stage 3: a person for every account, crew in every project, a year of time entries.
        # AUT-026: the administrator of the test is a person too.
        self.assertEqual(Person.objects.exclude(user=self.admin_user).count(), SIZE.users)
        self.assertEqual(self.project.crew_lines.count(), 20)
        self.assertEqual(CrewLine.objects.count(), SIZE.projects * 3 + 20)
        self.assertEqual(TimeEntry.objects.count(), SIZE.time_entries)
        self.assertEqual(TimeEntry.objects.filter(status=TimeEntryStatus.SUBMITTED).count(), SIZE.time_entries // 100)
        self.assertEqual(full.time_entries, 20_000)
        # Stage 5: every item has its place; the items of two main categories have inspections, some overdue.
        self.assertEqual(self.created["storage_places"], 200)
        self.assertFalse(MaterialItem.objects.filter(storage_location__isnull=True).exists())
        inspected = MaterialItem.objects.filter(material_model__category__code__in=INSPECTED_CATEGORY_CODES).count()
        self.assertTrue(0.85 * inspected < self.created["inspections"] < 0.95 * inspected)
        # Some overdue, most not; how many depends on the day the test runs.
        overdue = InspectionPlan().overdue_ids(MaterialItem.objects.values_list("pk", flat=True))
        self.assertTrue(0.05 * inspected < len(overdue) < 0.75 * inspected, len(overdue))

    def test_no_time_entries_of_one_person_overlap(self) -> None:
        """ZEI-011 holds in the generated data as well; otherwise the pages would show conflicts."""
        for person in Person.objects.filter(user__isnull=False):
            spans = sorted(TimeEntry.objects.filter(person=person).values_list("start", "end"))
            for (_start, end), (next_start, _end) in itertools.pairwise(spans):
                self.assertLessEqual(end, next_start)

    def setUp(self) -> None:
        super().setUp()
        if sys.gettrace() is not None:
            # A coverage tool or debugger slows every line down several times
            # over. The stopwatch tests would then measure the tool.
            self.stopwatch_is_meaningful = False
        else:
            self.stopwatch_is_meaningful = True

    def test_project_with_500_lines_opens_in_under_a_second(self) -> None:
        if not self.stopwatch_is_meaningful:
            self.skipTest("times are not meaningful while the code is traced")
        timings = {timing.label: timing for timing in measure(repeat=3, host="testserver", keep="fastest")}
        page = timings["Open the project with 500 lines in 20 groups (browser page)"]
        self.assertLess(page.seconds, 1.0)
        api = timings["Read the same project through the API (planning)"]
        self.assertLess(api.seconds, 1.0)

    def test_adding_a_line_with_availability_check_answers_in_under_half_a_second(self) -> None:
        if not self.stopwatch_is_meaningful:
            self.skipTest("times are not meaningful while the code is traced")
        timings = {timing.label: timing for timing in measure(repeat=3, host="testserver", keep="fastest")}
        service = timings["Add a line including the availability check (service)"]
        self.assertLess(service.seconds, 0.5)
        browser = timings["Add a line in the browser (answer with the refreshed planning)"]
        self.assertLess(browser.seconds, 0.5)
        # The measurement cleans up after itself.
        self.assertEqual(MaterialLine.objects.filter(project=self.project).count(), 500)

    def test_usual_pages_answer_in_under_a_second(self) -> None:
        """NFA-012: lists, overviews and API calls."""
        if not self.stopwatch_is_meaningful:
            self.skipTest("times are not meaningful while the code is traced")
        timings = [
            timing
            for timing in measure(repeat=3, host="testserver", keep="fastest")
            if timing.label in dict(USUAL_PAGES + FAMILY_PAGES)
        ]
        self.assertEqual(len(timings), len(USUAL_PAGES) + len(FAMILY_PAGES))
        for timing in timings:
            with self.subTest(page=timing.label):
                self.assertLess(timing.seconds, 1.0)

    def test_usual_pages_need_a_bounded_number_of_queries(self) -> None:
        """More robust than a stopwatch: no page asks the database once per row or per project.

        The limits have room for a few more queries, but not for one per
        row: a list page shows 50 rows, the installation of this test has
        100 projects and 4,000 items. One (LOG-001) is the vehicle
        bookings of a project, for its prices and for "Verladen in" on the
        packing list.
        """
        self.client.force_login(self.admin_user)
        for label, path in USUAL_PAGES:
            with self.subTest(page=label), CaptureQueriesContext(connection) as queries:
                response = self.client.get(page_path(path, self.project))
                self.assertEqual(response.status_code, 200)
            # PRD-052: +1 – the further wished items of all lines, read at once (not per line).
            self.assertLess(len(queries), 47, f"{label}: {len(queries)} queries")

    def test_pages_of_a_whole_project_need_queries_per_part_not_per_line(self) -> None:
        """PRJ-046, PRJ-048: the pages of a whole project look at every part, but at no line one by one."""
        self.client.force_login(self.admin_user)
        for label, path in FAMILY_PAGES:
            with self.subTest(page=label), CaptureQueriesContext(connection) as queries:
                response = self.client.get(page_path(path, self.project))
                self.assertEqual(response.status_code, 200)
            # The whole project and three parts: at most 45 queries for each of the four.
            self.assertLess(len(queries), 4 * 45, f"{label}: {len(queries)} queries")

    def test_pages_of_the_crew_need_a_bounded_number_of_queries(self) -> None:
        """What a person of the crew opens, as one of the generated people with a year of times."""
        self.client.force_login(User.objects.get(username="lasttest001"))
        for label, path in OWN_PAGES:
            with self.subTest(page=label), CaptureQueriesContext(connection) as queries:
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
            self.assertLess(len(queries), 45, f"{label}: {len(queries)} queries")

    def test_pages_of_the_crew_answer_in_under_a_second(self) -> None:
        if not self.stopwatch_is_meaningful:
            self.skipTest("times are not meaningful while the code is traced")
        timings = [
            timing for timing in measure(repeat=3, host="testserver", keep="fastest") if timing.label in dict(OWN_PAGES)
        ]
        self.assertEqual(len(timings), len(OWN_PAGES))
        for timing in timings:
            with self.subTest(page=timing.label):
                self.assertLess(timing.seconds, 1.0)

    def test_number_of_queries_does_not_grow_with_the_number_of_lines(self) -> None:
        """NFA-014: 500 lines need as many queries as 100 lines."""
        with CaptureQueriesContext(connection) as large:
            build_planning(self.project)
        keep = list(MaterialLine.objects.filter(project=self.project).values_list("pk", flat=True)[:100])
        MaterialLine.objects.filter(project=self.project).exclude(pk__in=keep).delete()
        with CaptureQueriesContext(connection) as small:
            build_planning(self.project)

        self.assertEqual(len(large), len(small))
        self.assertLess(len(large), 30)

    def test_page_itself_needs_a_bounded_number_of_queries(self) -> None:
        self.client.force_login(self.admin_user)
        url = reverse("projects:detail", args=[self.project.pk])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # A fixed number, whatever the size of the project. Stage 5 added two lookups of the
        # availability calculation: blocked items (MAT-024) and extracted contents (MAT-042).
        # Added the project number in the address (UIX-024, one lookup), the availability
        # marks of the crew (PER-021) and the access log, which writes the first read of a
        # record (AUT-028: a lookup and an insert; repeated reads within minutes cost nothing).
        # Added the block "Logistik" (LOG-001): the project's vehicle bookings and the vehicles to book.
        # PRD-052: the further wished items of the lines are read in one query for all lines.
        self.assertLess(len(queries), 50)

    def test_memory_of_the_process_stays_far_below_the_limit(self) -> None:
        build_planning(self.project)
        peak_megabytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        self.assertLess(peak_megabytes, 1024)

    def test_load_test_data_refuses_to_mix_with_real_data(self) -> None:
        make_customer("Echter Kunde")
        with self.assertRaises(ValidationError):
            create_load_test_data(SIZE)
