# SPDX-License-Identifier: GPL-3.0-or-later
"""Outgoing documents without a project: offers, order confirmations and invoices made in Accounting.

The requirement: a way to create offers, invoices and so on independently of projects and service cases, for example
a button "Neuer Ausgangsbeleg" in Buchhaltung → Ausgangsbelege that opens a dialog.

The way
-------
A document is never changed once it exists (DOK-007), so a free document is made in two steps, as the monthly
invoice of service cases is (DOK-016):

1. **The draft** (:class:`~rentalars.documents.models.DocumentDraft`): the dialog "Neuer Ausgangsbeleg" chooses the
   kind and the customer – with billing address, contact, date, reference – and creates the draft. The page
   "Ausgangsbeleg bearbeiten" then edits the lines (free lines, lines from products, text lines; discount, sorting),
   the texts and the options until the document is good.
2. **Issuing** (:func:`issue`): only now the number is taken from the number range of the kind – the ranges stay
   gapless and are shared with the documents of projects –, the content is frozen as for every document
   (``documents.content`` data classes), the PDF and for an invoice the XRechnung are rendered and stored with a
   checksum, and the draft is gone. From here on the document is like any other: it shows in Buchhaltung →
   Ausgangsbelege, goes to Lexware Office and the DATEV export, is sent by mail, and a free invoice is cancelled by a
   cancellation (``services.cancel_invoice``), which is a free document too.

Which kinds
-----------
:data:`~rentalars.documents.models.FREE_KINDS`: offer, order confirmation, invoice. A delivery note needs the
packlists of a project and a crew disposition its crew; a cancellation is made from its invoice.

Prices, taxes
-------------
A line's amount is quantity × unit price, rounded to cents, minus its discount (rounded); the net amounts per tax rate
are the sums of the lines, the tax of a rate is its net times the rate, rounded – as the price calculation of projects
does it (``projects.pricing``), without group discounts. The totals are stored with the document.

Not part of project figures
---------------------------
A free document belongs to a customer and no project: it is not in the profitability report, the invoice reminders
("Rechnung offen") and the project's tab "Documents" (they are about projects); it is in the list of outgoing
documents, on the page of its customer, the DATEV export and Lexware Office.

Product descriptions
----------------------------
A line from a product prints the product's description under it if the draft says so
(``DocumentDraft.print_product_descriptions``); the line's own title and note always print.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module
from rentalars.core.audit import record_event
from rentalars.core.i18n import document_language, for_documents
from rentalars.core.money import HUNDRED, money, percentage_of
from rentalars.customers.models import AddressKind
from rentalars.documents import content as builder
from rentalars.documents import outgoing, services
from rentalars.documents.models import (
    FREE_KINDS,
    NUMBER_RANGE_OF,
    Document,
    DocumentDraft,
    DocumentKind,
    DraftLine,
    TextBlock,
)

ZERO = Decimal("0")

#: The introductions a document without a project starts with (like ``services.DEFAULT_TEMPLATES``: the language of
#: the company's documents decides; the template of the kind can set its own, ``free_introduction``).
DEFAULT_INTRODUCTIONS = {
    DocumentKind.OFFER: "Gerne bieten wir Ihnen Folgendes an. Dieses Angebot gilt bis zum {valid_until}.",
    DocumentKind.ORDER_CONFIRMATION: "Vielen Dank für Ihren Auftrag. Wir bestätigen wie folgt:",
    DocumentKind.INVOICE: "Wir berechnen Ihnen:",
}
DEFAULT_INTRODUCTIONS_ENGLISH = {
    DocumentKind.OFFER: "We are pleased to offer the following. This offer is valid until {valid_until}.",
    DocumentKind.ORDER_CONFIRMATION: "Thank you for your order. We confirm it as follows:",
    DocumentKind.INVOICE: "We invoice:",
}


# --- Rights -------------------------------------------------------------------------------------------------


def may_see(rights: Any) -> bool:
    """Whether the drafts and documents without a project are open to these rights: as the list (DOK-020)."""
    return outgoing.may_see(rights)


def may_change(rights: Any) -> bool:
    """Whether these rights may make and change them: the list, and write access to every project.

    The same rights make a document of a project (write access to projects, the price right); a document of
    Buchhaltung belongs to no single project, so the access must hold for all of them.
    """
    return may_see(rights) and rights.level_everywhere(Module.PROJECTS) >= Level.WRITE


# --- Texts --------------------------------------------------------------------------------------------------


def default_introduction(kind: str) -> str:
    """The introduction a new draft of this kind starts with: the template's own, else the standard text."""
    template = services.template_for(kind)
    if template.free_introduction.strip():
        return template.free_introduction
    texts = DEFAULT_INTRODUCTIONS_ENGLISH if document_language() == "en" else DEFAULT_INTRODUCTIONS
    return texts.get(DocumentKind(kind), "")


