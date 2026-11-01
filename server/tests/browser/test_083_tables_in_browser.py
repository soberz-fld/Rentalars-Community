# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "tables", in a real browser: "Gruppieren nach" offers every shown column (UIX-044).

A column grouped in Python (the rental days of the projects, the content of the project templates) and one grouped
by its day (the start) apply at once and pass axe-core on a desk and on a phone, without horizontal scrolling.
"""

from __future__ import annotations

from rentalars.projects.models import ProjectTemplate
from tests.browser.test_081_ui_in_browser import UiInBrowserCase
from tests.helpers import at, make_project


class EveryColumnGroupsInBrowserTests(UiInBrowserCase):
    """UIX-044."""

    def setUp(self) -> None:
        super().setUp()
        make_project("Stadtfest", start=at(10), end=at(12))
        make_project("Kongress", start=at(10), end=at(14))
        ProjectTemplate.objects.create(name="Bühne klein", content={"groups": [], "lines": []})

    def test_a_computed_column_groups_at_once_and_passes_axe(self) -> None:
        self.open("/projects/?cols=number,name,rental_days")
        options = self.page.locator("#group-projects option").evaluate_all("nodes => nodes.map(n => n.value)")
        self.assertEqual(options, ["", "number", "name", "rental_days"])
        self.page.select_option("#group-projects", "rental_days")
        self.page.wait_for_url("**group=rental_days**")
        headings = self.page.locator("tr.table-group th")
        self.assertGreaterEqual(headings.count(), 2)
        self.assertRegex(headings.first.inner_text(), r"\d+ Eintr(ag|äge)$")
        self.axe()

    def test_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 375, "height": 800})
        for path in ("/projects/?group=period", "/projects/templates/?group=content", "/customers/?group=name"):
            with self.subTest(page=path):
                self.open(path)
                self.page.wait_for_load_state("networkidle")
                width = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(width, 375)
                self.axe()
