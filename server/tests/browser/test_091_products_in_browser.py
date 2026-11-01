# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the availability of a product follows the period at once, and a kit unfolds its components
in the material utilization (PRD-050, VFG-037).

The page tests (tests/unit/test_091_products.py) read the HTML; only a browser runs htmx, which loads the figures
when the period changes, and applies the style sheet that folds the rows of a kit's components.
"""

from __future__ import annotations

from rentalars.products.models import Product
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class ProductsInBrowserTests(BrowserTestCase):
    """The parts of the wishes around products that need the browser (PRD-050, VFG-037); no finding of axe-core."""

    bypass_csp = True  # axe-core is put into the page

    def axe_findings(self, within: str) -> list[str]:
        """What axe-core finds within the elements a selector names – nothing if axe-core is not at hand."""
        axe = _axe_path()
        if axe is None:
            return []
        self.page.wait_for_load_state("networkidle")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run({include: [[within]]},"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )

    def test_the_availability_follows_the_period_without_a_button(self) -> None:
        cable = Product.objects.get(article_number="K-010")
        self.open(f"/products/{cable.pk}/")
        result = self.page.locator("#availability-result")
        result.wait_for()
        self.assertEqual(self.page.get_by_role("button", name="Zeitraum prüfen").count(), 0)
        self.page.fill("#id_start", "2027-03-20T08:00")
        self.page.fill("#id_end", "2027-03-22T18:00")
        self.page.locator("#id_end").dispatch_event("change")
        result.locator("text=20.03.2027 08:00 – 22.03.2027 18:00").wait_for()
        self.settle()
        self.assertIn("start=2027-03-20T08%3A00", self.page.url)
        link = result.get_by_role("link", name="In der Materialauslastung zeigen")
        self.assertIn(f"product={cable.pk}&from=2027-03-20&days=3", link.get_attribute("href") or "")
        self.assertEqual(self.axe_findings("#availability-result"), [])

    def test_a_kit_unfolds_its_components_in_the_utilization(self) -> None:
        kit = Product.objects.get(article_number="T-100")
        self.open(f"/schedule/products/?product={kit.pk}&from=2027-03-08&weeks=1")
        components = self.page.locator(".tl-kit-parts .tl-label")
        self.assertEqual(components.count(), 3)
        self.assertTrue(components.first.is_visible())  # chosen alone: unfolded
        self.page.locator(f"label[for=kit-parts-{kit.pk}]").click()
        self.assertFalse(components.first.is_visible())
        self.page.locator(f"label[for=kit-parts-{kit.pk}]").click()
        self.assertTrue(components.first.is_visible())
        self.assertIn("komplette Sets im Bestand", self.page.locator(".tl-label.is-kit").inner_text())
        self.assertEqual(self.axe_findings(".utilization"), [])
