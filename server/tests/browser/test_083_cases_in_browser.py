# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "cases", in the browser: the further statuses of a service case open the follow-up dialog (PRJ-112),
the rule editor shows the trigger, condition and action of the service cases (ADM-013); axe-core on all of them, wide
and on a phone without horizontal scrolling (NFA-025).
"""

from __future__ import annotations

import datetime

from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, Project
from tests.browser import test_080_projects_in_browser as projects080


class CasesInBrowserTests(projects080.ProjectsInBrowserTests):
    """Anna of the sample data is the logged-in administrator."""

    # The tests of the base class run in their own module; here only these.
    test_a_show_file_picks_its_type_and_console = None  # type: ignore[assignment]
    test_divide_a_project_into_subprojects = None  # type: ignore[assignment]
    test_the_pages_of_the_service_cases = None  # type: ignore[assignment]

    def setUp(self) -> None:
        super().setUp()
        self.case = service_cases.create_case(name="Spot flackert", case_contact="Herr Meier")
        self.case_url = f"/projects/{self.case.number}/case/"

    def phone_findings(self) -> list[str]:
        """The current page at 375 pixels: no horizontal scrolling, and what axe-core finds."""
        self.page.set_viewport_size({"width": 375, "height": 800})
        try:
            self.page.wait_for_load_state("networkidle")
            width = self.page.evaluate("document.scrollingElement.scrollWidth")
            self.assertLessEqual(width, 375)
            return self.axe_findings()
        finally:
            self.page.set_viewport_size(self.viewport)

    def choose_status(self, label: str) -> None:
        """PRJ-112: choosing the status with the mouse opens the follow-up dialog at once – no button."""
        self.page.locator(".case-status-form select").select_option(label=label)

    def test_waiting_to_close_in_the_follow_up_dialog(self) -> None:
        """PRJ-112: the dialog opens over the page; cancelling saves nothing, saving needs day and time."""
        self.open(self.case_url)
        self.choose_status("wartet auf Schließen")
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        self.assertIn("Wiedervorlage", dialog.inner_text())
        self.assertIn("Schließen am", dialog.inner_text())
        self.assertEqual(self.both_themes("dialog#dialog"), [])
        dialog.get_by_role("button", name="Abbrechen").click()
        dialog.wait_for(state="hidden")
        # The list shows the status the case has again.
        self.assertEqual(self.page.locator(".case-status-form select").input_value(), "open")
        self.assertEqual(Project.objects.get(pk=self.case.pk).case_status, CaseStatus.OPEN)

        self.choose_status("wartet auf Schließen")
        dialog.wait_for()
        dialog.locator("input[name=follow_up_on]").fill("2027-03-05")
        dialog.get_by_role("button", name="Auf „wartet auf Schließen“ setzen").click()
        dialog.locator(".field.has-error").first.wait_for()
        self.assertIn("Dieses Feld ist zwingend erforderlich.", dialog.inner_text())  # the time
        dialog.locator("input[name=follow_up_at]").fill("16:00")
        dialog.get_by_role("button", name="Auf „wartet auf Schließen“ setzen").click()
        self.page.get_by_text("Der Servicefall ist jetzt „wartet auf Schließen“.").wait_for()
        self.page.wait_for_load_state("networkidle")
        case = Project.objects.get(pk=self.case.pk)
        self.assertEqual((case.case_status, case.follow_up_at), (CaseStatus.CLOSING, datetime.time(16, 0)))
        self.assertIn("Der Servicefall ist jetzt „wartet auf Schließen“.", self.text_of("main"))
        self.assertEqual(self.both_themes(), [])
        self.assertEqual(self.phone_findings(), [])

    def test_waiting_for_a_delivery_on_a_phone(self) -> None:
        """PRJ-112: the dialog of "waiting" asks what the case waits for – at 375 pixels as well."""
        self.page.set_viewport_size({"width": 375, "height": 800})
        try:
            self.open(self.case_url)
            self.choose_status("wartet")
            dialog = self.page.locator("dialog#dialog[open]")
            dialog.wait_for()
            dialog.locator("select[name=case_waiting_for]").select_option(label="Materiallieferung")
            dialog.locator("input[name=follow_up_on]").fill("2027-03-08")
            width = self.page.evaluate("document.scrollingElement.scrollWidth")
            self.assertLessEqual(width, 375)
            self.assertEqual(self.axe_findings("dialog#dialog"), [])
            dialog.get_by_role("button", name="Auf „wartet“ setzen").click()
            self.page.get_by_text("Der Servicefall ist jetzt „wartet auf Materiallieferung“.").wait_for()
            self.page.wait_for_load_state("networkidle")
        finally:
            self.page.set_viewport_size(self.viewport)
        self.assertIn("wartet auf Materiallieferung", self.text_of("main"))
        self.assertEqual(Project.objects.get(pk=self.case.pk).case_waiting_for, "delivery")

    def test_the_rule_editor(self) -> None:
        """ADM-013: "new communication in a service case" shows status and kind; "set the status" its status."""
        self.open("/administration/automations/new/")
        form = self.page.locator("form[data-automation-form]")
        form.locator("select[name=trigger]").select_option("case_communication")
        self.assertTrue(form.locator("select[name=case_status]").is_visible())
        self.assertTrue(form.locator("select[name=communication]").is_visible())
        self.assertFalse(form.locator("select[name=status]").is_visible())
        form.locator("select[name=action]").select_option("case_status")
        self.assertTrue(form.locator("select[name=new_case_status]").is_visible())
        self.assertEqual(self.both_themes("form"), [])
        form.locator("input[name=name]").fill("Wartet: Antwort öffnet")
        form.locator("select[name=case_status]").select_option("waiting")
        form.locator("select[name=communication]").select_option("mail_in")
        form.locator("select[name=new_case_status]").select_option("open")
        form.get_by_role("button", name="Automation speichern").click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("Wartet: Antwort öffnet", self.text_of("main"))
        self.assertIn("im Status „wartet“", self.text_of("main"))
        self.assertEqual(self.phone_findings(), [])

    def test_keyboard_steps_open_no_dialog_until_enter(self) -> None:
        """PRJ-112: the arrow keys step through the list without a dialog; Enter opens it, leaving the list too."""
        self.open(self.case_url)
        select = self.page.locator(".case-status-form select")
        select.focus()
        for _step in range(3):  # in Arbeit, wartet, wartet auf Schließen
            self.page.keyboard.press("ArrowDown")
        self.page.wait_for_timeout(300)
        self.assertEqual(self.page.locator("dialog#dialog[open]").count(), 0)
        self.assertEqual(select.input_value(), "closing")
        self.page.keyboard.press("Enter")
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        self.assertIn("Schließen am", dialog.inner_text())
        dialog.get_by_role("button", name="Abbrechen").click()
        dialog.wait_for(state="hidden")
        # The list is set back when the dialog's "close" event comes – a moment later on a busy machine.
        self.page.wait_for_function("() => document.querySelector('.case-status-form select').value === 'open'")
        self.assertEqual(select.input_value(), "open")
        # Stepping to "zurückgestellt" and leaving the list with Tab opens it as well.
        select.focus()
        for _step in range(4):
            self.page.keyboard.press("ArrowDown")
        self.page.keyboard.press("Tab")
        dialog.wait_for()
        self.assertIn("Zurückstellen", dialog.inner_text())
        self.assertEqual(self.axe_findings("dialog#dialog"), [])
        dialog.get_by_role("button", name="Abbrechen").click()
        dialog.wait_for(state="hidden")
        # "Status setzen" for a status without follow-up, as before.
        select.select_option(label="in Arbeit")
        self.assertEqual(self.page.locator("dialog#dialog[open]").count(), 0)
        self.page.get_by_role("button", name="Status setzen").click()
        self.page.get_by_text("Der Servicefall ist jetzt „in Arbeit“.").wait_for()
        self.assertEqual(Project.objects.get(pk=self.case.pk).case_status, CaseStatus.IN_PROGRESS)
        self.assertEqual(self.both_themes(), [])
