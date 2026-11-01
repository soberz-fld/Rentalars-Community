# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "fixes", in the browser: the quick entry offers job functions on a project without phases and crew
for somebody without job functions of their own (ZEI-007); the page of the surcharges says that only crew lines get
them (PER-009, PER-040); crew packs its own project, with the reason instead of "add material" – axe-core in
both themes, and on a phone without horizontal scrolling (NFA-025).
"""

from __future__ import annotations

import datetime

from rentalars.accounts.models import User
from rentalars.packing import services as packing
from rentalars.packing.models import PackEntry
from rentalars.personnel.models import JobFunction, PersonJobFunction
from rentalars.projects.access import person_of
from rentalars.timetracking.models import TimeEntry
from tests.browser import test_080_projects_in_browser as projects080
from tests.helpers import NOW, PASSWORD, make_person, make_project, make_user, plan


class FixesInBrowserTests(projects080.ProjectsInBrowserTests):
    """The logged-in administrator "anna" records on her own person – which has no job function, as in the report."""

    # The tests of the base class run in their own module; here only these.
    test_a_show_file_picks_its_type_and_console = None  # type: ignore[assignment]
    test_divide_a_project_into_subprojects = None  # type: ignore[assignment]
    test_the_pages_of_the_service_cases = None  # type: ignore[assignment]

    def setUp(self) -> None:
        super().setUp()
        self.person = person_of(User.objects.get(username="anna"))
        PersonJobFunction.objects.filter(person=self.person).delete()
        # A project that runs right now, without phases and without crew lines.
        self.messe = make_project(
            "Messe 084", start=NOW - datetime.timedelta(hours=4), end=NOW + datetime.timedelta(hours=8)
        )

    def phone_findings(self) -> list[str]:
        """The current page at 375 pixels: no horizontal scrolling, and what axe-core finds."""
        self.page.set_viewport_size({"width": 375, "height": 800})
        try:
            self.page.wait_for_load_state("networkidle")
            self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 375)
            return self.axe_findings()
        finally:
            self.page.set_viewport_size(self.viewport)

    def test_a_job_function_can_always_be_chosen(self) -> None:
        """ZEI-007: a job function can always be chosen here and the time can be saved."""
        self.assertIsNotNone(self.person)
        self.assertFalse(self.messe.phases.exists() or self.messe.crew_lines.exists())
        self.open("/")
        self.page.locator(".sidebar-action a").click()
        dialog = self.page.locator("#dialog[open]")
        dialog.wait_for()
        self.page.select_option("#dialog [name=project]", str(self.messe.pk))
        self.settle()
        offered = self.page.locator("#dialog [name=job_function] option").all_inner_texts()
        self.assertEqual(len(offered), JobFunction.objects.filter(is_active=True).count())
        self.assertNotEqual(self.page.input_value("#dialog [name=job_function]"), "")
        self.assertEqual(self.both_themes("#dialog"), [])
        self.page.select_option("#dialog [name=job_function]", label="Tontechniker")
        self.page.fill("#dialog [name=begin]", "05:00")
        self.page.fill("#dialog [name=end]", "07:00")
        self.page.locator("#dialog button[type=submit]", has_text="Zeit speichern").click()
        self.settle()
        self.assertIn("Zeit erfasst", self.text_of("#dialog"))
        entry = TimeEntry.objects.get(project=self.messe)
        self.assertEqual((entry.person, entry.job_function.name), (self.person, "Tontechniker"))

    def test_the_page_of_the_surcharges(self) -> None:
        """PER-009: the lead of the page names the crew lines – and nothing else."""
        self.open("/administration/surcharges/")
        lead = self.text_of("[data-crew-lines-only]")
        self.assertIn("Diese Zuschläge bekommen nur Personalpositionen", lead)
        self.assertIn("nie Material, Nebenkosten oder andere Positionen eines Projekts", lead)
        self.assertIn("Zuschläge im Preis der Personalpositionen", self.text_of("#time-surcharges"))
        self.assertEqual(self.both_themes(), [])
        self.assertEqual(self.phone_findings(), [])

    def test_crew_packs_its_own_project(self) -> None:
        """Crew ticks on the packing list of its project; instead of "add material" the reason is shown."""
        lea = make_user("lea", roles=("Crew",))
        plan(self.project, JobFunction.objects.get(name="Stagehand"), make_person("Lea Vogel", user=lea))
        self.page.context.clear_cookies()
        self.open("/login/")
        self.page.fill("#id_username", "lea")
        self.page.fill("#id_password", PASSWORD)
        self.page.click("button[type=submit]")
        self.page.wait_for_url(f"{self.live_server_url}/")
        self.open(f"/projects/{self.project.pk}/packlist/")
        self.assertIn(
            "Material nachtragen dürfen nur Personen, die das Projekt ändern dürfen oder für alle Projekte packen.",
            self.text_of("[data-no-addendum]"),
        )
        self.assertEqual(self.page.locator("form[action$='add-material/']").count(), 0)
        self.page.locator("#packlist button", has_text="Alle Zeilen abhaken").click()
        self.settle()
        packlist = packing.get_packlist(self.project)
        self.assertTrue(PackEntry.objects.filter(packlist=packlist, packed_quantity__gt=0).exists())
        self.assertEqual(self.both_themes("#packlist"), [])
        self.assertEqual(self.phone_findings(), [])
