# SPDX-License-Identifier: GPL-3.0-or-later
"""Base class for tests in a real browser (UIX-009, NFA-023).

Why these tests exist: the page tests in ``tests/ui`` read the HTML the
server sends, but they do not run the scripts of the page. Mistakes in the
interplay of page and script – an answer that lands in the wrong place, a
dialog that does not close – only show in a browser. The tests here click
through the pages that change without a page load.

They need Playwright and a Chromium browser, which are not part of the
normal development requirements::

    pip install playwright
    playwright install chromium
    python manage.py test tests.browser

Without Playwright every test of this folder is skipped. A browser that is
already installed can be named with ``RENTALARS_TEST_BROWSER=/path/to/chrome``.
"""

from __future__ import annotations

import glob
import os
import re
from typing import Any, ClassVar
from unittest import SkipTest

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache

from rentalars.core.demo import create_demo_data
from rentalars.core.middleware import SetupRequiredMiddleware
from rentalars.core.models import SystemSettings
from rentalars.material import numbering
from rentalars.projects.models import Project
from tests.helpers import PASSWORD, make_user, stop_the_clock

try:
    from playwright.sync_api import Browser, Page, Playwright, sync_playwright
except ImportError:  # the normal case on a machine that only runs the other tests
    sync_playwright = None  # type: ignore[assignment]


def _browser_path() -> str | None:
    """Return a browser to use instead of the one Playwright would download."""
    named = os.environ.get("RENTALARS_TEST_BROWSER")
    if named:
        return named
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    found = sorted(glob.glob(f"{root}/chromium-*/chrome-linux/chrome")) if root else []
    return found[-1] if found else None


class BrowserTestCase(StaticLiveServerTestCase):
    """A running server with the sample data and a browser that is logged in as administrator."""

    playwright: ClassVar[Playwright]
    browser: ClassVar[Browser]
    page: Page
    #: Width and height of the browser window.
    viewport: ClassVar[dict[str, int]] = {"width": 1360, "height": 900}
    #: Let the test put scripts of its own into the page (the accessibility check), past the
    #: Content Security Policy that otherwise forbids every script that is not Rentalars' own.
    bypass_csp: ClassVar[bool] = False
    #: Let pages ask the server whether they changed (UIX-020). Off for most tests: the question
    #: runs alongside the test's own requests, and the test server shares one SQLite connection
    #: between its threads – two requests at the same time can then read each other's rows.
    watch_changes: ClassVar[bool] = False

    @classmethod
    def setUpClass(cls) -> None:
        if sync_playwright is None:
            raise SkipTest("Playwright is not installed (see tests/browser/base.py).")
        # Playwright keeps an event loop running in this thread. Django then
        # refuses database access from the test itself unless told otherwise.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        try:
            # The browser must not send requests for the local server through a proxy of the machine.
            cls.browser = cls.playwright.chromium.launch(executable_path=_browser_path(), args=["--no-proxy-server"])
        except Exception as error:
            cls.playwright.stop()
            super().tearDownClass()
            raise SkipTest(f"No browser could be started: {error}") from error

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()
        os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)

    def setUp(self) -> None:
        super().setUp()
        stop_the_clock(self)
        system_settings = SystemSettings.load()
        system_settings.setup_completed = True
        system_settings.save()
        SetupRequiredMiddleware.reset()
        numbering.reset_cache()
        cache.clear()
        make_user("anna", superuser=True)
        create_demo_data()
        self.project = Project.objects.get(name="Stadtfest Hauptbühne")

        context = self.browser.new_context(
            viewport=self.viewport,  # type: ignore[arg-type]
            locale="de-DE",
            bypass_csp=self.bypass_csp,
        )
        self.addCleanup(context.close)
        self.page = context.new_page()
        self.page.set_default_timeout(10_000)
        #: Whatever goes wrong behind the scenes fails the test in tearDown.
        self.problems: list[str] = []
        self.page.on("console", lambda message: self._note_console(message))
        self.page.on("pageerror", lambda error: self.problems.append(f"script error: {error}"))
        self.page.on("response", lambda response: self._note_response(response))
        self.page.on("request", lambda request: self._note_request(request))
        self.page.on("dialog", lambda dialog: dialog.accept())  # "Really delete?" → yes
        if not self.watch_changes:
            self.page.route(
                re.compile(r"/changes/\?"),
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body='{"stamps": {}, "unread": 0}'
                ),
            )

        self.open("/login/")
        self.page.fill("#id_username", "anna")
        self.page.fill("#id_password", PASSWORD)
        self.page.click("button[type=submit]")
        self.page.wait_for_url(f"{self.live_server_url}/")

    def confirm(self) -> None:
        """Answer "yes" in the question of the page before deleting (UIX-018: a dialog, not the browser's)."""
        question = self.page.locator("dialog.confirm[open]")
        question.wait_for()
        question.locator(".dialog-foot button").last.click()
        question.wait_for(state="detached")

    def tearDown(self) -> None:
        self.assertEqual(self.problems, [])
        visible = self.page.inner_text("body")
        for leak in ("{#", "#}", "{%", "%}"):
            self.assertNotIn(leak, visible, "template syntax is visible on the page")
        super().tearDown()

    def _note_console(self, message: Any) -> None:
        if message.type == "error":
            self.problems.append(f"console: {message.text}")

    def _note_response(self, response: Any) -> None:
        if response.status >= 400:
            self.problems.append(f"{response.status} {response.request.method} {response.url}")

    def _note_request(self, request: Any) -> None:
        """NFA-050: no page asks another server for anything – no font, no script, no badge."""
        if not request.url.startswith((self.live_server_url, "data:", "blob:")):
            self.problems.append(f"request to another server: {request.url}")

    # --- Helpers the tests read like sentences with -------------------------------------

    def open(self, path: str) -> None:
        """Load a page of the application."""
        self.page.goto(self.live_server_url + path)

    def open_planning(self) -> None:
        """Open the planning page of the sample project."""
        self.open(f"/projects/{self.project.pk}/")

    def settle(self) -> None:
        """Wait until the page has taken in the answer of a background request."""
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_function("() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')")

    def group(self, name: str) -> Any:
        """The section of a group on the planning page."""
        return self.page.locator("section.group", has=self.page.locator(".group-head h3", has_text=name))

    def choose_product(self, container: Any, text: str) -> None:
        """Type into a product search field and take the first suggestion."""
        field = container.locator("[data-typeahead-input]")
        field.click()
        field.press_sequentially(text, delay=20)
        container.locator("[role=option]").first.wait_for()
        field.press("Enter")

    def text_of(self, selector: str) -> str:
        """The visible text of an element, on one line."""
        return " ".join(self.page.inner_text(selector).split())
