# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "ui", in the browser – with axe-core: the hour lines of the timelines lie on their columns at every
width (VFG-033); on the phone the menu slides in from the right and goes again by tap, swipe, Escape and Back, while
the desktop keeps its side navigation (UIX-045); the correspondence of a project and of a service case with the block
"Zusammenfassung" and the folded short overview (EML-050)."""

from __future__ import annotations

import io
import time
from typing import Any, ClassVar

from PIL import Image

from rentalars.ai.models import AISummary
from rentalars.products.models import Product
from rentalars.projects import service_cases
from tests.browser.base import BrowserTestCase
from tests.browser.test_071_planning_in_browser import AxeMixin
from tests.helpers import make_person, plan
from tests.unit.test_083_ai import add_mail

#: Pure colours for the lines (geometry unchanged), white behind them, the bars out of the way: then every drawn line
#: is a run of non-white pixels in one pixel row of the screenshot.
LINES_ONLY = """
.timeline { --line: rgb(0, 200, 0) !important; --line-strong: rgb(255, 0, 0) !important; }
.timeline .tl-grid { --tl-hour-line: rgb(0, 0, 255) !important; }
.timeline .tl-row, .timeline .tl-hours-head { background-color: rgb(255, 255, 255) !important; }
.timeline .tl-row > * { visibility: hidden !important; }
"""
#: Where the columns are (the cells of the hour head are the grid's columns) and where to read the lines.
GEOMETRY = """() => {
  const panel = document.querySelector('[data-tl-zoom]');
  const row = panel.querySelector('.tl-row');
  row.scrollIntoView({block: 'center'});
  const box = panel.getBoundingClientRect();
  return {
    left: panel.querySelector('.tl-label').getBoundingClientRect().right,
    right: box.left + panel.clientWidth,
    row: row.getBoundingClientRect().top + 1,
    head: panel.querySelector('.tl-hour').getBoundingClientRect().top + 1,
    cells: [...panel.querySelectorAll('.tl-hour')].map(c => { const b = c.getBoundingClientRect(); return [b.left, b.width]; }),
  };
}"""
HOUR_LINE = "g => getComputedStyle(g).getPropertyValue('--tl-hour-line').trim()"


def _line_starts(png: bytes) -> list[int]:
    """The first pixel of every run of non-white pixels in a screenshot one pixel high."""
    strip = Image.open(io.BytesIO(png)).convert("RGB")
    starts, inside = [], False
    for x in range(strip.width):
        dark = sum(strip.getpixel((x, 0))) < 740
        if dark and not inside:
            starts.append(x)
        inside = dark
    return starts


class HourLinesInTheBrowserTests(AxeMixin, BrowserTestCase):
    """VFG-033 (amended): every line – day, column, hour – on its place, at 1236 to 1920 px of window."""

    def setUp(self) -> None:
        super().setUp()
        plan(self.project, "Stagehand", make_person("Paul Weber", rates={"Stagehand": "20.00"}))
        self.product = Product.objects.filter(kind="rental", is_active=True).first().pk

    def misplaced(self) -> list[str]:
        """Lines more than a pixel beside their place, or lines where none belongs – at the start, middle and end."""
        panel = self.page.locator("[data-tl-zoom]")
        hours = int(panel.get_attribute("data-hours"))
        width = self.page.viewport_size["width"]
        found = []
        end = panel.evaluate("p => p.scrollWidth - p.clientWidth")
        for part in (0, 0.5, 1):
            # Not right at the ends: there the next span is loaded (VFG-022) and the columns move.
            panel.evaluate("(p, x) => { p.scrollLeft = x; }", min(max(end * part, 3), end - 3))
            geometry = self.page.evaluate(GEOMETRY)
            expected = [left + size * step / hours for left, size in geometry["cells"] for step in range(hours)]
            expected = [x for x in expected if geometry["left"] + 3 <= x <= geometry["right"] - 3]
            self.assertGreater(len(expected), 20)
            for where in ("row", "head"):
                drawn = _line_starts(
                    self.page.screenshot(clip={"x": 0, "y": geometry[where], "width": width, "height": 1})
                )
                for x in expected:
                    off = min((abs(x - start) for start in drawn), default=99)
                    if off > 1:
                        found.append(f"{where} at {part:.1f}: line for {x:.1f} px is {off:.1f} px off")
                for start in drawn:
                    inside = geometry["left"] + 5 <= start <= geometry["right"] - 5
                    if inside and min(abs(start - x) for x in expected) > 1.5:
                        found.append(f"{where} at {part:.1f}: a line at {start} px where none belongs")
        return found

    def check(self, url: str, width: int) -> None:
        self.page.set_viewport_size({"width": width, "height": 900})
        self.open(url)
        self.assertNotIn(self.page.locator(".tl-grid").first.evaluate(HOUR_LINE), ("", "transparent"))  # lines shown
        self.page.add_style_tag(content=LINES_ONLY)
        self.assertEqual(self.misplaced(), [])

    def test_the_timeline_at_five_widths(self) -> None:
        """VFG-033: Planung → Zeitstrahl – no offset between about 1236 and 1920 px."""
        for width, days in ((1236, 4), (1366, 4), (1440, 5), (1600, 5), (1920, 7)):
            with self.subTest(width=width, days=days):
                self.check(f"/schedule/timeline/?days={days}&from=2027-03-09", width)

    def test_the_other_hour_views(self) -> None:
        """VFG-033: Personalplan, Materialauslastung and the timeline of the project's schedule."""
        for url, width in (
            ("/schedule/personnel/?days=5&from=2027-03-09", 1440),
            (f"/schedule/products/?days=5&from=2027-03-09&product={self.product}", 1600),
            (f"/projects/{self.project.pk}/course/?days=3&from=2027-03-09", 1920),
        ):
            with self.subTest(url=url, width=width):
                self.check(url, width)

    def test_still_accessible(self) -> None:
        self.page.set_viewport_size({"width": 1440, "height": 900})
        self.open("/schedule/timeline/?days=5&from=2027-03-09")
        self.assertEqual(self.axe_findings(".timeline"), [])


