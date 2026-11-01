# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: the product form asks for the owner instead of prices in the category for customer material
(PRD-043), the owner is chosen by typing; and the pages with customer material checked with axe-core (PRJ-096)."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.masterdata.models import Category
from rentalars.products.models import Product
from rentalars.projects import services
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import ALL_RIGHTS, make_customer, make_items, make_model, make_product


def customer_material_category() -> Category:
    return Category.objects.get(parent__isnull=True, code="C")


class ProductFormInBrowserTests(BrowserTestCase):
    """PRD-043: the category decides whether the form asks for the owner or for prices."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")

    def test_choose_c_and_the_owner(self) -> None:
        self.open("/products/new/")
        owner = self.page.locator("#id_owner_text")
        price = self.page.locator("#id_price")
        self.assertFalse(owner.is_visible())
        # Choosing the category reloads the form with its presets – and the kind chosen before it (PRD-046).
        self.page.select_option("#id_category", str(customer_material_category().pk))
        self.page.wait_for_url("**/products/new/?kind=rental&category=*")
        self.assertEqual(self.page.input_value("#id_article_number"), "C-001")
        self.assertTrue(owner.is_visible())
        self.assertFalse(price.is_visible())
        self.assertTrue(self.page.locator("text=Dieses Material gehört dem oben genannten Kunden").is_visible())
        self.page.fill("#id_name", "Mischpult der Band")
        container = self.page.locator(".typeahead", has=owner)
        owner.click()
        owner.press_sequentially("Die B", delay=20)
        container.locator("[role=option]", has_text="Die Band").first.wait_for()
        owner.press("Enter")
        self.page.click("button[type=submit]:has-text('Produkt speichern')")
        self.page.wait_for_url("**/products/*/")
        product = Product.objects.get(article_number="C-001")
        self.assertEqual((product.owner, product.price), (self.band, None))
        self.assertIn("Eigentum von Die Band", self.text_of(".page-head"))

    def test_switching_the_category_while_editing(self) -> None:
        product = make_product("T-900", "Pult")
        self.open(f"/products/{product.pk}/edit/")
        self.assertTrue(self.page.locator("#id_price").is_visible())
        self.page.select_option("#id_category", str(customer_material_category().pk))
        self.assertTrue(self.page.locator("#id_owner_text").is_visible())
        self.assertFalse(self.page.locator("#id_price").is_visible())
        self.page.select_option("#id_category", str(Category.objects.get(parent__isnull=True, code="T").pk))
        self.assertFalse(self.page.locator("#id_owner_text").is_visible())
        self.assertTrue(self.page.locator("#id_price").is_visible())


class CustomerMaterialAccessibilityTests(BrowserTestCase):
    """NFA-025: the pages with customer material without a finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def findings(self, path: str) -> list[str]:
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        self.page.add_script_tag(path=str(self.axe))
        result = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        return [f"{path}: {finding}" for finding in result]

    def test_pages_with_customer_material(self) -> None:
        customer = self.project.customer
        desk = make_product("C-001", "Mischpult der Band", price=None, owner=customer)
        model = make_model("Yamaha CL5", desk)
        item = make_items(model, 1)[0]
        services.add_line(self.project, rights=ALL_RIGHTS, product=desk, quantity=1)
        services.add_line(self.project, rights=ALL_RIGHTS, product=desk, quantity=1)  # short: no subrental offered
        findings: list[str] = []
        for path in (
            f"/projects/{self.project.pk}/",
            f"/projects/{self.project.pk}/prices/",
            f"/projects/{self.project.pk}/packlist/",
            f"/customers/{customer.pk}/",
            f"/products/{desk.pk}/",
            f"/products/new/?owner={customer.pk}",
            f"/material/models/{model.pk}/",
            f"/material/items/{item.pk}/",
            "/shortages/",
        ):
            findings += self.findings(path)
        self.assertEqual(findings, [], "\n".join(findings))
        self.open_planning()
        self.assertIn("Kundenmaterial – wird mitgeführt", self.text_of("#planning"))
