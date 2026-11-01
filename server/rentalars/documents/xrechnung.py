# SPDX-License-Identifier: GPL-3.0-or-later
"""The invoice as structured electronic invoice: XRechnung in UBL syntax (DOK-006, EN 16931).

A German business has to be able to receive electronic invoices since 2025
and will have to send them in the years after. The XRechnung written here
follows the core invoice model EN 16931 with the German specification
XRechnung 3.0 and the UBL 2.1 syntax:

* every position becomes an invoice line. Its price is given for the whole
  quantity (``BaseQuantity`` = quantity): rental days and scale factor make
  "unit price × quantity" differ from the amount, and so the line stays
  exact without rounding;
* the discount of a position is a line allowance;
* discounts and flat prices of groups become allowances (or charges) per tax
  rate on the invoice, in the same proportion the price calculation uses;
* a cancellation is an invoice of type 384 ("corrected invoice") with
  negated amounts that refers to the invoice it cancels.

Mandatory data the company profile lacks (an e-mail address, the VAT ID or tax
number) is reported by :func:`missing_data` before the invoice is made.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any

from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.core.money import plain_decimal
from rentalars.documents.content import ZERO, DocumentContent

NAMESPACES = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
CURRENCY = "EUR"

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def missing_data(content: DocumentContent) -> list[str]:
    """What the electronic invoice needs and the company profile or customer does not have."""
    company = content.company
    missing = []
    if not company.get("name"):
        missing.append(_("company name"))
    if not (company.get("street") and company.get("city") and company.get("postal_code")):
        missing.append(_("company address"))
    if not company.get("email"):
        missing.append(_("company e-mail address"))
    if sum(character.isdigit() for character in company.get("phone") or "") < 3:
        # BR-DE-6, BR-DE-27: the seller's contact needs a telephone number.
        missing.append(_("company phone number"))
    if not (company.get("vat_id") or company.get("tax_number")):
        missing.append(_("VAT ID or tax number of the company"))
    if not content.recipient:
        missing.append(_("billing address of the customer"))
    if content.reverse_charge and not company.get("vat_id"):
        # BR-AE-02: with the tax owed by the customer the seller needs a VAT ID (a tax number does not do).
        missing.append(_("VAT ID of the company (the customer owes the tax)"))
    return missing


def _amount(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):f}"


#: Characters XML 1.0 does not allow (control characters, a pasted vertical tab, say); they would break the whole file.
NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _sub(parent: ET.Element, tag: str, text: Any = None, **attributes: str) -> ET.Element:
    prefix, name = tag.split(":")
    element = ET.SubElement(parent, f"{{{NAMESPACES[prefix]}}}{name}", attributes)
    if text is not None:
        element.text = NOT_XML.sub("", str(text))
    return element


def _money(parent: ET.Element, tag: str, value: Decimal) -> ET.Element:
    return _sub(parent, tag, _amount(value), currencyID=CURRENCY)


def _country_code(country: str) -> str:
    """ISO 3166 code of a country written out; Germany if empty."""
    names = {"": "DE", "deutschland": "DE", "germany": "DE", "österreich": "AT", "austria": "AT", "schweiz": "CH"}
    text = (country or "").strip()
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return names.get(text.lower(), "DE")


def _tax_category(parent: ET.Element, tag: str, category: str, percent: Decimal) -> None:
    element = _sub(parent, tag)
    _sub(element, "cbc:ID", category)
    _sub(element, "cbc:Percent", plain_decimal(percent))
    if category == "E" and tag == "cac:TaxCategory":
        _sub(element, "cbc:TaxExemptionReason", _("Exempt from VAT"))
    elif category == "AE" and tag == "cac:TaxCategory":
        _sub(element, "cbc:TaxExemptionReason", _("Reverse charge – the recipient of the service owes the tax"))
    scheme = _sub(element, "cac:TaxScheme")
    _sub(scheme, "cbc:ID", "VAT")


def _address_parts(lines: list[str]) -> tuple[str, str, str, str]:
    """Street, postal code, city and country from printed address lines (name first)."""
    rest = lines[1:] if len(lines) > 1 else lines
    street, postal_code, city, country = "", "", "", ""
    for line in rest:
        first, _space, remainder = line.partition(" ")
        if first.isdigit() and remainder and not postal_code:
            postal_code, city = first, remainder
        elif postal_code:
            country = line
        else:
            street = line
    return street, postal_code, city, country


def build_xml(content: DocumentContent) -> bytes:
    """The XRechnung of an invoice or cancellation as UTF-8 bytes."""
    root = ET.Element(f"{{{NAMESPACES['ubl']}}}Invoice")
    _sub(root, "cbc:CustomizationID", CUSTOMIZATION)
    _sub(root, "cbc:ProfileID", PROFILE)
    _sub(root, "cbc:ID", content.number)
    _sub(root, "cbc:IssueDate", content.issued_on.isoformat())
    if content.due_on:
        _sub(root, "cbc:DueDate", content.due_on.isoformat())
    # A partial invoice is 326 (UNTDID 1001, allowed by the XRechnung); advance and final invoice are 380.
    type_code = "384" if content.kind == "cancellation" else "326" if content.billing_type == "partial" else "380"
    _sub(root, "cbc:InvoiceTypeCode", type_code)
    if content.has_estimates:
        _sub(root, "cbc:Note", _("Contains estimated amounts."))
    _sub(root, "cbc:DocumentCurrencyCode", CURRENCY)
    # BT-10, mandatory in XRechnung: the reference of the buyer – here the project.
    _sub(root, "cbc:BuyerReference", content.buyer_reference or content.project.get("number") or "-")
    if content.service_start and content.service_end:
        period = _sub(root, "cac:InvoicePeriod")
        _sub(period, "cbc:StartDate", content.service_start.isoformat())
        _sub(period, "cbc:EndDate", content.service_end.isoformat())
    if content.cancels_number:
        reference = _sub(_sub(root, "cac:BillingReference"), "cac:InvoiceDocumentReference")
        _sub(reference, "cbc:ID", content.cancels_number)
        if content.cancels_date:
            _sub(reference, "cbc:IssueDate", content.cancels_date.isoformat())
    for deduction in content.deductions:
        # BG-3: a final invoice names the advance and partial invoices it deducts.
        reference = _sub(_sub(root, "cac:BillingReference"), "cac:InvoiceDocumentReference")
        _sub(reference, "cbc:ID", deduction.number)
        _sub(reference, "cbc:IssueDate", deduction.issued_on.isoformat())

    _seller(root, content.company)
    _buyer(root, content)

    company = content.company
    if company.get("iban"):
        means = _sub(root, "cac:PaymentMeans")
        _sub(means, "cbc:PaymentMeansCode", "58")  # SEPA credit transfer
        _sub(means, "cbc:PaymentID", content.number)
        account = _sub(means, "cac:PayeeFinancialAccount")
        _sub(account, "cbc:ID", company["iban"].replace(" ", ""))
        if company.get("bank_name"):
            _sub(account, "cbc:Name", company["name"])
        if company.get("bic"):
            _sub(_sub(account, "cac:FinancialInstitutionBranch"), "cbc:ID", company["bic"])
    if content.due_on:
        _sub(
            _sub(root, "cac:PaymentTerms"),
            "cbc:Note",
            _("Payable by %(date)s") % {"date": content.due_on.strftime(local_pattern("%d.%m.%Y"))},
        )

    allowances = ZERO
    charges = ZERO
    for share in content.tax_groups:
        difference = share.allowance
        if difference == ZERO:
            continue
        # Positions minus allowances plus charges must give the net amount (EN 16931 BR-CO-13).
        is_charge = difference < ZERO
        element = _sub(root, "cac:AllowanceCharge")
        _sub(element, "cbc:ChargeIndicator", "true" if is_charge else "false")
        _sub(element, "cbc:AllowanceChargeReason", _("Discount or flat price of groups"))
        amount = -difference if is_charge else difference
        _money(element, "cbc:Amount", amount)
        _tax_category(element, "cac:TaxCategory", content.category_of(share.category), share.percent)
        if is_charge:
            charges += amount
        else:
            allowances += amount

    tax_total = _sub(root, "cac:TaxTotal")
    _money(tax_total, "cbc:TaxAmount", content.tax_total)
    for share in content.tax_groups:
        subtotal = _sub(tax_total, "cac:TaxSubtotal")
        _money(subtotal, "cbc:TaxableAmount", share.net)
        _money(subtotal, "cbc:TaxAmount", share.tax)
        _tax_category(subtotal, "cac:TaxCategory", content.category_of(share.category), share.percent)

    lines_total = sum((position.amount for position in content.positions), ZERO)
    totals = _sub(root, "cac:LegalMonetaryTotal")
    _money(totals, "cbc:LineExtensionAmount", lines_total)
    _money(totals, "cbc:TaxExclusiveAmount", content.net_total)
    _money(totals, "cbc:TaxInclusiveAmount", content.gross_total)
    if allowances:
        _money(totals, "cbc:AllowanceTotalAmount", allowances)
    if charges:
        _money(totals, "cbc:ChargeTotalAmount", charges)
    if content.deductions:
        _money(totals, "cbc:PrepaidAmount", content.prepaid_total)  # BT-113
    _money(totals, "cbc:PayableAmount", content.payable_total)

    for index, position in enumerate(content.positions, start=1):
        _line(root, index, position, content)

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _seller(root: ET.Element, company: dict[str, Any]) -> None:
    party = _sub(_sub(root, "cac:AccountingSupplierParty"), "cac:Party")
    _sub(party, "cbc:EndpointID", company.get("email") or "", schemeID="EM")
    _sub(_sub(party, "cac:PartyName"), "cbc:Name", company.get("name") or "")
    address = _sub(party, "cac:PostalAddress")
    _sub(address, "cbc:StreetName", company.get("street") or "")
    _sub(address, "cbc:CityName", company.get("city") or "")
    _sub(address, "cbc:PostalZone", company.get("postal_code") or "")
    _sub(_sub(address, "cac:Country"), "cbc:IdentificationCode", _country_code(company.get("country") or ""))
    if company.get("vat_id"):
        scheme = _sub(party, "cac:PartyTaxScheme")
        _sub(scheme, "cbc:CompanyID", company["vat_id"])
        _sub(_sub(scheme, "cac:TaxScheme"), "cbc:ID", "VAT")
    if company.get("tax_number"):
        scheme = _sub(party, "cac:PartyTaxScheme")
        _sub(scheme, "cbc:CompanyID", company["tax_number"])
        _sub(_sub(scheme, "cac:TaxScheme"), "cbc:ID", "FC")
    legal = _sub(party, "cac:PartyLegalEntity")
    _sub(legal, "cbc:RegistrationName", company.get("name") or "")
    contact = _sub(party, "cac:Contact")
    _sub(contact, "cbc:Name", company.get("name") or "")
    _sub(contact, "cbc:Telephone", company.get("phone"))
    _sub(contact, "cbc:ElectronicMail", company.get("email") or "")


def _buyer(root: ET.Element, content: DocumentContent) -> None:
    party = _sub(_sub(root, "cac:AccountingCustomerParty"), "cac:Party")
    _sub(party, "cbc:EndpointID", content.recipient_email or content.company.get("email") or "", schemeID="EM")
    if content.customer_number:
        _sub(_sub(party, "cac:PartyIdentification"), "cbc:ID", content.customer_number)
    name = content.recipient[0] if content.recipient else ""
    street, postal_code, city, country = _address_parts(content.recipient)
    address = _sub(party, "cac:PostalAddress")
    if street:
        _sub(address, "cbc:StreetName", street)
    _sub(address, "cbc:CityName", city or "-")
    if postal_code:
        _sub(address, "cbc:PostalZone", postal_code)
    _sub(_sub(address, "cac:Country"), "cbc:IdentificationCode", _country_code(country))
    if content.customer_vat_id:
        scheme = _sub(party, "cac:PartyTaxScheme")
        _sub(scheme, "cbc:CompanyID", content.customer_vat_id)
        _sub(_sub(scheme, "cac:TaxScheme"), "cbc:ID", "VAT")
    _sub(_sub(party, "cac:PartyLegalEntity"), "cbc:RegistrationName", name)


def _line(root: ET.Element, index: int, position: Any, content: DocumentContent) -> None:
    line = _sub(root, "cac:InvoiceLine")
    _sub(line, "cbc:ID", str(index))
    quantity = position.quantity if position.quantity else Decimal("1")
    if (quantity < ZERO) != (position.base_amount < ZERO) and position.base_amount:
        quantity = -quantity
    _sub(line, "cbc:InvoicedQuantity", f"{quantity:f}", unitCode=position.unit_code)
    _money(line, "cbc:LineExtensionAmount", position.amount)
    # Quantity × price ÷ base quantity is the amount before discount; the discount is the difference.
    difference = position.base_amount - position.amount
    if difference:
        allowance = _sub(line, "cac:AllowanceCharge")
        _sub(allowance, "cbc:ChargeIndicator", "true" if difference < ZERO else "false")
        _sub(allowance, "cbc:AllowanceChargeReason", _("Discount"))
        _money(allowance, "cbc:Amount", abs(difference))
    item = _sub(line, "cac:Item")
    # BT-154: the description of the product (only on a document that prints the descriptions), then the
    # calculation notes of the position.
    description = "\n".join(text for text in (getattr(position, "description", ""), position.details) if text)
    if description:
        _sub(item, "cbc:Description", description)
    _sub(item, "cbc:Name", position.title or "-")
    if position.article_number:
        _sub(_sub(item, "cac:SellersItemIdentification"), "cbc:ID", position.article_number)
    category = content.category_of("S" if position.tax_percent > ZERO else "E")
    classified = _sub(item, "cac:ClassifiedTaxCategory")
    _sub(classified, "cbc:ID", category)
    _sub(classified, "cbc:Percent", plain_decimal(position.tax_percent))
    _sub(_sub(classified, "cac:TaxScheme"), "cbc:ID", "VAT")
    price = _sub(line, "cac:Price")
    # The price of the whole quantity: exact even with rental days and scale factors.
    _money(price, "cbc:PriceAmount", abs(position.base_amount))
    _sub(price, "cbc:BaseQuantity", f"{abs(quantity):f}", unitCode=position.unit_code)