def default_closing(kind: str) -> str:
    """The closing text a new draft starts with: that of the template of the kind."""
    return services.template_for(kind).closing


def free_kinds() -> list[DocumentKind]:
    """The kinds that can be made without a project now: without the invoice while invoices are off (DOK-014)."""
    kinds = [DocumentKind(kind) for kind in FREE_KINDS]
    if services.invoices_enabled():
        return kinds
    return [kind for kind in kinds if kind not in services.INVOICE_KINDS]


# --- The draft ----------------------------------------------------------------------------------------------


def check_customer(customer: Any) -> None:
    """A document is made for a customer who is there: not deactivated, not anonymised (KND-010).

    Raises:
        ValidationError: The customer cannot get a new document.
    """
    if customer is None:
        raise ValidationError({"customer": _("Choose the customer.")})
    if customer.is_anonymised:
        raise ValidationError({"customer": _("This customer was anonymised and cannot get new documents.")})
    if not customer.is_active:
        raise ValidationError({"customer": _("This customer is deactivated and cannot get new documents.")})


def _check_draft_values(draft: DocumentDraft) -> None:
    """The rules of a draft that hold when it is made and when it is changed."""
    errors: dict[str, str] = {}
    if draft.kind not in FREE_KINDS:
        errors["kind"] = _("A document without a project can be an offer, an order confirmation or an invoice.")
    elif draft.kind in services.INVOICE_KINDS and not services.invoices_enabled():
        errors["kind"] = services.invoices_off_message()
    if draft.billing_address_id and draft.billing_address.customer_id != draft.customer_id:
        errors["billing_address"] = _("This address belongs to another customer.")
    elif draft.billing_address_id and draft.billing_address.kind != AddressKind.BILLING:
        # As in the browser, which offers only the billing addresses of the customer.
        errors["billing_address"] = _("Choose a billing address of the customer; this is a delivery address.")
    if draft.contact_id and draft.contact.customer_id != draft.customer_id:
        errors["contact"] = _("This contact belongs to another customer.")
    if draft.service_end and not draft.service_start:
        errors["service_end"] = _("Enter when the service starts, too.")
    elif draft.service_start and draft.service_end and draft.service_end < draft.service_start:
        errors["service_end"] = _("The service cannot end before it starts.")
    if draft.kind != DocumentKind.INVOICE and (draft.payment_terms_days is not None or draft.service_start):
        errors["kind"] = errors.get("kind") or _("Payment terms and the date of service belong to an invoice.")
    if draft.kind != DocumentKind.OFFER and draft.valid_until is not None:
        errors["valid_until"] = _("Only an offer has a validity.")
    if draft.issued_on is not None:
        # The number comes from the range of today (with this year in it, as a rule) – a date of another year
        # or of the future would put the document into a period that is closed or not yet begun.
        today = timezone.localdate()
        if draft.issued_on > today:
            errors["issued_on"] = _("The date of a document cannot lie in the future. Leave it empty for today.")
        elif draft.issued_on.year != today.year:
            errors["issued_on"] = _("The date of a document must lie in the current year. Leave it empty for today.")
    if draft.valid_until and (draft.issued_on or timezone.localdate()) > draft.valid_until:
        errors["valid_until"] = _("An offer cannot be valid only until before its own date.")
    if errors:
        raise ValidationError(errors)


