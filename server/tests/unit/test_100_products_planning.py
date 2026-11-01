# SPDX-License-Identifier: GPL-3.0-or-later
"""Requirements in the project planning and the products. (PRJ-123, UIX-056)

* The overall discount of a project can also be given by a target amount, net or gross, and the percentage adapts
  automatically (PRJ-123).
* The search field under "Zugeordnetes Material" of a product, for adding existing models, shows suggestions
  (PRD-046).
* When a product is linked to a model while the project planning is open in a second tab, the stock in that open tab
  is updated – the page asks for what changed in the material (UIX-020).
* When a product or set that contains e.g. 10 pieces of a material is assigned in the planning and a certain item is
  stored there as wish, the quantity of the line adapts to the share, and the packing list shows exactly that wished
  item. Wished items count as pieces of a line (PRJ-064, PRD-052).

The scroll position after saving a group is a matter of the browser: tests/browser/test_100_products_planning_in_browser.py.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import ProjectScope
from rentalars.masterdata.models import TaxRate
from rentalars.packing import services as packing
from rentalars.projects import services
from rentalars.projects.overall_target import solve
from rentalars.projects.pricing import compute_project_prices
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_product,
    make_project,
    make_stock,
)
from tests.ui.base import UiTestCase, form_data

D = Decimal


def reduced_rate() -> TaxRate:
    """The tax rate of 7 %, made when a test needs it."""
    return TaxRate.objects.get_or_create(rate=D("7"), defaults={"name": "Ermäßigt"})[0]


def vat_project(**fields: object) -> object:
    """200,00 net: 100,00 at 19 % and 100,00 at 7 % – gross 226,00."""
    project = make_project(rental_days=1, **fields)
    reduced = reduced_rate()
    add_line(project, make_product("L-001", price="100.00", billing_mode="flat"), 1)
    add_line(project, make_product("L-002", price="100.00", billing_mode="flat", tax_rate=reduced), 1)
    return project


class DiscountTargetTests(RentalarsTestCase):
    """(discount target) The percentage that brings the project to a net or gross target."""

    def test_a_net_target_gives_the_percentage_and_the_total(self) -> None:
        project = vat_project()
        result = solve(project, net=D("180.00"))
        self.assertEqual((result.percent, result.discount, result.net_total), (D("10.00"), D("20.00"), D("180.00")))
        self.assertTrue(result.is_exact)
        self.assertEqual(result.gross_total, D("203.40"))  # 90 + 17.10 and 90 + 6.30 tax, shares lowered alike

    def test_a_gross_target_counts_the_tax_of_every_rate(self) -> None:
        project = vat_project()
        result = solve(project, gross=D("203.40"))
        self.assertEqual((result.percent, result.net_total, result.gross_total), (D("10.00"), D("180.00"), D("203.40")))
        # A plain division by the tax of one rate would be wrong: 200 at 7 and 19 mix to 13 %, not 19 %.
        services.set_overall_discount(project, rights=ALL_RIGHTS, percent=result.percent)
        self.assertEqual(compute_project_prices(project).gross_total, D("203.40"))

    def test_what_is_stored_is_what_the_pricing_code_shows(self) -> None:
        """Net and gross targets over many amounts: the figures named are those of the project afterwards."""
        project = vat_project()
        exact = 0
        for cents in range(22600, 14000, -331):
            target = D(cents) / 100
            result = solve(project, gross=target)
            services.set_overall_discount(project, rights=ALL_RIGHTS, percent=result.percent)
            prices = compute_project_prices(project)
            self.assertEqual((prices.net_total, prices.gross_total), (result.net_total, result.gross_total))
            self.assertLessEqual(abs(prices.gross_total - target), D("0.01"), target)
            exact += result.is_exact
        self.assertGreater(exact, 15, "nearly every amount is reached to the cent")
        for cents in range(20000, 9000, -517):
            target = D(cents) / 100
            result = solve(project, net=target)
            services.set_overall_discount(project, rights=ALL_RIGHTS, percent=result.percent)
            self.assertEqual(compute_project_prices(project).net_total, target)

    def test_the_percentage_has_as_many_places_as_the_cent_needs(self) -> None:
        project = make_project(rental_days=1)
        add_line(project, make_product("L-003", price="12345.67", billing_mode="flat"), 1)
        result = solve(project, net=D("10000.00"))
        self.assertTrue(result.is_exact)
        self.assertEqual(result.net_total, D("10000.00"))
        self.assertGreater(result.percent.as_tuple().exponent * -1, 2, "more than two places were needed")
        round_one = solve(project, net=D("11111.10"))  # exactly 10 %
        self.assertEqual(round_one.percent, D("10.00"))

    def test_the_rules_of_the_pricing_code_come_first(self) -> None:
        """Group discounts, optional lines and surcharges are in the sum the target is measured against."""
        project = make_project(rental_days=1)
        group = add_group(project, "Licht", discount_percent=D("50"))
        add_line(project, make_product("L-004", price="200.00", billing_mode="flat"), 1, group=group)
        add_line(project, make_product("L-005", price="40.00", billing_mode="flat"), 1, variant="optional")
        before = compute_project_prices(project).net_before_overall_discount
        self.assertEqual(before, D("100.00"))
        result = solve(project, net=D("90.00"))
        self.assertEqual((result.percent, result.net_before), (D("10.00"), D("100.00")))

    def test_the_target_stays_stored_and_is_not_recalculated_when_the_project_changes(self) -> None:
        project = vat_project()
        services.set_overall_discount_to_target(project, rights=ALL_RIGHTS, net=D("180.00"))
        project.refresh_from_db()
        self.assertEqual(project.overall_discount_percent, D("10.00"))
        add_line(project, make_product("L-006", price="100.00", billing_mode="flat"), 1)
        project.refresh_from_db()
        self.assertEqual(project.overall_discount_percent, D("10.00"))
        self.assertEqual(compute_project_prices(project).net_total, D("270.00"))

    def test_a_target_equal_to_the_sum_removes_the_discount(self) -> None:
        project = vat_project(overall_discount_percent=D("10"))
        result = services.set_overall_discount_to_target(project, rights=ALL_RIGHTS, net=D("200.00"))
        project.refresh_from_db()
        self.assertIsNone(result.percent)
        self.assertIsNone(project.overall_discount_percent)

    def test_a_target_of_nothing_is_a_discount_of_everything(self) -> None:
        result = solve(vat_project(), net=D("0"))
        self.assertEqual((result.percent, result.net_total, result.gross_total), (D("100.00"), D("0.00"), D("0.00")))

    def test_what_cannot_be_asked_for(self) -> None:
        project = vat_project()
        for given in ({"net": D("200.01")}, {"gross": D("226.01")}, {"net": D("-1")}, {}, {"net": D(1), "gross": D(1)}):
            with self.assertRaises(ValidationError, msg=str(given)):
                solve(project, **given)
        with self.assertRaises(ValidationError):
            solve(make_project("Leer"), net=D("10"))

    def test_the_service_needs_the_rights_and_an_open_project(self) -> None:
        from tests.unit.test_094_overall_discount import no_price_rights

        project = vat_project()
        with self.assertRaises(ValidationError):
            services.set_overall_discount_to_target(project, rights=no_price_rights(), net=D("100"))
        project.status = "closed"
        with self.assertRaises(ValidationError):
            services.set_overall_discount_to_target(project, rights=ALL_RIGHTS, net=D("100"))


class DiscountTargetPageTests(UiTestCase):
    """The dialog of the overall discount: four ways, a preview, a message."""

    def setUp(self) -> None:
        super().setUp()
        self.project = vat_project()
        self.url = reverse("projects:overall_discount", args=[self.project.pk])

    def test_the_dialog_offers_the_four_ways_and_says_the_percentage_stays(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        for text in ("Gesamtrabatt in Prozent", "Gesamtrabatt als Betrag", "Zielbetrag netto", "Zielbetrag brutto"):
            self.assertIn(text, page)
        self.assertIn("200,00 € netto, 226,00 € brutto", page)
        self.assertIn("nicht neu berechnet", page)
        self.assertIn('hx-trigger="input from:closest form delay:500ms"', page)

    def test_a_net_target_is_stored_as_percentage_and_named(self) -> None:
        response = self.htmx(
            "post", self.url, {"percent": "", "amount": "", "target_net": "180,00", "target_gross": ""}
        )
        text = response.content.decode()
        self.assertIn("Gesamtrabatt von 10 % gespeichert", text)
        self.assertIn("180,00 € netto, 203,40 € brutto", text)
        self.project.refresh_from_db()
        self.assertEqual(self.project.overall_discount_percent, D("10.00"))
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Gesamtrabatt 10 %", planning)

    def test_a_gross_target_that_is_not_reached_to_the_cent_says_so(self) -> None:
        # Tax rounding makes some gross amounts impossible. Found by trying every cent of this project (gross
        # 1,14): 1,13 cannot be reached – 1,12 and 1,14 can – and neither can 1,11, 1,01, 0,90 and others.
        project = make_project("Cent", rental_days=1)
        add_line(project, make_product("L-007", price="0.50", billing_mode="flat"), 1)
        add_line(project, make_product("L-008", price="0.50", billing_mode="flat", tax_rate=reduced_rate()), 1)
        result = solve(project, gross=D("1.13"))
        self.assertFalse(result.is_exact)
        self.assertEqual(result.gross_total, D("1.12"))
        self.assertTrue(solve(project, gross=D("1.12")).is_exact)
        url = reverse("projects:overall_discount", args=[project.pk])
        text = self.htmx("post", url, {"percent": "", "amount": "", "target_net": "", "target_gross": "1,13"})
        self.assertIn("nicht auf den Cent erreichen", text.content.decode())

    def test_percent_and_amount_work_as_before_next_to_a_stored_percentage(self) -> None:
        services.set_overall_discount(self.project, rights=ALL_RIGHTS, percent=D("12.5"))
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('value="12,5"', page)  # not "12,500000"
        self.client.post(self.url, {"percent": "12,5", "amount": "30", "target_net": "", "target_gross": ""})
        self.project.refresh_from_db()
        self.assertEqual(
            (self.project.overall_discount_percent, self.project.overall_discount_amount), (None, D("30.00"))
        )

    def test_a_target_typed_next_to_the_stored_percentage_wins_over_it(self) -> None:
        services.set_overall_discount(self.project, rights=ALL_RIGHTS, percent=D("12.5"))
        self.client.post(self.url, {"percent": "12,5", "amount": "", "target_net": "150", "target_gross": ""})
        self.project.refresh_from_db()
        self.assertEqual(self.project.overall_discount_percent, D("25.00"))

    def test_two_typed_values_are_refused(self) -> None:
        response = self.client.post(self.url, {"percent": "10", "amount": "", "target_net": "150", "target_gross": ""})
        self.assertIn("Nutze nur eines davon", response.content.decode())
        self.project.refresh_from_db()
        self.assertIsNone(self.project.overall_discount_percent)

    def test_a_target_above_the_sum_is_explained_in_the_dialog(self) -> None:
        response = self.client.post(self.url, {"percent": "", "amount": "", "target_net": "300", "target_gross": ""})
        self.assertIn("liegt über der Summe ohne Rabatt (200,00 €)", response.content.decode())
        self.project.refresh_from_db()
        self.assertIsNone(self.project.overall_discount_percent)

    def test_the_preview_tells_the_result_without_saving(self) -> None:
        shown = self.client.get(self.url, {"preview": "1", "percent": "", "amount": "", "target_gross": "203,40"})
        text = shown.content.decode()
        self.assertIn("Gespeicherter Prozentsatz: <strong>10 %</strong>", text)
        self.assertIn("<strong>180,00 € netto</strong>, <strong>203,40 € brutto</strong>", text)
        self.assertNotIn("nächstliegende", text)
        plain = self.client.get(self.url, {"preview": "1", "percent": "50", "amount": "", "target_net": ""}).content
        self.assertIn("100,00 € netto", plain.decode())
        none = self.client.get(self.url, {"preview": "1", "percent": "", "amount": ""}).content.decode()
        self.assertIn("Kein Gesamtrabatt.", none)
        wrong = self.client.get(self.url, {"preview": "1", "target_net": "999"}).content.decode()
        self.assertIn("liegt über der Summe ohne Rabatt", wrong)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.overall_discount_percent)

    def test_without_the_price_right_the_preview_is_refused_too(self) -> None:
        Role.objects.create(
            name="Planung ohne Preise", module_levels={"projects": 2}, special_rights=[], project_scope=ProjectScope.ALL
        )
        browser = self.browser_for("planer", "Planung ohne Preise")
        self.assertEqual(browser.get(self.url, {"preview": "1", "target_net": "100"}).status_code, 403)


class DiscountTargetApiTests(ApiTestCase):
    """POST /projects/{id}/overall-discount."""

    def test_a_target_is_stored_and_answered_with_the_sums(self) -> None:
        project = vat_project()
        base = f"{API}/projects/{project.pk}/overall-discount"
        answer = self.admin.post(base, {"target_gross": "203.40"}, format="json")
        self.assertEqual(answer.status_code, 200, answer.content)
        body = answer.json()
        self.assertEqual(
            (body["overall_discount_percent"], body["net_total"], body["gross_total"], body["exact"], body["saved"]),
            ("10.00", "180.00", "203.40", True, True),
        )
        self.assertEqual(
            (body["net_before_overall_discount"], body["gross_before_overall_discount"]), ("200.00", "226.00")
        )
        project.refresh_from_db()
        self.assertEqual(project.overall_discount_percent, D("10.00"))
        read = self.admin.get(f"{API}/projects/{project.pk}").json()
        self.assertEqual(read["overall_discount_percent"], "10.000000")

    def test_a_dry_run_saves_nothing(self) -> None:
        project = vat_project()
        answer = self.admin.post(
            f"{API}/projects/{project.pk}/overall-discount", {"target_net": "150", "dry_run": True}, format="json"
        )
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual((answer.json()["overall_discount_percent"], answer.json()["saved"]), ("25.00", False))
        project.refresh_from_db()
        self.assertIsNone(project.overall_discount_percent)

    def test_percent_amount_and_removing_go_through_the_same_door(self) -> None:
        project = vat_project()
        base = f"{API}/projects/{project.pk}/overall-discount"
        self.assertEqual(self.admin.post(base, {"percent": "10"}, format="json").json()["net_total"], "180.00")
        self.assertEqual(self.admin.post(base, {"amount": "30"}, format="json").json()["net_total"], "170.00")
        gone = self.admin.post(base, {}, format="json")
        self.assertEqual((gone.json()["overall_discount"], gone.json()["net_total"]), ("0.00", "200.00"))
        project.refresh_from_db()
        self.assertEqual((project.overall_discount_percent, project.overall_discount_amount), (None, None))

    def test_what_is_refused(self) -> None:
        project = vat_project()
        base = f"{API}/projects/{project.pk}/overall-discount"
        self.assert_error(self.admin.post(base, {"target_net": "300"}, format="json"), 400, "validation_error")
        self.assert_error(
            self.admin.post(base, {"target_net": "100", "target_gross": "100"}, format="json"), 400, "validation_error"
        )
        self.assert_error(self.admin.post(base, {"target_net": "abc"}, format="json"), 400, "validation_error")
        self.assert_error(self.admin.post(base, {"percent": "101"}, format="json"), 400, "validation_error")
        empty = make_project("Leer")
        self.assert_error(
            self.admin.post(f"{API}/projects/{empty.pk}/overall-discount", {"target_net": "10"}, format="json"),
            400,
            "validation_error",
        )

    def test_without_the_price_right_it_is_forbidden(self) -> None:
        Role.objects.create(
            name="Planung ohne Preise", module_levels={"projects": 2}, special_rights=[], project_scope=ProjectScope.ALL
        )
        project = vat_project()
        client = self.client_for("planer", "Planung ohne Preise")
        refused = client.post(f"{API}/projects/{project.pk}/overall-discount", {"target_net": "100"}, format="json")
        self.assertEqual(refused.status_code, 403)
        project.refresh_from_db()
        self.assertIsNone(project.overall_discount_percent)


class ModelSuggestionTests(UiTestCase):
    """(model search) PRD-046: what the field "Zugeordnetes Material" suggests."""

    def suggest(self, text: str, client=None) -> list[dict]:
        response = (client or self.client).get(reverse("material:model_suggest"), {"q": text})
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def test_the_words_may_be_spread_over_name_manufacturer_and_category(self) -> None:
        from tests.helpers import make_model

        free = make_model("Aura XIP", category_code="L", manufacturer="Martin")
        self.assertEqual([row["id"] for row in self.suggest("martin aura")], [free.pk])
        self.assertEqual([row["id"] for row in self.suggest("licht xip")], [free.pk])
        self.assertEqual([row["id"] for row in self.suggest("martin zzz")][-1:], [""])  # only the message
        self.assertEqual(self.suggest("martin aura")[0]["detail"], "Martin")

    def test_models_with_a_product_are_named_but_cannot_be_chosen(self) -> None:
        from tests.helpers import make_model

        free = make_model("Leiter 3-teilig", category_code="R")
        taken = make_model("Leiter 4-teilig", make_product("R-010"))
        rows = self.suggest("leiter")
        self.assertEqual([row["id"] for row in rows], [free.pk, ""])
        self.assertTrue(rows[1]["disabled"])
        self.assertEqual((rows[1]["label"], rows[1]["hint"]), (taken.name, "gehört schon zu R-010"))

    def test_an_empty_text_lists_the_first_free_models(self) -> None:
        from tests.helpers import make_model

        one = make_model("Anker", category_code="R")
        two = make_model("Boje", category_code="R")
        self.assertEqual([row["id"] for row in self.suggest("")], [one.pk, two.pk])

    def test_a_search_without_a_hit_says_so_instead_of_staying_empty(self) -> None:
        rows = self.suggest("qqqqq")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["disabled"])
        self.assertIn("Kein Modell gefunden", rows[0]["label"])
        everything_taken = self.suggest("")
        self.assertTrue(all(row.get("disabled") for row in everything_taken) or everything_taken == [])

    def test_the_field_is_marked_to_suggest_on_entry(self) -> None:
        product = make_product("K-005")
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[product.pk])))
        self.assertIn("data-typeahead-on-focus", page)

    def test_without_the_right_to_read_material_nothing_is_suggested(self) -> None:
        Role.objects.create(name="Keine", module_levels={"projects": 1})
        self.assertEqual(self.browser_for("kai", "Keine").get(reverse("material:model_suggest")).status_code, 403)


class StockRefreshTests(UiTestCase):
    """(stock refresh) UIX-020: an open planning page follows the material – models, items, products."""

    def setUp(self) -> None:
        super().setUp()
        from tests.helpers import make_model

        self.project = make_project("Bestand", rental_days=1)
        self.product = make_product("K-800", price="10.00")
        self.line = add_line(self.project, self.product, 2).line
        self.model = make_model("Bestandsmodell", category_code="S")
        self.stamp_url = reverse("core:changes")
        self.availability_url = reverse("projects:planning_availability", args=[self.project.pk])

    def stamp(self, client=None) -> str:
        key = f"stock:{self.project.pk}"
        return (client or self.client).get(self.stamp_url, {"keys": key}).json()["stamps"][key]

    def test_the_planning_page_watches_the_stock_and_knows_where_to_ask(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn(f"stock:{self.project.pk}", page.split('data-watch="')[1].split('"')[0])
        self.assertIn(f'data-stock-url="{self.availability_url}"', page)
        self.assertIn("data-stock-cell", page)
        other = self.assert_ok(self.client.get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertNotIn("stock:", other.split('data-watch="')[1].split('"')[0])

    def test_linking_a_model_to_a_product_moves_the_stamp(self) -> None:
        from tests.helpers import make_items

        before = self.stamp()
        self.assertEqual(self.stamp(), before)  # asking again changes nothing
        make_items(self.model, 3)
        self.model.default_product = self.product
        self.model.save()
        after = self.stamp()
        self.assertNotEqual(after, before)
        self.assertNotIn(".", after)  # the script does not count it after the page's own change (PER-033)

    def test_the_figures_follow_the_link(self) -> None:
        from tests.helpers import make_items

        before = self.assert_ok(self.client.get(self.availability_url))
        self.assertIn(f'data-stock-line="{self.line.pk}"', before)
        self.assertIn("Fehlmenge 2", before)
        make_items(self.model, 5)
        self.model.default_product = self.product
        self.model.save()
        after = self.assert_ok(self.client.get(self.availability_url))
        self.assertNotIn("Fehlmenge", after)
        self.assertIn("frei", after)

    def test_the_hints_above_the_lines_come_with_the_answer(self) -> None:
        answer = self.assert_ok(self.client.get(self.availability_url))
        notes = answer.split("<template data-stock-notes>")[1]
        self.assertIn("Es fehlen 2 Stück", notes)
        self.assertIn('id="planning-notes"', notes)

    def test_nothing_for_whoever_may_not_see_the_availability(self) -> None:
        Role.objects.create(name="Ohne Bestand", module_levels={"projects": 2}, special_rights=[])
        client = self.browser_for("kai", "Ohne Bestand")
        self.assertEqual(self.stamp(client), "")
        self.assertNotIn("data-stock-line", client.get(self.availability_url).content.decode())

    def test_without_the_projects_module_the_page_is_closed(self) -> None:
        Role.objects.create(name="Nur Material", module_levels={"material": 1})
        self.assertEqual(self.browser_for("lea", "Nur Material").get(self.availability_url).status_code, 403)

    def test_a_deleted_project_has_no_stamp(self) -> None:
        self.assertEqual(self.client.get(self.stamp_url, {"keys": "stock:999999"}).json()["stamps"]["stock:999999"], "")

    def test_the_question_costs_a_handful_of_indexed_queries(self) -> None:
        """(stock refresh) Cost: the stamp is one query per kind of object plus the project – no planning."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.stamp()  # content types and rights are cached from here on
        with CaptureQueriesContext(connection) as queries:
            self.stamp()
        stock = [query["sql"] for query in queries.captured_queries if "core_auditlogentry" in query["sql"].lower()]
        # (R3-7) 9 kinds since the categories (buffers) and the system settings are watched too.
        self.assertEqual(len(stock), 9)
        self.assertTrue(all("MAX(" in sql.upper() for sql in stock))
        self.assertLessEqual(len(queries), 16, [query["sql"][:80] for query in queries.captured_queries])


