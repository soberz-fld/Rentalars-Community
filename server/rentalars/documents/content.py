# SPDX-License-Identifier: GPL-3.0-or-later
"""What a document shows, put together from a project (DOK-003, DOK-004, DOK-006, DOK-010 – the offer of DOK-002).

An offer can show the groups with their sums only, without the positions in
them (DOK-013, :func:`only_groups`).

The content is plain data – texts, numbers, dates – so that it can be stored
with the document as it was (DOK-007) and turned into the PDF and, for an
invoice, into the XRechnung (``documents.xrechnung``) without a second
calculation that could come out differently.

Amounts come from the price calculation of the project
(``projects.pricing``). The net amounts per tax rate are taken from there as
they are: a discount of a group lowers the lines of every tax rate in the
same proportion, and the electronic invoice expresses that as a reduction
per tax rate (see :func:`_adjustments`).

Optional and alternative lines (PRJ-075) appear on an offer and an order
confirmation, marked and outside every sum; an invoice leaves them out, as it
leaves out optional groups (PRJ-040). Discounts appear as they apply, i.e.
limited to the maximum discount of a job function (PER-026).

Customer material (PRJ-096) – the customer's own gear, taken along – appears
on an offer and an order confirmation where it stands, without price and with
the hint that it is taken along without charge (``Position.customer_material``);
it is part of no sum. An offer with the groups only (DOK-013) keeps it listed
under its group, so the customer sees that the gear will be there. An
invoice leaves it out: there is nothing to charge, and the electronic invoice
lists only positions with an amount. The delivery note lists it with the
same hint; it is on the packlist, too.

Nested groups (PRJ-037) appear in the order of the planning: a group's own
positions, its subgroups each with their subtotal, then the group's
discount and its subtotal with everything in it (see :class:`Section`). The
positions are numbered straight through, and the electronic invoice lists
them flat as always – the sums come from the same price calculation.

Whole projects with subprojects (PRJ-045, PRJ-046, PRJ-060)
------------------------------------------------------------
Billing happens at the whole project: its offer, order confirmation and
invoice hold its own positions and then every part that is not cancelled,
each as a block – a section that opens the part with its number, name and
rental period, the part's groups, and a section that closes it with the
part's subtotal (``Section.subproject_block``). The numbers of the
positions run through the whole document; net, taxes per rate and gross
are those of all included projects together (``projects.family_prices``),
and the service period spans all of them. A part on its own gets no priced
document (see ``documents.services.check_can_make``). Lines taken over from
another part are not charged and so are left out; the delivery note of the
taking part names them as "taken over from" that part.
"""

from __future__ import annotations

import datetime
import itertools
import string
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.core.i18n import format_date, local_pattern, plural_of
from rentalars.core.money import format_decimal, format_money, money, plain_decimal
from rentalars.projects.models import Project

ZERO = Decimal("0")

#: Units of measure as UN/ECE Recommendation 20 codes, for the electronic invoice (EN 16931 BT-130).
UNIT_CODES = {
    "stk": "H87",
    "stück": "H87",
    "st": "H87",
    "m": "MTR",
    "kg": "KGM",
    "l": "LTR",
    "h": "HUR",
    "std": "HUR",
    "tag": "DAY",
    "tage": "DAY",
    "km": "KMT",
    "pauschal": "LS",
    "psch": "LS",
    "set": "SET",
    "paar": "PR",
    # UIX-029: the English abbreviations (start data of an English installation) – the same codes.
    "pcs": "H87",
    "pc": "H87",
    "piece": "H87",
    "pieces": "H87",
    "hr": "HUR",
    "hrs": "HUR",
    "hour": "HUR",
    "hours": "HUR",
    "day": "DAY",
    "days": "DAY",
    "flat": "LS",
    "kit": "SET",
    "pair": "PR",
}


def unit_code(abbreviation: str) -> str:
    """The UN/ECE code of a unit; ``C62`` ("one") if it is not known."""
    return UNIT_CODES.get((abbreviation or "").strip().lower().rstrip("."), "C62")


#: Member states of the EU by the prefix of their VAT IDs (Greece: EL). Not XI: Northern Ireland counts as EU for goods
#: only, a service to it is not taxed where the customer is.
EU_PREFIXES = frozenset(
    [
        "AT",
        "BE",
        "BG",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "EL",
        "ES",
        "FI",
        "FR",
        "HR",
        "HU",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    ]
)


def eu_vat_id(vat_id: str) -> str:
    """The VAT ID of a customer in another EU country, for bookings without German tax; "" otherwise."""
    vat_id = "".join((vat_id or "").split()).upper()
    return vat_id if vat_id[:2] in EU_PREFIXES and vat_id[:2] != "DE" else ""


def _small_business_now() -> bool:
    """Whether the company is a small business (§ 19 UStG) by the settings today; the default of a new document."""
    from rentalars.documents.models import AccountingSettings

    return AccountingSettings.load().small_business


def tax_category(percent: Decimal) -> str:
    """EN 16931 tax category: ``S`` standard rate, ``E`` exempt (``AE``, reverse charge, see ``DocumentContent``)."""
    return "S" if percent > ZERO else "E"


@dataclass
class Position:
    """One position of an order confirmation or invoice."""

    number: str
    title: str
    article_number: str = ""
    quantity: Decimal = ZERO
    unit: str = ""
    unit_code: str = "C62"
    details: str = ""
    unit_price: Decimal | None = None
    discount_percent: Decimal = ZERO
    base_amount: Decimal = ZERO
    discount_amount: Decimal = ZERO
    amount: Decimal = ZERO
    tax_name: str = ""
    tax_percent: Decimal = ZERO
    is_estimate: bool = False
    #: PRJ-075: "optional" or "alternative" for a line that is not part of any sum; "" for one that counts.
    variant: str = ""
    #: The words for ``variant`` on paper, e.g. "optional"; for an alternative "alternative to pos. 3" (PRJ-083).
    variant_label: str = ""
    #: PRJ-083: the line of the position, and for an alternative the line it could replace with its short name –
    #: :func:`name_alternatives` turns them into "alternative to pos. 3" once the positions are numbered.
    line_id: int | None = None
    alternative_to_line: int | None = None
    alternative_to_label: str = ""
    #: PRJ-096: the customer's own material, taken along without charge – no price, part of no sum.
    customer_material: bool = False
    #: Text line: a row of text without number, quantity and amount; ``title`` is the text, ``details`` the
    #: longer text below it.
    is_text: bool = False
    #: Product descriptions: the description of the position's product, printed under the title when the
    #: document asks for it (``DocumentContent.print_product_descriptions``); empty otherwise. The title and the
    #: ``details`` are the line's own texts and always stand.
    description: str = ""

    @property
    def counts(self) -> bool:
        """Whether the position is part of the sums (PRJ-075); customer material and text never are (PRJ-096)."""
        return not self.variant and not self.customer_material and not self.is_text


