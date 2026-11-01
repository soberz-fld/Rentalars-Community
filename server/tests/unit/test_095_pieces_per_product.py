# SPDX-License-Identifier: GPL-3.0-or-later
"""A product of several pieces – "10 × XLR cable 1.5 m" is the product K-005.

The requirement: a product can also be "10 pieces of material x", e.g. 10 times the model 1.5 m XLR is the product K-005.

``Product.pieces_per_product`` says how many items of its material one piece of the product is. Everything that
plans, reserves and packs counts in products (stock = fit items ÷ pieces, rounded down); the items are chosen and
issued ten by ten. With one piece per product nothing changes – the existing tests of stock, availability and
packing stay as they are, and a few tests here pin the old behaviour down once more.
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.accounts.rights import Rights
from rentalars.availability.engine import AvailabilityEngine, Demand, Firmness
from rentalars.availability.stock import ProductStock, stock_of_products
from rentalars.core import import_exports, imports
from rentalars.core.tabular import Table, read_table, resolve_mapping
from rentalars.material.models import ItemBlock, ItemStatus, MaterialItem
from rentalars.packing import services
from rentalars.packing.models import Allocation, PacklistStatus
from rentalars.products.models import Product
from rentalars.products.services import set_kit_components
from rentalars.projects import profitability
from rentalars.projects.list_sums import _prices_of
from rentalars.projects.models import Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    make_items,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
)
from tests.ui.base import UiTestCase, form_data

D = Decimal


def make_pack(article_number: str, items: int, pieces: int = 10, name: str | None = None) -> Product:
    """A product of ``pieces`` items each, with one model and ``items`` items – "XLR cable 1.5 m, 10-pack"."""
    product = make_product(article_number, name or "XLR-Kabel 1,5 m, 10er-Pack", pieces_per_product=pieces)
    make_items(make_model(f"XLR-Kabel 1,5 m {article_number}", product), items)
    return product


def free(product: Product, first: int = 10, last: int = 12) -> int:
    """The free pieces of a product from the ``first`` to the ``last`` of March 2027."""
    return AvailabilityEngine().availability([product.pk], at(first), at(last))[product.pk].free


class StockOfPiecesTests(RentalarsTestCase):
    """The stock of a product is the fit items divided by the pieces, rounded down."""

    def test_105_cables_are_ten_packs(self) -> None:
        pack = make_pack("K-005", 105)
        stock = stock_of_products([pack.pk])[pack.pk]
        self.assertEqual((stock.total, stock.operational, stock.plannable), (10, 10, 10))
        self.assertEqual((stock.total_pieces, stock.operational_pieces, stock.plannable_pieces), (105, 105, 105))
        self.assertEqual(stock.pieces_per_product, 10)
        self.assertEqual(stock.left_over_pieces, 5)
        self.assertTrue(stock.consists_of_pieces)

    def test_a_defective_item_takes_one_piece_not_one_product(self) -> None:
        """MAT-021: 105 items, 6 of them defective – 99 fit make 9 products, not 10."""
        pack = make_pack("K-005", 105)
        MaterialItem.objects.filter(inventory_number__in=range(1, 7)).update(status=ItemStatus.DEFECTIVE)
        stock = stock_of_products([pack.pk])[pack.pk]
        self.assertEqual((stock.total, stock.operational, stock.plannable), (10, 9, 9))
        self.assertEqual(stock.operational_pieces, 99)
        self.assertEqual(free(pack), 9)

    def test_fewer_items_than_one_piece_are_no_stock(self) -> None:
        pack = make_pack("K-005", 9)
        self.assertEqual(stock_of_products([pack.pk])[pack.pk].plannable, 0)
        self.assertEqual(free(pack), 0)

    def test_one_piece_per_product_is_as_before(self) -> None:
        cable = make_stock("K-006", 9)
        stock = stock_of_products([cable.pk])[cable.pk]
        self.assertEqual(stock, ProductStock(total=9, operational=9, plannable=9))
        self.assertEqual((stock.total_pieces, stock.plannable_pieces, stock.left_over_pieces), (9, 9, 0))
        self.assertFalse(stock.consists_of_pieces)

    def test_items_of_another_model_count_with_the_factor_of_their_product(self) -> None:
        """PRD-003: an item that names the product itself is one piece of it, whatever its own model is."""
        pack = make_pack("K-005", 20)
        single = make_stock("K-006", 5, "XLR-Kabel 1,5 m einzeln")
        MaterialItem.objects.filter(material_model__default_product=single).update(product_override=pack)
        self.assertEqual(stock_of_products([pack.pk])[pack.pk].plannable, 2)  # 25 items
        MaterialItem.objects.filter(material_model__default_product=pack).update(product_override=single)
        self.assertEqual(stock_of_products([pack.pk])[pack.pk].plannable, 0)  # only the 5 of the single model
        self.assertEqual(stock_of_products([single.pk])[single.pk].plannable, 20)  # one piece per product

    def test_bulk_rows_count_their_quantity_in_pieces(self) -> None:
        """MAT-005: 250 cable ties in one row are 25 packs of ten."""
        ties = make_product(
            "V-001", "Kabelbinder 10er", kind="sale", billing_mode="flat", price=None, sale_price="1.00"
        )
        Product.objects.filter(pk=ties.pk).update(pieces_per_product=10)
        make_items(make_model("Kabelbinder 200 mm", ties, bulk=True), 1, quantity=250)
        self.assertEqual(stock_of_products([ties.pk])[ties.pk].plannable, 25)

    def test_stock_of_all_products_needs_no_query_per_product(self) -> None:
        """NFA-014: the factor comes with the existing queries – still two, one pack or many."""
        for number in range(5):
            make_pack(f"K-{100 + number}", 30, 10 if number % 2 else 1)
        with self.assertNumQueries(2):
            stock_of_products(None)
        ids = [product.pk for product in Product.objects.all()]
        with CaptureQueriesContext(connection) as queries:
            stock_of_products(ids)
        self.assertEqual(len(queries), 2)


class ProductRulesTests(RentalarsTestCase):
    """The rules of ``Product.pieces_per_product``."""

    def test_at_least_one(self) -> None:
        product = make_product("K-005")
        product.pieces_per_product = 0
        with self.assertRaises(ValidationError) as caught:
            product.full_clean()
        self.assertIn("pieces_per_product", caught.exception.message_dict)

    def test_only_rental_and_sale_products_consist_of_several_pieces(self) -> None:
        product = make_product("K-005")
        for kind, price in (("kit", "10.00"), ("incidental", "10.00")):
            candidate = make_product(f"K-{7 if kind == 'kit' else 8}00", kind=kind, price=price)
            candidate.pieces_per_product = 5
            with self.assertRaises(ValidationError) as caught:
                candidate.full_clean()
            self.assertIn("pieces_per_product", caught.exception.message_dict, kind)
        product.pieces_per_product = 10
        product.full_clean()

    def test_not_changeable_while_items_are_chosen_or_out(self) -> None:
        pack = make_pack("K-005", 20)
        project = make_project()
        line = add_line(project, pack, 1).line
        packlist = services.get_packlist(project)
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CANCELLED)
        pack.pieces_per_product = 5
        pack.full_clean()  # planned in a cancelled project, nothing chosen yet: a plain setting
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CONFIRMED)
        services.choose_items(packlist, line.pk, pack.pk, [item.pk for item in MaterialItem.objects.all()[:3]])
        pack.refresh_from_db()
        pack.pieces_per_product = 5
        with self.assertRaises(ValidationError) as caught:
            pack.full_clean()
        self.assertIn("pieces_per_product", caught.exception.message_dict)
        services.choose_items(packlist, line.pk, pack.pk, [])
        pack.pieces_per_product = 5
        with self.assertRaises(ValidationError):
            pack.full_clean()  # nothing chosen, but the confirmed project still plans "1 ×"
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CLOSED)
        pack.full_clean()

    def test_not_changeable_while_running_projects_plan_it(self) -> None:
        """(pieces per product; PRD-052) "3 ×" in a project that is not finished means 3 packs of the old size."""
        pack = make_pack("K-005", 20)
        running = make_project("Läuft")
        add_line(running, pack, 3)
        add_line(make_project("Läuft auch"), pack, 1)
        done = make_project("Fertig", status=ProjectStatus.RETURNED)
        add_line(done, pack, 2)
        pack.pieces_per_product = 5
        with self.assertRaises(ValidationError) as caught:
            pack.full_clean()
        message = " ".join(caught.exception.message_dict["pieces_per_product"])
        self.assertIn("2 Positionen", message)
        Project.objects.filter(pk=running.pk).update(status=ProjectStatus.CANCELLED)
        with self.assertRaises(ValidationError) as caught:
            pack.full_clean()
        self.assertIn("1 Position ", " ".join(caught.exception.message_dict["pieces_per_product"]))
        Project.objects.update(status=ProjectStatus.CLOSED)
        pack.full_clean()
        Project.objects.update(status=ProjectStatus.CONFIRMED)
        pack.refresh_from_db()  # the stored number again: leaving it as it is is never refused
        pack.full_clean()


class AvailabilityOfPiecesTests(RentalarsTestCase):
    """Project lines reserve products; the stock is counted in products (VFG-002)."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack("K-005", 100)  # ten packs

    def test_one_line_reserves_whole_products(self) -> None:
        self.assertEqual(free(self.pack), 10)
        add_line(make_project("Stadtfest"), self.pack, 3)  # 30 cables
        self.assertEqual(free(self.pack), 7)

    def test_the_verdict_of_a_line_counts_products(self) -> None:
        add_line(make_project("Stadtfest"), self.pack, 3)
        ok = add_line(make_project("Dorffest"), self.pack, 7).availability
        self.assertEqual(ok.status, "ok")  # all ten packs are out, none is short
        self.assertEqual(ok.shortage_total, 0)
        short = add_line(make_project("Messe"), self.pack, 2).availability
        self.assertEqual(short.status, "short")
        self.assertEqual(short.shortage_total, 2)  # 2 packs short, not 20 cables
        self.assertEqual(short.main.stock, 10)
        self.assertEqual(short.main.required, 2)

    def test_not_enough_items_for_one_more_product_is_a_shortage(self) -> None:
        """25 cables are two packs, the third is missing – not 5 cables."""
        pack = make_pack("K-006", 25)
        verdict = add_line(make_project("Stadtfest"), pack, 3).availability
        self.assertEqual(verdict.status, "short")
        self.assertEqual((verdict.main.stock, verdict.main.required, verdict.shortage_total), (2, 3, 1))

    def test_the_quantity_of_a_line_is_in_products(self) -> None:
        """One project line "3 × K-005" is 30 cables: three packs leave 7 free of 10."""
        project = make_project()
        add_line(project, self.pack, 3)
        answer = AvailabilityEngine().availability([self.pack.pk], at(10), at(12))[self.pack.pk]
        self.assertEqual((answer.stock.plannable, answer.firm, answer.free), (10, 3, 7))
        self.assertEqual(sum(demand.quantity for demand in answer.occupiers), 3)

    def test_a_kit_with_a_pack_counts_products(self) -> None:
        """VFG-008: a kit of 2 packs and a speaker – 100 cables are 10 packs, so 5 kits."""
        speaker = make_stock("T-010", 20)
        kit = make_product("T-100", kind="kit", price="30.00")
        set_kit_components(kit, [(self.pack, 2), (speaker, 1)])
        answer = AvailabilityEngine().availability([kit.pk], at(10), at(12))[kit.pk]
        self.assertEqual(answer.stock.plannable, 5)
        add_line(make_project("Stadtfest"), kit, 2)
        self.assertEqual(free(self.pack), 6)
        self.assertEqual(AvailabilityEngine().availability([kit.pk], at(10), at(12))[kit.pk].free, 3)

    def test_blocked_items_take_whole_products_out_of_the_plan_only_when_needed(self) -> None:
        """MAT-024: three cables in repair at once take one pack, not three."""
        items = list(MaterialItem.objects.order_by("inventory_number")[:3])
        for item in items:
            ItemBlock.objects.create(item=item, start=at(9), end=at(13), reason="Stecker gebrochen")
        self.assertEqual(free(self.pack), 9)
        # An eleventh cable blocked as well: 4 blocked items, still one pack - the fifth..tenth do not add a second
        for item in MaterialItem.objects.order_by("inventory_number")[3:10]:
            ItemBlock.objects.create(item=item, start=at(9), end=at(13), reason="Stecker gebrochen")
        self.assertEqual(free(self.pack), 9)  # 10 blocked: exactly one pack
        ItemBlock.objects.create(
            item=MaterialItem.objects.order_by("inventory_number")[10], start=at(9), end=at(13), reason="Stecker"
        )
        self.assertEqual(free(self.pack), 8)  # 11 blocked: two packs
        self.assertEqual(free(self.pack, 14, 15), 10)  # after the blocks everything is free again

    def test_a_blocked_spare_item_takes_no_pack(self) -> None:
        """(pieces per product; PRD-052) 105 cables are ten packs, one blocked cable leaves ten; 100 leave nine."""
        spare = make_pack("K-007", 105)
        for item in MaterialItem.objects.filter(material_model__default_product=spare).order_by("inventory_number")[:1]:
            ItemBlock.objects.create(item=item, start=at(9), end=at(13), reason="Stecker gebrochen")
        self.assertEqual(free(spare), 10)
        for item in MaterialItem.objects.filter(material_model__default_product=spare).order_by("inventory_number")[
            1:5
        ]:
            ItemBlock.objects.create(item=item, start=at(9), end=at(13), reason="Stecker gebrochen")
        self.assertEqual(free(spare), 10)  # five blocked of five spare ones
        ItemBlock.objects.create(
            item=MaterialItem.objects.filter(material_model__default_product=spare).order_by("inventory_number")[5],
            start=at(9),
            end=at(13),
            reason="Stecker gebrochen",
        )
        self.assertEqual(free(spare), 9)  # six blocked: 99 fit items are nine packs
        self.assertEqual(free(self.pack), 10)

    def test_a_block_of_a_spare_item_in_one_period_only(self) -> None:
        spare = make_pack("K-007", 105)
        first, *others = MaterialItem.objects.filter(material_model__default_product=spare).order_by(
            "inventory_number"
        )[:7]
        for item in others[:5]:
            ItemBlock.objects.create(item=item, start=at(10), end=at(11), reason="Defekt")  # 5 at once: spare
        ItemBlock.objects.create(item=first, start=at(10), end=at(11), reason="Defekt")  # the sixth: a pack
        self.assertEqual(free(spare, 10, 11), 9)
        self.assertEqual(free(spare, 11, 12), 10)

    def test_the_timeline_of_an_item_leaves_out_its_own_joined_block(self) -> None:
        """(pieces per product; PRD-052) the blocks of 0001 and 0002 are one demand "0001, 0002"."""
        import datetime

        from rentalars.schedule.timelines import item_timeline

        first, second = MaterialItem.objects.order_by("inventory_number")[:2]
        for item in (first, second):
            ItemBlock.objects.create(item=item, start=at(10), end=at(12), reason="Defekt")
        # 100 cables, two blocked: no spare item, one pack is lost.
        days = [datetime.date(2027, 3, 8) + datetime.timedelta(days=offset) for offset in range(10)]
        for item, other in ((first, second), (second, first)):
            labels = [row.label for row in item_timeline(item, days, set()).rows]
            self.assertFalse(
                [label for label in labels if f"{item.display_id}," in label or f", {item.display_id}" in label],
                labels,
            )
            self.assertNotIn(f"{other.display_id} blocked", labels)

    def test_blocks_at_different_times_do_not_add_up(self) -> None:
        """Two cables blocked one after the other are one pack at a time."""
        first, second = MaterialItem.objects.order_by("inventory_number")[:2]
        ItemBlock.objects.create(item=first, start=at(10), end=at(11), reason="Defekt")
        ItemBlock.objects.create(item=second, start=at(11), end=at(12), reason="Defekt")
        self.assertEqual(free(self.pack), 9)
        demands = AvailabilityEngine().collect_demands({self.pack.pk}, at(9), at(13))[self.pack.pk]
        self.assertEqual([demand.quantity for demand in demands if demand.via == "blocked"], [1, 1])

    def test_blocks_of_a_product_of_one_piece_are_unchanged(self) -> None:
        cable = make_stock("K-006", 5)
        for item in MaterialItem.objects.filter(material_model__default_product=cable)[:2]:
            ItemBlock.objects.create(item=item, start=at(9), end=at(13), reason="Defekt")
        self.assertEqual(free(cable), 3)

    def test_optional_and_firm_are_told_apart_in_products(self) -> None:
        add_line(make_project("Option", status="option"), self.pack, 4)
        add_line(make_project("Fest"), self.pack, 3)
        answer = AvailabilityEngine().availability([self.pack.pk], at(10), at(12))[self.pack.pk]
        self.assertEqual((answer.firm, answer.optional, answer.free, answer.free_after_optional), (3, 4, 7, 3))

    def test_demand_objects_are_in_products(self) -> None:
        add_line(make_project("Stadtfest"), self.pack, 3)
        demands = AvailabilityEngine().collect_demands({self.pack.pk}, at(9), at(13))[self.pack.pk]
        self.assertTrue(all(isinstance(demand, Demand) and demand.firmness == Firmness.FIRM for demand in demands))
        self.assertEqual([demand.quantity for demand in demands], [3])


