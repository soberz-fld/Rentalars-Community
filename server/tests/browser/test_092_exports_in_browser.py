# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the export in the import format is downloaded, and the pages pass axe-core.

IMP-017 (export in the import format) and IMP-006 (the readable export of all data under "Sicherung").

The page tests (tests/unit/test_092_exports.py) check the files and the texts; here a real browser follows the
link "Export im Importformat" to a saved file, and axe-core judges the changed pages – the settings with the
exports next to the imports, the page "Sicherung und Verschlüsselung" with the readable export of all data,
and the import pages – against WCAG 2.1 AA (NFA-025; it runs with RENTALARS_AXE, see
tests/browser/test_accessibility_in_browser.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest import SkipTest

from tests.browser import test_accessibility_in_browser as accessibility  # a module: its tests do not run here
from tests.browser.base import BrowserTestCase


class ExportDownloadInBrowserTests(BrowserTestCase):
    """The link next to the import saves a CSV file with the headings of the import."""

    def test_download_from_the_settings(self) -> None:
        self.open("/administration/")
        with self.page.expect_download() as waiting:
            self.page.locator('a[href="/import/customers/export/"]').click()
        download = waiting.value
        self.assertRegex(download.suggested_filename, r"^kunden-importformat-\d{4}-\d{2}-\d{2}\.csv$")
        text = Path(download.path()).read_text(encoding="utf-8-sig")
        self.assertTrue(text.startswith("Nummer;Name;Vorname;Nachname;"), text[:80])


class ExportPagesAccessibilityTests(BrowserTestCase):
    """The changed pages without a finding of axe-core (NFA-025)."""

    bypass_csp = True
    findings = accessibility.AccessibilityInBrowserTests.findings

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def test_pages(self) -> None:
        findings: list[str] = []
        for path in ["/administration/", "/administration/backup/", "/material/import/", "/import/customers/"]:
            findings += self.findings(path)
        self.assertEqual(findings, [], "\n".join(findings))
