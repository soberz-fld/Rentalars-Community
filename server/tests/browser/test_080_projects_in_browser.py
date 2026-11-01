# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "projects", in the browser: a show file picks its type and console by itself (PRJ-089); "In
Teilprojekte gliedern" behind the arrow of "Teilprojekt hinzufügen" and its page (PRJ-050); the pages of the service
cases (PRJ-090) – and axe-core on all of them."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.masterdata.models import DocumentType
from rentalars.projects import service_cases
from rentalars.projects.models import Project, ProjectFile
from rentalars.projects.showfiles import showfile_type
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import add_group, add_line, at, make_project, make_stock, plan


class ProjectsInBrowserTests(BrowserTestCase):
    """PRJ-050, PRJ-089, PRJ-090 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def axe_findings(self, within: str = "") -> list[str]:
        """What axe-core finds on the page, or only within the elements a selector names."""
        self.page.wait_for_load_state("networkidle")
        # Colours in the middle of a transition (120 ms on buttons) are no finding.
        self.page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running')")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run(within ? {include: [[within]]} : document,"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )

    def both_themes(self, within: str = "") -> list[str]:
        """axe-core in the dark theme and – after switching, on the page's own content – in the light one."""
        findings = self.axe_findings(within)
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
        findings += [f"light: {finding}" for finding in self.axe_findings(within or "main")]
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        return findings

    def test_a_show_file_picks_its_type_and_console(self) -> None:
        """PRJ-089: choosing "Gala.esf3d" chooses "Showfile" and "ETC Eos"; a PDF leaves the fields hidden."""
        # The document types come from migrations; a browser test before this one may have emptied the tables.
        DocumentType.objects.get_or_create(
            name="Showfile", defaults={"is_showfile": True, "visible_to_crew": True, "position": 90}
        )
        DocumentType.objects.get_or_create(name="Vertrag", defaults={"position": 91})
        gala = make_project("Gala 080", start=at(20, 8), end=at(21, 22))
        self.open(f"/projects/{gala.number}/documents/")
        fields = self.page.locator("[data-showfile-fields]")
        self.assertFalse(fields.is_visible())
        self.page.set_input_files(
            "#id_file", files=[{"name": "Plan.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4"}]
        )
        self.assertEqual(self.page.locator("#id_document_type").input_value(), "")
        self.assertFalse(fields.is_visible())
        self.page.set_input_files(
            "#id_file", files=[{"name": "Gala.esf3d", "mimeType": "application/octet-stream", "buffer": b"show"}]
        )
        self.assertEqual(self.page.locator("#id_document_type").input_value(), str(showfile_type().pk))
        self.assertTrue(fields.is_visible())
        self.assertEqual(self.page.locator("#id_show_system").input_value(), "ETC Eos")
        self.page.fill("#id_show_version", "3.2.9")
        self.assertEqual(self.both_themes("#files"), [])
        self.page.locator("#files button[type=submit]").click()
        self.page.wait_for_load_state("networkidle")
        show = ProjectFile.objects.get(project=gala)
        self.assertEqual((show.show_system, show.show_version, show.is_current_show), ("ETC Eos", "3.2.9", True))
        self.assertIn("ETC Eos · Version 3.2.9", self.text_of("#files"))
        # The type can be chosen by hand as well: the fields appear with it.
        self.page.select_option("#id_document_type", label="Showfile")
        self.assertTrue(fields.is_visible())
        self.page.select_option("#id_document_type", label="Vertrag")
        self.assertFalse(fields.is_visible())
        self.assertEqual(self.axe_findings("#files"), [])

    def test_divide_a_project_into_subprojects(self) -> None:
        """PRJ-050: from the menu at "Teilprojekt hinzufügen" to the page and to the overview of the parts."""
        fest = make_project("Fest 080", start=at(20, 8), end=at(22, 22))
        spots = make_stock("L-080", 10, "Spot 080")
        market = add_group(fest, "Bühne Markt")
        add_group(fest, "Bühne Park")
        add_line(fest, spots, 2, group=market)
        plan(fest, "Lichttechnik", start=at(20, 8), end=at(20, 18))
        self.open(f"/projects/{fest.number}/")
        self.page.locator('summary[aria-label="Mehr zu Teilprojekten"]').click()
        link = self.page.locator("a", has_text="In Teilprojekte gliedern")
        link.wait_for()
        self.assertEqual(self.axe_findings(".project-actions"), [])
        link.click()
        self.page.wait_for_url(f"**/projects/{fest.number}/split/")
        self.assertEqual(self.both_themes(), [])
        self.page.locator(f'input[name="groups"][value="{market.pk}"]').check()
        self.page.locator("select[name^=crew_]").select_option(label="geht mit „Bühne Markt“")
        self.page.locator("form.split-form button[type=submit]").click()
        self.page.wait_for_url(f"**/projects/{fest.number}/parts/")
        part = Project.objects.get(parent=fest)
        self.assertEqual(part.name, "Bühne Markt")
        self.assertIn(f"{part.number} Bühne Markt", self.text_of("main"))
        self.assertEqual(part.crew_lines.count(), 1)

    def test_the_pages_of_the_service_cases(self) -> None:
        """PRJ-090: list, new case with a customer typed in, the case with its status – without finding."""
        service_cases.create_case(name="Kabeltrommel defekt", case_contact="Herr Meier")
        self.open("/projects/service-cases/")
        self.assertIn("Kabeltrommel defekt", self.text_of("main"))
        self.assertEqual(self.both_themes(), [])
        self.page.locator("a.btn", has_text="Neuer Servicefall").click()
        self.page.wait_for_url("**/projects/service-cases/new/")
        self.page.fill("#id_name", "Beamer flackert")
        field = self.page.locator("#id_customer_text")
        field.click()
        field.press_sequentially("Stadt", delay=20)
        self.page.locator("[role=option]").first.wait_for()
        field.press("Enter")
        self.settle()
        self.page.fill("#id_notes", "Seit dem Aufbau, Saal 2.")
        self.assertEqual(self.both_themes(), [])
        self.page.locator("form.form button[type=submit]").click()
        self.page.wait_for_url("**/case/")
        case = Project.objects.get(name="Beamer flackert")
        self.assertIsNotNone(case.customer)
        self.assertIn("Seit dem Aufbau, Saal 2.", self.text_of("main"))
        self.page.select_option("#id_case_status", "in_progress")
        self.page.locator(".case-status-form button").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(Project.objects.get(pk=case.pk).case_status, "in_progress")
        self.assertEqual(self.both_themes(), [])
        self.page.locator("a.btn", has_text="In Projekt umwandeln").click()
        self.page.wait_for_url("**/case/convert/")
        self.assertEqual(self.axe_findings(), [])
