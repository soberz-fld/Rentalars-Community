# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for customer material: the product form, list and page with the owner (PRD-043), the customer's
page, models, items and labels – and the material in the owner's projects: planning, price overview, packlist,
offer and delivery note (PRJ-096)."""

from __future__ import annotations

import datetime
import re
from decimal import Decimal

from django.urls import reverse

from rentalars.documents import services as documents
from rentalars.documents.content import build_delivery_note, build_priced
from rentalars.documents.models import DocumentKind
from rentalars.documents.pdf import render_html
from rentalars.masterdata.models import Category, TaxRate, Unit
from rentalars.material.labels import render_labels_html
from rentalars.packing import services as packing
from rentalars.packing.pdf import render_packlist_html
from rentalars.products.models import BillingMode, Product
from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_html
from tests.helpers import (
    ALL_RIGHTS,
    add_group,
    add_line,
    make_customer,
    make_items,
    make_model,
    make_product,
    make_project,
)
from tests.ui.base import UiTestCase

D = Decimal


def customer_material_category() -> Category:
    return Category.objects.get(parent__isnull=True, code="C")


class ProductPageTests(UiTestCase):
    """PRD-043: the owner in the product form, list and page."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")

    def test_add_material_from_the_customers_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.band.pk])))
        self.assertIn("Material des Kunden im Lager", page)
        link = f"{reverse('products:create')}?owner={self.band.pk}"
        self.assertIn(link, page)
        form = self.assert_ok(self.client.get(link))
        # The category for customer material is chosen, the owner set, the next article number suggested.
        self.assertRegex(form, rf'<option value="{customer_material_category().pk}" selected>')
        self.assertIn('value="C-001"', form)
        self.assertIn(f'name="owner" id="id_owner" value="{self.band.pk}"', form)
        self.assertIn('value="Die Band"', form)
        # The owner is asked for in C, the prices in every other category.
        self.assertIn(f'data-show-if="category={customer_material_category().pk}"', form)
        self.assertRegex(form, r'class="panel hidden" data-show-if="category=\|')
        response = self.client.post(
            link,
            {
                "category": customer_material_category().pk,
                "article_number": "C-001",
                "name": "Mischpult der Band",
                "owner": self.band.pk,
                "kind": "rental",
                "unit": Unit.objects.get(name="Stück (Miete)").pk,
                "tax_rate": TaxRate.get_default().pk,
                "billing_mode": "daily_piece",
                "rental_scale_mode": "inherit",
                "surcharge_type": "fixed",
                # Typed before the category was switched to C – hidden, and not taken over.
                "price": "25.00",
                "is_active": "on",
            },
        )
        product = Product.objects.get(article_number="C-001")
        self.assertRedirects(response, reverse("products:detail", args=[product.pk]))
        self.assertEqual((product.owner, product.price, product.billing_mode), (self.band, None, BillingMode.FLAT))

    def test_an_owner_outside_c_is_not_taken_over(self) -> None:
        sound = Category.objects.get(parent__isnull=True, code="T")
        self.client.post(
            reverse("products:create"),
            {
                "category": sound.pk,
                "article_number": "T-001",
                "name": "Pult",
                "owner": self.band.pk,
                "kind": "rental",
                "unit": Unit.objects.get(name="Stück (Miete)").pk,
                "tax_rate": TaxRate.get_default().pk,
                "billing_mode": "daily_piece",
                "rental_scale_mode": "inherit",
                "surcharge_type": "fixed",
                "price": "25.00",
                "is_active": "on",
            },
        )
        self.assertIsNone(Product.objects.get(article_number="T-001").owner)

    def test_c_without_owner_names_the_field(self) -> None:
        response = self.client.post(
            reverse("products:create"),
            {
                "category": customer_material_category().pk,
                "article_number": "C-001",
                "name": "Pult",
                "kind": "rental",
                "unit": Unit.objects.get(name="Stück (Miete)").pk,
                "tax_rate": TaxRate.get_default().pk,
                "billing_mode": "flat",
                "rental_scale_mode": "inherit",
                "surcharge_type": "fixed",
            },
        )
        page = self.assert_ok(response)
        self.assertIn("Kundenmaterial gehört einem Kunden: Wähle den Eigentümer.", page)

    def test_list_filter_column_and_page(self) -> None:
        desk = make_product("C-001", "Mischpult der Band", price=None, owner=self.band)
        make_product("T-001", "Eigenes Pult")
        url = reverse("products:list")
        page = self.assert_ok(self.client.get(url, {"owner": self.band.pk}))
        self.assertIn("Mischpult der Band", page)
        self.assertNotIn("Eigenes Pult", page)
        self.assertIn(">Kundenmaterial</span>", page)
        own = self.assert_ok(self.client.get(url, {"owner": "own"}))
        self.assertNotIn("Mischpult der Band", own)
        self.assertIn("Eigenes Pult", own)
        csv = self.client.get(url, {"format": "csv", "cols": "number,name,owner"}).content.decode("utf-8-sig")
        self.assertIn("Eigentümer", csv.splitlines()[0])
        self.assertIn("C-001;Mischpult der Band;Die Band", csv.replace('"', ""))
        detail = self.assert_ok(self.client.get(reverse("products:detail", args=[desk.pk])))
        self.assertIn("Eigentum von Die Band", detail)
        self.assertIn("Kundenmaterial, wird nie berechnet.", detail)