class ConsistencyOfPiecesTests(RentalarsTestCase):
    """The quick test of one line, the overview of shortages and the exact calculation agree (PRJ-057, NFA-012)."""

    def test_quick_verdict_equals_the_full_one_with_packs_kits_and_containers(self) -> None:
        from rentalars.material.models import ConnectionType
        from rentalars.material.services import install_item

        pack = make_pack("K-005", 100)
        speaker = make_stock("T-010", 20)
        kit = make_product("T-100", kind="kit", billing_mode="daily_kit")
        set_kit_components(kit, [(speaker, 1), (pack, 2)])
        case_product = make_product("S-600")
        case = make_items(make_model("Case", case_product), 1)[0]
        for item in MaterialItem.objects.filter(material_model__default_product=pack).order_by("inventory_number")[:12]:
            install_item(item, case, connection_type=ConnectionType.LOOSE)
        add_line(make_project("Anderes", start=at(11), end=at(13)), pack, 2)
        project = make_project("Groß", start=at(10), end=at(12))
        add_line(project, kit, 3)
        add_line(project, pack, 4)
        add_line(project, case_product, 1)
        add_line(project, pack, 3)  # more than there are
        lines = list(project.material_lines.select_related("product"))
        full = AvailabilityEngine().project_availability(project, lines)
        self.assertTrue(any(verdict.shortage_total for verdict in full.values()))
        for line in lines:
            self.assertEqual(AvailabilityEngine().line_availability(line), full[line.pk], line.title)

    def test_the_overview_of_shortages_counts_products(self) -> None:
        from rentalars.availability.services import open_shortages

        pack = make_pack("K-005", 25)  # two packs
        add_line(make_project("Stadtfest"), pack, 3)
        found = [(entry.product.pk, entry.quantity) for entry in open_shortages()]
        self.assertEqual(found, [(pack.pk, 1)])

    def test_loose_contents_of_a_container_are_whole_products_rounded_up(self) -> None:
        """VFG-016: twelve cables lie in the case; planning the case occupies two packs of ten (on the safe side)."""
        from rentalars.material.models import ConnectionType
        from rentalars.material.services import install_item

        pack = make_pack("K-005", 100)
        case_product = make_product("S-600")
        case = make_items(make_model("Case", case_product), 1)[0]
        for item in MaterialItem.objects.filter(material_model__default_product=pack).order_by("inventory_number")[:12]:
            install_item(item, case, connection_type=ConnectionType.LOOSE)
        self.assertEqual(free(pack), 10)
        add_line(make_project("Stadtfest"), case_product, 1)
        self.assertEqual(free(pack), 8)

    def test_a_container_of_several_items_occupies_the_contents_of_all_its_items(self) -> None:
        """(pieces per product; PRD-052) S-600 is two cases, three cables lie loose in each: "1 × S-600" is 6."""
        from rentalars.material.models import ConnectionType
        from rentalars.material.services import install_item

        cable = make_stock("K-006", 20)
        case_product = make_product("S-600", pieces_per_product=2)
        cases = make_items(make_model("Case", case_product), 2)
        cables = list(MaterialItem.objects.filter(material_model__default_product=cable).order_by("inventory_number"))
        for index, item in enumerate(cables[:6]):
            install_item(item, cases[index // 3], connection_type=ConnectionType.LOOSE)
        self.assertEqual(free(cable), 20)
        add_line(make_project("Stadtfest"), case_product, 1)
        self.assertEqual(free(cable), 14)  # six cables, not three

    def test_a_container_of_one_piece_is_unchanged(self) -> None:
        from rentalars.material.models import ConnectionType
        from rentalars.material.services import install_item

        cable = make_stock("K-006", 20)
        case_product = make_product("S-600")
        cases = make_items(make_model("Case", case_product), 2)
        cables = list(MaterialItem.objects.filter(material_model__default_product=cable).order_by("inventory_number"))
        for index, item in enumerate(cables[:6]):
            install_item(item, cases[index // 3], connection_type=ConnectionType.LOOSE)
        add_line(make_project("Stadtfest"), case_product, 1)
        self.assertEqual(free(cable), 17)  # the fuller case, three cables


class WishesOfPiecesTests(RentalarsTestCase):
    """PRJ-064: a wished model is asked for in items – each product of the line wants all its pieces of it."""

    def test_a_wish_for_a_model_counts_the_items_behind_the_products(self) -> None:
        from rentalars.projects.wishes import load_wishes

        pack = make_pack("K-005", 15)
        model = MaterialItem.objects.first().material_model
        project = make_project()
        line = add_line(project, pack, 2, preferred_model=model).line  # 2 products = 20 cables, 15 there
        wish = load_wishes(project, [line])[line.pk]
        self.assertEqual(len(wish.warnings), 1)
        self.assertIn("20", wish.warnings[0])
        fine = add_line(make_project("Anderes", start=at(20), end=at(22)), pack, 1, preferred_model=model).line
        self.assertEqual(load_wishes(fine.project, [fine])[fine.pk].warnings, [])

    def test_each_line_counts_with_the_pieces_of_its_own_product(self) -> None:
        """(pieces per product; PRD-052) the model belongs to a 10-pack, but this line plans single cables."""
        from rentalars.projects.wishes import load_wishes

        pack = make_pack("K-005", 15)
        model = MaterialItem.objects.first().material_model
        single = make_product("K-050", "XLR-Kabel einzeln")  # one piece per product, items of the same model
        MaterialItem.objects.filter(pk__in=[item.pk for item in MaterialItem.objects.all()[:3]]).update(
            product_override=single
        )  # three cables are sold singly: the model belongs to both products
        project = make_project()
        line = add_line(project, single, 12, preferred_model=model).line  # 12 cables, 15 there
        self.assertEqual(load_wishes(project, [line])[line.pk].warnings, [])
        # The 10-pack of another project at the same time wants ten items; with the 12 above that is more than 15.
        add_line(make_project("Anderes"), pack, 1, preferred_model=model)
        self.assertEqual(len(load_wishes(project, [line])[line.pk].warnings), 1)
        # The other way round: a line of the 10-pack still counts ten items for each piece.
        packed = add_line(make_project("Drittes", start=at(20), end=at(22)), pack, 1, preferred_model=model).line
        self.assertEqual(load_wishes(packed.project, [packed])[packed.pk].warnings, [])


class PackingOfPiecesTests(RentalarsTestCase):
    """The packlist asks for 10 items for each piece; a piece is complete when all its items are chosen."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack("K-005", 25)
        self.project = make_project()
        self.line = add_line(self.project, self.pack, 2).line
        self.packlist = services.get_packlist(self.project)

    def row(self) -> services.PackRow:
        self.packlist.refresh_from_db()
        return next(row for row in services.build_overview(self.packlist).rows if row.product.pk == self.pack.pk)

    def items(self, count: int, first: int = 0) -> list[int]:
        return [item.pk for item in MaterialItem.objects.order_by("inventory_number")[first : first + count]]

    def test_the_row_counts_products_and_knows_its_items(self) -> None:
        row = self.row()
        self.assertEqual((row.required, row.pieces_per_unit, row.pieces_required), (2, 10, 20))
        self.assertTrue(row.consists_of_pieces)
        self.assertEqual((row.pieces_chosen, row.units_chosen, row.pieces_missing_for_next), (0, 0, 0))

    def test_choose_up_to_ten_items_for_each_piece(self) -> None:
        services.choose_items(self.packlist, self.line.pk, self.pack.pk, self.items(20))
        self.assertEqual(self.row().pieces_chosen, 20)
        with self.assertRaises(ValidationError):
            services.choose_items(self.packlist, self.line.pk, self.pack.pk, self.items(21))

    def test_a_piece_with_fewer_items_is_not_complete(self) -> None:
        services.choose_items(self.packlist, self.line.pk, self.pack.pk, self.items(15))
        row = self.row()
        self.assertEqual((row.pieces_chosen, row.units_chosen, row.pieces_missing_for_next), (15, 1, 5))
        services.choose_items(self.packlist, self.line.pk, self.pack.pk, self.items(20))
        row = self.row()
        self.assertEqual((row.units_chosen, row.pieces_missing_for_next), (2, 0))

    def test_issue_one_piece_issues_its_ten_chosen_items(self) -> None:
        services.choose_items(self.packlist, self.line.pk, self.pack.pk, self.items(20))
        services.set_packed(self.packlist, self.line.pk, self.pack.pk, D(1))
        services.issue(self.packlist, only_packed=True)
        issued = Allocation.objects.filter(entry__packlist=self.packlist, issued_at__isnull=False)
        self.assertEqual(issued.count(), 10)
        self.assertEqual(MaterialItem.objects.filter(status=ItemStatus.IN_USE).count(), 10)
        self.assertEqual(Allocation.objects.filter(entry__packlist=self.packlist, issued_at__isnull=True).count(), 10)
        self.packlist.refresh_from_db()
        self.assertEqual(self.packlist.status, PacklistStatus.PARTLY_ISSUED)

    def test_nothing_is_allocated_where_it_is_unclear_which_items_go(self) -> None:
        """PCK-020: 25 cables, two packs out – which twenty is not known, nothing is blocked."""
        services.issue(self.packlist)
        self.assertFalse(Allocation.objects.exists())
        self.packlist.refresh_from_db()
        self.assertEqual(self.packlist.status, PacklistStatus.ISSUED)

    def test_the_whole_stock_going_out_is_allocated(self) -> None:
        """PCK-021: 20 cables and two packs – all twenty are beyond doubt."""
        pack = make_pack("K-006", 20)
        project = make_project("Dorffest", start=at(20), end=at(22))
        add_line(project, pack, 2)
        packlist = services.get_packlist(project)
        services.issue(packlist)
        self.assertEqual(Allocation.objects.filter(entry__packlist=packlist).count(), 20)

    def test_exactly_one_piece_of_items_left_is_beyond_doubt(self) -> None:
        pack = make_pack("K-006", 10)
        project = make_project("Dorffest", start=at(20), end=at(22))
        add_line(project, pack, 1)
        packlist = services.get_packlist(project)
        services.issue(packlist)
        self.assertEqual(Allocation.objects.filter(entry__packlist=packlist).count(), 10)

    def test_return_books_all_items_back(self) -> None:
        pack = make_pack("K-006", 20)
        project = make_project("Dorffest", start=at(20), end=at(22))
        add_line(project, pack, 2)
        packlist = services.get_packlist(project)
        services.issue(packlist)
        services.return_all(packlist)
        services.take_back(packlist)
        self.assertEqual(MaterialItem.objects.filter(status=ItemStatus.IN_USE).count(), 0)
        self.assertEqual(Allocation.objects.filter(returned_at__isnull=True).count(), 0)

    def test_weight_and_volume_are_those_of_all_items(self) -> None:
        """PCK-006: the model's weight is that of one cable."""
        model = MaterialItem.objects.first().material_model
        model.weight_kg = D("0.15")
        model.save()
        self.assertEqual(self.row().weight_kg, D("0.15") * 20)

    def test_the_row_of_a_product_of_one_piece_is_as_before(self) -> None:
        cable = make_stock("K-007", 9)
        line = add_line(make_project("Messe", start=at(20), end=at(22)), cable, 3).line
        packlist = services.get_packlist(line.project)
        row = next(row for row in services.build_overview(packlist).rows if row.product.pk == cable.pk)
        self.assertEqual((row.pieces_per_unit, row.pieces_required, row.consists_of_pieces), (1, 3, False))
        services.choose_items(
            packlist,
            line.pk,
            cable.pk,
            [item.pk for item in MaterialItem.objects.filter(material_model__default_product=cable)[:3]],
        )
        with self.assertRaises(ValidationError):
            services.choose_items(
                packlist,
                line.pk,
                cable.pk,
                [item.pk for item in MaterialItem.objects.filter(material_model__default_product=cable)[:4]],
            )

    def test_sold_packs_leave_the_stock_as_items(self) -> None:
        """PRD-013: two packs of ten ties sold – the whole stock of 20 goes, the line counts two."""
        ties = make_product(
            "V-001", "Kabelbinder 10er", kind="sale", billing_mode="flat", price=None, sale_price="1.00"
        )
        Product.objects.filter(pk=ties.pk).update(pieces_per_product=10)
        items = make_items(make_model("Kabelbinder 200 mm", ties), 20)
        project = make_project("Verkauf", start=at(20), end=at(22))
        line = add_line(project, ties, 2, is_sale=True).line
        services.issue(services.get_packlist(project))
        self.assertEqual(
            MaterialItem.objects.filter(pk__in=[item.pk for item in items], status=ItemStatus.SOLD).count(), 20
        )
        line.refresh_from_db()
        self.assertEqual(line.stock_removed_quantity, 2)

    def test_sold_packs_of_bulk_material(self) -> None:
        ties = make_product(
            "V-002", "Kabelbinder 100er", kind="sale", billing_mode="flat", price=None, sale_price="5.00"
        )
        Product.objects.filter(pk=ties.pk).update(pieces_per_product=100)
        (row,) = make_items(make_model("Kabelbinder 300 mm", ties, bulk=True), 1, quantity=1000)
        project = make_project("Verkauf", start=at(20), end=at(22))
        line = add_line(project, ties, 3, is_sale=True).line
        services.issue(services.get_packlist(project))
        row.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual((row.quantity, line.stock_removed_quantity), (700, 3))
        self.assertEqual(stock_of_products([ties.pk])[ties.pk].plannable, 7)


class RevenueOfPiecesTests(RentalarsTestCase):
    """MAT-053: a cable earns its share of the line – the amount divided by quantity × pieces."""

    def test_each_item_earns_a_share_per_piece(self) -> None:
        pack = make_pack("K-005", 40)
        project = make_project("Stadtfest")
        line = add_line(project, pack, 3).line
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CLOSED)
        project.refresh_from_db()
        net = _prices_of([project])[project.pk][0].net_total
        # The packlist chose 30 of the 40 cables.
        packlist = services.get_packlist(project)
        chosen = [item.pk for item in MaterialItem.objects.order_by("inventory_number")[:30]]
        entry_row = services.find_row(services.build_overview(packlist), line.pk, pack.pk)
        self.assertEqual(entry_row.pieces_required, 30)
        entry = services._entry_for(packlist, entry_row)
        for item_id in chosen:
            Allocation.objects.create(entry=entry, item_id=item_id)
        first = MaterialItem.objects.get(pk=chosen[0])
        revenue = profitability.item_revenue(first)
        self.assertEqual(revenue.direct, net / 30)
        self.assertEqual(profitability.item_revenue(MaterialItem.objects.get(pk=chosen[-1])).direct, net / 30)

    def test_pieces_nobody_chose_are_shared_over_the_items(self) -> None:
        pack = make_pack("K-005", 20)
        project = make_project("Stadtfest")
        add_line(project, pack, 1)
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CLOSED)
        project.refresh_from_db()
        net = _prices_of([project])[project.pk][0].net_total
        total = sum(profitability.item_revenue(item).estimated for item in MaterialItem.objects.all())
        # One pack = 10 cables of the 20 earned the net total between them: each of the 20 gets a twentieth of it ×
        # 10/20 of ... the share of a piece (net/10) spread over 20 items.
        self.assertEqual(round(total, 2), round(net, 2))
        self.assertEqual(
            round(profitability.item_revenue(MaterialItem.objects.first()).estimated, 2), round(net / 20, 2)
        )


class PagesOfPiecesTests(UiTestCase):
    """What a person sees: the product page, the model page, the form, the list, the packlist."""

    def setUp(self) -> None:
        super().setUp()
        self.pack = make_pack("K-005", 105)
        self.model = MaterialItem.objects.first().material_model

    def test_the_product_page_tells_what_it_consists_of(self) -> None:
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[self.pack.pk])))
        self.assertIn("Besteht aus", page)
        self.assertIn("10 ×", page)
        self.assertIn(self.model.name, page)
        self.assertIn("105 Exemplare exist" if False else "Es gibt 105 Exemplare, 105 davon sind planbar", page)
        self.assertIn("5 übrige Exemplare des Materials ergeben kein ganzes Produkt", page)

    def test_a_product_of_one_piece_says_nothing_of_pieces(self) -> None:
        cable = make_stock("K-006", 3)
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[cable.pk])))
        self.assertNotIn("Besteht aus", page)

    def test_the_model_page_names_the_product_and_its_pieces(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assertIn("Ein Exemplar des Produkts K-005 besteht aus 10 Stück dieses Modells.", page)
        form = self.assert_ok(self.client.get(reverse("material:model_edit", args=[self.model.pk])))
        self.assertIn("Ein Exemplar des Produkts K-005 besteht aus 10 Stück dieses Modells.", form)

    def test_the_item_page_says_it_is_one_of_ten(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[MaterialItem.objects.first().pk])))
        self.assertIn("Eines von 10 Exemplaren, aus denen ein Exemplar dieses Produkts besteht.", page)

    def test_the_product_list_shows_the_stock_in_products_and_items(self) -> None:
        page = self.assert_ok(self.client.get(reverse("products:list")))
        self.assertIn("10 Stk", page)
        self.assertIn("105 Exemplare", page)

    def test_the_form_shows_the_refusal_on_the_field(self) -> None:
        add_line(make_project("Läuft"), self.pack, 1)
        edit = reverse("products:edit", args=[self.pack.pk])
        response = self.client.post(edit, form_data(self.client.get(edit), pieces_per_product="5"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 Position eines noch nicht abgeschlossenen Projekts")
        self.pack.refresh_from_db()
        self.assertEqual(self.pack.pieces_per_product, 10)

    def test_the_form_sets_the_pieces(self) -> None:
        edit = reverse("products:edit", args=[self.pack.pk])
        response = self.client.post(edit, form_data(self.client.get(edit), pieces_per_product="5"))
        self.assertEqual(response.status_code, 302)
        self.pack.refresh_from_db()
        self.assertEqual(self.pack.pieces_per_product, 5)
        bad = self.client.post(edit, form_data(self.client.get(edit), pieces_per_product="0"))
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, "Stück je Produkt")

    def test_the_change_is_in_the_history_of_the_product(self) -> None:
        edit = reverse("products:edit", args=[self.pack.pk])
        self.client.post(edit, form_data(self.client.get(edit), pieces_per_product="5"))
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[self.pack.pk])))
        self.assertIn("Stück je Produkt", page)

    def test_a_copy_keeps_the_pieces(self) -> None:
        from rentalars.products import services as product_services

        values = product_services.duplicate_values(self.pack, ALL_RIGHTS)
        self.assertEqual(values["pieces_per_product"], 10)

    def test_the_packlist_shows_items_and_progress(self) -> None:
        project = make_project()
        line = add_line(project, self.pack, 2).line
        packlist = services.get_packlist(project)
        services.choose_items(
            packlist,
            line.pk,
            self.pack.pk,
            [item.pk for item in MaterialItem.objects.order_by("inventory_number")[:15]],
        )
        page = self.assert_ok(self.client.get(reverse("packing:packlist", args=[project.pk])))
        self.assertIn("je 10 Stück", page)
        self.assertIn("15 von 20 Exemplaren gewählt", page)
        self.assertIn("1 von 2 komplett, beim nächsten sind 5 von 10 Exemplaren gewählt", page)
        dialog = self.assert_ok(
            self.client.get(reverse("packing:items", args=[project.pk]), {"line": line.pk, "product": self.pack.pk})
        )
        self.assertIn("2 × 10 Exemplare, also 20 Exemplare", dialog)


