# SPDX-License-Identifier: GPL-3.0-or-later
"""Several invoices per project: advance, partial and final invoices, partial credit notes (DOK-030 to DOK-036).

Many projects are billed in steps: a
payment on account before the event, a part after it, the rest at the end. This module keeps the books of that.

What is billed, and how
-----------------------
* **Abschlagsrechnung / Teilrechnung** (``advance`` / ``partial``) bill an *amount* – a net amount or a percentage of the
  net total of the project, with a sentence what it is for. The amount is split over the tax rates of the project in the
  proportion of what is still unbilled, so every rate is billed in step and a final invoice leaves no odd cent behind.
  The document has one position per tax rate. (A part cannot be chosen line by line: group discounts, flat prices and the
  overall discount of the project are not defined for single lines. Name the part in the sentence.)
* **Schlussrechnung** (``final``) is the invoice of the whole project as ever – every position –, and it deducts the
  advance and partial invoices that are valid, each with its net, tax and gross amount (§ 14 (5) UStG). The total is the
  whole project; what is to pay is the total less what was invoiced on account. The electronic invoice carries the same
  in ``PrepaidAmount`` (BT-113) and one ``BillingReference`` (BG-3) per deducted invoice.
* The ordinary **Rechnung** (no type) bills the whole project in one piece, as before.

Rules (the protection against billing twice)
--------------------------------------------
* As long as an ordinary or final invoice of the project is valid (not cancelled) no further invoice is made for it:
  cancel it first.
* Once a part invoice is valid, the ordinary invoice is refused – the project is closed with a *final* invoice, which
  deducts what was invoiced on account. A final invoice needs at least one valid advance or partial invoice.
* Advance and partial invoices together never exceed the net total of the project as it is now (and no tax rate its
  share). When the project becomes cheaper than what was billed, the final invoice would be negative: it is refused with
  the amount and the way out – a partial credit note for an advance invoice.
* An advance or partial invoice is cancelled like any invoice – not while a final invoice that deducts it is valid.

Partial credit notes
--------------------
``credit_invoice`` credits a part of an invoice – a net amount or a percentage of what the invoice still bills – in a
document of the kind cancellation with the type ``credit`` that names the invoice (``Document.credit_for``). Several are
possible; together they never exceed the invoice. The invoice stays valid and counts with its amount less the credits.
Cancelling an invoice that has credits cancels what is left of it (a cancellation with the remaining amount), so that the
documents add up to nothing. Credits are bookings of their own with negative amounts, like a cancellation.

Not in this version: billing single lines, interest and reminders on part invoices, a cash discount per part, the
double-entry bookkeeping (noted for later, see the Stand document).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.i18n import for_documents
from rentalars.documents import content as builder
from rentalars.documents.models import NUMBER_RANGE_OF, PART_BILLING, BillingType, Document, DocumentKind
from rentalars.projects.models import Project

ZERO = Decimal(0)
CENT = Decimal("0.01")

RateKey = tuple[str, Decimal]


def cents(value: Decimal) -> Decimal:
    """Round to whole cents, half up."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Rate:
    """Net amount and tax of one tax rate."""

    name: str
    percent: Decimal
    category: str
    net: Decimal = ZERO
    tax: Decimal = ZERO

    @property
    def key(self) -> RateKey:
        """What identifies the rate: its name and percentage."""
        return (self.name, self.percent)

    @property
    def gross(self) -> Decimal:
        """Net and tax together."""
        return self.net + self.tax


def rates_of(shares: list[builder.TaxShare]) -> dict[RateKey, Rate]:
    """The tax shares of a document as rates by key; shares of the same rate are added."""
    result: dict[RateKey, Rate] = {}
    for share in shares:
        rate = result.setdefault((share.name, share.percent), Rate(share.name, share.percent, share.category))
        rate.net += share.net
        rate.tax += share.tax
    return result


def _add(into: dict[RateKey, Rate], other: dict[RateKey, Rate], sign: int = 1) -> None:
    for key, rate in other.items():
        row = into.setdefault(key, Rate(rate.name, rate.percent, rate.category))
        row.net += rate.net * sign
        row.tax += rate.tax * sign


def _sum(rates: dict[RateKey, Rate]) -> tuple[Decimal, Decimal]:
    return (sum((r.net for r in rates.values()), ZERO), sum((r.tax for r in rates.values()), ZERO))