def create_draft(
    customer: Any,
    kind: str,
    *,
    user: Any = None,
    billing_address: Any = None,
    contact: Any = None,
    issued_on: datetime.date | None = None,
    payment_terms_days: int | None = None,
    valid_until: datetime.date | None = None,
    service_start: datetime.date | None = None,
    service_end: datetime.date | None = None,
    reference: str = "",
    introduction: str | None = None,
    closing: str | None = None,
    text_block_ids: list[int] | None = None,
    print_product_descriptions: bool | None = None,
) -> DocumentDraft:
    """Make the draft of an outgoing document without a project.

    The texts start with the standard ones of the kind (:func:`default_introduction`, :func:`default_closing`);
    ``print_product_descriptions`` starts with the choice of the template of the kind. The billing address and the
    contact start with the customer's defaults when none is given and the customer has them.

    Raises:
        ValidationError: The customer cannot get a document, the kind does not fit, an address or contact belongs
            to another customer, or dates do not fit.
    """
    check_customer(customer)
    if kind not in FREE_KINDS:
        raise ValidationError(
            {"kind": _("A document without a project can be an offer, an order confirmation or an invoice.")}
        )
    if billing_address is None:
        billing_address = customer.default_address(AddressKind.BILLING)
    if contact is None:
        contact = customer.primary_contact
    template = services.template_for(kind)
    draft = DocumentDraft(
        kind=kind,
        customer=customer,
        billing_address=billing_address,
        contact=contact,
        issued_on=issued_on,
        payment_terms_days=payment_terms_days,
        valid_until=valid_until,
        service_start=service_start,
        service_end=service_end,
        reference=(reference or "").strip(),
        introduction=default_introduction(kind) if introduction is None else introduction,
        closing=default_closing(kind) if closing is None else closing,
        text_block_ids=list(text_block_ids or []),
        print_product_descriptions=template.print_product_descriptions
        if print_product_descriptions is None
        else print_product_descriptions,
        created_by=user if getattr(user, "pk", None) else None,
    )
    _check_draft_values(draft)
    draft.save()
    return draft


#: What :func:`update_draft` changes.
DRAFT_FIELDS = (
    "billing_address",
    "contact",
    "issued_on",
    "payment_terms_days",
    "valid_until",
    "service_start",
    "service_end",
    "reference",
    "introduction",
    "closing",
    "text_block_ids",
    "print_product_descriptions",
)


def update_draft(draft: DocumentDraft, **values: Any) -> DocumentDraft:
    """Change the header and texts of a draft; the kind and the customer stay (make a new draft instead).

    Raises:
        ValidationError: A value does not fit (see :func:`create_draft`).
    """
    unknown = set(values) - set(DRAFT_FIELDS)
    if unknown:
        raise ValueError(f"Not changeable: {', '.join(sorted(unknown))}")
    for name, value in values.items():
        if name == "reference":
            value = (value or "").strip()
        elif name == "print_product_descriptions" and value is None:
            # The API may send null ("as the template says", as when the draft is made); the column cannot be null.
            value = services.template_for(draft.kind).print_product_descriptions
        elif name in {"introduction", "closing"} and value is None:
            value = ""
        elif name == "text_block_ids" and value is None:
            value = []
        setattr(draft, name, value)
    _check_draft_values(draft)
    draft.changed_at = timezone.now()
    draft.save()
    return draft


def drafts_queryset() -> Any:
    """The open drafts, the newest changed first (a query set: the API pages it)."""
    return DocumentDraft.objects.select_related("customer").order_by("-changed_at", "-id")


def drafts_for_list() -> list[DocumentDraft]:
    """The open drafts, the newest changed first, for the list of outgoing documents (one query)."""
    return list(drafts_queryset())


