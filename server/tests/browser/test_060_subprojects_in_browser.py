# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: a part of a whole project, the overview and material taken over (PRJ-044 to PRJ-047, PRJ-060).

The sample project "Stadtfest Hauptbühne" becomes a whole project: a stage
"Bühne Marktplatz" is added in the set-up with six moving heads for the first
day. The tests add a second stage through the form, open the overview of the
whole project, take the moving heads over into the second stage through the
dialog of its planning – and check the overview and the planning with the
dialog open with axe-core (NFA-025).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest import SkipTest

from django.utils import timezone

from rentalars.products.models import Product
from rentalars.projects import services
from rentalars.projects.models import MaterialLine, Project
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import ALL_RIGHTS


def local(moment: datetime.datetime) -> str:
    """A moment as a field of the type datetime-local wants it."""
    return timezone.localtime(moment).strftime("%Y-%m-%dT%H:%M")


class SubprojectBrowserTestCase(BrowserTestCase):
    """The sample project as a whole project with a first stage that has six moving heads."""

    def setUp(self) -> None:
        super().setUp()
        whole = self.project
        self.first_day_end = whole.start + datetime.timedelta(days=1)
        self.market = services.create_subproject(
            whole, name="Bühne Marktplatz", start=whole.start, end=self.first_day_end
        )
        self.heads = Product.objects.get(article_number="L-020")  # "Moving Head Spot"
        self.source = services.add_line(self.market, rights=ALL_RIGHTS, product=self.heads, quantity=Decimal("6")).line

    def add_second_stage(self) -> Project:
        """Add "Bühne Schlosspark" through the form, from the second day to the end."""
        self.open(f"/projects/{self.project.pk}/subprojects/new/")
        self.page.fill("[name=name]", "Bühne Schlosspark")
        start, end = self.page.locator("[name=start]"), self.page.locator("[name=end]")
        start.fill(local(self.first_day_end + datetime.timedelta(hours=4)))
        start.dispatch_event("change")
        end.fill(local(self.project.end))
        end.dispatch_event("change")
        self.page.locator("form.form button[type=submit]").last.click()
        self.page.wait_for_url("**/projects/**")
        self.settle()
        return Project.objects.get(name="Bühne Schlosspark")

    def open_takeover_dialog(self, part: Project) -> None:
        self.open(f"/projects/{part.pk}/")
        self.settle()
        self.page.locator("button", has_text="Aus anderem Teilprojekt übernehmen").click()
        self.page.locator("dialog#dialog[open] .takeover-dialog").wait_for()


class SubprojectsInBrowserTests(SubprojectBrowserTestCase):
    def test_a_part_through_the_form_the_overview_and_a_take_over(self) -> None:
        park = self.add_second_stage()
        self.assertEqual((park.parent, park.number), (self.project, f"{self.project.number}-2"))
        self.assertIn("Teilprojekt", self.text_of("h1"))

        # The overview of the whole project: both stages and their sum.
        self.open(f"/projects/{park.pk}/parts/")
        overview = self.text_of(".family-table")
        for text in (self.market.number, park.number, "Gesamtprojekt mit allen Teilen"):
            self.assertIn(text, overview)
        self.assertIn(park.number, self.text_of(".family-table tr.is-current"))

        # Take the moving heads over through the dialog of the planning.
        self.open_takeover_dialog(park)
        row = self.page.locator(".takeover-sources tbody tr", has_text=self.market.number).filter(
            has_text=self.heads.article_number
        )
        row.locator("input[name=quantity]").fill("4")
        with self.page.expect_response(lambda response: "/lines/take-over/" in response.url):
            row.locator("button[type=submit]").click()
        self.settle()
        self.page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000)
        line = MaterialLine.objects.get(project=park, taken_over_from=self.source)
        self.assertEqual(line.quantity, Decimal("4"))
        row_text = self.page.inner_text(f'tr[data-line="{line.pk}"]')
        self.assertIn("übernommen", row_text)
        self.assertIn(self.market.number, row_text)


class SubprojectsAccessibilityTests(SubprojectBrowserTestCase):
    """NFA-025: the overview of a whole project and the take-over dialog, checked with axe-core."""

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

    def test_the_overview_and_the_take_over_dialog(self) -> None:
        park = services.create_subproject(
            self.project,
            name="Bühne Schlosspark",
            start=self.first_day_end + datetime.timedelta(hours=4),
            end=self.project.end,
        )
        found: list[str] = []
        self.open(f"/projects/{self.project.pk}/parts/")
        self.page.wait_for_load_state("networkidle")
        found += self.findings("overview")
        self.open_takeover_dialog(park)
        found += self.findings("planning with the take-over dialog")
        self.assertEqual(found, [], "\n".join(found))
