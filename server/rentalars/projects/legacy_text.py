# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading an old outgoing invoice from its text with simple patterns – the way without AI (legacy import; PRJ-130).

The requirement: a fallback (pattern heuristics) for when the AI is off, so that the feature stays usable with manual
correction. Without the AI (or when it fails) the text of the PDF is searched for

* invoice number, invoice date, currency and the totals – the way "Kauf einpflegen" does it
  (:func:`rentalars.material.purchases.head_from_text`, :func:`~rentalars.material.purchases.totals_in_text`), amounts
  read as the invoice writes them (German "1.072,50", English "1,072.50");
* the service period ("Leistungszeitraum", "vom … bis …"), the event ("Veranstaltung:", "Projekt:", "Betreff:") and its
  venue, "bezahlt am …";
* the customer: a customer of the system whose name stands in the text; else the address block – the first line with a
  postal code that is not the company's own, the street above it, the name above that – and the VAT ID that is not the
  company's;
* the positions: a line that ends in one to three amounts (unit price, total) is a position; its quantity is what
  makes quantity × price fit the total, and a text line between two positions belongs to the first as its note.

It is a help, not a reader: layouts of old systems differ, so everything it finds is only a *proposal* that the preview
shows to be checked and corrected, and a layout it does not understand gives an empty list of positions (the preview
then has empty rows to type in). Nothing here touches the database but reading the master data to match against.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any

from rentalars.core.money import money
from rentalars.material import purchases
from rentalars.projects.legacy_draft import (
    LIMITS,
    MAX_LINES,
    ZERO,
    CustomerPart,
    Draft,
    InvoicePart,
    Line,
    Totals,
    clip,
    date_of,
    decimal_of,
    long_text,
    vat_id_of,
)

_AMOUNT = r"-?\d{1,3}(?:[.  ]\d{3})*,\d{2}|-?\d+,\d{2}|-?\d{1,3}(?:,\d{3})+\.\d{2}|-?\d+\.\d{2}"
#: A line of a position: an optional running number, the text, one to three amounts (a percentage is no amount).
_POSITION = re.compile(
    rf"^\s*(?:(?P<pos>\d{{1,3}})[.)]?\s+)?(?P<body>\S.*?)\s+(?P<amounts>(?:(?:{_AMOUNT})\s*(?:€|EUR|eur|Euro)?\s*){{1,3}})$"
)
_AMOUNT_TOKEN = re.compile(_AMOUNT)
_PERCENT = re.compile(rf"(?:{_AMOUNT}|\d{{1,3}})\s*%")
#: Lines that are totals, taxes, bank or payment data and never a position.
_NOT_A_POSITION = re.compile(
    r"(?i)\b(?:netto|brutto|zwischensumme|gesamt|gesamtbetrag|rechnungsbetrag|endbetrag|summe|mwst|ust|umsatzsteuer|"
    r"mehrwertsteuer|zu\s+zahlen|zahlbar|total|subtotal|vat|tax|übertrag|iban|bic|skonto|steuernummer|ust-?id|"
    r"amount\s+due|seite|page)\b"
)
_HEADER = re.compile(r"(?i)\b(?:bezeichnung|beschreibung|leistung|artikel|description|item)\b")
_TOTALS_START = re.compile(r"(?i)\b(?:zwischensumme|nettobetrag|summe\s+netto|gesamtbetrag|rechnungsbetrag|subtotal)\b")
_DATE_TEXT = r"\d{1,2}\.\d{1,2}\.\d{4}"
_PERIOD = re.compile(
    rf"(?i)(?:leistungszeitraum|leistungsdatum|lieferdatum|veranstaltungsdatum|veranstaltung\s+am|zeitraum|"
    rf"service\s+period|vom)\s*[:.]?\s*(?P<a>{_DATE_TEXT})(?:\s*(?:-|–|—|bis|to)\s*(?P<b>{_DATE_TEXT}))?"
)
_EVENT = re.compile(r"(?i)^\W*(?:veranstaltung|projekt|event|betreff|anlass|auftrag)\s*[:\-–]\s*(?P<value>\S.*)$")
_VENUE = re.compile(r"(?i)^\W*(?:veranstaltungsort|spielort|location|venue)\s*[:\-–]\s*(?P<value>\S.*)$")
_PAID = re.compile(rf"(?i)(?:bezahlt|beglichen|zahlungseingang)\s*(?:am|vom|:)?\s*(?P<date>{_DATE_TEXT})?")
_VAT_LABEL = re.compile(
    r"(?i)(?:ust\.?-?\s*id(?:nr)?\.?|ust-?idnr|vat\s*(?:id|no\.?|number)?|umsatzsteuer-?id(?:entifikationsnummer)?)"
    r"[ ]*[:.]?[ ]*(?P<id>[A-Z]{2}[ ]?(?:U[ ]?)?(?:\d[ ]?){7,12})"
)
_VAT_PLAIN = re.compile(r"\b[A-Z]{2}\d{9,11}\b")
_RATE = re.compile(
    r"(?i)(?:(?P<a>\d{1,2}(?:,\d{1,2})?)\s*%\s*(?:mwst|ust|umsatzsteuer|mehrwertsteuer|vat))|"
    r"(?:(?:mwst|ust|umsatzsteuer|mehrwertsteuer|vat)\.?\s*(?:von|in\s+höhe\s+von)?\s*(?P<b>\d{1,2}(?:,\d{1,2})?)\s*%)"
)
_POSTAL_LINE = re.compile(r"^(?:[A-Z]{1,2}[- ])?(?P<postal>\d{4,5})\s+(?P<city>[^\d,].*)$")
_PERSON_LINE = re.compile(r"(?i)^(?:frau|herr|herrn|fr\.|hr\.|z\.?\s?hd\.?|zu\s+händen|attn\.?|attention)\b")
_STREET_LINE = re.compile(r"^\D[^\d]{2,}.*\d+\s?[a-zA-Z]?(?:[-/]\d+)?$|^\d+.*\D$")


