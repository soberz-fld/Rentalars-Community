# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "services": the service form shows the hour tiers (PER-035) and its job function
(PRD-044); the job function form names its service product; the crew planning shows the hours beyond the limit –
on a phone without horizontal scrolling, checked with axe-core (NFA-025)."""

from __future__ import annotations

from typing import Any
from unittest import SkipTest

from rentalars.personnel.models import JobFunction
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import make_product


class ServicesInBrowserTests(BrowserTestCase):
    """PRD-044, PER-035: what the pages show, with the page script and axe."""

    bypass_csp = True

    def axe(self) -> list[Any]:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.add_script_tag(path=str(axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def test_the_hour_tiers_appear_for_a_service_only(self) -> None:
        transport = make_product("N-001", "Fahrerdienst", price="95.00", kind="incidental", billing_mode="flat")
        self.open(f"/products/{transport.pk}/edit/")
        limit = self.page.locator("input[name=hours_limit]")
        self.assertFalse(limit.is_visible())
        self.page.select_option("select[name=kind]", "service")
        limit.wait_for()
        self.assertTrue(self.page.locator("input[name=price_above_limit]").is_visible())
        self.assertTrue(self.page.get_by_text("gehört zu genau einer Funktion des Personals").is_visible())
        self.page.select_option("select[name=kind]", "incidental")
        limit.wait_for(state="hidden")
        findings = self.axe()
        self.assertEqual(findings, [], "\n".join(findings))

    def test_the_service_of_a_function_and_the_function_of_a_service(self) -> None:
        function = JobFunction.objects.get(name="Tontechniker")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(f"/personnel/functions/{function.pk}/")
        link = self.page.locator("#service-product a")
        self.assertIn(function.service_product.article_number, link.inner_text())
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 375)
        findings = self.axe()
        self.assertEqual(findings, [], "\n".join(findings))
        with self.page.expect_navigation():
            link.click()
        self.assertIn("/products/", self.page.url)
        self.assertIn("ab 10 Std. am Tag", self.text_of("main"))
        self.assertIn("Tontechniker", self.text_of("dl.facts"))

    def test_the_crew_planning_shows_the_hours_beyond_the_limit_on_a_phone(self) -> None:
        # The sample data: Anna works 14 hours on the show day as Tontechniker, from 10 hours a day 55,00.
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open_planning()
        self.page.wait_for_load_state("networkidle")
        tier = self.page.locator("#planning-crew [data-hours-above-limit]").first
        tier.scroll_into_view_if_needed()
        self.assertIn("über der Grenze", tier.inner_text())
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 375)
        findings = self.axe()
        self.assertEqual(findings, [], "\n".join(findings))
