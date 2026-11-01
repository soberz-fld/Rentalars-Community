# SPDX-License-Identifier: GPL-3.0-or-later
"""Products – one price (PRD-047), duplicating (PRD-048), article numbers (PRD-049), availability (PRD-050)
and the material utilization (VFG-037, PRD-051).

1. The requirement: a rental product has only one price; the duplication by "Preis" and "Verkaufspreis" is removed.
   A product that is sold is created as a sales product.
2. The requirement: products have a "Duplizieren" button that creates a new object from an existing one.
3. The requirement: when a new product is created from a model, the article number adapts when a category is chosen –
   as when a product is created normally.
4. The requirement: choosing a period in the calendar of the product adapts the availability display; the button
   "Zeitraum prüfen" is no longer needed and is removed.
5. The requirement: Planung → Materialauslastung also lets products of the category "Sets" be chosen, expandable
   for the single parts of the set.
6. The requirement: the availability display of a product links to Planung → Materialauslastung, where the product
   is then selected.
"""

from __future__ import annotations

import importlib
import io
from decimal import Decimal as D  # noqa: N817

from django.apps import apps
from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.models import AuditLogEntry
from rentalars.core.tabular import read_table
from rentalars.masterdata.models import Category, ProductKindDefault, Unit
from rentalars.products.importer import import_products
from rentalars.products.models import KitComponent, Product, ProductKind
from rentalars.products.services import set_kit_components
from rentalars.projects import project_templates
from rentalars.projects.forms import LineForm
from rentalars.projects.lines import duplicate_line
from rentalars.projects.services import update_line
from rentalars.schedule.services import kit_loads, utilization_address
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    category,
    make_model,
    make_product,
    make_project,
    make_stock,
)
from tests.ui.base import UiTestCase, form_data

MIGRATION = importlib.import_module("rentalars.products.migrations.0009_one_price_091")


def sale_product(article_number: str = "V-001", sale_price: str = "14.90") -> Product:
    """A sale product, which has its sale price only."""
    return make_product(article_number, "Gaffa", kind="sale", billing_mode="flat", price=None, sale_price=D(sale_price))


def legacy_sale_price(product: Product, sale_price: str) -> Product:
    """Give a rental product a sale price – past the rules."""
    Product.objects.filter(pk=product.pk).update(sale_price=D(sale_price))
    product.refresh_from_db()
    return product


def sets_category() -> Category:
    """A main category "Sets" for kits, as the customer has it."""
    return Category.objects.create(
        name="Sets", code="ST", has_own_stock=False, default_product_kind=ProductKindDefault.KIT
    )


def make_kit(speakers: Product, stand: Product) -> Product:
    """A kit of two speakers and one stand in the category "Sets"."""
    kit = make_product("ST-001", "Aktivbox-Set", category=sets_category(), kind="kit", billing_mode="daily_kit")
    set_kit_components(kit, [(speakers, 2), (stand, 1)])
    return kit


# --- 1. One price per product -------------------------------------------------------------------


