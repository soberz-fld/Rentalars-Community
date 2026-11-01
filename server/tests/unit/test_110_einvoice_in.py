# SPDX-License-Identifier: GPL-3.0-or-later
"""Incoming e-invoices – XRechnung (UBL, CII) and ZUGFeRD / Factur-X are imported, read and shown (DOK-040, DOK-041).

The requirement: incoming e-invoices (XML/XRechnung and ZUGFeRD) are imported, read and shown (before, only PDF and
pictures).

* UBL ``Invoice`` / ``CreditNote`` and CII are read exactly, without AI: head, positions, discounts and surcharges.
* A PDF with an XML attached (ZUGFeRD / Factur-X) is read from the XML; the PDF stays the original, the XML is kept.
* Unsafe or foreign XML (DTD, entities, broken, not an invoice) is refused; the sums are compared with themselves.
* Pages and API: the format is shown, the XML is a download, every new operation is reached (API-014).
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.ai.models import AICall
from rentalars.incoming import einvoice, services
from rentalars.incoming.models import IncomingInvoice, PositionType, ReadingState
from rentalars.masterdata.models import Supplier
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase
from tests.ui.base import UiTestCase
from tests.unit.test_091_purchase import FilesMixin, pdf_of
from tests.unit.test_100_incoming import INCOMING_LINES

UBL_NS = (
    'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
    'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"'
)
CREDIT_NS = UBL_NS.replace("Invoice-2", "CreditNote-2")


def ubl(
    *,
    credit: bool = False,
    lines_total: str = "347.00",
    net: str = "367.00",
    tax: str = "69.73",
    gross: str = "436.73",
    customization: str = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
    extra: str = "",
) -> bytes:
    """A UBL invoice (XRechnung): 3 microphones at 99.00, 2 cables at 25.00, freight 30.00 and a discount of 10.00."""
    root = "CreditNote" if credit else "Invoice"
    ns = CREDIT_NS if credit else UBL_NS
    line = "CreditNoteLine" if credit else "InvoiceLine"
    quantity = "CreditedQuantity" if credit else "InvoicedQuantity"
    type_code = (
        "<cbc:CreditNoteTypeCode>381</cbc:CreditNoteTypeCode>"
        if credit
        else "<cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>"
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<{root} {ns}>
  <cbc:CustomizationID>{customization}</cbc:CustomizationID>
  <cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>
  <cbc:ID>RE-2027-0815</cbc:ID>
  <cbc:IssueDate>2027-02-22</cbc:IssueDate>
  <cbc:DueDate>2027-03-22</cbc:DueDate>
  {type_code}
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cbc:BuyerReference>04011000-12345-34</cbc:BuyerReference>
  <cac:OrderReference><cbc:ID>B-4711</cbc:ID></cac:OrderReference>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PartyName><cbc:Name>Muster</cbc:Name></cac:PartyName>
    <cac:PartyTaxScheme><cbc:CompanyID>DE123456789</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
    <cac:PartyLegalEntity><cbc:RegistrationName>Musikhaus Muster GmbH &amp; Co. KG</cbc:RegistrationName></cac:PartyLegalEntity>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:PaymentMeans><cbc:PaymentMeansCode>58</cbc:PaymentMeansCode>
    <cac:PayeeFinancialAccount><cbc:ID>DE02 1203 0000 0000 2020 51</cbc:ID></cac:PayeeFinancialAccount></cac:PaymentMeans>
  <cac:AllowanceCharge><cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>Treuerabatt</cbc:AllowanceChargeReason><cbc:Amount currencyID="EUR">10.00</cbc:Amount>
    <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory></cac:AllowanceCharge>
  <cac:AllowanceCharge><cbc:ChargeIndicator>true</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>Fracht und Verpackung</cbc:AllowanceChargeReason><cbc:Amount currencyID="EUR">30.00</cbc:Amount>
    <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory></cac:AllowanceCharge>
  <cac:TaxTotal><cbc:TaxAmount currencyID="EUR">{tax}</cbc:TaxAmount></cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="EUR">{lines_total}</cbc:LineExtensionAmount>
    <cbc:AllowanceTotalAmount currencyID="EUR">10.00</cbc:AllowanceTotalAmount>
    <cbc:ChargeTotalAmount currencyID="EUR">30.00</cbc:ChargeTotalAmount>
    <cbc:TaxExclusiveAmount currencyID="EUR">{net}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="EUR">{gross}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="EUR">{gross}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:{line}><cbc:ID>1</cbc:ID><cbc:{quantity} unitCode="C62">3</cbc:{quantity}>
    <cbc:LineExtensionAmount currencyID="EUR">297.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Shure SM58</cbc:Name><cac:SellersItemIdentification><cbc:ID>SM58-X</cbc:ID></cac:SellersItemIdentification>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="EUR">99.00</cbc:PriceAmount></cac:Price></cac:{line}>
  <cac:{line}><cbc:ID>2</cbc:ID><cbc:{quantity} unitCode="C62">2</cbc:{quantity}>
    <cbc:LineExtensionAmount currencyID="EUR">50.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Neutrik NL4 Kabel 10 m</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="EUR">25.00</cbc:PriceAmount></cac:Price></cac:{line}>
  {extra}
</{root}>""".encode()