@dataclass
class Section:
    """A group, the lines without group, the personnel or the surcharges, with its subtotal.

    A group with subgroups (PRJ-037) becomes two sections around those of its
    subgroups: one that ``opens`` it – its title and its own positions, no
    subtotal – and one that ``closes`` it after the subgroups – its discount
    and its subtotal with everything in it, no positions. The subtotals of
    the sections therefore must not simply be added up.

    A whole project's document (PRJ-046) has a block per subproject: one
    section opens it (``subproject_block``, ``part="opens"``: the heading of
    the part), its groups follow, one section closes it with the part's
    subtotal (``part="closes"``).
    """

    title: str
    description: str = ""
    positions: list[Position] = field(default_factory=list)
    subtotal: Decimal = ZERO
    #: Optional and alternative groups are shown but not added up (PRJ-040).
    optional: bool = False
    #: "Discount 10 %" or "flat price instead of 420,00" (PRJ-039); empty if none.
    adjustment_label: str = ""
    adjustment_amount: Decimal = ZERO
    #: PRJ-037: 0 for a top-level group, 1 and 2 for subgroups.
    level: int = 0
    #: PRJ-037: "" for a complete section; "opens" or "closes" for the two halves of a group with subgroups.
    #: PRJ-046: also the two sections around the block of a subproject (``subproject_block``).
    part: str = ""
    #: PRJ-046: the number of the subproject whose block the section belongs to; "" on the whole project's own.
    subproject: str = ""
    #: PRJ-046: True for the section that opens a subproject's block (its heading, no positions) and the one that
    #: closes it (the subproject's subtotal); ``part`` says which. Never added up with the others either.
    subproject_block: bool = False
    #: DOK-013: True for the sections of a group (both halves of a group with subgroups); False for the lines
    #: without group, the personnel, the surcharges and the blocks of subprojects.
    is_group: bool = False
    #: DOK-013: the offer shows only the group with its sum; the positions that make up the sum are left out.
    #: ``positions`` then holds only the optional and alternative lines, which are not part of the sum.
    positions_hidden: bool = False
    #: PRJ-083: for an alternative group, "alternative to “Licht”"; "" otherwise.
    alternative_to: str = ""
    #: PRJ-123: the overall discount of the project – one row with a negative amount in ``subtotal``,
    #: after everything the project holds; no positions. Never added up with the others either.
    overall_discount: bool = False
    #: Free outgoing documents: the positions of a document without a project – no heading, no subtotal.
    plain: bool = False
    #: Document hierarchy: the top level the section belongs to – "material" (the groups and the lines (DOK-025)
    #: without group), "personnel", "logistics" or "surcharges"; "" in older documents, for blocks of subprojects,
    #: the overall discount and documents without a project. Only used to print the levels; never added up.
    division: str = ""
    #: The first / last section of its division in this document (or block of a subproject).
    division_start: bool = False
    division_end: bool = False
    #: On the last section of the division "material": the sum of the whole division (groups and lines
    #: without group, as the price calculation has it). The other divisions are one section with its own subtotal.
    division_total: Decimal = ZERO


@dataclass
class TaxShare:
    """The net amount and tax of one tax rate (EN 16931 BG-23)."""

    name: str
    percent: Decimal
    category: str
    net: Decimal
    tax: Decimal
    #: Sum of the positions with this rate before group discounts and flat prices.
    positions_total: Decimal = ZERO

    @property
    def allowance(self) -> Decimal:
        """What group discounts and flat prices take off this rate (negative: add)."""
        return self.positions_total - self.net


@dataclass
class Deduction:
    """An advance or partial invoice that a final invoice deducts (§ 14 (5) UStG): net and tax per tax rate."""

    number: str
    issued_on: datetime.date
    title: str
    taxes: list[TaxShare] = field(default_factory=list)
    billing_type: str = ""

    @property
    def net(self) -> Decimal:
        """The net amount deducted."""
        return sum((share.net for share in self.taxes), ZERO)

    @property
    def tax(self) -> Decimal:
        """The tax deducted."""
        return sum((share.tax for share in self.taxes), ZERO)

    @property
    def gross(self) -> Decimal:
        """The gross amount deducted – what was invoiced (and paid) on account."""
        return self.net + self.tax

    @property
    def negative_gross(self) -> Decimal:
        """The gross amount as it stands in the column of amounts: a deduction is subtracted."""
        return -self.gross


@dataclass
class SimpleRow:
    """A row of a delivery note: quantity, article, name (no prices)."""

    quantity: Decimal
    unit: str
    article_number: str
    title: str
    note: str = ""
    #: PRJ-060: "2026-0042-1 Bühne Marktplatz" – the part the pieces come from straight, not from the warehouse.
    taken_over_from: str = ""
    #: PRJ-096: the customer's own material, taken along.
    customer_material: bool = False
    #: Product descriptions: the description of the product, if the delivery note asks for it.
    description: str = ""


@dataclass
class CrewRow:
    """A row of the crew disposition (DOK-004): who, when, where, as what – never a rate."""

    day: str
    start: str
    end: str
    person: str
    job_function: str
    place: str = ""
    phone: str = ""
    email: str = ""
    #: LOG-008: the vehicle the person travels with, "driver" added – empty without one.
    vehicle: str = ""


