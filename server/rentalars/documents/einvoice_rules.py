# SPDX-License-Identifier: GPL-3.0-or-later
"""The check of an e-invoice against the core rules of EN 16931 and of the XRechnung (DOK-042).

Own core checks: Rentalars reads UBL (Invoice, CreditNote) and CII (CrossIndustryInvoice, as in ZUGFeRD / Factur-X)
into one neutral form (:class:`Invoice`) and checks the rules on that form, so that every rule is written once for both
syntaxes. It reads the XML as safely as the incoming invoices (``incoming.einvoice``: no DTD, no entities, bounded).

What is checked, by the numbers of the standard (the text of a finding names the rule):

* the mandatory information – BR-01 to BR-16, BR-21 to BR-27;
* the sums – BR-CO-10, -13, -14, -15, -16 and -17 (tax per rate, a cent of tolerance for the rounding);
* the tax breakdown – BR-CO-04, -18, BR-45 to BR-48, the exemption reasons of the exempt categories and BR-S-08 (the basis of
  a rate against the lines of that rate);
* payment and seller – BR-CO-25, BR-50, BR-CO-26, BR-CO-09, the check digits of an IBAN;
* for an XRechnung: BR-DE-1 to BR-DE-9, BR-DE-15, BR-DE-17, BR-DE-21 (the form of the specification identifier;
  the pattern is the author's reading of the rule) and BR-DE-26.

What is **not** checked: the XML schema (XSD), the Schematron rules of the KoSIT and the code lists beyond the few named. A
file without a finding here can still be refused by a recipient's validator. The rules are the author's reading of the
standard, no official validator; ``RULESET`` is the version of this reading.
"""

from __future__ import annotations

import datetime
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.utils.translation import gettext as _

from rentalars.incoming.einvoice import (
    NS_CII,
    NS_UBL_CREDIT_NOTE,
    NS_UBL_INVOICE,
    EInvoiceError,
    _all,
    _cii_date,
    _decimal,
    _iso_date,
    _root_of,
    _text,
)

#: The version of this reading of the rules; stored with every result.
RULESET = "2026.1"

ERROR = "error"
WARNING = "warning"

ZERO = Decimal("0")
CENT = Decimal("0.01")
#: Tax per rate is a rounded result of the lines; one cent more or less is rounding, not an error.
TAX_TOLERANCE = Decimal("0.01")

#: The type codes the XRechnung allows (BR-DE-17): invoice, partial invoice, corrected invoice, self-billed, credit
#: note and the three of the second world of the standard.
XRECHNUNG_TYPE_CODES = frozenset({"326", "380", "384", "389", "381", "875", "876", "877"})

#: Categories that need a reason for the exemption (BR-E-10, BR-AE-10, BR-K-10, BR-G-10, BR-O-10).
EXEMPTION_RULES = {"E": "BR-E-10", "AE": "BR-AE-10", "K": "BR-IC-10", "G": "BR-G-10", "O": "BR-O-10"}
#: The rule "a line of this category needs a breakdown of the category" (BR-S-01 …).
CATEGORY_RULES = {
    "S": "BR-S-01",
    "Z": "BR-Z-01",
    "E": "BR-E-01",
    "AE": "BR-AE-01",
    "K": "BR-IC-01",
    "G": "BR-G-01",
    "O": "BR-O-01",
}
#: Categories without a rate (BR-O-05 for O); the others (S, Z, E, AE, K, G) carry a percentage.
NO_RATE_CATEGORIES = frozenset({"O"})


# --- The neutral form --------------------------------------------------------------------------------------------------


@dataclass
class Party:
    """Seller or buyer."""

    name: str = ""
    street: str = ""
    city: str = ""
    postcode: str = ""
    country: str = ""
    has_address: bool = False
    vat_id: str = ""
    tax_number: str = ""
    legal_id: str = ""
    other_id: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    has_contact: bool = False


@dataclass
class Line:
    """One invoice line."""

    ident: str = ""
    quantity: Decimal | None = None
    unit: str = ""
    net: Decimal | None = None
    price: Decimal | None = None
    name: str = ""
    category: str = ""
    rate: Decimal | None = None


@dataclass
class Charge:
    """An allowance or charge of the whole invoice."""

    is_charge: bool
    amount: Decimal | None
    category: str = ""
    rate: Decimal | None = None


@dataclass
class Breakdown:
    """One line of the tax breakdown (BG-23)."""

    category: str = ""
    rate: Decimal | None = None
    basis: Decimal | None = None
    amount: Decimal | None = None
    reason: str = ""


