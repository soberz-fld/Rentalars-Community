# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: a phase brings its period, and personnel is planned per phase (PRJ-080)."""

from __future__ import annotations

from django.utils import timezone

from rentalars.projects import course
from rentalars.projects.models import CrewLine
from tests.browser.base import BrowserTestCase
from tests.helpers import job_function


class CrewPerPhaseInBrowserTests(BrowserTestCase):
    def setUp(self) -> None:
        super().setUp()
        start = timezone.localtime(self.project.start).replace(hour=9, minute=0)
        self.phase = course.add_phase(
            self.project, kind="setup", title="Aufbau Bühne", start=start, end=start.replace(hour=17)
        )
        self.function = job_function("Stagehand", price="28.00")
        self.start_text = start.strftime("%Y-%m-%dT%H:%M")
        self.end_text = start.replace(hour=17).strftime("%Y-%m-%dT%H:%M")

    def test_choosing_a_phase_fills_in_its_period(self) -> None:
        self.open_planning()
        form = self.page.locator("form.crew-add")
        form.locator("select[name=phase]").select_option(str(self.phase.pk))
        self.assertEqual(form.locator("input[name=start]").input_value(), self.start_text)
        self.assertEqual(form.locator("input[name=end]").input_value(), self.end_text)
        form.locator("select[name=job_function]").select_option(str(self.function.pk))
        form.locator("button[type=submit]").click()
        self.settle()
        self.assertIn("Phase: Aufbau Bühne", self.text_of("#planning-crew"))
        line = CrewLine.objects.get(project=self.project, phase=self.phase)
        self.assertEqual((line.job_function, line.start, line.end), (self.function, self.phase.start, self.phase.end))

    def test_personnel_for_a_phase_from_the_schedule(self) -> None:
        self.open(f"/projects/{self.project.pk}/course/")
        self.page.locator(f"tbody[data-phase='{self.phase.pk}'] a", has_text="Personal für diese Phase").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        # PRJ-120: the job function with its places first; the lines get the period of the phase.
        dialog.locator("select[name=function_0]").select_option(str(self.function.pk))
        dialog.locator("input[name=places_0]").fill("2")
        dialog.locator("button[name=save]").click()
        # PRJ-120: back to the phases (as after a change of a crew line there, PRJ-110).
        self.page.wait_for_url(f"{self.live_server_url}/projects/{self.project.number}/course/#phases")
        self.page.wait_for_load_state("networkidle")
        crew = self.text_of(f"tbody[data-phase='{self.phase.pk}']")
        self.assertEqual(crew.count("Stagehand"), 2)
        self.assertEqual(CrewLine.objects.filter(phase=self.phase).count(), 2)