@dataclass
class Billed:
    """An advance or partial invoice with what it bills now: its amounts less the partial credits."""

    document: Document
    rates: dict[RateKey, Rate]
    credits: list[Document] = field(default_factory=list)

    @property
    def net(self) -> Decimal:
        """The net amount still billed."""
        return _sum(self.rates)[0]

    @property
    def tax(self) -> Decimal:
        """The tax still billed."""
        return _sum(self.rates)[1]

    @property
    def gross(self) -> Decimal:
        """The gross amount still billed."""
        return self.net + self.tax


@dataclass
class BillingState:
    """What a project amounts to and how much of it is billed (the "Abrechnungsstand")."""

    project: Project
    #: The project as it is now, by tax rate.
    project_rates: dict[RateKey, Rate]
    #: The valid advance and partial invoices, oldest first.
    parts: list[Billed]
    #: The valid ordinary or final invoice, if any.
    complete: Document | None
    #: The valid final invoice, if any (it is also :attr:`complete`).
    final: Document | None

    @property
    def project_net(self) -> Decimal:
        """The net total of the project."""
        return _sum(self.project_rates)[0]

    @property
    def project_gross(self) -> Decimal:
        """The gross total of the project."""
        net, tax = _sum(self.project_rates)
        return net + tax

    @property
    def billed_rates(self) -> dict[RateKey, Rate]:
        """What the advance and partial invoices bill, by rate."""
        rates: dict[RateKey, Rate] = {}
        for billed in self.parts:
            _add(rates, billed.rates)
        return rates

    @property
    def billed_net(self) -> Decimal:
        """Net amount of the advance and partial invoices."""
        return _sum(self.billed_rates)[0]

    @property
    def billed_gross(self) -> Decimal:
        """Gross amount of the advance and partial invoices."""
        net, tax = _sum(self.billed_rates)
        return net + tax

    @property
    def remaining_rates(self) -> dict[RateKey, Rate]:
        """What of the project is not billed by advance and partial invoices, by rate (never below nothing)."""
        rates: dict[RateKey, Rate] = {}
        _add(rates, self.project_rates)
        _add(rates, self.billed_rates, -1)
        return rates

    @property
    def remaining_net(self) -> Decimal:
        """The net amount that may still be billed by advance or partial invoices."""
        return max(ZERO, sum((max(ZERO, r.net) for r in self.remaining_rates.values()), ZERO))

    @property
    def remaining_gross(self) -> Decimal:
        """The gross amount left."""
        return max(ZERO, self.project_gross - self.billed_gross)

    @property
    def next_number(self) -> int:
        """The running number of the next advance or partial invoice."""
        used = [billed.document.billing_number or 0 for billed in self.parts]
        cancelled = (
            Document.objects.filter(
                project=self.project,
                kind=DocumentKind.INVOICE,
                billing_type__in=PART_BILLING,
                cancelled_by__isnull=False,
            )
            .order_by("-billing_number")
            .values_list("billing_number", flat=True)
            .first()
        )
        return max([*used, cancelled or 0]) + 1

    @property
    def has_parts(self) -> bool:
        """Whether a valid advance or partial invoice exists."""
        return bool(self.parts)


def _credits_of(document: Document) -> list[Document]:
    return list(document.partial_credits.order_by("created_at", "pk"))


def effective_rates(document: Document) -> tuple[dict[RateKey, Rate], list[Document]]:
    """What an invoice bills now – the amounts it books (less its deductions) plus its credits, by rate."""
    content = builder.from_json(document.content)
    rates = rates_of(content.booked_taxes)
    credits = _credits_of(document)
    for credit in credits:
        _add(rates, rates_of(builder.from_json(credit.content).taxes))
    return rates, credits


def project_rates(project: Project) -> dict[RateKey, Rate]:
    """The tax shares of the project as an invoice would bill it today (optional lines left out)."""
    from rentalars.projects.family_prices import family_prices

    return {
        (line.tax_rate.name, line.tax_rate.rate): Rate(
            line.tax_rate.name, line.tax_rate.rate, builder.tax_category(line.tax_rate.rate), line.net, line.tax
        )
        for line in family_prices(project).totals.tax_lines
    }