class PhoneMenuInTheBrowserTests(AxeMixin, BrowserTestCase):
    """UIX-045: on the phone the menu is a drawer from the right, as in the companion app."""

    viewport: ClassVar[dict[str, int]] = {"width": 390, "height": 800}

    def setUp(self) -> None:
        super().setUp()
        self.cdp = self.page.context.new_cdp_session(self.page)
        self.cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})

    # --- Helpers ---------------------------------------------------------------------------------------

    def touch(self, kind: str, x: float = 0, y: float = 0) -> None:
        points = [] if kind == "touchEnd" else [{"x": x, "y": y}]
        self.cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

    def swipe(self, start: float, end: float, *, y: float = 600, steps: int = 12, rest: float = 0.15) -> None:
        """A finger from start to end; it rests before letting go (no fling) unless rest is 0."""
        self.touch("touchStart", start, y)
        for step in range(1, steps + 1):
            self.touch("touchMove", start + (end - start) * step / steps, y)
            time.sleep(0.02)
        time.sleep(rest)
        self.touch("touchEnd")
        self.page.wait_for_timeout(350)

    def is_open(self) -> bool:
        return self.page.evaluate("document.body.classList.contains('nav-open')")

    def menu_state(self) -> dict[str, Any]:
        return self.page.evaluate(
            """() => {
              const nav = document.getElementById('sidebar'), box = nav.getBoundingClientRect();
              return {open: document.body.classList.contains('nav-open'), left: box.left, width: box.width,
                      visibility: getComputedStyle(nav).visibility, inert: document.querySelector('.main').inert,
                      expanded: document.querySelector('[data-toggle-nav]').getAttribute('aria-expanded'),
                      scrim: getComputedStyle(document.querySelector('.nav-scrim')).opacity,
                      entry: !!(history.state && history.state.rentalarsNav), url: location.pathname,
                      focus: document.activeElement.getAttribute('aria-label') || document.activeElement.textContent.trim()};
            }"""
        )

    def touch_listeners(self) -> list[str]:
        document = self.cdp.send("Runtime.evaluate", {"expression": "document"})["result"]["objectId"]
        found = self.cdp.send("DOMDebugger.getEventListeners", {"objectId": document})["listeners"]
        return sorted({listener["type"] for listener in found if listener["type"].startswith("touch")})

    # --- Tests -------------------------------------------------------------------------------------------

    def test_the_button_opens_it_from_the_right(self) -> None:
        """UIX-045: over the dimmed page, 300 px wide at the right edge; focus in it, the page behind inert; axe."""
        self.open("/projects/")
        closed = self.menu_state()
        self.assertEqual((closed["open"], closed["visibility"], closed["expanded"]), (False, "hidden", "false"))
        self.assertGreaterEqual(closed["left"], 390)  # out of view at the right
        self.page.click("[data-toggle-nav]")
        self.page.wait_for_timeout(350)
        state = self.menu_state()
        self.assertTrue(state["open"])
        self.assertEqual((state["left"], state["width"]), (90, 300))  # min(300 px, 86 % of 390 px)
        self.assertEqual(
            (state["visibility"], state["inert"], state["expanded"], state["scrim"]), ("visible", True, "true", "1")
        )
        self.assertEqual(state["focus"], "Menü schließen")
        self.assertEqual(
            self.page.evaluate("getComputedStyle(document.querySelector('.nav-scrim')).backgroundColor"),
            "rgba(0, 0, 0, 0.55)",
        )
        # Like the side navigation: name and company, the entries, the current one marked, the button, the foot.
        self.assertTrue(self.page.is_visible(".sidebar .brand"))
        self.assertEqual(self.page.get_attribute('.sidebar .nav a[aria-current="page"]', "href"), "/projects/")
        self.assertTrue(self.page.is_visible(".sidebar-action .btn"))
        self.assertTrue(self.page.is_visible(".sidebar-foot .version"))
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 390)
        self.assertEqual(self.axe_findings(), [])
        self.page.evaluate("document.documentElement.dataset.theme = 'light'")
        self.assertEqual(self.axe_findings(), [])

    def test_focus_stays_inside_and_escape_gives_it_back(self) -> None:
        """UIX-045: Tab goes round in the menu; Escape closes it, focus back on the menu button."""
        self.open("/projects/")
        self.page.focus("[data-toggle-nav]")
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(350)
        inside = "document.getElementById('sidebar').contains(document.activeElement)"
        for _ in range(25):
            self.page.keyboard.press("Tab")
            self.assertTrue(self.page.evaluate(inside))
        self.page.keyboard.press("Shift+Tab")
        self.assertTrue(self.page.evaluate(inside))
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(350)
        state = self.menu_state()
        self.assertEqual(
            (state["open"], state["inert"], state["expanded"], state["entry"]), (False, False, "false", False)
        )
        self.assertEqual(state["focus"], "Menü")
        self.assertEqual(self.menu_state()["visibility"], "hidden")

    def test_close_button_and_tap_beside_it(self) -> None:
        self.open("/projects/")
        self.page.click("[data-toggle-nav]")
        self.page.click(".nav-close")
        self.page.wait_for_timeout(350)
        self.assertFalse(self.is_open())
        self.page.click("[data-toggle-nav]")
        self.page.wait_for_timeout(350)
        self.page.mouse.click(40, 400)  # on the dimmed page
        self.page.wait_for_timeout(350)
        self.assertFalse(self.is_open())
        self.assertEqual(self.page.url, f"{self.live_server_url}/projects/")

    def test_back_closes_it_and_stays_on_the_page(self) -> None:
        """UIX-045: the browser's Back closes the menu instead of leaving the page."""
        self.open("/")
        self.open("/projects/")
        self.page.click("[data-toggle-nav]")
        self.page.wait_for_timeout(300)
        self.assertTrue(self.menu_state()["entry"])
        self.page.go_back()
        self.page.wait_for_timeout(350)
        state = self.menu_state()
        self.assertEqual((state["open"], state["url"]), (False, "/projects/"))
        self.page.go_back()
        self.page.wait_for_url(f"{self.live_server_url}/")

    def test_a_link_in_the_menu_and_back(self) -> None:
        """UIX-045: after following a link of the menu, Back leads to the page before – once, without the menu."""
        self.open("/")
        self.open("/projects/")
        self.page.click("[data-toggle-nav]")
        self.page.wait_for_timeout(300)
        with self.page.expect_navigation():
            self.page.click('#sidebar .nav a[href="/customers/"]')
        self.page.go_back()
        self.page.wait_for_url(f"{self.live_server_url}/projects/")
        self.assertFalse(self.is_open())
        self.page.go_back()
        self.page.wait_for_url(f"{self.live_server_url}/")

    def test_swipe_open_and_back(self) -> None:
        """UIX-045: a swipe from right to left anywhere opens it, past half way; a swipe to the right closes it."""
        self.open("/projects/")
        self.swipe(370, 120)
        state = self.menu_state()
        self.assertEqual((state["open"], state["left"], state["entry"]), (True, 90, True))
        self.swipe(150, 380, y=400)
        self.assertFalse(self.is_open())
        self.assertFalse(self.menu_state()["entry"])

    def test_by_distance_or_by_speed(self) -> None:
        """UIX-045: the menu follows the finger; a short slow swipe falls back, a short fast one opens it."""
        self.open("/projects/")
        self.touch("touchStart", 370, 600)
        for x in (355, 330, 290):
            self.touch("touchMove", x, 600)
            time.sleep(0.02)
        following = self.menu_state()
        self.assertAlmostEqual(following["left"], 390 - 80, delta=3)  # 80 px out, under the finger
        self.assertGreater(float(following["scrim"]), 0.1)
        time.sleep(0.15)  # the finger rests: no fling
        self.touch("touchEnd")
        self.page.wait_for_timeout(350)
        self.assertFalse(self.is_open())  # less than half out
        self.touch("touchStart", 370, 600)
        for x in (345, 310, 270):  # as fast as the browser takes it, 100 px
            self.touch("touchMove", x, 600)
        self.touch("touchEnd")
        self.page.wait_for_timeout(350)
        self.assertTrue(self.is_open())

    def test_not_from_what_scrolls_sideways(self) -> None:
        """UIX-045: a swipe on a timeline scrolls the timeline, as in the app (canScrollHorizontally)."""
        self.open("/schedule/timeline/?days=2&from=2027-03-09")
        row = self.page.locator(".timeline .tl-row").first.bounding_box()
        self.swipe(370, 100, y=row["y"] + row["height"] / 2)
        self.assertFalse(self.is_open())

    def test_with_reduced_motion(self) -> None:
        """UIX-045: no sliding when the system asks for less motion – it is simply there."""
        self.page.emulate_media(reduced_motion="reduce")
        self.open("/projects/")
        self.assertEqual(
            self.page.evaluate("getComputedStyle(document.getElementById('sidebar')).transitionDuration"), "0s"
        )
        self.page.click("[data-toggle-nav]")
        self.assertEqual(self.menu_state()["left"], 90)  # at once

    def test_crossing_the_breakpoint(self) -> None:
        """UIX-045: an open menu closes when the window grows past 900 px; the side navigation is back as it was."""
        self.open("/projects/")
        self.assertIn("touchstart", self.touch_listeners())
        self.page.click("[data-toggle-nav]")
        self.page.wait_for_timeout(300)
        self.page.set_viewport_size({"width": 1360, "height": 900})
        self.page.wait_for_timeout(100)
        state = self.menu_state()
        self.assertEqual((state["open"], state["inert"], state["entry"], state["left"]), (False, False, False, 0))
        self.assertNotIn("touchstart", self.touch_listeners())
        self.assertEqual(self.page.evaluate("getComputedStyle(document.getElementById('sidebar')).position"), "sticky")
        self.page.set_viewport_size({"width": 390, "height": 800})
        self.assertIn("touchstart", self.touch_listeners())
        self.assertFalse(self.is_open())


