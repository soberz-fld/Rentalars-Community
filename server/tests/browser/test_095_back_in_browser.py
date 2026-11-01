# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: Rentalars' "Zurück" after the browser's own back button (UIX-011, UIX-027).

The problem: on the products pages, after the browser's own back button took the user from the detail page to the overview, the back button of Rentalars went to the product last called and not to the page last opened.

The cause: a real browser brings a page back from its memory (the back/forward cache) when its back button is used, and
asks the server for nothing. The application's way back (``rentalars.core.trail``, a cookie) therefore still ended at the
product the user had just left; the next product opened got "Back" to that product. Playwright switches that memory
off by default, which is why the browser tests did not see it: the tests here start a Chromium that keeps pages in
memory like the ones people use, and skip themselves if the browser does not.

The fix is on the server: the click says in the ``Referer`` which page it comes from, and the way back is cut to that page
before the new page is added (``trail.follow_referer``).
"""

from __future__ import annotations

from django.core import signing

from rentalars.material.models import MaterialModel
from tests.browser.base import BrowserTestCase, _browser_path
from tests.helpers import PASSWORD


class InMemoryBrowserCase(BrowserTestCase):
    """A logged-in browser that keeps the pages it leaves in memory, and helpers to read the way back."""

    def setUp(self) -> None:
        super().setUp()
        # A browser that keeps the pages it leaves in memory, as the browsers of the people who use Rentalars do.
        browser = self.playwright.chromium.launch(
            executable_path=_browser_path(),
            args=["--no-proxy-server"],
            ignore_default_args=["--disable-back-forward-cache"],
        )
        self.addCleanup(browser.close)
        context = browser.new_context(viewport=self.viewport, locale="de-DE")  # type: ignore[arg-type]
        self.addCleanup(context.close)
        self.page = context.new_page()
        self.page.set_default_timeout(10_000)
        self.page.on("console", lambda message: self._note_console(message))
        self.page.on("pageerror", lambda error: self.problems.append(f"script error: {error}"))
        self.page.on("response", lambda response: self._note_response(response))
        self.page.on("request", lambda request: self._note_request(request))
        self.page.route(
            "**/changes/?*",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"stamps": {}, "unread": 0}'
            ),
        )
        self.open("/login/")
        self.page.fill("#id_username", "anna")
        self.page.fill("#id_password", PASSWORD)
        self.page.click("button[type=submit]")
        self.page.wait_for_url(f"{self.live_server_url}/")

    # --- Helpers ----------------------------------------------------------------------------------------

    def path(self) -> str:
        """The address of the page, without the server."""
        return self.page.url.replace(self.live_server_url, "")

    def mark(self) -> None:
        """Put a mark into the page: it is still there if the browser brings this very page back from memory."""
        self.page.evaluate("window.restoredFromMemory = true")

    def browser_back(self, expected: str) -> None:
        """The browser's own back button; the page it shows must be the one kept in memory (else the test is moot)."""
        self.page.go_back(wait_until="commit")
        self.page.wait_for_url(self.live_server_url + expected, wait_until="commit")  # a restored page fires no "load"
        if not self.page.evaluate("window.restoredFromMemory === true"):
            self.skipTest("This browser did not keep the page in memory; the situation described cannot arise.")

    def browser_forward(self, expected: str) -> None:
        """The browser's forward button."""
        self.page.go_forward(wait_until="commit")
        self.page.wait_for_url(self.live_server_url + expected, wait_until="commit")

    def open_row(self, row: int) -> str:
        """Open the product of a row of the list; return its address."""
        self.page.locator("tbody tr").nth(row).locator("a").first.click()
        self.page.wait_for_url("**/products/*/")
        self.page.wait_for_load_state("domcontentloaded")
        return self.path()

    def back_link(self) -> str | None:
        """Where "Back" at the top of the page leads (the link of the page, not the browser's history)."""
        link = self.page.locator("main a.back-link")
        return link.get_attribute("href") if link.count() else None

    def trail(self) -> list[str]:
        """The addresses on the application's way back, as the cookie keeps them."""
        cookies = [cookie for cookie in self.page.context.cookies() if cookie["name"] == "rentalars_trail"]
        if not cookies:
            return []
        return [address for _place, address in signing.loads(cookies[0]["value"], salt="rentalars.core.trail")]

    def to_the_list(self) -> None:
        """From the start page to the product list with the menu, as a person does."""
        self.open("/")
        self.page.locator("#sidebar a[href='/products/']").first.click()
        self.page.wait_for_url(self.live_server_url + "/products/")
        self.mark()


