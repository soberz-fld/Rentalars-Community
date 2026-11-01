# SPDX-License-Identifier: GPL-3.0-or-later
"""Credit balances in the open items (DOK-053) – refunds due to customers, credit notes of suppliers."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse

from rentalars.documents import payments, services
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice
from tests.api.base import API, ApiTestCase
from tests.ui.base import UiTestCase
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)


class CreditBase(AccountingCase):
    def credit_note(self, gross: str = "-119.00", number: str = "GS-1") -> IncomingInvoice:
        invoice = make_invoice()
        add(invoice, "Miete", "1", "100.00", position_type="other", tax_rate=D("19.00"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number=number, total_net=D(gross) / D("1.19"), total_gross=D(gross), invoice_date=TODAY
        )
        return IncomingInvoice.objects.get(pk=invoice.pk)

    def overpaid_invoice(self):
        invoice = self.invoice()  # 291,50
        payments.record(invoice, paid_on=TODAY, amount=D("300.00"), user=self.user)
        return invoice


class CreditServiceTests(CreditBase):
    def test_an_overpaid_invoice_is_a_refund_due(self) -> None:
        invoice = self.overpaid_invoice()
        rows = payments.credit_items(today=TODAY)
        self.assertEqual([(d.pk, b.remaining, b.state) for d, b in rows], [(invoice.pk, D("-8.50"), "overpaid")])
        self.assertEqual(payments.open_items(today=TODAY), [])
        payments.record(invoice, paid_on=TODAY, amount=D("-8.50"), user=self.user)
        self.assertEqual(payments.credit_items(today=TODAY), [])

    def test_an_invoice_cancelled_after_payment_is_a_refund_due(self) -> None:
        invoice = self.invoice()
        payments.record(invoice, paid_on=TODAY, amount=D("291.50"), user=self.user)
        services.cancel_invoice(invoice)
        rows = payments.credit_items(today=TODAY)
        self.assertEqual([(b.remaining, b.state) for _d, b in rows], [(D("-291.50"), "refund_due")])

    def test_an_open_or_paid_invoice_is_no_credit(self) -> None:
        invoice = self.invoice()
        self.assertEqual(payments.credit_items(today=TODAY), [])
        payments.record(invoice, paid_on=TODAY, amount=D("291.50"), user=self.user)
        self.assertEqual(payments.credit_items(today=TODAY), [])

    def test_a_credit_note_of_a_supplier_is_money_to_claim_until_it_is_paid_back(self) -> None:
        note = self.credit_note()
        self.assertEqual(
            [(i.pk, b.remaining) for i, b in incoming_payments.credit_items(today=TODAY)], [(note.pk, D("-119.00"))]
        )
        self.assertEqual(incoming_payments.open_items(today=TODAY), [])
        incoming_payments.record(note, paid_on=TODAY, amount=D("-119.00"), user=self.user)
        self.assertEqual(incoming_payments.credit_items(today=TODAY), [])

    def test_a_voided_payment_gives_the_credit_back(self) -> None:
        invoice = self.overpaid_invoice()
        payments.void(invoice.payments.get(), reason="wrong", user=self.user)
        self.assertEqual(payments.credit_items(today=TODAY), [])


class CreditPageTests(UiTestCase, CreditBase):
    def test_the_page_lists_both_directions_and_gives_a_csv(self) -> None:
        invoice = self.overpaid_invoice()
        self.credit_note()
        url = reverse("documents:open_items") + "?side=credits"
        page = self.assert_ok(self.client.get(url))
        self.assertIn(invoice.number, page)
        self.assertIn("GS-1", page)
        self.assertIn('data-direction="owe_customer"', page)
        self.assertIn('data-direction="owed_by_supplier"', page)
        self.assertIn("8,50", page)
        csv = self.client.get(url + "&format=csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("GS-1", csv.content.decode("utf-8"))
        self.assertIn("guthaben.csv", csv["Content-Disposition"])

    def test_the_other_tabs_link_to_it(self) -> None:
        page = self.assert_ok(self.client.get(reverse("documents:open_items")))
        self.assertIn("?side=credits", page)

    def test_only_the_sides_one_may_see(self) -> None:
        self.overpaid_invoice()
        self.credit_note()
        url = reverse("documents:open_items") + "?side=credits"
        page = self.assert_ok(self.browser_for("lagerist", "Lager").get(url))
        self.assertIn("GS-1", page)
        self.assertNotIn('data-direction="owe_customer"', page)
        self.assertEqual(self.browser_for("crewperson", "Crew").get(url).status_code, 403)


class CreditApiTests(CreditBase, ApiTestCase):
    def test_the_credits_side(self) -> None:
        self.overpaid_invoice()
        self.credit_note()
        body = self.admin.get(f"{API}/accounting/open-items?side=credits").json()
        self.assertEqual(
            (body["side"], body["total"], body["owed_to_customers"], body["owed_by_suppliers"]),
            ("credits", None, "8.50", "119.00"),
        )
        self.assertEqual(sorted(item["direction"] for item in body["items"]), ["owe_customer", "owed_by_supplier"])
        self.assertTrue(all(Decimal(item["remaining"]) < 0 for item in body["items"]))
        lager = self.client_for("lars3", "Lager").get(f"{API}/accounting/open-items?side=credits")
        self.assertEqual(lager.status_code, 200)
        self.assertEqual([item["direction"] for item in lager.json()["items"]], ["owed_by_supplier"])
        self.assertEqual(
            self.client_for("crew2", "Crew").get(f"{API}/accounting/open-items?side=credits").status_code, 403
        )