class ApiOfPiecesTests(ApiTestCase):
    """The product has the field, the stock and the availability tell the pieces, packlists name the items."""

    def test_the_field_defaults_to_one_and_is_changeable(self) -> None:
        cable = make_stock("K-006", 3)
        self.assertEqual(self.admin.get(f"{API}/products/{cable.pk}").json()["pieces_per_product"], 1)
        response = self.admin.patch(f"{API}/products/{cable.pk}", {"pieces_per_product": 3}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        body = self.admin.get(f"{API}/products/{cable.pk}").json()
        self.assertEqual(body["pieces_per_product"], 3)
        self.assertEqual(body["stock"], {"total": 1, "operational": 1, "plannable": 1})
        self.assertEqual(body["stock_pieces"], {"total": 3, "operational": 3, "plannable": 3})

    def test_created_with_pieces_and_refused_for_a_kit(self) -> None:
        category_id = make_product("K-005").category_id
        data = {
            "article_number": "K-050",
            "category": category_id,
            "name": "XLR 5er",
            "unit": make_product("K-006").unit_id,
            "tax_rate": make_product("K-007").tax_rate_id,
            "kind": "rental",
            "price": "10.00",
            "pieces_per_product": 5,
        }
        created = self.admin.post(f"{API}/products", data, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["pieces_per_product"], 5)
        refused = self.admin.post(
            f"{API}/products",
            {**data, "article_number": "K-051", "kind": "kit", "pieces_per_product": 5},
            format="json",
        )
        self.assert_error(refused, 400, "validation_error", "pieces_per_product")

    def test_availability_names_the_pieces(self) -> None:
        pack = make_pack("K-005", 100)
        add_line(make_project("Stadtfest"), pack, 3)
        answer = self.admin.get(
            f"{API}/products/{pack.pk}/availability",
            {"from": "2027-03-10T00:00:00+01:00", "to": "2027-03-12T00:00:00+01:00"},
        ).json()
        self.assertEqual(
            (answer["stock"], answer["firm"], answer["free"], answer["pieces_per_product"]), (10, 3, 7, 10)
        )

    def test_the_packlist_names_the_items(self) -> None:
        pack = make_pack("K-005", 25)
        project = make_project("Stadtfest")
        line = add_line(project, pack, 2).line
        packlist = services.get_packlist(project)
        chosen = [item.pk for item in MaterialItem.objects.order_by("inventory_number")[:12]]
        response = self.admin.put(
            f"{API}/projects/{project.pk}/packlists/{packlist.pk}/items",
            {"line": line.pk, "product": pack.pk, "items": chosen},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = [row for section in response.json()["sections"] for row in section["rows"]]
        row = next(row for row in rows if row["product"] == pack.pk)
        self.assertEqual(
            (row["pieces_per_unit"], row["pieces_required"], row["pieces_chosen"], row["units_chosen"]), (10, 20, 12, 1)
        )


class ImportExportOfPiecesTests(RentalarsTestCase):
    """The product list exported "im Importformat" has the column and reads it back (IMP-005, IMP-011)."""

    def text(self) -> str:
        return import_exports.text_of(import_exports.get("products"), Rights.everything())

    def read(self, text: str) -> Table:
        return read_table(io.BytesIO(text.encode("utf-8")), "export.csv")

    def test_the_export_has_the_column_and_comes_back_unchanged(self) -> None:
        make_pack("K-005", 5)
        make_stock("K-006", 1)
        text = self.text()
        table = self.read(text)
        self.assertIn("Stück je Produkt", table.headers)
        column = table.headers.index("Stück je Produkt")
        self.assertEqual(
            {row[0]: row[column] for row in table.rows if row[0] in ("K-005", "K-006")}, {"K-005": "10", "K-006": "1"}
        )
        kind = imports.get("products")
        mapping = resolve_mapping(table.headers, {}, kind.fields)
        report = imports.run(kind, table, mapping, dry_run=True, user=make_user("ida", superuser=True)).as_dict()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(
            report["row_counts"]["changed"] + report["row_counts"]["new"] + report["row_counts"]["error"], 0
        )

    def test_the_import_sets_and_checks_the_pieces(self) -> None:
        make_product("K-005")
        kind = imports.get("products")
        for value, ok in (("10", True), ("0", False), ("zehn", False), ("", True)):
            table = Table(headers=["Art.-Nr.", "Name", "Stück pro Produkt"], rows=[["K-005", "Produkt K-005", value]])
            report = kind.run(table, resolve_mapping(table.headers, {}, kind.fields), dry_run=False, rights=ALL_RIGHTS)
            self.assertEqual(report.ok, ok, (value, report.errors))
        self.assertEqual(Product.objects.get(article_number="K-005").pieces_per_product, 10)

    def test_a_kit_cannot_get_pieces_by_import(self) -> None:
        make_product("T-100", kind="kit", price="30.00")
        kind = imports.get("products")
        table = Table(headers=["Art.-Nr.", "Name", "Stück je Produkt"], rows=[["T-100", "Produkt T-100", "5"]])
        report = kind.run(table, resolve_mapping(table.headers, {}, kind.fields), dry_run=False, rights=ALL_RIGHTS)
        self.assertFalse(report.ok)


class PerformanceOfPiecesTests(RentalarsTestCase):
    """Products of one piece are not slower: no query is added per row, and the counts stay as before."""

    def test_the_product_list_and_the_availability_need_the_same_queries_with_or_without_pieces(self) -> None:
        plain = [make_stock(f"K-{200 + number}", 4) for number in range(6)]
        with CaptureQueriesContext(connection) as before:
            stock_of_products([product.pk for product in plain])
            AvailabilityEngine().availability([product.pk for product in plain], at(10), at(12))
        packs = [make_pack(f"K-{300 + number}", 40) for number in range(6)]
        with CaptureQueriesContext(connection) as after:
            stock_of_products([product.pk for product in packs])
            AvailabilityEngine().availability([product.pk for product in packs], at(10), at(12))
        self.assertEqual(len(after), len(before))
        with CaptureQueriesContext(connection) as one:
            stock_of_products([plain[0].pk])
        self.assertEqual(len(one), 2)


class ModelApiOfPiecesTests(ApiTestCase):
    """The material model tells the pieces of its product (read-only; the product holds the number)."""

    def test_the_model_names_the_pieces_of_its_product(self) -> None:
        make_pack("K-005", 3)
        loose = make_model("Ohne Produkt")
        model = MaterialItem.objects.first().material_model
        self.assertEqual(self.admin.get(f"{API}/material-models/{model.pk}").json()["pieces_per_product"], 10)
        self.assertEqual(self.admin.get(f"{API}/material-models/{loose.pk}").json()["pieces_per_product"], 1)
        listed = self.admin.get(f"{API}/material-models").json()["results"]
        self.assertEqual({row["name"]: row["pieces_per_product"] for row in listed}[model.name], 10)