def state_of(project: Project) -> BillingState:
    """The billing state of a project: what it amounts to, what the valid advance and partial invoices bill."""
    from rentalars.documents.invoice_reminders import invoices_of

    parts = []
    for document in part_invoices(project):
        rates, credits = effective_rates(document)
        parts.append(Billed(document, rates, credits))
    complete = invoices_of(project).order_by("-created_at").first()
    final = complete if complete is not None and complete.billing_type == BillingType.FINAL else None
    return BillingState(project, project_rates(project), parts, complete, final)


# --- The rules --------------------------------------------------------------------------------------------------


def part_invoices(project: Project) -> Any:
    """The valid advance and partial invoices of a project, oldest first."""
    return Document.objects.filter(
        project=project, kind=DocumentKind.INVOICE, billing_type__in=PART_BILLING, cancelled_by__isnull=True
    ).order_by("created_at", "pk")


def problems(project: Project, billing_type: str) -> list[str]:
    """Why an invoice of this type cannot be made on the project now; empty if nothing stops it.

    Checked for every invoice, also the ordinary one: with a valid advance or partial invoice it is refused. That a
    valid ordinary or final invoice stops every further one is said by ``services.check_can_make``. Whether the
    advance and partial invoices exceed the project is checked on the content (:func:`apply`).
    """
    if billing_type and billing_type not in (BillingType.ADVANCE, BillingType.PARTIAL, BillingType.FINAL):
        return [_("Unknown type of invoice.")]
    if billing_type and (project.is_service_case or project.parent_id):
        return [
            _("Advance, partial and final invoices are made on the whole project, not on a part or a service case.")
        ]
    if project.pk is None:
        return []
    numbers = list(part_invoices(project).values_list("number", flat=True))
    if billing_type == BillingType.FINAL and not numbers:
        return [_("There is no advance or partial invoice to deduct. Make an ordinary invoice instead.")]
    if not billing_type and numbers:
        return [
            _(
                "This project has advance or partial invoices (%(numbers)s). Make the final invoice: it deducts "
                "them. Cancel them first if the project is to be billed in one piece."
            )
            % {"numbers": ", ".join(numbers)}
        ]
    return []


def _money(value: Decimal) -> str:
    from rentalars.core.money import format_money

    return format_money(value)


def split(amount: Decimal, available: dict[RateKey, Rate], *, credit: bool = False) -> dict[RateKey, Decimal]:
    """Split a net amount over the tax rates in the proportion of what is available (never more than a rate has).

    Raises:
        ValidationError: More than is available.
    """
    usable = {key: rate for key, rate in available.items() if rate.net > ZERO}
    total = sum((rate.net for rate in usable.values()), ZERO)
    if amount > total or not usable:
        message = (
            _("The amount is more than what is left to credit: %(left)s net.")
            if credit
            else _("The amount is more than what is left to bill: %(left)s net.")
        )
        raise ValidationError({"amount": message % {"left": _money(total)}})
    keys = list(usable)
    shares: dict[RateKey, Decimal] = {}
    left = amount
    for key in keys[:-1]:
        share = min(cents(amount * usable[key].net / total), usable[key].net, left)
        shares[key] = share
        left -= share
    last = keys[-1]
    shares[last] = min(left, usable[last].net)
    left -= shares[last]
    for key in keys:  # the last rate was full: what rounding left goes to a rate with room
        if left <= ZERO:
            break
        room = usable[key].net - shares[key]
        extra = min(room, left)
        shares[key] += extra
        left -= extra
    return {key: share for key, share in shares.items() if share > ZERO}


def _tax_for(rate: Rate, net: Decimal, *, whole: bool = False) -> Decimal:
    """The tax of a net amount of a rate: net times the percentage, rounded to the cent (EN 16931 BR-CO-17).

    With ``whole`` the amount is all that is left of the rate (the cancellation of the remainder): then it is the tax
    that is left, so that invoice, credit notes and cancellation add up to nothing.
    """
    if whole and net == rate.net:
        return rate.tax
    return cents(net * rate.percent / Decimal(100))


def amount_from(base: Decimal, amount: Decimal | None, percent: Decimal | None) -> Decimal:
    """The net amount asked for: given, or a percentage of ``base``.

    Raises:
        ValidationError: Neither, both, or not above nothing.
    """
    if amount is not None and percent is not None:
        raise ValidationError({"amount": _("Give an amount or a percentage, not both.")})
    if percent is not None:
        if percent <= ZERO or percent > Decimal(100):
            raise ValidationError({"percent": _("The percentage must be above 0 and at most 100.")})
        return cents(base * percent / Decimal(100))
    if amount is None or amount <= ZERO:
        raise ValidationError({"amount": _("Enter the net amount or a percentage above 0.")})
    return cents(amount)