CII_NS = (
    'xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" '
    'xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" '
    'xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"'
)


def cii(
    *,
    guideline: str = "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:en16931",
    lines: bool = True,
    gross: str = "448.63",
) -> bytes:
    """A CII invoice (ZUGFeRD EN 16931 / Factur-X): 3 microphones and 2 cables, freight 30.00 as a surcharge."""
    items = (
        """
  <ram:IncludedSupplyChainTradeLineItem>
    <ram:AssociatedDocumentLineDocument><ram:LineID>1</ram:LineID></ram:AssociatedDocumentLineDocument>
    <ram:SpecifiedTradeProduct><ram:SellerAssignedID>SM58-X</ram:SellerAssignedID><ram:Name>Shure SM58</ram:Name></ram:SpecifiedTradeProduct>
    <ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice><ram:ChargeAmount>99.00</ram:ChargeAmount></ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement>
    <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="C62">3</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
    <ram:SpecifiedLineTradeSettlement><ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>19.00</ram:RateApplicablePercent></ram:ApplicableTradeTax>
      <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>297.00</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation></ram:SpecifiedLineTradeSettlement>
  </ram:IncludedSupplyChainTradeLineItem>
  <ram:IncludedSupplyChainTradeLineItem>
    <ram:AssociatedDocumentLineDocument><ram:LineID>2</ram:LineID></ram:AssociatedDocumentLineDocument>
    <ram:SpecifiedTradeProduct><ram:Name>Neutrik NL4 Kabel 10 m</ram:Name></ram:SpecifiedTradeProduct>
    <ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice><ram:ChargeAmount>25.00</ram:ChargeAmount></ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement>
    <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="C62">2</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
    <ram:SpecifiedLineTradeSettlement><ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>19.00</ram:RateApplicablePercent></ram:ApplicableTradeTax>
      <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>50.00</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation></ram:SpecifiedLineTradeSettlement>
  </ram:IncludedSupplyChainTradeLineItem>"""
        if lines
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice {CII_NS}>
  <rsm:ExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>{guideline}</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter></rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument><ram:ID>RE-2027-0815</ram:ID><ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime><udt:DateTimeString format="102">20270222</udt:DateTimeString></ram:IssueDateTime></rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>{items}
    <ram:ApplicableHeaderTradeAgreement>
      <ram:BuyerReference>991-01234-77</ram:BuyerReference>
      <ram:SellerTradeParty><ram:Name>Musikhaus Muster GmbH &amp; Co. KG</ram:Name>
        <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">DE123456789</ram:ID></ram:SpecifiedTaxRegistration></ram:SellerTradeParty>
      <ram:BuyerOrderReferencedDocument><ram:IssuerAssignedID>B-4711</ram:IssuerAssignedID></ram:BuyerOrderReferencedDocument>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>58</ram:TypeCode>
        <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>DE02120300000000202051</ram:IBANID></ram:PayeePartyCreditorFinancialAccount></ram:SpecifiedTradeSettlementPaymentMeans>
      <ram:SpecifiedTradeAllowanceCharge><ram:ChargeIndicator><udt:Indicator>true</udt:Indicator></ram:ChargeIndicator>
        <ram:ActualAmount>30.00</ram:ActualAmount><ram:Reason>Fracht und Verpackung</ram:Reason>
        <ram:CategoryTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>S</ram:CategoryCode><ram:RateApplicablePercent>19.00</ram:RateApplicablePercent></ram:CategoryTradeTax></ram:SpecifiedTradeAllowanceCharge>
      <ram:SpecifiedTradePaymentTerms><ram:DueDateDateTime><udt:DateTimeString format="102">20270322</udt:DateTimeString></ram:DueDateDateTime></ram:SpecifiedTradePaymentTerms>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>347.00</ram:LineTotalAmount><ram:ChargeTotalAmount>30.00</ram:ChargeTotalAmount>
        <ram:TaxBasisTotalAmount>377.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">71.63</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>{gross}</ram:GrandTotalAmount><ram:DuePayableAmount>{gross}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>""".encode()


def xml_upload(content: bytes, name: str = "rechnung.xml") -> SimpleUploadedFile:
    """An uploaded XML e-invoice."""
    return SimpleUploadedFile(name, content, "application/xml")


def zugferd_pdf(
    xml: bytes | None = None, *, name: str = "factur-x.xml", lines: tuple[str, ...] = INCOMING_LINES
) -> bytes:
    """A PDF with a text layer and an XML attached – as ZUGFeRD / Factur-X invoices come."""
    from pypdf import PdfWriter

    writer = PdfWriter(clone_from=io.BytesIO(pdf_of(lines)))
    writer.add_attachment(name, xml if xml is not None else cii())
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def pdf_upload(content: bytes, name: str = "zugferd.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, "application/pdf")


XXE = b"""<?xml version="1.0"?>
<!DOCTYPE Invoice [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"><ID>&xxe;</ID></Invoice>"""

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"><ID>&lol3;</ID></Invoice>"""


class ParserTests(RentalarsTestCase):
    """The reading itself: fields, profiles, credit notes, checks and the refusals."""

    def test_ubl_is_read_with_everything_the_register_needs(self) -> None:
        found = einvoice.parse(ubl())
        self.assertEqual((found.syntax, found.document, found.type_code), ("ubl", "invoice", "380"))
        self.assertEqual(found.profile, "XRechnung")
        self.assertEqual(
            (found.number, str(found.issue_date), str(found.due_date), found.currency),
            ("RE-2027-0815", "2027-02-22", "2027-03-22", "EUR"),
        )
        self.assertEqual(
            (found.supplier_name, found.supplier_vat_id), ("Musikhaus Muster GmbH & Co. KG", "DE123456789")
        )
        self.assertEqual(found.iban, "DE02120300000000202051")
        self.assertEqual((found.buyer_reference, found.order_reference), ("04011000-12345-34", "B-4711"))
        self.assertEqual(
            (found.total_net, found.total_tax, found.total_gross),
            (Decimal("367.00"), Decimal("69.73"), Decimal("436.73")),
        )
        self.assertEqual([(line.name, line.quantity, line.unit_price, line.net, line.tax_rate) for line in found.lines], [
            ("Shure SM58", Decimal(3), Decimal("99.00"), Decimal("297.00"), Decimal(19)),
            ("Neutrik NL4 Kabel 10 m", Decimal(2), Decimal("25.00"), Decimal("50.00"), Decimal(19)),
        ])  # fmt: skip
        self.assertEqual([(c.is_charge, c.amount, c.reason) for c in found.charges], [
            (False, Decimal("10.00"), "Treuerabatt"), (True, Decimal("30.00"), "Fracht und Verpackung"),
        ])  # fmt: skip
        self.assertEqual(found.warnings, [])

    def test_cii_is_read_and_its_profile_named(self) -> None:
        found = einvoice.parse(cii())
        self.assertEqual((found.syntax, found.profile), ("cii", "ZUGFeRD / Factur-X EN 16931"))
        self.assertEqual((str(found.issue_date), str(found.due_date)), ("2027-02-22", "2027-03-22"))
        self.assertEqual((found.supplier_vat_id, found.iban), ("DE123456789", "DE02120300000000202051"))
        self.assertEqual(
            (found.total_net, found.total_tax, found.total_gross),
            (Decimal("377.00"), Decimal("71.63"), Decimal("448.63")),
        )
        self.assertEqual([(line.article_number, line.quantity, line.net) for line in found.lines], [
            ("SM58-X", Decimal(3), Decimal("297.00")), ("", Decimal(2), Decimal("50.00")),
        ])  # fmt: skip
        self.assertEqual(found.warnings, [])

    def test_the_profiles_of_the_guideline(self) -> None:
        for guideline, profile in (
            ("urn:factur-x.eu:1p0:minimum", "ZUGFeRD / Factur-X MINIMUM"),
            ("urn:factur-x.eu:1p0:basicwl", "ZUGFeRD / Factur-X BASIC WL"),
            ("urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic", "ZUGFeRD / Factur-X BASIC"),
            ("urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended", "ZUGFeRD / Factur-X EXTENDED"),
            ("urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0", "XRechnung"),
            ("urn:cen.eu:en16931:2017", "EN 16931"),
        ):
            self.assertEqual(einvoice.parse(cii(guideline=guideline)).profile, profile, guideline)

    def test_a_profile_without_positions_reads_the_head_and_derives_the_tax(self) -> None:
        text = cii(guideline="urn:factur-x.eu:1p0:minimum", lines=False).decode()
        text = text.replace('<ram:TaxTotalAmount currencyID="EUR">71.63</ram:TaxTotalAmount>', "")
        found = einvoice.parse(text.encode())
        self.assertEqual(found.lines, [])
        self.assertEqual((found.total_tax, found.tax_derived), (Decimal("71.63"), True))
        self.assertEqual(einvoice.proposal(found)["positions"][0]["description"], "Fracht und Verpackung")

    def test_a_credit_note_keeps_its_amounts_and_has_no_goods(self) -> None:
        found = einvoice.parse(ubl(credit=True))
        self.assertTrue(found.is_credit_note)
        self.assertEqual(found.lines[0].quantity, Decimal(3))
        positions = einvoice.proposal(found)["positions"]
        self.assertEqual({row["kind"] for row in positions[:2]}, {"other"})
        self.assertTrue(einvoice.proposal(found)["note"])
        by_code = cii().replace(b"<ram:TypeCode>380</ram:TypeCode>", b"<ram:TypeCode>381</ram:TypeCode>")
        self.assertTrue(einvoice.parse(by_code).is_credit_note)

    def test_the_sums_are_compared_with_themselves(self) -> None:
        warnings = einvoice.parse(ubl(lines_total="350.00", net="360.00", gross="440.00")).warnings
        self.assertEqual(len(warnings), 3)  # lines vs. total of the lines, vs. net, net + tax vs. gross
        self.assertEqual(einvoice.parse(ubl(gross="436.74")).warnings, [])  # one cent is rounding
        self.assertEqual(len(einvoice.parse(ubl(gross="436.80")).warnings), 1)

    def test_a_quantity_of_zero_or_less_and_discounted_lines_make_sense(self) -> None:
        text = (
            ubl()
            .decode()
            .replace(
                '<cbc:InvoicedQuantity unitCode="C62">2</cbc:InvoicedQuantity>\n    <cbc:LineExtensionAmount currencyID="EUR">50.00',
                '<cbc:InvoicedQuantity unitCode="C62">2</cbc:InvoicedQuantity>\n    <cbc:LineExtensionAmount currencyID="EUR">45.00',
            )
        )
        rows = einvoice.proposal(einvoice.parse(text.encode()))["positions"]
        self.assertEqual(rows[1]["unit_price_net"], "22.5000")  # worked out from the net amount
        self.assertTrue(rows[1]["hints"])
        negative = text.replace('unitCode="C62">3<', 'unitCode="C62">-3<').replace(">297.00<", ">-297.00<")
        row = einvoice.proposal(einvoice.parse(negative.encode()))["positions"][0]
        self.assertEqual((row["quantity"], row["kind"]), ("1", "cost"))  # a refund line is kept as an amount

    def test_unsafe_and_foreign_xml_is_refused(self) -> None:
        for content in (XXE, BILLION_LAUGHS):
            with self.assertRaises(einvoice.EInvoiceError) as caught:
                einvoice.parse(content)
            self.assertIn("Dokumenttyp", str(caught.exception))
        with self.assertRaises(einvoice.EInvoiceError):
            einvoice.parse(b"<Invoice><unclosed>")
        with self.assertRaises(einvoice.EInvoiceError) as caught:
            einvoice.parse(b"<html><body/></html>")
        self.assertIn("html", str(caught.exception))
        with self.assertRaises(einvoice.EInvoiceError):
            einvoice.parse(b"")
        with self.assertRaises(einvoice.EInvoiceError):  # too deep to be an invoice
            einvoice.parse(b"<a>" * 100 + b"</a>" * 100)

    def test_the_xml_of_a_pdf_is_found_by_name_and_not_invented(self) -> None:
        xml = cii()
        self.assertEqual(einvoice.xml_in_pdf(zugferd_pdf(xml)), xml)
        self.assertEqual(einvoice.xml_in_pdf(zugferd_pdf(xml, name="rechnung-1.xml")), xml)  # any xml, if none is named
        self.assertIsNone(einvoice.xml_in_pdf(zugferd_pdf(xml, name="scan.png")))
        self.assertIsNone(einvoice.xml_in_pdf(pdf_of(INCOMING_LINES)))
        self.assertIsNone(einvoice.xml_in_pdf(b"%PDF-1.4 not really"))


class UploadTests(FilesMixin, RentalarsTestCase):
    """Uploading: the XML or the PDF with an XML becomes an invoice with its head and its positions."""

    def test_an_xrechnung_is_read_without_ai(self) -> None:
        Supplier.objects.create(name="Musikhaus Muster GmbH & Co. KG")
        invoice = services.create_from_upload(xml_upload(ubl()), user=None)
        self.assertEqual(
            (invoice.reading_state, invoice.reading["source"], invoice.einvoice_format),
            (ReadingState.DONE, "einvoice", "ubl"),
        )
        self.assertEqual(
            (
                invoice.invoice_number,
                str(invoice.invoice_date),
                str(invoice.due_date),
                invoice.currency,
                invoice.supplier.name,
            ),
            ("RE-2027-0815", "2027-02-22", "2027-03-22", "EUR", "Musikhaus Muster GmbH & Co. KG"),
        )
        self.assertEqual(
            (invoice.total_net, invoice.total_tax, invoice.total_gross),
            (Decimal("367.00"), Decimal("69.73"), Decimal("436.73")),
        )
        rows = [
            (p.description, p.position_type, p.quantity, p.unit_price_net, p.tax_rate, p.article_number, p.user_edited)
            for p in invoice.positions.all()
        ]
        self.assertEqual(rows, [
            ("Shure SM58", PositionType.GOODS, Decimal("3.000"), Decimal("99.0000"), Decimal("19.00"), "SM58-X", False),
            ("Neutrik NL4 Kabel 10 m", PositionType.GOODS, Decimal("2.000"), Decimal("25.0000"), Decimal("19.00"), "", False),
            ("Treuerabatt", PositionType.ANCILLARY, Decimal("1.000"), Decimal("-10.0000"), Decimal("19.00"), "", False),
            ("Fracht und Verpackung", PositionType.ANCILLARY, Decimal("1.000"), Decimal("30.0000"), Decimal("19.00"), "", False),
        ])  # fmt: skip
        self.assertEqual(invoice.einvoice["profile"], "XRechnung")
        self.assertEqual(invoice.einvoice["iban"], "DE02120300000000202051")
        self.assertEqual(invoice.xml_name, invoice.file.name)
        self.assertFalse(AICall.objects.exists())

    def test_a_cii_is_read(self) -> None:
        invoice = services.create_from_upload(xml_upload(cii(), "cii.xml"), user=None)
        self.assertEqual((invoice.einvoice_format, invoice.einvoice["profile"]), ("cii", "ZUGFeRD / Factur-X EN 16931"))
        self.assertEqual((invoice.total_net, invoice.total_gross), (Decimal("377.00"), Decimal("448.63")))
        self.assertEqual(invoice.positions.count(), 3)  # two lines and the surcharge
        self.assertEqual(invoice.supplier_name, "Musikhaus Muster GmbH & Co. KG")

    def test_a_credit_note_is_marked_and_cannot_be_booked_in(self) -> None:
        invoice = services.create_from_upload(xml_upload(ubl(credit=True)), user=None)
        self.assertTrue(invoice.einvoice["credit_note"])
        self.assertIn("Gutschrift", invoice.reading["note"])
        self.assertFalse(invoice.positions.filter(position_type=PositionType.GOODS).exists())

    def test_a_pdf_with_an_xml_is_read_from_the_xml_and_keeps_both(self) -> None:
        invoice = services.create_from_upload(pdf_upload(zugferd_pdf()), user=None)
        self.assertEqual(
            (invoice.reading["source"], invoice.einvoice_format, invoice.original_name),
            ("einvoice", "cii", "zugferd.pdf"),
        )
        self.assertTrue(invoice.is_pdf)
        self.assertTrue(invoice.file.name.endswith(".pdf"))
        self.assertTrue(invoice.xml_file.name.endswith(".xml"))
        self.assertNotEqual(invoice.xml_file.name, invoice.file.name)
        with invoice.xml_file.open("rb") as handle:
            self.assertEqual(handle.read(), cii())
        self.assertEqual(invoice.positions.count(), 3)  # positions from the XML, not from the PDF text
        self.assertEqual(invoice.total_gross, Decimal("448.63"))

    def test_a_pdf_without_an_xml_is_read_as_before(self) -> None:
        from tests.unit.test_100_incoming import upload

        invoice = services.create_from_upload(upload(), user=None)
        self.assertEqual((invoice.reading["source"], invoice.einvoice_format, invoice.xml_name), ("text", "", ""))
        self.assertEqual(invoice.einvoice, {})

    def test_a_broken_attachment_falls_back_to_the_pdf_and_says_so(self) -> None:
        invoice = services.create_from_upload(pdf_upload(zugferd_pdf(b"<Invoice><kaputt>")), user=None)
        self.assertEqual((invoice.reading["source"], invoice.einvoice_format), ("text", ""))
        self.assertEqual(invoice.invoice_number, "RE-2027-0815")  # from the text of the PDF
        self.assertIn("angehängte XML", invoice.reading["error"])
        self.assertTrue(invoice.xml_file)  # kept: it is part of the original

    def test_refused_files_leave_nothing_behind(self) -> None:
        for content, name in (
            (XXE, "x.xml"),
            (BILLION_LAUGHS, "y.xml"),
            (b"<kaputt", "z.xml"),
            (b"<Foo/>", "f.xml"),
            (b"", "leer.xml"),
        ):
            with self.assertRaises(ValidationError):
                services.create_from_upload(xml_upload(content, name), user=None)
        self.assertFalse(IncomingInvoice.objects.exists())

    def test_reading_again_reads_the_xml_and_keeps_what_a_person_corrected(self) -> None:
        invoice = services.create_from_upload(xml_upload(ubl()), user=None)
        mic = invoice.positions.get(article_number="SM58-X")
        services.update_position(mic, {"description": "Mikrofon Shure SM58 (Kapsel)"})
        services.update_head(invoice, {"invoice_number": "RE-KORRIGIERT"})
        services.start_reading(invoice, user=None)
        invoice.refresh_from_db()
        self.assertEqual(invoice.invoice_number, "RE-KORRIGIERT")
        self.assertEqual(invoice.positions.count(), 4)
        self.assertEqual(invoice.positions.get(article_number="SM58-X").description, "Mikrofon Shure SM58 (Kapsel)")
        self.assertEqual(invoice.reading["source"], "einvoice")

    def test_a_pdf_of_an_earlier_version_gets_its_xml_when_read_again(self) -> None:
        invoice = services.create_from_upload(pdf_upload(zugferd_pdf()), user=None, read=False)
        invoice.xml_file.delete(save=False)
        IncomingInvoice.objects.filter(pk=invoice.pk).update(xml_file="", einvoice_format="")
        invoice.refresh_from_db()
        self.assertEqual(invoice.xml_name, "")
        services.start_reading(invoice, user=None)
        invoice.refresh_from_db()
        self.assertEqual((invoice.reading["source"], invoice.einvoice_format), ("einvoice", "cii"))
        self.assertTrue(invoice.xml_name)

    def test_the_same_xml_twice_is_noticed(self) -> None:
        first = services.create_from_upload(xml_upload(ubl()), user=None)
        second = services.create_from_upload(xml_upload(ubl()), user=None)
        self.assertEqual(services.duplicates(second), [first])

    def test_a_contradicting_file_is_kept_with_warnings(self) -> None:
        invoice = services.create_from_upload(xml_upload(ubl(gross="500.00")), user=None)
        self.assertEqual(invoice.reading_state, ReadingState.DONE)
        self.assertEqual(len(invoice.einvoice["warnings"]), 1)
        self.assertEqual(invoice.total_gross, Decimal("500.00"))  # as the file says; the person decides

    def test_deleting_an_invoice_deletes_both_files(self) -> None:
        invoice = services.create_from_upload(pdf_upload(zugferd_pdf()), user=None)
        names = [invoice.file.name, invoice.xml_file.name]
        storage = invoice.file.storage
        with self.captureOnCommitCallbacks(execute=True):
            services.delete_invoice(invoice)
        self.assertFalse(any(storage.exists(name) for name in names))


class PageTests(FilesMixin, UiTestCase):
    """The pages show that the invoice is a structured e-invoice and give the XML."""

    def upload(self, content: bytes, name: str) -> str:
        response = self.client.post(
            reverse("incoming:upload"), {"file": SimpleUploadedFile(name, content)}, follow=True
        )
        return self.assert_ok(response)

    def test_the_upload_page_reads_an_xrechnung_and_shows_what_it_is(self) -> None:
        page = self.upload(ubl(gross="440.00"), "re.xml")
        invoice = IncomingInvoice.objects.get()
        self.assertIn("strukturierte E-Rechnung", page)
        self.assertIn("XRechnung", page)
        self.assertIn("UBL (XML)", page)
        self.assertIn("urn:xeinkauf.de:kosit:xrechnung_3.0", page)
        self.assertIn("DE02120300000000202051", page)
        self.assertIn("Die Datei widerspricht sich", page)  # the gross total is wrong
        self.assertIn("aus dem XML gelesen", page)
        self.assertIn(reverse("incoming:xml", args=[invoice.pk]), page)
        self.assertIn("Shure SM58", page)

    def test_a_zugferd_pdf_offers_the_pdf_and_the_xml(self) -> None:
        page = self.upload(zugferd_pdf(), "zugferd.pdf")
        invoice = IncomingInvoice.objects.get()
        self.assertIn("ZUGFeRD / Factur-X EN 16931", page)
        self.assertIn("XML aus dem PDF herunterladen", page)
        self.assertIn(reverse("incoming:file", args=[invoice.pk]), page)

    def test_a_plain_pdf_shows_no_einvoice_box(self) -> None:
        from tests.unit.test_100_incoming import upload

        response = self.client.post(reverse("incoming:upload"), {"file": upload()}, follow=True)
        self.assertNotIn("strukturierte E-Rechnung", self.assert_ok(response))

    def test_a_refused_xml_says_why(self) -> None:
        response = self.client.post(reverse("incoming:upload"), {"file": SimpleUploadedFile("x.xml", XXE)}, follow=True)
        self.assertIn("Dokumenttyp", self.assert_ok(response))
        self.assertFalse(IncomingInvoice.objects.exists())

    def test_the_xml_is_a_download_with_a_sandbox_policy(self) -> None:
        self.upload(ubl(), "re.xml")
        invoice = IncomingInvoice.objects.get()
        response = self.client.get(reverse("incoming:xml", args=[invoice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".xml", response["Content-Disposition"])
        self.assertIn("sandbox", response["Content-Security-Policy"])
        self.assertEqual(b"".join(response.streaming_content), ubl())

    def test_there_is_no_xml_for_an_invoice_without_one(self) -> None:
        from tests.unit.test_100_incoming import upload

        invoice = services.create_from_upload(upload(), user=None)
        self.assertEqual(self.client.get(reverse("incoming:xml", args=[invoice.pk])).status_code, 404)

    def test_reading_again_on_the_page_reads_the_xml(self) -> None:
        self.upload(ubl(), "re.xml")
        invoice = IncomingInvoice.objects.get()
        response = self.client.post(reverse("incoming:read", args=[invoice.pk]), follow=True)
        self.assertIn("aus dem XML gelesen", self.assert_ok(response))


class ApiTests(FilesMixin, ApiTestCase):
    """API-014: the upload of an XML and a ZUGFeRD PDF, the XML of an invoice."""

    def setUp(self) -> None:
        super().setUp()
        self.luka = self.client_for("luka", "Lager")

    def post(self, content: bytes, name: str) -> object:
        return self.luka.post(
            f"{API}/incoming-invoices", {"file": SimpleUploadedFile(name, content)}, format="multipart"
        )

    def test_an_xml_upload_is_read_and_its_xml_is_downloadable(self) -> None:
        response = self.post(ubl(), "re.xml")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["einvoice_format"], body["reading"]["source"]), ("ubl", "einvoice"))
        self.assertEqual(
            (body["invoice_number"], body["total_gross"], len(body["positions"])), ("RE-2027-0815", "436.73", 4)
        )
        self.assertEqual(body["einvoice"]["profile"], "XRechnung")
        self.assertEqual(body["einvoice"]["warnings"], [])
        shown = self.luka.get(body["xml_url"])
        self.assertEqual(shown.status_code, 200)
        self.assertIn("attachment", shown["Content-Disposition"])
        self.assertIn("sandbox", shown["Content-Security-Policy"])
        self.assertEqual(b"".join(shown.streaming_content), ubl())

    def test_a_zugferd_pdf_has_its_xml_and_a_plain_pdf_none(self) -> None:
        body = self.post(zugferd_pdf(), "z.pdf").json()
        self.assertEqual((body["einvoice_format"], body["file_url"].endswith("/file")), ("cii", True))
        xml = self.luka.get(f"{API}/incoming-invoices/{body['id']}/xml")
        self.assertEqual(b"".join(xml.streaming_content), cii())
        from tests.unit.test_100_incoming import upload

        plain = self.luka.post(f"{API}/incoming-invoices", {"file": upload()}, format="multipart").json()
        self.assertIsNone(plain["xml_url"])
        self.assertEqual(plain["einvoice"], {})
        self.assertEqual(self.luka.get(f"{API}/incoming-invoices/{plain['id']}/xml").status_code, 404)

    def test_unsafe_xml_is_refused_with_400(self) -> None:
        for content in (XXE, BILLION_LAUGHS, b"<kaputt", b"<Foo/>"):
            self.assert_error(self.post(content, "x.xml"), 400, "validation_error", "file")
        self.assertFalse(IncomingInvoice.objects.exists())

    def test_without_the_right_there_is_no_xml(self) -> None:
        body = self.post(ubl(), "re.xml").json()
        guest = self.client_for("fritz", "Freie Kraft")
        self.assertIn(guest.get(f"{API}/incoming-invoices/{body['id']}/xml").status_code, (403, 404))