# --- (piece share) -----------------------------------------------------------------------------------------


def make_pack(article_number: str = "K-701", items: int = 25, pieces: int = 10) -> object:
    """A product of ``pieces`` items each with one model and ``items`` items – "XLR cable, 10-pack"."""
    from tests.helpers import make_items, make_model

    product = make_product(article_number, "XLR-Kabel 10er-Pack", pieces_per_product=pieces, price="50.00")
    make_items(make_model(f"XLR-Kabel {article_number}", product), items)
    return product


def items_of(product: object, *numbers: int) -> list:
    """The items of a product by their position (1 = the first)."""
    from rentalars.material.models import MaterialItem

    found = list(MaterialItem.objects.for_product(product.pk).order_by("inventory_number"))
    return [found[number - 1] for number in numbers]


class PieceShareTests(RentalarsTestCase):
    """(piece share) PRJ-064, PRD-052: wished items are exactly some of the pieces of a line.

    The decision: a line of 1 × "10-pack" stands for ten pieces. Each item the planner wishes for covers one of
    them; the rest of the pack comes from any item. The quantity of the line and so the price stay as they are.
    """

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack()
        self.project = make_project("Anteil", rental_days=1)
        self.line = add_line(self.project, self.pack, 1).line

    def wish(self, *numbers: int) -> object:
        return services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=items_of(self.pack, *numbers)).line

    def test_a_line_stands_for_quantity_times_pieces(self) -> None:
        self.assertEqual(self.line.pieces_total, 10)
        self.line.quantity = D("3")
        self.assertEqual(self.line.pieces_total, 30)

    def test_several_wished_items_are_stored_the_first_one_leads(self) -> None:
        line = self.wish(3, 1, 2)
        line.refresh_from_db()
        first, second, third = items_of(self.pack, 3, 1, 2)
        self.assertEqual(line.preferred_item_id, first.pk)
        self.assertEqual(line.wished_item_ids, [first.pk, second.pk, third.pk][:1] + sorted([second.pk, third.pk]))
        self.assertEqual(line.preferred_model_id, first.material_model_id)

    def test_the_price_does_not_move(self) -> None:
        before = compute_project_prices(self.project).net_total
        self.wish(1, 2, 3)
        self.assertEqual(compute_project_prices(self.project).net_total, before)
        self.assertEqual(before, D("50.00"))
        self.line.refresh_from_db()
        self.assertEqual(self.line.quantity, D("1"))

    def test_the_availability_does_not_move_and_counts_the_pack(self) -> None:
        from rentalars.availability.engine import AvailabilityEngine
        from tests.helpers import at

        free_before = AvailabilityEngine().availability([self.pack.pk], at(10), at(12))[self.pack.pk].free
        self.wish(1, 2)
        self.assertEqual(
            AvailabilityEngine().availability([self.pack.pk], at(10), at(12))[self.pack.pk].free, free_before
        )

    def test_no_more_items_than_pieces(self) -> None:
        small = make_pack("K-702", items=25, pieces=2)
        line = add_line(self.project, small, 1).line
        with self.assertRaises(ValidationError) as caught:
            services.update_line(line, rights=ALL_RIGHTS, preferred_items=items_of(small, 1, 2, 3))
        self.assertIn("Jedes gewünschte Exemplar nimmt ein Stück", " ".join(caught.exception.messages))
        # Two packs of two pieces take four.
        services.update_line(line, rights=ALL_RIGHTS, quantity=D("2"), preferred_items=items_of(small, 1, 2, 3, 4))
        line.refresh_from_db()
        self.assertEqual(len(line.wished_items), 4)
        with self.assertRaises(ValidationError):
            services.update_line(line, rights=ALL_RIGHTS, quantity=D("1"))  # fewer pieces than wished items

    def test_an_item_of_another_product_is_refused(self) -> None:
        other = make_pack("K-703", items=3)
        with self.assertRaises(ValidationError):
            services.update_line(
                self.line, rights=ALL_RIGHTS, preferred_items=[*items_of(self.pack, 1), *items_of(other, 1)]
            )

    def test_taking_back_the_wish_takes_back_all_of_it(self) -> None:
        self.wish(1, 2, 3)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[])
        self.line.refresh_from_db()
        self.assertEqual((self.line.preferred_item_id, self.line.preferred_model_id), (None, None))
        self.assertEqual(self.line.further_preferred_items.count(), 0)

    def test_a_line_can_be_added_with_the_wish(self) -> None:
        added = services.add_line(
            self.project,
            rights=ALL_RIGHTS,
            product=self.pack,
            quantity=D("1"),
            preferred_items=items_of(self.pack, 4, 5),
        ).line
        added.refresh_from_db()
        self.assertEqual(added.wished_item_ids, [item.pk for item in items_of(self.pack, 4, 5)])

    def test_copies_keep_the_wish(self) -> None:
        from rentalars.projects.duplicate import duplicate_project

        self.wish(1, 2)
        copy = duplicate_project(
            self.project,
            name="Kopie",
            start=at(10, year=2028),
            end=at(11, year=2028),
            rights=ALL_RIGHTS,
            user=None,
        )
        copied = copy.material_lines.get()
        self.assertEqual(copied.wished_item_ids, self.line.wished_item_ids)
        group = add_group(self.project, "Kabel")
        services.update_line(self.line, rights=ALL_RIGHTS, group=group)
        new_group = services.copy_group(group, self.project, rights=ALL_RIGHTS)
        self.assertEqual(new_group.lines.get().wished_item_ids, self.line.wished_item_ids)

    def test_the_planning_names_the_share_and_warns_for_each_item(self) -> None:
        from rentalars.material.models import ItemStatus
        from rentalars.projects.planning import build_planning

        first, second = items_of(self.pack, 1, 2)
        self.wish(1, 2)
        second.status = ItemStatus.DEFECTIVE
        second.save()
        wish = build_planning(self.project).all_lines[0].wish
        self.assertEqual(wish.share, "2 von 10 Stück")
        self.assertIn(first.display_id, wish.label)
        self.assertIn(second.display_id, wish.label)
        self.assertEqual(len(wish.warnings), 1)
        self.assertIn(second.display_id, wish.warnings[0])

    def test_a_single_item_wish_of_a_plain_product_reads_as_before(self) -> None:
        from rentalars.projects.planning import build_planning

        plain = make_stock("K-710", 3, "Einzelstück")
        line = add_line(self.project, plain, 1).line
        item = items_of(plain, 2)[0]
        services.update_line(line, rights=ALL_RIGHTS, preferred_item=item)
        wish = next(planned.wish for planned in build_planning(self.project).all_lines if planned.line.pk == line.pk)
        self.assertEqual(wish.share, "")
        self.assertEqual(wish.label, f"Exemplar {item.display_id} ({item.material_model.display_short_name})")

    def test_another_project_wanting_a_further_item_is_a_rival(self) -> None:
        from rentalars.projects.planning import build_planning

        other = make_project("Konkurrenz", rental_days=1)
        rival = add_line(other, self.pack, 1).line
        services.update_line(rival, rights=ALL_RIGHTS, preferred_items=items_of(self.pack, 5, 6))
        self.wish(1, 6)
        wish = build_planning(self.project).all_lines[0].wish
        self.assertEqual(len(wish.warnings), 1)
        self.assertIn(other.number, wish.warnings[0])
        self.assertIn(items_of(self.pack, 6)[0].display_id, wish.warnings[0])

    def test_the_timeline_of_a_further_item_shows_the_wish(self) -> None:
        from rentalars.schedule.timelines import item_events
        from tests.helpers import at

        self.wish(1, 2)
        second = items_of(self.pack, 2)[0]
        events = item_events([second], at(1), at(30))[second.pk]
        self.assertEqual([event.kind for event in events if event.kind == "wish"], ["wish"])


