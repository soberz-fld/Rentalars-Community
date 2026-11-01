# SPDX-License-Identifier: GPL-3.0-or-later
"""What the independent review found in payments (DOK-048), EÜR (DOK-045), archive (DOK-043) and export (DOK-046).

Every test here pins one finding of the review so that it stays fixed.
"""

from __future__ import annotations

import datetime
import io
import zipfile
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import ValidationError

from rentalars.documents import archive, audit_export, billing, cii, euer, payments
from rentalars.documents.models import ArchiveRecord, ArchiveSource, ArchiveStatus
from rentalars.incoming import booking
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice
from tests.helpers import ALL_RIGHTS, make_model
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)


class ArchiveReviewTests(AccountingCase):
    def test_a_pdf_altered_before_it_was_registered_stays_a_finding(self) -> None:
        document = self.invoice()
        with document.file.storage.open(document.file.name, "wb") as handle:
            handle.write(b"changed before the first night")
        archive.register_missing()
        for _night in range(3):
            archive.run(everything=True)
            self.assertEqual(ArchiveRecord.objects.get().status, ArchiveStatus.CHANGED)

    def test_the_retention_of_an_incoming_invoice_counts_from_the_later_of_its_date_and_its_arrival(self) -> None:
        invoice = make_invoice()
        IncomingInvoice.objects.filter(pk=invoice.pk).update(invoice_date=datetime.date(2015, 5, 1))  # a typo
        record = archive.register(ArchiveSource.INCOMING, IncomingInvoice.objects.get(pk=invoice.pk))
        self.assertEqual(record.voucher_date, datetime.date(2015, 5, 1))
        self.assertEqual(record.retain_until, datetime.date(2035, 12, 31))  # the arrival in 2027 + 8 years

    def test_an_old_invoice_without_a_record_cannot_be_deleted_before_the_job_registered_it(self) -> None:
        invoice = make_invoice()
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            created_at=datetime.datetime(2027, 2, 20, tzinfo=datetime.UTC)
        )
        with self.assertRaises(ValidationError):
            archive.guard_deletion(IncomingInvoice.objects.get(pk=invoice.pk))
        self.assertEqual(ArchiveRecord.objects.count(), 1)

    def test_a_new_invoice_can_still_be_deleted_within_the_grace_time(self) -> None:
        invoice = make_invoice()
        archive.guard_deletion(invoice)
        self.assertEqual(ArchiveRecord.objects.count(), 0)

    def test_two_registrations_at_once_leave_one_record(self) -> None:
        document = self.invoice()
        first = archive.register(ArchiveSource.DOCUMENT, document)
        real = ArchiveRecord.objects.filter
        calls = {"n": 0}

        def blind_once(*args: object, **kwargs: object) -> object:
            calls["n"] += 1
            return ArchiveRecord.objects.none() if calls["n"] == 1 else real(*args, **kwargs)

        with mock.patch.object(ArchiveRecord.objects, "filter", side_effect=blind_once):
            second = archive.register(ArchiveSource.DOCUMENT, document)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ArchiveRecord.objects.count(), 1)


