# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent review: what the reproductions of the review found, as tests (DOK-023, DOK-024, IMP-010, MAT-020).

* booking pieces at a position whose amount does not divide into the pieces keeps the amount of the position;
* "record the purchase" of bulk material makes the amount of the row the amount of the position;
* the import leaves sold / blocked / defective items as they are, and a sold "import error" item goes back after a
  reversed sale;
* a booked-in spread (SpreadLock) is not touched by the choice of the pieces;
* an inactive tax account is refused for a position, but a position that has it keeps it;
* a note that has line breaks in the cell is written once.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.incoming import booking, services
from rentalars.incoming.models import PositionType
from rentalars.masterdata.models import TaxAccount
from rentalars.material import purchases, sales
from rentalars.material.models import ItemStatus, MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, make_model
from tests.unit.test_091_purchase import FilesMixin
from tests.unit.test_100_incoming import add, make_invoice, upload
from tests.unit.test_importer import HEAD, run


def item(number: int) -> MaterialItem:
    return MaterialItem.objects.get(inventory_number=number)


class PiecesAtAnAmountTests(RentalarsTestCase):
    """The pieces are chosen when booking in; the amount of the position stays what the invoice says."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Schraube M8", category_code="K", manufacturer="Würth")

    def test_pieces_that_divide_the_amount_change_quantity_and_unit_price(self) -> None:
        invoice = make_invoice()
        position = add(invoice, "Schraube M8", "1", "23.31")
        made = booking.book(
            invoice, [booking.Entry(position=position, model=self.model, count=3)], rights=ALL_RIGHTS, user=None
        )
        position.refresh_from_db()
        self.assertEqual((position.quantity, position.unit_price_net), (Decimal("3"), Decimal("7.7700")))
        self.assertEqual({entry.purchase_price for entry in made.items}, {Decimal("7.77")})

    def test_pieces_that_do_not_divide_the_amount_keep_the_amount(self) -> None:
        invoice = make_invoice()
        position = add(invoice, "Schraube M8", "1", "10.00")
        booking.book(
            invoice, [booking.Entry(position=position, model=self.model, count=3)], rights=ALL_RIGHTS, user=None
        )
        position.refresh_from_db()
        self.assertEqual(position.line_net, Decimal("10.00"))  # not 9.9999 and not 3 × 3.33
        prices = sorted(entry.purchase_price for entry in MaterialItem.objects.filter(source_position=position))
        self.assertEqual(sum(prices), Decimal("10.00"))

    def test_a_spread_that_was_made_is_not_changed_by_the_pieces(self) -> None:
        invoice = make_invoice()
        position = add(invoice, "Schraube M8", "2", "10.00")
        add(invoice, "Fracht", "1", "6.00", position_type=PositionType.ANCILLARY)
        booking.book(
            invoice, [booking.Entry(position=position, model=self.model, count=1)], rights=ALL_RIGHTS, user=None
        )
        position.refresh_from_db()
        self.assertEqual(position.quantity, Decimal("2"))  # frozen: items exist and the freight is spread
        plan = booking.plan(
            invoice, [booking.Entry(position=position, model=self.model, count=1, book_again=True)], rights=ALL_RIGHTS
        )
        self.assertTrue(plan.ok, plan.problems or [row.problems for row in plan.rows])


class RecordPurchaseOfBulkTests(FilesMixin, RentalarsTestCase):
    """500 screws at 0.05 are one position of 25.00, not of 0.05."""

    def test_the_amount_of_a_bulk_row_is_the_amount_of_the_position(self) -> None:
        screws = make_model("Schraube M8", category_code="K", bulk=True)
        kept = purchases.keep_invoice(upload(), user=None)
        done = purchases.create_purchase(
            purchases.Head(supplier_name="Würth", invoice_number="RE-5"),
            [purchases.Position(model=screws, count=500, unit_price=Decimal("0.05"))],
            rights=ALL_RIGHTS,
            user=None,
            invoice=kept,
        )
        invoice, created = services.create_from_purchase(done.items, user=None)
        self.assertTrue(created)
        position = invoice.positions.get()
        self.assertEqual(
            (position.quantity, position.unit_price_net, position.line_net), (500, Decimal("0.05"), Decimal("25.00"))
        )


class ImporterKeepsTheStatusTests(RentalarsTestCase):
    """An item that is not rentable anyway keeps its status; the note names the entries."""

    def test_a_sold_item_is_not_turned_into_an_import_error(self) -> None:
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;499,00\n")
        MaterialItem.objects.filter(inventory_number=310).update(status=ItemStatus.SOLD)
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n")
        self.assertEqual(item(310).status, ItemStatus.SOLD)
        self.assertEqual(item(310).note, "Kaufpreis: neun")
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;9,00\n")
        self.assertEqual(item(310).status, ItemStatus.SOLD)  # a clean row does not put it back on the shelf

    def test_a_reversed_sale_brings_an_import_error_item_back_as_it_was(self) -> None:
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n")
        row = item(310)
        self.assertEqual(row.status, ItemStatus.IMPORT_ERROR)
        sale = sales.sell(row, sold_on=datetime.date(2027, 3, 1), net_price=Decimal("50.00"), buyer_name="Hans Meier")
        self.assertEqual(item(310).status, ItemStatus.SOLD)
        sales.cancel(sale, reason="Irrtum")
        self.assertEqual(item(310).status, ItemStatus.IMPORT_ERROR)

    def test_a_cell_with_line_breaks_is_written_once(self) -> None:
        text = f'{HEAD};Seriennummer;Kaufpreis\n310;Empfänger;Ton;"A1\nB2";neun\n'
        run(text)
        run(text)
        lines = item(310).note.splitlines()
        self.assertEqual(len(lines), len(set(lines)))
        self.assertIn("Kaufpreis: neun", lines)


class InactiveAccountTests(ApiTestCase):
    """A tax account that is not in use any more is not given to a position – the one that has it keeps it."""

    def test_the_service_refuses_an_inactive_account_for_a_position(self) -> None:
        account = TaxAccount.objects.get(number="4980")
        account.is_active = False
        account.save()
        invoice = make_invoice()
        with self.assertRaises(ValidationError):
            add(invoice, "Gaffa", "1", "5.00", tax_account=account, position_type=PositionType.GOODS)

    def test_a_position_that_has_the_account_keeps_it_when_something_else_changes(self) -> None:
        account = TaxAccount.objects.get(number="4980")
        invoice = make_invoice()
        position = add(invoice, "Gaffa", "1", "5.00", tax_account=account, position_type=PositionType.GOODS)
        account.is_active = False
        account.save()
        response = self.admin.patch(
            f"{API}/incoming-invoices/{invoice.pk}/positions/{position.pk}",
            {"description": "Gaffa schwarz"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        position.refresh_from_db()
        self.assertEqual((position.description, position.tax_account), ("Gaffa schwarz", account))

    def test_the_api_refuses_an_inactive_account_for_a_position(self) -> None:
        account = TaxAccount.objects.get(number="4980")
        account.is_active = False
        account.save()
        invoice = make_invoice()
        response = self.admin.post(
            f"{API}/incoming-invoices/{invoice.pk}/positions",
            {"description": "Gaffa", "quantity": "1", "unit_price_net": "5.00", "tax_account": account.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)


class TaxAccountApiTests(ApiTestCase):
    """API-014: the resource ``/tax-accounts`` is whole – list, read, create, change, delete."""

    def test_the_whole_resource(self) -> None:
        created = self.admin.post(f"{API}/tax-accounts", {"number": "9999", "name": "Eigenes Konto"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        url = f"{API}/tax-accounts/{created.json()['id']}"
        self.assertEqual(self.admin.get(url).json()["number"], "9999")
        patched = self.admin.patch(url, {"name": "Eigenes Konto 2"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        put = self.admin.put(url, {"number": "9999", "name": "Eigenes Konto 3", "is_active": False}, format="json")
        self.assertEqual(put.status_code, 200, put.content)
        self.assertEqual(TaxAccount.objects.get(number="9999").name, "Eigenes Konto 3")
        self.assertEqual(self.admin.delete(url).status_code, 204)
        self.assertFalse(TaxAccount.objects.filter(number="9999").exists())

    def test_a_number_exists_once_and_is_digits(self) -> None:
        self.assertEqual(
            self.admin.post(f"{API}/tax-accounts", {"number": "3400", "name": "doppelt"}, format="json").status_code,
            400,
        )
        self.assertEqual(
            self.admin.post(f"{API}/tax-accounts", {"number": "34x0", "name": "Buchstabe"}, format="json").status_code,
            400,
        )

    def test_an_account_in_use_is_not_deleted(self) -> None:
        account = TaxAccount.objects.get(number="4980")
        add(make_invoice(), "Gaffa", "1", "5.00", tax_account=account, position_type=PositionType.GOODS)
        response = self.admin.delete(f"{API}/tax-accounts/{account.pk}")
        self.assertIn(response.status_code, (400, 409), response.content)
        self.assertTrue(TaxAccount.objects.filter(pk=account.pk).exists())