@dataclass
class DocumentContent:
    """Everything one document shows."""

    kind: str
    title: str
    number: str
    issued_on: datetime.date
    company: dict[str, Any]
    recipient: list[str]
    project: dict[str, Any]
    introduction: str = ""
    closing: str = ""
    footer: str = ""
    text_blocks: list[str] = field(default_factory=list)
    recipient_email: str = ""
    customer_number: str = ""
    #: BT-10 of the electronic invoice: the Leitweg-ID of an authority, else the project number.
    buyer_reference: str = ""
    customer_vat_id: str = ""
    #: § 19 UStG at the time of issue: a small business charges no tax, so there is no reverse charge either.
    small_business: bool = field(default_factory=lambda: _small_business_now())
    service_start: datetime.date | None = None
    service_end: datetime.date | None = None
    sections: list[Section] = field(default_factory=list)
    taxes: list[TaxShare] = field(default_factory=list)
    net_total: Decimal = ZERO
    tax_total: Decimal = ZERO
    gross_total: Decimal = ZERO
    optional_total: Decimal = ZERO
    #: PRJ-075: optional and alternative lines, not part of the total.
    optional_lines_total: Decimal = ZERO
    alternative_lines_total: Decimal = ZERO
    has_estimates: bool = False
    due_on: datetime.date | None = None
    #: DOK-010: until when an offer holds.
    valid_until: datetime.date | None = None
    #: DOK-013: "lines" – every position; "groups" – an offer with the groups and their sums only.
    detail: str = "lines"
    payment_terms_days: int | None = None
    #: A cancellation names the invoice it cancels.
    cancels_number: str = ""
    cancels_date: datetime.date | None = None
    delivery_rows: list[tuple[str, list[SimpleRow]]] = field(default_factory=list)
    crew_rows: list[CrewRow] = field(default_factory=list)
    #: Free outgoing documents: the subject line of a document without a project; empty with a project.
    reference: str = ""
    #: Product descriptions: whether the descriptions of the products stand under the positions. Chosen
    #: when the document is made; the positions carry what was chosen (``Position.description``).
    print_product_descriptions: bool = False
    #: Several invoices per project: ``Document.billing_type`` and the number among the part invoices.
    billing_type: str = ""
    billing_number: int | None = None
    #: On a final invoice the advance and partial invoices it deducts; the payable amount is the gross total
    #: less their gross amounts.
    deductions: list[Deduction] = field(default_factory=list)
    #: For an advance or partial invoice and a partial credit note, what it is about, in a sentence.
    billing_note: str = ""

    @property
    def prepaid_total(self) -> Decimal:
        """The gross amount of the deducted advance and partial invoices (EN 16931 BT-113)."""
        return sum((deduction.gross for deduction in self.deductions), ZERO)

    @property
    def payable_total(self) -> Decimal:
        """What is still to pay: the gross total less what was invoiced on account."""
        return self.gross_total - self.prepaid_total

    @property
    def tax_groups(self) -> list[TaxShare]:
        """The tax shares as the e-invoice wants them: one per category and percentage (EN 16931 BR-CO-17).

        Two tax rates of the master data may have the same percentage (say two "19 %" with different accounts); the
        invoice shows them apart, the e-invoice must not: a second sub-total with the same category and percentage is
        invalid. The amounts are added up.
        """
        merged: dict[tuple[str, Decimal], TaxShare] = {}
        for share in self.taxes:
            category = self.category_of(share.category)
            key = (category, share.percent.normalize())
            if key in merged:
                known = merged[key]
                known.net += share.net
                known.tax += share.tax
                known.positions_total += share.positions_total
            else:
                merged[key] = TaxShare(
                    name=share.name,
                    percent=share.percent,
                    category=share.category,
                    net=share.net,
                    tax=share.tax,
                    positions_total=share.positions_total,
                )
        return list(merged.values())

    @property
    def reverse_charge(self) -> bool:
        """Whether the tax is owed by the customer: a business in another EU country, and no tax charged.

        The service is taxed where the customer is (§ 3a (2), § 13b UStG); the invoice says so (§ 14a (5) UStG,
        "Steuerschuldnerschaft des Leistungsempfängers") and the e-invoice names the category ``AE`` instead of ``E``.
        """
        return (
            not self.small_business
            and bool(eu_vat_id(self.customer_vat_id))
            and any(share.category == "E" for share in self.taxes)
        )

    def category_of(self, category: str) -> str:
        """The category of the e-invoice for a stored one: ``E`` becomes ``AE`` while the customer owes the tax."""
        return "AE" if category == "E" and self.reverse_charge else category

    @property
    def booked_taxes(self) -> list[TaxShare]:
        """Net and tax per rate that this document adds to the revenue – the invoice less its deductions.

        The accounting (DATEV, Lexware Office) books these: the revenue of an advance invoice was booked with it, so
        the final invoice books the rest only. Without deductions these are the tax shares themselves.
        """
        if not self.deductions:
            return self.taxes
        rows = {
            (share.name, share.percent): TaxShare(share.name, share.percent, share.category, share.net, share.tax)
            for share in self.taxes
        }
        for deduction in self.deductions:
            for share in deduction.taxes:
                key = (share.name, share.percent)
                row = rows.setdefault(key, TaxShare(share.name, share.percent, share.category, ZERO, ZERO))
                row.net -= share.net
                row.tax -= share.tax
        return list(rows.values())

    @property
    def booked_net_total(self) -> Decimal:
        """The net amount of :attr:`booked_taxes`."""
        return sum((share.net for share in self.booked_taxes), ZERO)

    @property
    def booked_tax_total(self) -> Decimal:
        """The tax of :attr:`booked_taxes`."""
        return sum((share.tax for share in self.booked_taxes), ZERO)

    @property
    def booked_gross_total(self) -> Decimal:
        """The gross amount of :attr:`booked_taxes` – the amount the accounting books for this document."""
        return sum((share.net + share.tax for share in self.booked_taxes), ZERO)

    def as_json(self) -> dict[str, Any]:
        """The content for the database: dates and amounts as text."""
        return _jsonable(asdict(self))

    @property
    def positions(self) -> list[Position]:
        """All positions that count, in order: no optional group, no optional or alternative line."""
        return [
            position
            for section in self.sections
            if not section.optional
            for position in section.positions
            if position.counts
        ]

    @property
    def has_discounts(self) -> bool:
        """Whether any position shown has a discount – otherwise the column "Discount" is left out.

        Group discounts and flat prices are rows of their own and need no column. Text lines have no discount.
        """
        return any(
            position.discount_percent
            for section in self.sections
            for position in section.positions
            if not position.is_text
        )


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def fill(text: str, values: dict[str, str]) -> str:
    """Put the project's data into a text: "{project}" becomes "2027-0042" (DOK-005).

    Only plain placeholders are filled ("{customer}", also with a format such as "{due_date:>12}"). Anything else
    stays as it was written: an unknown "{xyz}", a "{customer.name}" or "{project[0]}" that reaches into a value,
    a stray brace. ``{{`` and ``}}`` give one brace each, as in a Python format string.
    """
    if not text:
        return ""
    try:
        parts = list(string.Formatter().parse(text))
    except ValueError:
        return text  # a stray brace: the text is printed as it was written
    result: list[str] = []
    for literal, field_name, spec, conversion in parts:
        result.append(literal)
        if field_name is None:
            continue
        written = "{" + field_name + (f"!{conversion}" if conversion else "") + (f":{spec}" if spec else "") + "}"
        if field_name not in values:
            result.append(written)
            continue
        try:
            value: Any = values[field_name]
            if conversion:
                value = string.Formatter().convert_field(value, conversion)
            result.append(format(value, spec or ""))
        except (ValueError, TypeError, KeyError):
            result.append(written)
    return "".join(result)


def unknown_placeholders(text: str, values: dict[str, str]) -> list[str]:
    """The placeholders of a text that :func:`fill` leaves as written, as they are written ("{customer.name}").

    Every placeholder in a text that is not one of ``values`` – misspelt, reaching into a value, or broken by a stray
    brace (then the text itself is named by its first brace). The page of a draft shows them, so that the text is
    corrected before the document is issued.
    """
    if not text:
        return []
    try:
        parts = list(string.Formatter().parse(text))
    except ValueError:
        start = min(text.index(brace) for brace in "{}" if brace in text)
        return [text[start:].split()[0]]
    found = []
    for _literal, field_name, spec, conversion in parts:
        if field_name is not None and field_name not in values:
            written = "{" + field_name + (f"!{conversion}" if conversion else "") + (f":{spec}" if spec else "") + "}"
            if written not in found:
                found.append(written)
    return found


