# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: persons dragged on the timeline of "Zeitplanung", their phase following (PRJ-121); personnel
for a phase by job function (PRJ-120) – with axe-core on the timeline and the dialogs.

The requirement: on the timeline of "Zeitplanung" dragging works in the general period and for the phases, and also in
the area of the persons; when the person is changed and is the only person of the function or phase, the function or
phase changes with them.
"""

from __future__ import annotations

from rentalars.projects import course
from rentalars.projects.models import CrewLine, PhaseKind, ProjectPhase
from tests.browser.base import BrowserTestCase
from tests.browser.test_071_planning_in_browser import AxeMixin
from tests.helpers import at, job_function, make_person, make_project, plan

#: Pixels of the row of a bar for so many minutes, measured in the page (the columns follow the window).
PIXELS = """([key, minutes]) => {
  const bar = document.querySelector(`[data-tl-key="${key}"]`);
  const panel = bar.closest('[data-tl-zoom]');
  const total = Number(panel.dataset.columns) * Number(panel.dataset.hours) * 60;
  return bar.closest('.tl-row').getBoundingClientRect().width / total * minutes;
}"""


class PersonsOnTheTimelineTests(AxeMixin, BrowserTestCase):
    """Drag a person's bar – the phase whose only person they are follows, as the dialog says; or not, unticked."""

    def setUp(self) -> None:
        super().setUp()
        self.feier = make_project("Firmenfeier", start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.feier, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.line = plan(
            self.feier, "Stagehand", make_person("Paul Weber", rates={"Stagehand": "20.00"}), phase=self.phase
        )
        self.course = f"/projects/{self.feier.number}/course/"
        self.key = f"crew-{self.line.pk}"

    def drag(self, key: str, minutes: int) -> None:
        """Press on a bar and move the mouse by so many minutes."""
        bar = self.page.locator(f'[data-tl-key="{key}"]')
        bar.scroll_into_view_if_needed()
        box = bar.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        distance = self.page.evaluate(PIXELS, [key, minutes])
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x + distance / 2, y, steps=4)
        self.page.mouse.move(x + distance, y, steps=4)
        self.assertEqual(self.page.locator(".tl-ghost").count(), 1)
        self.assertIn("Paul Weber", self.text_of(".tl-drag-tip"))
        self.page.mouse.up()
        self.page.locator("#dialog[open] .move-form").wait_for()

    def confirm_and_close(self) -> None:
        """ "Verschieben" in the dialog, then "Schließen" – which loads the page again."""
        self.page.locator("#move-foot button[type=submit]").click()
        self.page.locator("#dialog[open] [role=status]").wait_for()
        with self.page.expect_navigation():
            self.page.locator("#dialog [data-close-dialog]").click()
        self.page.wait_for_load_state("networkidle")

    def test_drag_a_person_and_the_phase_follows(self) -> None:
        self.open(self.course)
        self.assertEqual(self.axe_findings(".course-timeline"), [])
        self.drag(self.key, 62)  # snaps to the hour
        dialog = self.text_of("#dialog")
        self.assertIn("Einsatz von Paul Weber als Stagehand verschieben", dialog)
        self.assertIn("Neu: Mi 10.03. 15:00 – 21:00", dialog)
        self.assertIn("Die Phase „Aufbau“ wird mitverschoben, weil Paul Weber die einzige Person darin ist.", dialog)
        self.assertTrue(self.page.locator("#move-follow").is_checked())
        self.assertEqual(self.axe_findings("#dialog"), [])
        self.confirm_and_close()
        self.phase.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((self.phase.start, self.phase.end), (at(10, 15), at(10, 21)))
        self.assertEqual((self.line.start, self.line.end), (at(10, 15), at(10, 21)))
        # The page shows the new times, and the focus is back on the bar.
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.tlKey"), self.key)
        self.assertEqual(
            self.page.locator(f'[data-tl-key="phase-{self.phase.pk}"]').get_attribute("data-tl-start"),
            "2027-03-10T15:00",
        )

    def test_the_keyboard_way_without_the_phase(self) -> None:
        self.open(self.course)
        bar = self.page.locator(f'[data-tl-key="{self.key}"]')
        bar.focus()
        for _ in range(4):
            self.page.keyboard.press("ArrowRight")
        self.assertIn(
            "Einsatz von Paul Weber als Stagehand: Mi 10.03. 15:00 – 21:00.", self.text_of("[data-tl-announce]")
        )
        self.page.keyboard.press("Enter")
        self.page.locator("#dialog[open] .move-form").wait_for()
        self.page.locator("#move-follow").press("Space")  # only the person
        self.assertFalse(self.page.locator("#move-follow").is_checked())
        self.page.locator("#move-foot button[type=submit]").press("Enter")
        self.page.locator("#dialog[open] [role=status]").wait_for()
        self.assertNotIn("Aufbau: jetzt", self.text_of("#dialog"))
        self.phase.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((self.phase.start, self.line.start), (at(10, 14), at(10, 15)))