#: How many documents the page of a customer lists before it leads on to the list of all.
CUSTOMER_PAGE_LIMIT = 10


def customer_panel(rights: Any, customer: Any) -> dict[str, Any] | None:
    """What the page of a customer shows of his outgoing documents; ``None`` for who may not see them.

    The newest ones – with a project or without –, the open drafts and whether the user may make a new one.
    """
    if not may_see(rights):
        return None
    found = outgoing.documents().filter(customer=customer)
    return {
        "documents": list(
            found.select_related("project").defer("content").order_by("-issued_on", "-id")[:CUSTOMER_PAGE_LIMIT]
        ),
        "count": found.count(),
        "drafts": list(DocumentDraft.objects.filter(customer=customer).order_by("-changed_at", "-id")),
        "may_make": may_change(rights) and customer.is_active and not customer.is_anonymised,
    }


def delete_draft(draft: DocumentDraft) -> None:
    """Throw a draft away with its lines; no number was used up."""
    customer = draft.customer
    record_event(customer, "document.draft_deleted", {"kind": str(DocumentKind(draft.kind).label)})
    draft.lines.all().delete()
    draft.delete()


def discard_drafts_of(customer: Any) -> int:
    """Delete the drafts of a customer whose data is erased (KND-010); returns how many there were."""
    drafts = list(DocumentDraft.objects.filter(customer=customer))
    for draft in drafts:
        DraftLine.objects.filter(draft=draft).delete()
    DocumentDraft.objects.filter(customer=customer).delete()
    return len(drafts)


# --- The lines ----------------------------------------------------------------------------------------------


def _touch(draft: DocumentDraft) -> None:
    """Note that the draft changed (the list shows the newest first)."""
    DocumentDraft.objects.filter(pk=draft.pk).update(changed_at=timezone.now())


def product_price(product: Any) -> Decimal:
    """The net price a line takes from a product: the sale price of a sale product, else the price (PRD-047)."""
    from rentalars.products.models import ProductKind

    value = product.sale_price if product.kind == ProductKind.SALE else product.price
    return value if value is not None else ZERO


def check_product(product: Any) -> None:
    """Which products a line can be taken from: not the vehicles (priced per trip) and not the percentage surcharges.

    Raises:
        ValidationError: The product cannot be a line of a free document.
    """
    from rentalars.products.models import ProductKind, SurchargeType

    if product.owner_id:
        raise ValidationError({"product": _("The customer's own material is not sold.")})
    if product.kind == ProductKind.VEHICLE or (
        product.kind == ProductKind.SURCHARGE and product.surcharge_type == SurchargeType.PERCENT
    ):
        raise ValidationError({"product": _("This product cannot be a line here; enter the amount as a free line.")})


def _clean_line(line: DraftLine) -> None:
    """The rules of a line, shared by the page and the API."""
    errors: dict[str, str] = {}
    if not line.title.strip():
        errors["title"] = _("Enter a title.")
    if line.is_text:
        line.quantity, line.unit_price, line.discount_percent, line.unit = Decimal("1"), ZERO, ZERO, None
    else:
        if line.quantity < ZERO:
            errors["quantity"] = _("The quantity cannot be negative.")
        if line.unit_price < ZERO:
            errors["unit_price"] = _("The price cannot be negative.")
        if not ZERO <= line.discount_percent <= HUNDRED:
            errors["discount_percent"] = _("A discount is between 0 and 100 percent.")
    if errors:
        raise ValidationError(errors)


