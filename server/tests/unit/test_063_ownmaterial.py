# SPDX-License-Identifier: GPL-3.0-or-later
"""Customer material: the category C "Fremdmaterial" with the customer as owner (PRD-043), and such
material in the projects of its owner – taken along, never charged (PRJ-096)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.core.tabular import Table
from rentalars.customers.services import delete_customer
from rentalars.documents import xrechnung
from rentalars.documents.content import build_delivery_note, build_priced, customer_material_note, only_groups
from rentalars.masterdata import defaults
from rentalars.masterdata.models import Category, StorageLocation, Unit
from rentalars.material.labels import build_labels
from rentalars.packing import services as packing
from rentalars.products import services as product_services
from rentalars.products.importer import import_products
from rentalars.products.models import BillingMode, KitComponent, Product, ProductKind, ScaleMode
from rentalars.products.tables import PRODUCT_TABLE
from rentalars.projects import services
from rentalars.projects.lines import BulkAction, change_lines
from rentalars.projects.list_sums import attach_sums
from rentalars.projects.models import Group, LineVariant
from rentalars.projects.planning import build_planning
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.project_templates import apply_template, save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_customer,
    make_items,
    make_model,
    make_product,
    make_project,
    make_user,
    ready_for_invoices,
)

D = Decimal


def customer_material_category() -> Category:
    """The category C of the start data."""
    return Category.objects.get(parent__isnull=True, code="C")


def band_material(owner: object, article_number: str = "C-001", name: str = "Mischpult der Band", **fields: object):
    """A product of customer material, with no price."""
    return make_product(
        article_number, name, price=None, owner=owner, unit=Unit.objects.get(name="Stück (Miete)"), **fields
    )


def band_stock(owner: object, count: int, article_number: str = "C-001", **model_fields: object) -> Product:
    """Customer material with a model (weight, dimensions) and ``count`` items."""
    product = band_material(owner, article_number)
    model = make_model(f"Modell {article_number}", product)
    for name, value in model_fields.items():
        setattr(model, name, value)
    model.save()
    make_items(model, count)
    return product


class StartDataTests(RentalarsTestCase):
    """PRD-043: C "Fremdmaterial" for new installations."""

    def test_new_installations_have_c(self) -> None:
        category = customer_material_category()
        self.assertEqual(
            (category.name, category.is_customer_material, category.has_own_stock, category.default_product_kind),
            ("Fremdmaterial", True, True, "rental"),
        )
        self.assertEqual(category.default_unit.name, "Stück (Miete)")
        # No other start category is marked.
        self.assertEqual(list(Category.objects.filter(is_customer_material=True)), [category])

    def test_install_again_adds_nothing(self) -> None:
        count = Category.objects.count()
        defaults.install()
        self.assertEqual(Category.objects.count(), count)


class CategoryRuleTests(RentalarsTestCase):
    """PRD-043: the mark sits on main categories with stock and stays as it is once products use it."""

    def test_a_category_of_ones_own_choice_can_be_marked(self) -> None:
        backline = Category(name="Backline der Kunden", code="BK", is_customer_material=True)
        backline.full_clean()
        backline.save()
        self.assertTrue(Category(name="Amps", parent=backline).holds_customer_material)

    def test_only_main_categories_with_stock(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            Category(name="Pulte", parent=customer_material_category(), is_customer_material=True).full_clean()
        self.assertIn("is_customer_material", caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            Category(name="Kundenservice", code="KS", has_own_stock=False, is_customer_material=True).full_clean()

    def test_the_mark_stays_while_there_are_products(self) -> None:
        band_material(make_customer("Band"))
        category = customer_material_category()
        category.is_customer_material = False
        with self.assertRaises(ValidationError):
            category.full_clean()
        sound = Category.objects.get(parent__isnull=True, code="T")
        make_product("T-001")
        sound.is_customer_material = True
        with self.assertRaises(ValidationError):
            sound.full_clean()


class ProductRuleTests(RentalarsTestCase):
    """PRD-043: a product of customer material has an owner, no price, and never yields an amount."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")

    def test_customer_material_with_owner(self) -> None:
        product = band_material(self.band)
        self.assertTrue(product.is_customer_material)
        self.assertEqual((product.price, product.sale_price), (None, None))
        # Billing that never yields an amount: flat, without a scale.
        self.assertEqual((product.billing_mode, product.rental_scale_mode), (BillingMode.FLAT, ScaleMode.NONE))
        self.assertIsNone(product.effective_rental_scale())
        self.assertTrue(product.tracks_stock)

    def test_c_needs_an_owner(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            make_product("C-001", price=None)
        self.assertIn("owner", caught.exception.message_dict)

    def test_an_owner_only_in_c(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            make_product("T-001", owner=self.band)
        self.assertIn("owner", caught.exception.message_dict)

    def test_never_a_price(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            make_product("C-001", price="10.00", owner=self.band)
        self.assertIn("price", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            make_product("C-002", price=None, sale_price=D("5"), owner=self.band)
        self.assertIn("sale_price", caught.exception.message_dict)

    def test_rental_or_kit_only(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            make_product("C-001", price=None, owner=self.band, kind=ProductKind.SALE)
        self.assertIn("kind", caught.exception.message_dict)
        kit = make_product("C-002", price=None, owner=self.band, kind=ProductKind.KIT)
        self.assertTrue(kit.is_kit)

    def test_the_owner_stays_once_planned(self) -> None:
        product = band_stock(self.band, 1)
        add_line(make_project(customer=self.band), product)
        product.owner = make_customer("Andere Band")
        with self.assertRaises(ValidationError) as caught:
            product.full_clean()
        self.assertIn("owner", caught.exception.message_dict)

    def test_kits_keep_customer_material_apart(self) -> None:
        desk = band_material(self.band)
        own_kit = make_product("T-100", kind=ProductKind.KIT)
        with self.assertRaises(ValidationError):
            KitComponent(kit=own_kit, component=desk).full_clean()
        band_kit = make_product("C-002", price=None, owner=self.band, kind=ProductKind.KIT)
        KitComponent(kit=band_kit, component=desk).full_clean()
        with self.assertRaises(ValidationError):
            KitComponent(kit=band_kit, component=make_product("K-001")).full_clean()
        other = band_material(make_customer("Andere Band"), "C-003")
        with self.assertRaises(ValidationError):
            KitComponent(kit=band_kit, component=other).full_clean()

    def test_presets_of_c_and_of_an_owner(self) -> None:
        presets = product_services.presets_for_category(customer_material_category())
        self.assertEqual((presets["kind"], presets["billing_mode"]), ("rental", BillingMode.FLAT))
        self.assertEqual(presets["article_number"], "C-001")
        preset = product_services.presets_for_owner(self.band.pk, None)
        self.assertEqual((preset["owner"], preset["category"]), (self.band, customer_material_category()))

    def test_a_customer_with_material_is_not_deleted(self) -> None:
        band_material(self.band)
        with self.assertRaises(ValidationError) as caught:
            delete_customer(self.band)
        self.assertEqual(
            caught.exception.messages,
            ["Dieser Kunde hat Material im Lager und kann nicht gelöscht werden. Deaktiviere ihn stattdessen."],
        )

    def test_the_customers_material_with_stock_and_place(self) -> None:
        hall = StorageLocation.objects.create(name="Halle 2")
        desk = band_stock(self.band, 2)
        for item in desk.material_models.get().items.all():
            item.storage_location = hall
            item.save()
        band_material(self.band, "C-002", "Multicore 32/8")
        with CaptureQueriesContext(connection) as queries:
            overview = product_services.customer_material(self.band)
        self.assertLessEqual(len(queries), 5)
        self.assertEqual([entry.product.article_number for entry in overview], ["C-001", "C-002"])
        self.assertEqual((overview[0].stock.total, overview[0].locations), (2, ["Halle 2"]))
        self.assertEqual((overview[1].stock.total, overview[1].locations), (0, []))
        self.assertEqual(product_services.customer_material(make_customer("Ohne")), [])

    def test_labels_name_the_owner(self) -> None:
        desk = band_stock(self.band, 1)
        own = make_items(make_model("Pult", make_product("T-001")), 1)[0]
        labels = build_labels([desk.material_models.get().items.get(), own], "barcode")
        self.assertEqual([label.owner for label in labels], ["Eigentum von Die Band", ""])


class ProductImportTests(RentalarsTestCase):
    """PRD-043: the column "Eigentümer" of the product list, imported again by customer number or name."""

    def run_import(self, rows: list[list[str]], *, dry_run: bool = False) -> object:
        table = Table(headers=["Art.-Nr.", "Name", "Eigentümer"], rows=rows)
        return import_products(table, {"article_number": 0, "name": 1, "owner": 2}, dry_run=dry_run, rights=ALL_RIGHTS)

    def test_owner_by_number_and_by_name(self) -> None:
        band = make_customer("Die Band")
        report = self.run_import([["C-001", "Mischpult", band.number], ["C-002", "Multicore", "die band"]])
        self.assertEqual((report.errors, report.created), ([], 2))
        self.assertEqual(
            set(Product.objects.filter(owner=band).values_list("article_number", flat=True)), {"C-001", "C-002"}
        )

    def test_unknown_owner_and_missing_owner(self) -> None:
        report = self.run_import([["C-001", "Mischpult", "Niemand"], ["C-002", "Multicore", ""]])
        texts = [issue.message for issue in report.errors]
        self.assertIn("Es gibt keinen Kunden „Niemand“.", texts)
        self.assertTrue(any("Eigentümer" in text for text in texts), texts)
        self.assertFalse(Product.objects.filter(article_number__startswith="C-").exists())

    def test_the_export_has_the_column(self) -> None:
        band = make_customer("Die Band")
        band_material(band)
        column = next(column for column in PRODUCT_TABLE.columns if column.key == "owner")
        self.assertEqual(str(column.label), "Eigentümer")
        self.assertEqual(column.cell(Product.objects.get(article_number="C-001")), "Die Band")


class PlanningTests(RentalarsTestCase):
    """PRJ-096: customer material only in projects of its owner, taken along and never charged."""

    def setUp(self) -> None:
        super().setUp()
        self.band = make_customer("Die Band")
        self.band.default_discount_percent = D("10")
        self.band.save()
        self.desk = band_stock(
            self.band, 1, weight_kg=D("25.5"), length_cm=D("100"), width_cm=D("60"), height_cm=D("30")
        )
        self.project = make_project("Gig Stadthalle", customer=self.band)
        self.light = make_product("L-001", price="50.00", billing_mode=BillingMode.FLAT)

    def test_planned_in_the_owners_project(self) -> None:
        line = add_line(self.project, self.desk).line
        self.assertTrue(line.is_customer_material)
        self.assertEqual((line.unit_price, line.discount_percent, line.billing_mode), (D("0"), D("0"), "flat"))
        self.assertIsNone(line.scale_version)

    def test_refused_in_a_project_of_somebody_else(self) -> None:
        other = make_project("Stadtfest", customer=make_customer("Stadtwerke"))
        with self.assertRaises(ValidationError) as caught:
            add_line(other, self.desk)
        self.assertEqual(
            caught.exception.message_dict["product"],
            [
                "C-001 Mischpult der Band ist Kundenmaterial von Die Band und lässt sich nur in Projekten dieses "
                "Kunden einplanen."
            ],
        )
        self.assertFalse(other.material_lines.exists())

    def test_a_subproject_has_the_customer_of_its_whole_project(self) -> None:
        part = services.create_subproject(self.project, name="Soundcheck")
        self.assertTrue(add_line(part, self.desk).line.is_customer_material)

    def test_no_price_no_discount_no_option_no_sale(self) -> None:
        line = add_line(self.project, self.desk).line
        for changes, field in (
            ({"unit_price": D("10")}, "unit_price"),
            ({"discount_percent": D("5")}, "discount_percent"),
            ({"variant": LineVariant.OPTIONAL}, None),
            ({"is_sale": True}, "is_sale"),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError) as caught:
                services.update_line(line, rights=ALL_RIGHTS, **changes)
            if field is not None:
                self.assertIn(field, caught.exception.message_dict)
            line.refresh_from_db()

    def test_bulk_actions_skip_it(self) -> None:
        line = add_line(self.project, self.desk).line
        for action, values in ((BulkAction.OPTIONAL, {}), (BulkAction.DISCOUNT, {"discount_percent": D("5")})):
            result = change_lines(self.project, [line.pk], action, rights=ALL_RIGHTS, **values)
            self.assertEqual([skipped.line.pk for skipped in result.skipped], [line.pk])
        line.refresh_from_db()
        self.assertEqual((line.variant, line.discount_percent), ("", D("0")))

    def test_amount_zero_and_in_no_sum(self) -> None:
        group = add_group(self.project, "FOH")
        add_line(self.project, self.light, 2, group=group)
        desk = add_line(self.project, self.desk, group=group).line
        add_line(self.project, self.desk)
        prices = compute_project_prices(self.project)
        line_price = prices.by_line_id[desk.pk]
        self.assertEqual((line_price.amount, line_price.counts, line_price.is_customer_material), (D("0"), True, True))
        # The customer's standard discount applies to the light, not to the band's desk.
        self.assertEqual(prices.net_total, D("90.00"))
        self.assertEqual(prices.by_group_id[group.pk].lines_total, D("90.00"))
        self.assertEqual([tax_line.net for tax_line in prices.tax_lines], [D("90.00")])
        self.assertEqual((prices.optional_lines_total, prices.variant_lines), (D("0"), []))

    def test_a_flat_price_is_not_spread_onto_it(self) -> None:
        group = add_group(self.project, "Pauschal", flat_price=D("500"))
        add_line(self.project, self.desk, group=group)
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.net_total, D("500"))
        # Only the flat price itself is taxed – at the default rate, as for a group without lines.
        self.assertEqual(sum(tax_line.net for tax_line in prices.tax_lines), D("500"))

    def test_not_part_of_the_material_revenue(self) -> None:
        add_line(self.project, self.light, 2)
        add_line(self.project, self.desk)
        attach_sums([self.project], rights=ALL_RIGHTS, user=make_user("chef", superuser=True))
        self.assertEqual(self.project.list_sums.material_revenue, D("90.00"))

    def test_short_without_a_subrental(self) -> None:
        """Counted like own material: one desk, two projects of the band at the same time."""
        add_line(self.project, self.desk)
        second = add_line(make_project("Zweiter Gig", customer=self.band), self.desk).line
        planning = build_planning(second.project)
        [short] = planning.short_lines
        self.assertEqual([shortage.product for shortage in short.shortages], [self.desk])
        with self.assertRaises(ValidationError):
            services.accept_subrental_suggestion(second, self.desk, 1, rights=ALL_RIGHTS)

    def test_the_customer_of_the_project_stays(self) -> None:
        add_line(self.project, self.desk)
        with self.assertRaises(ValidationError) as caught:
            services.update_project(self.project, customer=make_customer("Andere"))
        self.assertIn("customer", caught.exception.message_dict)

    def test_copies_and_templates_leave_it_out_for_others(self) -> None:
        group = add_group(self.project, "FOH")
        add_line(self.project, self.desk, group=group)
        add_line(self.project, self.light, group=group)
        other = make_project("Stadtfest", customer=make_customer("Stadtwerke"))
        services.copy_group(group, other, rights=ALL_RIGHTS)
        self.assertEqual(list(other.material_lines.values_list("product", flat=True)), [self.light.pk])
        template = save_as_template(self.project, name="Band-Gig", rights=ALL_RIGHTS)
        third = make_project("Dritter", customer=make_customer("Dritte"))
        result = apply_template(template, third, rights=ALL_RIGHTS)
        self.assertEqual(list(third.material_lines.values_list("product", flat=True)), [self.light.pk])
        self.assertTrue(any("Kundenmaterial eines anderen Kunden" in text for text in result.left_out))
        again = make_project("Nächster Gig", customer=self.band)
        apply_template(template, again, rights=ALL_RIGHTS)
        self.assertEqual(again.material_lines.count(), 2)


class DocumentTests(RentalarsTestCase):
    """PRJ-096: offers list the customer's own material without price; the invoice leaves it out."""

    def setUp(self) -> None:
        super().setUp()
        self.band = ready_for_invoices(make_customer("Die Band"))
        self.desk = band_stock(self.band, 1, weight_kg=D("25"))
        self.project = make_project("Gig", customer=self.band)
        self.group = add_group(self.project, "FOH")
        add_line(self.project, make_product("L-001", price="50.00", billing_mode=BillingMode.FLAT), 2, group=self.group)
        add_line(self.project, self.desk, group=self.group)

    def build(self, kind: str) -> object:
        return build_priced(self.project, kind, title="Dokument", number="X-1", issued_on=datetime.date(2027, 3, 1))

    def positions(self, content: object) -> list[object]:
        return [position for section in content.sections for position in section.positions]

    def test_the_offer_lists_it_without_price(self) -> None:
        content = self.build("offer")
        light, desk = self.positions(content)
        self.assertTrue(desk.customer_material)
        self.assertEqual((desk.unit_price, desk.amount, desk.counts), (None, D("0"), False))
        self.assertEqual(desk.details, "Kundeneigenes Material – wird mitgeführt, ohne Berechnung")
        self.assertEqual(desk.details, customer_material_note())
        self.assertEqual(content.net_total, D("100.00"))
        self.assertEqual(content.positions, [light])
        self.assertEqual([share.positions_total for share in content.taxes], [D("100.00")])

    def test_offer_with_groups_only_names_it_under_its_group(self) -> None:
        content = only_groups(self.build("offer"))
        [section] = [section for section in content.sections if section.is_group]
        self.assertEqual([position.title for position in section.positions], ["Mischpult der Band"])
        self.assertEqual(section.positions[0].number, "1")

    def test_order_confirmation_too(self) -> None:
        self.assertTrue(self.positions(self.build("order_confirmation"))[1].customer_material)

    def test_the_invoice_leaves_it_out(self) -> None:
        content = self.build("invoice")
        self.assertEqual([position.title for position in self.positions(content)], ["Produkt L-001"])
        xml = xrechnung.build_xml(content).decode()
        self.assertEqual(xml.count("<cac:InvoiceLine>"), 1)
        self.assertNotIn("Mischpult", xml)

    def test_stored_and_read_again(self) -> None:
        from rentalars.documents.content import from_json

        again = from_json(self.build("offer").as_json())
        self.assertTrue(self.positions(again)[1].customer_material)

    def test_the_delivery_note_and_the_packlist_say_it_is_taken_along(self) -> None:
        packlist = packing.get_packlist(self.project)
        overview = packing.build_overview(packlist)
        row = next(row for row in overview.rows if row.product == self.desk)
        self.assertTrue(row.is_customer_material)
        self.assertEqual(row.weight_kg, D("25"))
        note = build_delivery_note(
            self.project, title="Lieferschein", number="LS-1", issued_on=datetime.date(2027, 3, 1)
        )
        rows = [entry for _title, entries in note.delivery_rows for entry in entries]
        self.assertEqual([entry.customer_material for entry in rows], [False, True])

    def test_issue_and_return_as_usual(self) -> None:
        packlist = packing.get_packlist(self.project)
        make_items(make_model("Scheinwerfer", Product.objects.get(article_number="L-001")), 2)
        packing.pack_all(packlist)
        packing.issue(packlist)
        overview = packing.build_overview(packlist)
        row = next(row for row in overview.rows if row.product == self.desk)
        self.assertEqual(row.issued, D("1"))


class GroupedTests(RentalarsTestCase):
    """PRJ-096 with nested groups and a whole project – the planning sees it in its group."""

    def test_in_a_subgroup(self) -> None:
        band = make_customer("Die Band")
        desk = band_stock(band, 1)
        project = make_project("Gig", customer=band, start=at(10), end=at(12))
        parent = add_group(project, "Ton")
        child = add_group(project, "FOH", parent=parent)
        line = add_line(project, desk, group=child).line
        planning = build_planning(project)
        planned = next(planned for group in planning.groups for planned in group.lines if planned.line.pk == line.pk)
        self.assertTrue(planned.price.is_customer_material)
        self.assertEqual(Group.objects.get(pk=child.pk).lines.count(), 1)