def _lines_of(text: str) -> list[str]:
    """The non-empty lines of the invoice text."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _amounts(numbers: purchases.InvoiceNumbers, tokens: list[str]) -> list[Decimal]:
    """The amounts of some tokens as the invoice writes them; a token that is none is left out."""
    found = []
    for token in tokens:
        amount = purchases.parse_amount(token.replace(" ", ""), decimal_comma=numbers.decimal_comma)
        if amount is not None:
            found.append(amount)
    return found


def _quantity_fits(quantity: Decimal, price: Decimal, total: Decimal) -> bool:
    """Whether quantity × price makes the total up to a cent per piece (the discount aside, it is the same line)."""
    return abs(money(quantity * price) - total) <= Decimal("0.02") + Decimal("0.005") * abs(quantity)


def position_from_line(line: str, numbers: purchases.InvoiceNumbers) -> Line | None:
    """One position from one line of text, or ``None`` if the line is none.

    The last amount is the total of the position, the one before it the unit price; with one amount alone it is the
    price of one piece. The quantity is a number at the end of the text (with a unit) that makes quantity × price
    fit the total; else total ÷ price if that is a sensible number; a discount shows as a quantity × price that is
    larger than the total.
    """
    if _NOT_A_POSITION.search(line):
        return None
    match = _POSITION.match(line)
    if match is None:
        return None
    body = match["body"].strip()
    if not any(character.isalpha() for character in body):
        return None
    cleaned_amounts = _PERCENT.sub(" ", match["amounts"])
    tokens = _AMOUNT_TOKEN.findall(cleaned_amounts)
    amounts = _amounts(numbers, tokens)
    if not amounts or len(amounts) != len(tokens):
        return None
    total = amounts[-1]
    price = amounts[-2] if len(amounts) >= 2 else total
    quantity = Decimal("1")
    unit = ""
    discount = ZERO
    tail = re.search(r"(?P<qty>\d+(?:[.,]\d{1,2})?)\s*(?P<unit>[A-Za-zÄÖÜäöü][A-Za-zÄÖÜäöü.]{0,7})?\s*$", body)
    if len(amounts) >= 2 and price != 0:
        if tail is not None:
            candidate = purchases.parse_amount(tail["qty"], decimal_comma=True)
            if candidate is not None and candidate > 0:
                if _quantity_fits(candidate, price, total):
                    quantity, unit = candidate, tail["unit"] or ""
                    body = body[: tail.start()].strip() or body
                elif 0 < total < money(candidate * price) and candidate * price > 0:
                    # A discount: quantity × price is more than the total.
                    ratio = total / (candidate * price)
                    if Decimal("0.01") <= ratio < 1:
                        quantity, unit = candidate, tail["unit"] or ""
                        discount = (Decimal(1) - ratio).quantize(Decimal("0.01")) * 100
                        body = body[: tail.start()].strip() or body
        if quantity == 1 and unit == "":
            share = total / price
            if share > 0 and share == share.quantize(Decimal("0.01")) and share <= Decimal("100000"):
                quantity = share
    title = clip(re.sub(r"\s+", " ", body), LIMITS["title"])
    if not title:
        return None
    return Line(
        title=title,
        quantity=quantity,
        unit=clip(unit.strip("."), LIMITS["unit"]),
        unit_price=price,
        discount=discount,
        amount=total,
    )


def positions_from_text(text: str, numbers: purchases.InvoiceNumbers | None = None) -> list[Line]:
    """The positions of the invoice: the lines between the table head and the totals that look like a position."""
    numbers = numbers or purchases.invoice_numbers(text)
    lines = _lines_of(text)
    start = 0
    for index, line in enumerate(lines):
        if _HEADER.search(line) and re.search(r"(?i)\b(?:menge|preis|betrag|qty|price|amount|anzahl)\b", line):
            start = index + 1
            break
    found: list[Line] = []
    previous_was_position = False
    for line in lines[start:]:
        if _TOTALS_START.search(line) and found:
            break
        if _HEADER.search(line) and re.search(r"(?i)\b(?:menge|preis|qty|price)\b", line):
            previous_was_position = False
            continue  # the head of a table on the next page
        position = position_from_line(line, numbers)
        if position is not None:
            found.append(position)
            previous_was_position = True
            if len(found) >= MAX_LINES:
                break
            continue
        if previous_was_position and found and len(line) <= 400 and not _NOT_A_POSITION.search(line):
            # A text between two positions belongs to the first as its note ("Aufbau am Freitag, inkl. Techniker").
            found[-1].note = long_text(f"{found[-1].note}\n{line}".strip())
        else:
            previous_was_position = False
    return found


def tax_rate_in_text(text: str, totals: Totals | None = None) -> Decimal | None:
    """The tax rate the invoice states ("19 % MwSt."); with several rates ``None`` – the preview asks.

    Without a rate in the text it is taken from the totals when they fit one (tax ÷ net).
    """
    rates = set()
    for match in _RATE.finditer(text or ""):
        value = match["a"] or match["b"]
        rate = decimal_of((value or "").replace(",", "."), places=2, limit=Decimal("100"))
        if rate is not None:
            rates.add(rate)
    if len(rates) == 1:
        return rates.pop()
    if not rates and totals is not None and totals.net and totals.tax is not None and totals.net > 0:
        share = (totals.tax / totals.net * 100).quantize(Decimal("0.1"))
        for known in (Decimal("19"), Decimal("7"), Decimal("0"), Decimal("16"), Decimal("5")):
            if abs(share - known) <= Decimal("0.3"):
                return known
    return None


def _tax_total(text: str, numbers: purchases.InvoiceNumbers) -> Decimal | None:
    """The amount of tax on a line that names the tax ("zzgl. 19 % MwSt. 190,00 €"): the largest such amount."""
    found = []
    for line in _lines_of(text):
        if not re.search(r"(?i)\b(?:mwst|ust|umsatzsteuer|mehrwertsteuer|vat)\b", line):
            continue
        tokens = _AMOUNT_TOKEN.findall(_PERCENT.sub(" ", line))
        amounts = _amounts(numbers, tokens[-1:]) if tokens else []
        found.extend(amount for amount in amounts if amount >= 0)
    return money(max(found)) if found else None


def customer_from_text(text: str) -> CustomerPart:
    """The customer by the address block and the VAT ID: not the company's own (``CompanyProfile``)."""
    from rentalars.core.models import CompanyProfile

    company = CompanyProfile.load()
    own_vat = vat_id_of(company.vat_id)
    own_postal = (company.postal_code or "").strip()
    lines = _lines_of(text)
    part = CustomerPart()
    for match in _VAT_LABEL.finditer(text or ""):
        candidate = vat_id_of(match["id"])
        if candidate and candidate != own_vat and re.fullmatch(r"[A-Z]{2}[0-9A-Z+*]{2,13}", candidate):
            part.vat_id = candidate
            break
    if not part.vat_id:
        for match in _VAT_PLAIN.finditer(text or ""):
            if match[0] != own_vat:
                part.vat_id = match[0]
                break
    for index, line in enumerate(lines[:30]):
        postal = _POSTAL_LINE.match(line)
        if postal is None or index == 0:
            continue
        around = " ".join(lines[max(0, index - 3) : index]).casefold()
        own_address = (
            postal["postal"] == own_postal
            and clip(postal["city"], 120).casefold() == (company.city or "").casefold()
            and bool(company.street or company.name)
            and ((company.street or "~").casefold() in around or (company.name or "~").casefold() in around)
        )
        if own_address:
            continue  # the company's own address (letterhead, footer) – a customer in the same town is not it
        part.postal_code = postal["postal"]
        part.city = clip(postal["city"], LIMITS["city"])
        above = [lines[i] for i in range(max(0, index - 3), index)]
        if above and _STREET_LINE.match(above[-1]) and any(character.isdigit() for character in above[-1]):
            part.street = clip(above.pop(), LIMITS["street"])
        above = [
            line
            for line in above
            if not re.search(r"(?i)rechnung|invoice|datum|kunden", line)
            and "·" not in line
            and " | " not in line
            and not (company.name and company.name.casefold() in line.casefold())
        ]
        # A line that names a person ("Frau Meier", "z. Hd. Herrn …") is the contact, not the company.
        people = [line for line in above if _PERSON_LINE.match(line)]
        named = [line for line in above if line not in people] or above
        if named:
            part.name = clip(named[0], LIMITS["name"])
            rest = named[1:]
            if rest:
                part.name_addition = clip(rest[0], LIMITS["name_addition"])
            elif people and named[0] not in people:
                part.name_addition = clip(people[0], LIMITS["name_addition"])
        break
    return part