def add_line(
    draft: DocumentDraft,
    *,
    title: str = "",
    note: str = "",
    quantity: Decimal | None = None,
    unit: Any = None,
    unit_price: Decimal | None = None,
    tax_rate: Any = None,
    discount_percent: Decimal | None = None,
    product: Any = None,
    is_text: bool = False,
) -> DraftLine:
    """Add a line at the end of a draft: free, from a product, or a text line.

    From a product (:func:`check_product`) the line starts with the product's name, unit, price and tax rate;
    whatever is given besides replaces it. A free line without a tax rate takes the default one.

    Raises:
        ValidationError: A value does not fit.
    """
    from rentalars.masterdata.models import TaxRate

    if product is not None:
        check_product(product)
    line = DraftLine(draft=draft, product=product, is_text=is_text)
    line.title = (title or (product.name if product is not None else "")).strip()
    line.note = (note or "").strip()
    line.quantity = Decimal("1") if quantity is None else quantity
    line.unit = unit if unit is not None else (product.unit if product is not None else None)
    line.unit_price = unit_price if unit_price is not None else (product_price(product) if product else ZERO)
    line.tax_rate = tax_rate or (product.tax_rate if product is not None else None) or TaxRate.get_default()
    line.discount_percent = ZERO if discount_percent is None else discount_percent
    if line.tax_rate is None:
        raise ValidationError({"tax_rate": _("Choose the tax rate.")})
    _clean_line(line)
    last = draft.lines.order_by("-position").values_list("position", flat=True).first()
    line.position = (last or 0) + 1
    line.save()
    _touch(draft)
    return line


#: What :func:`update_line` changes.
LINE_FIELDS = ("title", "note", "quantity", "unit", "unit_price", "tax_rate", "discount_percent")


def update_line(line: DraftLine, **values: Any) -> DraftLine:
    """Change a line: its texts, quantity, unit, price, tax rate or discount.

    Raises:
        ValidationError: A value does not fit.
    """
    unknown = set(values) - set(LINE_FIELDS)
    if unknown:
        raise ValueError(f"Not changeable: {', '.join(sorted(unknown))}")
    for name, value in values.items():
        setattr(line, name, value.strip() if name in {"title", "note"} and value is not None else value)
    _clean_line(line)
    line.save()
    _touch(line.draft)
    return line


def delete_line(line: DraftLine) -> None:
    """Take a line out of its draft."""
    draft = line.draft
    line.delete()
    _touch(draft)


def move_line(line: DraftLine, step: int) -> None:
    """Move a line up (``step=-1``) or down (``1``) by swapping its place with the neighbour's."""
    lines = list(line.draft.lines.all())
    index = next(position for position, other in enumerate(lines) if other.pk == line.pk)
    target = index + step
    if not 0 <= target < len(lines):
        return
    lines[index], lines[target] = lines[target], lines[index]
    renumber(line.draft, lines)


def reorder_lines(draft: DocumentDraft, ids: list[int]) -> None:
    """Put the lines in the order of ``ids``; lines not named follow in their old order.

    Raises:
        ValidationError: An ID is no line of the draft.
    """
    lines = {line.pk: line for line in draft.lines.all()}
    unknown = [pk for pk in ids if pk not in lines]
    if unknown:
        raise ValidationError({"lines": _("These lines are not part of the draft: %(ids)s.") % {"ids": unknown}})
    ordered = [lines.pop(pk) for pk in dict.fromkeys(ids)] + list(lines.values())
    renumber(draft, ordered)


def renumber(draft: DocumentDraft, lines: list[DraftLine]) -> None:
    """Write the places 1, 2, 3 … in the order of ``lines`` (only where they differ)."""
    for place, line in enumerate(lines, start=1):
        if line.position != place:
            line.position = place
            line.save(update_fields=["position"])
    _touch(draft)


# --- Amounts ------------------------------------------------------------------------------------------------


@dataclass
class Priced:
    """A line with its amounts."""

    line: DraftLine
    number: str = ""
    base: Decimal = ZERO
    discount: Decimal = ZERO
    amount: Decimal = ZERO


@dataclass
class Calculation:
    """The amounts of a draft: per line, per tax rate, in total."""

    lines: list[Priced] = field(default_factory=list)
    taxes: list[builder.TaxShare] = field(default_factory=list)
    net_total: Decimal = ZERO
    tax_total: Decimal = ZERO
    gross_total: Decimal = ZERO

    @property
    def priced_lines(self) -> list[Priced]:
        """The lines that count, without the text lines."""
        return [priced for priced in self.lines if not priced.line.is_text]


