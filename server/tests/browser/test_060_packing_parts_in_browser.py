# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: handovers between subprojects and the packlist of the whole project (PRJ-048, PRJ-060).

The sample project "Stadtfest Hauptbühne" becomes a whole project with two
stages. The six moving heads of the first stage go on to the second; the
first stage's packlist is issued in the set-up. The tests book the arrival on
the second stage's packlist and take it back – both answered in place by
htmx – and check the packlist with a takeover and the packlist of the whole
project with axe-core (NFA-025).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest import SkipTest

from rentalars.packing.models import Handover
from rentalars.packing.services import get_packlist, issue
from rentalars.products.models import Product
from rentalars.projects import services
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import ALL_RIGHTS


class PackingPartsBrowserTestCase(BrowserTestCase):
    """Two stages of the sample project; the moving heads go from the first straight on to the second."""

    def setUp(self) -> None:
        super().setUp()
        whole = self.project
        first_day_end = whole.start + datetime.timedelta(days=1)
        self.market = services.create_subproject(whole, name="Bühne Marktplatz", start=whole.start, end=first_day_end)
        self.park = services.create_subproject(
            whole, name="Bühne Schlosspark", start=first_day_end + datetime.timedelta(hours=4), end=whole.end
        )
        self.heads = Product.objects.get(article_number="L-020")  # "Moving Head Spot"
        source = services.add_line(self.market, rights=ALL_RIGHTS, product=self.heads, quantity=Decimal("6")).line
        self.taking = services.take_over_line(source, self.park, rights=ALL_RIGHTS).line
        issue(get_packlist(self.market))

    def takeover_row(self) -> object:
        return self.page.locator(".pack-row.is-takeover").first


class HandoverInBrowserTests(PackingPartsBrowserTestCase):
    def test_book_and_take_back_in_place(self) -> None:
        self.open(f"/projects/{self.park.pk}/packlist/")
        self.assertIn(f"Übernahme aus {self.market.number}", self.takeover_row().inner_text())
        form = self.takeover_row().locator("form.handover-form")
        form.locator("input[name=quantity]").fill("4")
        with self.page.expect_response(lambda response: "/handover/" in response.url):
            form.locator("button[type=submit]").click()
        self.settle()
        self.assertIn("4 von 6 übergeben", self.takeover_row().inner_text())
        self.assertIn(f"4 × L-020 aus {self.market.number} übergeben", self.text_of("#packlist .messages"))
        self.assertEqual(Handover.objects.get().quantity, 4)

        self.takeover_row().locator(".handover-bookings button").click()
        self.confirm()
        self.settle()
        self.takeover_row().locator("form.handover-form").wait_for()
        self.assertFalse(Handover.objects.exists())


class PackingPartsAccessibilityTests(PackingPartsBrowserTestCase):
    """NFA-025: the packlist with a takeover and the packlist of the whole project, checked with axe-core."""

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

    def test_packlists_of_the_parts_and_of_the_whole_project(self) -> None:
        found: list[str] = []
        for label, path in (
            ("packlist with a takeover", f"/projects/{self.park.pk}/packlist/"),
            ("packlist whose pieces go on", f"/projects/{self.market.pk}/packlist/?mode=return"),
            ("whole project by part", f"/projects/{self.project.pk}/packlist/family/?view=parts"),
            ("whole project by article", f"/projects/{self.project.pk}/packlist/family/?view=articles"),
        ):
            self.open(path)
            self.page.wait_for_load_state("networkidle")
            found += self.findings(label)
        self.assertEqual(found, [], "\n".join(found))