def customer_in_text(text: str) -> Any:
    """A customer of the system whose name stands in the text (not the company's own); the one named first, else ``None``."""
    from rentalars.core.models import CompanyProfile
    from rentalars.customers.models import Customer
    from rentalars.customers.services import normalised_name

    own = normalised_name(CompanyProfile.load().name or "")
    haystack = " ".join(re.findall(r"\w+", (text or "").casefold()))
    best: tuple[int, Any] | None = None
    for customer in Customer.objects.filter(anonymised_at__isnull=True, is_active=True).only("id", "name", "number"):
        name = normalised_name(customer.name)
        if len(name) < 6 or name == own:
            continue
        at = haystack.find(name)
        if at != -1 and (best is None or at < best[0]):
            best = (at, customer)
    return best[1] if best else None


def draft_from_text(text: str) -> Draft:
    """A draft from the text of an invoice by patterns only: head, period, customer, positions, totals; see the module text."""
    numbers = purchases.invoice_numbers(text)
    head = purchases.head_from_text(text)
    lines = _lines_of(text)
    invoice = InvoicePart(
        number=re.sub(r"[^A-Za-z0-9\-/._ ]", "", head["invoice_number"] or "")[: LIMITS["number"]],
        date=head["invoice_date"],
        currency=purchases.currency_code(head["currency"]) or "EUR",
    )
    period = _PERIOD.search(text or "")
    if period:
        first = date_of(period["a"])
        invoice.service_start = first
        invoice.service_end = date_of(period["b"]) or first
    for line in lines:
        match = _EVENT.match(line)
        if match and not invoice.event_name:
            invoice.event_name = clip(match["value"], LIMITS["event_name"])
        match = _VENUE.match(line)
        if match and not invoice.venue:
            invoice.venue = clip(match["value"], LIMITS["venue"])
    paid = _PAID.search(text or "")
    if paid and re.search(r"(?i)\b(?:bezahlt|beglichen|zahlungseingang)\b", paid[0]) and paid["date"]:
        invoice.paid, invoice.paid_on = True, date_of(paid["date"])
    totals = Totals(
        net=decimal_of(head["total_net"], places=2, limit=Decimal("9999999999.99")),
        tax=_tax_total(text, numbers),
        gross=decimal_of(head["total_gross"], places=2, limit=Decimal("9999999999.99")),
    )
    positions = positions_from_text(text, numbers)
    rate = tax_rate_in_text(text, totals)
    for position in positions:
        position.tax_percent = rate
    customer = customer_from_text(text)
    known = customer_in_text(text)
    if known is not None:
        customer.customer_id = known.pk
    draft = Draft(
        customer=customer,
        invoice=invoice,
        lines=positions,
        totals=totals,
        source="text",
        note=clip(getattr(text, "note", ""), 500),
    )
    if invoice.date is None and invoice.service_end is not None:
        draft.invoice.date = None
    return draft


def period_days(start: datetime.date | None, end: datetime.date | None) -> int:
    """The days of a service period, both ends counted; 0 without a start."""
    if start is None:
        return 0
    return ((end or start) - start).days + 1