class SuggestionTests(UiTestCase):
    """PRD-043: the components of a kit of customer material and the addendum while packing find the material."""

    def test_kit_components_and_packing(self) -> None:
        band = make_customer("Die Band")
        desk = make_product("C-001", "Mischpult der Band", price=None, owner=band)
        kit = make_product("C-002", "Set der Band", price=None, owner=band, kind="kit")
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[kit.pk])))
        # PRD-044: no service and no vehicle either – vehicles are planned under "Logistik" (LOG-001).
        self.assertIn(f"exclude_kind=surcharge,subrental,service,vehicle&amp;owner={band.pk}", page)
        found = self.client.get(reverse("products:suggest"), {"q": "Mischpult", "owner": band.pk}).json()
        self.assertEqual([row["id"] for row in found], [desk.pk])
        project = make_project("Gig", customer=band)
        packlist = self.assert_ok(self.client.get(reverse("packing:packlist", args=[project.pk])))
        self.assertIn(f"&amp;project={project.pk}", packlist)


class MaterialPageTests(UiTestCase):
    """PRD-043: models, items and labels of customer material name the owner."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")
        self.desk = make_product("C-001", "Mischpult der Band", price=None, owner=self.band)
        self.model = make_model("Yamaha CL5", self.desk)
        self.item = make_items(self.model, 1)[0]

    def test_model_item_and_label(self) -> None:
        model_page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assertIn("Eigentum von Die Band", model_page)
        item_page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.item.pk])))
        self.assertIn("Eigentum von Die Band", item_page)
        html = render_labels_html([self.item])
        self.assertIn('<div class="owner">Eigentum von Die Band</div>', html)

    def test_the_customers_page_lists_it(self) -> None:
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.band.pk])))
        section = page[page.index('id="customer-material"') :]
        self.assertIn("C-001", section[:2000])
        self.assertIn("1 Stk.", section[:2000])
        # A customer whose material is here cannot be deleted from the page.
        self.assertNotIn(reverse("customers:delete", args=[self.band.pk]), page)


class ProjectPageTests(UiTestCase):
    """PRJ-096: the planning, the price overview, the packlist and the documents of a gig of the band."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")
        self.desk = make_product("C-001", "Mischpult der Band", price=None, owner=self.band)
        model = make_model("Yamaha CL5", self.desk)
        model.weight_kg = D("36.5")
        model.save()
        make_items(model, 1)
        self.project = make_project("Gig Stadthalle", customer=self.band)
        self.group = add_group(self.project, "FOH")
        self.light = make_product("L-001", "Scheinwerfer", price="50.00", billing_mode=BillingMode.FLAT)
        add_line(self.project, self.light, 2, group=self.group)
        self.line = add_line(self.project, self.desk, group=self.group).line

    def row_of(self, page: str, line_id: int) -> str:
        return re.search(rf'<tr data-line="{line_id}".*?</tr>', page, flags=re.S).group(0)

    def test_the_planning_shows_the_badge_without_price(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        row = self.row_of(page, self.line.pk)
        self.assertIn("Kundenmaterial – wird mitgeführt", row)
        self.assertIn("nicht berechnet", row)
        self.assertNotIn("0,00", row)
        # Never optional, never an alternative: the two buttons are missing.
        self.assertNotIn('"action": "optional"', row)
        self.assertIn(f"project={self.project.pk}", page)
        self.assertIn("100,00", page)

    def test_a_shortage_offers_no_subrental(self) -> None:
        add_line(self.project, self.desk)
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Kundenmaterial lässt sich nicht zumieten.", page)
        self.assertNotIn("C-001</button>", page)
        self.assertNotIn("Zumieten: 1 × C-001", page)
        shortages = self.assert_ok(self.client.get(reverse("availability:shortages")))
        self.assertIn("Kundenmaterial lässt sich nicht zumieten.", shortages)

    def test_adding_it_to_another_customers_project_is_refused(self) -> None:
        other = make_project("Stadtfest", customer=make_customer("Stadtwerke"))
        response = self.htmx("post", reverse("projects:line_add", args=[other.pk]), {"product": self.desk.pk})
        self.assertIn("nur in Projekten dieses Kunden", response.content.decode())
        self.assertFalse(other.material_lines.exists())

    def test_price_overview_page_pdf_and_csv(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk]), {"lines": 1}))
        self.assertIn("Kundenmaterial – wird mitgeführt", page)
        html = render_price_overview_html(self.project, with_lines=True, rights=ALL_RIGHTS, user=self.admin_user)
        self.assertIn("Kundenmaterial – wird mitgeführt, nicht berechnet", html)
        csv = render_price_overview_csv(self.project, rights=ALL_RIGHTS, user=self.admin_user)
        text = csv if isinstance(csv, str) else csv.decode("utf-8-sig")
        row = next(line for line in text.splitlines() if "Mischpult" in line)
        self.assertIn("Kundenmaterial – wird mitgeführt", row)
        self.assertTrue(row.rstrip().endswith(";"), row)

    def test_packlist_screen_and_pdf(self) -> None:
        page = self.assert_ok(self.client.get(reverse("packing:packlist", args=[self.project.pk])))
        self.assertIn("Kundenmaterial – wird mitgeführt", page)
        overview = packing.build_overview(packing.get_packlist(self.project))
        pdf = render_packlist_html(overview)
        self.assertIn("Kundenmaterial – wird mitgeführt", pdf)
        self.assertIn("36,5", pdf)

    def test_offer_and_delivery_note(self) -> None:
        offer = build_priced(self.project, "offer", title="Angebot", number="AN-1", issued_on=datetime.date(2027, 3, 1))
        html = render_html(offer, documents.template_for(DocumentKind.OFFER))
        row = re.search(r"<tr>\s*<td class=\"pos\">2</td>.*?</tr>", html, flags=re.S).group(0)
        self.assertIn("Kundeneigenes Material – wird mitgeführt, ohne Berechnung", row)
        self.assertNotIn("0,00", row)
        note = build_delivery_note(
            self.project, title="Lieferschein", number="LS-1", issued_on=datetime.date(2027, 3, 1)
        )
        html = render_html(note, documents.template_for(DocumentKind.DELIVERY_NOTE))
        self.assertIn("Kundeneigenes Material – wird mitgeführt", html)