class BackAfterTheBrowsersBackButton(InMemoryBrowserCase):
    """The way back follows the browser's history, however the user moves."""

    def test_the_wish_list_product_browser_back_next_product_then_back(self) -> None:
        self.to_the_list()
        first = self.open_row(0)
        self.assertEqual(self.back_link(), "/products/")
        self.browser_back("/products/")
        # The list came back from memory: the application did not hear about it.
        self.assertEqual(self.trail(), ["/products/", first])
        second = self.open_row(2)
        self.assertNotEqual(first, second)
        # "Zurück" leads to the list – the page opened last before this product – not to the product before.
        self.assertEqual(self.back_link(), "/products/")
        self.assertEqual(self.trail(), ["/products/", second])
        self.page.locator("main a.back-link").click()
        self.page.wait_for_url(self.live_server_url + "/products/")

    def test_several_steps_back_and_forth(self) -> None:
        self.to_the_list()
        self.open_row(0)
        self.browser_back("/products/")
        self.open_row(1)
        self.browser_back("/products/")
        third = self.open_row(2)
        self.assertEqual(self.back_link(), "/products/")
        self.assertEqual(self.trail(), ["/products/", third])

    def test_the_forward_button_and_the_link_of_the_page_agree(self) -> None:
        self.to_the_list()
        first = self.open_row(0)
        self.browser_back("/products/")
        self.browser_forward(first)
        self.assertEqual(self.back_link(), "/products/")
        self.page.locator("main a.back-link").click()
        self.page.wait_for_url(self.live_server_url + "/products/")

    def test_a_product_and_back_without_the_browsers_button_is_as_before(self) -> None:
        self.to_the_list()
        self.open_row(0)
        self.assertEqual(self.back_link(), "/products/")
        self.page.locator("main a.back-link").click()
        self.page.wait_for_url(self.live_server_url + "/products/")
        self.assertEqual(self.trail(), ["/products/"])
        self.assertIsNone(self.back_link())  # a start page shows none

    def test_edit_save_and_back_still_leads_to_the_list(self) -> None:
        self.to_the_list()
        first = self.open_row(0)
        self.page.locator("main a[href$='/edit/']").first.click()
        self.page.wait_for_url("**/edit/")
        self.page.locator("form button[type=submit]", has_text="Produkt speichern").click()
        self.page.wait_for_url(self.live_server_url + first)
        self.assertEqual(self.back_link(), "/products/")
        self.assertEqual(self.trail(), ["/products/", first])
        self.page.locator("main a.back-link").click()
        self.page.wait_for_url(self.live_server_url + "/products/")

    def test_after_the_browsers_back_button_from_a_form(self) -> None:
        """List, product, form – the browser's back button to the product – another product: the form is gone."""
        self.to_the_list()
        first = self.open_row(0)
        self.mark()
        self.page.locator("main a[href$='/edit/']").first.click()
        self.page.wait_for_url("**/edit/")
        self.browser_back(first)
        self.assertEqual(self.trail(), ["/products/", first, first + "edit/"])  # the cookie does not know yet
        self.page.locator("main a.back-link").click()  # the page's own link: the list
        self.page.wait_for_url(self.live_server_url + "/products/")
        self.assertEqual(self.trail(), ["/products/"])

    def test_a_dialog_leaves_the_way_alone(self) -> None:
        self.to_the_list()
        self.open_row(0)
        self.page.locator(".sidebar-action a[hx-get]").click()
        self.page.locator("dialog#dialog[open]").wait_for()
        self.page.keyboard.press("Escape")
        self.page.locator("dialog#dialog[open]").wait_for(state="detached")
        self.assertEqual(self.back_link(), "/products/")

    def test_from_record_to_record(self) -> None:
        """Model, item, the browser's back button, the next item of the model: "Back" leads to the model."""
        model = max(MaterialModel.objects.all(), key=lambda found: found.items.count())
        self.assertGreaterEqual(model.items.count(), 2)
        self.open("/material/models/")
        self.page.wait_for_load_state("domcontentloaded")
        model_page = f"/material/models/{model.pk}/"
        self.open(model_page)
        self.mark()
        items = [f"/material/items/{item.pk}/" for item in model.items.order_by("inventory_number")[:2]]
        self.page.locator(f"main a[href='{items[0]}']:visible").first.click()
        self.page.wait_for_url(self.live_server_url + items[0])
        self.browser_back(model_page)
        self.page.locator(f"main a[href='{items[1]}']:visible").first.click()
        self.page.wait_for_url(self.live_server_url + items[1])
        self.assertEqual(self.back_link(), model_page)


class BackOnThePhone(InMemoryBrowserCase):
    """On a phone "Back" at the top of a start page is the browser's history; it stays consistent with it."""

    viewport = {"width": 380, "height": 740}  # type: ignore[assignment]

    def to_the_list(self) -> None:
        """From the start page to the product list with the menu of the phone."""
        self.open("/")
        self.page.locator("[data-toggle-nav]").click()
        self.page.locator("#sidebar a[href='/products/']").first.click()
        self.page.wait_for_url(self.live_server_url + "/products/")
        self.mark()

    def test_the_wish_on_the_phone(self) -> None:
        """List, product, browser back, "Zurück" at the top: the page before the list – not the product."""
        self.to_the_list()
        self.open_row(0)
        self.assertEqual(self.page.locator("a.topbar-back").get_attribute("href"), "/products/")
        self.browser_back("/products/")
        self.page.locator("a.topbar-back").click()
        self.page.wait_for_url(self.live_server_url + "/")
        self.assertEqual(self.path(), "/")

    def test_the_next_product_on_the_phone(self) -> None:
        self.to_the_list()
        self.open_row(0)
        self.browser_back("/products/")
        self.open_row(2)
        self.assertEqual(self.page.locator("a.topbar-back").get_attribute("href"), "/products/")
        self.page.locator("a.topbar-back").click()
        self.page.wait_for_url(self.live_server_url + "/products/")
