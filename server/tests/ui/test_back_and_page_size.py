# SPDX-License-Identifier: GPL-3.0-or-later
"""The way back to the view one came from, the number of entries per page, the tabs of material management.

Requirements UIX-011, UIX-012 and UIX-013.
"""

from __future__ import annotations

import re
from typing import Any

from django.core import signing
from django.test import Client
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.listing import DEFAULT_PAGE_SIZE, PAGE_SIZE_COOKIE, PAGE_SIZES
from rentalars.core.trail import COOKIE_NAME, MAX_ADDRESS_LENGTH, MAX_ENTRIES, step
from rentalars.material.models import MaterialItem, MaterialModel
from tests.helpers import (
    RentalarsTestCase,
    make_customer,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
)
from tests.ui.base import UiTestCase, form_data

BACK_LINK = re.compile(r'<a class="back-link no-print" href="([^"]*)">')


def back_of(html: str) -> str | None:
    """Where "Back" on a page leads, or ``None`` if the page shows no such link."""
    found = BACK_LINK.search(html)
    return found.group(1).replace("&amp;", "&") if found else None


class TrailTests(RentalarsTestCase):
    """The rules of the trail, without any page (UIX-011)."""

    def test_a_new_page_is_added_and_a_known_one_cuts_the_trail_back(self) -> None:
        trail = step([], "/products/", "/products/?page=3", starts_here=True)
        trail = step(trail, "/products/5/", "/products/5/", starts_here=False)
        trail = step(trail, "/material/models/9/", "/material/models/9/", starts_here=False)
        self.assertEqual([place for place, _address in trail], ["/products/", "/products/5/", "/material/models/9/"])

        again = step(trail, "/products/5/", "/products/5/", starts_here=False)

        self.assertEqual(again, [("/products/", "/products/?page=3"), ("/products/5/", "/products/5/")])

    def test_the_same_page_with_another_query_replaces_its_entry(self) -> None:
        trail = step([("/a/", "/a/")], "/list/", "/list/?page=2", starts_here=False)
        self.assertEqual(step(trail, "/list/", "/list/?page=3", starts_here=False)[-1], ("/list/", "/list/?page=3"))

    def test_a_start_page_begins_anew(self) -> None:
        trail = [("/products/", "/products/"), ("/products/5/", "/products/5/")]
        self.assertEqual(step(trail, "/customers/", "/customers/", starts_here=True), [("/customers/", "/customers/")])

    def test_the_trail_stays_short(self) -> None:
        trail: list[tuple[str, str]] = []
        for number in range(MAX_ENTRIES + 5):
            trail = step(trail, f"/p/{number}/", f"/p/{number}/", starts_here=False)
        self.assertEqual(len(trail), MAX_ENTRIES)
        self.assertEqual(trail[-1][0], f"/p/{MAX_ENTRIES + 4}/")
        long_query = "/list/?q=" + "x" * MAX_ADDRESS_LENGTH
        self.assertEqual(step([], "/list/", long_query, starts_here=False), [("/list/", "/list/")])