def calculate(lines: list[DraftLine]) -> Calculation:
    """The amounts of some lines, as described in the module: line amounts, net and tax per rate, totals."""
    result = Calculation()
    counter = 0
    shares: dict[int, list[Any]] = {}
    for line in lines:
        priced = Priced(line)
        if not line.is_text:
            counter += 1
            priced.number = str(counter)
            priced.base = money(line.quantity * line.unit_price)
            priced.discount = percentage_of(priced.base, line.discount_percent)
            priced.amount = priced.base - priced.discount
            entry = shares.setdefault(line.tax_rate_id, [line.tax_rate, ZERO])
            entry[1] += priced.amount
        result.lines.append(priced)
    for rate, net in sorted(shares.values(), key=lambda entry: -entry[0].rate):
        tax = money(net * rate.rate / HUNDRED)
        result.taxes.append(
            builder.TaxShare(
                name=rate.name,
                percent=rate.rate,
                category=builder.tax_category(rate.rate),
                net=net,
                tax=tax,
                positions_total=net,
            )
        )
    result.net_total = sum((share.net for share in result.taxes), ZERO)
    result.tax_total = sum((share.tax for share in result.taxes), ZERO)
    result.gross_total = result.net_total + result.tax_total
    return result


def lines_of(draft: DocumentDraft) -> list[DraftLine]:
    """The lines in their order, with what the amounts and the content need (one query)."""
    return list(draft.lines.select_related("tax_rate", "unit", "product"))


# --- The content --------------------------------------------------------------------------------------------


def payment_terms(draft: DocumentDraft) -> int:
    """Days to pay: the draft's own, else the customer's, else the company's (KND-006)."""
    from rentalars.core.models import CompanyProfile

    if draft.payment_terms_days is not None:
        return draft.payment_terms_days
    if draft.customer.payment_terms_days is not None:
        return draft.customer.payment_terms_days
    return CompanyProfile.load().payment_terms_days


def recipient_lines(draft: DocumentDraft) -> list[str]:
    """Where the document goes: the chosen billing address, else the customer's own."""
    if draft.billing_address_id:
        return draft.billing_address.address_lines
    return draft.customer.address_lines


def build_content(
    draft: DocumentDraft, *, number: str, issued_on: datetime.date | None = None
) -> builder.DocumentContent:
    """Put the content of the document together from a draft – the frozen content of every document.

    The data classes are those of the documents of projects (``documents.content``), so the PDF, the XRechnung, the
    exports and a cancellation work on them unchanged. The positions form one section without heading and subtotal.
    Only a line taken from a product has a description of its own, and only if the draft asks for it.

    Raises:
        ValidationError: The validity of an offer does not fit.
    """
    kind = DocumentKind(draft.kind)
    issued_on = issued_on or draft.issued_on or timezone.localdate()
    customer = draft.customer
    offer_until = None
    if kind == DocumentKind.OFFER:
        offer_until = services.offer_valid_until(issued_on, draft.valid_until)
    with for_documents():  # UIX-029: the fixed texts in the language of the company's documents
        template = services.template_for(kind)
        calculation = calculate(lines_of(draft))
        positions = [_position(priced, draft) for priced in calculation.lines]
        contact = draft.contact
        content = builder.DocumentContent(
            kind=kind.value,
            title=template.title,
            number=number,
            issued_on=issued_on,
            company=builder.company_data(),
            recipient=recipient_lines(draft),
            # The head of a document prints the project number if there is one; here only the contact.
            project={
                "number": "",
                "name": "",
                "period": "",
                "venue": "",
                "contact": contact.name if contact else "",
                "manager": "",
            },
            recipient_email=(contact.email if contact and contact.email else customer.email),
            customer_number=customer.number,
            customer_vat_id=customer.vat_id,
            # As for a project (``customer.buyer_reference or project.number``): the customer number takes the project's
            # place. The free text ``reference`` is the subject line, not a buyer reference (XRechnung BT-10).
            buyer_reference=customer.buyer_reference or customer.number,
            service_start=draft.service_start,
            service_end=draft.service_end or draft.service_start,
            sections=[builder.Section(title="", positions=positions, subtotal=calculation.net_total, plain=True)]
            if positions
            else [],
            taxes=calculation.taxes,
            net_total=calculation.net_total,
            tax_total=calculation.tax_total,
            gross_total=calculation.gross_total,
            reference=draft.reference,
            print_product_descriptions=draft.print_product_descriptions,
        )
        validity = None
        if kind == DocumentKind.INVOICE:
            content.payment_terms_days = payment_terms(draft)
            content.due_on = issued_on + datetime.timedelta(days=content.payment_terms_days)
        if kind == DocumentKind.OFFER:
            content.valid_until = offer_until
            validity = (offer_until - issued_on).days
        values = builder.free_placeholder_values(
            customer,
            contact=contact,
            due_on=content.due_on,
            terms=content.payment_terms_days,
            valid_until=content.valid_until,
            validity_days=validity,
        )
        content.introduction = builder.fill(draft.introduction, values)
        content.closing = builder.fill(draft.closing, values)
        content.footer = template.footer
        if draft.text_block_ids:
            blocks = {
                block.pk: block
                for block in TextBlock.objects.filter(pk__in=draft.text_block_ids, is_active=True)
                if block.fits(kind)
            }
            content.text_blocks = [builder.fill(blocks[pk].text, values) for pk in draft.text_block_ids if pk in blocks]
    return content


