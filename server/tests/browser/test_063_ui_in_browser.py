# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: filters that fold away (UIX-030), credits and company in the menu (UIX-031, UIX-032),
and the pages without login centred at every width (bug fix). The filters start folded on
every width (UIX-038)."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.core.middleware import SetupRequiredMiddleware
from rentalars.core.models import CompanyProfile, SystemSettings
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import PASSWORD

#: The centre of logo, box and footer in the window, measured on the text itself where there is text.
CENTRES = """() => {
  const middle = (rect) => (rect.left + rect.right) / 2;
  const textOf = (element) => { const range = document.createRange(); range.selectNodeContents(element); return range.getBoundingClientRect(); };
  return {
    window: document.documentElement.clientWidth / 2,
    logo: middle(document.querySelector('.public-brand img').getBoundingClientRect()),
    card: middle(document.querySelector('.public-card').getBoundingClientRect()),
    foot: middle(textOf(document.querySelector('.public-foot'))),
    scroll: document.scrollingElement.scrollWidth,
    width: document.documentElement.clientWidth,
  };
}"""


class PublicPagesCentredTests(BrowserTestCase):
    """Bug fix: on the login page logo, form and footer stood off the middle at some widths."""

    WIDTHS = (320, 360, 600, 768, 1024, 1366, 1920, 2560)

    def assert_centred(self, path: str) -> None:
        for width in self.WIDTHS:
            with self.subTest(path=path, width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.open(path)
                found = self.page.evaluate(CENTRES)
                for part in ("logo", "card", "foot"):
                    self.assertAlmostEqual(found[part], found["window"], delta=1, msg=f"{part}: {found}")
                self.assertLessEqual(found["scroll"], found["width"])

    def test_login_and_password_reset(self) -> None:
        self.page.context.clear_cookies()
        self.assert_centred("/login/")
        self.assert_centred("/password-reset/")

    def test_setup(self) -> None:
        settings = SystemSettings.load()
        settings.setup_completed = False
        settings.save()
        SetupRequiredMiddleware.reset()
        self.page.context.clear_cookies()
        self.assert_centred("/setup/")


#: UIX-030: every list whose filters fold away, with the key of its panel.
LISTS = (
    ("/projects/", "projects"),
    ("/material/", "material-items"),
    ("/material/models/", "material-models"),
    ("/material/inspections/", "inspections"),
    ("/products/", "products"),
    ("/customers/", "customers"),
    ("/customers/venues/", "venues"),
    ("/personnel/", "people"),
    ("/times/approval/", "time-approval"),
    ("/times/report/", "time-report"),
    ("/shortages/", "shortages"),
    ("/administration/mail/log/", "mail-log"),
    ("/administration/audit-log/", "audit-log"),
    ("/administration/access-log/", "access-log"),
    ("/administration/security-log/", "security-log"),
)


class AxeMixin:
    """The accessibility check of axe-core on the page as it is."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()  # type: ignore[misc]

    def axe_findings(self) -> list[str]:
        page = self.page  # type: ignore[attr-defined]
        if not page.evaluate("() => typeof axe !== 'undefined'"):
            page.add_script_tag(path=str(self.axe))
        return page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ': ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )


class FiltersOnPhoneTests(AxeMixin, BrowserTestCase):
    """UIX-030 on a phone: the filters start folded, the button opens them; UIX-038: folded on every load."""

    viewport = {"width": 360, "height": 740}

    def toggle(self) -> object:
        return self.page.locator("[data-filter-toggle]")

    def test_folded_at_first_with_the_active_filters_beside_the_button(self) -> None:
        self.open("/projects/?status=confirmed")
        toggle = self.toggle()
        self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
        self.assertEqual(toggle.get_attribute("aria-controls"), "filter-panel-projects")
        self.assertEqual(" ".join(toggle.inner_text().split()), "Filter (1 aktiv)")
        self.assertTrue(self.page.is_visible("#f-q"))  # the search stays in view
        self.assertFalse(self.page.is_visible("#f-status"))
        self.assertEqual(self.text_of("#filter-summary-projects"), "Status: Bestätigt")
        # Search and button share a row.
        search, button = self.page.locator("#f-q").bounding_box(), toggle.bounding_box()
        self.assertAlmostEqual(search["y"] + search["height"], button["y"] + button["height"], delta=1)

        toggle.click()
        self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
        self.assertTrue(self.page.is_visible("#f-status"))
        self.assertFalse(self.page.is_visible("#filter-summary-projects"))
        # UIX-038: not remembered – folded again on the next page load.
        self.open("/projects/")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "false")
        self.assertEqual(" ".join(self.toggle().inner_text().split()), "Filter")
        # Other lists are folded as well.
        self.open("/customers/")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "false")

    def test_keyboard_and_enter_in_the_search_while_folded(self) -> None:
        self.open("/projects/")
        self.page.focus("#f-q")
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.filterToggle"), "projects")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "true")
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "f-status")
        self.page.keyboard.press("Shift+Tab")
        self.page.keyboard.press("Space")
        self.assertEqual(self.toggle().get_attribute("aria-expanded"), "false")
        # The button that applies the filters is folded away; Enter in the search still searches.
        self.page.fill("#f-q", "Stadtfest")
        self.page.press("#f-q", "Enter")
        self.page.wait_for_url("**/projects/?q=Stadtfest*")
        self.assertIn("Stadtfest Hauptbühne", self.text_of("main"))
        self.assertEqual(self.page.input_value("#f-q"), "Stadtfest")

    def test_every_list_fits_and_passes_axe_folded_and_open(self) -> None:
        findings: list[str] = []
        for path, key in LISTS:
            with self.subTest(path=path):
                self.open(path)
                self.page.wait_for_load_state("networkidle")
                toggle = self.page.locator(f'[data-filter-toggle="{key}"]')
                self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                self.assertFalse(
                    self.page.locator(
                        f"#filter-panel-{key} select, #filter-panel-{key} input:not([type=hidden])"
                    ).first.is_visible()
                )
                self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
                findings += [f"{path} folded: {finding}" for finding in self.axe_findings()]
                toggle.click()
                self.assertTrue(
                    self.page.locator(
                        f"#filter-panel-{key} select, #filter-panel-{key} input:not([type=hidden])"
                    ).first.is_visible()
                )
                self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
                findings += [f"{path} open: {finding}" for finding in self.axe_findings()]
        self.assertEqual(findings, [], "\n".join(findings))

    def test_the_default_number_of_days_is_no_active_filter(self) -> None:
        self.open("/material/inspections/")
        self.assertEqual(" ".join(self.toggle().inner_text().split()), "Filter")
        self.open("/material/inspections/?days=90")
        self.assertEqual(" ".join(self.toggle().inner_text().split()), "Filter (1 aktiv)")
        self.assertIn("90", self.text_of("#filter-summary-inspections"))


class FiltersOnWideScreenTests(AxeMixin, BrowserTestCase):
    """UIX-038 on a wide screen: the filters start folded as on a phone (UIX-030).

    UIX-038: folded on every page load at every width – an opened list is no longer remembered;
    a filter with an error is never folded.
    """

    def test_folded_at_first_and_opened_by_the_button(self) -> None:
        self.open("/projects/?status=confirmed&since=2027-03-01")
        toggle = self.page.locator('[data-filter-toggle="projects"]')
        self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
        self.assertFalse(self.page.is_visible("#f-status"))
        self.assertEqual(" ".join(toggle.inner_text().split()), "Filter (2 aktiv)")
        self.assertEqual(
            self.page.locator("#filter-summary-projects .filter-chip").all_inner_texts(),
            ["Status: Bestätigt", "Von: 01.03.2027"],
        )
        self.assertEqual(self.axe_findings(), [])
        toggle.click()
        self.assertTrue(self.page.is_visible("#f-status"))
        self.assertFalse(self.page.is_visible("#filter-summary-projects"))
        self.assertEqual(self.axe_findings(), [])
        # UIX-038: opening is not remembered – the next page load is folded again, at every width.
        self.open("/projects/")
        self.assertEqual(self.page.locator("[data-filter-toggle]").get_attribute("aria-expanded"), "false")
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.page.wait_for_timeout(200)
        self.assertEqual(self.page.locator("[data-filter-toggle]").get_attribute("aria-expanded"), "false")
        # Folded on a phone, and so on a wide screen.
        self.open("/customers/")
        self.assertEqual(self.page.locator("[data-filter-toggle]").get_attribute("aria-expanded"), "false")
        self.page.set_viewport_size({"width": 1360, "height": 900})
        self.page.wait_for_timeout(200)
        self.assertEqual(self.page.locator("[data-filter-toggle]").get_attribute("aria-expanded"), "false")
        self.assertFalse(self.page.locator("#filter-panel-customers select").first.is_visible())

    def test_a_filter_with_an_error_is_never_folded(self) -> None:
        """UIX-038: not even when the list was folded by choice."""

        def with_error(route: object) -> None:
            response = route.fetch()  # type: ignore[attr-defined]
            body = response.text().replace(
                "data-filter-panel>", 'data-filter-panel><ul class="errorlist"><li>Kein gültiges Datum.</li></ul>', 1
            )
            route.fulfill(response=response, body=body)  # type: ignore[attr-defined]

        self.open("/projects/")
        self.page.locator("[data-filter-toggle]").click()
        self.page.locator("[data-filter-toggle]").click()  # opened and folded again
        self.page.route("**/projects/?since=*", with_error)
        self.open("/projects/?since=2027-03-01")
        self.assertEqual(self.page.locator("[data-filter-toggle]").get_attribute("aria-expanded"), "true")
        self.assertTrue(self.page.is_visible("#f-status"))
        self.assertTrue(self.page.is_visible("text=Kein gültiges Datum."))


class FiltersWithoutScriptsTests(BrowserTestCase):
    """UIX-030 without scripts: no button, every field shows – on a phone too."""

    def test_every_field_shows(self) -> None:
        context = self.browser.new_context(viewport={"width": 360, "height": 740}, java_script_enabled=False)
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.live_server_url + "/login/")
        page.fill("#id_username", "anna")
        page.fill("#id_password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url(f"{self.live_server_url}/")
        page.goto(self.live_server_url + "/projects/?status=confirmed")
        self.assertFalse(page.is_visible("[data-filter-toggle]"))
        self.assertTrue(page.is_visible("#f-status"))
        self.assertTrue(page.is_visible("#filter-panel-projects button[type=submit]"))
        self.assertLessEqual(page.evaluate("document.scrollingElement.scrollWidth"), 360)


class CompanyAndCreditInTheMenuTests(AxeMixin, BrowserTestCase):
    """UIX-032: the company under the name; UIX-031: the credit under the version."""

    def setUp(self) -> None:
        super().setUp()
        company = CompanyProfile.load()
        company.name = "Veranstaltungstechnik Musterstadt GmbH & Co. KG"
        company.save()

    def test_wide_screen(self) -> None:
        self.open("/")
        self.assertEqual(
            self.text_of(".sidebar .brand .brand-company"), "Veranstaltungstechnik Musterstadt GmbH & Co. KG"
        )
        name, company = (
            self.page.locator(".sidebar .brand").bounding_box(),
            self.page.locator(".sidebar .brand-company").bounding_box(),
        )
        self.assertLess(company["x"] + company["width"], name["x"] + name["width"] + 1)  # wraps inside the menu
        credit = self.page.locator(".sidebar-foot .credit-line a").first
        self.assertEqual(self.text_of(".sidebar-foot .credit-line"), "von fld-vt.de · Über")  # The link to "About"
        self.assertEqual(credit.get_attribute("href"), "https://fld-vt.de")
        self.assertEqual(credit.get_attribute("target"), "_blank")
        self.assertEqual(credit.get_attribute("rel"), "noopener")
        version = self.page.locator(".sidebar-foot .version").bounding_box()
        self.assertGreater(credit.bounding_box()["y"], version["y"])  # below the version
        self.assertEqual(self.axe_findings(), [])

    def test_phone(self) -> None:
        self.page.set_viewport_size({"width": 600, "height": 800})
        self.open("/projects/")
        self.assertTrue(self.page.is_visible(".topbar .brand-company"))
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 600)
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.open("/projects/")
        # No room beside the logo: the name is read out with the link, and shown at the top of the menu.
        self.assertEqual(self.page.locator(".topbar .brand-company").bounding_box()["width"], 1)
        self.assertLess(self.page.locator(".topbar").bounding_box()["height"], 60)
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.assertFalse(self.page.is_visible(".sidebar-company"))
        self.page.click("[data-toggle-nav]")
        # UIX-045: the menu is a drawer with the head of the side navigation – the company under
        # the name there, not in a line of its own above the search.
        self.assertTrue(self.page.is_visible(".sidebar .brand .brand-company"))
        self.assertFalse(self.page.is_visible(".sidebar-company"))
        self.assertEqual(
            self.text_of(".sidebar .brand .brand-company"), "Veranstaltungstechnik Musterstadt GmbH & Co. KG"
        )
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.assertEqual(self.axe_findings(), [])

    def test_short_page_on_a_phone_keeps_a_low_top_bar(self) -> None:
        """Fix: on a page with little content the top bar was stretched to a quarter of the window."""
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.open("/times/report/")
        self.assertLess(self.page.locator(".topbar").bounding_box()["height"], 60)