@dataclass
class Invoice:
    """An e-invoice as the rules see it, whatever its syntax."""

    syntax: str
    customization: str = ""
    profile_id: str = ""
    number: str = ""
    issue_date: datetime.date | None = None
    has_issue_date: bool = False
    due_date: datetime.date | None = None
    type_code: str = ""
    currency: str = ""
    buyer_reference: str = ""
    seller: Party = field(default_factory=Party)
    buyer: Party = field(default_factory=Party)
    means: list[tuple[str, str]] = field(default_factory=list)  # (type code, IBAN)
    has_means: bool = False
    terms: str = ""
    preceding: list[str] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    charges: list[Charge] = field(default_factory=list)
    breakdown: list[Breakdown] = field(default_factory=list)
    lines_total: Decimal | None = None
    allowance_total: Decimal | None = None
    charge_total: Decimal | None = None
    basis_total: Decimal | None = None  # BT-109, the total without tax
    tax_total: Decimal | None = None  # BT-110
    gross_total: Decimal | None = None  # BT-112
    prepaid: Decimal | None = None
    rounding: Decimal | None = None
    payable: Decimal | None = None

    @property
    def is_xrechnung(self) -> bool:
        """Whether the specification identifier names the XRechnung."""
        return "xrechnung" in self.customization.lower()

    @property
    def profile(self) -> str:
        """The profile as a word, for the page."""
        text = self.customization.lower()
        if "xrechnung" in text:
            return "XRechnung"
        if "factur-x" in text or "zugferd" in text:
            for marker, label in (
                (":minimum", "MINIMUM"),
                (":basicwl", "BASIC WL"),
                (":extended", "EXTENDED"),
                (":basic", "BASIC"),
            ):
                if marker in text:
                    return f"ZUGFeRD / Factur-X {label}"
            return "ZUGFeRD / Factur-X EN 16931"
        if "peppol" in text:
            return "Peppol BIS Billing"
        if "en16931" in text:
            return "EN 16931"
        return ""


@dataclass
class Finding:
    """One result of the check."""

    rule: str
    severity: str
    message: str
    location: str = ""


@dataclass
class Report:
    """The result: the findings, and what was checked."""

    syntax: str = ""
    profile: str = ""
    findings: list[Finding] = field(default_factory=list)
    ruleset: str = RULESET

    @property
    def errors(self) -> list[Finding]:
        """The findings that break a rule."""
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        """The findings that ask for a second look."""
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        """Whether no rule is broken."""
        return not self.errors

    def as_json(self) -> dict[str, Any]:
        """JSON-safe, for the column and the API."""
        return {
            "syntax": self.syntax,
            "profile": self.profile,
            "ruleset": self.ruleset,
            "ok": self.ok,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "findings": [asdict(f) for f in self.findings],
        }


# --- Reading UBL --------------------------------------------------------------------------------------------------------


def _party_ubl(party: ET.Element | None) -> Party:
    result = Party()
    if party is None:
        return result
    result.name = _text(party, "{*}PartyLegalEntity/{*}RegistrationName") or _text(party, "{*}PartyName/{*}Name")
    address = party.find("{*}PostalAddress")
    if address is not None:
        result.has_address = True
        result.street = _text(address, "{*}StreetName")
        result.city = _text(address, "{*}CityName")
        result.postcode = _text(address, "{*}PostalZone")
        result.country = _text(address, "{*}Country/{*}IdentificationCode")
    for scheme in _all(party, "{*}PartyTaxScheme"):
        code = _text(scheme, "{*}TaxScheme/{*}ID").upper()
        value = _text(scheme, "{*}CompanyID")
        if not value:
            continue
        if code in {"VAT", ""}:
            result.vat_id = result.vat_id or value
        else:
            result.tax_number = result.tax_number or value
    result.legal_id = _text(party, "{*}PartyLegalEntity/{*}CompanyID")
    result.other_id = _text(party, "{*}PartyIdentification/{*}ID")
    contact = party.find("{*}Contact")
    if contact is not None:
        result.contact_name = _text(contact, "{*}Name")
        result.contact_phone = _text(contact, "{*}Telephone")
        result.contact_email = _text(contact, "{*}ElectronicMail")
        result.has_contact = bool(result.contact_name or result.contact_phone or result.contact_email)
    return result


def _rate_ubl(node: ET.Element | None) -> tuple[str, Decimal | None]:
    if node is None:
        return "", None
    return _text(node, "{*}ID"), _decimal(_text(node, "{*}Percent"))


