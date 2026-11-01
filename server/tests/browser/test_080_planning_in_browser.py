# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: appointments dragged in a timeline with the mouse and moved with the keyboard, confirmed in
a dialog (VFG-026) – with axe-core on the timelines and the dialog; the tab "Dokumente" with invoices switched off
(DOK-014)."""

from __future__ import annotations

from django.urls import reverse

from rentalars.core.models import SystemSettings
from rentalars.projects import course
from rentalars.projects.models import CrewLine, PhaseKind, Project
from tests.browser.base import BrowserTestCase
from tests.browser.test_071_planning_in_browser import AxeMixin
from tests.helpers import at, make_person, make_project, plan

#: Pixels of the row of a bar for so many minutes, measured in the page (the columns follow the window).
PIXELS = """([key, minutes]) => {
  const bar = document.querySelector(`[data-tl-key="${key}"]`);
  const panel = bar.closest('[data-tl-zoom]');
  const total = Number(panel.dataset.columns) * Number(panel.dataset.hours) * 60;
  return bar.closest('.tl-row').getBoundingClientRect().width / total * minutes;
}"""


class MovingInTheTimelineTests(AxeMixin, BrowserTestCase):
    """VFG-026: drag with the mouse, resize at an end, move with the keyboard – the dialog confirms."""

    def setUp(self) -> None:
        super().setUp()
        self.drag_project = make_project("Firmenfeier", start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.drag_project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.line = plan(
            self.drag_project, "Stagehand", make_person("Paul Weber", rates={"Stagehand": "20.00"}), phase=self.phase
        )
        self.timeline = "/schedule/timeline/?days=3&from=2027-03-10"
        self.course = f"/projects/{self.drag_project.number}/course/"

    def drag(self, key: str, minutes: int, *, grip: str = "") -> None:
        """Press on a bar (or one of its ends) and move the mouse by so many minutes."""
        bar = self.page.locator(f'[data-tl-key="{key}"]')
        bar.scroll_into_view_if_needed()
        target = bar.locator(f".tl-grip.{grip}") if grip else bar
        box = target.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        distance = self.page.evaluate(PIXELS, [key, minutes])
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x + distance / 2, y, steps=4)
        self.page.mouse.move(x + distance, y, steps=4)
        self.assertEqual(self.page.locator(".tl-ghost").count(), 1)
        self.assertTrue(self.page.locator(".tl-drag-tip").is_visible())
        self.page.mouse.up()
        self.page.locator("#dialog[open] .move-form").wait_for()

    def confirm_and_close(self) -> None:
        """ "Verschieben" in the dialog, then "Schließen" – which loads the page again."""
        self.page.locator("#move-foot button[type=submit]").click()
        self.page.locator("#dialog[open] [role=status]").wait_for()
        with self.page.expect_navigation():
            self.page.locator("#dialog [data-close-dialog]").click()
        self.page.wait_for_load_state("networkidle")

    def test_drag_a_phase_with_the_mouse(self) -> None:
        self.open(self.timeline)
        self.assertEqual(self.axe_findings(".panel.timeline"), [])
        self.drag(f"phase-{self.phase.pk}", 62)  # snaps to the hour
        dialog = self.text_of("#dialog")
        self.assertIn("Aufbau verschieben", dialog)
        self.assertIn("Bisher: Mi 10.03. 14:00 – 20:00", dialog)
        self.assertIn("Neu: Mi 10.03. 15:00 – 21:00", dialog)
        self.assertIn("Paul Weber (Stagehand): bisher Mi 10.03. 14:00 – 20:00, jetzt Mi 10.03. 15:00 – 21:00", dialog)
        self.assertEqual(self.axe_findings("#dialog"), [])
        self.confirm_and_close()
        self.phase.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((self.phase.start, self.phase.end, self.line.start), (at(10, 15), at(10, 21), at(10, 15)))
        # The page shows the new times, and the focus is back on the bar.
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.tlKey"), f"phase-{self.phase.pk}")
        self.assertEqual(
            self.page.locator(f'[data-tl-key="phase-{self.phase.pk}"]').get_attribute("data-tl-start"),
            "2027-03-10T15:00",
        )

    def test_cancel_puts_the_bar_back(self) -> None:
        self.open(self.timeline)
        self.drag(f"phase-{self.phase.pk}", -90)
        self.assertIn("Neu: Mi 10.03. 12:30 – 18:30", self.text_of("#dialog"))
        self.page.locator("#move-foot [data-close-dialog]").click()
        self.page.locator("#dialog[open]").wait_for(state="detached")
        # The browser fires "close" as a task of its own after the dialog is shut; wait for it.
        self.page.wait_for_function("!document.querySelector('.tl-ghost, .tl-drag-tip, .is-moving')", timeout=5000)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 14))

    def test_a_click_still_opens_the_project(self) -> None:
        self.open(self.timeline)
        with self.page.expect_navigation():
            self.page.locator(f'[data-tl-key="period-{self.drag_project.pk}"] .tl-text').click()
        # the click opens the project's Überblick, the first tab, which is the page ".../deployment/" – adapted.
        self.assertTrue(self.page.url.endswith(f"/projects/{self.drag_project.number}/deployment/"))

    def test_the_end_of_the_rental_period(self) -> None:
        self.open(self.timeline)
        self.drag(f"period-{self.drag_project.pk}", 120, grip="is-end")
        dialog = self.text_of("#dialog")
        self.assertIn("Neu: Mi 10.03. 08:00 – Fr 12.03. 20:00", dialog)
        self.assertIn("Nur der Mietzeitraum ändert sich", dialog)
        self.confirm_and_close()
        project = Project.objects.get(pk=self.drag_project.pk)
        self.assertEqual((project.start, project.end), (at(10, 8), at(12, 20)))
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 14))

    def test_the_keyboard_way(self) -> None:
        self.open(self.course)
        self.assertEqual(self.axe_findings(".course-timeline"), [])
        bar = self.page.locator(f'[data-tl-key="phase-{self.phase.pk}"]')
        bar.focus()
        for _ in range(4):
            self.page.keyboard.press("ArrowRight")
        self.page.keyboard.press("Shift+ArrowRight")
        self.page.keyboard.press("Shift+ArrowRight")
        self.assertEqual(
            self.text_of("[data-tl-announce]"),
            "Aufbau: Mi 10.03. 15:00 – 21:30. Enter zeigt, was dann passiert; Escape nimmt es zurück.",
        )
        # Escape takes it back, nothing is asked.
        self.page.keyboard.press("Escape")
        self.assertEqual(self.page.locator(".tl-ghost").count(), 0)
        self.page.keyboard.press("ArrowLeft")
        self.page.keyboard.press("ArrowLeft")
        self.page.keyboard.press("Enter")
        self.page.locator("#dialog[open] .move-form").wait_for()
        self.assertIn("Neu: Mi 10.03. 13:30 – 19:30", self.text_of("#dialog"))
        # Without the crew: the box is ticked off with the keyboard as well.
        self.page.locator("#move-move_crew").press("Space")
        self.page.locator("#move-foot button[type=submit]").press("Enter")
        self.page.locator("#dialog[open] [role=status]").wait_for()
        self.assertIn("Aufbau: jetzt Mi 10.03. 13:30 – 19:30", self.text_of("#dialog"))
        # The dialog gives "Schließen" the focus once its answer is in place – on a busy machine a moment later.
        self.page.wait_for_function(
            "() => document.activeElement && document.activeElement.textContent.trim() === 'Schließen'"
        )
        with self.page.expect_navigation():
            self.page.keyboard.press("Enter")  # "Schließen" has the focus
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.tlKey"), f"phase-{self.phase.pk}")
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 13, 30))
        self.assertEqual(CrewLine.objects.get(pk=self.line.pk).start, at(10, 14))

    def test_a_click_opens_the_dialog_to_type_the_times(self) -> None:
        self.open(self.course)
        self.page.locator(f'[data-tl-key="phase-{self.phase.pk}"]').click()
        self.page.locator("#dialog[open] .move-form").wait_for()
        submit = self.page.locator("#move-foot button[type=submit]")
        self.assertTrue(submit.is_disabled())
        self.page.locator("#move-end").fill("2027-03-10T22:00")
        self.page.locator("#move-end").dispatch_event("change")
        self.page.wait_for_function("() => !document.querySelector('#move-foot button[type=submit]').disabled")
        self.assertIn("Neu: Mi 10.03. 14:00 – 22:00", self.text_of("#dialog"))
        self.page.evaluate("() => { document.documentElement.dataset.theme = 'light'; }")
        self.page.wait_for_timeout(400)
        self.assertEqual(self.axe_findings("#dialog"), [])
        self.confirm_and_close()
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.end, at(10, 22))

    def test_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.open(self.course)
        self.page.locator(f'[data-tl-key="phase-{self.phase.pk}"]').click()
        self.page.locator("#dialog[open] .move-form").wait_for()
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.assertEqual(self.axe_findings("#dialog"), [])


class InvoicesSwitchedOffTests(AxeMixin, BrowserTestCase):
    """DOK-014: the tab "Dokumente" without invoices, with axe-core."""

    def test_documents_without_invoices(self) -> None:
        settings = SystemSettings.load()
        settings.invoices_enabled = False
        settings.save()
        self.open(f"/projects/{self.project.number}/documents/")
        options = self.page.locator("#id_kind option").all_inner_texts()
        self.assertNotIn("Rechnung", options)
        self.assertIn("Angebot", options)
        self.assertTrue(self.page.locator("[data-invoices-off]").is_visible())
        self.assertEqual(self.axe_findings(), [])
        self.open(reverse("documents:accounting"))
        self.assertTrue(self.page.locator("#invoices-off").is_visible())
        self.assertEqual(self.axe_findings(), [])