def page_content(draft: DocumentDraft, calculation: Calculation) -> tuple[builder.DocumentContent | None, list[str]]:
    """The content the page of a draft checks, and what stops it from being built.

    A draft whose offer is no longer valid cannot be put together (``offer_valid_until`` refuses a date in the past);
    the page must stay open for editing all the same, so the reasons come back as messages instead of an error.
    Without a priced line there is nothing to check (``None``, no messages).
    """
    if not calculation.priced_lines:
        return None, []
    try:
        return build_content(draft, number=""), []
    except ValidationError as error:
        return None, error.messages


def placeholder_hints(draft: DocumentDraft) -> list[str]:
    """Hints about the placeholders of the texts that are not known and would print as written.

    "{customer.name}" or "{kunde}" is left as it stands in the document (it never stops the page or the issuing);
    the page names them so that the text can be corrected. Known placeholders: ``documents.content.free_placeholder_values``.
    """
    values = builder.free_placeholder_values(draft.customer, contact=draft.contact)
    texts = [draft.introduction, draft.closing]
    if draft.text_block_ids:
        texts += [
            block.text
            for block in TextBlock.objects.filter(pk__in=draft.text_block_ids, is_active=True)
            if block.fits(DocumentKind(draft.kind))
        ]
    found: list[str] = []
    for text in texts:
        for placeholder in builder.unknown_placeholders(text, values):
            if placeholder not in found:
                found.append(placeholder)
    if not found:
        return []
    return [
        _("The texts contain placeholders that are not known and print as written: %(items)s.")
        % {"items": ", ".join(found)}
    ]


def _position(priced: Priced, draft: DocumentDraft) -> builder.Position:
    """One line of the draft as a position of the document."""
    line = priced.line
    if line.is_text:
        return builder.Position(number="", title=line.title, details=line.note, line_id=line.pk, is_text=True)
    unit = line.unit.abbreviation if line.unit_id else ""
    return builder.Position(
        number=priced.number,
        title=line.title,
        article_number=line.product.article_number if line.product_id else "",
        quantity=line.quantity,
        unit=unit,
        unit_code=builder.unit_code(unit),
        # The line's own note: always printed, whatever is chosen for the descriptions of the products.
        details=line.note,
        unit_price=line.unit_price,
        discount_percent=line.discount_percent,
        base_amount=priced.base,
        discount_amount=priced.discount,
        amount=priced.amount,
        tax_name=line.tax_rate.name,
        tax_percent=line.tax_rate.rate,
        line_id=line.pk,
        description=builder.product_description(line.product) if draft.print_product_descriptions else "",
    )


