# SPDX-License-Identifier: GPL-3.0-or-later
"""Requirements from use around the material.

* IMP-014: the import is told whether the prices of the file are net or gross;
  gross prices are stored net.
* IMP-015: a cell ``#0802`` is the ID 0802.
* IMP-016, MAT-054: a price cell ``#0851`` – bought as a set, the price is
  noted at 0851; the item is linked to it and has no price of its own.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from rentalars.accounts.models import Role
from rentalars.accounts.rights import rights_of
from rentalars.core import imports
from rentalars.masterdata.models import TaxRate
from rentalars.material import services
from rentalars.material.forms import MaterialItemForm
from rentalars.material.importer import import_material, read_table, resolve_mapping, run_import
from rentalars.material.models import MaterialItem
from rentalars.material.numbering import parse_inventory_number
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_item, make_model, make_user


def run(text: str, *, dry_run: bool = False, gross_rate: Any = None) -> Any:
    """Import CSV text (semicolon-separated) and return the report."""
    data = read_table(io.BytesIO(text.encode("utf-8")), "material.csv")
    return import_material(
        data, resolve_mapping(data.headers, {}), dry_run=dry_run, actor="system:test", gross_rate=gross_rate
    )


HEAD = "ID;Artikelname;Kategorie;Kaufpreis"


def item(number: int) -> MaterialItem:
    return MaterialItem.objects.select_related("purchase_price_in").get(inventory_number=number)


class HashIdTests(RentalarsTestCase):
    """IMP-015: ``#0802`` is the ID 0802 – in the ID column, in "Einsatz/Verbindung", wherever an ID is typed."""

    def test_hash_is_taken_off(self) -> None:
        self.assertEqual(parse_inventory_number("#0802"), 802)
        self.assertEqual(parse_inventory_number(" # 0802 "), 802)
        with self.assertRaises(ValidationError):
            parse_inventory_number("#")

    def test_ids_with_hash_are_imported(self) -> None:
        report = run("ID;Artikelname;Kategorie;Einsatz/Verbindung\n#0802;Rack;Rack;\n#0803;Blende;Rack;#0802\n")
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(item(803).installed_in.inventory_number, 802)


class GrossPriceTests(RentalarsTestCase):
    """IMP-014: gross prices are divided by 1 + rate and stored net; net prices stay as they are."""

    def test_gross_prices_are_stored_net(self) -> None:
        report = run(f"{HEAD}\n1;Kabel;Kabel;119,00\n2;Kabel;Kabel;10\n", gross_rate=Decimal("19"))
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(item(1).purchase_price, Decimal("100.00"))
        self.assertEqual(item(2).purchase_price, Decimal("8.40"))
        self.assertEqual(report.prices_gross_rate, "19")
        self.assertEqual(report.as_dict()["prices_gross_rate"], "19")

    def test_net_prices_stay(self) -> None:
        run(f"{HEAD}\n1;Kabel;Kabel;119,00\n")
        self.assertEqual(item(1).purchase_price, Decimal("119.00"))

    def test_options_of_the_import_kind(self) -> None:
        """The registered material import offers net/gross and the tax rates; unknown values take the default."""
        TaxRate.objects.get_or_create(rate=Decimal("7"), defaults={"name": "7 %"})
        kind = imports.get("material")
        options = {option.key: option for option in kind.options}
        self.assertEqual([value for value, _label in options["prices"].choice_list()], ["net", "gross"])
        self.assertIn(("7", "7 %"), [(value, str(label)) for value, label in options["price_tax_rate"].choice_list()])
        self.assertEqual(kind.clean_options({"prices": "brutto"}), {"prices": "net", "price_tax_rate": "19"})
        self.assertEqual(
            kind.clean_options({"prices": "gross", "price_tax_rate": "7"}), {"prices": "gross", "price_tax_rate": "7"}
        )

    def test_run_import_reads_the_options(self) -> None:
        data = read_table(io.BytesIO(f"{HEAD}\n1;Kabel;Kabel;107\n".encode()), "a.csv")
        report = run_import(
            data,
            resolve_mapping(data.headers, {}),
            rights=None,
            options={"prices": "gross", "price_tax_rate": "7"},
            dry_run=False,
            actor="system:test",
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(item(1).purchase_price, Decimal("100.00"))


class PurchaseSetImportTests(RentalarsTestCase):
    """IMP-016, MAT-054: ``#0851`` in the price column links the item to the one with the price."""

    def test_set_members_point_to_the_item_with_the_price(self) -> None:
        report = run(f"{HEAD}\n851;Funkstrecke;Funk;1.200,00\n852;Empfänger;Funk;#0851\n853;Sender;Funk;#851\n")
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(item(851).purchase_price, Decimal("1200.00"))
        self.assertIsNone(item(851).purchase_price_in)
        for number in (852, 853):
            self.assertEqual(item(number).purchase_price_in.inventory_number, 851)
            self.assertIsNone(item(number).purchase_price)
        self.assertEqual(report.purchase_sets, ["0851: 0852, 0853"])
        self.assertEqual([member.inventory_number for member in item(852).purchase_set], [851, 852, 853])

    def test_the_item_with_the_price_may_come_later_in_the_file(self) -> None:
        report = run(f"{HEAD}\n852;Empfänger;Funk;#0851\n851;Funkstrecke;Funk;900\n")
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(item(852).purchase_price_in.inventory_number, 851)

    def test_a_chain_ends_at_the_item_with_the_price(self) -> None:
        report = run(f"{HEAD}\n851;A;Funk;900\n852;B;Funk;#0851\n853;C;Funk;#0852\n")
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(item(853).purchase_price_in.inventory_number, 851)

    def test_an_item_already_in_rentalars_can_carry_the_price(self) -> None:
        model = make_model("Funkstrecke")
        make_item(model, 851, purchase_price=Decimal("500.00"))
        report = run(f"{HEAD}\n852;B;Funk;#0851\n")
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(item(852).purchase_price_in.inventory_number, 851)

    def test_unknown_self_and_circles_flag_the_items(self) -> None:
        """The items are taken over with the status “import error”; their note names the cell."""
        unknown = run(f"{HEAD}\n852;B;Funk;#0999\n")
        self.assertTrue(unknown.ok)
        self.assertIn("0999", " ".join(str(issue) for issue in unknown.warnings))
        self.assertEqual(item(852).status, "import_error")
        self.assertIn("#0999", item(852).note)
        itself = run(f"{HEAD}\n853;B;Funk;#0853\n")
        self.assertTrue(itself.ok)
        self.assertEqual(item(853).status, "import_error")
        circle = run(f"{HEAD}\n851;A;Funk;#0854\n854;B;Funk;#0851\n")
        self.assertTrue(circle.ok)
        self.assertEqual({item(851).status, item(854).status}, {"import_error"})
        self.assertIsNone(item(851).purchase_price_in)

    def test_a_head_without_a_price_is_a_note(self) -> None:
        report = run(f"{HEAD}\n851;A;Funk;\n852;B;Funk;#0851\n")
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(any("0851" in str(issue) for issue in report.warnings))

    def test_a_price_of_its_own_ends_the_set(self) -> None:
        run(f"{HEAD}\n851;A;Funk;900\n852;B;Funk;#0851\n")
        report = run(f"{HEAD}\n852;B;Funk;100\n")
        self.assertTrue(report.ok, report.errors)
        self.assertIsNone(item(852).purchase_price_in)
        self.assertEqual(item(852).purchase_price, Decimal("100.00"))

    def test_an_item_outside_the_file_blocks_a_set_inside_a_set(self) -> None:
        run(f"{HEAD}\n851;A;Funk;900\n852;B;Funk;#0851\n")
        report = run(f"{HEAD}\n851;A;Funk;#0850\n850;Z;Funk;100\n")
        self.assertFalse(report.ok)
        self.assertIn("0852", str(report.errors[0]))
        self.assertEqual(item(851).purchase_price, Decimal("900.00"))

    def test_the_dry_run_reports_the_sets_and_writes_nothing(self) -> None:
        report = run(f"{HEAD}\n851;A;Funk;900\n852;B;Funk;#0851\n", dry_run=True)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.purchase_sets, ["0851: 0852"])
        self.assertFalse(MaterialItem.objects.exists())