def company_data() -> dict[str, Any]:
    """Name, address, contact, tax and bank data of the company (ADM-001)."""
    from rentalars.core.models import CompanyProfile

    company = CompanyProfile.load()
    return {
        "name": company.name,
        "street": company.street,
        "postal_code": company.postal_code,
        "city": company.city,
        "country": company.country,
        "lines": company.address_lines,
        "phone": company.phone,
        "email": company.email,
        "website": company.website,
        "tax_number": company.tax_number,
        "vat_id": company.vat_id,
        "bank_name": company.bank_name,
        "iban": company.iban,
        "bic": company.bic,
        "register_details": company.register_details,
        "payment_terms_days": company.payment_terms_days,
    }


def project_data(project: Project) -> dict[str, Any]:
    """The project as the head of a document shows it."""
    start = timezone.localtime(project.start)
    end = timezone.localtime(project.end)
    data = {
        "number": project.number,
        "name": project.name,
        "period": f"{start:{local_pattern('%d.%m.%Y')}} – {end:{local_pattern('%d.%m.%Y')}}",
        "venue": project.venue_label,
        "contact": project.contact.name if project.contact_id else "",
        "manager": project.manager.get_full_name() or project.manager.username if project.manager_id else "",
    }
    if project.event_start and project.event_end:
        event_start, event_end = timezone.localtime(project.event_start), timezone.localtime(project.event_end)
        data["event"] = (
            f"{event_start:{local_pattern('%d.%m.%Y %H:%M')}} – {event_end:{local_pattern('%d.%m.%Y %H:%M')}}"
        )
    return data


def placeholder_values(
    project: Project,
    *,
    due_on: datetime.date | None = None,
    terms: int | None = None,
    valid_until: datetime.date | None = None,
    validity_days: int | None = None,
) -> dict[str, str]:
    """The values for the placeholders of the texts (DOK-005).

    An offer also fills ``{valid_until}`` (DOK-010) and ``{validity_days}``,
    the number of days it holds (DOK-013).
    """
    data = project_data(project)
    # KND-004: {greeting} / {anrede} – the greeting set for the project's contact person ("" without one).
    contact = project.contact or (project.parent.contact if project.parent_id else None)
    greeting = ""
    if contact is not None:
        from rentalars.customers.greetings import greeting as greeting_of

        greeting = greeting_of(contact)
    return {
        "project": project.number,
        "project_name": project.name,
        "customer": project.customer_name,
        "period": data["period"],
        "venue": data["venue"],
        "due_date": due_on.strftime(local_pattern("%d.%m.%Y")) if due_on else "",
        "payment_terms": str(terms) if terms is not None else "",
        "valid_until": valid_until.strftime(local_pattern("%d.%m.%Y")) if valid_until else "",
        "validity_days": str(validity_days) if validity_days is not None else "",
        "greeting": greeting,
        "anrede": greeting,
    }


def free_placeholder_values(
    customer: Any,
    *,
    contact: Any = None,
    due_on: datetime.date | None = None,
    terms: int | None = None,
    valid_until: datetime.date | None = None,
    validity_days: int | None = None,
) -> dict[str, str]:
    """Free outgoing documents: the placeholders of a document without a project.

    The placeholders about a project stay empty; the others are as in :func:`placeholder_values`. ``{greeting}`` /
    ``{anrede}`` (KND-004) is the greeting set for ``contact``, else for the main contact of the customer, else the
    neutral formal greeting of the language of the documents ("Sehr geehrte Damen und Herren,").
    """
    from rentalars.customers import greetings

    if contact is None and customer is not None and customer.pk:
        contact = customer.primary_contact
    greeting = greetings.greeting(contact) if contact is not None else greetings.neutral_greeting()
    return {
        "project": "",
        "project_name": "",
        "customer": customer.name if customer is not None else "",
        "period": "",
        "venue": "",
        "due_date": due_on.strftime(local_pattern("%d.%m.%Y")) if due_on else "",
        "payment_terms": str(terms) if terms is not None else "",
        "valid_until": valid_until.strftime(local_pattern("%d.%m.%Y")) if valid_until else "",
        "validity_days": str(validity_days) if validity_days is not None else "",
        "greeting": greeting,
        "anrede": greeting,
    }


# --- Priced documents: order confirmation, invoice (DOK-003, DOK-006) ---------------------------


def product_description(product: Any) -> str:
    """Product descriptions: the description of a product as it would be printed; "" without a product.

    Always read when the positions are built; ``strip_descriptions`` takes it off again for a document that does
    not print the descriptions, so one rule serves every renderer.
    """
    return (product.description or "").strip() if product is not None else ""


def strip_descriptions(content: DocumentContent) -> DocumentContent:
    """Product descriptions: leave the descriptions of the products out of a document that does not print them.

    Only what comes from the product goes; the line's own text – its title and ``details`` – stays.
    """
    content.print_product_descriptions = False
    for section in content.sections:
        for position in section.positions:
            position.description = ""
    for _title, rows in content.delivery_rows:
        for row in rows:
            row.description = ""
    return content


def customer_material_note() -> str:
    """PRJ-096: what documents say about a line of the customer's own material."""
    return _("Customer's own material – taken along, not charged")


def _customer_material_position(number: str, planned: Any) -> Position:
    """PRJ-096: the customer's own material as a position: what and how many, the hint, no price."""
    line = planned.line
    unit = line.unit.abbreviation if line.unit_id else ""
    return Position(
        number=number,
        title=line.title,
        article_number=line.product.article_number,
        quantity=line.quantity,
        unit=unit,
        unit_code=unit_code(unit),
        details=customer_material_note(),
        unit_price=None,
        tax_name=line.tax_rate.name,
        tax_percent=line.tax_rate.rate,
        line_id=line.pk,
        customer_material=True,
        description=product_description(line.product),
    )


def _line_position(number: str, planned: Any) -> Position:
    line, price = planned.line, planned.price
    if line.is_text:
        # A text line is a row of text – no number, quantity, price or tax; xrechnung and the exports skip it.
        return Position(number="", title=line.title, details=line.note, line_id=line.pk, is_text=True)
    if price.is_customer_material:
        return _customer_material_position(number, planned)
    details = []
    if price.rental_days:
        days = ngettext("%(days)s rental day", "%(days)s rental days", plural_of(price.rental_days)) % {
            "days": price.rental_days
        }
        if price.scale_factor and price.scale_factor != Decimal("1"):
            days += ", " + _("factor %(factor)s") % {"factor": plain_decimal(price.scale_factor)}
        details.append(days)
    if line.is_percent_surcharge:
        details.append(
            _("%(percent)s %% of %(base)s")
            % {"percent": plain_decimal(line.surcharge_percent), "base": f"{price.surcharge_base:.2f}"}
        )
    unit = line.unit.abbreviation if line.unit_id else ""
    quantity = Decimal("1") if line.is_percent_surcharge else line.quantity
    return Position(
        number=number,
        title=line.title,
        article_number=line.product.article_number if line.product_id else "",
        quantity=quantity,
        unit=unit if not line.is_percent_surcharge else "",
        unit_code=unit_code(unit) if not line.is_percent_surcharge else "C62",
        details=", ".join(details),
        unit_price=None if line.is_percent_surcharge else line.unit_price,
        # PER-026: the discount as it applies, limited to the maximum of a job function.
        discount_percent=price.discount_percent or ZERO,
        base_amount=price.base_amount if not line.is_percent_surcharge else price.amount,
        discount_amount=price.discount_amount if not line.is_percent_surcharge else ZERO,
        amount=price.amount,
        tax_name=line.tax_rate.name,
        tax_percent=line.tax_rate.rate,
        is_estimate=price.is_estimate,
        variant=line.variant,
        variant_label=str(line.get_variant_display()) if line.variant else "",
        line_id=line.pk,
        alternative_to_line=line.alternative_to_id,
        alternative_to_label=getattr(planned, "alternative_label", ""),
        description=product_description(line.product if line.product_id else None),
    )


