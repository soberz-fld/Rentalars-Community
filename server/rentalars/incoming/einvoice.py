# SPDX-License-Identifier: GPL-3.0-or-later
"""Structured e-invoices coming in: XRechnung (UBL, CII), ZUGFeRD / Factur-X – read without AI (DOK-040, DOK-041).

The requirement: import, read and show structured e-invoices (XML/XRechnung and ZUGFeRD), not only PDF and images as before.

What is accepted
----------------
* a **XML file** – UBL 2.1 ``Invoice`` or ``CreditNote`` (XRechnung, Peppol BIS) or UN/CEFACT ``CrossIndustryInvoice``
  (CII, XRechnung-CII, ZUGFeRD 2, Factur-X);
* a **PDF with an XML attached** (ZUGFeRD / Factur-X; the attachment is found by its place in the PDF – ``/Names``
  ``/EmbeddedFiles`` and ``/AF`` – and taken when it is an invoice, by the usual names first).

Reading is deterministic: the fields of the standard EN 16931 are taken from their places in the XML
(:func:`parse`). Nothing is guessed and nothing goes to an AI. What the file says is checked for itself – lines
against the total of the lines, net plus tax against gross, the cent tolerance of the standard – and a difference
is a *warning* shown with the invoice, never a refusal: the invoice is in the register all the same.

Safety: XML with a document type declaration (DTD) or entities is refused (:func:`_refuse_unsafe`), as XRechnung
forbids it as well – so no external entity is loaded and nothing expands (XXE, "billion laughs"). The file is
checked by a first pass of the XML parser that builds nothing; only then is the tree built. Size, depth and the number
of elements are limited.

Credit notes
------------
A credit note (UBL ``CreditNote``, type code 381 and a few like it) keeps the amounts as the document writes them
(positive). The register has no sign convention for them yet: the invoice therefore
says so (``credit_note``) and its positions are of the kind "other", so that no goods can be booked in from it.

The module has no Django models in it except the match of the supplier; :func:`proposal` gives what
:func:`rentalars.incoming.reading.apply_proposal` takes.
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from xml.parsers import expat

from django.utils.translation import gettext as _

from rentalars.core.money import money

#: The most elements and the deepest nesting of an invoice XML; real invoices have some hundreds, nested ten deep.
MAX_ELEMENTS = 200_000
MAX_DEPTH = 64
#: The largest XML taken out of a PDF (the stream is not decompressed beyond it).
MAX_ATTACHMENT_BYTES = 8_000_000
#: Entries of the name tree and attached files looked at in a PDF.
_MAX_ATTACHMENTS = 50

#: The usual names of the attached file, best first (lower case): ZUGFeRD 2, Factur-X, XRechnung in a PDF, ZUGFeRD 1.
ATTACHMENT_NAMES = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")

#: Type codes (UNTDID 1001) of documents that reduce what is owed.
CREDIT_NOTE_CODES = frozenset({"381", "261", "262", "81", "83"})
#: Type codes of an invoice the buyer wrote himself – unusual for an incoming invoice.
SELF_BILLED_CODES = frozenset({"389", "261", "262"})

#: The difference between two amounts that is still rounding (EN 16931 allows one cent per comparison).
TOLERANCE = Decimal("0.01")
MAX_DIGITS_ABOVE_POINT = 12  # an amount or quantity of an e-invoice has at most this many digits before the point

NS_UBL_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_UBL_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
NS_CII = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"

SYNTAX_UBL = "ubl"
SYNTAX_CII = "cii"


class EInvoiceError(Exception):
    """The file is no e-invoice we can read; ``str(error)`` says why, for the person."""


@dataclass
class Line:
    """One position of the e-invoice."""

    place: str = ""
    name: str = ""
    description: str = ""
    article_number: str = ""
    quantity: Decimal | None = None
    unit_code: str = ""
    unit_price: Decimal | None = None
    net: Decimal | None = None
    tax_rate: Decimal | None = None


@dataclass
class Charge:
    """A discount or a surcharge of the whole document (``AllowanceCharge``)."""

    is_charge: bool
    amount: Decimal
    reason: str = ""
    tax_rate: Decimal | None = None


@dataclass
class EInvoice:
    """What an e-invoice says, as far as the register needs it."""

    syntax: str
    document: str  # "invoice" | "credit_note"
    type_code: str = ""
    customization_id: str = ""
    profile_id: str = ""
    number: str = ""
    issue_date: datetime.date | None = None
    due_date: datetime.date | None = None
    currency: str = ""
    supplier_name: str = ""
    supplier_vat_id: str = ""
    iban: str = ""
    buyer_reference: str = ""
    order_reference: str = ""
    note: str = ""
    lines_total: Decimal | None = None
    allowance_total: Decimal | None = None
    charge_total: Decimal | None = None
    total_net: Decimal | None = None
    total_tax: Decimal | None = None
    total_gross: Decimal | None = None
    payable: Decimal | None = None
    lines: list[Line] = field(default_factory=list)
    charges: list[Charge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tax_derived: bool = False

    @property
    def is_credit_note(self) -> bool:
        """Whether the document reduces what is owed."""
        return self.document == "credit_note"

    @property
    def profile(self) -> str:
        """The profile of the document as a word: XRechnung, or the ZUGFeRD / Factur-X profile, or EN 16931."""
        text = self.customization_id.lower()
        if "xrechnung" in text:
            return "XRechnung"
        if "peppol" in text or "peppol" in self.profile_id.lower():
            return "Peppol BIS Billing"
        if "factur-x" in text or "zugferd" in text:
            for marker, label in (
                (":minimum", "MINIMUM"),
                (":basicwl", "BASIC WL"),
                (":extended", "EXTENDED"),
                (":basic", "BASIC"),
                (":comfort", "EN 16931"),
                (":en16931", "EN 16931"),
            ):
                if marker in text:
                    return f"ZUGFeRD / Factur-X {label}"
            return "ZUGFeRD / Factur-X"
        if "en16931" in text:
            return "EN 16931"
        return ""

    def details(self) -> dict[str, Any]:
        """What the page and the API show about the file: JSON-safe, kept with the reading of the invoice."""
        return {
            "syntax": self.syntax,
            "document": self.document,
            "type_code": self.type_code,
            "credit_note": self.is_credit_note,
            "customization_id": self.customization_id,
            "profile_id": self.profile_id,
            "profile": self.profile,
            "supplier_vat_id": self.supplier_vat_id,
            "iban": self.iban,
            "buyer_reference": self.buyer_reference,
            "order_reference": self.order_reference,
            "lines": len(self.lines),
            "payable": str(self.payable) if self.payable is not None else "",
            "warnings": list(self.warnings),
        }


# --- Safe parsing --------------------------------------------------------------------------------------------------


def _refuse_unsafe(data: bytes, max_elements: int = MAX_ELEMENTS) -> None:
    """A first pass that builds nothing: refuse a DTD or entities, a document too large, too deep or not well-formed.

    Raises:
        EInvoiceError: with the reason, for the person.
    """
    parser = expat.ParserCreate()
    state = {"elements": 0, "depth": 0}

    def forbid(*_args: Any) -> None:
        raise EInvoiceError(
            _(
                "The XML contains a document type declaration or entities. E-invoices have none (XRechnung forbids "
                "them); the file is not read."
            )
        )

    def start(_name: str, _attributes: Any) -> None:
        state["elements"] += 1
        state["depth"] += 1
        if state["elements"] > max_elements or state["depth"] > MAX_DEPTH:
            raise EInvoiceError(_("The XML is too large or nested too deeply to be an invoice."))

    def end(_name: str) -> None:
        state["depth"] -= 1

    parser.StartDoctypeDeclHandler = forbid
    parser.EntityDeclHandler = forbid
    parser.UnparsedEntityDeclHandler = forbid
    parser.ExternalEntityRefHandler = forbid
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(data, True)
    except (expat.ExpatError, ValueError, LookupError) as error:  # ValueError: an encoding expat does not know
        raise EInvoiceError(_("The file is not well-formed XML.")) from error


def _root_of(data: bytes, *, max_elements: int = MAX_ELEMENTS) -> ET.Element:
    """The tree of the XML, after the safety pass (``max_elements``: another limit for a file that is no invoice)."""
    _refuse_unsafe(data, max_elements)
    try:
        return ET.fromstring(data)  # noqa: S314 - DTD and entities were refused by the first pass
    except ET.ParseError as error:  # pragma: no cover - the first pass found it already
        raise EInvoiceError(_("The file is not well-formed XML.")) from error


# --- Small readers over the tree (the namespace of an element is checked at the root only) -------------------------


def _text(element: ET.Element | None, path: str = "") -> str:
    """The trimmed text at a path below an element, empty if there is none."""
    if element is None:
        return ""
    found = element.find(path) if path else element
    return " ".join((found.text or "").split()) if found is not None else ""


def _all(element: ET.Element | None, path: str) -> list[ET.Element]:
    """Every element at a path below an element."""
    return element.findall(path) if element is not None else []


def _decimal(value: str) -> Decimal | None:
    """An amount or number as the standard writes it (a dot, no thousands separator); ``None`` if it is none."""
    if not value:
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        return None
    # An amount of an invoice has twelve digits at most; "9E+9999999" would only break the sums later (500 error).
    if (
        not number.is_finite()
        or number.adjusted() > MAX_DIGITS_ABOVE_POINT
        or number.adjusted() < -MAX_DIGITS_ABOVE_POINT
    ):
        return None
    return number


def _amount_at(element: ET.Element | None, path: str) -> Decimal | None:
    return _decimal(_text(element, path))


def _iso_date(value: str) -> datetime.date | None:
    """A day from ``2027-02-22`` (maybe with a time or zone after it) or ``20270222``."""
    value = (value or "").strip()
    try:
        if len(value) >= 10 and value[4] == "-":
            return datetime.date.fromisoformat(value[:10])
        if len(value) >= 8 and value[:8].isdigit():
            return datetime.datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        return None
    return None


def _cii_date(element: ET.Element | None) -> datetime.date | None:
    """A CII date: ``<udt:DateTimeString format="102">20270222</udt:DateTimeString>``."""
    if element is None:
        return None
    node = element.find("{*}DateTimeString")
    if node is None:
        return None
    return _iso_date(node.text or "")


# --- UBL -----------------------------------------------------------------------------------------------------------


def _ubl_lines(root: ET.Element, credit: bool, result: EInvoice) -> None:
    tag = "{*}CreditNoteLine" if credit else "{*}InvoiceLine"
    quantity_tag = "{*}CreditedQuantity" if credit else "{*}InvoicedQuantity"
    for node in _all(root, tag):
        quantity_node = node.find(quantity_tag)
        price = _amount_at(node, "{*}Price/{*}PriceAmount")
        base = _amount_at(node, "{*}Price/{*}BaseQuantity")
        if price is not None and base:
            price = price / base
        result.lines.append(
            Line(
                place=_text(node, "{*}ID"),
                name=_text(node, "{*}Item/{*}Name"),
                description=_text(node, "{*}Item/{*}Description"),
                article_number=_text(node, "{*}Item/{*}SellersItemIdentification/{*}ID"),
                quantity=_decimal(quantity_node.text or "") if quantity_node is not None else None,
                unit_code=quantity_node.get("unitCode", "") if quantity_node is not None else "",
                unit_price=price,
                net=_amount_at(node, "{*}LineExtensionAmount"),
                tax_rate=_amount_at(node, "{*}Item/{*}ClassifiedTaxCategory/{*}Percent"),
            )
        )


def _ubl_party_vat(party: ET.Element | None) -> str:
    for scheme in _all(party, "{*}PartyTaxScheme"):
        if _text(scheme, "{*}TaxScheme/{*}ID").upper() in {"VAT", ""}:
            found = _text(scheme, "{*}CompanyID")
            if found:
                return found
    return ""


def _from_ubl(root: ET.Element, credit: bool) -> EInvoice:
    document = "credit_note" if credit else "invoice"
    result = EInvoice(
        syntax=SYNTAX_UBL,
        document=document,
        customization_id=_text(root, "{*}CustomizationID"),
        profile_id=_text(root, "{*}ProfileID"),
        number=_text(root, "{*}ID"),
        issue_date=_iso_date(_text(root, "{*}IssueDate")),
        currency=_text(root, "{*}DocumentCurrencyCode").upper(),
        buyer_reference=_text(root, "{*}BuyerReference"),
        order_reference=_text(root, "{*}OrderReference/{*}ID"),
        note=_text(root, "{*}Note"),
    )
    result.type_code = _text(root, "{*}CreditNoteTypeCode" if credit else "{*}InvoiceTypeCode")
    if result.type_code in CREDIT_NOTE_CODES:
        result.document = "credit_note"
    due = _iso_date(_text(root, "{*}DueDate"))
    if due is None:
        due = _iso_date(_text(root, "{*}PaymentMeans/{*}PaymentDueDate"))
    result.due_date = due
    party = root.find("{*}AccountingSupplierParty/{*}Party")
    result.supplier_name = _text(party, "{*}PartyLegalEntity/{*}RegistrationName") or _text(
        party, "{*}PartyName/{*}Name"
    )
    result.supplier_vat_id = _ubl_party_vat(party)
    result.iban = _text(root, "{*}PaymentMeans/{*}PayeeFinancialAccount/{*}ID").replace(" ", "")
    monetary = root.find("{*}LegalMonetaryTotal")
    result.lines_total = _amount_at(monetary, "{*}LineExtensionAmount")
    result.allowance_total = _amount_at(monetary, "{*}AllowanceTotalAmount")
    result.charge_total = _amount_at(monetary, "{*}ChargeTotalAmount")
    result.total_net = _amount_at(monetary, "{*}TaxExclusiveAmount")
    result.total_gross = _amount_at(monetary, "{*}TaxInclusiveAmount")
    result.payable = _amount_at(monetary, "{*}PayableAmount")
    # The tax in the currency of the document (a second TaxTotal may be in the tax currency).
    for total in _all(root, "{*}TaxTotal"):
        amount = total.find("{*}TaxAmount")
        if amount is None:
            continue
        if not amount.get("currencyID") or amount.get("currencyID", "").upper() == result.currency:
            result.total_tax = _decimal(amount.text or "")
            break
    for node in _all(root, "{*}AllowanceCharge"):
        amount = _amount_at(node, "{*}Amount")
        if amount is None:
            continue
        result.charges.append(
            Charge(
                is_charge=_text(node, "{*}ChargeIndicator").lower() == "true",
                amount=amount,
                reason=_text(node, "{*}AllowanceChargeReason"),
                tax_rate=_amount_at(node, "{*}TaxCategory/{*}Percent"),
            )
        )
    _ubl_lines(root, credit, result)
    return result


# --- CII -----------------------------------------------------------------------------------------------------------


def _from_cii(root: ET.Element) -> EInvoice:
    document = root.find("{*}ExchangedDocument")
    context = root.find("{*}ExchangedDocumentContext")
    trade = root.find("{*}SupplyChainTradeTransaction")
    agreement = trade.find("{*}ApplicableHeaderTradeAgreement") if trade is not None else None
    settlement = trade.find("{*}ApplicableHeaderTradeSettlement") if trade is not None else None
    result = EInvoice(
        syntax=SYNTAX_CII,
        document="invoice",
        type_code=_text(document, "{*}TypeCode"),
        customization_id=_text(context, "{*}GuidelineSpecifiedDocumentContextParameter/{*}ID"),
        profile_id=_text(context, "{*}BusinessProcessSpecifiedDocumentContextParameter/{*}ID"),
        number=_text(document, "{*}ID"),
        issue_date=_cii_date(document.find("{*}IssueDateTime")) if document is not None else None,
        currency=_text(settlement, "{*}InvoiceCurrencyCode").upper(),
        buyer_reference=_text(agreement, "{*}BuyerReference"),
        order_reference=_text(agreement, "{*}BuyerOrderReferencedDocument/{*}IssuerAssignedID"),
        note=_text(document, "{*}IncludedNote/{*}Content"),
    )
    if result.type_code in CREDIT_NOTE_CODES:
        result.document = "credit_note"
    seller = agreement.find("{*}SellerTradeParty") if agreement is not None else None
    result.supplier_name = _text(seller, "{*}Name")
    registrations = _all(seller, "{*}SpecifiedTaxRegistration/{*}ID")
    vat = next((r for r in registrations if r.get("schemeID", "").upper() == "VA"), None)
    result.supplier_vat_id = " ".join(((vat.text if vat is not None else "") or "").split())
    result.iban = _text(
        settlement, "{*}SpecifiedTradeSettlementPaymentMeans/{*}PayeePartyCreditorFinancialAccount/{*}IBANID"
    ).replace(" ", "")
    terms = settlement.find("{*}SpecifiedTradePaymentTerms/{*}DueDateDateTime") if settlement is not None else None
    result.due_date = _cii_date(terms)
    summation = (
        settlement.find("{*}SpecifiedTradeSettlementHeaderMonetarySummation") if settlement is not None else None
    )
    result.lines_total = _amount_at(summation, "{*}LineTotalAmount")
    result.charge_total = _amount_at(summation, "{*}ChargeTotalAmount")
    result.allowance_total = _amount_at(summation, "{*}AllowanceTotalAmount")
    result.total_net = _amount_at(summation, "{*}TaxBasisTotalAmount")
    result.total_gross = _amount_at(summation, "{*}GrandTotalAmount")
    result.payable = _amount_at(summation, "{*}DuePayableAmount")
    for total in _all(summation, "{*}TaxTotalAmount"):
        if not total.get("currencyID") or total.get("currencyID", "").upper() == result.currency:
            result.total_tax = _decimal(total.text or "")
            break
    for node in _all(settlement, "{*}SpecifiedTradeAllowanceCharge"):
        amount = _amount_at(node, "{*}ActualAmount")
        if amount is None:
            continue
        result.charges.append(
            Charge(
                is_charge=_text(node, "{*}ChargeIndicator/{*}Indicator").lower() == "true",
                amount=amount,
                reason=_text(node, "{*}Reason"),
                tax_rate=_amount_at(node, "{*}CategoryTradeTax/{*}RateApplicablePercent"),
            )
        )
    if trade is not None:
        for node in _all(trade, "{*}IncludedSupplyChainTradeLineItem"):
            price = _amount_at(node, "{*}SpecifiedLineTradeAgreement/{*}NetPriceProductTradePrice/{*}ChargeAmount")
            base = _amount_at(node, "{*}SpecifiedLineTradeAgreement/{*}NetPriceProductTradePrice/{*}BasisQuantity")
            if price is not None and base:
                price = price / base
            quantity_node = node.find("{*}SpecifiedLineTradeDelivery/{*}BilledQuantity")
            result.lines.append(
                Line(
                    place=_text(node, "{*}AssociatedDocumentLineDocument/{*}LineID"),
                    name=_text(node, "{*}SpecifiedTradeProduct/{*}Name"),
                    description=_text(node, "{*}SpecifiedTradeProduct/{*}Description"),
                    article_number=_text(node, "{*}SpecifiedTradeProduct/{*}SellerAssignedID"),
                    quantity=_decimal(quantity_node.text or "") if quantity_node is not None else None,
                    unit_code=quantity_node.get("unitCode", "") if quantity_node is not None else "",
                    unit_price=price,
                    net=_amount_at(
                        node,
                        "{*}SpecifiedLineTradeSettlement/{*}SpecifiedTradeSettlementLineMonetarySummation/{*}LineTotalAmount",
                    ),
                    tax_rate=_amount_at(
                        node, "{*}SpecifiedLineTradeSettlement/{*}ApplicableTradeTax/{*}RateApplicablePercent"
                    ),
                )
            )
    return result


# --- Checks ----------------------------------------------------------------------------------------------------------


def _differs(first: Decimal, second: Decimal) -> bool:
    return abs(first - second) > TOLERANCE


def _check(result: EInvoice) -> None:
    """Compare what the file says with itself; each difference is a warning (the invoice is kept all the same)."""
    warnings = result.warnings
    if not result.number:
        warnings.append(_("The e-invoice has no invoice number."))
    if result.issue_date is None:
        warnings.append(_("The e-invoice has no readable invoice date."))
    if not result.currency:
        warnings.append(_("The e-invoice names no currency."))
    if result.total_net is None and result.total_gross is None:
        warnings.append(_("The e-invoice has no totals."))
    if result.type_code in SELF_BILLED_CODES and not result.is_credit_note:
        warnings.append(
            _("The document is a self-billed invoice (type %(code)s): the buyer wrote it. Check that it belongs here.")
            % {"code": result.type_code}
        )
    line_sum = sum((line.net for line in result.lines if line.net is not None), Decimal(0))
    lines_known = bool(result.lines) and all(line.net is not None for line in result.lines)
    if lines_known and result.lines_total is not None and _differs(line_sum, result.lines_total):
        warnings.append(
            _("The sum of the positions (%(lines)s) differs from the total of the positions (%(total)s).")
            % {"lines": line_sum, "total": result.lines_total}
        )
    base = result.lines_total if result.lines_total is not None else (line_sum if lines_known else None)
    if base is not None and result.total_net is not None:
        expected = base - (result.allowance_total or Decimal(0)) + (result.charge_total or Decimal(0))
        if result.allowance_total is None and result.charge_total is None and result.charges:
            expected = (
                base
                - sum((c.amount for c in result.charges if not c.is_charge), Decimal(0))
                + sum((c.amount for c in result.charges if c.is_charge), Decimal(0))
            )
        if _differs(expected, result.total_net):
            warnings.append(
                _(
                    "The positions with their discounts and surcharges (%(expected)s) differ from the total net "
                    "(%(total)s)."
                )
                % {"expected": expected, "total": result.total_net}
            )
    if result.total_net is not None and result.total_tax is not None and result.total_gross is not None:
        if _differs(result.total_net + result.total_tax, result.total_gross):
            warnings.append(
                _("Net (%(net)s) plus tax (%(tax)s) is not the gross total (%(gross)s).")
                % {"net": result.total_net, "tax": result.total_tax, "gross": result.total_gross}
            )
    if result.total_tax is None and result.total_net is not None and result.total_gross is not None:
        result.total_tax = result.total_gross - result.total_net
        result.tax_derived = True


def parse(data: bytes) -> EInvoice:
    """Read an e-invoice XML.

    Raises:
        EInvoiceError: The XML is unsafe, not well-formed, or no UBL / CII invoice; ``str(error)`` says why.
    """
    root = _root_of(data)
    namespace, _separator, local = root.tag[1:].partition("}") if root.tag.startswith("{") else ("", "", root.tag)
    if namespace == NS_UBL_INVOICE and local == "Invoice":
        result = _from_ubl(root, credit=False)
    elif namespace == NS_UBL_CREDIT_NOTE and local == "CreditNote":
        result = _from_ubl(root, credit=True)
    elif namespace == NS_CII and local == "CrossIndustryInvoice":
        result = _from_cii(root)
    else:
        raise EInvoiceError(
            _(
                "The XML is not an e-invoice we know (UBL Invoice or CreditNote, or UN/CEFACT CrossIndustryInvoice); "
                "its root element is “%(name)s”."
            )
            % {"name": local[:60]}
        )
    _check(result)
    return result


# --- The proposal for the register ---------------------------------------------------------------------------------


def _row_of_line(line: Line, credit: bool) -> dict[str, Any]:
    """A position of the proposal from a line of the e-invoice."""
    description = line.name or line.description
    hints: list[str] = []
    quantity = line.quantity
    price = line.unit_price
    if quantity is not None and quantity <= 0:
        # A negative or zero quantity cannot be booked in as pieces: keep the amount as one position.
        price = line.net
        quantity = Decimal(1)
        hints.append(_("The e-invoice gives a quantity of zero or less; the position is kept as one piece."))
    elif quantity is not None and line.net is not None:
        # The price of the position is what its net amount says (line discounts included), not only the unit price.
        if price is None or abs(quantity * price - line.net) > TOLERANCE:
            try:
                price = line.net / quantity
            except InvalidOperation:  # a quantity so small that the price has no place
                price, quantity = line.net, Decimal(1)
            if line.unit_price is not None:
                hints.append(_("The unit price was worked out from the net amount of the position (discounts)."))
    if quantity is None:
        quantity = Decimal(1)
        price = line.net if price is None else price
    elif quantity != 1 and price is not None and line.net is not None:
        # The price is kept to four places: if quantity × price does not give the net amount of the file back to the
        # cent (5000 pieces at 1.23 per 1000, 0.00333 a piece), the position is one piece at the net amount.
        try:
            rounded = price.quantize(Decimal("0.0001"))
            exact = money(quantity * rounded) == money(line.net)
        except InvalidOperation:
            exact = False
        if not exact:
            hints.append(_("The unit price does not fit four decimal places; the position is kept as one piece."))
            quantity, price = Decimal(1), line.net
    row: dict[str, Any] = {
        "description": description,
        "article_number": line.article_number,
        "quantity": str(quantity),
        "unit_price_net": str(price.quantize(Decimal("0.0001"))) if price is not None else "",
        "tax_rate": str(line.tax_rate) if line.tax_rate is not None else "",
        "hints": hints,
    }
    if credit:
        row["kind"] = "other"
    elif price is not None and price < 0:
        row["kind"] = "cost"  # only an ancillary cost can be negative (a discount)
    else:
        row["kind"] = ""  # by the words of the description, as for every reading without a kind
    return row


def proposal(result: EInvoice) -> dict[str, Any]:
    """The reading of an e-invoice as a proposal for :func:`rentalars.incoming.reading.apply_proposal`."""
    from rentalars.material import purchases

    supplier = purchases.match_supplier(result.supplier_name) if result.supplier_name else None
    positions = [_row_of_line(line, result.is_credit_note) for line in result.lines if line.name or line.description]
    for charge in result.charges:
        label = charge.reason or (_("Surcharge") if charge.is_charge else _("Discount"))
        positions.append(
            {
                "description": label,
                "quantity": "1",
                "unit_price_net": str(charge.amount if charge.is_charge else -charge.amount),
                "tax_rate": str(charge.tax_rate) if charge.tax_rate is not None else "",
                "kind": "cost",
                "charge": True,  # a reading that must cut positions keeps these (they change the total)
                "hints": [],
            }
        )
    notes = []
    if result.is_credit_note:
        notes.append(
            _(
                "This is a credit note: the amounts stand as the document writes them. Its positions are of the kind "
                "“other”, so no goods can be booked in from it."
            )
        )
    if result.tax_derived:
        notes.append(_("The document gives no tax total; it was worked out as gross minus net."))
    return {
        "source": "einvoice",
        "supplier": {
            "name": supplier.name if supplier is not None else result.supplier_name,
            "id": supplier.pk if supplier is not None else None,
            "existing": supplier is not None,
        },
        "invoice_number": result.number,
        "invoice_date": result.issue_date.isoformat() if result.issue_date else "",
        "due_date": result.due_date.isoformat() if result.due_date else "",
        "currency": result.currency,
        "total_net": str(result.total_net) if result.total_net is not None else "",
        "total_tax": str(result.total_tax) if result.total_tax is not None else "",
        "total_gross": str(result.total_gross) if result.total_gross is not None else "",
        "note": " ".join(notes),
        "positions": positions,
        "einvoice": result.details(),
    }


# --- The XML in a PDF ------------------------------------------------------------------------------------------------


def _filespecs(reader: Any) -> list[Any]:
    """The file specifications of a PDF: its embedded files (name tree) and its associated files (``/AF``)."""
    root = reader.trailer["/Root"]
    specs: list[Any] = []

    def walk(node: Any, depth: int = 0) -> None:
        node = node.get_object() if hasattr(node, "get_object") else node
        if depth > 6 or node is None or len(specs) >= _MAX_ATTACHMENTS:
            return
        names = node.get("/Names")
        if names is not None:
            items = names.get_object()
            for index in range(1, len(items), 2):
                specs.append(items[index].get_object())
        for kid in node.get("/Kids") or []:
            walk(kid, depth + 1)

    tree = root.get("/Names")
    if tree is not None:
        embedded = tree.get_object().get("/EmbeddedFiles")
        if embedded is not None:
            walk(embedded)
    for spec in root.get("/AF") or []:
        specs.append(spec.get_object())
    return specs[:_MAX_ATTACHMENTS]


def xml_in_pdf(data: bytes) -> bytes | None:
    """The XML of an e-invoice attached to a PDF (ZUGFeRD / Factur-X), or ``None`` if there is none.

    The usual names (:data:`ATTACHMENT_NAMES`) come first, then any other ``.xml`` attachment. An attachment is not
    decompressed beyond :data:`MAX_ATTACHMENT_BYTES`. It is *not* checked here whether it is an invoice – that is
    :func:`parse`.
    """
    try:
        from pypdf import PdfReader, apply_configuration

        from rentalars.material.purchases import _PDF_LIMITS
    except ImportError:  # pragma: no cover - pypdf is part of the requirements
        return None
    found: dict[str, bytes] = {}
    try:
        with apply_configuration(**{**_PDF_LIMITS, "zlib_maximum_output_length": MAX_ATTACHMENT_BYTES}):
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                reader.decrypt("")
            for spec in _filespecs(reader):
                name = str(spec.get("/UF") or spec.get("/F") or "")
                if not name.lower().endswith(".xml"):
                    continue
                stream = (spec.get("/EF") or {}).get("/F")
                if stream is None:
                    continue
                stream = stream.get_object()
                if int(stream.get("/Length", 0) or 0) > MAX_ATTACHMENT_BYTES:
                    continue
                content = stream.get_data()
                if len(content) <= MAX_ATTACHMENT_BYTES:
                    found.setdefault(name.lower().rsplit("/", 1)[-1], bytes(content))
    except Exception:  # pypdf raises many kinds of errors on broken files; the PDF is then just a PDF
        return None
    for name in ATTACHMENT_NAMES:
        if name in found:
            return found[name]
    return next(iter(found.values()), None)