class DesktopNavigationUnchangedTests(AxeMixin, BrowserTestCase):
    """UIX-045: above 900 px the side navigation stays exactly as it was – no drawer, no swipe."""

    def test_as_before(self) -> None:
        for width in (901, 1360, 1920):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.open("/projects/")
                look = self.page.evaluate(
                    """() => {
                      const nav = document.getElementById('sidebar'), style = getComputedStyle(nav);
                      return [style.position, style.display, style.transform, style.visibility, nav.getBoundingClientRect().left,
                              nav.getBoundingClientRect().width, document.querySelector('.main').getBoundingClientRect().left,
                              getComputedStyle(document.querySelector('.nav-close')).display,
                              getComputedStyle(document.querySelector('.nav-scrim')).display,
                              getComputedStyle(document.querySelector('.topbar')).display];
                    }"""
                )
                self.assertEqual(look, ["sticky", "flex", "none", "visible", 0, 216, 216, "none", "none", "none"])
                cdp = self.page.context.new_cdp_session(self.page)
                document = cdp.send("Runtime.evaluate", {"expression": "document"})["result"]["objectId"]
                types = {
                    item["type"]
                    for item in cdp.send("DOMDebugger.getEventListeners", {"objectId": document})["listeners"]
                }
                self.assertNotIn("touchstart", types)
                cdp.detach()
        self.page.keyboard.press("/")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "nav-search")
        self.assertFalse(self.page.evaluate("document.body.classList.contains('nav-open')"))
        self.assertEqual(self.axe_findings(".sidebar"), [])