def _from_ubl(root: ET.Element, credit: bool) -> Invoice:
    result = Invoice("UBL")
    result.customization = _text(root, "{*}CustomizationID")
    result.profile_id = _text(root, "{*}ProfileID")
    result.number = _text(root, "{*}ID")
    issue = _text(root, "{*}IssueDate")
    result.has_issue_date = bool(issue)
    result.issue_date = _iso_date(issue)
    result.due_date = _iso_date(_text(root, "{*}DueDate"))
    result.type_code = _text(root, "{*}CreditNoteTypeCode" if credit else "{*}InvoiceTypeCode")
    result.currency = _text(root, "{*}DocumentCurrencyCode")
    result.buyer_reference = _text(root, "{*}BuyerReference")
    result.seller = _party_ubl(root.find("{*}AccountingSupplierParty/{*}Party"))
    result.buyer = _party_ubl(root.find("{*}AccountingCustomerParty/{*}Party"))
    for node in _all(root, "{*}PaymentMeans"):
        result.has_means = True
        result.means.append(
            (_text(node, "{*}PaymentMeansCode"), _text(node, "{*}PayeeFinancialAccount/{*}ID").replace(" ", "").upper())
        )
    result.terms = " ".join(_text(node, "{*}Note") for node in _all(root, "{*}PaymentTerms")).strip()
    for node in _all(root, "{*}BillingReference/{*}InvoiceDocumentReference"):
        result.preceding.append(_text(node, "{*}ID"))
    line_tag, quantity_tag = (
        ("{*}CreditNoteLine", "{*}CreditedQuantity") if credit else ("{*}InvoiceLine", "{*}InvoicedQuantity")
    )
    for node in _all(root, line_tag):
        quantity = node.find(quantity_tag)
        category, rate = _rate_ubl(node.find("{*}Item/{*}ClassifiedTaxCategory"))
        result.lines.append(
            Line(
                ident=_text(node, "{*}ID"),
                quantity=_decimal(quantity.text or "") if quantity is not None else None,
                unit=quantity.get("unitCode", "") if quantity is not None else "",
                net=_decimal(_text(node, "{*}LineExtensionAmount")),
                price=_decimal(_text(node, "{*}Price/{*}PriceAmount")),
                name=_text(node, "{*}Item/{*}Name"),
                category=category,
                rate=rate,
            )
        )
    for node in _all(root, "{*}AllowanceCharge"):
        category, rate = _rate_ubl(node.find("{*}TaxCategory"))
        result.charges.append(
            Charge(
                _text(node, "{*}ChargeIndicator").lower() == "true", _decimal(_text(node, "{*}Amount")), category, rate
            )
        )
    for total in _all(root, "{*}TaxTotal"):
        amount = total.find("{*}TaxAmount")
        if (
            amount is not None
            and result.tax_total is None
            and amount.get("currencyID", result.currency) == result.currency
        ):
            result.tax_total = _decimal(amount.text or "")
        for sub in _all(total, "{*}TaxSubtotal"):
            category, rate = _rate_ubl(sub.find("{*}TaxCategory"))
            result.breakdown.append(
                Breakdown(
                    category,
                    rate,
                    _decimal(_text(sub, "{*}TaxableAmount")),
                    _decimal(_text(sub, "{*}TaxAmount")),
                    _text(sub, "{*}TaxCategory/{*}TaxExemptionReason")
                    or _text(sub, "{*}TaxCategory/{*}TaxExemptionReasonCode"),
                )
            )
    totals = root.find("{*}LegalMonetaryTotal")
    result.lines_total = _decimal(_text(totals, "{*}LineExtensionAmount"))
    result.basis_total = _decimal(_text(totals, "{*}TaxExclusiveAmount"))
    result.gross_total = _decimal(_text(totals, "{*}TaxInclusiveAmount"))
    result.allowance_total = _decimal(_text(totals, "{*}AllowanceTotalAmount"))
    result.charge_total = _decimal(_text(totals, "{*}ChargeTotalAmount"))
    result.prepaid = _decimal(_text(totals, "{*}PrepaidAmount"))
    result.rounding = _decimal(_text(totals, "{*}PayableRoundingAmount"))
    result.payable = _decimal(_text(totals, "{*}PayableAmount"))
    return result


# --- Reading CII ---------------------------------------------------------------------------------------------------------


