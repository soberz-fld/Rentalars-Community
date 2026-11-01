# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: the partial return (PCK-028), the packlist bar (PCK-029), the parts as sub-tabs (PCK-030).

On the packlist of the sample project "Stadtfest Hauptbühne" the first rows
are ticked and issued. In "Rücknahme" one row is ticked as back and booked
with "Rücknahme buchen" while the rest is still packed; back in
"Packen/Ausgabe" the rest is packed on. The pages are checked with axe-core
(NFA-025), also at the width of a phone.
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.packing.models import PackEntry, Packlist, PacklistStatus
from rentalars.projects.services import create_subproject
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import add_line, make_stock


class PartialReturnTestCase(BrowserTestCase):
    """The packlist of the sample project; the first two rows ticked and issued."""

    def rows(self) -> object:
        return self.page.locator("#packlist li.pack-row")

    def tick_and_issue_first_rows(self) -> None:
        self.open(f"/projects/{self.project.pk}/packlist/")
        for index in (0, 1):
            self.rows().nth(index).locator("button.tick").click()
            self.settle()
        with self.page.expect_navigation():
            self.page.get_by_role("button", name="Ausgeben", exact=True).click()
        self.page.wait_for_load_state("networkidle")


class PartialReturnInBrowserTests(PartialReturnTestCase):
    def test_take_back_part_while_packing_goes_on(self) -> None:
        self.tick_and_issue_first_rows()
        self.page.get_by_role("link", name="Rücknahme", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        book = self.page.get_by_role("button", name="Rücknahme buchen", exact=True)
        self.assertTrue(book.is_disabled())
        first = self.rows().nth(0)
        first.locator("button.tick").click()
        self.settle()
        self.assertIn("noch nicht gebucht", self.rows().nth(0).inner_text())
        self.assertIn("zurück abgehakt", self.text_of(".pack-legend"))
        with self.page.expect_navigation():
            book.click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("zurückgenommen", self.text_of("main .messages"))
        self.assertIn("is-taken-back", self.rows().nth(0).get_attribute("class"))
        self.assertEqual(self.rows().nth(0).locator("button.tick").count(), 0)
        packlist = Packlist.objects.get(project=self.project)
        self.assertEqual(packlist.status, PacklistStatus.PARTLY_ISSUED)
        entry = PackEntry.objects.filter(packlist=packlist, taken_back_quantity__gt=0).get()
        self.assertEqual(entry.taken_back_quantity, entry.issued_quantity)
        # Packing goes on in "Packen/Ausgabe".
        self.page.get_by_role("link", name="Packen/Ausgabe", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("zurückgenommen", self.text_of(".pack-legend"))
        third = self.rows().nth(2)
        third.locator("button.tick").click()
        self.settle()
        self.assertIn("abgehakte Stück", self.text_of(".pack-bar"))


class PackingAccessibilityTests(PartialReturnTestCase):
    """NFA-025: the packlist with its bar, both views, the parts as sub-tabs – wide and on a phone."""

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

    def test_packlist_pages(self) -> None:
        self.tick_and_issue_first_rows()
        part = create_subproject(self.project, name="Bühne Marktplatz", start=self.project.start, end=self.project.end)
        add_line(part, make_stock("K-777", 10, "Kabel extra"), 6)
        base = f"/projects/{self.project.pk}/packlist/"
        found: list[str] = []
        for width in (1360, 390):
            self.page.set_viewport_size({"width": width, "height": 900})
            for label, address in (
                ("packing", base + "?mode=pack"),
                ("taking back", base + "?mode=return"),
                ("all parts together", base + "family/"),
                ("a part", f"/projects/{part.pk}/packlist/"),
            ):
                self.open(address)
                self.page.wait_for_load_state("networkidle")
                found += self.findings(f"{label} at {width} px")
                # No page scrolls sideways on a phone.
                scrolls = self.page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
                self.assertFalse(scrolls, f"{label} at {width} px scrolls sideways")
        self.assertEqual(found, [], "\n".join(found))
