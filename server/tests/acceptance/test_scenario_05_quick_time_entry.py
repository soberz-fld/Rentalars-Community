# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 5 – Schnelle Zeiterfassung (catalogue chapter 11).

The scenario is told through the pages, as a person on a phone goes through
it. That the quick entry really opens as a dialog on a 360 pixel wide screen
is checked with a real browser in ``tests/browser/test_time_in_browser.py``.
"""

import datetime

from django.urls import reverse

from rentalars.timetracking.models import TimeEntry
from tests.helpers import NOW, job_function, make_internal_project, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase, form_data


class Scenario05QuickTimeEntry(UiTestCase):
    """ZEI-003 to ZEI-006, ZEI-009."""

    def setUp(self) -> None:
        super().setUp()
        self.sound = job_function("Tontechnik", price="45.00")
        self.user = make_user("anna", roles=("Crew",))
        self.person = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"}, user=self.user)
        # Today's project: the deployment began this morning.
        self.project = make_project(
            "Stadtfest", start=NOW - datetime.timedelta(hours=2), end=NOW + datetime.timedelta(days=1)
        )
        plan(self.project, self.sound, self.person)
        make_internal_project("Lager")
        self.phone = self.browser_of(self.user)
        self.quick = reverse("timetracking:quick")

    def test_time_tracking_is_one_tap_away_on_every_page(self) -> None:
        """ZEI-003."""
        for name in ("core:home", "projects:list", "timetracking:my_times", "accounts:account"):
            page = self.assert_ok(self.phone.get(reverse(name)))
            self.assertIn(f'hx-get="{self.quick}" hx-target="#dialog"', page, name)

    def test_todays_project_and_its_job_function_are_prefilled(self) -> None:
        """ZEI-006."""
        dialog = self.assert_ok(self.htmx("get", self.quick, client=self.phone))
        self.assertIn(f'<option value="{self.project.pk}" selected>', dialog)
        self.assertLess(dialog.index("Gerade eingeplant"), dialog.index("Intern"))
        self.assertRegex(dialog, rf'<option value="{self.sound.pk}" selected[^>]*>Tontechnik</option>')
        self.assertIn('value="2027-03-01"', dialog)  # today

    def test_begin_and_end_are_typed_and_saved_without_leaving_the_page(self) -> None:
        dialog = self.htmx("get", self.quick, client=self.phone)
        saved = self.htmx("post", self.quick, form_data(dialog, begin="06:00", end="08:00"), client=self.phone)
        # The answer is the confirmation inside the same dialog – no redirect, no other page.
        text = self.assert_ok(saved)
        self.assertIn("Zeit erfasst", text)
        self.assertIn("2 Std.", text)
        self.assertNotIn("<html", text)
        self.assertEqual(saved["HX-Trigger"], "timesChanged")

        entry = TimeEntry.objects.get()
        self.assertEqual((entry.person, entry.project, entry.job_function), (self.person, self.project, self.sound))
        self.assertEqual((entry.hours, entry.hourly_rate, entry.status), (2, 35, "submitted"))

    def test_a_second_entry_with_overlapping_time_is_refused(self) -> None:
        """ZEI-009."""
        dialog = self.htmx("get", self.quick, client=self.phone)
        self.htmx("post", self.quick, form_data(dialog, begin="06:00", end="08:00"), client=self.phone)
        dialog = self.htmx("get", self.quick, client=self.phone)
        refused = self.htmx("post", self.quick, form_data(dialog, begin="07:30", end="07:55"), client=self.phone)
        text = self.assert_ok(refused)
        self.assertIn("überschneidet sich mit dem Eintrag von 01.03. 06:00 bis 08:00", text)
        self.assertIn('value="07:30"', text)  # what was typed is still there
        self.assertEqual(TimeEntry.objects.count(), 1)

    def test_the_stopwatch_does_the_same_with_two_taps(self) -> None:
        """ZEI-005."""
        dialog = self.htmx("get", self.quick, client=self.phone)
        running = self.htmx("post", reverse("timetracking:timer_start"), form_data(dialog), client=self.phone)
        self.assertIn("Stoppuhr läuft", self.assert_ok(running))
        TimeEntry.objects.update(start=NOW - datetime.timedelta(hours=1, minutes=30))
        stopped = self.htmx("post", reverse("timetracking:timer_stop"), form_data(running), client=self.phone)
        self.assertIn("Zeit erfasst", self.assert_ok(stopped))
        self.assertEqual(TimeEntry.objects.get().hours, 1.5)
