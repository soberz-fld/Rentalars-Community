# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the audit mode with the keyboard alone, and the pages of the audits checked with axe-core.

The page tests (tests/unit/test_092_audits.py) send the forms as a browser would; only a browser shows where the
focus is after each step – the fast flow "ID, Enter, next ID, Enter" depends on it – and only axe-core judges the
pages against WCAG 2.1 AA (NFA-025; it runs with RENTALARS_AXE, see tests/browser/test_accessibility_in_browser.py).
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.material import audits
from rentalars.material.audit_models import AuditResult
from rentalars.material.models import MaterialItem
from tests.browser import test_accessibility_in_browser as accessibility  # a module: its tests do not run here
from tests.browser.base import BrowserTestCase
from tests.helpers import at, make_item, make_model, make_product


class AuditCase(BrowserTestCase):
    """A microphone 7427 and a cable 7428."""

    def setUp(self) -> None:
        super().setUp()
        self.microphone = make_item(make_model("Funkmikrofon 092", make_product("T-092")), 7427)
        self.cable = make_item(make_model("XLR-Kabel 092", make_product("K-092")), 7428)

    def focused(self) -> str:
        return self.page.evaluate("() => document.activeElement.id")


class AuditModeInBrowserTests(AuditCase):
    """The keyboard flow of the audit mode (MAT-068, MAT-070): the focus is always where the next key goes."""

    def test_with_the_keyboard_alone(self) -> None:
        self.open("/material/audit/")
        self.assertEqual(self.focused(), "audit-id")
        self.page.keyboard.type("#7427")
        self.page.keyboard.press("Enter")
        self.page.locator("#audit-item-title", has_text="Funkmikrofon 092").wait_for()
        self.assertEqual(self.focused(), "audit-next")
        # The next ID, Enter: 7427 is in order, 7428 is shown at once.
        self.page.keyboard.type("7428")
        self.page.keyboard.press("Enter")
        self.page.locator("#audit-item-title", has_text="XLR-Kabel 092").wait_for()
        self.assertEqual(self.microphone.audits.get().result, AuditResult.OK)
        # Quick picks are buttons that stay pressed; "Audit speichern" records them.
        self.page.locator(".audit-pick", has_text="Klett fehlt").click()
        self.assertTrue(self.page.locator('.audit-pick input[value="Klett fehlt"]').is_checked())
        self.page.fill("#audit-todo-text", "Mantel eingerissen")
        self.page.locator("#audit-todo-text").press("Enter")  # Enter in the field: "Audit speichern"
        self.page.locator(".messages", has_text="7428 geprüft: mit To-Dos.").wait_for()
        self.assertEqual(self.focused(), "audit-id")
        self.assertEqual(sorted(self.cable.todos.values_list("text", flat=True)), ["Klett fehlt", "Mantel eingerissen"])
        self.assertEqual(self.page.locator('section[aria-labelledby="audit-round-title"] tbody tr').count(), 2)

    def test_to_dos_ticked_done_together(self) -> None:
        for item in (self.microphone, self.cable):
            audits.add_todo(item, "Label fehlt")
        self.open("/material/open-points/to-dos/")
        bar = self.page.locator("#todos-done")
        self.assertFalse(bar.is_visible())  # only while something is ticked (UIX-048)
        self.page.locator('thead input[data-check-all="todos"]').check()
        bar.wait_for()
        bar.locator("button[type=submit]").click()
        self.page.locator(".messages", has_text="2 To-Dos erledigt.").wait_for()
        self.assertFalse(audits.open_todos().exists())


class AuditPagesAccessibilityTests(AuditCase):
    """The pages of the audits (MAT-067, MAT-068, MAT-069, MAT-070) without a finding of axe-core (NFA-025)."""

    bypass_csp = True
    findings = accessibility.AccessibilityInBrowserTests.findings

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def test_pages(self) -> None:
        MaterialItem.objects.filter(pk=self.microphone.pk).update(created_at=at(1, 8, year=2024))
        audits.record_audit(self.cable, todos=["Label fehlt"], note="Halle 2")
        audits.add_todo(self.microphone, "Reinigen")
        findings: list[str] = []
        for path in [
            "/material/audit/",
            "/material/audit/?id=7428",
            f"/material/items/{self.cable.pk}/",
            "/material/open-points/",
            "/material/open-points/to-dos/",
            "/material/open-points/audits/",
            "/administration/audits/",
        ]:
            findings += self.findings(path)
        self.assertEqual(findings, [], "\n".join(findings))
