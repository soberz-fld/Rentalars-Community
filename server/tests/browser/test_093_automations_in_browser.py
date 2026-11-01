# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "automations": the buttons of a rule in one row, the defaults deleted and restored
(ADM-019).

The requirement: the buttons "Ausschalten" and "Löschen" of an automation stand at the same height – "Löschen", whose
first child is an icon, sat on another baseline than "Ausschalten" and stood about 4 px higher. Only a browser lays
the page out: these tests measure the boxes of the buttons at 1280 and 390 px – in the rows of the list, on the page
of a rule and in the question before deleting – and click through deleting and restoring a default (the page tests
are in tests/unit/test_093_automations.py). axe-core judges the pages (NFA-025, with RENTALARS_AXE).
"""

from __future__ import annotations

from typing import Any
from unittest import SkipTest

from rentalars.automations import defaults
from rentalars.automations.models import Automation
from tests.browser import test_accessibility_in_browser as accessibility  # a module: its tests do not run here
from tests.browser.base import BrowserTestCase

AUTOMATIONS = "/administration/automations/"
WIDTHS = (1280, 390)


class AutomationCase(BrowserTestCase):
    """The four defaults (the test server starts with an empty database)."""

    def setUp(self) -> None:
        super().setUp()
        defaults.restore()

    def box(self, locator: Any) -> dict[str, float]:
        """Where a button is: top, height, left."""
        found = locator.bounding_box()
        self.assertIsNotNone(found)
        return found

    def assert_in_one_row(self, *buttons: Any) -> None:
        """The buttons have one top and one height."""
        boxes = [self.box(button) for button in buttons]
        for other in boxes[1:]:
            self.assertAlmostEqual(other["y"], boxes[0]["y"], delta=0.5, msg=boxes)
            self.assertAlmostEqual(other["height"], boxes[0]["height"], delta=0.5, msg=boxes)
        lefts = [found["x"] for found in boxes]
        self.assertEqual(lefts, sorted(lefts))  # side by side, in this order


class ButtonsInBrowserTests(AutomationCase):
    """'Bearbeiten', 'Ausschalten'/'Einschalten' and 'Löschen' in one row of one height, wide and on a phone."""

    def test_the_rows_of_the_list(self) -> None:
        Automation.objects.filter(default_key="case_backlog_due").update(is_active=False)  # "Einschalten" as well
        for width in WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 900})
            self.open(AUTOMATIONS)
            for rule in Automation.objects.all():
                cell = self.page.locator(f'.cell-buttons:has(button[form="delete-{rule.pk}"])')
                self.assert_in_one_row(
                    cell.get_by_role("link", name="Bearbeiten"),
                    cell.locator(f'button[form="toggle-{rule.pk}"]'),
                    cell.locator(f'button[form="delete-{rule.pk}"]'),
                )
            self.assertEqual(self.page.locator("button", has_text="Einschalten").count(), 1)

    def test_narrow_phones(self) -> None:
        """At 360 and 320 px the buttons may wrap – of one height – and the page never gets wider than the phone."""
        Automation.objects.filter(default_key="defect_case").delete()  # "Standard-Automationen wiederherstellen"
        for width in (360, 320):
            self.page.set_viewport_size({"width": width, "height": 800})
            self.open(AUTOMATIONS)
            self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), width)
            restore = self.box(self.page.get_by_role("button", name="Standard-Automationen wiederherstellen"))
            self.assertLessEqual(restore["x"] + restore["width"], width)
            heights = self.page.locator(".cell-buttons > *").evaluate_all(
                "buttons => buttons.map(button => button.getBoundingClientRect().height)"
            )
            self.assertEqual(len(heights), 9)
            self.assertEqual(len(set(heights)), 1, heights)

    def test_the_page_of_a_rule_and_the_question(self) -> None:
        rule = Automation.objects.get(default_key="defect_case")
        self.page.set_viewport_size({"width": 1280, "height": 900})
        self.open(f"{AUTOMATIONS}{rule.pk}/")
        row = self.page.locator(".btn-row", has=self.page.locator(f'button[form="delete-{rule.pk}"]'))
        save, cancel, delete = (
            row.get_by_role("button", name="Automation speichern"),
            row.get_by_role("link", name="Abbrechen"),
            row.get_by_role("button", name="Löschen"),
        )
        self.assert_in_one_row(save, cancel, delete)
        self.page.set_viewport_size({"width": 390, "height": 900})
        self.assert_in_one_row(save, cancel)  # on a phone "Löschen" may go to the next line – of the same height
        self.assertAlmostEqual(self.box(delete)["height"], self.box(save)["height"], delta=0.5)
        delete.click()
        question = self.page.locator("dialog.confirm[open]")
        question.wait_for()
        self.assertIn("„Standard-Automationen wiederherstellen“ holt sie zurück", question.inner_text())
        self.assert_in_one_row(
            question.get_by_role("button", name="Abbrechen"), question.get_by_role("button", name="Löschen")
        )
        question.get_by_role("button", name="Abbrechen").click()
        self.assertTrue(Automation.objects.filter(pk=rule.pk).exists())


class DefaultsInBrowserTests(AutomationCase):
    """A default edited, deleted and restored by clicking."""

    def test_edit_delete_restore(self) -> None:
        self.open(AUTOMATIONS)
        backlog = Automation.objects.get(default_key="case_backlog_due")
        self.page.locator(f'.cell-buttons:has(button[form="delete-{backlog.pk}"])').get_by_role(
            "link", name="Bearbeiten"
        ).click()
        self.page.locator("#default-note", has_text="Diese Automation kam mit Rentalars.").wait_for()
        self.page.fill("#id_name", "Rückstand: wieder öffnen")
        self.page.get_by_role("button", name="Automation speichern").click()
        self.page.locator(".messages", has_text="„Rückstand: wieder öffnen“ ist gespeichert.").wait_for()
        row = self.page.locator("tr", has=self.page.locator(f'button[form="delete-{backlog.pk}"]'))
        self.assertIn("geändert", row.inner_text())
        # Delete the defect rule with the question of the page ...
        defect = Automation.objects.get(default_key="defect_case")
        self.page.locator(f'button[form="delete-{defect.pk}"]').click()
        self.confirm()
        self.page.locator(".messages", has_text="holt sie zurück, wie sie kam.").wait_for()
        self.assertFalse(Automation.objects.filter(pk=defect.pk).exists())
        # ... and bring it back: the question names what is created.
        restore = self.page.get_by_role("button", name="Standard-Automationen wiederherstellen")
        self.assert_in_one_row(self.page.get_by_role("link", name="Neue Automation"), restore)
        restore.click()
        question = self.page.locator("dialog.confirm[open]")
        question.wait_for()
        self.assertIn("Rentalars legt an: „Defektmeldung → Servicefall“.", question.inner_text())
        self.confirm()
        self.page.locator(".messages", has_text="1 Standard-Automation wiederhergestellt").wait_for()
        self.assertEqual(self.page.get_by_role("button", name="Standard-Automationen wiederherstellen").count(), 0)
        self.assertEqual(Automation.objects.get(default_key="defect_case").name, "Defektmeldung → Servicefall")
        self.assertEqual(Automation.objects.get(default_key="case_backlog_due").name, "Rückstand: wieder öffnen")


class AutomationPagesAccessibilityTests(AutomationCase):
    """The list with marks and the button to restore, and the page of a default, without a finding of axe-core."""

    bypass_csp = True
    findings = accessibility.AccessibilityInBrowserTests.findings

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def test_pages(self) -> None:
        Automation.objects.filter(default_key="defect_case").delete()
        changed = Automation.objects.get(default_key="case_backlog_due")
        changed.name = "Rückstand: wieder öffnen"
        changed.save()
        findings: list[str] = []
        for width in WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 900})
            findings += self.findings(AUTOMATIONS)
            findings += self.findings(f"{AUTOMATIONS}{changed.pk}/")
        self.assertEqual(findings, [], "\n".join(findings))
