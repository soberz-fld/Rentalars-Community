# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: a new phase from the crew planning (PRJ-094), and the phases of the sample project (PRJ-092)."""

from __future__ import annotations

from unittest import SkipTest

from django.utils import timezone

from rentalars.personnel.models import JobFunction
from rentalars.projects.models import CrewLine, ProjectPhase
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class NewPhaseFromTheCrewPlanningTests(BrowserTestCase):
    """PRJ-094: "Neue Phase …" in the list of phases – in the form below the crew and in the dialog of a line."""

    def setUp(self) -> None:
        super().setUp()
        self.hand = JobFunction.objects.get(name="Stagehand")
        self.day = timezone.localtime(self.project.start).strftime("%Y-%m-%d")

    def fill_phase_dialog(self, kind: str, title: str, start: str, end: str) -> None:
        dialog = self.page.locator("dialog#phase-dialog[open]")
        dialog.wait_for()
        dialog.locator("select[name=kind]").select_option(kind)
        dialog.locator("input[name=title]").fill(title)
        dialog.locator("input[name=start]").fill(f"{self.day}T{start}")
        dialog.locator("input[name=end]").fill(f"{self.day}T{end}")
        # PRJ-120: the dialog has rows "Funktion + Plätze" with buttons of their own: "Phase speichern" is in the foot.
        dialog.locator(".dialog-foot button[type=submit]").click()
        dialog.wait_for(state="detached")

    def test_from_the_form_below_the_crew(self) -> None:
        self.open_planning()
        form = self.page.locator("form.crew-add")
        phases = form.locator("select[name=phase]")
        self.assertEqual(phases.locator("option").last.inner_text(), "Neue Phase …")
        form.locator("select[name=job_function]").select_option(str(self.hand.pk))
        form.locator("input[name=count]").fill("2")
        phases.select_option("new")
        self.page.locator("dialog#phase-dialog[open]").wait_for()
        # The list keeps its former choice while the dialog is open: the entry is never sent.
        self.assertEqual(phases.input_value(), "")
        self.fill_phase_dialog("planning", "Technikbesprechung", "07:00", "07:45")

        phase = ProjectPhase.objects.get(project=self.project, title="Technikbesprechung")
        self.assertEqual(phases.input_value(), str(phase.pk))
        self.assertIn("Technikbesprechung", phases.locator("option:checked").inner_text())
        self.assertEqual(self.page.evaluate("document.activeElement.name"), "phase")
        # What was typed stays; the period is the phase's, as with any phase chosen.
        self.assertEqual(form.locator("select[name=job_function]").input_value(), str(self.hand.pk))
        self.assertEqual(form.locator("input[name=count]").input_value(), "2")
        self.assertEqual(form.locator("input[name=start]").input_value(), f"{self.day}T07:00")
        self.assertEqual(form.locator("input[name=end]").input_value(), f"{self.day}T07:45")
        # In the order of time: before the phases of the day that start later; the entry stays last.
        labels = phases.locator("option").all_inner_texts()
        self.assertEqual(labels[-1], "Neue Phase …")
        self.assertLess(
            labels.index(phases.locator("option:checked").inner_text()),
            labels.index(next(label for label in labels if label.startswith("Packen"))),
        )

        form.locator("button[type=submit]").click()
        self.settle()
        self.assertEqual(CrewLine.objects.filter(phase=phase, job_function=self.hand).count(), 2)
        self.assertIn("Phase: Technikbesprechung", self.text_of("#planning-crew"))

    def test_from_the_dialog_of_a_crew_line(self) -> None:
        line = CrewLine.objects.filter(project=self.project, person__isnull=True).first()
        self.open_planning()
        self.page.locator(
            f'#planning-crew tr[data-crew-line="{line.pk}"] button[aria-label="Personalposition bearbeiten"]'
        ).click()
        crew_dialog = self.page.locator("dialog#dialog[open]")
        crew_dialog.wait_for()
        crew_dialog.locator("input[name=meeting_point]").fill("Lager, Tor 2")
        phases = crew_dialog.locator("select[name=phase]")

        # Escape closes the new dialog only, and the focus is back on the list.
        phases.select_option("new")
        self.page.locator("dialog#phase-dialog[open]").wait_for()
        self.page.keyboard.press("Escape")
        self.page.locator("dialog#phase-dialog[open]").wait_for(state="detached")
        self.assertEqual(crew_dialog.count(), 1)
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "id_phase")
        self.assertEqual(phases.input_value(), str(line.phase_id or ""))

        # "Abbrechen" as well.
        phases.select_option("new")
        self.page.locator("dialog#phase-dialog[open]").locator("button", has_text="Abbrechen").click()
        self.page.locator("dialog#phase-dialog[open]").wait_for(state="detached")
        self.assertEqual(crew_dialog.count(), 1)

        phases.select_option("new")
        self.fill_phase_dialog("aftercare", "Kabel prüfen", "16:00", "18:00")
        phase = ProjectPhase.objects.get(project=self.project, title="Kabel prüfen")
        self.assertEqual(crew_dialog.count(), 1)
        self.assertEqual(phases.input_value(), str(phase.pk))
        self.assertEqual(crew_dialog.locator("input[name=meeting_point]").input_value(), "Lager, Tor 2")
        # The list below the crew knows the new phase as well.
        self.assertEqual(self.page.locator(f'form.crew-add select[name=phase] option[value="{phase.pk}"]').count(), 1)

        crew_dialog.locator("button[type=submit]").click()
        self.settle()
        line.refresh_from_db()
        self.assertEqual(
            (line.phase, line.meeting_point, line.start, line.end), (phase, "Lager, Tor 2", phase.start, phase.end)
        )

    def test_with_the_keyboard(self) -> None:
        """Reaching the entry with the arrow keys only selects it; Enter opens the dialog, leaving puts the old back."""
        self.open_planning()
        phases = self.page.locator("form.crew-add select[name=phase]")
        phases.focus()
        self.page.keyboard.press("End")
        self.assertEqual(phases.input_value(), "new")
        self.assertEqual(self.page.locator("dialog#phase-dialog[open]").count(), 0)
        self.page.keyboard.press("Tab")
        self.assertEqual(phases.input_value(), "")

        phases.focus()
        self.page.keyboard.press("End")
        self.page.keyboard.press("Enter")
        dialog = self.page.locator("dialog#phase-dialog[open]")
        dialog.wait_for()
        self.assertEqual(self.page.evaluate("document.activeElement.name"), "kind")
        self.page.keyboard.press("Escape")
        dialog.wait_for(state="detached")
        self.assertEqual(self.page.evaluate("document.activeElement.name"), "phase")
        self.assertEqual(phases.input_value(), "")

    def test_a_mistake_stays_in_the_dialog(self) -> None:
        self.open_planning()
        self.page.locator("form.crew-add select[name=phase]").select_option("new")
        dialog = self.page.locator("dialog#phase-dialog[open]")
        dialog.wait_for()
        dialog.locator("input[name=start]").fill(f"{self.day}T18:00")
        dialog.locator("input[name=end]").evaluate("(field, value) => { field.value = value; }", f"{self.day}T08:00")
        dialog.locator(".dialog-foot button[type=submit]").click()
        dialog.locator(".has-error").first.wait_for()
        self.assertEqual(self.page.locator("dialog#phase-dialog[open]").count(), 1)
        self.assertEqual(ProjectPhase.objects.filter(project=self.project).count(), 6)