class StaffingDialogInBrowserTests(AxeMixin, BrowserTestCase):
    """Personnel for a phase: the places follow the rows at once; the people are found while typing."""

    def setUp(self) -> None:
        super().setUp()
        self.feier = make_project("Firmenfeier", start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.feier, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.hand = job_function("Stagehand", price="20.00")
        self.paul = make_person("Paul Weber", rates={"Stagehand": "20.00"})

    def test_function_places_people(self) -> None:
        self.open(f"/projects/{self.feier.number}/course/")
        self.page.locator(f"tbody[data-phase='{self.phase.pk}'] a", has_text="Personal für diese Phase").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        self.assertEqual(dialog.locator("#staffing-places .staffing-place").count(), 0)
        dialog.locator("select[name=function_0]").select_option(str(self.hand.pk))
        dialog.locator("#staffing-places .staffing-place").first.wait_for()
        self.assertEqual(dialog.locator("#staffing-places .staffing-place").count(), 1)
        places = dialog.locator("input[name=places_0]")
        places.fill("3")
        places.dispatch_event("change")
        self.page.wait_for_function("() => document.querySelectorAll('#staffing-places .staffing-place').length === 3")
        self.assertIn("Stagehand – 3 Plätze", self.text_of("#staffing-places"))
        field = dialog.locator("#staff-person_0_1")
        field.click()
        field.press_sequentially("Weber", delay=20)
        dialog.locator("[role=option]").first.wait_for()
        self.assertIn("kein Konflikt", dialog.locator("[role=option]").first.inner_text())
        field.press("Enter")
        self.assertEqual(self.axe_findings("#dialog"), [])
        with self.page.expect_navigation():
            dialog.locator("button[name=save]").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(CrewLine.objects.filter(phase=self.phase).count(), 3)
        self.assertEqual(CrewLine.objects.get(phase=self.phase, person__isnull=False).person, self.paul)
        self.assertIn("1 Person eingeplant.", self.text_of("main"))


class PlacesOfANewPhaseInBrowserTests(AxeMixin, BrowserTestCase):
    """A phase with places from "Neue Phase …" of the planning: the places show at once; the crew form keeps its values."""

    def test_the_places_show_at_once(self) -> None:
        self.open_planning()
        form = self.page.locator("form.crew-add")
        form.locator("input[name=count]").fill("3")
        form.locator("select[name=phase]").select_option("new")
        dialog = self.page.locator("dialog#phase-dialog[open]")
        dialog.wait_for()
        dialog.locator("select[name=kind]").select_option("teardown")
        dialog.locator("input[name=title]").fill("Abbau Bühne")
        dialog.locator("select[name=function_0]").select_option(label="Stagehand")
        dialog.locator("input[name=places_0]").fill("2")
        self.assertEqual(self.axe_findings("#phase-dialog"), [])
        dialog.locator(".dialog-foot button[type=submit]").click()
        dialog.wait_for(state="detached")
        self.settle()
        phase = ProjectPhase.objects.get(project=self.project, title="Abbau Bühne")
        self.assertEqual(CrewLine.objects.filter(phase=phase, person__isnull=True).count(), 2)
        self.page.wait_for_function(
            "() => document.querySelector('#planning-crew-lines').textContent.includes('Abbau Bühne')"
        )
        # The crew form that opened the dialog keeps what was typed, with the new phase chosen.
        self.assertEqual(form.locator("input[name=count]").input_value(), "3")
        self.assertEqual(form.locator("select[name=phase]").input_value(), str(phase.pk))
