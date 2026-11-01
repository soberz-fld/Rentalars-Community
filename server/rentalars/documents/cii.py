# SPDX-License-Identifier: GPL-3.0-or-later
"""The invoice as UN/CEFACT Cross Industry Invoice – the XML inside a ZUGFeRD / Factur-X PDF (DOK-049).

The same invoice as :mod:`rentalars.documents.xrechnung` writes in UBL, in the syntax of ZUGFeRD 2.x / Factur-X 1.0 with
the profile EN 16931 ("COMFORT"): the data model is that of EN 16931, so what is true of the UBL invoice is true here –
the price of a position is for its whole quantity (``BasisQuantity`` = quantity), a position's discount is a line
allowance, the discounts of groups are allowances per tax rate on the invoice, a cancellation is a corrected invoice
(384) that names the invoice it cancels, a final invoice names and deducts its advances.

Written by the author after the structure of the specification and checked by :mod:`rentalars.documents.einvoice_rules`
and structurally by the tests; **not** validated with the official schema or a validator of the community.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any

from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.documents.content import ZERO, DocumentContent
from rentalars.documents.xrechnung import CURRENCY, NOT_XML, _address_parts, _amount, _country_code

NAMESPACES = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    # The date of a referenced document (``FormattedIssueDateTime``) is a *qualified* date in the schema.
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}
#: The specification identifier of the profile EN 16931 of ZUGFeRD 2.x and Factur-X 1.0.
GUIDELINE = "urn:cen.eu:en16931:2017"
#: The name of the XML file inside the PDF (the name Factur-X prescribes).
FILE_NAME = "factur-x.xml"
#: ``ConformanceLevel`` of the XMP extension.
CONFORMANCE_LEVEL = "EN 16931"

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def _sub(parent: ET.Element, tag: str, text: Any = None, **attributes: str) -> ET.Element:
    prefix, name = tag.split(":")
    element = ET.SubElement(parent, f"{{{NAMESPACES[prefix]}}}{name}", attributes)
    if text is not None:
        element.text = NOT_XML.sub("", str(text))
    return element


def _date(parent: ET.Element, tag: str, day: Any) -> ET.Element:
    """A date as the schema has it: ``udt:DateTimeString``, but ``qdt:DateTimeString`` in ``FormattedIssueDateTime``."""
    element = _sub(parent, tag)
    prefix = "qdt" if tag.endswith("FormattedIssueDateTime") else "udt"
    _sub(element, f"{prefix}:DateTimeString", day.strftime("%Y%m%d"), format="102")
    return element


def _percent(value: Decimal) -> str:
    text = format(value.normalize(), "f")  # 10.00 -> "10", 7.50 -> "7.5", 0.00 -> "0"
    return text


def _trade_tax(parent: ET.Element, category: str, percent: Decimal, *, with_reason: bool = False) -> ET.Element:
    """``ApplicableTradeTax`` of a line (category and rate)."""
    element = _sub(parent, "ram:ApplicableTradeTax")
    _sub(element, "ram:TypeCode", "VAT")
    if with_reason and category == "E":
        _sub(element, "ram:ExemptionReason", _("Exempt from VAT"))
    elif with_reason and category == "AE":
        _sub(element, "ram:ExemptionReason", _("Reverse charge – the recipient of the service owes the tax"))
    _sub(element, "ram:CategoryCode", category)
    _sub(element, "ram:RateApplicablePercent", _percent(percent))
    return element


def _party(
    parent: ET.Element,
    tag: str,
    *,
    name: str,
    lines: list[str],
    country: str,
    email: str,
    vat_id: str,
    tax_number: str = "",
    identifier: str = "",
    contact: dict[str, str] | None = None,
) -> None:
    street, postal_code, city, own_country = _address_parts(lines) if lines else ("", "", "", "")
    party = _sub(parent, tag)
    if identifier:
        _sub(party, "ram:ID", identifier)
    _sub(party, "ram:Name", name)
    if contact:
        node = _sub(party, "ram:DefinedTradeContact")
        if contact.get("name"):
            _sub(node, "ram:PersonName", contact["name"])
        if contact.get("phone"):
            _sub(_sub(node, "ram:TelephoneUniversalCommunication"), "ram:CompleteNumber", contact["phone"])
        if contact.get("email"):
            _sub(_sub(node, "ram:EmailURIUniversalCommunication"), "ram:URIID", contact["email"])
    address = _sub(party, "ram:PostalTradeAddress")
    if postal_code:
        _sub(address, "ram:PostcodeCode", postal_code)
    if street:
        _sub(address, "ram:LineOne", street)
    _sub(address, "ram:CityName", city or "-")
    _sub(address, "ram:CountryID", _country_code(country or own_country))
    if email:
        _sub(_sub(party, "ram:URIUniversalCommunication"), "ram:URIID", email, schemeID="EM")
    if vat_id:
        _sub(_sub(party, "ram:SpecifiedTaxRegistration"), "ram:ID", vat_id, schemeID="VA")
    if tax_number:
        _sub(_sub(party, "ram:SpecifiedTaxRegistration"), "ram:ID", tax_number, schemeID="FC")


def build_cii(content: DocumentContent) -> bytes:
    """The invoice or cancellation as Cross Industry Invoice (profile EN 16931) in UTF-8."""
    root = ET.Element(f"{{{NAMESPACES['rsm']}}}CrossIndustryInvoice")
    context = _sub(root, "rsm:ExchangedDocumentContext")
    _sub(_sub(context, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", GUIDELINE)

    document = _sub(root, "rsm:ExchangedDocument")
    _sub(document, "ram:ID", content.number)
    type_code = "384" if content.kind == "cancellation" else "326" if content.billing_type == "partial" else "380"
    _sub(document, "ram:TypeCode", type_code)
    _date(document, "ram:IssueDateTime", content.issued_on)
    if content.has_estimates:
        _sub(_sub(document, "ram:IncludedNote"), "ram:Content", _("Contains estimated amounts."))

    transaction = _sub(root, "rsm:SupplyChainTradeTransaction")
    for index, position in enumerate(content.positions, start=1):
        _line(transaction, index, position, content)

    agreement = _sub(transaction, "ram:ApplicableHeaderTradeAgreement")
    _sub(agreement, "ram:BuyerReference", content.buyer_reference or content.project.get("number") or "-")
    company = content.company
    _party(
        agreement,
        "ram:SellerTradeParty",
        name=company.get("name") or "",
        lines=[
            "",
            company.get("street") or "",
            f"{company.get('postal_code') or ''} {company.get('city') or ''}".strip(),
        ],
        country=company.get("country") or "",
        email=company.get("email") or "",
        vat_id=company.get("vat_id") or "",
        tax_number=company.get("tax_number") or "",
        contact={
            "name": company.get("name") or "",
            "phone": company.get("phone") or "",
            "email": company.get("email") or "",
        },
    )
    _party(
        agreement,
        "ram:BuyerTradeParty",
        name=content.recipient[0] if content.recipient else "",
        lines=content.recipient,
        country="",
        email=content.recipient_email or "",
        vat_id=content.customer_vat_id or "",
        identifier=content.customer_number or "",
    )
    _sub(transaction, "ram:ApplicableHeaderTradeDelivery")

    settlement = _sub(transaction, "ram:ApplicableHeaderTradeSettlement")
    _sub(settlement, "ram:PaymentReference", content.number)
    _sub(settlement, "ram:InvoiceCurrencyCode", CURRENCY)
    if company.get("iban"):
        means = _sub(settlement, "ram:SpecifiedTradeSettlementPaymentMeans")
        _sub(means, "ram:TypeCode", "58")  # SEPA credit transfer
        account = _sub(means, "ram:PayeePartyCreditorFinancialAccount")
        _sub(account, "ram:IBANID", company["iban"].replace(" ", ""))
        if company.get("bic"):
            _sub(_sub(means, "ram:PayeeSpecifiedCreditorFinancialInstitution"), "ram:BICID", company["bic"])
    for share in content.tax_groups:
        tax = _sub(settlement, "ram:ApplicableTradeTax")
        _sub(tax, "ram:CalculatedAmount", _amount(share.tax))
        _sub(tax, "ram:TypeCode", "VAT")
        category = content.category_of(share.category)
        if category == "E":
            _sub(tax, "ram:ExemptionReason", _("Exempt from VAT"))
        elif category == "AE":
            _sub(tax, "ram:ExemptionReason", _("Reverse charge – the recipient of the service owes the tax"))
        _sub(tax, "ram:BasisAmount", _amount(share.net))
        _sub(tax, "ram:CategoryCode", category)
        _sub(tax, "ram:RateApplicablePercent", _percent(share.percent))
    if content.service_start and content.service_end:
        period = _sub(settlement, "ram:BillingSpecifiedPeriod")
        _date(period, "ram:StartDateTime", content.service_start)
        _date(period, "ram:EndDateTime", content.service_end)

    allowances = ZERO
    charges = ZERO
    for share in content.tax_groups:
        difference = share.allowance
        if difference == ZERO:
            continue
        is_charge = difference < ZERO
        amount = -difference if is_charge else difference
        element = _sub(settlement, "ram:SpecifiedTradeAllowanceCharge")
        _sub(_sub(element, "ram:ChargeIndicator"), "udt:Indicator", "true" if is_charge else "false")
        _sub(element, "ram:ActualAmount", _amount(amount))
        _sub(element, "ram:Reason", _("Discount or flat price of groups"))
        tax = _sub(element, "ram:CategoryTradeTax")
        _sub(tax, "ram:TypeCode", "VAT")
        _sub(tax, "ram:CategoryCode", content.category_of(share.category))
        _sub(tax, "ram:RateApplicablePercent", _percent(share.percent))
        if is_charge:
            charges += amount
        else:
            allowances += amount

    if content.due_on:
        terms = _sub(settlement, "ram:SpecifiedTradePaymentTerms")
        _sub(
            terms,
            "ram:Description",
            _("Payable by %(date)s") % {"date": content.due_on.strftime(local_pattern("%d.%m.%Y"))},
        )
        _date(terms, "ram:DueDateDateTime", content.due_on)

    lines_total = sum((position.amount for position in content.positions), ZERO)
    totals = _sub(settlement, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    _sub(totals, "ram:LineTotalAmount", _amount(lines_total))
    if charges:
        _sub(totals, "ram:ChargeTotalAmount", _amount(charges))
    if allowances:
        _sub(totals, "ram:AllowanceTotalAmount", _amount(allowances))
    _sub(totals, "ram:TaxBasisTotalAmount", _amount(content.net_total))
    _sub(totals, "ram:TaxTotalAmount", _amount(content.tax_total), currencyID=CURRENCY)
    _sub(totals, "ram:GrandTotalAmount", _amount(content.gross_total))
    if content.deductions:
        _sub(totals, "ram:TotalPrepaidAmount", _amount(content.prepaid_total))
    _sub(totals, "ram:DuePayableAmount", _amount(content.payable_total))

    references = []
    if content.cancels_number:
        references.append((content.cancels_number, content.cancels_date))
    references.extend((deduction.number, deduction.issued_on) for deduction in content.deductions)
    for number, day in references:
        referenced = _sub(settlement, "ram:InvoiceReferencedDocument")
        _sub(referenced, "ram:IssuerAssignedID", number)
        if day:
            _date(referenced, "ram:FormattedIssueDateTime", day)

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _line(transaction: ET.Element, index: int, position: Any, content: DocumentContent) -> None:
    line = _sub(transaction, "ram:IncludedSupplyChainTradeLineItem")
    _sub(_sub(line, "ram:AssociatedDocumentLineDocument"), "ram:LineID", str(index))
    product = _sub(line, "ram:SpecifiedTradeProduct")
    if position.article_number:
        _sub(product, "ram:SellerAssignedID", position.article_number)
    _sub(product, "ram:Name", position.title or "-")
    description = "\n".join(text for text in (getattr(position, "description", ""), position.details) if text)
    if description:
        _sub(product, "ram:Description", description)

    quantity = position.quantity if position.quantity else Decimal("1")
    if (quantity < ZERO) != (position.base_amount < ZERO) and position.base_amount:
        quantity = -quantity
    agreement = _sub(line, "ram:SpecifiedLineTradeAgreement")
    price = _sub(agreement, "ram:NetPriceProductTradePrice")
    _sub(price, "ram:ChargeAmount", _amount(abs(position.base_amount)))
    _sub(price, "ram:BasisQuantity", f"{abs(quantity):f}", unitCode=position.unit_code)
    delivery = _sub(line, "ram:SpecifiedLineTradeDelivery")
    _sub(delivery, "ram:BilledQuantity", f"{quantity:f}", unitCode=position.unit_code)

    settlement = _sub(line, "ram:SpecifiedLineTradeSettlement")
    category = content.category_of("S" if position.tax_percent > ZERO else "E")
    _trade_tax(settlement, category, position.tax_percent)
    difference = position.base_amount - position.amount
    if difference:
        allowance = _sub(settlement, "ram:SpecifiedTradeAllowanceCharge")
        _sub(_sub(allowance, "ram:ChargeIndicator"), "udt:Indicator", "true" if difference < ZERO else "false")
        _sub(allowance, "ram:ActualAmount", _amount(abs(difference)))
        _sub(allowance, "ram:Reason", _("Discount"))
    _sub(
        _sub(settlement, "ram:SpecifiedTradeSettlementLineMonetarySummation"),
        "ram:LineTotalAmount",
        _amount(position.amount),
    )
