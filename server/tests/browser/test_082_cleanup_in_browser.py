# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "clean-up", in a real browser: filters folded on every page load (UIX-038), headings of added and
computed columns sort (UIX-015), with axe-core on a desk and on a phone.
"""

from __future__ import annotations

from tests.browser.test_081_ui_in_browser import UiInBrowserCase


class FiltersAlwaysFoldedTests(UiInBrowserCase):
    """UIX-038: folded on every page load, at every width – an opened list is not remembered."""

    def toggle(self) -> object:
        return self.page.locator("[data-filter-toggle]")

    def test_folded_again_after_opening_and_the_active_filter_shows(self) -> None:
        self.open("/products/?kind=rental")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "false")
        self.assertEqual(" ".join(self.toggle().inner_text().split()), "Filter (1 aktiv)")
        self.assertTrue(self.page.is_visible("#filter-summary-products .filter-chip"))
        self.axe()
        self.toggle().click()
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "true")
        self.open("/products/")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "false")
        self.assertEqual(" ".join(self.toggle().inner_text().split()), "Filter")

    def test_on_a_phone_too(self) -> None:
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.open("/material/?status=available")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "false")
        self.assertEqual(" ".join(self.toggle().inner_text().split()), "Filter (1 aktiv)")
        self.toggle().click()
        self.open("/material/")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "false")
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.axe()

    def test_the_master_data_lists_fold_their_filters(self) -> None:
        self.open("/administration/masterdata/masterdata/category/?is_active__exact=1")
        details = self.page.locator("#changelist-filter details")
        self.assertGreater(details.count(), 0)
        for index in range(details.count()):
            self.assertIsNone(details.nth(index).get_attribute("open"))
        self.assertIn("Ja", self.page.locator("#changelist-filter details.is-active summary").inner_text())
        details.first.locator("summary").click()
        self.open("/administration/masterdata/masterdata/category/")
        self.assertIsNone(self.page.locator("#changelist-filter details").first.get_attribute("open"))


class ComputedColumnsSortTests(UiInBrowserCase):
    """UIX-015: a column a user adds – and a computed one – sorts by a click on its heading."""

    def test_volume_of_the_models(self) -> None:
        self.open("/material/models/?cols=name,volume,dimensions")
        self.page.locator("th", has_text="Volumen").locator("a").click()
        self.page.wait_for_url("**sort=volume*")
        self.assertEqual(self.page.locator("th[aria-sort]").inner_text().strip()[:7], "Volumen")
        self.axe()

    def test_a_sum_of_the_projects(self) -> None:
        self.open("/projects/?cols=number,net_total&all=1")
        self.page.locator("th", has_text="Summe netto").locator("a").click()
        self.page.wait_for_url("**sort=net_total*")
        self.assertEqual(self.page.locator("th[aria-sort]").get_attribute("aria-sort"), "ascending")
        self.axe()
