# SPDX-License-Identifier: GPL-3.0-or-later
"""Several invoices per project – advance, partial and final invoices, partial credit notes (DOK-030 to DOK-036).

The project of these tests::

    Licht (19 %)   1.000,00
    Catering (7 %)   500,00        net 1.500,00 · tax 190,00 + 35,00 = 225,00 · gross 1.725,00
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from rentalars.documents import billing, invoice_reminders, services
from rentalars.documents import content as builder
from rentalars.documents.billing import Billing
from rentalars.documents.models import BillingType, Document, DocumentKind
from rentalars.masterdata.models import TaxRate
from rentalars.products.models import BillingMode
from tests.helpers import RentalarsTestCase, add_line, make_product, make_project, ready_for_invoices

D = Decimal


def project_with_two_rates() -> Any:
    reduced, _created = TaxRate.objects.get_or_create(name="7 %", defaults={"rate": D("7")})
    project = make_project("Messe", customer=ready_for_invoices())
    add_line(project, make_product("L-101", "Licht", price="1000.00", billing_mode=BillingMode.FLAT), 1)
    add_line(
        project, make_product("T-101", "Catering", price="500.00", billing_mode=BillingMode.FLAT, tax_rate=reduced), 1
    )
    return project


def content_of(document: Document) -> builder.DocumentContent:
    return builder.from_json(document.content)


class PartInvoiceTests(RentalarsTestCase):
    """Advance and partial invoices: the amount, its split over the tax rates, the rules."""

    def setUp(self) -> None:
        super().setUp()
        self.project = project_with_two_rates()

    def part(self, kind: str = BillingType.ADVANCE, **options: Any) -> Document:
        return services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type=kind, **options))

    def test_the_state_of_a_new_project(self) -> None:
        state = billing.state_of(self.project)
        self.assertEqual((state.project_net, state.project_gross), (D("1500.00"), D("1725.00")))
        self.assertEqual(state.remaining_net, D("1500.00"))
        self.assertIsNone(state.complete)
        self.assertEqual(state.next_number, 1)

    def test_an_advance_invoice_by_percentage_splits_over_the_tax_rates(self) -> None:
        document = self.part(percent=D("20"), note="Anzahlung bei Auftrag")
        content = content_of(document)
        self.assertEqual(document.kind, DocumentKind.INVOICE)
        self.assertEqual((document.billing_type, document.billing_number), (BillingType.ADVANCE, 1))
        self.assertIn("1.", document.title)
        self.assertEqual(
            (content.net_total, content.tax_total, content.gross_total), (D("300.00"), D("45.00"), D("345.00"))
        )
        by_rate = {share.percent: (share.net, share.tax) for share in content.taxes}
        self.assertEqual(by_rate, {D("19.00"): (D("200.00"), D("38.00")), D("7.00"): (D("100.00"), D("7.00"))})
        self.assertEqual(len(content.positions), 2)
        self.assertIn("Anzahlung bei Auftrag", content.positions[0].title)
        self.assertTrue(document.xml_file)
        self.assertEqual(document.net_total, D("300.00"))

    def test_the_project_is_not_invoiced_by_a_part_invoice(self) -> None:
        self.part(percent=D("30"))
        self.assertFalse(invoice_reminders.invoices_of(self.project).exists())
        self.assertEqual(invoice_reminders.invoiced_ids([self.project.pk]), set())
        self.assertEqual(invoice_reminders.state_of(self.project), invoice_reminders.InvoiceState.OPEN)

    def test_parts_are_numbered_and_counted_down(self) -> None:
        first = self.part(percent=D("20"))
        second = self.part(BillingType.PARTIAL, amount=D("400.00"), note="Aufbau")
        self.assertEqual((first.billing_number, second.billing_number), (1, 2))
        self.assertEqual(content_of(second).billing_type, BillingType.PARTIAL)
        state = billing.state_of(self.project)
        self.assertEqual(state.billed_net, D("700.00"))
        self.assertEqual(state.remaining_net, D("800.00"))
        self.assertEqual(state.next_number, 3)

    def test_more_than_is_left_is_refused(self) -> None:
        self.part(percent=D("90"))
        with self.assertRaises(ValidationError) as caught:
            self.part(amount=D("200.00"))
        self.assertIn("amount", caught.exception.error_dict)
        self.assertEqual(Document.objects.filter(kind=DocumentKind.INVOICE).count(), 1)  # nothing was made
        self.part(amount=D("150.00"))  # exactly what is left is possible
        self.assertEqual(billing.state_of(self.project).remaining_net, D("0.00"))

    def test_the_amount_must_be_given_once_and_above_nothing(self) -> None:
        for options in (
            {},
            {"amount": D("0")},
            {"percent": D("0")},
            {"percent": D("101")},
            {"amount": D("5"), "percent": D("5")},
        ):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.part(**options)

    def test_the_ordinary_invoice_is_refused_while_a_part_invoice_is_valid(self) -> None:
        part = self.part(percent=D("20"))
        with self.assertRaises(ValidationError) as caught:
            services.create_document(self.project, DocumentKind.INVOICE)
        self.assertIn(part.number, " ".join(caught.exception.messages))
        # cancelled, the ordinary invoice is possible again
        services.cancel_invoice(part)
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        self.assertEqual(invoice.billing_type, "")

    def test_a_part_invoice_is_refused_while_the_project_is_invoiced(self) -> None:
        services.create_document(self.project, DocumentKind.INVOICE)
        with self.assertRaises(ValidationError):
            self.part(percent=D("10"))

    def test_the_final_invoice_needs_a_part_invoice(self) -> None:
        with self.assertRaises(ValidationError):
            services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type=BillingType.FINAL))

    def test_the_preview_follows_the_same_rules(self) -> None:
        pdf = services.preview(self.project, DocumentKind.INVOICE, billing=Billing(type="advance", percent=D("10")))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertFalse(Document.objects.exists())
        with self.assertRaises(ValidationError):
            services.preview(self.project, DocumentKind.INVOICE, billing=Billing(type="advance", percent=D("101")))

    def test_a_service_case_and_a_part_get_no_part_invoice(self) -> None:
        part = make_project("Teil", customer=self.project.customer)
        part.parent = self.project
        part.save()
        self.assertTrue(billing.problems(part, BillingType.ADVANCE))


class FinalInvoiceTests(RentalarsTestCase):
    """The final invoice deducts what was invoiced on account – and books only the rest."""

    def setUp(self) -> None:
        super().setUp()
        self.project = project_with_two_rates()
        self.first = services.create_document(
            self.project, DocumentKind.INVOICE, billing=Billing(type="advance", percent=D("20"))
        )
        self.second = services.create_document(
            self.project, DocumentKind.INVOICE, billing=Billing(type="partial", amount=D("400.00"))
        )

    def final(self) -> Document:
        return services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type="final"))

    def test_the_total_is_the_whole_project_and_the_payable_amount_less_the_deductions(self) -> None:
        document = self.final()
        content = content_of(document)
        self.assertEqual(document.billing_type, BillingType.FINAL)
        self.assertEqual(content.gross_total, D("1725.00"))
        self.assertEqual([d.number for d in content.deductions], [self.first.number, self.second.number])
        self.assertEqual(content.deductions[0].gross, D("345.00"))
        self.assertEqual(content.deductions[1].net, D("400.00"))
        self.assertEqual(content.prepaid_total, D("805.00"))
        self.assertEqual(content.payable_total, D("920.00"))
        self.assertEqual(
            document.gross_total, D("920.00")
        )  # the lists and sums hold what it adds, the advances are theirs
        self.assertEqual(invoice_reminders.invoiced_ids([self.project.pk]), {self.project.pk})

    def test_the_accounting_books_the_rest_only(self) -> None:
        content = content_of(self.final())
        self.assertEqual(content.booked_gross_total, D("920.00"))
        self.assertEqual(sum(share.net for share in content.booked_taxes), D("1500.00") - D("700.00"))
        self.assertEqual(content.booked_tax_total, D("225.00") - D("45.00") - D("60.00"))

    def test_the_electronic_invoice_states_prepaid_and_payable_amounts(self) -> None:
        document = self.final()
        xml = document.xml_file.read().decode()
        self.assertIn(">805.00<", xml)  # PrepaidAmount
        self.assertIn('<cbc:PayableAmount currencyID="EUR">920.00</cbc:PayableAmount>', xml)
        self.assertIn(f"<cbc:ID>{self.first.number}</cbc:ID>", xml)  # BillingReference
        self.assertIn(f"<cbc:ID>{self.second.number}</cbc:ID>", xml)
        self.assertIn("<cbc:InvoiceTypeCode>380<", xml)
        self.assertIn("<cbc:InvoiceTypeCode>326<", self.second.xml_file.read().decode())

    def test_the_pdf_shows_the_deductions_with_their_tax(self) -> None:
        from rentalars.documents.pdf import render_html

        html = render_html(content_of(self.final()), services.template_for(DocumentKind.INVOICE), draft=False)
        self.assertIn(self.first.number, html)
        self.assertIn("920,00", html)
        self.assertIn("345,00", html)
        self.assertIn("460,00", html)

    def test_the_voucher_for_lexware_holds_the_rest(self) -> None:
        from rentalars.documents.lexware import voucher_body
        from rentalars.documents.models import AccountingSettings

        document = self.final()
        body = voucher_body(document, content_of(document), AccountingSettings.load(), contact_id="")
        self.assertEqual(body["totalGrossAmount"], 920.0 if isinstance(body["totalGrossAmount"], float) else "920.00")

    def test_a_part_invoice_cannot_be_cancelled_or_credited_under_a_final_invoice(self) -> None:
        final = self.final()
        with self.assertRaises(ValidationError) as caught:
            services.cancel_invoice(self.first)
        self.assertIn(final.number, " ".join(caught.exception.messages))
        with self.assertRaises(ValidationError):
            billing.credit_invoice(self.first, percent=D("10"))
        # the final invoice is cancelled first – then the parts are free again
        services.cancel_invoice(final)
        self.assertFalse(invoice_reminders.invoices_of(self.project).exists())
        services.cancel_invoice(self.first)
        self.assertEqual(billing.state_of(self.project).billed_net, D("400.00"))

    def test_a_cancelled_final_invoice_cancels_the_deductions_too(self) -> None:
        final = self.final()
        cancellation = services.cancel_invoice(final)
        content = content_of(cancellation)
        self.assertEqual(
            content.billed_gross if hasattr(content, "billed_gross") else content.booked_gross_total, D("-920.00")
        )
        self.assertEqual(content.payable_total, D("-920.00"))
        # the part invoices are open for a new final invoice
        again = self.final()
        self.assertEqual(content_of(again).payable_total, D("920.00"))

    def test_a_credit_for_a_part_invoice_reduces_what_is_deducted(self) -> None:
        # not possible under a final invoice; before one, the credited amount is no longer deducted
        credit = billing.credit_invoice(self.second, amount=D("100.00"), note="Aufbau entfällt teilweise")
        self.assertEqual(credit.credit_for_id, self.second.pk)
        self.assertEqual(credit.billing_type, BillingType.CREDIT)
        self.assertEqual(billing.state_of(self.project).billed_net, D("600.00"))
        content = content_of(self.final())
        self.assertEqual(content.deductions[1].net, D("300.00"))
        self.assertEqual(content.payable_total, D("1725.00") - D("345.00") - D("345.00"))


class OverbilledTests(RentalarsTestCase):
    """When the project becomes cheaper than what was billed on account."""

    def test_the_final_invoice_would_be_negative(self) -> None:
        from rentalars.projects.models import MaterialLine

        project = project_with_two_rates()
        services.create_document(project, DocumentKind.INVOICE, billing=Billing(type="advance", percent=D("100")))
        MaterialLine.objects.filter(project=project, title="Licht").delete()
        with self.assertRaises(ValidationError):
            services.create_document(project, DocumentKind.INVOICE, billing=Billing(type="final"))


class PartialCreditTests(RentalarsTestCase):
    """Partial credit notes: several, never more than the invoice, cancelling what is left."""

    def setUp(self) -> None:
        super().setUp()
        self.project = project_with_two_rates()
        self.invoice = services.create_document(self.project, DocumentKind.INVOICE)

    def test_a_credit_note_has_negative_amounts_and_names_the_invoice(self) -> None:
        credit = billing.credit_invoice(self.invoice, percent=D("10"), note="Rabatt")
        content = content_of(credit)
        self.assertEqual(credit.kind, DocumentKind.CANCELLATION)
        self.assertEqual(credit.credit_for_id, self.invoice.pk)
        self.assertIsNone(credit.cancels_id)
        self.assertEqual(content.cancels_number, self.invoice.number)
        self.assertEqual(
            (content.net_total, content.tax_total, content.gross_total), (D("-150.00"), D("-22.50"), D("-172.50"))
        )
        self.assertTrue(credit.xml_file)
        self.assertIn("-150.00", credit.xml_file.read().decode().replace("−", "-"))
        self.invoice.refresh_from_db()
        self.assertIsNone(self.invoice.cancelled_by_id)  # the invoice stays valid
        self.assertTrue(invoice_reminders.invoices_of(self.project).exists())

    def test_credits_never_exceed_the_invoice(self) -> None:
        billing.credit_invoice(self.invoice, percent=D("60"))
        billing.credit_invoice(self.invoice, amount=D("500.00"))
        with self.assertRaises(ValidationError):
            billing.credit_invoice(self.invoice, amount=D("100.01"))
        remaining = sum(rate.net for rate in billing.effective_rates(self.invoice)[0].values())
        self.assertEqual(remaining, D("100.00"))

    def test_cancelling_an_invoice_with_credits_cancels_the_remainder(self) -> None:
        first = billing.credit_invoice(self.invoice, percent=D("25"))
        cancellation = services.cancel_invoice(self.invoice)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.cancelled_by_id, cancellation.pk)
        self.assertEqual(cancellation.cancels_id, self.invoice.pk)
        self.assertEqual(content_of(cancellation).net_total, D("-1125.00"))
        total = sum(
            (document.net_total for document in (self.invoice, first, cancellation)),
            D("0"),
        )
        self.assertEqual(total, D("0"))
        # the project can be invoiced anew
        self.assertFalse(invoice_reminders.invoices_of(self.project).exists())

    def test_only_valid_invoices_are_credited(self) -> None:
        cancellation = services.cancel_invoice(self.invoice)
        self.invoice.refresh_from_db()
        with self.assertRaises(ValidationError):
            billing.credit_invoice(self.invoice, percent=D("10"))
        with self.assertRaises(ValidationError):
            billing.credit_invoice(cancellation, percent=D("10"))

    def test_credits_are_refused_while_invoices_are_off(self) -> None:
        from rentalars.core.models import SystemSettings

        settings_row = SystemSettings.load()
        settings_row.invoices_enabled = False
        settings_row.save()
        with self.assertRaises(ValidationError):
            billing.credit_invoice(self.invoice, percent=D("10"))


class ReviewFindingsTests(RentalarsTestCase):
    """What the independent review found: credit in full, cents of the tax, sums, remainders."""

    def setUp(self) -> None:
        super().setUp()
        self.project = project_with_two_rates()

    def test_crediting_everything_is_the_cancellation(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        credit = billing.credit_invoice(invoice, percent=D("100"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.cancelled_by_id, credit.pk)
        self.assertEqual(credit.cancels_id, invoice.pk)
        self.assertEqual(content_of(credit).net_total, D("-1500.00"))
        services.create_document(self.project, DocumentKind.INVOICE)  # the project can be invoiced anew

    def test_crediting_the_rest_after_credits_is_the_cancellation_too(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        first = billing.credit_invoice(invoice, percent=D("60"))
        last = billing.credit_invoice(invoice, amount=D("600.00"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.cancelled_by_id, last.pk)
        total = sum((document.net_total for document in (invoice, first, last)), D("0"))
        self.assertEqual(total, D("0"))
        with self.assertRaises(ValidationError):
            billing.credit_invoice(invoice, amount=D("1.00"))

    def test_the_tax_of_every_part_invoice_is_net_times_the_rate_rounded(self) -> None:
        amounts = [D("333.33")] * 4 + [D("166.68")]
        for amount in amounts:
            content = content_of(
                services.create_document(
                    self.project, DocumentKind.INVOICE, billing=Billing(type=BillingType.PARTIAL, amount=amount)
                )
            )
            for share in content.taxes:
                self.assertEqual(share.tax, (share.net * share.percent / D(100)).quantize(D("0.01"), "ROUND_HALF_UP"))
        self.assertEqual(billing.state_of(self.project).remaining_net, D("0.00"))

    def test_the_sums_of_the_outgoing_documents_count_the_advance_once(self) -> None:
        from rentalars.documents import outgoing

        services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type="advance", percent=D("20")))
        services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type="final"))
        bookable = outgoing.totals(Document.objects.all()).bookable
        self.assertIsNone(bookable)  # no cancellation yet: the invoices alone
        kinds = {entry.kind: entry for entry in outgoing.totals(Document.objects.all()).kinds}
        self.assertEqual(kinds[DocumentKind.INVOICE].net, D("1500.00"))
        self.assertEqual(kinds[DocumentKind.INVOICE].gross, D("1725.00"))

    def test_the_cancellation_of_a_remainder_hands_the_statement_back(self) -> None:
        from unittest import mock

        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        billing.credit_invoice(invoice, percent=D("10"))
        with mock.patch("rentalars.documents.statements.invoice_cancelled") as hook:
            services.cancel_invoice(invoice)
        self.assertEqual(hook.call_count, 1)

    def test_the_cancellation_of_a_final_invoice_with_a_negative_rate_adds_up_to_nothing(self) -> None:
        from rentalars.projects.models import MaterialLine

        reduced = TaxRate.objects.get(name="7 %")
        services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type="advance", percent=D("50")))
        MaterialLine.objects.filter(project=self.project, title="Licht").delete()  # no 19 % any more
        add_line(
            self.project,
            make_product("T-102", "Zusatz", price="1500.00", billing_mode=BillingMode.FLAT, tax_rate=reduced),
            1,
        )
        final = services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type="final"))
        by_rate = {share.percent: share.net for share in content_of(final).booked_taxes}
        self.assertLess(by_rate[D("19.00")], 0)  # the advance billed more 19 % than the project has left
        credit = billing.credit_invoice(final, amount=D("10.00"))
        cancellation = services.cancel_invoice(final)
        books = [content_of(document) for document in (final, credit, cancellation)]
        self.assertEqual(sum((c.booked_gross_total for c in books), D("0")), D("0"))
        self.assertEqual(sum((c.booked_tax_total for c in books), D("0")), D("0"))
        self.assertGreaterEqual(min(p.unit_price for p in content_of(cancellation).positions), 0)  # BR-27
