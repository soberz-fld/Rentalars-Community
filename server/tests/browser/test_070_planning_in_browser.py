# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the colours of the personnel plan (VFG-027), the material utilization in hours (VFG-029),
the asterisk that follows the form (UIX-035), the buttons of a mailbox – and axe-core on these pages."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.projects.models import CrewLine, OpenItem, ProjectStatus
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import add_line, at, make_person, make_project, make_stock, plan
from tests.mailbox import add_mailbox

#: The look of the first bar that matches a selector: band, fill, height.
LOOK = """(selector) => {
  const bar = document.querySelector(selector);
  const style = getComputedStyle(bar);
  const panel = getComputedStyle(bar.closest('.panel') || document.body);
  return {
    band: style.borderLeftWidth, bandColour: style.borderLeftColor, fill: style.backgroundColor,
    panel: panel.backgroundColor, height: bar.getBoundingClientRect().height,
  };
}"""


class PlanningInBrowserTests(BrowserTestCase):
    """VFG-027, VFG-029 and UIX-035 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def axe_findings(self, within: str = "") -> list[str]:
        """What axe-core finds on the page, or only within the elements a selector names."""
        self.page.wait_for_load_state("networkidle")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run(within ? {include: [[within]]} : document,"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )

    def test_the_bars_of_the_personnel_plan_are_coloured(self) -> None:
        anna = make_person("Anna Krause", rates={"Lichttechnik": "35.00"})
        for status, day in ((ProjectStatus.INQUIRY, 2), (ProjectStatus.OPTION, 3), (ProjectStatus.OUT, 4)):
            project = make_project(f"Projekt {day}", start=at(day, 8), end=at(day, 22))
            plan(project, "Lichttechnik", anna, start=at(day, 8), end=at(day, 18))
            type(project).objects.filter(pk=project.pk).update(status=status)
        requested = plan(
            make_project("Gala", start=at(5, 8), end=at(5, 22)), "Lichttechnik", anna, start=at(5, 8), end=at(5, 18)
        )
        CrewLine.objects.filter(pk=requested.pk).update(request_status="requested")
        self.open("/schedule/personnel/?weeks=1&from=2027-03-01")
        firm = self.page.evaluate(LOOK, ".tl-deploy .tl-bar.crew.status-out")
        # Firm is orange even while the project is out; the bar is filled, its band 6 px wide.
        self.assertEqual((firm["band"], firm["bandColour"]), ("6px", "rgb(238, 89, 31)"))
        self.assertNotEqual(firm["fill"], firm["panel"])
        self.assertGreaterEqual(firm["height"], 24)
        self.assertEqual(
            self.page.evaluate(LOOK, ".tl-deploy .tl-bar.crew.status-option")["bandColour"], "rgb(244, 194, 13)"
        )
        self.assertEqual(
            self.page.evaluate(LOOK, ".tl-deploy .tl-bar.crew.status-inquiry")["bandColour"], "rgb(114, 114, 114)"
        )
        self.assertEqual(
            self.page.evaluate(
                "() => getComputedStyle(document.querySelector('.tl-deploy .tl-bar.requested')).borderLeftStyle"
            ),
            "dashed",
        )
        sample = self.page.evaluate(LOOK, ".plan-legend .tl-bar.legend.crew.status-confirmed")
        self.assertEqual(sample["band"], "6px")
        self.assertGreaterEqual(sample["height"], 22)
        self.assertEqual(self.axe_findings(), [])
        # The same in the light theme (prepared, used for printing): the text stays readable on every fill.
        self.page.evaluate("() => { document.documentElement.dataset.theme = 'light'; }")
        self.assertEqual(self.axe_findings(".personnel-plan"), [])
        self.assertEqual(self.axe_findings(".plan-legend"), [])

    def test_the_utilization_in_hours_moves_on_with_the_search(self) -> None:
        spot = make_stock("L-090", 10, "Moving Head Spot")
        add_line(make_project("Vortrag", start=at(10, 8), end=at(10, 12)), spot, 4)
        self.open("/schedule/products/?q=Moving&days=4&from=2027-03-10")
        # VFG-033: four days and two spans before and after them, in three-hour columns.
        self.assertEqual(self.page.locator("[data-tl-zoom]").get_attribute("data-columns"), "160")
        self.assertEqual(self.axe_findings(), [])
        # Scrolling to the left end loads the span before; the search then keeps the new span.
        self.page.evaluate("() => { const panel = document.querySelector('[data-tl-zoom]'); panel.scrollLeft = 0; }")
        self.page.wait_for_url("**/schedule/products/?*from=2027-03-06*")
        self.assertEqual(self.page.locator('input[name="from"][form="f-search"]').input_value(), "2027-03-06")
        field = self.page.locator("#f-q")
        field.fill("")
        field.press_sequentially("Moving", delay=20)
        self.page.locator(".typeahead [role=option]").first.wait_for()
        field.press("Enter")
        self.page.wait_for_url("**/schedule/products/?*product=*")
        self.assertIn("from=2027-03-06", self.page.url)
        self.assertIn("days=4", self.page.url)

    def test_the_asterisk_follows_the_kind_of_product(self) -> None:
        self.open("/products/new/")
        price, sale = self.page.locator("#id_price"), self.page.locator("#id_sale_price")
        mark = "(id) => !document.querySelector('label[for=' + id + '] .required').classList.contains('hidden')"
        self.assertTrue(self.page.evaluate(mark, "id_price"))
        self.assertFalse(self.page.evaluate(mark, "id_sale_price"))
        self.assertEqual((price.evaluate("e => e.required"), sale.evaluate("e => e.required")), (True, False))
        self.page.select_option("#id_kind", "sale")
        # PRD-046: the kind comes first; choosing it reloads a new product's form with its presets.
        self.page.wait_for_url("**/products/new/?kind=sale")
        self.assertFalse(self.page.evaluate(mark, "id_price"))
        self.assertTrue(self.page.evaluate(mark, "id_sale_price"))
        self.assertEqual((price.evaluate("e => e.required"), sale.evaluate("e => e.required")), (False, True))
        self.assertEqual(self.page.locator(".required-note").count(), 1)
        self.assertEqual(self.axe_findings(), [])

    def test_the_open_items_with_shortages(self) -> None:
        spot = make_stock("L-090", 2, "Moving Head Spot")
        festival = make_project("Fest", start=at(10, 8), end=at(12, 22), status=ProjectStatus.CONFIRMED_OPEN)
        OpenItem.objects.create(project=festival, text="Strom klären")
        line = add_line(festival, spot, 5).line
        self.open("/projects/open-items/")
        self.assertEqual(self.axe_findings(), [])
        self.page.click("text=Fehlbestand: 3 × Moving Head Spot")
        self.page.wait_for_url(f"**/projects/{festival.number}/#line-{line.pk}")
        self.assertTrue(self.page.evaluate(f"() => document.querySelector('#line-{line.pk}').matches(':target')"))

    def test_the_buttons_of_a_mailbox_stand_side_by_side(self) -> None:
        add_mailbox("Projekte", "projekte@verleih.example")
        for width in (1360, 360):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.open("/administration/mail/")
                boxes = self.page.evaluate(
                    "() => [...document.querySelectorAll('.cell-buttons .btn')].map(b => b.getBoundingClientRect())"
                    ".map(r => ({top: Math.round(r.top), height: Math.round(r.height)}))"
                )
                self.assertEqual(len(boxes), 2)
                self.assertEqual(boxes[0], boxes[1])
