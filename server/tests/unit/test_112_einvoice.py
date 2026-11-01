# SPDX-License-Identifier: GPL-3.0-or-later
"""The check of e-invoices against the rules (DOK-042) and ZUGFeRD / Factur-X (DOK-049, DOK-044).

The requirement: own core checks – Rentalars checks its own invoices and the incoming ones against EN 16931 and the XRechnung.

* Everything Rentalars writes passes its own check – ordinary, advance, partial and final invoice, partial credit note,
  cancellation – in both formats; a finding in these tests would be a bug of the writer or of the rule.
* A file that breaks a rule is told so, with the rule; the check is a finding, not a refusal, unless the setting says so.
* The format ZUGFeRD makes the stored PDF a PDF/A-3 with the CII inside; its checksum is that of this file.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext
from pypdf import PdfReader

from rentalars.documents import billing, einvoice_check, einvoice_rules, services
from rentalars.documents.billing import Billing
from rentalars.documents.models import (
    AccountingSettings,
    BillingType,
    Document,
    DocumentCheck,
    DocumentKind,
    InvoiceFormat,
)
from rentalars.incoming import services as incoming_services
from tests.unit.test_060_accounting import AccountingCase

D = Decimal


def rules_of(report: einvoice_rules.Report) -> set[str]:
    return {finding.rule for finding in report.findings}


def broken(xml: bytes, old: str, new: str) -> bytes:
    text = xml.decode("utf-8")
    assert text.count(old) >= 1, old
    return text.replace(old, new, 1).encode("utf-8")


class OwnInvoicesPass(AccountingCase):
    """Every kind of invoice Rentalars writes, in UBL and in CII."""

    def use(self, invoice_format: str) -> None:
        row = AccountingSettings.load()
        row.invoice_format = invoice_format
        row.save()

    def assert_clean(self, document: Document, invoice_format: str) -> None:
        check = einvoice_check.check_of(document)
        self.assertIsNotNone(check, document.number)
        assert check is not None
        self.assertEqual([(f["rule"], f["message"]) for f in check.findings], [], f"{document.number} {document.title}")
        again = einvoice_check.recheck(document)
        self.assertEqual((again.error_count, again.warning_count), (0, 0))
        self.assertEqual(again.syntax, "UBL" if invoice_format == InvoiceFormat.XRECHNUNG else "CII")

    def ordinary_and_cancellation(self, invoice_format: str) -> None:
        self.use(invoice_format)
        invoice = self.invoice()
        self.assert_clean(invoice, invoice_format)
        self.assert_clean(services.cancel_invoice(invoice), invoice_format)

    def parts(self, invoice_format: str) -> None:
        self.use(invoice_format)
        advance = services.create_document(
            self.project, DocumentKind.INVOICE, billing=Billing(type=BillingType.ADVANCE, percent=D("20"))
        )
        partial = services.create_document(
            self.project, DocumentKind.INVOICE, billing=Billing(type=BillingType.PARTIAL, amount=D("60.00"))
        )
        final = services.create_document(self.project, DocumentKind.INVOICE, billing=Billing(type=BillingType.FINAL))
        for document in (advance, partial, final):
            self.assert_clean(document, invoice_format)
        credit = billing.credit_invoice(final, amount=D("10.00"), note="Preisnachlass")
        self.assert_clean(credit, invoice_format)

    def test_ordinary_invoice_and_cancellation_in_xrechnung(self) -> None:
        self.ordinary_and_cancellation(InvoiceFormat.XRECHNUNG)

    def test_ordinary_invoice_and_cancellation_in_zugferd(self) -> None:
        self.ordinary_and_cancellation(InvoiceFormat.ZUGFERD)

    def test_advance_partial_final_and_credit_in_xrechnung(self) -> None:
        self.parts(InvoiceFormat.XRECHNUNG)

    def test_advance_partial_final_and_credit_in_zugferd(self) -> None:
        self.parts(InvoiceFormat.ZUGFERD)


class RulesTests(AccountingCase):
    """Files that break a rule are told so – the rule, what is wrong."""

    def setUp(self) -> None:
        super().setUp()
        self.xml = self.invoice().xml_file.read()

    def check(self, data: bytes) -> einvoice_rules.Report:
        return einvoice_rules.check(data)

    def test_the_file_as_written_has_no_finding(self) -> None:
        report = self.check(self.xml)
        self.assertEqual((report.syntax, report.profile), ("UBL", "XRechnung"))
        self.assertEqual(report.findings, [])

    def test_a_missing_buyer_reference_and_a_wrong_type_code(self) -> None:
        data = broken(self.xml, "<cbc:BuyerReference>", "<cbc:Foo>").replace(b"</cbc:BuyerReference>", b"</cbc:Foo>")
        self.assertIn("BR-DE-15", rules_of(self.check(data)))
        data = broken(self.xml, "<cbc:InvoiceTypeCode>380<", "<cbc:InvoiceTypeCode>999<")
        self.assertIn("BR-DE-17", rules_of(self.check(data)))

    def test_the_sums(self) -> None:
        data = broken(
            self.xml,
            '<cbc:TaxInclusiveAmount currencyID="EUR">291.50',
            '<cbc:TaxInclusiveAmount currencyID="EUR">292.50',
        )
        self.assertIn("BR-CO-15", rules_of(self.check(data)))
        data = broken(
            self.xml, '<cbc:PayableAmount currencyID="EUR">291.50', '<cbc:PayableAmount currencyID="EUR">290.50'
        )
        self.assertIn("BR-CO-16", rules_of(self.check(data)))
        data = broken(
            self.xml,
            '<cbc:LineExtensionAmount currencyID="EUR">250.00</cbc:LineExtensionAmount>\n    <cbc:TaxExclusiveAmount',
            '<cbc:LineExtensionAmount currencyID="EUR">251.00</cbc:LineExtensionAmount>\n    <cbc:TaxExclusiveAmount',
        )
        self.assertIn("BR-CO-10", rules_of(self.check(data)))
        data = broken(self.xml, '<cbc:TaxAmount currencyID="EUR">38.00', '<cbc:TaxAmount currencyID="EUR">39.00')
        found = rules_of(self.check(data))
        self.assertIn("BR-CO-17", found)

    def test_tax_rounding_of_one_cent_is_not_an_error(self) -> None:
        # 19 % of 200.00 is 38.00; 38.01 is a cent off – tolerated; the sums then differ by a cent as well (BR-CO-14, -15)
        data = broken(self.xml, '<cbc:TaxAmount currencyID="EUR">38.00', '<cbc:TaxAmount currencyID="EUR">38.01')
        self.assertNotIn("BR-CO-17", rules_of(self.check(data)))

    def test_payment_and_seller(self) -> None:
        data = broken(self.xml, "DE02120300000000202051", "DE02120300000000202052")
        report = self.check(data)
        self.assertEqual([f.rule for f in report.warnings], ["PLAUSI-IBAN"])
        self.assertTrue(report.ok)  # a warning, not an error
        data = self.xml.replace(b"<cbc:PaymentMeansCode>58<", b"<cbc:PaymentMeansCode>58<").replace(
            b"<cbc:ID>DE02120300000000202051</cbc:ID>", b"<cbc:ID></cbc:ID>"
        )
        self.assertIn("BR-50", rules_of(self.check(data)))
        data = broken(self.xml, "<cbc:CompanyID>DE999999999", "<cbc:CompanyID>999999999")
        self.assertIn("BR-CO-09", rules_of(self.check(data)))

    def test_no_due_date_and_no_term(self) -> None:
        text = self.xml.decode("utf-8")
        start = text.index("<cac:PaymentTerms>")
        end = text.index("</cac:PaymentTerms>") + len("</cac:PaymentTerms>")
        text = text[:start] + text[end:]
        if "<cbc:DueDate>" in text:
            a = text.index("<cbc:DueDate>")
            text = text[:a] + text[text.index("</cbc:DueDate>") + len("</cbc:DueDate>") :]
        self.assertIn("BR-CO-25", rules_of(self.check(text.encode())))

    def test_mandatory_parts_of_a_foreign_file(self) -> None:
        report = self.check(
            b'<?xml version="1.0"?><Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>'
        )
        found = rules_of(report)
        for rule in ("BR-01", "BR-02", "BR-03", "BR-04", "BR-05", "BR-06", "BR-07", "BR-12", "BR-16", "BR-CO-18"):
            self.assertIn(rule, found)
        self.assertFalse(report.ok)

    def test_a_category_without_a_breakdown_and_a_wrong_basis(self) -> None:
        text = self.xml.decode("utf-8")
        data = text.replace(
            '<cbc:TaxableAmount currencyID="EUR">200.00', '<cbc:TaxableAmount currencyID="EUR">210.00', 1
        ).encode()
        self.assertIn("BR-S-08", rules_of(self.check(data)))

    def test_an_exemption_needs_a_reason(self) -> None:
        text = (
            self.xml.decode("utf-8")
            .replace("<cbc:TaxExemptionReason>", "<cbc:Note>")
            .replace("</cbc:TaxExemptionReason>", "</cbc:Note>")
        )
        if "<cbc:ID>E</cbc:ID>" not in text:  # the project of the case has no exempt position: make one
            text = text.replace("<cbc:ID>S</cbc:ID>", "<cbc:ID>E</cbc:ID>")
        self.assertIn("BR-E-10", rules_of(self.check(text.encode())))

    def test_unsafe_and_foreign_xml_are_a_finding_not_an_exception(self) -> None:
        for data in (b"<a/>", b"not xml", b'<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>'):
            report = self.check(data)
            self.assertEqual([f.rule for f in report.findings], ["XML"])
            self.assertFalse(report.ok)

    def test_iban_check_digits(self) -> None:
        self.assertTrue(einvoice_rules.iban_valid("DE02 1203 0000 0000 2020 51"))
        self.assertFalse(einvoice_rules.iban_valid("DE02120300000000202052"))
        self.assertFalse(einvoice_rules.iban_valid("DE0"))

    def test_the_result_is_json(self) -> None:
        data = self.check(
            self.xml.replace(b"<cbc:BuyerReference>", b"<cbc:Foo>").replace(b"</cbc:BuyerReference>", b"</cbc:Foo>")
        ).as_json()
        self.assertEqual((data["ok"], data["errors"], data["ruleset"]), (False, 1, einvoice_rules.RULESET))
        self.assertEqual(data["findings"][0]["rule"], "BR-DE-15")


class StoredResultTests(AccountingCase):
    def test_the_result_is_kept_beside_the_document_and_repeated(self) -> None:
        document = self.invoice()
        check = DocumentCheck.objects.get(document=document)
        self.assertTrue(check.ok)
        self.assertEqual((check.syntax, check.profile, check.ruleset), ("UBL", "XRechnung", einvoice_rules.RULESET))
        again = einvoice_check.recheck(document)
        self.assertEqual(again.pk, check.pk)  # one per document
        self.assertGreaterEqual(again.checked_at, check.checked_at)

    def test_a_document_without_an_e_invoice_cannot_be_checked(self) -> None:
        offer = services.create_document(self.project, DocumentKind.OFFER)
        with self.assertRaises(ValidationError):
            einvoice_check.recheck(offer)
        self.assertFalse(DocumentCheck.objects.filter(document=offer).exists())

    def test_the_setting_can_stop_an_invoice_with_errors(self) -> None:
        # BR-DE-15 is always met by the writer, so break the writer for this test
        row = AccountingSettings.load()
        row.einvoice_blocks = True
        row.save()
        from unittest import mock

        from rentalars.documents import xrechnung

        real = xrechnung.build_xml

        def without_reference(content: Any) -> bytes:
            return (
                real(content)
                .replace(b"<cbc:BuyerReference>", b"<cbc:Foo>")
                .replace(b"</cbc:BuyerReference>", b"</cbc:Foo>")
            )

        # create_document imports build_xml inside the function: patch the module it imports from
        with mock.patch.object(xrechnung, "build_xml", without_reference), self.assertRaises(ValidationError):
            services.create_document(self.project, DocumentKind.INVOICE)
        self.assertFalse(Document.objects.filter(kind=DocumentKind.INVOICE).exists())
        # switched off, the same invoice is made and the finding kept
        row.einvoice_blocks = False
        row.save()
        with mock.patch.object(xrechnung, "build_xml", without_reference):
            document = services.create_document(self.project, DocumentKind.INVOICE)
        check = DocumentCheck.objects.get(document=document)
        self.assertEqual([f["rule"] for f in check.findings], ["BR-DE-15"])


class ZugferdTests(AccountingCase):
    def setUp(self) -> None:
        super().setUp()
        row = AccountingSettings.load()
        row.invoice_format = InvoiceFormat.ZUGFERD
        row.save()

    def test_the_stored_pdf_is_a_pdf_a_3_with_the_invoice_inside(self) -> None:
        document = self.invoice()
        self.assertEqual((document.einvoice_format, document.einvoice_syntax), ("zugferd", "zugferd"))
        pdf = document.file.read()
        import hashlib

        self.assertEqual(
            document.sha256, hashlib.sha256(pdf).hexdigest()
        )  # DOK-007: the checksum is that of the hybrid
        self.assertTrue(services.verify(document))
        reader = PdfReader(io.BytesIO(pdf))
        attachments = reader.attachments
        self.assertEqual(list(attachments), ["factur-x.xml"])
        embedded = attachments["factur-x.xml"][0]
        self.assertEqual(embedded, document.xml_file.read())  # the XML download is the embedded one
        root = reader.trailer["/Root"]
        files = root["/AF"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].get_object()["/AFRelationship"], "/Alternative")
        xmp = root["/Metadata"].get_object().get_data().decode("utf-8")
        for needle in (
            'pdfaid:part="3"',
            'pdfaid:conformance="B"',
            "<fx:DocumentType>INVOICE</fx:DocumentType>",
            "<fx:DocumentFileName>factur-x.xml</fx:DocumentFileName>",
            "<fx:ConformanceLevel>EN 16931</fx:ConformanceLevel>",
            "pdfaSchema:namespaceURI",
        ):
            self.assertIn(needle, xmp)
        self.assertEqual(xmp.count("</rdf:RDF>"), 1)
        self.assertIn("/OutputIntents", root)
        text = " ".join(page.extract_text() for page in reader.pages)
        self.assertIn(document.number, text)

    def test_the_check_reads_the_cii(self) -> None:
        document = self.invoice()
        check = DocumentCheck.objects.get(document=document)
        self.assertEqual((check.syntax, check.findings), ("CII", []))
        self.assertEqual(check.profile, "EN 16931")

    def test_the_pdf_is_read_as_an_incoming_invoice(self) -> None:
        """The loop: a ZUGFeRD PDF of Rentalars is an e-invoice for the register of incoming invoices."""
        from rentalars.incoming import einvoice

        document = self.invoice()
        parsed = einvoice.parse(einvoice.xml_in_pdf(document.file.read()) or b"")
        self.assertEqual((parsed.number, parsed.total_gross), (document.number, D("291.50")))
        self.assertEqual(parsed.profile, "EN 16931")

    def test_a_cancellation_follows_the_format(self) -> None:
        invoice = self.invoice()
        cancellation = services.cancel_invoice(invoice)
        self.assertEqual(cancellation.einvoice_format, "zugferd")
        xml = cancellation.xml_file.read()
        self.assertIn(b"<ram:TypeCode>384</ram:TypeCode>", xml)
        self.assertIn(b"<ram:IssuerAssignedID>" + invoice.number.encode() + b"</ram:IssuerAssignedID>", xml)

    def test_other_documents_stay_plain(self) -> None:
        offer = services.create_document(self.project, DocumentKind.OFFER)
        self.assertEqual((offer.einvoice_format, offer.einvoice_syntax), ("", ""))
        self.assertFalse(offer.xml_file)
        self.assertEqual(len(PdfReader(io.BytesIO(offer.file.read())).attachments), 0)

    def test_the_format_of_old_documents_is_what_they_were(self) -> None:
        row = AccountingSettings.load()
        row.invoice_format = InvoiceFormat.XRECHNUNG
        row.save()
        document = self.invoice()
        self.assertEqual(document.einvoice_syntax, "xrechnung")
        self.assertEqual(len(PdfReader(io.BytesIO(document.file.read())).attachments), 0)
        Document.objects.filter(pk=document.pk).update(einvoice_format="")  # as made earlier
        document.refresh_from_db()
        self.assertEqual(document.einvoice_syntax, "xrechnung")


class IncomingCheckTests(AccountingCase):
    def test_an_uploaded_e_invoice_is_checked_and_nothing_is_refused(self) -> None:
        from tests.unit.test_110_einvoice_in import ubl

        upload = SimpleUploadedFile("re.xml", ubl(), content_type="text/xml")
        invoice = incoming_services.create_from_upload(upload, user=self.user)
        check = invoice.einvoice_check
        self.assertFalse(check["ok"])  # the sample lacks addresses and a contact
        self.assertIn("BR-08", {finding["rule"] for finding in check["findings"]})
        self.assertEqual(check["syntax"], "UBL")
        again = einvoice_check.recheck_incoming(invoice)
        self.assertEqual(again["errors"], check["errors"])

    def test_an_invoice_without_xml_cannot_be_checked(self) -> None:
        from tests.unit.test_091_purchase import pdf_of

        upload = SimpleUploadedFile("re.pdf", pdf_of("Rechnung 4711"), content_type="application/pdf")
        invoice = incoming_services.create_from_upload(upload, user=self.user, read=False)
        self.assertEqual(invoice.einvoice_check, {})
        with self.assertRaises(ValidationError):
            einvoice_check.recheck_incoming(invoice)


class SendingTests(AccountingCase):
    """DOK-044: what goes out with the mail – the XML along with an XRechnung, not apart from a ZUGFeRD PDF."""

    def use(self, invoice_format: str) -> None:
        row = AccountingSettings.load()
        row.invoice_format = invoice_format
        row.save()

    def test_xrechnung_goes_out_with_its_xml(self) -> None:
        from rentalars.documents import free_mail
        from rentalars.mail import sending

        self.use(InvoiceFormat.XRECHNUNG)
        document = self.invoice()
        self.assertFalse(free_mail.initial_for(document)["xml"])  # chosen, not preselected, without a buyer reference
        self.customer.buyer_reference = "04011000-12345-34"  # the Leitweg-ID of an authority
        self.customer.save()
        document = Document.objects.get(pk=document.pk)
        self.assertTrue(free_mail.initial_for(document)["xml"])
        from tests.helpers import ALL_RIGHTS

        labels = dict(sending.document_choices(ALL_RIGHTS, self.project, self.user))
        self.assertIn("(XRechnung)", labels[f"xml:{document.pk}"])

    def test_a_zugferd_pdf_goes_out_alone(self) -> None:
        from rentalars.documents import free_mail

        self.use(InvoiceFormat.ZUGFERD)
        document = self.invoice()
        self.assertFalse(free_mail.initial_for(document)["xml"])
        form = free_mail.SendForm(document=document)
        self.assertIn("xml", form.fields)  # it can still be chosen
        self.assertEqual(str(form.fields["xml"].label), gettext("Send the XML of the invoice apart, too"))
        from rentalars.mail import sending
        from tests.helpers import ALL_RIGHTS

        labels = dict(sending.document_choices(ALL_RIGHTS, self.project, self.user))
        self.assertIn("ZUGFeRD XML", labels[f"xml:{document.pk}"])
