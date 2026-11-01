# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: issue per article (PCK-025).

On the packlist of the sample project "Stadtfest Hauptbühne", the first rows
are ticked – one in full, one with a typed quantity – and issued with
"Ausgeben". The page stays in packing mode: the row that went out in full
shows "ausgegeben" without a tick, the row that went out in part is packed
on, and the project keeps its status. The rest is ticked and issued; then
the project is "out". The partly issued packlist is checked with axe-core
(NFA-025).
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.packing.models import Packlist, PacklistStatus
from rentalars.projects.models import ProjectStatus
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class IssuePerArticleTestCase(BrowserTestCase):
    """The packlist of the sample project, ticked in part."""

    def rows(self) -> object:
        return self.page.locator("#packlist li.pack-row")

    def issue_button(self) -> object:
        return self.page.get_by_role("button", name="Ausgeben", exact=True)

    def tick_and_issue_first_rows(self) -> None:
        self.open(f"/projects/{self.project.pk}/packlist/")
        self.assertTrue(self.issue_button().is_disabled())
        self.rows().nth(0).locator("button.tick").click()
        self.settle()
        second = self.rows().nth(1)
        second.locator("input[type=number]").fill("4")
        second.locator("input[type=number]").dispatch_event("change")
        self.settle()
        with self.page.expect_navigation():
            self.issue_button().click()
        self.page.wait_for_load_state("networkidle")


class IssuePerArticleInBrowserTests(IssuePerArticleTestCase):
    def test_partial_issue_then_pack_on_and_issue_the_rest(self) -> None:
        self.tick_and_issue_first_rows()
        packlist = Packlist.objects.get(project=self.project)
        self.assertEqual(packlist.status, PacklistStatus.PARTLY_ISSUED)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.CONFIRMED)
        self.assertIn("Das abgehakte Material ist ausgegeben", self.text_of("main .messages"))
        self.assertIn("Das Projekt bleibt „Bestätigt“, bis alles ausgegeben ist.", self.text_of(".pack-partly"))

        # Still packing: the first row is out and has no tick, the second is packed on.
        first, second = self.rows().nth(0), self.rows().nth(1)
        self.assertIn("is-issued", first.get_attribute("class"))
        self.assertEqual(first.locator("button.tick").count(), 0)
        self.assertIn("4 von 6 ausgegeben", second.inner_text())
        self.assertTrue(self.issue_button().is_disabled())
        second.locator("button.tick").click()
        self.settle()
        self.assertEqual(self.rows().nth(1).locator("input[type=number]").input_value(), "6")
        self.assertIn("2 abgehakte Stück gehen raus.", self.text_of(".pack-bar"))
        with self.page.expect_navigation():
            self.issue_button().click()
        self.page.wait_for_load_state("networkidle")
        packlist.refresh_from_db()
        self.assertEqual(packlist.status, PacklistStatus.PARTLY_ISSUED)

        # The rest at once, as if packed on paper: "Alles ausgeben" asks first.
        self.page.get_by_role("button", name="Alles ausgeben", exact=True).click()
        with self.page.expect_navigation():
            self.confirm()
        self.page.wait_for_load_state("networkidle")
        packlist.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual((packlist.status, self.project.status), (PacklistStatus.ISSUED, ProjectStatus.OUT))
        self.assertIn("Unterwegs", self.page.inner_text("main"))


class IssuePerArticleAccessibilityTests(IssuePerArticleTestCase):
    """NFA-025: the partly issued packlist, packing and taking back, checked with axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def findings(self, label: str) -> list[str]:
        """What axe-core finds on the page as it is now."""
        self.page.add_script_tag(path=str(self.axe))
        result = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        return [f"{label}: {finding}" for finding in result]

    def test_partly_issued_packlist(self) -> None:
        self.tick_and_issue_first_rows()
        # Once more without the message of the issue: its list is a matter of the base template.
        self.open(f"/projects/{self.project.pk}/packlist/")
        self.page.wait_for_load_state("networkidle")
        found = self.findings("packing the rest")
        self.open(f"/projects/{self.project.pk}/packlist/?mode=return")
        self.page.wait_for_load_state("networkidle")
        found += self.findings("taking back")
        self.assertEqual(found, [], "\n".join(found))