# --- Building the content ---------------------------------------------------------------------------------------


@dataclass
class Billing:
    """What the maker of an invoice asked for: the type and, for an advance or partial invoice, the amount."""

    type: str = ""
    #: The net amount, or …
    amount: Decimal | None = None
    #: … a percentage of the net total of the project.
    percent: Decimal | None = None
    #: What the invoice is for ("Anzahlung bei Auftrag", "Aufbau und erster Veranstaltungstag").
    note: str = ""


def apply(project: Project, content: builder.DocumentContent, billing: Billing) -> None:
    """Turn the content of an ordinary invoice into the advance, partial or final invoice that was asked for.

    Called by ``services.build_content`` inside the language of the documents.

    Raises:
        ValidationError: The rules in the description of the module.
    """
    if not billing.type:
        return
    refusal = problems(project, billing.type)
    if refusal:
        raise ValidationError(refusal)
    state = state_of(project)  # one calculation of the project for the amounts
    if billing.type == BillingType.FINAL:
        _make_final(state, content)
    else:
        _make_part(state, content, billing)
    content.billing_type = billing.type


def _label(billing_type: str, number: int | None = None) -> str:
    if billing_type == BillingType.ADVANCE:
        return _("%(number)d. advance invoice") % {"number": number or 1}
    if billing_type == BillingType.PARTIAL:
        return _("%(number)d. partial invoice") % {"number": number or 1}
    return _("Final invoice")


def _make_final(state: BillingState, content: builder.DocumentContent) -> None:
    """The invoice of the whole project that deducts the advance and partial invoices."""
    content.title = _label(BillingType.FINAL)
    content.deductions = [
        builder.Deduction(
            number=billed.document.number,
            issued_on=billed.document.issued_on,
            title=billed.document.title,
            billing_type=billed.document.billing_type,
            taxes=[
                builder.TaxShare(rate.name, rate.percent, rate.category, rate.net, rate.tax)
                for rate in billed.rates.values()
                if rate.net or rate.tax
            ],
        )
        for billed in state.parts
    ]
    content.billing_note = _("The invoices on account are deducted.")
    content.introduction = (
        content.introduction
        + "\n\n"
        + _("This is our final invoice. Advance and partial invoices already issued are deducted below the total.")
    ).strip()
    if content.payable_total < ZERO:  # also checked by problems(): the content may be a little different
        raise ValidationError(
            _(
                "The advance and partial invoices are more than the final invoice. Credit a part of an advance invoice first."
            )
        )


def _make_part(state: BillingState, content: builder.DocumentContent, billing: Billing) -> None:
    """An advance or partial invoice: one position per tax rate for the amount asked for."""
    wanted = amount_from(state.project_net, billing.amount, billing.percent)
    available = state.remaining_rates
    shares = split(wanted, available)
    number = state.next_number
    title = _label(billing.type, number)
    what = (billing.note or "").strip()
    positions: list[builder.Position] = []
    taxes: list[builder.TaxShare] = []
    for index, (key, net) in enumerate(shares.items(), start=1):
        rate = available[key]
        tax = _tax_for(rate, net)
        text = what or (
            _("Payment on account for project %(number)s") % {"number": content.project.get("number", "")}
            if billing.type == BillingType.ADVANCE
            else _("Part of project %(number)s") % {"number": content.project.get("number", "")}
        )
        details = []
        if state.project_net:
            details.append(
                _("%(percent)s %% of the net total of %(total)s")
                % {
                    "percent": builder.format_decimal(net / state.project_net * 100, max_places=2),
                    "total": _money(state.project_net),
                }
            )
        positions.append(
            builder.Position(
                number=str(index),
                title=text if len(shares) == 1 else f"{text} ({rate.name})",
                quantity=Decimal(1),
                unit_code="C62",
                details=", ".join(details),
                unit_price=net,
                base_amount=net,
                amount=net,
                tax_name=rate.name,
                tax_percent=rate.percent,
            )
        )
        taxes.append(builder.TaxShare(rate.name, rate.percent, rate.category, net, tax, positions_total=net))
    net_total = sum((share.net for share in taxes), ZERO)
    tax_total = sum((share.tax for share in taxes), ZERO)
    content.title = title
    content.billing_number = number
    content.billing_note = what
    content.sections = [builder.Section(title="", positions=positions, subtotal=net_total, plain=True)]
    content.taxes = taxes
    content.net_total, content.tax_total, content.gross_total = net_total, tax_total, net_total + tax_total
    content.optional_total = content.optional_lines_total = content.alternative_lines_total = ZERO
    content.has_estimates = False
    sentence = (
        _("We invoice a payment on account for the project. The invoice is deducted from the final invoice.")
        if billing.type == BillingType.ADVANCE
        else _("We invoice a part of the project. The invoice is deducted from the final invoice.")
    )
    content.introduction = (content.introduction + "\n\n" + sentence).strip()