def _party_cii(party: ET.Element | None) -> Party:
    result = Party()
    if party is None:
        return result
    result.name = _text(party, "{*}Name")
    result.legal_id = _text(party, "{*}SpecifiedLegalOrganization/{*}ID")
    result.other_id = _text(party, "{*}ID") or _text(party, "{*}GlobalID")
    address = party.find("{*}PostalTradeAddress")
    if address is not None:
        result.has_address = True
        result.street = _text(address, "{*}LineOne")
        result.city = _text(address, "{*}CityName")
        result.postcode = _text(address, "{*}PostcodeCode")
        result.country = _text(address, "{*}CountryID")
    for registration in _all(party, "{*}SpecifiedTaxRegistration/{*}ID"):
        value = " ".join((registration.text or "").split())
        scheme = registration.get("schemeID", "").upper()
        if not value:
            continue
        if scheme == "VA":
            result.vat_id = result.vat_id or value
        else:
            result.tax_number = result.tax_number or value
    contact = party.find("{*}DefinedTradeContact")
    if contact is not None:
        result.contact_name = _text(contact, "{*}PersonName") or _text(contact, "{*}DepartmentName")
        result.contact_phone = _text(contact, "{*}TelephoneUniversalCommunication/{*}CompleteNumber")
        result.contact_email = _text(contact, "{*}EmailURIUniversalCommunication/{*}URIID")
        result.has_contact = bool(result.contact_name or result.contact_phone or result.contact_email)
    return result


def _from_cii(root: ET.Element) -> Invoice:
    result = Invoice("CII")
    result.customization = _text(
        root, "{*}ExchangedDocumentContext/{*}GuidelineSpecifiedDocumentContextParameter/{*}ID"
    )
    result.profile_id = _text(
        root, "{*}ExchangedDocumentContext/{*}BusinessProcessSpecifiedDocumentContextParameter/{*}ID"
    )
    document = root.find("{*}ExchangedDocument")
    result.number = _text(document, "{*}ID")
    result.type_code = _text(document, "{*}TypeCode")
    issue = document.find("{*}IssueDateTime") if document is not None else None
    result.has_issue_date = issue is not None and bool(_text(issue, "{*}DateTimeString"))
    result.issue_date = _cii_date(issue)
    transaction = root.find("{*}SupplyChainTradeTransaction")
    agreement = transaction.find("{*}ApplicableHeaderTradeAgreement") if transaction is not None else None
    settlement = transaction.find("{*}ApplicableHeaderTradeSettlement") if transaction is not None else None
    result.buyer_reference = _text(agreement, "{*}BuyerReference")
    result.seller = _party_cii(agreement.find("{*}SellerTradeParty") if agreement is not None else None)
    result.buyer = _party_cii(agreement.find("{*}BuyerTradeParty") if agreement is not None else None)
    result.currency = _text(settlement, "{*}InvoiceCurrencyCode")
    for node in _all(settlement, "{*}SpecifiedTradeSettlementPaymentMeans"):
        result.has_means = True
        result.means.append(
            (
                _text(node, "{*}TypeCode"),
                _text(node, "{*}PayeePartyCreditorFinancialAccount/{*}IBANID").replace(" ", "").upper(),
            )
        )
    terms = settlement.find("{*}SpecifiedTradePaymentTerms") if settlement is not None else None
    result.terms = _text(terms, "{*}Description")
    result.due_date = _cii_date(terms.find("{*}DueDateDateTime")) if terms is not None else None
    for node in _all(settlement, "{*}InvoiceReferencedDocument"):
        result.preceding.append(_text(node, "{*}IssuerAssignedID"))
    for node in _all(transaction, "{*}IncludedSupplyChainTradeLineItem"):
        quantity = node.find("{*}SpecifiedLineTradeDelivery/{*}BilledQuantity")
        tax = node.find("{*}SpecifiedLineTradeSettlement/{*}ApplicableTradeTax")
        result.lines.append(
            Line(
                ident=_text(node, "{*}AssociatedDocumentLineDocument/{*}LineID"),
                quantity=_decimal(quantity.text or "") if quantity is not None else None,
                unit=quantity.get("unitCode", "") if quantity is not None else "",
                net=_decimal(
                    _text(
                        node,
                        "{*}SpecifiedLineTradeSettlement/{*}SpecifiedTradeSettlementLineMonetarySummation/{*}LineTotalAmount",
                    )
                ),
                price=_decimal(
                    _text(node, "{*}SpecifiedLineTradeAgreement/{*}NetPriceProductTradePrice/{*}ChargeAmount")
                ),
                name=_text(node, "{*}SpecifiedTradeProduct/{*}Name"),
                category=_text(tax, "{*}CategoryCode"),
                rate=_decimal(_text(tax, "{*}RateApplicablePercent")),
            )
        )
    for node in _all(settlement, "{*}SpecifiedTradeAllowanceCharge"):
        result.charges.append(
            Charge(
                _text(node, "{*}ChargeIndicator/{*}Indicator").lower() == "true",
                _decimal(_text(node, "{*}ActualAmount")),
                _text(node, "{*}CategoryTradeTax/{*}CategoryCode"),
                _decimal(_text(node, "{*}CategoryTradeTax/{*}RateApplicablePercent")),
            )
        )
    for node in _all(settlement, "{*}ApplicableTradeTax"):
        result.breakdown.append(
            Breakdown(
                _text(node, "{*}CategoryCode"),
                _decimal(_text(node, "{*}RateApplicablePercent")),
                _decimal(_text(node, "{*}BasisAmount")),
                _decimal(_text(node, "{*}CalculatedAmount")),
                _text(node, "{*}ExemptionReason") or _text(node, "{*}ExemptionReasonCode"),
            )
        )
    totals = settlement.find("{*}SpecifiedTradeSettlementHeaderMonetarySummation") if settlement is not None else None
    result.lines_total = _decimal(_text(totals, "{*}LineTotalAmount"))
    result.charge_total = _decimal(_text(totals, "{*}ChargeTotalAmount"))
    result.allowance_total = _decimal(_text(totals, "{*}AllowanceTotalAmount"))
    result.basis_total = _decimal(_text(totals, "{*}TaxBasisTotalAmount"))
    result.tax_total = _decimal(_text(totals, "{*}TaxTotalAmount"))
    result.gross_total = _decimal(_text(totals, "{*}GrandTotalAmount"))
    result.prepaid = _decimal(_text(totals, "{*}TotalPrepaidAmount"))
    result.rounding = _decimal(_text(totals, "{*}RoundingAmount"))
    result.payable = _decimal(_text(totals, "{*}DuePayableAmount"))
    return result


