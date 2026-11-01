# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the answer to a deployment request shows on the open planning (PER-033).

* An answer that comes while the planner has the planning open shows without pressing reload – also when the
  planner saved something of their own just after it came: that change once took the answer's change over
  silently, and the line stood on "angefragt" until the page was loaded by hand.
* An accepted line offers no "erneut anfragen"; with new times (the automation switched off) it says so – on a
  phone without horizontal scrolling and checked with axe-core (NFA-025).
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.accounts.models import User
from rentalars.core.audit import acting_as
from rentalars.core.models import SystemSettings
from rentalars.projects import crew
from rentalars.projects.models import CrewLine
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import ALL_RIGHTS, make_person, plan


class AnswerOnTheOpenPlanningInBrowserTests(BrowserTestCase):
    """PER-033: the open planning follows the answer."""

    watch_changes = True

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", email="anna@crew.example")
        self.line = plan(self.project, "Tontechnik", self.anna)
        crew.request_deployment(self.line, user=User.objects.get(username="anna"))

    def request_cell(self) -> str:
        return " ".join(self.page.locator(f'tr[data-crew-line="{self.line.pk}"] .request').inner_text().split())

    def answer_elsewhere(self) -> None:
        """Anna answers – in her browser, or Rentalars takes her mail over: either way not this page."""
        account = self.anna.user
        with acting_as(account):
            crew.answer_deployment(CrewLine.objects.get(pk=self.line.pk), accept=True, user=account)

    def test_the_answer_shows_without_reload(self) -> None:
        self.open_planning()
        self.settle()
        self.assertIn("angefragt", self.request_cell())
        self.answer_elsewhere()
        with self.page.expect_navigation():
            self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        self.page.locator(f'tr[data-crew-line="{self.line.pk}"] .badge.green').wait_for()
        self.assertEqual(self.request_cell(), "zugesagt")

    def test_an_own_change_just_after_the_answer_does_not_swallow_it(self) -> None:
        self.open_planning()
        self.settle()
        self.answer_elsewhere()
        # The planner deletes a material line before the page asked again: only that line's group comes back.
        with self.page.expect_navigation():
            self.page.locator('table.lines form[hx-post$="/delete/"] button[data-confirm]').first.click()
            self.confirm()
        self.page.locator(f'tr[data-crew-line="{self.line.pk}"] .badge.green').wait_for()
        self.assertNotIn("erneut anfragen", self.request_cell())


class ChangedTimesInBrowserTests(BrowserTestCase):
    """PER-033: with new times and the automation off, the line says so; phone width and axe."""

    bypass_csp = True

    def test_on_a_phone_and_with_axe(self) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        system = SystemSettings.load()
        system.ask_again_on_new_times = False
        system.save()
        anna = make_person("Anna Becker", email="anna@crew.example")
        line = plan(self.project, "Tontechnik", anna)
        planner = User.objects.get(username="anna")
        crew.request_deployment(line, user=planner)
        crew.answer_deployment(line, accept=True, user=planner)
        crew.update_crew_line(CrewLine.objects.get(pk=line.pk), rights=ALL_RIGHTS, start=line.start.replace(minute=30))

        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open_planning()
        self.page.wait_for_load_state("networkidle")
        cell = self.page.locator(f'tr[data-crew-line="{line.pk}"] .request')
        self.assertIn("Zeiten geändert seit der Zusage", cell.inner_text())
        self.assertTrue(cell.get_by_role("button", name="erneut anfragen").is_visible())
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

        cell.get_by_role("button", name="erneut anfragen").click()
        # The request cell: the line also carries the yellow "Schätzung" of billing by effort (PER-036).
        self.page.locator(f'tr[data-crew-line="{line.pk}"] .request .badge.yellow').wait_for()
        self.assertNotIn("Zeiten geändert", cell.inner_text())
