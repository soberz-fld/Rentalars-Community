# SPDX-License-Identifier: GPL-3.0-or-later
"""NFA-025: the pages checked with axe-core against WCAG 2.1 level A and AA.

axe-core is the checker that browser tools for accessibility are built on.
It is not part of Rentalars (it has a licence of its own, MPL 2.0); the test
runs when it is at hand and is skipped otherwise::

    npm pack axe-core@4.10.2 && tar xzf axe-core-4.10.2.tgz
    RENTALARS_AXE=$PWD/package/axe.min.js python manage.py test tests.browser.test_accessibility_in_browser

What a program cannot judge – whether a text alternative says the right
thing, whether the order of reading makes sense – was looked at by hand; see
docs/dev/accessibility.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import SkipTest

from django.conf import settings

from rentalars.customers.models import Customer
from rentalars.material.models import MaterialItem
from rentalars.personnel.models import Person
from tests.browser.base import BrowserTestCase

WCAG_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]


def _axe_path() -> Path | None:
    named = os.environ.get("RENTALARS_AXE")
    candidates = [Path(named)] if named else []
    candidates.append(Path(settings.BASE_DIR) / "node_modules" / "axe-core" / "axe.min.js")
    return next((path for path in candidates if path.is_file()), None)


class AccessibilityInBrowserTests(BrowserTestCase):
    """Every main page without a finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see the docstring of this module).")
        super().setUpClass()

    def pages(self) -> list[str]:
        project = self.project.pk
        item = MaterialItem.objects.filter(material_model__default_product__isnull=False).first()
        product = item.material_model.default_product
        person = Person.objects.first()
        customer = Customer.objects.first()
        return [
            "/",
            "/projects/",
            f"/projects/{project}/",
            f"/projects/{project}/deployment/",
            f"/projects/{project}/packlist/",
            f"/projects/{project}/prices/",
            f"/projects/{project}/documents/",
            "/schedule/?view=month",
            "/schedule/?view=week",
            "/schedule/timeline/",
            "/schedule/personnel/",
            "/products/",
            f"/products/{product.pk}/",
            f"/products/{product.pk}/timeline/",
            "/material/",
            f"/material/items/{item.pk}/",
            f"/material/items/{item.pk}/timeline/",
            "/material/inspections/",
            "/material/import/",
            "/customers/",
            f"/customers/{customer.pk}/",
            "/personnel/",
            f"/personnel/people/{person.pk}/",
            f"/personnel/people/{person.pk}/timeline/",
            "/times/",
            "/times/approval/",
            "/times/report/",
            # "My area" (UIX-026), with the repetition of an entry open.
            "/me/availability/",
            "/me/",
            "/customers/venues/",
            "/shortages/",
            "/notifications/",
            "/administration/",
            "/administration/settings/",
            "/import/customers/",
            "/account/",
        ]

    def findings(self, path: str) -> list[str]:
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        self.page.add_script_tag(path=str(self.axe))
        result = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        return [f"{path}: {finding}" for finding in result]

    def test_main_pages(self) -> None:
        findings: list[str] = []
        for path in self.pages():
            findings += self.findings(path)
        self.assertEqual(findings, [], "\n".join(findings))

    def test_login_page(self) -> None:
        self.page.context.clear_cookies()
        self.assertEqual(self.findings("/login/"), [])


class PagesOf090Tests(BrowserTestCase):
    """With content, checked once (not in every subclass of :class:`AccessibilityInBrowserTests`).

    The logistics with a booking on a trip, its dialogs, the fleet, inquiries
    noted by hand, template texts, the monthly statements.
    """

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see the docstring of this module).")
        super().setUpClass()

    findings = AccessibilityInBrowserTests.findings

    def test_pages_of_090(self) -> None:
        from rentalars.projects import course, logistics
        from rentalars.projects.models import PhaseKind
        from tests.helpers import ALL_RIGHTS, at
        from tests.unit.test_090_logistics import make_fleet

        fleet = make_fleet()
        phase = course.add_phase(
            self.project, kind=PhaseKind.SETUP, start=self.project.start, end=self.project.start + (at(10, 4) - at(10))
        )
        car = logistics.add_vehicle_line(self.project, rights=ALL_RIGHTS, product=fleet["car"], item=fleet["van"])
        trailer = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=fleet["trailer"], item=fleet["box"]
        )
        use = logistics.add_trip_vehicle(
            self.project, rights=ALL_RIGHTS, trip_key=f"to_venue-{phase.pk}", vehicle_line=car, trailer_line=trailer
        )
        project = self.project.pk
        findings: list[str] = []
        for path in [
            f"/projects/{project}/",
            f"/projects/{project}/logistics/{car.pk}/",
            f"/projects/{project}/logistics/trips/{use.pk}/",
            f"/projects/{project}/prices/",
            "/material/fleet/",
            "/material/fleet/utilization/",
            f"/material/items/{fleet['van'].pk}/",
            f"/material/models/{fleet['van'].material_model_id}/",
            "/projects/inquiries/new/",
            "/administration/document-templates/default-texts/",
            # DOK-019: the monthly statement moved to "Buchhaltung", next to the outgoing documents.
            "/accounting/monthly/",
            "/accounting/documents/",
        ]:
            findings += self.findings(path)
        self.assertEqual(findings, [], "\n".join(findings))


class KeyboardTests(BrowserTestCase):
    """What does not need axe-core."""

    def test_the_keyboard_can_skip_the_navigation(self) -> None:
        """WCAG 2.4.1: the first stop of the Tab key leads straight to the content."""
        self.open(f"/projects/{self.project.pk}/")
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate("document.activeElement.textContent"), "Zum Inhalt springen")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "content")
