# SPDX-License-Identifier: GPL-3.0-or-later
"""The EÜR of a year (DOK-045) – income and expenses by payment, depreciation, small business, rounding.

The EÜR counts what flowed (Zufluss/Abfluss): the payments, split over the tax rates of their invoice. Fixed assets come in as
depreciation, not as an expense of the day of payment; the input tax counts with the payment all the same.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from rentalars.core import tax_split
from rentalars.documents import euer, payments, services
from rentalars.documents.models import AccountingSettings
from rentalars.incoming import booking
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice, PositionType
from rentalars.masterdata.models import TaxAccount
from rentalars.material.models import AssetKind
from tests.helpers import ALL_RIGHTS, make_model
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)


def rows_of(rows: list[euer.Row]) -> dict[str, tuple[Decimal, Decimal]]:
    return {row.label: (row.net, row.tax) for row in rows}


class SplitTests(AccountingCase):
    def test_a_payment_is_split_to_the_cent(self) -> None:
        shares = [("19", D("200.00"), D("38.00")), ("7", D("50.00"), D("3.50"))]
        for amount in ("291.50", "100.00", "0.01", "-50.00", "123.45"):
            parts = tax_split.split(D(amount), shares)
            self.assertEqual(sum((n + t for _k, n, t in parts), D("0")), D(amount), amount)

    def test_a_single_rate_keeps_the_ratio(self) -> None:
        parts = tax_split.split(D("119.00"), [("19", D("100.00"), D("19.00"))])
        self.assertEqual(parts, [("19", D("100.00"), D("19.00"))])


class IncomeTests(AccountingCase):
    def pay(self, invoice: object, amount: str, day: datetime.date = TODAY) -> object:
        return payments.record(invoice, paid_on=day, amount=D(amount), user=self.user)

    def test_income_is_the_payment_split_over_the_tax_rates(self) -> None:
        invoice = self.invoice()  # 200,00 at 19 % and 50,00 at 7 % = 291,50
        self.pay(invoice, "291.50")
        result = euer.compute(2027)
        self.assertEqual(len(result.income), 2)
        self.assertEqual(result.income_net, D("250.00"))
        self.assertEqual(result.tax_collected, D("41.50"))
        self.assertEqual(result.profit, D("250.00"))

    def test_a_part_payment_counts_in_proportion(self) -> None:
        invoice = self.invoice()
        self.pay(invoice, "145.75")
        result = euer.compute(2027)
        self.assertEqual(result.income_net + result.tax_collected, D("145.75"))
        self.assertEqual(result.income_net, D("125.00"))

    def test_only_the_year_of_the_payment_counts(self) -> None:
        invoice = self.invoice()
        self.pay(invoice, "100.00", datetime.date(2026, 12, 30))
        self.pay(invoice, "191.50", TODAY)
        self.assertEqual(euer.compute(2026).income_net + euer.compute(2026).tax_collected, D("100.00"))
        self.assertEqual(euer.compute(2027).income_net + euer.compute(2027).tax_collected, D("191.50"))

    def test_a_voided_payment_does_not_count_and_a_refund_reduces(self) -> None:
        invoice = self.invoice()
        wrong = self.pay(invoice, "999.00")
        payments.void(wrong, reason="typed wrong", user=self.user)
        self.pay(invoice, "291.50")
        self.pay(invoice, "-29.15")
        result = euer.compute(2027)
        self.assertEqual(result.income_net + result.tax_collected, D("262.35"))

    def test_a_credit_note_is_paid_back_and_counts_through_the_refund(self) -> None:
        invoice = self.invoice()
        self.pay(invoice, "291.50")
        services.cancel_invoice(invoice)
        self.pay(invoice, "-291.50")
        result = euer.compute(2027)
        self.assertEqual(result.income_net, D("0.00"))
        self.assertEqual(result.tax_collected, D("0.00"))

    def test_a_small_business_counts_gross(self) -> None:
        row = AccountingSettings.load()
        row.small_business = True
        row.save()
        self.pay(self.invoice(), "291.50")
        result = euer.compute(2027)
        self.assertEqual(result.income_net, D("291.50"))
        self.assertEqual(result.tax_collected, D("0.00"))
        self.assertTrue(result.small_business)

    def test_the_lines_add_up_to_the_figures(self) -> None:
        self.pay(self.invoice(), "291.50")
        result = euer.compute(2027)
        lines = [e for e in result.entries if e.kind == euer.INCOME]
        self.assertEqual(sum((e.net for e in lines), D("0")), result.income_net)
        csv_lines = euer.csv_rows(result)
        self.assertEqual(len(csv_lines), len(result.entries) + 1)


class ExpenseTests(AccountingCase):
    def invoice_in(self, net_positions: list[tuple[str, str, dict[str, object]]], **head: object) -> IncomingInvoice:
        invoice = make_invoice()
        for description, price, fields in net_positions:
            add(invoice, description, "1", price, tax_rate=D("19.00"), **fields)
        net = sum((D(price) for _d, price, _f in net_positions), D("0"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number="ER-1",
            invoice_date=datetime.date(2027, 2, 22),
            total_net=net,
            total_tax=(net * D("0.19")).quantize(D("0.01")),
            total_gross=(net * D("1.19")).quantize(D("0.01")),
            **head,
        )
        invoice.refresh_from_db()
        return invoice

    def test_an_expense_is_booked_per_tax_account_on_the_day_of_payment(self) -> None:
        account = TaxAccount.objects.create(number="9990", name="Testkonto")
        invoice = self.invoice_in(
            [("Miete Halle", "100.00", {"position_type": PositionType.OTHER, "tax_account": account})]
        )
        incoming_payments.record(invoice, paid_on=TODAY, amount=D("119.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(rows_of(result.expenses), {"9990 Testkonto": (D("100.00"), D("19.00"))})
        self.assertEqual(result.profit, D("-100.00"))
        self.assertEqual(euer.compute(2026).expense_net, D("0"))

    def test_an_unpaid_invoice_is_no_expense(self) -> None:
        self.invoice_in([("Miete Halle", "100.00", {"position_type": PositionType.OTHER})])
        self.assertEqual(euer.compute(2027).expenses, [])

    def test_a_foreign_currency_is_counted_by_the_rate_or_not_at_all(self) -> None:
        invoice = self.invoice_in([("Rental", "100.00", {"position_type": PositionType.OTHER})], currency="USD")
        incoming_payments.record(invoice, paid_on=TODAY, amount=D("119.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.expenses, [])
        self.assertTrue(any("exchange rate" in w or "Wechselkurs" in w for w in result.warnings))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(exchange_rate=D("0.5"))
        result = euer.compute(2027)
        self.assertEqual(result.expense_net, D("50.00"))
        self.assertEqual(result.input_tax, D("9.50"))

    def test_an_asset_is_depreciation_not_an_expense_but_its_input_tax_counts(self) -> None:
        invoice = self.invoice_in(
            [
                ("Mischpult", "1000.00", {"asset_kind": AssetKind.FIXED_ASSET, "useful_life_months": 60}),
                ("Fracht", "100.00", {"position_type": PositionType.ANCILLARY}),
            ]
        )
        position = invoice.positions.get(description="Mischpult")
        booking.book(
            invoice,
            [booking.Entry(position=position, model=make_model("Mischpult", category_code="T"))],
            rights=ALL_RIGHTS,
            user=None,
        )
        incoming_payments.record(invoice, paid_on=TODAY, amount=D("1309.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.expense_net, D("0.00"))  # the freight is part of the cost of the mixer
        self.assertEqual(result.input_tax, D("209.00"))
        self.assertEqual(result.depreciation.count, 1)
        self.assertGreater(result.depreciation.net, D("0"))
        self.assertLess(result.depreciation.net, D("1100.00"))
        self.assertEqual(result.profit, -result.depreciation.net)

    def test_a_low_value_asset_is_written_off_in_the_year_of_acquisition(self) -> None:
        invoice = self.invoice_in([("Kabel", "300.00", {"asset_kind": AssetKind.LOW_VALUE})])
        position = invoice.positions.get(description="Kabel")
        booking.book(
            invoice,
            [booking.Entry(position=position, model=make_model("Kabel", category_code="T"))],
            rights=ALL_RIGHTS,
            user=None,
        )
        incoming_payments.record(invoice, paid_on=TODAY, amount=D("357.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.depreciation.net, D("300.00"))
        self.assertEqual(result.expense_net, D("0.00"))
        self.assertEqual(euer.compute(2028).depreciation.net, D("0.00"))