class PurchaseSetRuleTests(RentalarsTestCase):
    """MAT-054: the rules hold for the form, the API and the import alike (``MaterialItem.clean``)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Funkstrecke")
        self.head = make_item(self.model, 851, purchase_price=Decimal("900.00"))
        self.member = make_item(self.model, 852)

    def test_a_member_has_no_price_of_its_own(self) -> None:
        self.member.purchase_price_in = self.head
        self.member.purchase_price = Decimal("10")
        with self.assertRaises(ValidationError) as caught:
            self.member.full_clean()
        self.assertIn("purchase_price", caught.exception.message_dict)

    def test_no_set_inside_a_set(self) -> None:
        self.member.purchase_price_in = self.head
        self.member.full_clean()
        self.member.save()
        third = make_item(self.model, 853)
        third.purchase_price_in = self.member
        with self.assertRaises(ValidationError):
            third.full_clean()
        self.head.purchase_price_in = third
        self.head.purchase_price = None
        with self.assertRaises(ValidationError):
            self.head.full_clean()

    def test_not_in_itself(self) -> None:
        self.head.purchase_price_in = self.head
        self.head.purchase_price = None
        with self.assertRaises(ValidationError):
            self.head.full_clean()

    def test_new_items_bought_as_a_set(self) -> None:
        created = services.create_items(self.model, 3, purchase_price=Decimal("300.00"), price_for_set=True)
        self.assertEqual(created[0].purchase_price, Decimal("300.00"))
        for member in created[1:]:
            member.refresh_from_db()
            self.assertEqual(member.purchase_price_in, created[0])
            self.assertIsNone(member.purchase_price)


class PurchaseSetRightsTests(ApiTestCase):
    """Review finding 13: the set an item was bought in tells about prices – only with that right (AUT-019)."""

    def setUp(self) -> None:
        super().setUp()
        model = make_model("Funkstrecke")
        self.head = make_item(model, 851, purchase_price=Decimal("900.00"))
        self.member = make_item(model, 852, purchase_price_in=self.head)

    def test_the_form_and_the_api(self) -> None:
        lager = Role.objects.get(name="Lager")
        lager.special_rights = []
        lager.save()
        form = MaterialItemForm(instance=self.member, rights=rights_of(make_user("luka", roles=("Lager",))))
        self.assertNotIn("purchase_price_in_number", form.fields)
        self.assertNotIn("purchase_price", form.fields)
        client = self.client_for("lena", "Lager")
        data = client.get(f"{API}/material-items/{self.member.pk}").json()
        self.assertNotIn("purchase_price_in", data)
        response = client.patch(f"{API}/material-items/{self.member.pk}", {"purchase_price_in": None}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.admin.get(f"{API}/material-items/{self.member.pk}").json()["purchase_price_in"], self.head.pk
        )
