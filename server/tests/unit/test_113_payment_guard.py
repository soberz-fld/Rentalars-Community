# SPDX-License-Identifier: GPL-3.0-or-later
"""A payment cannot be changed or deleted – not even around the services (DOK-051).

Not only the services keep to it: the model stops a script, the shell or a bulk ``update`` from changing an amount.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from rentalars.core.payment_base import PaymentLockedError
from rentalars.documents import payments
from rentalars.documents.models import OutgoingPayment
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice, IncomingPayment
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)


class OutgoingPaymentGuardTests(AccountingCase):
    def setUp(self) -> None:
        super().setUp()
        self.invoice_ = self.invoice()
        self.payment = payments.record(self.invoice_, paid_on=TODAY, amount=D("100.00"), user=self.user)

    def stored(self) -> OutgoingPayment:
        return OutgoingPayment.objects.get(pk=self.payment.pk)

    def test_a_field_cannot_be_changed(self) -> None:
        for field, value in (
            ("amount", D("1.00")),
            ("paid_on", datetime.date(2027, 2, 1)),
            ("method", "cash"),
            ("reference", "other"),
            ("note", "x"),
        ):
            payment = self.stored()
            setattr(payment, field, value)
            with self.assertRaises(PaymentLockedError, msg=field):
                payment.save()
        self.assertEqual(self.stored().amount, D("100.00"))

    def test_the_voiding_fields_alone_do_not_void(self) -> None:
        payment = self.stored()
        payment.void_reason = "no"
        with self.assertRaises(PaymentLockedError):
            payment.save()

    def test_it_cannot_be_deleted_one_by_one_or_in_bulk(self) -> None:
        with self.assertRaises(PaymentLockedError):
            self.stored().delete()
        with self.assertRaises(PaymentLockedError):
            OutgoingPayment.objects.all().delete()
        with self.assertRaises(PaymentLockedError):
            OutgoingPayment.objects.all().update(amount=D("1.00"))
        self.assertEqual(OutgoingPayment.objects.count(), 1)

    def test_a_new_object_with_the_number_of_a_stored_payment_does_not_overwrite_it(self) -> None:
        copy = OutgoingPayment(
            pk=self.payment.pk, document=self.invoice_, paid_on=TODAY, amount=D("1.00"), method="cash"
        )
        with self.assertRaises(PaymentLockedError):
            copy.save()
        with self.assertRaises(PaymentLockedError):
            OutgoingPayment.objects.bulk_create(
                [OutgoingPayment(pk=self.payment.pk, document=self.invoice_, paid_on=TODAY, amount=D("1.00"))],
                update_conflicts=True,
                update_fields=["amount"],
                unique_fields=["id"],
            )
        self.assertEqual(self.stored().amount, D("100.00"))

    def test_voiding_needs_a_reason_even_around_the_service(self) -> None:
        payment = self.stored()
        payment.voided_at = datetime.datetime(2027, 3, 2, tzinfo=datetime.UTC)
        with self.assertRaises(PaymentLockedError):
            payment.save()
        payment.void_reason = "  "
        with self.assertRaises(PaymentLockedError):
            payment.save()
        self.assertIsNone(self.stored().voided_at)
        payment.void_reason = "booked twice"
        payment.save()
        self.assertIsNotNone(self.stored().voided_at)

    def test_voiding_by_the_service_still_works_once(self) -> None:
        payments.void(self.stored(), reason="booked twice", user=self.user)
        voided = self.stored()
        self.assertIsNotNone(voided.voided_at)
        voided.void_reason = "something else"
        with self.assertRaises(PaymentLockedError):
            voided.save()
        voided = self.stored()
        voided.voided_at = None
        with self.assertRaises(PaymentLockedError):
            voided.save()
        self.assertEqual(self.stored().void_reason, "booked twice")

    def test_saving_it_unchanged_is_fine(self) -> None:
        payment = self.stored()
        payment.save()
        self.assertEqual(self.stored().amount, D("100.00"))


class IncomingPaymentGuardTests(AccountingCase):
    def test_the_same_for_payments_to_a_supplier(self) -> None:
        invoice = make_invoice()
        add(invoice, "Miete", "1", "100.00", position_type="other", tax_rate=D("19.00"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(invoice_number="ER-1", total_gross=D("119.00"))
        invoice = IncomingInvoice.objects.get(pk=invoice.pk)
        payment = incoming_payments.record(invoice, paid_on=TODAY, amount=D("119.00"), user=self.user)
        changed = IncomingPayment.objects.get(pk=payment.pk)
        changed.amount = D("1.00")
        with self.assertRaises(PaymentLockedError):
            changed.save()
        with self.assertRaises(PaymentLockedError):
            IncomingPayment.objects.filter(pk=payment.pk).delete()
        incoming_payments.void(payment, reason="returned", user=self.user)
        self.assertIsNotNone(IncomingPayment.objects.get(pk=payment.pk).voided_at)