class CorrespondenceInTheBrowserTests(AxeMixin, BrowserTestCase):
    """EML-050: the tab "Korrespondenz" of a project and of a service case – the same, "Zusammenfassung" folded."""

    def setUp(self) -> None:
        super().setUp()
        self.case = service_cases.create_case(name="Beamer flackert", customer=self.project.customer)
        for target in (self.project, self.case):
            add_mail(target, "Anfrage", "Passt der Aufbau am Donnerstag?")
            add_mail(target, "Re: Anfrage", "Ja, ab 8 Uhr.", incoming=False, days=1)
        AISummary.objects.create(
            project=self.case,
            text="Der Kunde fragt nach dem Aufbau.",
            model="m",
            provider_label="Lokale KI",
            covered_projects=[self.case.pk],
            mail_count=2,
        )

    def test_folded_in_both(self) -> None:
        for target in (self.project, self.case):
            with self.subTest(kind=target.kind):
                self.open(f"/projects/{target.pk}/mails/")
                block = self.page.locator("#ai-summary")
                block.locator("details.ai-overview").wait_for(state="attached")
                self.assertEqual(block.locator("h2").inner_text(), "Zusammenfassung")
                self.assertFalse(block.locator("details.ai-overview").evaluate("d => d.open"))
                self.assertNotIn("Passt der Aufbau am Donnerstag?", block.inner_text())
                block.get_by_text("Kurzüberblick ohne KI").click()
                self.assertIn("Passt der Aufbau am Donnerstag?", block.inner_text())
                self.assertEqual(self.axe_findings("#ai-summary"), [])
        block = self.page.locator("#ai-summary")
        text = block.inner_text()
        # EML-050: the summary by AI is folded as well – its line says what it is, a click opens it.
        self.assertIn("von KI erstellt", text)
        self.assertNotIn("Der Kunde fragt nach dem Aufbau.", text)
        block.locator("details.ai-result summary").click()
        text = block.inner_text()
        self.assertLess(text.index("Der Kunde fragt nach dem Aufbau."), text.index("Kurzüberblick ohne KI"))
        self.assertEqual(self.page.locator("nav.tabs a").first.inner_text(), "Überblick")  # PRJ-090
