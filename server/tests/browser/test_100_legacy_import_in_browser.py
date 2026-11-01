# SPDX-License-Identifier: GPL-3.0-or-later
"""Old projects from invoices in a real browser (legacy import; PRJ-130): the main flow, accessibility, a phone.

Upload a PDF invoice, check the preview (with a warning shown), correct a field, continue, read the confirmation and
take the project over; every page of the way is checked with axe-core (WCAG 2.1 A/AA, see
``tests.browser.test_accessibility_in_browser``) and the preview fits the width of a phone.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest import SkipTest

from django.test import override_settings

from rentalars.documents.models import Document
from rentalars.projects.models import Project, ProjectStatus
from tests.browser import test_accessibility_in_browser as accessibility
from tests.browser.base import BrowserTestCase
from tests.unit.test_100_legacy_import import invoice_pdf


class LegacyBase(BrowserTestCase):
    """Uploads go to a folder of the test; the checks of axe for the pages."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        super().setUpClass()

    def setUp(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        override = override_settings(DATA_DIR=folder, MEDIA_ROOT=str(folder / "media"), SERVE_MEDIA_VIA_NGINX=False)
        override.enable()
        self.addCleanup(override.disable)
        self.folder = folder
        super().setUp()

    def pdf(self, name: str = "rechnung.pdf", **options: Any) -> str:
        path = self.folder / name
        path.write_bytes(invoice_pdf(**options))
        return str(path)

    def findings(self) -> list[str]:
        """The findings of axe on the page as it is now."""
        if self.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.wait_for_load_state("networkidle")
        self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(  # type: ignore[no-any-return]
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            accessibility.WCAG_AA,
        )


class LegacyImportInBrowserTests(LegacyBase):
    """The way a person does it, with the checks of axe on every page."""

    def test_upload_check_correct_confirm(self) -> None:
        findings: dict[str, list[str]] = {}
        self.open("/accounting/legacy/")
        findings["overview"] = self.findings()
        self.page.set_input_files("#legacy-files", [self.pdf(wrong_total="700.00")])
        self.page.click("button:has-text('Hochladen und auslesen')")
        self.page.wait_for_url(re.compile(r"/accounting/legacy/\d+/$"))
        # The preview: what was read, and the warning about the sums.
        self.assertEqual(self.page.input_value("input[name$='-number']"), "2023-0042")
        self.assertIn("Die Positionen ergeben 710,00 €", self.page.inner_text("body"))
        self.assertEqual(Project.objects.filter(number__startswith="ALT-").count(), 0)  # nothing created yet
        findings["preview"] = self.findings()
        self.page.fill("input[name$='-event_name']", "Stadtfest 2023 (geprüft)")
        self.page.check("input[name='take']")
        self.page.click("button:has-text('Prüfen und weiter')")
        self.page.wait_for_selector("text=Genau das wird angelegt")
        self.assertIn("Stadtfest 2023 (geprüft)", self.page.inner_text("body"))
        self.assertEqual(Project.objects.filter(number__startswith="ALT-").count(), 0)  # still nothing
        findings["confirmation"] = self.findings()
        self.page.click("button:has-text('Projekt übernehmen')")
        self.page.wait_for_selector("text=wurde übernommen")
        project = Project.objects.get(number__startswith="ALT-")
        self.assertEqual((project.name, project.status), ("Stadtfest 2023 (geprüft)", ProjectStatus.CLOSED))
        self.assertEqual(Document.objects.filter(number="2023-0042").count(), 1)
        self.assertIn(project.number, self.page.inner_text("body"))
        findings["done"] = self.findings()
        self.page.click("button:has-text('Import zurücknehmen')")
        self.page.wait_for_selector("text=Der Import wurde zurückgenommen")
        self.assertEqual(Project.objects.filter(number__startswith="ALT-").count(), 0)
        found = [f"{page}: {finding}" for page, items in findings.items() for finding in items]
        self.assertEqual(found, [], "\n".join(found))

    def test_a_blocking_error_is_shown_and_nothing_is_created(self) -> None:
        self.open("/accounting/legacy/")
        self.page.set_input_files("#legacy-files", [self.pdf()])
        self.page.click("button:has-text('Hochladen und auslesen')")
        self.page.wait_for_url(re.compile(r"/accounting/legacy/\d+/$"))
        self.page.fill("input[name$='-number']", "")
        self.page.check("input[name='take']")
        self.page.click("button:has-text('Prüfen und weiter')")
        self.page.wait_for_selector("text=Gib die Rechnungsnummer ein.")
        self.assertEqual(Project.objects.filter(number__startswith="ALT-").count(), 0)
        found = self.findings()
        self.assertEqual(found, [], "\n".join(found))


class LegacyImportOnAPhoneTests(LegacyBase):
    """The preview fits the width of a phone."""

    viewport: Any = {"width": 360, "height": 740}

    def test_the_preview_fits_the_width(self) -> None:
        self.open("/accounting/legacy/")
        self.page.set_input_files("#legacy-files", [self.pdf()])
        self.page.click("button:has-text('Hochladen und auslesen')")
        self.page.wait_for_url(re.compile(r"/accounting/legacy/\d+/$"))
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