def name_alternatives(sections: list[Section]) -> None:
    """Write "alternative to pos. 3" on every alternative whose counterpart is a position of the document (PRJ-083).

    Called once the positions are numbered – and again when they are
    numbered anew (DOK-013). A counterpart that is no position of the
    document (left out, or only summed up in its group) is named by its
    quantity and title instead.
    """
    numbers = {
        position.line_id: position.number
        for section in sections
        for position in section.positions
        if position.line_id is not None
    }
    for section in sections:
        for position in section.positions:
            if position.alternative_to_line is None:
                continue
            number = numbers.get(position.alternative_to_line)
            if number is not None:
                position.variant_label = _("alternative to pos. %(number)s") % {"number": number}
            elif position.alternative_to_label:
                position.variant_label = _("alternative to “%(line)s”") % {"line": position.alternative_to_label}


def _crew_position(number: str, crew_price: Any) -> Position:
    """A crew line as a position: hours, days (PER-029, unit "Tag", code DAY) or a flat rate.

    PER-035: with hours beyond the limit of a day the details split
    them: "of which 2 h beyond 10 h a day at 55,00 €". The unit price is the
    price up to the limit; the amount is the sum of both, as the electronic
    invoice states it (the price of the whole quantity, see ``xrechnung``).

    PER-009: the surcharges for night, Sunday and holidays are part of
    the amount as well; the details name them by kind with percentage, hours
    and amount.
    """
    line = crew_price.line
    start, end = timezone.localtime(line.start), timezone.localtime(line.end)
    unit, unit_code = {"hour": (_("h"), "HUR"), "day": (_("day"), "DAY"), "flat": (_("flat"), "LS")}[
        crew_price.unit_kind
    ]
    details = f"{start:{local_pattern('%d.%m.%Y %H:%M')}} – {end:{local_pattern('%d.%m.%Y %H:%M')}}"
    if crew_price.has_hours_above_limit:
        details += "; " + _("of which %(hours)s h beyond %(limit)s h a day at %(price)s") % {
            "hours": format_decimal(crew_price.hours_above_limit, max_places=2),
            "limit": format_decimal(crew_price.hours_limit, max_places=2),
            "price": format_money(crew_price.unit_price_above_limit),
        }
    if crew_price.has_time_surcharges:
        # PER-009: "incl. surcharges 126,00 €: night 25 % on 4 h 45,00 €, Sunday 50 % on 2 h 45,00 €".
        details += "; " + _("incl. surcharges %(amount)s: %(parts)s") % {
            "amount": format_money(crew_price.time_surcharge_amount),
            "parts": ", ".join(
                _("%(kind)s %(percent)s %% on %(hours)s h %(amount)s")
                % {
                    "kind": part.short_label,
                    "percent": format_decimal(part.percent, max_places=2),
                    "hours": format_decimal(part.hours, max_places=2),
                    "amount": format_money(part.amount),
                }
                for part in crew_price.time_surcharges
            ),
        }
    return Position(
        number=number,
        title=line.title,
        article_number=line.service_product.article_number if line.service_product_id else "",
        quantity=crew_price.quantity,
        unit=unit,
        unit_code=unit_code,
        details=details,
        unit_price=line.unit_price if crew_price.unit_kind != "flat" else crew_price.base_amount,
        # PER-026: the discount of the crew line, limited to the maximum of its job function.
        discount_percent=crew_price.discount_percent,
        base_amount=crew_price.base_amount,
        discount_amount=crew_price.discount_amount,
        amount=crew_price.amount,
        tax_name=line.tax_rate.name,
        tax_percent=line.tax_rate.rate,
        is_estimate=crew_price.is_estimate,
        description=product_description(line.service_product if line.service_product_id else None),
    )


def _vehicle_position(number: str, vehicle_price: Any) -> Position:
    """LOG-011: a vehicle booking as a position – kilometres, days or a flat rate, with rate and trips.

    The details name every trip with its kilometres and rate – the trailer
    surcharge in it (LOG-006) – or its flat rate; for a trailer per day the
    days and the factor of the rental scale. The unit price is the amount
    before the discount divided by the quantity; the electronic invoice
    states the price of the whole quantity (see ``xrechnung``).
    """
    line = vehicle_price.line
    unit, code = {
        "day": (_("day"), "DAY"),
        "km": ("km", "KMT"),
        "flat": (_("flat"), "LS"),
        "mixed": (_("flat"), "LS"),
    }[vehicle_price.unit_kind]
    details: list[str] = []
    if vehicle_price.days is not None:
        days = (
            ngettext("%(days)s day with trips", "%(days)s days with trips", plural_of(vehicle_price.days))
            if vehicle_price.days_source == "trips"
            else ngettext("%(days)s rental day", "%(days)s rental days", plural_of(vehicle_price.days))
        ) % {"days": vehicle_price.days}
        if vehicle_price.scale_factor and vehicle_price.scale_factor != Decimal("1"):
            days += ", " + _("factor %(factor)s") % {"factor": format_decimal(vehicle_price.scale_factor, max_places=2)}
        details.append(days)
    else:
        for charge in vehicle_price.charges:
            when = (
                f"{timezone.localtime(charge.trip.start):{local_pattern('%d.%m.')}} {charge.trip.title}"
                if charge.trip is not None
                else _("Trip")
            )
            if charge.in_flat_rate:
                text = _("%(trip)s: in the flat rate of the trip") % {"trip": when}
            elif charge.km_source == "flat":
                text = _("%(trip)s: flat rate %(amount)s") % {"trip": when, "amount": format_money(charge.amount)}
            else:
                text = _("%(trip)s: %(km)s km at %(rate)s") % {
                    "trip": when,
                    "km": format_decimal(charge.km or ZERO, max_places=1),
                    "rate": format_money(charge.rate),
                }
                if charge.surcharge_rate:
                    text += " " + _("(incl. trailer surcharge %(rate)s)") % {
                        "rate": format_money(charge.surcharge_rate)
                    }
            details.append(text)
    return Position(
        number=number,
        title=line.label,
        article_number=line.product.article_number,
        quantity=vehicle_price.quantity,
        unit=unit,
        unit_code=code,
        details="; ".join(details),
        unit_price=vehicle_price.unit_price,
        discount_percent=vehicle_price.discount_percent,
        base_amount=vehicle_price.base_amount,
        discount_amount=vehicle_price.discount_amount,
        amount=vehicle_price.amount,
        tax_name=line.tax_rate.name,
        tax_percent=line.tax_rate.rate,
        is_estimate=vehicle_price.is_estimate,
        description=product_description(line.product),
    )


