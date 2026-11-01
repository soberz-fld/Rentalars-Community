# SPDX-License-Identifier: GPL-3.0-or-later
"""Review round 3, in the browser: the stock refresh of an open planning, the suggestion panel, open details.

(R3-6, R3-7, R3-10.) The page script is the thing under test; the server side is in
tests/unit/test_100_fix_r3.py. The time of the page is a fake clock (``page.clock``), so that "at most once every 20
seconds" and "give up after 15 seconds" are tested in milliseconds.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from rentalars.products import services as product_services
from rentalars.products import suggestions
from rentalars.products.models import ProductKind
from rentalars.products.relation_models import RelationKind
from tests.browser.base import BrowserTestCase
from tests.browser.test_100_products_planning_in_browser import AxeMixin
from tests.helpers import add_line, make_product, make_stock


class StockRefreshScriptTests(BrowserTestCase):
    """(R3-7) A burst of saves elsewhere asks for the figures once; nothing gets lost, nothing hangs."""

    watch_changes = True  # the page asks the server whether the stock changed – the answers are made up here
    bypass_csp = True

    def setUp(self) -> None:
        super().setUp()
        self.product = make_stock("K-811", 3, "Wunschartikel")
        self.line = add_line(self.project, self.product, 2).line
        self.stamp = 0
        self.availability: list[str] = []
        self.held: list[Any] = []
        self.hold = False
        self.moving = False  # whether the next question finds the stamp moved
        self.addCleanup(self.release_held)
        self.page.route("**/changes/?*", self.answer_changes)
        self.page.route("**/planning/availability/", self.answer_availability)

    def release_held(self) -> None:
        """Answers that were never given are given up, so that no request hangs when the page is closed."""
        for route in self.held:
            with contextlib.suppress(Exception):  # the page may be gone already
                route.abort()

    def answer_changes(self, route: Any) -> None:
        """Every question about the state gets a new stamp of the stock: as if somebody saved something each time."""
        if self.moving:
            self.stamp += 1
        body = {"stamps": {f"stock:{self.project.pk}": str(self.stamp)}, "unread": 0}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def answer_availability(self, route: Any) -> None:
        self.availability.append(route.request.url)
        if self.hold:
            self.held.append(route)  # answered by the test, or never
        else:
            route.continue_()

    def open_with_clock(self) -> None:
        """Open the planning; the clock stands still from there on, only the test moves it."""
        self.page.clock.install()
        self.open_planning()
        self.settle()
        self.page.clock.pause_at("2030-01-01T10:00:00")

    def poll(self) -> None:
        """What the browser does when the user comes back to the tab: the page asks whether anything changed."""
        before = self.stamp
        self.moving = True
        self.page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
        for _ in range(100):
            if self.stamp > before:
                break
            self.page.wait_for_timeout(20)
        self.moving = False
        self.page.wait_for_timeout(100)  # the answer is taken in

    def test_a_burst_asks_once_and_the_rest_waits_for_the_interval(self) -> None:
        self.open_with_clock()
        for _ in range(5):
            self.poll()
        self.assertEqual(len(self.availability), 1, self.availability)  # the first change asks at once
        self.page.clock.run_for(19_000)
        self.page.wait_for_timeout(200)
        self.assertEqual(len(self.availability), 1)  # the four others are one question, not yet due
        self.page.clock.run_for(1_500)
        self.page.wait_for_timeout(300)
        self.assertEqual(len(self.availability), 2, self.availability)
        self.page.clock.run_for(60_000)
        self.page.wait_for_timeout(200)
        self.assertEqual(len(self.availability), 2)  # nothing more is wanted

    def test_a_change_during_the_request_is_asked_for_afterwards(self) -> None:
        self.open_with_clock()
        self.hold = True
        self.poll()
        self.assertEqual(len(self.availability), 1)
        self.poll()  # while the answer is awaited
        self.assertEqual(len(self.availability), 1)
        self.hold = False
        self.held.pop().continue_()
        self.page.wait_for_timeout(300)
        self.page.clock.run_for(21_000)
        self.page.wait_for_timeout(300)
        self.assertEqual(len(self.availability), 2, self.availability)  # the second change was not lost

    def test_a_request_that_hangs_is_given_up_and_the_page_can_ask_again(self) -> None:
        self.open_with_clock()
        self.hold = True
        self.poll()
        self.assertEqual(len(self.availability), 1)
        self.page.clock.run_for(16_000)  # the 15 seconds are over
        self.page.wait_for_timeout(200)
        self.hold = False
        self.poll()
        self.page.clock.run_for(5_000)  # and the interval of 20 seconds since the first question as well
        self.page.wait_for_timeout(400)
        self.assertEqual(len(self.availability), 2, self.availability)

    def test_a_cell_with_the_focus_is_left_alone(self) -> None:
        self.page.unroute("**/planning/availability/")
        fresh = (
            f'<template data-stock-line="{self.line.pk}"><div data-part="cell">NEU</div>'
            '<div data-part="wish"></div></template>'
        )
        self.page.route(
            "**/planning/availability/",
            lambda route: route.fulfill(status=200, content_type="text/html", body=fresh),
        )
        self.open_planning()
        self.settle()
        cell = self.page.locator(f"#line-{self.line.pk} [data-stock-cell]")
        cell.evaluate('element => { element.innerHTML = \'<a href="#" id="held">alt</a>\'; }')
        self.page.focus("#held")
        self.poll()
        self.page.wait_for_timeout(300)
        self.assertEqual(cell.inner_text(), "alt")  # the user is in it: not replaced


class OpenDetailsKeepTheirStateTests(BrowserTestCase):
    """(R3-10) The open components of a kit stay open for the right line when others come and go."""

    def test_the_second_kit_stays_open_when_the_first_line_is_deleted(self) -> None:
        speaker = make_stock("S-811", 5, "Lautsprecher")
        first = make_product("K-811", "Erstes Set", kind=ProductKind.KIT)
        second = make_product("K-812", "Zweites Set", kind=ProductKind.KIT)
        for kit in (first, second):
            product_services.set_kit_components(kit, [(speaker, 2)])
        first_line = add_line(self.project, first, 1).line
        second_line = add_line(self.project, second, 1).line
        self.open_planning()
        self.settle()
        second_details = self.page.locator(f"#line-{second_line.pk} details")
        second_details.locator("summary").click()
        self.assertTrue(second_details.evaluate("element => element.open"))
        self.page.locator(f"#line-{first_line.pk}").get_by_role("button", name="Position löschen").click()
        self.confirm()
        self.page.locator(f"#line-{first_line.pk}").wait_for(state="detached")
        self.settle()
        self.page.wait_for_timeout(200)
        self.assertTrue(self.page.locator(f"#line-{second_line.pk} details").evaluate("element => element.open"))


class SuggestionPanelScriptTests(AxeMixin, BrowserTestCase):
    """(R3-6) The panel is asked for once after a burst of changes and announced only when it changes."""

    bypass_csp = True

    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("S-821", 5, "Lautsprecher Alpha")
        self.cable = make_stock("K-821", 20, "Speakon-Kabel")
        self.stand = make_stock("T-821", 10, "Stativ")
        suggestions.add_relation(self.speaker, self.cable, RelationKind.ACCESSORY, is_required=True)
        suggestions.add_relation(self.speaker, self.stand, RelationKind.ACCESSORY)
        add_line(self.project, self.speaker, 2)
        self.panel_requests: list[str] = []
        self.page.on(
            "request",
            lambda request: self.panel_requests.append(request.url) if "/suggestions/" in request.url else None,
        )

    def status(self) -> str:
        return self.page.locator("[data-suggestion-status]").inner_text()

    def test_a_burst_of_changes_asks_once_and_the_panel_is_no_live_region(self) -> None:
        self.open_planning()
        panel = self.page.locator("#suggestions")
        panel.get_by_text("Vorschläge für die Planung").wait_for()
        self.settle()
        self.assertEqual(self.status(), "")  # the first load is not announced
        self.assertIsNone(panel.get_attribute("aria-live"))
        self.assertEqual(self.page.locator("#suggestions [aria-live]").count(), 0)
        self.panel_requests.clear()
        self.page.evaluate(
            "() => { for (let i = 0; i < 6; i++) { document.body.dispatchEvent(new Event('planningChanged')); } }"
        )
        self.page.wait_for_timeout(1500)
        self.settle()
        self.assertEqual(len(self.panel_requests), 1, self.panel_requests)
        self.assertEqual(self.status(), "")  # the number of suggestions did not change: nothing is announced
        self.assertEqual(self.axe_findings("#suggestions"), [])

    def test_the_number_changing_is_announced(self) -> None:
        self.open_planning()
        panel = self.page.locator("#suggestions")
        panel.get_by_text("Vorschläge für die Planung").wait_for()
        self.settle()
        self.assertEqual(panel.locator("li").count(), 2)
        panel.locator("li", has_text="K-821").get_by_role("button", name="Hinzufügen").click()
        self.page.wait_for_function(
            "() => document.querySelector('[data-suggestion-status]').innerText.includes('Vorschlag')"
        )
        self.assertEqual(self.status(), "1 Vorschlag für die Planung")
        self.settle()
        self.assertEqual(self.page.locator("#suggestions li").count(), 1)
