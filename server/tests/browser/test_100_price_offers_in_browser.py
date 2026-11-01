# SPDX-License-Identifier: GPL-3.0-or-later
"""Price offers of freelancers in a real browser (PER-038): switch, offer, accept, marker.

The administrator switches the feature on in "Einstellungen → Preisangebote"; a freelancer (a second browser
window with their own login) asked for a deployment names a price instead of accepting; the planner accepts it
in the planning without a page load (htmx) and sees the marker next to the costs. Every page of the way is
checked with axe-core (WCAG 2.1 A/AA, see ``tests.browser.test_accessibility_in_browser``) and the pages fit a
phone. The freelancer does not see the stored rate where the setting says so.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest import SkipTest

from rentalars.accounts.models import User
from rentalars.core.models import SystemSettings
from rentalars.personnel.models import EmploymentKind
from rentalars.personnel.offer_models import OfferSettings, OfferStatus, PriceOffer
from rentalars.projects import crew
from tests.browser import test_accessibility_in_browser as accessibility
from tests.browser.base import BrowserTestCase
from tests.helpers import PASSWORD, at, job_function, make_person, make_user, plan


class PriceOffersInBrowserTests(BrowserTestCase):
    """The way a planner and a freelancer do it."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        super().setUpClass()

    def setUp(self) -> None:
        super().setUp()
        system = SystemSettings.load()
        system.people_see_own_rates = False
        system.save()
        self.account = make_user("frieda", roles=("Freie Kraft",))
        self.person = make_person("Frieda Frei", user=self.account, kind=EmploymentKind.FREELANCER)
        function = job_function("Tontechnik", guide="30.00")
        self.line = plan(self.project, function, self.person, start=at(10, 10), end=at(10, 18))
        self.line.hourly_rate = Decimal("30.00")
        self.line.save()
        crew.request_deployment(self.line, user=User.objects.get(username="anna"))
        # The freelancer's own window.
        context = self.browser.new_context(
            viewport={"width": 390, "height": 800},
            locale="de-DE",
            bypass_csp=True,  # type: ignore[arg-type]
        )
        self.addCleanup(context.close)
        self.freelancer = context.new_page()
        self.freelancer.set_default_timeout(10_000)
        self.freelancer.on("pageerror", lambda error: self.problems.append(f"script error (freelancer): {error}"))
        self.freelancer.route(
            "**/changes/?*",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"stamps": {}, "unread": 0}'
            ),
        )
        self.freelancer.goto(f"{self.live_server_url}/login/")
        self.freelancer.fill("#id_username", "frieda")
        self.freelancer.fill("#id_password", PASSWORD)
        self.freelancer.click("button[type=submit]")
        self.freelancer.wait_for_url(f"{self.live_server_url}/**")

    def findings(self, page: Any) -> list[str]:
        """The findings of axe on the page as it is now."""
        if self.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        page.wait_for_load_state("networkidle")
        page.add_script_tag(path=str(self.axe))
        return page.evaluate(  # type: ignore[no-any-return]
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            accessibility.WCAG_AA,
        )

    def no_horizontal_scroll(self, page: Any) -> None:
        """The page fits the window (a phone for the freelancer)."""
        wider = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        self.assertLessEqual(wider, 1, "the page scrolls sideways")

    def test_switch_on_offer_and_accept(self) -> None:
        findings: dict[str, list[str]] = {}

        # 1. The administrator switches the feature on.
        self.open("/administration/price-offers/")
        self.page.wait_for_selector("h1:has-text('Preisangebote freier Kräfte')")
        self.assertFalse(OfferSettings.load().enabled)
        findings["settings"] = self.findings(self.page)
        self.page.check("input[name='enabled']")
        self.page.fill("input[name='max_percent']", "150")
        self.page.click("button:has-text('Einstellungen speichern')")
        self.page.wait_for_selector("text=Einstellungen gespeichert")
        self.assertTrue(OfferSettings.load().enabled)

        # 2. The freelancer names a price instead of accepting.
        self.freelancer.goto(f"{self.live_server_url}/projects/{self.project.pk}/deployment/")
        self.freelancer.wait_for_selector("text=Preisangebot machen")
        findings["deployment before"] = self.findings(self.freelancer)
        self.no_horizontal_scroll(self.freelancer)
        self.freelancer.click("a:has-text('Preisangebot machen')")
        self.freelancer.wait_for_selector("h1:has-text('Preisangebot machen')")
        self.assertNotIn("30,00", self.freelancer.inner_text("body"))  # the stored rate stays hidden
        findings["offer form"] = self.findings(self.freelancer)
        self.no_horizontal_scroll(self.freelancer)
        self.freelancer.fill("input[name='amount']", "42.50")
        self.freelancer.fill("textarea[name='message']", "Wegen der Nachtarbeit")
        self.freelancer.click("button:has-text('Angebot senden')")
        self.freelancer.wait_for_selector("text=wartet auf Antwort")
        self.assertIn("Angebot zurückziehen", self.freelancer.inner_text("body"))
        findings["deployment after"] = self.findings(self.freelancer)
        self.no_horizontal_scroll(self.freelancer)
        offer = PriceOffer.objects.get()
        self.assertEqual((offer.amount, offer.status), (Decimal("42.50"), OfferStatus.OPEN))

        # 3. The planner sees it in the planning and in the overview, and accepts without a page load.
        self.open_planning()
        self.settle()
        box = self.page.locator(f'[data-crew-line="{self.line.pk}"] [data-offer-planning]')
        box.wait_for()
        self.assertIn("42,50", box.inner_text())
        self.assertIn("hinterlegt: 30,00", box.inner_text())
        findings["planning with offer"] = self.findings(self.page)
        self.open("/personnel/offers/")
        self.page.wait_for_selector("h1:has-text('Preisangebote')")
        self.assertIn("Frieda Frei", self.page.inner_text("body"))
        findings["overview"] = self.findings(self.page)

        self.open_planning()
        self.settle()
        self.page.evaluate("window.__marker = 'same page'")
        self.page.locator(
            f'[data-crew-line="{self.line.pk}"] [data-offer-planning] button:has-text("Angebot annehmen")'
        ).click()
        self.page.wait_for_selector(f'[data-crew-line="{self.line.pk}"] [data-offer-mark]')
        self.assertEqual(self.page.evaluate("window.__marker"), "same page")  # no page load
        mark = self.text_of(f'[data-crew-line="{self.line.pk}"] [data-offer-mark]')
        self.assertIn("42,50", mark)
        self.assertIn("hinterlegt: 30,00", mark)
        self.assertIn("zugesagt", self.text_of(f'[data-crew-line="{self.line.pk}"]'))
        findings["planning with marker"] = self.findings(self.page)
        self.line.refresh_from_db()
        self.assertEqual(self.line.hourly_rate, Decimal("42.50"))

        # 4. The freelancer reads the answer.
        self.freelancer.goto(f"{self.live_server_url}/projects/{self.project.pk}/deployment/")
        self.freelancer.wait_for_selector("text=Angebot")
        self.no_horizontal_scroll(self.freelancer)
        findings["deployment accepted"] = self.findings(self.freelancer)

        self.assertEqual({name: found for name, found in findings.items() if found}, {})
