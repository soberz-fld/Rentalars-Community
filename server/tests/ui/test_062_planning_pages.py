# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning wishes in the pages (VFG-024, VFG-025, PRD-041) and the phases at their real times."""

from __future__ import annotations

import re
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.accounts.models import Role
from rentalars.projects.models import ProjectPhase
from tests.helpers import add_line, at, make_person, make_product, make_project, make_stock, plan
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_accessibility import problems_of


def _bar_styles(page: str, css: str) -> list[str]:
    """The inline styles of the bars with this CSS class on a timeline page."""
    return re.findall(rf'<a class="tl-bar {css}" style="([^"]*)"', page)


class PhaseLengthTests(UiTestCase):
    """Bug: phases were drawn longer than they last – a bar filled every column it touched."""

    def test_a_phase_of_some_hours_fills_only_its_hours_of_the_day(self) -> None:
        project = make_project("Stadtfest", start=at(10, 8), end=at(12, 22))
        ProjectPhase.objects.create(project=project, kind="setup", start=at(10, 14), end=at(10, 20))
        page = self.assert_ok(self.client.get("/schedule/timeline/", {"from": "2027-03-08", "weeks": "1"}))
        # Wednesday is the third day column; 14:00 to 20:00 leaves 14 hours before and 4 after.
        self.assertEqual(
            _bar_styles(page, "phase"),
            ["grid-column: 3 / 4; margin-left: calc(58.333% + 1px); margin-right: calc(16.667% + 1px); --fill: 0.250"],
        )

    def test_a_phase_over_midnight_does_not_fill_two_days(self) -> None:
        project = make_project("Stadtfest", start=at(10, 8), end=at(12, 22))
        ProjectPhase.objects.create(project=project, kind="dismantling", start=at(11, 22), end=at(12, 2))
        page = self.assert_ok(self.client.get("/schedule/timeline/", {"from": "2027-03-08", "weeks": "1"}))
        self.assertEqual(
            _bar_styles(page, "phase"),
            ["grid-column: 4 / 6; margin-left: calc(45.833% + 1px); margin-right: calc(45.833% + 1px); --fill: 0.083"],
        )

    def test_in_hour_columns_a_short_phase_is_not_stretched_to_whole_columns(self) -> None:
        project = make_project("Vortrag", start=at(10, 7), end=at(10, 12))
        ProjectPhase.objects.create(project=project, kind="setup", start=at(10, 7, 30), end=at(10, 8, 15))
        page = self.assert_ok(self.client.get("/schedule/timeline/", {"days": "3", "from": "2027-03-10"}))
        # Two-hour columns from 4 March (VFG-033): 07:30 lies in the column 06–08 of
        # the 10th, 08:15 in 08–10.
        self.assertEqual(
            _bar_styles(page, "phase"),
            [
                "grid-column: 76 / 78; margin-left: calc(37.500% + 1px); margin-right: calc(43.750% + 1px); --fill: 0.188"
            ],
        )