class PieceShareInPackingTests(RentalarsTestCase):
    """(piece share) The packing list names exactly the wished items, and the issue notes them."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack()
        self.project = make_project("Packen", rental_days=1)
        self.line = add_line(self.project, self.pack, 1).line
        self.wished = items_of(self.pack, 7, 3)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=self.wished)
        self.packlist = packing.get_packlist(self.project)

    def row(self) -> object:
        return next(row for row in packing.build_overview(self.packlist).rows if row.product.pk == self.pack.pk)

    def test_the_row_names_the_wished_items_and_the_share(self) -> None:
        row = self.row()
        self.assertEqual(
            [wished.item_id for wished in row.wished],
            [item.pk for item in self.wished[:1]] + [items_of(self.pack, 3)[0].pk],
        )
        self.assertIn("2 von 10 Stück", row.wish)
        for item in self.wished:
            self.assertIn(item.display_id, row.wish)
        self.assertEqual(len(row.open_wished), 2)

    def test_the_pdf_shows_the_items_and_the_share(self) -> None:
        from rentalars.packing.pdf import render_packlist_html

        html = render_packlist_html(packing.build_overview(self.packlist))
        for item in self.wished:
            self.assertIn(item.display_id, html)
        self.assertIn("2 von 10 Stück", html)
        self.assertIn("Gewünscht:", html)

    def test_choosing_moves_them_from_wished_to_chosen(self) -> None:
        packing.choose_items(self.packlist, self.line.pk, self.pack.pk, [item.pk for item in self.wished])
        row = self.row()
        self.assertEqual(row.open_wished, [])
        self.assertTrue(all(wished.is_chosen for wished in row.wished))

    def test_the_issue_notes_exactly_the_wished_items(self) -> None:
        from rentalars.packing.models import Allocation

        packing.set_packed(self.packlist, self.line.pk, self.pack.pk, D(1))
        packing.issue(self.packlist, only_packed=True)
        noted = set(Allocation.objects.filter(entry__packlist=self.packlist).values_list("item_id", flat=True))
        self.assertEqual(noted, {item.pk for item in self.wished})

    def test_the_item_choice_names_and_orders_the_wished_ones_first(self) -> None:
        choices = packing.item_choices(self.packlist, self.row())
        first = [item.pk for item, _note, _free in choices[:2]]
        self.assertEqual(first, [item.pk for item in self.wished])
        self.assertIn("vom Planer gewünscht", choices[0][1])
        self.assertNotIn("gewünscht", choices[2][1])

    def test_the_price_sum_is_the_same_with_and_without_the_wish(self) -> None:
        with_wish = compute_project_prices(self.project).net_total
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[])
        self.assertEqual(compute_project_prices(self.project).net_total, with_wish)

    def test_a_row_without_wish_has_nothing_to_look_for(self) -> None:
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=[])
        self.assertEqual((self.row().wished, self.row().wish), ([], ""))


class PieceSharePagesTests(UiTestCase):
    """(piece share) The dialog of a line takes more than one wished item."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack()
        self.project = make_project("Dialog", rental_days=1)
        self.line = add_line(self.project, self.pack, 1).line
        self.url = reverse("projects:line_edit", args=[self.project.pk, self.line.pk])

    def test_the_dialog_offers_further_items_for_a_line_of_several_pieces(self) -> None:
        dialog = self.assert_ok(self.htmx("get", self.url))
        self.assertIn("Weitere bestimmte Exemplare (ID)", dialog)
        self.assertIn("eines der 10 Stücke", dialog)
        plain = add_line(self.project, make_stock("K-720", 3), 1).line
        self.assertNotIn(
            "Weitere bestimmte Exemplare",
            self.assert_ok(self.htmx("get", reverse("projects:line_edit", args=[self.project.pk, plain.pk]))),
        )

    def test_several_items_are_saved_and_shown_with_their_share(self) -> None:
        first, second, third = items_of(self.pack, 1, 2, 3)
        data = form_data(
            self.htmx("get", self.url),
            preferred_item_number=first.display_id,
            further_item_numbers=f"{second.display_id}, {third.display_id}",
        )
        self.assertEqual(self.htmx("post", self.url, data).status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual(self.line.wished_item_ids, [first.pk, second.pk, third.pk])
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("3 von 10 Stück", page)
        again = self.assert_ok(self.htmx("get", self.url))
        self.assertIn(f"{second.display_id}, {third.display_id}", again)

    def test_an_unknown_id_and_too_many_items_are_said_on_the_dialog(self) -> None:
        data = form_data(self.htmx("get", self.url), further_item_numbers="9999999")
        self.assertIn("Es gibt kein Exemplar mit der ID 9999999", self.htmx("post", self.url, data).content.decode())
        small = make_pack("K-721", items=5, pieces=2)
        line = add_line(self.project, small, 1).line
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        numbers = [item.display_id for item in items_of(small, 1, 2, 3)]
        data = form_data(
            self.htmx("get", url), preferred_item_number=numbers[0], further_item_numbers=", ".join(numbers[1:])
        )
        self.assertIn("Jedes gewünschte Exemplar nimmt ein Stück", self.htmx("post", url, data).content.decode())

    def test_the_packlist_page_shows_exactly_the_wished_items_with_their_spot(self) -> None:
        wished = items_of(self.pack, 7, 3)
        services.update_line(self.line, rights=ALL_RIGHTS, preferred_items=wished)
        page = self.assert_ok(self.client.get(reverse("packing:packlist", args=[self.project.pk])))
        row = page[page.index('class="meta wished"') :]
        row = row[: row.index("</div>")]
        self.assertIn("Gewünscht:", row)
        for item in wished:
            self.assertIn(item.display_id, row)
        self.assertIn("Wunsch: Exemplare", page)
        self.assertIn("2 von 10 Stück", page)

    def test_the_search_for_an_item_still_adds_a_line_with_that_wish(self) -> None:
        """PRJ-065: picking an item in the search of the planning adds the product with the item as wish."""
        item = items_of(self.pack, 4)[0]
        url = reverse("projects:line_add", args=[self.project.pk])
        self.htmx("post", url, {"product": f"{self.pack.pk}:i{item.pk}", "quantity": "1"})
        added = self.project.material_lines.order_by("-pk").first()
        self.assertEqual(added.wished_item_ids, [item.pk])


class PieceShareApiTests(ApiTestCase):
    """(piece share) The same through the API: ``preferred_items`` on the line and in the packlist."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack()
        self.project = make_project("Schnittstelle", rental_days=1)
        self.line = add_line(self.project, self.pack, 1).line
        self.url = f"{API}/projects/{self.project.pk}/material-lines"

    def test_the_wished_items_are_written_and_read(self) -> None:
        ids = [item.pk for item in items_of(self.pack, 5, 2, 9)]
        answer = self.admin.patch(f"{self.url}/{self.line.pk}", {"preferred_items": ids}, format="json")
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(answer.json()["preferred_items"], [ids[0], *sorted(ids[1:])])
        self.assertEqual(answer.json()["preferred_item"], ids[0])
        listed = self.admin.get(self.url).json()
        self.assertEqual(listed[0]["preferred_items"], answer.json()["preferred_items"])
        self.assertEqual(listed[0]["price"]["amount"], "50.00")  # the wish leaves the price alone

    def test_a_line_is_created_with_the_wish(self) -> None:
        ids = [item.pk for item in items_of(self.pack, 1, 2)]
        answer = self.admin.post(
            self.url, {"product": self.pack.pk, "quantity": "1", "preferred_items": ids}, format="json"
        )
        self.assertEqual(answer.status_code, 201, answer.content)
        self.assertEqual(answer.json()["preferred_items"], ids)

    def test_too_many_items_and_foreign_items_are_refused(self) -> None:
        small = make_pack("K-722", items=5, pieces=2)
        line = add_line(self.project, small, 1).line
        too_many = [item.pk for item in items_of(small, 1, 2, 3)]
        self.assert_error(
            self.admin.patch(f"{self.url}/{line.pk}", {"preferred_items": too_many}, format="json"),
            400,
            "validation_error",
        )
        foreign = [items_of(small, 1)[0].pk]
        self.assert_error(
            self.admin.patch(f"{self.url}/{self.line.pk}", {"preferred_items": foreign}, format="json"),
            400,
            "validation_error",
        )

    def test_emptying_the_list_takes_back_the_wish(self) -> None:
        ids = [item.pk for item in items_of(self.pack, 1, 2)]
        self.admin.patch(f"{self.url}/{self.line.pk}", {"preferred_items": ids}, format="json")
        answer = self.admin.patch(f"{self.url}/{self.line.pk}", {"preferred_items": []}, format="json")
        self.assertEqual((answer.json()["preferred_items"], answer.json()["preferred_item"]), ([], None))

    def test_the_packlist_names_every_wished_item(self) -> None:
        ids = [item.pk for item in items_of(self.pack, 5, 2)]
        self.admin.patch(f"{self.url}/{self.line.pk}", {"preferred_items": ids}, format="json")
        listing = self.admin.get(f"{API}/projects/{self.project.pk}/packlists").json()
        document = self.admin.get(f"{API}/projects/{self.project.pk}/packlists/{listing[0]['id']}").json()
        row = document["sections"][0]["rows"][0]
        self.assertEqual(row["preferred_items"], [ids[0], items_of(self.pack, 2)[0].pk])
        self.assertIn("2 von 10 Stück", row["wish"])