# --- Partial credit notes ---------------------------------------------------------------------------------------


def final_deducting(invoice: Document) -> Document | None:
    """The valid final invoice that deducts this advance or partial invoice, if there is one."""
    if invoice.billing_type not in PART_BILLING or not invoice.project_id:
        return None
    return (
        Document.objects.filter(
            project_id=invoice.project_id,
            kind=DocumentKind.INVOICE,
            billing_type=BillingType.FINAL,
            cancelled_by__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )


def lock_project_of(invoice: Document) -> None:
    """Lock the project row of an invoice, as making an invoice does.

    Credit, cancellation and a final invoice of the same project then wait for each other.
    """
    if invoice.project_id:
        Project.objects.select_for_update().filter(pk=invoice.project_id).first()


def credit_problems(invoice: Document) -> list[str]:
    """Why an invoice cannot be credited (partly) now; empty if it can."""
    result: list[str] = []
    if invoice.kind != DocumentKind.INVOICE:
        result.append(_("Only invoices are credited."))
        return result
    if invoice.cancelled_by_id:
        result.append(_("This invoice is already cancelled."))
    if invoice.is_historic:
        result.append(_("An invoice taken over from an old system cannot be credited here."))
    final = final_deducting(invoice)
    if final is not None:
        result.append(
            _("The final invoice %(number)s deducts this invoice. Cancel the final invoice first.")
            % {"number": final.number}
        )
    return result


@transaction.atomic
def credit_invoice(
    invoice: Document,
    *,
    amount: Decimal | None = None,
    percent: Decimal | None = None,
    note: str = "",
    remainder: bool = False,
    user: Any = None,
) -> Document:
    """Credit a part of an invoice by a document of the kind cancellation (a partial credit note).

    Args:
        invoice: A valid invoice.
        amount: The net amount credited, or …
        percent: … a percentage of what the invoice still bills (net).
        note: What the credit is for.
        remainder: Credit everything that is left and cancel the invoice (used by ``services.cancel_invoice`` for an
            invoice that has credits already).
        user: Who does it.

    Raises:
        ValidationError: Something stops the credit (see :func:`credit_problems`), or the amount is more than the
            invoice still bills.
    """
    from rentalars.core.models import NumberRange
    from rentalars.documents import services
    from rentalars.documents.pdf import render_pdf
    from rentalars.documents.xrechnung import build_xml, missing_data

    services.check_invoices_enabled()
    lock_project_of(invoice)  # the same order as when an invoice is made: the project first, then the invoice
    invoice = Document.objects.select_for_update().get(pk=invoice.pk)
    refusal = credit_problems(invoice)
    if refusal:
        raise ValidationError(refusal)
    rates, _credits = effective_rates(invoice)
    positive = {key: rate for key, rate in rates.items() if rate.net > ZERO}
    total = sum((rate.net for rate in rates.values()), ZERO)  # what the invoice bills now, net
    if total <= ZERO:
        raise ValidationError(_("Nothing of this invoice is left to credit."))
    original = builder.from_json(invoice.content)
    if not remainder:
        wanted = amount_from(total, amount, percent)
        if wanted > total:
            raise ValidationError(
                {"amount": _("The amount is more than what is left to credit: %(left)s net.") % {"left": _money(total)}}
            )
        # Crediting everything that is left is the cancellation of the invoice: nothing stays that could not be
        # cancelled any more.
        remainder = wanted == total
    if remainder:
        shares = {key: rate.net for key, rate in rates.items() if rate.net or rate.tax}
    else:
        shares = split(wanted, positive, credit=True)
    template = services.template_for(DocumentKind.CANCELLATION)
    with for_documents():
        content = builder.DocumentContent(
            kind=DocumentKind.CANCELLATION,
            title=_("Credit note") if not remainder else template.title,
            number="",
            issued_on=timezone.localdate(),
            company=builder.company_data(),
            recipient=original.recipient,
            project=original.project,
            introduction="",
            recipient_email=original.recipient_email,
            customer_number=original.customer_number,
            buyer_reference=original.buyer_reference,
            customer_vat_id=original.customer_vat_id,
            service_start=original.service_start,
            service_end=original.service_end,
            reference=original.reference,
            cancels_number=invoice.number,
            cancels_date=invoice.issued_on,
            billing_type=BillingType.CREDIT if not remainder else "",
        )
        positions: list[builder.Position] = []
        taxes: list[builder.TaxShare] = []
        what = (note or "").strip()
        for index, (key, net) in enumerate(shares.items(), start=1):
            rate = rates[key]
            tax = _tax_for(rate, net, whole=remainder)
            text = what or (
                _("Remainder of invoice %(number)s") % {"number": invoice.number}
                if remainder
                else _("Credit for invoice %(number)s") % {"number": invoice.number}
            )
            positions.append(
                builder.Position(
                    number=str(index),
                    title=text if len(shares) == 1 else f"{text} ({rate.name})",
                    # the price is never negative (BR-27): a rate that was left negative is credited with + 1 × price
                    quantity=Decimal(-1) if net >= ZERO else Decimal(1),
                    unit_code="C62",
                    unit_price=abs(net),
                    base_amount=-net,
                    amount=-net,
                    tax_name=rate.name,
                    tax_percent=rate.percent,
                )
            )
            taxes.append(builder.TaxShare(rate.name, rate.percent, rate.category, -net, -tax, positions_total=-net))
        net_total = sum((share.net for share in taxes), ZERO)
        tax_total = sum((share.tax for share in taxes), ZERO)
        content.sections = [builder.Section(title="", positions=positions, subtotal=net_total, plain=True)]
        content.taxes = taxes
        content.net_total, content.tax_total, content.gross_total = net_total, tax_total, net_total + tax_total
        content.billing_note = what
        content.introduction = (
            template.introduction
            if remainder and not _credits
            else (
                _(
                    "We credit the remainder of the invoice named above; with the credit notes issued before, it is cancelled in full."
                )
                if remainder
                else _("We credit a part of the invoice named above.")
            )
        )
        content.footer = template.footer
        if invoice.project_id is None:
            values = builder.free_placeholder_values(invoice.customer)
        else:
            values = builder.placeholder_values(invoice.project)
        content.introduction = builder.fill(content.introduction, values)
    missing = missing_data(content)
    if missing:
        raise ValidationError(
            _("For the electronic invoice, this is missing: %(items)s.") % {"items": ", ".join(missing)}
        )
    _value, content.number = NumberRange.allocate(NUMBER_RANGE_OF[DocumentKind.CANCELLATION])
    document = services._store(
        invoice.project, content, template, user=user, render=render_pdf, xml=build_xml, customer=invoice.customer
    )
    if remainder:
        Document.objects.filter(pk=document.pk).update(cancels=invoice)
        invoice.cancelled_by = document
        invoice.save(update_fields=["cancelled_by"])
        from rentalars.documents.statements import invoice_cancelled

        invoice_cancelled(invoice, document, user=user)  # a monthly invoice: its statement is a draft again
    else:
        Document.objects.filter(pk=document.pk).update(credit_for=invoice)
    record_event(
        invoice.project or invoice.customer,
        "document.cancelled" if remainder else "document.credited",
        {"kind": invoice.get_kind_display(), "number": invoice.number, "cancellation": document.number},
    )
    document.refresh_from_db()
    services._to_accounting(document, user)
    return document


def summary_rows(state: BillingState) -> list[dict[str, Any]]:
    """The rows of the billing table on the tab "Dokumente": the part invoices with their amounts."""
    return [
        {
            "document": billed.document,
            "net": billed.net,
            "gross": billed.gross,
            "credits": billed.credits,
        }
        for billed in state.parts
    ]


def today() -> datetime.date:
    """Today, the date a new document gets."""
    return timezone.localdate()