class DaysControlTests(UiTestCase):
    """VFG-024: "Days" with a number from 1 to 10, or "Weeks" as before – timeline and personnel plan."""

    def test_seven_days_in_six_hour_columns(self) -> None:
        make_project("Messe", start=at(10, 8), end=at(13, 18))
        page = self.assert_ok(self.client.get("/schedule/timeline/", {"days": "7", "from": "2027-03-10"}))
        self.assertIn('data-tl-zoom data-focus="56" data-shift="28" data-columns="140"', page)  # VFG-033: 5 spans
        self.assertIn('href="?days=7&amp;from=2027-03-10" aria-current="true">Tage</a>', page)
        self.assertIn('<label for="f-days">Tage</label><select id="f-days" name="days" data-autosubmit>', page)
        self.assertIn('<option value="7" selected>7</option>', page)
        self.assertNotIn('name="weeks" data-autosubmit', page)
        self.assertIn('title="Mi 10.03., 06:00–12:00">06</div>', page)
        self.assertIn("Mi 10.03.2027 – Di 16.03.2027", page)
        self.assertIn('data-later-url="?days=7&amp;from=2027-03-17"', page)
        # From 08:00, two hours into the column 06–12, to 18:00 three days later, the end of a column.
        self.assertIn('style="grid-column: 58 / 72; margin-left: calc(2.381% + 1px); --fill: 0.976', page)

    def test_weeks_offer_the_days_chosen_last(self) -> None:
        weeks = self.assert_ok(self.client.get("/schedule/timeline/", {"from": "2027-03-08", "weeks": "2"}))
        # VFG-028: four days unless another number was chosen (three).
        self.assertIn('href="?from=2027-03-08&amp;weeks=2&amp;days=4">Tage</a>', weeks)
        self.assertIn('<option value="2" selected>2</option>', weeks)
        self.assertNotIn('name="days"', weeks)
        self.assert_ok(self.client.get("/schedule/personnel/", {"days": "5", "from": "2027-03-10"}))
        again = self.assert_ok(self.client.get("/schedule/timeline/", {"from": "2027-03-08", "weeks": "2"}))
        self.assertIn('href="?from=2027-03-08&amp;weeks=2&amp;days=5">Tage</a>', again)

    def test_personnel_plan_of_ten_days(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest"), "Tontechnik", anna, start=at(10, 8), end=at(10, 18))
        page = self.assert_ok(self.client.get("/schedule/personnel/", {"days": "10", "from": "2027-03-10"}))
        self.assertIn('data-tl-zoom data-focus="80" data-shift="40" data-columns="200"', page)  # VFG-033
        self.assertIn('<input type="hidden" name="days" value="10">', page)
        self.assertIn('style="grid-column: 82 / 84; margin-left: calc(16.667% + 1px); --fill: 0.833"', page)


class UtilizationSuggestionTests(UiTestCase):
    """VFG-025: the search of the utilization suggests products; choosing one shows that product."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-020", 4, "Moving Head Spot")
        self.wash = make_stock("L-021", 2, "Moving Head Wash")
        add_line(make_project("Stadtfest"), self.spot, 3)

    def test_the_field_is_a_combobox_of_stock_products(self) -> None:
        page = self.assert_ok(self.client.get("/schedule/products/", {"from": "2027-03-08"}))
        self.assertIn(
            # PRD-045: incidental costs have no stock either – nor vehicles (LOG-002: their
            # utilization is that of the fleet). VFG-037: kits are suggested.
            '<div class="typeahead" data-typeahead data-url="/products/suggest/?exclude_kind=incidental,service,'
            'subrental,surcharge,vehicle">',
            page,
        )
        self.assertIn('<input type="search" id="f-q" name="q" value="" data-typeahead-input autocomplete="off">', page)
        self.assertIn('<input type="hidden" name="product" value="" data-typeahead-value data-autosubmit>', page)
        # The category is a form of its own, so that it never stands against a chosen product.
        self.assertIn('<select id="f-category" name="category" form="f-by-category" data-autosubmit>', page)
        self.assertEqual(problems_of(page), [])

    def test_suggestions_while_typing(self) -> None:
        make_product("N-010", "Moving-Head-Programmierung", kind="incidental", billing_mode="hourly")
        answer = self.client.get(
            "/products/suggest/", {"exclude_kind": "incidental,kit,service,subrental,surcharge", "q": "moving"}
        )
        self.assertEqual([row["label"] for row in answer.json()], ["L-020 Moving Head Spot", "L-021 Moving Head Wash"])

    def test_a_chosen_product_is_shown_alone(self) -> None:
        page = self.assert_ok(
            self.client.get(
                "/schedule/products/",
                {"q": "L-020 Moving Head Spot", "product": str(self.spot.pk), "from": "2027-03-08", "weeks": "1"},
            )
        )
        self.assertIn("Moving Head Spot", page)
        self.assertNotIn("Moving Head Wash", page)
        self.assertIn(f'name="product" value="{self.spot.pk}"', page)
        self.assertIn('value="L-020 Moving Head Spot" data-typeahead-input', page)
        # Moving on keeps the product.
        self.assertIn(f"product={self.spot.pk}", page[page.index("früher") - 200 : page.index("früher")])

    def test_typed_text_without_choosing_still_searches(self) -> None:
        page = self.assert_ok(self.client.get("/schedule/products/", {"q": "Moving", "from": "2027-03-08"}))
        self.assertIn("Moving Head Spot", page)
        self.assertIn("Moving Head Wash", page)


class ProductMaximumDiscountPageTests(UiTestCase):
    """PRD-041: form, page, list column and the hint in the planning."""

    def test_form_page_and_list(self) -> None:
        product = make_product("L-050", "Nebelmaschine", price="100.00")
        url = "/products/L-050/edit/"
        page = self.client.get(url)
        self.assertContains(page, "Höchster Rabatt in Prozent")
        self.assertRedirects(self.client.post(url, form_data(page, max_discount_percent="5")), "/products/L-050/")
        product.refresh_from_db()
        self.assertEqual(product.max_discount_percent, Decimal("5.00"))
        detail = self.assert_ok(self.client.get("/products/L-050/"))
        self.assertIn("<dt>Höchstrabatt</dt><dd>5 %</dd>", detail)
        listed = self.assert_ok(self.client.get("/products/", {"cols": "number,name,max_discount"}))
        self.assertIn("Höchstrabatt", listed)
        self.assertIn("5 %", listed)
        csv = self.client.get("/products/", {"format": "csv", "cols": "number,max_discount"}).content.decode()
        self.assertIn("Art.-Nr.;Höchstrabatt", csv)
        self.assertIn("L-050;5", csv)
        product.max_discount_percent = Decimal("0")
        product.save()
        self.assertIn("<dd>nicht rabattierbar</dd>", self.assert_ok(self.client.get("/products/L-050/")))

    def test_hidden_without_the_price_right(self) -> None:
        product = make_product("L-050", "Nebelmaschine", price="100.00", max_discount_percent=Decimal("5"))
        Role.objects.create(name="Lager ohne Preise", module_levels={"products": 3})
        warehouse = self.browser_for("lena", "Lager ohne Preise")
        page = warehouse.get("/products/L-050/edit/")
        self.assertNotContains(page, "Höchster Rabatt")
        self.assertNotContains(warehouse.get("/products/L-050/"), "Höchstrabatt")
        warehouse.post("/products/L-050/edit/", form_data(page, max_discount_percent="50"))
        product.refresh_from_db()
        self.assertEqual(product.max_discount_percent, Decimal("5.00"))

    def test_the_planning_names_the_product_as_the_limit(self) -> None:
        project = make_project()
        hazer = make_product("L-050", "Nebelmaschine", price="100.00", max_discount_percent=Decimal("5"))
        add_line(project, hazer, 1, discount_percent=Decimal("10"))
        page = self.assert_ok(self.client.get(f"/projects/{project.number}/"))
        self.assertIn("höchstens 5 % (Produkt)", page)
        self.assertNotIn("(Funktion)", page)


class AccessibilityAndQueryTests(UiTestCase):
    """NFA-025 and NFA-012 for the new spans and the utilization with a chosen product."""

    def fill(self, count: int) -> None:
        for number in range(count):
            project = make_project(f"Projekt {number}", start=at(2 + number % 6, 8), end=at(4 + number % 6, 18))
            ProjectPhase.objects.create(project=project, start=at(2 + number % 6, 14), end=at(2 + number % 6, 20))
            person = make_person(f"Person{number} Test", rates={"Stagehand": "20.00"})
            plan(project, "Stagehand", person, start=at(2 + number % 6, 8), end=at(2 + number % 6, 18))
            add_line(project, self.spot, 1)

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-020", 40, "Moving Head Spot")

    def paths(self) -> tuple[str, ...]:
        return (
            "/schedule/timeline/?days=7&from=2027-03-02",
            "/schedule/timeline/?days=10&from=2027-03-02",
            "/schedule/personnel/?days=5&from=2027-03-02",
            "/schedule/personnel/?days=10&from=2027-03-02",
            f"/schedule/products/?product={self.spot.pk}&q=L-020&from=2027-03-01",
        )

    def test_no_findings(self) -> None:
        self.fill(4)
        found = []
        for path in self.paths():
            found += [f"{path}: {problem}" for problem in problems_of(self.assert_ok(self.client.get(path)))]
        self.assertEqual(found, [], "\n".join(found))

    def test_queries_do_not_grow(self) -> None:
        def counts() -> list[int]:
            result = []
            for path in self.paths():
                with CaptureQueriesContext(connection) as queries:
                    self.assert_ok(self.client.get(path))
                result.append(len(queries))
            return result

        self.fill(2)
        few = counts()
        self.fill(10)
        self.assertEqual(counts(), few)