def priced_sections(
    project: Project,
    *,
    with_optional: bool = True,
    planning: Any = None,
    numbers: Iterator[int] | None = None,
    with_customer_material: bool = True,
) -> tuple[list[Section], Any]:
    """The positions of a project in groups with subtotals, and the calculated prices.

    Optional groups (PRJ-040) and optional or alternative lines (PRJ-075) are
    shown on an offer and an order confirmation, marked as not included in
    the total; an invoice leaves them out (``with_optional=False``). Lines
    taken over from another subproject (PRJ-060) are not charged and never
    appear. The customer's own material (PRJ-096) appears without price,
    with a hint; an invoice leaves it out (``with_customer_material=False``).

    Args:
        project: The project.
        with_optional: Whether optional groups and lines appear (marked).
        with_customer_material: Whether lines of the customer's own material appear (PRJ-096).
        planning: The project's planning, if the caller built it already.
        numbers: Where the numbers of the positions come from; a whole
            project's document numbers straight through all its parts
            (PRJ-046). Default: from 1.
    """
    from rentalars.projects.planning import build_planning

    planning = planning or build_planning(project)
    prices = planning.prices
    sections: list[Section] = []
    counter = numbers if numbers is not None else itertools.count(1)

    def numbered(planned_lines: list[Any]) -> list[Position]:
        positions = []
        for planned in planned_lines:
            if planned.line.is_covering_subrental:
                continue  # covers a shortage; the customer pays the line it covers (PRJ-018)
            if planned.line.taken_over_from_id:
                continue  # PRJ-060: taken over from another part; charged once, on the line it comes from
            if not with_optional and not planned.line.counts_toward_total:
                continue  # PRJ-075: an optional line the customer did not choose is not invoiced
            if not with_customer_material and planned.price.is_customer_material:
                continue  # PRJ-096: the customer's own material – nothing to invoice
            positions.append(_line_position("" if planned.line.is_text else str(next(counter)), planned))
        return positions

    def adjust(section: Section, group: Any) -> None:
        """The discount or flat price of a group (PRJ-039) on the section that carries its subtotal."""
        if group.group.flat_price is not None:
            section.adjustment_label = _("Flat price instead of %(amount)s") % {
                "amount": f"{group.prices.lines_total + group.prices.surcharges_total:.2f}".replace(".", ",")
            }
            # The subtotal, not the flat price itself: a maximum discount may raise it (PER-026).
            section.adjustment_amount = group.prices.subtotal - group.prices.lines_total - group.prices.surcharges_total
        elif group.prices.discount:
            if group.group.discount_percent is not None:
                section.adjustment_label = _("Discount %(percent)s %%") % {
                    "percent": plain_decimal(group.group.discount_percent).replace(".", ",")
                }
            else:
                section.adjustment_label = _("Discount")
            section.adjustment_amount = -group.prices.discount

    def alternative_of(group: Any) -> str:
        """PRJ-083: "alternative to “Licht”" for an alternative group that names the group it could replace."""
        target = getattr(group, "alternative_to", None)
        return _("alternative to “%(name)s”") % {"name": target.name} if target is not None else ""

    def add_group(group: Any) -> None:
        """A group and – PRJ-037 – its subgroups between its own positions and its subtotal."""
        optional = not group.prices.counts_toward_total
        if not with_optional and optional:
            return  # with the subgroups: they are optional or alternative as well
        section = Section(
            title=group.group.name,
            description=group.group.description,
            positions=numbered(group.lines),
            subtotal=group.prices.subtotal,
            optional=optional,
            level=group.depth,
            is_group=True,
            alternative_to=alternative_of(group),
            division="material",
        )
        if not group.children:
            adjust(section, group)
            sections.append(section)
            return
        section.part, section.subtotal = "opens", ZERO
        sections.append(section)
        for child in group.children:
            add_group(child)
        closing = Section(
            title=group.group.name,
            subtotal=group.prices.subtotal,
            optional=optional,
            level=group.depth,
            part="closes",
            is_group=True,
            division="material",
        )
        adjust(closing, group)
        sections.append(closing)

    for group in planning.root_groups:
        add_group(group)
    if planning.ungrouped:
        sections.append(
            Section(
                title=_("Without group"),
                positions=numbered(planning.ungrouped),
                subtotal=prices.ungrouped_total,
                division="material",
            )
        )
    if prices.crew:
        positions = [_crew_position(str(next(counter)), crew_price) for crew_price in prices.crew]
        sections.append(
            Section(title=_("Personnel"), positions=positions, subtotal=prices.personnel_total, division="personnel")
        )
    if prices.logistics:
        # LOG-011: the vehicles and trailers as a section of their own; a booking with nothing to charge
        # (no trip, no kilometre) is left out.
        positions = [
            _vehicle_position(str(next(counter)), planned.price)
            for planned in planning.logistics
            if planned.price.base_amount or planned.price.quantity
        ]
        if positions:
            sections.append(
                Section(
                    title=_("Logistics"), positions=positions, subtotal=prices.logistics_total, division="logistics"
                )
            )
    if planning.surcharges:
        sections.append(
            Section(
                title=_("Surcharges"),
                positions=numbered(planning.surcharges),
                subtotal=prices.surcharges_total,
                division="surcharges",
            )
        )
    if prices.overall_discount:
        # PRJ-123: after surcharges, on the sum of the project; the tax shares already carry it.
        percent = project.overall_discount_percent
        title = _("Overall discount")
        if percent:
            title = f"{title} {format_decimal(percent, max_places=6)} %"  # (R3-3) as stored
        sections.append(Section(title=title, subtotal=-prices.overall_discount, overall_discount=True))
    sections = [section for section in sections if section.positions or section.subtotal or section.part]
    mark_divisions(sections, material_total=prices.groups_total + prices.ungrouped_total)
    name_alternatives(sections)
    return sections, prices


def mark_divisions(sections: list[Section], *, material_total: Decimal) -> None:
    """Say which sections open and close each top level – Material, Personnel, Logistics, Surcharges.

    The sections of a division follow each other; ``division_start`` / ``division_end`` mark the first and the last.
    The last section of "material" also carries ``division_total``, the sum of the groups and the lines without
    group – the figure the price calculation has, so the printed sums fit the totals. A project whose material is
    only lines without group needs no heading of its own for them: the division heading says it (``plain``).
    """
    material = [section for section in sections if section.division == "material"]
    if material and all(not section.is_group for section in material):
        for section in material:
            section.plain = True  # no group at all: the lines stand under "Material", without a "Without group" row
    for name in ("material", "personnel", "logistics", "surcharges"):
        members = [section for section in sections if section.division == name]
        if not members:
            continue
        members[0].division_start = True
        members[-1].division_end = True
        if name == "material":
            members[-1].division_total = material_total


