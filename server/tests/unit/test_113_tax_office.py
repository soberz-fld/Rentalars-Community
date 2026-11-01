# SPDX-License-Identifier: GPL-3.0-or-later
"""Payments to the tax office are no expenses of the EÜR (DOK-052).

A supplier can be marked as a tax office: for
turnover tax the payment is set against the balance of the turnover tax, for income tax and the like it is shown apart.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse

from rentalars.documents import euer, payments
from rentalars.documents.models import AccountingSettings
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice, PositionType
from rentalars.masterdata.models import Supplier, TaxOfficeKind
from tests.api.base import API, ApiTestCase
from tests.ui.base import UiTestCase
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)


class TaxOfficeBase:
    def bill(self, supplier: Supplier | None, gross: str = "1000.00", number: str = "FA-1") -> IncomingInvoice:
        invoice = make_invoice()
        add(invoice, "Steuer", "1", gross, position_type=PositionType.OTHER, tax_rate=D("0"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number=number,
            supplier=supplier,
            total_net=D(gross),
            total_tax=D("0.00"),
            total_gross=D(gross),
        )
        return IncomingInvoice.objects.get(pk=invoice.pk)

    def office(self, kind: str) -> Supplier:
        return Supplier.objects.create(name=f"Finanzamt {kind}", tax_office=kind)


class TaxOfficeTests(TaxOfficeBase, AccountingCase):
    def test_without_the_mark_it_is_an_expense_as_before(self) -> None:
        shop = Supplier.objects.create(name="Händler")
        incoming_payments.record(self.bill(shop), paid_on=TODAY, amount=D("1000.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.expense_net, D("1000.00"))
        self.assertEqual(result.tax_office_vat.net, D("0"))

    def test_turnover_tax_paid_is_set_against_the_balance_not_the_profit(self) -> None:
        invoice = self.invoice()
        payments.record(invoice, paid_on=TODAY, amount=payments.balance(invoice).remaining, user=self.user)
        before = euer.compute(2027)
        office = self.office(TaxOfficeKind.VAT)
        incoming_payments.record(self.bill(office, "40.00"), paid_on=TODAY, amount=D("40.00"), user=self.user)
        after = euer.compute(2027)
        self.assertEqual(after.profit, before.profit)
        self.assertEqual(after.expenses, before.expenses)
        self.assertEqual(after.tax_office_vat.net, D("40.00"))
        self.assertEqual(after.vat_still_owed, before.tax_balance - D("40.00"))
        self.assertEqual(after.as_json()["tax_office_vat"], "40.00")
        kinds = {entry.kind for entry in after.entries}
        self.assertIn(euer.TAX_VAT, kinds)

    def test_income_tax_is_shown_apart_and_a_refund_counts_negative(self) -> None:
        office = self.office(TaxOfficeKind.INCOME)
        bill = self.bill(office, "500.00")
        incoming_payments.record(bill, paid_on=TODAY, amount=D("500.00"), user=self.user)
        incoming_payments.record(bill, paid_on=TODAY, amount=D("-100.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual((result.tax_office_income.net, result.tax_office_income.count), (D("400.00"), 2))
        self.assertEqual((result.expense_net, result.profit), (D("0"), D("0")))

    def test_the_lines_behind_the_figures_name_the_payment(self) -> None:
        office = self.office(TaxOfficeKind.VAT)
        payment = incoming_payments.record(self.bill(office, "40.00"), paid_on=TODAY, amount=D("40.00"), user=self.user)
        rows = euer.csv_rows(euer.compute(2027))
        self.assertTrue(any(row[8] == f"incoming_payment:{payment.pk}" and row[5] == "40.00" for row in rows[1:]))

    def test_the_result_names_it(self) -> None:
        office = self.office(TaxOfficeKind.VAT)
        incoming_payments.record(self.bill(office, "40.00"), paid_on=TODAY, amount=D("40.00"), user=self.user)
        body = euer.compute(2027).as_json()
        self.assertEqual((body["tax_office_vat"], body["tax_office_income"]), ("40.00", "0.00"))

    def test_a_small_business_owes_no_turnover_tax_but_shows_the_payment(self) -> None:
        settings = AccountingSettings.load()
        settings.small_business = True
        settings.save()
        office = self.office(TaxOfficeKind.VAT)
        incoming_payments.record(self.bill(office, "40.00"), paid_on=TODAY, amount=D("40.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual((result.tax_office_vat.net, result.vat_still_owed), (D("40.00"), D("0")))
        self.assertEqual(result.expenses, [])  # it is no expense either


class TaxOfficePageTests(TaxOfficeBase, UiTestCase, AccountingCase):
    def test_the_page_shows_what_is_paid_and_what_is_still_owed(self) -> None:
        vat = self.office(TaxOfficeKind.VAT)
        income = self.office(TaxOfficeKind.INCOME)
        incoming_payments.record(self.bill(vat, "40.00"), paid_on=TODAY, amount=D("40.00"), user=self.user)
        incoming_payments.record(self.bill(income, "400.00", "FA-2"), paid_on=TODAY, amount=D("400.00"), user=self.user)
        page = self.assert_ok(self.client.get(reverse("documents:euer") + "?year=2027"))
        self.assertIn("Noch an das Finanzamt zu zahlen", page)
        self.assertIn("An das Finanzamt gezahlte Umsatzsteuer", page)
        self.assertIn("Einkommensteuer und Ähnliches", page)

    def test_a_small_business_page_shows_the_payment_too(self) -> None:
        settings = AccountingSettings.load()
        settings.small_business = True
        settings.save()
        office = self.office(TaxOfficeKind.VAT)
        incoming_payments.record(self.bill(office, "40.00"), paid_on=TODAY, amount=D("40.00"), user=self.user)
        page = self.assert_ok(self.client.get(reverse("documents:euer") + "?year=2027"))
        self.assertIn("An das Finanzamt gezahlte Umsatzsteuer", page)
        self.assertNotIn("Noch an das Finanzamt zu zahlen", page)


class TaxOfficeApiTests(ApiTestCase):
    def test_the_api_gives_the_figures_and_the_mark_to_who_may_see_the_eur(self) -> None:
        office = Supplier.objects.create(name="Finanzamt", tax_office=TaxOfficeKind.VAT)
        body = self.admin.get(f"{API}/accounting/euer?year=2027").json()
        self.assertIn("tax_office_vat", body)
        self.assertEqual(self.admin.get(f"{API}/suppliers/{office.pk}").json()["tax_office"], "vat")

    def test_who_maintains_suppliers_cannot_change_how_the_eur_counts_them(self) -> None:
        shop = Supplier.objects.create(name="Händler")
        keeper = self.client_for("lager9", "Lager")  # may write the material, has no right to the EÜR
        self.assertNotIn("tax_office", keeper.get(f"{API}/suppliers/{shop.pk}").json())
        refused = keeper.patch(f"{API}/suppliers/{shop.pk}", {"tax_office": "income"}, format="json")
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(Supplier.objects.get(pk=shop.pk).tax_office, "")
        self.assertEqual(keeper.patch(f"{API}/suppliers/{shop.pk}", {"note": "x"}, format="json").status_code, 200)
        changed = self.admin.patch(f"{API}/suppliers/{shop.pk}", {"tax_office": "income"}, format="json")
        self.assertEqual((changed.status_code, Supplier.objects.get(pk=shop.pk).tax_office), (200, "income"))