class PhasesOfTheSampleProjectTests(BrowserTestCase):
    """PRJ-092: the sample project's course with the new kinds, on the page "Zeitplanung"."""

    def test_the_course_from_the_site_visit_to_the_follow_up_work(self) -> None:
        self.open(f"/projects/{self.project.pk}/course/")
        text = self.text_of("table.phases")
        self.assertLess(text.index("Ortsbegehung mit dem Kulturamt"), text.index("Packen"))
        self.assertLess(text.index("Packen"), text.index("Nachbereitung"))
        self.assertIn("Planungen und Besprechungen", text)


class AccessibilityOfTheNewPhaseTests(BrowserTestCase):
    """NFA-025 with axe-core: the planning with the dialog for a new phase over the dialog of a crew line."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def run_axe(self) -> list[str]:
        self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def test_no_findings(self) -> None:
        self.open_planning()
        self.page.locator("form.crew-add select[name=phase]").select_option("new")
        self.page.locator("dialog#phase-dialog[open]").wait_for()
        findings = [f"new phase from the form: {finding}" for finding in self.run_axe()]
        self.page.keyboard.press("Escape")
        line = CrewLine.objects.filter(project=self.project).first()
        self.page.locator(
            f'#planning-crew tr[data-crew-line="{line.pk}"] button[aria-label="Personalposition bearbeiten"]'
        ).click()
        self.page.locator("dialog#dialog[open]").wait_for()
        self.page.locator("dialog#dialog select[name=phase]").select_option("new")
        self.page.locator("dialog#phase-dialog[open]").wait_for()
        findings += [f"new phase over a crew line: {finding}" for finding in self.run_axe()]
        self.assertEqual(findings, [], "\n".join(findings))