def _tax_shares(sections: list[Section], tax_lines: list[Any]) -> list[TaxShare]:
    """The net amount per tax rate as the price calculation splits it, with the positions behind it.

    ``tax_lines`` are those of the price calculation, or of all projects of a
    whole project's document together (PRJ-046, ``projects.family_prices``).
    """
    positions_by_rate: dict[str, Decimal] = {}
    for section in sections:
        if section.optional:
            continue
        for position in section.positions:
            if not position.counts:
                continue
            positions_by_rate[position.tax_name] = positions_by_rate.get(position.tax_name, ZERO) + position.amount
    return [
        TaxShare(
            name=tax_line.tax_rate.name,
            percent=tax_line.tax_rate.rate,
            category=tax_category(tax_line.tax_rate.rate),
            net=tax_line.net,
            tax=tax_line.tax,
            positions_total=positions_by_rate.get(tax_line.tax_rate.name, ZERO),
        )
        for tax_line in tax_lines
    ]


def build_priced(project: Project, kind: str, *, title: str, number: str, issued_on: datetime.date) -> DocumentContent:
    """Offer, order confirmation or invoice: positions, subtotals, taxes, total (DOK-003, DOK-006, DOK-010).

    For a whole project with subprojects (PRJ-045, PRJ-046) the positions of
    every part that is not cancelled follow its own, each part as a block;
    see the description of the module.
    """
    from rentalars.projects.family_prices import family_prices

    with_optional = kind != "invoice"
    family = family_prices(project)
    numbers = itertools.count(1)
    sections: list[Section] = []
    for block in family.blocks:
        own, _prices = priced_sections(
            block.project,
            with_optional=with_optional,
            planning=block.planning,
            numbers=numbers,
            with_customer_material=kind != "invoice",
        )
        if block is family.own:
            sections += own
        elif own:  # a part with nothing to charge is left out
            sections += _subproject_block(block, own)
    totals = family.totals
    customer = project.customer
    content = DocumentContent(
        kind=kind,
        title=title,
        number=number,
        issued_on=issued_on,
        company=company_data(),
        recipient=project.billing_address_lines,
        project=project_data(project),
        recipient_email=customer.email if customer else "",
        customer_number=customer.number if customer else "",
        customer_vat_id=customer.vat_id if customer else "",
        buyer_reference=(customer.buyer_reference if customer else "") or project.number,
        # The rental days are counted over the reservation period, so that is the period of service –
        # the same as the placeholder {period} of the texts. PRJ-046: from the first to the last of all parts.
        service_start=min(timezone.localtime(member.start).date() for member in family.projects),
        service_end=max(timezone.localtime(member.end).date() for member in family.projects),
        sections=sections,
        taxes=_tax_shares(sections, totals.tax_lines),
        net_total=totals.net_total,
        tax_total=totals.tax_total,
        gross_total=totals.gross_total,
        optional_total=totals.optional_total,
        optional_lines_total=totals.optional_lines_total if with_optional else ZERO,
        alternative_lines_total=totals.alternative_lines_total if with_optional else ZERO,
        has_estimates=totals.has_estimates,
    )
    if project.contact_id and project.contact.email:
        content.recipient_email = project.contact.email
    return content


def _subproject_block(block: Any, sections: list[Section]) -> list[Section]:
    """A subproject's sections between its heading and its subtotal (PRJ-046)."""
    number = block.project.number
    for section in sections:
        section.subproject = number
    venue = block.project.venue_label
    opening = Section(
        title=block.heading,
        description=_("Venue: %(venue)s") % {"venue": venue} if venue else "",
        part="opens",
        subproject=number,
        subproject_block=True,
    )
    closing = Section(
        title=block.title, subtotal=block.prices.net_total, part="closes", subproject=number, subproject_block=True
    )
    return [opening, *sections, closing]


def only_groups(content: DocumentContent) -> DocumentContent:
    """DOK-013: the offer with the groups and their sums, without the positions that make up the sums.

    Every group keeps its title, its description and its sum
    (``Section.positions_hidden``). A group with subgroups (PRJ-037) keeps
    both halves: its subgroups follow with their sums, and the closing half
    carries the sum with everything in it. A whole project's offer (PRJ-046)
    keeps the block of every part, with the part's groups and its subtotal.
    Optional and alternative lines (PRJ-075) stay listed: they are not part
    of their group's sum, so the sum cannot stand for them. So does the
    customer's own material (PRJ-096): it is in no sum either, and the
    customer is to see that it is taken along. Lines without
    group, the personnel and the surcharges are listed as before. The
    remaining positions are numbered again from 1; totals and taxes are
    those of the complete offer.
    """
    content.detail = "groups"
    for section in content.sections:
        if section.is_group:
            section.positions = [position for position in section.positions if not position.counts]
            section.positions_hidden = True
    numbers = itertools.count(1)
    for section in content.sections:
        for position in section.positions:
            if not position.is_text:  # A text row has no number
                position.number = str(next(numbers))
    name_alternatives(content.sections)  # PRJ-083: the numbers are new
    return content


def negated(content: DocumentContent, *, title: str, number: str, issued_on: datetime.date) -> DocumentContent:
    """The content of a cancellation: the invoice with every amount negated."""
    import copy

    result = copy.deepcopy(content)
    result.kind, result.title, result.number, result.issued_on = "cancellation", title, number, issued_on
    result.cancels_number, result.cancels_date = content.number, content.issued_on
    result.due_on = None
    result.billing_type, result.billing_number = "", None  # A cancellation is no advance or final invoice
    for section in result.sections:
        section.subtotal = -section.subtotal
        section.adjustment_amount = -section.adjustment_amount
        section.division_total = -section.division_total
        for position in section.positions:
            position.quantity = -position.quantity
            position.base_amount = -position.base_amount
            position.discount_amount = -position.discount_amount
            position.amount = -position.amount
    for share in result.taxes:
        share.net, share.tax, share.positions_total = -share.net, -share.tax, -share.positions_total
    result.net_total, result.tax_total, result.gross_total = (
        -content.net_total,
        -content.tax_total,
        -content.gross_total,
    )
    for deduction in result.deductions:  # What a final invoice deducted is deducted from its cancellation, too
        for share in deduction.taxes:
            share.net, share.tax, share.positions_total = -share.net, -share.tax, -share.positions_total
    return result


