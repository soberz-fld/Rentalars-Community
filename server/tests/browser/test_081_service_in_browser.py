# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "service", in the browser: people taking part in a service case (PRJ-108) – added and taken off on the
page of the case, listed under My area → Servicefälle –, the distance home – company in the personnel form and the
calculation of a trip (ZEI-027), the switch of the hints in the settings (ZEI-018); axe-core on all of them, wide and
on a phone without horizontal scrolling (NFA-025).
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from rentalars.accounts.rights import Rights
from rentalars.personnel.models import Person
from rentalars.projects import service_cases
from rentalars.projects.models import ServiceCaseParticipant
from rentalars.timetracking import expenses
from rentalars.timetracking.models import ExpenseKind
from tests.browser import test_080_projects_in_browser as projects080
from tests.helpers import job_function


class ServiceInBrowserTests(projects080.ProjectsInBrowserTests):
    """Anna of the sample data is the logged-in administrator – and a person (AUT-026)."""

    # The tests of the base class run in their own module; here only these.
    test_a_show_file_picks_its_type_and_console = None  # type: ignore[assignment]
    test_divide_a_project_into_subprojects = None  # type: ignore[assignment]
    test_the_pages_of_the_service_cases = None  # type: ignore[assignment]

    def setUp(self) -> None:
        super().setUp()
        self.anna = Person.objects.get(user__username="anna")
        self.light = job_function("Lichttechnik")
        self.case = service_cases.create_case(name="Spot flackert", case_contact="Herr Meier")

    def on_a_phone(self, path: str) -> list[str]:
        """The page at 375 pixels: no horizontal scrolling, and what axe-core finds."""
        self.page.set_viewport_size({"width": 375, "height": 800})
        try:
            self.open(path)
            self.page.wait_for_load_state("networkidle")
            width = self.page.evaluate("document.scrollingElement.scrollWidth")
            self.assertLessEqual(width, 375, path)
            return self.axe_findings()
        finally:
            self.page.set_viewport_size(self.viewport)

    def test_add_and_take_off_a_person(self) -> None:
        """PRJ-108: the form of the case page, the trash-can button with its question – without finding."""
        self.open(f"/projects/{self.case.number}/case/")
        panel = self.page.locator("#participants")
        self.assertIn("Noch niemand ist beteiligt.", panel.inner_text())
        panel.locator("select[name=person]").select_option(label=self.anna.name)
        panel.locator("select[name=job_function]").select_option(label="Lichttechnik")
        panel.locator("input[name=note]").fill("Ersatzlampe mitnehmen")
        self.assertEqual(self.both_themes("#participants"), [])
        panel.get_by_role("button", name="Person hinzufügen").click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("Ersatzlampe mitnehmen", self.text_of("#participants"))
        self.assertEqual(ServiceCaseParticipant.objects.get().job_function, self.light)
        self.assertEqual(self.both_themes(), [])
        self.page.get_by_role("button", name=f"{self.anna.name} vom Servicefall nehmen").click()
        self.confirm()
        self.page.wait_for_load_state("networkidle")
        self.page.locator("#participants").get_by_text(
            "Noch niemand ist beteiligt."
        ).wait_for()  # the swap takes a moment
        self.assertFalse(ServiceCaseParticipant.objects.exists())
        self.assertEqual(self.on_a_phone(f"/projects/{self.case.number}/case/"), [])

    def test_my_area_lists_the_case(self) -> None:
        """PRJ-108: My area → Servicefälle – a table with columns, CSV and grouping; wide and on a phone."""
        service_cases.add_participant(self.case, self.anna, job_function=self.light, note="Leiter")
        self.open("/me/service-cases/")
        main = self.text_of("main")
        self.assertIn("Spot flackert", main)
        self.assertIn("beteiligt als Lichttechnik", main)
        self.assertEqual(self.both_themes(), [])
        self.page.locator("a", has_text="Servicefälle").first.wait_for()
        self.assertEqual(self.on_a_phone("/me/service-cases/"), [])

    def test_commute_in_the_personnel_form_and_a_trip(self) -> None:
        """ZEI-027: the field in the personnel form; the trip shows "42 km − 28 km Arbeitsweg = 14 km"."""
        self.open(f"/personnel/people/{self.anna.pk}/edit/")
        field = self.page.get_by_label("Entfernung Wohnung – Betrieb (km)")
        field.fill("14")
        self.assertEqual(self.axe_findings("form"), [])
        self.page.get_by_role("button", name="Person speichern").click()
        self.page.wait_for_load_state("networkidle")
        self.anna.refresh_from_db()
        self.assertEqual(self.anna.commute_km, Decimal("14"))
        expenses.create_expense(
            person=self.anna,
            project=self.project,
            kind=ExpenseKind.TRAVEL,
            date=timezone.localdate(),
            kilometres=Decimal("42"),
            rights=Rights.everything(),
            user=None,
        )
        self.open("/times/expenses/")
        self.assertIn("42 km − 28 km Arbeitsweg = 14 km", self.text_of("main"))
        self.assertEqual(self.both_themes(), [])

    def test_the_switches_in_the_settings(self) -> None:
        """ZEI-018, ZEI-027: both switches on the settings page – without finding."""
        self.open("/administration/settings/")
        self.assertTrue(self.page.get_by_label("Hinweise zu Arbeitszeiten anzeigen").is_checked())
        self.assertTrue(self.page.get_by_label("Arbeitsweg von Fahrten abziehen").is_checked())
        self.assertEqual(self.axe_findings("main"), [])
