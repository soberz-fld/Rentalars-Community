# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the model suggestions on a product page, the scroll position of the planning page. (PRD-046, PRJ-123, PRJ-064, UIX-056)

(product/planning requirements.) Page and API tests are in tests/unit/test_100_products_planning.py.
"""

from __future__ import annotations

from typing import Any

from rentalars.products.models import Product
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import add_group, add_line, make_items, make_model, make_product, make_stock


class AxeMixin:
    """The accessibility check of the other browser tests, for the elements a selector names."""

    page: Any

    def axe_findings(self, within: str) -> list[str]:
        """What axe-core finds within the elements a selector names – nothing if axe-core is not at hand."""
        axe = _axe_path()
        if axe is None:
            return []
        self.page.wait_for_load_state("networkidle")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run({include: [[within]]},"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )


class ModelSuggestionsInBrowserTests(AxeMixin, BrowserTestCase):
    """(model search) The field "Zugeordnetes Material" of a product suggests models without a product."""

    bypass_csp = True  # axe-core is put into the page

    def open_product(self) -> Any:
        """The page of a product that takes models; returns the type-ahead of the field "Vorhandenes Modell"."""
        product = Product.objects.get(article_number="K-010")
        self.open(f"/products/{product.pk}/")
        return self.page.locator("[data-typeahead]", has=self.page.get_by_label("Vorhandenes Modell"))

    def test_typing_shows_the_free_models_and_names_the_taken_ones(self) -> None:
        free = make_model("Leiter 3-teilig XYZ", category_code="R", manufacturer="Zarges")
        make_model("Leiter mit Produkt", Product.objects.get(article_number="K-010"))
        root = self.open_product()
        field = root.locator("[data-typeahead-input]")
        field.click()
        field.press_sequentially("leit", delay=30)
        enabled = root.locator("[role=option]:not([aria-disabled=true])")
        enabled.first.wait_for()
        self.settle()
        self.assertIn(free.name, root.locator("[role=option]").all_inner_texts()[1])
        self.assertIn("Zarges", " ".join(root.locator("[role=option]").all_inner_texts()))
        taken = root.locator("[role=option][aria-disabled=true]")
        self.assertEqual(taken.count(), 1)
        self.assertIn("gehört schon zu K-010", taken.inner_text())
        self.assertEqual(self.axe_findings("dialog, main"), [])
        # A row that cannot be chosen is skipped by the keyboard and does nothing when clicked.
        taken.click(force=True)
        self.assertEqual(root.locator("[data-typeahead-value]").input_value(), "")
        enabled.nth(1).click()
        self.assertEqual(root.locator("[data-typeahead-value]").input_value(), str(free.pk))
        self.page.get_by_role("button", name="Vorhandenes Modell zuordnen").click()
        self.page.get_by_text("gehört jetzt zu K-010").wait_for()

    def test_the_words_may_be_spread_over_name_and_manufacturer(self) -> None:
        free = make_model("Quasar Zeta", category_code="L", manufacturer="Vortex")
        root = self.open_product()
        field = root.locator("[data-typeahead-input]")
        field.click()
        field.press_sequentially("vortex quasar", delay=30)
        root.locator("[role=option]").first.wait_for()
        self.settle()
        # Waits for the search for the whole text: the list of the first letters is still shown for a moment.
        self.page.wait_for_function("() => document.querySelectorAll('[role=option]').length === 1")
        self.assertIn(free.name, root.locator("[role=option]").first.inner_text())

    def test_the_field_suggests_when_it_is_entered_and_says_so_when_nothing_fits(self) -> None:
        free = make_model("Leiter 3-teilig XYZ", category_code="R")
        root = self.open_product()
        field = root.locator("[data-typeahead-input]")
        field.click()
        root.locator("[role=option]").first.wait_for()
        self.assertIn(free.name, " ".join(root.locator("[role=option]").all_inner_texts()))
        field.press_sequentially("qqqq", delay=30)
        message = root.locator("[role=option][aria-disabled=true]")
        message.wait_for()
        self.settle()
        self.assertIn("Kein Modell gefunden", message.inner_text())
        self.assertEqual(root.locator("[role=option]:not([aria-disabled=true])").count(), 0)


class GroupSaveKeepsPlaceTests(BrowserTestCase):
    """(subgroup scroll) Saving a group on a long planning page keeps the scroll position."""

    def long_project(self) -> None:
        for index in range(6):
            group = add_group(self.project, f"Zusatzgruppe {index}")
            for number in range(5):
                product = make_stock(f"K-9{index}{number}", 20, f"Zusatzartikel {index}-{number}")
                add_line(self.project, product, 2, group=group)

    def scrolled_to(self, name: str) -> int:
        """Scroll the section of a group into view, a little further, and return the position."""
        self.group(name).scroll_into_view_if_needed()
        self.page.evaluate("() => window.scrollTo(0, window.scrollY + 40)")
        position = self.page.evaluate("() => window.scrollY")
        self.assertGreater(position, 500, "the page is long enough to make the test mean something")
        return position

    def test_saving_a_group_keeps_the_scroll_position(self) -> None:
        self.long_project()
        self.open_planning()
        before = self.scrolled_to("Zusatzgruppe 3")
        self.group("Zusatzgruppe 3").get_by_role("button", name="Gruppe bearbeiten").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        dialog.locator("#id_description").fill("Neue Beschreibung")
        dialog.get_by_role("button", name="Gruppe speichern").click()
        self.page.locator("dialog[open]").wait_for(state="detached")
        self.settle()
        self.assertIn("Neue Beschreibung", self.page.inner_text("body"))
        self.assertLess(abs(self.page.evaluate("() => window.scrollY") - before), 5)

    def test_copying_a_group_and_switching_it_to_optional_keep_the_position_and_the_open_details(self) -> None:
        self.long_project()
        self.open_planning()
        first = self.page.locator("#planning details").first
        first.locator("summary").click()
        self.assertTrue(first.evaluate("element => element.open"))
        before = self.scrolled_to("Zusatzgruppe 4")
        self.group("Zusatzgruppe 4").get_by_role("button", name="Optionale Teilgruppe").click()
        self.settle()
        self.assertLess(abs(self.page.evaluate("() => window.scrollY") - before), 5)
        self.assertTrue(self.page.locator("#planning details").first.evaluate("element => element.open"))

    def test_saving_a_line_keeps_the_scroll_position(self) -> None:
        self.long_project()
        self.open_planning()
        before = self.scrolled_to("Zusatzgruppe 3")
        self.group("Zusatzgruppe 3").locator("tr[data-line]").nth(1).get_by_role(
            "button", name="Position bearbeiten"
        ).click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        dialog.locator("#id_quantity").fill("3")
        dialog.get_by_role("button", name="Speichern").last.click()
        self.page.locator("dialog[open]").wait_for(state="detached")
        self.settle()
        self.assertLess(abs(self.page.evaluate("() => window.scrollY") - before), 5)


class OpenPlanningFollowsTheStockTests(AxeMixin, BrowserTestCase):
    """(stock refresh) A planning tab that stays open follows a model linked to a product in another tab."""

    watch_changes = True  # the page asks the server whether the stock changed – that is what is tested
    bypass_csp = True

    def setUp(self) -> None:
        super().setUp()
        self.product = make_product("K-801", "Wunschartikel")
        self.line = add_line(self.project, self.product, 2).line
        self.model = make_model("Neues Modell 801", category_code="S")
        make_items(self.model, 5)
        self.requests: list[str] = []
        self.page.on("request", lambda request: self.requests.append(request.url.replace(self.live_server_url, "")))

    def cell(self) -> Any:
        return self.page.locator(f"#line-{self.line.pk} [data-stock-cell]")

    def asked(self, part: str) -> int:
        return len([url for url in self.requests if part in url])

    def come_back_to_the_tab(self) -> None:
        """What the browser does when the user switches back to the tab."""
        self.page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")

    def link_in_a_second_tab(self) -> None:
        """Link the model to the product on the product page, in another tab, the way a user does."""
        other = self.page.context.new_page()
        other.goto(f"{self.live_server_url}/products/{self.product.pk}/")
        field = other.locator("[data-typeahead]", has=other.get_by_label("Vorhandenes Modell")).locator(
            "[data-typeahead-input]"
        )
        field.click()
        field.press_sequentially("Neues Modell", delay=30)
        other.locator("[role=option]:not([aria-disabled=true])").first.wait_for()
        other.wait_for_load_state("networkidle")
        field.press("Enter")
        other.get_by_role("button", name="Vorhandenes Modell zuordnen").click()
        other.get_by_text("gehört jetzt zu K-801").wait_for()
        other.close()

    def test_the_availability_follows_without_losing_what_is_typed(self) -> None:
        self.open_planning()
        self.settle()
        self.assertIn("Fehlmenge 2", self.cell().inner_text())
        self.assertIn("Es fehlen 2 Stück", self.page.inner_text("#planning-notes"))
        typed = self.page.locator("#planning .group-name")
        typed.fill("Halb getippte Gruppe")
        self.page.evaluate("() => window.scrollTo(0, 120)")
        before = self.page.evaluate("() => window.scrollY")

        self.link_in_a_second_tab()
        self.requests.clear()
        self.come_back_to_the_tab()
        self.page.wait_for_function(
            "selector => document.querySelector(selector).innerText.includes('frei')",
            arg=f"#line-{self.line.pk} [data-stock-cell]",
        )
        self.settle()

        self.assertNotIn("Fehlmenge", self.cell().inner_text())
        self.assertNotIn("fehlen", self.page.inner_text("#planning-notes"))
        self.assertEqual(typed.input_value(), "Halb getippte Gruppe")
        self.assertLess(abs(self.page.evaluate("() => window.scrollY") - before), 5)
        # Cost: one question for the state and, since it moved, one for the figures – no page load.
        # (Coming back to the tab also fires the window's "focus"; the question is asked once per event, at most.)
        self.assertIn(self.asked("/changes/"), (1, 2), self.requests)
        self.assertEqual(self.asked("/planning/availability/"), 1, self.requests)
        self.assertEqual(
            len(
                [
                    url
                    for url in self.requests
                    if url.startswith(f"/projects/{self.project.pk}/") and "/planning/" not in url
                ]
            ),
            0,
            self.requests,
        )
        self.assertEqual(self.axe_findings("#planning"), [])

        # Nothing changed since: coming back again asks the cheap question only.
        self.requests.clear()
        self.come_back_to_the_tab()
        self.settle()
        self.assertIn(self.asked("/changes/"), (1, 2), self.requests)
        self.assertEqual(self.asked("/planning/availability/"), 0, self.requests)

    def test_the_own_saving_does_not_ask_for_the_figures_again(self) -> None:
        self.open_planning()
        self.settle()
        self.page.locator(f"#line-{self.line.pk}").get_by_role("button", name="Position bearbeiten").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        dialog.locator("#id_quantity").fill("3")
        self.requests.clear()
        dialog.get_by_role("button", name="Speichern").last.click()
        self.page.locator("dialog[open]").wait_for(state="detached")
        self.settle()
        self.page.wait_for_timeout(600)  # the page adopts the new state 300 ms after its own change
        self.settle()
        self.assertEqual(self.asked("/planning/availability/"), 0, self.requests)
        self.assertIn("Fehlmenge 3", self.cell().inner_text())


class DiscountTargetInBrowserTests(AxeMixin, BrowserTestCase):
    """(discount target) The dialog of the overall discount: four ways, a live preview, accessible."""

    bypass_csp = True

    def open_dialog(self) -> Any:
        self.open_planning()
        self.page.get_by_role("button", name="Gesamtrabatt festlegen").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        return dialog

    def test_a_typed_target_shows_the_stored_percentage_before_saving(self) -> None:
        dialog = self.open_dialog()
        for label in ("Gesamtrabatt in Prozent", "Gesamtrabatt als Betrag", "Zielbetrag netto", "Zielbetrag brutto"):
            self.assertEqual(dialog.get_by_label(label).count(), 1, label)
        dialog.get_by_label("Zielbetrag netto").fill("1000")
        preview = dialog.locator("#overall-discount-preview")
        preview.get_by_text("Gespeicherter Prozentsatz").wait_for()
        self.settle()
        self.assertIn("nicht neu berechnet", dialog.inner_text())
        self.assertEqual(self.axe_findings("dialog[open]"), [])
        dialog.get_by_role("button", name="Speichern").click()
        self.page.locator("dialog[open]").wait_for(state="detached")
        self.settle()
        self.assertIn("Gesamtrabatt", self.page.inner_text("#planning-totals, #planning"))

    def test_switching_to_a_gross_target_replaces_the_preview(self) -> None:
        dialog = self.open_dialog()
        dialog.get_by_label("Zielbetrag brutto").fill("1190")
        dialog.locator("#overall-discount-preview").get_by_text("Gespeicherter Prozentsatz").wait_for()
        self.settle()
        first = dialog.locator("#overall-discount-preview").inner_text()
        dialog.get_by_label("Zielbetrag brutto").fill("")
        dialog.get_by_label("Zielbetrag netto").fill("2000000")
        dialog.locator("#overall-discount-preview").get_by_text("liegt über der Summe ohne Rabatt").wait_for()
        self.assertNotEqual(first, dialog.locator("#overall-discount-preview").inner_text())


class PieceShareInBrowserTests(AxeMixin, BrowserTestCase):
    """(piece share) The dialog of a line takes several wished items; the planning names the share."""

    bypass_csp = True

    def test_several_items_are_wished_and_the_planning_names_the_share(self) -> None:
        product = make_product("K-802", "Kabelpaket", pieces_per_product=10)
        items = make_items(make_model("Kabel 802", product), 12)
        line = add_line(self.project, product, 1).line
        self.open_planning()
        row = self.page.locator(f"#line-{line.pk}")
        row.get_by_role("button", name="Position bearbeiten").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        dialog.get_by_label("Weitere bestimmte Exemplare (ID)").fill(f"{items[1].display_id}, {items[2].display_id}")
        dialog.locator("[data-typeahead-input]").first.fill(items[0].display_id)
        self.assertEqual(self.axe_findings("dialog[open]"), [])
        dialog.get_by_role("button", name="Speichern").last.click()
        self.page.locator("dialog[open]").wait_for(state="detached")
        self.settle()
        self.assertIn("3 von 10 Stück", row.inner_text())
        line.refresh_from_db()
        self.assertEqual(len(line.wished_items), 3)
