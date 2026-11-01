# SPDX-License-Identifier: GPL-3.0-or-later
"""Payments and open items (DOK-048) – balances are computed, a payment is a booking that is voided, never edited."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.core.audit import AuditedModel  # noqa: F401  (a payment is an audited record)
from rentalars.documents import payments, services
from rentalars.documents.models import Document, OutgoingPayment
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice
from rentalars.projects.legacy_models import LegacyImportBatch, LegacyImportItem
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)


class OutgoingPaymentTests(AccountingCase):
    def reload(self, document: Document) -> Document:
        return Document.objects.get(pk=document.pk)

    def test_the_balance_is_worked_out_from_the_payments(self) -> None:
        invoice = self.invoice()  # 291,50
        self.assertEqual((payments.balance(invoice).state, payments.balance(invoice).remaining), ("open", D("291.50")))
        payments.record(invoice, paid_on=TODAY, amount=D("100.00"), user=self.user)
        balance = payments.balance(self.reload(invoice))
        self.assertEqual((balance.state, balance.paid, balance.remaining), ("partial", D("100.00"), D("191.50")))
        payments.record(invoice, paid_on=TODAY, amount=D("191.50"), user=self.user)
        self.assertEqual(payments.balance(self.reload(invoice)).state, "paid")
        payments.record(invoice, paid_on=TODAY, amount=D("1.00"), user=self.user)
        self.assertEqual(payments.balance(self.reload(invoice)).state, "overpaid")

    def test_a_payment_is_voided_with_a_reason_and_stays(self) -> None:
        invoice = self.invoice()
        payment = payments.record(invoice, paid_on=TODAY, amount=D("291.50"), user=self.user)
        with self.assertRaises(ValidationError):
            payments.void(payment, reason="  ", user=self.user)
        payments.void(payment, reason="booked twice", user=self.user)
        self.assertEqual(OutgoingPayment.objects.count(), 1)
        self.assertEqual(payments.balance(self.reload(invoice)).state, "open")
        with self.assertRaises(ValidationError):
            payments.void(OutgoingPayment.objects.get(), reason="again", user=self.user)

    def test_rules_of_a_payment(self) -> None:
        invoice = self.invoice()
        for values in (
            {"paid_on": datetime.date(2027, 3, 2), "amount": D("5")},  # in the future
            {"paid_on": TODAY, "amount": D("0")},
            {"paid_on": TODAY, "amount": None},
            {"paid_on": None, "amount": D("5")},
            {"paid_on": TODAY, "amount": D("5"), "method": "gift"},
            {"paid_on": TODAY, "amount": D("99999999999")},
        ):
            with self.assertRaises(ValidationError, msg=str(values)):
                payments.record(invoice, user=self.user, **values)
        offer = services.create_document(self.project, "offer", user=self.user)
        with self.assertRaises(ValidationError):
            payments.record(offer, paid_on=TODAY, amount=D("5"), user=self.user)

    def test_a_cancellation_and_a_credit_note_lower_what_is_payable(self) -> None:
        invoice = self.invoice()
        payments.record(invoice, paid_on=TODAY, amount=D("291.50"), user=self.user)
        services.cancel_invoice(invoice)
        balance = payments.balance(self.reload(invoice))
        self.assertEqual((balance.payable, balance.state), (D("0.00"), "refund_due"))
        payments.record(invoice, paid_on=TODAY, amount=D("-291.50"), user=self.user)
        self.assertEqual(payments.balance(self.reload(invoice)).state, "cancelled")

    def test_open_items_are_the_invoices_that_still_demand_money(self) -> None:
        invoice = self.invoice()
        rows = payments.open_items(today=TODAY)
        self.assertEqual([(d.pk, b.remaining) for d, b in rows], [(invoice.pk, D("291.50"))])
        self.assertTrue(rows[0][1].overdue is False or rows[0][0].due_on < TODAY)
        payments.record(invoice, paid_on=TODAY, amount=D("291.50"), user=self.user)
        self.assertEqual(payments.open_items(today=TODAY), [])

    def test_overdue_follows_the_due_day(self) -> None:
        invoice = self.invoice()
        late = payments.open_items(today=invoice.due_on + datetime.timedelta(days=1))[0][1]
        early = payments.open_items(today=invoice.due_on)[0][1]
        self.assertTrue(late.overdue)
        self.assertFalse(early.overdue)

    def test_an_old_invoice_that_counts_as_paid_is_no_open_item_and_takes_no_payment(self) -> None:
        invoice = self.invoice()
        batch = LegacyImportBatch.objects.create()
        LegacyImportItem.objects.create(batch=batch, document=invoice, paid=True, paid_on=datetime.date(2027, 2, 1))
        invoice = self.reload(invoice)
        balance = payments.balance(invoice)
        self.assertTrue(balance.imported_paid)
        self.assertEqual(balance.state, "paid")
        self.assertEqual(payments.open_items(today=TODAY), [])
        with self.assertRaises(ValidationError):
            payments.record(invoice, paid_on=TODAY, amount=D("5"), user=self.user)

    def test_an_old_invoice_not_paid_is_an_open_item(self) -> None:
        invoice = self.invoice()
        LegacyImportItem.objects.create(batch=LegacyImportBatch.objects.create(), document=invoice, paid=False)
        self.assertEqual([d.pk for d, _b in payments.open_items(today=TODAY)], [invoice.pk])


class IncomingPaymentTests(AccountingCase):
    def invoice_in(self, gross: str | None = "119.00", **fields: object) -> IncomingInvoice:
        invoice = make_invoice()
        add(invoice, "Miete", "1", "100.00", position_type="other", tax_rate=D("19.00"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number="ER-1", total_gross=D(gross) if gross else None, due_date=datetime.date(2027, 2, 1), **fields
        )
        return IncomingInvoice.objects.get(pk=invoice.pk)

    def test_balance_payments_and_void(self) -> None:
        invoice = self.invoice_in()
        balance = incoming_payments.balance(invoice)
        self.assertEqual((balance.state, balance.remaining, balance.overdue), ("open", D("119.00"), True))
        payment = incoming_payments.record(invoice, paid_on=TODAY, amount=D("119.00"), user=self.user)
        self.assertEqual(incoming_payments.balance(IncomingInvoice.objects.get(pk=invoice.pk)).state, "paid")
        incoming_payments.void(payment, reason="returned by the bank", user=self.user)
        self.assertEqual(incoming_payments.balance(IncomingInvoice.objects.get(pk=invoice.pk)).state, "open")

    def test_a_credit_note_of_the_supplier_has_negative_totals(self) -> None:
        invoice = self.invoice_in("-119.00")
        incoming_payments.record(invoice, paid_on=TODAY, amount=D("-119.00"), user=self.user)
        self.assertEqual(incoming_payments.balance(IncomingInvoice.objects.get(pk=invoice.pk)).state, "paid")

    def test_no_payment_without_the_totals(self) -> None:
        invoice = self.invoice_in(None)
        self.assertIsNone(incoming_payments.balance(invoice))
        with self.assertRaises(ValidationError):
            incoming_payments.record(invoice, paid_on=TODAY, amount=D("5"), user=self.user)

    def test_open_items_oldest_due_day_first(self) -> None:
        first = self.invoice_in()
        second = self.invoice_in()
        IncomingInvoice.objects.filter(pk=second.pk).update(due_date=datetime.date(2027, 1, 1))
        rows = incoming_payments.open_items(today=TODAY)
        self.assertEqual([invoice.pk for invoice, _b in rows], [second.pk, first.pk])
        incoming_payments.record(second, paid_on=TODAY, amount=D("119.00"), user=self.user)
        self.assertEqual([invoice.pk for invoice, _b in incoming_payments.open_items(today=TODAY)], [first.pk])