def read(data: bytes) -> Invoice:
    """The e-invoice in the neutral form.

    Raises:
        EInvoiceError: The XML is unsafe, not well-formed, or no UBL / CII invoice.
    """
    root = _root_of(data)
    namespace, _sep, local = root.tag[1:].partition("}") if root.tag.startswith("{") else ("", "", root.tag)
    if namespace == NS_UBL_INVOICE and local == "Invoice":
        return _from_ubl(root, credit=False)
    if namespace == NS_UBL_CREDIT_NOTE and local == "CreditNote":
        return _from_ubl(root, credit=True)
    if namespace == NS_CII and local == "CrossIndustryInvoice":
        return _from_cii(root)
    raise EInvoiceError(
        _(
            "The XML is not an e-invoice we know (UBL Invoice or CreditNote, or UN/CEFACT CrossIndustryInvoice); its root element is “%(name)s”."
        )
        % {"name": local[:60]}
    )


# --- The rules ------------------------------------------------------------------------------------------------------------


def cents(value: Decimal) -> Decimal:
    """Whole cents, halves up."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def iban_valid(iban: str) -> bool:
    """The check digits of an IBAN (ISO 13616, mod 97)."""
    text = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", text):
        return False
    moved = text[4:] + text[:4]
    number = "".join(str(int(char, 36)) for char in moved)
    return int(number) % 97 == 1


class _Collector:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def error(self, rule: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(rule, ERROR, message, location))

    def warn(self, rule: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(rule, WARNING, message, location))


def _mandatory(invoice: Invoice, out: _Collector) -> None:
    if not invoice.customization:
        out.error("BR-01", _("The specification identifier is missing."), "BT-24")
    if not invoice.number:
        out.error("BR-02", _("The invoice number is missing."), "BT-1")
    if not invoice.has_issue_date:
        out.error("BR-03", _("The invoice date is missing."), "BT-2")
    elif invoice.issue_date is None:
        out.error("BR-03", _("The invoice date is not a date."), "BT-2")
    if not invoice.type_code:
        out.error("BR-04", _("The type of the invoice (type code) is missing."), "BT-3")
    if not re.fullmatch(r"[A-Z]{3}", invoice.currency or ""):
        out.error("BR-05", _("The currency is missing or not a three-letter code."), "BT-5")
    for rule_name, rule_address, rule_country, party, side in (
        ("BR-06", "BR-08", "BR-09", invoice.seller, _("seller")),
        ("BR-07", "BR-10", "BR-11", invoice.buyer, _("buyer")),
    ):
        location = "BG-4" if party is invoice.seller else "BG-7"
        if not party.name:
            out.error(rule_name, _("The name of the %(side)s is missing.") % {"side": side}, location)
        if not party.has_address:
            out.error(rule_address, _("The address of the %(side)s is missing.") % {"side": side}, location)
        elif not re.fullmatch(r"[A-Z]{2}", party.country or ""):
            out.error(
                rule_country,
                _("The country of the %(side)s is missing or not a two-letter code.") % {"side": side},
                location,
            )
    if invoice.lines_total is None:
        out.error("BR-12", _("The sum of the line amounts is missing."), "BT-106")
    if invoice.basis_total is None:
        out.error("BR-13", _("The invoice total without tax is missing."), "BT-109")
    if invoice.gross_total is None:
        out.error("BR-14", _("The invoice total with tax is missing."), "BT-112")
    if invoice.payable is None:
        out.error("BR-15", _("The amount due for payment is missing."), "BT-115")
    if not invoice.lines:
        out.error("BR-16", _("The invoice has no line."), "BG-25")
    for index, line in enumerate(invoice.lines, start=1):
        label = _("line %(number)s") % {"number": line.ident or index}
        if not line.ident:
            out.error("BR-21", _("A line has no identifier (%(label)s).") % {"label": label}, "BT-126")
        if line.quantity is None:
            out.error("BR-22", _("The quantity is missing (%(label)s).") % {"label": label}, "BT-129")
        if not line.unit:
            out.error("BR-23", _("The unit of the quantity is missing (%(label)s).") % {"label": label}, "BT-130")
        if line.net is None:
            out.error("BR-24", _("The net amount is missing (%(label)s).") % {"label": label}, "BT-131")
        if not line.name:
            out.error("BR-25", _("The name of the item is missing (%(label)s).") % {"label": label}, "BT-153")
        if line.price is None:
            out.error("BR-26", _("The net price is missing (%(label)s).") % {"label": label}, "BT-146")
        elif line.price < 0:
            out.error("BR-27", _("The net price is negative (%(label)s).") % {"label": label}, "BT-146")
        if not line.category:
            out.error("BR-CO-04", _("The tax category is missing (%(label)s).") % {"label": label}, "BT-151")


def _differs(first: Decimal, second: Decimal, tolerance: Decimal = ZERO) -> bool:
    return abs(cents(first) - cents(second)) > tolerance


def _sums(invoice: Invoice, out: _Collector) -> None:
    line_sum = sum((line.net for line in invoice.lines if line.net is not None), ZERO)
    if invoice.lines_total is not None and invoice.lines and _differs(line_sum, invoice.lines_total):
        out.error(
            "BR-CO-10",
            _("The sum of the lines (%(lines)s) is not the sum of the line amounts (%(total)s).")
            % {"lines": cents(line_sum), "total": invoice.lines_total},
            "BT-106",
        )
    if invoice.lines_total is not None and invoice.basis_total is not None:
        allowance = invoice.allowance_total or ZERO
        charge = invoice.charge_total or ZERO
        if _differs(invoice.lines_total - allowance + charge, invoice.basis_total):
            out.error(
                "BR-CO-13",
                _("The lines less allowances plus charges (%(expected)s) are not the total without tax (%(total)s).")
                % {"expected": cents(invoice.lines_total - allowance + charge), "total": invoice.basis_total},
                "BT-109",
            )
    if invoice.allowance_total is not None:
        listed = sum((c.amount or ZERO for c in invoice.charges if not c.is_charge), ZERO)
        if _differs(listed, invoice.allowance_total):
            out.error(
                "BR-CO-11",
                _("The sum of the allowances (%(listed)s) is not the total of the allowances (%(total)s).")
                % {"listed": cents(listed), "total": invoice.allowance_total},
                "BT-107",
            )
    if invoice.charge_total is not None:
        listed = sum((c.amount or ZERO for c in invoice.charges if c.is_charge), ZERO)
        if _differs(listed, invoice.charge_total):
            out.error(
                "BR-CO-12",
                _("The sum of the charges (%(listed)s) is not the total of the charges (%(total)s).")
                % {"listed": cents(listed), "total": invoice.charge_total},
                "BT-108",
            )
    if not invoice.breakdown:
        out.error("BR-CO-18", _("The tax breakdown is missing."), "BG-23")
    tax_sum = sum((row.amount or ZERO for row in invoice.breakdown), ZERO)
    if invoice.tax_total is not None and invoice.breakdown and _differs(tax_sum, invoice.tax_total):
        out.error(
            "BR-CO-14",
            _("The tax amounts of the breakdown (%(sum)s) are not the total tax (%(total)s).")
            % {"sum": cents(tax_sum), "total": invoice.tax_total},
            "BT-110",
        )
    if invoice.basis_total is not None and invoice.gross_total is not None:
        tax = invoice.tax_total if invoice.tax_total is not None else ZERO
        if _differs(invoice.basis_total + tax, invoice.gross_total):
            out.error(
                "BR-CO-15",
                _("The total without tax (%(net)s) plus the tax (%(tax)s) is not the total with tax (%(gross)s).")
                % {"net": invoice.basis_total, "tax": cents(tax), "gross": invoice.gross_total},
                "BT-112",
            )
    if invoice.gross_total is not None and invoice.payable is not None:
        expected = invoice.gross_total - (invoice.prepaid or ZERO) + (invoice.rounding or ZERO)
        if _differs(expected, invoice.payable):
            out.error(
                "BR-CO-16",
                _("The total with tax less the prepaid amount (%(expected)s) is not the amount due (%(due)s).")
                % {"expected": cents(expected), "due": invoice.payable},
                "BT-115",
            )


def _breakdown(invoice: Invoice, out: _Collector) -> None:
    for row in invoice.breakdown:
        label = f"{row.category or '?'} {row.rate if row.rate is not None else ''}".strip()
        if row.basis is None:
            out.error("BR-45", _("The taxable amount is missing (%(label)s).") % {"label": label}, "BT-116")
        if row.amount is None:
            out.error("BR-46", _("The tax amount is missing (%(label)s).") % {"label": label}, "BT-117")
        if not row.category:
            out.error("BR-47", _("The tax category is missing in the breakdown."), "BT-118")
            continue
        if row.rate is None and row.category not in NO_RATE_CATEGORIES:
            out.error("BR-48", _("The tax rate is missing (%(label)s).") % {"label": label}, "BT-119")
        if row.category in EXEMPTION_RULES and not row.reason:
            out.error(
                EXEMPTION_RULES[row.category],
                _("A reason for the exemption is missing (%(label)s).") % {"label": label},
                "BT-120",
            )
        if row.category == "S" and row.rate is not None and row.rate <= 0:
            out.error("BR-S-05", _("The standard rate must be above zero (%(label)s).") % {"label": label}, "BT-119")
        if (
            row.rate is not None
            and row.basis is not None
            and row.amount is not None
            and row.category in {"S", "Z", "E", "AE", "K", "G"}
        ):
            expected = cents(row.basis * row.rate / 100)
            if _differs(expected, row.amount, TAX_TOLERANCE):
                out.error(
                    "BR-CO-17",
                    _(
                        "The tax amount (%(amount)s) is not the taxable amount times the rate (%(expected)s) (%(label)s)."
                    )
                    % {"amount": row.amount, "expected": expected, "label": label},
                    "BT-117",
                )
    # BR-S-08 and its kin: the taxable amount of a rate is the lines of that rate, less allowances, plus charges.
    basis: dict[tuple[str, Decimal | None], Decimal] = {}
    for line in invoice.lines:
        key = (line.category, line.rate if line.rate is not None else ZERO)
        basis[key] = basis.get(key, ZERO) + (line.net or ZERO)
    for charge in invoice.charges:
        key = (charge.category, charge.rate if charge.rate is not None else ZERO)
        basis[key] = basis.get(key, ZERO) + (charge.amount or ZERO) * (1 if charge.is_charge else -1)
    listed = {(row.category, row.rate if row.rate is not None else ZERO): row for row in invoice.breakdown}
    for key, expected_basis in basis.items():
        if not key[0]:
            continue
        row = listed.get(key)
        label = f"{key[0]} {key[1]}"
        if row is None:
            out.error(
                CATEGORY_RULES.get(key[0], "BR-CO-04"),
                _("Lines have the tax category and rate %(label)s, the breakdown has none for it.") % {"label": label},
                "BG-23",
            )
        elif row.basis is not None and _differs(row.basis, expected_basis, TAX_TOLERANCE):
            out.error(
                "BR-S-08",
                _(
                    "The taxable amount of %(label)s (%(basis)s) is not the lines of this rate less allowances plus charges (%(expected)s)."
                )
                % {"label": label, "basis": row.basis, "expected": cents(expected_basis)},
                "BT-116",
            )


def _payment_and_parties(invoice: Invoice, out: _Collector) -> None:
    payable = invoice.payable or ZERO
    if payable > 0 and invoice.due_date is None and not invoice.terms:
        out.error("BR-CO-25", _("An amount is due, but there is neither a due date nor a payment term."), "BT-9")
    for code, iban in invoice.means:
        if code in {"30", "58"} and not iban:
            out.error("BR-50", _("A credit transfer needs the IBAN of the account to pay to."), "BT-84")
        elif iban and not iban_valid(iban):
            out.warn("PLAUSI-IBAN", _("The check digits of the IBAN %(iban)s do not fit.") % {"iban": iban}, "BT-84")
    seller = invoice.seller
    if not (seller.vat_id or seller.tax_number or seller.legal_id or seller.other_id):
        out.error(
            "BR-CO-26",
            _("The seller needs an identifier: VAT ID, tax number, registration number or another identifier."),
            "BT-29",
        )
    if seller.vat_id and not re.match(r"^[A-Z]{2}", seller.vat_id):
        out.error("BR-CO-09", _("The VAT ID of the seller must start with the country code."), "BT-31")
    if invoice.buyer.vat_id and not re.match(r"^[A-Z]{2}", invoice.buyer.vat_id):
        out.error("BR-CO-09", _("The VAT ID of the buyer must start with the country code."), "BT-48")
    for party, side in ((seller, _("seller")), (invoice.buyer, _("buyer"))):
        if party.vat_id.startswith("DE") and not re.fullmatch(r"DE\d{9}", party.vat_id.replace(" ", "")):
            out.warn(
                "PLAUSI-USTID",
                _("The German VAT ID of the %(side)s should be DE and nine digits.") % {"side": side},
                "BT-31",
            )


#: BR-DE-21: the specification identifier (BT-24) of an XRechnung, in the form of version 3 (``xeinkauf.de``) or of version 2
#: (``xoev-de``), with the extension identifier a file may add. The author's reading of the rule, not the KoSIT's pattern.
XRECHNUNG_SPECIFICATION = re.compile(
    r"^urn:cen\.eu:en16931:2017#(?:"
    r"(?:compliant|conformant)#urn:(?:xeinkauf\.de:kosit:xrechnung_\d+\.\d+|xoev-de:kosit:standard:xrechnung_\d+\.\d+)"
    r"(?:#conformant#urn:xeinkauf\.de:kosit:extension:xrechnung_\d+\.\d+)?"
    r"|conformant#urn:xeinkauf\.de:kosit:extension:xrechnung_\d+\.\d+)$"
)


def _xrechnung(invoice: Invoice, out: _Collector) -> None:
    if not XRECHNUNG_SPECIFICATION.match(invoice.customization.strip()):
        out.error(
            "BR-DE-21",
            _(
                "The specification identifier is not that of an XRechnung (urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0)."
            ),
            "BT-24",
        )
    if not invoice.has_means:
        out.error("BR-DE-1", _("An XRechnung needs payment instructions."), "BG-16")
    seller, buyer = invoice.seller, invoice.buyer
    if not seller.has_contact:
        out.error("BR-DE-2", _("An XRechnung needs the contact of the seller."), "BG-6")
    if not seller.city:
        out.error("BR-DE-3", _("The city of the seller is missing."), "BT-37")
    if not seller.postcode:
        out.error("BR-DE-4", _("The postal code of the seller is missing."), "BT-38")
    if seller.has_contact:
        if not seller.contact_name:
            out.error("BR-DE-5", _("The name of the contact of the seller is missing."), "BT-41")
        if not seller.contact_phone:
            out.error("BR-DE-6", _("The telephone number of the contact of the seller is missing."), "BT-42")
        if not seller.contact_email:
            out.error("BR-DE-7", _("The e-mail address of the contact of the seller is missing."), "BT-43")
    if not buyer.city:
        out.error("BR-DE-8", _("The city of the buyer is missing."), "BT-52")
    if not buyer.postcode:
        out.error("BR-DE-9", _("The postal code of the buyer is missing."), "BT-53")
    if not invoice.buyer_reference:
        out.error("BR-DE-15", _("An XRechnung needs the buyer reference (Leitweg-ID or another reference)."), "BT-10")
    if invoice.type_code and invoice.type_code not in XRECHNUNG_TYPE_CODES:
        out.error(
            "BR-DE-17",
            _("The type code %(code)s is not allowed in an XRechnung.") % {"code": invoice.type_code},
            "BT-3",
        )
    if invoice.type_code == "384" and not any(invoice.preceding):
        out.error("BR-DE-26", _("A corrected invoice names the invoice it corrects."), "BG-3")


def check_invoice(invoice: Invoice) -> Report:
    """Check an invoice in the neutral form against the rules."""
    out = _Collector()
    _mandatory(invoice, out)
    _sums(invoice, out)
    _breakdown(invoice, out)
    _payment_and_parties(invoice, out)
    if invoice.is_xrechnung:
        _xrechnung(invoice, out)
    # The same rule broken by several lines is said once.
    seen: set[tuple[str, str]] = set()
    unique: list[Finding] = []
    for finding in out.findings:
        key = (finding.rule, finding.message)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return Report(invoice.syntax, invoice.profile, unique)


def check(data: bytes) -> Report:
    """Check an e-invoice (the XML) against the rules.

    A file that is no e-invoice is a finding as well, not an exception: the person is told why.
    """
    try:
        invoice = read(data)
    except EInvoiceError as error:
        return Report("", "", [Finding("XML", ERROR, str(error))])
    return check_invoice(invoice)