def from_json(data: dict[str, Any]) -> DocumentContent:
    """Rebuild the content of a stored document, e.g. to cancel an invoice."""

    def date(value: Any) -> datetime.date | None:
        return datetime.date.fromisoformat(value) if value else None

    def decimal(value: Any) -> Decimal:
        return Decimal(str(value)) if value not in (None, "") else ZERO

    sections = []
    for section in data.get("sections", []):
        positions = [
            Position(
                **{
                    **position,
                    "quantity": decimal(position["quantity"]),
                    "unit_price": decimal(position["unit_price"]) if position.get("unit_price") is not None else None,
                    "discount_percent": decimal(position["discount_percent"]),
                    "base_amount": decimal(position["base_amount"]),
                    "discount_amount": decimal(position["discount_amount"]),
                    "amount": decimal(position["amount"]),
                    "tax_percent": decimal(position["tax_percent"]),
                }
            )
            for position in section["positions"]
        ]
        sections.append(
            Section(
                **{
                    **section,
                    "positions": positions,
                    "subtotal": decimal(section["subtotal"]),
                    "adjustment_amount": decimal(section["adjustment_amount"]),
                    "division_total": decimal(section.get("division_total")),
                }
            )
        )
    taxes = [
        TaxShare(
            **{
                **share,
                "percent": decimal(share["percent"]),
                "net": decimal(share["net"]),
                "tax": decimal(share["tax"]),
                "positions_total": decimal(share["positions_total"]),
            }
        )
        for share in data.get("taxes", [])
    ]
    deductions = [
        Deduction(
            number=deduction["number"],
            issued_on=date(deduction["issued_on"]) or datetime.date.min,
            title=deduction.get("title", ""),
            billing_type=deduction.get("billing_type", ""),
            taxes=[
                TaxShare(
                    **{
                        **share,
                        "percent": decimal(share["percent"]),
                        "net": decimal(share["net"]),
                        "tax": decimal(share["tax"]),
                        "positions_total": decimal(share.get("positions_total")),
                    }
                )
                for share in deduction.get("taxes", [])
            ],
        )
        for deduction in data.get("deductions", [])
    ]
    plain = {
        key: value
        for key, value in data.items()
        if key not in {"sections", "taxes", "delivery_rows", "crew_rows", "deductions"}
    }
    for key in ("issued_on", "service_start", "service_end", "due_on", "cancels_date", "valid_until"):
        plain[key] = date(plain.get(key))
    for key in (
        "net_total",
        "tax_total",
        "gross_total",
        "optional_total",
        "optional_lines_total",
        "alternative_lines_total",
    ):
        plain[key] = decimal(plain.get(key))
    # An older document knows no reverse charge: it is shown as it was issued.
    plain.setdefault("small_business", True)
    return DocumentContent(**plain, sections=sections, taxes=taxes, deductions=deductions)


# --- Delivery note (DOK-003) and crew disposition (DOK-004) -------------------------------------


def build_delivery_note(
    project: Project, *, title: str, number: str, issued_on: datetime.date, packlist: Any = None
) -> DocumentContent:
    """What goes to the customer, per packlist, without prices (DOK-003, PCK-007).

    A delivery note is made per project – for a subproject with the part's
    own delivery address (PRJ-048); a whole project's delivery note holds
    the whole project's own packlists only. Pieces a part takes over from
    another part (PRJ-060) are on it, named "taken over from" that part:
    they come straight from there, not from the warehouse.
    """
    from rentalars.packing import services as packing

    lists = [packlist] if packlist is not None else packing.packlists_of(project)
    rows: list[tuple[str, list[SimpleRow]]] = []
    for current in lists:
        overview = packing.build_overview(current)
        sources = _takeover_sources([row.line for row in overview.rows])
        entries = [
            SimpleRow(
                quantity=_delivered_quantity(row),
                unit=row.product.unit.abbreviation,
                article_number=row.product.article_number,
                title=row.title,
                note=", ".join(row.allocated_ids),
                taken_over_from=sources.get(row.line.taken_over_from_id or 0, ""),
                customer_material=row.is_customer_material,  # PRJ-096
                description=product_description(row.product),  # product descriptions
            )
            for row in overview.rows
        ]
        if entries:
            rows.append((current.label if len(lists) > 1 or current.title else "", entries))
    return DocumentContent(
        kind="delivery_note",
        title=title,
        number=number,
        issued_on=issued_on,
        company=company_data(),
        recipient=project.delivery_address_lines,
        project=project_data(project),
        customer_number=project.customer.number if project.customer_id else "",
        delivery_rows=rows,
    )


def _takeover_sources(lines: list[Any]) -> dict[int, str]:
    """For lines taken over from another part (PRJ-060): the part each source line belongs to, as text.

    One query, none without such a line.
    """
    from rentalars.projects.models import MaterialLine

    ids = {line.taken_over_from_id for line in lines if line.taken_over_from_id}
    if not ids:
        return {}
    return {
        source.pk: f"{source.project.number} {source.project.name}"
        for source in MaterialLine.objects.filter(pk__in=ids).select_related("project")
    }


def _delivered_quantity(row: Any) -> Decimal:
    """What a delivery note lists of a packlist row: what went out, else what is to go.

    A row of taken-over pieces (PRJ-060) may count nothing to take from the
    warehouse; it still lists the pieces of its line.
    """
    if row.issued:
        return row.issued
    if row.required or not row.line.taken_over_from_id or row.kit_title:
        return row.required
    return row.line.quantity


def _crew_vehicle(line: Any) -> str:
    """LOG-008: "Sprinter (B-RL 100), driver" for the crew disposition; "" without a vehicle."""
    if not line.vehicle_line_id:
        return ""
    label = line.vehicle_line.crew_label
    return f"{label}, {_('driver')}" if line.is_driver else label


def build_crew_sheet(project: Project, *, title: str, number: str, issued_on: datetime.date) -> DocumentContent:
    """Who works when and where as what, with the contact data people released (DOK-004, PER-019).

    Hourly rates and flat rates never appear.
    """
    rows = []
    related = ("person", "job_function", "vehicle_line__item__vehicle", "vehicle_line__supplier")
    for line in project.crew_lines.select_related(*related).order_by("start", "id"):
        start, end = timezone.localtime(line.start), timezone.localtime(line.end)
        person = line.person
        rows.append(
            CrewRow(
                day=format_date(start, "D d.m.Y"),
                start=start.strftime("%H:%M"),
                end=end.strftime(local_pattern("%d.%m. %H:%M"))
                if end.date() != start.date()
                else end.strftime("%H:%M"),
                person=person.name if person else str(_("open")),
                job_function=line.job_function.name,
                place=line.meeting_point or project.venue_label,
                phone=person.phone if person and person.share_phone else "",
                email=person.email if person and person.share_email else "",
                vehicle=_crew_vehicle(line),
            )
        )
    return DocumentContent(
        kind="crew_sheet",
        title=title,
        number=number,
        issued_on=issued_on,
        company=company_data(),
        recipient=[],
        project=project_data(project),
        crew_rows=rows,
    )


def rounded(value: Decimal) -> Decimal:
    """Two decimals, as on paper."""
    return money(value)