class BackLinkTests(UiTestCase):
    """ "Back" in the top left corner leads to the view the user came from (UIX-011)."""

    def setUp(self) -> None:
        super().setUp()
        self.products = [make_product(f"K-{number:03d}", f"Kabel {number} m") for number in range(1, 31)]
        self.product = self.products[4]
        self.detail = reverse("products:detail", args=[self.product.pk])

    def get(self, url: str, client: Client | None = None) -> str:
        """Open a page and return its text."""
        return self.assert_ok((client or self.client).get(url))

    def test_from_a_product_back_to_the_list_as_it_was(self) -> None:
        """The example of the requirement: filter, sort order, page and page length are still there."""
        listing = reverse("products:list") + "?q=Kabel&sort=-name&per_page=25&page=2"
        self.assertIsNone(back_of(self.get(listing)))  # a start page has no way behind it

        self.assertEqual(back_of(self.get(self.detail)), listing)

    def test_after_editing_and_saving_back_still_leads_to_the_list(self) -> None:
        """The browser's own back button would lead into the form that was just saved."""
        listing = reverse("products:list") + "?q=Kabel"
        self.get(listing)
        self.get(self.detail)
        edit = reverse("products:edit", args=[self.product.pk])
        form = self.client.get(edit)
        self.assertEqual(back_of(self.assert_ok(form)), self.detail)  # from the form: back to the product

        saved = self.client.post(edit, form_data(form, name="Kabel, neu benannt"), follow=True)

        self.assertEqual(saved.redirect_chain[-1][0], self.detail)
        self.assertEqual(back_of(self.assert_ok(saved)), listing)

    def test_a_new_record_does_not_lead_back_into_the_empty_form(self) -> None:
        listing = reverse("customers:list")
        self.get(listing)
        form = self.client.get(reverse("customers:create"))
        self.assertEqual(back_of(self.assert_ok(form)), listing)

        created = self.client.post(reverse("customers:create"), form_data(form, name="Neukunde GmbH"), follow=True)

        self.assertIn("Neukunde GmbH", self.assert_ok(created))
        self.assertNotEqual(created.redirect_chain[-1][0], listing)
        self.assertEqual(back_of(created.content.decode()), listing)

    def test_going_round_in_a_circle_does_not_lose_the_way_out(self) -> None:
        """List, product, rental scales, the same product again: back leads to the list, not to the scales."""
        listing = reverse("products:list") + "?page=1"
        self.get(listing)
        self.get(self.detail)
        self.assertEqual(back_of(self.get(reverse("products:scale_list"))), self.detail)

        self.assertEqual(back_of(self.get(self.detail)), listing)

    def test_from_one_record_to_the_next_and_back_step_by_step(self) -> None:
        model = make_model("Kabeltrommel 50 m", product=self.product)
        item = make_items(model, 1)[0]
        models = reverse("material:model_list")
        model_page = reverse("material:model_detail", args=[model.pk])
        item_page = reverse("material:item_detail", args=[item.pk])
        self.get(models)
        self.assertEqual(back_of(self.get(model_page)), models)
        self.assertEqual(back_of(self.get(item_page)), model_page)
        self.assertEqual(back_of(self.get(self.detail)), item_page)
        # ... and each step back shortens the way.
        self.assertEqual(back_of(self.get(item_page)), model_page)
        self.assertEqual(back_of(self.get(model_page)), models)

    def test_the_tabs_of_a_project_count_as_one_page(self) -> None:
        """Back leaves the project; it does not walk through its tabs."""
        project = make_project(customer=make_customer())
        listing = reverse("projects:list") + "?status=confirmed"
        self.get(listing)
        for name in ("projects:detail", "projects:price_overview", "packing:packlist", "projects:history"):
            with self.subTest(tab=name):
                self.assertEqual(back_of(self.get(reverse(name, args=[project.pk]))), listing)
        # The form of the project is a page of its own: back leads to the tab one came from.
        edit = self.get(reverse("projects:edit", args=[project.pk]))
        self.assertEqual(back_of(edit), reverse("projects:history", args=[project.pk]))

    def test_start_pages_show_no_back_link(self) -> None:
        self.get(self.detail)
        for name in ("core:home", "projects:list", "material:model_list", "material:item_list", "products:list"):
            with self.subTest(page=name):
                self.assertIsNone(back_of(self.get(reverse(name))))
        self.assertIsNone(back_of(self.get(reverse("core:search") + "?q=Kabel")))

    def test_search_results_are_a_place_to_come_back_to(self) -> None:
        results = reverse("core:search") + "?q=Kabel+5"
        self.get(results)
        self.assertEqual(back_of(self.get(self.detail)), results)

    def test_without_a_way_behind_back_leads_to_the_start_of_the_section(self) -> None:
        """Someone who opens a product from a bookmark or a link in a mail."""
        visitor = self.browser_of(self.admin_user)  # a second browser, which has not been anywhere yet
        self.assertEqual(back_of(self.get(self.detail, visitor)), reverse("products:list"))
        model = make_model("Stativ")
        another = self.browser_of(self.admin_user)
        self.assertEqual(
            back_of(self.get(reverse("material:model_detail", args=[model.pk]), another)),
            reverse("material:model_list"),
        )

    def test_parts_of_pages_and_downloads_leave_the_way_as_it_is(self) -> None:
        project = make_project(customer=make_customer())
        listing = reverse("projects:list")
        self.get(listing)
        self.get(reverse("projects:detail", args=[project.pk]))
        before = self.client.cookies[COOKIE_NAME].value

        self.htmx("get", reverse("projects:detail", args=[project.pk]))
        self.htmx("get", reverse("projects:planning_notes", args=[project.pk]))
        self.client.get(reverse("products:suggest") + "?q=Kabel")
        self.client.get(reverse("packing:pdf", args=[project.pk]))
        self.client.get("/products/999999/")  # a page that does not exist

        self.assertEqual(self.client.cookies[COOKIE_NAME].value, before)

    def test_a_cookie_that_was_tampered_with_is_ignored(self) -> None:
        """What ends up in a link must come from this application and point into it."""
        self.get(reverse("products:list"))
        for forged in (
            "not signed at all",
            signing.dumps([["/x/", "https://evil.example/"], ["/y/", "/y/"]], salt="rentalars.core.trail"),
            signing.dumps([["/x/", "//evil.example/"], ["/y/", "/y/"]], salt="rentalars.core.trail"),
            signing.dumps({"not": "a list"}, salt="rentalars.core.trail"),
            signing.dumps([["/x/", "/x/"]], salt="another purpose"),
        ):
            with self.subTest(cookie=forged[:30]):
                self.client.cookies[COOKIE_NAME] = forged
                self.assertEqual(back_of(self.get(self.detail)), reverse("products:list"))

    def test_logging_out_forgets_the_way(self) -> None:
        self.get(reverse("products:list"))
        self.get(self.detail)
        self.assertTrue(self.client.cookies[COOKIE_NAME].value)

        self.client.post(reverse("accounts:logout"))
        self.client.get(reverse("accounts:login"))

        self.assertEqual(self.client.cookies[COOKIE_NAME].value, "")


