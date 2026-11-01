# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "manual", in a real browser: one page per chapter (UIX-029). (UIX-057)

The contents page, a chapter on a phone (no sideways scroll, axe), the way from chapter to chapter, and the
forwarding of an old address with an anchor – under the Content Security Policy as the browser of a user has it.
"""

from __future__ import annotations

import re

from tests.browser.base import BrowserTestCase
from tests.browser.test_081_ui_in_browser import UiInBrowserCase


class ManualPagesInBrowserTests(UiInBrowserCase):
    """The pages as people see them."""

    def test_contents_and_chapter_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.open("/manual/")
        self.assertEqual(self.page.locator(".manual-chapter-link").count(), 18)
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.axe()
        self.page.locator(".manual-chapter-link").nth(6).click()
        self.page.wait_for_url("**/manual/7/")
        self.assertEqual(self.page.locator("article.manual h2").first.get_attribute("id"), "7-projekte-planen")
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.axe()

    def test_previous_and_next(self) -> None:
        self.open("/manual/4/")
        self.page.locator(".manual-pager a[rel=next]").last.click()
        self.page.wait_for_url("**/manual/5/")
        self.assertIn("Produkte", self.page.locator("article.manual h2").first.inner_text())
        self.page.locator(".manual-pager a[rel=prev]").first.click()
        self.page.wait_for_url("**/manual/4/")

    def test_the_list_of_chapters_beside_a_chapter(self) -> None:
        self.open("/manual/4/")
        current = self.page.locator(".manual-toc a[aria-current=page]")
        self.assertEqual(current.count(), 1)
        self.assertIn("4. Material", current.inner_text())
        self.page.locator(".manual-toc a", has_text="8. Preise").first.click()
        self.page.wait_for_url("**/manual/8/")

    def test_the_search(self) -> None:
        self.open("/manual/")
        self.page.fill(".manual-search input[type=search]", "Rabatt")
        self.page.press(".manual-search input[type=search]", "Enter")
        self.page.wait_for_url("**/manual/?q=Rabatt")
        self.assertGreater(self.page.locator(".manual-hits li").count(), 3)
        self.axe()
        self.page.locator(".manual-hits a").first.click()
        self.page.wait_for_url(re.compile(r".*/manual/\d+/#.+"))

    def test_a_section_link_scrolls_to_the_section(self) -> None:
        self.open("/manual/7/")
        link = self.page.locator(".manual-toc ol ol a").nth(2)
        target = link.get_attribute("href")[1:]
        link.click()
        self.assertTrue(self.page.locator(f'[id="{target}"]').is_visible())


class OldAddressesTests(BrowserTestCase):
    """Without the bypass of the policy: the script of the page is allowed to do this."""

    def test_an_old_address_with_an_anchor_is_forwarded(self) -> None:
        self.open("/manual/#7-projekte-planen")
        self.page.wait_for_url(re.compile(r".*/manual/7/#7-projekte-planen$"))
        self.assertTrue(self.page.locator('[id="7-projekte-planen"]').is_visible())

    def test_a_section_anchor_finds_its_chapter(self) -> None:
        self.open("/manual/")
        anchor = self.page.evaluate(
            "async () => { const r = await fetch('/manual/anchors/'); const d = await r.json();"
            " return Object.keys(d.chapters).find(k => d.chapters[k] === 8 && !/^8-/.test(k)); }"
        )
        self.open(f"/manual/#{anchor}")
        self.page.wait_for_url(re.compile(r".*/manual/8/#.+"))

    def test_an_unknown_anchor_stays_on_the_contents(self) -> None:
        self.open("/manual/#gibt-es-nicht")
        self.page.wait_for_load_state("networkidle")
        self.assertTrue(self.page.url.endswith("/manual/#gibt-es-nicht"))
        self.assertEqual(self.page.locator(".manual-chapter-link").count(), 18)
