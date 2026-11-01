# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the add forms of the planning, the warning of the project form (tests/unit/test_095_project_pages.py).

Only a browser shows that the fields of "Personal" and "Logistik" stand on one line – whatever help text a field has –,
that the buttons and the tick "Fest eingeplant" line up with them, that nothing scrolls sideways on a phone, that the
warning "Veranstaltung endet nach „Material zurück bis“" comes and goes while the fields are typed, and – with axe-core
(RENTALARS_AXE, see tests/browser/test_accessibility_in_browser.py) – that the pages meet WCAG 2.1 AA.
"""

from __future__ import annotations

from typing import Any
from unittest import SkipTest

from rentalars.projects import course
from rentalars.projects.models import PhaseKind
from tests.browser import test_accessibility_in_browser as accessibility  # a module: its tests do not run here
from tests.browser.base import BrowserTestCase
from tests.unit.test_090_logistics import make_fleet

#: What stands in the row of fields: inputs, selects and buttons (not the tick, not hidden or detached inputs).
CONTROLS = "input:not([type=hidden]):not([type=checkbox]), select, button.btn"


class AddFormsInBrowserTests(BrowserTestCase):
    """Add forms of the planning: one line for the fields, the buttons level with them."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def setUp(self) -> None:
        super().setUp()
        make_fleet()
        course.add_phase(self.project, kind=PhaseKind.SETUP, start=self.project.start, end=self.project.end)

    def boxes(self, form: str) -> list[tuple[str, float, float]]:
        """Name, top and height of every control of a form that is on show."""
        return self.page.evaluate(
            """([css, controls]) => [...document.querySelector(css).querySelectorAll(controls)]
                .filter(e => e.offsetParent)
                .map(e => [e.name || e.textContent.trim(), e.getBoundingClientRect().top, e.getBoundingClientRect().height])""",
            [form, CONTROLS],
        )

    def assert_rows_level(self, form: str) -> list[float]:
        """Every control as high as a button, and those of one row at the same top; returns the tops of the rows."""
        rows: list[float] = []
        for name, top, height in self.boxes(form):
            self.assertAlmostEqual(height, 40, delta=1, msg=f"{form}: {name}")
            if not any(abs(top - row) < 1.5 for row in rows):
                rows.append(top)
        return rows

    def test_wide_screen(self) -> None:
        self.page.set_viewport_size({"width": 1676, "height": 900})
        self.open_planning()
        for form, rows in (("form.crew-add", 2), ("form.vehicle-add", 1)):
            self.assertEqual(len(self.assert_rows_level(form)), rows, form)
        # The calendar button is in the group of buttons; the help is below it and does not move a field.
        self.assertEqual(self.page.locator("form.crew-add .add-actions .range-btn").count(), 1)
        self.assertEqual(self.page.locator("form.vehicle-add .add-actions .range-btn").count(), 1)
        tops = {name: top for name, top, _height in self.boxes("form.crew-add")}
        self.assertAlmostEqual(tops["job_function"], tops["phase"], delta=1)
        self.assertAlmostEqual(tops["Zeitraum im Kalender wählen"], tops["Einplanen"], delta=1)
        # The tick stands at the height of the buttons.
        tick = self.page.locator("form.crew-add .crew-firm input").bounding_box()
        button = self.page.locator("form.crew-add .add-actions .range-btn").bounding_box()
        self.assertAlmostEqual(tick["y"] + tick["height"] / 2, button["y"] + button["height"] / 2, delta=2)

    def test_phone(self) -> None:
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.open_planning()
        for form in ("form.crew-add", "form.vehicle-add"):
            self.assert_rows_level(form)
            boxes = self.boxes(form)
            self.assertEqual(
                len({round(top) for _name, top, _height in boxes}), len(boxes), form
            )  # one below the other
        self.assertTrue(self.page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"))

    def test_accessibility(self) -> None:
        findings: list[str] = []
        for width in (1676, 390):
            self.page.set_viewport_size({"width": width, "height": 900})
            self.open_planning()
            self.settle()
            self.page.add_script_tag(path=str(self.axe))
            found: Any = self.page.evaluate(
                "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
                ".map(v => v.id + ': ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
                accessibility.WCAG_AA,
            )
            findings += [f"{width}px: {finding}" for finding in found]
        self.assertEqual(findings, [], "\n".join(findings))


class EventWarningInBrowserTests(BrowserTestCase):
    """PRJ-005 (event end; PRJ-127): the warning appears while the end of the event is typed, and saving works."""

    def test_live_warning(self) -> None:
        self.open(f"/projects/{self.project.pk}/edit/")
        warning = self.page.locator("[data-event-warning]")
        end = self.page.locator("#id_end").input_value()
        self.assertFalse(warning.is_visible())
        later = f"{end[:8]}{int(end[8:10]) + 1:02d}{end[10:]}"
        self.page.fill("#id_event_end", later)
        self.assertTrue(warning.is_visible())
        self.assertIn("Veranstaltung endet nach „Material zurück bis“", warning.inner_text())
        self.page.fill("#id_event_end", end)
        self.assertFalse(warning.is_visible())
        self.page.fill("#id_event_start", self.page.locator("#id_start").input_value())  # both or neither
        self.page.fill("#id_event_end", later)
        self.page.click("button[type=submit].btn")  # saving is possible; the message is on the next page
        self.page.wait_for_url(f"{self.live_server_url}/projects/{self.project.number}/")
        self.assertIn("Veranstaltung endet nach „Material zurück bis“", self.page.inner_text("body"))