class ExportReviewTests(AccountingCase):
    def test_an_incoming_invoice_without_a_date_is_in_the_export_by_its_arrival(self) -> None:
        invoice = make_invoice()
        IncomingInvoice.objects.filter(pk=invoice.pk).update(invoice_date=None)
        data = audit_export.build(2027).read()
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        self.assertTrue(any(name.startswith("belege/eingang/") for name in names), names)

    def test_two_numbers_that_look_alike_do_not_shadow_each_other(self) -> None:
        for number in ("A/1", "A_1"):
            invoice = make_invoice()
            IncomingInvoice.objects.filter(pk=invoice.pk).update(invoice_number=number)
        names = zipfile.ZipFile(io.BytesIO(audit_export.build(2027).read())).namelist()
        self.assertEqual(len(names), len(set(names)))

    def test_a_cell_that_starts_like_a_formula_is_defused_but_a_negative_amount_is_not(self) -> None:
        self.assertEqual(audit_export._text("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(audit_export._text("@x"), "'@x")
        self.assertEqual(audit_export._text(D("-5")), "-5.00")


class EuerReviewTests(AccountingCase):
    def test_a_payment_follows_the_credit_notes_issued_until_its_day_and_a_refund_follows_the_credit_note(self) -> None:
        invoice = self.invoice()  # 200,00 at 19 % and 50,00 at 7 %
        credit = billing.credit_invoice(invoice, percent=D("10"), note="Nachlass")
        type(credit).objects.filter(pk=credit.pk).update(issued_on=datetime.date(2027, 2, 27))
        invoice = type(invoice).objects.get(pk=invoice.pk)
        before = euer._shares_of(invoice, datetime.date(2027, 2, 25))
        after = euer._shares_of(invoice, datetime.date(2027, 3, 1))
        self.assertEqual(sum(net for _k, net, _t in before), D("250.00"))
        self.assertEqual(sum(net for _k, net, _t in after), D("225.00"))
        refund = euer._shares_of(invoice, datetime.date(2027, 3, 1), refund=True)
        self.assertEqual(sum(net for _k, net, _t in refund), D("-25.00"))

    def test_the_whole_story_adds_up_in_the_eur(self) -> None:
        invoice = self.invoice()
        payments.record(invoice, paid_on=datetime.date(2027, 2, 25), amount=D("291.50"), user=self.user)
        credit = billing.credit_invoice(invoice, percent=D("10"), note="Nachlass")
        type(credit).objects.filter(pk=credit.pk).update(issued_on=datetime.date(2027, 2, 27))
        payments.record(invoice, paid_on=datetime.date(2027, 3, 1), amount=D("-29.15"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.income_net, D("225.00"))
        self.assertEqual(result.tax_collected, D("37.35"))

    def test_a_refund_of_a_credit_note_on_the_untaxed_line_is_not_counted_on_the_taxed_line(self) -> None:
        taxed, untaxed = (D("19"), D("100.00"), D("19.00")), (D("0"), D("100.00"), D("0.00"))
        credit_line = (D("0"), D("-100.00"), D("0.00"))
        by_doc = {"invoice": [taxed, untaxed], "credit": [credit_line]}
        invoice = SimpleNamespace(
            key="invoice",
            issued_on=TODAY,
            partial_credits=SimpleNamespace(all=lambda: [SimpleNamespace(key="credit", issued_on=TODAY)]),
            cancelled_by=None,
        )
        with mock.patch.object(euer, "_parts_of", side_effect=lambda doc: by_doc[doc.key]):
            refund = euer._shares_of(invoice, TODAY, refund=True)
            payment = euer._shares_of(invoice, TODAY)
        self.assertEqual([key for key, _n, _t in refund], [D("0")])
        self.assertEqual(
            [key for key, n, t in payment if n + t], [D("19")]
        )  # the 0 % line is credited in full: nothing left

    def test_of_five_pieces_only_the_booked_ones_are_an_asset(self) -> None:
        invoice = make_invoice()
        position = add(invoice, "Kabel", "5", "300.00")
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number="ER-5",
            invoice_date=datetime.date(2027, 2, 22),
            total_net=D("1500.00"),
            total_tax=D("285.00"),
            total_gross=D("1785.00"),
        )
        type(position).objects.filter(pk=position.pk).update(tax_rate=D("19.00"))
        invoice = IncomingInvoice.objects.get(pk=invoice.pk)
        booking.book(
            invoice,
            [booking.Entry(position=invoice.positions.get(), model=make_model("Kabel", category_code="T"), count=2)],
            rights=ALL_RIGHTS,
            user=None,
        )
        incoming_payments.record(invoice, paid_on=TODAY, amount=D("1785.00"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.depreciation.net, D("600.00"))
        self.assertEqual(result.expense_net, D("900.00"))  # the three pieces not booked in
        self.assertEqual(result.input_tax, D("285.00"))


class SmallReviewTests(AccountingCase):
    def test_a_credit_note_of_a_supplier_is_read_like_an_invoice_mirrored(self) -> None:
        self.assertEqual(payments.state_for(D("-100"), D("0")), "open")
        self.assertEqual(payments.state_for(D("-100"), D("-40")), "partial")
        self.assertEqual(payments.state_for(D("-100"), D("-100")), "paid")
        self.assertEqual(payments.state_for(D("-100"), D("-120")), "overpaid")

    def test_a_percentage_keeps_its_zeros(self) -> None:
        self.assertEqual(cii._percent(D("10")), "10")
        self.assertEqual(cii._percent(D("20.00")), "20")
        self.assertEqual(cii._percent(D("7.50")), "7.5")
        self.assertEqual(cii._percent(D("0.00")), "0")

    def test_a_control_character_does_not_break_the_xml(self) -> None:
        import xml.etree.ElementTree as ET

        root = ET.Element("a")
        cii._sub(root, "ram:Name", "Mischpult\x0b-Set")
        ET.fromstring(ET.tostring(root))  # would raise for \x0b if it were kept
        self.assertNotIn("\x0b", root[0].text or "")
