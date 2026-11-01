# SPDX-License-Identifier: GPL-3.0-or-later
"""The price overview and the documents of a whole project with subprojects in a real browser (PRJ-046, NFA-025).

The sample festival "Stadtfest Hauptbühne" gets two stages; the second takes
over the moving heads of the first. Checked with axe-core (see
``tests.browser.test_accessibility_in_browser``) and at the width of a phone.
"""

from __future__ import annotations

from typing import Any

from rentalars.projects import services
from rentalars.projects.models import Project
from tests.browser import test_accessibility_in_browser as accessibility
from tests.browser.base import BrowserTestCase
from tests.helpers import ALL_RIGHTS


def add_stages(project: Project) -> tuple[Project, Project]:
    """Two stages of the sample festival, the second taking over the moving heads of the first."""
    first = services.create_subproject(
        project, name="Bühne Schlosspark", end=project.start + (project.end - project.start) / 2
    )
    second = services.create_subproject(project, name="Bühne Hafen", start=first.end, venue="Hafenbecken")
    source = project.material_lines.filter(product__isnull=False, group__isnull=False).order_by("position").first()
    group = services.add_group(first, rights=ALL_RIGHTS, name="Licht")
    line = services.add_line(first, rights=ALL_RIGHTS, product=source.product, quantity=source.quantity, group=group)
    services.take_over_line(line.line, second, rights=ALL_RIGHTS)
    return first, second


class FamilyPricesInBrowserTests(BrowserTestCase):
    """The blocks of the parts fit a phone."""

    viewport: Any = {"width": 360, "height": 740}

    def test_the_price_overview_with_parts_fits_the_width_of_a_phone(self) -> None:
        first, _second = add_stages(self.project)
        for path in (
            f"/projects/{self.project.pk}/prices/",
            f"/projects/{self.project.pk}/prices/?detail=groups",
            f"/projects/{first.pk}/prices/",
            f"/projects/{self.project.pk}/documents/",
            f"/projects/{first.pk}/documents/",
        ):
            with self.subTest(page=path):
                self.open(path)
                width = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(width, 360, f"{path} is {width} pixels wide")


class FamilyPricesAccessibilityTests(accessibility.AccessibilityInBrowserTests):
    """NFA-025: the price overview and the documents tab of a whole project and of a part, checked with axe."""

    def setUp(self) -> None:
        super().setUp()
        self.first, self.second = add_stages(self.project)

    def pages(self) -> list[str]:
        return [
            f"/projects/{self.project.pk}/prices/",
            f"/projects/{self.second.pk}/prices/",
            f"/projects/{self.project.pk}/documents/",
            f"/projects/{self.first.pk}/documents/",
        ]