# --- Checking, previewing, issuing ----------------------------------------------------------------------------


def problems(draft: DocumentDraft, content: builder.DocumentContent | None = None) -> list[str]:
    """Reasons that stop the draft from being issued; empty if none.

    A document needs a customer who is there, at least one line, and – an invoice – the data the electronic
    invoice requires.
    """
    from rentalars.documents.xrechnung import missing_data

    found: list[str] = []
    if draft.kind in services.INVOICE_KINDS and not services.invoices_enabled():
        return [services.invoices_off_message()]  # DOK-014: nothing else matters
    try:
        check_customer(draft.customer)
        _check_draft_values(draft)
    except ValidationError as error:
        found += error.messages
    if not draft.lines.filter(is_text=False).exists():
        found.append(_("Add at least one line with a price."))
    if draft.kind == DocumentKind.INVOICE and content is not None:
        missing = missing_data(content)
        if missing:
            found.append(_("For the electronic invoice, this is missing: %(items)s.") % {"items": ", ".join(missing)})
    return found


def preview(draft: DocumentDraft) -> bytes:
    """The PDF as it would come out, marked as draft; nothing is stored or counted.

    Raises:
        ValidationError: The draft cannot be issued (:func:`problems` without the data of the electronic invoice).
    """
    from rentalars.documents.pdf import render_pdf

    errors = problems(draft)
    if errors:
        raise ValidationError(errors)
    with for_documents():
        draft_number = _("DRAFT")
    content = build_content(draft, number=draft_number, issued_on=draft.issued_on or timezone.localdate())
    return render_pdf(content, services.template_for(draft.kind), draft=True)


@transaction.atomic
def issue(draft: DocumentDraft, *, user: Any = None) -> Document:
    """Turn the draft into a document for good: number, PDF, XRechnung, checksum – and the draft is gone.

    The number comes from the range of the kind, the same as for the documents of projects (ADM-003); it is taken
    only after everything was checked, so a refused draft uses none up. An invoice goes to the accounting at once
    when the settings say so (DOK-011).

    Raises:
        ValidationError: Something stops the document (:func:`problems`), or the draft is gone because somebody
            issued it a moment before (code ``already_issued``).
    """
    from rentalars.core.models import NumberRange
    from rentalars.documents.pdf import render_pdf
    from rentalars.documents.xrechnung import build_xml

    try:
        draft = (
            DocumentDraft.objects.select_for_update()
            .select_related("customer", "billing_address", "contact")
            .get(pk=draft.pk)
        )
    except DocumentDraft.DoesNotExist:
        # Two people issued it at the same moment: the second one finds it gone.
        raise ValidationError(_("This draft was already issued or deleted."), code="already_issued") from None
    errors = problems(draft)
    if errors:
        raise ValidationError(errors)
    content = build_content(draft, number="")
    errors = problems(draft, content)
    if errors:
        raise ValidationError(errors)
    _value, content.number = NumberRange.allocate(NUMBER_RANGE_OF[DocumentKind(draft.kind)])
    document = services._store(
        None,
        content,
        services.template_for(draft.kind),
        user=user,
        render=render_pdf,
        xml=build_xml,
        customer=draft.customer,
    )
    # The draft has served: it goes without a trace of its own – the document is the record.
    DraftLine.objects.filter(draft=draft).delete()
    DocumentDraft.objects.filter(pk=draft.pk).delete()
    from rentalars.material import sales

    sales.link_issued_invoice(draft.pk, document)  # The sale this draft was made for now names the invoice
    services._to_accounting(document, user)
    return document


def text_blocks_for(kind: str) -> list[TextBlock]:
    """The text blocks a draft of this kind can add."""
    return services.text_blocks_for(kind)
