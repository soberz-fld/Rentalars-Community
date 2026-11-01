# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "project", in the browser – with axe-core: the crew on the timeline of Zeitplanung as in the personnel
plan (VFG-035), an open place of a phase filled in the crew dialog (PRJ-110), a trip changed and removed (PRJ-111),
My area → Meine Einsätze on a phone (UIX-043)."""

from __future__ import annotations

from typing import ClassVar

from django.urls import reverse

from rentalars.accounts.models import User
from rentalars.core.models import CompanyProfile
from rentalars.personnel.models import AvailabilityMark
from rentalars.projects import course
from rentalars.projects.models import CrewLine, PhaseKind, TripAdjustment
from tests.browser.base import BrowserTestCase
from tests.browser.test_071_planning_in_browser import AxeMixin
from tests.helpers import at, make_person, make_project, plan


class ZeitplanungInTheBrowserTests(AxeMixin, BrowserTestCase):
    """VFG-035, PRJ-110, PRJ-111 on the page "Zeitplanung"."""

    viewport: ClassVar[dict[str, int]] = {"width": 1360, "height": 1000}

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.warehouse_address = "Hafenstraße 1, 12345 Musterstadt"
        profile.save()
        self.job = make_project("Firmenfeier", start=at(10, 8), end=at(11, 20), venue="Stadthalle, Marktplatz 1")
        self.setup = course.add_phase(self.job, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16))
        self.paul = make_person("Paul Weber", rates={"Stagehand": "20.00"})
        self.vera = make_person("Vera Lang", rates={"Stagehand": "20.00"})
        self.line = plan(self.job, "Stagehand", self.paul, phase=self.setup)
        self.open_place = plan(self.job, "Stagehand", None, phase=self.setup)
        AvailabilityMark.objects.create(person=self.paul, start=at(10, 12), end=at(10, 14), state="unavailable")
        AvailabilityMark.objects.create(person=self.paul, start=at(11, 8), end=at(11, 12), state="limited")
        self.url = reverse("projects:course", args=[self.job])

    def test_the_crew_as_in_the_personnel_plan(self) -> None:
        """VFG-035: the conflict filled red, the availability hatched, the exact times in the hover."""
        self.open(self.url)
        conflict = self.page.locator(".project-timeline .tl-bar.crew.is-conflict").first
        self.assertIn("Mi 10.03., 8:00 Uhr bis 16:00 Uhr", conflict.get_attribute("title"))
        red = self.page.evaluate(
            "(() => { const s = document.createElement('span'); s.style.color = getComputedStyle("
            "document.documentElement).getPropertyValue('--red'); document.body.append(s);"
            " const c = getComputedStyle(s).color; s.remove(); return c; })()"
        )
        self.assertEqual(conflict.evaluate("bar => getComputedStyle(bar).backgroundColor"), red)
        image = self.page.locator(".project-timeline .tl-avail .tl-bar.is-unavailable").first.evaluate(
            "bar => getComputedStyle(bar).backgroundImage"
        )
        self.assertIn("repeating-linear-gradient", image)
        self.assertEqual(self.page.locator(".project-timeline .tl-label.person .plan-warning").count(), 1)
        self.assertEqual(self.axe_findings(".course-timeline"), [])

    def test_fill_an_open_place_in_the_dialog(self) -> None:
        """PRJ-110: the crew dialog of the planning, opened from the phase; back on Zeitplanung afterwards."""
        self.open(self.url)
        self.assertEqual(self.axe_findings("#phases"), [])
        self.page.locator(f'[data-crew-line="{self.open_place.pk}"] .phase-crew-actions a').click()
        self.page.locator("#dialog[open] form").wait_for()
        self.assertEqual(self.axe_findings("#dialog"), [])
        self.page.select_option("#dialog select[name=person]", str(self.vera.pk))
        with self.page.expect_navigation():
            self.page.locator("#dialog button[type=submit]").click()
        self.page.wait_for_load_state("networkidle")
        self.assertTrue(self.page.url.endswith(self.url), self.page.url)
        self.assertEqual(CrewLine.objects.get(pk=self.open_place.pk).person, self.vera)
        self.assertIn("Personalposition gespeichert.", self.text_of("body"))
        row = self.page.locator(f'[data-crew-line="{self.open_place.pk}"]')
        self.assertIn("Vera Lang", row.inner_text())
        self.assertIn("anfragen", row.inner_text())

    def test_change_and_remove_a_trip(self) -> None:
        """PRJ-111: the dialog of a trip; removed, it is listed to be brought back."""
        key = f"to_venue-{self.setup.pk}"
        self.open(self.url)
        self.page.locator(f'tr[data-trip="{key}"] .actions a').click()
        self.page.locator("#dialog[open] form").wait_for()
        self.assertEqual(self.axe_findings("#dialog"), [])
        self.page.fill("#dialog textarea[name=note]", "Rampe hinten")
        with self.page.expect_navigation():
            self.page.locator("#dialog button[type=submit]").click()
        self.page.wait_for_load_state("networkidle")
        row = self.page.locator(f'tr[data-trip="{key}"]')
        self.assertIn("angepasst", row.inner_text())
        self.assertIn("Rampe hinten", row.inner_text())
        self.assertEqual(self.axe_findings("#trips"), [])
        row.locator('button[aria-label^="Fahrt"]').click()
        self.confirm()
        # The form posts after the question closes; wait for the new page, not only for a quiet network.
        self.page.locator("#trips").get_by_text("Entfernte Fahrten").wait_for()
        self.assertIn("Entfernte Fahrten", self.text_of("#trips"))
        self.assertTrue(TripAdjustment.objects.get(trip_key=key).is_removed)
        self.assertEqual(self.axe_findings("#trips"), [])


class MyDeploymentsOnAPhoneTests(AxeMixin, BrowserTestCase):
    """UIX-043: My area → Meine Einsätze at 375 px – no sideways scrolling, filters folded."""

    viewport: ClassVar[dict[str, int]] = {"width": 375, "height": 800}

    def setUp(self) -> None:
        super().setUp()
        person = make_person("Anna", user=User.objects.get(username="anna"), rates={"Stagehand": "20.00"})
        plan(make_project("Sommerfest am See mit einem langen Namen"), "Stagehand", person, meeting_point="Tor 3")

    def test_the_tab_on_a_phone(self) -> None:
        self.open("/me/deployments/")
        self.assertIn("Sommerfest am See", self.text_of("main"))
        self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), True)
        self.assertFalse(self.page.locator("[data-filter-panel] select[name=period]").is_visible())
        self.assertEqual(self.axe_findings(), [])