class OnePriceRuleTests(RentalarsTestCase):
    """A rental product has its price, a sale product its sale price – never both (PRD-047)."""

    def test_a_rental_product_or_kit_has_no_sale_price(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            make_product("K-005", price="1.50", sale_price=D("12.00"))
        self.assertIn("sale_price", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            make_product("T-100", kind="kit", billing_mode="daily_kit", sale_price=D("50.00"))
        self.assertIn("sale_price", caught.exception.message_dict)

    def test_a_sale_product_has_its_sale_price_only(self) -> None:
        tape = sale_product()
        self.assertEqual((tape.price, tape.sale_price), (None, D("14.90")))
        tape.price = D("2.00")
        with self.assertRaises(ValidationError) as caught:
            tape.full_clean()
        self.assertIn("price", caught.exception.message_dict)
        tape.price, tape.sale_price = None, None
        with self.assertRaises(ValidationError) as caught:
            tape.full_clean()
        self.assertIn("sale_price", caught.exception.message_dict)


class OnePriceMigrationTests(RentalarsTestCase):
    """``products/0009_one_price_091``: the second price goes, written to the change log (PRD-047)."""

    def test_sale_prices_of_rental_products_and_prices_of_sale_products_are_removed_and_logged(self) -> None:
        cable = legacy_sale_price(make_product("K-005", price="1.50"), "12.00")
        tape = sale_product()
        Product.objects.filter(pk=tape.pk).update(price=D("2.00"))
        lamp = make_product("L-010", price="20.00")

        MIGRATION.remove_second_prices(apps, None)

        cable.refresh_from_db()
        tape.refresh_from_db()
        lamp.refresh_from_db()
        self.assertEqual((cable.price, cable.sale_price), (D("1.50"), None))
        self.assertEqual((tape.price, tape.sale_price), (None, D("14.90")))
        self.assertEqual((lamp.price, lamp.sale_price), (D("20.00"), None))
        cable_entry = AuditLogEntry.for_object(cable).get(actor_label="Aktualisierung 0.9.1")
        self.assertEqual(cable_entry.changes, {"sale_price": ["12.00", None]})
        tape_entry = AuditLogEntry.for_object(tape).get(actor_label="Aktualisierung 0.9.1")
        self.assertEqual(tape_entry.changes, {"price": ["2.00", None]})
        self.assertFalse(AuditLogEntry.objects.filter(actor_label="Aktualisierung 0.9.1", object_id=str(lamp.pk)))
        # Running it again finds nothing more to do.
        MIGRATION.remove_second_prices(apps, None)
        self.assertEqual(AuditLogEntry.objects.filter(actor_label="Aktualisierung 0.9.1").count(), 2)

    def test_the_three_cases(self) -> None:
        """Rental with both prices, rental with only a sale price, sale product with both prices."""
        both = legacy_sale_price(make_product("K-005", price="1.50"), "12.00")
        only_sale = make_product("K-006", price="1.00")
        Product.objects.filter(pk=only_sale.pk).update(price=None, sale_price=D("9.00"))  # older data
        tape = sale_product()
        Product.objects.filter(pk=tape.pk).update(price=D("2.00"))

        MIGRATION.remove_second_prices(apps, None)

        logged = {
            entry.object_id: entry.changes for entry in AuditLogEntry.objects.filter(actor_label="Aktualisierung 0.9.1")
        }
        both.refresh_from_db()
        self.assertEqual((both.kind, both.price, both.sale_price), ("rental", D("1.50"), None))
        self.assertEqual(logged[str(both.pk)], {"sale_price": ["12.00", None]})
        only_sale.refresh_from_db()
        self.assertEqual(
            (only_sale.kind, only_sale.billing_mode, only_sale.price, only_sale.sale_price),
            ("sale", "flat", None, D("9.00")),
        )
        self.assertEqual(
            logged[str(only_sale.pk)], {"kind": ["rental", "sale"], "billing_mode": ["daily_piece", "flat"]}
        )
        tape.refresh_from_db()
        self.assertEqual((tape.kind, tape.price, tape.sale_price), ("sale", None, D("14.90")))
        self.assertEqual(logged[str(tape.pk)], {"price": ["2.00", None]})
        for product in (both, only_sale, tape):
            product.full_clean()

    def test_a_converted_product_keeps_working(self) -> None:
        """Items, model, kit, sold lines, availability and packing of a rental product that only had a sale price."""
        from rentalars.availability.engine import AvailabilityEngine
        from rentalars.packing.services import build_overview, get_packlist

        tape = make_stock("K-006", 10, "Kabelbinder")
        Product.objects.filter(pk=tape.pk).update(price=None, sale_price=D("0.50"))
        tape.refresh_from_db()
        kit = make_product("T-100", "Aktivbox-Set", kind="kit", billing_mode="daily_kit")
        set_kit_components(kit, [(make_stock("T-010", 4, "Topteil"), 1), (tape, 2)])
        project = make_project()
        sold = add_line(project, tape, 3).line  # sold by default: no rental price
        self.assertTrue(sold.is_sale)
        kit_line = add_line(project, kit, 2).line

        MIGRATION.remove_second_prices(apps, None)

        tape.refresh_from_db()
        self.assertEqual((tape.kind, tape.sale_price, tape.tracks_stock), ("sale", D("0.50"), True))
        tape.full_clean()
        for component in kit.components.all():
            component.full_clean()
        sold.refresh_from_db()
        sold.full_clean()
        self.assertEqual(update_line(sold, rights=ALL_RIGHTS, quantity=D("4")).line.unit_price, D("0.50"))
        new = add_line(project, tape, 1).line
        self.assertEqual((new.is_sale, new.unit_price), (True, D("0.50")))
        kit_line.refresh_from_db()
        kit_line.full_clean()
        answer = AvailabilityEngine().availability([tape.pk, kit.pk], at(10, 12), at(11, 12))
        # 10 pieces: 4 + 1 sold, 2 × 2 in the kits.
        self.assertEqual((answer[tape.pk].stock.plannable, answer[tape.pk].firm), (10, 9))
        self.assertTrue(answer[kit.pk].checked)
        rows = build_overview(get_packlist(project)).rows
        # Packed: the sold line (4), the new one (1) and the two kits (2 × 2).
        self.assertEqual(sorted(row.required for row in rows if row.product.pk == tape.pk), [D("1"), D("4"), D("4")])


class SoldLinesTests(RentalarsTestCase):
    """A line that sold a rental product before stays valid and editable; no new sale of a rental product (PRD-047)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = legacy_sale_price(make_stock("K-005", 9, "XLR-Kabel 5 m", price="1.50"), "12.00")
        self.project = make_project()
        self.sold = add_line(self.project, self.cable, 2, is_sale=True).line  # as was possible earlier
        MIGRATION.remove_second_prices(apps, None)
        self.cable.refresh_from_db()
        self.sold.refresh_from_db()

    def test_the_sold_line_keeps_its_price_and_stays_editable(self) -> None:
        self.assertEqual((self.sold.is_sale, self.sold.unit_price), (True, D("12.00")))
        self.sold.full_clean()
        changed = update_line(self.sold, rights=ALL_RIGHTS, quantity=D("3"), unit_price=D("11.00")).line
        self.assertEqual((changed.is_sale, changed.quantity, changed.unit_price), (True, D("3"), D("11.00")))
        copy = duplicate_line(changed, rights=ALL_RIGHTS).line
        self.assertEqual((copy.is_sale, copy.unit_price), (True, D("11.00")))

    def test_a_rental_product_is_no_longer_sold(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            add_line(self.project, self.cable, 1, is_sale=True)
        self.assertIn("is_sale", caught.exception.message_dict)
        rented = add_line(self.project, self.cable, 1).line
        with self.assertRaises(ValidationError):
            update_line(rented, rights=ALL_RIGHTS, is_sale=True)
        self.assertNotIn("is_sale", LineForm(line=rented, rights=ALL_RIGHTS).fields)

    def test_the_sold_line_can_be_rented_again_once(self) -> None:
        form = LineForm(line=self.sold, rights=ALL_RIGHTS)
        self.assertIn("is_sale", form.fields)
        self.assertIn("Verkaufsprodukt", str(form.fields["is_sale"].help_text))
        rented = update_line(self.sold, rights=ALL_RIGHTS, is_sale=False).line
        self.assertEqual((rented.is_sale, rented.unit_price), (False, D("1.50")))
        self.assertNotIn("is_sale", LineForm(line=rented, rights=ALL_RIGHTS).fields)

    def test_a_template_with_the_sold_line_rents_it(self) -> None:
        template = project_templates.save_as_template(self.project, name="Kabel", rights=ALL_RIGHTS)
        target = make_project("Stadtfest 2028", start=at(20), end=at(22))
        project_templates.apply_template(template, target, rights=ALL_RIGHTS)
        line = target.material_lines.get()
        self.assertEqual((line.is_sale, line.unit_price), (False, D("1.50")))

    def test_sale_products_are_sold_as_before(self) -> None:
        tape = sale_product()
        line = add_line(self.project, tape, 3).line
        self.assertEqual((line.is_sale, line.unit_price), (True, D("14.90")))
        self.assertNotIn("is_sale", LineForm(line=line, rights=ALL_RIGHTS).fields)


class OnePricePageTests(UiTestCase):
    """Form, page and list show the one price; the import reads it (PRD-047)."""

    def test_the_form_of_a_rental_product_asks_for_the_price_only(self) -> None:
        cable = make_product("K-005", price="1.50")
        edit = reverse("products:edit", args=[cable.pk])
        page = self.assert_ok(self.client.get(edit))
        self.assertIn('<div data-show-if="kind=sale" class="hidden">', page)
        self.client.post(edit, form_data(self.client.get(edit), sale_price="12.00", name="XLR-Kabel 5 m"))
        cable.refresh_from_db()
        self.assertEqual((cable.name, cable.price, cable.sale_price), ("XLR-Kabel 5 m", D("1.50"), None))
        detail = self.assert_ok(self.client.get(reverse("products:detail", args=[cable.pk])))
        self.assertIn("Preis je Tag (netto)", detail)
        self.assertNotIn("Verkaufspreis", detail)

    def test_a_sale_product_keeps_its_sale_price(self) -> None:
        page = self.client.get(reverse("products:create"), {"category": category("V").pk})
        data = form_data(page, name="Gaffa schwarz", sale_price="14.90", price="2.00")
        self.assertEqual(data["kind"], "sale")
        self.assertIn('<div data-show-if="kind=sale">', page.content.decode())
        self.client.post(reverse("products:create"), data)
        tape = Product.objects.get(name="Gaffa schwarz")
        self.assertEqual((tape.price, tape.sale_price), (None, D("14.90")))
        self.assertIn(
            "Verkaufspreis (netto)", self.assert_ok(self.client.get(reverse("products:detail", args=[tape.pk])))
        )

    def test_the_list_has_one_price_column(self) -> None:
        make_product("K-005", "XLR-Kabel", price="1.50")
        sale_product()
        csv = self.client.get(reverse("products:list"), {"format": "csv", "columns": "number,price"})
        text = csv.content.decode("utf-8-sig")
        self.assertIn("Preis", text.splitlines()[0])
        self.assertNotIn("Verkaufspreis", text)
        self.assertIn("V-001;Gaffa;", text)
        self.assertIn(";14,9;", text)
        self.assertIn(";1,5;", text)
        page = self.assert_ok(self.client.get(reverse("products:list"), {"columns": "number,name,sale_price,price"}))
        self.assertNotIn("Verkaufspreis", page)

    def test_the_import_reads_the_one_price(self) -> None:
        rows = "Art.-Nr.;Name;Art;Preis;Verkaufspreis\nV-002;Kreppband;Verkauf;3,50;\nK-007;Kabel;Miete;1,00;9,00\n"
        table = read_table(io.BytesIO(rows.encode()), "produkte.csv")
        mapping = {"article_number": 0, "name": 1, "kind": 2, "price": 3, "sale_price": 4}
        report = import_products(table, mapping, dry_run=False, rights=ALL_RIGHTS)
        self.assertTrue(report.ok, report.errors)
        tape = Product.objects.get(article_number="V-002")
        cable = Product.objects.get(article_number="K-007")
        self.assertEqual((tape.price, tape.sale_price), (None, D("3.50")))
        self.assertEqual((cable.price, cable.sale_price), (D("1.00"), None))
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("Nur Verkaufsprodukte haben einen Verkaufspreis", report.warnings[0].message)


class OnePriceApiTests(ApiTestCase):
    """The API refuses the second price; sale products are created as before (PRD-047)."""

    def body(self, article_number: str, **fields: object) -> dict[str, object]:
        code = article_number.split("-")[0]
        return {
            "article_number": article_number,
            "name": f"Produkt {article_number}",
            "category": category(code).pk,
            "unit": Unit.objects.get(name="Stück (Miete)").pk,
            "tax_rate": category(code).pk and Product._meta.get_field("tax_rate").related_model.get_default().pk,
            "kind": "rental",
            "billing_mode": "daily_piece",
            **fields,
        }

    def test_one_price_through_the_api(self) -> None:
        refused = self.admin.post(
            f"{API}/products", self.body("K-005", price="1.50", sale_price="12.00"), format="json"
        )
        self.assert_error(refused, 400, "validation_error", "sale_price")
        sale = self.body("V-002", kind="sale", billing_mode="flat", sale_price="3.50")
        created = self.admin.post(f"{API}/products", sale, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["price"], created.data["sale_price"]), (None, "3.50"))
        both = self.admin.patch(f"{API}/products/{created.data['id']}", {"price": "1.00"}, format="json")
        self.assert_error(both, 400, "validation_error", "price")


# --- 2. Duplicating a product --------------------------------------------------------------------


class DuplicateTests(UiTestCase):
    """ "Duplizieren" opens the form of a new product, filled from the one on the page (PRD-048)."""

    def test_the_form_is_filled_and_nothing_is_saved_before_saving(self) -> None:
        cable = make_product("K-005", "XLR-Kabel 5 m", price="1.50", gtin="4006381333931", description="Neutrik")
        make_product("K-009")
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[cable.pk])))
        address = f"{reverse('products:create')}?duplicate={cable.pk}"
        self.assertIn(f'href="{address}"', page.replace("&amp;", "&"))
        self.assertIn("Duplizieren", page)

        count = Product.objects.count()
        form = self.client.get(address)
        data = form_data(form)
        self.assertEqual(data["article_number"], "K-010")
        self.assertEqual(
            (data["name"], data["kind"], data["price"], data["description"]),
            ("XLR-Kabel 5 m", "rental", "1,50", "Neutrik"),
        )
        self.assertEqual((data["gtin"], data["duplicate"]), ("", str(cable.pk)))
        self.assertIn("Eine Kopie von K-005 XLR-Kabel 5 m", form.content.decode())
        self.assertEqual(Product.objects.count(), count)

        self.client.post(reverse("products:create"), {**data, "name": "XLR-Kabel 10 m"})
        copy = Product.objects.get(article_number="K-010")
        self.assertEqual(
            (copy.name, copy.price, copy.category, copy.gtin), ("XLR-Kabel 10 m", D("1.50"), cable.category, "")
        )

    def test_a_kit_is_duplicated_with_its_components(self) -> None:
        kit = make_kit(make_stock("T-010", 6, "Topteil"), make_stock("T-020", 3, "Stativ"))
        form = self.client.get(reverse("products:create"), {"duplicate": kit.pk})
        self.assertIn("Beim Speichern werden auch die Bestandteile des Sets übernommen", form.content.decode())
        self.client.post(reverse("products:create"), form_data(form, name="Aktivbox-Set 2"))
        copy = Product.objects.get(name="Aktivbox-Set 2")
        self.assertEqual(copy.article_number, "ST-002")
        self.assertEqual(
            sorted(copy.components.values_list("component__article_number", "quantity")), [("T-010", 2), ("T-020", 1)]
        )
        self.assertEqual(KitComponent.objects.filter(kit=kit).count(), 2)

    def test_choosing_another_category_keeps_the_copy(self) -> None:
        lamp = make_product("L-010", "Spot", price="20.00")
        data = form_data(
            self.client.get(reverse("products:create"), {"duplicate": lamp.pk, "category": category("T").pk})
        )
        self.assertEqual((data["article_number"], data["name"], data["price"]), ("T-001", "Spot", "20,00"))

    def test_without_the_price_right_no_price_is_copied(self) -> None:
        lamp = make_product("L-010", "Spot", price="20.00")
        Role.objects.create(name="Werkstatt", module_levels={"products": 2})
        workshop = self.browser_for("willi", "Werkstatt")
        page = workshop.get(reverse("products:create"), {"duplicate": lamp.pk})
        self.assertNotIn("price", form_data(page))
        self.assertNotIn("20,00", page.content.decode())


class DuplicateApiTests(ApiTestCase):
    """``POST /products/{id}/duplicate`` – the same through the API (PRD-048)."""

    def test_duplicate_through_the_api(self) -> None:
        kit = make_kit(make_stock("T-010", 6, "Topteil"), make_stock("T-020", 3, "Stativ"))
        answer = self.admin.post(f"{API}/products/{kit.pk}/duplicate", {"name": "Aktivbox-Set B"}, format="json")
        self.assertEqual(answer.status_code, 201, answer.data)
        self.assertEqual((answer.data["article_number"], answer.data["name"]), ("ST-002", "Aktivbox-Set B"))
        self.assertEqual([part["quantity"] for part in answer.data["components"]], [2, 1])
        self.assertEqual(Product.objects.filter(kind=ProductKind.KIT).count(), 2)


# --- 3. The article number follows the category in the form of a product made from a model -------


class ArticleNumberTests(UiTestCase):
    """ "Als Produkt anlegen" opens the form; choosing a category there brings its article number (PRD-049)."""

    def test_the_article_number_follows_the_category(self) -> None:
        make_product("T-004")
        model = make_model("Mackie SRM450", category_code="L")
        response = self.client.post(reverse("material:model_create_product", args=[model.pk]))
        product = Product.objects.get(name="Mackie SRM450")
        self.assertEqual(product.article_number, "L-001")
        edit = reverse("products:edit", args=[product.pk])
        self.assertRedirects(response, edit)
        page = self.assert_ok(self.client.get(edit))
        address = reverse("products:article_number", args=[product.pk])
        self.assertIn(f'hx-get="{address}" hx-trigger="change" hx-target="#article-number-field"', page)

        field = self.assert_ok(self.htmx("get", address, {"category": category("T").pk}))
        self.assertIn('id="article-number-field"', field)
        self.assertIn('value="T-005"', field)
        back = self.assert_ok(self.htmx("get", address, {"category": category("L").pk}))
        self.assertIn('value="L-001"', back)

        self.client.post(edit, form_data(self.client.get(edit), category=category("T").pk, article_number="T-005"))
        product.refresh_from_db()
        self.assertEqual((product.article_number, product.category.code), ("T-005", "T"))


class ArticleNumberApiTests(ApiTestCase):
    """``suggest-article-number`` keeps the number of the product named, as the form does (PRD-049)."""

    def test_suggestion_for_a_product(self) -> None:
        product = make_product("L-001")
        make_product("T-004")
        url = f"{API}/products/suggest-article-number"
        self.assertEqual(
            self.admin.get(url, {"category": category("T").pk, "product": product.pk}).data["article_number"], "T-005"
        )
        self.assertEqual(
            self.admin.get(url, {"category": category("L").pk, "product": product.pk}).data["article_number"], "L-001"
        )
        self.assertEqual(self.admin.get(url, {"category": category("L").pk}).data["article_number"], "L-002")


# --- 4. and 6. The availability follows the period, and leads to the utilization -----------------


class AvailabilityPanelTests(UiTestCase):
    """The period chosen is shown at once; "Zeitraum prüfen" only without JavaScript (PRD-050).

    The link to Planung → Materialauslastung with product and period (PRD-051).
    """

    def test_the_period_updates_the_figures_without_the_button(self) -> None:
        cable = make_stock("K-005", 9, "XLR-Kabel 5 m")
        add_line(make_project("Stadtfest", start=at(10), end=at(12)), cable, 6)
        address = reverse("products:detail", args=[cable.pk])
        page = self.assert_ok(self.client.get(address))
        self.assertIn(f'hx-get="{address}" hx-trigger="change delay:400ms" hx-target="#availability-result"', page)
        self.assertIn('hx-select="#availability-result"', page)
        before, button, after = page.partition("Zeitraum prüfen")
        self.assertTrue(button)
        self.assertIn("<noscript>", before[-200:])
        self.assertNotIn("Zeitraum prüfen", after)

        answer = self.assert_ok(self.htmx("get", address, {"start": "2027-03-11T00:00", "end": "2027-03-13T00:00"}))
        result = answer[answer.index('id="availability-result"') :]
        self.assertIn("11.03.2027 00:00 – 13.03.2027 00:00", result)
        self.assertIn("frei <b>3</b>", result)
        self.assertIn("3 von 9 frei vom 11.03.2027 00:00 bis 13.03.2027 00:00", answer)

    def test_a_link_to_the_utilization_with_product_and_period(self) -> None:
        cable = make_stock("K-005", 9, "XLR-Kabel 5 m")
        address = reverse("products:detail", args=[cable.pk])
        page = self.assert_ok(self.client.get(address, {"start": "2027-03-10T08:00", "end": "2027-03-24T08:00"}))
        link = f"/schedule/products/?product={cable.pk}&amp;from=2027-03-10&amp;weeks=3"
        self.assertIn(f'href="{link}"', page)
        self.assertIn("In der Materialauslastung zeigen", page)
        short = self.assert_ok(self.client.get(address, {"start": "2027-03-10T08:00", "end": "2027-03-12T08:00"}))
        self.assertIn(f"/schedule/products/?product={cable.pk}&amp;from=2027-03-10&amp;days=3", short)
        target = self.assert_ok(self.client.get(f"/schedule/products/?product={cable.pk}&from=2027-03-10&weeks=3"))
        self.assertIn("XLR-Kabel 5 m", target)
        # Who may not open the utilization gets no link; nor does a product without stock.
        Role.objects.create(name="Werkstatt", module_levels={"products": 2})
        workshop = self.browser_for("willi", "Werkstatt")
        self.assertNotIn("In der Materialauslastung zeigen", self.assert_ok(workshop.get(address)))
        transport = make_product("N-001", "Transport", kind="incidental", billing_mode="flat")
        self.assertNotIn(
            "In der Materialauslastung zeigen",
            self.assert_ok(self.client.get(reverse("products:detail", args=[transport.pk]))),
        )

    def test_the_address_of_the_utilization(self) -> None:
        self.assertEqual(
            utilization_address(7, at(10, 8), at(24, 8)), "/schedule/products/?product=7&from=2027-03-10&weeks=3"
        )
        self.assertEqual(
            utilization_address(7, at(10, 8), at(12)), "/schedule/products/?product=7&from=2027-03-10&days=2"
        )
        self.assertEqual(
            utilization_address(7, at(10, 8), at(10, 9)), "/schedule/products/?product=7&from=2027-03-10&days=1"
        )


# --- 5. Kits in the material utilization ---------------------------------------------------------


class KitUtilizationTests(UiTestCase):
    """A kit's row counts complete kits; its components unfold below it (VFG-037)."""

    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("T-010", 9, "Topteil")
        self.stand = make_stock("T-020", 3, "Stativ")
        self.kit = make_kit(self.speaker, self.stand)
        add_line(make_project("Stadtfest", start=at(10, 8), end=at(11, 18)), self.speaker, 4)
        add_line(make_project("Option", start=at(10, 8), end=at(11, 18), status="option"), self.stand, 1)
        add_line(make_project("Messe", start=at(10, 8), end=at(11, 18)), self.kit, 1)

    def test_complete_kits_column_by_column(self) -> None:
        """2 speakers and 1 stand make a kit: 9 + 3 in stock, 4 + 2 speakers and 1 stand taken, 1 stand as option."""
        from rentalars.availability.services import utilization

        days = [at(9).date(), at(10).date()]
        loads = utilization([self.speaker.pk, self.stand.pk], days)
        before, during = kit_loads({self.speaker.pk: 2, self.stand.pk: 1}, loads)
        self.assertEqual((before.stock, before.free, before.optional), (3, 3, 0))
        # Speakers: 9 - 6 = 3 free → 1 kit; stands: 3 - 1 = 2 free, 1 after the option.
        self.assertEqual((during.stock, during.free, during.firm, during.optional), (3, 1, 2, 0))

    def test_the_kit_is_chosen_and_unfolds_its_components(self) -> None:
        page = self.assert_ok(
            self.client.get("/schedule/products/", {"product": self.kit.pk, "from": "2027-03-08", "weeks": "1"})
        )
        self.assertIn("Aktivbox-Set", page)
        self.assertIn("3 komplette Sets im Bestand", page)
        self.assertIn(f'id="kit-parts-{self.kit.pk}" data-keep-state="kit-{self.kit.pk}" checked', page)
        parts = page[page.index('class="tl-kit-parts"') :]
        self.assertIn("T-010", parts)
        self.assertIn("T-020", parts)
        self.assertIn('title="je Set">2 ×</span>', parts)
        self.assertIn("1 von 3 frei, 0 weitere als Optionen", page)
        self.assertIn("Sets: wie viele komplette Sets frei sind", page)

    def test_the_category_of_sets_and_the_suggestions(self) -> None:
        sets = Category.objects.get(code="ST")
        page = self.assert_ok(self.client.get("/schedule/products/", {"category": sets.pk, "from": "2027-03-08"}))
        self.assertIn("Aktivbox-Set", page)
        self.assertIn(f'id="kit-parts-{self.kit.pk}" data-keep-state="kit-{self.kit.pk}">', page)  # folded
        suggest = page.split('data-url="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
        self.assertNotIn("kit", suggest)
        found = self.client.get(suggest, {"q": "Aktivbox"}).json()
        self.assertEqual([entry["id"] for entry in found], [self.kit.pk])

    def test_hour_columns(self) -> None:
        page = self.assert_ok(
            self.client.get("/schedule/products/", {"product": self.kit.pk, "from": "2027-03-10", "days": "2"})
        )
        self.assertIn('class="tl-load free-ok"', page)
        self.assertIn(": 1 von 3 frei, 0 weitere als Optionen", page)
        self.assertIn('class="tl-kit-parts"', page)


class KitUtilizationApiTests(ApiTestCase):
    """``GET /utilization`` answers kits with their components (VFG-037)."""

    def test_utilization_of_a_kit(self) -> None:
        speaker = make_stock("T-010", 9, "Topteil")
        stand = make_stock("T-020", 3, "Stativ")
        kit = make_kit(speaker, stand)
        add_line(make_project("Stadtfest", start=at(10, 8), end=at(11, 18)), speaker, 4)
        answer = self.admin.get(
            f"{API}/utilization", {"product": [kit.pk, stand.pk], "from": "2027-03-10", "days": "1"}
        )
        self.assertEqual(answer.status_code, 200, answer.data)
        by_number = {entry["article_number"]: entry for entry in answer.data}
        set_day = by_number["ST-001"]["days"][0]
        self.assertEqual((set_day["stock"], set_day["free"]), (3, 2))
        self.assertEqual(
            [(part["article_number"], part["per_kit"]) for part in by_number["ST-001"]["components"]],
            [("T-010", 2), ("T-020", 1)],
        )
        self.assertEqual(by_number["ST-001"]["components"][0]["days"][0]["firm"], 4)
        self.assertEqual(by_number["T-020"]["components"], [])