class PageSizeTests(UiTestCase):
    """Lists let the user choose how many entries a page shows; 50 by default (UIX-012)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("XLR-Kabel 5 m")
        make_items(self.model, 120)
        self.items = reverse("material:item_list")

    def rows_of(self, response: Any) -> int:
        """How many material items a list page shows."""
        return len(re.findall(r'href="/material/items/\d+/"', self.assert_ok(response)))

    def test_fifty_by_default_and_the_choice_is_offered(self) -> None:
        response = self.client.get(self.items)
        self.assertEqual(self.rows_of(response), DEFAULT_PAGE_SIZE)
        text = response.content.decode()
        self.assertIn("Je Seite", text)
        self.assertIn('<strong aria-current="true">50</strong>', text)
        for size in (25, 100, 200):
            self.assertIn(f'href="?per_page={size}"', text)
        self.assertEqual(PAGE_SIZES, (25, 50, 100, 200))

    def test_the_chosen_number_is_shown_and_starts_at_page_one(self) -> None:
        response = self.client.get(self.items + "?per_page=100&page=2")
        self.assertEqual(self.rows_of(response), 20)
        text = response.content.decode()
        self.assertIn("Seite 2 von 2", text)
        self.assertIn('<strong aria-current="true">100</strong>', text)
        # Another length means other rows on "page 2": the links of the choice drop the page.
        self.assertIn('href="?per_page=25"', text)
        # Paging keeps the chosen length.
        self.assertIn('href="?per_page=100&amp;page=1"', text)

    def test_filters_and_sort_order_survive_the_choice(self) -> None:
        text = self.assert_ok(self.client.get(self.items + "?q=XLR&sort=-inventory_number&page=2"))
        self.assertIn('href="?q=XLR&amp;sort=-inventory_number&amp;per_page=100"', text)

    def test_the_choice_is_remembered_for_this_list(self) -> None:
        """UIX-050: remembered per user and list, like the columns.

        Requirement UIX-050 asks
        for the choice per list (tests/unit/test_092_ui.py tests it in more lists).
        """
        self.assertEqual(self.rows_of(self.client.get(self.items + "?per_page=25")), 25)
        self.assertNotIn(PAGE_SIZE_COOKIE, self.client.cookies)

        self.assertEqual(self.rows_of(self.client.get(self.items)), 25)
        model_page = self.client.get(reverse("material:model_detail", args=[self.model.pk]))
        self.assertIn('<strong aria-current="true">50</strong>', self.assert_ok(model_page))  # another list
        # The address still wins over what was remembered.
        self.assertEqual(self.rows_of(self.client.get(self.items + "?per_page=200")), 120)

    def test_only_numbers_within_the_bounds_are_accepted(self) -> None:
        """A list of everything on one page would be a cheap way to keep the server busy.

        UIX-050: any whole number from 5 to 1,000 may be typed (it was 25, 50, 100
        and 200 only); anything else is refused with a message, and the list keeps its length.
        """
        for wish in ("5000", "1001", "0", "4", "-1", "abc"):
            with self.subTest(per_page=wish):
                response = self.client.get(self.items, {"per_page": wish})
                self.assertEqual(self.rows_of(response), DEFAULT_PAGE_SIZE)
                self.assertIn("ganze Zahl von 5 bis 1.000", response.content.decode())
        self.assertEqual(self.rows_of(self.client.get(self.items, {"per_page": ""})), DEFAULT_PAGE_SIZE)
        self.assertEqual(self.rows_of(self.client.get(self.items, {"per_page": "51"})), 51)
        self.client.cookies[PAGE_SIZE_COOKIE] = "100000"  # left: ignored and removed
        response = self.client.get(self.items)
        self.assertEqual(self.rows_of(response), 51)
        self.assertEqual(response.cookies[PAGE_SIZE_COOKIE].value, "")

    def test_a_short_list_offers_no_choice(self) -> None:
        MaterialItem.objects.filter(inventory_number__gt=20).delete()
        self.assertNotIn("Je Seite", self.assert_ok(self.client.get(self.items)))

    def test_every_list_offers_the_choice(self) -> None:
        for number in range(60):
            make_product(f"L-{number:03d}", f"Lampe {number}")
            make_customer(f"Kunde {number}")
            make_project(f"Projekt {number}")
            make_model(f"Modell {number}")
        for name in ("products:list", "customers:list", "projects:list", "material:model_list", "core:audit_log"):
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name), {"per_page": "25"}))
                self.assertIn('<strong aria-current="true">25</strong>', text)


class MaterialManagementTabsTests(UiTestCase):
    """Products and material share one entry of the navigation and one row of tabs (UIX-013)."""

    # LOG-002: the tab "Fuhrpark" before "Import", right after "Exemplare". MAT-070: "Ohne Produkt" became "Offene Punkte"
    # (tests/unit/test_092_audits.py); "Audit" after "Prüfungen", for who may change the material.
    TABS = ["Produkte", "Modelle", "Exemplare", "Fuhrpark", "Offene Punkte", "Prüfungen", "Audit", "Import"]

    def tabs_of(self, text: str) -> list[str]:
        tabs = text[text.index('<nav class="tabs"') : text.index("</nav>", text.index('<nav class="tabs"'))]
        return re.findall(r">([^<>]+)</a>", tabs)

    def navigation_of(self, text: str) -> list[str]:
        navigation = text[text.index('<ul class="nav">') : text.index("</ul>", text.index('<ul class="nav">'))]
        return [label.strip() for label in re.findall(r"</svg>([^<>]+)</a>", navigation)]

    def test_one_entry_with_six_tabs_products_first(self) -> None:
        for name in ("products:list", "material:model_list", "material:item_list", "material:import"):
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name)))
                self.assertEqual(self.tabs_of(text), self.TABS)
                # The one entry of the navigation leads to the first tab and is marked on all of them.
                self.assertIn('<a href="/products/" aria-current="page">', text)
                self.assertIn("<h1>Materialverwaltung</h1>", text)
        navigation = self.navigation_of(self.assert_ok(self.client.get(reverse("products:list"))))
        self.assertEqual(
            navigation,
            # Stage 4: shortages moved into "Planung" (VFG-013); "E-Mail" arrived (EML-029) and became the
            # tab "Anfragen" of "Projekte" (EML-042).
            [
                "Projekte",
                "Planung",
                "Materialverwaltung",
                "Buchhaltung",  # Outgoing documents and the monthly statement (tests/unit/test_091_accounting.py)
                "Kunden",
                "Personal",
                "Auswertungen",  # PRJ-115: profitability, for who may read every project and see prices
                "Mein Bereich",  # UIX-026: formerly "Zeiterfassung"
                "Einstellungen",  # UIX-023: formerly "Verwaltung"
            ],
        )

    def test_pages_below_the_tabs_keep_the_entry_marked(self) -> None:
        product = make_stock("K-005", 2, "XLR-Kabel 5 m")
        model = MaterialModel.objects.get(default_product=product)
        for url in (
            reverse("products:detail", args=[product.pk]),
            reverse("material:model_detail", args=[model.pk]),
            reverse("material:item_detail", args=[model.items.first().pk]),
        ):
            self.assertIn('<a href="/products/" aria-current="page">', self.assert_ok(self.client.get(url)), url)

    def test_the_rental_scales_belong_to_the_administration(self) -> None:
        """UIX-013: no button on the product tab; the master data lead there."""
        products = self.assert_ok(self.client.get(reverse("products:list")))
        self.assertNotIn(reverse("products:scale_list"), products)
        administration = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(reverse("products:scale_list"), administration)
        scales = self.assert_ok(self.client.get(reverse("products:scale_list")))
        self.assertIn('<a href="/administration/" aria-current="page">', scales)
        self.assertNotIn('<a href="/products/" aria-current="page">', scales)
        self.assertIn('<a class="back-link no-print" href="/administration/">', scales)

    def test_someone_with_material_only_lands_on_the_models(self) -> None:
        role = Role.objects.create(name="Nur Material", module_levels={"material": 1})
        user = make_user("lagerist")
        user.roles.set([role])
        browser = self.browser_of(user)
        text = self.assert_ok(browser.get(reverse("material:model_list")))
        # LOG-002: the fleet is part of the material administration.
        # MAT-068, MAT-070: "Offene Punkte" instead of "Ohne Produkt"; no "Audit" without write access.
        self.assertEqual(self.tabs_of(text), ["Modelle", "Exemplare", "Fuhrpark", "Offene Punkte", "Prüfungen"])
        self.assertEqual(self.navigation_of(text), ["Materialverwaltung", "Mein Bereich"])
        self.assertIn('<a href="/material/models/" aria-current="page">', text)
        self.assertEqual(browser.get(reverse("products:list")).status_code, 403)

    def test_someone_with_products_only_sees_one_tab(self) -> None:
        role = Role.objects.create(name="Nur Produkte", module_levels={"products": 1})
        user = make_user("vertrieb")
        user.roles.set([role])
        text = self.assert_ok(self.browser_of(user).get(reverse("products:list")))
        self.assertEqual(self.tabs_of(text), ["Produkte"])


class NoBackFromTheNavigationTests(UiTestCase):
    """UIX-041: no page reached from the main navigation shows "Back" – nor any tab of its section.

    The rule holds for every link of the layout around the page – the entries of the sidebar, its action
    button "Zeit erfassen", the search, the links at its foot (notifications, own account) and the buttons of
    the top bar – and for every tab the pages of those links show. Before each page another page is opened, so
    that there is a way behind it: a page that is not a start page (``core.trail.START_PAGES``) would show
    "Back". A new tab or a new link of the layout is walked by this test without being named here. Not
    walked: the back arrow of the phone's top bar (UIX-027), which is "Back" itself.
    """

    #: The layout around a page: everything before ``<main``.
    LAYOUT = re.compile(r"^(.*?)<main ", re.S)
    TAB_BAR = re.compile(r'<nav class="tabs"[^>]*>(.*?)</nav>', re.S)
    LINK = re.compile(r'<a (?![^>]*topbar-back)[^>]*href="(/(?!static/)[^"#]*)"')
    #: Forms of the layout that open a page – the search.
    GET_FORM = re.compile(r'<form [^>]*method="get"[^>]*action="(/[^"]*)"')

    def links_in(self, pattern: re.Pattern[str], text: str) -> list[str]:
        """The addresses of the links inside the parts of a page matched by ``pattern``."""
        return [address.replace("&amp;", "&") for part in pattern.findall(text) for address in self.LINK.findall(part)]

    def layout_links(self, text: str) -> list[str]:
        """Every page the layout leads to: links, and the search with a word."""
        layout = self.LAYOUT.findall(text)[0]
        forms = [f"{action}?q=Kabel" for action in self.GET_FORM.findall(layout)]
        return [*dict.fromkeys(self.links_in(self.LAYOUT, text) + forms)]

    def walk(self, client: Client) -> list[str]:
        """Open every entry of the navigation and every tab of its pages; return the pages that show "Back"."""
        detour = reverse("products:detail", args=[make_product("K-901", "Umweg").pk])
        start = self.assert_ok(client.get(reverse("core:home")))
        entries = self.layout_links(start)
        for expected in ("/times/quick/", "/notifications/", "/account/", "/search/?q=Kabel", "/projects/"):
            self.assertIn(expected, entries)
        seen: set[str] = set()
        showing_back = []
        queue = list(entries)
        while queue:
            address = queue.pop(0)
            if address in seen:
                continue
            seen.add(address)
            client.get(detour)  # a way behind the page
            response = client.get(address, follow=True)
            text = self.assert_ok(response)
            if back_of(text) is not None:
                showing_back.append(address)
            queue += [tab for tab in self.links_in(self.TAB_BAR, text) if tab not in seen]
        self.assertGreater(len(seen), 25)  # navigation entries and their tabs
        return showing_back

    def test_no_back_link_on_the_pages_of_the_navigation_and_their_tabs(self) -> None:
        """The office with every right: projects, service cases, expenses, planning, settings …"""
        self.assertEqual(self.walk(self.client), [])

    def test_no_back_link_for_somebody_who_records_only_their_own_times(self) -> None:
        """Crew see "My area" with the report of their own hours and "My expenses" as tabs."""
        crew = self.browser_for("carla", "Crew")
        home = self.assert_ok(crew.get(reverse("core:home")))
        for address in [*self.layout_links(home), reverse("timetracking:my_expenses")]:
            crew.get(reverse("core:search") + "?q=x")  # a start page: the trail begins there, "Back" would lead to it
            text = self.assert_ok(crew.get(address, follow=True))
            with self.subTest(page=address):
                self.assertIsNone(back_of(text))
            for tab in self.links_in(self.TAB_BAR, text):
                crew.get(reverse("core:search") + "?q=x")
                with self.subTest(tab=tab):
                    self.assertIsNone(back_of(self.assert_ok(crew.get(tab, follow=True))))

    def test_service_cases_and_expenses_by_name(self) -> None:
        """The three pages named in the requirement: Servicefälle, Spesen, Meine Spesen."""
        for name in ("projects:cases", "timetracking:expense_report", "timetracking:my_expenses"):
            self.client.get(reverse("products:list"))
            with self.subTest(page=name):
                self.assertIsNone(back_of(self.assert_ok(self.client.get(reverse(name)))))
